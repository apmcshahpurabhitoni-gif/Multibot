from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_scan_runs_are_remote_durable_and_restored():
    db = (ROOT / "db.py").read_text(encoding="utf-8")
    schema = (ROOT / "schema.sql").read_text(encoding="utf-8")

    assert "self._restore_scan_runs_if_needed()" in db
    assert 'self._supabase_request("GET","scan_runs"' in db
    assert 'self._supabase_request("POST","scan_runs"' in db
    assert 'CREATE TABLE IF NOT EXISTS public.scan_runs' in schema
    assert 'create index if not exists scan_runs_started_idx' in schema


def test_scan_history_keeps_payload_as_json():
    db = (ROOT / "db.py").read_text(encoding="utf-8")
    assert 'json.dumps(payload or {},default=str)' in db
    assert 'json.loads(r["payload"] or "{}")' in db
