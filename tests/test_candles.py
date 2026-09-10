import pandas as pd
import pytest

from candles import (
    CandleValidationError,
    candle_close_timestamp,
    candle_display_range,
    candle_open_timestamp,
    closed_candles,
    is_hourly_observation,
)


def test_1015_candle_is_0915_to_1014():
    timestamp = pd.Timestamp("2026-08-31 10:15:00+05:30")

    assert is_hourly_observation(timestamp)
    assert candle_open_timestamp(timestamp) == pd.Timestamp(
        "2026-08-31 09:15:00+05:30"
    )
    assert candle_close_timestamp(timestamp) == timestamp
    assert candle_display_range(timestamp) == "09:15-10:14"


def test_1115_candle_is_1015_to_1114():
    timestamp = pd.Timestamp("2026-08-31 11:15:00+05:30")

    assert candle_display_range(timestamp) == "10:15-11:14"


def test_1215_candle_is_1115_to_1214():
    timestamp = pd.Timestamp("2026-08-31 12:15:00+05:30")

    assert candle_display_range(timestamp) == "11:15-12:14"


def test_1315_candle_is_1215_to_1314():
    timestamp = pd.Timestamp("2026-08-31 13:15:00+05:30")

    assert candle_display_range(timestamp) == "12:15-13:14"


def test_1415_candle_is_1315_to_1414():
    timestamp = pd.Timestamp("2026-08-31 14:15:00+05:30")

    assert candle_display_range(timestamp) == "13:15-14:14"


def test_1515_candle_is_1415_to_1514():
    timestamp = pd.Timestamp("2026-08-31 15:15:00+05:30")

    assert is_hourly_observation(timestamp)
    assert candle_display_range(timestamp) == "14:15-15:14"


def test_1516_is_not_a_canonical_hourly_close():
    timestamp = pd.Timestamp("2026-08-31 15:16:00+05:30")

    assert not is_hourly_observation(timestamp)

    with pytest.raises(CandleValidationError):
        candle_close_timestamp(timestamp)


def test_1015_candle_is_not_closed_before_1015():
    index = pd.DatetimeIndex(["2026-08-31 10:15:00+05:30"])

    frame = pd.DataFrame(
        {
            "open": [100],
            "high": [102],
            "low": [99],
            "close": [101],
        },
        index=index,
    )

    result = closed_candles(
        frame,
        as_of=pd.Timestamp("2026-08-31 10:14:59+05:30"),
    )

    assert result.empty


def test_1015_candle_is_closed_at_1015():
    index = pd.DatetimeIndex(["2026-08-31 10:15:00+05:30"])

    frame = pd.DataFrame(
        {
            "open": [100],
            "high": [102],
            "low": [99],
            "close": [101],
        },
        index=index,
    )

    result = closed_candles(
        frame,
        as_of=pd.Timestamp("2026-08-31 10:15:00+05:30"),
    )

    assert list(result.index) == list(index)
