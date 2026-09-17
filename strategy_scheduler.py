"""Canonical manifest schedule parser for plug-and-play strategies."""
from __future__ import annotations

import pandas as pd

SCHEDULES = {
    "canonical_sweep_schedule": {"type": "interval", "seconds": 60},
    "daily_completed_candle": {"type": "interval", "seconds": 86400},
}


def _timeframe_seconds(timeframe: str) -> int:
    """Convert a manifest timeframe into seconds for generic polling."""
    value = str(timeframe or "").strip().lower()
    if not value:
        raise ValueError("Completed-candle schedule requires a timeframe")
    units = {"m": 60, "h": 3600, "d": 86400, "w": 7 * 86400}
    try:
        amount = int(value[:-1])
        multiplier = units[value[-1]]
    except (KeyError, ValueError):
        raise ValueError(f"Unsupported strategy timeframe: {timeframe!r}") from None
    if amount <= 0:
        raise ValueError(f"Invalid strategy timeframe: {timeframe!r}")
    return amount * multiplier


class StrategyScheduler:
    def __init__(self):
        self._last = {}

    def interval_seconds(self, strategy):
        schedule = strategy.manifest.schedule
        if isinstance(schedule, dict):
            if schedule.get("type") != "interval":
                raise ValueError(f"Unsupported schedule type for {strategy.manifest.id}: {schedule!r}")
            seconds = int(schedule.get("seconds", 0))
        elif str(schedule) == "completed_candle":
            timeframes = tuple(strategy.manifest.timeframes or ())
            if len(timeframes) != 1:
                raise ValueError(
                    f"Strategy {strategy.manifest.id} uses completed_candle and must declare exactly one timeframe"
                )
            seconds = _timeframe_seconds(timeframes[0])
        else:
            spec = SCHEDULES.get(str(schedule))
            if spec is None:
                raise ValueError(
                    f"Strategy {strategy.manifest.id} uses unknown schedule {schedule!r}; "
                    "add it to SCHEDULES or use {'type':'interval','seconds':N}."
                )
            seconds = int(spec["seconds"])
        if seconds <= 0:
            raise ValueError(f"Invalid schedule interval for {strategy.manifest.id}")
        return seconds

    def is_due(self, strategy, now):
        key = strategy.manifest.id
        current = pd.Timestamp(now)
        last = self._last.get(key)
        if last is None:
            self._last[key] = current
            return True
        if (current - last).total_seconds() >= self.interval_seconds(strategy):
            self._last[key] = current
            return True
        return False
