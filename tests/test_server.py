"""Every action is a tool on one MCP server, called by the harness by name.
The world throws events; the beings they reach decide what to do about them."""

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import anyio
from mcp import Client

from elsewhere import server
from elsewhere.adapters.backends import Settings, register
from elsewhere.adapters.backends.stub import StubBackend
from elsewhere.domain.chronicle import Category
from elsewhere.harness import tick
from elsewhere.harness.schemas import CallName
from elsewhere.interface import cli, seed
from elsewhere.server import Tool

STAY = {"reason": "", "doing": "", "action": "", "target": "",
        "duration": 21600, "sleep": False}
QUIET = {"action": "", "duration": 86400}


def configuration():
    return {name: Settings(backend="stub", model="stub") for name in CallName}


def calling(world, tool, arguments):
    """One call on the world's server, as the harness makes it."""
    async def run():
        async with Client(server.build(world)) as client:
            return await client.call_tool(str(tool), arguments)
    return anyio.run(run)


class Town(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "world"
        self.world = seed.build(self.root)
        self.stub = StubBackend({CallName.ACT: STAY, CallName.STIR: QUIET})
        register(self.stub)

    def tearDown(self):
        self.temporary.cleanup()

    def asked(self, name):
        return [call.mind for call in self.stub.calls if call.name == name]


class TestTheServer(Town):
    def test_every_action_is_a_tool(self):
        async def run():
            async with Client(server.build(self.world)) as client:
                return await client.list_tools()
        offered = {tool.name for tool in anyio.run(run).tools}
        self.assertEqual(offered, {str(tool) for tool in Tool})

    def test_a_tool_does_what_it_says(self):
        result = calling(self.world, Tool.MOVE, {"being": "havvah", "to": "bethel"})
        self.assertFalse(result.is_error)
        self.assertEqual(self.world.beings["havvah"].location.place, "bethel")

    def test_what_cannot_be_reached_is_refused_and_nothing_changes(self):
        # Havvah is at the garden; no way runs from there to Mizpah.
        result = calling(self.world, Tool.MOVE, {"being": "havvah", "to": "mizpah"})
        self.assertTrue(result.is_error)
        self.assertIn("no way runs", result.content[0].text)
        self.assertEqual(self.world.beings["havvah"].location.place, "garden")

    def test_nobody_walks_out_except_where_the_road_goes(self):
        before = len(self.world.chronicle)
        result = calling(self.world, Tool.LEAVE, {"being": "havvah"})
        self.assertTrue(result.is_error)
        self.assertTrue(self.world.beings["havvah"].present)
        self.assertEqual(len(self.world.chronicle), before)

    def test_the_world_has_its_own_tools(self):
        result = calling(self.world, Tool.OCCUR, {"what": "A storm broke.", "where": "bethel",
                                                  "reach": "the whole town"})
        self.assertFalse(result.is_error)
        event = self.world.chronicle.all()[-1]
        self.assertEqual(event.category, Category.OCCURRENCE)
        self.assertEqual(sorted(event.informed), sorted(self.world.beings))

    def test_waiting_with_nobody_named_is_the_world_waiting(self):
        calling(self.world, Tool.WAIT, {"duration": 48.0})
        self.assertEqual(self.world.due_at, self.world.current + 48.0)


FLOOD = {"why_now": "the river has been rising for days",
         "what": "The water came into the garden.",
         "where": "Gan Eden", "who": "Havvah", "reach": "the people there",
         "name": "", "from_where": "", "biography": "", "idiolect": "",
         "action": "occur", "duration": 604800}


class TestTheWorldThrowsAnEvent(Town):
    def setUp(self):
        super().setUp()
        self.stub.set(CallName.STIR, FLOOD)

    def her_act(self):
        return next(call for call in self.stub.calls
                    if call.name == CallName.ACT and call.mind == "havvah")

    def test_the_world_is_not_offered_anybody_s_tools(self):
        tick.tick(self.world, configuration())
        schema = next(call for call in self.stub.calls if call.name == CallName.STIR).schema
        self.assertEqual(schema["properties"]["action"]["enum"], ["", "occur", "admit"])

    def test_it_reaches_her_before_she_decides(self):
        tick.tick(self.world, configuration())
        self.assertIn("The water came into the garden.", self.her_act().user)

    def test_what_she_does_about_it_is_hers(self):
        self.stub.answers["act|havvah"] = {**STAY, "reason": "the water",
                                          "action": "move", "target": "Beth El"}
        report = tick.tick(self.world, configuration())
        self.assertEqual(report.stir.decision.tool, Tool.OCCUR, "the world only threw an event")
        self.assertEqual(report.decisions["havvah"].arguments,
                         {"being": "havvah", "to": "bethel"},
                         "she chose it, and the harness named the method")
        self.assertEqual(self.world.beings["havvah"].location.place, "bethel")

    def test_and_staying_is_hers_too(self):
        tick.tick(self.world, configuration())       # her answer is to stay
        self.assertEqual(self.world.beings["havvah"].location.place, "garden",
                         "nothing in the world moved her for her")


class TestNoWayInFromOutside(unittest.TestCase):
    """Nothing outside the world decides a turn: there is no command for it."""

    def test_the_command_line_cannot_direct_anybody(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.build_parser().parse_args(["direct", "move", "{}"])


if __name__ == "__main__":
    unittest.main()
