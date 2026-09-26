import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere import prompts, retrieval, schemas, seed
from elsewhere.backends import Call, Settings, Transcript, ask, extract_json
from elsewhere.backends.stub import StubBackend
from elsewhere.world import store
from elsewhere.world.entities import Being, Where, Who
from elsewhere.world.memories import Memory


def memory(**kw):
    base = dict(id="m1", owner="p", at=100 * 24, account="the water rose over the fields",
                means="I was frightened", feeling="fear",
                told=[100 * 24])
    base.update(kw)
    return Memory(**base)


class TestWorldStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "world"

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_world_survives_being_written_and_read(self):
        world = seed.build(self.root)
        world.memories("p_havvah").add(memory(owner="p_havvah", at=world.at))
        store.save(world)

        back = store.load(self.root)
        self.assertEqual(back.name, world.name)
        self.assertEqual(back.at, world.at)
        self.assertEqual(len(back.beings), len(world.beings))
        self.assertEqual(back.beings["p_havvah"].who.card,
                         world.beings["p_havvah"].who.card)
        self.assertEqual(len(back.memories("p_havvah")), 1)
        self.assertEqual(len(back.chronicle), len(world.chronicle))

    def test_a_being_round_trips_through_its_three_parts(self):
        world = seed.build(self.root)
        havvah = world.beings["p_havvah"]
        havvah.who.thought = "the water again"
        havvah.where.now("standing at the edge of it")
        havvah.when.wake_at = world.at + 3.0
        store.save(world)
        back = store.load(self.root).beings["p_havvah"]
        self.assertEqual(back.who.thought, "the water again")
        self.assertEqual(back.who.card, havvah.who.card)
        self.assertEqual(back.where.doing, "standing at the edge of it")
        self.assertEqual(back.when.wake_at, world.at + 3.0)
        # Each part writes its own half of the file, which is why adding a
        # field to one of them cannot silently drop it on the next save.
        self.assertEqual(set(back.to_dict()),
                         {"id", "name", "mind", "who", "where", "when"})

    def test_being_here_is_one_fact_and_not_two(self):
        world = seed.build(self.root)
        lilith = world.beings["p_lilith"]
        self.assertTrue(lilith.present)
        lilith.when.left_at = world.at
        self.assertFalse(lilith.present, "derived, so it cannot disagree")

    def test_no_way_in_this_town_runs_one_direction_only(self):
        # It is not that somebody checked. It is that a way is one entry, so
        # there is no second copy for it to disagree with. Under the old shape
        # two of the seeded town's paths were one-way and nothing could have
        # said so.
        world = seed.build(self.root)
        for place in world.places:
            for other in world.map.beside(place):
                self.assertIn(place, world.map.beside(other))

    def test_a_place_is_prose_and_the_town_owns_the_map(self):
        world = seed.build(self.root)
        garden = world.places["garden"]
        self.assertEqual(set(garden.to_dict()), {"id", "name", "description"})
        self.assertEqual(world.map.road_out, "mizpah")
        self.assertIn("yard", world.map.beside("garden"))

    def test_starting_over_does_not_leave_the_old_town_on_disk(self):
        # `clear_world` said "people" and `save` said "beings" for long enough that
        # `initialize` over an existing world loaded the old world's people back in
        # beside the new ones.
        world = seed.build(self.root)
        world.beings["p_ghost"] = type(world.beings["p_havvah"])(
            id="p_ghost", name="Ghost")
        store.save(world)
        again = seed.build(self.root)
        store.save(again)
        self.assertNotIn("p_ghost", store.load(self.root).beings)

    def test_the_chronicle_only_ever_grows(self):
        world = seed.build(self.root)
        before = len(world.chronicle)
        world.record("test", "something happened", place="bethel")
        store.save(world)
        lines = (self.root / "chronicle.jsonl").read_text().strip().splitlines()
        self.assertEqual(len(lines), before + 1)
        self.assertEqual(json.loads(lines[-1])["account"], "something happened")

    def test_two_ticks_cannot_run_at_once(self):
        self.root.mkdir(parents=True)
        with store.tick_lock(self.root):
            with self.assertRaises(store.Locked):
                with store.tick_lock(self.root):
                    pass
        with store.tick_lock(self.root):      # released, so it can be taken again
            pass


