from dataclasses import dataclass
from typing import Tuple

# Тип прямоугольника
Rect = Tuple[int, int, int, int]

LINUX_ROLE_MAP = {

    # Buttons
    "push button": "button",
    "toggle button": "button",
    "button": "button",

    # Inputs
    "text": "input",
    "entry": "input",
    "password text": "input",
    "spin button": "input",

    # Checkboxes
    "check box": "checkbox",
    "check menu item": "checkbox",

    # Radio
    "radio button": "radio",

    # Select / dropdown
    "combo box": "select",
    "list item": "option",

    # Tabs
    "page tab": "tab",

    # Menus
    "menu item": "menuitem",

    # Links
    "link": "link",

    # Scroll
    "scroll bar": "scrollbar",

    # Sliders
    "slider": "slider",

    # Trees
    "tree item": "treeitem",

    # Terminal
    "terminal": "terminal",

    # --- CONTAINERS (не рисуем) ---
    "panel": "container",
    "frame": "container",
    "dialog": "container",
    "tool bar": "container",
    "filler": "container",
    "scroll pane": "container",
    "menu": "container",
    "menu bar": "container",
    "list": "container",
    "page tab list": "container",
    "table": "container",
    "table cell": "container",
    "tree": "container",
    "label": "container",
    "separator": "container",
}



INTERACTIVE_ELEMENTS = {
    "button",
    "input",
    "textarea",
    "select",
    "link",
    "span"
}


UIA_ROLE_MAP = {
    "Button": "button",
    "Edit": "input",
    "Hyperlink": "link",
    "ComboBox": "select",
    "Text": "span",
    "ToggleButton": "button",
    "SplitButton": "button",
    "MenuItem": "button",
    "TabItem": "button",
    "Tab": "button",
    "ListItem": "button",
    "DataItem": "button",
    "TreeItem": "span", # элементы дерева (диски, папки)
}

@dataclass(frozen=True)
class Element:
    id: int
    type: str
    text: str
    bbox: Rect
