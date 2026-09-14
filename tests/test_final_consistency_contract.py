from pathlib import Path
import pandas as pd

from dashboard import signal_to_dict
from signal_lifecycle import dashboard_signal
from strategies.base import Signal

ROOT=Path(__file__).resolve().parents[1]


def _signal(entry=100.0, stop=95.0, target=110.0):
    return Signal("Sweep V2","v2.1","BTC-USD","SELL",pd.Timestamp("2026-09-14T03:30:00",tz="Asia/Kolkata"),"4H","TEST",entry,stop,target,{})


def test_dashboard_signal_contract_preserves_levels_and_actionability():
    row=signal_to_dict(_signal())
    assert row["entry"]==100.0
    assert row["stop_loss"]==95.0
    assert row["take_profit"]==110.0
    assert row["has_trade_levels"] is True
    assert "actionable" in row


def test_dashboard_signal_marks_missing_levels_non_actionable():
    event={"strategy":"Sweep V2","version":"v2.1","symbol":"BTC-USD","direction":"SELL","timestamp":"2026-09-14T00:00:00+00:00","timeframe":"4H","reason":"STALE_SIGNAL","pipeline_status":"STALE","metadata":{}}
    row=dashboard_signal(event,now=pd.Timestamp("2026-09-14T00:30:00+00:00"))
    assert row["has_trade_levels"] is False
    assert row["actionable"] is False


def test_final_frontend_contract_uses_safe_json_and_separated_backtest_semantics():
    app=(ROOT/"app.js").read_text(encoding="utf-8")
    css=(ROOT/"styles.css").read_text(encoding="utf-8")
    assert "function readJsonResponse" in app
    assert 'readJsonResponse(response,"Backtest API")' in app
    assert "Signals generated during this test" in app
    assert "Detected opportunities" not in app
    assert "Signal details unavailable" in app
    assert "max-height:560px !important" in css
    assert "overflow-y:auto !important" in css
