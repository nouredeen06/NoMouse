"""Grid cell math for the row/column labeled overlay."""

from dataclasses import dataclass


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float

    def center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2


def cell_rect_rc(region: Rect, cols: int, rows: int, row: int, col: int) -> Rect:
    """Row/col addressed cell: row is 1-indexed, col is 0-indexed (a=0)."""
    cw = region.w / cols
    ch = region.h / rows
    return Rect(x=region.x + col * cw, y=region.y + (row - 1) * ch, w=cw, h=ch)
