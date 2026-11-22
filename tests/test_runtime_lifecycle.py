"""Regression tests for the single active MULTIBOT2 runtime owner."""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from db import DatabaseManager
from strategy_service import RuntimeLeadershipError, StrategyService
import main


def test_runtime_lease_allows_one_owner_and_expires(tmp_path):
    db = DatabaseManager(str(tmp_path / "runtime.db"))

    assert db.acquire_runtime_lease("process-a", ttl_seconds=60, now_epoch=100)
    assert not db.acquire_runtime_lease("process-b", ttl_seconds=60, now_epoch=110)
    assert db.runtime_lease_owner()["owner_id"] == "process-a"
    assert "runtime_leases" not in db._TABLES  # leases are ephemeral, never copied from old local state
    assert db.runtime_lease_is_owned("process-a", now_epoch=159)
    assert not db.runtime_lease_is_owned("process-a", now_epoch=160)

    # The current owner can renew; a competing process cannot steal a live lease.
    assert db.renew_runtime_lease("process-a", ttl_seconds=60, now_epoch=120)
    assert not db.acquire_runtime_lease("process-b", ttl_seconds=60, now_epoch=179)

    # Once expired, the new process takes ownership and the old owner cannot renew.
    assert db.acquire_runtime_lease("process-b", ttl_seconds=60, now_epoch=181)
    assert not db.renew_runtime_lease("process-a", ttl_seconds=60, now_epoch=182)
    assert db.runtime_lease_owner()["owner_id"] == "process-b"
    assert db.runtime_lease_is_owned("process-b", now_epoch=182)


def test_runtime_lease_release_only_releases_its_owner(tmp_path):
    db = DatabaseManager(str(tmp_path / "runtime.db"))
    assert db.acquire_runtime_lease("process-a", now_epoch=100)
    db.release_runtime_lease("process-b")
    assert db.runtime_lease_owner()["owner_id"] == "process-a"
    db.release_runtime_lease("process-a")
    assert db.runtime_lease_owner() is None


def test_named_worker_start_is_idempotent(monkeypatch):
    stop = threading.Event()
    started = []
    started_event = threading.Event()
    monkeypatch.setattr(main, "WORKER_THREADS", {})
    monkeypatch.setattr(main, "LOCK", threading.RLock())

    def worker():
        started.append(True)
        started_event.set()
        stop.wait(2)

    first = main._start_worker("test-worker", worker)
    second = main._start_worker("test-worker", worker)
    try:
        assert first is second
        assert started_event.wait(1)
        assert len(started) == 1
    finally:
        stop.set()
        first.join(timeout=2)


def test_runtime_entrypoint_has_single_leader_gate():
    source = Path(main.__file__).read_text(encoding="utf-8")
    assert "DB.acquire_runtime_lease" in source
    assert "DB.renew_runtime_lease" in source
    assert "_require_runtime_leader()" in source
    assert "RUNTIME_LEASE_REQUIRED=True" in source
    assert "runtime_guard=_require_runtime_leader" in source
    assert 'if __name__=="__main__": raise SystemExit(main())' in source


def test_runtime_guard_fails_closed_when_process_is_not_leader(monkeypatch):
    monkeypatch.setattr(main, "RUNTIME_LEASE_REQUIRED", True)
    monkeypatch.setattr(main, "RUNTIME_LEADER", False)
    monkeypatch.setattr(main, "STOP", threading.Event())
    with pytest.raises(RuntimeError, match="not the active"):
        main._require_runtime_leader()


def test_deployment_entrypoints_are_consistent():
    root = Path(main.__file__).resolve().parent
    legacy = (root / "startup.py").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    telegram = (root / "telegram.py").read_text(encoding="utf-8")

    assert "from main import main as runtime_main" in legacy
    assert "telegram_send" not in legacy
    assert "./.venv/bin/python main.py" in readme
    assert "https://multibot-1d1fdf1c.appliedintelligencecorporation.com/dashboard" in telegram
    assert "https://multibot-1d1fdf1c.appliedintelligencecorporation.com/architecture" in telegram


def test_runtime_lease_is_part_of_the_shared_schema():
    root = Path(main.__file__).resolve().parent
    schema_test = (root / "tests" / "test_schema_parity.py").read_text(encoding="utf-8")
    assert '"runtime_leases"' in schema_test


def test_deployed_runtime_requires_shared_turso_lease_backend(monkeypatch):
    monkeypatch.setenv("PORT", "10000")
    monkeypatch.delenv("MULTIBOT_ALLOW_LOCAL_RUNTIME_LEASE", raising=False)
    monkeypatch.setattr(main.DB, "turso_enabled", False)
    with pytest.raises(RuntimeError, match="Turso is required"):
        main._validate_runtime_lease_backend()

    monkeypatch.setenv("MULTIBOT_ALLOW_LOCAL_RUNTIME_LEASE", "true")
    main._validate_runtime_lease_backend()


def test_shutdown_drains_workers_before_releasing_lease():
    source = Path(main.__file__).read_text(encoding="utf-8")
    shutdown = source.split("deadline=time.monotonic()+45.0", 1)[1]
    assert shutdown.index("worker.join") < shutdown.index("DB.release_runtime_lease")
    assert "lease left to expire" in shutdown


def test_concurrent_runtime_claims_have_exactly_one_winner(tmp_path):
    db_path = str(tmp_path / "shared-runtime.db")
    first_db = DatabaseManager(db_path)
    second_db = DatabaseManager(db_path)
    barrier = threading.Barrier(2)
    results = []

    def claim(database, owner):
        barrier.wait(timeout=2)
        results.append(database.acquire_runtime_lease(owner, now_epoch=500))

    first = threading.Thread(target=claim, args=(first_db, "process-a"))
    second = threading.Thread(target=claim, args=(second_db, "process-b"))
    first.start()
    second.start()
    first.join(timeout=5)
    second.join(timeout=5)

    assert not first.is_alive() and not second.is_alive()
    assert sum(results) == 1


