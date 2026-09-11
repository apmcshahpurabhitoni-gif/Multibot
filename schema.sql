-- MULTIBOT2 production persistence schema. No pending_sweeps workflow.
create table if not exists public.accounts(name text primary key,starting_balance double precision not null default 100000,balance double precision not null default 100000,daily_trades integer not null default 0,trades_today integer not null default 0,planned_risk_used double precision not null default 0,last_reset_date text,reset_date text,updated_at timestamptz not null default now());
create table if not exists public.active_trades(id text primary key,symbol text not null default '',market text not null default 'NSE',account text not null default '',strat text not null default '',type text not null default 'LONG',entry double precision not null default 0,sl double precision not null default 0,tp double precision not null default 0,qty double precision not null default 0,trail_sl double precision not null default 0,ts_trigger text,opened_at timestamptz,time_str text,updated_at timestamptz not null default now());

alter table public.active_trades add column if not exists symbol text not null default '';
alter table public.active_trades add column if not exists market text not null default 'NSE';
alter table public.active_trades add column if not exists account text not null default '';
alter table public.active_trades add column if not exists strat text not null default '';
alter table public.active_trades add column if not exists type text not null default 'LONG';
alter table public.active_trades add column if not exists entry double precision not null default 0;
alter table public.active_trades add column if not exists sl double precision not null default 0;
alter table public.active_trades add column if not exists tp double precision not null default 0;
alter table public.active_trades add column if not exists qty double precision not null default 0;
alter table public.active_trades add column if not exists trail_sl double precision not null default 0;
alter table public.active_trades add column if not exists ts_trigger text;
alter table public.active_trades add column if not exists opened_at timestamptz;
alter table public.active_trades add column if not exists time_str text;
alter table public.active_trades add column if not exists updated_at timestamptz not null default now();

create table if not exists public.closed_trades(id text primary key,symbol text not null default '',market text not null default 'NSE',account text not null default '',strat text not null default '',type text not null default 'LONG',entry double precision not null default 0,sl double precision not null default 0,tp double precision not null default 0,qty double precision not null default 0,trail_sl double precision not null default 0,ts_trigger text,opened_at timestamptz,time_str text,exit_price double precision not null default 0,pnl double precision not null default 0,result text not null default '',exit_reason text not null default '',close_time timestamptz,closed_at timestamptz,updated_at timestamptz not null default now());
alter table public.closed_trades add column if not exists sl double precision not null default 0;
alter table public.closed_trades add column if not exists tp double precision not null default 0;
alter table public.closed_trades add column if not exists qty double precision not null default 0;
alter table public.closed_trades add column if not exists trail_sl double precision not null default 0;
alter table public.closed_trades add column if not exists ts_trigger text;
alter table public.closed_trades add column if not exists opened_at timestamptz;
alter table public.closed_trades add column if not exists time_str text;

create table if not exists public.sent_signals(sig_key text primary key,send_count integer not null default 0,last_sent_ts bigint,reminder_due_at timestamptz,message_text text,metadata jsonb,updated_at timestamptz not null default now());
alter table public.sent_signals add column if not exists reminder_due_at timestamptz;
alter table public.sent_signals add column if not exists message_text text;
alter table public.sent_signals add column if not exists metadata jsonb;

create index if not exists active_trades_account_idx on public.active_trades(account);
create index if not exists closed_trades_account_idx on public.closed_trades(account);
create index if not exists closed_trades_closed_at_idx on public.closed_trades(closed_at);
create index if not exists sent_signals_last_sent_idx on public.sent_signals(last_sent_ts);

create table if not exists public.signal_events(signal_id text primary key,signal_key text not null,strategy text not null,version text,symbol text not null,direction text not null,timestamp timestamptz not null,timeframe text,reason text,pipeline_status text not null,metadata jsonb not null default '{}'::jsonb,created_at timestamptz not null default now(),updated_at timestamptz not null default now());
create table if not exists public.signal_deliveries(id bigserial primary key,signal_id text not null references public.signal_events(signal_id) on delete cascade,channel text not null,status text not null,attempted_at timestamptz not null default now(),error text,message_type text,metadata jsonb not null default '{}'::jsonb);
with ranked as (
  select signal_id, signal_key, row_number() over (partition by signal_key order by updated_at desc, created_at desc, ctid desc) as rn,
         first_value(signal_id) over (partition by signal_key order by updated_at desc, created_at desc, ctid desc) as keep_id
  from public.signal_events
)
update public.signal_deliveries d set signal_id = r.keep_id
from ranked r
where d.signal_id = r.signal_id and r.rn > 1;
with ranked as (
  select ctid, row_number() over (partition by signal_key order by updated_at desc, created_at desc, ctid desc) as rn
  from public.signal_events
)
delete from public.signal_events where ctid in (select ctid from ranked where rn > 1);
create unique index if not exists signal_events_key_uidx on public.signal_events(signal_key);
create index if not exists signal_events_timestamp_idx on public.signal_events(timestamp desc);
create index if not exists signal_deliveries_signal_idx on public.signal_deliveries(signal_id,attempted_at desc);

create table if not exists public.scan_runs(id text primary key,strategy_id text not null,started_at timestamptz not null,finished_at timestamptz,status text not null,payload jsonb not null default '{}'::jsonb);
create index if not exists scan_runs_started_idx on public.scan_runs(started_at desc);

-- Runtime-aligned durable Yahoo cache. These columns exactly match DatabaseManager.save_market_data_cache().
create table if not exists public.market_data_cache(
    cache_key text primary key,
    symbol text not null,
    period text not null,
    interval text not null,
    validate_hourly boolean not null default true,
    payload jsonb not null,
    updated_at timestamptz not null default now()
);
alter table public.market_data_cache add column if not exists period text;
alter table public.market_data_cache add column if not exists interval text;
alter table public.market_data_cache add column if not exists validate_hourly boolean not null default true;
alter table public.market_data_cache add column if not exists payload jsonb;
alter table public.market_data_cache add column if not exists updated_at timestamptz not null default now();
alter table public.market_data_cache add column if not exists symbol text;
create index if not exists market_data_cache_symbol_idx on public.market_data_cache(symbol,updated_at desc);
create index if not exists market_data_cache_updated_idx on public.market_data_cache(updated_at desc);

-- Keep this schema server-side; never expose SUPABASE_KEY to the browser.
