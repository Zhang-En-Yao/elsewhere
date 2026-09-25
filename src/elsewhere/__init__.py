"""Elsewhere - a persistent world that remembers.

v2. The engine keeps the ledger and decides what can be reached; a language
model decides what any of it meant.
"""

__version__ = "2.0"

#: The world keeps one clock: hours since it began, as a float. Days, seasons
#: and the reading on a clock face are all worked out from it when something
#: needs to say them out loud. Nothing stores a day, and nothing stores a
#: named part of the day.
HOURS_PER_DAY = 24.0

SCHEMA_VERSION = 9