def test_strategy_service_propagates_lease_loss():
    def lost_lease():
        raise RuntimeLeadershipError("lease lost")

    service = StrategyService(
        registry=object(),
        provider=object(),
        database=object(),
        accounts={},
        runtime_guard=lost_lease,
    )
    with pytest.raises(RuntimeLeadershipError, match="lease lost"):
        service._check_runtime_guard()


def test_runtime_guard_caches_remote_lease_verification(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "RUNTIME_LEASE_REQUIRED", True)
    monkeypatch.setattr(main, "RUNTIME_LEADER", True)
    monkeypatch.setattr(main, "RUNTIME_OWNER_ID", "process-a")
    monkeypatch.setattr(main, "STOP", threading.Event())
    monkeypatch.setattr(main, "RUNTIME_LEASE_LAST_VERIFIED", 0.0)
    monkeypatch.setattr(main, "RUNTIME_LEASE_VERIFY_INTERVAL_SECONDS", 5.0)
    monkeypatch.setattr(main, "RUNTIME_LEASE_VERIFY_LOCK", threading.Lock())
    monkeypatch.setattr(main.DB, "runtime_lease_is_owned", lambda owner: calls.append(owner) or True)

    main._require_runtime_leader()
    main._require_runtime_leader()
    assert calls == ["process-a"]


def test_runtime_lease_retries_transient_turso_failure_with_fresh_connection(tmp_path, monkeypatch):
    import db as db_module

    database = DatabaseManager(str(tmp_path / "runtime.db"))
    monkeypatch.setattr(db_module.time, "sleep", lambda _seconds: None)
    opened = []

    class Cursor:
        def __init__(self, row=None):
            self.row = row

        def fetchone(self):
            return self.row

    class FakeConnection:
        def __init__(self, fail=False):
            self.fail = fail
            self.closed = False
            self.executed = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            self.closed = True

        def execute(self, sql, parameters=()):
            self.executed.append(sql)
            if sql.lstrip().startswith("INSERT INTO runtime_leases") and self.fail:
                raise RuntimeError(
                    "interactive transaction was rolled back because the stream "
                    "was idle for too long; retry the transaction (SQLITE_BUSY)"
                )
            if sql.lstrip().startswith("SELECT owner_id FROM runtime_leases"):
                return Cursor({"owner_id": "process-a"})
            return Cursor()

    def connect():
        # First connection fails during the UPSERT; retry uses a fresh
        # connection for the write and another fresh one for verification.
        connection = FakeConnection(fail=not opened)
        opened.append(connection)
        return connection

    monkeypatch.setattr(database, "_connect", connect)
    assert database.acquire_runtime_lease("process-a", now_epoch=100)
    assert len(opened) == 3
    assert all(connection.closed for connection in opened)
    assert opened[1].executed[0].lstrip().startswith("INSERT INTO runtime_leases")
    assert opened[2].executed[0].lstrip().startswith("SELECT owner_id FROM runtime_leases")


def test_runtime_lease_does_not_retry_non_transient_errors(tmp_path, monkeypatch):
    import db as db_module

    database = DatabaseManager(str(tmp_path / "runtime.db"))
    monkeypatch.setattr(db_module.time, "sleep", lambda _seconds: None)
    attempts = []

    class BrokenConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return None

        def execute(self, sql, parameters=()):
            attempts.append(sql)
            raise RuntimeError("invalid SQL syntax")

    monkeypatch.setattr(database, "_connect", lambda: BrokenConnection())
    with pytest.raises(RuntimeError, match="invalid SQL syntax"):
        database.acquire_runtime_lease("process-a", now_epoch=100)
    assert len(attempts) == 1


def test_web_server_retries_address_in_use_without_exiting_runtime(monkeypatch):
    import errno

    class FastStopEvent(threading.Event):
        def wait(self, timeout=None):
            return False

    stop = FastStopEvent()
    calls = []
    closed = []

    class FakeServer:
        def serve_forever(self):
            stop.set()

        def server_close(self):
            closed.append(True)

    def make_server(host, port, app, **kwargs):
        assert kwargs.get("server_class") is main.ThreadingWSGIServer
        calls.append((host, port))
        if len(calls) == 1:
            raise OSError(errno.EADDRINUSE, "Address already in use")
        return FakeServer()

    monkeypatch.setattr(main, "STOP", stop)
    monkeypatch.setattr(main, "LOCK", threading.RLock())
    monkeypatch.setattr(main, "HTTP_SERVER", None)
    monkeypatch.setattr(main, "make_server", make_server)
    monkeypatch.setattr(main, "build_app", lambda: object())
    monkeypatch.setenv("PORT", "10000")

    main.web_server()

    assert len(calls) == 2
    assert closed == [True]
    assert main.HTTP_SERVER is None


def test_remote_connection_wraps_statement_error_without_masking_it():
    import db as db_module

    class BrokenTursoConnection:
        def execute(self, sql, parameters=()):
            raise ValueError(
                "Hrana: stream error: interactive transaction was rolled back "
                "because the stream was idle for too long (SQLITE_BUSY)"
            )

        def rollback(self):
            raise ValueError("Hrana: cannot rollback - no transaction is active")

        def close(self):
            pass

    remote=db_module._RemoteConnection(BrokenTursoConnection())
    with pytest.raises(db_module.DatabaseError, match="stream was idle for too long"):
        with remote as connection:
            connection.execute("UPDATE runtime_leases SET owner_id=?",("process-a",))
