"""Durable runtime state and canonical signal lifecycle."""
from __future__ import annotations
import json, os, sqlite3
from datetime import datetime, timezone
from urllib import error, parse, request

DEFAULT_DB_PATH=os.getenv("BOT_STATE_DB_PATH","/tmp/workspace/multibot2_state.db")
SUPABASE_URL=os.getenv("SUPABASE_URL","").rstrip("/")
SUPABASE_KEY=os.getenv("SUPABASE_KEY","")

class DatabaseError(RuntimeError): pass

class DatabaseManager:
    def __init__(self,path=None):
        self.path=path or DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(os.path.abspath(self.path)),exist_ok=True)
        self._initialize(); self._restore_from_supabase_if_needed()

    @property
    def supabase_enabled(self): return bool(SUPABASE_URL and SUPABASE_KEY)

    def _connect(self):
        c=sqlite3.connect(self.path,timeout=30); c.row_factory=sqlite3.Row; return c

    def _initialize(self):
        with self._connect() as c:
            c.executescript("""PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS accounts(name TEXT PRIMARY KEY,starting_balance REAL NOT NULL,balance REAL NOT NULL,trades_today INTEGER NOT NULL DEFAULT 0,planned_risk_used REAL NOT NULL DEFAULT 0,reset_date TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS trades(id TEXT PRIMARY KEY,status TEXT NOT NULL,payload TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS signals(signal_key TEXT PRIMARY KEY,send_count INTEGER NOT NULL DEFAULT 0,first_sent_at TEXT,last_sent_at TEXT,reminder_due_at TEXT,reminder_sent INTEGER NOT NULL DEFAULT 0,message_text TEXT,metadata TEXT);
CREATE TABLE IF NOT EXISTS signal_events(signal_id TEXT PRIMARY KEY,signal_key TEXT NOT NULL,strategy TEXT NOT NULL,version TEXT,symbol TEXT NOT NULL,direction TEXT NOT NULL,timestamp TEXT NOT NULL,timeframe TEXT,reason TEXT,pipeline_status TEXT NOT NULL,metadata TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS deliveries(id INTEGER PRIMARY KEY AUTOINCREMENT,signal_id TEXT NOT NULL,channel TEXT NOT NULL,status TEXT NOT NULL,attempted_at TEXT NOT NULL,error TEXT,message_type TEXT,metadata TEXT);
CREATE INDEX IF NOT EXISTS signal_events_timestamp_idx ON signal_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS signal_events_key_idx ON signal_events(signal_key);
CREATE INDEX IF NOT EXISTS deliveries_signal_idx ON deliveries(signal_id,attempted_at DESC);
"""); c.commit()

    def _supabase_request(self,method,table,*,params="",data=None,upsert=False):
        if not self.supabase_enabled:return None
        url=f"{SUPABASE_URL}/rest/v1/{table}"+("?"+params if params else "")
        headers={"apikey":SUPABASE_KEY,"Authorization":f"Bearer {SUPABASE_KEY}","Content-Type":"application/json","Accept":"application/json","Prefer":"return=representation"}
        if upsert: headers["Prefer"]="resolution=merge-duplicates,return=representation"
        try:
            body=None if data is None else json.dumps(data,default=str).encode()
            with request.urlopen(request.Request(url,data=body,headers=headers,method=method),timeout=10) as response:
                raw=response.read().decode(); return json.loads(raw) if raw else True
        except (error.HTTPError,error.URLError,TimeoutError,ValueError) as exc:
            raise DatabaseError(f"Supabase {method} {table} failed: {exc}") from exc

    def _require_supabase(self,result,operation):
        if self.supabase_enabled and result is None: raise DatabaseError(f"Supabase persistence failed during {operation}")

    def _restore_from_supabase_if_needed(self):
        # Local runtime cache is restored only for legacy account/trade/send tables.
        if not self.supabase_enabled:return
        with self._connect() as c:
            if any(c.execute(f"SELECT 1 FROM {t} LIMIT 1").fetchone() for t in ("accounts","trades","signals")): return
        self._restore_accounts(); self._restore_trades(); self._restore_signals()

    def _restore_accounts(self):
        rows=self._supabase_request("GET","accounts",params="select=*") or []
        with self._connect() as c:
            for r in rows:
                if not r.get("name"):continue
                c.execute("INSERT OR REPLACE INTO accounts VALUES(?,?,?,?,?,?)",(r["name"],float(r.get("starting_balance",100000) or 100000),float(r.get("balance",100000) or 100000),int(r.get("daily_trades",r.get("trades_today",0)) or 0),float(r.get("planned_risk_used",0) or 0),str(r.get("last_reset_date",r.get("reset_date","")) or "")))
            c.commit()

    def _restore_trades(self):
        for table,status in (("active_trades","OPEN"),("closed_trades","CLOSED")):
            rows=self._supabase_request("GET",table,params="select=*") or []
            with self._connect() as c:
                for r in rows:
                    tid=str(r.get("id","") or "")
                    if not tid:continue
                    payload={"id":tid,"status":status,"symbol":r.get("symbol",""),"market":r.get("market","NSE"),"account":r.get("account",""),"strategy":r.get("strat",r.get("strategy","")),"type":r.get("type","BUY"),"entry":float(r.get("entry",0) or 0),"sl":float(r.get("sl",0) or 0),"tp":float(r.get("tp",0) or 0),"qty":float(r.get("qty",0) or 0),"trail_sl":float(r.get("trail_sl",r.get("sl",0)) or 0),"signal_ts":r.get("ts_trigger",""),"opened_at":r.get("opened_at","") or ""}
                    if status=="CLOSED": payload.update({"exit_price":float(r.get("exit_price",0) or 0),"pnl":float(r.get("pnl",0) or 0),"result":r.get("result",""),"exit_reason":r.get("exit_reason",""),"closed_at":r.get("closed_at",r.get("close_time","")) or ""})
                    updated=payload.get("closed_at") or payload.get("opened_at") or datetime.now(timezone.utc).isoformat()
                    c.execute("INSERT OR REPLACE INTO trades VALUES(?,?,?,?)",(tid,status,json.dumps(payload,default=str),str(updated)))
                c.commit()

    def _restore_signals(self):
        rows=self._supabase_request("GET","sent_signals",params="select=*") or []
        with self._connect() as c:
            for r in rows:
                key=str(r.get("sig_key",r.get("signal_key","")) or "")
                if not key:continue
                count=min(int(r.get("send_count",0) or 0),2); metadata=r.get("metadata") or "{}"
                if isinstance(metadata,dict): metadata=json.dumps(metadata)
                c.execute("INSERT OR REPLACE INTO signals VALUES(?,?,?,?,?,?,?,?)",(key,count,None,None,r.get("reminder_due_at"),int(count>=2),r.get("message_text"),metadata))
            c.commit()

    def load_accounts(self,names,starting_balance,today):
        with self._connect() as c:
            for name in names:
                row=c.execute("SELECT * FROM accounts WHERE name=?",(name,)).fetchone()
                if row is None:c.execute("INSERT INTO accounts VALUES(?,?,?,?,?,?)",(name,starting_balance,starting_balance,0,0.0,today))
                elif row["reset_date"]!=today:c.execute("UPDATE accounts SET trades_today=0,planned_risk_used=0,reset_date=? WHERE name=?",(today,name))
            c.commit(); rows=c.execute("SELECT * FROM accounts WHERE name IN (%s)"%",".join("?" for _ in names),names).fetchall()
        return {x["name"]:dict(x) for x in rows}

    def save_account(self,name,*,balance,trades_today,planned_risk_used,reset_date):
        with self._connect() as c:c.execute("UPDATE accounts SET balance=?,trades_today=?,planned_risk_used=?,reset_date=? WHERE name=?",(balance,trades_today,planned_risk_used,reset_date,name)); c.commit()
        result=self._supabase_request("POST","accounts",data={"name":name,"starting_balance":100000.0,"balance":balance,"daily_trades":trades_today,"trades_today":trades_today,"planned_risk_used":planned_risk_used,"last_reset_date":reset_date,"reset_date":reset_date},upsert=True); self._require_supabase(result,"account")

    def save_trade(self,trade_id,status,payload,updated_at):
        payload=dict(payload); payload["status"]=status
        with self._connect() as c:c.execute("INSERT INTO trades VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,payload=excluded.payload,updated_at=excluded.updated_at",(trade_id,status,json.dumps(payload,default=str),updated_at)); c.commit()
        if status=="OPEN":
            data={"id":trade_id,"symbol":payload.get("symbol",""),"market":payload.get("market","NSE"),"account":payload.get("account",""),"strat":payload.get("strategy",""),"type":payload.get("type","BUY"),"entry":payload.get("entry",0),"sl":payload.get("sl",0),"tp":payload.get("tp",0),"qty":payload.get("qty",0),"trail_sl":payload.get("trail_sl",payload.get("sl",0)),"ts_trigger":payload.get("signal_ts",""),"opened_at":payload.get("opened_at",updated_at),"time_str":payload.get("opened_at",updated_at)}
            result=self._supabase_request("POST","active_trades",data=data,upsert=True); self._require_supabase(result,"open trade")
        else:
            result=self._supabase_request("DELETE","active_trades",params=parse.urlencode({"id":f"eq.{trade_id}"})); self._require_supabase(result,"active trade delete")
            data={"id":trade_id,"symbol":payload.get("symbol",""),"market":payload.get("market","NSE"),"account":payload.get("account",""),"strat":payload.get("strategy",""),"type":payload.get("type","BUY"),"entry":payload.get("entry",0),"sl":payload.get("sl",0),"tp":payload.get("tp",0),"qty":payload.get("qty",0),"trail_sl":payload.get("trail_sl",payload.get("sl",0)),"ts_trigger":payload.get("signal_ts",""),"opened_at":payload.get("opened_at",updated_at),"time_str":payload.get("opened_at",updated_at),"exit_price":payload.get("exit_price",0),"pnl":payload.get("pnl",0),"result":payload.get("result",payload.get("exit_reason","")),"exit_reason":payload.get("exit_reason",""),"close_time":payload.get("closed_at",updated_at),"closed_at":payload.get("closed_at",updated_at)}
            result=self._supabase_request("POST","closed_trades",data=data,upsert=True); self._require_supabase(result,"closed trade")

    def load_trades(self,status=None):
        with self._connect() as c: rows=c.execute("SELECT payload FROM trades"+(" WHERE status=?" if status else "")+" ORDER BY updated_at DESC",(status,) if status else ()).fetchall()
        return [json.loads(x["payload"]) for x in rows]

    def record_signal_event(self,signal_id,signal_key,signal,*,pipeline_status,created_at=None):
        ts=created_at or datetime.now(timezone.utc).isoformat(); metadata=dict(signal.metadata or {})
        row=(signal_id,signal_key,signal.strategy,signal.version,signal.symbol,signal.direction,signal.timestamp.isoformat(),signal.timeframe,signal.reason,pipeline_status,json.dumps(metadata,default=str),ts,ts)
        with self._connect() as c:c.execute("INSERT OR REPLACE INTO signal_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",row); c.commit()
        return signal_id

    def update_signal_status(self,signal_id,status):
        with self._connect() as c:c.execute("UPDATE signal_events SET pipeline_status=?,updated_at=? WHERE signal_id=?",(status,datetime.now(timezone.utc).isoformat(),signal_id)); c.commit()

    def record_delivery(self,signal_id,*,channel,status,attempted_at=None,error_text=None,message_type=None,metadata=None):
        with self._connect() as c:c.execute("INSERT INTO deliveries(signal_id,channel,status,attempted_at,error,message_type,metadata) VALUES(?,?,?,?,?,?,?)",(signal_id,channel,status,attempted_at or datetime.now(timezone.utc).isoformat(),error_text,message_type,json.dumps(metadata or {},default=str))); c.commit()

    def delivery_status(self,signal_id):
        with self._connect() as c: row=c.execute("SELECT status,attempted_at,error,message_type FROM deliveries WHERE signal_id=? ORDER BY id DESC LIMIT 1",(signal_id,)).fetchone()
        return dict(row) if row else None

    def load_signal_history(self,limit=500):
        with self._connect() as c: rows=c.execute("SELECT * FROM signal_events ORDER BY timestamp DESC LIMIT ?",(max(1,min(int(limit),2000)),)).fetchall()
        out=[]
        for r in rows:
            try: metadata=json.loads(r["metadata"] or "{}")
            except Exception: metadata={}
            item={k:r[k] for k in ("signal_id","signal_key","strategy","version","symbol","direction","timestamp","timeframe","reason","pipeline_status","created_at","updated_at")}
            item["signal"]=item["direction"]; item["strategy_version"]=item["version"]; item["metadata"]=metadata; item["delivery"]=self.delivery_status(r["signal_id"]); out.append(item)
        return out

    def record_signal_send(self,key,sent_at,reminder_due_at=None,message_text=None,metadata=None):
        with self._connect() as c:
            row=c.execute("SELECT send_count FROM signals WHERE signal_key=?",(key,)).fetchone()
            if row is None: count=1; c.execute("INSERT INTO signals VALUES(?,?,?,?,?,?,?,?)",(key,1,sent_at,sent_at,reminder_due_at,0,message_text,json.dumps(metadata or {},default=str)))
            else: count=min(int(row["send_count"])+1,2); c.execute("UPDATE signals SET send_count=?,last_sent_at=?,reminder_sent=? WHERE signal_key=?",(count,sent_at,1 if count>=2 else 0,key))
            c.commit()
        result=self._supabase_request("POST","sent_signals",data={"sig_key":key,"send_count":count,"last_sent_ts":int(_timestamp_ms(sent_at)),"reminder_due_at":reminder_due_at,"message_text":message_text,"metadata":metadata or {}},upsert=True); self._require_supabase(result,"signal send"); return count

    def signal_count(self,key):
        with self._connect() as c: row=c.execute("SELECT send_count FROM signals WHERE signal_key=?",(key,)).fetchone()
        return int(row["send_count"]) if row else 0

    def due_reminders(self,now_iso):
        with self._connect() as c: rows=c.execute("SELECT * FROM signals WHERE send_count=1 AND reminder_sent=0 AND reminder_due_at IS NOT NULL AND reminder_due_at<=?",(now_iso,)).fetchall()
        return [dict(x) for x in rows]

    def mark_reminder_sent(self,key,sent_at):
        with self._connect() as c:c.execute("UPDATE signals SET send_count=2,reminder_sent=1,last_sent_at=? WHERE signal_key=? AND send_count=1",(sent_at,key)); c.commit()
        result=self._supabase_request("POST","sent_signals",data={"sig_key":key,"send_count":2,"last_sent_ts":int(_timestamp_ms(sent_at))},upsert=True); self._require_supabase(result,"reminder")

def _timestamp_ms(value):
    try:return datetime.fromisoformat(str(value).replace("Z","+00:00")).timestamp()*1000
    except Exception:return datetime.now(timezone.utc).timestamp()*1000

__all__=["DatabaseError","DatabaseManager"]
