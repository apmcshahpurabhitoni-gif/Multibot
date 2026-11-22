import sqlite3
import sys
import types

import pytest

import db as db_module
from db import DatabaseManager


def _fake_libsql_module(remote_path):
    def connect(database, auth_token):
        assert database.startswith("libsql://")
        assert auth_token == "test-token"
        return sqlite3.connect(remote_path, timeout=30)
    return types.SimpleNamespace(connect=connect)


def test_turso_remote_database_survives_manager_restart(tmp_path, monkeypatch):
    remote_path = str(tmp_path / "turso-primary.db")
    monkeypatch.setattr(db_module, "TURSO_DATABASE_URL", "libsql://unit-test.aws-ap-south-1.turso.io")
    monkeypatch.setattr(db_module, "TURSO_AUTH_TOKEN", "test-token")
    monkeypatch.setattr(db_module, "DEFAULT_DB_PATH", str(tmp_path / "unused-default.db"))
    monkeypatch.setitem(sys.modules, "libsql", _fake_libsql_module(remote_path))

    first = DatabaseManager(str(tmp_path / "ephemeral-a.db"))
    first.load_accounts(("sweep_4h",), 100000, "2026-11-22")
    first.save_account(
        "sweep_4h",
        balance=98500,
        trades_today=1,
        planned_risk_used=2000,
        reset_date="2026-11-22",
    )
    first.record_scan_run("run-1", "sweep_v2", "2026-11-22T10:00:00+05:30", "OK", {"checked": 25})
    first.save_trade("trade-1", "CLOSED", {"symbol": "BTC-USD", "account": "sweep_4h", "pnl": 1200}, "2026-11-22T10:05:00+05:30")
    first.record_signal_send("sweep_v2|BTC-USD|BUY|candle-1", "2026-11-22T10:06:00+05:30")
    first.save_scan_error_alert(
        "sweep_v2", "MARKET_DATA_ERROR@BTC-USD",
        first_sent_at="2026-11-22T10:00:00+05:30",
        last_sent_at="2026-11-22T10:00:00+05:30",
    )
    first.save_market_data_cache(
        "test-cache", "BTC-USD", "30d", "1h", True,
        '{"close":100}', "2026-11-22T10:00:00+05:30",
    )

    # A new app container has a different local path but reconnects to the same
    # remote Turso database and sees the previous account and scan history.
    restarted = DatabaseManager(str(tmp_path / "ephemeral-b.db"))
    account = restarted.load_accounts(("sweep_4h",), 100000, "2026-11-22")["sweep_4h"]
    assert account["balance"] == 98500
    assert account["trades_today"] == 1
    assert account["planned_risk_used"] == 2000
    assert restarted.load_scan_runs()[0]["id"] == "run-1"
    assert restarted.load_trades("CLOSED")[0]["pnl"] == 1200
    assert restarted.signal_count("sweep_v2|BTC-USD|BUY|candle-1") == 1
    assert restarted.load_scan_error_alert("sweep_v2")["fingerprint"] == "MARKET_DATA_ERROR@BTC-USD"
    assert restarted.load_market_data_cache("test-cache")["payload"] == '{"close":100}'
    assert restarted.market_data_cache_health() == {"enabled": True, "remote": True, "reason": "READ_WRITE_OK"}


def test_turso_imports_existing_local_sqlite_state_once(tmp_path, monkeypatch):
    local_path = str(tmp_path / "legacy-state.db")
    legacy = DatabaseManager(local_path)
    legacy.load_accounts(("macro",), 100000, "2026-11-22")
    legacy.save_account(
        "macro",
        balance=97000,
        trades_today=2,
        planned_risk_used=4000,
        reset_date="2026-11-22",
    )
    legacy.save_trade(
        "trade-1",
        "CLOSED",
        {"symbol": "BTC-USD", "account": "macro", "pnl": 1500},
        "2026-11-22T10:00:00+05:30",
    )

    remote_path = str(tmp_path / "turso-migration.db")
    monkeypatch.setattr(db_module, "TURSO_DATABASE_URL", "libsql://unit-test.aws-ap-south-1.turso.io")
    monkeypatch.setattr(db_module, "TURSO_AUTH_TOKEN", "test-token")
    monkeypatch.setattr(db_module, "DEFAULT_DB_PATH", str(tmp_path / "unused-default.db"))
    monkeypatch.setitem(sys.modules, "libsql", _fake_libsql_module(remote_path))

    migrated = DatabaseManager(local_path)
    account = migrated.load_accounts(("macro",), 100000, "2026-11-22")["macro"]
    assert account["balance"] == 97000
    assert account["trades_today"] == 2
    assert migrated.load_trades("CLOSED")[0]["pnl"] == 1500

    # Reopening must not re-import stale local rows over later remote changes.
    migrated.save_account(
        "macro",
        balance=96000,
        trades_today=3,
        planned_risk_used=6000,
        reset_date="2026-11-22",
    )
    reopened = DatabaseManager(local_path)
    assert reopened.load_accounts(("macro",), 100000, "2026-11-22")["macro"]["balance"] == 96000


