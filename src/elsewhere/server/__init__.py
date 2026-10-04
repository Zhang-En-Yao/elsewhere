"""Every action in the world, as a tool on one MCP server.

The harness reaches the world only through these tools, over an in-process
MCP session (`mcp.Client(build(world))`): a mind's answer is turned into one
of these calls. The harness names the method itself; no model is ever shown
this server's tool list or descriptions, or picks from them. A being's turn
calls only that being's tools, and the world's turn only the world's: the
world never acts for a being - it records what happens, and each being who it
reaches decides for themselves what to do about it.
Every tool checks what can be reached before it does anything, so nothing
that arrives here gets further than the engine allows. What is refused comes
back as an MCP tool error.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from ..application import actions
from ..domain.world import World


class Tool(str, Enum):
    # A being's.
    STAY = "stay"
    MOVE = "move"
    TALK = "talk"
    SAY = "say"
    LEAVE = "leave"
    # The world's.
    OCCUR = "occur"
    ADMIT = "admit"
    # Either's: a being's timer, or the world's when no being is named.
    WAIT = "wait"

    def __str__(self) -> str:
        return self.value


def build(world: World) -> MCPServer:
    server = MCPServer(
        "elsewhere",
        instructions=(
            f"The world of {world.name}. Every tool checks what can be reached "
            f"before it acts; beings and places are named by id."
        ),
        log_level="ERROR",
    )

    def refusing(action, *arguments, **keywords):
        try:
            return action(*arguments, **keywords)
        except actions.Refused as refusal:
            raise ToolError(str(refusal)) from None

    @server.tool(
        name=Tool.STAY,
        description=("A being stays where they are, doing what they say they are doing."),
    )
    def stay(being: str, doing: str = "") -> dict:
        refusing(actions.stay, world, being, doing)
        return {"being": being}

    @server.tool(name=Tool.MOVE, description=("A being walks to a place beside where they stand."))
    def move(being: str, to: str) -> dict:
        origin = refusing(actions.move, world, being, to)
        return {"being": being, "from": origin, "to": to}

    @server.tool(
        name=Tool.TALK,
        description=(
            "A being turns to somebody to talk. met is false when that somebody is "
            "no longer there."
        ),
    )
    def talk(being: str, to: str) -> dict:
        met = refusing(actions.talk, world, being, to)
        return {"being": being, "to": to, "met": met}

    @server.tool(
        name=Tool.SAY,
        description=(
            "A being says one thing out loud to somebody where they are; everyone "
            "there hears it."
        ),
    )
    def say(being: str, to: str, utterance: str) -> dict:
        event = refusing(actions.say, world, being, to, utterance)
        return {"event": event.id, "account": event.account}

    @server.tool(
        name=Tool.LEAVE,
        description=(
            "A being takes the road out, from where the road goes out, and is never "
            "asked anything again."
        ),
    )
    def leave(being: str, reason: str = "") -> dict:
        event = refusing(actions.leave, world, being, reason)
        return {"event": event.id, "account": event.account}

    @server.tool(
        name=Tool.WAIT,
        description=(
            "Sets when a being, or the world if no being is named, is next asked: "
            "a duration from now. No duration leaves no timer."
        ),
    )
    def wait(duration: Optional[float] = None, being: Optional[str] = None) -> dict:
        at = refusing(actions.wait, world, duration, being)
        return {"due_at": at}

    @server.tool(
        name=Tool.OCCUR,
        description=(
            "Something happens to the town that nobody in it chose: where (a place "
            "id), who it happens to (a being id, or empty), and whether the people "
            f"there or the whole town notice ({', '.join(map(str, actions.Reach))})."
        ),
    )
    def occur(
        what: str,
        where: str = "",
        who: str = "",
        reach: str = str(actions.Reach.THERE),
        why_now: str = "",
    ) -> dict:
        event = refusing(actions.occur, world, what, where, who, reach, why_now)
        return {"event": event.id, "account": event.account}

    @server.tool(
        name=Tool.ADMIT,
        description=("Somebody comes up the road into the town, carrying nothing of it."),
    )
    def admit(
        name: str, from_where: str = "", biography: str = "", idiolect: str = "", why_now: str = ""
    ) -> dict:
        being, event = refusing(
            actions.admit, world, name, from_where, biography, idiolect, why_now
        )
        return {"being": being.id, "event": event.id, "account": event.account}

    return server
