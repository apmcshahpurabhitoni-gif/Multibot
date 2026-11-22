"""Regression tests for the single active MULTIBOT2 runtime owner."""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from db import DatabaseManager
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
    assert 'if __name__=="__main__": raise SystemExit(main())' in source


def test_runtime_guard_fails_closed_when_process_is_not_leader(monkeypatch):
    monkeypatch.setattr(main, "RUNTIME_LEASE_REQUIRED", True)
    monkeypatch.setattr(main, "RUNTIME_LEADER", False)
    monkeypatch.setattr(main, "STOP", threading.Event())
    with pytest.raises(RuntimeError, match="not the active"):
        main._require_runtime_leader()


def test_deployment_entrypoints_are_consistent():
    root = Path(main.__file__).resolve().parent
    render = (root / "render.yaml").read_text(encoding="utf-8")
    legacy = (root / "startup.py").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")

    assert "startCommand: python main.py" in render
    assert "python startup.py && python main.py" not in render
    assert "from main import main as runtime_main" in legacy
    assert "telegram_send" not in legacy
    assert "python main.py" in readme


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
