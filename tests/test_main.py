import io
import json

import main


def _call(method, path, *, origin=None, host="localhost:3000", forwarded=None,
          token=None, authorization=None, body=b""):
    """Drive the real WSGI app with a crafted request."""
    app = main.build_app()
    env = {
        "PATH_INFO": path, "REQUEST_METHOD": method, "HTTP_HOST": host,
        "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body),
        "wsgi.errors": io.StringIO(), "wsgi.url_scheme": "http",
        "SERVER_NAME": "localhost", "SERVER_PORT": "3000",
    }
    if origin is not None:
        env["HTTP_ORIGIN"] = origin
    if forwarded is not None:
        env["HTTP_X_FORWARDED_HOST"] = forwarded
    if token is not None:
        env["HTTP_X_ADMIN_TOKEN"] = token
    if authorization is not None:
        env["HTTP_AUTHORIZATION"] = authorization
    captured = {}
    chunks = app(env, lambda status, headers: captured.__setitem__("status", status))
    raw = b"".join(chunks)
    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        payload = None
    return captured["status"], payload


def test_registry_is_strategy_driven():
    main.ensure_runtime()
    assert set(main.REGISTRY.ids()) == {"adaptive_trend", "sweep_v2", "engulfing_66_sma"}


def test_ping_contract_exists():
    assert callable(main.web_server) and callable(main.run_strategy_cycle)


# --- configuration endpoint protection ----------------------------------

def test_settings_reads_stay_open_for_the_dashboard(monkeypatch):
    """Reads must keep working without a token: the Tools cards consume them."""
    monkeypatch.delenv("DASHBOARD_API_TOKEN", raising=False)
    status, payload = _call("GET", "/api/settings", origin="http://localhost:3000")
    assert status == "200 OK" and payload["ok"] is True
    # Clients without Origin/Referer (curl, server-to-server) also read.
    status, payload = _call("GET", "/api/notifications")
    assert status == "200 OK" and payload["ok"] is True


def test_configuration_endpoints_reject_cross_origin_requests(monkeypatch):
    monkeypatch.delenv("DASHBOARD_API_TOKEN", raising=False)
    for path in ("/api/settings", "/api/notifications"):
        for method, body in (("GET", b""), ("POST", b"{")):
            status, payload = _call(method, path, origin="https://evil.example", body=body)
            assert status == "403 Forbidden", (method, path, status)
            assert payload["code"] == "CROSS_ORIGIN"


def test_configuration_writes_are_open_by_default(monkeypatch):
    """Local-first default: no token configured, same-origin writes proceed."""
    monkeypatch.delenv("DASHBOARD_API_TOKEN", raising=False)
    status, payload = _call("POST", "/api/settings",
                            origin="http://localhost:3000", body=b"{")
    assert status == "400 Bad Request"  # reached the handler, not an auth wall
    assert payload["ok"] is False


def test_admin_token_gates_every_configuration_write(monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "sekret-token")
    origin = "http://localhost:3000"
    # Missing token -> 401 with a machine-readable code.
    status, payload = _call("POST", "/api/settings", origin=origin, body=b"{")
    assert status == "401 Unauthorized" and payload["code"] == "ADMIN_TOKEN_REQUIRED"
    # Wrong token -> still refused.
    status, payload = _call("POST", "/api/notifications", origin=origin,
                            token="nope", body=b"{")
    assert status == "401 Unauthorized" and payload["code"] == "ADMIN_TOKEN_REQUIRED"
    # Correct token via X-Admin-Token -> the write proceeds (400 = bad JSON body).
    status, _ = _call("POST", "/api/settings", origin=origin,
                      token="sekret-token", body=b"{")
    assert status == "400 Bad Request"
    # Correct token via Authorization: Bearer -> also proceeds.
    status, _ = _call("POST", "/api/notifications", origin=origin,
                      authorization="Bearer sekret-token", body=b"{")
    assert status == "400 Bad Request"
    # Reads remain open so the dashboard keeps rendering.
    status, _ = _call("GET", "/api/settings", origin=origin)
    assert status == "200 OK"


# --- scan error alert dedup ----------------------------------------------

class _FakeNotifier:
    def __init__(self):
        self.calls = []

    def deliver(self, **kwargs):
        self.calls.append(kwargs)
        return True


