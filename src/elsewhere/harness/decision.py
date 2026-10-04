"""What one turn comes to, for a being or for the world: one tool call on the
server, and when to be asked again."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..domain.calendar import virtual_of


@dataclass
class Decision:
    #: A `server.Tool`; None when there is nothing to call (the world, quiet).
    tool: Optional[str] = None
    #: The tool's arguments, ids resolved: exactly what goes to the server.
    arguments: dict = field(default_factory=dict)
    #: What `Tool.WAIT` is called with after it; None leaves no timer.
    duration: Optional[float] = None
    #: Ending the day; the only trigger for `consolidate`.
    sleep: bool = False
    reason: str = ""
    doing: str = ""
    #: True when the mind gave nothing usable and this is the engine's own.
    defaulted: bool = False


def duration_of(answer: Optional[dict]) -> Optional[float]:
    """The answer's `duration`, which a mind gives in clock seconds, as a length
    of world time if it is a number, else None."""
    if not answer:
        return None
    value = answer.get("duration")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return virtual_of(float(value))
