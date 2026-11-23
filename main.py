"""MULTIBOT2 runtime: registry-driven strategies, one shared trade lifecycle."""
from __future__ import annotations
import errno, hmac, json, logging, os, signal as os_signal, threading, time, uuid, warnings
from urllib import parse, request
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server
import pandas as pd
from backtest import backtest_strategy
from config import *
from dashboard import build_dashboard_snapshot
from db import DatabaseManager
from news import NewsService
from reminders import ReminderService
import bot_settings
import channels
from strategy_service import RuntimeLeadershipError, StrategyService
from strategies import discover_strategies
from sweep_engine import last_quarantine
from telegram import TelegramConfig, TelegramMessage, msg_backtest, msg_balance, msg_error, msg_news_pause, msg_news_refresh, msg_risk, msg_scan_error, msg_scan_result, msg_scan_started, msg_start, msg_whats_new, msg_stats, msg_summary, msg_test, msg_weekly, send_message
from trading import AccountState
from trade_monitor import TradeMonitor
from strategy_scheduler import StrategyScheduler
from news_gate import NewsGate
from yahoo_provider import YahooProvider

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger=logging.getLogger("multibot2")
warnings.filterwarnings("ignore", message="The .*generic.* unit for NumPy timedelta is deprecated.*", category=DeprecationWarning, module="yfinance\\..*")
DB=DatabaseManager(settings.db_path); _CONFIG_DB=DB if DB.turso_enabled else None; bot_settings.configure_database(_CONFIG_DB); channels.configure_database(_CONFIG_DB); NEWS=NewsService(); ACCOUNTS={}; REMINDERS=None; STOP=threading.Event(); LOCK=threading.RLock(); NEWS_PAUSE_ENABLED=False
REGISTRY=None; SERVICE=None; TRADE_MONITOR=None; SCHEDULER=StrategyScheduler(); NEWS_GATE=NewsGate(NEWS, enabled=NEWS_PAUSE_ENABLED)
LAST_SCANS={}
LAST_PING_AT=None
SETTINGS_LOADED=False
# A Turso-backed lease elects exactly one active worker across overlapping
# deployment containers. Other instances may serve the dashboard in standby.
RUNTIME_LEASE_TTL_SECONDS=60
RUNTIME_LEASE_HEARTBEAT_SECONDS=15
RUNTIME_OWNER_ID=None
RUNTIME_LEADER=False
RUNTIME_LEASE_REQUIRED=False
RUNTIME_LEASE_LAST_VERIFIED=0.0
RUNTIME_LEASE_VERIFY_INTERVAL_SECONDS=5.0
RUNTIME_LEASE_VERIFY_LOCK=threading.Lock()
# A brief DNS/connect failure must not shut trading down. The deferral is a
# wall-clock window, not a call budget: one scan calls the guard once per asset,
# so a counter would be spent in milliseconds. The window opens at the first
# transient failure and trading continues until it closes.
RUNTIME_LEASE_TRANSIENT_GRACE_SECONDS=60.0
RUNTIME_LEASE_TRANSIENT_UNTIL=0.0
RUNTIME_LEASE_TRANSIENT_FAILURES=0
HTTP_SERVER=None

class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    """Serve dashboard requests concurrently so one slow API call cannot block the UI."""
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = True
REMINDER_THREAD=None
WORKER_THREADS={}
_MAIN_STARTED=False
_MAIN_START_LOCK=threading.Lock()

def now(): return pd.Timestamp.now(tz=IST_TIMEZONE)
def validate_runtime_configuration():
    validate_configuration()
    if settings.timezone!=IST_TIMEZONE or settings.market_data_provider!="yahoo" or settings.freshness_hours!=1: raise ValueError("Locked runtime configuration was changed")
def init_state():
    rows=DB.load_accounts(account_names(),ACCOUNT_SIZES,now().date().isoformat())
    fresh={n:AccountState(n,float(rows[n]["starting_balance"]),float(rows[n]["balance"]),float(rows[n]["planned_risk_used"]),int(rows[n]["trades_today"])) for n in account_names()}
    # Mutated in place, never rebound: StrategyService and TradeMonitor are
    # handed this exact dict at construction, so replacing it would leave them
    # holding accounts the dashboard no longer knows about.
    for gone in [name for name in ACCOUNTS if name not in fresh]: ACCOUNTS.pop(gone,None)
    ACCOUNTS.update(fresh)
def refresh_runtime_accounts():
    """Re-read account rows after the account list changed.

    Adding or removing an account changes what the scan loop and the monitor
    hold in memory, not just what config says. init_state() mutates the shared
    dict, so one call is enough.
    """
    if REGISTRY is None or SERVICE is None: return
    with LOCK: init_state()
def ensure_runtime():
    global REGISTRY,SERVICE,REMINDERS,TRADE_MONITOR,SETTINGS_LOADED
    # Install anything saved from the Tools screen before anything can trade,
    # then let validate_runtime_configuration() re-check its invariants.
    if not SETTINGS_LOADED:
        bot_settings.load(); SETTINGS_LOADED=True
    validate_runtime_configuration()
    health=DB.market_data_cache_health()
    logger.info("Market data cache health | enabled=%s remote=%s reason=%s",health["enabled"],health["remote"],health["reason"])
    if not ACCOUNTS: init_state()
    if REGISTRY is None: REGISTRY=discover_strategies()
    if SERVICE is None: SERVICE=StrategyService(registry=REGISTRY,provider=YahooProvider(database=DB),database=DB,accounts=ACCOUNTS,news_gate=NEWS_GATE,runtime_guard=_require_runtime_leader)
    if TRADE_MONITOR is None: TRADE_MONITOR=TradeMonitor(database=DB,price_lookup=lambda symbol: SERVICE.current_price(symbol),accounts=ACCOUNTS)
    if REMINDERS is None and settings.telegram_bot_token and settings.telegram_chat_id: REMINDERS=ReminderService(DB)
    with LOCK:
        for st in REGISTRY.all():
            LAST_SCANS.setdefault(
                st.manifest.id,
                {"status":"NOT_RUN","at":None,"checked":0,"directional":0,"sent":0,"errors":0},
            )
