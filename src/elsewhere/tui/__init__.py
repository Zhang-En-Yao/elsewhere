"""A window on the world, for looking rather than for running.

`elsewhere status`, `person`, `timeline` and `event` each answer one question
and stop, which is right for a command and wrong for sitting with a world: the
thing worth seeing is a memory in reach beside the same memory out of it, and
the hour after somebody arrived beside what they turned out to have kept of it.
A printed page cannot put two of those side by side. A window can.

    views.py    what to show, as a pure function of a loaded world
    screen.py   where on a terminal to put it, and what a key does

Nothing here judges anything - no view decides what can be reached, and no
view writes a word anybody in the world would have written. It reads the
ledger, asks `retrieval.py` what would come back if somebody were asked now,
and shows both answers.

The one thing it writes is where you stopped reading.
"""

from __future__ import annotations

__all__ = ["run"]


def run(root) -> None:
    """Open a window on the world at `root`. Imported late: curses is heavy."""
    from .screen import run as _run
    _run(root)
