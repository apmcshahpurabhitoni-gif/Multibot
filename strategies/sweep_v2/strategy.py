from __future__ import annotations
import pandas as pd
from strategies.base import Signal, Strategy, StrategyManifest
from sweep_engine import build_closed_candles
from config import LIVE_ASSET_MAP, LIVE_SYMBOLS
class SweepV2Strategy(Strategy):
    manifest=StrategyManifest(id="sweep_v2",name="Sweep V2",version="2.0.1",description="Strict two-sided sweep followed by final-close classification.",assets=LIVE_SYMBOLS,timeframes=("1h","4h"),schedule="canonical_sweep_schedule",account="sweep_4h",capabilities=("signal","strategy_sl","risk_reward_tp","scheduled_scan","backtest"),parameters={"timeframe":{"type":"strategy","default":"asset_schedule"},"risk_reward":{"type":"number","default":2.0,"min":1.0,"max":10.0,"editable":False}})
    def data_request(self,symbol,*,period="30d"):
        return ("1h" if LIVE_ASSET_MAP[symbol].market=="NSE" else "30m"),period
    def prepare_candles(self,symbol,candles,*,now):
        return build_closed_candles(candles,symbol,now=now,lookback_days=7)[0]
    def generate_signal(self,symbol,candles,*,now):
        asset=LIVE_ASSET_MAP[symbol]; timeframe=asset.sweep_timeframe; ts=candles.index[-1] if len(candles) else pd.Timestamp(now)
        if len(candles)<2:return Signal(self.manifest.name,self.manifest.version,symbol,"NO_SIGNAL",ts,timeframe,"NO_SWEEP")
        previous,current=candles.iloc[-2],candles.iloc[-1]
        if not(float(current.high)>float(previous.high) and float(current.low)<float(previous.low)):return Signal(self.manifest.name,self.manifest.version,symbol,"NO_SIGNAL",ts,timeframe,"NO_SWEEP")
        if float(current.close)>float(previous.high): direction="BUY"
        elif float(current.close)<float(previous.low): direction="SELL"
        else: direction="NEUTRAL"
        entry=float(current.close)
        if direction=="BUY": sl=float(current.low);tp=entry+2*(entry-sl)
        elif direction=="SELL": sl=float(current.high);tp=entry-2*(sl-entry)
        else: sl=tp=None
        return Signal(self.manifest.name,self.manifest.version,symbol,direction,ts,timeframe,direction,entry,sl,tp,{"candle_start":pd.Timestamp(ts).isoformat(),"previous":{k:float(previous[k]) for k in("open","high","low","close")},"current":{k:float(current[k]) for k in("open","high","low","close")}})
def create_strategy():return SweepV2Strategy()
