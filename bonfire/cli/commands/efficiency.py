"""bonfire efficiency command."""

from __future__ import annotations

from typing import Dict, List

from bonfire.cli import helpers


def run(argv: List[str]) -> int:
    del argv
    payload = helpers.call_transformer("summarize_model_efficiency")
    rows_in = payload.get("models", []) if isinstance(payload, dict) else []

    if not rows_in:
        print("No model efficiency data yet.")
        return 0

    rows: List[Dict[str, str]] = []
    for row in rows_in[:20]:
        rows.append(
            {
                "model": str(row.get("model", "unknown")),
                "events_count": helpers.fmt_int(row.get("events_count", 0)),
                "total_tokens": helpers.fmt_int(row.get("total_tokens", 0)),
                "avg_tokens_per_event": helpers.fmt_float(row.get("avg_tokens_per_event", 0), 2),
                "efficiency_ratio": helpers.fmt_float(row.get("efficiency_ratio", 0), 3),
                "avg_latency_ms": helpers.fmt_float(row.get("avg_latency_ms", 0), 2) if row.get("avg_latency_ms") is not None else "-",
                "cost_total": helpers.fmt_usd(row.get("cost_total", 0)) if row.get("cost_total") is not None else "-",
            }
        )

    print("Bonfire Model Efficiency")
    print(
        helpers.print_table(
            [
                ("model", "model"),
                ("events_count", "events_count"),
                ("total_tokens", "total_tokens"),
                ("avg_tokens_per_event", "avg_tokens_per_event"),
                ("efficiency_ratio", "efficiency_ratio"),
                ("avg_latency_ms", "avg_latency_ms"),
                ("cost_total", "cost_total"),
            ],
            rows,
        )
    )
    return 0
