import pandas as pd
import pytest

from market_data import (
    MarketDataError,
    build_nse_hourly_candles,
    candles_from_records,
    candle_age_hours,
    build_global_hourly_candles,
    build_nse_hourly_from_provider_hourly,
    normalize_candles,
    validate_symbol,
    yahoo_symbol,
)


def make_candles():
    index = pd.DatetimeIndex(
        [
            "2026-08-31 10:15:00+05:30",
            "2026-08-31 11:15:00+05:30",
        ]
    )

    return pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [103.0, 104.0],
            "low": [99.0, 100.0],
            "close": [102.0, 103.0],
        },
        index=index,
    )


def make_one_hour_of_minutes(
    start="2026-08-31 09:15:00+05:30",
):
    index = pd.date_range(
        start=start,
        periods=60,
        freq="1min",
    )

    values = range(100, 160)

    return pd.DataFrame(
        {
            "open": [float(value) for value in values],
            "high": [float(value + 1) for value in values],
            "low": [float(value - 1) for value in values],
            "close": [float(value + 0.5) for value in values],
        },
        index=index,
    )


def test_normalize_candles_accepts_valid_ohlc():
    result = normalize_candles(
        make_candles()
    )

    assert list(result.columns) == [
        "open",
        "high",
        "low",
        "close",
    ]

    assert len(result) == 2


def test_normalize_candles_sorts_timestamps():
    frame = make_candles().iloc[::-1]

    result = normalize_candles(frame)

    assert result.index.is_monotonic_increasing


def test_duplicate_timestamps_are_rejected():
    frame = make_candles()

    frame = pd.concat(
        [frame, frame.iloc[[0]]]
    )

    with pytest.raises(MarketDataError):
        normalize_candles(frame)


def test_naive_timestamps_are_rejected():
    frame = make_candles()

    frame.index = pd.DatetimeIndex(
        [
            "2026-08-31 10:15:00",
            "2026-08-31 11:15:00",
        ]
    )

    with pytest.raises(MarketDataError):
        normalize_candles(frame)


def test_missing_ohlc_column_is_rejected():
    frame = make_candles().drop(
        columns=["close"]
    )

    with pytest.raises(MarketDataError):
        normalize_candles(frame)


def test_nan_ohlc_is_rejected():
    frame = make_candles()

    frame.loc[
        frame.index[0],
        "close",
    ] = float("nan")

    with pytest.raises(MarketDataError):
        normalize_candles(frame)


def test_non_positive_prices_are_rejected():
    frame = make_candles()

    frame.loc[
        frame.index[0],
        "low",
    ] = 0

    with pytest.raises(MarketDataError):
        normalize_candles(frame)


def test_invalid_high_is_rejected():
    frame = make_candles()

    frame.loc[
        frame.index[0],
        "high",
    ] = 98

    with pytest.raises(MarketDataError):
        normalize_candles(frame)


def test_invalid_low_is_rejected():
    frame = make_candles()

    frame.loc[
        frame.index[0],
        "low",
    ] = 104

    with pytest.raises(MarketDataError):
        normalize_candles(frame)


def test_candles_from_records():
    records = [
        {
            "timestamp":
                "2026-08-31T10:15:00+05:30",
            "open": 100,
            "high": 103,
            "low": 99,
            "close": 102,
        },
        {
            "timestamp":
                "2026-08-31T11:15:00+05:30",
            "open": 102,
            "high": 105,
            "low": 101,
            "close": 104,
        },
    ]

    result = candles_from_records(records)

    assert len(result) == 2
    assert result.index.tz is not None


def test_empty_records_return_empty_ist_frame():
    result = candles_from_records([])

    assert result.empty
    assert result.index.tz is not None


def test_invalid_timestamp_is_rejected():
    records = [
        {
            "timestamp": "not-a-date",
            "open": 100,
            "high": 103,
            "low": 99,
            "close": 102,
        }
    ]

    with pytest.raises(MarketDataError):
        candles_from_records(records)


def test_validate_symbol_normalizes_symbol():
    assert (
        validate_symbol(" reliance ")
        == "RELIANCE"
    )


def test_empty_symbol_is_rejected():
    with pytest.raises(MarketDataError):
        validate_symbol("")


def test_yahoo_symbol_uses_nse_suffix():
    assert yahoo_symbol("RELIANCE") == "RELIANCE.NS"


def test_symbol_outside_fixed_universe_is_rejected():
    with pytest.raises(MarketDataError):
        yahoo_symbol("AAPL")


def test_global_live_symbols_use_their_canonical_yahoo_ticker():
    assert yahoo_symbol("BTC-USD") == "BTC-USD"
    assert yahoo_symbol("GC=F") == "GC=F"
    assert yahoo_symbol("^NSEI") == "^NSEI"


