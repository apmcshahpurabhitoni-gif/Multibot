"""Turso transport-failure behaviour.

A brief DNS/connect failure reaching Turso is transient: it must be retried on a
fresh connection, must not stop trading, and must not turn /api/dashboard into a
500. These tests pin the exact failure shape seen in production logs.
"""
import io
import json
import threading
import time

import main
from db import DatabaseError, DatabaseManager

DNS_FAILURE = (
    "Turso SQL execution failed: Hrana: `http error: `error trying to connect: "
    "dns error: failed to lookup address information: Temporary failure in "
    "name resolution``"
)


def _dns_error():
    return DatabaseError(DNS_FAILURE)


def _raiser(*args, **kwargs):
    raise _dns_error()


def _call(method, path, *, host="localhost:3000"):
    """Drive the real WSGI app with a crafted same-origin request."""
    app = main.build_app()
    env = {
        "PATH_INFO": path, "REQUEST_METHOD": method, "HTTP_HOST": host,
        "CONTENT_LENGTH": "0", "wsgi.input": io.BytesIO(b""),
        "wsgi.errors": io.StringIO(), "wsgi.url_scheme": "http",
        "SERVER_NAME": "localhost", "SERVER_PORT": "3000",
    }
    captured = {}
    chunks = app(env, lambda status, headers: captured.__setitem__("status", status))
    raw = b"".join(chunks)
    return captured["status"], json.loads(raw or b"{}")


def test_dns_and_connect_failures_are_transient_but_schema_errors_are_not():
    for text in (
        DNS_FAILURE,
        "Turso connection failed: [Errno -2] Name or service not known",
        "error trying to connect: dns error: failed to lookup address information",
        "connect error: Connection refused",
        "network is unreachable",
    ):
        assert DatabaseManager.is_transient_database_error(DatabaseError(text)) is True, text
    assert DatabaseManager.is_transient_database_error(DatabaseError("no such table: trades")) is False
    assert DatabaseManager.is_transient_database_error(DatabaseError("UNIQUE constraint failed")) is False


def test_runtime_lease_read_retries_dns_failure_on_a_fresh_connection(tmp_path):
    db = DatabaseManager(str(tmp_path / "state.db"))
    real_connect = db._connect
    db.turso_enabled = True
    attempts = []

    def flaky_connect():
        attempts.append(1)
        if len(attempts) == 1:
            raise _dns_error()
        db.turso_enabled = False  # stand in for a recovered connection
        return real_connect()

    db._connect = flaky_connect
    assert db.runtime_lease_is_owned("owner-1") is False
    assert len(attempts) == 2, "the DNS blip should be retried exactly once more"


def test_lease_guard_defers_across_a_whole_scan_without_hammering_turso(monkeypatch):
    """One scan calls the guard once per asset; the deferral must survive that."""
    stop = threading.Event()
    monkeypatch.setattr(main, "STOP", stop)
    monkeypatch.setattr(main, "RUNTIME_LEASE_REQUIRED", True)
    monkeypatch.setattr(main, "RUNTIME_LEADER", True)
    monkeypatch.setattr(main, "RUNTIME_OWNER_ID", "owner-1")
    monkeypatch.setattr(main, "RUNTIME_LEASE_TRANSIENT_FAILURES", 0)
    monkeypatch.setattr(main, "RUNTIME_LEASE_TRANSIENT_UNTIL", 0.0)
    reads = []

    def failing_read(*args, **kwargs):
        reads.append(1)
        raise _dns_error()

    monkeypatch.setattr(main.DB, "runtime_lease_is_owned", failing_read)

    # 500 per-asset guard calls, as a large scan would do.
    for _ in range(500):
        main._require_runtime_leader()

    assert stop.is_set() is False, "a transient blip must not stop trading mid-scan"
    assert len(reads) == 1, f"expected one probe then a quiet grace window, got {len(reads)} reads"
    assert main.RUNTIME_LEASE_TRANSIENT_UNTIL > 0.0


def test_lease_guard_still_fails_closed_once_the_grace_window_expires(monkeypatch):
    stop = threading.Event()
    monkeypatch.setattr(main, "STOP", stop)
    monkeypatch.setattr(main, "RUNTIME_LEASE_REQUIRED", True)
    monkeypatch.setattr(main, "RUNTIME_LEADER", True)
    monkeypatch.setattr(main, "RUNTIME_OWNER_ID", "owner-1")
    monkeypatch.setattr(main, "RUNTIME_LEASE_TRANSIENT_FAILURES", 0)
    monkeypatch.setattr(main, "RUNTIME_LEASE_TRANSIENT_UNTIL", 0.0)
    monkeypatch.setattr(main.DB, "runtime_lease_is_owned", _raiser)

    main._require_runtime_leader()  # opens the grace window
    assert stop.is_set() is False

    # The window has elapsed and the endpoint is still unreachable.
    monkeypatch.setattr(main, "RUNTIME_LEASE_TRANSIENT_UNTIL", time.monotonic() - 1.0)
    monkeypatch.setattr(main, "RUNTIME_LEASE_LAST_VERIFIED", 0.0)
    try:
        main._require_runtime_leader()
    except main.RuntimeLeadershipError:
        pass
    else:  # pragma: no cover - explicit failure message beats a bare assert
        raise AssertionError("a persistent database outage must eventually fail closed")
    assert stop.is_set() is True


def test_dashboard_degrades_instead_of_500_on_dns_failure(monkeypatch):
    # The default snapshot reads every section on one connection; when that read
    # fails it falls back to per-section reads, which must each degrade too.
    monkeypatch.setattr(main.DB, "dashboard_reads", _raiser)
    monkeypatch.setattr(main.DB, "load_trades", _raiser)
    monkeypatch.setattr(main.DB, "load_signal_history", _raiser)
    monkeypatch.setattr(main.DB, "load_scan_runs", _raiser)

    status, payload = _call("GET", "/api/dashboard")

    assert status.startswith("200"), status
    assert payload["ok"] is True
    assert payload["degraded"] is True
    assert {"dashboard_reads", "trades", "signal_history", "scan_history"} <= set(payload["health"]["degraded_sections"])
    assert payload["counts"]["trades"] == 0
    assert payload["counts"]["signals"] == 0


def test_dashboard_still_reports_a_non_transient_failure(monkeypatch):
    def broken(*args, **kwargs):
        raise DatabaseError("no such table: trades")

    monkeypatch.setattr(main.DB, "dashboard_reads", broken)

    status, payload = _call("GET", "/api/dashboard")

    assert status.startswith("500"), status
    assert payload["ok"] is False


def test_dashboard_snapshot_reads_every_section_on_one_connection(monkeypatch):
    """A snapshot pays for one Turso handshake, not one per section."""
    opened = []
    real_connect = main.DB._connect

    def counting_connect():
        opened.append(1)
        return real_connect()

    monkeypatch.setattr(main.DB, "_connect", counting_connect)

    payload = main.snapshot()

    assert payload["ok"] is True
    assert len(opened) == 1, f"expected one connection per snapshot, got {len(opened)}"
    assert {"signals", "trades", "accounts", "scan", "health", "counts", "strategies", "universe"} <= set(payload)
