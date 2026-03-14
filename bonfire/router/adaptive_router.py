#!/usr/bin/env python3
"""Adaptive model selection for Bonfire v3."""

from __future__ import annotations

from typing import Dict, Tuple


def _normalize_model(model: str) -> str:
    m = (model or "").lower().strip()
    if "gpt4" in m or "gpt-4" in m:
        return "gpt4"
    if "claude" in m:
        return "claude-sonnet"
    if "kimi" in m:
        return "kimi"
    return m or "claude-sonnet"


def score_task_complexity(prompt: str, predicted_tokens: int) -> float:
    text = (prompt or "").lower()
    base = predicted_tokens or 0
    if "analysis" in text or "reason" in text:
        base += 2200
    if "multi-step" in text or "plan" in text:
        base += 1000
    if "trace" in text or "debug" in text or "investigate" in text:
        base += 500
    return float(base)


def choose_model(
    *,
    requested_model: str,
    lane: str,
    predicted_tokens: int,
    prompt: str,
) -> Tuple[str, str]:
    """Return (model, mode) for v3 adaptive routing."""
    lane = (lane or "interactive").lower().strip() or "interactive"
    model = _normalize_model(requested_model)

    if lane == "system":
        return ("claude-sonnet", "system_default")

    complexity = score_task_complexity(prompt, predicted_tokens)
    if lane == "background":
        if complexity >= 5500:
            return ("claude-sonnet", "background_upgrade_guarded")
        return ("kimi", "background_default")

    # interactive mode
    if complexity <= 1500:
        return ("kimi", "interactive_small_task")
    if complexity <= 5500:
        return ("claude-sonnet", "interactive_reasoning")
    return ("gpt4", "interactive_heavy")

