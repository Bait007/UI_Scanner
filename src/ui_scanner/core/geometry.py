from typing import Iterable, List, Tuple

Rect = Tuple[int, int, int, int]


def rect_area(rect: Rect) -> int:
    x1, y1, x2, y2 = rect
    return max(0, x2 - x1) * max(0, y2 - y1)


def intersect_rect(first: Rect, second: Rect):
    x1 = max(first[0], second[0])
    y1 = max(first[1], second[1])
    x2 = min(first[2], second[2])
    y2 = min(first[3], second[3])

    if x1 >= x2 or y1 >= y2:
        return None

    return x1, y1, x2, y2


def rect_contains(outer: Rect, inner: Rect, tolerance: int = 1) -> bool:
    return (
        outer[0] - tolerance <= inner[0]
        and outer[1] - tolerance <= inner[1]
        and outer[2] + tolerance >= inner[2]
        and outer[3] + tolerance >= inner[3]
    )


def intersection_over_union(first: Rect, second: Rect) -> float:
    intersection = intersect_rect(first, second)
    if intersection is None:
        return 0.0

    intersection_area = rect_area(intersection)
    union_area = rect_area(first) + rect_area(second) - intersection_area
    return intersection_area / union_area if union_area else 0.0


def subtract_rect(base: Rect, overlay: Rect) -> List[Rect]:
    bx1, by1, bx2, by2 = base
    ox1, oy1, ox2, oy2 = overlay

    ix1 = max(bx1, ox1)
    iy1 = max(by1, oy1)
    ix2 = min(bx2, ox2)
    iy2 = min(by2, oy2)

    # Прямоугольники не пересекаются
    if ix1 >= ix2 or iy1 >= iy2:
        return [base]
    result: List[Rect] = []

    if by1 < iy1:
        result.append((bx1, by1, bx2, iy1))

    if iy2 < by2:
        result.append((bx1, iy2, bx2, by2))

    if bx1 < ix1:
        result.append((bx1, iy1, ix1, iy2))

    if ix2 < bx2:
        result.append((ix2, iy1, bx2, iy2))

    return result


def subtract_rects(base: Rect, overlays: Iterable[Rect]) -> List[Rect]:
    visible = [base]

    for overlay in overlays:
        next_visible: List[Rect] = []

        for rect in visible:
            next_visible.extend(subtract_rect(rect, overlay))

        visible = next_visible
        if not visible:
            break

    return visible
