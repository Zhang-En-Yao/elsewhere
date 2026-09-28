"""The TUI's pure views, and that the window never writes. No terminal needed."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere import cli, seed
from elsewhere.tui import cartography, views

WIDE = "去年的雨"           # four columns' worth of two characters each


def text(lines):
    return "\n".join(line.text for line in lines)


class Window(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.world = seed.build(Path(self.temporary.name) / "world")

    def tearDown(self):
        self.temporary.cleanup()


class TestMeasuring(unittest.TestCase):
    """Wide characters count as two columns."""

    def test_a_wide_character_is_two_columns(self):
        self.assertEqual(views.width("ab"), 2)
        self.assertEqual(views.width(WIDE), len(WIDE) * 2)

    def test_padding_lines_up_what_a_terminal_lines_up(self):
        self.assertEqual(views.width(views.pad(WIDE[:1], 9)), 9)
        self.assertEqual(views.width(views.pad("Havvah", 9)), 9)

    def test_clipping_never_overruns_the_room_it_was_given(self):
        for columns in range(1, 12):
            self.assertLessEqual(views.width(views.clip(WIDE * 3, columns)), columns)
            self.assertLessEqual(views.width(views.clip("a word or two", columns)),
                                 columns)

    def test_what_fits_is_left_exactly_as_it_was(self):
        self.assertEqual(views.clip("Havvah", 20), "Havvah")


class TestWrapping(unittest.TestCase):

    def test_nothing_comes_back_wider_than_asked_for(self):
        line = views.Line("    Havvah   " + "a sentence that will not fit " * 4,
                          under=13)
        for columns in (20, 34, 55, 80):
            for one in views.wrap(line, columns):
                self.assertLessEqual(views.width(one.text), columns)

    def test_the_indent_and_the_columns_inside_it_survive(self):
        line = views.Line("    Havvah   He works too late, and he knows it too well.",
                          under=13)
        first = views.wrap(line, 40)[0]
        self.assertTrue(first.text.startswith("    Havvah   He"),
                        "a wrapper that normalises whitespace takes every "
                        "aligned column apart: " + repr(first.text))

    def test_the_remainder_goes_on_under_what_it_is_a_remainder_of(self):
        line = views.Line("  doing       something that will have to be wrapped",
                          under=14)
        rest = views.wrap(line, 30)[1:]
        self.assertTrue(rest)
        for one in rest:
            self.assertTrue(one.text.startswith(" " * 14), repr(one.text))
            self.assertFalse(one.text.startswith(" " * 15), repr(one.text))

    def test_a_word_longer_than_the_room_still_goes_somewhere(self):
        got = views.wrap(views.Line("  " + "x" * 200, under=2), 20)
        self.assertGreater(len(got), 1)
        self.assertEqual(sum(one.text.count("x") for one in got), 200)

    def test_a_line_that_fits_is_one_line_and_the_same_one(self):
        line = views.Line("  short enough", "dim", under=2)
        self.assertEqual(views.wrap(line, 40), [line])

    def test_the_tone_is_carried_to_every_piece(self):
        line = views.Line("  " + "long enough to split " * 5, "warn", under=2)
        got = views.wrap(line, 30)
        self.assertGreater(len(got), 1)
        self.assertTrue(all(one.tone == "warn" for one in got))


class TestMap(Window):
    """Laid out from the ways alone, so it has to hold whatever town it is given."""

    def drawn(self, key="", columns=60):
        return text(views.map_detail(self.world, key, columns))

    def test_every_place_is_on_it(self):
        drawn = self.drawn()
        for place in self.world.places.values():
            self.assertIn(place.name, drawn)

    def test_the_place_looked_at_is_the_one_in_brackets(self):
        drawn = self.drawn("marah")
        self.assertIn("[Marah]", drawn)
        self.assertNotIn("[Mizpah]", drawn)

    def test_it_is_never_wider_than_the_pane(self):
        for columns in (30, 45, 60, 90):
            labels = {place.id: place.name for place in self.world.places.values()}
            drawing = cartography.draw(labels, self.world.map.positions,
                                       self.world.map.ways, columns, 12)
            self.assertLessEqual(len(drawing), 12)
            for row in drawing:
                # The screen wraps every line; a drawing has to come through whole.
                self.assertLessEqual(views.width(row), columns, row)

    def test_the_same_town_is_drawn_the_same_way(self):
        self.assertEqual(self.drawn("yard"), self.drawn("yard"))

    def test_a_wide_name_keeps_the_columns_it_is_owed(self):
        self.world.places["marah"].name = WIDE
        for line in views.map_detail(self.world, "", 60):
            self.assertLessEqual(views.width(line.text), 60, line.text)
        self.assertIn(WIDE, self.drawn())


class TestGeography(Window):
    """Laid out once, when the world is made, and kept with it."""

    def test_every_place_is_given_a_position_when_the_world_is_made(self):
        self.assertEqual(set(self.world.map.positions), set(self.world.places))

    def test_places_fewer_ways_apart_lie_closer(self):
        import math
        from itertools import combinations
        from elsewhere.world import geography
        apart = geography.steps(list(self.world.places), self.world.map.ways)
        drawn: dict = {}
        for one, other in combinations(self.world.places, 2):
            drawn.setdefault(apart[one][other], []).append(
                math.dist(self.world.map.positions[one], self.world.map.positions[other]))
        means = [sum(distances) / len(distances) for _, distances in sorted(drawn.items())]
        self.assertEqual(means, sorted(means))

    def test_the_same_town_lies_the_same_way(self):
        from elsewhere.world import geography
        self.assertEqual(geography.layout(list(self.world.places), self.world.map.ways),
                         self.world.map.positions)

    def test_positions_survive_a_save(self):
        from elsewhere.world import store
        store.save(self.world)
        self.assertEqual(store.load(self.world.root).map.positions,
                         self.world.map.positions)

    def test_a_world_made_before_positions_still_has_a_map(self):
        self.world.map.positions = {}
        drawn = text(views.map_detail(self.world, "", 60))
        for place in self.world.places.values():
            self.assertIn(place.name, drawn)


class TestEveryViewAnswers(Window):
    def test_nothing_in_a_list_leads_nowhere(self):
        for view in views.VIEWS:
            for row in view.rows(self.world):
                if not row.key:
                    continue          # a divider; the cursor cannot land on it
                lines = view.detail(self.world, row.key, 60)
                self.assertTrue(lines, f"{view.name} says nothing about {row.key}")
                for line in lines:
                    self.assertIn(line.tone, views.TONES)

    def test_a_key_the_world_does_not_have_is_answered_and_not_raised(self):
        for view in views.VIEWS:
            self.assertTrue(view.detail(self.world, "no-such-thing", 60))

    def test_the_world_view_holds_every_place_and_the_world_itself(self):
        keys = [row.key for row in views.world_rows(self.world)]
        self.assertIn(views.WORLD_KEY, keys)
        for place_id in self.world.places:
            self.assertIn(place_id, keys)

    def test_nobody_gone_means_nothing_about_who_is_gone(self):
        self.assertNotIn(views.GONE_KEY,
                         [row.key for row in views.world_rows(self.world)])
        self.world.beings["lilith"].when.left_at = self.world.at
        self.assertIn(views.GONE_KEY,
                      [row.key for row in views.world_rows(self.world)])


class TestWhereYouStoppedReading(Window):
    def test_the_line_falls_where_you_stopped(self):
        self.world.read_through = 1
        rows = views.chronicle_rows(self.world)
        divider = [index for index, row in enumerate(rows) if row.text == views.UNREAD]
        self.assertEqual(len(divider), 1)
        self.assertEqual(rows[divider[0] - 1].key, self.world.chronicle.all()[0].id)
        self.assertEqual(rows[divider[0] + 1].key, self.world.chronicle.all()[1].id)

    def test_having_read_it_all_leaves_no_line(self):
        self.world.read_through = len(self.world.chronicle)
        self.assertNotIn(views.UNREAD,
                         [row.text for row in views.chronicle_rows(self.world)])

    def test_a_divider_is_not_something_the_cursor_can_land_on(self):
        self.world.read_through = 1
        for row in views.chronicle_rows(self.world):
            if row.text == views.UNREAD:
                self.assertEqual(row.key, "")


class TestItShowsWhatTheyCarry(Window):

    def test_the_whole_page_is_shown(self):
        havvah = self.world.beings["havvah"]
        body = text(views.being_detail(self.world, havvah.id))
        for line in havvah.who.notebook.splitlines():
            self.assertIn(line, body)

    def test_it_says_how_many_pages_came_before(self):
        from elsewhere.world.pages import Page
        havvah = self.world.beings["havvah"]
        self.world.pages(havvah.id).append(Page(at=self.world.at, notebook="one"))
        self.world.pages(havvah.id).append(Page(at=self.world.at, notebook="two"))
        # The page seed wrote them with, then these two.
        self.assertIn("newest of 3 pages", text(views.being_detail(self.world, havvah.id)))

    def test_what_they_have_not_gone_over_is_shown_apart_from_it(self):
        from elsewhere.world.notes import Note
        havvah = self.world.beings["havvah"]
        self.world.notes(havvah.id).append(Note(at=self.world.at,
                                                account="feathers on the path"))
        body = text(views.being_detail(self.world, havvah.id))
        self.assertIn("not gone over yet", body)
        self.assertIn("feathers on the path", body)
        havvah.when.settled_through = 1
        body = text(views.being_detail(self.world, havvah.id))
        self.assertNotIn("feathers on the path", body, "once gone over, only the page has it")


class TestSomebodyWhoLeft(Window):
    def test_they_are_read_as_they_stood_the_hour_they_went(self):
        lilith = self.world.beings["lilith"]
        lilith.when.left_at = self.world.at
        was = text(views.being_detail(self.world, lilith.id))
        self.assertIn(lilith.who.notebook.splitlines()[0], was)
        self.assertIn("left on", was)

        # Frozen at the moment she left.
        self.world.at += 24 * 360
        self.world.record("occurrence", "A storm broke over the town.",
                          place="bethel", informed=["havvah", "bezalel"])
        self.assertEqual(text(views.being_detail(self.world, lilith.id)), was)


class TestOneEventManyPlaces(Window):
    def test_everyone_it_reached_is_named_with_where_they_stood(self):
        event = self.world.chronicle.all()[0]
        self.assertTrue(event.informed, "the fixture proves nothing")
        body = text(views.event_detail(self.world, event.id))
        self.assertIn(event.account, body, "history's own account is shown too")
        for being_id in event.informed:
            self.assertIn(self.world.beings[being_id].name, body)
            self.assertIn(event.data["viewpoints"][being_id], body)


class FakeScreen:
    """Enough of a curses window to drive `screen.App.key`; draws nothing."""

    def getmaxyx(self):
        return (34, 100)


class TestTheWindowWritesNothing(Window):

    def files(self):
        out = {}
        for path in sorted(self.world.root.rglob("*")):
            if path.is_file():
                out[path] = (path.read_bytes(), path.stat().st_mtime_ns)
            else:
                out[path] = None
        return out

    def setUp(self):
        super().setUp()
        from elsewhere.world import store
        store.save(self.world)

    def test_looking_at_all_of_it_changes_none_of_it(self):
        was = self.files()
        for view in views.VIEWS:
            for row in view.rows(self.world):
                if row.key:
                    view.detail(self.world, row.key, 60)
        self.assertEqual(self.files(), was)

    def test_no_key_on_it_writes_anything(self):
        from elsewhere.tui import screen

        app = screen.App(self.world.root, FakeScreen())
        was = self.files()
        pressed = [ord(character) for character in "123456789jkhlgGb rfcmxyz?\t"]
        pressed += [screen.curses.KEY_DOWN, screen.curses.KEY_UP,
                    screen.curses.KEY_NPAGE, screen.curses.KEY_PPAGE,
                    screen.curses.KEY_RESIZE, screen.curses.KEY_LEFT,
                    screen.curses.KEY_RIGHT, screen.curses.KEY_BTAB]
        for _ in range(3):
            for key in pressed:
                app.key(key)
                app.shown(60)             # what a frame would ask it to work out
        self.assertEqual(self.files(), was,
                         "some key in the window wrote to the world")

    def test_it_holds_nothing_that_could_write(self):
        """Static guard: drive-the-keys only covers keys that exist today."""
        source = Path(__file__).resolve().parents[1] / "src" / "elsewhere" / "tui"
        for path in sorted(source.glob("*.py")):
            body = path.read_text(encoding="utf-8")
            for writer in ("store.save", "TickLock", ".save(", "open(",
                           "write_text", "read_through ="):
                self.assertNotIn(writer, body,
                                 f"{path.name} reaches for {writer!r}; the "
                                 f"window is supposed to only read")


if __name__ == "__main__":
    unittest.main()
