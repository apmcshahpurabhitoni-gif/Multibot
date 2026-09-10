"""Backend-only dashboard payload builder. No strategy/risk calculations."""
from __future__ import annotations
from typing import Any, Iterable
from config import *
from strategies import Signal
from trading import AccountState, PaperTrade

def signal_to_dict(s):
    if isinstance(s, dict): return dict(s)
    return {"strategy":s.strategy,"strategy_version":s.version,"symbol":s.symbol,"signal":s.direction,"timestamp":s.timestamp.isoformat(),"timeframe":s.timeframe,"reason":s.reason,"entry":s.entry,"stop_loss":s.stop_loss,"take_profit":s.take_profit,"metadata":s.metadata}
def trade_to_dict(t):
    if isinstance(t, dict): return dict(t)
    p=t.plan; return {"status":t.status,"plan":{"strategy":p.strategy,"strategy_version":p.strategy_version,"side":p.side,"signal_timestamp":p.signal_timestamp.isoformat(),"timeframe":p.timeframe,"entry":p.entry,"stop_loss":p.stop_loss,"take_profit":p.take_profit,"risk_per_unit":p.risk_per_unit,"trailing_policy":p.trailing_policy},"quantity":t.quantity,"planned_risk":t.planned_risk,"exit_price":t.exit_price,"exit_timestamp":t.exit_timestamp.isoformat() if t.exit_timestamp else None,"exit_reason":t.exit_reason}
def account_to_dict(a: AccountState):
    return {"name":a.name,"starting_balance":a.starting_balance,"balance":a.balance,"planned_risk_used":a.planned_risk_used,"daily_trade_limit":a.daily_trade_limit,"max_daily_planned_risk":a.max_daily_planned_risk,"trades_today":a.trades_today,"remaining_trades":a.remaining_trades,"remaining_planned_risk":a.remaining_planned_risk}
def build_dashboard_snapshot(*,version=APP_VERSION,whats_new=WHAT_IS_NEW,accounts=(),signals=(),trades=(),scan=None,health=None,strategies=()):
    sr=[signal_to_dict(x) for x in signals]; tr=[trade_to_dict(x) for x in trades]; ar=[account_to_dict(x) for x in accounts]
    catalog=[]
    for st in strategies:
        catalog.append({"id":st.manifest.id,"name":st.manifest.name,"version":st.manifest.version,"description":st.manifest.description,"assets":list(st.manifest.assets),"timeframes":list(st.manifest.timeframes),"schedule":st.manifest.schedule,"account":st.manifest.account,"capabilities":list(st.manifest.capabilities),"parameters":st.manifest.parameters})
    return {"ok":True,"version":version,"whats_new":list(whats_new),"generated_at":pd.Timestamp.now(tz=IST_TIMEZONE).isoformat(),"backtest_assets":[{"key":symbol,"ticker":v["ticker"],"label":v["label"],"group":v["group"]} for symbol,v in BACKTEST_ASSETS.items()],"system":{"status":"ONLINE","mode":"PAPER","timezone":IST_TIMEZONE,"provider":"YAHOO","freshness_hours":SIGNAL_FRESHNESS_HOURS,"leverage":LEVERAGE},"rules":{"account_size_inr":ACCOUNT_SIZE_INR,"risk_per_trade_inr":RISK_PER_TRADE_INR,"account_trade_limits":dict(ACCOUNT_TRADE_LIMITS)},"universe":{"count":len(LIVE_ASSETS),"symbols":list(LIVE_SYMBOLS),"asset_metadata":[{"symbol":a.symbol,"label":a.label,"ticker":a.yahoo_symbol,"market":a.market,"asset_type":a.asset_type,"group":a.group,"sweep_timeframe":a.sweep_timeframe} for a in LIVE_ASSETS]},"strategies":catalog,"accounts":{"count":len(ar),"names":list(ACCOUNT_NAMES),"data":ar},"signals":sr,"trades":tr,"scan":scan or {},"health":health or {},"counts":{"signals":len(sr),"trades":len(tr),"open_trades":sum(x["status"]=="OPEN" for x in tr),"closed_trades":sum(x["status"]=="CLOSED" for x in tr)}}
def empty_dashboard_snapshot(): return build_dashboard_snapshot()
