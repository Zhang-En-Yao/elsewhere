"""The window: what it shows, and that it never claims more than the engine would.

Only the pure half is tested, and that is the whole reason it is a pure half.
`views.py` is asked for its lines and the lines are read; nothing here opens a
terminal. What is left in `screen.py` is where on a screen to put a line, which
a test cannot check and a person can see at a glance.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere import cli, retrieval, seed
from elsewhere.tui import views
from elsewhere.world.memories import Memory

WIDE = "去年的雨"           # four columns' worth of two characters each


def text(lines):
    return "\n".join(line.text for line in lines)


class Window(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.world = seed.build(Path(self.tmp.name) / "world")

    def tearDown(self):
        self.tmp.cleanup()

    def remember(self, owner, **kw):
        base = dict(id=self.world.next_id("mem"), owner=owner, at=self.world.at,
                    account="the water rose over the fields", feeling="fear",
                    told=[self.world.at])
        base.update(kw)
        return self.world.memories(owner).add(Memory(**base))


class TestMeasuring(unittest.TestCase):
    """A world can be seeded in any language, so len() is not a width."""

    def test_a_wide_character_is_two_columns(self):
        self.assertEqual(views.width("ab"), 2)
        self.assertEqual(views.width(WIDE), len(WIDE) * 2)

    def test_padding_lines_up_what_a_terminal_lines_up(self):
        self.assertEqual(views.width(views.pad(WIDE[:1], 9)), 9)
        self.assertEqual(views.width(views.pad("Eve", 9)), 9)

    def test_clipping_never_overruns_the_room_it_was_given(self):
        for columns in range(1, 12):
            self.assertLessEqual(views.width(views.clip(WIDE * 3, columns)), columns)
            self.assertLessEqual(views.width(views.clip("a word or two", columns)),
                                 columns)

    def test_what_fits_is_left_exactly_as_it_was(self):
        self.assertEqual(views.clip("Eve", 20), "Eve")


class TestWrapping(unittest.TestCase):
    """Half of what is on screen is held in columns a space wide."""

    def test_nothing_comes_back_wider_than_asked_for(self):
        line = views.Line("    Adam     " + "a sentence that will not fit " * 4,
                          under=13)
        for columns in (20, 34, 55, 80):
            for one in views.wrap(line, columns):
                self.assertLessEqual(views.width(one.text), columns)

    def test_the_indent_and_the_columns_inside_it_survive(self):
        line = views.Line("    Adam     He works too late, and he knows it too well.",
                          under=13)
        first = views.wrap(line, 40)[0]
        self.assertTrue(first.text.startswith("    Adam     He"),
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


class TestEveryViewAnswers(Window):
    def test_nothing_in_a_list_leads_nowhere(self):
        for view in views.VIEWS:
            for row in view.rows(self.world):
                if not row.key:
                    continue          # a divider; the cursor cannot land on it
                lines = view.detail(self.world, row.key)
                self.assertTrue(lines, f"{view.name} says nothing about {row.key}")
                for line in lines:
                    self.assertIn(line.tone, views.TONES)

    def test_a_key_the_world_does_not_have_is_answered_and_not_raised(self):
        # A world reloaded under the cursor can lose whatever was selected.
        for view in views.VIEWS:
            self.assertTrue(view.detail(self.world, "no-such-thing"))

    def test_the_town_holds_every_place_and_the_world_itself(self):
        keys = [row.key for row in views.town_rows(self.world)]
        self.assertIn(views.WORLD_KEY, keys)
        for place_id in self.world.places:
            self.assertIn(place_id, keys)

    def test_nobody_gone_means_nothing_about_who_is_gone(self):
        self.assertNotIn(views.GONE_KEY,
                         [row.key for row in views.town_rows(self.world)])
        self.world.beings["p_lilith"].when.left_at = self.world.at
        self.assertIn(views.GONE_KEY,
                      [row.key for row in views.town_rows(self.world)])


class TestWhereYouStoppedReading(Window):
    def test_the_line_falls_where_you_stopped(self):
        self.world.news_seen = 1
        rows = views.chronicle_rows(self.world)
        divider = [index for index, row in enumerate(rows) if row.text == views.UNREAD]
        self.assertEqual(len(divider), 1)
        self.assertEqual(rows[divider[0] - 1].key, self.world.chronicle.all()[0].id)
        self.assertEqual(rows[divider[0] + 1].key, self.world.chronicle.all()[1].id)

    def test_having_read_it_all_leaves_no_line(self):
        self.world.news_seen = len(self.world.chronicle)
        self.assertNotIn(views.UNREAD,
                         [row.text for row in views.chronicle_rows(self.world)])

    def test_a_divider_is_not_something_the_cursor_can_land_on(self):
        self.world.news_seen = 1
        for row in views.chronicle_rows(self.world):
            if row.text == views.UNREAD:
                self.assertEqual(row.key, "")


class TestItShowsWhatTheEngineWouldHandOver(Window):
    """The one thing a window can do that a printed page cannot."""

    def test_out_of_reach_is_shown_as_out_of_reach_and_not_left_out(self):
        eve = self.world.beings["p_eve"]
        for index in range(retrieval.CONTEXT_MEMORIES + 3):
            self.remember(eve.id, account=f"the {index}th thing that happened",
                          at=self.world.at - index * 24 * 30,
                          told=[self.world.at - index * 24 * 30])
        memories = list(self.world.memories(eve.id))
        reach = retrieval.recallable(memories, self.world.at)
        self.assertLess(len(reach), len(memories), "the fixture proves nothing")

        lines = views.person_detail(self.world, eve.id)
        body = text(lines)
        for memory in memories:
            self.assertIn(memory.account, body,
                          "a window has room for what would not come back")
        self.assertIn("below here", body,
                      "and has to say where reach ended, or it is claiming "
                      "they hold all of it equally")
        # Everything above the line is in reach; everything below it is not.
        dim = [line for line in lines if line.tone == "dim"]
        for memory in memories:
            if memory in reach:
                continue
            self.assertTrue(any(memory.account in line.text for line in dim),
                            f"{memory.account!r} is out of reach and not dimmed")

    def test_a_memory_that_moved_shows_what_it_used_to_be(self):
        eve = self.world.beings["p_eve"]
        memory = self.remember(eve.id, account="the water rose over the fields")
        memory.rewrite("the water came for us", self.world.at)
        body = text(views.person_detail(self.world, eve.id))
        self.assertIn("the water came for us", body)
        self.assertIn("the water rose over the fields", body)

    def test_a_belief_with_nothing_left_to_point_at_says_so(self):
        from elsewhere.world.entities import Belief
        eve = self.world.beings["p_eve"]
        gone = self.remember(eve.id, account="a thing nobody has thought of since",
                             at=0.0, told=[0.0])
        for index in range(retrieval.CONTEXT_MEMORIES + 1):
            self.remember(eve.id, account=f"something newer, {index}")
        eve.who.beliefs.append(Belief(claim="the water always comes back",
                                      origin=[gone.id], held=[self.world.at]))
        self.assertTrue(retrieval.on_faith(eve.who.beliefs[0],
                                           self.world.memories(eve.id), self.world.at),
                        "the fixture proves nothing")
        self.assertIn("on faith", text(views.person_detail(self.world, eve.id)))


class TestSomebodyWhoLeft(Window):
    def test_they_are_read_as_they_stood_the_hour_they_went(self):
        lilith = self.world.beings["p_lilith"]
        memory = self.remember(lilith.id, account="the ridge path, and the valley")
        lilith.when.left_at = self.world.at
        was = text(views.person_detail(self.world, lilith.id))
        self.assertIn("the ridge path, and the valley", was)
        self.assertIn("left on", was)

        # A year of world time passes for everybody else. Nothing about them
        # may move: the world has no idea what has become of them.
        self.world.at += 24 * 360
        self.assertEqual(text(views.person_detail(self.world, lilith.id)), was)
        self.assertIn(memory.account,
                      text(views.person_detail(self.world, lilith.id)))


class TestOneEventManyVersions(Window):
    def test_everyone_who_was_there_is_put_beside_everyone_else(self):
        event = self.world.chronicle.all()[0]
        kept = {}
        for person_id in event.reached:
            kept[person_id] = self.remember(
                person_id, account=f"what {person_id} would say about it",
                event_id=event.id)
        body = text(views.event_detail(self.world, event.id))
        self.assertIn(event.account, body, "history's own account is shown too")
        for person_id, memory in kept.items():
            self.assertIn(memory.account, body)
            self.assertIn(self.world.beings[person_id].name, body)

    def test_somebody_who_was_there_and_kept_nothing_is_still_named(self):
        event = self.world.chronicle.all()[0]
        self.assertTrue(event.reached, "the fixture proves nothing")
        body = text(views.event_detail(self.world, event.id))
        for person_id in event.reached:
            self.assertIn(self.world.beings[person_id].name, body)
        self.assertIn("nothing stayed", body)


class TestOneReport(Window):
    """A step is shown by a terminal and by a window, and formats itself once."""

    def test_the_printed_report_is_the_lines_and_nothing_else(self):
        import io
        from contextlib import redirect_stdout
        from elsewhere.tick import TickReport

        report = TickReport(label="Year 1, day 1, 08:00", hours=2.0)
        caught = io.StringIO()
        with redirect_stdout(caught):
            cli.print_report(self.world, report)
        self.assertEqual(caught.getvalue().splitlines(),
                         [""] + cli.report_lines(self.world, report))

    def test_a_step_where_nothing_was_scheduled_says_so(self):
        from elsewhere.tick import TickReport
        lines = cli.report_lines(self.world, TickReport(label="x", idle=True))
        self.assertIn("nothing in the world is scheduled", "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
