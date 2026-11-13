from typing import List, Tuple, Any, Optional
import pyatspi

from ..elements.element import Element, LINUX_ROLE_MAP
from ..config import MIN_ELEMENT_WIDTH, MIN_ELEMENT_HEIGHT, log

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
                    return

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

                try:
                    state = win.getState()
                    visible = state.contains(pyatspi.STATE_VISIBLE) and state.contains(
                        pyatspi.STATE_SHOWING
                    )
                    iconified_state = getattr(pyatspi, "STATE_ICONIFIED", None)
                    minimized = (
                        state.contains(iconified_state)
                        if iconified_state is not None
                        else False
                    )
                except Exception:
                    visible = True
                    minimized = False

                if w < MIN_ELEMENT_WIDTH or h < MIN_ELEMENT_HEIGHT:
                    continue

                windows.append(
                    LinuxWindow(
                        hwnd=id(win),
                        title=win.name or app.name,
                        rect=(x, y, x + w, y + h),
                        visible=visible,
                        minimized=minimized,
                        window_obj=win
                    )
                )

            except Exception as e:
                log.debug(f"Ошибка получения окна: {e}")
                continue

    log.info(f"AT-SPI окон найдено: {len(windows)}")

    return windows


def get_z_order(windows: List[LinuxWindow]) -> List[int]:
    try:
        from ewmh import EWMH

        ewmh = EWMH()
        stacking = list(ewmh.getClientListStacking() or [])
        unused = list(windows)
        result: List[int] = []

        for x_window in reversed(stacking):
            title = ewmh.getWmName(x_window)
            if isinstance(title, bytes):
                title = title.decode("utf-8", errors="replace")

            match = next((window for window in unused if window.title == title), None)
            if match is not None:
                result.append(match.hwnd)
                unused.remove(match)

        result.extend(
            window.hwnd
            for window in sorted(unused, key=lambda item: (item.rect[1], item.rect[0]))
        )
        return result
    except Exception as error:
        log.debug("Не удалось получить EWMH Z-order: %s", error)
        return [
            window.hwnd
            for window in sorted(windows, key=lambda item: (item.rect[1], item.rect[0]))
        ]
