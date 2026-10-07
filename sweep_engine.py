"""Canonical Sweep V2 candle engine.

Sweep V2 is intentionally narrow: two-sided liquidity sweep followed by
final-close classification. No FVG, pending-sweep or persistence logic lives
here.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
import logging
import pandas as pd

from config import (
    GOLD_SWEEP_HOURS_IST,
    BTC_SWEEP_HOURS_IST,
    IST_TIMEZONE,
    LIVE_ASSET_MAP,
    NSE_INDEX_SWEEP_HOURS_IST,
    SWEEP_MINUTE_GLOBAL,
    SWEEP_MINUTE_NSE,
)
from market_data import MarketDataError, normalize_candles, quarantine_invalid_rows

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SweepResult:
    direction: str
    timeframe: str
    candle_start: pd.Timestamp
    candle_end: pd.Timestamp
    previous: dict
    current: dict
    high_swept: bool
    low_swept: bool
    schedule_warning: str | None = None


def _ist(frame: pd.DataFrame, *, symbol: str | None = None) -> pd.DataFrame:
    """Quarantine invalid provider rows, then apply strict normalization.

    One malformed candle must never poison unrelated valid candles: invalid
    rows are identified and dropped *as rows* (never repaired), then the
    survivors go through the unchanged strict ``normalize_candles``. A sweep
    window that loses a row then fails the exact-completeness checks below, so
    an incomplete candle is rejected rather than manufactured. If every row is
    invalid there is nothing left to trade on and the strict error raises.
    """
    clean, issues = quarantine_invalid_rows(frame)
    if issues:
        dropped_rows = len({str(issue.timestamp) for issue in issues})
        report = {
            "symbol": symbol,
            "raw_rows": int(len(frame)),
            "valid_rows": int(len(clean)),
            "dropped_rows": dropped_rows,
            "invalid_cells": len(issues),
            "issues": [issue.as_dict() for issue in issues[:20]],
            "updated_at": pd.Timestamp.now(tz=IST_TIMEZONE).isoformat(),
        }
        if symbol:
            _record_quarantine(symbol, report)
        logger.warning(
            "Invalid OHLC rows quarantined | symbol=%s | dropped_rows=%d/%d | invalid_cells=%d | first=%s",
            symbol or "?", dropped_rows, len(frame), len(issues), issues[0].describe(),
        )
        if clean.empty:
            error = MarketDataError(
                "OHLC data contains invalid values "
                f"(all {len(frame)} rows are invalid; first: {issues[0].describe()})"
            )
            error.diagnostics = {
                "error": str(error),
                "invalid_cells": len(issues),
                "failing_field": issues[0].field,
                "failing_candle": str(issues[0].timestamp),
                "raw_value": str(issues[0].raw_value),
                "value_kind": issues[0].kind,
            }
            raise error
    elif symbol:
        # Recovery: a clean frame retires the symbol's quarantine report so
        # the diagnostic endpoint only ever shows current bad rows.
        _record_quarantine(symbol, None)
    return normalize_candles(clean)


_QUARANTINE_LOCK = Lock()
_QUARANTINE_REPORTS: dict[str, dict] = {}


def _record_quarantine(symbol: str, report: dict | None) -> None:
    with _QUARANTINE_LOCK:
        if report is None:
            _QUARANTINE_REPORTS.pop(symbol, None)
        else:
            _QUARANTINE_REPORTS[symbol] = report


def last_quarantine(symbol: str) -> dict | None:
    """Latest quarantine report for one symbol (dashboard diagnostics)."""
    with _QUARANTINE_LOCK:
        report = _QUARANTINE_REPORTS.get(str(symbol).strip().upper())
        if report is None:
            return None
        return {**report, "issues": list(report["issues"])}


def _ohlc(group: pd.DataFrame) -> dict:
    group = group.sort_index()
    return {
        "open": float(group.open.iloc[0]),
        "high": float(group.high.max()),
        "low": float(group.low.min()),
        "close": float(group.close.iloc[-1]),
    }


def _day_starts(now: pd.Timestamp, hours: tuple[int, ...], minute: int, lookback_days: int = 3):
    day = now.normalize() - pd.Timedelta(days=lookback_days)
    end_day = now.normalize()
    while day <= end_day:
        for hour in hours:
            yield day + pd.Timedelta(hours=hour, minutes=minute)
        day += pd.Timedelta(days=1)


def _infer_interval(frame: pd.DataFrame) -> pd.Timedelta:
    if len(frame.index) < 2:
        return pd.Timedelta(hours=1)
    diffs = pd.Series(frame.index).diff().dropna()
    if diffs.empty:
        return pd.Timedelta(hours=1)
    return pd.Timedelta(diffs.mode().iloc[0])


def _explicit_bars(
    frame: pd.DataFrame,
    starts,
    duration: pd.Timedelta,
    *,
    provider_interval: pd.Timedelta,
    now: pd.Timestamp,
) -> pd.DataFrame:
    rows = []
    expected_count = int(duration / provider_interval)
    for start in starts:
        end = start + duration
        if end > now:
            continue
        group = frame[(frame.index >= start) & (frame.index < end)].sort_index()
        expected = pd.date_range(
            start=start,
            periods=expected_count,
            freq=provider_interval,
            tz=IST_TIMEZONE,
        )
        if len(group) != expected_count or not group.index.equals(expected):
            continue
        rows.append({
            "timestamp": start,
            **_ohlc(group),
        })
    if not rows:
        return pd.DataFrame(
            columns=["open", "high", "low", "close"],
            index=pd.DatetimeIndex([], tz=IST_TIMEZONE),
        )
    return pd.DataFrame(rows).set_index("timestamp").sort_index()


def build_closed_candles(
    frame: pd.DataFrame,
    symbol: str,
    now: pd.Timestamp | None = None,
    *,
    lookback_days: int = 3,
):
    """Return only completed, schedule-aligned Sweep candles."""
    if frame is None or frame.empty:
        return pd.DataFrame(), "", "No market data"

    symbol = str(symbol).strip().upper()
    if symbol not in LIVE_ASSET_MAP:
        raise ValueError(f"Unknown live asset: {symbol}")

    current = pd.Timestamp.now(tz=IST_TIMEZONE) if now is None else pd.Timestamp(now)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    current = current.tz_convert(IST_TIMEZONE)
    data = _ist(frame, symbol=symbol)

    if symbol in ("^NSEI", "^NSEBANK"):
        interval = _infer_interval(data)
        if interval not in (pd.Timedelta(minutes=1), pd.Timedelta(hours=1)):
            return pd.DataFrame(), "1H", "Unsupported provider interval"
        bars = _explicit_bars(
            data,
            _day_starts(current, NSE_INDEX_SWEEP_HOURS_IST, SWEEP_MINUTE_NSE, lookback_days),
            pd.Timedelta(hours=1),
            provider_interval=interval,
            now=current,
        )
        return bars, "1H", None

    asset = LIVE_ASSET_MAP[symbol]
    if asset.asset_type == "equity":
        starts = _day_starts(current, (9, 13), SWEEP_MINUTE_NSE, lookback_days)
        rows = []
        for start in starts:
            duration = pd.Timedelta(hours=4 if start.hour == 9 else 2)
            end = start + duration
            if end > current:
                continue
            group = data[(data.index >= start) & (data.index < end)].sort_index()
            interval = _infer_interval(data)
            if interval not in (pd.Timedelta(minutes=1), pd.Timedelta(hours=1)):
                continue
            expected_count = int(duration / interval)
            expected = pd.date_range(
                start=start,
                periods=expected_count,
                freq=interval,
                tz=IST_TIMEZONE,
            )
            if len(group) != expected_count or not group.index.equals(expected):
                continue
            rows.append({"timestamp": start, **_ohlc(group)})
        if not rows:
            return pd.DataFrame(), "4H", "No complete NSE session bars"
        return pd.DataFrame(rows).set_index("timestamp").sort_index(), "4H", None

    hours = BTC_SWEEP_HOURS_IST if symbol == "BTC-USD" else GOLD_SWEEP_HOURS_IST
    interval = _infer_interval(data)
    if interval not in (pd.Timedelta(minutes=30), pd.Timedelta(hours=1)):
        return pd.DataFrame(), "4H", "Unsupported provider interval"
    bars = _explicit_bars(
        data,
        _day_starts(current, hours, SWEEP_MINUTE_GLOBAL, lookback_days),
        pd.Timedelta(hours=4),
        provider_interval=interval,
        now=current,
    )
    return bars, "4H", None


def detect_sweep(
    frame: pd.DataFrame,
    symbol: str,
    now: pd.Timestamp | None = None,
) -> SweepResult | None:
    bars, timeframe, warning = build_closed_candles(frame, symbol, now)
    if len(bars) < 2:
        return None

    symbol = str(symbol).strip().upper()
    asset = LIVE_ASSET_MAP[symbol]
    previous = bars.iloc[-2]
    current = bars.iloc[-1]
    start = pd.Timestamp(bars.index[-1])

    if asset.asset_type == "equity":
        duration = pd.Timedelta(hours=4 if start.hour == 9 else 2)
    else:
        duration = pd.Timedelta(hours=1 if timeframe == "1H" else 4)

    end = start + duration
    high_swept = float(current.high) > float(previous.high)
    low_swept = float(current.low) < float(previous.low)

    if not (high_swept and low_swept):
        return None

    close = float(current.close)
    if close > float(previous.high):
        direction = "BULLISH"
    elif close < float(previous.low):
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    expected_minute = (
        SWEEP_MINUTE_NSE
        if asset.market == "NSE"
        else SWEEP_MINUTE_GLOBAL
    )
    expected_hours = (
        set((9, 13))
        if asset.asset_type == "equity"
        else set(NSE_INDEX_SWEEP_HOURS_IST)
        if symbol in ("^NSEI", "^NSEBANK")
        else set(BTC_SWEEP_HOURS_IST if symbol == "BTC-USD" else GOLD_SWEEP_HOURS_IST)
    )
    schedule_warning = warning
    if start.hour not in expected_hours or start.minute != expected_minute:
        schedule_warning = (
            f"Candle start {start:%H:%M IST} is outside configured schedule"
        )

    return SweepResult(
        direction=direction,
        timeframe=timeframe,
        candle_start=start,
        candle_end=end,
        previous={k: float(previous[k]) for k in ("open", "high", "low", "close")},
        current={k: float(current[k]) for k in ("open", "high", "low", "close")},
        high_swept=high_swept,
        low_swept=low_swept,
        schedule_warning=schedule_warning,
    )


__all__ = ["SweepResult", "build_closed_candles", "detect_sweep", "last_quarantine"]
