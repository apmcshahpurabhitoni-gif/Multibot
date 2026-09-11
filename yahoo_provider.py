"""Yahoo Finance market-data adapter for MULTIBOT2.

Yahoo Finance is the locked market-data source. The adapter deliberately lets
current yfinance manage its native HTTP client; passing a plain requests.Session
to modern yfinance causes the curl_cffi session error seen in the dashboard.
"""
from __future__ import annotations
import time
import warnings
from threading import RLock
from typing import Optional
import pandas as pd
try:
    import yfinance as yf
except ImportError:  # test/import environments may not have optional runtime deps installed
    yf = None
from candles import validate_hourly_observations
from config import IST_TIMEZONE

YF_TTL_BY_INTERVAL = {"1m": 45.0, "1h": 300.0, "4h": 300.0, "1d": 600.0}
YAHOO_BACKOFF_SECONDS = 600.0

class YahooDataError(RuntimeError):
    """Raised when Yahoo data cannot be safely returned."""

class YahooProvider:
    """Rate-conscious Yahoo Finance provider with period-aware caching."""
    def __init__(self, *, session: Optional[object] = None) -> None:
        self._external_session = session
        self._cache: dict[tuple[str, str, str, bool], tuple[pd.DataFrame, float]] = {}
        self._backoff_until = 0.0
        self._lock = RLock()

    def _ttl(self, interval: str) -> float:
        return YF_TTL_BY_INTERVAL.get(interval, 60.0)

    def _cached(self, symbol: str, period: str, interval: str, validate_hourly: bool) -> Optional[pd.DataFrame]:
        key = (symbol, period, interval, validate_hourly)
        with self._lock:
            item = self._cache.get(key)
            if item is None:
                return None
            frame, cached_at = item
            if time.monotonic() - cached_at < self._ttl(interval):
                return frame.copy()
            self._cache.pop(key, None)
            return None

    def _store(self, key: tuple[str, str, str, bool], frame: pd.DataFrame) -> pd.DataFrame:
        with self._lock:
            self._cache[key] = (frame.copy(), time.monotonic())
        return frame.copy()

    @staticmethod
    def _validate_request(period: str, interval: str) -> None:
        """Reject Yahoo combinations known to be invalid before making a request."""
        if interval == "1m" and period not in {"1d", "2d", "5d", "7d"}:
            raise YahooDataError(
                f"Yahoo 1m data requires a short lookback (1d/2d/5d/7d); got period={period}"
            )

    def fetch(self, symbol: str, *, period: str = "5d", interval: str = "1h", validate_hourly: bool = True) -> pd.DataFrame:
        """Fetch Yahoo candles without the incompatible requests.Session argument."""
        self._validate_request(period, interval)
        cached = self._cached(symbol, period, interval, validate_hourly)
        if cached is not None:
            return cached
        with self._lock:
            if time.monotonic() < self._backoff_until:
                raise YahooDataError("Yahoo Finance is in rate-limit backoff")
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="The .*generic.* unit for NumPy timedelta is deprecated.*", category=DeprecationWarning)
                frame = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=True, threads=False)
        except Exception as exc:
            message = str(exc)
            if "429" in message or "too many requests" in message.lower() or "rate" in message.lower():
                with self._lock:
                    self._backoff_until = time.monotonic() + YAHOO_BACKOFF_SECONDS
            raise YahooDataError(f"Yahoo request failed for {symbol}: {exc}") from exc
        if frame is None or frame.empty:
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
        return self._store((symbol, period, interval, validate_hourly), frame)

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    def in_backoff(self) -> bool:
        with self._lock:
            return time.monotonic() < self._backoff_until

_default_provider = YahooProvider()

def fetch_yahoo(symbol: str, *, period: str = "5d", interval: str = "1h", validate_hourly: bool = True) -> pd.DataFrame:
    return _default_provider.fetch(symbol, period=period, interval=interval, validate_hourly=validate_hourly)
