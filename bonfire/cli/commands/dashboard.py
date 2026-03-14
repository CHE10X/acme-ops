"""bonfire dashboard command."""

from __future__ import annotations

import argparse
from typing import List

from bonfire.cli import helpers


def run(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="bonfire dashboard", add_help=False)
    parser.add_argument("-host", "--host", default="127.0.0.1")
    parser.add_argument("-port", "--port", type=int, default=8765)
    parser.add_argument("-h", "--help", action="store_true")
    ns, _ = parser.parse_known_args(argv)

    if ns.help:
        print("Usage: bonfire dashboard [-host 127.0.0.1] [-port 8765]")
        return 0

    ok, result = helpers.launch_dashboard(str(ns.host), int(ns.port))
    if ok:
        print("Bonfire Dashboard started")
        print(result)
        return 0

    print(result)
    return 1
