import json

import pandas as pd

import yahoo_provider


class _CacheDatabase:
    def __init__(self):
        self.payload = None

    def save_market_data_cache(self, cache_key, symbol, period, interval, validate_hourly, payload, updated_at):
        self.payload = payload


def test_yahoo_cache_payload_has_json_null_for_missing_values():
    db = _CacheDatabase()
    provider = yahoo_provider.YahooProvider(database=db)
    frame = pd.DataFrame(
        {
            "open": [100.0, float("nan")],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
        },
        index=pd.DatetimeIndex(
            ["2026-09-22 10:00:00+05:30", "2026-09-22 11:00:00+05:30"]
        ),
    )

    provider._store(("RELIANCE.NS", "1d", "1m", False), frame)

    decoded = json.loads(db.payload)
    assert decoded["data"][1][0] is None
    assert "NaN" not in db.payload



def test_turso_cache_read_failure_falls_back_without_aborting_provider():
    class BrokenCacheDatabase:
        def load_market_data_cache(self, cache_key):
            raise RuntimeError("SQLITE_BUSY: stream was idle for too long")

        def save_market_data_cache(self, *args, **kwargs):
            raise RuntimeError("SQLITE_BUSY: stream was idle for too long")

    provider = yahoo_provider.YahooProvider(database=BrokenCacheDatabase())
    key = ("BTC-USD", "1d", "1h", False)
    assert provider._restore_persisted(key) is None


def test_turso_cache_write_failure_keeps_successful_frame_in_memory():
    class BrokenCacheDatabase:
        def save_market_data_cache(self, *args, **kwargs):
            raise RuntimeError("SQLITE_BUSY: stream was idle for too long")

    provider = yahoo_provider.YahooProvider(database=BrokenCacheDatabase())
    frame = pd.DataFrame(
        {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5]},
        index=pd.DatetimeIndex(["2026-09-22 10:00:00+05:30"]),
    )

    stored = provider._store(("BTC-USD", "1d", "1h", False), frame)
    pd.testing.assert_frame_equal(stored, frame)
    pd.testing.assert_frame_equal(provider._cached(("BTC-USD", "1d", "1h", False)), frame)
