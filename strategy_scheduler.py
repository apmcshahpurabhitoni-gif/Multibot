"""Canonical manifest schedule parser for plug-and-play strategies.

The scheduler owns only execution cadence. Strategy-specific candle/session
construction remains inside the strategy or its shared market-data helpers.
"""
from __future__ import annotations

import re

import pandas as pd


SCHEDULES = {
    # Sweep V2 intentionally polls frequently; its canonical session schedule
    # is resolved by sweep_engine when building completed candles.
    "canonical_sweep_schedule": {"type": "interval", "seconds": 60},
    "daily_completed_candle": {"type": "interval", "seconds": 86400},
}


def _timeframe_seconds(timeframe: str) -> int:
    """Convert a strategy timeframe (e.g. 1h, 1d) to seconds."""
    value = str(timeframe or "").strip().lower()
    match = re.fullmatch(r"(\d+)\s*([mhdw])", value)
    if not match:
        raise ValueError(f"Unsupported strategy timeframe: {timeframe!r}")
    amount, unit = int(match.group(1)), match.group(2)
    multiplier = {"m": 60, "h": 3600, "d": 86400, "w": 604800}[unit]
    seconds = amount * multiplier
    if seconds <= 0:
        raise ValueError(f"Invalid strategy timeframe: {timeframe!r}")
    return seconds


class StrategyScheduler:
    def __init__(self):
        self._last = {}

    def interval_seconds(self, strategy):
        schedule = strategy.manifest.schedule
        if isinstance(schedule, dict):
            if schedule.get("type") != "interval":
                raise ValueError(
                    f"Unsupported schedule type for {strategy.manifest.id}: {schedule!r}"
                )
            seconds = int(schedule.get("seconds", 0))
        else:
            schedule_name = str(schedule)
            spec = SCHEDULES.get(schedule_name)
            if spec is not None:
                seconds = int(spec["seconds"])
            elif schedule_name == "completed_candle":
                timeframes = tuple(strategy.manifest.timeframes or ())
                if len(timeframes) != 1:
                    raise ValueError(
                        f"completed_candle requires exactly one strategy timeframe for "
                        f"{strategy.manifest.id}: {timeframes!r}"
                    )
                seconds = _timeframe_seconds(timeframes[0])
            else:
                raise ValueError(
                    f"Strategy {strategy.manifest.id} uses unknown schedule {schedule!r}; "
                    "add a generic schedule or use {'type':'interval','seconds':N}."
                )
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
