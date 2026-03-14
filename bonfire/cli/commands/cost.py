"""bonfire cost command."""

from __future__ import annotations

from typing import Dict, List

from bonfire.cli import helpers


def run(argv: List[str]) -> int:
    del argv
    payload = helpers.call_transformer("summarize_economics")
    totals = payload.get("totals", {}) if isinstance(payload, dict) else {}
    agent_rows = payload.get("agent_rows", []) if isinstance(payload, dict) else []
    model_rows = payload.get("model_rows", []) if isinstance(payload, dict) else []

    total_cost = totals.get("total_cost_usd", 0.0)
    daily_total = totals.get("total_tokens", 0)

    if (not agent_rows and not model_rows) and float(total_cost or 0.0) <= 0.0:
        print("Insufficient cost data.")
        return 0

    print("Bonfire Cost")
    print(f"cost_today: {helpers.fmt_usd(total_cost)}")
    print(f"daily_total_tokens: {helpers.fmt_int(daily_total)}")

    if agent_rows:
        rows: List[Dict[str, str]] = []
        for row in agent_rows[:12]:
            rows.append(
                {
                    "agent": str(row.get("agent_id", "unknown")),
                    "cost_total": helpers.fmt_usd(row.get("cost_total", 0.0)),
                    "tokens": helpers.fmt_int(row.get("token_total", 0)),
                }
            )
        print("\ncost_by_agent")
        print(helpers.print_table([("agent", "agent"), ("cost_total", "cost_total"), ("tokens", "tokens")], rows))

    if model_rows:
        rows = []
        for row in model_rows[:12]:
            rows.append(
                {
                    "model": str(row.get("model", "unknown")),
                    "cost_total": helpers.fmt_usd(row.get("cost_total", 0.0)),
                    "tokens": helpers.fmt_int(row.get("token_total", 0)),
                }
            )
        print("\ncost_by_model")
        print(helpers.print_table([("model", "model"), ("cost_total", "cost_total"), ("tokens", "tokens")], rows))

    return 0
