import hashlib
import os
import time
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from PIL import Image, ImageDraw

from .config import (
    COLOR_MAX,
    COLOR_MIN,
    IS_LINUX,
    IS_WINDOWS,
    JSON_DIR,
    MIN_VISIBLE_RATIO,
    MIN_VISIBLE_WINDOW_AREA,
    SCREENSHOT_DIR,
    TEXT_OFFSET_Y,
    UIA_SCAN_BUDGET_MS,
    UIA_HARD_TIMEOUT_MS,
    log
)
from .core.geometry import intersect_rect, rect_area, subtract_rects
from .core.json_serializer import save_json
from .core.screenshot import take_screenshot
from .elements.element import Element, Rect

if IS_WINDOWS:
    from .platforms.windows import (
        WindowsUIAWorker,
        get_all_windows,
        get_virtual_screen_rect,
        get_z_order
    )
elif IS_LINUX:
    from .platforms.linux import get_all_windows, get_z_order


def _deduplicate_elements(elements: Iterable[Element]) -> List[Element]:
    unique: Dict[Tuple[str, str, Rect], Element] = {}
    for element in elements:
        unique.setdefault((element.type, element.text, element.bbox), element)

    return sorted(
        unique.values(),
        key=lambda item: (
            item.bbox[1], item.bbox[0], item.bbox[3], item.bbox[2],
            item.type, item.text
        )
    )


def _deterministic_color(key: str) -> Tuple[int, int, int]:
    digest = hashlib.blake2b(key.encode("utf-8"), digest_size=3).digest()
    span = COLOR_MAX - COLOR_MIN + 1
    return tuple(COLOR_MIN + value % span for value in digest)


def _select_visible_windows(windows_in_order: List[Any], screen_rect: Rect) -> List[Any]:
    selected: List[Any] = []
    covered: List[Rect] = []

    for window in windows_in_order:
        if not window.visible or window.minimized or getattr(window, "cloaked", False):
            continue

        clipped = intersect_rect(window.rect, screen_rect)
        if clipped is None:
            continue

        visible_chunks = subtract_rects(clipped, covered)
        visible_area = sum(rect_area(chunk) for chunk in visible_chunks)
        if visible_area < MIN_VISIBLE_WINDOW_AREA:
            continue

        selected.append(window)
        if getattr(window, "occludes", True):
            covered.append(clipped)

    return selected


