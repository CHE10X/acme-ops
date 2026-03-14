#!/usr/bin/env python3
"""Predict token usage before model execution."""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from statistics import mean
from typing import Dict, Optional


_LOCK = threading.Lock()
_WINDOW = 24
_AGENT_HISTORY = defaultdict(
    lambda: {
        "tokens": deque(maxlen=_WINDOW),
        "ratios": deque(maxlen=_WINDOW),
        "predictions": deque(maxlen=_WINDOW),
    }
)

_MODEL_FACTOR = {
    "kimi": 0.78,
    "claude-sonnet": 1.0,
    "gpt4": 1.4,
}
_LANE_FACTOR = {
    "background": 0.7,
    "interactive": 1.0,
    "system": 1.0,
}
_COMPLEX_KEYWORDS = ("analyze", "plan", "compare", "design", "implement", "debug", "refactor", "incident")


def _iso_name(model: str) -> str:
    m = (model or "").lower().strip()
    if "gpt4" in m or "gpt-4" in m:
        return "gpt4"
    if "claude" in m:
        return "claude-sonnet"
    if "kimi" in m:
        return "kimi"
    return m or "claude-sonnet"


def _complexity_factor(prompt: str) -> float:
    if not prompt:
        return 1.0
    normalized = (prompt or "").lower()
    long_words = sum(1 for chunk in normalized.split() if len(chunk) > 12)
    prompt_len = len(normalized)
    keyword_hits = sum(1 for kw in _COMPLEX_KEYWORDS if kw in normalized)
    base = 1.0
    if prompt_len > 1800:
        base += 0.25
    if long_words > 20:
        base += 0.20
    if keyword_hits >= 2:
        base += 0.30
    return min(2.1, base)


def _safe_int(value: object, default: int = 0) -> int:
    try:
        n = int(value)
        return n if n >= 0 else default
    except Exception:
        return default


def estimate_tokens(
    prompt: str,
    *,
    agent_id: str | None = None,
    session_id: str | None = None,  # kept for caller contracts and future extension
    model: str | None = None,
    lane: str | None = None,
    tool_invocations: int = 0,
) -> Dict[str, int]:
    """Predict token burn before request execution."""
    model_name = _iso_name(model or "claude-sonnet")
    lane_name = (lane or "interactive").strip().lower() or "interactive"
    lane_name = lane_name if lane_name in _LANE_FACTOR else "interactive"

    prompt_tokens = max(1, len((prompt or "")) // 4)
    model_factor = _MODEL_FACTOR.get(model_name, 1.0)
    lane_factor = _LANE_FACTOR.get(lane_name, 1.0)
    complexity = _complexity_factor(prompt or "")
    tool_factor = 1.0 + (min(int(tool_invocations), 6) * 0.08)
    baseline = float(prompt_tokens) * (0.9 + min(0.35, tool_factor - 1.0))

    history = _AGENT_HISTORY[(agent_id or "unknown")]
    with _LOCK:
        history_tokens = list(history["tokens"])
        recent_predictions = list(history["predictions"])
    recent_avg = mean(history_tokens) if history_tokens else max(1.0, float(prompt_tokens))
    if recent_predictions:
        correction = mean(recent_predictions)
        trend = min(1.45, max(0.6, 1.0 / correction)) if correction > 0 else 1.0
    else:
        trend = 1.0

    predicted_prompt = int(max(1.0, prompt_tokens * model_factor * lane_factor * complexity * trend))
    predicted_total = int(
        predicted_prompt
        * 2.2
        * (0.85 + 0.25 * (tool_factor - 1.0))
    )
    completion_guess = max(1, int(predicted_total * 0.35))
    if "reasoning" in (prompt or "").lower():
        completion_guess = int(completion_guess * 1.4)
    completion_guess = max(1, completion_guess)
    predicted_total = max(predicted_prompt + completion_guess, predicted_prompt + 1)

    return {
        "agent_id": agent_id or "unknown",
        "session_id": session_id or "",
        "model": model_name,
        "lane": lane_name,
        "prompt_tokens": predicted_prompt,
        "completion_tokens": completion_guess,
        "total_tokens": predicted_total,
        "tool_invocations": max(0, int(tool_invocations)),
        "estimated": True,
    }


def record_actual(
    *,
    agent_id: str,
    model: str,
    total_tokens: int,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    predicted_tokens: int | None = None,
) -> None:
    """Record observed request cost for continuous local prediction correction."""
    total_tokens = _safe_int(total_tokens, 0)
    if total_tokens <= 0:
        return

    with _LOCK:
        state = _AGENT_HISTORY[(agent_id or "unknown")]
        state["tokens"].append(total_tokens)

        prompt = max(0, int(prompt_tokens))
        completion = max(0, int(completion_tokens))
        if prompt == 0 and completion == 0 and total_tokens > 0:
            completion = max(1, total_tokens - (total_tokens // 3))
            prompt = total_tokens - completion
        ratio = min(1.0, completion / max(1, (prompt + completion)))
        state["ratios"].append(float(ratio))
        if predicted_tokens is not None:
            p = _safe_int(predicted_tokens, total_tokens)
            if p > 0:
                state["predictions"].append(float(total_tokens) / max(1.0, float(p)))


def threshold_mitigation(total_tokens: int, lane: str) -> str:
    """Return mitigation hint when predicted usage is high for lane."""
    lane = (lane or "interactive").lower()
    if lane == "background":
        if total_tokens >= 12000:
            return "reject"
        if total_tokens >= 5500:
            return "downgrade"
        return "allow"
    if total_tokens >= 18000:
        return "reject"
    if total_tokens >= 9000:
        return "downgrade"
    return "allow"


def get_agent_profile(agent_id: str) -> Dict[str, int]:
    with _LOCK:
        state = _AGENT_HISTORY.get(agent_id or "unknown", {})
        if not state:
            return {"avg_total": 0, "ratio": 0, "recent_error": 0}
        tokens = list(state["tokens"])
        ratios = list(state["ratios"])
        if not tokens:
            return {"avg_total": 0, "ratio": 0, "recent_error": 0}
        avg_total = int(mean(tokens))
        ratio = int(mean(ratios) * 100) if ratios else 50
        return {"avg_total": avg_total, "ratio": ratio, "recent_error": len(state["predictions"])}
