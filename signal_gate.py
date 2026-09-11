"""Canonical signal freshness and identity helpers for MULTIBOT2."""
from __future__ import annotations
import re
import pandas as pd
from config import SIGNAL_FRESHNESS_HOURS, IST_TIMEZONE
from strategies.base import Signal

MAX_MESSAGE_SEND_COUNT = 2

def normalize_timestamp(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        raise ValueError("Timestamp must be timezone-aware")
    return ts.tz_convert(IST_TIMEZONE)

def _timeframe_delta(timeframe: str) -> pd.Timedelta:
    value = str(timeframe or "").strip().upper()
    match = re.fullmatch(r"(\d+)\s*(M|H|D|W)", value)
    if not match:
        raise ValueError(f"Unsupported signal timeframe: {timeframe!r}")
    amount, unit = int(match.group(1)), match.group(2)
    return {"M": pd.Timedelta(minutes=amount), "H": pd.Timedelta(hours=amount),
            "D": pd.Timedelta(days=amount), "W": pd.Timedelta(weeks=amount)}[unit]

def signal_actionable_at(signal: Signal) -> pd.Timestamp:
    """The completed-candle close when this candle-based signal first became actionable."""
    return normalize_timestamp(signal.timestamp) + _timeframe_delta(signal.timeframe)

def signal_age_hours(signal: Signal, *, now: pd.Timestamp | None = None) -> float:
    current = normalize_timestamp(pd.Timestamp.now(tz=IST_TIMEZONE) if now is None else now)
    candle_at = normalize_timestamp(signal.timestamp)
    if current < candle_at:
        raise ValueError("Signal timestamp cannot be in the future")
    actionable_at = signal_actionable_at(signal)
    return max(0.0, (current - actionable_at).total_seconds() / 3600)

def is_fresh_age(age_hours: float) -> bool:
    return 0 <= float(age_hours) <= SIGNAL_FRESHNESS_HOURS

def is_signal_fresh(signal: Signal, *, now: pd.Timestamp | None = None) -> bool:
    return is_fresh_age(signal_age_hours(signal, now=now))

def build_signal_identity(signal: Signal, *, symbol: str | None = None) -> str:
    normalized = (symbol or signal.symbol).strip().upper()
    if not normalized:
        raise ValueError("Signal symbol cannot be empty")
    return "|".join((signal.strategy, normalized, signal.direction,
                     normalize_timestamp(signal.timestamp).isoformat()))

class SignalGate:
    """Stateless freshness and identity facade; durable send counts belong to DatabaseManager."""
    max_age_hours = SIGNAL_FRESHNESS_HOURS
    max_repeats = MAX_MESSAGE_SEND_COUNT
    def __init__(self, max_age_hours=SIGNAL_FRESHNESS_HOURS, max_repeats=MAX_MESSAGE_SEND_COUNT):
        if max_age_hours != SIGNAL_FRESHNESS_HOURS:
            raise ValueError("MULTIBOT2 freshness is locked at 1 hour")
        if max_repeats != MAX_MESSAGE_SEND_COUNT:
            raise ValueError("MULTIBOT2 maximum signal sends is locked at 2")
    def age_hours(self, signal: Signal, *, now: pd.Timestamp | None = None) -> float:
        return signal_age_hours(signal, now=now)
    def is_fresh(self, signal: Signal, *, now: pd.Timestamp | None = None) -> bool:
        return is_signal_fresh(signal, now=now)
    @staticmethod
    def signal_key(signal: Signal, *, symbol: str | None = None) -> str:
        return build_signal_identity(signal, symbol=symbol)
    def can_send(self, signal: Signal, *, symbol: str | None = None, now: pd.Timestamp | None = None) -> bool:
        return signal.is_directional and self.is_fresh(signal, now=now)

def signal_status(signal: Signal, *, now: pd.Timestamp | None = None) -> tuple[str, float]:
    age = signal_age_hours(signal, now=now)
    return ("FRESH" if is_fresh_age(age) else "STALE", age)

__all__=["SignalGate","MAX_MESSAGE_SEND_COUNT","build_signal_identity","is_fresh_age",
         "is_signal_fresh","signal_age_hours","signal_actionable_at","signal_status"]