class TestRetrieval(unittest.TestCase):
    def test_what_is_brought_up_stays_and_what_is_not_falls_behind(self):
        # What a memory is worth is how often anybody has had cause to think
        # of it. Nothing declares that on the day; it is counted afterwards.
        never = memory(id="a")
        told = memory(id="b", told=[100 * 24, 101 * 24, 300 * 24, 600 * 24])
        at = (100 + 900) * 24
        self.assertGreater(retrieval.activation(told, at),
                           retrieval.activation(never, at))
        self.assertEqual(
            retrieval.recallable([never, told], at, limit=1)[0].id, "b")

    def test_when_it_was_told_matters_and_not_only_how_often(self):
        # Three tellings in one week and three a year apart leave a memory in
        # very different places. A tally cannot tell them apart; `told` can.
        week = memory(told=[100 * 24, 101 * 24, 103 * 24, 106 * 24])
        spread = memory(told=[100 * 24, 465 * 24, 830 * 24])
        self.assertEqual(week.recalls, 3)
        self.assertNotEqual(retrieval.activation(week, 1200 * 24),
                            retrieval.activation(spread, 1200 * 24))

    def test_a_memory_gets_further_away_the_longer_nobody_touches_it(self):
        t = memory()
        self.assertGreater(retrieval.activation(t, 110 * 24),
                           retrieval.activation(t, 220 * 24))
        # and it moves continuously: dusk is further off than noon.
        self.assertGreater(retrieval.activation(t, 110 * 24),
                           retrieval.activation(t, 110 * 24 + 6))

    def test_only_a_handful_can_be_brought_to_mind(self):
        memories = [memory(id=f"m{i}", at=100 * 24 - i, told=[100 * 24 - i])
                  for i in range(20)]
        got = retrieval.recallable(memories, 100 * 24, limit=6)
        self.assertEqual(len(got), 6)
        self.assertEqual(got[0].id, "m0")          # freshest first, all else equal
        # The rest are forgotten for the purposes of the next thought, and
        # still on disk for anybody reading.
        self.assertTrue(retrieval.out_of_reach(memories[-1], memories, 100 * 24))

    def test_what_the_moment_is_about_pulls_its_own_subject_forward(self):
        here, elsewhere_ = [1.0, 0.0], [0.0, 1.0]
        plain = memory(id="a", at=99 * 24, told=[99 * 24], embedding=elsewhere_)
        cued = memory(id="b", at=90 * 24, told=[90 * 24], embedding=here)
        self.assertEqual(
            retrieval.recallable([plain, cued], 110 * 24, here, limit=2)[0].id, "b")
        # and with nothing to be about, the fresher memory is simply nearer
        self.assertEqual(
            retrieval.recallable([plain, cued], 110 * 24, limit=2)[0].id, "a")

    def test_a_memory_with_no_vector_is_ranked_not_dropped(self):
        # An embedder that was down when this was written must not cost
        # somebody the memory - it costs them only the pull towards it.
        no_vector = memory(id="a")
        placed = memory(id="b", embedding=[1.0, 0.0])
        got = retrieval.recallable([no_vector, placed], 101 * 24, [1.0, 0.0])
        self.assertEqual({t.id for t in got}, {"a", "b"})

    def test_nearness_survives_a_change_of_embedder(self):
        # Vectors of different width are not comparable, and saying so is
        # better than a number nobody can interpret.
        self.assertEqual(retrieval.nearness([1.0, 0.0], [1.0, 0.0, 0.0]), 0.0)
        self.assertEqual(retrieval.nearness([], [1.0]), 0.0)
        self.assertAlmostEqual(retrieval.nearness([1.0, 0.0], [1.0, 0.0]), 1.0)

    def test_something_out_of_reach_can_still_be_pointed_at(self):
        # No second mechanism for this, and no similarity threshold: the cue
        # enters the one equation as spreading activation, so a moment that
        # points straight at an old memory lifts it over a fresher one that
        # nothing points at.
        old = memory(id="old", at=100 * 24, told=[100 * 24], embedding=[1.0, 0.0])
        recent = [memory(id=f"n{i}", at=(800 + i) * 24, told=[(800 + i) * 24],
                        embedding=[0.0, 1.0]) for i in range(6)]
        at = 1000 * 24
        self.assertTrue(retrieval.out_of_reach(old, [old] + recent, at))
        self.assertFalse(retrieval.out_of_reach(old, [old] + recent, at,
                                                cue=[1.0, 0.0]))

    def test_rewriting_keeps_the_older_wording(self):
        t = memory()
        t.rewrite("something about a flood", at=200 * 24, feeling="fear")
        self.assertEqual(t.account, "something about a flood")
        self.assertEqual(t.history, ["the water rose over the fields"])
        self.assertEqual(t.recalls, 1)
        self.assertEqual(t.told[-1], 200 * 24,
                         "the occasion is the record; there is no second copy of it")


