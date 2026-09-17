from config import LIVE_SYMBOLS
from strategies import discover_strategies


def test_builtin_strategies_are_discovered():
    registry = discover_strategies()
    assert set(registry.ids()) == {"adaptive_trend", "sweep_v2", "engulfing_66_sma"}


def test_adaptive_trend_only_supports_global_assets():
    registry = discover_strategies()
    strategy = registry.get("adaptive_trend")
    assert set(strategy.manifest.assets) == {"BTC-USD", "GC=F"}


def test_engulfing_66_sma_is_available_for_live_universe():
    registry = discover_strategies()
    strategy = registry.get("engulfing_66_sma")
    assert set(strategy.manifest.assets) == set(LIVE_SYMBOLS)
    assert strategy.manifest.timeframes == ("1h",)
    assert strategy.manifest.schedule == "completed_candle"
    assert "signal" in strategy.manifest.capabilities
    assert "backtest" in strategy.manifest.capabilities
