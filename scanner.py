import os
import time
import random
from typing import List, Dict, Any

from concurrent.futures import ThreadPoolExecutor

from PIL import ImageDraw
from rtree import index

from config import (
    IS_WINDOWS,
    IS_LINUX,
    SCREENSHOT_DIR,
    JSON_DIR,
    TEXT_OFFSET_Y,
    COLOR_MIN,
    COLOR_MAX,
    log
)
from elements.element import Element
from core.geometry import rect_area, subtract_rects
from core.screenshot import take_screenshot
from core.json_serializer import save_json

if IS_WINDOWS:
    from platforms.windows import (
        collect_window_elements,
        get_all_windows,
        get_z_order
    )

elif IS_LINUX:
    from platforms.linux import LinuxWindow, get_all_windows, get_z_order



class DesktopScanner:
    def __init__(self):
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        os.makedirs(JSON_DIR, exist_ok=True)
        self._reset_state()

    def _reset_state(self):
        self.windows = []
        self.z_order: List[int] = []
        self.hwnd_to_window: Dict[int, Any] = {}
        self.screen_img = None
        self.screen_width = 0
        self.screen_height = 0
        self.covered_rects: List[Any] = []
        self.all_elements: List[Dict[str, Any]] = []
        self.unique_elements: Dict[Any, float] = {}
        self.element_global_id = 0

    def get_all_windows(self):
        if IS_WINDOWS:
            self.windows = get_all_windows()
        elif IS_LINUX:
            self.windows = get_all_windows()
        log.info(f"Найдено окон: {len(self.windows)}")

    def get_windows_z_order(self):
        if IS_WINDOWS:
            self.z_order = get_z_order()
        elif IS_LINUX:
            self.z_order = get_z_order(self.windows)
        self.hwnd_to_window = {w.hwnd: w for w in self.windows}

    def scan(self):
        log.info("Сканируем экран")
        self._reset_state()

        self.get_all_windows()
        self.get_windows_z_order()

        self.screen_img, self.screen_width, self.screen_height = take_screenshot()
        if self.screen_img is None:
            log.error("Скриншот не получен")
            return

        # --- Оптимизация: кэширование часто используемых объектов и функций ---
        screen_w = self.screen_width
        screen_h = self.screen_height
        inv_w = 1.0 / screen_w
        inv_h = 1.0 / screen_h

        covered_rects = self.covered_rects
        unique_elements = self.unique_elements
        all_elements = self.all_elements

        rtree_idx = index.Index()
        draw = ImageDraw.Draw(self.screen_img)
        draw_rect = draw.rectangle
        draw_text = draw.text

        rect_area_fn = rect_area
        subtract_rects_fn = subtract_rects
        rand_int = random.randint
        tuple_fn = tuple
        max_fn = max
        min_fn = min
        str_fn = str

        color_min = COLOR_MIN
        color_max = COLOR_MAX
        text_offset_y = TEXT_OFFSET_Y

        # Окна в правильном порядке
        windows_in_order = [
            self.hwnd_to_window[hwnd]
            for hwnd in self.z_order
            if hwnd in self.hwnd_to_window
        ]

        # Параллельный сбор элементов
        elements_map = {}

        visible_windows = [
            win for win in windows_in_order
            if win.visible and not win.minimized
        ]

        if IS_WINDOWS:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(collect_window_elements,visible_windows)
                elements_map = future.result()

        elif IS_LINUX:
            elements_map = {
                window.hwnd: window.get_elements()
                for window in visible_windows
            }

        # Основная обработка
        element_global_id = 0

        for win in windows_in_order:
            if not win.visible or win.minimized:
                continue

            elements = elements_map.get(win.hwnd, [])

            # Оптимизация: если элементов нет, всё равно добавляем окно в R-tree для корректного перекрытия последующих
            if not elements:
                rtree_idx.insert(len(covered_rects), win.rect)
                covered_rects.append(win.rect)
                continue

            win_rect = win.rect
            win_title = win.title

            for el in elements:
                vx1, vy1, vx2, vy2 = el.bbox

                if vx2 <= 0 or vy2 <= 0 or vx1 >= screen_w or vy1 >= screen_h:
                    continue

                # Клиппинг по окну
                vx1 = max_fn(vx1, win_rect[0])
                vy1 = max_fn(vy1, win_rect[1])
                vx2 = min_fn(vx2, win_rect[2])
                vy2 = min_fn(vy2, win_rect[3])

                if vx1 >= vx2 or vy1 >= vy2:
                    continue

                element_rect = (vx1, vy1, vx2, vy2)
                original_area = rect_area_fn(element_rect)

                overlapping_ids = tuple_fn(rtree_idx.intersection(element_rect))

                if not overlapping_ids:
                    best_rect = element_rect
                    visible_area = original_area

                else:
                    overlays = [
                        covered_rects[index]
                        for index in overlapping_ids
                    ]

                    visible_chunks = subtract_rects_fn(element_rect, overlays)

                    if not visible_chunks:
                        continue

                    visible_area = sum(rect_area_fn(chunk) for chunk in visible_chunks)

                    visibility_ratio = visible_area / original_area

                    if visibility_ratio < 0.15:
                        continue

                    best_rect = max_fn(visible_chunks, key=rect_area_fn)

                area = visible_area

                element_key = (win_title, el.type, el.text, el.bbox)

                if element_key in unique_elements:
                    if area <= unique_elements[element_key]:
                        continue

                unique_elements[element_key] = area

                ix1, iy1, ix2, iy2 = best_rect

                color = (
                    rand_int(color_min, color_max),
                    rand_int(color_min, color_max),
                    rand_int(color_min, color_max)
                )

                draw_rect([ix1, iy1, ix2, iy2], outline=color, width=2)
                draw_text((ix1, max(0, iy1 - text_offset_y)), str_fn(element_global_id), fill=color)

                norm_bbox = (
                    ix1 * inv_w,
                    iy1 * inv_h,
                    ix2 * inv_w,
                    iy2 * inv_h
                )

                all_elements.append({
                    "id": element_global_id,
                    "type": el.type,
                    "text": el.text,
                    "bbox": norm_bbox,
                    "window": win_title
                })

                element_global_id += 1

            rtree_idx.insert(len(covered_rects), win.rect)
            covered_rects.append(win.rect)

        self.element_global_id = element_global_id

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        img_path = os.path.join(SCREENSHOT_DIR, f"FULL_DESKTOP_{timestamp}.jpg")
        json_path = os.path.join(JSON_DIR, f"FULL_DESKTOP_{timestamp}.json")

        if self.screen_img.mode == "RGBA":
            self.screen_img = self.screen_img.convert("RGB")

        self.screen_img.save(img_path, format="JPEG", quality=85)
        save_json(json_path, {"elements": all_elements})

        log.info(f"Найдено элементов: {len(all_elements)}")