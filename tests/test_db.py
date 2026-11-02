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


def test_supabase_restore_network_failure_does_not_block_sqlite_startup(tmp_path, monkeypatch):
    """A Supabase outage must not prevent a local SQLite runtime from opening."""
    from db import DatabaseManager, DatabaseError

    db = DatabaseManager(str(tmp_path / "state.db"))
    calls = []

    monkeypatch.setattr(DatabaseManager, "supabase_enabled", property(lambda self: True))

    def unavailable(self, method, table, **kwargs):
        calls.append((method, table))
        raise DatabaseError(f"Supabase {method} {table} failed: DNS unavailable")

    monkeypatch.setattr(DatabaseManager, "_supabase_request", unavailable)

    # A wiped/new local database must still initialize even when the very first
    # remote restore (accounts) cannot resolve Supabase.
    reopened = DatabaseManager(str(tmp_path / "fresh.db"))
    accounts = reopened.load_accounts(("sweep_4h",), 100000, "2026-11-03")

    assert accounts["sweep_4h"]["balance"] == 100000
    assert calls == [("GET", "accounts")]


def test_supabase_restore_failure_does_not_replace_existing_local_state(tmp_path, monkeypatch):
    """Local records remain authoritative when remote rehydration is offline."""
    from db import DatabaseManager, DatabaseError

    path = str(tmp_path / "state.db")
    local = DatabaseManager(path)
    local.load_accounts(("sweep_4h",), 100000, "2026-11-03")
    local.save_account(
        "sweep_4h",
        balance=98500,
        trades_today=1,
        planned_risk_used=2000,
        reset_date="2026-11-03",
    )

    monkeypatch.setattr(DatabaseManager, "supabase_enabled", property(lambda self: True))

    def unavailable(self, method, table, **kwargs):
        raise DatabaseError(f"Supabase {method} {table} failed: DNS unavailable")

    monkeypatch.setattr(DatabaseManager, "_supabase_request", unavailable)

    reopened = DatabaseManager(path)
    accounts = reopened.load_accounts(("sweep_4h",), 100000, "2026-11-03")

    assert accounts["sweep_4h"]["balance"] == 98500
    assert accounts["sweep_4h"]["trades_today"] == 1
    assert accounts["sweep_4h"]["planned_risk_used"] == 2000
