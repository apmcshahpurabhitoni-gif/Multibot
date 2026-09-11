-- MULTIBOT2 production persistence schema. No pending_sweeps workflow.
create table if not exists public.accounts(name text primary key,starting_balance double precision not null default 100000,balance double precision not null default 100000,daily_trades integer not null default 0,trades_today integer not null default 0,planned_risk_used double precision not null default 0,last_reset_date text,reset_date text,updated_at timestamptz not null default now());
create table if not exists public.active_trades(id text primary key,symbol text not null default '',market text not null default 'NSE',account text not null default '',strat text not null default '',type text not null default 'LONG',entry double precision not null default 0,sl double precision not null default 0,tp double precision not null default 0,qty double precision not null default 0,trail_sl double precision not null default 0,ts_trigger text,opened_at timestamptz,time_str text,updated_at timestamptz not null default now());
create table if not exists public.closed_trades(id text primary key,symbol text not null default '',market text not null default 'NSE',account text not null default '',strat text not null default '',type text not null default 'LONG',entry double precision not null default 0,sl double precision not null default 0,tp double precision not null default 0,qty double precision not null default 0,trail_sl double precision not null default 0,ts_trigger text,opened_at timestamptz,time_str text,exit_price double precision not null default 0,pnl double precision not null default 0,result text not null default '',exit_reason text not null default '',close_time timestamptz,closed_at timestamptz,updated_at timestamptz not null default now());
create table if not exists public.sent_signals(sig_key text primary key,send_count integer not null default 0,last_sent_ts bigint,reminder_due_at timestamptz,message_text text,metadata jsonb,updated_at timestamptz not null default now());
alter table public.closed_trades add column if not exists sl double precision not null default 0;
alter table public.closed_trades add column if not exists tp double precision not null default 0;
alter table public.closed_trades add column if not exists qty double precision not null default 0;
alter table public.closed_trades add column if not exists trail_sl double precision not null default 0;
alter table public.closed_trades add column if not exists ts_trigger text;
alter table public.closed_trades add column if not exists opened_at timestamptz;
alter table public.closed_trades add column if not exists time_str text;
alter table public.sent_signals add column if not exists reminder_due_at timestamptz;
alter table public.sent_signals add column if not exists message_text text;
alter table public.sent_signals add column if not exists metadata jsonb;
create index if not exists active_trades_account_idx on public.active_trades(account);create index if not exists closed_trades_account_idx on public.closed_trades(account);create index if not exists closed_trades_closed_at_idx on public.closed_trades(closed_at);create index if not exists sent_signals_last_sent_idx on public.sent_signals(last_sent_ts);
-- Keep this schema server-side; never expose SUPABASE_KEY to the browser.

-- Canonical signal lifecycle and delivery history.
create table if not exists public.signal_events(signal_id text primary key,signal_key text not null,strategy text not null,version text,symbol text not null,direction text not null,timestamp timestamptz not null,timeframe text,reason text,pipeline_status text not null,metadata jsonb not null default '{}'::jsonb,created_at timestamptz not null default now(),updated_at timestamptz not null default now());
create table if not exists public.signal_deliveries(id bigserial primary key,signal_id text not null references public.signal_events(signal_id) on delete cascade,channel text not null,status text not null,attempted_at timestamptz not null default now(),error text,message_type text,metadata jsonb not null default '{}'::jsonb);
create index if not exists signal_events_timestamp_idx on public.signal_events(timestamp desc);create index if not exists signal_events_key_idx on public.signal_events(signal_key);create index if not exists signal_deliveries_signal_idx on public.signal_deliveries(signal_id,attempted_at desc);
