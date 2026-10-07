"""Generic strategy execution: data request -> plugin -> canonical Signal."""
from __future__ import annotations
import pandas as pd
from config import LIVE_ASSET_MAP
from yahoo_provider import YahooProvider
from strategies.base import Strategy, Signal

class StrategyEngine:
    def __init__(self, provider=None): self.provider = provider or YahooProvider()
    def fetch(self, strategy: Strategy, symbol: str, *, period="30d", provenance=None) -> pd.DataFrame:
        asset = LIVE_ASSET_MAP[symbol]
        interval, fetch_period = strategy.data_request(symbol, period=period)
        if provenance is not None:
            provenance.update({"yahoo_symbol": asset.yahoo_symbol, "interval": interval, "period": fetch_period})
        return self.provider.fetch(asset.yahoo_symbol, period=fetch_period, interval=interval, validate_hourly=False, provenance=provenance)
    def evaluate(self, strategy: Strategy, symbol: str, *, now: pd.Timestamp, period="30d", candles=None) -> tuple[Signal,pd.DataFrame]:
        frame = candles if candles is not None else self.fetch(strategy, symbol, period=period)
        prepared = strategy.prepare_candles(symbol, frame, now=now)
        return strategy.generate_signal(symbol, prepared, now=now), prepared
