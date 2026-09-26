"""The waiting line: what it says, and everything it must not touch.

The account of what happened is the product; the waiting line is a courtesy to
whoever is watching a terminal. So most of what is checked here is restraint -
that a pipe, a log and a test see byte for byte what they saw before there was
one, and that nothing about a world depends on anybody watching it.
"""

import contextlib
import io
import itertools
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere import backends, progress, seed
from elsewhere.backends import Call, Settings, ask, embed, probe, register
from elsewhere.backends.stub import StubBackend
from elsewhere.schemas import CallName, grammar


class Tty(io.StringIO):
    """A stream that claims to be a terminal, so the drawing is switched on."""

    def isatty(self) -> bool:
        return True


def call(name=CallName.PERCEIVE, about="p_havvah") -> Call:
    return Call(name=name, system="s", user="u", schema=grammar(name), about=about)


class Heard:
    """A watcher that only writes down what it was told."""

    def __init__(self):
        self.said = []

    def asking(self, call, attempt):
        self.said.append(("asking", call.name, attempt))

    def answered(self, call, took, ok):
        self.said.append(("answered", call.name, ok))

    def placing(self, count):
        self.said.append(("placing", count))

    def placed(self, took, ok):
        self.said.append(("placed", ok))


class WhatItSaysTest(unittest.TestCase):
    def test_a_person_is_named_and_nothing_else_is(self):
        self.assertEqual(progress.person("p_havvah"), "Havvah")
        self.assertEqual(progress.person("town"), "")
        self.assertEqual(progress.person("road"), "")

    def test_every_call_site_has_something_to_say(self):
        # A new CallName with no line here would show its own name, which is
        # not wrong but is not English either.
        for name in CallName:
            self.assertIn(name, progress.DOING, f"{name} has no waiting line")
            self.assertNotIn("{", progress.doing(call(name)))

    def test_the_ones_nobody_in_particular_is_asked_are_not_given_a_name(self):
        self.assertEqual(progress.doing(call(CallName.DIRECT, "town")),
                         "asking the town whether anything happens to it")
        self.assertTrue(progress.doing(call(CallName.ACT)).startswith("Havvah"))

    def test_a_length_of_waiting_reads_as_one(self):
        self.assertEqual(progress.span(3.4), "3s")
        self.assertEqual(progress.span(59.6), "60s")
        self.assertEqual(progress.span(64), "1m04s")
        self.assertEqual(progress.span(3600), "60m00s")


class DrawingTest(unittest.TestCase):
    def test_nothing_is_drawn_where_nothing_can_be_seen(self):
        stream = io.StringIO()                       # a pipe, a log, a test
        shown = progress.Progress(stream=stream)
        self.assertFalse(shown.live)
        with shown:
            shown.asking(call(), 1)
            shown.answered(call(), 0.1, True)
        self.assertEqual(stream.getvalue(), "")
        self.assertEqual(shown.answered_count, 1)

    def test_on_a_terminal_the_line_is_rewritten_where_it_stands(self):
        stream = Tty()
        shown = progress.Progress(stream=stream, every=1000)   # no spinning here
        with shown:
            shown.asking(call(), 1)
            drawn = stream.getvalue()
            self.assertIn("Havvah is taking it in", drawn)
            self.assertTrue(drawn.startswith("\r"))
            self.assertNotIn("\n", drawn)            # one line, and it stays one
        self.assertTrue(stream.getvalue().endswith("\r"))       # taken back off

    def test_saying_something_does_not_leave_the_line_in_it(self):
        stream = Tty()
        out = io.StringIO()
        shown = progress.Progress(stream=stream, every=1000)
        with shown:
            shown.asking(call(), 1)
            was, sys.stdout = sys.stdout, out
            try:
                shown.say("the descent")
            finally:
                sys.stdout = was
        # What was said went to stdout whole, with none of the waiting in it.
        self.assertEqual(out.getvalue(), "the descent\n")

    def test_a_second_try_says_so(self):
        shown = progress.Progress(stream=Tty(), every=1000)
        shown.asking(call(), 2)
        self.assertIn("again", shown.line())

    def test_an_unusable_answer_is_counted_where_it_can_be_seen(self):
        shown = progress.Progress(stream=Tty(), every=1000)
        shown.answered(call(), 0.1, False)
        self.assertIn("unusable", shown.line())

    def test_a_terminal_that_goes_away_does_not_take_the_run_with_it(self):
        class Closed(Tty):
            def write(self, text):
                raise OSError("gone")

        shown = progress.Progress(stream=Closed(), every=1000)
        with shown:
            shown.asking(call(), 1)                  # must not raise
            shown.answered(call(), 0.1, True)
        self.assertFalse(shown.live)
        self.assertEqual(shown.answered_count, 1)

    def test_the_line_never_runs_past_the_terminal(self):
        # A line wider than the terminal would wrap, and then \r would go back
        # to the start of the wrong line and leave a trail of them.
        shown = progress.Progress(stream=Tty(), every=1000)
        shown._doing = "x" * 500
        with shown:
            shown.draw()
        self.assertLess(shown._drawn, shutil.get_terminal_size((80, 24)).columns)


