"""bonfire alerts command."""

from __future__ import annotations

from typing import Dict, List

from bonfire.cli import helpers


def run(argv: List[str]) -> int:
    del argv
    alerts = helpers.recent_alert_events(hours=24.0, limit=500)
    if not alerts:
        print("No alerts found.")
        return 0

    rows: List[Dict[str, str]] = []
    for alert in alerts[-30:]:
        rows.append(
            {
                "timestamp": str(alert.get("timestamp", "unavailable")),
                "severity": str(alert.get("severity", "unknown")),
                "agent": str(alert.get("agent") or helpers.parse_agent_from_message(str(alert.get("message", ""))) or "-")[:20],
                "message": str(alert.get("message", ""))[:100],
            }
        )

    print("Bonfire Alerts (last 24h)")
    print(helpers.print_table(
        [
            ("timestamp", "timestamp"),
            ("severity", "severity"),
            ("agent", "agent"),
            ("message", "message"),
        ],
        rows,
    ))
    return 0
