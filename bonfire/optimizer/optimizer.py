#!/usr/bin/env python3
"""V3 model selection optimizer."""

from __future__ import annotations

from typing import Any, Dict

from bonfire.router.adaptive_router import choose_model


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        value = int(value)
        if value < 0:
            return default
        return value
    except Exception:
        return default


def _coerce_str(value: Any, default: str = "") -> str:
    try:
        value = str(value)
    except Exception:
        return default
    return value.strip() or default


def determine_tier(predicted_tokens: int, lane: str, prompt: str = "") -> str:
    """Classify expected request work into a routing tier."""
    lane = _coerce_str(lane, "interactive")
    tokens = _coerce_int(predicted_tokens, 0)
    prompt_l = _coerce_str(prompt, "").lower()

    if lane == "system":
        return "large"
    if lane == "background":
        if tokens >= 6000:
            return "medium"
        return "small"

    if tokens >= 9000 or any(word in prompt_l for word in ("analysis", "architecture", "design", "synthesize", "incident")):
        return "large"
    if tokens >= 3000 or any(word in prompt_l for word in ("plan", "investigate", "debug", "reason")):
        return "medium"
    return "small"


def optimize_model(
    *,
    requested_model: str,
    lane: str,
    predicted_tokens: int,
    prompt: str,
) -> Dict[str, Any]:
    """Return the optimizer's model recommendation and tier metadata."""
    model, reason = choose_model(
        requested_model=requested_model,
        lane=lane,
        predicted_tokens=predicted_tokens,
        prompt=prompt,
    )
    tier = determine_tier(predicted_tokens, lane, prompt)
    return {
        "requested_model": _coerce_str(requested_model, ""),
        "lane": _coerce_str(lane, "interactive"),
        "predicted_tokens": _coerce_int(predicted_tokens, 0),
        "model_tier": tier,
        "model": _coerce_str(model, requested_model),
        "decision_reason": _coerce_str(reason, "adaptive_select"),
    }


def optimize(agent_context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    context = agent_context or {}
    return optimize_model(
        requested_model=_coerce_str(context.get("requested_model") or context.get("model"), "claude-sonnet"),
        lane=_coerce_str(context.get("lane"), "interactive"),
        predicted_tokens=_coerce_int(context.get("predicted_tokens"), 0),
        prompt=_coerce_str(context.get("prompt"), ""),
    )
