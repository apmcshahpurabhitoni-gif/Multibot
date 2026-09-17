import pytest

from strategy_scheduler import StrategyScheduler
from strategies.base import Strategy, StrategyManifest


class OneHourStrategy(Strategy):
    manifest = StrategyManifest(
        id="test_1h_completed",
        name="Test 1H Completed",
        version="1",
        description="test",
        assets=("X",),
        timeframes=("1h",),
        schedule="completed_candle",
        parameters={},
    )

    def generate_signal(self, symbol, candles, *, now):
        return None


class OneDayStrategy(Strategy):
    manifest = StrategyManifest(
        id="test_1d_completed",
        name="Test 1D Completed",
        version="1",
        description="test",
        assets=("X",),
        timeframes=("1D",),
        schedule="completed_candle",
        parameters={},
    )

    def generate_signal(self, symbol, candles, *, now):
        return None


def test_completed_candle_uses_declared_timeframe():
    scheduler = StrategyScheduler()
    assert scheduler.interval_seconds(OneHourStrategy()) == 3600
    assert scheduler.interval_seconds(OneDayStrategy()) == 86400


def test_completed_candle_requires_timeframe():
    class NoTimeframeStrategy(OneHourStrategy):
        manifest = StrategyManifest(
            id="test_no_timeframe",
            name="Test No Timeframe",
            version="1",
            description="test",
            assets=("X",),
            timeframes=(),
            schedule="completed_candle",
            parameters={},
        )

    with pytest.raises(ValueError, match="requires a timeframe"):
        StrategyScheduler().interval_seconds(NoTimeframeStrategy())
