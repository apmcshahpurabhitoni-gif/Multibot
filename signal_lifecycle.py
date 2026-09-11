"""Canonical signal occurrence and dashboard contract helpers."""
from __future__ import annotations
from dataclasses import dataclass
from uuid import uuid4
import pandas as pd

TERMINAL={"NON_DIRECTIONAL","STALE","DUPLICATE_LIMIT","ACCOUNT_LIMIT","NO_TRADE_PLAN","DELIVERED","ERROR"}

def new_signal_id(): return uuid4().hex

def signal_key(signal, gate, symbol):
    return gate.signal_key(signal,symbol=symbol)

def dashboard_signal(event, send_state=None, delivery=None, now=None):
    current=pd.Timestamp.now(tz="Asia/Kolkata") if now is None else pd.Timestamp(now)
    ts=pd.Timestamp(event["timestamp"])
    if ts.tzinfo is None: ts=ts.tz_localize("Asia/Kolkata")
    age=max(0,int((current.tz_convert(ts.tzinfo)-ts).total_seconds()/60))
    out=dict(event)
    out["freshness"]="FRESH" if age<=60 else "STALE"
    out["age_minutes"]=age
    out["send_count"]=int((send_state or {}).get("send_count",0))
    out["first_sent_at"]=(send_state or {}).get("first_sent_at")
    out["last_sent_at"]=(send_state or {}).get("last_sent_at")
    out["delivery"]=delivery
    return out