def _require_runtime_leader():
    global RUNTIME_LEADER,RUNTIME_LEASE_LAST_VERIFIED,RUNTIME_LEASE_TRANSIENT_FAILURES,RUNTIME_LEASE_TRANSIENT_UNTIL
    if not RUNTIME_LEASE_REQUIRED:
        return
    if not RUNTIME_LEADER or STOP.is_set() or not RUNTIME_OWNER_ID:
        raise RuntimeLeadershipError("This process is not the active MULTIBOT2 runtime leader")
    # While the transient grace window is open, skip the remote read entirely:
    # a scan touches this guard once per asset, so retrying per call would hammer
    # a failing endpoint and exhaust any call-count budget immediately.
    if RUNTIME_LEASE_TRANSIENT_UNTIL and time.monotonic()<RUNTIME_LEASE_TRANSIENT_UNTIL:
        return
    # Guard every asset and dispatch boundary, but amortize the remote read:
    # the lease heartbeat is 15s and a verification is cached for at most 5s.
    # A process resuming after a long pause always re-checks before trading.
    verified_at=time.monotonic()
    if verified_at-RUNTIME_LEASE_LAST_VERIFIED<RUNTIME_LEASE_VERIFY_INTERVAL_SECONDS:
        return
    with RUNTIME_LEASE_VERIFY_LOCK:
        verified_at=time.monotonic()
        if verified_at-RUNTIME_LEASE_LAST_VERIFIED<RUNTIME_LEASE_VERIFY_INTERVAL_SECONDS:
            return
        try:
            owned=DB.runtime_lease_is_owned(RUNTIME_OWNER_ID)
        except Exception as exc:
            # A transient DNS/connect failure is not lost leadership: open a
            # time-bounded grace window, keep trading, and only fail closed once
            # that window has actually elapsed.
            if DB.is_transient_database_error(exc):
                RUNTIME_LEASE_TRANSIENT_FAILURES+=1
                if not RUNTIME_LEASE_TRANSIENT_UNTIL:
                    RUNTIME_LEASE_TRANSIENT_UNTIL=time.monotonic()+RUNTIME_LEASE_TRANSIENT_GRACE_SECONDS
                    logger.warning(
                        "Runtime lease verification deferred | transient database error | grace_seconds=%s | error=%s",
                        RUNTIME_LEASE_TRANSIENT_GRACE_SECONDS,exc,
                    )
                    return
                if time.monotonic()<RUNTIME_LEASE_TRANSIENT_UNTIL:
                    return
            RUNTIME_LEADER=False
            STOP.set()
            if REMINDERS is not None: REMINDERS.stop()
            raise RuntimeLeadershipError("Runtime lease could not be verified; trading stopped")
        if not owned:
            RUNTIME_LEADER=False
            STOP.set()
            if REMINDERS is not None: REMINDERS.stop()
            raise RuntimeLeadershipError("Runtime lease ownership was lost; trading stopped")
        RUNTIME_LEASE_TRANSIENT_FAILURES=0
        RUNTIME_LEASE_TRANSIENT_UNTIL=0.0
        RUNTIME_LEASE_LAST_VERIFIED=verified_at

def run_strategy_cycle(strategy_id,*,now_at=None,send=True,period="30d"):
    _require_runtime_leader()
    ensure_runtime()
    current=now_at or now()
    started=time.monotonic()
    run_id=f"{strategy_id}_{int(current.timestamp()*1000)}"
    DB.record_scan_run(run_id,strategy_id,current.isoformat(),"RUNNING",{"checked":0,"directional":0,"sent":0,"errors":0})
    try:
        results=SERVICE.scan_and_dispatch(strategy_id,now=current,period=period,send=send)
    except Exception as exc:
        payload={"checked":0,"directional":0,"sent":0,"errors":1,"error":str(exc)}
        try:
            DB.record_scan_run(run_id,strategy_id,current.isoformat(),"FAILED",payload,now().isoformat())
        except Exception:
            logger.exception("Failed to persist FAILED scan history | strategy=%s run_id=%s",strategy_id,run_id)
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
    try:
        DB.record_scan_run(run_id,strategy_id,current.isoformat(),status,payload,now().isoformat())
    except Exception:
        # The scan and its side effects have already completed. Do not replay
        # trading or Telegram delivery because only history finalization failed.
        logger.exception("Scan completed but final history persistence failed | strategy=%s run_id=%s",strategy_id,run_id)
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
    _notify_scan(run_id,strategy_id,payload,results)
    return results
def run_all_cycles(*,now_at=None,send=True,period="30d",force=False):
    _require_runtime_leader()
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
    _require_runtime_leader()
    ensure_runtime(); return TRADE_MONITOR.monitor_once(now=now())
def monitor_loop():
    while not STOP.is_set():
        try: monitor_once()
        except Exception: logger.exception("Monitor cycle failed")
        STOP.wait(settings.monitor_interval_seconds)
def _backtest_payload(strategy,symbol,period):
    ensure_runtime(); key=strategy.strip().lower(); st=REGISTRY.get(key); symbol=symbol.strip().upper()
    if symbol not in st.manifest.assets: raise ValueError(f"{key} does not support {symbol}")
    frame=SERVICE.engine.fetch(st,symbol,period=period)
    # Backtests route on the same table as live dispatch, so a backtest of an
    # asset is charged to the account that would actually trade it.
    account=resolve_account(key,LIVE_ASSET_MAP[symbol],pd.Timestamp.now(tz=IST_TIMEZONE),st.manifest.account)
    result=backtest_strategy(st,symbol,frame,account=account)
    m=result.metrics
    daily={}
    for sig in result.signals:
        d=sig.timestamp.tz_convert(IST_TIMEZONE).date().isoformat() if sig.timestamp.tzinfo else sig.timestamp.date().isoformat()
        daily.setdefault(d,{"buy":0,"sell":0,"total":0})
        if sig.direction=="BUY": daily[d]["buy"]+=1; daily[d]["total"]+=1
        elif sig.direction=="SELL": daily[d]["sell"]+=1; daily[d]["total"]+=1
    signals=[{
        "timestamp":x.timestamp.isoformat(),"direction":x.direction,"reason":x.reason,
        "entry":x.entry,"stop_loss":x.stop_loss,"take_profit":x.take_profit,
        "symbol":x.symbol,"strategy":x.strategy,"strategy_version":x.version,
        "timeframe":x.timeframe,"source":"BACKTEST"
    } for x in result.signals if x.is_directional][-200:]
    directional = [sig for sig in result.signals if sig.is_directional]
    buy_signals = sum(sig.direction == "BUY" for sig in directional)
    sell_signals = sum(sig.direction == "SELL" for sig in directional)
    trades_taken = int(m.number_of_trades)
    planned_risk = float(trades_taken * RISK_PER_TRADE_INR)
    equity = float(result.starting_account)
    equity_curve = [{"timestamp": frame.index[0].isoformat() if len(frame) else now().isoformat(), "equity": equity}]
    for trade in result.trades:
        equity += float(trade.pnl)
        equity_curve.append({"timestamp": trade.timestamp.isoformat(), "equity": round(equity, 2)})
    return {"ok":True,"strategy":result.strategy,"strategy_id":st.manifest.id,"strategy_version":result.strategy_version,"symbol":symbol,"asset":BACKTEST_ASSETS[symbol],"period":period,"parameters":result.parameters,"candle_count":len(frame),"buy_signals":buy_signals,"sell_signals":sell_signals,"trades_taken":trades_taken,"planned_risk":planned_risk,"equity_curve":equity_curve,"metrics":{"return_pct":m.return_pct,"max_drawdown_pct":m.max_drawdown_pct,"sharpe":m.sharpe,"sortino":m.sortino,"win_rate_pct":m.win_rate_pct,"profit_factor":m.profit_factor,"number_of_trades":m.number_of_trades,"average_trade":m.average_trade,"max_losing_streak":m.max_losing_streak,"exposure_pct":m.exposure_pct,"risk_adjusted_performance":m.risk_adjusted_performance,"rating":m.rating,"rating_label":m.rating_label,"breakdown":m.breakdown},"daily":[{"date":d,**v} for d,v in sorted(daily.items())],"signals":signals,"trades":[{"timestamp":x.timestamp.isoformat(),"direction":x.direction,"entry":x.entry,"exit":x.exit,"pnl":x.pnl,"bars_held":x.bars_held} for x in result.trades][-200:],"generated_at":now().isoformat()}
