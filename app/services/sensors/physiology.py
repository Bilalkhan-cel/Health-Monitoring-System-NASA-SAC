"""PhysiologyModel: generated blood pressure, glucose and respiration (Section 10A.9).

No sensor exists for these attributes, so the prototype generates them with a
deterministic, time-based model. ``sample`` is a pure function: the same seed and
time always give the same values, and there are no ``random()`` calls at read time.
Nothing here may ever be described as measured.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

# Normal mode stays inside the Good/Okay bands of thresholds.yaml.
SYS_RANGE = (98, 129)
DIA_RANGE = (62, 79)
PULSE_PRESSURE = (32, 55)
GLUCOSE_RANGE = (72, 145)
RESP_RANGE = (11, 19)
MEAL_TAU_MIN = 45.0


def stable_seed(*parts: str) -> int:
    """A seed that is the same on every run and every machine."""
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _unit(seed: int, *keys: int) -> float:
    """Deterministic value in [0, 1) for a seed and integer keys."""
    payload = ",".join(str(item) for item in (seed, *keys)).encode("ascii")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") / 2**64


def smooth_noise(seed: int, t: float, period_s: float, channel: int = 0) -> float:
    """Cosine-interpolated value noise in [-1, 1]."""
    position = t / period_s
    index = math.floor(position)
    fraction = position - index
    a = _unit(seed, channel, index) * 2 - 1
    b = _unit(seed, channel, index + 1) * 2 - 1
    blend = (1 - math.cos(math.pi * fraction)) / 2
    return a + (b - a) * blend


def clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def circadian(t_utc: datetime) -> float:
    """Daily rhythm in [-1, 1], peaking at 16:00 on the mission clock."""
    hour = t_utc.hour + t_utc.minute / 60 + t_utc.second / 3600
    return math.cos(2 * math.pi * (hour - 16) / 24)


@dataclass(frozen=True)
class PhysiologyModel:
    """Generated attributes for one astronaut."""

    seed: int
    meal_times: tuple[str, ...] = ("07:30", "12:30", "18:30")

    @property
    def sys_base(self) -> float:
        return 108 + 14 * _unit(self.seed, 101)

    @property
    def fasting_base(self) -> float:
        return 80 + 14 * _unit(self.seed, 102)

    @property
    def meal_amplitude(self) -> float:
        return 25 + 13 * _unit(self.seed, 103)

    def arousal(self, t_utc: datetime, hr_live: float | None = None, hr_expected: float = 72.0) -> float:
        """Shared latent state in [0, 1] that keeps related values consistent."""
        t = t_utc.timestamp()
        hr_excess = clip((hr_live - hr_expected) / 40, -0.5, 0.5) if hr_live is not None else 0.0
        return clip(0.5 + 0.25 * smooth_noise(self.seed, t, 2700, 1) + 0.10 * circadian(t_utc) + 0.5 * hr_excess, 0, 1)

    def _meals_before(self, t_utc: datetime) -> list[datetime]:
        """Meal instants (jittered +/- 15 min per day by the seed) up to ``t_utc``."""
        meals: list[datetime] = []
        for day_offset in (0, -1):
            day = (t_utc + timedelta(days=day_offset)).date()
            for slot, text in enumerate(self.meal_times):
                hour, minute = (int(part) for part in text.split(":"))
                jitter = (_unit(self.seed, 200 + slot, day.toordinal()) * 2 - 1) * 15
                meal = datetime(day.year, day.month, day.day, hour, minute) + timedelta(minutes=jitter)
                if meal <= t_utc:
                    meals.append(meal)
        return meals

    def glucose_context(self, t_utc: datetime) -> str:
        meals = self._meals_before(t_utc)
        if not meals:
            return "fasting"
        minutes = (t_utc - max(meals)).total_seconds() / 60
        if minutes >= 480:
            return "fasting"
        return "post_meal" if 90 <= minutes <= 150 else "random"

    def sample(self, t_utc: datetime, hr_live: float | None = None, hr_expected: float = 72.0) -> dict[str, object]:
        """Generated values at one instant."""
        t = t_utc.timestamp()
        a = self.arousal(t_utc, hr_live, hr_expected)
        noise_8 = smooth_noise(self.seed, t, 480, 2)

        systolic = self.sys_base + 8 * (a - 0.5) + 4 * circadian(t_utc) + 2.5 * noise_8
        systolic = clip(systolic, *SYS_RANGE)
        diastolic = clip(0.6 * systolic + 6 + 1.5 * smooth_noise(self.seed, t, 480, 3), *DIA_RANGE)
        diastolic = clip(diastolic, systolic - PULSE_PRESSURE[1], systolic - PULSE_PRESSURE[0])

        glucose = self.fasting_base + 2 * smooth_noise(self.seed, t, 2700, 4)
        for meal in self._meals_before(t_utc):
            dt = (t_utc - meal).total_seconds() / 60
            glucose += self.meal_amplitude * (dt / MEAL_TAU_MIN) * math.exp(1 - dt / MEAL_TAU_MIN)
        glucose = clip(glucose, *GLUCOSE_RANGE)

        respiration = clip(13.5 + 2.5 * (a - 0.5) + 0.5 * smooth_noise(self.seed, t, 480, 5), *RESP_RANGE)
        return {
            "systolic": round(systolic),
            "diastolic": round(diastolic),
            "glucose": round(glucose),
            "glucose_context": self.glucose_context(t_utc),
            "respiration": round(respiration),
            "arousal": a,
        }
