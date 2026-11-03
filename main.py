#!/usr/bin/env python3
"""Timblee Pad launcher."""

from __future__ import annotations

import sys

from timblee_pad import APP_NAME, APP_VERSION


def entry(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else list(argv)
    # Keep the release/version probe usable even on build hosts before PyQt6 is
    # installed; normal launches import the GUI only after this fast path.
    if "--version" in arguments:
        print(f"{APP_NAME} {APP_VERSION}")
        return 0
    from timblee_pad.app import main as gui_main

    return gui_main(arguments)


if __name__ == "__main__":
    raise SystemExit(entry())
