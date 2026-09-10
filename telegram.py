"""Telegram adapter. It formats canonical signals/trades but never computes them."""
from __future__ import annotations
from dataclasses import dataclass
import os
from urllib import parse, request
import pandas as pd
from strategies import Signal
from trading import PaperTrade
from config import LIVE_ASSET_MAP
BR="━━━━━━━━━━━━━━━━━━━━━━"; BR2="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
DASHBOARD_URL=os.getenv("DASHBOARD_URL","https://multibot2-t74l.onrender.com/dashboard")
class TelegramConfigurationError(RuntimeError): pass
class TelegramTemplateError(RuntimeError): pass
@dataclass(frozen=True)
class TelegramConfig:
    bot_token:str; chat_id:str
    @classmethod
    def from_env(cls):
        token=os.getenv("TELEGRAM_BOT_TOKEN"); chat_id=os.getenv("TELEGRAM_CHAT_ID")
        if not token: raise TelegramConfigurationError("TELEGRAM_BOT_TOKEN is not configured")
        if not chat_id: raise TelegramConfigurationError("TELEGRAM_CHAT_ID is not configured")
        return cls(token,chat_id)
@dataclass(frozen=True)
class TelegramMessage: message_type:str; text:str

def signal_message_type(signal):
    if signal.direction not in {"BUY","SELL"}: raise TelegramTemplateError(f"No approved template for {signal.strategy}/{signal.direction}")
    return f"MSG-SIGNAL-{signal.direction}-V1"
def _currency(symbol,market):
    asset = LIVE_ASSET_MAP.get(str(symbol).strip().upper())
    currency = asset.currency if asset is not None else ("INR" if str(market).upper()=="NSE" else "USD")
    return "₹" if currency=="INR" else "$"
def _decimals(symbol): return 2
def build_signal_fields(signal:Signal,**fields):
    symbol=fields.get("symbol",signal.symbol); market=fields.get("market",""); d=_decimals(symbol); freshness=fields.get("freshness","FRESH"); age=fields.get("age_str","")
    return {"strategy":signal.strategy,"version":signal.version,"asset":fields.get("asset",symbol),"symbol":symbol,"market":market,"timeframe":fields.get("timeframe",signal.timeframe),"direction":"LONG 📈" if signal.direction=="BUY" else "SHORT 📉","status_tag":freshness,"status_icon":"⚠️" if freshness=="STALE" else "✅","age_str":age,"time_str":signal.timestamp.strftime("%d-%b-%Y %H:%M IST"),"currency":_currency(symbol,market),"entry_fmt":f"{float(fields.get('entry',signal.entry or 0)):,.{d}f}","sl_fmt":f"{float(fields.get('stop_loss',signal.stop_loss or 0)):,.{d}f}","tp_fmt":f"{float(fields.get('take_profit',signal.take_profit or 0)):,.{d}f}","qty_fmt":f"{float(fields.get('quantity',0)):,.4f}","risk_fmt":f"{float(fields.get('risk',0)):,.2f}","account":str(fields.get("account","")).upper()}
def render_signal_message(signal,**fields):
    f=build_signal_fields(signal,**fields); text=(f"{'🟢' if signal.direction=='BUY' else '🔴'} *{f['strategy']} · {f['asset']}* · {f['status_icon']}\n{BR}\n🪙 *Asset:* `{f['asset']}` (`{f['symbol']}`)\n🌐 *Market:* {f['market']}\n📊 *Direction:* {f['direction']}\n⏱ *Timeframe:* {f['timeframe']}\n{BR}\n⏳ *Signal Status:* `{f['status_tag']}` ({f['age_str']})\n⏰ *Candle Closed:* `{f['time_str']}`\n{BR}\n💼 *PAPER TRADE EXECUTED*\n{BR}\n🏢 *Account:* `{f['account']}`\n📍 *Entry:* `{f['currency']}{f['entry_fmt']}`\n🛑 *Stop Loss:* `{f['currency']}{f['sl_fmt']}`\n🎯 *Take Profit:* `{f['currency']}{f['tp_fmt']}`\n📦 *Quantity:* `{f['qty_fmt']}`\n💸 *Risk:* `₹{f['risk_fmt']}`\n{BR}\nℹ️ _Strategy: {f['version']} · Fresh ≤1h · Stale >1h_\n{BR2}")
    return TelegramMessage(signal_message_type(signal),text)
def build_trade_fields(trade:PaperTrade):
    p=trade.plan; return {"strategy":p.strategy,"strategy_version":p.strategy_version,"side":p.side,"signal_timestamp":p.signal_timestamp.isoformat(),"timeframe":p.timeframe,"entry":p.entry,"stop_loss":p.stop_loss,"take_profit":p.take_profit,"risk_per_unit":p.risk_per_unit,"status":trade.status,"exit_price":trade.exit_price if trade.exit_price is not None else "","exit_timestamp":trade.exit_timestamp.isoformat() if trade.exit_timestamp else "","exit_reason":trade.exit_reason or ""}
