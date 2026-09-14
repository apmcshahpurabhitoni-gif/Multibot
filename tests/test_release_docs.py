from pathlib import Path

from config import APP_VERSION, WHAT_IS_NEW
from release_notes import RELEASE_HIGHLIGHTS, telegram_whats_new
from telegram import msg_whats_new

ROOT = Path(__file__).resolve().parents[1]


def test_config_reexports_canonical_release_source():
    assert WHAT_IS_NEW == RELEASE_HIGHLIGHTS


def test_telegram_uses_canonical_release_source():
    assert msg_whats_new() == telegram_whats_new()
    for item in RELEASE_HIGHLIGHTS:
        assert item in msg_whats_new()


def test_release_documents_match_canonical_source():
    expected = "\n".join(f"- {item}" for item in RELEASE_HIGHLIGHTS)
    whats = (ROOT / "WHATS_NEW.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"v{APP_VERSION}" in whats
    assert expected in whats
    assert f"## 🆕 What's New — v{APP_VERSION}" in readme
    assert expected in readme
