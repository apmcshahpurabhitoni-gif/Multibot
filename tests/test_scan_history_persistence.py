from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_scan_history_is_created_in_the_primary_database():
    db = (ROOT / "db.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS scan_runs" in db
    assert 'def record_scan_run(self,run_id,strategy_id,started_at,status,payload,finished_at=None):' in db
    assert 'INSERT INTO scan_runs(id,strategy_id,started_at,finished_at,status,payload)' in db
    assert 'ON CONFLICT(id) DO UPDATE SET' in db
    assert "def load_scan_runs(self,limit=50):" in db


def test_scan_history_keeps_payload_as_json():
    db = (ROOT / "db.py").read_text(encoding="utf-8")
    assert 'json.dumps(payload or {},default=str)' in db
    assert 'json.loads(r["payload"] or "{}")' in db


def test_turso_is_the_configured_remote_database():
    db = (ROOT / "db.py").read_text(encoding="utf-8")
    assert 'TURSO_DATABASE_URL=os.getenv("TURSO_DATABASE_URL","").strip()' in db
    assert 'TURSO_AUTH_TOKEN=os.getenv("TURSO_AUTH_TOKEN","").strip()' in db
    assert "libsql.connect(TURSO_DATABASE_URL,auth_token=TURSO_AUTH_TOKEN)" in db
    assert "_supabase_request" not in db
