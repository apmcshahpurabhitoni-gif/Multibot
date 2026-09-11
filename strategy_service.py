"""Shared plug-in strategy lifecycle: evaluate -> persist -> notify -> accept trade."""
from __future__ import annotations
from dataclasses import dataclass
from threading import RLock
import logging
import pandas as pd
from config import ACCOUNT_NAMES,ACCOUNT_SIZE_INR,LIVE_ASSET_MAP,LIVE_ASSETS,USD_TO_INR
from db import DatabaseManager
from notification_service import NotificationService
from signal_gate import SignalGate
from signal_lifecycle import new_signal_id,signal_key
from strategy_engine import StrategyEngine
from strategies.base import Signal
from telegram import TelegramConfig,TelegramMessage,render_signal_message
from trading import AccountState,PaperTrade,TradePlan,can_open_trade,quantity_for_risk,register_trade
logger=logging.getLogger("multibot2.strategy_service")

@dataclass(frozen=True)
class DispatchResult:
    symbol:str; signal:Signal; trade:PaperTrade|None; message:TelegramMessage|None
    sent:bool; reason:str; account:str; trade_id:str|None=None; signal_id:str|None=None

class StrategyService:
    def __init__(self,*,registry,provider=None,database=None,accounts=None,telegram_config=None,notifier=None):
        self.registry=registry; self.engine=StrategyEngine(provider); self.database=database or DatabaseManager()
        self.gate=SignalGate(); self.telegram_config=telegram_config; self.notifier=notifier or NotificationService(self.database,telegram_config)
        self._lock=RLock()
        if accounts is not None:self.accounts=accounts
        else:
            today=pd.Timestamp.now(tz="Asia/Kolkata").date().isoformat(); rows=self.database.load_accounts(ACCOUNT_NAMES,ACCOUNT_SIZE_INR,today)
            self.accounts={n:AccountState(n,float(rows[n]["starting_balance"]),float(rows[n]["balance"]),float(rows[n]["planned_risk_used"]),int(rows[n]["trades_today"])) for n in ACCOUNT_NAMES}

    def _now(self,value=None):
        t=pd.Timestamp.now(tz="Asia/Kolkata") if value is None else pd.Timestamp(value)
        if t.tzinfo is None: raise ValueError("Runtime timestamp must be timezone-aware")
        return t.tz_convert("Asia/Kolkata")

    def scan_symbol(self,strategy_id,symbol,*,now=None,period="30d"):
        strategy=self.registry.get(strategy_id); current=self._now(now)
        if symbol not in strategy.manifest.assets: raise ValueError(f"{strategy_id} does not support {symbol}")
        return self.engine.evaluate(strategy,symbol,now=current,period=period)

    def _record(self,signal,key,status):
        sid=new_signal_id(); self.database.record_signal_event(sid,key,signal,pipeline_status=status); return sid

    def _result(self,symbol,signal,account,reason,**kw): return DispatchResult(symbol,signal,kw.get("trade"),kw.get("message"),kw.get("sent",False),reason,account,kw.get("trade_id"),kw.get("signal_id"))

    def dispatch(self,strategy_id,symbol,signal,*,current_price,now=None,send=True):
        strategy=self.registry.get(strategy_id); asset=LIVE_ASSET_MAP[symbol]; current=self._now(now); account_name=strategy.manifest.account
        key=signal_key(signal,self.gate,symbol); sid=self._record(signal,key,"GENERATED")
        if not signal.is_directional:
            self.database.update_signal_status(sid,"NON_DIRECTIONAL")
            return self._result(symbol,signal,account_name,signal.reason or "NO_DIRECTIONAL_SIGNAL",signal_id=sid)
        if not self.gate.is_fresh(signal,now=current):
            self.database.update_signal_status(sid,"STALE")
            return self._result(symbol,signal,account_name,"STALE_SIGNAL",signal_id=sid)
        with self._lock:
            count=self.database.signal_count(key)
            if count>=2:
                self.database.update_signal_status(sid,"DUPLICATE_LIMIT"); return self._result(symbol,signal,account_name,"DUPLICATE_SIGNAL_LIMIT",signal_id=sid)
            if count==1:
                self.database.update_signal_status(sid,"REMINDER_PENDING"); return self._result(symbol,signal,account_name,"REMINDER_PENDING",signal_id=sid)
            account=self.accounts[account_name]
            if not can_open_trade(account):
                self.database.update_signal_status(sid,"ACCOUNT_LIMIT"); return self._result(symbol,signal,account_name,"ACCOUNT_DAILY_LIMIT",signal_id=sid)
            plan_tuple=strategy.build_trade_plan(signal,entry=current_price)
            if not plan_tuple:
                self.database.update_signal_status(sid,"NO_TRADE_PLAN"); return self._result(symbol,signal,account_name,"NO_TRADE_PLAN",signal_id=sid)
            entry,sl,tp=plan_tuple; fx=1.0 if asset.currency=="INR" else USD_TO_INR
            qty=quantity_for_risk(entry,sl,fx_rate=fx)
            plan=TradePlan(strategy.manifest.name,signal.direction,signal.timestamp,float(entry),float(sl),float(tp),timeframe=signal.timeframe,strategy_version=signal.version,metadata=signal.metadata,trailing_policy=strategy.trailing_policy(),fx_rate=fx)
            trade=PaperTrade(plan=plan,account=account_name,quantity=qty)
            age=max(0,int((current-signal.timestamp).total_seconds()/60))
            message=render_signal_message(signal,symbol=symbol,asset=asset.label,market=asset.market,timeframe=signal.timeframe,entry=entry,stop_loss=sl,take_profit=tp,quantity=qty,risk=trade.planned_risk,account=account_name,freshness="FRESH",age_str=f"{age} min ago")
            self.database.update_signal_status(sid,"READY")
            if not send:return self._result(symbol,signal,account_name,"READY_TO_SEND",trade=trade,message=message,signal_id=sid)
            delivered=self.notifier.deliver(signal_id=sid,message=message,metadata={"signal_key":key,"strategy":strategy.manifest.id,"symbol":symbol})
            if not delivered:
                self.database.update_signal_status(sid,"DELIVERY_FAILED")
                return self._result(symbol,signal,account_name,"TELEGRAM_FAILED",trade=trade,message=message,signal_id=sid)
            updated=register_trade(account,planned_risk=trade.planned_risk); self.accounts[account_name]=updated
            trade_id=f"{account_name}_{symbol}_{int(current.timestamp()*1000)}"
            row={"id":trade_id,"status":"OPEN","signal_id":sid,"symbol":symbol,"label":asset.label,"market":asset.market,"asset_type":asset.asset_type,"group":asset.group,"timeframe":signal.timeframe,"account":account_name,"strategy":plan.strategy,"strategy_version":plan.strategy_version,"type":signal.direction,"entry":entry,"sl":sl,"tp":tp,"qty":qty,"risk_per_unit":plan.risk_per_unit,"risk_per_unit_inr":plan.risk_per_unit_inr,"fx_rate":plan.fx_rate,"currency":asset.currency,"planned_risk":trade.planned_risk,"signal_ts":signal.timestamp.isoformat(),"opened_at":current.isoformat(),"trailing_policy":plan.trailing_policy}
            self.database.save_trade(trade_id,"OPEN",row,current.isoformat())
            self.database.save_account(account_name,balance=updated.balance,trades_today=updated.trades_today,planned_risk_used=updated.planned_risk_used,reset_date=current.date().isoformat())
            self.database.record_signal_send(key,current.isoformat(),(current+pd.Timedelta(hours=1)).isoformat(),message.text,{"signal_id":sid,"message_type":message.message_type})
            self.database.update_signal_status(sid,"DELIVERED")
            return self._result(symbol,signal,account_name,"SENT_AND_ACCEPTED",trade=trade,message=message,sent=True,trade_id=trade_id,signal_id=sid)

    def current_price(self,symbol):
        asset=LIVE_ASSET_MAP[symbol]
        try:
            frame=self.engine.provider.fetch(asset.yahoo_symbol,period="1d",interval="1m",validate_hourly=False)
            return None if frame.empty else float(frame.close.iloc[-1])
        except Exception as exc: logger.warning("Current price lookup failed for %s: %s",symbol,exc); return None

    def scan_and_dispatch(self,strategy_id,*,now=None,period="30d",send=True):
        strategy=self.registry.get(strategy_id); current=self._now(now); results=[]
        for asset in LIVE_ASSETS:
            if asset.symbol not in strategy.manifest.assets: continue
            try:
                signal,_=self.scan_symbol(strategy_id,asset.symbol,now=current,period=period)
                price=self.current_price(asset.symbol) if signal.is_directional else 0.0
                if signal.is_directional and price is None:
                    signal=Signal(strategy.manifest.name,strategy.manifest.version,asset.symbol,"NO_SIGNAL",current,signal.timeframe,"MARKET_DATA_ERROR",metadata={"error":"CURRENT_PRICE_UNAVAILABLE"})
                results.append(self.dispatch(strategy_id,asset.symbol,signal,current_price=price or 0.0,now=current,send=send))
            except Exception as exc:
                signal=Signal(strategy.manifest.name,strategy.manifest.version,asset.symbol,"NO_SIGNAL",current,strategy.manifest.timeframes[0],"MARKET_DATA_ERROR",metadata={"error":str(exc)})
                key=signal_key(signal,self.gate,asset.symbol); sid=self._record(signal,key,"ERROR")
                results.append(self._result(asset.symbol,signal,strategy.manifest.account,f"MARKET_DATA_ERROR: {exc}",signal_id=sid))
        return results
