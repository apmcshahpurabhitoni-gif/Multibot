import main


def test_keepalive_contract_tracks_last_ping():
    source = open("main.py", encoding="utf-8").read()
    assert "LAST_PING_AT=None" in source
    assert 'Keepalive ping received' in source
    assert '"keepalive":keepalive' in source
    assert '"last_ping_at":LAST_PING_AT' in source
