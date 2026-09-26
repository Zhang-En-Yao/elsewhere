"""The terminal half: where each line goes, and what a key does.

Everything with an opinion about the world is in `views.py`. This file knows
about columns, tones as colours, a cursor, and a thread.

Two things here are worth saying out loud, because both are decisions rather
than mechanics:

*A window is not a console.* What it writes is where you stopped reading, and
nothing else. Ending a world is deliberately not on any key: it is the one act
that cannot be undone, and it belongs to a command you had to type. A world
being `end`ed while you watch reads correctly anyway - the window simply says
so and goes on showing what happened.

*The world is reloaded, never shared.* A step is lived on a worker thread by a
`World` that thread loaded for itself, under the same directory lock the
scheduler takes, and the drawing thread finds out about it the way it finds out
about the launchd agent's steps: the files on disk moved. So nothing here is
holding an object somebody else is halfway through writing, and watching a
world you are also running is the same code path as watching one that a
schedule is running somewhere behind you.
"""

from __future__ import annotations

import curses
import queue
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..world import store
from . import views
from .views import VIEWS, Line, Row

#: How long the window waits on a key before looking at the clock and the
#: files again. Short enough that a step somebody else lived shows up while
#: you are still looking at it; long enough to be asleep the rest of the time.
PAUSE_MS = 500

#: A fourth tab, which is not a view of the world but of what was asked of it.
LIVE = "Live"

KEYS = ("1-4 view   TAB pane   j/k move   g/G ends   f follow   c go on   "
        "m mark read   ? keys   q quit")

HELP = """\
Keys

  1 2 3 4     town, people, history, and what is being asked of the world
  TAB         move between the list and what it is showing
  j k         down and up; also the arrow keys
  g G         the top, and the end
  SPACE b     a screenful down, and back
  r           read the world off disk again, now
  f           follow: pick the world's changes up as they land (on by default)
  c           let the world go on for however long you have been away
  m           mark everything that has happened as read
  q           close the window

What this window writes

  Only where you stopped reading, which is what `m` does. Everything else
  here reads.

  Ending a world is not on a key. It is the one thing that cannot be taken
  back, so it stays a command you have to type: elsewhere --world <path> end

Letting it go on

  `c` lives the hours the wall clock says are owed, exactly as
  `elsewhere continue` does and under the same lock, so it is safe while a
  schedule is running. It needs a reachable mind; if there is none, the
  world waits and says so.
"""


def _tones() -> Dict[str, int]:
    """Tones as this terminal's attributes, and defaults where it has none."""
    plain = curses.A_NORMAL
    accent, warn = plain, plain
    try:
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_YELLOW, -1)
        accent, warn = curses.color_pair(1), curses.color_pair(2)
    except curses.error:
        accent, warn = curses.A_BOLD, curses.A_BOLD
    return {"plain": plain, "dim": curses.A_DIM, "bold": curses.A_BOLD,
            "accent": accent, "warn": warn, "rule": curses.A_DIM}


