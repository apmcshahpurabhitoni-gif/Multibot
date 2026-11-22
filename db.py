"""Durable runtime state backed by Turso/libSQL, with SQLite for local development."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

from config import ACCOUNT_SIZE_INR, ACCOUNT_SIZES

DEFAULT_DB_PATH=os.getenv("BOT_STATE_DB_PATH","/tmp/workspace/multibot2_state.db")
TURSO_DATABASE_URL=os.getenv("TURSO_DATABASE_URL","").strip()
TURSO_AUTH_TOKEN=os.getenv("TURSO_AUTH_TOKEN","").strip()


class DatabaseError(RuntimeError):
    """Raised when the configured durable database cannot be reached."""


class _RemoteRow(dict):
    """Mapping row with sqlite3.Row-style integer and named indexing."""
    def __init__(self, names, values):
        self._values=tuple(values)
        super().__init__(zip(names,self._values))

    def __getitem__(self,key):
        if isinstance(key,int):
            return self._values[key]
        return super().__getitem__(key)


class _RemoteCursor:
    def __init__(self,cursor):
        self._cursor=cursor

    @property
    def description(self):
        return self._cursor.description

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    def _convert(self,row):
        if row is None:
            return None
        names=[column[0] for column in (self.description or ())]
        return _RemoteRow(names,row)

    def fetchone(self):
        return self._convert(self._cursor.fetchone())

    def fetchall(self):
        return [self._convert(row) for row in (self._cursor.fetchall() or [])]

    def fetchmany(self,size=None):
        rows=self._cursor.fetchmany(size) if size is not None else self._cursor.fetchmany()
        return [self._convert(row) for row in (rows or [])]

    def __iter__(self):
        while True:
            row=self.fetchone()
            if row is None:
                break
            yield row


class _RemoteConnection:
    """Small sqlite3-compatible adapter for Turso's DB-API connection."""
    def __init__(self,connection):
        self._connection=connection

    def execute(self,sql,parameters=()):
        return _RemoteCursor(self._connection.execute(sql,tuple(parameters or ())))

    def executemany(self,sql,seq_of_parameters):
        cursor=None
        for parameters in seq_of_parameters:
            cursor=self.execute(sql,parameters)
        return cursor

    def executescript(self,script):
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self,exc_type,exc_value,traceback):
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()
        return False


