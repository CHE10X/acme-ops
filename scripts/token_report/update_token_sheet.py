#!/usr/bin/env python3
"""
Daily token usage aggregator → Google Sheets.
Reads all agent session files, aggregates by date, appends new rows to sheet.

Sheet: https://docs.google.com/spreadsheets/d/1MnQLIIgnDxn18BxujxrRX3t9BN82mxqbdRiPJeAIKgI
Tab: Daily Summary
"""

import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SHEET_ID = "1MnQLIIgnDxn18BxujxrRX3t9BN82mxqbdRiPJeAIKgI"
SHEET_TAB = "Daily Summary"
GOG_ACCOUNT = "hendrik.homarus@gmail.com"
AGENTS_DIR = Path(os.path.expanduser("~/.openclaw/agents"))

AGENTS = ["hendrik", "heike", "soren", "gerrit", "gwen", "quartermaster"]


def parse_sessions(agent: str) -> dict:
    """Parse all session files for an agent, aggregate by date."""
    sessions_dir = AGENTS_DIR / agent / "sessions"
    if not sessions_dir.exists():
        return {}

    daily = defaultdict(lambda: {
        "sessions": set(),
        "input": 0,
        "output": 0,
        "cache_read": 0,
        "cache_write": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
    })

    for session_file in sessions_dir.glob("*.jsonl"):
        session_id = session_file.stem
        for line in session_file.read_text().strip().split("\n"):
            if not line:
                continue
            try:
                d = json.loads(line)
                msg = d.get("message", {})
                if not isinstance(msg, dict):
                    continue
                usage = msg.get("usage")
                if not usage or not isinstance(usage, dict):
                    continue
                if not usage.get("totalTokens"):
                    continue

                ts = d.get("timestamp", "")
                if ts:
                    try:
                        # Handle both ISO string and millisecond timestamp
                        if isinstance(ts, str):
                            date = ts[:10]  # "2026-03-17T..."[:10] = "2026-03-17"
                        else:
                            date = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                    except Exception:
                        continue
                else:
                    continue

                daily[date]["sessions"].add(session_id)
                daily[date]["input"] += usage.get("input", 0)
                daily[date]["output"] += usage.get("output", 0)
                daily[date]["cache_read"] += usage.get("cacheRead", 0)
                daily[date]["cache_write"] += usage.get("cacheWrite", 0)
                daily[date]["total_tokens"] += usage.get("totalTokens", 0)
                cost = usage.get("cost", {})
                if isinstance(cost, dict):
                    daily[date]["cost_usd"] += cost.get("total", 0.0)

            except Exception:
                continue

    return daily


def get_existing_dates() -> set:
    """Get dates already in the sheet."""
    result = subprocess.run(
        ["gog", "sheets", "get", SHEET_ID, f"{SHEET_TAB}!A2:A1000",
         "--json", "--account", GOG_ACCOUNT],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return set()
    try:
        data = json.loads(result.stdout)
        values = data.get("values", [])
        return {row[0] for row in values if row}
    except Exception:
        return set()


def append_rows(rows: list):
    """Append new rows to the sheet."""
    if not rows:
        return
    values_json = json.dumps(rows)
    result = subprocess.run(
        ["gog", "sheets", "append", SHEET_ID, f"{SHEET_TAB}!A:I",
         "--values-json", values_json,
         "--insert", "INSERT_ROWS",
         "--account", GOG_ACCOUNT],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Error appending rows: {result.stderr}", file=sys.stderr)
    else:
        print(f"Appended {len(rows)} rows to sheet.")


def main():
    print("Aggregating token usage by date...")

    # Aggregate across all agents
    all_daily = defaultdict(lambda: {
        "agents": set(),
        "sessions": set(),
        "input": 0,
        "output": 0,
        "cache_read": 0,
        "cache_write": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
    })

    for agent in AGENTS:
        agent_daily = parse_sessions(agent)
        for date, data in agent_daily.items():
            if data["total_tokens"] > 0:
                all_daily[date]["agents"].add(agent)
                all_daily[date]["sessions"].update(data["sessions"])
                all_daily[date]["input"] += data["input"]
                all_daily[date]["output"] += data["output"]
                all_daily[date]["cache_read"] += data["cache_read"]
                all_daily[date]["cache_write"] += data["cache_write"]
                all_daily[date]["total_tokens"] += data["total_tokens"]
                all_daily[date]["cost_usd"] += data["cost_usd"]

    if not all_daily:
        print("No usage data found.")
        return

    # Get existing dates
    existing_dates = get_existing_dates()
    print(f"Found {len(existing_dates)} existing dates in sheet.")

    # Build new rows
    new_rows = []
    for date in sorted(all_daily.keys()):
        if date in existing_dates:
            continue
        d = all_daily[date]
        new_rows.append([
            date,
            len(d["agents"]),
            len(d["sessions"]),
            d["input"],
            d["output"],
            d["cache_read"],
            d["cache_write"],
            d["total_tokens"],
            round(d["cost_usd"], 6),
        ])

    if not new_rows:
        print("No new dates to add.")
        return

    print(f"Adding {len(new_rows)} new rows...")
    append_rows(new_rows)
    print("Done.")


if __name__ == "__main__":
    main()
