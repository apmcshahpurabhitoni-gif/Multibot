"""MULTIBOT2 runtime: registry-driven strategies, one shared trade lifecycle."""
from __future__ import annotations
import json, logging, os, threading, time, warnings
from urllib import parse, request
from wsgiref.simple_server import make_server
import pandas as pd
from backtest import backtest_strategy
from config import *
from dashboard import build_dashboard_snapshot
from db import DatabaseManager
from news import NewsService
from reminders import ReminderService
from strategy_service import StrategyService
from strategies import discover_strategies
from telegram import TelegramConfig, TelegramMessage, msg_backtest, msg_balance, msg_error, msg_news_pause, msg_news_refresh, msg_risk, msg_scan_result, msg_scan_started, msg_start, msg_stats, msg_summary, msg_test, msg_weekly, send_message
from trading import AccountState
from trade_monitor import TradeMonitor
from strategy_scheduler import StrategyScheduler
from news_gate import NewsGate
from yahoo_provider import YahooProvider

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger=logging.getLogger("multibot2")
warnings.filterwarnings("ignore", message="The .*generic.* unit for NumPy timedelta is deprecated.*", category=DeprecationWarning, module="yfinance\\..*")
DB=DatabaseManager(settings.db_path); NEWS=NewsService(); ACCOUNTS={}; REMINDERS=None; STOP=threading.Event(); LOCK=threading.RLock(); NEWS_PAUSE_ENABLED=False
REGISTRY=None; SERVICE=None; TRADE_MONITOR=None; SCHEDULER=StrategyScheduler(); NEWS_GATE=NewsGate(NEWS, enabled=NEWS_PAUSE_ENABLED)
LAST_SCANS={}

def now(): return pd.Timestamp.now(tz=IST_TIMEZONE)
def validate_runtime_configuration():
    validate_configuration()
    if settings.timezone!=IST_TIMEZONE or settings.market_data_provider!="yahoo" or settings.freshness_hours!=1: raise ValueError("Locked runtime configuration was changed")
def init_state():
    global ACCOUNTS
    rows=DB.load_accounts(ACCOUNT_NAMES,ACCOUNT_SIZE_INR,now().date().isoformat())
    ACCOUNTS={n:AccountState(n,float(rows[n]["starting_balance"]),float(rows[n]["balance"]),float(rows[n]["planned_risk_used"]),int(rows[n]["trades_today"])) for n in ACCOUNT_NAMES}
def ensure_runtime():
    global REGISTRY,SERVICE,REMINDERS,TRADE_MONITOR
    validate_runtime_configuration()
    health=DB.market_data_cache_health()
    logger.info("Market data cache health | enabled=%s remote=%s reason=%s",health["enabled"],health["remote"],health["reason"])
    if not ACCOUNTS: init_state()
    if REGISTRY is None: REGISTRY=discover_strategies()
    if SERVICE is None: SERVICE=StrategyService(registry=REGISTRY,provider=YahooProvider(database=DB),database=DB,accounts=ACCOUNTS,news_gate=NEWS_GATE)
    if TRADE_MONITOR is None: TRADE_MONITOR=TradeMonitor(database=DB,price_lookup=lambda symbol: SERVICE.current_price(symbol),accounts=ACCOUNTS)
    if REMINDERS is None and settings.telegram_bot_token and settings.telegram_chat_id: REMINDERS=ReminderService(DB)
    with LOCK:
        for st in REGISTRY.all():
            LAST_SCANS.setdefault(
                st.manifest.id,
                {"status":"NOT_RUN","at":None,"checked":0,"directional":0,"sent":0,"errors":0},
            )
