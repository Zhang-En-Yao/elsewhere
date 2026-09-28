"""Events befall the town, and each person carries one page from day to day."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere import agents, recollection, schemas, seed, tick
from elsewhere.schemas import CallName
from elsewhere.backends import Settings, register
from elsewhere.backends.stub import StubBackend
from elsewhere.world import chronicle
from elsewhere.world.notes import Note

CALLS = tuple(CallName)[:-1]    # every call but the probe
STAY = {"because": "", "doing": "", "action": "", "target": "",
        "again_in_hours": 6.0, "settling": False}
QUIET = {"why_now": "", "what": "", "where": "Beth El", "who": "",
         "reach": "the people there", "happens": False,
         "again_in_hours": 24.0}


def configuration():
    return {name: Settings(backend="stub", model="stub") for name in (*CALLS, "embed")}


class Town(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.world = seed.build(Path(self.temporary.name) / "world")
        self.stub = StubBackend({CallName.ACT: STAY, CallName.STIR: QUIET})
        register(self.stub)

    def tearDown(self):
        self.temporary.cleanup()

    def calls(self, name):
        return [call for call in self.stub.calls if call.name == name]

    def a_day_on(self):
        self.world.at += 24


class TestStir(Town):
    def test_asked_about_once_a_day_whatever_the_hour(self):
        for _ in range(4):                       # four steps: a whole day
            tick.tick(self.world, configuration())
        self.assertEqual(len(self.calls(CallName.STIR)), 1,
                         "asked on the first step, then not again inside the day")
        tick.tick(self.world, configuration())
        self.assertEqual(len(self.calls(CallName.STIR)), 2,
                         "a day on, it is worth asking again")

    def test_it_can_only_name_what_exists(self):
        tick.tick(self.world, configuration())
        schema = self.calls(CallName.STIR)[0].schema
        self.assertIn("Mizpah", schema["properties"]["where"]["enum"])
        self.assertEqual(schema["properties"]["who"]["enum"],
                         ["", "Bezalel", "Havvah", "Lilith"])

    def test_most_days_nothing_happens(self):
        before = len(self.world.chronicle)
        report = tick.tick(self.world, configuration())
        self.assertIsNone(report.occurrence)
        self.assertEqual(len(self.world.chronicle), before)

    def test_something_happening_to_someone_happens_where_they_are(self):
        self.stub.set(CallName.STIR, {"why_now": "the roof", "what": "A beam cracked overhead.",
                                      "where": "Mizpah", "who": "Bezalel",
                                      "reach": "the people there", "happens": True})
        report = tick.tick(self.world, configuration())
        event = self.world.chronicle.get(report.occurrence.event_id)
        self.assertEqual(event.place, "yard", "Bezalel is in his own yard, not on the ridge")
        self.assertEqual(event.category, chronicle.OCCURRENCE)
        self.assertEqual(event.informed, ["p_bezalel"])
        bezalel = next(call for call in self.calls(CallName.ACT) if call.about == "p_bezalel")
        self.assertIn("A beam cracked overhead.", bezalel.user,
                      "and it is in front of him when he decides what to do")

    def test_something_the_whole_town_notices_reaches_everyone(self):
        self.stub.set(CallName.STIR, {"why_now": "", "what": "A storm broke over the town.",
                                      "where": "Beth El", "who": "",
                                      "reach": "the whole town", "happens": True})
        report = tick.tick(self.world, configuration())
        event = self.world.chronicle.get(report.occurrence.event_id)
        self.assertEqual(sorted(event.informed), sorted(self.world.beings))
        lilith = next(call for call in self.calls(CallName.ACT) if call.about == "p_lilith")
        self.assertIn("A storm broke over the town.", lilith.user)
        self.assertIn("word of it reached you", lilith.user)

    def test_the_town_says_itself_how_long_a_quiet_stretch_it_gets(self):
        self.stub.set(CallName.STIR, {"why_now": "", "what": "A goat got loose.",
                                      "where": "Beth El", "who": "",
                                      "reach": "the people there", "happens": True,
                                      "again_in_hours": 336.0})
        tick.tick(self.world, configuration())
        self.assertEqual(len(self.calls(CallName.STIR)), 1)
        self.assertEqual(self.world.town_wake_at, self.world.at + 336.0)
        for _ in range(8):                       # two days further on
            tick.tick(self.world, configuration())
        self.assertEqual(len(self.calls(CallName.STIR)), 1,
                         "it said a fortnight, and a fortnight is what it gets")
        for name in ("DIRECTOR_MIN_GAP", "DIRECTOR_EVERY"):
            self.assertFalse(hasattr(agents, name))

    def test_the_town_does_not_see_inside_anyone(self):
        tick.tick(self.world, configuration())
        user = self.calls(CallName.STIR)[0].user
        for being in self.world.beings.values():
            self.assertNotIn(being.who.notebook.splitlines()[0], user)


class TestNoting(Town):
    """What reaches somebody is shown to them once, and what they keep of it
    is in their own words."""

    def happen(self, account, to=("p_lilith",)):
        return self.world.record("occurrence", account, place="mizpah",
                                 informed=list(to))

    def look_up(self):
        for being in self.world.beings.values():
            being.when.wake_at = self.world.at
        return tick.tick(self.world, configuration())

    def test_what_they_keep_is_written_in_their_own_words(self):
        event = self.happen("A hawk took one of the ridge hens.")
        self.stub.answers["act|p_lilith"] = {**STAY, "noted": "feathers on the path, still moving"}
        self.look_up()
        notes = self.world.notes("p_lilith").all()
        self.assertEqual([note.account for note in notes], ["feathers on the path, still moving"])
        self.assertIn(event.id, notes[0].event_ids, "and it knows what it was a note of")
        self.assertTrue(notes[0].embedding, "placed, so it can be found by meaning later")

    def test_the_chronicle_is_shown_once_and_never_again(self):
        self.happen("A hawk took one of the ridge hens.")
        self.look_up()
        self.world.at += 1
        self.look_up()
        lilith = [call for call in self.calls(CallName.ACT) if call.about == "p_lilith"]
        self.assertIn("A hawk took one of the ridge hens.", lilith[0].user)
        self.assertNotIn("A hawk took one of the ridge hens.", lilith[1].user,
                         "what she did not note, she no longer has")

    def test_most_of_it_sticks_to_nobody(self):
        self.happen("A hawk took one of the ridge hens.")
        self.look_up()                        # the stub notes nothing
        self.assertEqual(self.world.notes("p_lilith").all(), [])

    def test_their_day_is_in_front_of_them_all_day(self):
        self.happen("A hawk took one of the ridge hens.")
        self.stub.answers["act|p_lilith"] = {**STAY, "noted": "feathers on the path"}
        self.look_up()
        self.world.at += 1
        self.stub.answers["act|p_lilith"] = STAY
        self.look_up()
        later = [call for call in self.calls(CallName.ACT) if call.about == "p_lilith"][-1]
        self.assertIn("feathers on the path", later.user)

    def test_what_did_not_reach_them_is_not_theirs(self):
        self.happen("Havvah found the gate open.", to=("p_havvah",))
        self.look_up()
        lilith = next(call for call in self.calls(CallName.ACT) if call.about == "p_lilith")
        self.assertNotIn("Havvah found the gate open.", lilith.user)

    def test_only_so_much_is_ever_in_front_of_anyone_at_once(self):
        for index in range(agents.NEW_EVENTS + 3):
            self.happen(f"the {index}th thing")
        seen = agents.unseen(self.world, self.world.beings["p_lilith"])
        self.assertEqual(len(seen), agents.NEW_EVENTS)
        self.assertEqual(seen[-1][0].account, f"the {agents.NEW_EVENTS + 2}th thing",
                         "the newest, and what is older than that is gone")


class TestSettle(Town):
    PAGE = "The water is in everything I own now. Havvah will not look at me."

    def note(self, account, who="p_lilith", at=None):
        return self.world.notes(who).append(Note(at=self.world.at if at is None else at,
                                                 account=account))

    def settling(self, who="p_lilith"):
        self.stub.answers[f"act|{who}"] = {**STAY, "settling": True}
        return tick.tick(self.world, configuration())

    def test_only_whoever_is_stopping_goes_over_their_day(self):
        self.settling()
        self.assertEqual([call.about for call in self.calls(CallName.SETTLE)], ["p_lilith"])

    def test_the_page_is_theirs_to_write(self):
        self.stub.set(CallName.SETTLE, {"notebook": self.PAGE})
        report = self.settling()
        self.assertEqual(self.world.beings["p_lilith"].who.notebook, self.PAGE, "all of it, replaced")
        self.assertEqual(report.settled, ["p_lilith"])
        self.assertNotIn(self.PAGE, self.world.beings["p_havvah"].who.notebook, "and only hers")

    def test_they_go_over_their_notes_and_not_what_happened(self):
        self.world.record("occurrence", "A hawk took one of the ridge hens.",
                          place="mizpah", informed=["p_lilith"])
        self.note("feathers on the path")
        self.world.beings["p_lilith"].when.seen_through = len(self.world.chronicle)
        self.stub.set(CallName.SETTLE, {"notebook": self.PAGE})
        self.settling()
        user = self.calls(CallName.SETTLE)[0].user
        self.assertIn("feathers on the path", user)
        self.assertNotIn("A hawk took one of the ridge hens.", user,
                         "the chronicle is not shown twice, not even at night")
        self.assertEqual(agents.day_notes(self.world, self.world.beings["p_lilith"]), [],
                         "and once gone over, the day is the page")

    def test_a_page_nobody_wrote_changes_nothing_and_loses_nothing(self):
        lilith = self.world.beings["p_lilith"]
        before = lilith.who.notebook
        self.note("feathers on the path")
        report = self.settling()                     # the stub writes an empty page
        self.assertEqual(lilith.who.notebook, before)
        self.assertEqual(report.settled, [])
        self.assertTrue(agents.day_notes(self.world, lilith),
                        "the day waits to be gone over next time")

    def test_what_they_did_is_something_to_go_over(self):
        self.world.beings["p_lilith"].where.log("walking the ridge path again")
        self.settling()
        user = self.calls(CallName.SETTLE)[0].user
        self.assertIn("What you have been doing", user)
        self.assertIn("walking the ridge path again", user)

    def test_the_page_has_a_size_and_they_are_told_it(self):
        self.settling()
        user = self.calls(CallName.SETTLE)[0].user
        self.assertIn(f"of {schemas.NOTEBOOK_CHARACTERS} characters", user)
        self.assertIn(self.world.beings["p_lilith"].who.notebook, user,
                      "and they are shown the page they are rewriting")

    def test_a_page_too_long_is_handed_back_to_be_cut(self):
        attempts = []

        def answer(call):
            attempts.append(call.user)
            return {"notebook": ("x" * (schemas.NOTEBOOK_CHARACTERS + 1)
                                 if len(attempts) == 1 else self.PAGE)}

        self.stub.set(CallName.SETTLE, answer)
        self.settling()
        self.assertEqual(len(attempts), 2)
        self.assertIn("at most", attempts[1])
        self.assertEqual(self.world.beings["p_lilith"].who.notebook, self.PAGE)

    def test_every_page_they_ever_wrote_is_kept(self):
        first = self.world.beings["p_lilith"].who.notebook
        for page in ("the first night", "", "the second night"):
            self.stub.set(CallName.SETTLE, {"notebook": page})
            self.settling()
            self.world.at += 24
        kept = [page.notebook for page in self.world.pages("p_lilith").all()]
        self.assertEqual(kept, [first, "the first night", "the second night"],
                         "the page she started with, then one per night she wrote one")

    def test_an_old_note_can_come_back_when_the_day_points_at_it(self):
        self.note("the road past Mizpah goes further than anyone says", at=10.0)
        self.note("the goat is lame again", at=11.0)
        self.stub.set(CallName.SETTLE, {"notebook": self.PAGE})
        self.settling()                          # those two are now gone over
        self.world.at += 24
        self.note("a stranger asked where the road past Mizpah goes")
        self.settling()
        user = self.calls(CallName.SETTLE)[-1].user
        self.assertIn("the road past Mizpah goes further than anyone says", user,
                      "in the words she had it in then")
        self.assertNotIn("the goat is lame again", user, "one thing comes back, not all")

    def test_a_being_is_three_pieces_of_writing(self):
        self.assertEqual(set(self.world.beings["p_lilith"].who.to_dict()),
                         {"card", "manner", "notebook"})


def vector_extension_installed():
    import sqlite3
    from contextlib import closing
    with closing(sqlite3.connect(":memory:")) as connection:
        return recollection.load_vector_extension(connection)


class TestRecollection(unittest.TestCase):
    NOTES = [Note(at=10.0, account="The flood took the first garden."),
             Note(at=20.0, account="Bezalel has good hands."),
             Note(at=30.0, account="The goat is lame.")]

    def test_the_note_the_cue_points_at_comes_back(self):
        self.assertEqual(recollection.recall(self.NOTES, "The goat went lame again"),
                         self.NOTES[2])

    def test_a_word_in_another_form_is_the_same_word(self):
        got = recollection.recall(self.NOTES, "Floods in the lower garden")
        self.assertEqual(got.account, "The flood took the first garden.")

    def test_there_is_no_threshold_only_the_best_there_is(self):
        """A request answered with the best match, however slight: whether it
        meant anything is the mind's to say, not a number's."""
        self.assertIsNotNone(recollection.recall(self.NOTES, "rain on the ridge"),
                             "'the' is a word they share")

    def test_nothing_shared_brings_nothing_back(self):
        self.assertIsNone(recollection.recall(self.NOTES, "rain upon a ridge"))
        self.assertIsNone(recollection.recall([], "the flood"))

    def test_a_cue_is_only_ever_words(self):
        for cue in ('He said "NOT this" AND (that', "* ^ : - OR", ""):
            recollection.recall(self.NOTES, cue)       # must not raise

    def test_two_rankings_are_fused_by_rank(self):
        # A note first in both beats one first in only one.
        fused = recollection.fuse([[0, 1], [0, 2]])
        self.assertGreater(fused[0], fused[1])
        self.assertAlmostEqual(fused[0], 2 / (recollection.FUSION_K + 1))

    @unittest.skipUnless(vector_extension_installed(), "sqlite-vec is not installed")
    def test_meaning_finds_what_no_word_does(self):
        placed = [Note(at=1.0, account="a", embedding=[1.0, 0.0], embedded_by="e"),
                  Note(at=2.0, account="b", embedding=[0.0, 1.0], embedded_by="e")]
        got = recollection.recall(placed, "", cue_vector=[0.1, 0.9], embedder="e")
        self.assertIs(got, placed[1])

    @unittest.skipUnless(vector_extension_installed(), "sqlite-vec is not installed")
    def test_another_embedder_s_vectors_are_not_compared(self):
        placed = [Note(at=1.0, account="a", embedding=[0.0, 1.0], embedded_by="old")]
        self.assertIsNone(recollection.recall(placed, "", cue_vector=[0.0, 1.0],
                                                    embedder="new"))


if __name__ == "__main__":
    unittest.main()
