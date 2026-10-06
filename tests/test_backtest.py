import pandas as pd, numpy as np, pytest
from backtest import backtest_strategy
from config import ACCOUNT_RISK_PER_TRADE, ACCOUNT_SIZES, ACCOUNT_TRADE_LIMITS
from strategies.adaptive_trend import AdaptiveTrendMomentum

def test_backtest_returns_metrics():
    idx=pd.date_range("2024-01-01",periods=140,freq="D",tz="Asia/Kolkata"); c=pd.Series(np.linspace(100,250,140),index=idx); f=pd.DataFrame({"open":c-1,"high":c+2,"low":c-2,"close":c},index=idx)
    r=backtest_strategy(AdaptiveTrendMomentum(),"BTC-USD",f,account="macro"); assert r.metrics.rating>=0

# --- account context: backtest must size, start and limit like live -------

def _wave_frame(periods=400):
    idx=pd.date_range("2024-01-01",periods=periods,freq="D",tz="Asia/Kolkata")
    values=200+np.arange(periods)*0.15+25*np.sin(np.arange(periods)/11.0)
    close=pd.Series(values,index=idx)
    return pd.DataFrame({"open":close-1,"high":close+2,"low":close-2,"close":close},index=idx)

def test_backtest_starts_from_the_selected_account_capital(monkeypatch):
    """Regression: starting balance and return% follow the account, not a global."""
    frame=_wave_frame()
    baseline=backtest_strategy(AdaptiveTrendMomentum(),"BTC-USD",frame,account="macro")
    assert baseline.trades, "fixture must produce at least one trade"
    assert baseline.starting_account==ACCOUNT_SIZES["macro"]
    monkeypatch.setitem(ACCOUNT_SIZES,"macro",40_000.0)
    smaller=backtest_strategy(AdaptiveTrendMomentum(),"BTC-USD",frame,account="macro")
    assert smaller.starting_account==40_000.0
    # Capital sets the baseline only; position sizing stays on the risk budget,
    # so every trade's pnl must be identical between the two runs.
    assert [t.pnl for t in smaller.trades]==[t.pnl for t in baseline.trades]
    assert smaller.metrics.return_pct!=baseline.metrics.return_pct

def test_backtest_sizes_positions_from_the_account_risk_budget(monkeypatch):
    """Regression: quantity_for_risk must receive the account's risk budget."""
    frame=_wave_frame()
    baseline=backtest_strategy(AdaptiveTrendMomentum(),"BTC-USD",frame,account="macro")
    assert baseline.trades
    monkeypatch.setitem(ACCOUNT_RISK_PER_TRADE,"macro",500.0)
    reduced=backtest_strategy(AdaptiveTrendMomentum(),"BTC-USD",frame,account="macro")
    assert len(reduced.trades)==len(baseline.trades)
    for full,half in zip(baseline.trades,reduced.trades):
        assert half.timestamp==full.timestamp and half.direction==full.direction
        # Risk budget quartered -> position size (and therefore pnl) quartered.
        assert abs(half.pnl)==pytest.approx(abs(full.pnl)*0.25,rel=1e-9)

def test_backtest_enforces_the_selected_accounts_daily_trade_limit(monkeypatch):
    """Regression: the daily trade limit is read from the account context."""
    frame=_wave_frame()
    baseline=backtest_strategy(AdaptiveTrendMomentum(),"BTC-USD",frame,account="macro")
    assert baseline.trades
    monkeypatch.setitem(ACCOUNT_TRADE_LIMITS,"macro",0)
    blocked=backtest_strategy(AdaptiveTrendMomentum(),"BTC-USD",frame,account="macro")
    assert blocked.trades==()

def test_backtest_defaults_to_the_strategies_manifest_account():
    frame=_wave_frame()
    strategy=AdaptiveTrendMomentum()
    result=backtest_strategy(strategy,"BTC-USD",frame)
    assert result.starting_account==ACCOUNT_SIZES[strategy.manifest.account]
