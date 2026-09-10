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
