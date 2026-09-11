"""Yahoo Finance market-data adapter for MULTIBOT2.

Yahoo Finance is the locked market-data source. This provider is deliberately
rate-limit conscious: cache first, deduplicate requests per symbol, back off
exponentially after failures, and return recent valid data whenever possible.
"""
from __future__ import annotations

import json
import logging
import time
import warnings
from datetime import datetime, timezone
from threading import Lock, RLock
from typing import Optional

import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None

from candles import validate_hourly_observations
from config import IST_TIMEZONE

YF_TTL_BY_INTERVAL = {"1m": 45.0, "30m": 120.0, "1h": 300.0, "4h": 300.0, "1d": 600.0}
YAHOO_BACKOFF_SECONDS = 120.0
YAHOO_MAX_BACKOFF_SECONDS = 1800.0
YAHOO_STALE_GRACE_SECONDS = 900.0


class YahooDataError(RuntimeError):
    """Raised when Yahoo data cannot be safely returned."""


logger = logging.getLogger(__name__)


class YahooProvider:
    """Rate-conscious Yahoo Finance provider with resilient caching."""

    def __init__(self, *, session: Optional[object] = None, database=None) -> None:
        self._external_session = session
        self._database = database
        self._cache: dict[tuple[str, str, str, bool], tuple[pd.DataFrame, float]] = {}
        self._last_success: dict[tuple[str, str, str, bool], tuple[pd.DataFrame, float]] = {}
        self._backoff_until: dict[str, float] = {}
        self._failure_count: dict[str, int] = {}
        self._symbol_locks: dict[str, Lock] = {}
        self._lock = RLock()

    def _ttl(self, interval: str) -> float:
        return YF_TTL_BY_INTERVAL.get(interval, 60.0)

    @staticmethod
    def _key_id(key: tuple[str, str, str, bool]) -> str:
        return "|".join((key[0], key[1], key[2], str(int(bool(key[3])))))

    def _symbol_lock(self, symbol: str) -> Lock:
        with self._lock:
            return self._symbol_locks.setdefault(symbol, Lock())

    def _cached(self, key: tuple[str, str, str, bool]) -> Optional[pd.DataFrame]:
        with self._lock:
            item = self._cache.get(key)
            if item is None:
                return None
            frame, cached_at = item
            if time.monotonic() - cached_at < self._ttl(key[2]):
                return frame.copy()
            self._cache.pop(key, None)
        return None

    def _restore_persisted(self, key: tuple[str, str, str, bool]):
        if self._database is None:
            return None
        row = self._database.load_market_data_cache(self._key_id(key))
        if not row:
            logger.info("Yahoo persistent cache miss | symbol=%s key=%s", key[0], self._key_id(key))
            return None
        try:
            updated = pd.Timestamp(row["updated_at"])
            if updated.tzinfo is None:
                updated = updated.tz_localize("UTC")
            age = (datetime.now(timezone.utc) - updated.to_pydatetime().astimezone(timezone.utc)).total_seconds()
            if age > YAHOO_STALE_GRACE_SECONDS:
                return None
            payload = json.loads(row["payload"])
            frame = pd.DataFrame(payload["data"], columns=payload["columns"])
            frame.index = pd.to_datetime(payload["index"], utc=True).tz_convert(IST_TIMEZONE)
            logger.info("Yahoo persistent cache hit | symbol=%s age_seconds=%d", key[0], int(age))
            return frame, age
        except Exception as exc:
            logger.warning("Yahoo persistent cache restore failed | symbol=%s error=%s", key[0], exc)
            return None

    def _compatible_stale(self, key: tuple[str, str, str, bool]) -> Optional[pd.DataFrame]:
        """Return recent data only from the same symbol and interval.

        Period may differ because a larger history request can safely satisfy a
        shorter lookback after the caller receives the frame. Intervals are never
        mixed, preventing accidental 1d/30m/1h strategy input substitution.
        """
        now = time.monotonic()
        candidates: list[tuple[pd.DataFrame, float]] = []
        with self._lock:
            exact = self._last_success.get(key)
            if exact is not None:
                candidates.append(exact)
            for other_key, item in self._last_success.items():
                if other_key == key:
                    continue
                if other_key[0] == key[0] and other_key[2] == key[2] and other_key[3] == key[3]:
                    candidates.append(item)
        fresh = [(frame, saved) for frame, saved in candidates if now - saved <= YAHOO_STALE_GRACE_SECONDS]
        if not fresh:
            return None
        frame, _ = max(fresh, key=lambda item: item[1])
        logger.info(
            "Yahoo stale fallback | symbol=%s requested=%s compatible_cache=true",
            key[0], self._key_id(key),
        )
        return frame.copy()

    def _stale(self, key: tuple[str, str, str, bool]) -> Optional[pd.DataFrame]:
        frame = self._compatible_stale(key)
        if frame is not None:
            return frame
        persisted = self._restore_persisted(key)
        if persisted is not None:
            frame, age = persisted
            with self._lock:
                self._last_success[key] = (frame.copy(), time.monotonic() - age)
            return frame.copy()
        return None

    def _store(self, key: tuple[str, str, str, bool], frame: pd.DataFrame) -> pd.DataFrame:
        now = time.monotonic()
        with self._lock:
            self._cache[key] = (frame.copy(), now)
            self._last_success[key] = (frame.copy(), now)
            self._failure_count.pop(key[0], None)
            self._backoff_until.pop(key[0], None)
        if self._database is not None:
            payload = {
                "columns": list(frame.columns),
                "index": [x.isoformat() for x in frame.index],
                "data": frame.values.tolist(),
            }
            self._database.save_market_data_cache(
                self._key_id(key), key[0], key[1], key[2], key[3],
                json.dumps(payload, separators=(",", ":"), default=str),
                datetime.now(timezone.utc).isoformat(),
            )
            logger.info("Yahoo persistent cache saved | symbol=%s key=%s", key[0], self._key_id(key))
        return frame.copy()

    def _activate_backoff(self, symbol: str, reason: str) -> float:
        with self._lock:
            failures = self._failure_count.get(symbol, 0) + 1
            self._failure_count[symbol] = failures
            delay = min(
                YAHOO_BACKOFF_SECONDS * (2 ** (failures - 1)),
                YAHOO_MAX_BACKOFF_SECONDS,
            )
            self._backoff_until[symbol] = time.monotonic() + delay
        logger.warning(
            "Yahoo backoff activated | symbol=%s failures=%d retry_in=%ds reason=%s",
            symbol, failures, int(delay), reason,
        )
        return delay

    @staticmethod
    def _validate_request(period: str, interval: str) -> None:
        if interval == "1m" and period not in {"1d", "2d", "5d", "7d"}:
            raise YahooDataError(
                f"Yahoo 1m data requires a short lookback (1d/2d/5d/7d); got period={period}"
            )

    def _in_backoff(self, symbol: str) -> float:
        with self._lock:
            return max(0.0, self._backoff_until.get(symbol, 0.0) - time.monotonic())

    def fetch(
        self,
        symbol: str,
        *,
        period: str = "5d",
        interval: str = "1h",
        validate_hourly: bool = True,
    ) -> pd.DataFrame:
        """Fetch Yahoo candles with cache-first, deduplication and backoff."""
        if yf is None:
            raise YahooDataError("yfinance is not installed")

        self._validate_request(period, interval)
        key = (symbol, period, interval, validate_hourly)

        cached = self._cached(key)
        if cached is not None:
            return cached

        symbol_lock = self._symbol_lock(symbol)
        with symbol_lock:
            # Another concurrent caller may have completed while we waited.
            cached = self._cached(key)
            if cached is not None:
                return cached

            persisted = self._restore_persisted(key)
            if persisted is not None:
                frame, age = persisted
                if age <= self._ttl(interval):
                    now = time.monotonic()
                    with self._lock:
                        self._cache[key] = (frame.copy(), now)
                        self._last_success[key] = (frame.copy(), now - age)
                    return frame.copy()

            retry_in = self._in_backoff(symbol)
            if retry_in > 0:
                stale = self._stale(key)
                if stale is not None:
                    logger.info(
                        "Yahoo request skipped during backoff | symbol=%s retry_in=%ds source=cache",
                        symbol, int(retry_in),
                    )
                    return stale
                raise YahooDataError(
                    f"Yahoo Finance is in rate-limit backoff for {symbol}; retry_in={int(retry_in)}s"
                )

            try:
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message="The .*generic.* unit for NumPy timedelta is deprecated.*",
                        category=DeprecationWarning,
                    )
                    frame = yf.download(
                        symbol,
                        period=period,
                        interval=interval,
                        progress=False,
                        auto_adjust=True,
                        threads=False,
                    )
            except Exception as exc:
                message = str(exc)
                rate_limited = (
                    "429" in message
                    or "too many requests" in message.lower()
                    or "rate limit" in message.lower()
                    or "ratelimit" in message.lower()
                )
                self._activate_backoff(symbol, "rate_limit" if rate_limited else "request_error")
                stale = self._stale(key)
                if stale is not None:
                    return stale
                raise YahooDataError(f"Yahoo request failed for {symbol}: {exc}") from exc

            # yfinance may swallow YFRateLimitError and return an empty frame.
            if frame is None or frame.empty:
                self._activate_backoff(symbol, "empty_response_or_rate_limit")
                stale = self._stale(key)
                if stale is not None:
                    return stale
                raise YahooDataError(f"Yahoo returned no data for {symbol}")

            if isinstance(frame.columns, pd.MultiIndex):
                frame.columns = frame.columns.get_level_values(0)

            required = {"Open", "High", "Low", "Close"}
            if not required.issubset(frame.columns):
                raise YahooDataError(f"Yahoo response for {symbol} is missing OHLC columns")

            frame = frame[["Open", "High", "Low", "Close"]].copy()
            frame.columns = [column.lower() for column in frame.columns]

            if not isinstance(frame.index, pd.DatetimeIndex):
                raise YahooDataError("Yahoo response has no DatetimeIndex")
            if frame.index.tz is None:
                frame.index = frame.index.tz_localize("UTC")

            frame.index = frame.index.tz_convert(IST_TIMEZONE)
            frame = frame.sort_index()

            if interval == "1h" and validate_hourly:
                validate_hourly_observations(frame)

            return self._store(key, frame)

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    def in_backoff(self, symbol: str | None = None) -> bool:
        with self._lock:
            now = time.monotonic()
            if symbol is not None:
                return now < self._backoff_until.get(symbol, 0.0)
            return any(now < until for until in self._backoff_until.values())


_default_provider = YahooProvider()


def fetch_yahoo(
    symbol: str,
    *,
    period: str = "5d",
    interval: str = "1h",
    validate_hourly: bool = True,
) -> pd.DataFrame:
    return _default_provider.fetch(
        symbol,
        period=period,
        interval=interval,
        validate_hourly=validate_hourly,
    )
