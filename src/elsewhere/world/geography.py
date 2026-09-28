"""Where each place lies, worked out once from which places touch which.

The seed says only which places a way joins; this puts them on a plane so
that the straight-line distance between two places is as close as it can be
to how many ways apart they are - by stress majorization, localized form
(Gansner, Koren & North, "Graph Drawing by Stress Majorization", Graph
Drawing 2004, LNCS 3383), weighting each pair by the inverse square of its
distance as that paper does. Distances along the ways are breadth-first.

The result is turned so its longest spread runs left to right (the principal
axis), and is in units of one way. No randomness: the same town always lies
the same way.
"""

from __future__ import annotations

import math
from collections import deque
from typing import Dict, List, Sequence, Tuple

ITERATIONS = 500
#: Stop once an iteration lowers the stress by less than this fraction.
TOLERANCE = 1e-5


def steps(places: Sequence[str], ways: Sequence[Sequence[str]]) -> Dict[str, Dict[str, int]]:
    """How many ways apart every pair is; unreachable pairs are left out."""
    beside: Dict[str, List[str]] = {place: [] for place in places}
    for one, other in ways:
        if one in beside and other in beside and one != other:
            beside[one].append(other)
            beside[other].append(one)
    apart: Dict[str, Dict[str, int]] = {}
    for origin in places:
        reached = {origin: 0}
        queue = deque([origin])
        while queue:
            place = queue.popleft()
            for neighbour in beside[place]:
                if neighbour not in reached:
                    reached[neighbour] = reached[place] + 1
                    queue.append(neighbour)
        apart[origin] = reached
    return apart


def stress(position: Dict[str, List[float]], target: Dict[Tuple[str, str], float]) -> float:
    total = 0.0
    for (one, other), distance in target.items():
        actual = math.dist(position[one], position[other])
        total += (actual - distance) ** 2 / distance ** 2
    return total


def layout(places: Sequence[str], ways: Sequence[Sequence[str]]) -> Dict[str, List[float]]:
    places = list(places)
    count = len(places)
    if count == 0:
        return {}
    apart = steps(places, ways)
    # A place nobody can walk to is still put somewhere: one further than the
    # furthest anybody can walk.
    furthest = max((distance for reached in apart.values() for distance in reached.values()),
                   default=0) + 1
    target = {(one, other): float(apart[one].get(other, furthest))
              for index, one in enumerate(places) for other in places[index + 1:]}

    def distance(one: str, other: str) -> float:
        return target.get((one, other)) or target[(other, one)]

    radius = furthest / 2
    position = {place: [radius * math.cos(2 * math.pi * index / count),
                        radius * math.sin(2 * math.pi * index / count)]
                for index, place in enumerate(places)}
    previous = stress(position, target)
    for _ in range(ITERATIONS):
        for place in places:
            x = y = weights = 0.0
            for other in places:
                if other == place:
                    continue
                wanted = distance(place, other)
                weight = wanted ** -2
                dx = position[place][0] - position[other][0]
                dy = position[place][1] - position[other][1]
                actual = math.hypot(dx, dy) or 1e-9
                x += weight * (position[other][0] + wanted * dx / actual)
                y += weight * (position[other][1] + wanted * dy / actual)
                weights += weight
            position[place] = [x / weights, y / weights]
        current = stress(position, target)
        if previous - current < TOLERANCE * previous:
            break
        previous = current
    return level(position)


def level(position: Dict[str, List[float]]) -> Dict[str, List[float]]:
    """Turn onto the principal axis, then move so the least x and y are 0."""
    count = len(position)
    mean_x = sum(x for x, _ in position.values()) / count
    mean_y = sum(y for _, y in position.values()) / count
    xx = sum((x - mean_x) ** 2 for x, _ in position.values())
    yy = sum((y - mean_y) ** 2 for _, y in position.values())
    xy = sum((x - mean_x) * (y - mean_y) for x, y in position.values())
    angle = -0.5 * math.atan2(2 * xy, xx - yy)
    cosine, sine = math.cos(angle), math.sin(angle)
    turned = {place: [(x - mean_x) * cosine - (y - mean_y) * sine,
                      (x - mean_x) * sine + (y - mean_y) * cosine]
              for place, (x, y) in position.items()}
    least_x = min(x for x, _ in turned.values())
    least_y = min(y for _, y in turned.values())
    return {place: [round(x - least_x, 3), round(y - least_y, 3)]
            for place, (x, y) in turned.items()}
