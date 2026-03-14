#!/usr/bin/env python3
"""Bonfire route telemetry adapter."""

from __future__ import annotations

from typing import Any, Dict, Optional

from bonfire.bonfire_logger import append_event, _iso_now
from bonfire.risk.agent_risk_score import record_request as record_risk_request

try:
    from bonfire.predictor.token_predictor import record_actual as record_predicted_actual
except Exception:  # pragma: no cover
    record_predicted_actual = None

try:
    from bonfire.budgets.budget_manager import record_usage
except Exception:
    record_usage = None


def _to_int(value: Any, default: int = -1) -> int:
    try:
        value = int(value)
        return value if value >= 0 else default
    except (TypeError, ValueError):
        return default


def _coerce_usage(usage: Optional[Dict[str, Any]]) -> Dict[str, int]:
    if not isinstance(usage, dict):
        return {"prompt_tokens": -1, "completion_tokens": -1, "total_tokens": -1}

    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    total = usage.get("total_tokens")
    if prompt is None and "input" in usage:
        prompt = usage.get("input")
    if completion is None and "output" in usage:
        completion = usage.get("output")
    if total is None and "total" in usage:
        total = usage.get("total")

    prompt_tokens = _to_int(prompt)
    completion_tokens = _to_int(completion)
    total_tokens = _to_int(total)
    if total_tokens < 0 and prompt_tokens >= 0 or completion_tokens >= 0:
        total_tokens = max(0, prompt_tokens) + max(0, completion_tokens)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def estimate_total_tokens(prompt: str, completion: str) -> Dict[str, int]:
    prompt_tokens = max(0, int(len(prompt or "") / 4))
    completion_tokens = max(0, int(len(completion or "") / 4))
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def record_route_decision(
    *,
    agent_id: str,
    session_id: str,
    requested_model: str,
    selected_model: str | None,
    selected_lane: str | None = None,
    decision_ms: int = 0,
    governor_action: str = "allow",
    governor_status: str = "ALLOW",
    predicted_prompt_tokens: int = -1,
    predicted_completion_tokens: int = -1,
    predicted_total_tokens: int = -1,
    status: str = "ok",
    model_tier: str = "medium",
    optimizer_reason: str = "",
) -> None:
    append_event(
        {
            "timestamp": _iso_now(),
            "event": "router_decision",
            "agent_id": agent_id,
            "session_id": session_id,
            "model": selected_model or requested_model,
            "prompt_tokens": _to_int(predicted_prompt_tokens, -1),
            "completion_tokens": _to_int(predicted_completion_tokens, -1),
            "total_tokens": _to_int(predicted_total_tokens, -1),
            "tool_used": "model_router",
            "latency_ms": _to_int(decision_ms, 0),
            "status": status,
            "lane": selected_lane or "interactive",
            "session_runway": governor_action,
            "governor_status": governor_status,
            "governor_action": governor_action,
            "model_tier": model_tier,
            "optimizer_reason": optimizer_reason,
        }
    )


def record_route_event(
    *,
    agent_id: str,
    session_id: str,
    model: str,
    prompt: str,
    completion: str,
    usage: Optional[Dict[str, Any]],
    latency_ms: int,
    tool_used: str,
    status: str,
    started_at_ms: int,
    lane: str | None = None,
    session_runway: str | None = None,
    predicted_tokens: Optional[int] = None,
) -> None:
    usage_tokens = _coerce_usage(usage)
    if usage_tokens["total_tokens"] < 0:
        usage_tokens = estimate_total_tokens(prompt, completion)

    total_tokens = usage_tokens["total_tokens"]
    event = {
        "timestamp": _iso_now(),
        "agent_id": agent_id,
        "session_id": session_id,
        "model": model,
        "prompt_tokens": usage_tokens["prompt_tokens"],
        "completion_tokens": usage_tokens["completion_tokens"],
        "total_tokens": total_tokens,
        "tool_used": tool_used,
        "latency_ms": _to_int(latency_ms),
        "status": status,
        "started_at_ms": int(started_at_ms),
        "lane": lane or "unknown",
        "session_runway": session_runway or "unknown",
    }
    if predicted_tokens is not None:
        event["predicted_tokens"] = int(predicted_tokens)
    append_event(event)

    try:
        record_risk_request(
            agent_id=agent_id,
            session_id=session_id,
            model=model,
            total_tokens=total_tokens,
            prompt_tokens=usage_tokens["prompt_tokens"],
            completion_tokens=usage_tokens["completion_tokens"],
            latency_ms=_to_int(latency_ms),
            status=status,
            lane=lane or "interactive",
        )
    except Exception:
        pass

    if record_predicted_actual is not None:
        try:
            record_predicted_actual(
                agent_id=agent_id,
                model=model,
                total_tokens=total_tokens,
                prompt_tokens=usage_tokens["prompt_tokens"],
                completion_tokens=usage_tokens["completion_tokens"],
                predicted_tokens=predicted_tokens,
            )
        except Exception:
            pass

    if record_usage is not None:
        try:
            record_usage(agent_id, lane or "interactive", model, session_id, total_tokens)
        except Exception:
            pass
