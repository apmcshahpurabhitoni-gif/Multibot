import pandas as pd, numpy as np
from strategies import discover_strategies

def test_plugins_have_stable_contract():
    r=discover_strategies()
    assert set(r.ids()) == {"adaptive_trend","sweep_v2"}
    for s in r.all():
        assert s.manifest.id and s.manifest.name and s.manifest.version
        assert s.manifest.assets and s.manifest.timeframes

def test_adaptive_trend_produces_canonical_signal():
    s=discover_strategies().get("adaptive_trend"); idx=pd.date_range("2024-01-01",periods=120,freq="D",tz="Asia/Kolkata"); c=pd.Series(np.linspace(100,300,120),index=idx); f=pd.DataFrame({"open":c-1,"high":c+2,"low":c-2,"close":c},index=idx)
    x=s.generate_signal("BTC-USD",f,now=idx[-1]); assert x.strategy==s.manifest.name and x.version==s.manifest.version and x.timeframe=="1D"
