#!/usr/bin/env python3
"""Forecasting and economy reports for Bonfire v3."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

from bonfire.bonfire_logger import atomic_write_json, iter_events
from bonfire.predictor.token_predictor import get_agent_profile
from bonfire.risk.agent_risk_score import list_scores

HEALTH_PATH = Path.home() / ".openclaw" / "logs" / "bonfire_health.json"
ECONOMY_PATH = Path.home() / ".openclaw" / "logs" / "bonfire_economics.json"

_ALERT_PATH = Path.home() / ".openclaw" / "logs" / "bonfire_alerts.log"

_PRICING = {
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


def _to_hour(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%dT%H")
    except Exception:
        return "unknown"


def _to_day(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except Exception:
        return "unknown"


def _canonical_model(model: str) -> str:
    m = (model or "").lower().strip()
    if "gpt4" in m or "gpt-4" in m:
        return "gpt4"
    if "claude" in m:
        return "claude-sonnet"
    if "kimi" in m:
        return "kimi"
    return m or "unknown"


def _event_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rates = _PRICING.get(_canonical_model(model), None)
    if not rates:
        return 0.0
    return (prompt_tokens / 1_000_000) * rates["input"] + (completion_tokens / 1_000_000) * rates["output"]


def _recent_alerts_for(agent_id: str | None = None, max_lines: int = 5) -> list[str]:
    if not _ALERT_PATH.exists():
        return []
    rows = []
    try:
        with _ALERT_PATH.open("r", encoding="utf-8") as fh:
            lines = [row.strip() for row in fh if row.strip()]
    except Exception:
        return []
    if agent_id:
        for raw in reversed(lines):
            if f"agent={agent_id}" in raw:
                rows.append(raw)
                if len(rows) >= max_lines:
                    break
    else:
        rows = lines[-max_lines:]
        rows.reverse()
    return list(reversed(rows))


def build_health_report(*, last_hours: int = 1) -> dict:
    cutoff = datetime.utcnow() - timedelta(hours=last_hours)
    cutoff_ts = cutoff.timestamp()
    by_agent_tokens: Dict[str, int] = defaultdict(int)
    by_agent_distribution = defaultdict(lambda: defaultdict(int))
    total = 0

    for event in iter_events():
        if event.get("event") in ("session_start", "session_end"):
            continue
        try:
            ts = float(datetime.fromisoformat(str(event.get("timestamp", "")).replace("Z", "+00:00")).timestamp())
        except Exception:
            continue
        if ts < cutoff_ts:
            continue
        total_tokens = _safe_int(event.get("total_tokens"), -1)
        if total_tokens < 0:
            continue
        aid = str(event.get("agent_id", "unknown"))
        model = str(event.get("model", "unknown"))
        by_agent_tokens[aid] += total_tokens
        by_agent_distribution[aid][ _canonical_model(model) ] += total_tokens
        total += total_tokens

    risk_scores = {row["agent_id"]: row for row in list_scores()}

    rows = []
    for agent, tokens in by_agent_tokens.items():
        profile = get_agent_profile(agent)
        predicted = int((profile.get("avg_total") or 0) * 1.2)
        rows.append(
            {
                "agent_id": agent,
                "risk_score": risk_scores.get(agent, {}).get("risk_score", 0),
                "risk_level": risk_scores.get(agent, {}).get("risk_level", "healthy"),
                "hourly_tokens": tokens,
                "predicted_tokens": predicted,
                "model_distribution": dict(sorted(by_agent_distribution[agent].items(), key=lambda kv: kv[1], reverse=True)),
                "alerts": _recent_alerts_for(agent),
                "efficiency_hint": "unknown",
            }
        )

    report = {
        "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "window_hours": int(last_hours),
        "total_tokens": total,
        "agents": sorted(rows, key=lambda row: row["hourly_tokens"], reverse=True),
    }
    atomic_write_json(HEALTH_PATH, report)
    return report


def build_economics_report(*, day: str | None = None) -> dict:
    target_day = day or datetime.utcnow().strftime("%Y-%m-%d")
    by_agent_tokens = defaultdict(int)
    by_agent_cost = defaultdict(float)
    by_agent_tasks = defaultdict(int)
    by_model_cost = defaultdict(float)
    by_model_tokens = defaultdict(int)
    total_tokens = 0
    total_cost = 0.0
    by_hour = defaultdict(float)
    by_hour_tokens = defaultdict(int)

    for event in iter_events():
        if event.get("event") in ("session_start", "session_end"):
            continue
        total_tokens_event = _safe_int(event.get("total_tokens"), -1)
        if total_tokens_event < 0:
            continue
        key_day = _to_day(str(event.get("timestamp", "")))
        if key_day != target_day:
            continue
        aid = str(event.get("agent_id", "unknown"))
        prompt_tokens = _safe_int(event.get("prompt_tokens"), 0)
        completion_tokens = _safe_int(event.get("completion_tokens"), 0)
        if completion_tokens < 0:
            completion_tokens = max(0, total_tokens_event // 2)
        model = str(event.get("model", "unknown"))
        cost = _event_cost(model, prompt_tokens, completion_tokens)

        by_agent_tokens[aid] += total_tokens_event
        by_agent_cost[aid] += cost
        by_agent_tasks[aid] += 1
        by_model_cost[_canonical_model(model)] += cost
        by_model_tokens[_canonical_model(model)] += total_tokens_event
        by_hour[_to_hour(str(event.get("timestamp", "")))] += cost
        by_hour_tokens[_to_hour(str(event.get("timestamp", "")))] += total_tokens_event
        total_tokens += total_tokens_event
        total_cost += cost

    cost_per_task = {
        agent: (by_agent_cost[agent] / max(1, by_agent_tasks[agent]))
        for agent in by_agent_cost
    }
    efficiency_index = {
        agent: min(1.0, by_agent_cost[agent] / max(1.0, by_agent_tokens[agent])) for agent in by_agent_cost
    }

    model_total = sum(by_model_tokens.values()) or 1
    model_share = {
        model: round((count / model_total) * 100.0, 2) for model, count in by_model_tokens.items()
    }

    report = {
        "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "day": target_day,
        "totals": {
            "total_tokens": int(total_tokens),
            "total_cost_usd": float(total_cost),
            "cost_per_task": {agent: float(v) for agent, v in sorted(cost_per_task.items(), key=lambda kv: kv[1], reverse=True)},
            "token_efficiency_index": {agent: round(float(v), 4) for agent, v in sorted(efficiency_index.items(), key=lambda kv: kv[1], reverse=True)},
            "agent_cost": {agent: float(v) for agent, v in sorted(by_agent_cost.items(), key=lambda kv: kv[1], reverse=True)},
            "agent_tokens": {agent: int(v) for agent, v in sorted(by_agent_tokens.items(), key=lambda kv: kv[1], reverse=True)},
        },
        "model_usage_share": model_share,
        "cost_by_hour": dict(sorted(by_hour.items())),
        "tokens_by_hour": dict(sorted(by_hour_tokens.items())),
    }
    atomic_write_json(ECONOMY_PATH, report)
    return report


def print_forecast() -> None:
    report = build_health_report(last_hours=1)
    print("Bonfire forecast (hourly health snapshot):")
    for row in report.get("agents", [])[:10]:
        print(
            f"  {row['agent_id']}: risk={row['risk_score']} ({row['risk_level']}), "
            f"hourly={row['hourly_tokens']}, predicted={row['predicted_tokens']}"
        )
    if not report.get("agents"):
        print("  no data")
    if report.get("total_tokens", 0):
        print(f"  total_window_tokens={report['total_tokens']}")


def print_efficiency(*, hours: int = 1) -> None:
    economics = build_economics_report()
    print("Bonfire efficiency and economics:")
    print(f"  total cost: ${economics['totals']['total_cost_usd']:.6f}")
    print("  top token efficiency by agent:")
    for agent, value in list(economics["totals"]["token_efficiency_index"].items())[:10]:
        print(f"    {agent}: {value:.4f}")
    if not economics["totals"]["token_efficiency_index"]:
        print("    no data")


def print_optimization_guidance() -> None:
    economy = build_economics_report()
    if not economy["totals"]["agent_tokens"]:
        print("No optimization guidance: insufficient data.")
        return
    print("Optimize recommendations:")
    for agent, cost in list(economy["totals"]["agent_cost"].items())[:5]:
        print(f"  {agent}: highest cost driver, ${cost:.4f}")
