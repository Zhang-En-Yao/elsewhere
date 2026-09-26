"""Departures and arrivals: the engine's gates, not the mind's choice."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere import agents, cli, seed, tick as tick_mod
from elsewhere.schemas import CallName
from elsewhere.backends import Settings, register
from elsewhere.backends.stub import StubBackend
from elsewhere.world import chronicle
from elsewhere.world.entities import Where
from elsewhere.world.memories import Memory

CALLS = tuple(CallName)[:-1]    # every call but the probe
STAY = {"because": "", "doing": "", "action": "stay", "target": "",
        "for_hours": 6.0, "settling": False}
QUIET = {"why_now": "", "what": "", "where": "Beth El", "who": "",
         "reach": "the people there", "happens": False,
         "ask_again_in_hours": 24.0}
GOING = {"because": "I said I would go before the rains", "action": "leave",
         "target": ""}
NOBODY = {"comes": False, "ask_again_in_hours": 24.0}
SOMEBODY = {"why_now": "nobody has tended the ridge plants since she went",
            "name": "Tam", "from_where": "beyond the ridge",
            "card": "You came for the plants and you keep to them.",
            "manner": "You say a thing once.", "comes": True,
            "ask_again_in_hours": 8760.0}


def configuration():
    return {name: Settings(backend="stub", model="stub") for name in CALLS}


class Road(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.world = seed.build(Path(self.tmp.name) / "world")
        self.stub = StubBackend({CallName.ACT: STAY, CallName.PERCEIVE: {"stuck": False},
                                 CallName.DIRECT: QUIET, CallName.REFLECT: {}, CallName.ARRIVE: NOBODY})
        register(self.stub)
        self.lilith = self.world.beings["p_lilith"]

    def tearDown(self):
        self.tmp.cleanup()

    def calls(self, name):
        return [c for c in self.stub.calls if c.name == name]


    def present(self):
        return sorted(p.id for p in self.world.beings.values() if p.present)

    def send_lilith_away(self):
        self.lilith.where.place = "mizpah"
        self.stub.answers["act|p_lilith"] = GOING
        report = tick_mod.tick(self.world, configuration())
        self.stub.answers["act|p_lilith"] = STAY
        return report


class TestWhetherAnyoneCanGoAtAll(Road):
    def test_only_from_where_the_road_goes_out(self):
        self.assertEqual(agents.leaving_place(self.world).id, "mizpah")
        self.assertTrue(agents.may_leave(self.world, self.lilith))
        self.lilith.where.place = "yard"
        self.assertFalse(agents.may_leave(self.world, self.lilith),
                         "the yard is not a way out of anywhere")

    def test_the_hour_is_not_the_engine_s_business(self):
        self.world.at = 3 * 24 + 3.0                 # three in the morning
        self.assertFalse(self.world.daylight)
        self.assertTrue(agents.may_leave(self.world, self.lilith),
                        "whether to go at this hour is hers to answer, in 'because'")

    def test_not_if_it_would_stop_being_a_town(self):
        self.world.beings["p_bezalel"].when.left_at = self.world.at
        self.assertEqual(len(self.present()), 2)
        self.assertFalse(agents.may_leave(self.world, self.lilith),
                         "two people are not a town anybody can leave")

    def test_how_often_anybody_goes_is_nobody_business_but_theirs(self):
        self.world.beings["p_x0"] = type(self.lilith)(id="p_x0", name="X0", where=Where(place="bethel"))
        self.send_lilith_away()
        havvah = self.world.beings["p_havvah"]
        havvah.where.place = "mizpah"
        self.assertTrue(agents.may_leave(self.world, havvah))
        self.assertFalse(hasattr(agents, "DEPARTURE_MIN_GAP"))

    def test_the_verb_is_not_in_the_vocabulary_anywhere_else(self):
        self.lilith.where.place = "yard"
        tick_mod.tick(self.world, configuration())
        schema = next(c for c in self.calls(CallName.ACT) if c.about == "p_lilith").schema
        self.assertNotIn("leave", schema["properties"]["action"]["enum"])

    def test_and_is_where_it_is(self):
        tick_mod.tick(self.world, configuration())
        schema = next(c for c in self.calls(CallName.ACT) if c.about == "p_lilith").schema
        self.assertIn("leave", schema["properties"]["action"]["enum"])
        user = next(c for c in self.calls(CallName.ACT) if c.about == "p_lilith").user
        self.assertIn("road also goes out", user)

    def test_a_lenient_backend_still_cannot_walk_someone_out(self):
        self.lilith.where.place = "yard"           # no road out of the yard
        self.stub.answers["act|p_lilith"] = GOING
        report = tick_mod.tick(self.world, configuration())
        self.assertEqual(report.decisions["p_lilith"].action, "stay")
        self.assertIn("p_lilith", self.present())


class TestGoing(Road):
    def test_she_is_gone(self):
        report = self.send_lilith_away()
        self.assertEqual(len(report.departures), 1)
        self.assertFalse(self.lilith.present)
        self.assertEqual(self.lilith.when.left_at, self.world.at)
        self.assertNotIn("p_lilith", self.present())
        self.assertNotIn(self.lilith, self.world.beings_at("mizpah"))

    def test_the_whole_town_hears_it(self):
        report = self.send_lilith_away()
        event = self.world.chronicle.get(report.departures[0].event_id)
        self.assertEqual(event.category, chronicle.DEPARTURE)
        self.assertEqual(sorted(event.reached), sorted(self.world.beings))
        havvah = next(c for c in self.calls(CallName.PERCEIVE) if c.about == "p_havvah")
        self.assertIn("word of it reached you", havvah.user)

    def test_she_gets_one_last_look_at_it(self):
        self.send_lilith_away()
        hers = next(c for c in self.calls(CallName.PERCEIVE) if c.about == "p_lilith")
        self.assertIn("looking back", hers.user)

    def test_what_she_had_stays_where_it_is(self):
        self.world.memories("p_lilith").add(Memory(
            id="mem9001", owner="p_lilith", at=self.world.at,
            account="the valley disappearing under the water", told=[self.world.at]))
        self.send_lilith_away()
        kept = list(self.world.memories("p_lilith"))
        self.assertIn("mem9001", [t.id for t in kept])

    def test_and_so_does_what_everyone_wrote_about_her(self):
        self.send_lilith_away()
        havvah = self.world.beings["p_havvah"]
        self.assertEqual(havvah.who.regards["p_lilith"].account,
                         "Young. Always about to go somewhere.")

    def test_whoever_went_to_find_her_finds_the_road(self):
        bezalel = self.world.beings["p_bezalel"]
        bezalel.where.place = "mizpah"
        self.stub.answers["act|p_bezalel"] = {"because": "", "action": "talk",
                                           "target": "Lilith"}
        report = self.send_lilith_away()
        self.assertIn(("p_bezalel", "p_lilith"), report.missed)
        self.assertIn("who had gone", bezalel.where.doing)
        self.assertEqual(report.talks, [])

    def test_the_town_stops_asking_her_anything(self):
        self.send_lilith_away()
        before = len(self.calls(CallName.ACT))
        tick_mod.tick(self.world, configuration())
        asked = [c.about for c in self.calls(CallName.ACT)[before:]]
        self.assertNotIn("p_lilith", asked)

    def test_and_stops_offering_her_to_the_director(self):
        self.send_lilith_away()
        # The director was already asked in the step she left; wait for the next.
        self.world.at += 24
        tick_mod.tick(self.world, configuration())
        call = self.calls(CallName.DIRECT)[-1]
        self.assertNotIn("Lilith", call.schema["properties"]["who"]["enum"])
        listed = call.user.split("People:")[1].split("Lately")[0]
        self.assertNotIn("Lilith", listed,
                         "nor standing on the ridge path among the people it is shown")
        self.assertIn("Lilith took the road", call.user,
                      "but the record still says she went - that is why_now material")


class TestComing(Road):
    def after_a_gap(self, hours=None):
        if hours is not None:
            self.world.at += hours
        else:
            self.world.road_wake_at = self.world.at
        return tick_mod.tick(self.world, configuration())

    def test_the_road_keeps_its_own_timer(self):
        tick_mod.tick(self.world, configuration())
        self.assertEqual(len(self.calls(CallName.ARRIVE)), 1)
        self.assertEqual(self.world.road_wake_at, self.world.at + 24.0,
                         "the stub said a day; nothing in the engine said anything")
        for name in ("ARRIVAL_MIN_GAP", "ARRIVAL_SETTLED_GAP"):
            self.assertFalse(hasattr(agents, name))

    def test_it_is_not_asked_again_until_it_said_so(self):
        tick_mod.tick(self.world, configuration())
        self.stub.set(CallName.ARRIVE, {"comes": False, "ask_again_in_hours": 8760.0})
        self.world.road_wake_at = self.world.at
        tick_mod.tick(self.world, configuration())
        asked = len(self.calls(CallName.ARRIVE))
        for _ in range(3):
            tick_mod.tick(self.world, configuration())
        self.assertEqual(len(self.calls(CallName.ARRIVE)), asked,
                         "it said a year, and a year is what it gets")

    def test_usually_nobody_comes(self):
        self.send_lilith_away()
        report = self.after_a_gap()
        self.assertIsNone(report.arrival)
        self.assertEqual(len(self.present()), 2)

    def test_somebody_comes_up_the_road(self):
        self.send_lilith_away()
        self.stub.set(CallName.ARRIVE, SOMEBODY)
        report = self.after_a_gap()

        self.assertIsNotNone(report.arrival)
        tam = self.world.being_by_name("Tam")
        self.assertIsNotNone(tam)
        self.assertEqual(tam.id, "p_tam")
        self.assertEqual(tam.where.place, "mizpah", "they come in the way she went out")
        self.assertEqual(tam.who.card, "You came for the plants and you keep to them.")
        self.assertEqual(tam.when.arrived_at, self.world.at)
        self.assertTrue(tam.present)
        self.assertEqual(tam.where.home, "", "a newcomer has nowhere of their own")

        event = self.world.chronicle.get(report.arrival.event_id)
        self.assertEqual(event.category, chronicle.ARRIVAL)
        self.assertEqual(event.involved, ["p_tam"])
        self.assertIn("beyond the ridge", event.account)

    def test_the_newcomer_gets_their_first_day(self):
        self.send_lilith_away()
        self.stub.set(CallName.ARRIVE, SOMEBODY)
        before = len(self.calls(CallName.ACT))
        self.after_a_gap()
        asked = [c.about for c in self.calls(CallName.ACT)[before:]]
        self.assertIn("p_tam", asked,
                      "they live the day they arrived, not the one after")

    def test_they_see_the_place_for_the_first_time(self):
        self.send_lilith_away()
        self.stub.set(CallName.ARRIVE, SOMEBODY)
        before = len(self.calls(CallName.PERCEIVE))
        self.after_a_gap()
        theirs = next(c for c in self.calls(CallName.PERCEIVE)[before:] if c.about == "p_tam")
        self.assertIn("for the first time", theirs.user)

    def test_nobody_here_knows_them(self):
        self.send_lilith_away()
        self.stub.set(CallName.ARRIVE, SOMEBODY)
        self.after_a_gap()
        tam = self.world.being_by_name("Tam")
        self.assertEqual(tam.who.regards, {})
        self.assertEqual(self.world.beings["p_havvah"].who.regards.get("p_tam"), None)

    def test_the_road_is_told_who_is_missing(self):
        self.send_lilith_away()
        self.stub.set(CallName.ARRIVE, SOMEBODY)
        self.after_a_gap()
        user = self.calls(CallName.ARRIVE)[-1].user
        self.assertIn("Who has gone", user)
        self.assertIn("Lilith", user)

    def test_a_road_that_answers_nothing_usable_is_asked_again(self):
        tick_mod.tick(self.world, configuration())
        self.stub.set(CallName.ARRIVE, {"comes": False})
        self.world.road_wake_at = self.world.at
        tick_mod.tick(self.world, configuration())
        asked = len(self.calls(CallName.ARRIVE))
        tick_mod.tick(self.world, configuration())
        self.assertEqual(len(self.calls(CallName.ARRIVE)), asked + 1)

    def test_and_can_then_be_more_than_it_ever_was(self):
        self.stub.set(CallName.ARRIVE, {**SOMEBODY, "name": "Edda"})
        self.after_a_gap()
        self.assertEqual(len(self.present()), 4,
                         "nobody left, and the town is bigger than it started")

    def test_but_not_more_than_a_town_anybody_knows(self):
        for n in range(agents.TOWN_CEILING - len(self.present())):
            self.world.beings[f"p_x{n}"] = type(self.lilith)(
                id=f"p_x{n}", name=f"X{n}", where=Where(place="bethel"))
        self.assertEqual(len(self.present()), agents.TOWN_CEILING)
        self.world.road_wake_at = self.world.at
        self.assertFalse(agents.may_arrive(self.world),
                         "there is nowhere to put anybody, so it is never asked")

    def test_and_can_shrink_until_it_stops_being_one(self):
        # A filler lets one test see both the allowed and the blocked departure.
        filler = type(self.lilith)(id="p_x0", name="X0", where=Where(place="bethel"))
        self.world.beings["p_x0"] = filler
        self.send_lilith_away()                    # 3 present: bezalel, havvah, x0
        filler.where.place = "mizpah"
        self.assertTrue(agents.may_leave(self.world, filler))
        filler.when.left_at = self.world.at
        bezalel = self.world.beings["p_bezalel"]
        bezalel.where.place = "mizpah"
        self.assertEqual(len(self.present()), 2)
        self.assertFalse(agents.may_leave(self.world, bezalel),
                         "the last two cannot both walk out")

    def test_a_name_the_town_already_uses_is_refused(self):
        self.send_lilith_away()
        self.stub.set(CallName.ARRIVE, {**SOMEBODY, "name": "Havvah"})
        report = self.after_a_gap()
        self.assertIsNone(report.arrival)
        self.assertEqual(len(self.present()), 2)

    def test_so_is_coming_back_under_the_same_name(self):
        self.send_lilith_away()
        self.stub.set(CallName.ARRIVE, {**SOMEBODY, "name": "Lilith"})
        report = self.after_a_gap()
        self.assertIsNone(report.arrival, "Lilith is gone, and her name went with her")


class TestReading(Road):
    def test_the_report_survives_both(self):
        report = self.send_lilith_away()
        cli.print_report(self.world, report)          # must not raise
        self.stub.set(CallName.ARRIVE, SOMEBODY)
        self.world.road_wake_at = self.world.at
        cli.print_report(self.world, tick_mod.tick(self.world, configuration()))

    def test_somebody_who_left_is_read_as_they_were(self):
        self.world.memories("p_lilith").add(Memory(
            id="mem9001", owner="p_lilith", at=self.world.at,
            account="the valley disappearing under the water", told=[self.world.at]))
        self.send_lilith_away()
        left_at = self.lilith.when.left_at
        self.world.at += 4000 * 24                 # long enough to lose anything
        from elsewhere import retrieval
        memory = list(self.world.memories("p_lilith"))[0]
        # A departed person's memories are read at `left_at`.
        self.assertGreater(retrieval.chance(retrieval.activation(memory, left_at)),
                           0.5, "as of the day she went, she still had it")
        self.assertLess(retrieval.chance(retrieval.activation(memory, self.world.at)),
                        0.05, "and on today's clock it would be long gone")


if __name__ == "__main__":
    unittest.main()
