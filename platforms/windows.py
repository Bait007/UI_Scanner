import sys
sys.coinit_flags = 0

from dataclasses import dataclass
from typing import Dict, List

import pythoncom
import comtypes
import comtypes.client

import win32con
import win32gui

from config import MIN_ELEMENT_HEIGHT, MIN_ELEMENT_WIDTH, log
from elements.element import (
    Element,
    INTERACTIVE_ELEMENTS,
    UIA_ROLE_MAP,
    Rect
)

@dataclass(frozen=True)
class WindowsWindow:
    hwnd: int
    title: str
    rect: Rect
    visible: bool
    minimized: bool


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

            type_conditions.append(
                self.automation.CreatePropertyCondition(self.uia_module.UIA_ControlTypePropertyId, control_type_id))

        type_condition = (
            type_conditions[0]
            if len(type_conditions) == 1
            else self.automation.CreateOrConditionFromArray(type_conditions)
        )

        enabled_condition = (
            self.automation.CreatePropertyCondition(
                self.uia_module.UIA_IsEnabledPropertyId,
                True
            )
        )

        onscreen_condition = (
            self.automation.CreatePropertyCondition(
                self.uia_module.UIA_IsOffscreenPropertyId,
                False
            )
        )

        return self.automation.CreateAndConditionFromArray([
            type_condition,
            enabled_condition,
            onscreen_condition
        ])

    def _create_cache_request(self):
        cache = self.automation.CreateCacheRequest()

        property_ids = (
            self.uia_module.UIA_ControlTypePropertyId,
            self.uia_module.UIA_NamePropertyId,
            self.uia_module.UIA_BoundingRectanglePropertyId,
            self.uia_module.UIA_IsEnabledPropertyId,
            self.uia_module.UIA_IsOffscreenPropertyId
        )

        for property_id in property_ids:
            cache.AddProperty(property_id)

        # Кешируем сами найденные элементы.
        cache.TreeScope = self.uia_module.TreeScope_Element
        cache.TreeFilter = self.automation.ControlViewCondition

        # Возвращаем snapshot без живых UIA-ссылок.
        cache.AutomationElementMode = (self.uia_module.AutomationElementMode_None)

        return cache

    def get_elements(self, hwnd: int) -> List[Element]:
        elements: List[Element] = []

        try:
            root = self.automation.ElementFromHandle(hwnd)

            found = root.FindAllBuildCache(
                self.uia_module.TreeScope_Descendants,
                self.condition,
                self.cache_request
            )

        except Exception as error:
            log.warning(
                "Не удалось получить UIA-элементы HWND %s: %s",
                hwnd,
                error
            )
            return elements

        for index in range(found.Length):
            try:
                item = found.GetElement(index)

                control_type = self.control_types_by_id.get(item.CachedControlType)

                if control_type is None:
                    continue

                role = UIA_ROLE_MAP.get(
                    control_type,
                    control_type.lower()
                )

                rect = item.CachedBoundingRectangle

                width = rect.right - rect.left
                height = rect.bottom - rect.top

                if (width < MIN_ELEMENT_WIDTH) or (height < MIN_ELEMENT_HEIGHT):
                    continue

                elements.append(
                    Element(
                        id=len(elements),
                        type=role,
                        text=item.CachedName or "",
                        bbox=(
                            rect.left,
                            rect.top,
                            rect.right,
                            rect.bottom
                        )
                    )
                )

            except Exception:
                continue

        return elements


def collect_window_elements(windows: List[WindowsWindow]) -> Dict[int, List[Element]]:
    pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
    client = None

    try:
        client = WindowsUIAClient()
        return {
            window.hwnd: client.get_elements(window.hwnd)
            for window in windows
        }

    finally:
        client = None
        pythoncom.CoUninitialize()


def get_all_windows() -> List[WindowsWindow]:
    windows: List[WindowsWindow] = []

    def callback(hwnd, _ ):
        try:
            rect = win32gui.GetWindowRect(hwnd)

            windows.append(
                WindowsWindow(
                    hwnd=hwnd,
                    title=win32gui.GetWindowText(hwnd),
                    rect=rect,
                    visible=bool(win32gui.IsWindowVisible(hwnd)),
                    minimized=bool(win32gui.IsIconic(hwnd))
                )
            )

        except Exception as error:
            log.debug(
                "Ошибка получения окна HWND %s: %s",
                hwnd,
                error
            )

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
