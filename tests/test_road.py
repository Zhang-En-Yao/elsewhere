"""Departures and arrivals: the engine's gates, not the mind's choice."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere.application import reachability, schedule
from elsewhere.application import actions
from elsewhere.harness import memory, tick, world as world_agent
from elsewhere.server import Tool
from elsewhere.interface import cli, seed
from elsewhere.harness.schemas import CallName
from elsewhere.adapters.backends import Settings, register
from elsewhere.adapters.backends.stub import StubBackend
from elsewhere.domain.chronicle import Category
from elsewhere.domain.entities import Location

CALLS = tuple(CallName)
STAY = {"reason": "", "doing": "", "action": "", "target": "", "duration": 21600, "sleep": False}
QUIET = {
    "why_now": "",
    "what": "",
    "where": "Beth El",
    "who": "",
    "reach": "the people there",
    "action": "",
    "duration": 86400,
}
GOING = {"reason": "I said I would go before the rains", "action": "leave", "target": ""}
SOMEBODY = {
    "why_now": "nobody has tended the ridge plants since she went",
    "name": "Tam",
    "from_where": "beyond the ridge",
    "biography": "You came for the plants and you keep to them.",
    "idiolect": "You say a thing once.",
    "action": "admit",
    "duration": 31536000,
}


def configuration():
    return {name: Settings(backend="stub", model="stub") for name in CALLS}


class Road(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.world = seed.build(Path(self.temporary.name) / "world")
        self.stub = StubBackend({CallName.ACT: STAY, CallName.STIR: QUIET})
        register(self.stub)
        self.lilith = self.world.beings["lilith"]

    def tearDown(self):
        self.temporary.cleanup()

    def calls(self, name):
        return [call for call in self.stub.calls if call.name == name]

    def stood(self, pid, event):
        """Where `pid` stood for `event`, as it is put in front of them."""
        return dict(
            (event.id, where)
            for event, where in memory.percepts(self.world, self.world.beings[pid])
        )[event.id]

    def present(self):
        return sorted(being.id for being in self.world.beings.values() if being.present)

    def send_lilith_away(self):
        self.lilith.location.place = "mizpah"
        self.stub.answers["act|lilith"] = GOING
        report = tick.tick(self.world, configuration())
        self.stub.answers["act|lilith"] = STAY
        return report


class TestWhetherAnyoneCanGoAtAll(Road):
    def test_only_from_where_the_road_goes_out(self):
        self.assertEqual(self.world.places.get(self.world.map.road).id, "mizpah")
        self.assertTrue(reachability.may_leave(self.world, self.lilith))
        self.lilith.location.place = "yard"
        self.assertFalse(
            reachability.may_leave(self.world, self.lilith), "the yard is not a way out of anywhere"
        )

    def test_the_hour_is_not_the_engine_s_business(self):
        self.world.current = 3 * 24 + 3.0  # three in the morning
        self.assertFalse(self.world.daylight)
        self.assertTrue(
            reachability.may_leave(self.world, self.lilith),
            "whether to go at this hour is hers to answer, in 'reason'",
        )

    def test_even_the_last_of_them_may_go(self):
        for pid in ("bezalel", "havvah"):
            self.world.beings[pid].clock.left_at = self.world.current
        self.assertEqual(self.present(), ["lilith"])
        self.lilith.location.place = "mizpah"
        self.assertTrue(
            reachability.may_leave(self.world, self.lilith),
            "there is no number of people below which nobody may go",
        )

    def test_how_often_anybody_goes_is_nobody_business_but_theirs(self):
        self.world.beings["x0"] = type(self.lilith)(
            id="x0", name="X0", location=Location(place="bethel")
        )
        self.send_lilith_away()
        havvah = self.world.beings["havvah"]
        havvah.location.place = "mizpah"
        self.assertTrue(reachability.may_leave(self.world, havvah))
        self.assertFalse(hasattr(actions, "DEPARTURE_MIN_GAP"))

    def test_the_verb_is_not_in_the_vocabulary_anywhere_else(self):
        self.lilith.location.place = "yard"
        tick.tick(self.world, configuration())
        schema = next(call for call in self.calls(CallName.ACT) if call.mind == "lilith").schema
        self.assertNotIn("leave", schema["properties"]["action"]["enum"])

    def test_and_is_where_it_is(self):
        tick.tick(self.world, configuration())
        schema = next(call for call in self.calls(CallName.ACT) if call.mind == "lilith").schema
        self.assertIn("leave", schema["properties"]["action"]["enum"])
        user = next(call for call in self.calls(CallName.ACT) if call.mind == "lilith").user
        self.assertIn("road also goes out", user)

    def test_a_lenient_backend_still_cannot_walk_someone_out(self):
        self.lilith.location.place = "yard"  # no road out of the yard
        self.stub.answers["act|lilith"] = GOING
        report = tick.tick(self.world, configuration())
        self.assertEqual(
            report.decisions["lilith"].tool, Tool.STAY, "what was not offered is not called"
        )
        self.assertIn("lilith", self.present())


class TestGoing(Road):
    def test_she_is_gone(self):
        report = self.send_lilith_away()
        self.assertEqual(len(report.departures), 1)
        self.assertFalse(self.lilith.present)
        self.assertEqual(self.lilith.clock.left_at, self.world.current)
        self.assertNotIn("lilith", self.present())
        self.assertNotIn(self.lilith, self.world.beings_at("mizpah"))

    def test_the_whole_town_hears_it(self):
        report = self.send_lilith_away()
        event = self.world.event(report.departures[0].event_id)
        self.assertEqual(event.category, Category.DEPARTURE)
        self.assertEqual(sorted(event.informed), sorted(self.world.beings))
        self.assertIn("word of it reached you", self.stood("havvah", event))

    def test_the_record_has_where_she_stood_as_she_went(self):
        report = self.send_lilith_away()
        event = self.world.event(report.departures[0].event_id)
        self.assertIn("looking back", event.data["perspectives"]["lilith"])

    def test_what_she_had_stays_where_it_is(self):
        held = self.lilith.identity.self_schema
        self.send_lilith_away()
        self.stub.set(
            CallName.CONSOLIDATE,
            {
                "engrams": [],
                "self_schema": {
                    "idiolect": "",
                    "traits": [],
                    "concerns": ["somebody else's"],
                    "assumptions": [],
                    "impressions": [],
                },
            },
        )
        for _ in range(3):
            tick.tick(self.world, configuration())
        self.assertEqual(self.lilith.identity.self_schema, held)

    def test_and_so_does_what_everyone_wrote_about_her(self):
        self.send_lilith_away()
        self.assertIn(
            "Young. Always about to go somewhere. Six days since.",
            [
                impression.impression
                for impression in self.world.beings["havvah"].identity.self_schema.impressions
            ],
        )

    def test_whoever_went_to_find_her_finds_the_road(self):
        bezalel = self.world.beings["bezalel"]
        bezalel.location.place = "mizpah"
        self.stub.answers["act|bezalel"] = {"reason": "", "action": "talk", "target": "Lilith"}
        report = self.send_lilith_away()
        self.assertIn(("bezalel", "lilith"), report.missed)
        self.assertIn("who had gone", bezalel.activity.doing)
        self.assertEqual(report.talks, [])

    def test_the_town_stops_asking_her_anything(self):
        self.send_lilith_away()
        before = len(self.calls(CallName.ACT))
        tick.tick(self.world, configuration())
        asked = [call.mind for call in self.calls(CallName.ACT)[before:]]
        self.assertNotIn("lilith", asked)

    def test_and_stops_offering_her_to_the_town(self):
        self.send_lilith_away()
        # The town was already asked in the step she left; wait for the next.
        self.world.current += 24
        tick.tick(self.world, configuration())
        call = self.calls(CallName.STIR)[-1]
        self.assertNotIn("Lilith", call.schema["properties"]["who"]["enum"])
        listed = call.user.split("People (")[1].split("Who has gone")[0]
        self.assertNotIn(
            "Lilith", listed, "nor standing on the ridge path among the people it is shown"
        )
        self.assertIn(
            "Lilith took the road",
            call.user,
            "but the record still says she went - that is why_now material",
        )


class TestComing(Road):
    def after_a_gap(self, duration=None):
        if duration is not None:
            self.world.current += duration
        else:
            self.world.due_at = self.world.current
        return tick.tick(self.world, configuration())

    def test_the_world_keeps_its_own_timer(self):
        tick.tick(self.world, configuration())
        self.assertEqual(len(self.calls(CallName.STIR)), 1)
        self.assertEqual(
            self.world.due_at,
            self.world.current + 24.0,
            "the stub said a day; nothing in the engine said anything",
        )
        for name in ("ARRIVAL_MIN_GAP", "ARRIVAL_SETTLED_GAP"):
            self.assertFalse(hasattr(world_agent, name))

    def test_it_is_not_asked_again_until_it_said_so(self):
        tick.tick(self.world, configuration())
        self.stub.set(CallName.STIR, {"action": "", "duration": 31536000})
        self.world.due_at = self.world.current
        tick.tick(self.world, configuration())
        asked = len(self.calls(CallName.STIR))
        for _ in range(3):
            tick.tick(self.world, configuration())
        self.assertEqual(
            len(self.calls(CallName.STIR)), asked, "it said a year, and a year is what it gets"
        )

    def test_usually_nobody_comes(self):
        self.send_lilith_away()
        report = self.after_a_gap()
        self.assertIsNone(report.stir.arrival)
        self.assertEqual(len(self.present()), 2)

    def test_somebody_comes_up_the_road(self):
        self.send_lilith_away()
        self.stub.set(CallName.STIR, SOMEBODY)
        report = self.after_a_gap()

        self.assertIsNotNone(report.stir.arrival)
        tam = self.world.being_by_name("Tam")
        self.assertIsNotNone(tam)
        self.assertEqual(tam.id, "tam")
        self.assertEqual(tam.location.place, "mizpah", "they come in the way she went out")
        self.assertEqual(tam.identity.biography, "You came for the plants and you keep to them.")
        self.assertEqual(tam.clock.arrived_at, self.world.current)
        self.assertTrue(tam.present)
        self.assertEqual(tam.location.home, "", "a newcomer has nowhere of their own")

        event = self.world.event(report.stir.arrival.event_id)
        self.assertEqual(event.category, Category.ARRIVAL)
        self.assertEqual(event.involved, ["tam"])
        self.assertIn("beyond the ridge", event.account)

    def test_the_newcomer_gets_their_first_day(self):
        self.send_lilith_away()
        self.stub.set(CallName.STIR, SOMEBODY)
        before = len(self.calls(CallName.ACT))
        self.after_a_gap()
        asked = [call.mind for call in self.calls(CallName.ACT)[before:]]
        self.assertIn("tam", asked, "they live the day they arrived, not the one after")

    def test_they_see_the_place_for_the_first_time(self):
        self.send_lilith_away()
        self.stub.set(CallName.STIR, SOMEBODY)
        before = len(self.calls(CallName.ACT))
        self.after_a_gap()
        theirs = next(call for call in self.calls(CallName.ACT)[before:] if call.mind == "tam")
        self.assertIn("for the first time", theirs.user)

    def test_nothing_from_before_they_came_is_theirs(self):
        self.send_lilith_away()
        self.stub.set(CallName.STIR, SOMEBODY)
        before = len(self.calls(CallName.ACT))
        self.after_a_gap()
        tam = self.world.being_by_name("Tam")
        self.assertEqual(
            tam.identity.self_schema.concerns
            + tam.identity.self_schema.assumptions
            + tam.identity.self_schema.impressions,
            [],
            "they carry nothing of this place yet",
        )
        self.assertEqual(tam.identity.self_schema.idiolect, "You say a thing once.")
        theirs = next(call for call in self.calls(CallName.ACT)[before:] if call.mind == "tam")
        self.assertIn(
            "came up the road", theirs.user, "the first thing that is theirs is coming up the road"
        )
        self.assertNotIn("Lilith took the road", theirs.user)
        self.assertNotIn(
            "Tam",
            [
                impression.being
                for impression in self.world.beings["havvah"].identity.self_schema.impressions
            ],
        )

    def test_the_road_is_told_who_is_missing(self):
        self.send_lilith_away()
        self.stub.set(CallName.STIR, SOMEBODY)
        self.after_a_gap()
        user = self.calls(CallName.STIR)[-1].user
        self.assertIn("Who has gone", user)
        self.assertIn("Lilith", user)

    def test_a_road_that_answers_nothing_usable_is_asked_again(self):
        tick.tick(self.world, configuration())
        self.stub.set(CallName.STIR, {"action": ""})
        self.world.due_at = self.world.current
        tick.tick(self.world, configuration())
        asked = len(self.calls(CallName.STIR))
        tick.tick(self.world, configuration())
        self.assertEqual(len(self.calls(CallName.STIR)), asked + 1)

    def test_and_can_then_be_more_than_it_ever_was(self):
        self.stub.set(CallName.STIR, {**SOMEBODY, "name": "Edda"})
        self.after_a_gap()
        self.assertEqual(
            len(self.present()), 4, "nobody left, and the town is bigger than it started"
        )

    def test_an_empty_town_is_still_a_town_the_road_is_asked_about(self):
        for being in self.world.beings.values():
            being.clock.left_at = self.world.current
        self.assertEqual(self.present(), [])
        self.stub.set(CallName.STIR, SOMEBODY)
        report = self.after_a_gap()
        self.assertIsNotNone(report.stir.arrival)
        self.assertEqual(len(self.present()), 1)

    def test_and_nobody_is_turned_away_for_the_town_being_big(self):
        for index in range(10):
            self.world.beings[f"x{index}"] = type(self.lilith)(
                id=f"x{index}", name=f"X{index}", location=Location(place="bethel")
            )
        self.assertGreater(len(self.present()), 8)
        self.world.due_at = self.world.current
        self.assertTrue(schedule.world_due(self.world))
        self.stub.set(CallName.STIR, SOMEBODY)
        before = len(self.present())
        self.after_a_gap()
        self.assertEqual(len(self.present()), before + 1)

    def test_a_name_the_town_already_uses_is_not_refused(self):
        """Two people can share a name; the road doesn't judge meaning,
        only whether someone can be reached - arrival time tells them apart."""
        self.send_lilith_away()
        self.stub.set(CallName.STIR, {**SOMEBODY, "name": "Havvah"})
        report = self.after_a_gap()
        self.assertIsNotNone(report.stir.arrival)
        self.assertEqual(len(self.present()), 3)
        havvahs = [
            being
            for being in self.world.beings.values()
            if being.present and being.name == "Havvah"
        ]
        self.assertEqual(len(havvahs), 2)
        self.assertNotEqual(havvahs[0].clock.arrived_at, havvahs[1].clock.arrived_at)

    def test_so_is_coming_back_under_the_same_name(self):
        self.send_lilith_away()
        self.stub.set(CallName.STIR, {**SOMEBODY, "name": "Lilith"})
        report = self.after_a_gap()
        self.assertIsNotNone(
            report.stir.arrival, "the name is free to use again - the person is not the same"
        )
        self.assertEqual(len(self.present()), 3)


class TestReading(Road):
    def test_the_report_survives_both(self):
        report = self.send_lilith_away()
        cli.print_report(self.world, report)  # must not raise
        self.stub.set(CallName.STIR, SOMEBODY)
        self.world.due_at = self.world.current
        cli.print_report(self.world, tick.tick(self.world, configuration()))

    def test_nothing_that_happens_after_reaches_somebody_who_left(self):
        self.send_lilith_away()
        was = memory.percepts(self.world, self.lilith)
        self.stub.set(
            CallName.STIR,
            {
                **QUIET,
                "what": "A storm broke over the town.",
                "reach": "the whole town",
                "action": "occur",
            },
        )
        self.world.current += 24
        tick.tick(self.world, configuration())
        self.assertEqual(memory.percepts(self.world, self.lilith), was)


if __name__ == "__main__":
    unittest.main()
