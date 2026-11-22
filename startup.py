"""Backward-compatible launcher for the single MULTIBOT2 runtime entrypoint.

Deployments must run main.py directly. This module intentionally has no
Telegram, database, scanner or scheduler side effects of its own.
"""
from __future__ import annotations


def main() -> int:
    from main import main as runtime_main
    return runtime_main()


if __name__ == "__main__":
    raise SystemExit(main())