def test_partial_turso_configuration_fails_clearly(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "TURSO_DATABASE_URL", "libsql://unit-test.aws-ap-south-1.turso.io")
    monkeypatch.setattr(db_module, "TURSO_AUTH_TOKEN", "")
    import pytest
    with pytest.raises(db_module.DatabaseError, match="must both be configured"):
        DatabaseManager(str(tmp_path / "state.db"))


def test_calendar_cache_uses_turso_as_its_durable_store(tmp_path, monkeypatch):
    remote_path = str(tmp_path / "turso-calendar.db")
    monkeypatch.setattr(db_module, "TURSO_DATABASE_URL", "libsql://unit-test.aws-ap-south-1.turso.io")
    monkeypatch.setattr(db_module, "TURSO_AUTH_TOKEN", "test-token")
    monkeypatch.setattr(db_module, "DEFAULT_DB_PATH", str(tmp_path / "unused-default.db"))
    monkeypatch.setitem(sys.modules, "libsql", _fake_libsql_module(remote_path))

    from calendar_store import CalendarStore

    first = CalendarStore(str(tmp_path / "calendar-a.db"))
    events = [{"id": "event-1", "title": "CPI", "impact": "High"}]
    first.save_week("forex_factory", "2026-11-23", events)

    restarted = CalendarStore(str(tmp_path / "calendar-b.db"))
    restored, fetched_at = restarted.load_week("forex_factory", "2026-11-23")
    assert restored == events
    assert fetched_at
    latest, _ = restarted.load_latest()
    assert latest == events



def test_market_data_cache_read_retries_transient_turso_error_with_fresh_connection(tmp_path, monkeypatch):
    import db as db_module

    database = DatabaseManager(str(tmp_path / "cache-read.db"))
    database.turso_enabled = True
    monkeypatch.setattr(db_module.time, "sleep", lambda _seconds: None)
    connections = []

    class Cursor:
        def fetchone(self):
            return {
                "cache_key": "BTC-USD|1d|1h|0",
                "symbol": "BTC-USD",
                "period": "1d",
                "interval": "1h",
                "validate_hourly": 0,
                "payload": '{"close":100}',
                "updated_at": "2026-11-22T10:00:00+00:00",
            }

    class FakeConnection:
        def __init__(self, fail):
            self.fail = fail

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, sql, parameters=()):
            if self.fail:
                raise RuntimeError(
                    "interactive transaction was rolled back because the stream "
                    "was idle for too long; retry the transaction (SQLITE_BUSY)"
                )
            return Cursor()

    def connect():
        connection = FakeConnection(fail=not connections)
        connections.append(connection)
        return connection

    monkeypatch.setattr(database, "_connect", connect)
    row = database.load_market_data_cache("BTC-USD|1d|1h|0")
    assert row["payload"] == '{"close":100}'
    assert len(connections) == 2


