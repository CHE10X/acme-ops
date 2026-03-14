#!/usr/bin/env python3
"""Transform raw Bonfire files into dashboard payloads."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Sequence, Tuple

from . import data_loader
from .status_colors import normalize_state


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _risk_level(score: Any) -> str:
    try:
        value = float(score)
    except Exception:
        return "unavailable"
    if value >= 80:
        return "runaway"
    if value >= 60:
        return "high"
    if value >= 30:
        return "caution"
    if value >= 0:
        return "healthy"
    return "unavailable"


def _normalize_state(value: Any) -> str:
    return normalize_state(str(value or ""))


def _sum_tokens(event: dict) -> int:
    total = _to_int(event.get("total_tokens", 0))
    if total:
        return total
    return _to_int(event.get("prompt_tokens", 0)) + _to_int(event.get("completion_tokens", 0))


def _window_events(events: Sequence[dict], now: datetime, window_hours: float) -> List[dict]:
    cutoff = now - timedelta(hours=window_hours)
    return [event for event in events if (event.get("parsed_ts") is None or event["parsed_ts"] >= cutoff)]


def _status_messages(token_error: str | None, health_error: str | None, economy_error: str | None, alert_error: str | None) -> List[str]:
    messages = []
    if token_error == "missing":
        messages.append("no telemetry available")
    if alert_error == "missing":
        messages.append("source file unavailable")
    if health_error == "missing":
        messages.append("source file unavailable")
    if economy_error == "missing":
        messages.append("source file unavailable")
    if not messages:
        return messages
    seen = set()
    deduped: List[str] = []
    for message in messages:
        if message in seen:
            continue
        seen.add(message)
        deduped.append(message)
    return deduped


def _health_agents_to_map(health: dict) -> Dict[str, dict]:
    risk_source = health.get("agents", {})
    rows: Dict[str, dict] = {}
    if isinstance(risk_source, list):
        for row in risk_source:
            if isinstance(row, dict):
                rows[str(row.get("agent_id", "unknown"))] = row
    elif isinstance(risk_source, dict):
        for agent, row in risk_source.items():
            if isinstance(row, dict):
                rows[str(agent)] = row
    return rows


def _extract_field(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text)
    return match.group(1) if match else None


def _score_to_state(score: Any) -> str:
    return _normalize_state(_risk_level(score))


def _bucket_5m_key(ts: datetime) -> str:
    minute_bucket = ts.minute - (ts.minute % 5)
    return ts.replace(minute=minute_bucket, second=0, microsecond=0).isoformat().replace("+00:00", "Z")


def _intensity_band(value: int) -> str:
    if value <= 0:
        return "none"
    if value <= 20:
        return "low"
    if value <= 200:
        return "medium"
    if value <= 800:
        return "high"
    return "extreme"


def _band_from_loop_score(score: float) -> str:
    if score >= 7:
        return "critical"
    if score >= 5:
        return "high"
    if score >= 3:
        return "moderate"
    return "low"


def _severity_to_order(severity: str) -> int:
    return {"critical": 3, "high": 2, "moderate": 1, "low": 0}.get(severity, -1)


def _safe_ts_key(ts: Any) -> str:
    if isinstance(ts, datetime):
        return ts.isoformat().replace("+00:00", "Z")
    return "unavailable"


def summarize_overview() -> Dict[str, Any]:
    now = data_loader._now_utc()
    events_24h, token_error = data_loader.load_token_events(now=now, lookback_hours=24.0)
    events_1h, _ = data_loader.load_token_events(now=now, lookback_hours=1.0)
    health, health_error = data_loader.load_health_snapshot()
    economics, economy_error = data_loader.load_economics_snapshot()
    alerts, alert_error = data_loader.load_alert_events(limit=250)

    last_1h = sum(_sum_tokens(event) for event in events_1h)
    last_24h = sum(_sum_tokens(event) for event in events_24h)
    active_sessions = _estimate_active_sessions(events_24h)
    latest_alert = alerts[-1] if alerts else None

    health_agents = health.get("agents", [])
    if isinstance(health_agents, dict):
        health_agents = list(health_agents.values())
    top_risk_agent = None
    if isinstance(health_agents, list) and health_agents:
        ranked = sorted(health_agents, key=lambda item: _to_float(item.get("risk_score", 0)), reverse=True)
        top = ranked[0]
        top_risk_agent = {
            "agent_id": top.get("agent_id"),
            "risk_score": top.get("risk_score", 0),
            "risk_level": _normalize_state(top.get("risk_level", _risk_level(top.get("risk_score")))),
        }

    cost_today = float(economics.get("totals", {}).get("total_cost_usd", 0.0))
    if cost_today == 0.0 and "total_cost" in economics:
        cost_today = _to_float(economics.get("total_cost"))

    return {
        "metrics": {
            "total_tokens_last_1h": last_1h,
            "total_tokens_last_24h": last_24h,
            "active_sessions": active_sessions,
            "cost_today": round(cost_today, 6),
            "top_risk_agent": top_risk_agent,
            "latest_alert": {
                "timestamp": latest_alert.get("timestamp") if latest_alert else None,
                "message": latest_alert.get("message") if latest_alert else None,
                "severity": latest_alert.get("severity") if latest_alert else None,
                "agent": latest_alert.get("agent") if latest_alert else None,
            }
            if latest_alert
            else None,
            "last_refresh": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        },
        "status_messages": _status_messages(token_error, health_error, economy_error, alert_error),
        "sources": data_loader.load_source_status(),
    }


def summarize_agents() -> Dict[str, Any]:
    now = data_loader._now_utc()
    events, token_error = data_loader.load_token_events(now=now, lookback_hours=24.0)
    health, health_error = data_loader.load_health_snapshot()
    alerts, alert_error = data_loader.load_alert_events(limit=250)

    by_agent_tokens: Dict[str, int] = defaultdict(int)
    by_model: Dict[str, Counter[str]] = defaultdict(Counter)
    by_agent_comp: Dict[str, int] = defaultdict(int)

    for event in events:
        agent = str(event.get("agent_id", "unknown"))
        model = str(event.get("model", "unknown"))
        total_tokens = _sum_tokens(event)
        completion = _to_int(event.get("completion_tokens", 0))
        by_agent_tokens[agent] += total_tokens
        by_model[agent][model] += total_tokens
        by_agent_comp[agent] += completion

    recent_1h = _window_events(events, now, 1.0)
    hourly_tokens: Dict[str, int] = defaultdict(int)
    for event in recent_1h:
        hourly_tokens[str(event.get("agent_id", "unknown"))] += _sum_tokens(event)

    predicted_map: Dict[str, float] = {}
    risk_map: Dict[str, float] = {}
    alerts_by_agent: Dict[str, int] = defaultdict(int)
    for agent, row in _health_agents_to_map(health).items():
        risk_map[agent] = _to_float(row.get("risk_score", 0))
        if "predicted_tokens" in row:
            predicted_map[agent] = _to_float(row.get("predicted_tokens", 0))

    for alert in alerts:
        if alert.get("agent"):
            alerts_by_agent[alert["agent"]] += 1

    rows: List[dict] = []
    agent_ids = set(by_agent_tokens) | set(risk_map) | set(predicted_map) | set(hourly_tokens)
    for agent in sorted(agent_ids):
        total = by_agent_tokens.get(agent, 0)
        comp = by_agent_comp.get(agent, 0)
        dominant_model = max(by_model[agent], key=lambda item: by_model[agent][item]) if by_model[agent] else "unknown"
        risk_score = risk_map.get(agent, 0)
        rows.append(
            {
                "agent_id": agent,
                "hourly_tokens": hourly_tokens.get(agent, 0),
                "predicted_tokens": predicted_map.get(agent, 0),
                "risk_score": risk_score,
                "risk_level": _score_to_state(risk_score),
                "efficiency": round(comp / total, 3) if total > 0 else 0,
                "dominant_model": dominant_model,
                "alerts_count": alerts_by_agent.get(agent, 0),
            }
        )

    return {
        "agents": rows,
        "status_messages": _status_messages(token_error, health_error, None, alert_error),
        "sources": data_loader.load_source_status(),
    }


def summarize_economics() -> Dict[str, Any]:
    now = data_loader._now_utc()
    events, token_error = data_loader.load_token_events(now=now, lookback_hours=24.0)
    economy, economy_error = data_loader.load_economics_snapshot()

    totals = economy.get("totals", {}) if isinstance(economy, dict) else {}
    model_share = economy.get("model_usage_share", {}) if isinstance(economy, dict) else {}
    cost_by_hour = economy.get("cost_by_hour", {}) if isinstance(economy, dict) else {}

    by_agent_tokens: Dict[str, int] = defaultdict(int)
    by_model_tokens: Dict[str, int] = defaultdict(int)
    for event in events:
        agent = str(event.get("agent_id", "unknown"))
        model = str(event.get("model", "unknown"))
        tokens = _sum_tokens(event)
        by_agent_tokens[agent] += tokens
        by_model_tokens[model] += tokens

    agent_cost_map = totals.get("agent_cost", {})
    cost_per_task_map = totals.get("cost_per_task", {})
    model_cost_map = totals.get("model_cost", {})
    efficiency_index_map = totals.get("token_efficiency_index", {})
    if not isinstance(agent_cost_map, dict):
        agent_cost_map = {}
    if not isinstance(cost_per_task_map, dict):
        cost_per_task_map = {}
    if not isinstance(model_cost_map, dict):
        model_cost_map = {}
    if not isinstance(efficiency_index_map, dict):
        efficiency_index_map = {}

    model_dist = [
        {"model": name, "share": value}
        for name, value in sorted(model_share.items(), key=lambda item: item[0])
    ] if isinstance(model_share, dict) else []

    rows = []
    agent_ids = set(by_agent_tokens) | set(agent_cost_map)
    for agent in sorted(agent_ids):
        rows.append(
            {
                "agent_id": agent,
                "token_total": by_agent_tokens.get(agent, 0),
                "cost_total": _to_float(agent_cost_map.get(agent, 0)),
                "cost_per_task": _to_float(cost_per_task_map.get(agent, 0)),
                "efficiency_index": _to_float(efficiency_index_map.get(agent, 0)),
            }
        )

    model_rows = [
        {
            "model": model,
            "token_total": by_model_tokens.get(model, 0),
            "cost_total": _to_float(model_cost_map.get(model, 0)),
        }
        for model in sorted(set(by_model_tokens) | set(model_cost_map))
    ]

    if economy_error:
        status_messages = _status_messages(token_error, None, economy_error, None)
    else:
        status_messages = _status_messages(token_error, None, None, None)

    if not economy:
        model_dist = []
        model_rows = [
            {"model": model, "token_total": token_total, "cost_total": 0.0}
            for model, token_total in sorted(by_model_tokens.items())
        ]

    return {
        "agent_rows": rows,
        "model_rows": model_rows,
        "model_distribution": model_dist,
        "cost_by_hour": [
            {"hour": hour, "cost": _to_float(cost)}
            for hour, cost in sorted(cost_by_hour.items())
        ] if isinstance(cost_by_hour, dict) else [],
        "totals": {
            "total_tokens": _to_float(totals.get("total_tokens", sum(by_agent_tokens.values()))),
            "total_cost_usd": _to_float(totals.get("total_cost_usd", 0.0)),
            "token_efficiency_index": _to_float(
                (sum(efficiency_index_map.values()) / len(efficiency_index_map)) if efficiency_index_map else 0.0
            ),
            "cost_by_hour_available": bool(cost_by_hour),
            "generated_at": economy.get("generated_at") if isinstance(economy, dict) else None,
        },
        "status_messages": status_messages,
        "sources": data_loader.load_source_status(),
        "generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def summarize_alerts() -> Dict[str, Any]:
    alerts, alert_error = data_loader.load_alert_events(limit=200)
    health, health_error = data_loader.load_health_snapshot()

    risky_agents = set()
    for row in _health_agents_to_map(health).values():
        if _to_float(row.get("risk_score", 0)) >= 60:
            risky_agents.add(str(row.get("agent_id", "unknown")))

    sorted_alerts = sorted(alerts, key=lambda item: item.get("timestamp", ""), reverse=True)
    runaway_alerts = [a for a in sorted_alerts if a.get("severity") == "runaway"]
    mitigation_alerts = [a for a in sorted_alerts if a.get("intervention")]
    token_spikes = [a for a in sorted_alerts if a.get("token_spike")]
    derived_governance = [
        a
        for a in sorted_alerts
        if any(token in (a.get("message") or "").lower() for token in ("governor", "model_guard", "tool", "budget", "runaway"))
    ]

    return {
        "alerts": sorted_alerts[:75],
        "runaway_interventions": runaway_alerts[:75],
        "mitigations": mitigation_alerts[:75],
        "top_token_spikes": token_spikes[:75],
        "runaway_agents": sorted(risky_agents),
        "governance_actions": derived_governance[:75],
        "status_messages": _status_messages(None, health_error, None, alert_error),
        "sources": data_loader.load_source_status(),
    }


def summarize_runaway_agents() -> Dict[str, Any]:
    now = data_loader._now_utc()
    events, token_error = data_loader.load_token_events(now=now, lookback_hours=1.0)
    alerts, alert_error = data_loader.load_alert_events(limit=0, now=now, lookback_hours=1.0)
    health, health_error = data_loader.load_health_snapshot()

    health_map = _health_agents_to_map(health)
    risk_map = {agent: _to_float(row.get("risk_score", 0)) for agent, row in health_map.items()}
    recent_tokens: Dict[str, int] = defaultdict(int)
    for event in events:
        recent_tokens[str(event.get("agent_id", "unknown"))] += _sum_tokens(event)

    alerts_last_hour: Dict[str, int] = defaultdict(int)
    latest_alert_by_agent: Dict[str, tuple[datetime | None, str]] = {}
    for alert in alerts:
        agent = alert.get("agent")
        if not agent:
            continue
        msg = str(alert.get("message", "")).lower()
        is_runaway_msg = any(token in msg for token in ("runaway", "terminate", "throttle", "cooldown"))
        if is_runaway_msg or alert.get("severity") == "runaway":
            alerts_last_hour[agent] += 1

        parsed_ts = alert.get("parsed_ts")
        previous = latest_alert_by_agent.get(agent)
        if previous is None or ((parsed_ts or now) > (previous[0] or now)):
            latest_alert_by_agent[agent] = (parsed_ts, str(alert.get("message", "")))

    candidate_agents = set(recent_tokens) | set(risk_map) | set(alerts_last_hour)
    rows: List[dict] = []
    for agent in sorted(candidate_agents):
        risk_score = risk_map.get(agent, 0)
        alert_count = alerts_last_hour.get(agent, 0)
        is_runaway = risk_score >= 80 or alert_count > 0
        if not is_runaway:
            continue
        rows.append(
            {
                "agent_id": agent,
                "risk_score": risk_score,
                "risk_level": _score_to_state(risk_score),
                "recent_tokens": recent_tokens.get(agent, 0),
                "alerts_last_hour": alert_count,
                "latest_alert": latest_alert_by_agent.get(agent, (None, ""))[1],
            }
        )

    return {
        "runaway_agents": rows,
        "status_messages": _status_messages(token_error, health_error, None, alert_error),
        "sources": data_loader.load_source_status(),
    }


def summarize_burn_rate() -> Dict[str, Any]:
    now = data_loader._now_utc()
    events, token_error = data_loader.load_token_events(now=now, lookback_hours=1.0)
    if token_error == "missing":
        return {
            "available": False,
            "message": "source file unavailable",
            "points": [],
            "status_messages": _status_messages(token_error, None, None, None),
            "sources": data_loader.load_source_status(),
        }

    bucket_last = now.replace(second=0, microsecond=0)
    buckets: Dict[str, int] = {}
    for minute_offset in range(59, -1, -1):
        key = (bucket_last - timedelta(minutes=minute_offset)).isoformat().replace("+00:00", "Z")
        buckets[key] = 0

    for event in events:
        ts = event.get("parsed_ts")
        if ts is None:
            continue
        key = ts.replace(second=0, microsecond=0).isoformat().replace("+00:00", "Z")
        if key in buckets:
            buckets[key] += _sum_tokens(event)

    points = [{"timestamp": key, "tokens": buckets[key]} for key in sorted(buckets)]
    return {
        "available": True,
        "message": "ok" if points else "insufficient recent data",
        "points": points,
        "status_messages": _status_messages(token_error, None, None, None),
        "sources": data_loader.load_source_status(),
    }


def summarize_model_downgrades() -> Dict[str, Any]:
    alerts, alert_error = data_loader.load_alert_events(limit=0)
    events: List[dict] = []

    for alert in alerts:
        raw_message = str(alert.get("message", ""))
        lower_message = raw_message.lower()
        if not any(token in lower_message for token in ("model_mitigated", "downgrade", "model_changed")):
            continue

        events.append(
            {
                "timestamp": alert.get("timestamp"),
                "parsed_ts": alert.get("parsed_ts"),
                "agent": alert.get("agent") or _extract_field(raw_message, r"agent=([^\s]+)") or "unknown",
                "original_model": _extract_field(raw_message, r"original=([^\s]+)") or "unknown",
                "new_model": (
                    _extract_field(raw_message, r"updated=([^\s]+)")
                    or _extract_field(raw_message, r"model=([^\s]+)")
                    or "unknown"
                ),
                "reason": _extract_field(lower_message, r"(model_mitigated|model_changed|downgrad\w*)") or "model change",
            }
        )

    ordered = sorted(events, key=lambda item: item.get("parsed_ts") or data_loader._now_utc(), reverse=True)
    status_messages = _status_messages(None, None, None, alert_error)
    return {
        "events": [
            {
                "timestamp": item.get("timestamp"),
                "agent": item.get("agent"),
                "original_model": item.get("original_model"),
                "new_model": item.get("new_model"),
                "reason": item.get("reason"),
            }
            for item in ordered
        ],
        "available": False if alert_error == "missing" else True,
        "message": "source file unavailable" if alert_error == "missing" else ("ok" if ordered else "insufficient recent data"),
        "status_messages": status_messages,
        "sources": data_loader.load_source_status(),
    }


def summarize_agent_heatmap() -> Dict[str, Any]:
    now = data_loader._now_utc()
    events, token_error = data_loader.load_token_events(now=now, lookback_hours=1.0)
    if token_error == "missing":
        return {
            "available": False,
            "message": "source file unavailable",
            "heatmap": [],
            "status_messages": _status_messages(token_error, None, None, None),
            "sources": data_loader.load_source_status(),
        }

    bucket_end = now.replace(second=0, microsecond=0)
    bucket_starts = [
        (bucket_end - timedelta(minutes=55 - 5 * index)).replace(second=0, microsecond=0)
        for index in range(12)
    ]

    bucket_labels = [_bucket_5m_key(start) for start in bucket_starts]
    agent_buckets: Dict[str, Dict[str, int]] = defaultdict(lambda: {label: 0 for label in bucket_labels})
    for event in events:
        ts = event.get("parsed_ts")
        if not isinstance(ts, datetime):
            continue
        key = _bucket_5m_key(ts)
        if key not in set(bucket_labels):
            continue
        agent = str(event.get("agent_id", "unknown"))
        agent_buckets[agent][key] += _sum_tokens(event)

    rows: List[dict] = []
    max_bucket = 0
    for buckets in agent_buckets.values():
        for value in buckets.values():
            if value > max_bucket:
                max_bucket = value

    for agent in sorted(agent_buckets):
        buckets_payload = []
        for label in bucket_labels:
            value = agent_buckets[agent].get(label, 0)
            buckets_payload.append(
                {
                    "bucket_start": label,
                    "total_tokens": value,
                    "intensity": _intensity_band(value),
                }
            )
        rows.append({"agent_id": agent, "buckets": buckets_payload})

    if not rows:
        return {
            "available": True,
            "message": "insufficient recent data",
            "bucket_starts": bucket_labels,
            "heatmap": [],
            "max_bucket_tokens": 0,
            "status_messages": _status_messages(token_error, None, None, None),
            "sources": data_loader.load_source_status(),
        }

    rows = sorted(rows, key=lambda row: sum((bucket["total_tokens"] for bucket in row["buckets"])), reverse=True)
    for row in rows:
        for bucket in row["buckets"]:
            bucket["intensity"] = _intensity_band(bucket["total_tokens"])
    return {
        "available": True,
        "message": "ok" if rows else "insufficient recent data",
        "bucket_starts": bucket_labels,
        "heatmap": rows,
        "max_bucket_tokens": max_bucket,
        "status_messages": _status_messages(token_error, None, None, None),
        "sources": data_loader.load_source_status(),
    }


def summarize_model_efficiency() -> Dict[str, Any]:
    now = data_loader._now_utc()
    events, token_error = data_loader.load_token_events(now=now, lookback_hours=24.0)
    economics, economy_error = data_loader.load_economics_snapshot()
    if token_error == "missing":
        return {
            "available": False,
            "message": "source file unavailable",
            "models": [],
            "status_messages": _status_messages(token_error, None, None, None),
            "sources": data_loader.load_source_status(),
        }

    totals = economics.get("totals", {}) if isinstance(economics, dict) else {}
    model_cost_map = totals.get("model_cost", {})
    if not isinstance(model_cost_map, dict):
        model_cost_map = {}
    pricing = None
    if isinstance(economics.get("pricing"), dict):
        pricing = economics["pricing"]
    elif isinstance(economics.get("model_pricing"), dict):
        pricing = economics["model_pricing"]
    model_costs = defaultdict(float)
    model_prompt = defaultdict(int)
    model_completion = defaultdict(int)
    model_events = defaultdict(int)
    model_latency = defaultdict(list)

    for event in events:
        model = str(event.get("model", "unknown"))
        model_events[model] += 1
        p = _to_int(event.get("prompt_tokens", 0))
        c = _to_int(event.get("completion_tokens", 0))
        if p == 0 and c == 0:
            total_tokens = _sum_tokens(event)
            # split unknowns equally when direct fields are absent
            p = int(total_tokens * 0.75)
            c = max(0, total_tokens - p)
        model_prompt[model] += p
        model_completion[model] += c
        if p + c <= 0:
            continue
        if pricing and isinstance(pricing.get(model), dict):
            input_rate = _to_float(pricing.get(model, {}).get("input"), 0.0)
            output_rate = _to_float(pricing.get(model, {}).get("output"), 0.0)
            model_costs[model] += (p / 1_000_000) * input_rate + (c / 1_000_000) * output_rate
        elif model in model_cost_map:
            model_costs[model] = _to_float(model_cost_map.get(model, 0.0))
        latency = _to_float(event.get("latency_ms", 0), 0.0)
        if latency > 0:
            model_latency[model].append(latency)

    rows = []
    for model in sorted(set(model_prompt) | set(model_completion) | set(model_events)):
        total_prompt = model_prompt.get(model, 0)
        total_completion = model_completion.get(model, 0)
        total_tokens = total_prompt + total_completion
        avg_tokens = (total_tokens / model_events.get(model, 1)) if model_events.get(model) else 0.0
        avg_latency = sum(model_latency[model]) / len(model_latency[model]) if model_latency[model] else None
        row_cost = None
        if model in model_cost_map:
            row_cost = _to_float(model_cost_map.get(model, 0))
        elif model_costs[model] > 0:
            row_cost = model_costs[model]
        rows.append(
            {
                "model": model,
                "events_count": model_events.get(model, 0),
                "total_prompt_tokens": total_prompt,
                "total_completion_tokens": total_completion,
                "total_tokens": total_tokens,
                "avg_tokens_per_event": round(avg_tokens, 2),
                "efficiency_ratio": round((total_completion / total_tokens), 3) if total_tokens else 0,
                "cost_total": row_cost,
                "avg_latency_ms": round(avg_latency, 2) if avg_latency is not None else None,
            }
        )

    rows.sort(key=lambda row: row["total_tokens"], reverse=True)
    return {
        "available": True,
        "message": "ok" if rows else "insufficient recent data",
        "models": rows,
        "economics_available": not bool(economy_error),
        "status_messages": _status_messages(token_error, None, economy_error, None),
        "sources": data_loader.load_source_status(),
    }


def summarize_reasoning_loops() -> Dict[str, Any]:
    now = data_loader._now_utc()
    events, token_error = data_loader.load_token_events(now=now, lookback_hours=1.0)
    alerts, alert_error = data_loader.load_alert_events(limit=0, now=now, lookback_hours=1.0)
    if token_error == "missing":
        return {
            "available": False,
            "message": "source file unavailable",
            "loops": [],
            "status_messages": _status_messages(token_error, None, None, alert_error),
            "sources": data_loader.load_source_status(),
        }

    mitigation_phrases = ("throttle", "cooldown", "runaway", "retry", "mitigated", "model_mitigated")
    alert_counts_by_agent: Dict[str, int] = defaultdict(int)
    for alert in alerts:
        agent = alert.get("agent")
        if not agent:
            continue
        msg = str(alert.get("message", "")).lower()
        if any(token in msg for token in mitigation_phrases):
            alert_counts_by_agent[agent] += 1

    grouped: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for event in events:
        ts = event.get("parsed_ts")
        if not isinstance(ts, datetime):
            continue
        agent = str(event.get("agent_id", "unknown"))
        session = str(event.get("session_id") or f"agent-model:{event.get('model', 'unknown')}")
        grouped[(agent, session)].append(event)

    loops: List[dict] = []
    for (agent, session), group in grouped.items():
        if len(group) < 5:
            continue
        group.sort(key=lambda e: e.get("parsed_ts") or now)
        times = [e.get("parsed_ts") for e in group if isinstance(e.get("parsed_ts"), datetime)]
        if len(times) < 2:
            continue
        window_seconds = (times[-1] - times[0]).total_seconds()
        window_minutes = max(1, math.ceil(window_seconds / 60))
        event_count = len(group)
        token_values = [_sum_tokens(event) for event in group]
        if token_values:
            token_span = max(token_values) - min(token_values)
        else:
            token_span = 0
        gaps = [(times[i] - times[i - 1]).total_seconds() for i in range(1, len(times))]
        avg_gap = sum(gaps) / len(gaps) if gaps else 0.0
        models = [str(event.get("model", "unknown")) for event in group]
        model_unique = len(set(models))

        loop_score = 0.0
        signals: List[str] = []
        if event_count >= 8 and avg_gap <= 45:
            loop_score += 2.5
            signals.append("rapid repeated events")
        if token_span <= 40 and event_count >= 6:
            loop_score += 2.0
            signals.append("low token variance")
        if model_unique == 1 and event_count >= 6:
            loop_score += 1.5
            signals.append("same model churn")
        if model_unique > 2 and event_count >= 8:
            loop_score += 1.2
            signals.append("same model churn")
        if alert_counts_by_agent.get(agent, 0) >= 1:
            loop_score += 1.5
            signals.append("repeated mitigations")
        if "retry" in "".join(models).lower() or any(
            any(token in str(event.get("tool_name", "") or "").lower() for token in ("retry", "rerun"))
            for event in group
        ):
            loop_score += 0.8
            signals.append("repeated tool churn")

        if loop_score < 0.5:
            continue

        loops.append(
            {
                "agent_id": agent,
                "session_id": None if session.startswith("agent-model:") else session,
                "event_count": event_count,
                "time_window_minutes": window_minutes,
                "loop_score": _band_from_loop_score(loop_score),
                "reason_signals": signals,
                "latest_timestamp": _safe_ts_key(times[-1]),
                "score_value": loop_score,
            }
        )

    loops.sort(
        key=lambda row: (_severity_to_order(row["loop_score"]), row["event_count"], row["time_window_minutes"]),
        reverse=True,
    )
    # keep payload clean while still sortable by UI by display score only
    for row in loops:
        del row["score_value"]

    return {
        "available": True,
        "message": "ok" if loops else "insufficient recent data",
        "loops": loops,
        "status_messages": _status_messages(token_error, None, None, alert_error),
        "sources": data_loader.load_source_status(),
    }


def summarize_cost_anomalies() -> Dict[str, Any]:
    now = data_loader._now_utc()
    events, token_error = data_loader.load_token_events(now=now, lookback_hours=24.0)
    economics, economy_error = data_loader.load_economics_snapshot()

    if token_error == "missing":
        return {
            "available": False,
            "message": "source file unavailable",
            "anomalies": [],
            "status_messages": _status_messages(token_error, None, None, None),
            "sources": data_loader.load_source_status(),
        }

    anomalies: List[dict] = []

    def _pct_delta(base: float, observed: float) -> float:
        if base <= 0:
            return 100.0 if observed > 0 else 0.0
        return round(((observed - base) / base) * 100.0, 2)

    def _severity(delta: float) -> str:
        if delta >= 140.0:
            return "critical"
        if delta >= 80.0:
            return "high"
        if delta >= 40.0:
            return "caution"
        return "none"

    totals = economics.get("totals", {}) if isinstance(economics, dict) else {}
    cost_by_hour = totals.get("cost_by_hour", {}) if isinstance(totals, dict) else {}
    if isinstance(cost_by_hour, dict) and cost_by_hour:
        ordered_hours = sorted(cost_by_hour.items(), key=lambda item: item[0])
        latest_hour, latest_cost = ordered_hours[-1]
        prev_costs = [val for _, val in ordered_hours[:-1]]
        if prev_costs:
            base = sum(prev_costs) / len(prev_costs)
            delta = _pct_delta(base, _to_float(latest_cost))
            severity = _severity(delta)
            if severity != "none":
                anomalies.append(
                    {
                        "timestamp": _safe_ts_key(now),
                        "scope": "system",
                        "entity": "all",
                        "baseline_cost": base,
                        "observed_cost": _to_float(latest_cost),
                        "delta_percent": delta,
                        "severity": severity,
                        "reason": f"cost rise vs baseline by {delta}%",
                    }
                )

    if not anomalies:
        # estimate from token burn when no economics cost summary exists
        hours: Dict[str, Dict[str, int]] = {}
        for event in events:
            ts = event.get("parsed_ts")
            if not isinstance(ts, datetime):
                continue
            hour = ts.replace(minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")
            model = str(event.get("model", "unknown"))
            agent = str(event.get("agent_id", "unknown"))
            if hour not in hours:
                hours[hour] = {"all": 0}
            hours[hour][f"agent::{agent}"] = hours[hour].get(f"agent::{agent}", 0)
            hours[hour][f"model::{model}"] = hours[hour].get(f"model::{model}", 0)
            tokens = _sum_tokens(event)
            hours[hour]["all"] += tokens
            hours[hour][f"agent::{agent}"] += tokens
            hours[hour][f"model::{model}"] += tokens

        # pick last two intervals and compare against preceding rolling mean
        ordered = sorted(hours.items(), key=lambda item: item[0])
        for scope in ("all",):
            recent = [bucket.get(scope, 0) for _, bucket in ordered[-4:]]
            if len(recent) >= 4:
                latest = recent[-1]
                baseline = sum(recent[:-1]) / max(1, len(recent[:-1]))
                if baseline > 0 and latest > baseline:
                    base_cost = baseline * 0.00002
                    obs_cost = latest * 0.00002
                    delta = _pct_delta(base_cost, obs_cost)
                    sev = _severity(delta)
                    if sev != "none":
                        anomalies.append(
                            {
                                "timestamp": ordered[-1][0],
                                "scope": "system",
                                "entity": "all",
                                "baseline_cost": base_cost,
                                "observed_cost": obs_cost,
                                "delta_percent": delta,
                                "severity": sev,
                                "reason": "estimated from token growth",
                            }
                        )
        # model/agent granularity using last and prior averages
        scope_pairs = [k for k in {k for bucket in hours.values() for k in bucket.keys()} if k != "all"]
        for key in sorted(scope_pairs):
            series = [bucket.get(key, 0) for _, bucket in ordered]
            if len(series) < 4:
                continue
            latest_tokens = series[-1]
            baseline = sum(series[-4:-1]) / 3
            base_cost = baseline * 0.00002
            obs_cost = latest_tokens * 0.00002
            delta = _pct_delta(base_cost, obs_cost)
            sev = _severity(delta)
            if sev != "none":
                scope = "agent" if key.startswith("agent::") else "model"
                entity = key.split("::", 1)[1]
                anomalies.append(
                    {
                        "timestamp": ordered[-1][0],
                        "scope": scope,
                        "entity": entity,
                        "baseline_cost": base_cost,
                        "observed_cost": obs_cost,
                        "delta_percent": delta,
                        "severity": sev,
                        "reason": "estimated from token growth",
                    }
                )

    if not anomalies:
        return {
            "available": True,
            "message": "insufficient recent data",
            "anomalies": [],
            "status_messages": _status_messages(token_error, None, economy_error, None),
            "sources": data_loader.load_source_status(),
        }

    anomalies.sort(key=lambda row: (_severity_to_order(row["severity"]), row["timestamp"]), reverse=True)
    return {
        "available": True,
        "message": "ok",
        "anomalies": anomalies,
        "status_messages": _status_messages(token_error, None, economy_error, None),
        "sources": data_loader.load_source_status(),
    }


def _estimate_active_sessions(events: Sequence[dict]) -> int:
    started = set()
    ended = set()
    for event in events:
        session = str(event.get("session_id", ""))
        if not session:
            continue
        status = str(event.get("status", ""))
        if status == "session_start":
            started.add(session)
        elif status == "session_end":
            ended.add(session)
    active = started - ended
    if active:
        return len(active)
    sessions = {str(event.get("session_id", "")) for event in events if event.get("session_id")}
    return len(sessions)
