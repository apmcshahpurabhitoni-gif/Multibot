"""Canonical signal occurrence and dashboard contract helpers."""
from __future__ import annotations
from dataclasses import dataclass
from uuid import uuid4
import pandas as pd
from signal_gate import signal_status
from strategies.base import Signal

TERMINAL={"NON_DIRECTIONAL","STALE","DUPLICATE_LIMIT","ACCOUNT_LIMIT","NO_TRADE_PLAN","DELIVERED","ERROR"}

def new_signal_id(): return uuid4().hex

def signal_key(signal, gate, symbol):
    return gate.signal_key(signal,symbol=symbol)

def dashboard_signal(event, send_state=None, delivery=None, now=None):
    current=pd.Timestamp.now(tz="Asia/Kolkata") if now is None else pd.Timestamp(now)
    ts=pd.Timestamp(event["timestamp"])
    if ts.tzinfo is None: ts=ts.tz_localize("Asia/Kolkata")
    signal=Signal(
        str(event.get("strategy","")),
        str(event.get("version","")),
        str(event.get("symbol","")),
        str(event.get("direction","NO_SIGNAL")),
        ts,
        str(event.get("timeframe","")),
        str(event.get("reason","")),
    )
    try:
        freshness, age_hours = signal_status(signal, now=current)
        age=max(0,int(age_hours*60))
    except (ValueError, TypeError, OverflowError) as exc:
        # One malformed historical row must never 500 the entire dashboard API.
        import logging
        logging.getLogger(__name__).warning("Malformed signal row degraded to STALE | key=%s error=%s",event.get("signal_id") or event.get("timestamp"),exc)
        freshness, age = "STALE", 0
    out=dict(event)
    metadata=dict(out.get("metadata") or {})
    # Support rows written before levels were promoted to canonical event metadata.
    for key in ("entry", "stop_loss", "take_profit"):
        if out.get(key) is None and key in metadata:
            out[key]=metadata.get(key)
    out["freshness"]=freshness
    out["age_minutes"]=age
    out["send_count"]=int((send_state or {}).get("send_count",0))
    out["first_sent_at"]=(send_state or {}).get("first_sent_at")
    out["last_sent_at"]=(send_state or {}).get("last_sent_at")
    out["delivery"]=delivery
    levels=(out.get("entry"),out.get("stop_loss"),out.get("take_profit"))
    out["has_trade_levels"]=all(value is not None for value in levels)
    out["actionable"]=bool(out["has_trade_levels"] and freshness=="FRESH" and str(out.get("pipeline_status","")).upper() not in {"STALE","ERROR","NO_TRADE_PLAN","ACCOUNT_LIMIT","DUPLICATE_LIMIT"})
    return out
