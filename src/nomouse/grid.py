"""Grid cell math shared by the interactive overlay and the headless --run path."""

from dataclasses import dataclass

from nomouse.config import Config, StageGrid
from nomouse.monitors import MonitorGeometry


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float

    def center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2


def cell_rect(region: Rect, grid: StageGrid, n: int) -> Rect:
    idx = n - 1
    col = idx % grid.cols
    row = idx // grid.cols
    cw = region.w / grid.cols
    ch = region.h / grid.rows
    return Rect(x=region.x + col * cw, y=region.y + row * ch, w=cw, h=ch)


def cell_rect_rc(region: Rect, cols: int, rows: int, row: int, col: int) -> Rect:
    """Row/col addressed cell: row is 1-indexed, col is 0-indexed (a=0)."""
    cw = region.w / cols
    ch = region.h / rows
    return Rect(x=region.x + col * cw, y=region.y + (row - 1) * ch, w=cw, h=ch)


def resolve_region(monitor: MonitorGeometry, config: Config, numbers: list[int]) -> Rect:
    """Walk a sequence of 1-3 cell picks (one per stage) to a final Rect."""
    if not (1 <= len(numbers) <= 3):
        raise ValueError("expected 1 to 3 cell numbers (one per grid stage)")

    stages = [config.stage1, config.stage2, config.stage3]
    region = Rect(monitor.x, monitor.y, monitor.width, monitor.height)

    for stage_grid, n in zip(stages, numbers):
        max_n = stage_grid.cols * stage_grid.rows
        if not (1 <= n <= max_n):
            raise ValueError(f"cell {n} out of range for a {stage_grid.cols}x{stage_grid.rows} grid (1-{max_n})")
        region = cell_rect(region, stage_grid, n)

    return region
