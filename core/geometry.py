from typing import List, Tuple
from rtree import index

Rect = Tuple[int, int, int, int]
# cчитаем площадь
def rect_area(rect: Rect) -> int:
    x1, y1, x2, y2 = rect
    return max(0, x2 - x1) * max(0, y2 - y1)

def subtract_rects(base_rect: Rect, overlay_rects: List[Rect]) -> List[Rect]:
    if not overlay_rects:
        return [base_rect]

    # Создаем R-tree для overlay
    rtree_idx = index.Index()
    for i, rect in enumerate(overlay_rects):
        rtree_idx.insert(i, rect)

    visible_rects = [base_rect]

    for _ in range(len(overlay_rects)):
        new_visible = []
        for vx1, vy1, vx2, vy2 in visible_rects:
            # ищем перекрытия через R-tree
            overlapping_ids = list(rtree_idx.intersection((vx1, vy1, vx2, vy2)))
            if not overlapping_ids:
                new_visible.append((vx1, vy1, vx2, vy2))
                continue

            # делим прямоугольник на части
            temp_rects = [(vx1, vy1, vx2, vy2)]
            for oid in overlapping_ids:
                ox1, oy1, ox2, oy2 = overlay_rects[oid]
                updated = []
                for tx1, ty1, tx2, ty2 in temp_rects:
                    if ox2 <= tx1 or ox1 >= tx2 or oy2 <= ty1 or oy1 >= ty2:
                        updated.append((tx1, ty1, tx2, ty2))
                        continue

                    if ty1 < oy1:
                        updated.append((tx1, ty1, tx2, oy1))
                    if ty2 > oy2:
                        updated.append((tx1, oy2, tx2, ty2))
                    if tx1 < ox1:
                        updated.append((tx1, max(ty1, oy1), ox1, min(ty2, oy2)))
                    if tx2 > ox2:
                        updated.append((ox2, max(ty1, oy1), tx2, min(ty2, oy2)))
                temp_rects = updated
            new_visible.extend(temp_rects)
        visible_rects = new_visible

    return visible_rects