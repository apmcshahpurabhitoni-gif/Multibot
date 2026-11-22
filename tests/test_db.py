import pandas as pd
from db import DatabaseManager

def test_signal_send_limit_survives_restart(tmp_path):
    path=tmp_path/"state.db";db=DatabaseManager(str(path));key="adaptive_trend|BTC-USD|BUY|2026-08-31T10:15:00+05:30";db.record_signal_send(key,"2026-08-31T10:20:00+05:30","2026-08-31T11:20:00+05:30","message",{"x":1});assert db.signal_count(key)==1
    reopened=DatabaseManager(str(path));assert reopened.signal_count(key)==1;assert len(reopened.due_reminders("2026-08-31T11:20:00+05:30"))==1
    reopened.mark_reminder_sent(key,"2026-08-31T11:21:00+05:30");assert reopened.signal_count(key)==2;assert reopened.due_reminders("2026-08-31T12:00:00+05:30")==[]

def test_account_daily_reset(tmp_path):
    db=DatabaseManager(str(tmp_path/"state.db"));rows=db.load_accounts(("nifty",),100000,"2026-08-31");assert rows["nifty"]["trades_today"]==0
    db.save_account("nifty",balance=98000,trades_today=2,planned_risk_used=4000,reset_date="2026-08-31")
    rows=db.load_accounts(("nifty",),100000,"2026-09-01");assert rows["nifty"]["trades_today"]==0 and rows["nifty"]["planned_risk_used"]==0

def test_load_signal_history_batches_delivery_and_send_state(tmp_path):
    from types import SimpleNamespace

    db = DatabaseManager(str(tmp_path / "history.db"))
    signal = SimpleNamespace(
        strategy="sweep_v2",
        version="2.0.0",
        symbol="BTC-USD",
        direction="BUY",
        timestamp=pd.Timestamp("2026-11-22T10:00:00+05:30"),
        timeframe="4h",
        reason="test signal",
        metadata={"entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0},
    )
    signal_id = db.record_signal_event(
        "signal-1", "sweep_v2|BTC-USD|BUY|2026-11-22", signal,
        pipeline_status="READY",
    )
    db.record_delivery(signal_id, channel="telegram", status="FAILED", attempted_at="2026-11-22T10:01:00+05:30", error_text="temporary")
    db.record_delivery(signal_id, channel="telegram", status="SENT", attempted_at="2026-11-22T10:02:00+05:30")
    db.record_signal_send("sweep_v2|BTC-USD|BUY|2026-11-22", "2026-11-22T10:02:00+05:30")

    original_connect = db._connect
    connection_count = 0

    def counted_connect():
        nonlocal connection_count
        connection_count += 1
        return original_connect()

    db._connect = counted_connect
    rows = db.load_signal_history(500)

    assert connection_count == 1
    assert len(rows) == 1
    assert rows[0]["delivery"] == {
        "status": "SENT",
        "attempted_at": "2026-11-22T10:02:00+05:30",
        "error": None,
        "message_type": None,
    }
    assert rows[0]["send_state"] == {
        "send_count": 1,
        "first_sent_at": "2026-11-22T10:02:00+05:30",
        "last_sent_at": "2026-11-22T10:02:00+05:30",
    }
