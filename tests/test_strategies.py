import numpy as np
import pandas as pd

from strategies import discover_strategies


def test_plugins_have_stable_contract():
    registry = discover_strategies()
    assert set(registry.ids()) == {"adaptive_trend", "sweep_v2", "engulfing_66_sma"}
    for strategy in registry.all():
        assert strategy.manifest.id and strategy.manifest.name and strategy.manifest.version
        assert strategy.manifest.assets and strategy.manifest.timeframes


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
