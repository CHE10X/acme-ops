"""bonfire runaway command."""

from __future__ import annotations

from typing import Dict, List

from bonfire.cli import helpers


def run(argv: List[str]) -> int:
    del argv
    payload = helpers.call_transformer("summarize_runaway_agents")
    loops_payload = helpers.call_transformer("summarize_reasoning_loops")

    runaway_rows = payload.get("runaway_agents", []) if isinstance(payload, dict) else []
    loop_rows = loops_payload.get("loops", []) if isinstance(loops_payload, dict) else []
    loop_map = {str(row.get("agent_id")): str(row.get("loop_score", "unknown")) for row in loop_rows}

    if not runaway_rows:
        print("No runaway agents detected.")
        return 0

    rows: List[Dict[str, str]] = []
    for row in runaway_rows[:20]:
        agent = str(row.get("agent_id", "unknown"))
        rows.append(
            {
                "agent": agent,
                "loop_score": loop_map.get(agent, "unknown"),
                "risk_score": helpers.fmt_float(row.get("risk_score", 0), 2),
                "recent_tokens": helpers.fmt_int(row.get("recent_tokens", 0)),
                "latest_alert": str(row.get("latest_alert", ""))[:80] or "-",
            }
        )

    print("Bonfire Runaway")
    print(
        helpers.print_table(
            [
                ("agent", "agent"),
                ("loop_score", "loop_score"),
                ("risk_score", "risk_score"),
                ("recent_tokens", "recent_tokens"),
                ("latest_alert", "latest_alert"),
            ],
            rows,
        )
    )
    return 0
