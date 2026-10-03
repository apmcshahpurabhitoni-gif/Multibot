from config import LIVE_SYMBOLS
from strategies import discover_strategies


def test_builtin_strategies_are_discovered():
    """Shipped strategies must always be registered; extra plug-ins are fine."""
    from strategies.registry import BUILTIN_STRATEGY_IDS

    registry = discover_strategies()
    assert set(BUILTIN_STRATEGY_IDS) <= set(registry.ids()), (
        f"missing shipped strategies: {sorted(set(BUILTIN_STRATEGY_IDS) - set(registry.ids()))}"
    )


def test_a_dropped_in_strategy_is_registered_without_any_registry_edit():
    """The plug-in promise: two files in strategies/<id>/ is the whole step."""
    import importlib
    import shutil
    import sys
    import textwrap
    from pathlib import Path

    strategies_dir = Path(__file__).resolve().parents[1] / "strategies"
    probe = strategies_dir / "zz_dropin_probe"
    probe.mkdir()
    try:
        (probe / "__init__.py").write_text(
            "from .strategy import Probe, create_strategy\n"
            "__all__ = [\"Probe\", \"create_strategy\"]\n", encoding="utf-8")
        (probe / "strategy.py").write_text(textwrap.dedent('''
            from strategies.base import Signal, Strategy, StrategyManifest


            class Probe(Strategy):
                manifest = StrategyManifest(
                    "zz_probe", "ZZ Probe", "1.0.0", "Drop-in probe.",
                    ("RELIANCE",), ("1D",), "probe", {})

                def generate_signal(self, symbol, candles, *, now):
                    return Signal(self.manifest.name, self.manifest.version, symbol,
                                  "NO_SIGNAL", now, "1D", "PROBE")


            def create_strategy():
                return Probe()
        ''').strip() + "\n", encoding="utf-8")

        for name in [m for m in list(sys.modules) if m.startswith("strategies.zz_dropin_probe")]:
            del sys.modules[name]
        importlib.invalidate_caches()

        registry = discover_strategies()
        assert "zz_probe" in registry.ids(), (
            "a two-file strategies/<id>/ package was not discovered")
    finally:
        shutil.rmtree(probe, ignore_errors=True)
        for name in [m for m in list(sys.modules) if m.startswith("strategies.zz_dropin_probe")]:
            del sys.modules[name]
        importlib.invalidate_caches()


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