class DesktopScanner:
    def __init__(self, save_outputs: bool = True):
        self.save_outputs = save_outputs
        if save_outputs:
            os.makedirs(SCREENSHOT_DIR, exist_ok=True)
            os.makedirs(JSON_DIR, exist_ok=True)

        self._uia_worker: Optional[Any] = None
        if IS_WINDOWS:
            self._uia_worker = WindowsUIAWorker()

        self._reset_state()

    def close(self):
        if self._uia_worker is not None:
            if not self._uia_worker.close():
                log.warning("UIA worker did not stop within the timeout")
            self._uia_worker = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _reset_state(self):
        self.windows: List[Any] = []
        self.z_order: List[int] = []
        self.hwnd_to_window: Dict[int, Any] = {}
        self.screen_img: Optional[Image.Image] = None
        self.screen_left = 0
        self.screen_top = 0
        self.screen_width = 0
        self.screen_height = 0
        self.all_elements: List[Dict[str, Any]] = []
        self.element_global_id = 0
        self.timings: Dict[str, float] = {}

    def _load_windows(self):
        self.windows = get_all_windows()
        self.z_order = get_z_order() if IS_WINDOWS else get_z_order(self.windows)
        self.hwnd_to_window = {window.hwnd: window for window in self.windows}
        return [
            self.hwnd_to_window[hwnd]
            for hwnd in self.z_order
            if hwnd in self.hwnd_to_window
        ]

    def scan(self) -> Dict[str, Any]:
        total_started = time.perf_counter()
        self._reset_state()
        log.info("Сканируем экран")

        stage_started = time.perf_counter()
        windows_in_order = self._load_windows()
        self.timings["windows_ms"] = (time.perf_counter() - stage_started) * 1000.0

        if IS_WINDOWS:
            desktop_rect = get_virtual_screen_rect()
            visible_windows = _select_visible_windows(windows_in_order, desktop_rect)
            uia_future = self._uia_worker.submit(visible_windows, UIA_SCAN_BUDGET_MS)
        else:
            visible_windows = [
                window
                for window in windows_in_order
                if window.visible and not window.minimized
            ]
            uia_future = None

        log.info(
            "Окон ОС: %d; реально видимых для сканирования: %d",
            len(self.windows),
            len(visible_windows)
        )

        stage_started = time.perf_counter()
        (
            self.screen_img,
            self.screen_left,
            self.screen_top,
            self.screen_width,
            self.screen_height
        ) = take_screenshot()
        self.timings["screenshot_ms"] = (time.perf_counter() - stage_started) * 1000.0

        if self.screen_img is None:
            raise RuntimeError("Скриншот не получен")

        if IS_WINDOWS:
            try:
                batch = uia_future.result(timeout=UIA_HARD_TIMEOUT_MS / 1000.0)
            except FutureTimeoutError:
                log.error("UIA hard timeout after %.0f ms", UIA_HARD_TIMEOUT_MS)
                elements_map = {}
                self.timings["uia_ms"] = UIA_HARD_TIMEOUT_MS
            else:
                elements_map = batch.elements
                self.timings["uia_ms"] = batch.elapsed_ms
                if batch.skipped_hwnds:
                    log.warning("UIA budget exhausted; skipped windows: %d", len(batch.skipped_hwnds))
                for hwnd, duration in sorted(
                    batch.window_times_ms.items(),
                    key=lambda item: item[1],
                    reverse=True
                ):
                    if duration >= 5.0:
                        window = self.hwnd_to_window.get(hwnd)
                        log.info(
                            "UIA %.1f ms: %s",
                            duration,
                            repr(window.title if window else hwnd)
                        )
        else:
            stage_started = time.perf_counter()
            elements_map = {
                window.hwnd: window.get_elements()
                for window in visible_windows
            }
            self.timings["uia_ms"] = (time.perf_counter() - stage_started) * 1000.0

        stage_started = time.perf_counter()
        screen_rect = (
            self.screen_left,
            self.screen_top,
            self.screen_left + self.screen_width,
            self.screen_top + self.screen_height
        )
        covered_rects: List[Rect] = []
        candidates: List[Dict[str, Any]] = []

        for window_index, window in enumerate(visible_windows):
            window_rect = intersect_rect(window.rect, screen_rect)
            if window_rect is None:
                continue

            elements = _deduplicate_elements(elements_map.get(window.hwnd, []))
            for element in elements:
                element_rect = intersect_rect(element.bbox, window_rect)
                if element_rect is None:
                    continue

                overlays = [
                    overlay
                    for overlay in covered_rects
                    if intersect_rect(element_rect, overlay) is not None
                ]
                visible_chunks = subtract_rects(element_rect, overlays)
                if not visible_chunks:
                    continue

                original_area = rect_area(element_rect)
                visible_area = sum(rect_area(chunk) for chunk in visible_chunks)
                if visible_area / original_area < MIN_VISIBLE_RATIO:
                    continue

                click_rect = max(visible_chunks, key=rect_area)
                candidates.append(
                    {
                        "window_index": window_index,
                        "window": window.title,
                        "type": element.type,
                        "text": element.text,
                        "bbox_px": click_rect
                    }
                )

            if getattr(window, "occludes", True):
                covered_rects.append(window_rect)

        candidates.sort(
            key=lambda item: (
                item["window_index"],
                item["bbox_px"][1],
                item["bbox_px"][0],
                item["type"],
                item["text"]
            )
        )

        draw = ImageDraw.Draw(self.screen_img)
        inv_width = 1.0 / self.screen_width
        inv_height = 1.0 / self.screen_height
        all_elements: List[Dict[str, Any]] = []

        for element_id, candidate in enumerate(candidates):
            x1, y1, x2, y2 = candidate["bbox_px"]
            local_rect = (
                x1 - self.screen_left,
                y1 - self.screen_top,
                x2 - self.screen_left,
                y2 - self.screen_top
            )
            key = (
                f"{candidate['window']}|{candidate['type']}|"
                f"{candidate['text']}|{candidate['bbox_px']}"
            )
            color = _deterministic_color(key)
            draw.rectangle(local_rect, outline=color, width=2)
            draw.text(
                (local_rect[0], max(0, local_rect[1] - TEXT_OFFSET_Y)),
                str(element_id),
                fill=color
            )
            all_elements.append(
                {
                    "id": element_id,
                    "type": candidate["type"],
                    "text": candidate["text"],
                    "bbox": (
                        local_rect[0] * inv_width,
                        local_rect[1] * inv_height,
                        local_rect[2] * inv_width,
                        local_rect[3] * inv_height
                    ),
                    "window": candidate["window"]
                }
            )

        self.all_elements = all_elements
        self.element_global_id = len(all_elements)
        self.timings["processing_ms"] = (time.perf_counter() - stage_started) * 1000.0
        self.timings["capture_ms"] = (time.perf_counter() - total_started) * 1000.0

        image_path = None
        json_path = None
        persist_started = time.perf_counter()
        if self.save_outputs:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            image_path = os.path.join(SCREENSHOT_DIR, f"FULL_DESKTOP_{timestamp}.jpg")
            json_path = os.path.join(JSON_DIR, f"FULL_DESKTOP_{timestamp}.json")
            self.screen_img.save(image_path, format="JPEG", quality=85)
            save_json(json_path, {"elements": all_elements}, pretty=True)

        self.timings["persist_ms"] = (time.perf_counter() - persist_started) * 1000.0
        self.timings["total_ms"] = (time.perf_counter() - total_started) * 1000.0

        log.info("Найдено элементов: %d", len(all_elements))
        log.info(
            "Время: capture %.1f ms; persist %.1f ms; total %.1f ms "
            "(screenshot %.1f; UIA %.1f; processing %.1f)",
            self.timings["capture_ms"],
            self.timings["persist_ms"],
            self.timings["total_ms"],
            self.timings["screenshot_ms"],
            self.timings["uia_ms"],
            self.timings["processing_ms"]
        )

        return {
            "elements": all_elements,
            "timings_ms": dict(self.timings),
            "image_path": image_path,
            "json_path": json_path
        }
