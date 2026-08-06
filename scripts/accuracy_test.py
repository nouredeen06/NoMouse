#!/usr/bin/env python3
"""Measure positioning accuracy of clicker.move_to over many trials.

Resolves a fixed grid-cell sequence to a target point once, then repeatedly
randomizes the starting cursor position and moves to that target, comparing
the requested target against the actually-landed position (no button press,
so it's safe to run thousands of times without side effects on the desktop).

Usage: python3 scripts/accuracy_test.py 2 7 5 --iterations 1000
"""

import argparse
import random
import statistics

from mouseoverlay import session
from mouseoverlay.clicker import get_cursor_pos, move_to
from mouseoverlay.config import load_config
from mouseoverlay.grid import resolve_region
from mouseoverlay.monitors import get_focused_monitor


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cells", nargs="+", type=int, help="grid cell sequence, e.g. 2 7 5")
    parser.add_argument("--iterations", type=int, default=1000)
    args = parser.parse_args()

    backend = session.get_backend_name()
    config = load_config()
    monitor = get_focused_monitor(backend)
    region = resolve_region(monitor, config, args.cells)
    target_x, target_y = region.center()

    print(f"backend: {backend}")
    print(f"monitor: {monitor.x},{monitor.y} {monitor.width}x{monitor.height}")
    print(f"cells {args.cells} -> target ({target_x:.1f}, {target_y:.1f})")
    print(f"running {args.iterations} trials...\n")

    errors = []
    worst: list[tuple[float, int, int]] = []

    for i in range(args.iterations):
        start_x = random.randint(monitor.x, monitor.x + monitor.width - 1)
        start_y = random.randint(monitor.y, monitor.y + monitor.height - 1)
        move_to(backend, start_x, start_y)

        move_to(backend, target_x, target_y)
        actual_x, actual_y = get_cursor_pos(backend)

        err = ((actual_x - target_x) ** 2 + (actual_y - target_y) ** 2) ** 0.5
        errors.append(err)
        worst.append((err, actual_x, actual_y))

        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{args.iterations}...")

    worst.sort(key=lambda t: -t[0])

    print("\n--- results ---")
    print(f"trials: {len(errors)}")
    print(f"mean error:   {statistics.mean(errors):.2f}px")
    print(f"median error: {statistics.median(errors):.2f}px")
    print(f"stdev:        {statistics.pstdev(errors):.2f}px")
    print(f"max error:    {max(errors):.2f}px")
    for threshold in (0, 1, 2, 5, 10):
        pct = 100 * sum(1 for e in errors if e <= threshold) / len(errors)
        print(f"within {threshold}px: {pct:.1f}%")

    print("\nworst 10 trials:")
    for err, ax, ay in worst[:10]:
        print(f"  error={err:.1f}px landed=({ax},{ay}) target=({target_x:.0f},{target_y:.0f})")


if __name__ == "__main__":
    main()
