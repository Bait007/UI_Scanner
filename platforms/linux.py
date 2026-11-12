from typing import List, Tuple, Any, Optional
import pyatspi

from elements.element import Element, LINUX_ROLE_MAP
from config import MIN_ELEMENT_WIDTH, MIN_ELEMENT_HEIGHT, log

Rect = Tuple[int, int, int, int]


class LinuxWindow:

    def __init__(self, hwnd: int, title: str, rect: Rect,
                 visible: bool, minimized: bool, window_obj: Any):

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

        def walk(node):
            nonlocal element_id

            try:

                role = node.getRoleName().lower()
                mapped_role = LINUX_ROLE_MAP.get(role, role)

                # некоторые элементы не имеют component interface
                try:
                    comp = node.queryComponent()
                    ext = comp.getExtents(pyatspi.DESKTOP_COORDS)

                    x, y = ext.x, ext.y
                    w, h = ext.width, ext.height

                except Exception:
                    x = y = w = h = 0

                if w < MIN_ELEMENT_WIDTH or h < MIN_ELEMENT_HEIGHT:
                    pass

                text = node.name or ""

                # исключаем определенные элементы
                if mapped_role not in {"container", "image", "heading", "section", "landmark", "document web", "internal frame"}:
                    elements.append(
                        Element(
                            element_id,
                            mapped_role,
                            text,
                            (x, y, x + w, y + h)
                        )
                    )

                    element_id += 1

                # рекурсивный обход
                for i in range(node.childCount):
                    child = node.getChildAtIndex(i)
                    walk(child)

            except Exception as e:
                log.debug(f"AT-SPI element error: {e}")

        try:
            walk(self.window_obj)
        except Exception as e:
            log.warning(f"Ошибка при обходе окна '{self.title}': {e}")

        self._cached_elements = elements

        log.debug(f"Найдено элементов в окне '{self.title}': {len(elements)}")

        return elements


# получение всех окон
def get_all_windows() -> List[LinuxWindow]:
    windows: List[LinuxWindow] = []

    try:
        desktop = pyatspi.Registry.getDesktop(0)
    except Exception as e:
        log.exception(f"AT-SPI недоступен: {e}")
        return windows

    for i in range(desktop.childCount):

        app = desktop.getChildAtIndex(i)

        for j in range(app.childCount):

            try:
                win = app.getChildAtIndex(j)

                role = win.getRoleName()

                if role not in ("frame", "window", "dialog"):
                    continue

                comp = win.queryComponent()
                ext = comp.getExtents(pyatspi.DESKTOP_COORDS)

                x, y = ext.x, ext.y
                w, h = ext.width, ext.height

                if w < MIN_ELEMENT_WIDTH or h < MIN_ELEMENT_HEIGHT:
                    continue

                windows.append(
                    LinuxWindow(
                        hwnd=id(win),
                        title=win.name or app.name,
                        rect=(x, y, x + w, y + h),
                        visible=True,
                        minimized=False,
                        window_obj=win
                    )
                )

            except Exception as e:
                log.debug(f"Ошибка получения окна: {e}")
                continue

    log.info(f"AT-SPI окон найдено: {len(windows)}")

    return windows


# примерный Z-order
def get_z_order(windows: List[LinuxWindow]) -> List[int]:
    return [w.hwnd for w in sorted(windows, key=lambda win: (win.rect[1], win.rect[0]))]