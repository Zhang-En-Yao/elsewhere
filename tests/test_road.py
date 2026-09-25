"""The road runs both ways: who walks out of the world, and who walks into it.

Everything here is the engine's half. Whether somebody wants to go is the
mind's business and is not tested. Whether the world will let them, and what it
does to a town when they do, is.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere import agents, cli, seed, tick as tick_mod
from elsewhere.backends import Settings, register
from elsewhere.backends.stub import StubBackend
from elsewhere.world import chronicle
from elsewhere.world.memories import Trace

CALLS = ("perceive", "act", "speak", "recall", "reflect", "direct", "arrive")
STAY = {"because": "", "doing": "", "action": "stay", "target": ""}
QUIET = {"why_now": "", "what": "", "where": "The Shelter", "who": "",
         "reach": "the people there", "happens": False}
GOING = {"because": "I said I would go before the rains", "action": "leave",
         "target": ""}
NOBODY = {"comes": False}
SOMEBODY = {"why_now": "nobody has tended the ridge plants since she went",
            "name": "Tam", "from_where": "beyond the ridge",
            "card": "You came for the plants and you keep to them.",
            "voice": "Dry, and not much of it.", "comes": True}


def config():
    return {name: Settings(backend="stub", model="stub") for name in CALLS}


class Road(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.world = seed.build(Path(self.tmp.name) / "world")
        self.stub = StubBackend({"act": STAY, "perceive": {"weight": "nothing"},
                                 "direct": QUIET, "reflect": {}, "arrive": NOBODY})
        register(self.stub)
        # Lilith begins on the ridge path, which is the way out of Wend.
        self.lilith = self.world.beings["p_lilith"]

    def tearDown(self):
        self.tmp.cleanup()

    def calls(self, name):
        return [c for c in self.stub.calls if c.name == name]


    def present(self):
        return sorted(p.id for p in self.world.beings.values() if p.present)

    def send_lilith_away(self):
        """Put Lilith on the road and let her take it."""
        self.lilith.place = "ridge"
        self.stub.answers["act|p_lilith"] = GOING
        report = tick_mod.tick(self.world, config())
        self.stub.answers["act|p_lilith"] = STAY
        return report


class TestWhetherAnyoneCanGoAtAll(Road):
    def test_only_from_where_the_road_goes_out(self):
        self.assertEqual(agents.leaving_place(self.world).id, "ridge")
        self.assertTrue(agents.may_leave(self.world, self.lilith))
        self.lilith.place = "yard"
        self.assertFalse(agents.may_leave(self.world, self.lilith),
                         "the yard is not a way out of anywhere")

    def test_the_hour_is_not_the_engine_s_business(self):
        # There used to be a fourth gate here: not at night. It was the engine
        # deciding that nobody is the sort of person who walks out in the dark.
        self.world.at = 3 * 24 + 3.0                 # three in the morning
        self.assertFalse(self.world.daylight)
        self.assertTrue(agents.may_leave(self.world, self.lilith),
                        "whether to go at this hour is hers to answer, in 'because'")

    def test_not_if_it_would_stop_being_a_town(self):
        self.world.beings["p_adam"].present = False
        self.assertEqual(len(self.present()), 2)
        self.assertFalse(agents.may_leave(self.world, self.lilith),
                         "two people are not a town anybody can leave")

    def test_not_twice_in_the_same_season(self):
        # A filler person keeps the town above the floor after Lilith goes, so
        # the day-gap gate is what is actually being tested here, not the floor.
        self.world.beings["p_x0"] = type(self.lilith)(id="p_x0", name="X0", place="shelter")
        self.send_lilith_away()
        eve = self.world.beings["p_eve"]
        eve.place = "ridge"
        self.assertFalse(agents.may_leave(self.world, eve))
        self.world.at += agents.DEPARTURE_MIN_GAP
        self.assertTrue(agents.may_leave(self.world, eve))

    def test_the_verb_is_not_in_the_vocabulary_anywhere_else(self):
        self.lilith.place = "yard"
        tick_mod.tick(self.world, config())
        schema = next(c for c in self.calls("act") if c.about == "p_lilith").schema
        self.assertNotIn("leave", schema["properties"]["action"]["enum"])

    def test_and_is_where_it_is(self):
        tick_mod.tick(self.world, config())
        schema = next(c for c in self.calls("act") if c.about == "p_lilith").schema
        self.assertIn("leave", schema["properties"]["action"]["enum"])
        user = next(c for c in self.calls("act") if c.about == "p_lilith").user
        self.assertIn("road also goes out", user)

    def test_a_lenient_backend_still_cannot_walk_someone_out(self):
        self.lilith.place = "yard"           # no road out of the yard
        self.stub.answers["act|p_lilith"] = GOING
        report = tick_mod.tick(self.world, config())
        self.assertEqual(report.decisions["p_lilith"].action, "stay")
        self.assertIn("p_lilith", self.present())


class TestGoing(Road):
    def test_she_is_gone(self):
        report = self.send_lilith_away()
        self.assertEqual(len(report.departures), 1)
        self.assertFalse(self.lilith.present)
        self.assertEqual(self.lilith.left_at, self.world.at)
        self.assertNotIn("p_lilith", self.present())
        self.assertNotIn(self.lilith, self.world.beings_at("ridge"))

    def test_the_whole_town_hears_it(self):
        report = self.send_lilith_away()
        event = self.world.chronicle.get(report.departures[0].event_id)
        self.assertEqual(event.category, chronicle.DEPARTURE)
        self.assertEqual(sorted(event.reached), sorted(self.world.beings))
        eve = next(c for c in self.calls("perceive") if c.about == "p_eve")
        self.assertIn("word of it reached you", eve.user)

    def test_she_gets_one_last_look_at_it(self):
        self.send_lilith_away()
        hers = next(c for c in self.calls("perceive") if c.about == "p_lilith")
        self.assertIn("looking back", hers.user)

    def test_what_she_had_stays_where_it_is(self):
        self.world.traces("p_lilith").add(Trace(
            id="mem9001", owner="p_lilith", at=self.world.at,
            trace="the valley disappearing under the water", salience=0.9,
            touched_at=self.world.at))
        self.send_lilith_away()
        kept = list(self.world.traces("p_lilith"))
        self.assertIn("mem9001", [t.id for t in kept])

    def test_and_so_does_what_everyone_wrote_about_her(self):
        self.send_lilith_away()
        eve = self.world.beings["p_eve"]
        self.assertEqual(eve.regards["p_lilith"].account,
                         "Young. Always about to go somewhere.")

    def test_whoever_went_to_find_her_finds_the_road(self):
        adam = self.world.beings["p_adam"]
        adam.place = "ridge"
        self.stub.answers["act|p_adam"] = {"because": "", "action": "talk",
                                           "target": "Lilith"}
        report = self.send_lilith_away()
        self.assertIn(("p_adam", "p_lilith"), report.missed)
        self.assertIn("who had gone", adam.doing)
        self.assertEqual(report.talks, [])

    def test_the_town_stops_asking_her_anything(self):
        self.send_lilith_away()
        before = len(self.calls("act"))
        tick_mod.tick(self.world, config())
        asked = [c.about for c in self.calls("act")[before:]]
        self.assertNotIn("p_lilith", asked)

    def test_and_stops_offering_her_to_the_director(self):
        self.send_lilith_away()
        # The town is asked once a day, and the first asking of this one came
        # in the same step she went, before she had gone. Wait for the next.
        self.world.at += 24
        tick_mod.tick(self.world, config())
        call = self.calls("direct")[-1]
        self.assertNotIn("Lilith", call.schema["properties"]["who"]["enum"])
        listed = call.user.split("People:")[1].split("Lately")[0]
        self.assertNotIn("Lilith", listed,
                         "nor standing on the ridge path among the people it is shown")
        self.assertIn("Lilith took the road", call.user,
                      "but the record still says she went - that is why_now material")


class TestComing(Road):
    def after_a_gap(self, hours=None):
        self.world.at += agents.ARRIVAL_MIN_GAP if hours is None else hours
        return tick_mod.tick(self.world, config())

    def test_a_whole_town_draws_nobody(self):
        tick_mod.tick(self.world, config())
        self.assertEqual(self.calls("arrive"), [],
                         "nobody is missing; the road is not even asked")

    def test_a_town_short_of_somebody_waits_first(self):
        self.send_lilith_away()
        tick_mod.tick(self.world, config())
        self.assertEqual(self.calls("arrive"), [],
                         "the step after she went is too soon")

    def test_then_it_asks(self):
        self.send_lilith_away()
        self.after_a_gap()
        self.assertEqual(len(self.calls("arrive")), 1)

    def test_usually_nobody_comes(self):
        self.send_lilith_away()
        report = self.after_a_gap()
        self.assertIsNone(report.arrival)
        self.assertEqual(len(self.present()), 2)

    def test_somebody_comes_up_the_road(self):
        self.send_lilith_away()
        self.stub.set("arrive", SOMEBODY)
        report = self.after_a_gap()

        self.assertIsNotNone(report.arrival)
        tam = self.world.being_by_name("Tam")
        self.assertIsNotNone(tam)
        self.assertEqual(tam.id, "p_tam")
        self.assertEqual(tam.place, "ridge", "they come in the way she went out")
        self.assertEqual(tam.card, "You came for the plants and you keep to them.")
        self.assertEqual(tam.arrived_at, self.world.at)
        self.assertTrue(tam.present)
        self.assertEqual(tam.home, "", "a newcomer has nowhere of their own")

        event = self.world.chronicle.get(report.arrival.event_id)
        self.assertEqual(event.category, chronicle.ARRIVAL)
        self.assertEqual(event.involved, ["p_tam"])
        self.assertIn("beyond the ridge", event.account)

    def test_the_newcomer_gets_their_first_day(self):
        self.send_lilith_away()
        self.stub.set("arrive", SOMEBODY)
        before = len(self.calls("act"))
        self.after_a_gap()
        asked = [c.about for c in self.calls("act")[before:]]
        self.assertIn("p_tam", asked,
                      "they arrive in the morning and live the day they arrived")

    def test_they_see_the_place_for_the_first_time(self):
        self.send_lilith_away()
        self.stub.set("arrive", SOMEBODY)
        before = len(self.calls("perceive"))
        self.after_a_gap()
        theirs = next(c for c in self.calls("perceive")[before:] if c.about == "p_tam")
        self.assertIn("for the first time", theirs.user)

    def test_nobody_here_knows_them(self):
        self.send_lilith_away()
        self.stub.set("arrive", SOMEBODY)
        self.after_a_gap()
        tam = self.world.being_by_name("Tam")
        self.assertEqual(tam.regards, {})
        self.assertEqual(self.world.beings["p_eve"].regards.get("p_tam"), None)

    def test_the_road_is_told_who_is_missing(self):
        self.send_lilith_away()
        self.stub.set("arrive", SOMEBODY)
        self.after_a_gap()
        user = self.calls("arrive")[0].user
        self.assertIn("Who has gone", user)
        self.assertIn("Lilith", user)

    def test_asking_counts_even_when_nobody_comes(self):
        self.send_lilith_away()
        self.after_a_gap()                   # asked; nobody came
        self.assertEqual(len(self.calls("arrive")), 1)
        asked_at = self.world.road_asked_at
        tick_mod.tick(self.world, config())
        self.assertEqual(len(self.calls("arrive")), 1,
                         "a town that is owed somebody still does not ask every step")
        self.assertEqual(self.world.road_asked_at, asked_at,
                         "and the anchor stays where the asking put it")

    def test_a_town_that_is_whole_waits_a_year(self):
        self.send_lilith_away()
        self.stub.set("arrive", SOMEBODY)
        self.after_a_gap()
        self.assertEqual(len(self.present()), 3, "back to the size it began at")
        self.assertFalse(agents.may_arrive(self.world))
        self.world.at += agents.ARRIVAL_MIN_GAP
        self.assertFalse(agents.may_arrive(self.world), "a month is not enough now")
        self.world.at += agents.ARRIVAL_SETTLED_GAP
        self.assertTrue(agents.may_arrive(self.world))

    def test_and_can_then_be_more_than_it_ever_was(self):
        self.stub.set("arrive", {**SOMEBODY, "name": "Edda"})
        self.after_a_gap(agents.ARRIVAL_SETTLED_GAP)
        self.assertEqual(len(self.present()), 4,
                         "nobody left, and the town is bigger than it started")

    def test_but_not_more_than_a_town_anybody_knows(self):
        for n in range(agents.TOWN_CEILING - len(self.present())):
            self.world.beings[f"p_x{n}"] = type(self.lilith)(
                id=f"p_x{n}", name=f"X{n}", place="shelter")
        self.assertEqual(len(self.present()), agents.TOWN_CEILING)
        self.world.at += agents.ARRIVAL_SETTLED_GAP * 2
        self.assertFalse(agents.may_arrive(self.world))

    def test_and_can_shrink_until_it_stops_being_one(self):
        # A filler person is added first, so the floor is reached one departure
        # later than it would be from the seed's three alone, and both the
        # allowed and the blocked departure can be seen in one test.
        filler = type(self.lilith)(id="p_x0", name="X0", place="shelter")
        self.world.beings["p_x0"] = filler
        self.send_lilith_away()                    # 3 present: adam, eve, x0
        filler.place = "ridge"
        self.world.at += agents.DEPARTURE_MIN_GAP
        self.assertTrue(agents.may_leave(self.world, filler))
        filler.present = False
        adam = self.world.beings["p_adam"]
        adam.place = "ridge"
        self.world.at += agents.DEPARTURE_MIN_GAP
        self.assertEqual(len(self.present()), 2)
        self.assertFalse(agents.may_leave(self.world, adam),
                         "the last two cannot both walk out")

    def test_a_name_the_town_already_uses_is_refused(self):
        self.send_lilith_away()
        self.stub.set("arrive", {**SOMEBODY, "name": "Eve"})
        report = self.after_a_gap()
        self.assertIsNone(report.arrival)
        self.assertEqual(len(self.present()), 2)

    def test_so_is_coming_back_under_the_same_name(self):
        self.send_lilith_away()
        self.stub.set("arrive", {**SOMEBODY, "name": "Lilith"})
        report = self.after_a_gap()
        self.assertIsNone(report.arrival, "Lilith is gone, and her name went with her")


class TestReading(Road):
    def test_the_report_survives_both(self):
        report = self.send_lilith_away()
        cli.print_report(self.world, report)          # must not raise
        self.stub.set("arrive", SOMEBODY)
        self.world.at += agents.ARRIVAL_MIN_GAP
        cli.print_report(self.world, tick_mod.tick(self.world, config()))

    def test_somebody_who_left_is_read_as_they_were(self):
        self.world.traces("p_lilith").add(Trace(
            id="mem9001", owner="p_lilith", at=self.world.at,
            trace="the valley disappearing under the water", salience=0.5,
            touched_at=self.world.at))
        self.send_lilith_away()
        left_at = self.lilith.left_at
        self.world.at += 4000 * 24                 # long enough to lose anything
        from elsewhere import retrieval
        trace = list(self.world.traces("p_lilith"))[0]
        self.assertTrue(retrieval.dormant(trace, self.world.at))
        self.assertFalse(retrieval.dormant(trace, left_at),
                         "as of the day she went, she still had it")


if __name__ == "__main__":
    unittest.main()
