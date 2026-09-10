import pandas as pd

from strategies.sweep_v2.strategy import SweepV2Strategy


def test_sweep_uses_prepared_candles_without_second_engine_pass():
    index = pd.date_range("2026-01-01", periods=2, freq="4h", tz="Asia/Kolkata")
    frame = pd.DataFrame(
        {
            "open": [100, 100],
            "high": [110, 112],
            "low": [90, 88],
            "close": [100, 111],
        },
        index=index,
    )
    strategy = SweepV2Strategy()
    signal = strategy.generate_signal("RELIANCE.NS", frame, now=index[-1])
    assert signal.direction == "BUY"
    assert signal.timeframe == "4H"
