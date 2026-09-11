"""Sweep V2 strategy: canonical classification, no lifecycle ownership."""
from __future__ import annotations
import pandas as pd
from config import LIVE_ASSET_MAP,LIVE_SYMBOLS
from strategies.base import Signal,Strategy,StrategyManifest
from sweep_engine import build_closed_candles

class SweepV2Strategy(Strategy):
    manifest=StrategyManifest(id="sweep_v2",name="Sweep V2",version="2.1.0",description="Strict two-sided sweep followed by final-close classification with durable diagnostics.",assets=LIVE_SYMBOLS,timeframes=("1h","4h"),schedule="canonical_sweep_schedule",account="sweep_4h",capabilities=("signal","strategy_sl","risk_reward_tp","scheduled_scan","backtest"),parameters={"timeframe":{"type":"strategy","default":"asset_schedule"},"risk_reward":{"type":"number","default":2.0,"min":1.0,"max":10.0,"editable":False}})

    def data_request(self,symbol,*,period="30d"):
        asset=LIVE_ASSET_MAP[symbol]; return ("1h" if asset.market=="NSE" else "30m"),period

    def prepare_candles(self,symbol,candles,*,now):
        closed,_,_=build_closed_candles(candles,symbol,now=now,lookback_days=7); return closed

    def generate_signal(self,symbol,candles,*,now):
        asset=LIVE_ASSET_MAP[symbol]; timeframe=asset.sweep_timeframe; timestamp=candles.index[-1] if len(candles) else pd.Timestamp(now)
        if len(candles)<2:
            return Signal(self.manifest.name,self.manifest.version,symbol,"NO_SIGNAL",timestamp,timeframe,"INSUFFICIENT_CANDLES",metadata={"candle_count":len(candles)})
        previous,current=candles.iloc[-2],candles.iloc[-1]
        high_swept=float(current["high"])>float(previous["high"]); low_swept=float(current["low"])<float(previous["low"])
        diagnostics={"candle_start":pd.Timestamp(timestamp).isoformat(),"previous":{k:float(previous[k]) for k in ("open","high","low","close")},"current":{k:float(current[k]) for k in ("open","high","low","close")},"high_swept":high_swept,"low_swept":low_swept}
        if not (high_swept and low_swept):
            reason="ONE_SIDED_SWEEP" if high_swept or low_swept else "NO_SWEEP"
            diagnostics["classification"]="NO_SIGNAL"
            return Signal(self.manifest.name,self.manifest.version,symbol,"NO_SIGNAL",timestamp,timeframe,reason,metadata=diagnostics)
        entry=float(current["close"])
        if entry>float(previous["high"]):
            direction,reason,stop_loss="BUY","BULLISH",float(current["low"]); take_profit=entry+2*(entry-stop_loss)
        elif entry<float(previous["low"]):
            direction,reason,stop_loss="SELL","BEARISH",float(current["high"]); take_profit=entry-2*(stop_loss-entry)
        else:
            direction,reason,stop_loss,take_profit="NEUTRAL","NEUTRAL",None,None
        diagnostics["classification"]=direction
        return Signal(self.manifest.name,self.manifest.version,symbol,direction,timestamp,timeframe,reason,entry,stop_loss,take_profit,diagnostics)

def create_strategy(): return SweepV2Strategy()
