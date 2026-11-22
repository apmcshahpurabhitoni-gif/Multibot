"""Regression tests for the single active MULTIBOT2 runtime owner."""
from __future__ import annotations

import threading

from db import DatabaseManager
import main


def test_runtime_lease_allows_one_owner_and_expires(tmp_path):
    db = DatabaseManager(str(tmp_path / "runtime.db"))

    assert db.acquire_runtime_lease("process-a", ttl_seconds=60, now_epoch=100)
    assert not db.acquire_runtime_lease("process-b", ttl_seconds=60, now_epoch=110)
    assert db.runtime_lease_owner()["owner_id"] == "process-a"

    # The current owner can renew; a competing process cannot steal a live lease.
    assert db.renew_runtime_lease("process-a", ttl_seconds=60, now_epoch=120)
    assert not db.acquire_runtime_lease("process-b", ttl_seconds=60, now_epoch=179)

    # Once expired, the new process takes ownership and the old owner cannot renew.
    assert db.acquire_runtime_lease("process-b", ttl_seconds=60, now_epoch=181)
    assert not db.renew_runtime_lease("process-a", ttl_seconds=60, now_epoch=182)
    assert db.runtime_lease_owner()["owner_id"] == "process-b"


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
    monkeypatch.setattr(main, "WORKER_THREADS", {})
    monkeypatch.setattr(main, "LOCK", threading.RLock())

    def worker():
        started.append(True)
        stop.wait(2)

    first = main._start_worker("test-worker", worker)
    second = main._start_worker("test-worker", worker)
    try:
        assert first is second
        assert len(started) == 1
    finally:
        stop.set()
        first.join(timeout=2)


def test_runtime_entrypoint_has_single_leader_gate():
    source = (main.__file__ and __import__("pathlib").Path(main.__file__).read_text())
    assert "DB.acquire_runtime_lease" in source
    assert "DB.renew_runtime_lease" in source
    assert "_require_runtime_leader()" in source
    assert "RUNTIME_LEASE_REQUIRED=True" in source
