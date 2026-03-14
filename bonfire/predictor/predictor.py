#!/usr/bin/env python3
"""V3 routing predictor facade."""

from __future__ import annotations

from typing import Any, Dict

try:
    from bonfire.predictor.token_predictor import estimate_tokens as _estimate_tokens
except Exception:  # pragma: no cover
    _estimate_tokens = None


def _coerce_str(value: Any, default: str = "") -> str:
    try:
        value = str(value)
    except Exception:
        return default
    return value.strip() or default


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        value = int(value)
        if value < 0:
            return default
        return value
    except Exception:
        return default


def _fallback_estimate(prompt: str) -> Dict[str, int]:
    prompt_tokens = max(0, len(prompt or "") // 4)
    completion_tokens = max(0, prompt_tokens // 2)
    return {
        "agent_id": "unknown",
        "session_id": "",
        "model": "claude-sonnet",
        "lane": "interactive",
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "tool_invocations": 0,
        "estimated": True,
    }


def predict(agent_context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Estimate token usage for a request before model execution.

    Args:
        agent_context: dict with optional keys agent_id, session_id, prompt,
            requested_model, lane, tool_invocations.
    """
    context = agent_context or {}
    prompt = _coerce_str(context.get("prompt"), "")
    predicted: Dict[str, Any]

    requested_model = _coerce_str(context.get("requested_model") or context.get("model"), "claude-sonnet")
    lane = _coerce_str(context.get("lane"), "interactive")
    agent_id = _coerce_str(context.get("agent_id"), "unknown")
    session_id = _coerce_str(context.get("session_id"), "")
    tool_invocations = _coerce_int(context.get("tool_invocations"), 0)

    if _estimate_tokens is not None:
        try:
            predicted = dict(_estimate_tokens(
                prompt,
                agent_id=agent_id,
                session_id=session_id,
                model=requested_model,
                lane=lane,
                tool_invocations=tool_invocations,
            ))
        except Exception:
            predicted = _fallback_estimate(prompt)
    else:
        predicted = _fallback_estimate(prompt)

    predicted.setdefault("agent_id", agent_id)
    predicted.setdefault("session_id", session_id)
    predicted.setdefault("model", requested_model)
    predicted.setdefault("lane", lane)
    predicted.setdefault("tool_invocations", tool_invocations)

    return {
        "agent_id": _coerce_str(predicted.get("agent_id"), agent_id),
        "session_id": _coerce_str(predicted.get("session_id"), session_id),
        "model": _coerce_str(predicted.get("model"), requested_model),
        "lane": _coerce_str(predicted.get("lane"), lane),
        "prompt_tokens": _coerce_int(predicted.get("prompt_tokens"), 0),
        "completion_tokens": _coerce_int(predicted.get("completion_tokens"), 0),
        "total_tokens": _coerce_int(predicted.get("total_tokens"), 0),
        "tool_invocations": _coerce_int(predicted.get("tool_invocations"), tool_invocations),
        "estimated": bool(predicted.get("estimated", True)),
        "requested_model": requested_model,
    }


def predict_tokens(agent_context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Alias for router-facing code."""
    return predict(agent_context)