def _scan_error_alert_state(strategy_ids, entries=None):
    """Persisted incident rows for the dashboard's scan diagnostics (no secrets).

    `entries` is the preloaded {strategy_id: row} map from the single dashboard
    read; without it each strategy costs its own Turso round trip.
    """
    ids = tuple(strategy_ids)
    if entries is None:
        try:
            entries = DB.load_scan_error_alerts(ids)
        except Exception as exc:
            # Scan diagnostics are not worth failing the whole dashboard over.
            if not DB.is_transient_database_error(exc):
                raise
            entries = {}
    state = {}
    for strategy_id in ids:
        entry = entries.get(strategy_id)
        if not entry:
            continue
        state[strategy_id] = {
            "fingerprint": entry["fingerprint"],
            "first_sent_at": entry["first_sent_at"],
            "last_sent_at": entry["last_sent_at"],
            "suppressed": int(entry["suppressed"]),
            "updated_at": entry["updated_at"],
        }
    return state

def _scan_snapshot(error_alerts=None):
    """Return one dashboard contract with aggregate and per-strategy scan state."""
    with LOCK:
        strategies = {key: dict(value) for key, value in LAST_SCANS.items()}
    if not strategies:
        return {
            "status": "NOT_RUN", "at": None, "checked": 0,
            "directional": 0, "sent": 0, "errors": 0,
            "strategies": {}, "error_alerts": _scan_error_alert_state([], error_alerts or {}),
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
        "error_alerts": _scan_error_alert_state(list(strategies), error_alerts),
    }

_SNAPSHOT_NO_FALLBACK=object()

def _dashboard_snapshot_stage(name,operation,*,fallback=_SNAPSHOT_NO_FALLBACK,degraded=None,attempts=3):
    """Log each snapshot stage so a stalled API request has a precise last marker.

    A brief Turso/DNS outage must not turn the dashboard into a 500: transient
    database errors are retried on a fresh connection, and a section that still
    cannot be read returns a degraded value the browser can render instead of
    aborting the whole snapshot.
    """
    started=time.monotonic()
    logger.info("Dashboard snapshot stage started | stage=%s",name)
    for attempt in range(max(1,int(attempts))):
        try:
            result=operation()
        except Exception as exc:
            if DB.is_transient_database_error(exc) and attempt+1<attempts:
                logger.warning(
                    "Dashboard snapshot stage retry | stage=%s | attempt=%s/%s | error=%s",
                    name,attempt+1,attempts,exc,
                )
                time.sleep(0.2*(2**attempt))
                continue
            # Degrade only for a transport blip. A permanent error (missing
            # table, bad SQL) must still surface instead of silently rendering
            # an empty dashboard.
            if fallback is _SNAPSHOT_NO_FALLBACK or not DB.is_transient_database_error(exc):
                logger.exception("Dashboard snapshot stage failed | stage=%s | elapsed_ms=%s",name,round((time.monotonic()-started)*1000))
                raise
            logger.warning(
                "Dashboard snapshot stage degraded | stage=%s | elapsed_ms=%s | error=%s",
                name,round((time.monotonic()-started)*1000),exc,
            )
            if degraded is not None and name not in degraded:
                degraded.append(name)
            return fallback
        logger.info("Dashboard snapshot stage complete | stage=%s | elapsed_ms=%s",name,round((time.monotonic()-started)*1000))
        return result

# The dashboard's default snapshot shows the most recent 500 signals; the
# read is one query on the shared dashboard connection.
SIGNAL_HISTORY_LIMIT=500
# The page refreshes every 30s, so a snapshot younger than this is served from
# memory instead of rebuilding and paying another Turso handshake per request.
# The TTL clears the poll interval with margin, so a page refresh is a cache hit
# (an entry is already 30s old when the next refresh arrives) while a long-idle
# tab still rebuilds. Scan cycles run every few minutes, so this staleness is
# invisible on the dashboard.
SNAPSHOT_CACHE_TTL_SECONDS=35.0
_SNAPSHOT_CACHE={"payload":None,"at":0.0}
_SNAPSHOT_CACHE_LOCK=threading.Lock()

def _account_fallback():
    """Last-resort account state when the durable read is unavailable."""
    return {name:{"starting_balance":acct.starting_balance,"balance":acct.balance,
                  "planned_risk_used":acct.planned_risk_used,"trades_today":acct.trades_today}
            for name,acct in ACCOUNTS.items()}

def snapshot():
    """Return the dashboard payload, reusing a recent one when it is still fresh."""
    started=time.monotonic()
    with _SNAPSHOT_CACHE_LOCK:
        cached=_SNAPSHOT_CACHE["payload"]
        cached_at=_SNAPSHOT_CACHE["at"]
    if cached is not None and started-cached_at<SNAPSHOT_CACHE_TTL_SECONDS:
        logger.info("Dashboard snapshot cache hit | age_ms=%s",round((started-cached_at)*1000))
        return cached
    payload=_build_dashboard_payload(started)
    # Never cache a degraded payload: the next request should retry the read
    # instead of serving empty sections for the whole TTL.
    if not payload.get("degraded"):
        with _SNAPSHOT_CACHE_LOCK:
            _SNAPSHOT_CACHE["payload"]=payload
            _SNAPSHOT_CACHE["at"]=time.monotonic()
    return payload

def _build_dashboard_payload(started):
    degraded=[]
    _dashboard_snapshot_stage("runtime_init",ensure_runtime)
    names=account_names()
    today=now().date().isoformat()
    with LOCK: strategy_ids=tuple(LAST_SCANS)
    # One connection and one handshake for every section. Each Turso connection
    # costs most of a second, so the per-section reads used to dominate the
    # request even though every section is small.
    bundle=_dashboard_snapshot_stage(
        "dashboard_reads",
        lambda:DB.dashboard_reads(
            names=names,starting_balance=ACCOUNT_SIZES,today=today,
            signal_limit=SIGNAL_HISTORY_LIMIT,strategy_ids=strategy_ids,
        ),
        fallback=None,
        degraded=degraded,
        attempts=1,
    )
    if bundle is None:
        # Degrade straight away. Re-running the sections individually would pay
        # another handshake per section while Turso is already unreachable.
        fresh=_account_fallback()
        signals=[]
        trades=[]
        failed_deliveries=[]
        scan_alerts={}
        scan_history=[]
    else:
        fresh=bundle["accounts"]
        signals=bundle["signals"]
        trades=bundle["trades"]
        failed_deliveries=bundle["failed_deliveries"]
        scan_alerts=bundle["scan_error_alerts"]
        scan_history=bundle["scan_runs"]
    accounts=[AccountState(n,float(fresh[n]["starting_balance"]),float(fresh[n]["balance"]),float(fresh[n]["planned_risk_used"]),int(fresh[n]["trades_today"])) for n in names if n in fresh]
    scan=_dashboard_snapshot_stage("scan_state",lambda:_scan_snapshot(scan_alerts))
    payload=build_dashboard_snapshot(
        version=APP_VERSION,
        whats_new=WHAT_IS_NEW,
        accounts=accounts,
        signals=signals,
        trades=trades,
        scan={**scan,"history":scan_history},
        health={
            "database":"TURSO" if DB.turso_enabled else "LOCAL_SQLITE",
            "provider":"YAHOO",
            "telegram":"CONFIGURED" if settings.telegram_bot_token else "DISABLED",
            "telegram_failed_deliveries":len(failed_deliveries),
            "open_trades":sum(1 for trade in trades if str(trade.get("status","")).upper()=="OPEN"),
            "signal_lifecycle":"ENABLED",
            "degraded_sections":list(degraded),
        },
        strategies=REGISTRY.all(),
    )
    payload["degraded"]=bool(degraded)
    logger.info(
        "Dashboard snapshot complete | elapsed_ms=%s | signals=%s | trades=%s | degraded=%s",
        round((time.monotonic()-started)*1000),len(signals),len(trades),degraded or "none",
    )
    return payload
