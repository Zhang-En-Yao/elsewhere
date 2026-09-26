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

And nothing here writes. Not the clock, not where you stopped reading, not a
byte under the world's directory: a window is for looking, and what changes a
world stays a command you have to type. `elsewhere continue` lets it go on,
`elsewhere news` marks what you have read, `elsewhere end` closes it. Run any
of them elsewhere and the window picks the change up by itself, which is the
same thing it does for the launchd agent.
"""

from __future__ import annotations

__all__ = ["run"]


def run(root) -> None:
    """Open a window on the world at `root`. Imported late: curses is heavy."""
    from .screen import run as _run
    _run(root)
