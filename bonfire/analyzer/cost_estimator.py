#!/usr/bin/env python3
"""Bonfire cost estimation and reporting."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict

from bonfire.bonfire_logger import atomic_write_json, iter_events

COST_LOG_PATH = Path.home() / ".openclaw" / "logs" / "bonfire_costs.json"
PRICING = {
    "claude-sonnet": {"input": 3.0, "output": 15.0},
    "gpt4": {"input": 10.0, "output": 30.0},
    "kimi": {"input": 1.0, "output": 3.0},
}


def _safe_int(value, default: int = 0) -> int:
    try:
        n = int(value)
        return n if n >= 0 else default
    except Exception:
        return default


def _canonical_model(model: str) -> str:
    m = (model or "").lower()
    if "claude" in m:
        return "claude-sonnet"
    if "gpt-4" in m or "gpt4" in m:
        return "gpt4"
    if "kimi" in m or "kimi-k2" in m or "kimi-" in m:
        return "kimi"
    return m or "unknown"


def _hour_key(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%dT%H")
    except Exception:
        return "unknown"


def _day_key(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except Exception:
        return "unknown"


def _compute_event_cost(model: str, prompt_tokens: int, completion_tokens: int) -> tuple[float, bool]:
    canonical = _canonical_model(model)
    rates = PRICING.get(canonical)
    if not rates:
        return 0.0, False
    input_cost = (prompt_tokens / 1_000_000) * float(rates.get("input", 0.0))
    output_cost = (completion_tokens / 1_000_000) * float(rates.get("output", 0.0))
    return input_cost + output_cost, True


def build_cost_report() -> dict:
    by_agent = defaultdict(float)
    by_model = defaultdict(float)
    by_hour = defaultdict(float)
    by_hour_tokens = defaultdict(int)
    by_day = defaultdict(float)
    by_day_tokens = defaultdict(int)
    top_events = []
    known_model_events = 0

    for event in iter_events():
        if event.get("event") in ("session_start", "session_end"):
            continue

        total_tokens = _safe_int(event.get("total_tokens"), -1)
        if total_tokens < 0:
            continue

        ts = str(event.get("timestamp", ""))
        hkey = _hour_key(ts)
        dkey = _day_key(ts)
        model = str(event.get("model", "unknown"))
        prompt_tokens = _safe_int(event.get("prompt_tokens", 0), 0)
        completion_tokens = _safe_int(event.get("completion_tokens", 0), 0)
        if completion_tokens < 0:
            # Approximate output as half total when only total is present.
            completion_tokens = max(0, total_tokens - prompt_tokens)
            if completion_tokens < 0:
                completion_tokens = total_tokens // 2
                prompt_tokens = total_tokens - completion_tokens

        event_cost, known = _compute_event_cost(model, prompt_tokens, completion_tokens)
        if known:
            known_model_events += 1

        by_agent[str(event.get("agent_id", "unknown"))] += event_cost
        by_model[_canonical_model(model)] += event_cost
        by_hour[hkey] += event_cost
        by_day[dkey] += event_cost
        by_hour_tokens[hkey] += total_tokens
        by_day_tokens[dkey] += total_tokens

        top_events.append(
            {
                "timestamp": ts,
                "agent_id": str(event.get("agent_id", "unknown")),
                "session_id": event.get("session_id", "unknown"),
                "model": model,
                "total_tokens": total_tokens,
                "status": event.get("status", "unknown"),
                "cost_usd": event_cost,
            }
        )

    largest = sorted(top_events, key=lambda r: r["cost_usd"], reverse=True)[:10]

    report = {
        "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "totals": {
            "events": len(top_events),
            "events_with_pricing": known_model_events,
            "agent_count": len(by_agent),
        },
        "cost_by_agent": dict(sorted(by_agent.items(), key=lambda kv: kv[1], reverse=True)),
        "cost_by_model": dict(sorted(by_model.items(), key=lambda kv: kv[1], reverse=True)),
        "cost_by_hour": dict(sorted(by_hour.items())),
        "tokens_by_hour": dict(sorted(by_hour_tokens.items())),
        "cost_by_day": dict(sorted(by_day.items())),
        "tokens_by_day": dict(sorted(by_day_tokens.items())),
        "largest_cost_events": largest,
        "pricing": PRICING,
    }
    report["totals"]["total_hour_cost_usd"] = sum(by_hour.values())
    report["totals"]["total_daily_cost_usd"] = sum(by_day.values())
    report["totals"]["distinct_models"] = len(by_model)

    atomic_write_json(COST_LOG_PATH, report)
    return report


def print_cost(hours: int = 24, top_n: int = 5) -> None:
    report = build_cost_report()
    now = datetime.utcnow()
    cutoff_hour = now.timestamp() - (hours * 3600)
    hourly_items = []
    for key, value in report["cost_by_hour"].items():
        if key == "unknown":
            continue
        try:
            ts = datetime.strptime(key, "%Y-%m-%dT%H").timestamp()
        except Exception:
            continue
        if ts >= cutoff_hour:
            hourly_items.append((key, value))

    now_hour = datetime.utcnow().strftime("%Y-%m-%dT%H")
    print(f"Bonfire cost (last {hours}h, ending at {now_hour})")
    period_cost = sum(v for _, v in hourly_items)
    print(f"Total cost (window): ${period_cost:.6f}")

    print("Top agent cost:")
    for agent, amount in list(report["cost_by_agent"].items())[:top_n]:
        print(f"  {agent}: ${amount:.6f}")
    if not report["cost_by_agent"]:
        print("  no data")

    print("Top model cost:")
    for model, amount in list(report["cost_by_model"].items())[:top_n]:
        print(f"  {model}: ${amount:.6f}")
    if not report["cost_by_model"]:
        print("  no data")

    recent_hours = sorted((k for k, _ in hourly_items))
    print("Hourly cost trace:")
    for hour in recent_hours:
        print(f"  {hour}: ${report['cost_by_hour'].get(hour, 0.0):.6f}")
    if not recent_hours:
        print("  no hourly cost")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bonfire cost report")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args()
    print_cost(hours=max(1, int(args.hours)), top_n=max(1, int(args.top)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
