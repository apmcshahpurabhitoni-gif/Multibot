"""Registry-driven backtesting and transparent strategy scoring."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import math
import pandas as pd
from config import ACCOUNT_SIZE_INR, ACCOUNT_TRADE_LIMITS, LIVE_ASSET_MAP, RISK_PER_TRADE_INR, USD_TO_INR
from trading import quantity_for_risk
from strategies.base import Signal

@dataclass(frozen=True)
class BacktestTrade:
    timestamp: pd.Timestamp; direction: str; entry: float; exit: float; pnl: float; bars_held: int

@dataclass(frozen=True)
class BacktestMetrics:
    return_pct: float; max_drawdown_pct: float; sharpe: float; sortino: float; win_rate_pct: float
    profit_factor: float; number_of_trades: int; average_trade: float; max_losing_streak: int
    exposure_pct: float; risk_adjusted_performance: float; rating: float; rating_label: str; breakdown: dict

@dataclass(frozen=True)
class BacktestResult:
    strategy: str; strategy_version: str; symbol: str; starting_account: float
    signals: tuple[Signal,...]; trades: tuple[BacktestTrade,...]; metrics: BacktestMetrics; parameters: dict

def _annualized_sharpe(returns):
    if len(returns)<2 or returns.std(ddof=1)==0: return 0.0
    return float(returns.mean()/returns.std(ddof=1)*math.sqrt(252))

def _sortino(returns):
    if len(returns)<2: return 0.0
    downside=returns[returns<0]
    if len(downside)==0: return float("inf") if returns.mean()>0 else 0.0
    d=downside.std(ddof=1) if len(downside)>1 else abs(float(downside.iloc[0]))
    return float(returns.mean()/d*math.sqrt(252)) if d else 0.0

def score_metrics(metrics_raw):
    # Transparent bounded component score. Extremes are capped to avoid one metric dominating.
    ret=max(0,min(100,50+metrics_raw["return_pct"]*1.5))
    risk=max(0,min(100,100-metrics_raw["max_drawdown_pct"]*2.5))
    consistency=max(0,min(100,metrics_raw["win_rate_pct"]*1.25))
    efficiency=max(0,min(100,50+metrics_raw["sharpe"]*20+metrics_raw["sortino"]*10))
    sample=min(100,metrics_raw["number_of_trades"]*0.5)
    pf=min(100,metrics_raw["profit_factor"]*40) if math.isfinite(metrics_raw["profit_factor"]) else 100
    breakdown={"performance":round((ret+pf)/2,2),"risk":round(risk,2),"consistency":round(consistency,2),"efficiency":round(efficiency,2),"robustness":round((sample+max(0,100-metrics_raw["max_losing_streak"]*8))/2,2)}
    raw=breakdown["performance"]*.25+breakdown["risk"]*.25+breakdown["consistency"]*.20+breakdown["efficiency"]*.15+breakdown["robustness"]*.15
    confidence=min(1.0,metrics_raw["number_of_trades"]/100)
    rating=50+(raw-50)*confidence
    label="Exceptional" if rating>=90 else "Strong" if rating>=80 else "Good" if rating>=70 else "Moderate" if rating>=60 else "Weak" if rating>=50 else "Poor"
    return round(max(0,min(100,rating)),2),label,breakdown

def _simulate(frame, strategy, symbol, account_limit):
    signals=[]; trades=[]; equity=ACCOUNT_SIZE_INR; peak=equity; max_dd=0; exposure_bars=0
    current_day=None; day_trades=0; next_eligible=0
    f=frame.sort_index(); asset=LIVE_ASSET_MAP[symbol]; fx_rate=1.0 if asset.currency=="INR" else USD_TO_INR
    for i in range(max(2,50),len(f)):
        if i < next_eligible: continue
        prefix=f.iloc[:i+1]; ts=f.index[i]; signal=strategy.backtest_signal(symbol,prefix,now=ts); signals.append(signal)
        if not signal.is_directional or signal.stop_loss is None or signal.take_profit is None: continue
        day=ts.tz_convert("Asia/Kolkata").date() if ts.tzinfo else ts.date()
        if day!=current_day: current_day=day; day_trades=0
        if day_trades>=account_limit: continue
        entry=float(signal.entry or f.close.iloc[i]); sl=float(signal.stop_loss); tp=float(signal.take_profit)
        try: qty=quantity_for_risk(entry,sl,fx_rate=fx_rate)
        except ValueError: continue
        exit_price=None; exit_i=i
        for j in range(i+1,len(f)):
            hi,lo=float(f.high.iloc[j]),float(f.low.iloc[j])
            if signal.direction=="BUY":
                if lo<=sl: exit_price=sl; exit_i=j; break
                if hi>=tp: exit_price=tp; exit_i=j; break
            else:
                if hi>=sl: exit_price=sl; exit_i=j; break
                if lo<=tp: exit_price=tp; exit_i=j; break
        if exit_price is None: exit_price=float(f.close.iloc[-1]); exit_i=len(f)-1
        pnl=(exit_price-entry)*qty*(1 if signal.direction=="BUY" else -1)*fx_rate
        equity+=pnl; peak=max(peak,equity); max_dd=max(max_dd,(peak-equity)/peak*100); exposure_bars+=max(1,exit_i-i)
        trades.append(BacktestTrade(ts,signal.direction,entry,exit_price,pnl,exit_i-i))
        day_trades+=1; next_eligible=max(i+1,exit_i+1)
    return signals,trades,equity,max_dd,exposure_bars
def backtest_strategy(strategy, symbol, candles, *, account=None, parameters=None):
    if not isinstance(candles,pd.DataFrame) or not isinstance(candles.index,pd.DatetimeIndex): raise ValueError("Backtest candles must use a timezone-aware DatetimeIndex")
    if candles.index.tz is None: raise ValueError("Backtest timestamps must be timezone-aware")
    account=account or strategy.manifest.account; limit=int(ACCOUNT_TRADE_LIMITS[account]); signals,trades,equity,max_dd,exposure_bars=_simulate(candles,strategy,symbol,limit)
    pnls=pd.Series([t.pnl for t in trades],dtype=float); wins=pnls[pnls>0]; losses=pnls[pnls<0]; pf=float(wins.sum()/abs(losses.sum())) if losses.sum()!=0 else (float("inf") if wins.sum()>0 else 0.0)
    returns=pnls/ACCOUNT_SIZE_INR if len(pnls) else pd.Series(dtype=float); win_rate=float((pnls>0).mean()*100) if len(pnls) else 0; avg=float(pnls.mean()) if len(pnls) else 0; streak=max_streak=0
    for x in pnls: streak=streak+1 if x<0 else 0; max_streak=max(max_streak,streak)
    exposure=min(100,exposure_bars/max(1,len(candles))*100)
    raw={"return_pct":(equity/ACCOUNT_SIZE_INR-1)*100,"max_drawdown_pct":max_dd,"sharpe":_annualized_sharpe(returns),"sortino":_sortino(returns),"win_rate_pct":win_rate,"profit_factor":pf,"number_of_trades":len(trades),"average_trade":avg,"max_losing_streak":max_streak,"exposure_pct":exposure}
    raw["risk_adjusted_performance"]=max(0,raw["sharpe"])*max(0,raw["sortino"])
    rating,label,breakdown=score_metrics(raw)
    metrics=BacktestMetrics(raw["return_pct"],raw["max_drawdown_pct"],raw["sharpe"],raw["sortino"],raw["win_rate_pct"],raw["profit_factor"],raw["number_of_trades"],raw["average_trade"],raw["max_losing_streak"],raw["exposure_pct"],raw["risk_adjusted_performance"],rating,label,breakdown)
    return BacktestResult(strategy.manifest.name,strategy.manifest.version,symbol,ACCOUNT_SIZE_INR,tuple(signals),tuple(trades),metrics,parameters or strategy.validate_config({}))
