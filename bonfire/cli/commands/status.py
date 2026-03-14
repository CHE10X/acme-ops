"""bonfire status command."""

from __future__ import annotations

from typing import Any, Dict, List

from bonfire.cli import helpers


def _state_or_unknown(value: Any) -> str:
    if not value:
        return "unknown"
    return str(value)


def _derive_subsystem_states(events: List[Dict[str, Any]], alerts: List[Dict[str, Any]]) -> Dict[str, str]:
    router = any((event.get("event") in {"router_decision", "router_signal"}) or event.get("tool_used") == "model_router" for event in events)
    predictor = any(
        isinstance(event.get("decision"), dict) and (
            "predicted_total_tokens" in event["decision"]
            or "predicted_prompt_tokens" in event["decision"]
            or "predicted_completion_tokens" in event["decision"]
        )
        for event in events
    )
    optimizer = any(
        isinstance(event.get("decision"), dict) and (
            event["decision"].get("optimizer_reason")
            or event["decision"].get("model_tier")
        )
        for event in events
    )
    governor = any(
        (
            event.get("governor_action")
            or event.get("governor_status")
            or (isinstance(event.get("decision"), dict) and (event["decision"].get("governor_action") or event["decision"].get("governor_status")))
        )
        for event in events
    ) or any("governor" in str(alert.get("message", "")).lower() for alert in alerts)

    return {
        "router": "active" if router else "unknown",
        "predictor": "active" if predictor else "unknown",
        "optimizer": "active" if optimizer else "unknown",
        "governor": "active" if governor else "unknown",
    }


def run(argv: List[str]) -> int:
    del argv
    overview = helpers.call_transformer("summarize_overview")
    metrics = overview.get("metrics", {}) if isinstance(overview, dict) else {}
    sources = overview.get("sources", {}) if isinstance(overview, dict) else {}

    events_24h = helpers.recent_token_events(hours=24.0, max_events=5000)
    alerts_24h = helpers.recent_alert_events(hours=24.0, limit=500)
    states = _derive_subsystem_states(events_24h, alerts_24h)

    active_sessions = metrics.get("active_sessions")
    if active_sessions in (None, ""):
        active_sessions = len({str(event.get("session_id")) for event in events_24h if event.get("session_id")})

    tokens_1h = metrics.get("total_tokens_last_1h")
    if tokens_1h in (None, ""):
        events_1h = helpers.recent_token_events(hours=1.0, max_events=5000)
        tokens_1h = sum(int(event.get("total_tokens", 0) or 0) for event in events_1h)

    tokens_24h = metrics.get("total_tokens_last_24h")
    if tokens_24h in (None, ""):
        tokens_24h = sum(int(event.get("total_tokens", 0) or 0) for event in events_24h)

    cost_today = metrics.get("cost_today")
    if cost_today in (None, ""):
        econ = helpers.read_json(helpers.ECONOMICS_PATH)
        cost_today = ((econ.get("totals") or {}).get("total_cost_usd", 0.0) if isinstance(econ, dict) else 0.0)

    severity_counts: Dict[str, int] = {}
    for alert in alerts_24h:
        sev = str(alert.get("severity", "unknown"))
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    print("Bonfire Status")
    all_sources_missing = bool(sources) and all(not bool((row or {}).get("available")) for row in sources.values())
    if all_sources_missing and not events_24h:
        print("No telemetry available yet.")
        return 0

    print(f"router: {_state_or_unknown(states['router'])}")
    print(f"predictor: {_state_or_unknown(states['predictor'])}")
    print(f"optimizer: {_state_or_unknown(states['optimizer'])}")
    print(f"governor: {_state_or_unknown(states['governor'])}")
    print(f"active_sessions: {helpers.fmt_int(active_sessions)}")
    print(f"tokens_last_1h: {helpers.fmt_int(tokens_1h)}")
    print(f"tokens_last_24h: {helpers.fmt_int(tokens_24h)}")
    print(f"cost_today: {helpers.fmt_usd(cost_today)}")
    if severity_counts:
        summary = ", ".join(f"{k}={v}" for k, v in sorted(severity_counts.items()))
        print(f"alerts: {summary}")
    else:
        print("alerts: none")
    return 0
