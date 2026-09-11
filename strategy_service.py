"""Shared plug-in strategy signal orchestration."""
from __future__ import annotations
from dataclasses import dataclass
from threading import RLock
import logging, hashlib
import pandas as pd
from config import ACCOUNT_NAMES,ACCOUNT_SIZE_INR,LIVE_ASSET_MAP,LIVE_ASSETS,RISK_PER_TRADE_INR,USD_TO_INR
from db import DatabaseManager
from signal_gate import SignalGate
from strategy_engine import StrategyEngine
from strategies.base import Signal
from telegram import TelegramConfig,TelegramMessage,render_signal_message,send_message
from trading import AccountState,PaperTrade,TradePlan,can_open_trade,quantity_for_risk,register_trade

logger=logging.getLogger("multibot2.strategy_service")

@dataclass(frozen=True)
class DispatchResult:
    symbol:str; signal:Signal; trade:PaperTrade|None; message:TelegramMessage|None
    sent:bool; reason:str; account:str; trade_id:str|None=None; signal_id:str|None=None

class StrategyService:
    def __init__(self,*,registry,provider=None,database=None,accounts=None,telegram_config=None):
        self.registry=registry; self.engine=StrategyEngine(provider); self.database=database or DatabaseManager(); self.gate=SignalGate(); self.telegram_config=telegram_config; self._lock=RLock()
        if accounts is not None:self.accounts=accounts
        else:
            today=pd.Timestamp.now(tz="Asia/Kolkata").date().isoformat(); rows=self.database.load_accounts(ACCOUNT_NAMES,ACCOUNT_SIZE_INR,today)
            self.accounts={n:AccountState(n,float(rows[n]["starting_balance"]),float(rows[n]["balance"]),float(rows[n]["planned_risk_used"]),int(rows[n]["trades_today"])) for n in ACCOUNT_NAMES}

    def _now(self,value=None):
        t=pd.Timestamp.now(tz="Asia/Kolkata") if value is None else pd.Timestamp(value)
        if t.tzinfo is None:raise ValueError("Runtime timestamp must be timezone-aware")
        return t.tz_convert("Asia/Kolkata")
    def _config(self):return self.telegram_config or TelegramConfig.from_env()

    def scan_symbol(self,strategy_id,symbol,*,now=None,period="30d"):
        strategy=self.registry.get(strategy_id); current=self._now(now)
        if symbol not in strategy.manifest.assets:raise ValueError(f"{strategy_id} does not support {symbol}")
        return self.engine.evaluate(strategy,symbol,now=current,period=period)

    def _event(self,signal,key,status):
        signal_id=hashlib.sha256(key.encode()).hexdigest()[:32]
        self.database.record_signal_event(signal_id,key,signal,pipeline_status=status)
        return signal_id

    def _result(self,symbol,signal,account,reason,*,trade=None,message=None,sent=False,trade_id=None,signal_id=None):
        return DispatchResult(symbol,signal,trade,message,sent,reason,account,trade_id,signal_id)

    def dispatch(self,strategy_id,symbol,signal,*,current_price,now=None,send=True):
        strategy=self.registry.get(strategy_id); asset=LIVE_ASSET_MAP[symbol]; current=self._now(now); account_name=strategy.manifest.account
        key=self.gate.signal_key(signal,symbol=symbol); signal_id=self._event(signal,key,"GENERATED")

        if not signal.is_directional:
            self.database.update_signal_status(signal_id,"NON_DIRECTIONAL")
            return self._result(symbol,signal,account_name,signal.reason or "NO_DIRECTIONAL_SIGNAL",signal_id=signal_id)
        if not self.gate.is_fresh(signal,now=current):
            self.database.update_signal_status(signal_id,"STALE")
            return self._result(symbol,signal,account_name,"STALE_SIGNAL",signal_id=signal_id)

        with self._lock:
            count=self.database.signal_count(key)
            if count>=2:
                self.database.update_signal_status(signal_id,"DUPLICATE_LIMIT")
                return self._result(symbol,signal,account_name,"DUPLICATE_SIGNAL_LIMIT",signal_id=signal_id)
            if count==1:
                self.database.update_signal_status(signal_id,"REMINDER_PENDING")
                return self._result(symbol,signal,account_name,"REMINDER_PENDING",signal_id=signal_id)

            account=self.accounts[account_name]
            if not can_open_trade(account):
                self.database.update_signal_status(signal_id,"ACCOUNT_LIMIT")
                return self._result(symbol,signal,account_name,"ACCOUNT_DAILY_LIMIT",signal_id=signal_id)

            plan_tuple=strategy.build_trade_plan(signal,entry=current_price)
            if not plan_tuple:
                self.database.update_signal_status(signal_id,"NO_TRADE_PLAN")
                return self._result(symbol,signal,account_name,"NO_TRADE_PLAN",signal_id=signal_id)
            entry,sl,tp=plan_tuple
            fx_rate=1.0 if asset.currency=="INR" else USD_TO_INR
            qty=quantity_for_risk(entry,sl,fx_rate=fx_rate)
            plan=TradePlan(strategy.manifest.name,signal.direction,signal.timestamp,float(entry),float(sl),float(tp),timeframe=signal.timeframe,strategy_version=signal.version,metadata=signal.metadata,trailing_policy=strategy.trailing_policy(),fx_rate=fx_rate)
            trade=PaperTrade(plan=plan,account=account_name,quantity=qty)
            age=max(0,int((current-signal.timestamp).total_seconds()/60)); age_text=f"{age} min ago" if age<60 else f"{age//60} hr {age%60} min ago"
            message=render_signal_message(signal,symbol=symbol,asset=asset.label,market=asset.market,timeframe=signal.timeframe,entry=entry,stop_loss=sl,take_profit=tp,quantity=qty,risk=trade.planned_risk,account=account_name,freshness="FRESH",age_str=age_text)
            if not send:
                self.database.update_signal_status(signal_id,"READY")
                return self._result(symbol,signal,account_name,"READY_TO_SEND",trade=trade,message=message,signal_id=signal_id)

            updated=register_trade(account,planned_risk=trade.planned_risk); self.accounts[account_name]=updated
            trade_id=f"{account_name}_{symbol}_{int(current.timestamp()*1000)}"
            row={"id":trade_id,"status":"OPEN","symbol":symbol,"label":asset.label,"market":asset.market,"asset_type":asset.asset_type,"group":asset.group,"timeframe":signal.timeframe,"account":account_name,"strategy":plan.strategy,"strategy_version":plan.strategy_version,"type":signal.direction,"entry":entry,"sl":sl,"tp":tp,"qty":qty,"risk_per_unit":plan.risk_per_unit,"risk_per_unit_inr":plan.risk_per_unit_inr,"fx_rate":plan.fx_rate,"currency":asset.currency,"planned_risk":trade.planned_risk,"signal_ts":signal.timestamp.isoformat(),"opened_at":current.isoformat(),"trailing_policy":plan.trailing_policy,"signal_id":signal_id}
            self.database.save_trade(trade_id,"OPEN",row,current.isoformat())
            self.database.save_account(account_name,balance=updated.balance,trades_today=updated.trades_today,planned_risk_used=updated.planned_risk_used,reset_date=current.date().isoformat())
            self.database.update_signal_status(signal_id,"ACCEPTED")

            metadata={"message_type":message.message_type,"strategy":plan.strategy,"strategy_version":plan.strategy_version,"symbol":symbol,"asset":asset.label,"market":asset.market,"timeframe":signal.timeframe,"direction":signal.direction,"timestamp":signal.timestamp.isoformat(),"reason":signal.reason}
            self.database.record_delivery(signal_id,channel="telegram",status="PENDING",message_type=message.message_type,metadata=metadata)
            try:
                send_message(message,self._config())
                self.database.record_signal_send(key,current.isoformat(),(current+pd.Timedelta(hours=1)).isoformat(),message.text,metadata)
                self.database.record_delivery(signal_id,channel="telegram",status="SENT",message_type=message.message_type,metadata=metadata)
                self.database.update_signal_status(signal_id,"DELIVERED")
                return self._result(symbol,signal,account_name,"SENT_AND_ACCEPTED",trade=trade,message=message,sent=True,trade_id=trade_id,signal_id=signal_id)
            except Exception as exc:
                logger.exception("Telegram delivery failed for %s",signal_id)
                self.database.record_delivery(signal_id,channel="telegram",status="FAILED",error_text=str(exc),message_type=message.message_type,metadata=metadata)
                self.database.update_signal_status(signal_id,"DELIVERY_FAILED")
                return self._result(symbol,signal,account_name,"TELEGRAM_FAILED",trade=trade,message=message,trade_id=trade_id,signal_id=signal_id)

    def current_price(self,symbol):
        asset=LIVE_ASSET_MAP[symbol]
        try:
            frame=self.engine.provider.fetch(asset.yahoo_symbol,period="1d",interval="1m",validate_hourly=False)
            return None if frame.empty else float(frame.close.iloc[-1])
        except Exception as exc:
            logger.warning("Current price lookup failed for %s: %s",symbol,exc); return None

    def scan_and_dispatch(self,strategy_id,*,now=None,period="30d",send=True):
        strategy=self.registry.get(strategy_id); current=self._now(now); results=[]
        for asset in LIVE_ASSETS:
            if asset.symbol not in strategy.manifest.assets:continue
            try:
                signal,_=self.scan_symbol(strategy_id,asset.symbol,now=current,period=period)
                # Always dispatch: the orchestrator records directional and non-directional outcomes.
                price=self.current_price(asset.symbol) if signal.is_directional else 0.0
                results.append(self.dispatch(strategy_id,asset.symbol,signal,current_price=price or 0.0,now=current,send=send))
            except Exception as exc:
                signal=Signal(strategy.manifest.name,strategy.manifest.version,asset.symbol,"NO_SIGNAL",current,strategy.manifest.timeframes[0],"MARKET_DATA_ERROR",metadata={"error":str(exc)})
                key=self.gate.signal_key(signal,symbol=asset.symbol); signal_id=self._event(signal,key,"ERROR")
                results.append(self._result(asset.symbol,signal,strategy.manifest.account,f"MARKET_DATA_ERROR: {exc}",signal_id=signal_id))
        return results