# Scan-level error alerts are edge-triggered and durable: an asset outage that
# fails every sweep must not post one bubble per sweep, and a Render redeploy or
# process restart must not forget an open incident. The incident record lives in
# db.scan_error_alerts (Turso primary, local SQLite for development), keyed per strategy:
# the first scan with errors alerts; repeats with the same failing-asset set and
# error classes stay silent (every sweep still logs full technical detail and
# records a scan_runs row); a changed failure set alerts immediately; an
# identical failure set re-alerts at most once per SCAN_ERROR_REPEAT_SECONDS.
# A clean scan clears the incident.
SCAN_ERROR_REPEAT_SECONDS = 3600

def scan_error_alert_decision(entry, fingerprint, *, now, repeat_seconds=SCAN_ERROR_REPEAT_SECONDS):
    """Decide what to do for one scan's error fingerprint.

    Pure function over the *persisted* incident row so the same decision can be
    reproduced after a restart, a redeploy or from another worker:
      send     -> no open incident, or a different affected asset/error class
      suppress -> identical open incident inside the repeat window
      reminder -> identical open incident after the window (bounded: one send
                  per window, because the reminder refreshes last_sent_at)
    """
    if entry is None or entry.get("fingerprint") != fingerprint:
        return "send"
    try:
        last = pd.Timestamp(entry.get("last_sent_at"))
    except Exception:
        return "send"
    if last.tzinfo is None:
        last = last.tz_localize("UTC")
    if (now - last).total_seconds() >= repeat_seconds:
        return "reminder"
    return "suppress"

def _short_market_reason(text):
    """One human phrase for a market-data failure; raw exceptions stay in logs."""
    lowered = str(text).lower()
    if "invalid values" in lowered or "must be positive" in lowered or "invalid high" in lowered or "invalid low" in lowered:
        return "invalid OHLC"
    if "no data" in lowered:
        return "no market data"
    if "backoff" in lowered or "rate limit" in lowered or "rate-limit" in lowered:
        return "rate-limit backoff"
    if "duplicate" in lowered:
        return "duplicate candles"
    if "missing required ohlc" in lowered or "missing ohlc" in lowered:
        return "missing OHLC columns"
    if "timezone" in lowered:
        return "bad timestamps"
    if "telegram" in lowered:
        return "telegram delivery failed"
    return "market data error"

def _scan_error_entries(results):
    """Asset-first alert entries built from signal metadata (never raw traces)."""
    entries = []
    for result in results:
        reason = getattr(result, "reason", "") or ""
        signal = getattr(result, "signal", None)
        metadata = getattr(signal, "metadata", None)
        diagnostics = (metadata or {}).get("diagnostics") if isinstance(metadata, dict) else None
        diagnostics = diagnostics or {}
        symbol = str(getattr(result, "symbol", "") or "")
        asset = LIVE_ASSET_MAP.get(symbol.strip().upper())
        label = asset.label if asset is not None else symbol
        is_market = reason.startswith("MARKET_DATA_ERROR")
        detail = diagnostics.get("error") or reason.split(":", 1)[-1].strip() or reason
        candle = None
        failing = diagnostics.get("failing_candle")
        if failing:
            try:
                timestamp = pd.Timestamp(failing)
                if timestamp.tzinfo is None:
                    timestamp = timestamp.tz_localize(IST_TIMEZONE)
                candle = timestamp.tz_convert(IST_TIMEZONE).strftime("%d %b %Y %H:%M IST")
            except Exception:
                candle = str(failing)
        entries.append({
            "heading": "MARKET DATA ERROR" if is_market else "DELIVERY ERROR",
            "asset": label,
            "symbol": symbol,
            "reason": _short_market_reason(detail) if is_market else "telegram delivery failed",
            "candle": candle,
        })
    return entries

def _notify_scan(run_id,strategy_id,payload,results,*,at=None):
    """Tell subscribed channels how one strategy's scan ended.

    Scan events are opt-in per channel (channels.py): the scanner runs every few
    minutes, so only a channel that explicitly asked for SCAN or ERROR gets this
    traffic -- the delivery fan-out never falls back to the default Telegram chat
    for SCAN, which is what posted a "Scan complete" bubble every sweep.
    `audit=False` because a scan run has no signal_events row, and
    signal_deliveries.signal_id is a foreign key into that table.

    Repeated ERROR notifications are deduplicated by the persisted incident in
    db.scan_error_alerts (see scan_error_alert_decision): strict validation and
    the per-sweep technical logs are unchanged; only the chat bubble is bounded,
    and the bubble names each affected asset with a short reason instead of
    echoing raw exceptions.
    """
    if SERVICE is None: return
    try:
        if payload.get("errors"):
            error_results=[r for r in results if getattr(r,"reason","").startswith("MARKET_DATA_ERROR") or getattr(r,"reason","")=="TELEGRAM_FAILED"]
            categories=sorted({r.reason.split(":")[0].strip() for r in error_results})
            symbols=sorted({r.symbol for r in error_results})
            fingerprint="|".join(categories+["@"]+symbols)
            current=at or now()
            entry=DB.load_scan_error_alert(strategy_id)
            decision=scan_error_alert_decision(entry,fingerprint,now=current)
            if decision=="suppress":
                DB.bump_scan_error_alert_suppression(strategy_id)
                refreshed=DB.load_scan_error_alert(strategy_id) or {}
                logger.info("Scan error alert suppressed | strategy=%s | errors=%s | identical failure set already reported | suppressed=%s",strategy_id,payload.get("errors"),refreshed.get("suppressed"))
                return
            message=TelegramMessage("MSG-SCAN-ERROR-V1",msg_scan_error(strategy_id,_scan_error_entries(error_results)))
            delivered=SERVICE.notifier.deliver(signal_id=f"scan:{run_id}",message=message,kind="ERROR",metadata={"strategy":strategy_id,**payload},audit=False)
            if delivered:
                first_sent_at=(entry.get("first_sent_at") if decision=="reminder" and entry else None) or current.isoformat()
                DB.save_scan_error_alert(strategy_id,fingerprint,first_sent_at=first_sent_at,last_sent_at=current.isoformat(),suppressed=0,updated_at=current.isoformat())
            else:
                # Nothing reached chat: keep the incident open so the next scan
                # retries instead of silently swallowing the first alert.
                logger.info("Scan error alert not delivered; incident not recorded | strategy=%s",strategy_id)
            return
        if DB.load_scan_error_alert(strategy_id):
            DB.clear_scan_error_alert(strategy_id)
            logger.info("Scan error alert cleared after clean scan | strategy=%s",strategy_id)
        message=TelegramMessage("MSG-SCAN-COMPLETE-V1",msg_scan_result(payload.get("sent",0),payload.get("checked",0)))
        SERVICE.notifier.deliver(signal_id=f"scan:{run_id}",message=message,kind="SCAN",metadata={"strategy":strategy_id,**payload},audit=False)
    except Exception:
        logger.exception("Scan notification failed")

