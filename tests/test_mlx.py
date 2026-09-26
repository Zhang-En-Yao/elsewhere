"""What the MLX backend hands the grammar; needs no model."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere.backends.open_source.mlx import closed
from elsewhere.schemas import CallName, grammar


class ClosedTest(unittest.TestCase):
    def test_objects_take_only_the_fields_they_name(self):
        schema = closed({"type": "object", "properties": {
            "who": {"type": "object", "properties": {"name": {"type": "string"}}},
            "tags": {"type": "array", "items": {
                "type": "object", "properties": {"t": {"type": "string"}}}}}})
        self.assertIs(schema["additionalProperties"], False)
        self.assertIs(schema["properties"]["who"]["additionalProperties"], False)
        self.assertIs(schema["properties"]["tags"]["items"]["additionalProperties"],
                      False)

    def test_a_schema_that_says_otherwise_is_left_alone(self):
        schema = closed({"type": "object", "properties": {},
                         "additionalProperties": {"type": "string"}})
        self.assertEqual(schema["additionalProperties"], {"type": "string"})

    def test_the_original_is_not_touched(self):
        original = grammar(CallName.PERCEIVE)
        closed(original)
        self.assertNotIn("additionalProperties", original)


if __name__ == "__main__":
    unittest.main()
