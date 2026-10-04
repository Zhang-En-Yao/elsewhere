"""Events befall the town, and each person sleeps on what they kept of it."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere.adapters import retrieval
from elsewhere.harness import memory, prompts, schemas, tick, world as world_agent
from elsewhere.interface import seed
from elsewhere.harness.schemas import CallName
from elsewhere.adapters.backends import Settings, register
from elsewhere.adapters.backends.stub import StubBackend
from elsewhere.domain.chronicle import Category
from elsewhere.domain.memory import Engram, Episode, Gist, SelfSchema, episodes_of_engram

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
        self.world.current += 24


class TestStir(Town):
    def test_asked_about_once_a_day_whatever_the_hour(self):
        for _ in range(4):  # four steps: a whole day
            tick.tick(self.world, configuration())
        self.assertEqual(
            len(self.calls(CallName.STIR)),
            1,
            "asked on the first step, then not again inside the day",
        )
        tick.tick(self.world, configuration())
        self.assertEqual(len(self.calls(CallName.STIR)), 2, "a day on, it is worth asking again")

    def test_it_can_only_name_what_exists(self):
        tick.tick(self.world, configuration())
        schema = self.calls(CallName.STIR)[0].schema
        self.assertIn("Mizpah", schema["properties"]["where"]["enum"])
        self.assertEqual(schema["properties"]["who"]["enum"], ["", "Bezalel", "Havvah", "Lilith"])

    def test_most_days_nothing_happens(self):
        before = len(self.world.chronicle)
        report = tick.tick(self.world, configuration())
        self.assertIsNone(report.stir.occurrence)
        self.assertEqual(len(self.world.chronicle), before)

    def test_something_happening_to_someone_happens_where_they_are(self):
        self.stub.set(
            CallName.STIR,
            {
                "why_now": "the roof",
                "what": "A beam cracked overhead.",
                "where": "Mizpah",
                "who": "Bezalel",
                "reach": "the people there",
                "action": "occur",
            },
        )
        report = tick.tick(self.world, configuration())
        event = self.world.event(report.stir.occurrence.event_id)
        self.assertEqual(event.place, "yard", "Bezalel is in his own yard, not on the ridge")
        self.assertEqual(event.category, Category.OCCURRENCE)
        self.assertEqual(event.informed, ["bezalel"])
        bezalel = next(call for call in self.calls(CallName.ACT) if call.mind == "bezalel")
        self.assertIn(
            "A beam cracked overhead.",
            bezalel.user,
            "and it is in front of him when he decides what to do",
        )

    def test_something_the_whole_town_notices_reaches_everyone(self):
        self.stub.set(
            CallName.STIR,
            {
                "why_now": "",
                "what": "A storm broke over the town.",
                "where": "Beth El",
                "who": "",
                "reach": "the whole town",
                "action": "occur",
            },
        )
        report = tick.tick(self.world, configuration())
        event = self.world.event(report.stir.occurrence.event_id)
        self.assertEqual(sorted(event.informed), sorted(self.world.beings))
        lilith = next(call for call in self.calls(CallName.ACT) if call.mind == "lilith")
        self.assertIn("A storm broke over the town.", lilith.user)
        self.assertIn("word of it reached you", lilith.user)

    def test_the_town_says_itself_how_long_a_quiet_stretch_it_gets(self):
        self.stub.set(
            CallName.STIR,
            {
                "why_now": "",
                "what": "A goat got loose.",
                "where": "Beth El",
                "who": "",
                "reach": "the people there",
                "action": "occur",
                "duration": 1209600,
            },
        )
        tick.tick(self.world, configuration())
        self.assertEqual(len(self.calls(CallName.STIR)), 1)
        self.assertEqual(self.world.due_at, self.world.current + 336.0)
        for _ in range(8):  # two days further on
            tick.tick(self.world, configuration())
        self.assertEqual(
            len(self.calls(CallName.STIR)),
            1,
            "it said a fortnight, and a fortnight is what it gets",
        )
        for name in ("DIRECTOR_MIN_GAP", "DIRECTOR_EVERY"):
            self.assertFalse(hasattr(world_agent, name))

    def test_the_town_does_not_see_inside_anyone(self):
        tick.tick(self.world, configuration())
        user = self.calls(CallName.STIR)[0].user
        for being in self.world.beings.values():
            self.assertNotIn(being.identity.self_schema.concerns[0], user)


class TestNoting(Town):
    """What reaches somebody is shown to them once, and what they keep of it
    is in their own words."""

    def happen(self, account, to=("lilith",)):
        return self.world.record("occurrence", account, place="mizpah", informed=list(to))

    def look_up(self):
        for being in self.world.beings.values():
            being.clock.due_at = self.world.current
        return tick.tick(self.world, configuration())

    def test_what_they_keep_is_written_in_their_own_words(self):
        event = self.happen("A hawk took one of the ridge hens.")
        self.stub.answers["act|lilith"] = {**STAY, "encoded": "feathers on the path, still moving"}
        self.look_up()
        episodes = self.world.episodes("lilith").all()
        self.assertEqual(
            [episode.account for episode in episodes], ["feathers on the path, still moving"]
        )
        self.assertIn(event.id, episodes[0].event_ids, "and it knows what it was of")

    def test_the_chronicle_is_shown_once_and_never_again(self):
        self.happen("A hawk took one of the ridge hens.")
        self.look_up()
        self.world.current += 1
        self.look_up()
        lilith = [call for call in self.calls(CallName.ACT) if call.mind == "lilith"]
        self.assertIn("A hawk took one of the ridge hens.", lilith[0].user)
        self.assertNotIn(
            "A hawk took one of the ridge hens.",
            lilith[1].user,
            "what she did not note, she no longer has",
        )

    def test_most_of_it_sticks_to_nobody(self):
        self.happen("A hawk took one of the ridge hens.")
        self.look_up()  # the stub encodes nothing
        self.assertEqual(self.world.episodes("lilith").all(), [])

    def test_their_day_is_in_front_of_them_all_day(self):
        self.happen("A hawk took one of the ridge hens.")
        self.stub.answers["act|lilith"] = {**STAY, "encoded": "feathers on the path"}
        self.look_up()
        self.world.current += 1
        self.stub.answers["act|lilith"] = STAY
        self.look_up()
        later = [call for call in self.calls(CallName.ACT) if call.mind == "lilith"][-1]
        self.assertIn("feathers on the path", later.user)

    def test_what_did_not_reach_them_is_not_theirs(self):
        self.happen("Havvah found the gate open.", to=("havvah",))
        self.look_up()
        lilith = next(call for call in self.calls(CallName.ACT) if call.mind == "lilith")
        self.assertNotIn("Havvah found the gate open.", lilith.user)

    def test_only_so_much_is_ever_in_front_of_anyone_at_once(self):
        for index in range(memory.SENSORY_SPAN + 3):
            self.happen(f"the {index}th thing")
        seen = memory.percepts(self.world, self.world.beings["lilith"])
        self.assertEqual(len(seen), memory.SENSORY_SPAN)
        self.assertEqual(
            seen[-1][0].account,
            f"the {memory.SENSORY_SPAN + 2}th thing",
            "the newest, and what is older than that is gone",
        )


def written(*concerns, engrams=()):
    """A consolidate answer: these engrams, and a self-schema of these concerns."""
    return {
        "engrams": [
            {
                "gists": [
                    {"proposition": proposition, "weight": weight} for proposition, weight in gists
                ]
            }
            for gists in engrams
        ],
        "self_schema": {
            "idiolect": "You are quick.",
            "traits": [],
            "concerns": list(concerns),
            "assumptions": [],
            "impressions": [],
        },
    }


#: What a sleep that made nothing of the day answers.
NOTHING = {
    "engrams": [],
    "self_schema": {
        "idiolect": "",
        "traits": [],
        "concerns": [],
        "assumptions": [],
        "impressions": [],
    },
}


class TestConsolidate(Town):
    CONCERN = "The water is in everything I own now."

    def encode(self, account, who="lilith", at=None):
        return self.world.episodes(who).append(
            Episode(at=self.world.current if at is None else at, account=account)
        )

    def settling(self, who="lilith"):
        self.stub.answers[f"act|{who}"] = {**STAY, "sleep": True}
        return tick.tick(self.world, configuration())

    def test_only_whoever_is_stopping_sleeps_on_their_day(self):
        self.settling()
        self.assertEqual([call.mind for call in self.calls(CallName.CONSOLIDATE)], ["lilith"])

    def test_the_self_schema_is_rewritten_whole(self):
        self.stub.set(CallName.CONSOLIDATE, written(self.CONCERN))
        report = self.settling()
        lilith = self.world.beings["lilith"].identity.self_schema
        self.assertEqual(lilith.concerns, [self.CONCERN])
        self.assertEqual(lilith.impressions, [], "all of it, replaced")
        self.assertEqual(lilith.at, self.world.current)
        self.assertEqual(report.consolidated, ["lilith"])
        self.assertNotIn(
            self.CONCERN, self.world.beings["havvah"].identity.self_schema.concerns, "and only hers"
        )

    def test_what_they_are_like_is_rewritten_and_carried_into_the_next_day(self):
        answer = written(self.CONCERN)
        answer["self_schema"]["traits"] = ["I do not leave a thing half-mended."]
        self.stub.set(CallName.CONSOLIDATE, answer)
        self.settling()
        self.assertEqual(
            self.world.beings["lilith"].identity.self_schema.traits,
            ["I do not leave a thing half-mended."],
        )
        self.assertIn(
            "I do not leave a thing half-mended.",
            prompts.being_block(self.world.beings["lilith"]),
            "and it is in front of them on every call after",
        )

    def test_the_biography_is_never_rewritten(self):
        biography = self.world.beings["lilith"].identity.biography
        self.stub.set(CallName.CONSOLIDATE, written(self.CONCERN))
        self.settling()
        self.assertEqual(self.world.beings["lilith"].identity.biography, biography)

    def test_the_day_is_laid_down_as_gists(self):
        self.encode("feathers on the path, still moving")
        self.stub.set(
            CallName.CONSOLIDATE,
            written(
                self.CONCERN,
                engrams=[
                    [
                        ("feathers on the path", 0.9),
                        ("they were still moving", 0.4),
                        ("it was below the ridge", 1.7),
                    ]
                ],
            ),
        )
        self.settling()
        engrams = self.world.engrams("lilith").all()
        self.assertEqual(len(engrams), 1)
        self.assertEqual(
            engrams[0].gists,
            [
                Gist("feathers on the path", 0.9),
                Gist("they were still moving", 0.4),
                Gist("it was below the ridge", 1.0),
            ],
            "in the order they were laid down, weights held to 0 to 1",
        )
        self.assertEqual(engrams[0].at, self.world.current)
        self.assertTrue(engrams[0].embedding, "placed, so it can be found by meaning later")
        self.assertEqual(
            [
                episode.account
                for episode in episodes_of_engram(self.world.episodes("lilith").all(), engrams[0])
            ],
            ["feathers on the path, still moving"],
            "and traceable to the day it came from",
        )

    def test_an_ordinary_day_lays_down_nothing(self):
        self.encode("the goat again")
        self.stub.set(CallName.CONSOLIDATE, written(self.CONCERN))
        self.settling()
        self.assertEqual(self.world.engrams("lilith").all(), [])
        self.assertEqual(
            memory.short_term(self.world, self.world.beings["lilith"]),
            [],
            "and the day is gone over all the same",
        )

    def test_it_is_not_put_to_them(self):
        self.settling()
        call = self.calls(CallName.CONSOLIDATE)[0]
        self.assertIn("You are not them", call.system)
        self.assertNotIn("What you have kept", call.user, "they are asleep")

    def test_they_sleep_on_their_episodes_and_not_what_happened(self):
        self.world.record(
            "occurrence", "A hawk took one of the ridge hens.", place="mizpah", informed=["lilith"]
        )
        self.encode("feathers on the path")
        self.world.beings["lilith"].clock.perceived_through = len(self.world.chronicle)
        self.stub.set(CallName.CONSOLIDATE, written(self.CONCERN))
        self.settling()
        user = self.calls(CallName.CONSOLIDATE)[0].user
        self.assertIn("feathers on the path", user)
        self.assertNotIn(
            "A hawk took one of the ridge hens.",
            user,
            "the chronicle is not shown twice, not even at night",
        )
        self.assertEqual(
            memory.short_term(self.world, self.world.beings["lilith"]),
            [],
            "and once slept on, the short-term store is empty",
        )

    def test_an_empty_self_schema_changes_nothing_and_loses_nothing(self):
        lilith = self.world.beings["lilith"]
        before = lilith.identity.self_schema
        self.encode("feathers on the path")
        report = self.settling()  # the stub writes an empty one
        self.assertEqual(lilith.identity.self_schema, before)
        self.assertEqual(report.consolidated, [])
        self.assertEqual(self.world.engrams("lilith").all(), [])
        self.assertTrue(
            memory.short_term(self.world, lilith), "the day waits to be slept on next time"
        )

    def test_what_they_did_is_something_to_sleep_on(self):
        self.world.beings["lilith"].activity.log("walking the ridge path again")
        self.settling()
        user = self.calls(CallName.CONSOLIDATE)[0].user
        self.assertIn("What they have been doing", user)
        self.assertIn("walking the ridge path again", user)

    def test_the_self_schema_has_a_size_and_it_is_told(self):
        self.settling()
        user = self.calls(CallName.CONSOLIDATE)[0].user
        self.assertIn(f"of {schemas.SELF_SCHEMA_CHARACTERS} characters", user)
        self.assertIn(
            self.world.beings["lilith"].identity.self_schema.concerns[0],
            user,
            "and it is shown the self-schema it is rewriting",
        )

    def test_a_self_schema_too_long_is_handed_back_to_be_cut(self):
        attempts = []

        def answer(call):
            attempts.append(call.user)
            return written(
                "x" * (schemas.SELF_SCHEMA_CHARACTERS + 1) if len(attempts) == 1 else self.CONCERN
            )

        self.stub.set(CallName.CONSOLIDATE, answer)
        self.settling()
        self.assertEqual(len(attempts), 2)
        self.assertIn("at most", attempts[1])
        self.assertEqual(self.world.beings["lilith"].identity.self_schema.concerns, [self.CONCERN])

    def test_every_self_schema_they_ever_held_is_kept(self):
        first = self.world.beings["lilith"].identity.self_schema.concerns
        for concern in ("the first night", "", "the second night"):
            self.stub.set(CallName.CONSOLIDATE, written(concern) if concern else NOTHING)
            self.settling()
            self.world.current += 24
        kept = [version.concerns for version in self.world.self_schemas("lilith").all()]
        self.assertEqual(
            kept,
            [first, ["the first night"], ["the second night"]],
            "the one she started with, then one per night that changed it",
        )

    def test_an_old_engram_comes_back_in_pieces_when_the_day_points_at_it(self):
        self.encode("the road past Mizpah goes further than anyone says", at=10.0)
        self.stub.set(
            CallName.CONSOLIDATE,
            written(
                self.CONCERN,
                engrams=[
                    [("road", 0.9), ("Mizpah", 0.8), ("further", 0.3), ("anyone", 0.1)],
                    [("goat", 0.9), ("lame", 0.8)],
                ],
            ),
        )
        self.settling()  # laid down tonight
        self.world.current += 24 * 15  # a fortnight and a day: a quarter left
        self.encode("a stranger asked where the road past Mizpah goes")
        self.stub.set(CallName.CONSOLIDATE, written(self.CONCERN))
        self.settling()
        user = self.calls(CallName.CONSOLIDATE)[-1].user
        self.assertIn("weeks ago", user, "roughly when, never to the hour")
        self.assertIn("  road\n", user, "only the heaviest of its words")
        self.assertNotIn("further", user)
        self.assertNotIn("goat", user, "one thing comes back, not all")
        self.assertNotIn(
            "further than anyone says",
            user,
            "never the words she had it in: those were never laid down",
        )

    def test_a_being_is_two_pieces_of_writing(self):
        self.assertEqual(
            set(self.world.beings["lilith"].identity.to_dict()), {"biography", "self_schema"}
        )


def vector_extension_installed():
    from contextlib import closing

    with closing(retrieval.connect()) as connection:
        return retrieval.load_vector_extension(connection)


def engram(*propositions, at=0.0, embedding=(), embedded_by=""):
    return Engram(
        at=at,
        gists=[Gist(proposition, 1.0) for proposition in propositions],
        embedding=list(embedding),
        embedded_by=embedded_by,
    )


class TestSearch(unittest.TestCase):
    ENGRAMS = [
        engram("the first flood came", "it took the garden", at=10.0),
        engram("Bezalel showed me his hands", at=20.0),
        engram("the goat is lame", at=30.0),
    ]

    def test_the_engram_the_cue_points_at_comes_back(self):
        self.assertEqual(
            retrieval.search(self.ENGRAMS, "The goat went lame again"), self.ENGRAMS[2]
        )

    def test_a_word_in_another_form_is_the_same_word(self):
        got = retrieval.search(self.ENGRAMS, "Floods in the lower garden")
        self.assertIs(got, self.ENGRAMS[0])

    def test_there_is_no_threshold_only_the_best_there_is(self):
        """A request answered with the best match, however slight: whether it
        meant anything is the mind's to say, not a number's."""
        self.assertIsNotNone(
            retrieval.search(self.ENGRAMS, "his hands were cold"), "'hands' is a word they share"
        )

    def test_nothing_shared_brings_nothing_back(self):
        self.assertIsNone(retrieval.search(self.ENGRAMS, "rain upon a ridge"))
        self.assertIsNone(retrieval.search([], "the flood"))

    def test_a_cue_is_only_ever_words(self):
        for cue in ('He said "NOT this" AND (that', "* ^ : - OR", ""):
            retrieval.search(self.ENGRAMS, cue)  # must not raise

    def test_two_rankings_are_fused_by_rank(self):
        # An engram first in both beats one first in only one.
        fused = retrieval.fuse([[0, 1], [0, 2]])
        self.assertGreater(fused[0], fused[1])
        self.assertAlmostEqual(fused[0], 2 / (retrieval.FUSION_K + 1))

    @unittest.skipUnless(vector_extension_installed(), "sqlite-vec is not installed")
    def test_meaning_finds_what_no_word_does(self):
        placed = [
            engram("a", embedding=[1.0, 0.0], embedded_by="e"),
            engram("b", embedding=[0.0, 1.0], embedded_by="e"),
        ]
        got = retrieval.search(placed, "", cue_vector=[0.1, 0.9], embedder="e")
        self.assertIs(got, placed[1])

    @unittest.skipUnless(vector_extension_installed(), "sqlite-vec is not installed")
    def test_another_embedder_s_vectors_are_not_compared(self):
        placed = [engram("a", embedding=[0.0, 1.0], embedded_by="old")]
        self.assertIsNone(retrieval.search(placed, "", cue_vector=[0.0, 1.0], embedder="new"))


class TestForgetting(unittest.TestCase):
    """The power law of forgetting (Wixted & Ebbesen 1991), at ACT-R's d = 0.5."""

    ENGRAM = Engram(
        at=0.0,
        gists=[
            Gist("he came up the road", 0.3),
            Gist("he said he was from Mizpah", 0.9),
            Gist("nobody knew him", 0.6),
            Gist("there was dust on him", 0.1),
        ],
    )

    def test_it_follows_a_power_law(self):
        self.assertEqual(retrieval.retention(0), 1.0)
        self.assertAlmostEqual(retrieval.retention(3), 0.5)
        self.assertAlmostEqual(retrieval.retention(99), 0.1)
        self.assertEqual(retrieval.retention(-1), 1.0, "nothing is fresher than new")

    def test_what_is_left_is_what_weighed_most(self):
        self.assertEqual(retrieval.fragment(self.ENGRAM, 0), self.ENGRAM, "all of it, at first")
        self.assertEqual(
            [gist.proposition for gist in retrieval.fragment(self.ENGRAM, 3).gists],
            ["he said he was from Mizpah", "nobody knew him"],
            "half, the heaviest, in the order laid down",
        )
        self.assertEqual(
            [gist.proposition for gist in retrieval.fragment(self.ENGRAM, 99).gists],
            ["he said he was from Mizpah"],
            "and something is always left of it",
        )

    def test_the_engram_itself_is_never_revised(self):
        retrieval.fragment(self.ENGRAM, 99)
        self.assertEqual(len(self.ENGRAM.gists), 4)


if __name__ == "__main__":
    unittest.main()
