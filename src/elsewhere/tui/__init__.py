"""Read-only curses window on a world.

    views.py    what to show, as pure functions of a loaded world
    screen.py   layout, colours and keys

It never writes under the world's directory; it reloads when the files change.
"""

from __future__ import annotations

__all__ = ["run"]


def run(root) -> None:
    """Imported late: curses is heavy."""
    from .screen import run as _run
    _run(root)
