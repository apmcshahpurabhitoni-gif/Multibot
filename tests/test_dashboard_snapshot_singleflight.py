from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import main


def _reset_snapshot_state(monkeypatch):
    monkeypatch.setattr(main, "_DASHBOARD_SNAPSHOT_CONDITION", threading.Condition(threading.Lock()))
    monkeypatch.setattr(main, "_DASHBOARD_SNAPSHOT_CACHE", None)
    monkeypatch.setattr(main, "_DASHBOARD_SNAPSHOT_CACHE_AT", 0.0)
    monkeypatch.setattr(main, "_DASHBOARD_SNAPSHOT_BUILDING", False)


def test_concurrent_cold_dashboard_requests_share_one_snapshot_build(monkeypatch):
    _reset_snapshot_state(monkeypatch)
    started = threading.Event()
    release = threading.Event()
    calls = []
    payload = {"ok": True, "generation": 1}

    def build():
        calls.append(1)
        started.set()
        assert release.wait(3)
        return payload

    monkeypatch.setattr(main, "_build_dashboard_snapshot", build)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(main.snapshot) for _ in range(8)]
        assert started.wait(2)
        release.set()
        results = [future.result(timeout=5) for future in futures]

    assert len(calls) == 1
    assert all(result is payload for result in results)


def test_stale_dashboard_snapshot_is_served_during_refresh(monkeypatch):
    _reset_snapshot_state(monkeypatch)
    stale = {"ok": True, "generation": 1}
    started = threading.Event()
    release = threading.Event()
    monkeypatch.setattr(main, "_DASHBOARD_SNAPSHOT_CACHE", stale)
    monkeypatch.setattr(main, "_DASHBOARD_SNAPSHOT_CACHE_AT", 0.0)

    def build():
        started.set()
        assert release.wait(3)
        return {"ok": True, "generation": 2}

    monkeypatch.setattr(main, "_build_dashboard_snapshot", build)
    with ThreadPoolExecutor(max_workers=2) as pool:
        refresh = pool.submit(main.snapshot)
        assert started.wait(2)
        assert main.snapshot() is stale
        release.set()
        assert refresh.result(timeout=5)["generation"] == 2

    assert main.snapshot()["generation"] == 2
