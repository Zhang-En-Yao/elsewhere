"""Time in Elsewhere.

A day has four phases.  Time passes whether or not anyone is watching.
"""

from __future__ import annotations

from dataclasses import dataclass

PHASES = ("morning", "afternoon", "evening", "night")
PHASES_PER_DAY = len(PHASES)
DAYS_PER_SEASON = 30
SEASONS = ("spring", "summer", "autumn", "winter")
DAYS_PER_YEAR = DAYS_PER_SEASON * len(SEASONS)


@dataclass
class Clock:
    day: int = 1
    phase: int = 0

    def advance(self) -> None:
        self.phase += 1
        if self.phase >= PHASES_PER_DAY:
            self.phase = 0
            self.day += 1

    @property
    def phase_name(self) -> str:
        return PHASES[self.phase]

    @property
    def is_new_day(self) -> bool:
        return self.phase == 0

    @property
    def season(self) -> str:
        return SEASONS[((self.day - 1) // DAYS_PER_SEASON) % len(SEASONS)]

    @property
    def year(self) -> int:
        return (self.day - 1) // DAYS_PER_YEAR + 1

    @property
    def day_of_year(self) -> int:
        return (self.day - 1) % DAYS_PER_YEAR + 1

    def label(self) -> str:
        return f"Year {self.year}, day {self.day_of_year} ({self.season} {self.phase_name})"

    def to_dict(self) -> dict:
        return {"day": self.day, "phase": self.phase}

    @classmethod
    def from_dict(cls, data: dict) -> "Clock":
        return cls(day=int(data["day"]), phase=int(data["phase"]))
