"""bonfire watch command."""

from __future__ import annotations

import argparse
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from bonfire.cli import helpers


def _safe_interval(value: Any) -> float:
    try:
        parsed = float(value)
        if parsed <= 0:
            return 3.0
        return parsed
    except Exception:
        return 3.0


def _event_total_tokens(event: Dict[str, Any]) -> int:
    try:
        total = int(event.get("total_tokens", 0) or 0)
    except Exception:
        total = 0
    if total > 0:
        return total
    try:
        prompt = int(event.get("prompt_tokens", 0) or 0)
    except Exception:
        prompt = 0
    try:
        completion = int(event.get("completion_tokens", 0) or 0)
    except Exception:
        completion = 0
    return max(0, prompt + completion)


def _event_ts(event: Dict[str, Any]) -> datetime | None:
    ts = event.get("parsed_ts")
    if isinstance(ts, datetime):
        return ts
    raw = event.get("timestamp")
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def _clear() -> None:
    print("\033[2J\033[H", end="")


def _latest_alert(alerts: List[Dict[str, Any]]) -> str:
    if not alerts:
        return "none"
    item = alerts[-1]
    severity = str(item.get("severity") or "unknown")
    agent = str(item.get("agent") or helpers.parse_agent_from_message(str(item.get("message", ""))) or "-")
    message = str(item.get("message", "")).strip()
    trimmed = message[:80]
    return f"{severity} agent={agent} {trimmed}".strip()


def _risk_map() -> Dict[str, Any]:
    health = helpers.read_json(helpers.HEALTH_PATH)
    agents = health.get("agents", []) if isinstance(health, dict) else []
    mapping: Dict[str, Any] = {}
    if isinstance(agents, dict):
        for agent, row in agents.items():
            if isinstance(row, dict):
                mapping[str(agent)] = row.get("risk_score", "unknown")
        return mapping
    if isinstance(agents, list):
        for row in agents:
            if isinstance(row, dict):
                mapping[str(row.get("agent_id", "unknown"))] = row.get("risk_score", "unknown")
    return mapping


def _collect_frame() -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    events = helpers.recent_token_events(hours=24.0, max_events=8000)
    alerts = helpers.recent_alert_events(hours=24.0, limit=200)
    economics = helpers.read_json(helpers.ECONOMICS_PATH)

    cutoff_1m = now - timedelta(minutes=1)
    cutoff_1h = now - timedelta(hours=1)

    tokens_last_1m = 0
    tokens_last_1h = 0
    tokens_last_24h = 0

    active_sessions = set()
    agent_tokens_5m = defaultdict(int)
    agent_model_tokens = defaultdict(lambda: defaultdict(int))
    agent_sessions = defaultdict(set)

    model_requests = defaultdict(int)
    model_tokens = defaultdict(int)
    model_latency = defaultdict(list)

    cutoff_5m = now - timedelta(minutes=5)

    for event in events:
        tokens = _event_total_tokens(event)
        ts = _event_ts(event)
        tokens_last_24h += tokens
        if ts is not None and ts >= cutoff_1h:
            tokens_last_1h += tokens
        if ts is not None and ts >= cutoff_1m:
            tokens_last_1m += tokens

        session_id = event.get("session_id")
        if session_id:
            active_sessions.add(str(session_id))

        agent = str(event.get("agent_id") or "unknown")
        model = str(event.get("model") or "unknown")

        if ts is not None and ts >= cutoff_5m:
            agent_tokens_5m[agent] += tokens
            agent_model_tokens[agent][model] += tokens
            if session_id:
                agent_sessions[agent].add(str(session_id))
            model_requests[model] += 1
            model_tokens[model] += tokens
            latency = event.get("latency_ms")
            try:
                latency_value = float(latency)
            except Exception:
                latency_value = 0.0
            if latency_value > 0:
                model_latency[model].append(latency_value)

    cost_today = ((economics.get("totals") or {}).get("total_cost_usd", 0.0) if isinstance(economics, dict) else 0.0)

    risk_map = _risk_map()

    agent_rows: List[Tuple[str, str, float, str, int, int]] = []
    for agent, tokens_5m in agent_tokens_5m.items():
        dominant_model = "unknown"
        by_model = agent_model_tokens.get(agent, {})
        if by_model:
            dominant_model = max(by_model, key=by_model.get)
        tok_per_min = tokens_5m / 5.0
        risk_value = risk_map.get(agent, "unknown")
        if risk_value == "unknown":
            risk_text = "unknown"
        else:
            risk_text = helpers.fmt_float(risk_value, 1)
        sessions = len(agent_sessions.get(agent, set()))
        agent_rows.append((agent, dominant_model, tok_per_min, risk_text, sessions, tokens_5m))
    agent_rows.sort(key=lambda row: row[5], reverse=True)

    model_rows: List[Tuple[str, int, int, str]] = []
    for model, total_tokens in model_tokens.items():
        reqs = int(model_requests.get(model, 0))
        latencies = model_latency.get(model, [])
        if latencies:
            avg_latency = sum(latencies) / len(latencies)
            latency_text = helpers.fmt_float(avg_latency, 1)
        else:
            latency_text = "unknown"
        model_rows.append((model, reqs, total_tokens, latency_text))
    model_rows.sort(key=lambda row: row[2], reverse=True)

    all_missing = not any(
        [helpers.TOKENS_PATH.exists(), helpers.HEALTH_PATH.exists(), helpers.ECONOMICS_PATH.exists(), helpers.ALERTS_PATH.exists()]
    )

    return {
        "refreshed": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "all_missing": all_missing,
        "active_sessions": len(active_sessions),
        "tokens_last_1m": tokens_last_1m,
        "tokens_last_1h": tokens_last_1h,
        "tokens_last_24h": tokens_last_24h,
        "cost_today": cost_today,
        "latest_alert": _latest_alert(alerts),
        "agent_rows": agent_rows[:10],
        "model_rows": model_rows[:10],
        "alerts": alerts[-5:],
    }


