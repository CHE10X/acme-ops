"""
Resilience Event Bus (REB) — shared write helper
PROJ-2026-008

Append-only NDJSON event bus for the resilience layer.
Every resilience product emits here. Bonfire tails as consumer.

Usage:
    from acme_ops.resilience.reb import reb_emit
    reb_emit("sentinel", "funnel_drift", "HIGH", {"alignment_state": "DIVERGED"})
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

# Canonical REB location
REB_DIR = Path(os.environ.get("OPENCLAW_RESILIENCE_DIR", Path.home() / ".openclaw" / "resilience"))
REB_FILE = REB_DIR / "resilience_events.jsonl"

VALID_SEVERITIES = {"INFO", "WARN", "HIGH", "CRITICAL"}


def reb_emit(source: str, event_type: str, severity: str, payload: dict = None) -> dict:
    """
    Emit an event to the Resilience Event Bus.

    Args:
        source:     Product name (e.g. "sentinel", "infrawatch", "watchdog")
        event_type: Event identifier (e.g. "funnel_drift", "config_drift", "gateway_stall")
        severity:   One of INFO | WARN | HIGH | CRITICAL
        payload:    Optional dict with event-specific data

    Returns:
        The event dict that was written.

    Raises:
        ValueError: if severity is not one of the valid values
    """
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"Invalid severity '{severity}'. Must be one of {VALID_SEVERITIES}")

    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "event_type": event_type,
        "severity": severity,
        "payload": payload or {},
    }

    # Auto-create resilience dir on first write
    REB_DIR.mkdir(parents=True, exist_ok=True)

    with open(REB_FILE, "a") as f:
        f.write(json.dumps(event) + "\n")

    return event


def reb_tail(since_ts: str = None, severity_filter: list = None) -> list:
    """
    Read events from the REB, optionally filtered by timestamp or severity.

    Args:
        since_ts:        ISO-8601 timestamp — only return events after this
        severity_filter: List of severities to include (e.g. ["HIGH", "CRITICAL"])

    Returns:
        List of event dicts, chronological order
    """
    if not REB_FILE.exists():
        return []

    events = []
    with open(REB_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if since_ts and event.get("ts", "") <= since_ts:
                continue

            if severity_filter and event.get("severity") not in severity_filter:
                continue

            events.append(event)

    return events


def reb_last(n: int = 10, severity_filter: list = None) -> list:
    """Return the last N events from the REB."""
    return reb_tail(severity_filter=severity_filter)[-n:]


if __name__ == "__main__":
    # Self-test
    print(f"REB location: {REB_FILE}")
    test_event = reb_emit("reb", "self_test", "INFO", {"msg": "REB write helper initialized"})
    print(f"Test event written: {test_event}")
    recent = reb_last(1)
    print(f"Last event: {recent[0] if recent else 'none'}")
    print("OK")
