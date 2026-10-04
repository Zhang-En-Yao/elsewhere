"""The world's clock: time since it began, read as days, dates and seasons.

The Gregorian calendar, with virtual time counted from `EPOCH`; seasons are the
meteorological ones of the northern hemisphere.
"""

from __future__ import annotations

from datetime import date, timedelta

from .. import VIRTUAL_TIME_PER_DAY

EPOCH = date(1994, 9, 9)

#: Plain names, so a model knows what they mean; each lasts three months,
#: winter first (December to February).
SEASONS = ("winter", "spring", "summer", "autumn")
MONTHS_PER_YEAR = 12
MONTHS_PER_SEASON = 3

#: Real time is what a clock, a person and a model count in; virtual time is the
#: world's own, in whatever unit makes a day `VIRTUAL_TIME_PER_DAY` long.
SECONDS_PER_DAY = timedelta(days=1).total_seconds()
SECONDS_PER_HOUR = timedelta(hours=1).total_seconds()
SECONDS_PER_MINUTE = timedelta(minutes=1).total_seconds()

DAWN, DUSK = 6.0, 20.0


def real_of(virtual: float) -> float:
    return virtual * (SECONDS_PER_DAY / VIRTUAL_TIME_PER_DAY)


def virtual_of(real: float) -> float:
    return real * (VIRTUAL_TIME_PER_DAY / SECONDS_PER_DAY)


def day_of(virtual: float) -> int:
    return int(virtual // VIRTUAL_TIME_PER_DAY) + 1


def gregorian_of(virtual: float) -> date:
    return EPOCH + timedelta(days=day_of(virtual) - 1)


def season_of(virtual: float) -> str:
    """E.g. 'autumn'."""
    return SEASONS[gregorian_of(virtual).month % MONTHS_PER_YEAR // MONTHS_PER_SEASON]


def year_of(virtual: float) -> int:
    """E.g. 2025."""
    return gregorian_of(virtual).year


def date_of(virtual: float) -> str:
    """E.g. '4 October'."""
    day = gregorian_of(virtual)
    return f"{day.day} {day:%B}"


def clock_of(virtual: float) -> str:
    """E.g. '03:00'."""
    hours, remainder = divmod(real_of(virtual % VIRTUAL_TIME_PER_DAY), SECONDS_PER_HOUR)
    return f"{int(hours):02d}:{int(remainder // SECONDS_PER_MINUTE):02d}"


def virtual_on(year: int, month: int, day: int, hour: float) -> float:
    return ((date(year, month, day) - EPOCH).days) * VIRTUAL_TIME_PER_DAY + virtual_of(
        hour * SECONDS_PER_HOUR
    )
