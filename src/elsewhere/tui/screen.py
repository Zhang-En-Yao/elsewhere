"""The terminal half: where each line goes, and what a key does.

Everything with an opinion about the world is in `views.py`. This file knows
about columns, tones as colours, and a cursor.

Two things here are worth saying out loud, because both are decisions rather
than mechanics:

*The window writes nothing.* Not the clock, not where you stopped reading, not
a single byte under the world's directory. Every key on it either moves the
cursor or reads the files again. Anything that changes a world is a command you
have to type - `elsewhere continue` to let it go on, `elsewhere news` to mark
what you have read, `elsewhere end` to close it for good - and that is the
point rather than an omission: you are one of this world's inhabitants and not
its console. It also means the window cannot corrupt a world, cannot race the
schedule, and needs no lock.

*The world is reloaded, never held.* The only way this window learns anything
is that the files on disk moved, which is how it sees a step the launchd agent
lived, a `continue` you ran in another terminal, and an `end`. So there is
nothing to keep in sync: watching a world that something else is running is
the only case there is.
"""

from __future__ import annotations

import curses
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..world import store
from . import views
from .views import VIEWS, Line, Row

#: How long the window waits on a key before looking at the files again. Short
#: enough that a step somebody else lived shows up while you are still looking
#: at it; long enough to be asleep the rest of the time.
PAUSE_MS = 500

KEYS = ("1-3 view   TAB pane   j/k move   g/G ends   r read again   f follow   "
        "? keys   q quit")

HELP = """\
Keys

  1 2 3       town, people, history
  TAB         move between the list and what it is showing
  j k         down and up; also the arrow keys
  g G         the top, and the end
  SPACE b     a screenful down, and back
  r           read the world off disk again, now
  f           follow: pick the world's changes up as they land (on by default)
  q           close the window

This window only reads

  Nothing on any key here writes anything under the world's directory - not
  the clock, and not where you stopped reading. So there is no key that lets
  the world go on, and none that marks the news read.

  Whatever changes a world is a command, because it is worth having typed:

    elsewhere continue        let it go on for however long you have been away
    elsewhere news            what happened since you last looked, and mark it
    elsewhere end             end it for good; what happened stays readable

  Run any of them in another terminal and this window will pick the change up
  by itself. The same goes for the launchd agent: `make schedule` keeps a day
  here to a day there, and you can leave this open while it does.
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


class App:
    """One window on one world. It reads the world and nothing else."""

    def __init__(self, root: Path, screen) -> None:
        self.root = Path(root)
        self.screen = screen
        self.world = store.load(self.root)
        self.tone = _tones()
        self.tab = 0
        self.cursor: Dict[int, int] = {}
        self.top: Dict[int, int] = {}
        self.down = 0                     # how far into what is being shown
        self.on_detail = False
        self.follow = True
        self.helping = False
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
        """Enough of the files to notice that something moved the world."""
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

    def view(self):
        return VIEWS[self.tab]

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
        rows = self.rows()
        index = self.cursor.get(self.tab, 0)
        return rows[index].key if 0 <= index < len(rows) else ""

    def _settle(self) -> None:
        """Land the cursor on something that can be landed on."""
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
        right = str(unseen) + " new" if unseen > 0 else "all read"
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
        for index, view in enumerate(VIEWS):
            label = str(index + 1) + " " + view.title
            here = index == self.tab
            self.put(1, x, label,
                     (self.tone["accent"] | curses.A_BOLD) if here
                     else self.tone["dim"], max(0, width - x))
            x += views.width(label) + 3
        self.rule(2, width)
        body, top = height - 5, 3
        if self.helping:
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
        self.down = max(0, min(self.down, max(0, len(lines) - body)))
        for offset in range(body):
            at = self.down + offset
            if at >= len(lines):
                break
            line = lines[at]
            self.put(top + offset, x, line.text,
                     self.tone.get(line.tone, curses.A_NORMAL), columns)
        if self.down + body < len(lines):
            self.put(top + body - 1, x + max(0, columns - 6), " more ",
                     self.tone["dim"], 6)

    # -- what the keys do; none of them writes anything -------------------

    def move(self, step: int) -> None:
        """Down or up: the cursor in the list, or what is being shown beside it."""
        if self.helping or self.on_detail:
            self.scroll(step)
            return
        rows = self.rows()
        at = self.cursor.get(self.tab, 0)
        while True:
            at += step
            if not 0 <= at < len(rows):
                return
            if rows[at].key:
                self.cursor[self.tab] = at
                self.down = 0
                return

    def scroll(self, step: int) -> None:
        self.down = max(0, self.down + step)

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
        elif ord("1") <= pressed <= ord("0") + len(VIEWS):
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
            if self.on_detail or self.helping:
                self.down = 0
            else:
                self.cursor[self.tab] = 0
                self._settle()
        elif pressed == ord("G"):
            if self.on_detail or self.helping:
                self.down = 10 ** 9        # clamped against the room in _draw_shown
            else:
                self.cursor[self.tab] = max(0, len(self.rows()) - 1)
                self._settle()
        elif pressed == ord("r"):
            self.reload(say=True)
        elif pressed == ord("f"):
            self.follow = not self.follow
            self.message = ("following what lands" if self.follow
                            else "not following; r reads again")
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
            # Something may have moved the world: a schedule behind it, or a
            # command in another terminal. Never this window.
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