def test_repeated_scan_error_alerts_are_deduplicated(monkeypatch, tmp_path):
    """One asset outage must not post one ERROR bubble per sweep, while a new
    failure set and a recovered-then-failed cycle still alert.

    Suppression state is the persisted incident in db.scan_error_alerts — not
    process memory — so the same guarantees hold across a restart (covered in
    test_sweep_market_data_errors.py)."""
    from types import SimpleNamespace
    from db import DatabaseManager

    notifier = _FakeNotifier()
    monkeypatch.setattr(main, "SERVICE", SimpleNamespace(notifier=notifier))
    monkeypatch.setattr(main, "DB", DatabaseManager(str(tmp_path / "state.db")))
    payload = {"errors": 1, "checked": 25, "sent": 0}
    first = [SimpleNamespace(symbol="BTC-USD", reason="MARKET_DATA_ERROR: HTTP 429")]
    main._notify_scan("r1", "sweep_v2", payload, first)
    assert len(notifier.calls) == 1 and notifier.calls[0]["kind"] == "ERROR"
    # Same failing asset, different error text: still one incident.
    repeat = [SimpleNamespace(symbol="BTC-USD", reason="MARKET_DATA_ERROR: timeout")]
    main._notify_scan("r2", "sweep_v2", payload, repeat)
    assert len(notifier.calls) == 1
    # A different failing asset is a new incident and alerts immediately.
    widened = repeat + [SimpleNamespace(symbol="GC=F", reason="MARKET_DATA_ERROR: timeout")]
    main._notify_scan("r3", "sweep_v2", payload, widened)
    assert len(notifier.calls) == 2
    # A clean scan clears the durable incident...
    main._notify_scan("r4", "sweep_v2", {"errors": 0, "checked": 25, "sent": 1}, [])
    assert len(notifier.calls) == 3 and notifier.calls[-1]["kind"] == "SCAN"
    assert main.DB.load_scan_error_alert("sweep_v2") is None
    # ...so the next failure alerts again.
    main._notify_scan("r5", "sweep_v2", payload, first)
    assert len(notifier.calls) == 4 and notifier.calls[-1]["kind"] == "ERROR"


def test_scan_error_alert_is_bounded_by_a_repeat_window():
    """An all-day outage re-alerts at most once per hour, not per sweep.

    The window is judged from the persisted incident with wall-clock time, so a
    process restart cannot reset it (the old monotonic in-memory state could)."""
    from datetime import datetime, timedelta, timezone

    base = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
    strategy_id, fingerprint = "adaptive_trend", "MARKET_DATA_ERROR@BTC-USD"
    assert main.scan_error_alert_decision(None, fingerprint, now=base) == "send"
    entry = {
        "strategy_id": strategy_id,
        "fingerprint": fingerprint,
        "first_sent_at": base.isoformat(),
        "last_sent_at": base.isoformat(),
        "suppressed": 0,
    }
    for _ in range(50):
        assert main.scan_error_alert_decision(entry, fingerprint, now=base) == "suppress"
    after = base + timedelta(seconds=main.SCAN_ERROR_REPEAT_SECONDS)
    assert main.scan_error_alert_decision(entry, fingerprint, now=after) == "reminder"
    # The reminder re-arms the window: bounded to one send per repeat window.
    rearmed = dict(entry, last_sent_at=after.isoformat())
    assert main.scan_error_alert_decision(rearmed, fingerprint, now=after) == "suppress"


def test_origin_check_honours_forwarded_host_behind_a_proxy(monkeypatch):
    """A public Origin must match X-Forwarded-Host, not the internal Host."""
    monkeypatch.delenv("DASHBOARD_API_TOKEN", raising=False)
    status, payload = _call("POST", "/api/settings", origin="https://app.example",
                            host="internal:8080", forwarded="app.example", body=b"{")
    assert status == "400 Bad Request"  # same-origin as the browser sees it
    # Without the forwarded header the same request is cross-origin.
    status, payload = _call("POST", "/api/settings", origin="https://app.example",
                            host="internal:8080", body=b"{")
    assert status == "403 Forbidden" and payload["code"] == "CROSS_ORIGIN"
