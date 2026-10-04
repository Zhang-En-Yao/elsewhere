"""Terminal layout and key handling for the TUI.

Writes nothing, so it needs no lock; it reloads the world whenever the files
on disk change.
"""

from __future__ import annotations

import curses
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ...adapters import storage
from .. import bookmark
from . import views
from .views import VIEWS, Line, Row

#: Key wait before re-checking the files for changes.
PAUSE_MILLISECONDS = 500

#: Rows above the list: the bar, the tabs, the rule.
FIXED_ROWS = 3

#: How long the logo stays on closing when nothing is pressed.
CLOSING_MILLISECONDS = 1000

#: How long each frame of the logo's wingbeat stays.
FRAME_MILLISECONDS = 130

#: Every key only moves what is being looked at; `?` lists them.
KEYS = "esc back   ? keys   q quit"

#: How many pages back Esc and Backspace can go.
TRAIL = 64

HELP = """\
Keys

  1 2 3 4     world, beings, history, view, the tabs in order
  ENTER       go where this leads: a place, a being or an event to where it
              is on the map; a place on the map to all of what is known of it
  ESC         back to the page before, however you left it: Enter, a click
              or another tab (BACKSPACE too); on this page, close it
  mouse       click a tab or a row, double-click to go where it leads, and
              scroll with the wheel
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


def tones() -> Dict[str, int]:
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
    return {
        "plain": plain,
        "dim": curses.A_DIM,
        "bold": curses.A_BOLD,
        "accent": accent,
        "warn": warn,
        "rule": curses.A_DIM,
    }


class App:

    def __init__(self, root: Path, screen) -> None:
        self.root = Path(root)
        self.screen = screen
        self.world = storage.load(self.root)
        self.tones = tones()
        self.tab = 0
        self.cursor: Dict[int, int] = {}
        self.top: Dict[int, int] = {}
        self.down = 0  # how far into what is being shown
        self.on_detail = False
        self.follow = True
        self.helping = False
        self.message = ""
        #: Where Enter has led from, to go back to: (tab, row key).
        self.trail: List[Tuple[int, str]] = []
        #: Where the last frame put things, for the mouse to find.
        self.tab_spans: List[Tuple[int, int]] = []
        self.list_columns = 0
        self.body = 0
        self.stamp = self._stamp()
        self._shown: Optional[Tuple] = None
        self._lines: List[Line] = []
        self._listed: Optional[Tuple] = None
        self._rows: List[Row] = []
        for index in range(len(VIEWS)):
            self.cursor[index], self.top[index] = 0, 0
        self.snap()

    def _stamp(self) -> tuple:
        """Cheap fingerprint of the files, to detect changes."""
        times = []
        for path in (self.root / "world.json", self.root / "chronicle.jsonl"):
            try:
                times.append(path.stat().st_mtime_ns)
            except OSError:
                times.append(0)
        try:
            times.append(
                sum(
                    path.stat().st_mtime_ns
                    for path in [
                        *(self.root / "beings").glob("*.json"),
                        *(self.root / "episodes").glob("*.jsonl"),
                    ]
                )
            )
        except OSError:
            times.append(0)
        return tuple(times)

    def reload(self, announce: bool = False) -> None:
        """Reload, keeping the current selection."""
        selected = self.selected()
        try:
            self.world = storage.load(self.root)
        except (OSError, ValueError) as exception:
            self.message = "could not read the world: " + str(exception)
            return
        self.stamp = self._stamp()
        self._shown = self._listed = None
        if selected:
            for index, row in enumerate(self.rows()):
                if row.key == selected:
                    self.cursor[self.tab] = index
                    break
        self.snap()
        if announce:
            self.message = "read again at " + time.strftime("%H:%M:%S")

    def view(self):
        return VIEWS[self.tab]

    def rows(self) -> List[Row]:
        """Cached per change: a frame asks several times and it walks the
        whole chronicle."""
        key = (self.tab, self.stamp)
        if key != self._listed:
            self._listed, self._rows = key, self.view().rows(self.world)
        return self._rows

    def selected(self) -> str:
        rows = self.rows()
        index = self.cursor.get(self.tab, 0)
        return rows[index].key if 0 <= index < len(rows) else ""

    def snap(self) -> None:
        """Put the cursor back on a selectable row."""
        rows = self.rows()
        index = min(max(0, self.cursor.get(self.tab, 0)), max(0, len(rows) - 1))
        if rows and not rows[index].key:
            after = [position for position in range(index, len(rows)) if rows[position].key]
            before = [position for position in range(index, -1, -1) if rows[position].key]
            index = after[0] if after else (before[0] if before else index)
        self.cursor[self.tab] = index

    def shown(self, columns: int) -> List[Line]:
        """Wrapped detail pane, cached per change."""
        # The minute, too: what is due "now" moves with the wall clock.
        key = (self.tab, self.selected(), columns, self.stamp, self.helping, int(time.time() // 60))
        if key == self._shown:
            return self._lines
        if self.helping:
            source = [Line(text) for text in HELP.splitlines()]
        else:
            source = self.view().detail(self.world, self.selected(), columns)
        wrapped: List[Line] = []
        for line in source:
            wrapped.extend(views.wrap(line, columns))
        self._shown, self._lines = key, wrapped
        return wrapped

    def put(self, y: int, x: int, text: str, attribute: int, columns: int) -> None:
        if columns <= 0 or y < 0:
            return
        try:
            self.screen.addstr(y, x, views.clip(text, columns), attribute)
        except curses.error:
            pass  # the last cell of the last line

    def rule(self, y: int, width: int) -> None:
        try:
            self.screen.hline(y, 0, curses.ACS_HLINE, width)
        except curses.error:
            pass

    def draw(self) -> None:
        self.screen.erase()
        height, width = self.screen.getmaxyx()
        if height < 8 or width < 40:
            self.put(0, 0, "a little more room, please", self.tones["dim"], width)
            self.screen.noutrefresh()
            curses.doupdate()
            return
        world = self.world
        left = (
            world.name
            + "   "
            + world.label()
            + "   the sun "
            + ("is up" if world.daylight else "is down")
        )
        if world.closed:
            left += "   (ended)"
        unread = len(world.chronicle) - bookmark.load(world)
        right = str(unread) + " new" if unread > 0 else "all read"
        groups = views.upcoming(world)
        if groups and not world.closed:
            soonest = groups[0][0]
            right = (
                "next "
                + (
                    "now"
                    if soonest <= world.current
                    else views.wall(views.by_clock(world, soonest), time.time())
                )
                + ("" if views.agent(world) else ", not scheduled")
                + "   "
                + right
            )
        if not self.follow:
            right += "   not following"
        # On a narrow terminal the clock is dropped before the status.
        room = max(0, width - views.width(right) - 2)
        self.put(0, 0, views.pad(views.clip(left, room), width), curses.A_REVERSE, width)
        self.put(
            0,
            max(0, width - views.width(right) - 1),
            right,
            curses.A_REVERSE | curses.A_BOLD,
            width,
        )
        x = 1
        self.tab_spans = []
        for index, view in enumerate(VIEWS):
            label = view.title
            self.tab_spans.append((x, x + views.width(label)))
            here = index == self.tab
            self.put(
                1,
                x,
                label,
                (self.tones["accent"] | curses.A_BOLD) if here else self.tones["dim"],
                max(0, width - x),
            )
            x += views.width(label) + 3
        self.rule(2, width)
        body, top = height - 5, FIXED_ROWS
        self.body = body
        self.list_columns = 0
        if self.helping:
            self.draw_shown(top, 0, body, width)
        else:
            columns = max(20, min(46, width * 2 // 5))
            self.list_columns = columns
            self.draw_rows(top, 0, body, columns)
            try:
                self.screen.vline(top, columns, curses.ACS_VLINE, body)
            except curses.error:
                pass
            self.draw_shown(top, columns + 2, body, width - columns - 3)
        self.rule(height - 2, width)
        foot = self.message or KEYS
        self.put(
            height - 1, 0, foot, self.tones["accent"] if self.message else self.tones["dim"], width
        )
        self.screen.noutrefresh()
        curses.doupdate()

    def draw_rows(self, top: int, x: int, body: int, columns: int) -> None:
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
            position = start + offset
            if position >= len(rows):
                break
            row = rows[position]
            attribute = self.tones.get(row.tone, curses.A_NORMAL)
            if position == index and row.key:
                attribute = curses.A_REVERSE | (0 if self.on_detail else curses.A_BOLD)
                self.put(
                    top + offset, x, views.pad(" " + row.text, columns - 1), attribute, columns - 1
                )
            else:
                self.put(top + offset, x, " " + row.text, attribute, columns - 1)

    def draw_shown(self, top: int, x: int, body: int, columns: int) -> None:
        lines = self.shown(max(10, columns))
        self.down = max(0, min(self.down, max(0, len(lines) - body)))
        for offset in range(body):
            position = self.down + offset
            if position >= len(lines):
                break
            line = lines[position]
            self.put(
                top + offset, x, line.text, self.tones.get(line.tone, curses.A_NORMAL), columns
            )
            for column, text, tone in line.spans:
                self.put(
                    top + offset,
                    x + column,
                    text,
                    self.tones.get(tone, curses.A_NORMAL),
                    columns - column,
                )
        if self.down + body < len(lines):
            self.put(top + body - 1, x + max(0, columns - 6), " more ", self.tones["dim"], 6)

    def move(self, step: int) -> None:
        if self.helping or self.on_detail:
            self.scroll(step)
            return
        rows = self.rows()
        position = self.cursor.get(self.tab, 0)
        while True:
            position += step
            if not 0 <= position < len(rows):
                return
            if rows[position].key:
                self.cursor[self.tab] = position
                self.down = 0
                return

    def go(self, tab: int, key: str = "", remember: bool = True) -> None:
        """Show another page, on the row `key` if it has one. Leaving a page
        leaves it on the trail, to come back to."""
        if remember and tab != self.tab:
            self.trail.append((self.tab, self.selected()))
            del self.trail[:-TRAIL]
        self.tab = tab
        self.helping = False
        self.on_detail = False
        self.down = 0
        for index, row in enumerate(self.rows()):
            if key and row.key == key:
                self.cursor[tab] = index
                break
        self.snap()

    def lead(self) -> None:
        """Enter: go where the selected row leads, remembering the way back."""
        selected = self.selected()
        target = self.view().link(self.world, selected) if selected else None
        names = [view.name for view in VIEWS]
        if target is None or target[0] not in names:
            self.message = "nothing leads on from here"
            return
        self.go(names.index(target[0]), target[1])

    def back(self) -> None:
        if not self.trail:
            self.message = "nowhere to go back to"
            return
        tab, key = self.trail.pop()
        self.go(tab, key, remember=False)

    def click(self) -> None:
        """A mouse event: tabs and rows are clicked, the wheel scrolls."""
        try:
            _, x, y, _, state = curses.getmouse()
        except curses.error:
            return
        up = state & curses.BUTTON4_PRESSED
        down = state & getattr(curses, "BUTTON5_PRESSED", 0)
        in_list = 0 <= x < self.list_columns
        if up or down:
            step = -1 if up else 1
            if in_list and not self.helping:
                self.on_detail = False
                self.move(step)
            else:
                self.scroll(3 * step)
            return
        if y == 1:
            for index, (start, end) in enumerate(self.tab_spans):
                if start <= x < end and index != self.tab:
                    self.go(index)
            return
        row = y - FIXED_ROWS
        if not 0 <= row < self.body or self.helping:
            return
        if not in_list:
            self.on_detail = True
            return
        position = self.top.get(self.tab, 0) + row
        rows = self.rows()
        if position < len(rows) and rows[position].key:
            if position != self.cursor.get(self.tab):
                self.down = 0
            self.cursor[self.tab] = position
            self.on_detail = False
            if state & curses.BUTTON1_DOUBLE_CLICKED:
                self.lead()

    def scroll(self, step: int) -> None:
        self.down = max(0, self.down + step)

    def key(self, pressed: int) -> bool:
        """False when the key closes the window."""
        self.message = ""
        if pressed == ord("q"):
            if self.helping:
                self.helping = False
                return True
            return False
        if pressed == 27:  # Esc: out of the keys page, else back
            if self.helping:
                self.helping = False
            else:
                self.back()
            return True
        if pressed == curses.KEY_RESIZE:
            self._shown = None
        elif pressed == ord("?"):
            self.helping = not self.helping
            self.down = 0
        elif ord("1") <= pressed <= ord("0") + len(VIEWS):
            self.go(pressed - ord("1"))
        elif pressed in (ord("\n"), ord("\r"), curses.KEY_ENTER):
            if not self.helping:
                self.lead()
        elif pressed in (curses.KEY_BACKSPACE, 127, 8):
            self.back()
        elif pressed == curses.KEY_MOUSE:
            self.click()
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
                self.snap()
        elif pressed == ord("G"):
            if self.on_detail or self.helping:
                self.down = 10**9  # clamped against the room in draw_shown
            else:
                self.cursor[self.tab] = max(0, len(self.rows()) - 1)
                self.snap()
        elif pressed == ord("r"):
            self.reload(announce=True)
        elif pressed == ord("f"):
            self.follow = not self.follow
            self.message = "following what lands" if self.follow else "not following; r reads again"
        return True

    def splash(self, milliseconds: int) -> None:
        """The logo, its wings beating, with the world's name under it, until a
        key is pressed or `milliseconds` pass (-1: until a key). The key is not
        passed on; resizing the terminal only redraws it."""
        shown = -1 if milliseconds < 0 else max(1, milliseconds // FRAME_MILLISECONDS)
        self.screen.timeout(FRAME_MILLISECONDS)
        index = 0
        while index != shown:
            height, width = self.screen.getmaxyx()
            frames = views.logo(width - 2, height - 3)
            if not frames:
                return
            drawing = frames[index % len(frames)]
            # Centred on the widest frame, so the drawing does not shift as it beats.
            widest = views.widest(width - 2, height - 3)
            caption = [
                ("Elsewhere", self.tones["bold"]),
                (self.world.name + "   " + self.world.label(), self.tones["dim"]),
            ]
            self.screen.erase()
            top = max(0, (height - len(drawing) - 1 - len(caption)) // 2)
            left = max(0, (width - widest) // 2)
            for offset, line in enumerate(drawing):
                self.put(top + offset, left, line, self.tones["plain"], width - left)
            for offset, (text, attribute) in enumerate(caption, start=len(drawing) + 1):
                self.put(
                    top + offset, max(0, (width - views.width(text)) // 2), text, attribute, width
                )
            self.screen.noutrefresh()
            curses.doupdate()
            if self.screen.getch() not in (-1, curses.KEY_RESIZE):
                return
            index += 1

    def loop(self) -> None:
        curses.curs_set(0)
        # Esc on its own, without waiting to see whether a sequence follows.
        curses.set_escdelay(25)
        curses.mousemask(
            curses.BUTTON1_CLICKED
            | curses.BUTTON1_DOUBLE_CLICKED
            | curses.BUTTON4_PRESSED
            | getattr(curses, "BUTTON5_PRESSED", 0)
        )
        self.splash(-1)
        self.screen.timeout(PAUSE_MILLISECONDS)
        while True:
            self.draw()
            try:
                pressed = self.screen.getch()
            except KeyboardInterrupt:
                break
            if pressed != -1 and not self.key(pressed):
                break
            if self.follow and self._stamp() != self.stamp:
                self.reload()
        self.splash(CLOSING_MILLISECONDS)


def run(root) -> None:
    root = Path(root)
    if not storage.exists(root):
        raise FileNotFoundError(root)
    try:
        curses.wrapper(lambda screen: App(root, screen).loop())
    except KeyboardInterrupt:
        pass