class Runner:
    """Letting the world go on, off the thread that is drawing it.

    The thread loads its own world and saves it; this side only ever reads the
    lines it reports. `log` is kept whole for the session - it is the one place
    the window shows what was actually asked of a mind and what came back of
    it, and throwing that away on a redraw would be losing the only thing on
    screen that is not on disk somewhere else.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.said: "queue.Queue[str]" = queue.Queue()
        self.log: List[Line] = []
        self._thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, most: int = 8) -> bool:
        if self.running:
            return False
        self.log.append(Line(""))
        self._thread = threading.Thread(target=self._work, args=(most,),
                                        daemon=True)
        self._thread.start()
        return True

    def _work(self, most: int) -> None:
        # Imported here and not at the top: `cli` reaches for this module when
        # it wires up `watch`, and a thread is a fine place to pay for it.
        from .. import cli
        try:
            world = store.load(self.root)
            if world.closed:
                self.said.put(world.name + " has ended. Nothing more happens "
                                           "here.")
                return
            cli.go_on(world, most, self.said.put)
        except store.Locked as exception:
            self.said.put("not now: " + str(exception))
        except Exception as exception:              # a window should not die of it
            self.said.put(type(exception).__name__ + ": " + str(exception))

    def drain(self) -> bool:
        """Take whatever the thread has said. True if anything had been."""
        got = False
        while True:
            try:
                text = self.said.get_nowait()
            except queue.Empty:
                break
            got = True
            tone = "dim" if text.startswith("[") or not text.strip() else "plain"
            self.log.append(Line(text, tone))
        return got


class App:
    """One window on one world."""

    def __init__(self, root: Path, screen) -> None:
        self.root = Path(root)
        self.screen = screen
        self.world = store.load(self.root)
        self.runner = Runner(self.root)
        self.tone = _tones()
        self.tab = 0                      # 0..len(VIEWS)-1 are views; last is LIVE
        self.cursor: Dict[int, int] = {}
        self.top: Dict[int, int] = {}
        self.down = 0                     # how far into what is being shown
        self.tail = 0                     # lines held back from the end of the log
        self.on_detail = False
        self.follow = True
        self.helping = False
        self.going = False                # a step of our own is being lived
        self.message = ""
        self.stamp = self._stamp()
        self._shown: Optional[Tuple] = None
        self._lines: List[Line] = []
        self._listed: Optional[Tuple] = None
        self._rows: List[Row] = []
        for index in range(len(VIEWS)):
            self.cursor[index], self.top[index] = 0, 0
        self._settle()

    # -- the world underneath ---------------------------------------------

    def _stamp(self) -> tuple:
        """Enough of the files to notice that somebody else moved the world."""
        out = []
        for path in (self.root / "world.json", self.root / "chronicle.jsonl"):
            try:
                out.append(path.stat().st_mtime_ns)
            except OSError:
                out.append(0)
        try:
            out.append(sum(path.stat().st_mtime_ns for path in
                           (self.root / "memories").glob("*.jsonl")))
        except OSError:
            out.append(0)
        return tuple(out)

    def reload(self, say: bool = False) -> None:
        """Read the world off disk again, staying on whatever was selected."""
        keep = self.selected()
        try:
            self.world = store.load(self.root)
        except (OSError, ValueError) as exception:
            self.message = "could not read the world: " + str(exception)
            return
        self.stamp = self._stamp()
        self._shown = self._listed = None
        if keep:
            for index, row in enumerate(self.rows()):
                if row.key == keep:
                    self.cursor[self.tab] = index
                    break
        self._settle()
        if say:
            self.message = "read again at " + time.strftime("%H:%M:%S")

    # -- what is on screen ------------------------------------------------

    @property
    def live(self) -> bool:
        return self.tab == len(VIEWS)

    def view(self):
        return VIEWS[min(self.tab, len(VIEWS) - 1)]

    def rows(self) -> List[Row]:
        """This tab's list, worked out once per change rather than per draw.

        A frame asks for the list three or four times - to draw it, to settle
        the cursor on it, and to find out what is selected - and in a world
        with a long chronicle that is a walk over every event that ever
        happened, twice a second, for a list that has not moved.
        """
        key = (self.tab, self.stamp)
        if key != self._listed:
            self._listed, self._rows = key, self.view().rows(self.world)
        return self._rows

    def selected(self) -> str:
        if self.live:
            return ""              # a log has no rows and nothing to select
        rows = self.rows()
        index = self.cursor.get(self.tab, 0)
        return rows[index].key if 0 <= index < len(rows) else ""

    def _settle(self) -> None:
        """Land the cursor on something that can be landed on."""
        if self.live:
            return
        rows = self.rows()
        index = min(max(0, self.cursor.get(self.tab, 0)), max(0, len(rows) - 1))
        if rows and not rows[index].key:
            after = [i for i in range(index, len(rows)) if rows[i].key]
            before = [i for i in range(index, -1, -1) if rows[i].key]
            index = after[0] if after else (before[0] if before else index)
        self.cursor[self.tab] = index

    def shown(self, columns: int) -> List[Line]:
        """The right-hand side, wrapped, and worked out once per change."""
        key = (self.tab, self.selected(), columns, self.stamp, self.helping)
        if key == self._shown:
            return self._lines
        if self.helping:
            raw = [Line(text) for text in HELP.splitlines()]
        elif self.live:
            raw = self.runner.log or [
                Line("Nothing has been asked of anybody from this window yet.",
                     "dim"),
                Line(""),
                Line("  Press c to let the world go on for however long you "
                     "have been away. It lives the hours that are owed, the "
                     "same as elsewhere continue, and stops when there is "
                     "nothing due.", "dim", under=2)]
        else:
            raw = self.view().detail(self.world, self.selected())
        out: List[Line] = []
        for line in raw:
            out.extend(views.wrap(line, columns))
        self._shown, self._lines = key, out
        return out

    # -- drawing ----------------------------------------------------------

    def put(self, y: int, x: int, text: str, attr: int, columns: int) -> None:
        if columns <= 0 or y < 0:
            return
        try:
            self.screen.addstr(y, x, views.clip(text, columns), attr)
        except curses.error:
            pass                        # the last cell of the last line

    def rule(self, y: int, width: int) -> None:
        """A line across. Whatever this terminal draws lines with."""
        try:
            self.screen.hline(y, 0, curses.ACS_HLINE, width)
        except curses.error:
            pass

    def draw(self) -> None:
        self.screen.erase()
        height, width = self.screen.getmaxyx()
        if height < 8 or width < 40:
            self.put(0, 0, "a little more room, please", self.tone["dim"], width)
            self.screen.noutrefresh()
            curses.doupdate()
            return
        world = self.world
        # the world, and the hour it is at
        left = (world.name + "   " + world.label() + "   the sun "
                + ("is up" if world.daylight else "is down"))
        if world.closed:
            left += "   (ended)"
        unseen = len(world.chronicle) - world.news_seen
        right = ("going on" if self.runner.running else
                 (str(unseen) + " new" if unseen > 0 else "all read"))
        if not self.follow:
            right += "   not following"
        # The hour gives up its room to the state of things, not the other way
        # round: on a narrow terminal the clock is worth less than "2 new".
        room = max(0, width - views.width(right) - 2)
        self.put(0, 0, views.pad(views.clip(left, room), width),
                 curses.A_REVERSE, width)
        self.put(0, max(0, width - views.width(right) - 1), right,
                 curses.A_REVERSE | curses.A_BOLD, width)
        # the tabs
        x = 1
        for index, title in enumerate([view.title for view in VIEWS] + [LIVE]):
            label = str(index + 1) + " " + title
            here = index == self.tab
            self.put(1, x, label,
                     (self.tone["accent"] | curses.A_BOLD) if here
                     else self.tone["dim"], max(0, width - x))
            x += views.width(label) + 3
        self.rule(2, width)
        body, top = height - 5, 3
        if self.live or self.helping:
            self._draw_shown(top, 0, body, width)
        else:
            columns = max(20, min(46, width * 2 // 5))
            self._draw_rows(top, 0, body, columns)
            try:
                self.screen.vline(top, columns, curses.ACS_VLINE, body)
            except curses.error:
                pass
            self._draw_shown(top, columns + 2, body, width - columns - 3)
        self.rule(height - 2, width)
        foot = self.message or KEYS
        self.put(height - 1, 0, foot,
                 self.tone["accent"] if self.message else self.tone["dim"], width)
        self.screen.noutrefresh()
        curses.doupdate()

    def _draw_rows(self, top: int, x: int, body: int, columns: int) -> None:
        rows = self.rows()
        index = self.cursor.get(self.tab, 0)
        start = self.top.get(self.tab, 0)
        start = min(start, max(0, len(rows) - body))
        if index < start:
            start = index
        elif index >= start + body:
            start = index - body + 1
        self.top[self.tab] = max(0, start)
        for offset in range(body):
            at = start + offset
            if at >= len(rows):
                break
            row = rows[at]
            attr = self.tone.get(row.tone, curses.A_NORMAL)
            if at == index and row.key:
                attr = curses.A_REVERSE | (0 if self.on_detail else curses.A_BOLD)
                self.put(top + offset, x, views.pad(" " + row.text, columns - 1),
                         attr, columns - 1)
            else:
                self.put(top + offset, x, " " + row.text, attr, columns - 1)

    def _draw_shown(self, top: int, x: int, body: int, columns: int) -> None:
        lines = self.shown(max(10, columns))
        if self.live and not self.helping:
            # A log reads from the end. `tail` is how far back from it we have
            # been pulled, so new lines arriving do not move what is on screen
            # out from under somebody who scrolled up to read it. Clamped here
            # rather than where it is set, because how far back it is possible
            # to be is a fact about the log and the room, and neither of those
            # is known to a keypress.
            self.tail = max(0, min(self.tail, max(0, len(lines) - body)))
            start = max(0, len(lines) - body - self.tail)
        else:
            self.down = max(0, min(self.down, max(0, len(lines) - body)))
            start = self.down
        for offset in range(body):
            at = start + offset
            if at >= len(lines):
                break
            line = lines[at]
            self.put(top + offset, x, line.text,
                     self.tone.get(line.tone, curses.A_NORMAL), columns)
        if start + body < len(lines):
            self.put(top + body - 1, x + max(0, columns - 6), " more ",
                     self.tone["dim"], 6)

    # -- what the keys do -------------------------------------------------

    def move(self, step: int) -> None:
        """Down or up: the cursor in the list, or what is being shown beside it."""
        if self.helping or self.live or self.on_detail:
            self.scroll(step)
            return
        rows = self.rows()
        index = self.cursor.get(self.tab, 0)
        at = index
        while True:
            at += step
            if not 0 <= at < len(rows):
                return
            if rows[at].key:
                self.cursor[self.tab] = at
                self.down = 0
                return

    def scroll(self, step: int) -> None:
        if self.live and not self.helping:
            self.tail = max(0, self.tail - step)
        else:
            self.down = max(0, self.down + step)

    def go_on(self) -> None:
        if self.world.closed:
            self.message = self.world.name + " has ended. Nothing more happens here."
            return
        self.tab = len(VIEWS)
        if self.runner.start():
            self.going = True
            self.message = "living the hours that are owed; this takes a mind"
        else:
            self.message = "already going on"

    def mark_read(self) -> None:
        """The one thing this window writes: where you stopped reading."""
        try:
            with store.tick_lock(self.root):
                world = store.load(self.root)
                world.news_seen = len(world.chronicle)
                store.save(world)
        except store.Locked as exception:
            self.message = "not now: " + str(exception)
            return
        except (OSError, ValueError) as exception:
            self.message = "could not write: " + str(exception)
            return
        self.reload()
        self.message = "read up to here"

    def key(self, pressed: int) -> bool:
        """Answer a key. False when it was the one that closes the window."""
        self.message = ""
        if pressed in (ord("q"), 27):
            if self.helping:
                self.helping = False
                return True
            return False
        if pressed == curses.KEY_RESIZE:
            self._shown = None
        elif pressed == ord("?"):
            self.helping = not self.helping
            self.down = 0
        elif ord("1") <= pressed <= ord("0") + len(VIEWS) + 1:
            self.tab = pressed - ord("1")
            self.helping = False
            self.on_detail = False
            self.down = 0
            self._settle()
        elif pressed in (ord("\t"), ord("l"), curses.KEY_RIGHT):
            self.on_detail = True
        elif pressed in (curses.KEY_BTAB, ord("h"), curses.KEY_LEFT):
            self.on_detail = False
        elif pressed in (ord("j"), curses.KEY_DOWN):
            self.move(1)
        elif pressed in (ord("k"), curses.KEY_UP):
            self.move(-1)
        elif pressed in (ord(" "), curses.KEY_NPAGE):
            self.scroll(max(1, self.screen.getmaxyx()[0] - 7))
        elif pressed in (ord("b"), curses.KEY_PPAGE):
            self.scroll(-max(1, self.screen.getmaxyx()[0] - 7))
        elif pressed == ord("g"):
            if self.on_detail or self.live or self.helping:
                self.down, self.tail = 0, 10 ** 9
            else:
                self.cursor[self.tab] = 0
                self._settle()
        elif pressed == ord("G"):
            if self.on_detail or self.live or self.helping:
                self.down, self.tail = 10 ** 9, 0
            else:
                self.cursor[self.tab] = max(0, len(self.rows()) - 1)
                self._settle()
        elif pressed == ord("r"):
            self.reload(say=True)
        elif pressed == ord("f"):
            self.follow = not self.follow
            self.message = ("following what lands" if self.follow
                            else "not following; r reads again")
        elif pressed == ord("c"):
            self.go_on()
        elif pressed == ord("m"):
            self.mark_read()
        return True

    # -- the loop ---------------------------------------------------------

    def loop(self) -> None:
        curses.curs_set(0)
        self.screen.timeout(PAUSE_MS)
        while True:
            self.draw()
            try:
                pressed = self.screen.getch()
            except KeyboardInterrupt:
                return
            if pressed != -1 and not self.key(pressed):
                return
            if self.runner.drain():
                self._shown = None
            if self.going and not self.runner.running:
                # It has finished saying whatever it had to say. The line about
                # it being under way is no longer true, so it goes.
                self.going, self.message = False, ""
            # Somebody else may have moved the world: this window's own worker,
            # a schedule behind it, or a command in another terminal.
            if self.follow and self._stamp() != self.stamp:
                self.reload()


def run(root) -> None:
    """Open a window on the world at `root`, and keep it open."""
    root = Path(root)
    if not store.exists(root):
        raise FileNotFoundError(root)
    try:
        curses.wrapper(lambda screen: App(root, screen).loop())
    except KeyboardInterrupt:
        pass
