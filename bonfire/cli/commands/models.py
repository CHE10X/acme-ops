"""bonfire models command."""

from __future__ import annotations

from typing import Dict, List

from bonfire.cli import helpers


def run(argv: List[str]) -> int:
    del argv
    events = helpers.recent_token_events(hours=24.0, max_events=5000)
    rows: List[Dict[str, str]] = []

    for event in events:
        if str(event.get("event", "")) != "router_decision":
            continue
        decision = event.get("decision") if isinstance(event.get("decision"), dict) else {}
        rows.append(
            {
                "timestamp": str(event.get("timestamp", "unavailable")),
                "agent": str(event.get("agent_id", "unknown")),
                "requested_model": str(decision.get("requested_model", "unknown")),
                "selected_model": str(decision.get("selected_model", event.get("model", "unknown"))),
                "reason": str(decision.get("optimizer_reason", decision.get("governor_action", "route"))),
            }
        )

    if not rows:
        fallback = helpers.call_transformer("summarize_model_downgrades")
        for row in fallback.get("events", []) if isinstance(fallback, dict) else []:
            rows.append(
                {
                    "timestamp": str(row.get("timestamp", "unavailable")),
                    "agent": str(row.get("agent", "unknown")),
                    "requested_model": str(row.get("original_model", "unknown")),
                    "selected_model": str(row.get("new_model", "unknown")),
                    "reason": str(row.get("reason", "model change")),
                }
            )

    if not rows:
        print("No model routing decisions recorded yet.")
        return 0

    rows = rows[-30:]
    print("Bonfire Model Decisions")
    print(
        helpers.print_table(
            [
                ("timestamp", "timestamp"),
                ("agent", "agent"),
                ("requested_model", "requested_model"),
                ("selected_model", "selected_model"),
                ("reason", "reason"),
            ],
            rows,
        )
    )
    return 0
