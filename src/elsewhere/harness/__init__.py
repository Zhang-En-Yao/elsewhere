"""The harness: everything between a model and the world.

It decides what each mind is shown and keeps what it keeps (`memory`), puts
the question (`prompts`, `schemas`), and turns the answer into a tool call on
the MCP server (`being`, `world`). `tick` runs one step of all of it.

Two agents, never mixed: a being (`being.py`: act, speak, consolidate) is one
person's mind and sees only what reached them; the world (`world.py`: stir)
is the objective world and sees only what anyone could see. The world throws
events; the beings they reach decide for themselves what to do about them.

The harness names every MCP method itself, from the answer: no model is shown
the server's tools or picks one.
"""