def _render(frame: Dict[str, Any]) -> None:
    print("BONFIRE WATCH")
    if frame.get("all_missing"):
        print("No telemetry available yet.")
        return

    print(f"Refreshed: {frame.get('refreshed', 'unknown')}")
    print()

    print("SYSTEM")
    print(f"active_sessions: {helpers.fmt_int(frame.get('active_sessions', 0))}")
    print(f"tokens_last_1m: {helpers.fmt_int(frame.get('tokens_last_1m', 0))}")
    print(f"tokens_last_1h: {helpers.fmt_int(frame.get('tokens_last_1h', 0))}")
    print(f"tokens_last_24h: {helpers.fmt_int(frame.get('tokens_last_24h', 0))}")
    print(f"cost_today: {helpers.fmt_usd(frame.get('cost_today', 0.0))}")
    print(f"latest_alert: {frame.get('latest_alert', 'none')}")
    print()

    print("AGENTS")
    agent_rows = frame.get("agent_rows", [])
    if not agent_rows:
        print("No agent activity.")
    else:
        print("agent_id | model | tok/min | risk | sessions")
        for agent, model, tok_per_min, risk, sessions, _ in agent_rows:
            print(f"{agent} | {model} | {helpers.fmt_float(tok_per_min, 2)} | {risk} | {sessions}")
    print()

    print("MODELS")
    model_rows = frame.get("model_rows", [])
    if not model_rows:
        print("No model activity.")
    else:
        print("model | requests | tokens | avg_latency")
        for model, requests, tokens, avg_latency in model_rows:
            latency_text = avg_latency if avg_latency != "unknown" else "latency unknown"
            print(f"{model} | {requests} requests | {tokens} tokens | {latency_text}")
    print()

    print("ALERTS")
    alerts = frame.get("alerts", [])
    if not alerts:
        print("No alerts.")
    else:
        print("timestamp | severity | message")
        for item in alerts:
            timestamp = str(item.get("timestamp", "unavailable"))
            severity = str(item.get("severity", "unknown"))
            message = str(item.get("message", ""))[:120]
            print(f"{timestamp} | {severity} | {message}")


def run(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="bonfire watch", add_help=False)
    parser.add_argument("-interval", "--interval", default="3")
    parser.add_argument("-h", "--help", action="store_true")
    ns, _ = parser.parse_known_args(argv)

    if ns.help:
        print("Usage: bonfire watch [-interval 3]")
        return 0

    interval = _safe_interval(ns.interval)

    try:
        while True:
            frame = _collect_frame()
            _clear()
            _render(frame)
            time.sleep(interval)
    except KeyboardInterrupt:
        print()
        return 0