def run_strategy_cycle(strategy_id,*,now_at=None,send=True,period="30d"):
    ensure_runtime()
    current=now_at or now()
    started=time.monotonic()
    run_id=f"{strategy_id}_{int(current.timestamp()*1000)}"
    DB.record_scan_run(run_id,strategy_id,current.isoformat(),"RUNNING",{"checked":0,"directional":0,"sent":0,"errors":0})
    try:
        results=SERVICE.scan_and_dispatch(strategy_id,now=current,period=period,send=send)
    except Exception as exc:
        payload={"checked":0,"directional":0,"sent":0,"errors":1,"error":str(exc)}
        DB.record_scan_run(run_id,strategy_id,current.isoformat(),"FAILED",payload,now().isoformat())
        with LOCK: LAST_SCANS[strategy_id].update(status="ERROR",at=current.isoformat(),**payload)
        raise
    payload={"checked":len(results),"directional":sum(r.signal.is_directional for r in results),"sent":sum(r.sent for r in results),"errors":sum(r.reason.startswith("MARKET_DATA_ERROR") or r.reason=="TELEGRAM_FAILED" for r in results)}
    payload["buy"]=sum(r.signal.direction=="BUY" for r in results); payload["sell"]=sum(r.signal.direction=="SELL" for r in results); payload["no_signal"]=sum(not r.signal.is_directional for r in results)
    status="PARTIAL" if payload["errors"] else "OK"
    reasons={reason:sum(r.reason==reason for r in results) for reason in sorted({r.reason for r in results})}
    directional=[r for r in results if r.signal.is_directional]
    if directional:
        logger.info("Directional dispatch | strategy=%s | outcomes=%s",strategy_id,"; ".join("{}:{}:{}:sent={}".format(r.symbol,r.signal.direction,r.reason,r.sent) for r in directional))
    logger.info("Scan complete | strategy=%s | checked=%s | buy=%s | sell=%s | no_signal=%s | sent=%s | errors=%s | reasons=%s | elapsed_ms=%s",strategy_id,payload["checked"],payload["buy"],payload["sell"],payload["no_signal"],payload["sent"],payload["errors"],reasons,round((time.monotonic()-started)*1000))
    DB.record_scan_run(run_id,strategy_id,current.isoformat(),status,payload,now().isoformat())
    with LOCK:
        info=LAST_SCANS[strategy_id]
        info.update(
            status=status,
            at=current.isoformat(),
            checked=len(results),
            directional=sum(r.signal.is_directional for r in results),
            sent=sum(r.sent for r in results),
            errors=sum(r.reason.startswith("MARKET_DATA_ERROR") or r.reason=="TELEGRAM_FAILED" for r in results),
            reasons={reason:sum(r.reason==reason for r in results) for reason in sorted({r.reason for r in results})},
            elapsed_ms=round((time.monotonic()-started)*1000),
        )
    return results
def run_all_cycles(*,now_at=None,send=True,period="30d",force=False):
    ensure_runtime(); out=[]
    current=now_at or now()
    for st in REGISTRY.all():
        if force or SCHEDULER.is_due(st,current):
            out.extend(run_strategy_cycle(st.manifest.id,now_at=current,send=send,period=period))
    return out
def scanner_loop():
    while not STOP.is_set():
        try:
            run_all_cycles(send=True)
            if SERVICE is not None: SERVICE.notifier.retry_failed()
        except Exception: logger.exception("Strategy scan cycle failed")
        # Never sleep longer than the fastest registered strategy schedule.
        interval=settings.scan_interval_seconds
        if REGISTRY is not None:
            try: interval=min(interval,*[SCHEDULER.interval_seconds(st) for st in REGISTRY.all()])
            except Exception: logger.exception("Could not resolve strategy scan interval")
        STOP.wait(interval)
def monitor_once():
    ensure_runtime(); return TRADE_MONITOR.monitor_once(now=now())
def monitor_loop():
    while not STOP.is_set():
        try: monitor_once()
        except Exception: logger.exception("Monitor cycle failed")
        STOP.wait(settings.monitor_interval_seconds)
