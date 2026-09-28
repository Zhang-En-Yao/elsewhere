import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere import prompts, schemas, seed
from elsewhere.schemas import CallName
from elsewhere.backends import Call, Settings, Transcript, ask, extract_json
from elsewhere.backends.stub import StubBackend
from elsewhere.world import store
from elsewhere.world.entities import Being, Who


class TestWorldStore(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "world"

    def tearDown(self):
        self.temporary.cleanup()

    def test_a_world_survives_being_written_and_read(self):
        world = seed.build(self.root)
        world.beings["p_havvah"].who.notebook = "the water, again"
        world.beings["p_havvah"].when.seen_through = 3
        world.beings["p_havvah"].when.settled_through = 2
        store.save(world)

        back = store.load(self.root)
        self.assertEqual(back.name, world.name)
        self.assertEqual(back.at, world.at)
        self.assertEqual(len(back.beings), len(world.beings))
        self.assertEqual(back.beings["p_havvah"].who.card,
                         world.beings["p_havvah"].who.card)
        self.assertEqual(back.beings["p_havvah"].who.notebook, "the water, again")
        self.assertEqual(back.beings["p_havvah"].when.seen_through, 3)
        self.assertEqual(back.beings["p_havvah"].when.settled_through, 2)
        self.assertEqual(len(back.chronicle), len(world.chronicle))

    def test_a_being_round_trips_through_its_three_parts(self):
        world = seed.build(self.root)
        havvah = world.beings["p_havvah"]
        havvah.who.notebook = "the water again"
        havvah.where.log("standing at the edge of it")
        havvah.when.wake_at = world.at + 3.0
        store.save(world)
        back = store.load(self.root).beings["p_havvah"]
        self.assertEqual(back.who.notebook, "the water again")
        self.assertEqual(back.who.card, havvah.who.card)
        self.assertEqual(back.where.doing, "standing at the edge of it")
        self.assertEqual(back.when.wake_at, world.at + 3.0)
        self.assertEqual(set(back.to_dict()),
                         {"id", "name", "mind", "who", "where", "when"})

    def test_being_here_is_one_fact_and_not_two(self):
        world = seed.build(self.root)
        lilith = world.beings["p_lilith"]
        self.assertTrue(lilith.present)
        lilith.when.left_at = world.at
        self.assertFalse(lilith.present, "derived, so it cannot disagree")

    def test_no_way_in_this_town_runs_one_direction_only(self):
        world = seed.build(self.root)
        for place in world.places:
            for other in world.map.beside(place):
                self.assertIn(place, world.map.beside(other))

    def test_a_place_is_prose_and_the_town_owns_the_map(self):
        world = seed.build(self.root)
        garden = world.places["garden"]
        self.assertEqual(set(garden.to_dict()), {"id", "name", "description"})
        self.assertEqual(world.map.road, "mizpah")
        self.assertIn("yard", world.map.beside("garden"))

    def test_starting_over_does_not_leave_the_old_town_on_disk(self):
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
        with store.TickLock(self.root):
            with self.assertRaises(store.Locked):
                with store.TickLock(self.root):
                    pass
        with store.TickLock(self.root):      # released, so it can be taken again
            pass


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
            return ({"notebook": 5} if len(attempts) == 1
                    else {"notebook": "the water"})

        backend = StubBackend({CallName.SETTLE: answer})
        got = ask(backend, Call(CallName.SETTLE, "s", "u", schemas.SETTLE, "p_havvah"),
                  Settings(backend="stub", model="stub"))
        self.assertEqual(got, {"notebook": "the water"})
        self.assertEqual(len(attempts), 2)
        self.assertIn("not usable", attempts[1])

    def test_a_mind_that_never_makes_sense_is_simply_silent(self):
        backend = StubBackend({CallName.SETTLE: "I am not going to answer that"})
        got = ask(backend, Call(CallName.SETTLE, "s", "u", schemas.SETTLE, "p"),
                  Settings(backend="stub", model="stub"))
        self.assertIsNone(got)

    def test_every_exchange_is_written_to_the_tape(self):
        with tempfile.TemporaryDirectory() as temporary:
            tape = Path(temporary) / "t.jsonl"
            backend = StubBackend({CallName.SETTLE: {"notebook": "the water"}})
            ask(backend, Call(CallName.SETTLE, "s", "u", schemas.SETTLE, "p_havvah"),
                Settings(backend="stub", model="stub"), Transcript(tape))
            rows = [json.loads(line) for line in tape.read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0]["ok"])
            self.assertEqual(rows[0]["about"], "p_havvah")

    def test_a_page_is_as_long_as_the_schema_says_and_no_longer(self):
        most = schemas.NOTEBOOK_CHARACTERS
        clean, complaint = schemas.validate(CallName.SETTLE, {"notebook": "x" * most})
        self.assertIsNone(complaint)
        clean, complaint = schemas.validate(CallName.SETTLE, {"notebook": "x" * (most + 1)})
        self.assertIsNone(clean)
        self.assertIn(f"at most {most}", complaint)
        self.assertEqual(schemas.grammar(CallName.SETTLE)["properties"]["notebook"]["maxLength"],
                         most, "the grammar carries the same limit to the decoder")

    def test_every_call_has_a_schema_and_a_grammar(self):
        for name in CallName:
            self.assertIn(name, schemas.SCHEMA_BY_CALL_NAME, f"{name} has no schema")
            grammar = schemas.grammar(name)
            self.assertEqual(grammar["required"], list(grammar["properties"]))

    def test_a_call_name_is_spelled_the_way_it_is_written_down(self):
        self.assertEqual(f"{CallName.ACT}|p_lilith", "act|p_lilith")
        self.assertEqual(json.dumps({CallName.ACT: 1}), '{"act": 1}')
        self.assertIs(Call("act", "s", "u", {}).name, CallName.ACT)

    def test_a_misspelled_call_is_refused_when_it_is_made(self):
        with self.assertRaises(ValueError):
            Call("setle", "s", "u", {})



class TestMannerIsAFactNotASpecification(unittest.TestCase):

    def test_the_seed_says_what_they_do_not_what_the_output_should_look_like(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        world = seed.build(Path(temporary.name) / "world")
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


if __name__ == "__main__":
    unittest.main()
