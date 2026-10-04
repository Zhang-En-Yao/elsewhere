"""What comes back: one engram, found by what the moment points at, and only as
much of it as time has left.

Finding it takes two published rankings, each run by a library and neither by
hand, fused by a third:

    lexical   Okapi BM25 (Robertson & Zaragoza 2009, "The Probabilistic
              Relevance Framework: BM25 and Beyond"), as SQLite's FTS5 computes
              it at its own parameters, over words reduced by the Porter
              stemmer (Porter 1980). Good at names: Marah, Havvah.
    dense     cosine distance between sentence embeddings, by sqlite-vec's
              `vec_distance_cosine`. Good at a thing said in other words.
    fused     Reciprocal Rank Fusion (Cormack, Clarke & Buettcher 2009,
              "Reciprocal Rank Fusion outperforms Condorcet and individual
              Rank Learning Methods"), at the paper's k = 60.

Without an embedder, or without sqlite-vec, the dense ranking is left out and
BM25 alone decides. sqlite-vec is an extension, and the SQLite that python.org
builds Python with for macOS cannot load one, so sqlean.py's SQLite (which can,
and has FTS5) is used whenever it is installed, and the standard library's when not. There is no threshold: the best there is comes back,
however slight, and whether it meant anything is the mind's to say.

What comes back of it follows the power law of forgetting (Wixted & Ebbesen
1991, "On the Form of Forgetting"): the share of its gists that survive is
(1 + days)^-d, at ACT-R's decay d = 0.5 (Anderson & Lebiere 1998), and the
ones that survive are the ones the mind weighted heaviest when it slept on it.
"""

from __future__ import annotations

import math
import re
from contextlib import closing
from dataclasses import replace
from typing import Dict, List, Optional, Sequence

from ..domain.memory import Engram

try:
    import sqlean as sqlite
except ImportError:
    import sqlite3 as sqlite

#: RRF's k, as published: it damps how much the very top of one ranking counts.
FUSION_K = 60
#: ACT-R's base-level decay, as published.
DECAY = 0.5


def connect() -> sqlite.Connection:
    """An in-memory database, on whichever SQLite can load sqlite-vec."""
    return sqlite.connect(":memory:")


def load_vector_extension(connection: sqlite.Connection) -> bool:
    """Load sqlite-vec into this connection; False if it cannot be."""
    try:
        import sqlite_vec

        connection.enable_load_extension(True)
        sqlite_vec.load(connection)
        connection.enable_load_extension(False)
        return True
    except (ImportError, AttributeError, sqlite.OperationalError):
        return False


def lexical_ranking(connection: sqlite.Connection, documents: Sequence[str], cue: str) -> List[int]:
    # Each word quoted, so the cue is only ever words and never FTS5 syntax.
    words = sorted(set(re.findall(r"\w+", cue)))
    if not words:
        return []
    connection.execute(
        "CREATE VIRTUAL TABLE lexical USING " "fts5(document, tokenize='porter unicode61')"
    )
    connection.executemany(
        "INSERT INTO lexical(rowid, document) VALUES (?, ?)",
        [(index + 1, document) for index, document in enumerate(documents)],
    )
    rows = connection.execute(
        "SELECT rowid FROM lexical WHERE lexical MATCH ? ORDER BY bm25(lexical)",
        (" OR ".join(f'"{word}"' for word in words),),
    ).fetchall()
    return [row[0] - 1 for row in rows]


def dense_ranking(
    connection: sqlite.Connection,
    engrams: Sequence[Engram],
    cue_vector: Sequence[float],
    embedder: str,
) -> List[int]:
    if not cue_vector or not embedder or not load_vector_extension(connection):
        return []
    import sqlite_vec

    vectors = [
        (index, sqlite_vec.serialize_float32(list(engram.embedding)))
        for index, engram in enumerate(engrams)
        if engram.embedded_by == embedder and len(engram.embedding) == len(cue_vector)
    ]
    if not vectors:
        return []
    connection.execute("CREATE TABLE dense(position INTEGER PRIMARY KEY, embedding BLOB)")
    connection.executemany("INSERT INTO dense VALUES (?, ?)", vectors)
    rows = connection.execute(
        "SELECT position FROM dense ORDER BY vec_distance_cosine(embedding, ?)",
        (sqlite_vec.serialize_float32(list(cue_vector)),),
    ).fetchall()
    return [row[0] for row in rows]


def fuse(rankings: Sequence[Sequence[int]]) -> Dict[int, float]:
    scores: Dict[int, float] = {}
    for ranking in rankings:
        for rank, position in enumerate(ranking, 1):
            scores[position] = scores.get(position, 0.0) + 1.0 / (FUSION_K + rank)
    return scores


def search(
    engrams: Sequence[Engram], cue: str, cue_vector: Sequence[float] = (), embedder: str = ""
) -> Optional[Engram]:
    """The one engram the cue points at most, or None when nothing is shared."""
    if not engrams:
        return None
    with closing(connect()) as connection:
        rankings = [
            lexical_ranking(connection, [engram.text for engram in engrams], cue),
            dense_ranking(connection, engrams, cue_vector, embedder),
        ]
    scores = fuse(rankings)
    if not scores:
        return None
    return engrams[max(sorted(scores), key=lambda position: scores[position])]


def retention(days: float) -> float:
    """The share of an engram's gists still there after this many days."""
    return (1.0 + max(0.0, days)) ** -DECAY


def fragment(engram: Engram, days: float) -> Engram:
    """The engram as it comes back after this many days: its heaviest gists,
    as many as `retention` leaves, in the order they were laid down."""
    if not engram.gists:
        return engram
    surviving = math.ceil(len(engram.gists) * retention(days))
    heaviest = sorted(
        range(len(engram.gists)), key=lambda position: -engram.gists[position].weight
    )[:surviving]
    return replace(engram, gists=[engram.gists[position] for position in sorted(heaviest)])
