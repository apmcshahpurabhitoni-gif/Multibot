"""Guard against tests that silently depend on the wall clock.

``tests/test_api_contract.py`` called ``dashboard_signal()`` with a hardcoded
event timestamp and no ``now=``. Freshness is exactly one hour, so the event
aged out of the window the moment real time passed the stamp, and
``test_actionable_requires_levels_and_freshness`` began failing -- first on CI,
then locally -- with no code change anywhere. It had been passing only because
the hardcoded timestamp was still in the *future*.

That is the worst class of test failure: it is not a bug report, it is a
calendar event. Nothing in the diff explains it.

The rule this enforces: **any function whose ``now`` defaults to the wall clock
must be called in tests with an explicit ``now=``.** Parsed with ``ast`` rather
than grep so that a function name inside a string or a comment is not mistaken
for a call site.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"

# (function, module that must define it). These all default `now` to real time.
CLOCK_FUNCTIONS = {
    "dashboard_signal": "signal_lifecycle",
    "signal_status": "signal_gate",
    "can_send": "signal_gate",
}


def _calls(path: Path):
    """Yield (lineno, func_name, node) for every call in the file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            yield node.lineno, func.id, node
        elif isinstance(func, ast.Attribute):
            yield node.lineno, func.attr, node


def _passes_now(node: ast.Call) -> bool:
    return any(
        kw.arg == "now"
        or (kw.arg is None and isinstance(kw.value, ast.Name) and kw.value.id == "now")
        for kw in node.keywords
    ) or any(isinstance(a, ast.Name) and a.id == "now" for a in node.args)


@pytest.mark.parametrize("path", sorted(TESTS.glob("test_*.py")), ids=lambda p: p.name)
def test_no_test_calls_a_wall_clock_function_without_pinning_now(path: Path):
    offenders = [
        f"{path.name}:{lineno} {name}() has no now="
        for lineno, name, node in _calls(path)
        if name in CLOCK_FUNCTIONS and not _passes_now(node)
    ]
    assert not offenders, (
        "these calls fall back to the real clock and will start failing on a "
        "date rather than on a change:\n  " + "\n  ".join(offenders)
    )


def test_the_guarded_functions_really_do_default_to_the_wall_clock():
    """If a function ever gains a required now=, this guard's premise changes."""
    import inspect

    import signal_gate
    import signal_lifecycle

    # can_send is a SignalGate method, not a module-level function.
    resolved = {
        "dashboard_signal": signal_lifecycle.dashboard_signal,
        "signal_status": signal_gate.signal_status,
        "can_send": signal_gate.SignalGate.can_send,
    }
    for name in CLOCK_FUNCTIONS:
        parameter = inspect.signature(resolved[name]).parameters.get("now")
        assert parameter is not None, f"{name}() no longer takes now="
        assert parameter.default is None, (
            f"{name}() now defaults to {parameter.default!r}, not the wall clock; "
            "update CLOCK_FUNCTIONS in this guard"
        )


def test_the_reference_clock_is_inside_the_freshness_window():
    """A now= far from the event would make the guard above pass but the test lie."""
    import importlib.util

    import pandas as pd
    from config import SIGNAL_FRESHNESS_HOURS

    # Loaded by path rather than by name so this does not depend on pytest's
    # sys.path handling for a tests/ directory with no __init__.py.
    path = TESTS / "test_api_contract.py"
    spec = importlib.util.spec_from_file_location("_contract_under_test", path)
    contract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract)

    event = pd.Timestamp(contract._EVENT_TS)
    age_hours = (contract._NOW - event).total_seconds() / 3600
    assert 0 < age_hours < SIGNAL_FRESHNESS_HOURS, (
        f"test_api_contract's reference clock is {age_hours:.2f}h from its event, "
        f"outside the {SIGNAL_FRESHNESS_HOURS}h freshness window; the assertions "
        "would pass or fail for the wrong reason"
    )
