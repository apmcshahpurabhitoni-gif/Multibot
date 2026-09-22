import pandas as pd
import pytest

import yahoo_provider


def _fake_download(*args, **kwargs):
    index = pd.DatetimeIndex(
        ["2026-09-22 10:00:00", "2026-09-22 11:00:00"],
        tz="UTC",
    )
    columns = pd.MultiIndex.from_tuples(
        [
            ("Open", "RELIANCE.NS"),
            ("Open", "duplicate"),
            ("High", "RELIANCE.NS"),
            ("Low", "RELIANCE.NS"),
            ("Close", "RELIANCE.NS"),
        ]
    )
    return pd.DataFrame(
        [
            [100.0, 100.0, 101.0, 99.0, 100.5],
            [101.0, 101.0, 102.0, 100.0, 101.5],
        ],
        index=index,
        columns=columns,
    )


def test_yahoo_provider_flattens_duplicate_ohlc_labels(monkeypatch):
    monkeypatch.setattr(yahoo_provider.yf, "download", _fake_download)
    provider = yahoo_provider.YahooProvider()

    frame = provider.fetch(
        "RELIANCE.NS",
        period="1d",
        interval="1m",
        validate_hourly=False,
    )

    assert list(frame.columns) == ["open", "high", "low", "close"]
    assert frame["close"].iloc[-1] == pytest.approx(101.5)
    assert not frame.columns.duplicated().any()


def test_yahoo_provider_rejects_duplicate_timestamps(monkeypatch):
    def fake_download(*args, **kwargs):
        index = pd.DatetimeIndex(
            ["2026-09-22 10:00:00", "2026-09-22 10:00:00"],
            tz="UTC",
        )
        return pd.DataFrame(
            {
                "Open": [100.0, 101.0],
                "High": [101.0, 102.0],
                "Low": [99.0, 100.0],
                "Close": [100.5, 101.5],
            },
            index=index,
        )

    monkeypatch.setattr(yahoo_provider.yf, "download", fake_download)
    provider = yahoo_provider.YahooProvider()

    with pytest.raises(
        yahoo_provider.YahooDataError,
        match="duplicate candle timestamps",
    ):
        provider.fetch(
            "RELIANCE.NS",
            period="1d",
            interval="1m",
            validate_hourly=False,
        )