def _summary_state_path():
    return os.getenv("SUMMARY_STATE_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)),"notification_summary_state.json")

def _load_summary_state():
    try:
        with open(_summary_state_path(),"r",encoding="utf-8") as handle:
            raw=json.load(handle)
        return raw if isinstance(raw,dict) else {}
    except (OSError,json.JSONDecodeError):
        return {}

def _save_summary_state(state):
    path=_summary_state_path()
    try:
        tmp=path+".tmp"
        with open(tmp,"w",encoding="utf-8") as handle: json.dump(state,handle,indent=2)
        os.replace(tmp,path)
    except OSError as exc:
        logger.warning("Summary state could not be persisted: %s",exc)

def due_summaries(current,state,*,daily_hour=None,weekly_day=None):
    """Which periodic summaries are due at `current`, given what already went out.

    Pure on purpose: the daily/weekly boundary is the kind of logic that silently
    sends twice (or never) if it is only reachable through a running thread.
    `weekly_day` uses Python's Monday=0 convention; the default is Sunday.
    """
    if daily_hour is None: daily_hour=int(os.getenv("SUMMARY_DAILY_HOUR","18"))
    if weekly_day is None: weekly_day=int(os.getenv("SUMMARY_WEEKLY_DAY","6"))
    local=pd.Timestamp(current).tz_convert(IST_TIMEZONE)
    if local.hour < daily_hour: return []
    day=local.date().isoformat()
    due=[]
    if state.get("daily") != day: due.append("daily")
    if local.weekday()==weekly_day and state.get("weekly") != day: due.append("weekly")
    return due

def _summary_subscribers():
    try:
        return [c for c in channels.load() if c["enabled"] and "SUMMARY" in c["events"]]
    except Exception:
        logger.exception("Notification channel read failed")
        return []

def run_summaries():
    """Send whatever daily/weekly summary is due, and remember what went out.

    Checked against the subscriptions rather than a flag captured at boot, so a
    channel added from the Tools screen this afternoon gets today's summary
    instead of waiting for a restart. With no subscriber this is one small file
    read a minute and nothing else.
    """
    if SERVICE is None or not _summary_subscribers(): return []
    current=now(); state=_load_summary_state(); sent=[]
    for which in due_summaries(current,state):
        try:
            if which=="daily":
                message=TelegramMessage("MSG-SUMMARY-V1",msg_summary(DB.load_trades("OPEN"),DB.load_trades("CLOSED")))
            else:
                message=TelegramMessage("MSG-WEEKLY-V1",msg_weekly(DB.load_trades("CLOSED")))
            delivered=SERVICE.notifier.deliver(signal_id=f"summary:{which}",message=message,kind="SUMMARY",metadata={"summary":which,"at":current.isoformat()},audit=False)
        except Exception:
            logger.exception("Summary notification failed | summary=%s",which); continue
        if delivered:
            state[which]=current.tz_convert(IST_TIMEZONE).date().isoformat(); sent.append(which)
    if sent: _save_summary_state(state)
    return sent

def summary_loop():
    while not STOP.is_set():
        try:
            _require_runtime_leader()
            run_summaries()
        except Exception: logger.exception("Summary cycle failed")
        STOP.wait(60)

def _json_response(start,payload,status="200 OK"): start(status,[("Content-Type","application/json; charset=utf-8"),("Cache-Control","no-store")]); return [json.dumps(payload,default=str).encode()]
def _settings_response(env,start):
    """GET/POST /api/settings - read or replace accounts, assets and routing.

    These values decide which account takes a real trade and on how much
    capital, so they are written on the server: an unsaved edit is never
    applied, and a rejected one leaves the running configuration untouched.
    """
    method=env.get("REQUEST_METHOD","GET").upper()
    if method=="GET":
        return _json_response(start,{"ok":True,"settings":bot_settings.settings_state(),"defaults":bot_settings.default_settings()})
    if method!="POST":
        start("405 Method Not Allowed",[("Content-Type","application/json; charset=utf-8"),("Cache-Control","no-store"),("Allow","GET, POST")])
        return [b'{"ok":false,"error":"Use POST to change bot settings."}']
    try:
        length=int(env.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length=0
    raw=env["wsgi.input"].read(length) if length>0 else b""
    try:
        payload=json.loads(raw or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _json_response(start,{"ok":False,"error":"Malformed JSON body."},"400 Bad Request")
    if not isinstance(payload,dict):
        return _json_response(start,{"ok":False,"error":"Settings must be an object."},"400 Bad Request")
    body=payload.get("settings")
    document=body if body is not None else payload
    try:
        if document.get("action")=="reset":
            state=bot_settings.reset(); message="Settings restored to the built-in defaults."
        else:
            state=bot_settings.save(document)
            message="Settings saved and applied to the running bot."
    except ValueError as exc:
        # A rejected edit must not disturb the configuration already in force.
        logger.info("Settings change rejected | error=%s",exc)
        return _json_response(start,{"ok":False,"error":str(exc),"settings":bot_settings.settings_state()},"400 Bad Request")
    logger.info("Settings change applied | %s",message)
    # Accounts and assets are runtime state now: the scan loops, the monitor and
    # the dashboard all hold their own account maps built once at startup.
    init_state(); refresh_runtime_accounts()
    return _json_response(start,{"ok":True,"settings":bot_settings.settings_state(),"message":message})
def _notifications_response(env,start):
    """GET/POST /api/notifications - read or replace the delivery channels.

    Webhook targets are credentials (a Discord/Slack webhook URL *is* the token),
    so a read never returns one: the dashboard gets `has_target`/`has_secret`
    plus a blank, and posting a blank back keeps whatever is stored. Telegram
    keeps working with no channel saved at all.
    """
    method=env.get("REQUEST_METHOD","GET").upper()
    if method=="GET":
        return _json_response(start,{"ok":True,**channels.state()})
    if method!="POST":
        start("405 Method Not Allowed",[("Content-Type","application/json; charset=utf-8"),("Cache-Control","no-store"),("Allow","GET, POST")])
        return [b'{"ok":false,"error":"Use POST to change notification channels."}']
    try:
        length=int(env.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length=0
    raw=env["wsgi.input"].read(length) if length>0 else b""
    try:
        payload=json.loads(raw or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _json_response(start,{"ok":False,"error":"Malformed JSON body."},"400 Bad Request")
    if not isinstance(payload,dict):
        return _json_response(start,{"ok":False,"error":"Channels must be an object."},"400 Bad Request")
    try:
        if payload.get("action")=="reset":
            channels.reset(); message="Notification channels restored to the default."
        else:
            channels.save(payload.get("channels",payload)); message="Notification channels saved."
    except ValueError as exc:
        logger.info("Notification channel change rejected | error=%s",exc)
        return _json_response(start,{"ok":False,"error":str(exc),**channels.state()},"400 Bad Request")
    logger.info("Notification channels changed | %s",message)
    return _json_response(start,{"ok":True,"message":message,**channels.state()})
def _sweep_diagnostic_payload(*, period="30d"):
    """Run the real Sweep V2 data -> prepare -> signal path without dispatching or sending."""
    ensure_runtime()
    strategy = REGISTRY.get("sweep_v2")
    current = now()
    rows = []
    totals = {"assets": 0, "ok": 0, "errors": 0, "directional": 0, "reasons": {}}
    for asset in live_assets():
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
                        "diagnostics": getattr(exc, "diagnostics", None),
                        "quarantined": last_quarantine(asset.symbol),
                        "direction": None, "reason": "MARKET_DATA_ERROR"})
            totals["errors"] += 1
            totals["reasons"]["MARKET_DATA_ERROR"] = totals["reasons"].get("MARKET_DATA_ERROR", 0) + 1
        else:
            # Rows that scanned clean still surface any quarantined (dropped)
            # provider rows the sweep engine saw while building candles.
            quarantined = last_quarantine(asset.symbol)
            if quarantined:
                row["quarantined"] = quarantined
        rows.append(row)
    return {"ok": True, "strategy": {"id": strategy.manifest.id, "name": strategy.manifest.name,
            "version": strategy.manifest.version}, "generated_at": current.isoformat(),
            "period": period, "totals": totals, "assets": rows}
def _calendar_payload(query):
    target=query.get("date",[None])[0]; impacts={x.strip().title() for x in query.get("impact",["All"])[0].split(",") if x.strip()} or {"All"}; return NEWS.get(target_date=target,impacts={"All"} if "All" in impacts else impacts,force=query.get("refresh")==["1"])
def _hostname(value, *, authority=False):
    """Lowercased hostname from an Origin/Referer URL or a Host-style authority."""
    text=str(value or "").strip().lower()
    if not text: return ""
    try:
        return parse.urlsplit(("//"+text) if authority else text).hostname or ""
    except ValueError:
        return ""
def _same_origin_request(env):
    """Cross-origin reads and writes to configuration endpoints are rejected.

    Browsers attach Origin (sometimes Referer) to cross-site calls, so a
    hostile page can never read or forge a settings/notifications request from
    the operator's browser. A request with neither header (curl, server-to-
    server) passes this layer — state-changing clients still need the admin
    token when one is configured. Hostnames are compared without ports so a
    proxy does not break the dashboard."""
    forwarded=env.get("HTTP_X_FORWARDED_HOST") or ""
    if "," in forwarded: forwarded=forwarded.split(",")[0]
    host=_hostname(forwarded,authority=True) or _hostname(env.get("HTTP_HOST",""),authority=True)
    origin=env.get("HTTP_ORIGIN")
    if origin:
        return bool(host) and _hostname(origin)==host
    referer=env.get("HTTP_REFERER")
    if referer:
        referrer_host=_hostname(referer)
        if referrer_host: return bool(host) and referrer_host==host
    return True
def _admin_token_allowed(env):
    """Require the configured deployment admin token using constant-time comparison."""
    expected=os.getenv("DASHBOARD_API_TOKEN","").strip()
    # Keep local-first development compatible when no deployment token is set.
    if not expected: return True
    supplied=str(env.get("HTTP_X_ADMIN_TOKEN","") or "").strip()
    if not supplied:
        authorization=str(env.get("HTTP_AUTHORIZATION","") or "")
        if authorization[:7].lower()=="bearer ": supplied=authorization[7:].strip()
    return bool(supplied) and hmac.compare_digest(supplied,expected)
def _admin_write_allowed(env):
    """Compatibility alias for the existing configuration-write gate."""
    return _admin_token_allowed(env)
def _admin_api_guard(env,start,*,require_token=True):
    """Reject cross-origin requests and optionally require the deployment token."""
    if not _same_origin_request(env):
        logger.info("API request rejected | reason=CROSS_ORIGIN origin=%s host=%s",env.get("HTTP_ORIGIN") or env.get("HTTP_REFERER"),env.get("HTTP_HOST"))
        return _json_response(start,{"ok":False,"error":"Cross-origin requests to the dashboard API are not allowed.","code":"CROSS_ORIGIN"},"403 Forbidden")
    if require_token and not _admin_token_allowed(env):
        return _json_response(start,{"ok":False,"error":"An admin token is required for this dashboard API. Send it as X-Admin-Token or Authorization: Bearer.","code":"ADMIN_TOKEN_REQUIRED"},"401 Unauthorized")
    return None
def _config_endpoint_guard(env,start):
    """Preserve configuration same-origin checks and protect reads and writes."""
    return _admin_api_guard(env,start)
def build_app():
    root=os.path.dirname(__file__); files={"/":("dashboard.html","text/html; charset=utf-8"),"/dashboard":("dashboard.html","text/html; charset=utf-8"),"/app.js":("app.js","application/javascript"),"/styles.css":("styles.css","text/css"),"/appearance.js":("appearance.js","application/javascript"),"/dashboard-live-wiring.js":("dashboard-live-wiring.js","application/javascript"),"/appearance-overrides.css":("appearance-overrides.css","text/css"),"/foundation.css":("foundation.css","text/css"),"/notifications.js":("notifications.js","application/javascript"),"/manifest.webmanifest":("manifest.webmanifest","application/manifest+json"),"/sw.js":("sw.js","application/javascript"),"/app-icon.svg":("app-icon.svg","image/svg+xml")}
    def app(env,start):
        path=env.get("PATH_INFO","/"); query=parse.parse_qs(env.get("QUERY_STRING",""))
        if path=="/ping":
            global LAST_PING_AT
            with LOCK: LAST_PING_AT=now().isoformat(); last_ping=LAST_PING_AT
            logger.info("Keepalive ping received | at=%s",last_ping)
            start("200 OK",[("Content-Type","text/plain"),("Cache-Control","no-store")])
            return [b"pong"]
        if path=="/api/health":
            # Public health contract: expose status and keepalive only.
            try:
                current=now()
                with LOCK: last_ping=LAST_PING_AT
                keepalive_age_minutes=None
                keepalive="UNKNOWN"
                if last_ping:
                    keepalive_age_minutes=max(0,(current-pd.Timestamp(last_ping)).total_seconds()/60)
                    keepalive="OK" if keepalive_age_minutes <= 15 else "STALE"
                payload={"ok":True,"status":"ONLINE","timestamp":current.isoformat(),
                    "keepalive":keepalive,"last_ping_at":last_ping,
                    "keepalive_age_minutes":round(keepalive_age_minutes,1) if keepalive_age_minutes is not None else None}
                return _json_response(start,payload)
            except Exception:
                logger.exception("Health check failed")
                return _json_response(start,{"ok":False,"status":"DEGRADED","timestamp":now().isoformat()},"503 Service Unavailable")
        if path=="/api/dashboard":
            guard=_admin_api_guard(env,start)
            if guard is not None: return guard
            request_started=time.monotonic()
            try:
                payload=snapshot()
                logger.info("Dashboard API request complete | elapsed_ms=%s",round((time.monotonic()-request_started)*1000))
                return _json_response(start,payload)
            except Exception as exc:
                logger.exception("Dashboard API request failed | elapsed_ms=%s",round((time.monotonic()-request_started)*1000))
                return _json_response(start,{"ok":False,"error":str(exc)},"500 Internal Server Error")
        if path=="/api/diagnostics/sweep":
            guard=_admin_api_guard(env,start)
            if guard is not None: return guard
            try:return _json_response(start,_sweep_diagnostic_payload(period=query.get("period",["30d"])[0]))
            except Exception as exc:
                logger.exception("Sweep diagnostics failed")
                return _json_response(start,{"ok":False,"error_type":type(exc).__name__,"error":str(exc)},"500 Internal Server Error")
        if path=="/api/settings":
            guard=_config_endpoint_guard(env,start)
            if guard is not None: return guard
            try:
                return _settings_response(env,start)
            except Exception as exc:
                logger.exception("Settings request failed")
                return _json_response(start,{"ok":False,"error":str(exc)},"500 Internal Server Error")
        if path=="/api/notifications":
            guard=_config_endpoint_guard(env,start)
            if guard is not None: return guard
            try:
                return _notifications_response(env,start)
            except Exception as exc:
                logger.exception("Notification channel request failed")
                return _json_response(start,{"ok":False,"error":str(exc)},"500 Internal Server Error")
        if path in ("/api/calendar","/api/news"):
            guard=_admin_api_guard(env,start)
            if guard is not None: return guard
            try:return _json_response(start,_calendar_payload(query))
            except Exception as exc:return _json_response(start,{"ok":False,"error":str(exc)},"400 Bad Request")
        if path=="/api/backtest":
            guard=_admin_api_guard(env,start)
            if guard is not None: return guard
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
        if path == "/architecture":
            architecture_path = os.path.join(root, "docs", "architecture", "multibot2-architecture.html")
            try:
                body = open(architecture_path, "rb").read()
            except OSError:
                start("404 Not Found", [("Content-Type", "text/plain")])
                return [b"Architecture file not found"]
            start("200 OK", [("Content-Type", "text/html; charset=utf-8"), ("Cache-Control", "no-store")])
            return [body]
        if path in files:
            name,typ=files[path]
            try: body=open(os.path.join(root,name),"rb").read()
            except OSError: start("404 Not Found",[("Content-Type","text/plain")]); return [b"Not found"]
            start("200 OK",[("Content-Type",typ),("Cache-Control","no-store")]); return [body]
        start("404 Not Found",[("Content-Type","text/plain")]); return [b"Not found"]
    return app
def web_server():
    global HTTP_SERVER
    port=int(os.getenv("PORT","10000"))
    while not STOP.is_set():
        server=None
        try:
            server=make_server("0.0.0.0",port,build_app(),server_class=ThreadingWSGIServer)
            with LOCK: HTTP_SERVER=server
            logger.info("Dashboard HTTP server listening | port=%s pid=%s",port,os.getpid())
            server.serve_forever()
            return
        except OSError as exc:
            if exc.errno==errno.EADDRINUSE and not STOP.is_set():
                # Another process may already own the shared application port.
                # Keep this runtime alive and retry; do not kill its trading
                # supervisor just because this process cannot bind the UI yet.
                logger.warning("Dashboard port already in use | port=%s pid=%s retry_in=5s",port,os.getpid())
                STOP.wait(5)
                continue
            logger.exception("Dashboard HTTP server stopped unexpectedly | pid=%s",os.getpid())
            return
        except Exception:
            logger.exception("Dashboard HTTP server stopped unexpectedly | pid=%s",os.getpid())
            return
        finally:
            if server is not None:
                try: server.server_close()
                except Exception: logger.exception("Dashboard HTTP server close failed")
            with LOCK:
                if HTTP_SERVER is server:
                    HTTP_SERVER=None
def _send_chat(chat_id,message):
    config=TelegramConfig.from_env(); target=TelegramConfig(config.bot_token,str(chat_id)); send_message(message if isinstance(message,TelegramMessage) else TelegramMessage("MSG-COMMAND-V1",message),target)
def _handle_command(chat_id,cmd):
    global NEWS_PAUSE_ENABLED
    try:
        if cmd in ("/start","/menu"): _send_chat(chat_id,msg_start())
        elif cmd=="/whatsnew": _send_chat(chat_id,msg_whats_new())
        elif cmd in ("/check","/scan"): _send_chat(chat_id,msg_scan_started()); results=run_all_cycles(send=True,force=True); _send_chat(chat_id,msg_scan_result(sum(r.sent for r in results),sum(len(st.manifest.assets) for st in REGISTRY.all())))
        elif cmd=="/balance": _send_chat(chat_id,msg_balance(ACCOUNTS))
        elif cmd=="/summary": _send_chat(chat_id,msg_summary(DB.load_trades("OPEN"),DB.load_trades("CLOSED")))
        elif cmd=="/risk": _send_chat(chat_id,msg_risk(DB.load_trades("OPEN")))
        elif cmd=="/stats": _send_chat(chat_id,msg_stats(DB.load_trades("CLOSED")))
        elif cmd=="/weekly": _send_chat(chat_id,msg_weekly(DB.load_trades("CLOSED")))
        elif cmd=="/newspause":
            # Read-modify-write plus the paired NEWS_GATE mutation. The Telegram
            # polling thread and the scheduler thread both read this, so the
            # whole flip has to be atomic under the lock that already exists.
            with LOCK:
                NEWS_PAUSE_ENABLED=not NEWS_PAUSE_ENABLED
                NEWS_GATE.enabled=NEWS_PAUSE_ENABLED
                paused=NEWS_PAUSE_ENABLED
            _send_chat(chat_id,msg_news_pause(paused))
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

def _send_startup_announcement():
    """Send the startup notice and release notes as two separate Telegram messages."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.info("Telegram startup announcements skipped | reason=not_configured")
        return
    try:
        config = TelegramConfig.from_env()
    except Exception as exc:
        logger.warning("Telegram startup announcements skipped | pid=%s error=%s", os.getpid(), exc)
        return

    # Keep these as two independent sends: a failure in one must not suppress
    # the other, and neither may prevent the trading runtime from starting.
    announcements = (
        ("MSG-STARTUP-V1", msg_start(), "startup"),
        ("MSG-WHATSNEW-STARTUP-V1", msg_whats_new(), "what's-new"),
    )
    for message_type, body, label in announcements:
        try:
            send_message(TelegramMessage(message_type, body), config)
            logger.info("Telegram %s announcement sent | pid=%s", label, os.getpid())
        except Exception as exc:
            logger.warning("Telegram %s announcement failed | pid=%s error=%s", label, os.getpid(), exc)

def _start_worker(name,target):
    """Start one named worker in this process; never create duplicate loops."""
    with LOCK:
        current=WORKER_THREADS.get(name)
        if current is not None and current.is_alive():
            logger.warning("Worker start skipped | name=%s pid=%s reason=already_alive",name,os.getpid())
            return current
        worker=threading.Thread(target=target,daemon=True,name=name)
        WORKER_THREADS[name]=worker
        worker.start()
        logger.info("Worker started | name=%s pid=%s",name,os.getpid())
        return worker

def _start_leader_workers():
    global RUNTIME_LEADER,REMINDER_THREAD
    RUNTIME_LEADER=True
    logger.info("Runtime leadership acquired | pid=%s owner=%s",os.getpid(),RUNTIME_OWNER_ID)
    _require_runtime_leader()
    _send_startup_announcement()
    _require_runtime_leader()
    _start_worker("scanner",scanner_loop)
    _start_worker("monitor",monitor_loop)
    _start_worker("summaries",summary_loop)
    logger.info("Summary scheduler started | daily_hour=%s weekly_day=%s pid=%s",os.getenv("SUMMARY_DAILY_HOUR","18"),os.getenv("SUMMARY_WEEKLY_DAY","6"),os.getpid())
    if settings.telegram_bot_token and settings.telegram_chat_id:
        if _telegram_command_polling_enabled():
            _start_worker("telegram",telegram_commands)
            logger.info("Telegram command polling enabled | pid=%s",os.getpid())
        else:
            logger.info("Telegram command polling disabled; signal delivery remains enabled")
        if REMINDERS is not None:
            REMINDER_THREAD=REMINDERS.start()
            logger.info("Reminder worker started | pid=%s",os.getpid())
    logger.info("MULTIBOT2 %s started: %d assets, Yahoo, %d plug-in strategies, 1h freshness, paper mode | pid=%s owner=%s",APP_VERSION,len(live_assets()),len(REGISTRY.all()),os.getpid(),RUNTIME_OWNER_ID)

def _validate_runtime_lease_backend():
    # A local SQLite lease cannot coordinate separate deployment containers.
    # Deployed processes therefore require the shared Turso primary. Local
    # development can use SQLite; the override is explicit for special cases.
    allow_local=os.getenv("MULTIBOT_ALLOW_LOCAL_RUNTIME_LEASE","").strip().lower() in {"1","true","yes","on"}
    if os.getenv("PORT") and not DB.turso_enabled and not allow_local:
        raise RuntimeError(
            "Turso is required for deployment-wide runtime leadership. "
            "Configure TURSO_DATABASE_URL and TURSO_AUTH_TOKEN, or explicitly "
            "set MULTIBOT_ALLOW_LOCAL_RUNTIME_LEASE=true for a single-process test."
        )

def main():
    global _MAIN_STARTED,RUNTIME_OWNER_ID,RUNTIME_LEADER,RUNTIME_LEASE_REQUIRED,RUNTIME_LEASE_LAST_VERIFIED
    try:
        _validate_runtime_lease_backend()
    except Exception as exc:
        logger.critical("Runtime startup refused | reason=%s",exc)
        return 1
    with _MAIN_START_LOCK:
        if _MAIN_STARTED:
            logger.warning("Runtime entrypoint invoked more than once in one process | pid=%s",os.getpid())
            return 0
        _MAIN_STARTED=True

    STOP.clear()
    RUNTIME_LEASE_REQUIRED=True
    RUNTIME_LEASE_LAST_VERIFIED=0.0
    RUNTIME_OWNER_ID=f"{os.getenv('HOSTNAME','host')}:{os.getpid()}:{uuid.uuid4().hex[:12]}"
    logger.info("Runtime process booting | pid=%s owner=%s",os.getpid(),RUNTIME_OWNER_ID)

    def request_shutdown(signum,frame):
        logger.info("Runtime shutdown requested | signal=%s pid=%s",signum,os.getpid())
        STOP.set()

    previous_handlers={}
    for sig in (os_signal.SIGTERM,os_signal.SIGINT):
        try:
            previous_handlers[sig]=os_signal.getsignal(sig)
            os_signal.signal(sig,request_shutdown)
        except (ValueError,OSError):
            # Signal handlers can only be installed by the main interpreter thread.
            pass

    _start_worker("dashboard",web_server)
    try:
        while not STOP.is_set():
            if not RUNTIME_LEADER:
                try:
                    if DB.acquire_runtime_lease(RUNTIME_OWNER_ID,ttl_seconds=RUNTIME_LEASE_TTL_SECONDS):
                        # Initialize before declaring leadership. If initialization
                        # fails, release the lease so another healthy instance can try.
                        try:
                            ensure_runtime()
                            # Initialization/migration may take time on a cold
                            # deployment. Re-claim immediately before workers
                            # start so an expired lease cannot activate a stale owner.
                            if not DB.renew_runtime_lease(RUNTIME_OWNER_ID,ttl_seconds=RUNTIME_LEASE_TTL_SECONDS):
                                raise RuntimeError("Runtime lease was lost during initialization")
                            RUNTIME_LEASE_LAST_VERIFIED=time.monotonic()
                        except Exception:
                            DB.release_runtime_lease(RUNTIME_OWNER_ID)
                            raise
                        _start_leader_workers()
                    else:
                        current=DB.runtime_lease_owner() or {}
                        logger.info("Runtime standby | pid=%s active_owner=%s retry_in=%ss",os.getpid(),current.get("owner_id","unknown"),RUNTIME_LEASE_HEARTBEAT_SECONDS)
                except Exception:
                    logger.exception("Runtime leadership acquisition failed; trading workers remain stopped | pid=%s",os.getpid())
            else:
                try:
                    renewed=DB.renew_runtime_lease(RUNTIME_OWNER_ID,ttl_seconds=RUNTIME_LEASE_TTL_SECONDS)
                    if renewed: RUNTIME_LEASE_LAST_VERIFIED=time.monotonic()
                except Exception:
                    logger.exception("Runtime lease heartbeat failed; stopping trading workers | pid=%s",os.getpid())
                    renewed=False
                if not renewed:
                    RUNTIME_LEADER=False
                    logger.critical("Runtime leadership lost; fail-closed shutdown initiated | pid=%s",os.getpid())
                    STOP.set()
                    if REMINDERS is not None: REMINDERS.stop()
            STOP.wait(RUNTIME_LEASE_HEARTBEAT_SECONDS)
    finally:
        RUNTIME_LEADER=False
        STOP.set()
        if REMINDERS is not None:
            try: REMINDERS.stop()
            except Exception: logger.exception("Reminder worker shutdown failed")
        with LOCK: server=HTTP_SERVER
        if server is not None:
            try: server.shutdown()
            except Exception: logger.exception("Dashboard shutdown failed | pid=%s",os.getpid())
        # Keep the lease until every operational worker has stopped. If a worker
        # is stuck in an upstream request, leave the lease to expire rather than
        # allowing a replacement process to trade concurrently with it.
        deadline=time.monotonic()+45.0
        workers=list(WORKER_THREADS.values())
        if REMINDER_THREAD is not None: workers.append(REMINDER_THREAD)
        for worker in workers:
            if worker is threading.current_thread(): continue
            worker.join(timeout=max(0.0,deadline-time.monotonic()))
        still_alive=[worker.name for worker in workers if worker.is_alive()]
        if still_alive:
            logger.error("Runtime workers did not stop before shutdown deadline; lease left to expire | workers=%s",still_alive)
        else:
            try:
                DB.release_runtime_lease(RUNTIME_OWNER_ID)
                logger.info("Runtime lease released | pid=%s owner=%s",os.getpid(),RUNTIME_OWNER_ID)
            except Exception:
                logger.exception("Runtime lease release failed | pid=%s",os.getpid())
        for sig,handler in previous_handlers.items():
            try: os_signal.signal(sig,handler)
            except (ValueError,OSError): pass
        logger.info("Runtime process stopped | pid=%s",os.getpid())
    return 0
if __name__=="__main__": raise SystemExit(main())
