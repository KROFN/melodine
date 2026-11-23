#!/usr/bin/env python3
"""Legacy launcher kept for backward compatibility with Melodine v1.

Prefer the installed entry points instead::

    melodine        # interactive TUI
    mld get "..."   # headless CLI alias
"""

from __future__ import annotations

import sys


def main() -> None:
    try:
        from melodine.cli.main import main as cli_main

        cli_main()
    except KeyboardInterrupt:
        print("\nGoodbye! / Do vstrechi!")
        sys.exit(0)


if __name__ == "__main__":
    main()