def signal_rejection_message(*,strategy,symbol,reason,detail=""):
    labels={"STALE_SIGNAL":"⏳ Signal is older than the 1-hour freshness limit.","DUPLICATE_SIGNAL_LIMIT":"🔁 Signal reached its two-send limit.","REMINDER_PENDING":"🔔 Initial signal already exists; reminder workflow owns the second send.","ACCOUNT_DAILY_LIMIT":"🛑 Account daily limit reached.","NO_DIRECTIONAL_SIGNAL":"💤 No BUY/SELL signal was produced."}; return TelegramMessage("MSG-SIGNAL-REJECTED-V1",f"⚠️ *SIGNAL NOT SENT*\n{BR}\n🧠 *Strategy:* `{strategy}`\n🪙 *Asset:* `{symbol}`\n📝 {labels.get(reason,detail or reason)}\n{BR2}")
def trade_closed_message(trade,live,pnl,balance,is_long,hit_tp): return TelegramMessage("MSG-TRADE-CLOSED-V1",f"{'🟢' if pnl>=0 else '🔴'} *TRADE CLOSED*\n{BR}\n🧠 `{trade.plan.strategy}` · `{trade.plan.strategy_version}`\n🪙 `{trade.plan.entry}` → `{trade.exit_price}`\n💰 P&L: `₹{pnl:,.2f}`\n💼 Balance: `₹{balance:,.2f}`\n{BR2}")
def msg_start(): return f"🤖 *MULTIBOT2 ONLINE*\n{BR}\n🧩 Plug-and-play strategy engine\n📡 Yahoo Finance\n🧪 PAPER ONLY\n📊 {len(LIVE_ASSET_MAP)} locked assets\n🌐 {DASHBOARD_URL}\n{BR2}"
def msg_scan_started(): return f"🔍 *SCAN STARTED*\n{BR}\n🧩 Running discovered strategy plug-ins\n📊 {len(LIVE_ASSET_MAP)} locked live assets\n⏳ Please wait...\n{BR2}"
def msg_scan_result(found,checked): return f"🔎 *SCAN COMPLETE*\n{BR}\n📊 Evaluations: `{checked}`\n🎯 New signals: `{found}`\n{BR2}"
def msg_balance(accounts): return f"💰 *ACCOUNT BALANCE*\n{BR}\n"+"\n".join(f"🏢 `{a.name}` · ₹{a.balance:,.2f} · {a.remaining_trades} trades left" for a in accounts.values())+f"\n{BR2}"
def msg_summary(active,history,live_prices=None): return f"📊 *SUMMARY*\n{BR}\n🟢 Open: `{len(active)}`\n⚪ Closed: `{len(history)}`\n{BR2}"
def msg_risk(active): return f"🛡️ *RISK*\n{BR}\n📂 Open trades: `{len(active)}`\n🎯 Base risk: `₹2,000`\n{BR2}"
def msg_stats(history): return f"📈 *STATS*\n{BR}\n📂 Closed trades: `{len(history)}`\n{BR2}"
def msg_weekly(history,now=None): return f"🗓️ *WEEKLY*\n{BR}\n📂 Closed trades: `{len(history)}`\n{BR2}"
def msg_test(ok,detail): return f"🧪 *DATA FEED TEST*\n{BR}\n{'🟢' if ok else '🔴'} `{detail}`\n📡 Yahoo Finance\n{BR2}"
def msg_news_pause(enabled): return f"📰 *NEWS PAUSE*\n{BR}\n{'🟡 ENABLED' if enabled else '🟢 DISABLED'}\n{BR2}"
def msg_news_refresh(): return f"📰 *NEWS CALENDAR REFRESH*\n{BR}\n🔄 Refresh requested.\n{BR2}"
def msg_backtest(): return f"📈 *BACKTEST ENGINE*\n{BR}\n🧪 Versioned strategy research only.\n🛡️ Paper trading remains active.\n{BR2}"
def msg_error(context,error): return f"⚠️ *ERROR — {context}*\n{BR}\n❌ `{str(error)[:700]}`\n🛡️ Paper mode remains active.\n{BR2}"
def reminder_message(original_text): return TelegramMessage("MSG-REMINDER-V1",f"🔔 *SIGNAL REMINDER*\n{BR}\n{original_text}\n{BR2}")
def send_message(message,config):
    if not message.text.strip(): raise TelegramTemplateError("Cannot send an empty Telegram message")
    data=parse.urlencode({"chat_id":config.chat_id,"text":message.text,"parse_mode":"Markdown"}).encode(); req=request.Request(f"https://api.telegram.org/bot{config.bot_token}/sendMessage",data=data,method="POST",headers={"Content-Type":"application/x-www-form-urlencoded"})
    with request.urlopen(req,timeout=15) as response:
        if response.status!=200: raise RuntimeError(f"Telegram API request failed: HTTP {response.status}")
__all__=["TelegramConfig","TelegramMessage","TelegramConfigurationError","TelegramTemplateError","signal_message_type","render_signal_message","send_message","signal_rejection_message","trade_closed_message","msg_start","msg_scan_started","msg_scan_result","msg_balance","msg_summary","msg_risk","msg_stats","msg_weekly","msg_test","msg_news_pause","msg_news_refresh","msg_backtest","msg_error","reminder_message","build_trade_fields"]
