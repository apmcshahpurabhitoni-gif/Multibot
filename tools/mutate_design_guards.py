"""Mutation-test every guard added in this pass.

Each mutation reverts one fix in a throwaway copy of the whole project and runs
only the guard that protects it. A guard that still passes on the broken state
is worse than no guard, so every run must exit non-zero.
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]

APP = "app.js"
AO = "appearance-overrides.css"
ST = "styles.css"
HTML = "dashboard.html"
CHANNELS = "channels.py"
NOTIFIER = "notification_service.py"
MAIN = "main.py"
ASSETS_GUARD = "test_asset_category_stacks_on_a_phone_instead_of_paying_for_a_rail"
CAUSE3_GUARD = "test_asset_category_items_holds_four_columns_above_the_breakpoint"

# A bare guard name lives in the visual audit module; "file.py::name" points at
# any other module, so a guard added somewhere else is still mutation-tested.
DEFAULT_GUARD_FILE = "tests/test_visual_consistency_audit.py"

MUTATIONS = [
    (
        "chevron back in the meta strip, above its own title",
        APP,
        (
            """      <div class="calendar-event-head">
        <strong class="calendar-title">${escapeHtml(item.title||"Economic event")}</strong>
        ${expandButton(key,"event")}
      </div>
      <div class="calendar-meta">
        <strong class="calendar-time-value">${escapeHtml(item.time||"All day")}</strong>""",
            """      <div class="calendar-meta">
        <strong class="calendar-title">${escapeHtml(item.title||"Economic event")}</strong>
        <strong class="calendar-time-value">${escapeHtml(item.time||"All day")}</strong>""",
        ),
        "test_calendar_event_chevron_shares_the_title_row",
    ),
    (
        "impact pill hidden again below 390px",
        AO,
        (
            "@media(max-width:390px){\n  /* Superseded: the impact pill was dropped",
            "@media(max-width:390px){\n  #page-calendar .calendar-meta .impact-pill{display:none!important}\n  /* Superseded: the impact pill was dropped",
        ),
        "test_calendar_impact_pill_is_not_hidden_on_a_phone",
    ),
    (
        "routing shouts the raw account id again",
        APP,
        (
            "const account=escapeHtml(accountLabel(rule.account));",
            "const account=escapeHtml(rule.account.toUpperCase());",
        ),
        "test_accounts_are_named_not_spelled_out",
    ),
    (
        "status line back to its 96-character paragraph",
        APP,
        (
            'settingsStatus("Saved \u00b7 applied to the running bot","info");',
            'settingsStatus("Saved on the server and applied to the running bot. Nothing here changes a trade until you save.","info");',
        ),
        "test_settings_status_line_is_one_line_and_one_fact",
    ),
    (
        "money fields lose their unit",
        APP,
        (
            'field("starting_balance","Capital",1,100000000,1000,true)',
            'field("starting_balance","Capital",1,100000000,1000)',
        ),
        "test_money_limit_fields_carry_their_unit",
    ),
    (
        "dead repeat() columns restored on .universe-grid",
        ST,
        (
            ".universe-grid{display:grid;gap:8px}",
            ".universe-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}",
        ),
        "test_universe_grid_carries_no_dead_column_declaration",
    ),
    (
        "category rail pinned to a fixed 132px again",
        AO,
        (
            "html #page-tools .tool-universe .universe-grid>.asset-category{\n  grid-template-columns:minmax(102px,max-content) minmax(0,1fr)!important;\n  align-items:start!important;\n}",
            "html #page-tools .tool-universe .universe-grid>.asset-category{\n  grid-template-columns:132px minmax(0,1fr)!important;\n  align-items:start!important;\n}",
        ),
        ASSETS_GUARD,
    ),
    (
        "desktop rail goes back to sizing itself per label",
        AO,
        (
            "grid-template-columns:minmax(102px,max-content) minmax(0,1fr)!important;",
            "grid-template-columns:auto minmax(0,1fr)!important;",
        ),
        ASSETS_GUARD,
    ),
    (
        "phone rows go back to a label-width rail",
        AO,
        (
            "@media(max-width:560px){\n  html #page-tools .tool-universe .universe-grid>.asset-category{\n    grid-template-columns:minmax(0,1fr)!important;\n    row-gap:6px!important;\n  }",
            "@media(max-width:560px){\n  html #page-tools .tool-universe .universe-grid>.asset-category{\n    grid-template-columns:auto minmax(0,1fr)!important;\n  }",
        ),
        ASSETS_GUARD,
    ),
    (
        "the label floats in the middle of the ticker block again",
        AO,
        (
            "  grid-template-columns:minmax(102px,max-content) minmax(0,1fr)!important;\n  align-items:start!important;",
            "  grid-template-columns:minmax(102px,max-content) minmax(0,1fr)!important;\n  align-items:center!important;",
        ),
        ASSETS_GUARD,
    ),
    (
        "the desktop four-column escalation drops back to two columns",
        AO,
        (
            "  html #page-tools .tool-universe .asset-category-items{\n    grid-template-columns:repeat(4,minmax(0,1fr))!important;",
            "  html #page-tools .tool-universe .asset-category-items{\n    grid-template-columns:repeat(2,minmax(0,1fr))!important;",
        ),
        CAUSE3_GUARD,
    ),
    (
        "the four-column rule escapes its desktop media query onto a phone",
        AO,
        (
            "@media(min-width:761px){\n  html #page-tools .tool-universe .asset-category-items{\n    grid-template-columns:repeat(4,minmax(0,1fr))!important;\n  }\n}",
            "html #page-tools .tool-universe .asset-category-items{\n  grid-template-columns:repeat(4,minmax(0,1fr))!important;\n}",
        ),
        CAUSE3_GUARD,
    ),
    (
        "the notifications card posts through the trading settings hook",
        HTML,
        (
            "data-notifications-save>Save</button>",
            "data-save-settings>Save</button>",
        ),
        "tests/test_notification_channels.py::test_the_notifications_card_does_not_borrow_the_trading_save_hook",
    ),
    (
        "a saved webhook secret is returned to the browser again",
        CHANNELS,
        (
            '        public["secret"] = ""',
            '        public["secret"] = channel["secret"]',
        ),
        "tests/test_notification_channels.py::test_a_read_never_returns_a_webhook_target_or_secret",
    ),
    (
        "every channel receives every event again, ignoring its subscriptions",
        NOTIFIER,
        (
            'return [c for c in configured if c["enabled"] and kind in c["events"]]',
            'return [c for c in configured if c["enabled"]]',
        ),
        "tests/test_notification_channels.py::test_a_channel_only_receives_the_events_it_subscribed_to",
    ),
    (
        "summaries go out again even when no channel subscribes to them",
        MAIN,
        (
            'if SERVICE is None or not _summary_subscribers(): return []',
            'if SERVICE is None: return []',
        ),
        "tests/test_notification_channels.py::test_summaries_follow_the_live_subscriptions",
    ),
]


def run(argv, cwd):
    return subprocess.run(
        argv, cwd=cwd, capture_output=True, text=True, timeout=900
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep",
        action="store_true",
        help="leave the mutated copies on disk instead of removing them",
    )
    args = parser.parse_args()

    failures = []

    def fresh_copy(root):
        if root.exists():
            shutil.rmtree(root)
        # The whole project, not a partial copy: a partial tree changes what
        # the suite can even import, and a green control on the wrong tree makes
        # every failure below meaningless. That has happened twice already.
        #
        # The runtime database and its WAL sidecars are excluded because the
        # preview holds them open and rewrites them while the copy runs: a
        # sidecar can disappear between listing and reading and abort the whole
        # harness. None of the design guards read the database.
        shutil.copytree(SRC, root, ignore=shutil.ignore_patterns(
            "__pycache__", ".git", "*.pyc", "*.db", "*.db-shm", "*.db-wal",
            "*.db-journal", ".pytest_cache",
        ))
        return root

    with tempfile.TemporaryDirectory(prefix="mut-") as scratch:
        control_root = fresh_copy(Path(scratch) / "control")
        control = run([sys.executable, "-m", "pytest", "-q"], control_root)
        print(f"clean-tree control: exit={control.returncode}")
        if control.returncode != 0:
            print(control.stdout[-3000:])
            return 1
        print(control.stdout.strip().splitlines()[-1])

        for index, (name, relative, (old, new), guard) in enumerate(MUTATIONS):
            work = fresh_copy(Path(scratch) / f"case-{index}")
            target = work / relative
            text = target.read_text(encoding="utf-8")
            if text.count(old) < 1:
                failures.append(f"{guard}: mutation target not found in {relative}")
                print(f"NOT APPLIED  {guard}")
                continue
            target.write_text(text.replace(old, new, 1), encoding="utf-8")
            result = run(
                [sys.executable, "-m", "pytest", "-q",
                 guard if "::" in guard else f"{DEFAULT_GUARD_FILE}::{guard}"],
                work,
            )
            caught = result.returncode != 0
            print(f"{'caught ' if caught else 'MISSED  '} {guard}  ({name})")
            if not caught:
                failures.append(f"{guard} passed on the reverted state")
            else:
                line = [ln for ln in result.stdout.splitlines() if ln.startswith("E ")]
                if line:
                    print(f"            {line[0][:150]}")

    if failures:
        print("\nFAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"\nall {len(MUTATIONS)} mutations caught")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())