def _backtest_payload(strategy,symbol,period):
    ensure_runtime(); key=strategy.strip().lower(); st=REGISTRY.get(key); symbol=symbol.strip().upper()
    if symbol not in st.manifest.assets: raise ValueError(f"{key} does not support {symbol}")
    frame=SERVICE.engine.fetch(st,symbol,period=period); result=backtest_strategy(st,symbol,frame,account=st.manifest.account)
    m=result.metrics
    daily={}
    for sig in result.signals:
        d=sig.timestamp.tz_convert(IST_TIMEZONE).date().isoformat() if sig.timestamp.tzinfo else sig.timestamp.date().isoformat()
        daily.setdefault(d,{"buy":0,"sell":0,"total":0})
        if sig.direction=="BUY": daily[d]["buy"]+=1; daily[d]["total"]+=1
        elif sig.direction=="SELL": daily[d]["sell"]+=1; daily[d]["total"]+=1
    signals=[{"timestamp":x.timestamp.isoformat(),"direction":x.direction,"reason":x.reason,"entry":x.entry} for x in result.signals if x.is_directional][-200:]
    directional = [sig for sig in result.signals if sig.is_directional]
    buy_signals = sum(sig.direction == "BUY" for sig in directional)
    sell_signals = sum(sig.direction == "SELL" for sig in directional)
    trades_taken = int(m.number_of_trades)
    planned_risk = float(trades_taken * RISK_PER_TRADE_INR)
    return {"ok":True,"strategy":result.strategy,"strategy_id":st.manifest.id,"strategy_version":result.strategy_version,"symbol":symbol,"asset":BACKTEST_ASSETS[symbol],"period":period,"parameters":result.parameters,"candle_count":len(frame),"buy_signals":buy_signals,"sell_signals":sell_signals,"trades_taken":trades_taken,"planned_risk":planned_risk,"metrics":{"return_pct":m.return_pct,"max_drawdown_pct":m.max_drawdown_pct,"sharpe":m.sharpe,"sortino":m.sortino,"win_rate_pct":m.win_rate_pct,"profit_factor":m.profit_factor,"number_of_trades":m.number_of_trades,"average_trade":m.average_trade,"max_losing_streak":m.max_losing_streak,"exposure_pct":m.exposure_pct,"risk_adjusted_performance":m.risk_adjusted_performance,"rating":m.rating,"rating_label":m.rating_label,"breakdown":m.breakdown},"daily":[{"date":d,**v} for d,v in sorted(daily.items())],"signals":signals,"generated_at":now().isoformat()}
def _scan_snapshot():
    """Return one dashboard contract with aggregate and per-strategy scan state."""
    with LOCK:
        strategies = {key: dict(value) for key, value in LAST_SCANS.items()}
    if not strategies:
        return {
            "status": "NOT_RUN", "at": None, "checked": 0,
            "directional": 0, "sent": 0, "errors": 0,
            "strategies": {},
        }
    rows = list(strategies.values())
    completed = [row for row in rows if row.get("status") in {"OK","PARTIAL"}]
    latest_at = max((row.get("at") for row in completed if row.get("at")), default=None)
    if any(row.get("status") == "ERROR" for row in rows):
        status = "ERROR"
    elif completed:
        status = "COMPLETE"
    else:
        status = "NOT_RUN"
    return {
        "status": status,
        "at": latest_at,
        "checked": sum(int(row.get("checked", 0)) for row in completed),
        "directional": sum(int(row.get("directional", 0)) for row in completed),
        "sent": sum(int(row.get("sent", 0)) for row in completed),
        "errors": sum(int(row.get("errors", 0)) for row in rows),
        "strategies": strategies,
    }

