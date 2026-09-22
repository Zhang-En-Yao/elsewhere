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
from elsewhere.world.memories import Trace

CALLS = ("perceive", "act", "speak", "recall", "reflect", "direct", "arrive")
STAY = {"because": "", "action": "stay", "target": ""}
QUIET = {"why_now": "", "what": "", "where": "The Old Market", "who": "",
         "reach": "the people there", "tags": [], "happens": False}
GOING = {"because": "I said I would go before winter", "action": "leave",
         "target": ""}
NOBODY = {"comes": False}
SOMEBODY = {"why_now": "nobody has ground grain since the miller went",
            "name": "Tam", "from_where": "the coast road", "trade": "miller",
            "age": 30, "card": "You came for the mill and you keep to it.",
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
        # Carol begins on the hill road, which is the way out of Wend.
        self.carol = self.world.people["p_carol"]

    def tearDown(self):
        self.tmp.cleanup()

    def calls(self, name):
        return [c for c in self.stub.calls if c.name == name]

    def to_phase(self, name):
        order = ["morning", "afternoon", "evening", "night"]
        self.world.phase = (order.index(name) - 1) % 4

    def present(self):
        return sorted(p.id for p in self.world.people.values() if p.present)

    def send_carol_away(self):
        """Put Carol on the road and let her take it."""
        self.carol.place = "hill"
        self.stub.answers["act|p_carol"] = GOING
        report = tick_mod.tick(self.world, config())
        self.stub.answers["act|p_carol"] = STAY
        return report


class TestWhetherAnyoneCanGoAtAll(Road):
    def test_only_from_where_the_road_goes_out(self):
        self.assertEqual(agents.leaving_place(self.world).id, "hill")
        self.assertTrue(agents.may_leave(self.world, self.carol))
        self.carol.place = "market"
        self.assertFalse(agents.may_leave(self.world, self.carol),
                         "the market is not a way out of anywhere")

    def test_not_at_night(self):
        self.world.phase = 3
        self.assertEqual(self.world.phase_name, "night")
        self.assertFalse(agents.may_leave(self.world, self.carol))

    def test_not_if_it_would_stop_being_a_town(self):
        for pid in ("p_alice", "p_bram"):
            self.world.people[pid].present = False
        self.assertEqual(len(self.present()), 2)
        self.assertFalse(agents.may_leave(self.world, self.carol),
                         "two people are not a town anybody can leave")

    def test_not_twice_in_the_same_season(self):
        self.send_carol_away()
        alice = self.world.people["p_alice"]
        alice.place = "hill"
        self.assertFalse(agents.may_leave(self.world, alice))
        self.world.day += agents.DEPARTURE_MIN_GAP_DAYS
        self.assertTrue(agents.may_leave(self.world, alice))

    def test_the_verb_is_not_in_the_vocabulary_anywhere_else(self):
        self.carol.place = "market"
        tick_mod.tick(self.world, config())
        schema = next(c for c in self.calls("act") if c.about == "p_carol").schema
        self.assertNotIn("leave", schema["properties"]["action"]["enum"])

    def test_and_is_where_it_is(self):
        tick_mod.tick(self.world, config())
        schema = next(c for c in self.calls("act") if c.about == "p_carol").schema
        self.assertIn("leave", schema["properties"]["action"]["enum"])
        user = next(c for c in self.calls("act") if c.about == "p_carol").user
        self.assertIn("road also goes out", user)

    def test_a_lenient_backend_still_cannot_walk_someone_out(self):
        self.carol.place = "market"           # no road out of the market
        self.stub.answers["act|p_carol"] = GOING
        report = tick_mod.tick(self.world, config())
        self.assertEqual(report.decisions["p_carol"].action, "stay")
        self.assertIn("p_carol", self.present())


class TestGoing(Road):
    def test_she_is_gone(self):
        report = self.send_carol_away()
        self.assertEqual(len(report.departures), 1)
        self.assertFalse(self.carol.present)
        self.assertEqual(self.carol.left_on, self.world.day)
        self.assertNotIn("p_carol", self.present())
        self.assertNotIn(self.carol, self.world.people_at("hill"))

    def test_the_whole_town_hears_it(self):
        report = self.send_carol_away()
        event = self.world.chronicle.get(report.departures[0].event_id)
        self.assertEqual(event.kind, "departure")
        self.assertEqual(sorted(event.present), sorted(self.world.people))
        david = next(c for c in self.calls("perceive") if c.about == "p_david")
        self.assertIn("word of it reached you", david.user)

    def test_she_gets_one_last_look_at_it(self):
        self.send_carol_away()
        hers = next(c for c in self.calls("perceive") if c.about == "p_carol")
        self.assertIn("looking back", hers.user)

    def test_what_she_had_stays_where_it_is(self):
        self.world.traces("p_carol").add(Trace(
            id="mem9001", owner="p_carol", day=self.world.day,
            trace="the glow over the roofs", salience=0.9, tags=["fire"],
            last_touched=self.world.day))
        self.send_carol_away()
        kept = list(self.world.traces("p_carol"))
        self.assertIn("mem9001", [t.id for t in kept])

    def test_and_so_does_what_everyone_wrote_about_her(self):
        self.send_carol_away()
        alice = self.world.people["p_alice"]
        self.assertEqual(alice.ties["p_carol"].note,
                         "Young. Always about to go somewhere.")

    def test_whoever_went_to_find_her_finds_the_road(self):
        alice = self.world.people["p_alice"]
        alice.place = "hill"
        self.stub.answers["act|p_alice"] = {"because": "", "action": "talk",
                                            "target": "Carol"}
        report = self.send_carol_away()
        self.assertIn(("p_alice", "p_carol"), report.missed)
        self.assertIn("who had gone", alice.last_action)
        self.assertEqual(report.talks, [])

    def test_the_town_stops_asking_her_anything(self):
        self.send_carol_away()
        before = len(self.calls("act"))
        tick_mod.tick(self.world, config())
        asked = [c.about for c in self.calls("act")[before:]]
        self.assertNotIn("p_carol", asked)

    def test_and_stops_offering_her_to_the_director(self):
        self.send_carol_away()
        self.to_phase("morning")
        tick_mod.tick(self.world, config())
        call = self.calls("direct")[-1]
        self.assertNotIn("Carol", call.schema["properties"]["who"]["enum"])
        listed = call.user.split("People:")[1].split("Lately")[0]
        self.assertNotIn("Carol", listed,
                         "nor standing on the hill road among the people it is shown")
        self.assertIn("Carol took the road", call.user,
                      "but the record still says she went - that is why_now material")


class TestComing(Road):
    def morning_after_a_gap(self, days=None):
        self.world.day += agents.ARRIVAL_MIN_GAP_DAYS if days is None else days
        self.to_phase("morning")
        return tick_mod.tick(self.world, config())

    def test_a_whole_town_draws_nobody(self):
        self.to_phase("morning")
        tick_mod.tick(self.world, config())
        self.assertEqual(self.calls("arrive"), [],
                         "nobody is missing; the road is not even asked")

    def test_a_town_short_of_somebody_waits_first(self):
        self.send_carol_away()
        self.to_phase("morning")
        tick_mod.tick(self.world, config())
        self.assertEqual(self.calls("arrive"), [],
                         "the morning after she went is too soon")

    def test_then_it_asks(self):
        self.send_carol_away()
        self.morning_after_a_gap()
        self.assertEqual(len(self.calls("arrive")), 1)

    def test_usually_nobody_comes(self):
        self.send_carol_away()
        report = self.morning_after_a_gap()
        self.assertIsNone(report.arrival)
        self.assertEqual(len(self.present()), 3)

    def test_somebody_comes_up_the_road(self):
        self.send_carol_away()
        self.stub.set("arrive", SOMEBODY)
        report = self.morning_after_a_gap()

        self.assertIsNotNone(report.arrival)
        tam = self.world.person_by_name("Tam")
        self.assertIsNotNone(tam)
        self.assertEqual(tam.id, "p_tam")
        self.assertEqual(tam.place, "hill", "they come in the way she went out")
        self.assertEqual(tam.occupation, "miller")
        self.assertEqual(tam.arrived_on, self.world.day)
        self.assertTrue(tam.present)
        self.assertEqual(tam.home, "", "a newcomer has nowhere of their own")

        event = self.world.chronicle.get(report.arrival.event_id)
        self.assertEqual(event.kind, "arrival")
        self.assertEqual(event.who, ["p_tam"])
        self.assertIn("the coast road", event.what)

    def test_the_newcomer_gets_their_first_day(self):
        self.send_carol_away()
        self.stub.set("arrive", SOMEBODY)
        before = len(self.calls("act"))
        self.morning_after_a_gap()
        asked = [c.about for c in self.calls("act")[before:]]
        self.assertIn("p_tam", asked,
                      "they arrive in the morning and live the day they arrived")

    def test_they_see_the_place_for_the_first_time(self):
        self.send_carol_away()
        self.stub.set("arrive", SOMEBODY)
        before = len(self.calls("perceive"))
        self.morning_after_a_gap()
        theirs = next(c for c in self.calls("perceive")[before:] if c.about == "p_tam")
        self.assertIn("for the first time", theirs.user)

    def test_nobody_here_knows_them(self):
        self.send_carol_away()
        self.stub.set("arrive", SOMEBODY)
        self.morning_after_a_gap()
        tam = self.world.person_by_name("Tam")
        self.assertEqual(tam.ties, {})
        self.assertEqual(self.world.people["p_alice"].ties.get("p_tam"), None)

    def test_the_road_is_told_who_is_missing(self):
        self.send_carol_away()
        self.stub.set("arrive", SOMEBODY)
        self.morning_after_a_gap()
        user = self.calls("arrive")[0].user
        self.assertIn("Who has gone", user)
        self.assertIn("Carol", user)

    def test_asking_counts_even_when_nobody_comes(self):
        self.send_carol_away()
        self.morning_after_a_gap()                   # asked; nobody came
        self.assertEqual(len(self.calls("arrive")), 1)
        self.to_phase("morning")
        tick_mod.tick(self.world, config())
        self.assertEqual(len(self.calls("arrive")), 1,
                         "a town that is owed somebody still does not ask daily")
        self.assertEqual(self.world.road_asked_on, self.world.day - 1)

    def test_a_town_that_is_whole_waits_a_year(self):
        self.send_carol_away()
        self.stub.set("arrive", SOMEBODY)
        self.morning_after_a_gap()
        self.assertEqual(len(self.present()), 4, "back to the size it began at")
        self.assertFalse(agents.may_arrive(self.world))
        self.world.day += agents.ARRIVAL_MIN_GAP_DAYS
        self.assertFalse(agents.may_arrive(self.world), "a month is not enough now")
        self.world.day += agents.ARRIVAL_SETTLED_GAP_DAYS
        self.assertTrue(agents.may_arrive(self.world))

    def test_and_can_then_be_more_than_it_ever_was(self):
        self.stub.set("arrive", {**SOMEBODY, "name": "Edda"})
        self.morning_after_a_gap(agents.ARRIVAL_SETTLED_GAP_DAYS)
        self.assertEqual(len(self.present()), 5,
                         "nobody left, and the town is bigger than it started")

    def test_but_not_more_than_a_town_anybody_knows(self):
        for n in range(agents.TOWN_CEILING - len(self.present())):
            self.world.people[f"p_x{n}"] = type(self.carol)(
                id=f"p_x{n}", name=f"X{n}", place="square")
        self.assertEqual(len(self.present()), agents.TOWN_CEILING)
        self.world.day += agents.ARRIVAL_SETTLED_GAP_DAYS * 2
        self.assertFalse(agents.may_arrive(self.world))

    def test_and_can_shrink_until_it_stops_being_one(self):
        self.send_carol_away()
        alice = self.world.people["p_alice"]
        alice.place = "hill"
        self.world.day += agents.DEPARTURE_MIN_GAP_DAYS
        self.assertTrue(agents.may_leave(self.world, alice))
        alice.present = False
        bram = self.world.people["p_bram"]
        bram.place = "hill"
        self.world.day += agents.DEPARTURE_MIN_GAP_DAYS
        self.assertEqual(len(self.present()), 2)
        self.assertFalse(agents.may_leave(self.world, bram),
                         "the last two cannot both walk out")

    def test_a_name_the_town_already_uses_is_refused(self):
        self.send_carol_away()
        self.stub.set("arrive", {**SOMEBODY, "name": "Alice"})
        report = self.morning_after_a_gap()
        self.assertIsNone(report.arrival)
        self.assertEqual(len(self.present()), 3)

    def test_so_is_coming_back_under_the_same_name(self):
        self.send_carol_away()
        self.stub.set("arrive", {**SOMEBODY, "name": "Carol"})
        report = self.morning_after_a_gap()
        self.assertIsNone(report.arrival, "Carol is gone, and her name went with her")


class TestReading(Road):
    def test_the_report_survives_both(self):
        report = self.send_carol_away()
        cli.print_report(self.world, report)          # must not raise
        self.stub.set("arrive", SOMEBODY)
        self.world.day += agents.ARRIVAL_MIN_GAP_DAYS
        self.to_phase("morning")
        cli.print_report(self.world, tick_mod.tick(self.world, config()))

    def test_somebody_who_left_is_read_as_they_were(self):
        self.world.traces("p_carol").add(Trace(
            id="mem9001", owner="p_carol", day=self.world.day,
            trace="the glow over the roofs", salience=0.5, tags=["fire"],
            last_touched=self.world.day))
        self.send_carol_away()
        left_on = self.carol.left_on
        self.world.day += 4000                 # long enough to lose anything
        from elsewhere import retrieval
        trace = list(self.world.traces("p_carol"))[0]
        self.assertTrue(retrieval.dormant(trace, self.world.day))
        self.assertFalse(retrieval.dormant(trace, left_on),
                         "as of the day she went, she still had it")


if __name__ == "__main__":
    unittest.main()