class TestAnswers(unittest.TestCase):
    def test_json_is_found_inside_whatever_came_back(self):
        self.assertEqual(extract_json('{"stuck": true}'), {"stuck": True})
        self.assertEqual(extract_json('```json\n{"stuck": false}\n```'),
                         {"stuck": False})
        self.assertEqual(extract_json('Sure! {"stuck": true} Hope that helps.'),
                         {"stuck": True})
        self.assertEqual(extract_json('{"account": "a } brace"}'),
                         {"account": "a } brace"})
        self.assertIsNone(extract_json("I am a 125M parameter model and I ramble"))

    def test_a_bad_answer_is_complained_about_and_retried(self):
        attempts = []

        def answer(call):
            attempts.append(call.user)
            return ({"stuck": "a great deal"} if len(attempts) == 1
                    else {"stuck": True})

        backend = StubBackend({"perceive": answer})
        got = ask(backend, Call("perceive", "s", "u", schemas.PERCEIVE, "p_havvah"),
                  Settings(backend="stub", model="stub"))
        self.assertEqual(got, {"stuck": True})
        self.assertEqual(len(attempts), 2)
        self.assertIn("not usable", attempts[1])

    def test_a_mind_that_never_makes_sense_is_simply_silent(self):
        backend = StubBackend({"perceive": "I am not going to answer that"})
        got = ask(backend, Call("perceive", "s", "u", schemas.PERCEIVE, "p"),
                  Settings(backend="stub", model="stub"))
        self.assertIsNone(got)

    def test_every_exchange_is_written_to_the_tape(self):
        with tempfile.TemporaryDirectory() as tmp:
            tape = Path(tmp) / "t.jsonl"
            backend = StubBackend({"perceive": {"stuck": True}})
            ask(backend, Call("perceive", "s", "u", schemas.PERCEIVE, "p_havvah"),
                Settings(backend="stub", model="stub"), Transcript(tape))
            rows = [json.loads(l) for l in tape.read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0]["ok"])
            self.assertEqual(rows[0]["about"], "p_havvah")

    def test_a_feeling_is_not_chosen_from_a_list(self):
        # The engine never compares two feelings or sorts by one - it stores
        # them, prints them, and hands them back as text. A vocabulary here
        # would be a constraint on a person for nobody's benefit.
        for name in ("perceive", "recall"):
            self.assertNotIn("enum", schemas.BY_NAME[name]["properties"]["feeling"],
                             f"{name} is telling people what they may feel")
        clean, complaint = schemas.validate(
            "perceive", {"account": "the sound of it", "stuck": True,
                         "feeling": "something close to relief, but not quite"})
        self.assertIsNone(complaint)
        self.assertEqual(clean["feeling"], "something close to relief, but not quite")

    def test_a_memory_carries_nothing_nobody_reads(self):
        # Five fields went when it turned out nothing anywhere read them, and
        # each had a plausible reason to exist right up until somebody looked.
        # This is the list, so that the next one has to be argued for.
        t = memory()
        self.assertEqual(
            set(t.to_dict()) | {"means", "feeling", "embedding", "event_id",
                                "history"},
            {"id", "owner", "at", "account", "means", "feeling", "embedding",
             "event_id", "told", "history"})
        for gone in ("source", "touched_at", "heard", "about", "place",
                     "salience"):
            self.assertFalse(hasattr(t, gone), f"{gone} is back, and unread")

    def test_what_a_memory_used_to_be_is_shown_to_somebody(self):
        # `history` is the only evidence in the world that a memory moved,
        # and it was being kept for nobody until `person` and `event` printed
        # it. A field worth storing is a field something reads.
        t = memory()
        t.rewrite("water, and not being able to look away", at=200 * 24)
        self.assertEqual(t.history, ["the water rose over the fields"])

    def test_a_memory_carries_no_number_for_how_much_it_mattered(self):
        # The five-word ladder and the five floats under it are both gone.
        self.assertNotIn("weight", schemas.PERCEIVE["properties"])
        self.assertFalse(hasattr(schemas, "weight_to_salience"))
        self.assertFalse(hasattr(Memory(id="m", owner="p", at=0.0, account="x"),
                                 "salience"))


