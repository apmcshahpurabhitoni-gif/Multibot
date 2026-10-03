import numpy as np
import pandas as pd

from backtest import backtest_strategy
from config import LIVE_ASSET_MAP
from strategies import discover_strategies


def test_plugins_have_stable_contract():
    """Adding strategies/<id>/ must need no registry edit -- but must be valid.

    The three shipped strategies must always be present. Anything else is a
    drop-in plug-in and is held to the full contract instead of an exact list,
    because pinning an exact list is what made adding a strategy fail six tests
    for a change that was already working.
    """
    from strategies.registry import BUILTIN_STRATEGY_IDS

    registry = discover_strategies()
    assert set(BUILTIN_STRATEGY_IDS) <= set(registry.ids()), (
        f"missing shipped strategies: {sorted(set(BUILTIN_STRATEGY_IDS) - set(registry.ids()))}"
    )
    for strategy in registry.all():
        assert strategy.manifest.id and strategy.manifest.name and strategy.manifest.version
        assert strategy.manifest.assets and strategy.manifest.timeframes
        unknown = [a for a in strategy.manifest.assets if a not in LIVE_ASSET_MAP]
        assert not unknown, (
            f"{strategy.manifest.id} lists assets outside the universe: {unknown}"
        )


def test_adaptive_trend_produces_canonical_signal():
    strategy = discover_strategies().get("adaptive_trend")
    index = pd.date_range("2024-01-01", periods=120, freq="D", tz="Asia/Kolkata")
    close = pd.Series(np.linspace(100, 300, 120), index=index)
    frame = pd.DataFrame(
        {"open": close - 1, "high": close + 2, "low": close - 2, "close": close},
        index=index,
    )
    signal = strategy.generate_signal("BTC-USD", frame, now=index[-1])
    assert signal.strategy == strategy.manifest.name
    assert signal.version == strategy.manifest.version
    assert signal.timeframe == "1D"


def test_all_backtest_capable_plugins_use_common_engine():
    index = pd.date_range("2026-01-01", periods=140, freq="h", tz="Asia/Kolkata")
    close = pd.Series(np.linspace(100, 180, len(index)), index=index)
    frame = pd.DataFrame(
        {"open": close - 1, "high": close + 2, "low": close - 2, "close": close},
        index=index,
    )
    for strategy in discover_strategies().all():
        if "backtest" not in strategy.manifest.capabilities:
            continue
        symbol = strategy.manifest.assets[0]
        if symbol not in {"BTC-USD", "GC=F"}:
            continue
        result = backtest_strategy(strategy, symbol, frame)
        assert result.strategy == strategy.manifest.name
        assert result.strategy_version == strategy.manifest.version
        assert result.symbol == symbol
        assert isinstance(result.trades, tuple)
