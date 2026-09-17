import numpy as np
import pandas as pd
import pytest

from strategies.engulfing_66_sma import create_strategy


IST = "Asia/Kolkata"


def _frame(*, bullish=True, n=100):
    index = pd.date_range("2026-01-01", periods=n, freq="h", tz=IST)
    close = np.full(n, 95.0)
    close[-12:-2] = np.linspace(95.0, 101.0, 10)
    open_ = close.copy()
    high = close + 0.5
    low = close - 0.5
    if bullish:
        open_[-2], close[-2], high[-2], low[-2] = 101.0, 99.0, 102.0, 98.5
        open_[-1], close[-1], high[-1], low[-1] = 98.0, 101.5, 102.0, 95.8
    else:
        close = np.full(n, 105.0)
        close[-12:-2] = np.linspace(105.0, 99.0, 10)
        open_ = close.copy()
        high = close + 0.5
        low = close - 0.5
        open_[-2], close[-2], high[-2], low[-2] = 99.0, 101.0, 101.5, 98.0
        open_[-1], close[-1], high[-1], low[-1] = 102.0, 98.5, 105.2, 97.5
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close},
        index=index,
    )


def test_manifest_and_data_request_are_consistent():
    strategy = create_strategy()
    assert strategy.manifest.id == "engulfing_66_sma"
    assert strategy.manifest.timeframes == ("1h",)
    assert strategy.manifest.parameters["timeframe"]["options"] == ["1h"]
    assert strategy.manifest.parameters["timeframe"]["editable"] is False
    assert strategy.data_request("RELIANCE") == ("1h", "60d")


def test_bullish_setup_matches_pine_rules():
    strategy = create_strategy()
    frame = _frame(bullish=True)
    signal = strategy.generate_signal(
        "RELIANCE", frame, now=frame.index[-1] + pd.Timedelta(hours=1)
    )
    assert signal.direction == "BUY"
    assert signal.reason == "BULLISH_ENGULFING_AT_66_SMA"
    assert signal.entry == frame.close.iloc[-1]
    assert signal.stop_loss < signal.entry < signal.take_profit


def test_bearish_setup_matches_pine_rules():
    strategy = create_strategy()
    frame = _frame(bullish=False)
    signal = strategy.generate_signal(
        "RELIANCE", frame, now=frame.index[-1] + pd.Timedelta(hours=1)
    )
    assert signal.direction == "SELL"
    assert signal.reason == "BEARISH_ENGULFING_AT_66_SMA"
    assert signal.take_profit < signal.entry < signal.stop_loss


def test_unclosed_last_candle_is_not_used_by_default():
    strategy = create_strategy()
    frame = _frame(bullish=True)
    prepared = strategy.prepare_candles(
        "RELIANCE", frame, now=frame.index[-1] + pd.Timedelta(minutes=30)
    )
    assert len(prepared) == len(frame) - 1
    assert prepared.index[-1] == frame.index[-2]


def test_strict_engulf_requires_full_range_break():
    strategy = create_strategy()
    frame = _frame(bullish=True)
    cfg = strategy.validate_config({"strict_engulf": True})
    assert cfg["strict_engulf"] is True

    # The normal setup is deliberately not a full-range engulfing candle.
    sma, atr = strategy._indicators(frame, cfg)
    approved, reason, _ = strategy._signal_at(
        frame,
        len(frame) - 1,
        cfg=cfg,
        sma=sma,
        atr=atr,
        last_signal_index=-10**9,
    )
    assert approved is False
    assert reason == "NO_APPROVED_SETUP"


def test_invalid_body_range_is_rejected():
    strategy = create_strategy()
    with pytest.raises(ValueError, match="max_body_atr"):
        strategy.validate_config({"min_body_atr": 4.0, "max_body_atr": 3.5})


def test_insufficient_history_is_safe():
    strategy = create_strategy()
    frame = _frame(n=10)
    signal = strategy.generate_signal(
        "RELIANCE", frame, now=frame.index[-1] + pd.Timedelta(hours=1)
    )
    assert signal.direction == "NO_SIGNAL"
    assert signal.reason == "INSUFFICIENT_DATA"
