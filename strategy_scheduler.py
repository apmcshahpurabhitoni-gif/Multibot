"""Canonical manifest schedule parser for plug-and-play strategies."""
from __future__ import annotations

import pandas as pd

SCHEDULES = {
    "canonical_sweep_schedule": {"type": "interval", "seconds": 60},
    "daily_completed_candle": {"type": "interval", "seconds": 86400},
}


def _timeframe_seconds(timeframe: str) -> int:
    """Convert a strategy timeframe into its candle duration."""
    value = str(timeframe).strip().lower()
    if not value:
        raise ValueError("Strategy completed_candle schedule requires a timeframe")

    unit = value[-1]
    try:
        amount = int(value[:-1])
    except ValueError as exc:
        raise ValueError(f"Unsupported timeframe for completed_candle: {timeframe!r}") from exc

    multipliers = {"m": 60, "h": 3600, "d": 86400, "w": 604800}
    if amount <= 0 or unit not in multipliers:
        raise ValueError(f"Unsupported timeframe for completed_candle: {timeframe!r}")
    return amount * multipliers[unit]


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
            timeframes = strategy.manifest.timeframes
            if not timeframes:
                raise ValueError(
                    f"Strategy {strategy.manifest.id} uses completed_candle without a timeframe"
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
