from types import SimpleNamespace
import pandas as pd
import pytest
from market_sessions import market_session_status

def asset(market, asset_type):
    return SimpleNamespace(market=market, asset_type=asset_type)

def stamp(value):
    return pd.Timestamp(value).to_pydatetime()

@pytest.mark.parametrize("market,kind", [("NSE","equity"),("Gold","commodity"),("Forex","forex")])
def test_sunday_afternoon_ist_blocks_non_crypto_markets(market, kind):
    result = market_session_status(asset(market, kind), stamp("2026-11-22 15:00:00+05:30"))
    assert not result.is_open

def test_bitcoin_is_open_24_7_even_on_sunday():
    assert market_session_status(asset("Crypto","crypto"), stamp("2026-11-22 15:00:00+05:30")).is_open

def test_nse_regular_session_and_boundaries():
    item = asset("NSE","equity")
    assert not market_session_status(item, stamp("2026-11-23 09:14:59+05:30")).is_open
    assert market_session_status(item, stamp("2026-11-23 09:15:00+05:30")).is_open
    assert market_session_status(item, stamp("2026-11-23 15:29:59+05:30")).is_open
    assert not market_session_status(item, stamp("2026-11-23 15:30:00+05:30")).is_open

def test_comex_sunday_reopens_at_1800_new_york():
    item = asset("Gold","commodity")
    assert not market_session_status(item, stamp("2026-11-23 04:29:00+05:30")).is_open
    assert market_session_status(item, stamp("2026-11-23 04:30:00+05:30")).is_open

def test_comex_daily_maintenance_break():
    assert not market_session_status(asset("Gold","commodity"), stamp("2026-11-23 03:00:00+05:30")).is_open

def test_forex_week_opens_sunday_1700_new_york():
    item = asset("Forex","forex")
    assert not market_session_status(item, stamp("2026-11-23 03:29:00+05:30")).is_open
    assert market_session_status(item, stamp("2026-11-23 03:30:00+05:30")).is_open

def test_nse_configured_holiday_is_closed(monkeypatch):
    monkeypatch.setenv("NSE_MARKET_HOLIDAYS", "2026-11-23, 2026-12-25")
    result = market_session_status(asset("NSE","equity"), stamp("2026-11-23 10:00:00+05:30"))
    assert not result.is_open
    assert "holiday" in result.reason

def test_unknown_market_fails_closed():
    result = market_session_status(asset("Other","other"), stamp("2026-11-23 10:00:00+05:30"))
    assert not result.is_open
