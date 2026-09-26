"""A line that says what is being waited on, for the two commands that wait.

Nothing in the engine has any notion of progress, and that is right: `ask` puts
one question to a mind and gives back an answer, and both making a world and
living an hour of one are hundreds of those. But the person who typed the
command is then looking at a terminal that has printed nothing - `initialize`
asks a dozen questions before its first line, and one step of `continue` can
ask dozens before the account of that step is ready - and a slow model and a
hung one look exactly alike from there.

So: one line, redrawn where it stands, saying which question is out, how long
it has been out, and how many have come back. It goes on stderr, because what
happened goes on stdout and has to keep piping into a file; and it draws
nothing at all unless stderr is a terminal, which is why the scheduled run
(`scripts/schedule.sh`, whose stderr is a log) gets not one extra byte.

It hangs off `backends.watched` rather than off the commands, because what
takes the time is the questions and every one of them goes through one place.
Neither `tick` nor `seed` is told that anybody is watching.
"""

from __future__ import annotations

import shutil
import sys
import threading
import time
from contextlib import contextmanager
from typing import Iterator, Optional

from . import backends
from .backends import Call
from .schemas import CallName

#: What to call each question while it is out. A person's name goes where the
#: brace is; the three that nobody in particular is asked have no brace.
DOING = {
    CallName.PERCEIVE: "{} is taking it in",
    CallName.ACT: "{} is deciding",
    CallName.SPEAK: "{} is finding the words",
    CallName.RECALL: "{} is going back over it",
    CallName.REFLECT: "{} is going over the day",
    CallName.DIRECT: "asking the town whether anything happens to it",
    CallName.ARRIVE: "asking the road who is on it",
    CallName.PROBE: "reaching the minds",
}

FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def person(about: str) -> str:
    """A name out of a person id, or nothing for what is not a person.

    Worked out from the id rather than looked up, because this has no world to
    ask: `seed.build` is halfway through making the one it is reporting on. Ids
    are made from the name (`agents._free_being_id`), so for anybody called one
    word this is their name, and for a stranger who came up the road under two
    it is a run-on of them. It labels a wait; it is not a record of anything.
    """
    return about[2:].capitalize() if about.startswith("p_") else ""


def doing(call: Call) -> str:
    """What to say is happening while `call` is out."""
    return DOING.get(call.name, str(call.name)).format(person(call.about))


def span(seconds: float) -> str:
    """A length of waiting, as short as it can be said."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    return f"{int(seconds // 60)}m{int(seconds % 60):02d}s"


class Progress:
    """The waiting line: what `backends.watched` tells, and `say` prints past.

    Everything here is safe on a stream that is not a terminal, where it draws
    nothing and `say` is a plain print. A stream that closes or refuses a write
    ends the drawing rather than the run - a world must not fail to be lived
    because nobody was watching it.
    """

    def __init__(self, stream=None, total: Optional[int] = None,
                 every: float = 0.2):
        self.stream = sys.stderr if stream is None else stream
        #: How many questions there are to ask, if that is known in advance.
        self.total = total
        self.every = every
        self.live = bool(getattr(self.stream, "isatty", bool)())
        self.began = time.time()
        self.answered_count = 0
        self.unusable = 0
        self._doing = ""            # what is out now; "" between questions
        self._out_since = 0.0
        self._drawn = 0             # how much of the line is ours to wipe
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ---- what there is to say ------------------------------------------

    def line(self) -> str:
        """The waiting line as it stands this instant."""
        frame = FRAMES[int((time.time() - self.began) / 0.12) % len(FRAMES)]
        done = (f"{self.answered_count}/{self.total}" if self.total
                else str(self.answered_count))
        if self.unusable:
            done += f" (+{self.unusable} unusable)"
        out = (f"{self._doing} · {span(time.time() - self._out_since)}"
               if self._doing else "waiting")
        return f"{frame} {out} · {done} answered in {span(time.time() - self.began)}"

    # ---- the seam backends.ask talks to --------------------------------

    def asking(self, call: Call, attempt: int) -> None:
        with self._lock:
            self._doing = doing(call) + (" again" if attempt > 1 else "")
            self._out_since = time.time()
        self.draw()

    def answered(self, call: Call, took: float, ok: bool) -> None:
        with self._lock:
            self.answered_count += 1
            if not ok:
                self.unusable += 1
            self._doing = ""
        self.draw()

    def placing(self, count: int) -> None:
        # Not counted as an answer: nobody was asked anything. It is here
        # because on one machine serving one model at a time it is most of the
        # wait between two questions, and a line that said "waiting" through
        # all of it would be telling the truth badly.
        with self._lock:
            self._doing = ("placing it in meaning" if count == 1
                           else f"placing {count} things in meaning")
            self._out_since = time.time()
        self.draw()

    def placed(self, took: float, ok: bool) -> None:
        with self._lock:
            self._doing = ""
        self.draw()

    # ---- what the commands print through -------------------------------

    def say(self, line: str = "") -> None:
        """One line of the account, with the waiting line got out of its way.

        This is what goes where `go_on` and `seed.build` take a `say`: stdout
        keeps the account, in the order it was written, with nothing of the
        waiting mixed into it.
        """
        with self._lock:
            self.wipe()
            print(line)
            self.draw()

    # ---- drawing -------------------------------------------------------

    def draw(self) -> None:
        if not self.live:
            return
        with self._lock:
            room = shutil.get_terminal_size((80, 24)).columns - 1
            line = self.line()[:room]
            pad = " " * max(0, self._drawn - len(line))
            self._drawn = len(line)
            self._write("\r" + line + pad)

    def wipe(self) -> None:
        """Take the line back off the terminal, leaving the cursor at column 0."""
        if not self.live or not self._drawn:
            return
        with self._lock:
            self._write("\r" + " " * self._drawn + "\r")
            self._drawn = 0

    def _write(self, text: str) -> None:
        try:
            self.stream.write(text)
            self.stream.flush()
        except (OSError, ValueError):
            # The terminal went away. The world has not.
            self.live = False

    # ---- while it is open ----------------------------------------------

    def _spin(self) -> None:
        while not self._stop.wait(self.every):
            self.draw()

    def __enter__(self) -> "Progress":
        # The clock only starts ticking on the way in, so a Progress made
        # early does not report the time it spent unused.
        self.began = time.time()
        if self.live:
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exception) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        self.wipe()


@contextmanager
def watching(total: Optional[int] = None, stream=None) -> Iterator[Progress]:
    """Show what is being waited on, for as long as this is open.

    Print the account through the `Progress` it gives back - `waiting.say` -
    and not with `print`, or the account and the waiting line write over each
    other on the way out.
    """
    shown = Progress(stream=stream, total=total)
    with backends.watched(shown), shown:
        yield shown
