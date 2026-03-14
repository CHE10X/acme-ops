#!/usr/bin/env python3
"""
Bonfire v2 token rollups for operator summary.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
import argparse

from bonfire.bonfire_logger import append_event, ALERT_LOG_PATH, SUMMARY_PATH, atomic_write_json, iter_events
from bonfire.budgets.budget_manager import get_runtime_snapshot
from bonfire.collector.session_tracker import get_active_sessions


def _to_int(value, default: int = 0) -> int:
    try:
        value = int(value)
        return value if value >= 0 else default
    except Exception:
        return default


def _hour_key(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%dT%H")
    except Exception:
        return "unknown"


def build_summary() -> dict:
    agent_totals = defaultdict(int)
    model_totals = defaultdict(int)
    hour_totals = defaultdict(int)
    top_events = []
    active_count = len(get_active_sessions())

    for event in iter_events():
        status = str(event.get("status", "")).lower()
        if event.get("event") in ("session_start", "session_end"):
            continue
        total_tokens = _to_int(event.get("total_tokens"), -1)
        if total_tokens < 0:
            continue
        agent_id = str(event.get("agent_id", "unknown"))
        model = str(event.get("model", "unknown"))
        hour = _hour_key(str(event.get("timestamp", "")))
        agent_totals[agent_id] += total_tokens
        model_totals[model] += total_tokens
        hour_totals[hour] += total_tokens
        top_events.append(
            {
                "timestamp": event.get("timestamp"),
                "agent_id": agent_id,
                "model": model,
                "total_tokens": total_tokens,
                "tool_used": event.get("tool_used"),
                "session_id": event.get("session_id"),
                "status": status,
            }
        )

    total_events = len(top_events)
    total_tokens = sum(evt["total_tokens"] for evt in top_events)

    largest = sorted(top_events, key=lambda row: row["total_tokens"], reverse=True)[:10]
    spikes = []
    if ALERT_LOG_PATH.exists():
        with ALERT_LOG_PATH.open("r", encoding="utf-8") as fh:
            for raw in fh:
                if "SPIKE" in raw:
                    spikes.append(raw.strip())

    summary = {
        "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "totals": {
            "total_events": total_events,
            "total_tokens": total_tokens,
            "average_request_tokens": (total_tokens / total_events) if total_events else 0.0,
            "active_sessions": active_count,
        },
        "tokens_per_agent": dict(sorted(agent_totals.items(), key=lambda kv: kv[1], reverse=True)),
        "tokens_per_model": dict(sorted(model_totals.items(), key=lambda kv: kv[1], reverse=True)),
        "tokens_per_hour": dict(sorted(hour_totals.items())),
        "largest_token_events": largest,
        "recent_spikes": spikes[-10:],
        "governance": get_runtime_snapshot(),
    }
    atomic_write_json(SUMMARY_PATH, summary)
    return summary


def print_status(last_hours: int = 1, top_spikes: int = 5) -> None:
    summary = build_summary()
    cutoff = datetime.utcnow() - timedelta(hours=last_hours)
    cutoff_ts = cutoff.timestamp()

    by_agent = defaultdict(int)
    by_model = defaultdict(int)
    for event in iter_events():
        ts = event.get("timestamp")
        if not ts:
            continue
        try:
            parsed = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except Exception:
            continue
        if parsed.timestamp() < cutoff_ts:
            continue
        if event.get("event") in ("session_start", "session_end"):
            continue
        total = _to_int(event.get("total_tokens"), -1)
        if total < 0:
            continue
        by_agent[str(event.get("agent_id", "unknown"))] += total
        by_model[str(event.get("model", "unknown"))] += total

    print(f"Agent token usage (last {last_hours}h):")
    for agent, total in sorted(by_agent.items(), key=lambda kv: kv[1], reverse=True):
        print(f"  {agent}: {total}")
    if not by_agent:
        print("  no events")

    print("Model token usage:")
    for model, total in sorted(by_model.items(), key=lambda kv: kv[1], reverse=True):
        print(f"  {model}: {total}")
    if not by_model:
        print("  no events")

    print(f"Top token spikes (last):")
    for raw in summary.get("recent_spikes", [])[:top_spikes]:
        print(f"  {raw}")
    if not summary.get("recent_spikes"):
        print("  no spikes recorded")

    print(f"Active sessions: {summary['totals']['active_sessions']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bonfire status + rollup")
    parser.add_argument("--hours", type=int, default=1)
    parser.add_argument("--top-spikes", type=int, default=5)
    args = parser.parse_args()
    print_status(last_hours=args.hours, top_spikes=args.top_spikes)
    append_event(
        {
            "event": "operator_summary",
            "agent_id": "system",
            "session_id": "operator",
            "model": "bonfire",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "tool_used": "token_rollup",
            "latency_ms": 0,
            "status": "success",
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
