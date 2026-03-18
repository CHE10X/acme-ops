#!/usr/bin/env python3
"""
QM Audit — read interface for enforcement_log.jsonl
Usage: python3 audit.py [task-id|agent|project]
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

LOG_PATH = Path(__file__).parent.parent / "logs" / "enforcement_log.jsonl"


def verify_line(line: str, stored_hash: str) -> bool:
    """Verify SHA256 of line content matches stored hash."""
    content = line.rsplit('", "sha256":', 1)[0] + '"}'
    return hashlib.sha256(content.encode()).hexdigest() == stored_hash


def read_log(filter_term: str | None = None) -> list[dict]:
    if not LOG_PATH.exists():
        return []
    entries = []
    with LOG_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if filter_term:
                    values = " ".join(str(v) for v in entry.values()).lower()
                    if filter_term.lower() not in values:
                        continue
                entries.append(entry)
            except json.JSONDecodeError:
                continue
    return entries


def append_log(action: str, **kwargs) -> None:
    """Append an enforcement action to the log with SHA256."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "action": action, **kwargs}
    content = json.dumps(entry)
    entry["sha256"] = hashlib.sha256(content.encode()).hexdigest()
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def main() -> None:
    filter_term = sys.argv[1] if len(sys.argv) > 1 else None
    entries = read_log(filter_term)
    if not entries:
        print("No enforcement log entries found." + (f" (filter: {filter_term})" if filter_term else ""))
        return
    for e in entries:
        sha = e.pop("sha256", "?")
        print(json.dumps(e) + f"  [sha256: {sha[:12]}...]")


if __name__ == "__main__":
    main()
