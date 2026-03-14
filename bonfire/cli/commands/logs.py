"""bonfire logs command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

from bonfire.cli import helpers


def _read_tail(path: Path, count: int) -> List[str]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            lines = [line.rstrip("\n") for line in fh]
    except Exception:
        return []
    if count <= 0:
        return [line for line in lines if line.strip()]
    return [line for line in lines[-count:] if line.strip()]


def _format_token_lines(lines: List[str]) -> List[str]:
    output: List[str] = []
    for line in lines:
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        ts = payload.get("timestamp", "unavailable")
        agent = payload.get("agent_id", "unknown")
        model = payload.get("model", "unknown")
        tokens = payload.get("total_tokens", 0)
        status = payload.get("status", payload.get("event", "unknown"))
        output.append(f"{ts} agent={agent} model={model} tokens={tokens} status={status}")
    return output


def run(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="bonfire logs", add_help=False)
    parser.add_argument("-tail", "--tail", type=int, default=20)
    parser.add_argument("-alerts", "--alerts", action="store_true")
    parser.add_argument("-tokens", "--tokens", action="store_true")
    parser.add_argument("-h", "--help", action="store_true")
    ns, _ = parser.parse_known_args(argv)

    if ns.help:
        print("Usage: bonfire logs [-tail 20] [-alerts] [-tokens]")
        return 0

    show_alerts = ns.alerts or (not ns.alerts and not ns.tokens)
    show_tokens = ns.tokens or (not ns.alerts and not ns.tokens)

    printed = False

    if show_alerts:
        alert_lines = _read_tail(helpers.ALERTS_PATH, ns.tail)
        if alert_lines:
            printed = True
            print("Bonfire Alerts Log")
            for line in alert_lines:
                print(line)

    if show_tokens:
        token_lines = _read_tail(helpers.TOKENS_PATH, ns.tail)
        formatted = _format_token_lines(token_lines)
        if formatted:
            if printed:
                print()
            printed = True
            print("Bonfire Tokens Log")
            for line in formatted:
                print(line)

    if not printed:
        print("No Bonfire logs found.")
    return 0
