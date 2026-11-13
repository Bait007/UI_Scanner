import unittest
from dataclasses import dataclass

from ui_scanner.core.geometry import rect_area, subtract_rects
from ui_scanner.elements.element import Element
from ui_scanner.scanner import _deduplicate_elements, _select_visible_windows


@dataclass(frozen=True)
class FakeWindow:
    hwnd: int
    rect: tuple
    visible: bool = True
    minimized: bool = False
    cloaked: bool = False
    occludes: bool = True


class GeometryTests(unittest.TestCase):
    def test_subtract_center(self):
        chunks = subtract_rects((0, 0, 10, 10), [(2, 2, 8, 8)])
        self.assertEqual(sum(map(rect_area, chunks)), 64)

    def test_full_cover(self):
        self.assertEqual(subtract_rects((0, 0, 10, 10), [(0, 0, 10, 10)]), [])


class ElementFilterTests(unittest.TestCase):
    def test_only_exact_duplicates_are_removed(self):
        elements = [
            Element(0, "button", "Chat row", (0, 0, 200, 40)),
            Element(1, "button", "Chat row", (0, 0, 200, 40)),
            Element(2, "button", "Rename", (150, 5, 170, 25)),
            Element(3, "button", "Separate", (220, 0, 260, 40))
        ]
        filtered = _deduplicate_elements(elements)
        self.assertEqual([item.text for item in filtered], ["Chat row", "Separate", "Rename"])


class WindowFilterTests(unittest.TestCase):
    def test_fully_covered_window_is_not_scanned(self):
        top = FakeWindow(1, (0, 0, 100, 100))
        hidden = FakeWindow(2, (0, 0, 100, 100))
        selected = _select_visible_windows([top, hidden], (0, 0, 100, 100))
        self.assertEqual([window.hwnd for window in selected], [1])

    def test_partially_visible_window_is_scanned(self):
        top = FakeWindow(1, (0, 0, 50, 100))
        lower = FakeWindow(2, (0, 0, 100, 100))
        selected = _select_visible_windows([top, lower], (0, 0, 100, 100))
        self.assertEqual([window.hwnd for window in selected], [1, 2])


if __name__ == "__main__":
    unittest.main()
