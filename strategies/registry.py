"""Automatic strategy discovery and registry."""
from __future__ import annotations
import importlib, pkgutil
from typing import Iterable
from .base import Strategy

#: The strategies this repository ships. Dropping a new package into
#: strategies/ registers it automatically -- that is the whole plug-in contract
#: -- but it is not part of the shipped manifest, the docs inventory or the
#: rebuild kit. Guards that check those therefore read this, not "whatever is
#: discovered", so a local experiment cannot fail the build and a shipped one
#: cannot be silently dropped from the docs.
BUILTIN_STRATEGY_IDS: tuple[str, ...] = (
    "adaptive_trend",
    "engulfing_66_sma",
    "sweep_v2",
)

class StrategyRegistry:
    def __init__(self): self._strategies: dict[str, Strategy] = {}
    def register(self, strategy: Strategy) -> None:
        sid = strategy.manifest.id
        if sid in self._strategies: raise ValueError(f"Duplicate strategy id: {sid}")
        self._strategies[sid] = strategy
    def get(self, strategy_id: str) -> Strategy: return self._strategies[strategy_id]
    def all(self) -> tuple[Strategy, ...]: return tuple(self._strategies.values())
    def for_symbol(self, symbol: str) -> tuple[Strategy, ...]:
        return tuple(s for s in self._strategies.values() if symbol in s.manifest.assets)
    def ids(self) -> tuple[str, ...]: return tuple(self._strategies)

def discover_strategies() -> StrategyRegistry:
    registry = StrategyRegistry()
    import strategies
    for mod in pkgutil.iter_modules(strategies.__path__):
        if mod.name.startswith("_") or mod.name in {"base", "registry"}: continue
        package = importlib.import_module(f"strategies.{mod.name}")
        factory = getattr(package, "create_strategy", None)
        if factory is not None: registry.register(factory())
    return registry
