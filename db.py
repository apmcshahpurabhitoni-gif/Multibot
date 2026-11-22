"""Durable runtime state backed by Turso/libSQL, with SQLite for local development."""
from __future__ import annotations

import json
import os
import sqlite3
import time
import threading
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
    def description(self): return self._cursor.description
    @property
    def rowcount(self): return self._cursor.rowcount
    @property
    def lastrowid(self): return self._cursor.lastrowid
    def _convert(self,row):
        if row is None:return None
        names=[column[0] for column in (self.description or ())]
        return _RemoteRow(names,row)
    def fetchone(self):
        try:return self._convert(self._cursor.fetchone())
        except Exception as exc:raise DatabaseError(f"Turso cursor fetch failed: {exc}") from exc
    def fetchall(self):
        try:return [self._convert(row) for row in (self._cursor.fetchall() or [])]
        except Exception as exc:raise DatabaseError(f"Turso cursor fetch failed: {exc}") from exc
    def fetchmany(self,size=None):
        try:
            rows=self._cursor.fetchmany(size) if size is not None else self._cursor.fetchmany()
            return [self._convert(row) for row in (rows or [])]
        except Exception as exc:raise DatabaseError(f"Turso cursor fetch failed: {exc}") from exc
    def __iter__(self):
        while True:
            row=self.fetchone()
            if row is None:break
            yield row


class _RemoteConnection:
    """sqlite3-compatible adapter with one commit per pending write."""
    _WRITE_KEYWORDS={"INSERT","UPDATE","DELETE","REPLACE","CREATE","DROP","ALTER","VACUUM","REINDEX","PRAGMA","BEGIN","SAVEPOINT","RELEASE","END"}
    def __init__(self,connection):
        self._connection=connection
        self._transaction_pending=False
    def execute(self,sql,parameters=()):
        try:cursor=self._connection.execute(sql,tuple(parameters or ()))
        except Exception as exc:raise DatabaseError(f"Turso SQL execution failed: {exc}") from exc
        statement=str(sql).lstrip()
        keyword=statement.split(None,1)[0].upper() if statement else ""
        if keyword in self._WRITE_KEYWORDS:self._transaction_pending=True
        return _RemoteCursor(cursor)
    def executemany(self,sql,seq_of_parameters):
        cursor=None
        for parameters in seq_of_parameters:cursor=self.execute(sql,parameters)
        return cursor
    def executescript(self,script):
        for statement in script.split(";"):
            if statement.strip():self.execute(statement)
    def commit(self):
        if not self._transaction_pending:return
        try:self._connection.commit()
        except Exception as exc:raise DatabaseError(f"Turso commit failed: {exc}") from exc
        self._transaction_pending=False
    def rollback(self):
        if not self._transaction_pending:return
        try:self._connection.rollback()
        except Exception as exc:raise DatabaseError(f"Turso rollback failed: {exc}") from exc
        self._transaction_pending=False
    def close(self):self._connection.close()
    def __enter__(self):return self
    def __exit__(self,exc_type,exc_value,traceback):
        active_exception=exc_type is not None
        try:
            if active_exception:
                try:self.rollback()
                except Exception:pass
            else:
                try:self.commit()
                except Exception:
                    active_exception=True
                    try:self.rollback()
                    except Exception:pass
                    raise
        finally:
            try:self.close()
            except Exception:
                if not active_exception:raise
        return False


