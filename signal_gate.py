"""Canonical signal freshness and identity helpers for MULTIBOT2."""
from __future__ import annotations
import pandas as pd
from config import SIGNAL_FRESHNESS_HOURS, IST_TIMEZONE
from strategies.base import Signal

MAX_MESSAGE_SEND_COUNT = 2

def normalize_timestamp(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        raise ValueError("Timestamp must be timezone-aware")
    return ts.tz_convert(IST_TIMEZONE)

def signal_age_hours(signal: Signal, *, now: pd.Timestamp | None = None) -> float:
    ts = normalize_timestamp(signal.timestamp)
    current = normalize_timestamp(pd.Timestamp.now(tz=IST_TIMEZONE) if now is None else now)
    age = (current - ts).total_seconds() / 3600
    if age < 0:
        raise ValueError("Signal timestamp cannot be in the future")
    return age

def is_fresh_age(age_hours: float) -> bool:
    return 0 <= float(age_hours) <= SIGNAL_FRESHNESS_HOURS

def is_signal_fresh(signal: Signal, *, now: pd.Timestamp | None = None) -> bool:
    return is_fresh_age(signal_age_hours(signal, now=now))

def build_signal_identity(signal: Signal, *, symbol: str | None = None) -> str:
    normalized = (symbol or signal.symbol).strip().upper()
    if not normalized:
        raise ValueError("Signal symbol cannot be empty")
    return "|".join((
        signal.strategy,
        normalized,
        signal.direction,
        normalize_timestamp(signal.timestamp).isoformat(),
    ))

class SignalGate:
    """Stateless compatibility facade.

    Durable duplicate/send counts belong to DatabaseManager. This object owns
    only freshness and canonical signal identity so every runtime path agrees.
    """

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

    def accept(self, signal: Signal, *, symbol: str | None = None, now: pd.Timestamp | None = None) -> bool:
        return self.can_send(signal, symbol=symbol, now=now)

    def clear(self):
        return None

    def snapshot(self):
        return {}

    def restore(self, counts):
        if not isinstance(counts, dict):
            raise TypeError("Signal counts must be a dictionary")

def signal_status(signal: Signal, *, now: pd.Timestamp | None = None) -> tuple[str, float]:
    age = signal_age_hours(signal, now=now)
    return ("FRESH" if is_fresh_age(age) else "STALE", age)

__all__ = [
    "SignalGate", "MAX_MESSAGE_SEND_COUNT", "build_signal_identity",
    "is_fresh_age", "is_signal_fresh", "signal_age_hours", "signal_status",
]