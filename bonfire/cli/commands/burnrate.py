"""bonfire burnrate command."""

from __future__ import annotations

from typing import List

from bonfire.cli import helpers


def _status(avg_per_min: float) -> str:
    if avg_per_min >= 1000:
        return "critical"
    if avg_per_min >= 400:
        return "high"
    if avg_per_min >= 100:
        return "normal"
    return "low"


def run(argv: List[str]) -> int:
    del argv
    payload = helpers.call_transformer("summarize_burn_rate")
    points = payload.get("points", []) if isinstance(payload, dict) else []

    if not points:
        print("No burn-rate data yet.")
        return 0

    tokens_60 = sum(int(point.get("tokens", 0) or 0) for point in points)
    avg = tokens_60 / 60.0
    print("Bonfire Burn Rate")
    print(f"tokens_last_60m: {helpers.fmt_int(tokens_60)}")
    print(f"avg_tokens_per_minute: {helpers.fmt_float(avg, 2)}")
    print(f"burn_status: {_status(avg)}")
    return 0