def test_market_data_cache_upsert_retries_transient_turso_error(tmp_path, monkeypatch):
    import db as db_module

    database = DatabaseManager(str(tmp_path / "cache-write.db"))
    database.turso_enabled = True
    monkeypatch.setattr(db_module.time, "sleep", lambda _seconds: None)
    connections = []

    class FakeConnection:
        def __init__(self, fail):
            self.fail = fail
            self.executed = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, sql, parameters=()):
            self.executed = True
            if self.fail:
                raise RuntimeError(
                    "interactive transaction was rolled back because the stream "
                    "was idle for too long; retry the transaction (SQLITE_BUSY)"
                )

    def connect():
        connection = FakeConnection(fail=not connections)
        connections.append(connection)
        return connection

    monkeypatch.setattr(database, "_connect", connect)
    database.save_market_data_cache(
        "BTC-USD|1d|1h|0", "BTC-USD", "1d", "1h", False,
        '{"close":100}', "2026-11-22T10:00:00+00:00",
    )
    assert len(connections) == 2
    assert all(connection.executed for connection in connections)


def test_remote_connection_commits_only_pending_writes_once():
    class Cursor:
        description = None

    class FakeConnection:
        def __init__(self):
            self.commits = 0
            self.closed = False

        def execute(self, sql, parameters=()):
            return Cursor()

        def commit(self):
            self.commits += 1

        def rollback(self):
            pass

        def close(self):
            self.closed = True

    inner = FakeConnection()
    with db_module._RemoteConnection(inner) as connection:
        connection.execute("INSERT INTO sample(value) VALUES(?)", ("x",))
        connection.commit()
    assert inner.commits == 1
    assert inner.closed

    read_only = FakeConnection()
    with db_module._RemoteConnection(read_only) as connection:
        connection.execute("SELECT 1")
    assert read_only.commits == 0
    assert read_only.closed


def test_scan_run_retries_ambiguous_hrana_commit_with_fresh_connection(tmp_path, monkeypatch):
    remote_path = str(tmp_path / "turso-scan-retry.db")
    database = DatabaseManager(remote_path)
    database.turso_enabled = True
    monkeypatch.setattr(db_module.time, "sleep", lambda _seconds: None)
    opened = []

    class CommitFault:
        def __init__(self, connection, fail_after_commit):
            self.connection = connection
            self.fail_after_commit = fail_after_commit

        def execute(self, sql, parameters=()):
            return self.connection.execute(sql, parameters)

        def commit(self):
            self.connection.commit()
            if self.fail_after_commit:
                self.fail_after_commit = False
                raise ValueError(
                    "Hrana: interactive transaction was rolled back because "
                    "the stream was idle for too long (SQLITE_BUSY)"
                )

        def rollback(self):
            self.connection.rollback()

        def close(self):
            self.connection.close()

    def connect():
        raw = sqlite3.connect(remote_path, timeout=30)
        raw.row_factory = sqlite3.Row
        wrapped = db_module._RemoteConnection(CommitFault(raw, fail_after_commit=not opened))
        opened.append(wrapped)
        return wrapped

    monkeypatch.setattr(database, "_connect", connect)
    database.record_scan_run(
        "stable-run-id", "sweep_v2", "2026-11-22T10:00:00+05:30",
        "OK", {"checked": 1}, "2026-11-22T10:01:00+05:30",
    )

    assert len(opened) == 2
    with sqlite3.connect(remote_path) as check:
        assert check.execute("SELECT count(*) FROM scan_runs WHERE id='stable-run-id'").fetchone()[0] == 1


def test_append_only_delivery_is_not_blindly_retried_after_ambiguous_commit(tmp_path, monkeypatch):
    remote_path = str(tmp_path / "turso-delivery-no-retry.db")
    database = DatabaseManager(remote_path)
    database.turso_enabled = True
    opened = []

    class CommitFault:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, sql, parameters=()):
            return self.connection.execute(sql, parameters)

        def commit(self):
            self.connection.commit()
            raise ValueError("Hrana SQLITE_BUSY: stream was idle for too long")

        def rollback(self):
            self.connection.rollback()

        def close(self):
            self.connection.close()

    def connect():
        raw = sqlite3.connect(remote_path, timeout=30)
        raw.row_factory = sqlite3.Row
        opened.append(True)
        return db_module._RemoteConnection(CommitFault(raw))

    monkeypatch.setattr(database, "_connect", connect)
    with pytest.raises(db_module.DatabaseError, match="SQLITE_BUSY"):
        database.record_delivery("signal-1", channel="telegram", status="SENT")

    assert len(opened) == 1
    with sqlite3.connect(remote_path) as check:
        assert check.execute("SELECT count(*) FROM deliveries WHERE signal_id='signal-1'").fetchone()[0] == 1
