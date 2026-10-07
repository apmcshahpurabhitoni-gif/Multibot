"""Canonical market-data layer for MULTIBOT2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Iterable

import pandas as pd

from config import (
    IST_TIMEZONE,
    NSE_MARKET_CLOSE,
    NSE_MARKET_OPEN,
    NSE_15_SYMBOLS,
    LIVE_ASSET_MAP,
)
from yahoo_provider import YahooProvider


REQUIRED_OHLC = (
    "open",
    "high",
    "low",
    "close",
)

YAHOO_NSE_SUFFIX = ".NS"


class MarketDataError(ValueError):
    """Raised when market data fails validation."""


@dataclass(frozen=True)
class OHLCIssue:
    """One invalid OHLC cell, captured before any coercion.

    Quarantine and diagnostics both need to know *which* field, *which*
    candle and *what* the provider actually sent — the historic whole-frame
    error ("OHLC data contains invalid values") answered none of that.
    """

    timestamp: object
    field: str
    raw_value: object
    kind: str  # nan | non_numeric | non_positive | invalid_high | invalid_low

    def describe(self) -> str:
        return (
            f"field={self.field}, candle={self.timestamp}, "
            f"raw_value={self.raw_value!r}, kind={self.kind}"
        )

    def as_dict(self) -> dict:
        return {
            "field": self.field,
            "candle": str(self.timestamp),
            "raw_value": str(self.raw_value),
            "kind": self.kind,
        }


def _invalid_ohlc_rows(frame: pd.DataFrame) -> tuple[list[OHLCIssue], list[bool]]:
    """Identify invalid OHLC cells row-by-row. Never mutates values."""

    missing = [
        column
        for column in REQUIRED_OHLC
        if column not in frame.columns
    ]
    if missing:
        raise MarketDataError(
            "Missing required OHLC columns: " + ", ".join(missing)
        )

    issues: list[OHLCIssue] = []
    row_bad = [False] * len(frame.index)
    numeric: dict[str, list] = {}
    raw_values = {column: frame[column].to_numpy() for column in REQUIRED_OHLC}
    index_values = list(frame.index)

    for column in REQUIRED_OHLC:
        series = pd.to_numeric(frame[column], errors="coerce")
        numeric[column] = series.tolist()
        not_numeric = series.isna().to_numpy()
        raw_missing = frame[column].isna().to_numpy()
        not_positive = (series <= 0).to_numpy()
        for position in range(len(index_values)):
            if not_numeric[position]:
                kind = "nan" if raw_missing[position] else "non_numeric"
                issues.append(
                    OHLCIssue(index_values[position], column, raw_values[column][position], kind)
                )
                row_bad[position] = True
            elif not_positive[position]:
                issues.append(
                    OHLCIssue(index_values[position], column, raw_values[column][position], "non_positive")
                )
                row_bad[position] = True

    for position in range(len(index_values)):
        if row_bad[position]:
            continue
        open_value = numeric["open"][position]
        high_value = numeric["high"][position]
        low_value = numeric["low"][position]
        close_value = numeric["close"][position]
        if high_value < max(open_value, close_value):
            issues.append(
                OHLCIssue(index_values[position], "high", raw_values["high"][position], "invalid_high")
            )
            row_bad[position] = True
        elif low_value > min(open_value, close_value):
            issues.append(
                OHLCIssue(index_values[position], "low", raw_values["low"][position], "invalid_low")
            )
            row_bad[position] = True

    return issues, row_bad


def find_invalid_ohlc_rows(frame: pd.DataFrame) -> list[OHLCIssue]:
    """Public row-level inspection used by diagnostics and tests."""

    issues, _ = _invalid_ohlc_rows(frame)
    return issues


def quarantine_invalid_rows(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, list[OHLCIssue]]:
    """Split invalid provider rows out of an otherwise valid frame.

    Contract:
    - invalid rows are identified, never repaired (no zero-fill, no
      forward-fill, no coercion of the surviving cells);
    - valid rows come back untouched so a single malformed candle can never
      poison unrelated candles;
    - strict ``normalize_candles`` still runs on the survivors, so validation
      is not weakened — only scoped.
    """

    issues, row_bad = _invalid_ohlc_rows(frame)
    if not issues:
        return frame, []
    clean = frame[[not bad for bad in row_bad]]
    return clean, issues


@dataclass(frozen=True)
class Candle:
    """One normalized OHLC candle."""

    timestamp: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None

    def __post_init__(self) -> None:
        timestamp = pd.Timestamp(self.timestamp)

        if timestamp.tzinfo is None:
            raise MarketDataError(
                "Candle timestamp must be timezone-aware"
            )

        prices = (
            self.open,
            self.high,
            self.low,
            self.close,
        )

        if any(pd.isna(value) for value in prices):
            raise MarketDataError(
                "Candle OHLC values cannot be NaN"
            )

        if any(float(value) <= 0 for value in prices):
            raise MarketDataError(
                "Candle OHLC values must be positive"
            )

        if self.high < max(
            self.open,
            self.close,
        ):
            raise MarketDataError(
                "Candle high is below open/close"
            )

        if self.low > min(
            self.open,
            self.close,
        ):
            raise MarketDataError(
                "Candle low is above open/close"
            )


def normalize_candles(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    """Normalize provider data into canonical IST OHLC data."""

    if not isinstance(frame, pd.DataFrame):
        raise TypeError(
            "Market data must be a pandas DataFrame"
        )

    missing = [
        column
        for column in REQUIRED_OHLC
        if column not in frame.columns
    ]

    if missing:
        raise MarketDataError(
            "Missing required OHLC columns: "
            + ", ".join(missing)
        )

    result = frame.copy()

    if not isinstance(
        result.index,
        pd.DatetimeIndex,
    ):
        raise MarketDataError(
            "Market-data index must be a DatetimeIndex"
        )

    if result.index.tz is None:
        raise MarketDataError(
            "Market-data timestamps must be timezone-aware"
        )

    result.index = result.index.tz_convert(
        IST_TIMEZONE
    )

    result = result.sort_index()

    if result.index.has_duplicates:
        raise MarketDataError(
            "Market-data timestamps must be unique"
        )

    # Row-level diagnosis first, still strict: any invalid cell raises, but the
    # error now names the field, the candle timestamp and the raw value the
    # provider actually sent (pre-coercion).
    issues, _ = _invalid_ohlc_rows(result)
    if issues:
        first = issues[0]
        detail = (
            first.describe()
            if len(issues) == 1
            else f"{len(issues)} invalid cells; first: {first.describe()}"
        )
        error = MarketDataError(
            "OHLC data contains invalid values (" + detail + ")"
        )
        error.diagnostics = {
            "error": str(error),
            "invalid_cells": len(issues),
            "failing_field": first.field,
            "failing_candle": str(first.timestamp),
            "raw_value": str(first.raw_value),
            "value_kind": first.kind,
        }
        raise error

    for column in REQUIRED_OHLC:
        result[column] = pd.to_numeric(
            result[column],
            errors="coerce",
        )

    # Backstop: unreachable for cells already diagnosed above, retained so the
    # strict OHLC contract keeps its historical guarantees.
    if result[list(REQUIRED_OHLC)].isna().any().any():
        raise MarketDataError(
            "OHLC data contains invalid values"
        )

    if (result[list(REQUIRED_OHLC)] <= 0).any().any():
        raise MarketDataError(
            "OHLC values must be positive"
        )

    invalid_high = (
        result["high"]
        < result[["open", "close"]].max(axis=1)
    )

    invalid_low = (
        result["low"]
        > result[["open", "close"]].min(axis=1)
    )

    if invalid_high.any():
        raise MarketDataError(
            "One or more candles have invalid highs"
        )

    if invalid_low.any():
        raise MarketDataError(
            "One or more candles have invalid lows"
        )

    return result


def candles_from_records(
    records: Iterable[dict],
) -> pd.DataFrame:
    """Convert provider-neutral candle records to canonical data."""

    records = list(records)

    if not records:
        return pd.DataFrame(
            columns=list(REQUIRED_OHLC),
            index=pd.DatetimeIndex(
                [],
                tz=IST_TIMEZONE,
            ),
        )

    frame = pd.DataFrame(records)

    if "timestamp" not in frame.columns:
        raise MarketDataError(
            "Every candle requires a timestamp"
        )

    timestamps = pd.to_datetime(
        frame.pop("timestamp"),
        errors="coerce",
    )

    if timestamps.isna().any():
        raise MarketDataError(
            "One or more candle timestamps are invalid"
        )

    if timestamps.dt.tz is None:
        raise MarketDataError(
            "Candle timestamps must be timezone-aware"
        )

    frame.index = timestamps.dt.tz_convert(
        IST_TIMEZONE
    )

    return normalize_candles(frame)


def validate_symbol(
    symbol: str,
) -> str:
    """Normalize and validate a locked MULTIBOT2 live symbol."""

    if not isinstance(symbol, str):
        raise TypeError(
            "Symbol must be a string"
        )

    symbol = symbol.strip().upper()

    if not symbol:
        raise MarketDataError(
            "Symbol cannot be empty"
        )

    return symbol


def get_required_symbols() -> tuple[str, ...]:
    """Return the frozen 19-asset live universe."""
    return tuple(LIVE_ASSET_MAP)


def yahoo_symbol(symbol: str) -> str:
    """Return the canonical Yahoo Finance ticker for any live asset."""
    symbol = validate_symbol(symbol)
    asset = LIVE_ASSET_MAP.get(symbol)
    if asset is None:
        raise MarketDataError(
            f"Symbol is outside the fixed 19-asset universe: {symbol}"
        )
    return asset.yahoo_symbol


def _session_minute_mask(
    index: pd.DatetimeIndex,
) -> pd.Series:
    """Return timestamps inside the NSE cash session."""

    market_open = time.fromisoformat(NSE_MARKET_OPEN)
    market_close = time.fromisoformat(NSE_MARKET_CLOSE)

    return pd.Series(
        [
            market_open <= timestamp.time() < market_close
            for timestamp in index
        ],
        index=index,
    )


def build_nse_hourly_candles(
    minute_frame: pd.DataFrame,
) -> pd.DataFrame:
    """Build canonical NSE 1H candles from 1-minute Yahoo data.

    Canonical convention:

        09:15-10:14 -> timestamp 10:15
        10:15-11:14 -> timestamp 11:15
        11:15-12:14 -> timestamp 12:15
        12:15-13:14 -> timestamp 13:15
        13:15-14:14 -> timestamp 14:15
        14:15-15:14 -> timestamp 15:15

    The remaining 15:15-15:29 session minutes are not another
    hourly candle.
    """

    frame = normalize_candles(minute_frame)

    if frame.empty:
        return frame

    session_mask = _session_minute_mask(frame.index)
    frame = frame.loc[session_mask.to_numpy()].copy()

    if frame.empty:
        return frame

    frame["session_date"] = frame.index.date
    frame["minute_from_open"] = (
        (
            frame.index.hour * 60
            + frame.index.minute
        )
        - (9 * 60 + 15)
    )

    frame = frame[
        (frame["minute_from_open"] >= 0)
        & (frame["minute_from_open"] < 360)
    ].copy()

    if frame.empty:
        return pd.DataFrame(
            columns=list(REQUIRED_OHLC),
            index=pd.DatetimeIndex(
                [],
                tz=IST_TIMEZONE,
            ),
        )

    frame["bucket"] = (
        frame["minute_from_open"] // 60
    )

    output: list[dict] = []

    for (session_date, bucket), group in frame.groupby(
        ["session_date", "bucket"],
        sort=True,
    ):
        group = group.sort_index()

        if len(group) != 60:
            # Never manufacture an hourly candle from incomplete data.
            continue

        expected = pd.date_range(
            start=group.index[0],
            periods=60,
            freq="1min",
            tz=IST_TIMEZONE,
        )

        if not group.index.equals(expected):
            continue

        open_timestamp = group.index[0]

        close_timestamp = open_timestamp + pd.Timedelta(
            hours=1
        )

        output.append(
            {
                "timestamp": close_timestamp,
                "open": float(group["open"].iloc[0]),
                "high": float(group["high"].max()),
                "low": float(group["low"].min()),
                "close": float(group["close"].iloc[-1]),
            }
        )

    if not output:
        return pd.DataFrame(
            columns=list(REQUIRED_OHLC),
            index=pd.DatetimeIndex(
                [],
                tz=IST_TIMEZONE,
            ),
        )

    result = candles_from_records(output)

    return result


def fetch_nse_hourly(
    symbol: str,
    *,
    provider: YahooProvider | None = None,
    period: str = "5d",
) -> pd.DataFrame:
    """Fetch and construct canonical NSE 1H candles from Yahoo 1m data."""

    yahoo = provider or YahooProvider()

    yf_symbol = yahoo_symbol(symbol)

    minute_data = yahoo.fetch(
        yf_symbol,
        period=period,
        interval="1m",
        validate_hourly=False,
    )

    return build_nse_hourly_candles(
        minute_data
    )




def build_nse_hourly_from_provider_hourly(
    hourly_frame: pd.DataFrame,
) -> pd.DataFrame:
    """Canonicalize Yahoo's native NSE 1H bars when minute history is unavailable.

    Yahoo may label an hourly interval by its opening timestamp (09:15, 10:15,
    ... 14:15). We convert those to the locked close timestamps. If the source
    is already close-stamped, it is retained. Only the six canonical session
    bars are accepted.
    """
    frame = normalize_candles(hourly_frame)
    if frame.empty:
        return frame
    rows = []
    for day in sorted(set(frame.index.date)):
        day_start = pd.Timestamp(day).tz_localize(IST_TIMEZONE)
        g = frame[(frame.index >= day_start + pd.Timedelta(hours=9, minutes=15)) &
                  (frame.index < day_start + pd.Timedelta(hours=15, minutes=30))].sort_index()
        if g.empty:
            continue
        opens = [
            day_start + pd.Timedelta(hours=9, minutes=15),
            day_start + pd.Timedelta(hours=10, minutes=15),
            day_start + pd.Timedelta(hours=11, minutes=15),
            day_start + pd.Timedelta(hours=12, minutes=15),
            day_start + pd.Timedelta(hours=13, minutes=15),
            day_start + pd.Timedelta(hours=14, minutes=15),
        ]
        closes = [x + pd.Timedelta(hours=1) for x in opens]
        idx = list(g.index)
        if idx == opens:
            for start, close_ts in zip(opens, closes):
                row = g.loc[start]
                rows.append({
                    "timestamp": close_ts,
                    "open": float(row.open),
                    "high": float(row.high),
                    "low": float(row.low),
                    "close": float(row.close),
                })
        elif idx == closes:
            for close_ts in closes:
                row = g.loc[close_ts]
                rows.append({
                    "timestamp": close_ts,
                    "open": float(row.open),
                    "high": float(row.high),
                    "low": float(row.low),
                    "close": float(row.close),
                })
    if not rows:
        return pd.DataFrame(columns=list(REQUIRED_OHLC),
                            index=pd.DatetimeIndex([], tz=IST_TIMEZONE))
    return candles_from_records(rows)

def build_global_hourly_candles(
    intraday_frame: pd.DataFrame,
    *,
    anchor_minute: int = 30,
    as_of: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Build complete global 1H candles on the locked :30 boundary.

    Each candle contains two complete 30-minute provider bars and is
    timestamped at its close. Incomplete candles are never returned.
    """
    frame = normalize_candles(intraday_frame)
    if frame.empty:
        return frame
    if not 0 <= int(anchor_minute) <= 59:
        raise MarketDataError("anchor_minute must be between 0 and 59")
    if as_of is not None:
        as_of = pd.Timestamp(as_of)
        if as_of.tzinfo is None:
            raise MarketDataError("as_of must be timezone-aware")
        as_of = as_of.tz_convert(IST_TIMEZONE)

    rows: list[dict] = []
    for day in sorted(set(frame.index.date)):
        day_start = pd.Timestamp(day).tz_localize(IST_TIMEZONE)
        start = day_start + pd.Timedelta(minutes=anchor_minute)
        while start < day_start + pd.Timedelta(days=1):
            end = start + pd.Timedelta(hours=1)
            if as_of is not None and end > as_of:
                break
            group = frame[(frame.index >= start) & (frame.index < end)].sort_index()
            expected = pd.date_range(
                start=start, periods=2, freq="30min", tz=IST_TIMEZONE
            )
            if len(group) == 2 and group.index.equals(expected):
                rows.append({
                    "timestamp": end,
                    "open": float(group.open.iloc[0]),
                    "high": float(group.high.max()),
                    "low": float(group.low.min()),
                    "close": float(group.close.iloc[-1]),
                })
            start += pd.Timedelta(hours=1)

    if not rows:
        return pd.DataFrame(
            columns=list(REQUIRED_OHLC),
            index=pd.DatetimeIndex([], tz=IST_TIMEZONE),
        )
    return candles_from_records(rows)

def candle_age_hours(
    timestamp: pd.Timestamp,
    now: pd.Timestamp,
) -> float:
    """Return candle age in hours."""

    timestamp = pd.Timestamp(timestamp)
    now = pd.Timestamp(now)

    if timestamp.tzinfo is None:
        raise MarketDataError(
            "Candle timestamp must be timezone-aware"
        )

    if now.tzinfo is None:
        raise MarketDataError(
            "Current timestamp must be timezone-aware"
        )

    timestamp = timestamp.tz_convert(
        IST_TIMEZONE
    )

    now = now.tz_convert(
        IST_TIMEZONE
    )

    age = (
        now - timestamp
    ).total_seconds() / 3600

    if age < 0:
        raise MarketDataError(
            "Candle timestamp cannot be in the future"
        )

    return age
