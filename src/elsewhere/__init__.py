"""Elsewhere - a persistent world that remembers.

    domain/        what the world is made of; imports nothing outside itself
    application/   the engine: what can be reached, the timers, every action
    server/        every action, as a tool on one MCP server
    harness/       the minds: what each is shown, what it is asked, and its
                   answer turned into a tool call on that server
    adapters/      the world on disk, the backends that reach a model, retrieval
    interface/     the command line, the window, and the seed

Each layer imports only the layers listed above it.
"""

from datetime import timedelta

__version__ = "0.1.0"

#: World time is a float since the start, in whatever unit makes a day this
#: long; days, dates and clock readings are always derived from it.
VIRTUAL_TIME_PER_DAY = 24.0

#: The wall clock is kept pace with a day to a day: one unit of world time is
#: this many real seconds.
REAL_TIME_PER_VIRTUAL_TIME = timedelta(days=1).total_seconds() / VIRTUAL_TIME_PER_DAY

#: 1: the world as the domain, application, server, harness, adapters and
#:    interface layers lay it out.
SCHEMA_VERSION = 1
