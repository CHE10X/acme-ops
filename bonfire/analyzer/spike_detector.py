#!/usr/bin/env python3
"""
Bonfire v2 spike detector.
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime
import argparse
import json

from bonfire.bonfire_logger import TOKEN_LOG_PATH, append_alert


def _safe_int(value, default: int = -1) -> int:
    try:
        n = int(value)
        return n if n >= 0 else default
    except Exception:
        return default


def detect_spikes(
    rolling_window: int = 25,
    session_threshold: int = 20000,
    agent_hourly_threshold: int = 5000,
) -> None:
    if not TOKEN_LOG_PATH.exists():
        return
    window = deque()
    session_totals = defaultdict(int)
    hourly_totals = defaultdict(int)
    session_alerted = set()
    hourly_alerted = set()

    with TOKEN_LOG_PATH.open("r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                ev = json.loads(raw)
            except Exception:
                continue
            total = _safe_int(ev.get("total_tokens"), -1)
            if total < 0:
                continue
            if ev.get("status") in ("session_start", "session_end"):
                continue
            aid = str(ev.get("agent_id", "unknown"))
            sid = str(ev.get("session_id", ""))
            ts = str(ev.get("timestamp", ""))
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                continue
            hour_key = dt.strftime("%Y-%m-%dT%H")

            if len(window) >= rolling_window:
                window.popleft()
            avg = (sum(v for v in window) / len(window)) if window else 0.0
            window.append(total)
            if avg > 0 and total >= 4 * avg and len(window) >= 5:
                append_alert(
                    f"SPIKE single_request model={ev.get('model')} agent={aid} session={sid} total={total} avg={avg:.2f}"
                )

            session_totals[sid] += total
            if sid and sid not in session_alerted and session_totals[sid] >= session_threshold:
                session_alerted.add(sid)
                append_alert(
                    f"SPIKE session_tokens_exceeded session={sid} agent={aid} total={session_totals[sid]} threshold={session_threshold}"
                )

            hourly_key = f"{aid}|{hour_key}"
            hourly_totals[hourly_key] += total
            if hourly_totals[hourly_key] >= agent_hourly_threshold and hourly_key not in hourly_alerted:
                hourly_alerted.add(hourly_key)
                append_alert(
                    f"SPIKE hourly_tokens_exceeded agent={aid} hour={hour_key} total={hourly_totals[hourly_key]} threshold={agent_hourly_threshold}"
                )


def main() -> int:
    parser = argparse.ArgumentParser(description="Bonfire spike detector")
    parser.add_argument("--rolling-window", type=int, default=25)
    parser.add_argument("--session-threshold", type=int, default=20000)
    parser.add_argument("--agent-hourly-threshold", type=int, default=5000)
    args = parser.parse_args()
    detect_spikes(
        rolling_window=args.rolling_window,
        session_threshold=args.session_threshold,
        agent_hourly_threshold=args.agent_hourly_threshold,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
