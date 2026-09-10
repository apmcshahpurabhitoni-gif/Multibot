"""Canonical signal freshness and identity helpers for MULTIBOT2."""
from __future__ import annotations
import pandas as pd
from config import SIGNAL_FRESHNESS_HOURS,IST_TIMEZONE
from strategies.base import Signal
MAX_MESSAGE_SEND_COUNT=2
def normalize_timestamp(value):
    ts=pd.Timestamp(value)
    if ts.tzinfo is None:raise ValueError("Timestamp must be timezone-aware")
    return ts.tz_convert(IST_TIMEZONE)
def signal_age_hours(signal,*,now=None):
    age=(normalize_timestamp(pd.Timestamp.now(tz=IST_TIMEZONE) if now is None else now)-normalize_timestamp(signal.timestamp)).total_seconds()/3600
    if age<0:raise ValueError("Signal timestamp cannot be in the future")
    return age
def is_fresh_age(age_hours):return 0<=float(age_hours)<=SIGNAL_FRESHNESS_HOURS
def is_signal_fresh(signal,*,now=None):return is_fresh_age(signal_age_hours(signal,now=now))
def build_signal_identity(signal,*,symbol=None):
    normalized=(symbol or signal.symbol).strip().upper()
    if not normalized:raise ValueError("Signal symbol cannot be empty")
    return "|".join((signal.strategy,normalized,signal.direction,normalize_timestamp(signal.timestamp).isoformat()))
class SignalGate:
    """Stateless freshness/identity facade. DatabaseManager exclusively owns send counts."""
    def __init__(self,max_age_hours=SIGNAL_FRESHNESS_HOURS,max_repeats=MAX_MESSAGE_SEND_COUNT):
        if max_age_hours!=SIGNAL_FRESHNESS_HOURS or max_repeats!=MAX_MESSAGE_SEND_COUNT:raise ValueError("Locked signal rules cannot be overridden")
    def age_hours(self,signal,*,now=None):return signal_age_hours(signal,now=now)
    def is_fresh(self,signal,*,now=None):return is_signal_fresh(signal,now=now)
    @staticmethod
    def signal_key(signal,*,symbol=None):return build_signal_identity(signal,symbol=symbol)
    def can_send(self,signal,*,symbol=None,now=None):return signal.is_directional and self.is_fresh(signal,now=now)
def signal_status(signal,*,now=None):
    age=signal_age_hours(signal,now=now);return ("FRESH" if is_fresh_age(age) else "STALE",age)