class DatabaseManager:
    """One database interface: Turso in deployments, SQLite in local tests."""

    _TABLES = (
        "accounts","trades","signals","signal_events","deliveries","scan_runs",
        "scan_error_alerts","market_data_cache","forex_calendar_week_cache","app_config",
        "forex_calendar_attempts",
    )

    def __init__(self,path=None):
        self.path=path or DEFAULT_DB_PATH
        self.turso_enabled=bool(TURSO_DATABASE_URL and TURSO_AUTH_TOKEN)
        self._health_check_lock=threading.Lock()
        self._health_check_at=0.0
        self._health_check_result=None
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
CREATE TABLE IF NOT EXISTS app_config(config_key TEXT PRIMARY KEY,payload TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runtime_leases(lease_key TEXT PRIMARY KEY,owner_id TEXT NOT NULL,expires_at REAL NOT NULL,updated_at TEXT NOT NULL);
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


    # --- single active runtime lease ----------------------------------------
    # Every deployed process may serve the dashboard, but only the process
    # holding this database-backed lease may scan, monitor trades or poll
    # Telegram. Atomic UPSERT makes the election safe across containers.
    @staticmethod
    def _is_retryable_turso_error(exc):
        message=str(exc).lower()
        return any(marker in message for marker in (
            "sqlite_busy","database is locked","database is busy",
            "interactive transaction was rolled back","stream was idle for too long",
            "stream is idle for too long","connection reset","connection closed",
            "broken pipe","timed out","timeout","temporarily unavailable","transport error",
        ))

    @staticmethod
    def _is_retryable_runtime_lease_error(exc):
        return DatabaseManager._is_retryable_turso_error(exc)

    def _retry_turso_operation(self,operation,*,operation_name="database operation",attempts=3):
        """Retry only idempotent work; every attempt must open a fresh connection."""
        attempts=max(1,int(attempts))
        for attempt in range(attempts):
            try:return operation()
            except Exception as exc:
                if not self.turso_enabled or not self._is_retryable_turso_error(exc):raise
                if attempt+1>=attempts:
                    raise DatabaseError(f"Turso {operation_name} failed after {attempts} attempts: {exc}") from exc
                time.sleep(0.2*(2**attempt))

    def run_idempotent_operation(self,operation,*,operation_name="database operation"):
        """Retry a repeatable read or idempotent write using fresh connections."""
        return self._retry_turso_operation(operation,operation_name=operation_name)

    def _retry_turso_cache_operation(self,operation):
        return self._retry_turso_operation(operation,operation_name="market-data cache operation")

    def acquire_runtime_lease(self,owner_id,*,ttl_seconds=60,now_epoch=None):
        import time
        now_epoch=float(time.time() if now_epoch is None else now_epoch)
        expires=now_epoch+max(15.0,float(ttl_seconds))
        stamp=datetime.now(timezone.utc).isoformat()
        # Commit the atomic UPSERT before verifying ownership. Keeping a
        # write followed by a read in the same interactive Hrana transaction
        # can leave the stream open long enough for Turso to roll it back.
        # The ownership read therefore uses a separate, fresh connection.
        # Repeating this claim is idempotent even if a prior commit response
        # was lost, and the conditional UPSERT still prevents lease stealing.
        for attempt in range(3):
            try:
                with self._connect() as c:
                    c.execute(
                        """INSERT INTO runtime_leases(lease_key,owner_id,expires_at,updated_at)
                           VALUES('primary',?,?,?)
                           ON CONFLICT(lease_key) DO UPDATE SET
                             owner_id=excluded.owner_id,
                             expires_at=excluded.expires_at,
                             updated_at=excluded.updated_at
                           WHERE runtime_leases.expires_at<=?
                              OR runtime_leases.owner_id=?""",
                        (str(owner_id),expires,stamp,now_epoch,str(owner_id)),
                    )
                with self._connect() as verify:
                    row=verify.execute(
                        "SELECT owner_id FROM runtime_leases WHERE lease_key='primary'"
                    ).fetchone()
                return bool(row and row["owner_id"]==str(owner_id))
            except Exception as exc:
                if attempt==2 or not self._is_retryable_runtime_lease_error(exc):
                    raise
                time.sleep(0.2 * (2 ** attempt))
        return False

    def renew_runtime_lease(self,owner_id,*,ttl_seconds=60,now_epoch=None):
        # Renewal is the same atomic claim: an expired owner may renew only if
        # nobody else has acquired the lease in the meantime.
        return self.acquire_runtime_lease(
            owner_id,ttl_seconds=ttl_seconds,now_epoch=now_epoch
        )

    def runtime_lease_is_owned(self,owner_id,*,now_epoch=None):
        import time
        current=float(time.time() if now_epoch is None else now_epoch)
        with self._connect() as c:
            row=c.execute(
                "SELECT owner_id,expires_at FROM runtime_leases WHERE lease_key='primary'"
            ).fetchone()
        return bool(
            row
            and row["owner_id"]==str(owner_id)
            and float(row["expires_at"])>current
        )

    def runtime_lease_owner(self):
        with self._connect() as c:
            row=c.execute(
                "SELECT owner_id,expires_at FROM runtime_leases WHERE lease_key='primary'"
            ).fetchone()
        return dict(row) if row else None

    def release_runtime_lease(self,owner_id):
        def release():
            with self._connect() as c:
                c.execute("DELETE FROM runtime_leases WHERE lease_key='primary' AND owner_id=?",(str(owner_id),))
        return self._retry_turso_operation(release,operation_name="release runtime lease")
    def load_app_config(self,key):
        """Load an operator configuration document from the durable store."""
        with self._connect() as connection:
            row=connection.execute("SELECT payload FROM app_config WHERE config_key=?",(key,)).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["payload"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise DatabaseError(f"Stored configuration {key!r} is invalid JSON: {exc}") from exc

    def save_app_config(self,key,payload):
        """Atomically replace one operator configuration document."""
        encoded=json.dumps(payload,separators=(",",":"),ensure_ascii=False)
        def write():
            with self._connect() as connection:
                connection.execute("INSERT OR REPLACE INTO app_config(config_key,payload,updated_at) VALUES(?,?,?)",(key,encoded,datetime.now(timezone.utc).isoformat()))
        return self._retry_turso_operation(write,operation_name="save app configuration")
    def load_accounts(self,names,starting_balance,today):
        """Create/refresh account rows; replay is safe because values are deterministic."""
        sizes=starting_balance if isinstance(starting_balance,dict) else None
        names=tuple(names)
        def load():
            with self._connect() as c:
                for name in names:
                    opening=float(sizes.get(name,ACCOUNT_SIZE_INR) if sizes is not None else starting_balance)
                    row=c.execute("SELECT * FROM accounts WHERE name=?",(name,)).fetchone()
                    if row is None:c.execute("INSERT INTO accounts VALUES(?,?,?,?,?,?)",(name,opening,opening,0,0.0,today))
                    elif row["reset_date"]!=today:c.execute("UPDATE accounts SET trades_today=0,planned_risk_used=0,reset_date=? WHERE name=?",(today,name))
                if not names:return {}
                rows=c.execute("SELECT * FROM accounts WHERE name IN (%s)" % ",".join("?" for _ in names),names).fetchall()
            return {x["name"]:dict(x) for x in rows}
        return self._retry_turso_operation(load,operation_name="load accounts")
    def account_trade_count(self,name):
        """Trades ever recorded against an account, open and closed.

        A book that has traded is never deleted: the trades name the account and
        removing the book would orphan that history.
        """
        with self._connect() as c:
            live=c.execute("SELECT count(*) AS n FROM trades WHERE json_extract(payload,'$.account')=?",(name,)).fetchone()
        return int(live["n"] if live and "n" in live.keys() else 0)

    def save_account(self,name,*,balance,trades_today,planned_risk_used,reset_date):
        def write():
            with self._connect() as c:
                c.execute("UPDATE accounts SET balance=?,trades_today=?,planned_risk_used=?,reset_date=? WHERE name=?",(balance,trades_today,planned_risk_used,reset_date,name))
        return self._retry_turso_operation(write,operation_name="save account")
    def save_trade(self,trade_id,status,payload,updated_at):
        payload=dict(payload);payload["status"]=status
        encoded=json.dumps(payload,default=str)
        def write():
            with self._connect() as c:
                c.execute("INSERT INTO trades VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,payload=excluded.payload,updated_at=excluded.updated_at",(trade_id,status,encoded,updated_at))
        return self._retry_turso_operation(write,operation_name="save trade")
    def load_trades(self,status=None):
        with self._connect() as c: rows=c.execute("SELECT payload FROM trades"+(" WHERE status=?" if status else "")+" ORDER BY updated_at DESC",(status,) if status else ()).fetchall()
        return [json.loads(x["payload"]) for x in rows]

    def record_signal_event(self,signal_id,signal_key,signal,*,pipeline_status,created_at=None):
        ts=created_at or datetime.now(timezone.utc).isoformat()
        metadata=dict(signal.metadata or {})
        metadata.update({"entry":getattr(signal,"entry",None),"stop_loss":getattr(signal,"stop_loss",None),"take_profit":getattr(signal,"take_profit",None)})
        encoded=json.dumps(metadata,default=str);requested_id=str(signal_id)
        def write():
            canonical_id=requested_id
            with self._connect() as c:
                existing=c.execute("SELECT signal_id,created_at FROM signal_events WHERE signal_key=?",(signal_key,)).fetchone()
                if existing:
                    canonical_id=str(existing["signal_id"])
                    c.execute("""UPDATE signal_events SET strategy=?,version=?,symbol=?,direction=?,timestamp=?,timeframe=?,reason=?,pipeline_status=?,metadata=?,updated_at=? WHERE signal_key=?""",(signal.strategy,signal.version,signal.symbol,signal.direction,signal.timestamp.isoformat(),signal.timeframe,signal.reason,pipeline_status,encoded,ts,signal_key))
                else:
                    created=created_at or ts
                    row=(canonical_id,signal_key,signal.strategy,signal.version,signal.symbol,signal.direction,signal.timestamp.isoformat(),signal.timeframe,signal.reason,pipeline_status,encoded,created,ts)
                    c.execute("INSERT INTO signal_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",row)
            return canonical_id
        return self._retry_turso_operation(write,operation_name="record signal event")
    def update_signal_status(self,signal_id,status):
        ts=datetime.now(timezone.utc).isoformat()
        def write():
            with self._connect() as c:
                c.execute("UPDATE signal_events SET pipeline_status=?,updated_at=? WHERE signal_id=?",(status,ts,signal_id))
        return self._retry_turso_operation(write,operation_name="update signal status")
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
        """Persist a cache value; its UPSERT is safe to retry on a fresh connection."""
        row=(cache_key,symbol,period,interval,int(bool(validate_hourly)),payload,updated_at)

        def write():
            with self._connect() as c:
                c.execute(
                    "INSERT INTO market_data_cache VALUES(?,?,?,?,?,?,?) ON CONFLICT(cache_key) DO UPDATE SET symbol=excluded.symbol,period=excluded.period,interval=excluded.interval,validate_hourly=excluded.validate_hourly,payload=excluded.payload,updated_at=excluded.updated_at",
                    row,
                )

        return self._retry_turso_cache_operation(write)

    def market_data_cache_health(self):
        """Check remote reads and writes, cached briefly to avoid probe traffic."""
        if not self.turso_enabled:return {"enabled":False,"remote":False,"reason":"LOCAL_SQLITE"}
        with self._health_check_lock:
            checked_at=time.monotonic()
            if self._health_check_result is not None and checked_at-self._health_check_at<30:
                return dict(self._health_check_result)
            stamp=datetime.now(timezone.utc).isoformat()
            def probe():
                with self._connect() as c:
                    c.execute("SELECT 1").fetchone()
                    c.execute("INSERT INTO market_data_cache(cache_key,symbol,period,interval,validate_hourly,payload,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(cache_key) DO UPDATE SET updated_at=excluded.updated_at",("__multibot_health_probe__","__HEALTHCHECK__","0","0",0,"{}",stamp))
            try:
                self._retry_turso_operation(probe,operation_name="read/write health probe")
                result={"enabled":True,"remote":True,"reason":"READ_WRITE_OK"}
            except Exception as exc:result={"enabled":True,"remote":False,"reason":str(exc)}
            self._health_check_at=checked_at;self._health_check_result=dict(result)
            return result

    def load_market_data_cache(self,cache_key):
        """Read one cache value, retrying transient Turso failures safely."""
        def read():
            with self._connect() as c:
                row=c.execute("SELECT * FROM market_data_cache WHERE cache_key=?",(cache_key,)).fetchone()
            return dict(row) if row else None

        return self._retry_turso_cache_operation(read)

    def record_scan_run(self,run_id,strategy_id,started_at,status,payload,finished_at=None):
        """Upsert by stable run_id so an ambiguous commit can be retried safely."""
        row=(run_id,strategy_id,started_at,finished_at,status,json.dumps(payload or {},default=str))
        def write():
            with self._connect() as c:
                c.execute("""INSERT INTO scan_runs(id,strategy_id,started_at,finished_at,status,payload)
                    VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                    strategy_id=excluded.strategy_id,started_at=excluded.started_at,
                    finished_at=excluded.finished_at,status=excluded.status,payload=excluded.payload""",row)
        return self._retry_turso_operation(write,operation_name="record scan run")
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
        def write():
            with self._connect() as c:
                c.execute("INSERT INTO scan_error_alerts(strategy_id,fingerprint,first_sent_at,last_sent_at,suppressed,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(strategy_id) DO UPDATE SET fingerprint=excluded.fingerprint,first_sent_at=excluded.first_sent_at,last_sent_at=excluded.last_sent_at,suppressed=excluded.suppressed,updated_at=excluded.updated_at",row)
        return self._retry_turso_operation(write,operation_name="save scan error alert")
    def bump_scan_error_alert_suppression(self,strategy_id):
        """Count a suppressed repeat locally; counters never need remote sync."""
        with self._connect() as c:
            c.execute("UPDATE scan_error_alerts SET suppressed=suppressed+1,updated_at=? WHERE strategy_id=?",(datetime.now(timezone.utc).isoformat(),strategy_id)); c.commit()

    def clear_scan_error_alert(self,strategy_id):
        def write():
            with self._connect() as c:c.execute("DELETE FROM scan_error_alerts WHERE strategy_id=?",(strategy_id,))
        return self._retry_turso_operation(write,operation_name="clear scan error alert")
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
        def write():
            with self._connect() as c:
                c.execute("UPDATE signals SET send_count=2,reminder_sent=1,last_sent_at=? WHERE signal_key=? AND send_count=1",(sent_at,key))
        return self._retry_turso_operation(write,operation_name="mark reminder sent")
