import pandas as pd, numpy as np
from backtest import backtest_strategy
from strategies.adaptive_trend import AdaptiveTrendMomentum

def test_backtest_returns_metrics():
    idx=pd.date_range("2024-01-01",periods=140,freq="D",tz="Asia/Kolkata"); c=pd.Series(np.linspace(100,250,140),index=idx); f=pd.DataFrame({"open":c-1,"high":c+2,"low":c-2,"close":c},index=idx)
    r=backtest_strategy(AdaptiveTrendMomentum(),"BTC-USD",f,account="macro"); assert r.metrics.rating>=0
