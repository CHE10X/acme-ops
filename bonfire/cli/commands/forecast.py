"""bonfire forecast command."""

from __future__ import annotations

from typing import List

from bonfire.cli import helpers


def run(argv: List[str]) -> int:
    del argv
    agents_payload = helpers.call_transformer("summarize_agents")
    econ_payload = helpers.call_transformer("summarize_economics")
    agent_sources = agents_payload.get("sources", {}) if isinstance(agents_payload, dict) else {}
    econ_sources = econ_payload.get("sources", {}) if isinstance(econ_payload, dict) else {}

    agents = agents_payload.get("agents", []) if isinstance(agents_payload, dict) else []
    totals = econ_payload.get("totals", {}) if isinstance(econ_payload, dict) else {}

    projected_next_hour = 0.0
    for row in agents:
        projected_next_hour += float(row.get("predicted_tokens", 0) or 0)

    all_agent_sources_missing = bool(agent_sources) and all(not bool((row or {}).get("available")) for row in agent_sources.values())
    all_econ_sources_missing = bool(econ_sources) and all(not bool((row or {}).get("available")) for row in econ_sources.values())
    no_forecast_signal = projected_next_hour <= 0 and float(totals.get("total_tokens", 0) or 0) <= 0
    if no_forecast_signal and (all_agent_sources_missing or all_econ_sources_missing):
        print("Forecast unavailable.")
        return 0

    projected_daily_tokens = (projected_next_hour * 24.0) if projected_next_hour > 0 else None

    projected_daily_cost = None
    total_tokens = float(totals.get("total_tokens", 0) or 0)
    total_cost = float(totals.get("total_cost_usd", 0) or 0)
    if projected_daily_tokens and total_tokens > 0 and total_cost >= 0:
        projected_daily_cost = (total_cost / total_tokens) * projected_daily_tokens

    print("Bonfire Forecast")
    if projected_next_hour > 0:
        print(f"projected_tokens_next_hour: {helpers.fmt_int(projected_next_hour)}")
    else:
        print("projected_tokens_next_hour: unavailable")

    if projected_daily_tokens is not None:
        print(f"projected_daily_total: {helpers.fmt_int(projected_daily_tokens)}")
    else:
        print("projected_daily_total: unavailable")

    if projected_daily_cost is not None:
        print(f"projected_daily_cost: {helpers.fmt_usd(projected_daily_cost)}")
    else:
        print("projected_daily_cost: unavailable")
    return 0
