import pandas as pd
from strategies.base import Signal
from signal_gate import signal_status, signal_actionable_at

IST="Asia/Kolkata"

def sig(ts, timeframe="4H"):
    return Signal("Sweep V2","1","TCS","BUY",pd.Timestamp(ts,tz=IST),timeframe,"BULLISH",1,0.9,1.2)

def test_4h_signal_is_fresh_for_one_hour_after_completed_candle_close():
    s=sig("2026-09-11 09:15")
    assert signal_actionable_at(s) == pd.Timestamp("2026-09-11 13:15",tz=IST)
    assert signal_status(s,now=pd.Timestamp("2026-09-11 13:58",tz=IST))[0] == "FRESH"

def test_4h_signal_is_stale_after_one_hour_from_completed_candle_close():
    s=sig("2026-09-11 09:15")
    assert signal_status(s,now=pd.Timestamp("2026-09-11 14:16",tz=IST))[0] == "STALE"

def test_restart_later_does_not_replay_old_signal_as_fresh():
    s=sig("2026-09-11 09:15")
    assert signal_status(s,now=pd.Timestamp("2026-09-12 09:15",tz=IST))[0] == "STALE"


def test_stale_directional_signal_is_persisted_before_delivery_is_skipped():
    from strategies import discover_strategies
    from strategy_service import StrategyService
    from db import DatabaseManager
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        db=DatabaseManager(path=str(Path(td)/"state.db"))
        service=StrategyService(registry=discover_strategies(),database=db)
        signal=sig("2026-09-11 09:15")
        result=service.dispatch("sweep_v2","TCS",signal,current_price=1.0,now=pd.Timestamp("2026-09-11 14:16",tz=IST),send=True)
        assert result.reason == "STALE_SIGNAL"
        assert result.sent is False
        rows=db.load_signal_history()
        row=next(x for x in rows if x["signal_id"]==result.signal_id)
        assert row["direction"]=="BUY"
        assert row["pipeline_status"]=="STALE"
        assert row["delivery"]["status"]=="NOT_SENT_STALE"
