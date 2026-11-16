import ctypes
import logging
import queue
import sys
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


sys.coinit_flags = 0
logging.getLogger("comtypes").setLevel(logging.WARNING)

import comtypes
import comtypes.client
import pythoncom
import win32api
import win32con
import win32gui
import win32process

from ..config import MIN_ELEMENT_HEIGHT, MIN_ELEMENT_WIDTH, log
from ..elements.element import Element, INTERACTIVE_ELEMENTS, UIA_ROLE_MAP, Rect


DWMWA_CLOAKED = 14


def _enable_per_monitor_dpi_awareness():
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except (AttributeError, OSError):
        pass

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


_enable_per_monitor_dpi_awareness()


@dataclass(frozen=True)
class WindowsWindow:
    hwnd: int
    title: str
    rect: Rect
    visible: bool
    minimized: bool
    class_name: str
    process_id: int
    cloaked: bool
    occludes: bool


@dataclass(frozen=True)
class UIAScanBatch:
    elements: Dict[int, List[Element]]
    window_times_ms: Dict[int, float]
    skipped_hwnds: Tuple[int, ...]
    elapsed_ms: float


def _is_cloaked(hwnd: int) -> bool:
    value = ctypes.c_int(0)
    try:
        result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            hwnd,
            DWMWA_CLOAKED,
            ctypes.byref(value),
            ctypes.sizeof(value)
        )
        return result == 0 and bool(value.value)
    except (AttributeError, OSError):
        return False


def _window_occludes(hwnd: int) -> bool:
    try:
        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    except Exception:
        return True
    return not bool(ex_style & win32con.WS_EX_TRANSPARENT)


class WindowsUIAClient:
    def __init__(self):
        self.uia_module = comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient

        self.automation = comtypes.CoCreateInstance(
            UIAutomationClient.CUIAutomation().IPersist_GetClassID(),
            interface=UIAutomationClient.IUIAutomation,
            clsctx=comtypes.CLSCTX_INPROC_SERVER
        )
        self.control_types_by_id: Dict[int, str] = {}
        self.condition = self._create_condition()
        self.cache_request = self._create_cache_request()

    def _create_condition(self):
        type_conditions = []
        for control_type, role in UIA_ROLE_MAP.items():
            if role not in INTERACTIVE_ELEMENTS:
                continue
            constant_name = f"UIA_{control_type}ControlTypeId"
            if not hasattr(self.uia_module, constant_name):
                continue
            control_type_id = getattr(self.uia_module, constant_name)
            self.control_types_by_id[control_type_id] = control_type
            condition = self.automation.CreatePropertyCondition(self.uia_module.UIA_ControlTypePropertyId, control_type_id)
            type_conditions.append(condition)

        if not type_conditions:
            raise RuntimeError("No supported UIA control types configured")

        type_condition = (
            type_conditions[0]
            if len(type_conditions) == 1
            else self.automation.CreateOrConditionFromArray(type_conditions)
        )
        enabled_condition = self.automation.CreatePropertyCondition(self.uia_module.UIA_IsEnabledPropertyId, True)
        onscreen_condition = self.automation.CreatePropertyCondition(self.uia_module.UIA_IsOffscreenPropertyId, False)
        return self.automation.CreateAndConditionFromArray([type_condition, enabled_condition, onscreen_condition])

    def _create_cache_request(self):
        cache = self.automation.CreateCacheRequest()
        for property_id in (
            self.uia_module.UIA_ControlTypePropertyId,
            self.uia_module.UIA_NamePropertyId,
            self.uia_module.UIA_BoundingRectanglePropertyId,
            self.uia_module.UIA_IsEnabledPropertyId,
            self.uia_module.UIA_IsOffscreenPropertyId
        ):
            cache.AddProperty(property_id)
        cache.TreeScope = self.uia_module.TreeScope_Element
        cache.TreeFilter = self.automation.ControlViewCondition
        cache.AutomationElementMode = self.uia_module.AutomationElementMode_None
        return cache

    def get_elements(self, hwnd: int) -> List[Element]:
        try:
            root = self.automation.ElementFromHandle(hwnd)
            found = root.FindAllBuildCache(
                self.uia_module.TreeScope_Descendants,
                self.condition,
                self.cache_request
            )
        except Exception as error:
            log.warning("Не удалось получить UIA-элементы HWND %s: %s", hwnd, error)
            return []

        elements: List[Element] = []
        for index in range(found.Length):
            try:
                item = found.GetElement(index)
                control_type = self.control_types_by_id.get(item.CachedControlType)
                if control_type is None:
                    continue
                rect = item.CachedBoundingRectangle
                width = rect.right - rect.left
                height = rect.bottom - rect.top
                if width < MIN_ELEMENT_WIDTH or height < MIN_ELEMENT_HEIGHT:
                    continue
                elements.append(
                    Element(
                        id=0,
                        type=UIA_ROLE_MAP.get(control_type, control_type.lower()),
                        text=item.CachedName or "",
                        bbox=(rect.left, rect.top, rect.right, rect.bottom)
                    )
                )
            except Exception as error:
                log.debug(
                    "Ошибка UIA-элемента HWND %s, index %s: %s",
                    hwnd,
                    index,
                    error
                )
                continue

        return sorted(
            elements,
            key=lambda item: (
                item.bbox[1], item.bbox[0], item.bbox[3], item.bbox[2],
                item.type, item.text
            )
        )


