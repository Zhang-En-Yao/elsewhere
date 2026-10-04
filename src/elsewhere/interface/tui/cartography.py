"""The town's map drawn in characters.

Where each place lies was worked out once, when the world was made
(`world.geography`, kept in `Map.positions`); this only scales that onto a
character grid - the same scale both ways, so distances stay true - and dots
each way onto it with Bresenham's line algorithm (Bresenham, "Algorithm for
computer control of a digital plotter", IBM Systems Journal 4(1), 1965).
"""

from __future__ import annotations

import unicodedata
from typing import Dict, List, Sequence, Tuple

#: A terminal cell is about twice as tall as it is wide.
CELL_ASPECT = 2.0

#: Every way is drawn with this one mark, whatever its slope.
STROKE = "."

#: Stands in the cell a wide character spills into.
SPILL = ""


def line(start: Tuple[int, int], end: Tuple[int, int]) -> List[Tuple[int, int]]:
    """Bresenham: the cells between two points, neither end included."""
    (x0, y0), (x1, y1) = start, end
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    error = dx + dy
    cells: List[Tuple[int, int]] = []
    x, y = x0, y0
    while (x, y) != (x1, y1):
        doubled = 2 * error
        if doubled >= dy:
            error += dy
            x += sx
        if doubled <= dx:
            error += dx
            y += sy
        cells.append((x, y))
    return cells[:-1]


def cells(text: str) -> List[str]:
    """One entry per terminal column: a wide character is followed by `SPILL`."""
    placed: List[str] = []
    for character in text:
        if unicodedata.combining(character):
            continue
        placed.append(character)
        if unicodedata.east_asian_width(character) in "WF":
            placed.append(SPILL)
    return placed


def draw(
    labels: Dict[str, str],
    positions: Dict[str, List[float]],
    ways: Sequence[Sequence[str]],
    columns: int,
    rows: int,
) -> Tuple[List[str], Dict[str, Tuple[int, int]]]:
    """Names where `positions` puts them, and a dotted line for each way, in at
    most `columns` by `rows`; a place with no position is left off. Also gives
    the row and column each name starts at, for whatever is drawn over it."""
    places = [place for place in labels if place in positions]
    if not places or columns <= 0 or rows <= 0:
        return [], {}
    widest = max(len(cells(labels[place])) for place in places)
    margin = min(widest // 2 + 1, columns // 2)
    room_x, room_y = max(0, columns - 1 - 2 * margin), rows - 1
    least_x = min(positions[place][0] for place in places)
    least_y = min(positions[place][1] for place in places)
    spread_x = max(positions[place][0] for place in places) - least_x
    spread_y = max(positions[place][1] for place in places) - least_y
    # One scale for both axes, counted in cell widths.
    scales = [room_x / spread_x] if spread_x else []
    scales += [room_y * CELL_ASPECT / spread_y] if spread_y else []
    scale = min(scales, default=0.0)
    left = margin + (room_x - round(spread_x * scale)) // 2
    centre = {
        place: (
            left + round((positions[place][0] - least_x) * scale),
            round((positions[place][1] - least_y) * scale / CELL_ASPECT),
        )
        for place in places
    }
    height = max(y for _, y in centre.values()) + 1
    grid = [[" "] * columns for _ in range(height)]
    for one, other in ways:
        if one in centre and other in centre:
            for x, y in line(centre[one], centre[other]):
                grid[y][x] = STROKE
    starts: Dict[str, Tuple[int, int]] = {}
    for place in places:
        x, y = centre[place]
        pieces = cells(labels[place])
        start = min(max(0, x - len(pieces) // 2), max(0, columns - len(pieces)))
        starts[place] = (y, start)
        for offset, piece in enumerate(pieces):
            if 0 <= start + offset < columns:
                grid[y][start + offset] = piece
    return ["".join(row).rstrip() for row in grid], starts