class WatchingTest(unittest.TestCase):
    """What `backends` tells a watcher, and how little it depends on one."""

    def setUp(self):
        self.heard = Heard()
        self.stub = StubBackend()
        self.settings = Settings(backend="stub", model="stub")

    def test_a_question_is_announced_and_its_answer_reported(self):
        with backends.watched(self.heard):
            ask(self.stub, call(), self.settings)
        self.assertEqual(self.heard.said,
                         [("asking", CallName.PERCEIVE, 1),
                          ("answered", CallName.PERCEIVE, True)])

    def test_a_repair_is_visible_as_a_second_asking(self):
        self.stub.set(CallName.PERCEIVE, "not json at all")
        with backends.watched(self.heard):
            self.assertIsNone(ask(self.stub, call(), self.settings))
        self.assertEqual([said[0] for said in self.heard.said],
                         ["asking", "answered", "asking", "answered"])
        self.assertEqual([said[2] for said in self.heard.said if said[0] == "asking"],
                         [1, 2])
        self.assertFalse(any(said[2] for said in self.heard.said
                             if said[0] == "answered"))

    def test_reaching_the_minds_is_a_wait_like_any_other(self):
        backends.register(self.stub)
        try:
            with backends.watched(self.heard):
                ok, _ = probe(self.settings)
            self.assertTrue(ok)
            self.assertEqual([said[0] for said in self.heard.said],
                             ["asking", "answered"])
            self.assertEqual(self.heard.said[0][1], CallName.PROBE)
        finally:
            backends._bootstrap()

    def test_placing_something_in_meaning_is_reported_too(self):
        backends.register(self.stub)
        try:
            with backends.watched(self.heard):
                self.assertTrue(embed(["the water came over the stones"],
                                      self.settings))
            self.assertEqual(self.heard.said, [("placing", 1), ("placed", True)])
        finally:
            backends._bootstrap()

    def test_an_embedder_that_is_down_is_reported_as_nothing_placed(self):
        class Down(StubBackend):
            def embed(self, texts, settings=None):
                raise OSError("no server")

        backends.register(Down())
        try:
            with backends.watched(self.heard):
                self.assertEqual(embed(["anything"], self.settings), [])
            self.assertEqual(self.heard.said, [("placing", 1), ("placed", False)])
        finally:
            backends._bootstrap()

    def test_nobody_is_told_anything_once_the_watching_is_over(self):
        with backends.watched(self.heard):
            pass
        self.assertEqual(backends._watchers, [])
        ask(self.stub, call(), self.settings)
        self.assertEqual(self.heard.said, [])

    def test_a_watcher_is_let_go_even_when_the_world_fails(self):
        with self.assertRaises(ValueError):
            with backends.watched(self.heard):
                raise ValueError("a world that could not be made")
        self.assertEqual(backends._watchers, [])

    def test_watching_leaves_the_answer_exactly_as_it_was(self):
        without = ask(self.stub, call(), self.settings)
        with backends.watched(self.heard):
            within = ask(self.stub, call(), self.settings)
        self.assertEqual(without, within)


class MakingAWorldTest(unittest.TestCase):
    """The four events, and the line each one gets while everybody takes it in."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "world"
        # Everybody keeps something of everything, and no two of them keep the
        # same words - so a line saying "3 of 3" has counted three people and
        # not three copies of one memory.
        counted = itertools.count()
        register(StubBackend({
            CallName.PERCEIVE: lambda call: {
                "stuck": True, "feeling": "fear", "means": "",
                "account": f"what {call.about} made of it ({next(counted)})"},
        }))

    def tearDown(self):
        self.tmp.cleanup()
        backends._bootstrap()          # the dial tone back, for whoever is next

    def configuration(self):
        settings = Settings(backend="stub", model="stub")
        return {name: settings for name in CallName}

    def test_a_world_built_in_silence_says_nothing(self):
        # `build` is a library call before it is anything else, and every other
        # test in this suite makes worlds by it.
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            seed.build(self.root, configuration=self.configuration())
        self.assertEqual(out.getvalue(), "")

    def test_each_event_is_accounted_for_as_it_is_taken_in(self):
        said = []
        seed.build(self.root, configuration=self.configuration(), say=said.append)
        self.assertEqual(len(said), 4)
        for line, category in zip(said, ("descent", "churning", "flood", "lifting")):
            self.assertIn(category, line)
            self.assertIn("3 of 3 kept", line)

    def test_with_no_mind_there_is_nothing_to_account_for(self):
        # Nobody was asked anything, so there is no wait to report on.
        said = []
        seed.build(self.root, configuration=None, say=said.append)
        self.assertEqual(said, [])

    def test_what_stuck_is_what_comes_back(self):
        world = seed.build(self.root, configuration=self.configuration())
        event = world.chronicle.all()[0]
        kept = seed.remember(world, event, self.configuration())
        self.assertEqual(len(kept), len(event.reached))
        self.assertEqual(sorted(memory.owner for memory in kept),
                         sorted(event.reached))

    def test_a_mind_that_keeps_nothing_is_not_counted_as_having_kept(self):
        register(StubBackend({CallName.PERCEIVE: {"stuck": False}}))
        said = []
        world = seed.build(self.root, configuration=self.configuration(),
                           say=said.append)
        self.assertIn("0 of 3 kept", said[0])
        self.assertEqual(seed.remember(world, world.chronicle.all()[0],
                                       self.configuration()), [])


if __name__ == "__main__":
    unittest.main()
