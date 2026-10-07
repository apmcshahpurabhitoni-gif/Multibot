"""Sweep V2 market-data failure contract.

Verified against the real failure path (reproduced before the fix): one
malformed Yahoo candle used to poison the entire 7-day frame with the bare
error "OHLC data contains invalid values", and the alert dedup lived only in
process memory. The contract now:

- identifies invalid provider rows (field, candle, raw value, kind);
- never uses an invalid row for trading and never repairs it (no zero-fill,
  no forward-fill, no coercion of surviving cells);
- keeps valid candles usable when the bad row is outside the required sweep
  window;
- rejects (never manufactures) a sweep candle whose window lost a row;
- keeps strict OHLC validation fully active;
- deduplicates scan alerts from a durable incident row that survives restarts
  and redeploys, with edge-triggered sends and a bounded hourly reminder.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

import config  # noqa: F401  # strategy discovery must precede sweep_engine
from config import IST_TIMEZONE, LIVE_ASSET_MAP
from db import DatabaseManager
from market_data import (
    MarketDataError,
    find_invalid_ohlc_rows,
    normalize_candles,
    quarantine_invalid_rows,
)
from strategy_service import StrategyService
from strategies import discover_strategies
from sweep_engine import build_closed_candles, last_quarantine
from telegram import msg_scan_error
from trading import AccountState

SYMBOL = "BTC-USD"
NOW = pd.Timestamp("2026-10-06 22:30:00+05:30")


def make_frame() -> pd.DataFrame:
    """Eight days of hourly candles covering every completed BTC sweep window."""
    index = pd.date_range("2026-09-29 00:30:00", periods=8 * 24, freq="1h", tz=IST_TIMEZONE)
    return pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
        index=index,
    )


def closed_bars(frame: pd.DataFrame) -> pd.DataFrame:
    bars, _, warning = build_closed_candles(frame, SYMBOL, now=NOW, lookback_days=7)
    assert warning is None
    return bars


# --- 1-3: invalid-row identification (strict validation stays active) ----


def test_nan_ohlc_row_is_identified_with_field_timestamp_and_raw_value():
    frame = make_frame()
    bad_ts = frame.index[3]
    frame.loc[bad_ts, "close"] = float("nan")

    issues = find_invalid_ohlc_rows(frame)

    assert len(issues) == 1
    issue = issues[0]
    assert issue.field == "close"
    assert issue.kind == "nan"
    assert issue.timestamp == bad_ts
    assert str(issue.raw_value) == "nan"  # captured before any coercion
    assert "field=close" in issue.describe()


def test_non_numeric_ohlc_row_is_identified():
    frame = make_frame().astype(object)
    bad_ts = frame.index[5]
    frame.loc[bad_ts, "high"] = "not-a-number"

    issues = find_invalid_ohlc_rows(frame)

    assert [issue.kind for issue in issues] == ["non_numeric"]
    assert issues[0].raw_value == "not-a-number"
    assert issues[0].timestamp == bad_ts


def test_invalid_high_and_low_rows_are_identified():
    frame = make_frame()
    bad_ts = frame.index[2]
    frame.loc[bad_ts, "high"] = 90.0  # below open/close
    issues = find_invalid_ohlc_rows(frame)
    assert [issue.kind for issue in issues] == ["invalid_high"]
    assert issues[0].field == "high"

    frame = make_frame()
    frame.loc[bad_ts, "low"] = 110.0  # above open/close
    issues = find_invalid_ohlc_rows(frame)
    assert [issue.kind for issue in issues] == ["invalid_low"]
    assert issues[0].field == "low"


def test_strict_normalize_still_rejects_any_invalid_cell_with_diagnostics():
    """normalize_candles itself remains strict: no quarantine, no exceptions."""
    frame = make_frame()
    frame.loc[frame.index[0], "close"] = float("nan")

    with pytest.raises(MarketDataError, match="OHLC data contains invalid values"):
        normalize_candles(frame)

    try:
        normalize_candles(frame)
    except MarketDataError as exc:
        diagnostics = getattr(exc, "diagnostics", None)
        assert diagnostics is not None
        assert diagnostics["failing_field"] == "close"
        assert diagnostics["value_kind"] == "nan"
        assert diagnostics["failing_candle"] == str(frame.index[0])


# --- 4: malformed candle OUTSIDE the required window ---------------------


def test_malformed_row_outside_required_window_keeps_valid_candles():
    """A bad row the sweep never needs must not poison unrelated candles."""
    pristine = closed_bars(make_frame())

    frame = make_frame()
    bad_ts = frame.index[0]  # 00:30 — before the first sweep window (01:30)
    frame.loc[bad_ts, "close"] = float("nan")

    bars = closed_bars(frame)  # no exception

    assert list(bars.index) == list(pristine.index)
    pd.testing.assert_frame_equal(bars, pristine)


# --- 5: malformed candle INSIDE the required window ----------------------


def test_malformed_row_inside_required_window_rejects_that_candle():
    """The window that lost a row is rejected; it is never manufactured."""
    pristine = closed_bars(make_frame())
    window_start = pd.Timestamp("2026-10-06 17:30:00+05:30")  # completed 4H window
    inside_ts = window_start + pd.Timedelta(hours=2)  # 19:30, inside the window
    assert window_start in pristine.index

    frame = make_frame()
    frame.loc[inside_ts, "low"] = float("nan")
    bars = closed_bars(frame)  # still no exception: only the candle is lost

    assert window_start not in bars.index  # rejected, not manufactured
    assert len(bars) == len(pristine) - 1  # exactly one candle fewer
    # Every surviving candle is a complete window from the pristine baseline.
    assert set(bars.index) == set(pristine.index) - {window_start}
    # The quarantined row is reported for diagnostics.
    report = last_quarantine(SYMBOL)
    assert report is not None and report["dropped_rows"] == 1


def test_all_rows_invalid_is_a_real_failure_with_diagnostics():
    frame = make_frame()
    frame["close"] = float("nan")

    with pytest.raises(MarketDataError, match="all 192 rows are invalid"):
        build_closed_candles(frame, SYMBOL, now=NOW, lookback_days=7)

    try:
        build_closed_candles(frame, SYMBOL, now=NOW, lookback_days=7)
    except MarketDataError as exc:
        diagnostics = getattr(exc, "diagnostics", None)
        assert diagnostics is not None
        assert diagnostics["failing_field"] == "close"
        assert diagnostics["value_kind"] == "nan"


def test_clean_frame_retires_the_quarantine_report():
    frame = make_frame()
    frame.loc[frame.index[0], "close"] = float("nan")
    closed_bars(frame)
    assert last_quarantine(SYMBOL) is not None

    closed_bars(make_frame())  # clean scan clears the report (recovery)
    assert last_quarantine(SYMBOL) is None


# --- full-path diagnostics capture (scan_symbol -> signal metadata) -------


class _AllBadProvider:
    def fetch(self, symbol, *, period, interval, validate_hourly=True, provenance=None):
        if provenance is not None:
            provenance.update({"source": "fresh", "age_seconds": 0.0, "cache_key": "test-key"})
        frame = make_frame()
        frame["close"] = float("nan")
        return frame


def _service(tmp_path) -> StrategyService:
    return StrategyService(
        registry=discover_strategies(),
        provider=_AllBadProvider(),
        database=DatabaseManager(str(tmp_path / "state.db")),
        accounts={"sweep_4h": AccountState("sweep_4h", 100000.0, 100000.0, 0.0, 0)},
    )


def test_scan_symbol_captures_the_full_diagnostic_list(tmp_path):
    service = _service(tmp_path)
    strategy = service.registry.get("sweep_v2")
    asset = LIVE_ASSET_MAP[SYMBOL]

    with pytest.raises(MarketDataError) as caught:
        service.scan_symbol("sweep_v2", SYMBOL, now=NOW, period="30d")

    diagnostics = caught.value.diagnostics
    assert diagnostics["strategy"] == "sweep_v2"
    assert diagnostics["asset"] == asset.label
    assert diagnostics["symbol"] == SYMBOL
    assert diagnostics["yahoo_symbol"] == asset.yahoo_symbol
    assert diagnostics["provider_interval"] == "30m"
    assert diagnostics["requested_period"] == "30d"
    assert diagnostics["data_source"] == "fresh"
    assert diagnostics["cache_age_seconds"] == 0.0
    assert diagnostics["cache_key"] == "test-key"
    assert diagnostics["scan_timestamp"] == NOW.isoformat()
    # Failing-cell detail propagated from the market-data layer.
    assert diagnostics["failing_field"] == "close"
    assert diagnostics["value_kind"] == "nan"
    assert "invalid values" in diagnostics["error"]


def test_market_data_error_signal_carries_diagnostics_for_the_dashboard(tmp_path, monkeypatch):
    """The dashboard history (signal_events.metadata) must expose the capture."""
    service = _service(tmp_path)
    monkeypatch.setattr(
        "strategy_service.assets_for_strategy",
        lambda strategy_id: [LIVE_ASSET_MAP[SYMBOL]],
    )

    results = service.scan_and_dispatch("sweep_v2", now=NOW, send=False)

    assert len(results) == 1
    result = results[0]
    assert result.reason.startswith("MARKET_DATA_ERROR")
    diagnostics = result.signal.metadata.get("diagnostics")
    assert diagnostics is not None
    assert diagnostics["symbol"] == SYMBOL
    assert diagnostics["failing_field"] == "close"
    # Persisted for the dashboard history.
    stored = service.database.load_signal_history(10)
    assert stored[0]["metadata"].get("diagnostics") is not None


# --- 6-10: durable alert dedup -------------------------------------------


class _FakeNotifier:
    def __init__(self):
        self.calls = []

    def deliver(self, **kwargs):
        self.calls.append(kwargs)
        return True


def _wire(monkeypatch, tmp_path):
    from types import SimpleNamespace

    notifier = _FakeNotifier()
    monkeypatch.setattr(main_module(), "SERVICE", SimpleNamespace(notifier=notifier))
    db = DatabaseManager(str(tmp_path / "state.db"))
    monkeypatch.setattr(main_module(), "DB", db)
    return notifier, db


def main_module():
    import main
    return main


def _result(symbol="BTC-USD", reason="MARKET_DATA_ERROR: OHLC data contains invalid values"):
    return SimpleNamespace(symbol=symbol, reason=reason)


PAYLOAD = {"errors": 1, "checked": 25, "sent": 0}


def test_same_error_repeated_ten_times_sends_one_alert(monkeypatch, tmp_path):
    main = main_module()
    notifier, db = _wire(monkeypatch, tmp_path)

    for run in range(10):
        main._notify_scan(f"r{run}", "sweep_v2", PAYLOAD, [_result()])

    assert len(notifier.calls) == 1
    assert notifier.calls[0]["kind"] == "ERROR"
    incident = db.load_scan_error_alert("sweep_v2")
    assert incident is not None
    assert incident["suppressed"] == 9  # nine repeats counted, none delivered


def test_process_restart_keeps_suppression(monkeypatch, tmp_path):
    """A restarted process (new DatabaseManager, same storage) stays silent."""
    main = main_module()
    notifier, db = _wire(monkeypatch, tmp_path)

    main._notify_scan("r1", "sweep_v2", PAYLOAD, [_result()])
    assert len(notifier.calls) == 1

    # Simulated restart: state must come back from the persisted incident.
    monkeypatch.setattr(main, "DB", DatabaseManager(str(tmp_path / "state.db")))
    main._notify_scan("r2", "sweep_v2", PAYLOAD, [_result()])

    assert len(notifier.calls) == 1  # still suppressed after restart


def test_redeploy_restores_incident_from_supabase_mirror(monkeypatch, tmp_path):
    """Wiped local disk (Render redeploy) rehydrates the incident from remote."""
    from db import DatabaseManager as DB

    source = DB(str(tmp_path / "source.db"))
    first = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
    source.save_scan_error_alert(
        "sweep_v2", "MARKET_DATA_ERROR@BTC-USD",
        first_sent_at=first.isoformat(), last_sent_at=first.isoformat(),
    )
    remote_rows = [source.load_scan_error_alert("sweep_v2")]

    monkeypatch.setattr(DB, "supabase_enabled", True)
    monkeypatch.setattr(
        DB, "_supabase_request",
        lambda self, method, table, **kw: (remote_rows if method == "GET" else True),
    )
    wiped = DB(str(tmp_path / "wiped.db"))  # empty local disk at boot

    restored = wiped.load_scan_error_alert("sweep_v2")
    assert restored is not None
    assert restored["fingerprint"] == "MARKET_DATA_ERROR@BTC-USD"

    import main
    decision = main.scan_error_alert_decision(
        restored, "MARKET_DATA_ERROR@BTC-USD",
        now=first + timedelta(minutes=5),
    )
    assert decision == "suppress"  # redeploy did not re-arm the alert


def test_different_asset_failure_sends_a_new_alert(monkeypatch, tmp_path):
    main = main_module()
    notifier, db = _wire(monkeypatch, tmp_path)

    main._notify_scan("r1", "sweep_v2", PAYLOAD, [_result(symbol="BTC-USD")])
    main._notify_scan("r2", "sweep_v2", PAYLOAD, [_result(symbol="BTC-USD")])
    assert len(notifier.calls) == 1

    main._notify_scan("r3", "sweep_v2", PAYLOAD,
                      [_result(symbol="BTC-USD"), _result(symbol="GC=F")])
    assert len(notifier.calls) == 2


def test_different_error_class_sends_a_new_alert(monkeypatch, tmp_path):
    main = main_module()
    notifier, db = _wire(monkeypatch, tmp_path)

    main._notify_scan("r1", "sweep_v2", PAYLOAD, [_result()])
    assert len(notifier.calls) == 1

    main._notify_scan("r2", "sweep_v2", PAYLOAD,
                      [_result(reason="TELEGRAM_FAILED: HTTP 500")])
    assert len(notifier.calls) == 2


def test_recovery_clears_the_incident(monkeypatch, tmp_path):
    main = main_module()
    notifier, db = _wire(monkeypatch, tmp_path)

    main._notify_scan("r1", "sweep_v2", PAYLOAD, [_result()])
    assert db.load_scan_error_alert("sweep_v2") is not None

    main._notify_scan("r2", "sweep_v2", {"errors": 0, "checked": 25, "sent": 1}, [])
    assert db.load_scan_error_alert("sweep_v2") is None  # incident closed

    main._notify_scan("r3", "sweep_v2", PAYLOAD, [_result()])
    assert len(notifier.calls) == 3  # fresh incident after recovery


def test_bounded_reminder_after_the_repeat_window(monkeypatch, tmp_path):
    main = main_module()
    notifier, db = _wire(monkeypatch, tmp_path)
    base = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
    stamp = lambda seconds: base + timedelta(seconds=seconds)

    main._notify_scan("r1", "sweep_v2", PAYLOAD, [_result()], at=pd.Timestamp(base))
    assert len(notifier.calls) == 1

    main._notify_scan("r2", "sweep_v2", PAYLOAD, [_result()], at=pd.Timestamp(stamp(60)))
    assert len(notifier.calls) == 1  # inside the window: suppressed

    main._notify_scan("r3", "sweep_v2", PAYLOAD, [_result()],
                      at=pd.Timestamp(stamp(main.SCAN_ERROR_REPEAT_SECONDS)))
    assert len(notifier.calls) == 2  # one bounded reminder after the window

    main._notify_scan("r4", "sweep_v2", PAYLOAD, [_result()],
                      at=pd.Timestamp(stamp(main.SCAN_ERROR_REPEAT_SECONDS + 60)))
    assert len(notifier.calls) == 2  # reminder re-armed the window

    incident = db.load_scan_error_alert("sweep_v2")
    assert incident["first_sent_at"] == base.isoformat()  # original incident kept


# --- Telegram surface: asset-first, no raw exceptions ---------------------


def test_scan_error_bubble_names_asset_reason_and_candle_without_raw_trace():
    diagnostics = {
        "error": "OHLC data contains invalid values (field=close, candle=2026-10-06 19:30:00+05:30, raw_value=nan, kind=nan)",
        "failing_field": "close",
        "failing_candle": "2026-10-06 19:30:00+05:30",
        "value_kind": "nan",
    }
    signal = SimpleNamespace(metadata={"diagnostics": diagnostics})
    result = SimpleNamespace(
        symbol="BTC-USD",
        reason="MARKET_DATA_ERROR: OHLC data contains invalid values (field=close, ...)",
        signal=signal,
    )

    main = main_module()
    entries = main._scan_error_entries([result])
    text = msg_scan_error("sweep_v2", entries)

    assert f"Asset: {LIVE_ASSET_MAP['BTC-USD'].label}" in text
    assert "Reason: invalid OHLC" in text
    assert "Candle: 06 Oct 2026 19:30 IST" in text
    assert "MARKET DATA ERROR" in text
    assert "Paper mode remains active" in text
    # Full technical detail never reaches chat.
    assert "field=close" not in text
    assert "raw_value" not in text


def test_quarantine_never_repairs_values():
    """Sanity: quarantine drops rows, it never rewrites a surviving cell."""
    frame = make_frame()
    bad_ts = frame.index[7]
    frame.loc[bad_ts, "close"] = float("nan")
    before = frame.drop(index=[bad_ts])

    clean, issues = quarantine_invalid_rows(frame)

    assert len(issues) == 1
    pd.testing.assert_frame_equal(clean, before)