if __name__ == "__main__":
    unittest.main()


class TestTheAnswerIsNotInTheQuestion(unittest.TestCase):
    """`perceive` asks for a short fragment in their own voice. So is `thought`."""

    def being(self):
        return Being(id="p_bezalel", name="Bezalel", who=Who(
            card="You build what holds.",
            thought="The roof is not finished and the rains are not waiting",
            wants=["finish the roof"]))

    def test_perceive_is_not_shown_the_one_sentence_shaped_like_its_answer(self):
        being = self.being()
        asked = prompts.perceive_user(
            being=being, what_happened="Beth El came down in the night.",
            where="Beth El", when="02:00 on Chaitra 3 waxing, in spring", at=200 * 24,
            others=[], memories=[], part_of_it=True)
        self.assertNotIn(being.who.thought, asked)
        self.assertIn("You build what holds.", asked)     # who they are stays

    def test_every_other_call_still_is(self):
        being = self.being()
        self.assertIn(being.who.thought, prompts.being_block(being))
        self.assertIn(being.who.thought, prompts.reflect_user(being, [], []))


class TestMannerIsAFactNotASpecification(unittest.TestCase):
    """What survives a change of model is a fact about a person."""

    def test_the_seed_says_what_they_do_not_what_the_output_should_look_like(self):
        # "short sentences" is a note to whoever is rendering them, and would
        # have to be deleted out of every saved being the day the model gets
        # better. "you say as little as will do" is true of somebody.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        world = seed.build(Path(tmp.name) / "world")
        spec = ("sentence", "short", "terse", "brief", "plain and", "words,")
        for being in world.beings.values():
            self.assertTrue(being.who.manner, f"{being.name} has no manner")
            self.assertTrue(being.who.manner.startswith("You "),
                            f"{being.name}'s manner is not about them: {being.who.manner!r}")
            for word in spec:
                self.assertNotIn(word, being.who.manner.lower(),
                                 f"{being.name}'s manner specifies output: {being.who.manner!r}")

    def test_it_is_a_line_of_its_own_because_that_is_what_worked(self):
        being = Being(id="p", name="Havvah",
                      who=Who(card="You keep the garden alive.",
                              manner="You say as little as will do."))
        block = prompts.being_block(being)
        self.assertIn("\nHow you talk: You say as little as will do.", block)


class TestAnOccasionThatHasNotHappened(unittest.TestCase):
    def test_a_later_telling_does_not_reach_back_and_hold_it_up(self):
        # `max(age, an hour)` would have made a telling from day 1000 the
        # freshest thing about this memory when asked on day 10.
        later = memory(told=[100 * 24, 1100 * 24])
        alone = memory(told=[100 * 24])
        self.assertEqual(retrieval.activation(later, 110 * 24),
                         retrieval.activation(alone, 110 * 24))
        # and once it has happened, it counts
        self.assertGreater(retrieval.activation(later, 1200 * 24),
                           retrieval.activation(alone, 1200 * 24))

    def test_nothing_has_happened_yet_at_all(self):
        never = memory(told=[500 * 24])
        self.assertEqual(retrieval.chance(retrieval.activation(never, 100 * 24)), 0.0)
        self.assertEqual(retrieval.recallable([never], 100 * 24), [])
