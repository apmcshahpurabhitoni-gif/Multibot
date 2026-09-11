"""Yahoo Finance market-data adapter for MULTIBOT2.

Yahoo Finance is the locked market-data source. The adapter deliberately lets
current yfinance manage its native HTTP client; passing a plain requests.Session
to modern yfinance causes the curl_cffi session error seen in the dashboard.
"""
from __future__ import annotations
import json
import time
import warnings
from datetime import datetime, timezone
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
YAHOO_BACKOFF_SECONDS = 120.0
YAHOO_STALE_GRACE_SECONDS = 900.0

class YahooDataError(RuntimeError):
    """Raised when Yahoo data cannot be safely returned."""

class YahooProvider:
    """Rate-conscious Yahoo Finance provider with period-aware caching."""
    def __init__(self, *, session: Optional[object] = None, database=None) -> None:
        self._external_session = session
        self._database = database
        self._cache: dict[tuple[str, str, str, bool], tuple[pd.DataFrame, float]] = {}
        self._backoff_until: dict[str, float] = {}
        self._last_success: dict[tuple[str, str, str, bool], tuple[pd.DataFrame, float]] = {}
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

    @staticmethod
    def _key_id(key): return "|".join((key[0],key[1],key[2],str(int(bool(key[3])))))

    def _restore_persisted(self,key):
        if self._database is None:return None
        row=self._database.load_market_data_cache(self._key_id(key))
        if not row:return None
        try:
            updated=pd.Timestamp(row["updated_at"])
            if updated.tzinfo is None:updated=updated.tz_localize("UTC")
            age=(datetime.now(timezone.utc)-updated.to_pydatetime().astimezone(timezone.utc)).total_seconds()
            if age>YAHOO_STALE_GRACE_SECONDS:return None
            payload=json.loads(row["payload"]); frame=pd.DataFrame(payload["data"],columns=payload["columns"])
            frame.index=pd.to_datetime(payload["index"],utc=True).tz_convert(IST_TIMEZONE)
            return frame,age
        except Exception:return None

    def _stale(self,key):
        with self._lock:item=self._last_success.get(key)
        if item and time.monotonic()-item[1]<=YAHOO_STALE_GRACE_SECONDS:return item[0].copy()
        persisted=self._restore_persisted(key)
        if persisted is not None:
            frame,age=persisted
            with self._lock:self._last_success[key]=(frame.copy(),time.monotonic()-age)
            return frame.copy()
        return None

    def _store(self, key: tuple[str, str, str, bool], frame: pd.DataFrame) -> pd.DataFrame:
        now=time.monotonic()
        with self._lock:self._cache[key]=(frame.copy(),now); self._last_success[key]=(frame.copy(),now)
        if self._database is not None:
            payload={"columns":list(frame.columns),"index":[x.isoformat() for x in frame.index],"data":frame.values.tolist()}
            self._database.save_market_data_cache(self._key_id(key),key[0],key[1],key[2],key[3],json.dumps(payload,separators=(",",":"),default=str),datetime.now(timezone.utc).isoformat())
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
        key = (symbol, period, interval, validate_hourly)
        with self._lock:
            until = self._backoff_until.get(symbol, 0.0)
        if time.monotonic() < until:
            stale=self._stale(key)
            if stale is not None: return stale
            raise YahooDataError(f"Yahoo Finance is in rate-limit backoff for {symbol}")
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="The .*generic.* unit for NumPy timedelta is deprecated.*", category=DeprecationWarning)
                frame = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=True, threads=False)
        except Exception as exc:
            message = str(exc)
            if "429" in message or "too many requests" in message.lower() or "rate" in message.lower():
                with self._lock:
                    self._backoff_until[symbol] = time.monotonic() + YAHOO_BACKOFF_SECONDS
            raise YahooDataError(f"Yahoo request failed for {symbol}: {exc}") from exc
        if frame is None or frame.empty:
            with self._lock:self._backoff_until[symbol] = time.monotonic() + YAHOO_BACKOFF_SECONDS
            stale=self._stale(key)
            if stale is not None: return stale
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

    def in_backoff(self, symbol: str | None = None) -> bool:
        with self._lock:
            now = time.monotonic()
            if symbol is not None: return now < self._backoff_until.get(symbol, 0.0)
            return any(now < until for until in self._backoff_until.values())

_default_provider = YahooProvider()

def fetch_yahoo(symbol: str, *, period: str = "5d", interval: str = "1h", validate_hourly: bool = True) -> pd.DataFrame:
    return _default_provider.fetch(symbol, period=period, interval=interval, validate_hourly=validate_hourly)