def snapshot():
    ensure_runtime(); fresh=DB.load_accounts(ACCOUNT_NAMES,ACCOUNT_SIZE_INR,now().date().isoformat()); accounts=[AccountState(n,float(fresh[n]["starting_balance"]),float(fresh[n]["balance"]),float(fresh[n]["planned_risk_used"]),int(fresh[n]["trades_today"])) for n in ACCOUNT_NAMES]
    failed_deliveries=DB.failed_deliveries(20)
    return build_dashboard_snapshot(version=APP_VERSION,whats_new=WHAT_IS_NEW,accounts=accounts,signals=DB.load_signal_history(500),trades=DB.load_trades(),scan={**_scan_snapshot(),"history":DB.load_scan_runs(50)},health={"database":"SUPABASE+SQLITE" if DB.supabase_enabled else "SQLITE_FALLBACK","provider":"YAHOO","telegram":"CONFIGURED" if settings.telegram_bot_token else "DISABLED","telegram_failed_deliveries":len(failed_deliveries),"open_trades":len(DB.load_trades("OPEN")),"signal_lifecycle":"ENABLED"},strategies=REGISTRY.all())
def _json_response(start,payload,status="200 OK"): start(status,[("Content-Type","application/json"),("Cache-Control","no-store")]); return [json.dumps(payload,default=str).encode()]
def _sweep_diagnostic_payload(*, period="30d"):
    """Run the real Sweep V2 data -> prepare -> signal path without dispatching or sending."""
    ensure_runtime()
    strategy = REGISTRY.get("sweep_v2")
    current = now()
    rows = []
    totals = {"assets": 0, "ok": 0, "errors": 0, "directional": 0, "reasons": {}}
    for asset in LIVE_ASSETS:
        if asset.symbol not in strategy.manifest.assets:
            continue
        totals["assets"] += 1
        row = {"symbol": asset.symbol, "label": asset.label, "market": asset.market,
               "timeframe": asset.sweep_timeframe}
        try:
            frame = SERVICE.engine.fetch(strategy, asset.symbol, period=period)
            row["raw_candles"] = len(frame) if frame is not None else 0
            prepared = strategy.prepare_candles(asset.symbol, frame, now=current)
            row["prepared_candles"] = len(prepared) if prepared is not None else 0
            signal = strategy.generate_signal(asset.symbol, prepared, now=current)
            row.update({"status": "OK", "direction": signal.direction, "reason": signal.reason,
                        "timestamp": signal.timestamp.isoformat(), "entry": signal.entry,
                        "stop_loss": signal.stop_loss, "take_profit": signal.take_profit,
                        "metadata": signal.metadata})
            totals["ok"] += 1
            totals["directional"] += int(signal.is_directional)
            totals["reasons"][signal.reason] = totals["reasons"].get(signal.reason, 0) + 1
        except Exception as exc:
            row.update({"status": "ERROR", "error_type": type(exc).__name__, "error": str(exc),
                        "direction": None, "reason": "MARKET_DATA_ERROR"})
            totals["errors"] += 1
            totals["reasons"]["MARKET_DATA_ERROR"] = totals["reasons"].get("MARKET_DATA_ERROR", 0) + 1
        rows.append(row)
    return {"ok": True, "strategy": {"id": strategy.manifest.id, "name": strategy.manifest.name,
            "version": strategy.manifest.version}, "generated_at": current.isoformat(),
            "period": period, "totals": totals, "assets": rows}
def _calendar_payload(query):
    target=query.get("date",[None])[0]; impacts={x.strip().title() for x in query.get("impact",["All"])[0].split(",") if x.strip()} or {"All"}; return NEWS.get(target_date=target,impacts={"All"} if "All" in impacts else impacts,force=query.get("refresh")==["1"])
