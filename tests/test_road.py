"""Departures and arrivals: the engine's gates, not the mind's choice."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere import agents, cli, seed, tick
from elsewhere.schemas import CallName
from elsewhere.backends import Settings, register
from elsewhere.backends.stub import StubBackend
from elsewhere.world import chronicle
from elsewhere.world.entities import Where

CALLS = tuple(CallName)[:-1]    # every call but the probe
STAY = {"because": "", "doing": "", "action": "", "target": "",
        "again_in_hours": 6.0, "settling": False}
QUIET = {"why_now": "", "what": "", "where": "Beth El", "who": "",
         "reach": "the people there", "happens": False,
         "again_in_hours": 24.0}
GOING = {"because": "I said I would go before the rains", "action": "leave",
         "target": ""}
NOBODY = {"happens": False, "again_in_hours": 24.0}
SOMEBODY = {"why_now": "nobody has tended the ridge plants since she went",
            "name": "Tam", "from_where": "beyond the ridge",
            "card": "You came for the plants and you keep to them.",
            "manner": "You say a thing once.", "happens": True,
            "again_in_hours": 8760.0}


def configuration():
    return {name: Settings(backend="stub", model="stub") for name in CALLS}


class Road(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.world = seed.build(Path(self.temporary.name) / "world")
        self.stub = StubBackend({CallName.ACT: STAY, CallName.STIR: QUIET,
                                 CallName.ARRIVE: NOBODY})
        register(self.stub)
        self.lilith = self.world.beings["lilith"]

    def tearDown(self):
        self.temporary.cleanup()

    def calls(self, name):
        return [call for call in self.stub.calls if call.name == name]

    def stood(self, pid, event):
        """Where `pid` stood for `event`, as it is put in front of them."""
        return dict((event.id, where) for event, where in agents.unseen(
            self.world, self.world.beings[pid]))[event.id]

    def present(self):
        return sorted(being.id for being in self.world.beings.values() if being.present)

    def send_lilith_away(self):
        self.lilith.where.place = "mizpah"
        self.stub.answers["act|lilith"] = GOING
        report = tick.tick(self.world, configuration())
        self.stub.answers["act|lilith"] = STAY
        return report


class TestWhetherAnyoneCanGoAtAll(Road):
    def test_only_from_where_the_road_goes_out(self):
        self.assertEqual(self.world.places.get(self.world.map.road).id, "mizpah")
        self.assertTrue(agents.may_leave(self.world, self.lilith))
        self.lilith.where.place = "yard"
        self.assertFalse(agents.may_leave(self.world, self.lilith),
                         "the yard is not a way out of anywhere")

    def test_the_hour_is_not_the_engine_s_business(self):
        self.world.at = 3 * 24 + 3.0                 # three in the morning
        self.assertFalse(self.world.daylight)
        self.assertTrue(agents.may_leave(self.world, self.lilith),
                        "whether to go at this hour is hers to answer, in 'because'")

    def test_even_the_last_of_them_may_go(self):
        for pid in ("bezalel", "havvah"):
            self.world.beings[pid].when.left_at = self.world.at
        self.assertEqual(self.present(), ["lilith"])
        self.lilith.where.place = "mizpah"
        self.assertTrue(agents.may_leave(self.world, self.lilith),
                        "there is no number of people below which nobody may go")

    def test_how_often_anybody_goes_is_nobody_business_but_theirs(self):
        self.world.beings["x0"] = type(self.lilith)(id="x0", name="X0", where=Where(place="bethel"))
        self.send_lilith_away()
        havvah = self.world.beings["havvah"]
        havvah.where.place = "mizpah"
        self.assertTrue(agents.may_leave(self.world, havvah))
        self.assertFalse(hasattr(agents, "DEPARTURE_MIN_GAP"))

    def test_the_verb_is_not_in_the_vocabulary_anywhere_else(self):
        self.lilith.where.place = "yard"
        tick.tick(self.world, configuration())
        schema = next(call for call in self.calls(CallName.ACT) if call.about == "lilith").schema
        self.assertNotIn("leave", schema["properties"]["action"]["enum"])

    def test_and_is_where_it_is(self):
        tick.tick(self.world, configuration())
        schema = next(call for call in self.calls(CallName.ACT) if call.about == "lilith").schema
        self.assertIn("leave", schema["properties"]["action"]["enum"])
        user = next(call for call in self.calls(CallName.ACT) if call.about == "lilith").user
        self.assertIn("road also goes out", user)

    def test_a_lenient_backend_still_cannot_walk_someone_out(self):
        self.lilith.where.place = "yard"           # no road out of the yard
        self.stub.answers["act|lilith"] = GOING
        report = tick.tick(self.world, configuration())
        self.assertIsNone(report.decisions["lilith"].action)
        self.assertIn("lilith", self.present())


class TestGoing(Road):
    def test_she_is_gone(self):
        report = self.send_lilith_away()
        self.assertEqual(len(report.departures), 1)
        self.assertFalse(self.lilith.present)
        self.assertEqual(self.lilith.when.left_at, self.world.at)
        self.assertNotIn("lilith", self.present())
        self.assertNotIn(self.lilith, self.world.beings_at("mizpah"))

    def test_the_whole_town_hears_it(self):
        report = self.send_lilith_away()
        event = self.world.chronicle.get(report.departures[0].event_id)
        self.assertEqual(event.category, chronicle.DEPARTURE)
        self.assertEqual(sorted(event.informed), sorted(self.world.beings))
        self.assertIn("word of it reached you", self.stood("havvah", event))

    def test_the_record_has_where_she_stood_as_she_went(self):
        report = self.send_lilith_away()
        event = self.world.chronicle.get(report.departures[0].event_id)
        self.assertIn("looking back", event.data["viewpoints"]["lilith"])

    def test_what_she_had_stays_where_it_is(self):
        page = self.lilith.who.notebook
        self.send_lilith_away()
        self.stub.set(CallName.SETTLE, {"notebook": "somebody else's page"})
        for _ in range(3):
            tick.tick(self.world, configuration())
        self.assertEqual(self.lilith.who.notebook, page)

    def test_and_so_does_what_everyone_wrote_about_her(self):
        self.send_lilith_away()
        self.assertIn("young. Always about to go somewhere.",
                      self.world.beings["havvah"].who.notebook)

    def test_whoever_went_to_find_her_finds_the_road(self):
        bezalel = self.world.beings["bezalel"]
        bezalel.where.place = "mizpah"
        self.stub.answers["act|bezalel"] = {"because": "", "action": "talk",
                                           "target": "Lilith"}
        report = self.send_lilith_away()
        self.assertIn(("bezalel", "lilith"), report.missed)
        self.assertIn("who had gone", bezalel.where.doing)
        self.assertEqual(report.talks, [])

    def test_the_town_stops_asking_her_anything(self):
        self.send_lilith_away()
        before = len(self.calls(CallName.ACT))
        tick.tick(self.world, configuration())
        asked = [call.about for call in self.calls(CallName.ACT)[before:]]
        self.assertNotIn("lilith", asked)

    def test_and_stops_offering_her_to_the_town(self):
        self.send_lilith_away()
        # The town was already asked in the step she left; wait for the next.
        self.world.at += 24
        tick.tick(self.world, configuration())
        call = self.calls(CallName.STIR)[-1]
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
        return tick.tick(self.world, configuration())

    def test_the_road_keeps_its_own_timer(self):
        tick.tick(self.world, configuration())
        self.assertEqual(len(self.calls(CallName.ARRIVE)), 1)
        self.assertEqual(self.world.road_wake_at, self.world.at + 24.0,
                         "the stub said a day; nothing in the engine said anything")
        for name in ("ARRIVAL_MIN_GAP", "ARRIVAL_SETTLED_GAP"):
            self.assertFalse(hasattr(agents, name))

    def test_it_is_not_asked_again_until_it_said_so(self):
        tick.tick(self.world, configuration())
        self.stub.set(CallName.ARRIVE, {"happens": False, "again_in_hours": 8760.0})
        self.world.road_wake_at = self.world.at
        tick.tick(self.world, configuration())
        asked = len(self.calls(CallName.ARRIVE))
        for _ in range(3):
            tick.tick(self.world, configuration())
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
        self.assertEqual(tam.id, "tam")
        self.assertEqual(tam.where.place, "mizpah", "they come in the way she went out")
        self.assertEqual(tam.who.card, "You came for the plants and you keep to them.")
        self.assertEqual(tam.when.arrived_at, self.world.at)
        self.assertTrue(tam.present)
        self.assertEqual(tam.where.home, "", "a newcomer has nowhere of their own")

        event = self.world.chronicle.get(report.arrival.event_id)
        self.assertEqual(event.category, chronicle.ARRIVAL)
        self.assertEqual(event.involved, ["tam"])
        self.assertIn("beyond the ridge", event.account)

    def test_the_newcomer_gets_their_first_day(self):
        self.send_lilith_away()
        self.stub.set(CallName.ARRIVE, SOMEBODY)
        before = len(self.calls(CallName.ACT))
        self.after_a_gap()
        asked = [call.about for call in self.calls(CallName.ACT)[before:]]
        self.assertIn("tam", asked,
                      "they live the day they arrived, not the one after")

    def test_they_see_the_place_for_the_first_time(self):
        self.send_lilith_away()
        self.stub.set(CallName.ARRIVE, SOMEBODY)
        before = len(self.calls(CallName.ACT))
        self.after_a_gap()
        theirs = next(call for call in self.calls(CallName.ACT)[before:] if call.about == "tam")
        self.assertIn("for the first time", theirs.user)

    def test_nothing_from_before_they_came_is_theirs(self):
        self.send_lilith_away()
        self.stub.set(CallName.ARRIVE, SOMEBODY)
        before = len(self.calls(CallName.ACT))
        self.after_a_gap()
        tam = self.world.being_by_name("Tam")
        self.assertEqual(tam.who.notebook, "", "they carry nothing of this place yet")
        theirs = next(call for call in self.calls(CallName.ACT)[before:] if call.about == "tam")
        self.assertIn("came up the road", theirs.user,
                      "the first thing that is theirs is coming up the road")
        self.assertNotIn("Lilith took the road", theirs.user)
        self.assertNotIn("Tam", self.world.beings["havvah"].who.notebook)

    def test_the_road_is_told_who_is_missing(self):
        self.send_lilith_away()
        self.stub.set(CallName.ARRIVE, SOMEBODY)
        self.after_a_gap()
        user = self.calls(CallName.ARRIVE)[-1].user
        self.assertIn("Who has gone", user)
        self.assertIn("Lilith", user)

    def test_a_road_that_answers_nothing_usable_is_asked_again(self):
        tick.tick(self.world, configuration())
        self.stub.set(CallName.ARRIVE, {"happens": False})
        self.world.road_wake_at = self.world.at
        tick.tick(self.world, configuration())
        asked = len(self.calls(CallName.ARRIVE))
        tick.tick(self.world, configuration())
        self.assertEqual(len(self.calls(CallName.ARRIVE)), asked + 1)

    def test_and_can_then_be_more_than_it_ever_was(self):
        self.stub.set(CallName.ARRIVE, {**SOMEBODY, "name": "Edda"})
        self.after_a_gap()
        self.assertEqual(len(self.present()), 4,
                         "nobody left, and the town is bigger than it started")

    def test_an_empty_town_is_still_a_town_the_road_is_asked_about(self):
        for being in self.world.beings.values():
            being.when.left_at = self.world.at
        self.assertEqual(self.present(), [])
        self.stub.set(CallName.ARRIVE, SOMEBODY)
        report = self.after_a_gap()
        self.assertIsNotNone(report.arrival)
        self.assertEqual(len(self.present()), 1)

    def test_and_nobody_is_turned_away_for_the_town_being_big(self):
        for index in range(10):
            self.world.beings[f"x{index}"] = type(self.lilith)(
                id=f"x{index}", name=f"X{index}", where=Where(place="bethel"))
        self.assertGreater(len(self.present()), 8)
        self.world.road_wake_at = self.world.at
        self.assertTrue(agents.may_arrive(self.world))
        self.stub.set(CallName.ARRIVE, SOMEBODY)
        before = len(self.present())
        self.after_a_gap()
        self.assertEqual(len(self.present()), before + 1)

    def test_a_name_the_town_already_uses_is_not_refused(self):
        """Two people can share a name; the road doesn't judge meaning,
        only whether someone can be reached - arrival time tells them apart."""
        self.send_lilith_away()
        self.stub.set(CallName.ARRIVE, {**SOMEBODY, "name": "Havvah"})
        report = self.after_a_gap()
        self.assertIsNotNone(report.arrival)
        self.assertEqual(len(self.present()), 3)
        havvahs = [being for being in self.world.beings.values()
                  if being.present and being.name == "Havvah"]
        self.assertEqual(len(havvahs), 2)
        self.assertNotEqual(havvahs[0].when.arrived_at, havvahs[1].when.arrived_at)

    def test_so_is_coming_back_under_the_same_name(self):
        self.send_lilith_away()
        self.stub.set(CallName.ARRIVE, {**SOMEBODY, "name": "Lilith"})
        report = self.after_a_gap()
        self.assertIsNotNone(report.arrival, "the name is free to use again - the person is not the same")
        self.assertEqual(len(self.present()), 3)


class TestReading(Road):
    def test_the_report_survives_both(self):
        report = self.send_lilith_away()
        cli.print_report(self.world, report)          # must not raise
        self.stub.set(CallName.ARRIVE, SOMEBODY)
        self.world.road_wake_at = self.world.at
        cli.print_report(self.world, tick.tick(self.world, configuration()))

    def test_nothing_that_happens_after_reaches_somebody_who_left(self):
        self.send_lilith_away()
        was = agents.unseen(self.world, self.lilith)
        self.stub.set(CallName.STIR, {**QUIET, "what": "A storm broke over the town.",
                                      "reach": "the whole town", "happens": True})
        self.world.at += 24
        tick.tick(self.world, configuration())
        self.assertEqual(agents.unseen(self.world, self.lilith), was)


if __name__ == "__main__":
    unittest.main()
