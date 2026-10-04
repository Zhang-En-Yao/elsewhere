"""Where each place lies, worked out once from which places touch which.

The seed says only which places a way joins; this puts them on a plane so
that the straight-line distance between two places is as close as it can be
to how many ways apart they are - by Kamada-Kawai (Kamada & Kawai, "An
algorithm for drawing general undirected graphs", Information Processing
Letters 31, 1989), as networkx implements it. Distances along the ways are
breadth-first.

The result is turned so its longest spread runs left to right (the principal
axis). No randomness: the same town always lies the same way. Only the
proportions mean anything; the whole is scaled to fit a unit square.
"""

from __future__ import annotations

from typing import Dict, List, Sequence

import networkx
import numpy


def steps(places: Sequence[str], ways: Sequence[Sequence[str]]) -> Dict[str, Dict[str, int]]:
    """How many ways apart every pair is; unreachable pairs are left out."""
    graph = networkx.Graph()
    graph.add_nodes_from(places)
    graph.add_edges_from(
        (one, other) for one, other in ways if one in graph and other in graph and one != other
    )
    return dict(networkx.all_pairs_shortest_path_length(graph))


def layout(places: Sequence[str], ways: Sequence[Sequence[str]]) -> Dict[str, List[float]]:
    places = list(places)
    if not places:
        return {}
    apart = steps(places, ways)
    # A place nobody can walk to is still put somewhere: one further than the
    # furthest anybody can walk.
    furthest = max(distance for reached in apart.values() for distance in reached.values()) + 1
    graph = networkx.Graph()
    graph.add_nodes_from(places)
    position = networkx.kamada_kawai_layout(
        graph,
        dist={one: {other: apart[one].get(other, furthest) for other in places} for one in places},
    )
    return level(position)


def level(position: Dict[str, Sequence[float]]) -> Dict[str, List[float]]:
    """Turn onto the principal axis, then move so the least x and y are 0."""
    places = list(position)
    coordinates = numpy.array([position[place] for place in places], dtype=float)
    coordinates -= coordinates.mean(axis=0)
    _, _, axes = numpy.linalg.svd(coordinates, full_matrices=False)
    turned = coordinates @ axes.T
    turned -= turned.min(axis=0)
    return {
        place: [round(float(x), 3), round(float(y), 3)] for place, (x, y) in zip(places, turned)
    }