def web_server():
    root=os.path.dirname(__file__); files={"/":("dashboard.html","text/html; charset=utf-8"),"/dashboard":("dashboard.html","text/html; charset=utf-8"),"/app.js":("app.js","application/javascript"),"/styles.css":("styles.css","text/css")}
    def app(env,start):
        path=env.get("PATH_INFO","/"); query=parse.parse_qs(env.get("QUERY_STRING",""))
        if path=="/ping": start("200 OK",[("Content-Type","text/plain"),("Cache-Control","no-store")]); return [b"pong"]
        if path=="/api/health":
            try:
                ensure_runtime()
                payload={"ok":True,"status":"ONLINE","version":APP_VERSION,"timestamp":now().isoformat(),
                    "runtime":True,"database":"SUPABASE+SQLITE" if DB.supabase_enabled else "SQLITE_FALLBACK",
                    "scheduler":not STOP.is_set(),"strategies":len(REGISTRY.all()),
                    "provider":MARKET_DATA_PROVIDER,"telegram":"CONFIGURED" if settings.telegram_bot_token else "DISABLED"}
                return _json_response(start,payload)
            except Exception as exc:
                return _json_response(start,{"ok":False,"status":"DEGRADED","error":str(exc),"timestamp":now().isoformat()},"503 Service Unavailable")
        if path=="/api/dashboard":
            try:return _json_response(start,snapshot())
            except Exception as exc:return _json_response(start,{"ok":False,"error":str(exc)},"500 Internal Server Error")
        if path=="/api/diagnostics/sweep":
            try:return _json_response(start,_sweep_diagnostic_payload(period=query.get("period",["30d"])[0]))
            except Exception as exc:
                logger.exception("Sweep diagnostics failed")
                return _json_response(start,{"ok":False,"error_type":type(exc).__name__,"error":str(exc)},"500 Internal Server Error")
        if path in ("/api/calendar","/api/news"):
            try:return _json_response(start,_calendar_payload(query))
            except Exception as exc:return _json_response(start,{"ok":False,"error":str(exc)},"400 Bad Request")
        if path=="/api/backtest":
            try:
                ensure_runtime()
                default_strategy = REGISTRY.ids()[0]
                return _json_response(start,_backtest_payload(
                    query.get("strategy",[default_strategy])[0],
                    query.get("symbol",[LIVE_SYMBOLS[0]])[0],
                    query.get("period",["30d"])[0],
                ))
            except Exception as exc:
                logger.exception("Backtest request failed")
                return _json_response(start,{"ok":False,"error":str(exc)},"400 Bad Request")
        if path in files:
            name,typ=files[path]
            try: body=open(os.path.join(root,name),"rb").read()
            except OSError: start("404 Not Found",[("Content-Type","text/plain")]); return [b"Not found"]
            start("200 OK",[("Content-Type",typ),("Cache-Control","no-store")]); return [body]
        start("404 Not Found",[("Content-Type","text/plain")]); return [b"Not found"]
    make_server("0.0.0.0",int(os.getenv("PORT","10000")),app).serve_forever()
def _send_chat(chat_id,message):
    config=TelegramConfig.from_env(); target=TelegramConfig(config.bot_token,str(chat_id)); send_message(message if isinstance(message,TelegramMessage) else TelegramMessage("MSG-COMMAND-V1",message),target)
def _handle_command(chat_id,cmd):
    global NEWS_PAUSE_ENABLED
    try:
        if cmd in ("/start","/menu"): _send_chat(chat_id,msg_start())
        elif cmd in ("/check","/scan"): _send_chat(chat_id,msg_scan_started()); results=run_all_cycles(send=True,force=True); _send_chat(chat_id,msg_scan_result(sum(r.sent for r in results),sum(len(st.manifest.assets) for st in REGISTRY.all())))
        elif cmd=="/balance": _send_chat(chat_id,msg_balance(ACCOUNTS))
        elif cmd=="/summary": _send_chat(chat_id,msg_summary(DB.load_trades("OPEN"),DB.load_trades("CLOSED")))
        elif cmd=="/risk": _send_chat(chat_id,msg_risk(DB.load_trades("OPEN")))
        elif cmd=="/stats": _send_chat(chat_id,msg_stats(DB.load_trades("CLOSED")))
        elif cmd=="/weekly": _send_chat(chat_id,msg_weekly(DB.load_trades("CLOSED")))
        elif cmd=="/newspause":
            NEWS_PAUSE_ENABLED=not NEWS_PAUSE_ENABLED
            NEWS_GATE.enabled=NEWS_PAUSE_ENABLED
            _send_chat(chat_id,msg_news_pause(NEWS_PAUSE_ENABLED))
        elif cmd=="/refreshnews": NEWS.refresh(); _send_chat(chat_id,msg_news_refresh())
        elif cmd=="/backtest": _send_chat(chat_id,msg_backtest())
        elif cmd=="/test": ensure_runtime(); ok=SERVICE.engine.provider.fetch("RELIANCE.NS",period="2d",interval="1d",validate_hourly=False) is not None; _send_chat(chat_id,msg_test(ok,"Yahoo Finance responded." if ok else "Yahoo Finance did not respond."))
    except Exception as exc:
        logger.exception("Telegram command failed")
        try:
            _send_chat(chat_id,msg_error(f"COMMAND {cmd}",exc))
        except Exception:
            logger.exception("Failed to send Telegram command error response")
