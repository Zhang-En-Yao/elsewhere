import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere.harness import prompts, schemas
from elsewhere.interface import seed
from elsewhere.harness.schemas import CallName
from elsewhere.adapters.backends import Call, Settings, Transcript, ask, extract_json
from elsewhere.adapters.backends.stub import StubBackend
from elsewhere.adapters import storage
from elsewhere.domain.entities import Being, Identity
from elsewhere.domain.memory import Impression, SelfSchema


def self_schema(*concerns):
    return {
        "idiolect": "",
        "traits": [],
        "concerns": list(concerns),
        "assumptions": [],
        "impressions": [],
    }


def consolidated(*concerns):
    return {"engrams": [], "self_schema": self_schema(*concerns)}


class TestWorldStore(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "world"

    def tearDown(self):
        self.temporary.cleanup()

    def test_a_world_survives_being_written_and_read(self):
        world = seed.build(self.root)
        world.beings["havvah"].identity.self_schema.concerns = ["the water, again"]
        world.beings["havvah"].clock.perceived_through = 3
        world.beings["havvah"].clock.consolidated_through = 2
        storage.save(world)

        back = storage.load(self.root)
        self.assertEqual(back.name, world.name)
        self.assertEqual(back.current, world.current)
        self.assertEqual(len(back.beings), len(world.beings))
        self.assertEqual(
            back.beings["havvah"].identity.biography, world.beings["havvah"].identity.biography
        )
        self.assertEqual(
            back.beings["havvah"].identity.self_schema, world.beings["havvah"].identity.self_schema
        )
        self.assertEqual(back.beings["havvah"].identity.self_schema.concerns, ["the water, again"])
        self.assertEqual(back.beings["havvah"].clock.perceived_through, 3)
        self.assertEqual(back.beings["havvah"].clock.consolidated_through, 2)
        self.assertEqual(len(back.chronicle), len(world.chronicle))

    def test_a_being_round_trips_through_its_three_parts(self):
        world = seed.build(self.root)
        havvah = world.beings["havvah"]
        havvah.identity.self_schema.impressions = [Impression("Bezalel", "good hands")]
        havvah.activity.log("standing at the edge of it")
        havvah.clock.due_at = world.current + 3.0
        storage.save(world)
        back = storage.load(self.root).beings["havvah"]
        self.assertEqual(
            back.identity.self_schema.impressions, [Impression("Bezalel", "good hands")]
        )
        self.assertEqual(back.identity.biography, havvah.identity.biography)
        self.assertEqual(back.activity.doing, "standing at the edge of it")
        self.assertEqual(back.clock.due_at, world.current + 3.0)
        self.assertEqual(
            set(back.to_dict()), {"id", "name", "mind", "identity", "location", "activity", "clock"}
        )

    def test_being_here_is_one_fact_and_not_two(self):
        world = seed.build(self.root)
        lilith = world.beings["lilith"]
        self.assertTrue(lilith.present)
        lilith.clock.left_at = world.current
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
        world.beings["ghost"] = type(world.beings["havvah"])(id="ghost", name="Ghost")
        storage.save(world)
        again = seed.build(self.root)
        storage.save(again)
        self.assertNotIn("ghost", storage.load(self.root).beings)

    def test_the_chronicle_only_ever_grows(self):
        world = seed.build(self.root)
        before = len(world.chronicle)
        world.record("test", "something happened", place="bethel")
        storage.save(world)
        lines = (self.root / "chronicle.jsonl").read_text().strip().splitlines()
        self.assertEqual(len(lines), before + 1)
        self.assertEqual(json.loads(lines[-1])["account"], "something happened")

    def test_two_ticks_cannot_run_at_once(self):
        self.root.mkdir(parents=True)
        with storage.Lock(self.root):
            with self.assertRaises(storage.Locked):
                with storage.Lock(self.root):
                    pass
        with storage.Lock(self.root):  # released, so it can be taken again
            pass


class TestAnswers(unittest.TestCase):
    def test_json_is_found_inside_whatever_came_back(self):
        self.assertEqual(extract_json('{"stuck": true}'), {"stuck": True})
        self.assertEqual(extract_json('```json\n{"stuck": false}\n```'), {"stuck": False})
        self.assertEqual(extract_json('Sure! {"stuck": true} Hope that helps.'), {"stuck": True})
        self.assertEqual(extract_json('{"account": "a } brace"}'), {"account": "a } brace"})
        self.assertIsNone(extract_json("I am a 125M parameter model and I ramble"))

    def test_a_bad_answer_is_complained_about_and_retried(self):
        attempts = []

        def answer(call):
            attempts.append(call.user)
            return (
                {"engrams": [], "self_schema": 5}
                if len(attempts) == 1
                else consolidated("the water")
            )

        backend = StubBackend({CallName.CONSOLIDATE: answer})
        got = ask(
            backend,
            Call(CallName.CONSOLIDATE, "s", "u", schemas.CONSOLIDATE, "havvah"),
            Settings(backend="stub", model="stub"),
            check=lambda data: schemas.validate(CallName.CONSOLIDATE, data),
        )
        self.assertEqual(got, consolidated("the water"))
        self.assertEqual(len(attempts), 2)
        self.assertIn("not usable", attempts[1])

    def test_a_mind_that_never_makes_sense_is_simply_silent(self):
        backend = StubBackend({CallName.CONSOLIDATE: "I am not going to answer that"})
        got = ask(
            backend,
            Call(CallName.CONSOLIDATE, "s", "u", schemas.CONSOLIDATE, "p"),
            Settings(backend="stub", model="stub"),
        )
        self.assertIsNone(got)

    def test_every_exchange_is_written_to_the_tape(self):
        with tempfile.TemporaryDirectory() as temporary:
            tape = Path(temporary) / "t.jsonl"
            backend = StubBackend({CallName.CONSOLIDATE: consolidated("the water")})
            ask(
                backend,
                Call(CallName.CONSOLIDATE, "s", "u", schemas.CONSOLIDATE, "havvah"),
                Settings(backend="stub", model="stub"),
                Transcript(tape),
            )
            rows = [json.loads(line) for line in tape.read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0]["ok"])
            self.assertEqual(rows[0]["mind"], "havvah")

    def test_a_self_schema_is_as_long_as_the_schema_says_and_no_longer(self):
        most = schemas.SELF_SCHEMA_CHARACTERS
        half = most // 2
        clean, complaint = schemas.validate(
            CallName.CONSOLIDATE, consolidated("x" * half, "y" * (most - half))
        )
        self.assertIsNone(complaint)
        clean, complaint = schemas.validate(
            CallName.CONSOLIDATE, consolidated("x" * half, "y" * (most - half + 1))
        )
        self.assertIsNone(clean)
        self.assertIn(f"at most {most}", complaint, "every field counted together")

    def test_what_is_inside_an_answer_is_checked_too(self):
        clean, complaint = schemas.validate(
            CallName.CONSOLIDATE,
            {
                "engrams": [{"gists": [{"proposition": "its eye was open", "weight": "heavy"}]}],
                "self_schema": self_schema(),
            },
        )
        self.assertIsNone(clean)
        self.assertIn("'weight' must be a number", complaint)
        clean, complaint = schemas.validate(
            CallName.CONSOLIDATE,
            {
                "engrams": [
                    {"gists": [{"proposition": "its eye was open", "weight": 1, "why": "x"}]}
                ],
                "self_schema": self_schema(),
                "mood": "x",
            },
        )
        self.assertEqual(
            clean,
            {
                "engrams": [{"gists": [{"proposition": "its eye was open", "weight": 1.0}]}],
                "self_schema": self_schema(),
            },
            "and what nobody asked for is dropped, at every depth",
        )

    def test_every_call_has_a_schema_and_a_grammar(self):
        for name in CallName:
            self.assertIn(name, schemas.SCHEMA_BY_CALL_NAME, f"{name} has no schema")
            grammar = schemas.grammar(name)
            self.assertEqual(grammar["required"], list(grammar["properties"]))

    def test_a_call_name_is_spelled_the_way_it_is_written_down(self):
        self.assertEqual(f"{CallName.ACT}|lilith", "act|lilith")
        self.assertEqual(json.dumps({CallName.ACT: 1}), '{"act": 1}')

    def test_a_misspelled_call_is_refused_when_it_is_made(self):
        with self.assertRaises(ValueError):
            CallName("setle")


class TestIdiolectIsAFactNotASpecification(unittest.TestCase):

    def test_the_seed_says_what_they_do_not_what_the_output_should_look_like(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        world = seed.build(Path(temporary.name) / "world")
        spec = ("sentence", "short", "terse", "brief", "plain and", "words,")
        for being in world.beings.values():
            idiolect = being.identity.self_schema.idiolect
            self.assertTrue(idiolect, f"{being.name} has no idiolect")
            self.assertTrue(
                idiolect.startswith("You "),
                f"{being.name}'s idiolect is not about them: {idiolect!r}",
            )
            for word in spec:
                self.assertNotIn(
                    word,
                    idiolect.lower(),
                    f"{being.name}'s idiolect specifies output: {idiolect!r}",
                )

    def test_it_is_a_line_of_its_own_because_that_is_what_worked(self):
        being = Being(
            id="p",
            name="Havvah",
            identity=Identity(
                biography="You keep the garden alive.",
                self_schema=SelfSchema(idiolect="You say as little as will do."),
            ),
        )
        block = prompts.being_block(being)
        self.assertIn("\nHow you talk: You say as little as will do.", block)


if __name__ == "__main__":
    unittest.main()
