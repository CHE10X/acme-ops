#!/usr/bin/env python3
"""Agent risk scoring for Bonfire v3."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from statistics import mean, pstdev
from typing import Dict

from bonfire.collector.session_tracker import get_session_start


_LOCK = threading.Lock()
_WINDOW_SECS = 60.0
_STATE = defaultdict(
    lambda: {
        "tokens": deque(),
        "latency": deque(),
        "errors": deque(),
        "tool_calls": deque(),
        "escalations": deque(),
    }
)


def _prune(bucket: deque, now: float) -> None:
    while bucket and now - bucket[0][0] > _WINDOW_SECS:
        bucket.popleft()


def _safe_int(value, default: int = 0) -> int:
    try:
        n = int(value)
        return n if n >= 0 else default
    except Exception:
        return default


def record_request(
    *,
    agent_id: str,
    session_id: str,
    model: str,
    total_tokens: int,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    latency_ms: int = 0,
    status: str = "success",
    lane: str = "interactive",
) -> None:
    now = time.time()
    with _LOCK:
        state = _STATE[(agent_id or "unknown")]
        state["tokens"].append((now, _safe_int(total_tokens, 0)))
        state["latency"].append((now, _safe_int(latency_ms, 0)))
        state["errors"].append((now, 0 if str(status).lower() == "success" else 1))
        _prune(state["tokens"], now)
        _prune(state["latency"], now)
        _prune(state["errors"], now)


def record_tool_call(agent_id: str, session_id: str | None = None) -> None:
    now = time.time()
    with _LOCK:
        state = _STATE[(agent_id or "unknown")]
        state["tool_calls"].append((now, 1))
        _prune(state["tool_calls"], now)


def record_escalation(agent_id: str, source: str = "model_guard") -> None:
    now = time.time()
    with _LOCK:
        state = _STATE[(agent_id or "unknown")]
        state["escalations"].append((now, 1))
        _prune(state["escalations"], now)


def _factor_from_bucket(bucket: deque, window_sum: bool = True) -> float:
    return float(sum(v for _ts, v in bucket)) if window_sum else 0.0


def score_for(agent_id: str, session_id: str | None = None) -> Dict[str, object]:
    now = time.time()
    with _LOCK:
        state = _STATE[(agent_id or "unknown")]
        for bucket_name in ("tokens", "latency", "errors", "tool_calls", "escalations"):
            _prune(state[bucket_name], now)

        token_values = [v for _ts, v in state["tokens"] if v > 0]
        err_values = [v for _ts, v in state["errors"] if v > 0]
        token_count = len(state["tokens"])
        if token_count > 0:
            token_avg = mean([v for _ts, v in state["tokens"] if v > 0] or [0])
            token_std = pstdev([v for _ts, v in state["tokens"] if v > 0]) if len(token_values) > 1 else 0.0
            token_volatility = min(30.0, (token_std / max(1.0, token_avg)) * 100.0)
        else:
            token_volatility = 0.0

        tool_calls = _factor_from_bucket(state["tool_calls"])
        escalation_rate = _factor_from_bucket(state["escalations"])
        session_age = 0
        if session_id:
            start_ts = get_session_start(agent_id, session_id=session_id)
            if start_ts:
                session_age = max(0.0, now - float(start_ts))
        session_factor = min(25.0, session_age / 120.0)
        latency_values = [v for _ts, v in state["latency"]]
        latency_factor = min(20.0, (mean(latency_values) / 100.0) if latency_values else 0.0)
        error_factor = min(25.0, (len(err_values) / max(1, token_count)) * 100.0)
        tool_factor = min(20.0, tool_calls * 2.0)
        escalation_factor = min(25.0, escalation_rate * 4.0)

        risk = token_volatility + session_factor + error_factor + latency_factor + tool_factor + escalation_factor
        risk = max(0.0, min(100.0, risk))

        if risk >= 80:
            level = "runaway"
        elif risk >= 60:
            level = "high"
        elif risk >= 30:
            level = "caution"
        else:
            level = "healthy"

        return {
            "agent_id": agent_id or "unknown",
            "risk_score": int(risk),
            "risk_level": level,
            "components": {
                "token_volatility": round(token_volatility, 2),
                "session_length_factor": round(session_factor, 2),
                "tool_loop_factor": round(tool_factor, 2),
                "error_rate_factor": round(error_factor, 2),
                "model_escalation_factor": round(escalation_factor, 2),
            },
            "sample": {
                "events": len(state["tokens"]),
                "tool_calls": int(tool_calls),
                "errors": len(err_values),
            },
        }


def list_scores() -> list[Dict[str, object]]:
    scores = []
    with _LOCK:
        ids = list(_STATE.keys())
    for agent_id in ids:
        scores.append(score_for(agent_id))
    return sorted(scores, key=lambda row: row["risk_score"], reverse=True)


def print_risk_summary(top_n: int = 5) -> None:
    scores = list_scores()
    print("Agent risk ranking:")
    for row in scores[:top_n]:
        print(
            f"  {row['agent_id']}: score={row['risk_score']} level={row['risk_level']} "
            f"events={row['sample']['events']} tool_calls={row['sample']['tool_calls']}"
        )
    if not scores:
        print("  no risk data")