def _telegram_api_call(token,method,payload=None,timeout=15):
    data=parse.urlencode(payload or {}).encode(); req=request.Request(f"https://api.telegram.org/bot{token}/{method}",data=data,method="POST",headers={"Content-Type":"application/x-www-form-urlencoded"})
    with request.urlopen(req,timeout=timeout) as response: body=json.loads(response.read())
    if not body.get("ok"): raise RuntimeError(body.get("description") or f"Telegram API {method} failed")
    return body
def _prepare_telegram_polling(token):
    _telegram_api_call(token,"deleteWebhook",{"drop_pending_updates":"false"}); me=_telegram_api_call(token,"getMe").get("result",{}); logger.info("Telegram polling ready: bot=@%s id=%s",me.get("username","unknown"),me.get("id","unknown"))
def telegram_commands():
    token=settings.telegram_bot_token
    if not token:return
    try:_prepare_telegram_polling(token)
    except Exception as exc: logger.warning("Telegram polling initialization failed: %s",exc); STOP.wait(30)
    offset=0; conflict_logged_at=0.0
    while not STOP.is_set():
        try:
            data=_telegram_api_call(token,"getUpdates",{"timeout":20,"offset":offset},timeout=30)
            for update in data.get("result",[]):
                offset=int(update["update_id"])+1; message=update.get("message",{}); chat_id=message.get("chat",{}).get("id"); text=str(message.get("text","")); cmd=text.split()[0].split("@")[0].lower() if text else ""
                if chat_id and str(chat_id)==str(settings.telegram_chat_id) and cmd: threading.Thread(target=_handle_command,args=(str(chat_id),cmd),daemon=True).start()
        except Exception as exc:
            msg=str(exc)
            if "409" in msg or "conflict" in msg.lower():
                t=time.monotonic()
                if t-conflict_logged_at>=60: logger.warning("Telegram polling conflict: %s",msg); conflict_logged_at=t
                STOP.wait(30)
            else: logger.warning("Telegram polling failed: %s",msg); STOP.wait(5)
def _telegram_command_polling_enabled():
    # Signal delivery uses sendMessage and does not require getUpdates polling.
    # Polling is opt-in so another Telegram client cannot silently conflict with
    # the scanner's primary signal-delivery runtime.
    return os.getenv("TELEGRAM_COMMAND_POLLING", "true").strip().lower() in {"1","true","yes","on"}

def main():
    ensure_runtime()
    threading.Thread(target=web_server,daemon=True,name="dashboard").start()
    threading.Thread(target=scanner_loop,daemon=True,name="scanner").start()
    threading.Thread(target=monitor_loop,daemon=True,name="monitor").start()
    if settings.telegram_bot_token and settings.telegram_chat_id:
        if _telegram_command_polling_enabled():
            threading.Thread(target=telegram_commands,daemon=True,name="telegram").start()
            logger.info("Telegram command polling enabled")
        else:
            logger.info("Telegram command polling disabled; signal delivery remains enabled")
        if REMINDERS is not None:
            REMINDERS.start()
    logger.info("MULTIBOT2 %s started: %d assets, Yahoo, %d plug-in strategies, 1h freshness, paper mode",APP_VERSION,len(LIVE_ASSETS),len(REGISTRY.all()))
    while True: time.sleep(3600)
if __name__=="__main__": main()
