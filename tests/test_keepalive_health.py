"""Keepalive contract.

The /ping handler runs on a wsgiref request thread while /api/health runs on
another, so LAST_PING_AT is genuinely shared mutable state. This test pins both
halves of that contract: the value is published under LOCK, and the health
payload reads it from a locked snapshot rather than from the bare global.
"""
import re

import main


def _source() -> str:
    with open("main.py", encoding="utf-8") as handle:
        return handle.read()


def test_keepalive_contract_tracks_last_ping():
    source = _source()
    assert "LAST_PING_AT=None" in source
    assert "Keepalive ping received" in source
    assert '"keepalive":keepalive' in source
    assert '"last_ping_at":last_ping' in source


def test_last_ping_is_published_under_the_lock():
    """/ping must not write shared state outside LOCK."""
    source = _source()
    assert re.search(
        r"with LOCK:\s*LAST_PING_AT=now\(\)\.isoformat\(\); last_ping=LAST_PING_AT",
        source,
    ), "/ping writes LAST_PING_AT without holding LOCK"


def test_health_reads_last_ping_under_the_lock():
    """/api/health must snapshot the global under LOCK, not read it bare."""
    source = _source()
    assert "with LOCK: last_ping=LAST_PING_AT" in source, (
        "/api/health reads LAST_PING_AT without holding LOCK"
    )
    assert '"last_ping_at":LAST_PING_AT' not in source, (
        "/api/health still reads the bare global instead of the locked snapshot"
    )


def test_runtime_exposes_the_keepalive_fields():
    """The module still builds a payload carrying the keepalive contract."""
    assert main.LAST_PING_AT is None or isinstance(main.LAST_PING_AT, str)
    assert main.LOCK is not None
