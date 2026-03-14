"""bonfire risk command."""

from __future__ import annotations

from typing import Dict, List

from bonfire.cli import helpers


def run(argv: List[str]) -> int:
    del argv
    agents_payload = helpers.call_transformer("summarize_agents")
    runaway_payload = helpers.call_transformer("summarize_runaway_agents")
    alerts_payload = helpers.call_transformer("summarize_alerts")

    agents = agents_payload.get("agents", []) if isinstance(agents_payload, dict) else []
    risky = sorted(agents, key=lambda row: float(row.get("risk_score", 0) or 0), reverse=True)
    risky = [row for row in risky if float(row.get("risk_score", 0) or 0) > 0]
    runaway_count = len((runaway_payload.get("runaway_agents", []) if isinstance(runaway_payload, dict) else []))
    interventions = (alerts_payload.get("governance_actions", []) if isinstance(alerts_payload, dict) else [])[:8]

    if not risky and runaway_count == 0 and not interventions:
        print("No meaningful risk data yet.")
        return 0

    print("Bonfire Risk")
    print(f"runaway_count: {runaway_count}")

    if risky:
        rows: List[Dict[str, str]] = []
        for row in risky[:10]:
            rows.append(
                {
                    "agent": str(row.get("agent_id", "unknown")),
                    "risk_score": helpers.fmt_float(row.get("risk_score", 0.0), 2),
                    "risk_level": str(row.get("risk_level", "unknown")),
                }
            )
        print("\ntop_risk_agents")
        print(helpers.print_table([("agent", "agent"), ("risk_score", "risk_score"), ("risk_level", "risk_level")], rows))

    if interventions:
        rows = []
        for item in interventions:
            rows.append(
                {
                    "timestamp": str(item.get("timestamp", "unavailable")),
                    "agent": str(item.get("agent") or "-"),
                    "message": str(item.get("message", ""))[:100],
                }
            )
        print("\nrecent_governor_interventions")
        print(helpers.print_table([("timestamp", "timestamp"), ("agent", "agent"), ("message", "message")], rows))

    return 0