def test_first_hour_is_0915_to_1014():
    frame = make_one_hour_of_minutes()

    result = build_nse_hourly_candles(frame)

    assert len(result) == 1

    assert result.index[0] == pd.Timestamp(
        "2026-08-31 10:15:00+05:30"
    )


def test_first_hour_uses_first_open_and_last_close():
    frame = make_one_hour_of_minutes()

    result = build_nse_hourly_candles(frame)

    assert result.iloc[0]["open"] == 100.0
    assert result.iloc[0]["close"] == 159.5
    assert result.iloc[0]["high"] == 160.0
    assert result.iloc[0]["low"] == 99.0


def test_two_hour_candles_have_1015_boundary():
    first = make_one_hour_of_minutes(
        "2026-08-31 09:15:00+05:30"
    )

    second = make_one_hour_of_minutes(
        "2026-08-31 10:15:00+05:30"
    )

    second = second.copy()

    result = build_nse_hourly_candles(
        pd.concat([first, second])
    )

    assert len(result) == 2

    assert list(result.index) == [
        pd.Timestamp(
            "2026-08-31 10:15:00+05:30"
        ),
        pd.Timestamp(
            "2026-08-31 11:15:00+05:30"
        ),
    ]


def test_incomplete_hour_is_not_manufactured():
    frame = make_one_hour_of_minutes()

    frame = frame.iloc[:-1]

    result = build_nse_hourly_candles(frame)

    assert result.empty


def test_missing_minute_is_not_manufactured():
    frame = make_one_hour_of_minutes()

    frame = frame.drop(
        frame.index[30]
    )

    result = build_nse_hourly_candles(frame)

    assert result.empty


def test_1515_to_1529_does_not_create_extra_hour():
    frame = make_one_hour_of_minutes(
        "2026-08-31 14:15:00+05:30"
    )

    extra_index = pd.date_range(
        "2026-08-31 15:15:00+05:30",
        periods=15,
        freq="1min",
    )

    extra = pd.DataFrame(
        {
            "open": [200.0] * 15,
            "high": [201.0] * 15,
            "low": [199.0] * 15,
            "close": [200.5] * 15,
        },
        index=extra_index,
    )

    result = build_nse_hourly_candles(
        pd.concat([frame, extra])
    )

    assert len(result) == 1

    assert result.index[0] == pd.Timestamp(
        "2026-08-31 15:15:00+05:30"
    )


def test_candle_age_hours():
    timestamp = pd.Timestamp(
        "2026-08-31 10:15:00+05:30"
    )

    now = pd.Timestamp(
        "2026-08-31 11:15:00+05:30"
    )

    assert candle_age_hours(
        timestamp,
        now,
    ) == 1.0


def test_future_candle_is_rejected():
    timestamp = pd.Timestamp(
        "2026-08-31 12:15:00+05:30"
    )

    now = pd.Timestamp(
        "2026-08-31 11:15:00+05:30"
    )

    with pytest.raises(MarketDataError):
        candle_age_hours(
            timestamp,
            now,
        )


def test_global_30m_bars_build_close_stamped_1h():
    idx = pd.date_range("2026-09-01 09:30", periods=4, freq="30min", tz="Asia/Kolkata")
    close = pd.Series([100, 101, 102, 103], index=idx, dtype=float)
    raw = pd.DataFrame({"open":close-.5,"high":close+1,"low":close-1,"close":close}, index=idx)
    out = build_global_hourly_candles(raw, as_of=pd.Timestamp("2026-09-01 11:00+05:30"))
    assert list(out.index) == [
        pd.Timestamp("2026-09-01 10:30+05:30"),
        pd.Timestamp("2026-09-01 11:30+05:30"),
    ][0:1]
    assert out.iloc[0].close == 101.0


def test_global_incomplete_30m_hour_is_dropped():
    idx = pd.date_range("2026-09-01 09:30", periods=3, freq="30min", tz="Asia/Kolkata")
    close = pd.Series([100,101,102], index=idx, dtype=float)
    raw = pd.DataFrame({"open":close-.5,"high":close+1,"low":close-1,"close":close}, index=idx)
    out = build_global_hourly_candles(raw, as_of=pd.Timestamp("2026-09-01 11:30+05:30"))
    assert len(out) == 1


def test_nse_provider_hourly_is_converted_to_canonical_close_times():
    idx = pd.date_range("2026-09-01 09:15", periods=6, freq="1h", tz="Asia/Kolkata")
    close = pd.Series(range(100,106), index=idx, dtype=float)
    raw = pd.DataFrame({"open":close-.5,"high":close+1,"low":close-1,"close":close}, index=idx)
    out = build_nse_hourly_from_provider_hourly(raw)
    assert list(out.index) == list(pd.date_range("2026-09-01 10:15", periods=6, freq="1h", tz="Asia/Kolkata"))
