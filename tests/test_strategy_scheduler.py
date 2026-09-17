import pytest

from strategy_scheduler import StrategyScheduler
from strategies.base import StrategyManifest


class StubStrategy:
    def __init__(self, schedule, timeframes):
        self.manifest = StrategyManifest(
            id="stub",
            name="Stub",
            version="1.0.0",
            description="",
            assets=("BTC-USD",),
            timeframes=timeframes,
            schedule=schedule,
            parameters={},
        )


def test_completed_candle_uses_declared_timeframe():
    scheduler = StrategyScheduler()
    assert scheduler.interval_seconds(StubStrategy("completed_candle", ("1h",))) == 3600
    assert scheduler.interval_seconds(StubStrategy("completed_candle", ("1d",))) == 86400


def test_completed_candle_requires_one_timeframe():
    with pytest.raises(ValueError, match="exactly one timeframe"):
        StrategyScheduler().interval_seconds(
            StubStrategy("completed_candle", ("1h", "4h"))
        )


def test_completed_candle_rejects_invalid_timeframe():
    with pytest.raises(ValueError, match="Unsupported strategy timeframe"):
        StrategyScheduler().interval_seconds(StubStrategy("completed_candle", ("bad",)))
