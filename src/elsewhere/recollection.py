"""What comes back: one earlier note, found by what the moment points at.

Two published rankings, each run by a library and neither by hand, fused by a
third:

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
BM25 alone decides. There is no threshold: the best there is comes back,
however slight, and whether it meant anything is the mind's to say.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from typing import Dict, List, Optional, Sequence

from .world.notes import Note

#: RRF's k, as published: it damps how much the very top of one ranking counts.
FUSION_K = 60


def load_vector_extension(connection: sqlite3.Connection) -> bool:
    """Load sqlite-vec into this connection; False if it cannot be."""
    try:
        import sqlite_vec
        connection.enable_load_extension(True)
        sqlite_vec.load(connection)
        connection.enable_load_extension(False)
        return True
    except (ImportError, AttributeError, sqlite3.OperationalError):
        return False


def lexical_ranking(connection: sqlite3.Connection, accounts: Sequence[str],
                    cue: str) -> List[int]:
    # Each word quoted, so the cue is only ever words and never FTS5 syntax.
    words = sorted(set(re.findall(r"\w+", cue)))
    if not words:
        return []
    connection.execute("CREATE VIRTUAL TABLE lexical USING "
                       "fts5(account, tokenize='porter unicode61')")
    connection.executemany("INSERT INTO lexical(rowid, account) VALUES (?, ?)",
                           [(index + 1, account) for index, account in enumerate(accounts)])
    rows = connection.execute(
        "SELECT rowid FROM lexical WHERE lexical MATCH ? ORDER BY bm25(lexical)",
        (" OR ".join(f'"{word}"' for word in words),)).fetchall()
    return [row[0] - 1 for row in rows]


def dense_ranking(connection: sqlite3.Connection, notes: Sequence[Note],
                  cue_vector: Sequence[float], embedder: str) -> List[int]:
    if not cue_vector or not embedder or not load_vector_extension(connection):
        return []
    import sqlite_vec

    vectors = [(index, sqlite_vec.serialize_float32(list(note.embedding)))
              for index, note in enumerate(notes)
              if note.embedded_by == embedder and len(note.embedding) == len(cue_vector)]
    if not vectors:
        return []
    connection.execute("CREATE TABLE dense(position INTEGER PRIMARY KEY, embedding BLOB)")
    connection.executemany("INSERT INTO dense VALUES (?, ?)", vectors)
    rows = connection.execute(
        "SELECT position FROM dense ORDER BY vec_distance_cosine(embedding, ?)",
        (sqlite_vec.serialize_float32(list(cue_vector)),)).fetchall()
    return [row[0] for row in rows]


def fuse(rankings: Sequence[Sequence[int]]) -> Dict[int, float]:
    scores: Dict[int, float] = {}
    for ranking in rankings:
        for rank, position in enumerate(ranking, 1):
            scores[position] = scores.get(position, 0.0) + 1.0 / (FUSION_K + rank)
    return scores


def recall(notes: Sequence[Note], cue: str,
                 cue_vector: Sequence[float] = (), embedder: str = "") -> Optional[Note]:
    """The one note the cue points at most, or None when nothing is shared."""
    if not notes:
        return None
    with closing(sqlite3.connect(":memory:")) as connection:
        rankings = [lexical_ranking(connection, [note.account for note in notes], cue),
                    dense_ranking(connection, notes, cue_vector, embedder)]
    scores = fuse(rankings)
    if not scores:
        return None
    return notes[max(sorted(scores), key=lambda position: scores[position])]
