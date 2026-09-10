import pandas as pd

from strategies.base import Signal, Strategy, StrategyManifest


class PreparedStrategy(Strategy):
    manifest = StrategyManifest(
        id="prepared",
        name="Prepared",
        version="1",
        description="test",
        assets=("X",),
        timeframes=("1d",),
        schedule="test",
        parameters={},
    )

    def prepare_candles(self, symbol, candles, *, now):
        return candles.iloc[:-1]

    def generate_signal(self, symbol, candles, *, now):
        return Signal(
            self.manifest.name,
            self.manifest.version,
            symbol,
            "NO_SIGNAL",
            candles.index[-1],
            "1D",
            str(len(candles)),
        )


def test_backtest_uses_same_prepare_contract_as_live():
    index = pd.date_range("2026-01-01", periods=3, freq="D", tz="Asia/Kolkata")
    frame = pd.DataFrame(
        {"open": [1, 2, 3], "high": [1, 2, 3], "low": [1, 2, 3], "close": [1, 2, 3]},
        index=index,
    )
    strategy = PreparedStrategy()
    signal = strategy.backtest_signal("X", frame, now=index[-1])
    assert signal.reason == "2"
