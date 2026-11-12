from typing import List, Any, Optional

from pywinauto import Desktop
from pywinauto.uia_defines import NoPatternInterfaceError
import win32gui
import win32con

from elements.element import Element, INTERACTIVE_ELEMENTS, UIA_ROLE_MAP, Rect
from config import MIN_ELEMENT_WIDTH, MIN_ELEMENT_HEIGHT, log
import pythoncom
#
class WindowsWindow:
    def __init__(
        self,
        hwnd: int,
        title: str,
        rect: Rect,
        visible: bool,
        minimized: bool,
        window_obj: Any
    ):
        self.hwnd = hwnd
        self.title = title
        self.rect = rect
        self.visible = visible
        self.minimized = minimized
        self.window_obj = window_obj
        self._cached_elements: Optional[List[Element]] = None

    def get_elements(self) -> List[Element]:
        if self._cached_elements is not None:
            return self._cached_elements

        elements: List[Element] = []
        element_id = 0
        pythoncom.CoInitialize()
        try:
            try:
                descendants = self.window_obj.descendants()
            except Exception as e:
                log.warning(f"Не удалось получить descendants для окна '{self.title}': {e}")
                self._cached_elements = []
                return self._cached_elements

            for ctrl in descendants:
                try:
                    info = ctrl.element_info
                    rect = info.rectangle
                    width = rect.right - rect.left
                    height = rect.bottom - rect.top

                    if width < MIN_ELEMENT_WIDTH or height < MIN_ELEMENT_HEIGHT:
                        continue

                    if not info.enabled:
                        continue

                    control_type = info.control_type
                    role = UIA_ROLE_MAP.get(control_type, control_type.lower())
                    if role not in INTERACTIVE_ELEMENTS:
                        continue

                    text = info.name or ""

                    elements.append(
                        Element(
                            element_id,
                            role,
                            text,
                            (rect.left, rect.top, rect.right, rect.bottom)
                        )
                    )
                    element_id += 1

                except Exception:
                    continue

        finally:
            pythoncom.CoUninitialize()

            self._cached_elements = elements
            return elements


def get_all_windows() -> List[WindowsWindow]:
    desktop = Desktop(backend="uia")
    windows: List[WindowsWindow] = []

    for w in desktop.windows():
        try:
            rect_obj = w.rectangle()

            windows.append(
                WindowsWindow(
                    hwnd=w.handle,
                    title=w.window_text(),
                    rect=(
                        rect_obj.left,
                        rect_obj.top,
                        rect_obj.right,
                        rect_obj.bottom
                    ),
                    visible=w.is_visible(),
                    minimized=w.is_minimized(),
                    window_obj=w
                )
            )

        except NoPatternInterfaceError:
            log.warning(f"Окно без UIA паттернов: {w.window_text()}")
        except Exception as e:
            log.exception(f"Ошибка получения окна '{w.window_text()}': {e}")

    return windows


def get_z_order() -> List[int]:
    z: List[int] = []
    hwnd = win32gui.GetTopWindow(None)

    while hwnd:
        z.append(hwnd)
        hwnd = win32gui.GetWindow(hwnd, win32con.GW_HWNDNEXT)

    return z