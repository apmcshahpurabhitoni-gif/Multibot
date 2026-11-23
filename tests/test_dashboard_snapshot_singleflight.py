from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import main


def _reset_snapshot_state(monkeypatch):
    monkeypatch.setattr(main, "_DASHBOARD_SNAPSHOT_CONDITION", threading.Condition(threading.Lock()))
    monkeypatch.setattr(main, "_DASHBOARD_SNAPSHOT_CACHE", None)
    monkeypatch.setattr(main, "_DASHBOARD_SNAPSHOT_CACHE_AT", 0.0)
    monkeypatch.setattr(main, "_DASHBOARD_SNAPSHOT_BUILDING", False)
    monkeypatch.setattr(main, "_DASHBOARD_SNAPSHOT_LAST_ERROR", None)
    monkeypatch.setattr(main, "_DASHBOARD_SNAPSHOT_FAILURE_AT", 0.0)


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

 
 
def test_concurrent_runtime_initialization_runs_health_check_once(monkeypatch):
    from types import SimpleNamespace

    calls = []
    monkeypatch.setattr(main, "_RUNTIME_INIT_LOCK", threading.RLock())
    monkeypatch.setattr(main, "_RUNTIME_INITIALIZED", False)
    monkeypatch.setattr(main, "SETTINGS_LOADED", True)
    monkeypatch.setattr(main, "validate_runtime_configuration", lambda: None)
    monkeypatch.setattr(main.DB, "market_data_cache_health", lambda: calls.append(1) or {
        "enabled": True, "remote": True, "reason": "READ_WRITE_OK"
    })
    monkeypatch.setattr(main, "ACCOUNTS", {"test": object()})
    monkeypatch.setattr(main, "REGISTRY", SimpleNamespace(all=lambda: []))
    monkeypatch.setattr(main, "SERVICE", object())
    monkeypatch.setattr(main, "TRADE_MONITOR", object())
    monkeypatch.setattr(main, "REMINDERS", None)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: main.ensure_runtime(), range(8)))

    assert len(calls) == 1
    assert main._RUNTIME_INITIALIZED is True



def test_concurrent_cold_failure_does_not_retry_for_each_waiter(monkeypatch):
    _reset_snapshot_state(monkeypatch)

    class TrackingCondition(threading.Condition):
        def __init__(self):
            super().__init__(threading.Lock())
            self.waiter_count = 0
            self.all_waiting = threading.Event()

        def wait(self, timeout=None):
            self.waiter_count += 1
            if self.waiter_count >= 7:
                self.all_waiting.set()
            return super().wait(timeout)

    condition = TrackingCondition()
    monkeypatch.setattr(main, "_DASHBOARD_SNAPSHOT_CONDITION", condition)
    calls = []
    started = threading.Event()
    release = threading.Event()

    def build():
        calls.append(1)
        started.set()
        assert release.wait(3)
        raise OSError("temporary database outage")

    monkeypatch.setattr(main, "_build_dashboard_snapshot", build)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(main.snapshot) for _ in range(8)]
        assert started.wait(2)
        assert condition.all_waiting.wait(2)
        release.set()
        for future in futures:
            try:
                future.result(timeout=5)
            except (OSError, RuntimeError):
                pass
            else:
                raise AssertionError("cold snapshot failure should reach every waiter")

    assert len(calls) == 1
    assert main._DASHBOARD_SNAPSHOT_BUILDING is False