class DatabaseManager:
    """One database interface: Turso in deployments, SQLite in local tests."""

    _TABLES = (
        "accounts","trades","signals","signal_events","deliveries","scan_runs",
        "scan_error_alerts","market_data_cache","forex_calendar_week_cache",
        "forex_calendar_attempts",
    )

    def __init__(self,path=None):
        self.path=path or DEFAULT_DB_PATH
        self.turso_enabled=bool(TURSO_DATABASE_URL and TURSO_AUTH_TOKEN)
        if bool(TURSO_DATABASE_URL) != bool(TURSO_AUTH_TOKEN):
            raise DatabaseError("TURSO_DATABASE_URL and TURSO_AUTH_TOKEN must both be configured")
        os.makedirs(os.path.dirname(os.path.abspath(self.path)),exist_ok=True)
        self._initialize()
        if self.turso_enabled:
            self._migrate_local_sqlite_once()

    def _connect(self):
        if self.turso_enabled:
            try:
                import libsql
                connection=libsql.connect(TURSO_DATABASE_URL,auth_token=TURSO_AUTH_TOKEN)
                return _RemoteConnection(connection)
            except Exception as exc:
                raise DatabaseError(f"Turso connection failed: {exc}") from exc
        connection=sqlite3.connect(self.path,timeout=30)
        connection.row_factory=sqlite3.Row
        return connection

    def _initialize(self):
        schema="""
CREATE TABLE IF NOT EXISTS accounts(name TEXT PRIMARY KEY,starting_balance REAL NOT NULL,balance REAL NOT NULL,trades_today INTEGER NOT NULL DEFAULT 0,planned_risk_used REAL NOT NULL DEFAULT 0,reset_date TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS trades(id TEXT PRIMARY KEY,status TEXT NOT NULL,payload TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS signals(signal_key TEXT PRIMARY KEY,send_count INTEGER NOT NULL DEFAULT 0,first_sent_at TEXT,last_sent_at TEXT,reminder_due_at TEXT,reminder_sent INTEGER NOT NULL DEFAULT 0,message_text TEXT,metadata TEXT);
CREATE TABLE IF NOT EXISTS signal_events(signal_id TEXT PRIMARY KEY,signal_key TEXT NOT NULL,strategy TEXT NOT NULL,version TEXT,symbol TEXT NOT NULL,direction TEXT NOT NULL,timestamp TEXT NOT NULL,timeframe TEXT,reason TEXT,pipeline_status TEXT NOT NULL,metadata TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS deliveries(id INTEGER PRIMARY KEY AUTOINCREMENT,signal_id TEXT NOT NULL,channel TEXT NOT NULL,status TEXT NOT NULL,attempted_at TEXT NOT NULL,error TEXT,message_type TEXT,metadata TEXT);
CREATE TABLE IF NOT EXISTS scan_runs(id TEXT PRIMARY KEY,strategy_id TEXT NOT NULL,started_at TEXT NOT NULL,finished_at TEXT,status TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS scan_error_alerts(strategy_id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,first_sent_at TEXT NOT NULL,last_sent_at TEXT NOT NULL,suppressed INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS market_data_cache(cache_key TEXT PRIMARY KEY,symbol TEXT NOT NULL,period TEXT NOT NULL,interval TEXT NOT NULL,validate_hourly INTEGER NOT NULL,payload TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS forex_calendar_week_cache(feed_key TEXT NOT NULL,week_start TEXT NOT NULL,fetched_at TEXT NOT NULL,events TEXT NOT NULL,PRIMARY KEY(feed_key,week_start));
CREATE TABLE IF NOT EXISTS forex_calendar_attempts(feed_key TEXT NOT NULL,week_start TEXT NOT NULL,attempted_at TEXT NOT NULL,error TEXT NOT NULL,PRIMARY KEY(feed_key,week_start));
CREATE TABLE IF NOT EXISTS multibot_migrations(migration_key TEXT PRIMARY KEY,completed_at TEXT NOT NULL);
DELETE FROM signal_events WHERE rowid NOT IN (SELECT MAX(rowid) FROM signal_events GROUP BY signal_key);
CREATE UNIQUE INDEX IF NOT EXISTS signal_events_key_uidx ON signal_events(signal_key);
CREATE INDEX IF NOT EXISTS signal_events_timestamp_idx ON signal_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS deliveries_signal_idx ON deliveries(signal_id,attempted_at DESC);
CREATE INDEX IF NOT EXISTS scan_runs_started_idx ON scan_runs(started_at DESC);
"""
        with self._connect() as connection:
            if not self.turso_enabled:
                connection.execute("PRAGMA journal_mode=WAL")
            for statement in schema.split(";"):
                if statement.strip():
                    connection.execute(statement)
            connection.commit()

    def _migrate_local_sqlite_once(self):
        """Import a pre-existing local SQLite state file into Turso exactly once.

        Existing rows in Turso win on primary-key conflicts. The local source file
        is never deleted or modified by this migration.
        """
        migration_key="local-sqlite-to-turso-v1"
        with self._connect() as remote:
            if remote.execute("SELECT 1 FROM multibot_migrations WHERE migration_key=?",(migration_key,)).fetchone():
                return
            # Both paths have existed in deployed versions: main.py used the
            # configured path while CalendarStore historically defaulted to
            # /tmp/workspace. Import both before marking the one-time migration.
            candidates=[]
            for candidate in (self.path,DEFAULT_DB_PATH):
                absolute=os.path.abspath(candidate)
                if absolute not in candidates:
                    candidates.append(absolute)
            try:
                for local_path in candidates:
                    if not os.path.isfile(local_path) or os.path.getsize(local_path)==0:
                        continue
                    source=sqlite3.connect(f"file:{local_path}?mode=ro",uri=True)
                    try:
                        existing={row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                        for table in self._TABLES:
                            if table not in existing:
                                continue
                            columns=[row[1] for row in source.execute(f"PRAGMA table_info({table})")]
                            if not columns:
                                continue
                            placeholders=",".join("?" for _ in columns)
                            column_sql=",".join(f'"{column}"' for column in columns)
                            sql=f"INSERT OR IGNORE INTO {table} ({column_sql}) VALUES ({placeholders})"
                            for row in source.execute(f'SELECT * FROM "{table}"'):
                                remote.execute(sql,tuple(row))
                    finally:
                        source.close()
            except Exception as exc:
                raise DatabaseError(f"Local SQLite to Turso migration failed; local files preserved: {exc}") from exc
            remote.execute(
                "INSERT OR REPLACE INTO multibot_migrations(migration_key,completed_at) VALUES(?,?)",
                (migration_key,datetime.now(timezone.utc).isoformat()),
            )
            remote.commit()


    def load_accounts(self,names,starting_balance,today):
        """Create/refresh one row per account.

        `starting_balance` is either a single figure (every account opens at the
        same size) or a per-account mapping, so an operator can give one book a
        different capital base without touching the others.
        """
        sizes=starting_balance if isinstance(starting_balance,dict) else None
        with self._connect() as c:
            for name in names:
                opening=float(sizes.get(name,ACCOUNT_SIZE_INR) if sizes is not None else starting_balance)
                row=c.execute("SELECT * FROM accounts WHERE name=?",(name,)).fetchone()
                if row is None:c.execute("INSERT INTO accounts VALUES(?,?,?,?,?,?)",(name,opening,opening,0,0.0,today))
                elif row["reset_date"]!=today:c.execute("UPDATE accounts SET trades_today=0,planned_risk_used=0,reset_date=? WHERE name=?",(today,name))
            c.commit(); rows=c.execute("SELECT * FROM accounts WHERE name IN (%s)"%",".join("?" for _ in names),names).fetchall()
        return {x["name"]:dict(x) for x in rows}

    def account_trade_count(self,name):
        """Trades ever recorded against an account, open and closed.

        A book that has traded is never deleted: the trades name the account and
        removing the book would orphan that history.
        """
        with self._connect() as c:
            live=c.execute("SELECT count(*) AS n FROM trades WHERE json_extract(payload,'$.account')=?",(name,)).fetchone()
        return int(live["n"] if live and "n" in live.keys() else 0)

    def save_account(self,name,*,balance,trades_today,planned_risk_used,reset_date):
        with self._connect() as c:
            c.execute(
                "UPDATE accounts SET balance=?,trades_today=?,planned_risk_used=?,reset_date=? WHERE name=?",
                (balance,trades_today,planned_risk_used,reset_date,name),
            )
            c.commit()

    def save_trade(self,trade_id,status,payload,updated_at):
        payload=dict(payload)
        payload["status"]=status
        with self._connect() as c:
            c.execute(
                "INSERT INTO trades VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,payload=excluded.payload,updated_at=excluded.updated_at",
                (trade_id,status,json.dumps(payload,default=str),updated_at),
            )
            c.commit()

    def load_trades(self,status=None):
        with self._connect() as c: rows=c.execute("SELECT payload FROM trades"+(" WHERE status=?" if status else "")+" ORDER BY updated_at DESC",(status,) if status else ()).fetchall()
        return [json.loads(x["payload"]) for x in rows]

    def record_signal_event(self,signal_id,signal_key,signal,*,pipeline_status,created_at=None):
        ts=created_at or datetime.now(timezone.utc).isoformat()
        metadata=dict(signal.metadata or {})
        metadata.update({"entry":getattr(signal,"entry",None),"stop_loss":getattr(signal,"stop_loss",None),"take_profit":getattr(signal,"take_profit",None)})
        with self._connect() as c:
            existing=c.execute("SELECT signal_id,created_at FROM signal_events WHERE signal_key=?",(signal_key,)).fetchone()
            if existing:
                signal_id=str(existing["signal_id"])
                created_at=existing["created_at"]
                c.execute(
                    """UPDATE signal_events SET strategy=?,version=?,symbol=?,direction=?,timestamp=?,timeframe=?,reason=?,pipeline_status=?,metadata=?,updated_at=? WHERE signal_key=?""",
                    (signal.strategy,signal.version,signal.symbol,signal.direction,signal.timestamp.isoformat(),signal.timeframe,signal.reason,pipeline_status,json.dumps(metadata,default=str),ts,signal_key),
                )
            else:
                created_at=created_at or ts
                row=(signal_id,signal_key,signal.strategy,signal.version,signal.symbol,signal.direction,signal.timestamp.isoformat(),signal.timeframe,signal.reason,pipeline_status,json.dumps(metadata,default=str),created_at,ts)
                c.execute("INSERT INTO signal_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",row)
            c.commit()
        return signal_id

    def update_signal_status(self,signal_id,status):
        ts=datetime.now(timezone.utc).isoformat()
        with self._connect() as c:
            c.execute("UPDATE signal_events SET pipeline_status=?,updated_at=? WHERE signal_id=?",(status,ts,signal_id))
            c.commit()

    def record_delivery(self,signal_id,*,channel,status,attempted_at=None,error_text=None,message_type=None,metadata=None):
        ts=attempted_at or datetime.now(timezone.utc).isoformat()
        meta=metadata or {}
        with self._connect() as c:
            c.execute(
                "INSERT INTO deliveries(signal_id,channel,status,attempted_at,error,message_type,metadata) VALUES(?,?,?,?,?,?,?)",
                (signal_id,channel,status,ts,error_text,message_type,json.dumps(meta,default=str)),
            )
            c.commit()

    def signal_send_state(self,key):
        with self._connect() as c: row=c.execute("SELECT send_count,first_sent_at,last_sent_at FROM signals WHERE signal_key=?",(key,)).fetchone()
        return dict(row) if row else {"send_count":0,"first_sent_at":None,"last_sent_at":None}

    def failed_deliveries(self,limit=20):
        with self._connect() as c:
            rows=c.execute("""SELECT d.* FROM deliveries d JOIN (SELECT signal_id,MAX(id) AS max_id FROM deliveries GROUP BY signal_id) latest ON latest.max_id=d.id WHERE d.status='FAILED' ORDER BY d.id LIMIT ?""",(int(limit),)).fetchall()
        out=[]
        for r in rows:
            item=dict(r)
            try:item["metadata"]=json.loads(item.get("metadata") or "{}")
            except Exception:item["metadata"]={}
            out.append(item)
        return out

    def save_market_data_cache(self,cache_key,symbol,period,interval,validate_hourly,payload,updated_at):
        row=(cache_key,symbol,period,interval,int(bool(validate_hourly)),payload,updated_at)
        with self._connect() as c:
            c.execute(
                "INSERT INTO market_data_cache VALUES(?,?,?,?,?,?,?) ON CONFLICT(cache_key) DO UPDATE SET symbol=excluded.symbol,period=excluded.period,interval=excluded.interval,validate_hourly=excluded.validate_hourly,payload=excluded.payload,updated_at=excluded.updated_at",
                row,
            )
            c.commit()

    def market_data_cache_health(self):
        if not self.turso_enabled:
            return {"enabled":False,"remote":False,"reason":"LOCAL_SQLITE"}
        try:
            with self._connect() as c:
                c.execute("SELECT 1").fetchone()
            return {"enabled":True,"remote":True,"reason":"OK"}
        except Exception as exc:
            return {"enabled":True,"remote":False,"reason":str(exc)}

    def load_market_data_cache(self,cache_key):
        with self._connect() as c:
            row=c.execute("SELECT * FROM market_data_cache WHERE cache_key=?",(cache_key,)).fetchone()
        return dict(row) if row else None

    def record_scan_run(self,run_id,strategy_id,started_at,status,payload,finished_at=None):
        with self._connect() as c:
            c.execute(
                "INSERT OR REPLACE INTO scan_runs VALUES(?,?,?,?,?,?)",
                (run_id,strategy_id,started_at,finished_at,status,json.dumps(payload or {},default=str)),
            )
            c.commit()

    def load_scan_runs(self,limit=50):
        with self._connect() as c: rows=c.execute("SELECT * FROM scan_runs ORDER BY started_at DESC LIMIT ?",(int(limit),)).fetchall()
        out=[]
        for r in rows:
            try: payload=json.loads(r["payload"] or "{}")
            except Exception: payload={}
            out.append({**dict(r),"payload":payload})
        return out

    # --- scan-level error alert state (durable dedup) -------------------------
    # The incident record lives in the same durable database as every other runtime
    # state table, so suppression survives process restarts and redeploys.

    def load_scan_error_alert(self,strategy_id):
        with self._connect() as c:
            row=c.execute("SELECT * FROM scan_error_alerts WHERE strategy_id=?",(strategy_id,)).fetchone()
        return dict(row) if row else None

    def save_scan_error_alert(self,strategy_id,fingerprint,*,first_sent_at,last_sent_at,suppressed=0,updated_at=None):
        updated_at=updated_at or datetime.now(timezone.utc).isoformat()
        row=(strategy_id,fingerprint,first_sent_at,last_sent_at,int(suppressed),updated_at)
        with self._connect() as c:
            c.execute(
                "INSERT INTO scan_error_alerts(strategy_id,fingerprint,first_sent_at,last_sent_at,suppressed,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(strategy_id) DO UPDATE SET fingerprint=excluded.fingerprint,first_sent_at=excluded.first_sent_at,last_sent_at=excluded.last_sent_at,suppressed=excluded.suppressed,updated_at=excluded.updated_at",
                row,
            )
            c.commit()

    def bump_scan_error_alert_suppression(self,strategy_id):
        """Count a suppressed repeat locally; counters never need remote sync."""
        with self._connect() as c:
            c.execute("UPDATE scan_error_alerts SET suppressed=suppressed+1,updated_at=? WHERE strategy_id=?",(datetime.now(timezone.utc).isoformat(),strategy_id)); c.commit()

    def clear_scan_error_alert(self,strategy_id):
        with self._connect() as c:
            c.execute("DELETE FROM scan_error_alerts WHERE strategy_id=?",(strategy_id,))
            c.commit()

    def signal_event(self,signal_id):
        """Read the canonical lifecycle row for one signal by its event id.

        Returns the row as a dict, or None when the event is unknown.
        """
        with self._connect() as c:
            row=c.execute("SELECT * FROM signal_events WHERE signal_id=?",(signal_id,)).fetchone()
        return dict(row) if row else None

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
            item["signal"]=item["direction"]; item["strategy_version"]=item["version"]; item["metadata"]=metadata
            item["entry"]=metadata.get("entry"); item["stop_loss"]=metadata.get("stop_loss"); item["take_profit"]=metadata.get("take_profit")
            try:
                item["delivery"]=self.delivery_status(r["signal_id"]); item["send_state"]=self.signal_send_state(r["signal_key"])
            except Exception:
                item["delivery"]=None; item["send_state"]={"send_count":0,"first_sent_at":None,"last_sent_at":None}
            out.append(item)
        return out

    def record_signal_send(self,key,sent_at,reminder_due_at=None,message_text=None,metadata=None):
        with self._connect() as c:
            row=c.execute("SELECT send_count FROM signals WHERE signal_key=?",(key,)).fetchone()
            if row is None:
                count=1
                c.execute(
                    "INSERT INTO signals VALUES(?,?,?,?,?,?,?,?)",
                    (key,1,sent_at,sent_at,reminder_due_at,0,message_text,json.dumps(metadata or {},default=str)),
                )
            else:
                count=min(int(row["send_count"])+1,2)
                c.execute(
                    "UPDATE signals SET send_count=?,last_sent_at=?,reminder_sent=? WHERE signal_key=?",
                    (count,sent_at,1 if count>=2 else 0,key),
                )
            c.commit()
        return count

    def signal_count(self,key):
        with self._connect() as c: row=c.execute("SELECT send_count FROM signals WHERE signal_key=?",(key,)).fetchone()
        return int(row["send_count"]) if row else 0

    def due_reminders(self,now_iso):
        with self._connect() as c: rows=c.execute("SELECT * FROM signals WHERE send_count=1 AND reminder_sent=0 AND reminder_due_at IS NOT NULL AND reminder_due_at<=?",(now_iso,)).fetchall()
        return [dict(x) for x in rows]

    def mark_reminder_sent(self,key,sent_at):
        with self._connect() as c:
            c.execute(
                "UPDATE signals SET send_count=2,reminder_sent=1,last_sent_at=? WHERE signal_key=? AND send_count=1",
                (sent_at,key),
            )
            c.commit()