class WindowsUIAWorker:
    def __init__(self):
        self._requests = queue.Queue()
        self._ready = threading.Event()
        self._startup_error: Optional[BaseException] = None
        self.initialization_ms = 0.0
        self._thread = threading.Thread(
            target=self._run,
            name="ui-scanner-uia",
            daemon=True
        )
        self._thread.start()
        self._ready.wait()
        if self._startup_error is not None:
            raise RuntimeError("Failed to initialize Windows UI Automation") from self._startup_error

    def _run(self):
        started = time.perf_counter()
        pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
        client = None
        try:
            try:
                client = WindowsUIAClient()
                self.initialization_ms = (time.perf_counter() - started) * 1000.0
            except BaseException as error:
                self._startup_error = error
                return
            finally:
                self._ready.set()

            while True:
                request = self._requests.get()
                if request is None:
                    break
                windows, budget_ms, future = request
                if future.set_running_or_notify_cancel():
                    try:
                        future.set_result(self._collect(client, windows, budget_ms))
                    except BaseException as error:
                        future.set_exception(error)
        finally:
            client = None
            pythoncom.CoUninitialize()

    @staticmethod
    def _collect(
        client: WindowsUIAClient,
        windows: List[WindowsWindow],
        budget_ms: Optional[float]
    ) -> UIAScanBatch:
        started = time.perf_counter()
        elements: Dict[int, List[Element]] = {}
        window_times: Dict[int, float] = {}
        skipped: List[int] = []

        for position, window in enumerate(windows):
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if budget_ms is not None and elapsed_ms >= budget_ms:
                skipped.extend(item.hwnd for item in windows[position:])
                break
            window_started = time.perf_counter()
            window_elements = client.get_elements(window.hwnd)

            width = max(0, window.rect[2] - window.rect[0])
            height = max(0, window.rect[3] - window.rect[1])
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if (
                len(window_elements) <= 3
                and bool(window.title)
                and width * height >= 100_000
                and (budget_ms is None or elapsed_ms + 5.0 < budget_ms)
            ):
                time.sleep(0.005)
                retried = client.get_elements(window.hwnd)
                if len(retried) > len(window_elements):
                    window_elements = retried

            elements[window.hwnd] = window_elements
            window_times[window.hwnd] = (
                time.perf_counter() - window_started
            ) * 1000.0

        return UIAScanBatch(
            elements=elements,
            window_times_ms=window_times,
            skipped_hwnds=tuple(skipped),
            elapsed_ms=(time.perf_counter() - started) * 1000.0
        )

    def submit(self, windows: List[WindowsWindow], budget_ms: Optional[float]) -> Future:
        future = Future()
        self._requests.put((windows, budget_ms, future))
        return future

    def close(self, timeout: float = 1.0) -> bool:
        if not self._thread.is_alive():
            return True
        self._requests.put(None)
        self._thread.join(timeout)
        return not self._thread.is_alive()


def get_all_windows() -> List[WindowsWindow]:
    windows: List[WindowsWindow] = []

    def callback(hwnd, _):
        try:
            rect = win32gui.GetWindowRect(hwnd)
            _, process_id = win32process.GetWindowThreadProcessId(hwnd)
            windows.append(
                WindowsWindow(
                    hwnd=hwnd,
                    title=win32gui.GetWindowText(hwnd),
                    rect=rect,
                    visible=bool(win32gui.IsWindowVisible(hwnd)),
                    minimized=bool(win32gui.IsIconic(hwnd)),
                    class_name=win32gui.GetClassName(hwnd),
                    process_id=process_id,
                    cloaked=_is_cloaked(hwnd),
                    occludes=_window_occludes(hwnd)
                )
            )
        except Exception as error:
            log.debug("Ошибка получения окна HWND %s: %s", hwnd, error)
        return True

    win32gui.EnumWindows(callback, None)
    return windows


def get_z_order() -> List[int]:
    result: List[int] = []
    hwnd = win32gui.GetTopWindow(None)
    while hwnd:
        result.append(hwnd)
        hwnd = win32gui.GetWindow(hwnd, win32con.GW_HWNDNEXT)
    return result


def get_virtual_screen_rect() -> Rect:
    left = win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
    top = win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
    width = win32api.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN)
    height = win32api.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN)
    return left, top, left + width, top + height
