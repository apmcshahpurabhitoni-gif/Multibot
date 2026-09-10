"""Adaptive Trend Momentum strategy.

The strategy is intentionally self-contained. Operational lifecycle rules are
owned by the core engine; this module only computes the trading decision and
its initial exit levels.
"""
from __future__ import annotations
import pandas as pd
from strategies.base import Signal, Strategy, StrategyManifest

IST = "Asia/Kolkata"

def _atr(frame: pd.DataFrame, period: int) -> pd.Series:
    prev = frame["close"].shift(1)
    tr = pd.concat([(frame.high-frame.low), (frame.high-prev).abs(), (frame.low-prev).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()

class AdaptiveTrendMomentum(Strategy):
    manifest = StrategyManifest(
        id="adaptive_trend",
        name="Adaptive Trend Momentum",
        version="1.0.0",
        description="Daily trend, momentum and Donchian-breakout strategy with ATR volatility filtering.",
        assets=("BTC-USD", "GC=F"),
        timeframes=("1d",),
        schedule="daily_completed_candle",
        account="macro",
        capabilities=("signal", "fixed_sl", "fixed_tp", "trailing_stop", "backtest"),
        parameters={
            "timeframe": {"type":"select", "options":["1d"], "default":"1d", "editable":False},
            "ema_fast": {"type":"integer", "min":5, "max":100, "default":20},
            "ema_slow": {"type":"integer", "min":10, "max":200, "default":50},
            "momentum_period": {"type":"integer", "min":5, "max":100, "default":40},
            "donchian_period": {"type":"integer", "min":5, "max":100, "default":20},
            "atr_period": {"type":"integer", "min":5, "max":50, "default":14},
            "volatility_min_pct": {"type":"number", "min":0.0, "max":20.0, "default":0.5},
            "stop_atr": {"type":"number", "min":0.25, "max":10.0, "default":1.5},
            "reward_risk": {"type":"number", "min":0.5, "max":10.0, "default":2.0},
            "trailing_stop": {"type":"boolean", "default":True},
            "trailing_atr": {"type":"number", "min":0.25, "max":10.0, "default":1.5},
        },
    )
    def data_request(self, symbol, *, period="30d"):
        return "1d", "2y"

    def prepare_candles(self, symbol, candles, *, now):
        f = candles.copy().sort_index()
        if f.empty:
            return f
        if not isinstance(f.index, pd.DatetimeIndex):
            raise ValueError("Adaptive Trend candles require a DatetimeIndex")
        if f.index.tz is None:
            raise ValueError("Adaptive Trend candle timestamps must be timezone-aware")
        current = pd.Timestamp(now)
        if current.tzinfo is None:
            raise ValueError("Runtime timestamp must be timezone-aware")
        current = current.tz_convert(IST)
        last_ts = f.index[-1].tz_convert(IST)
        # Daily bars are labelled by their session date. A bar from today's
        # session is not completed yet and must never drive a live signal.
        if last_ts.date() >= current.date():
            f = f.iloc[:-1]
        return f

    def generate_signal(self, symbol, candles, *, now):
        cfg = self.validate_config({})
        f = candles.copy().sort_index()
        if len(f) < max(cfg["ema_slow"], cfg["momentum_period"], cfg["donchian_period"] + 1, cfg["atr_period"]) + 2:
            ts = f.index[-1] if len(f) else now
            return Signal(self.manifest.name,self.manifest.version,symbol,"NO_SIGNAL",ts,"1D","INSUFFICIENT_DATA")
        ts = f.index[-1]
        close = f.close.astype(float)
        fast = close.ewm(span=cfg["ema_fast"], adjust=False).mean()
        slow = close.ewm(span=cfg["ema_slow"], adjust=False).mean()
        momentum = close / close.shift(cfg["momentum_period"]) - 1
        upper = f.high.shift(1).rolling(cfg["donchian_period"]).max()
        lower = f.low.shift(1).rolling(cfg["donchian_period"]).min()
        atr = _atr(f, cfg["atr_period"])
        vol_pct = atr / close * 100
        e, a = float(close.iloc[-1]), float(atr.iloc[-1])
        if pd.isna(fast.iloc[-1]) or pd.isna(slow.iloc[-1]) or pd.isna(momentum.iloc[-1]) or pd.isna(upper.iloc[-1]) or pd.isna(lower.iloc[-1]) or pd.isna(a):
            return Signal(self.manifest.name,self.manifest.version,symbol,"NO_SIGNAL",ts,"1D","INDICATOR_DATA_UNAVAILABLE")
        if float(vol_pct.iloc[-1]) < cfg["volatility_min_pct"]:
            return Signal(self.manifest.name,self.manifest.version,symbol,"NO_SIGNAL",ts,"1D","VOLATILITY_FILTER")
        long_ok = fast.iloc[-1] > slow.iloc[-1] and momentum.iloc[-1] > 0 and e > upper.iloc[-1]
        short_ok = fast.iloc[-1] < slow.iloc[-1] and momentum.iloc[-1] < 0 and e < lower.iloc[-1]
        if not (long_ok or short_ok):
            return Signal(self.manifest.name,self.manifest.version,symbol,"NO_SIGNAL",ts,"1D","NO_APPROVED_ALIGNMENT",e)
        distance = a * cfg["stop_atr"]
        if long_ok:
            sl, tp, direction = e-distance, e+distance*cfg["reward_risk"], "BUY"
            reason = "EMA_MOMENTUM_DONCHIAN_LONG"
        else:
            sl, tp, direction = e+distance, e-distance*cfg["reward_risk"], "SELL"
            reason = "EMA_MOMENTUM_DONCHIAN_SHORT"
        return Signal(self.manifest.name,self.manifest.version,symbol,direction,ts,"1D",reason,e,sl,tp,{"atr":a,"momentum":float(momentum.iloc[-1]),"volatility_pct":float(vol_pct.iloc[-1])})
    def trailing_policy(self, config=None):
        cfg = self.validate_config(config or {})
        return {"enabled": bool(cfg["trailing_stop"]), "type":"atr", "atr_multiple":float(cfg["trailing_atr"])}

def create_strategy(): return AdaptiveTrendMomentum()
