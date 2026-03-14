#!/usr/bin/env python3
"""Shared dashboard state-to-color mapping."""

from __future__ import annotations

STATES = ("healthy", "caution", "high", "runaway", "unavailable")

STATE_CLASS = {
    "healthy": "state-healthy",
    "caution": "state-caution",
    "high": "state-high",
    "runaway": "state-runaway",
    "unavailable": "state-unavailable",
}

DEFAULT_STATE = "unavailable"


def normalize_state(value: str | None) -> str:
    """Normalize arbitrary labels into a dashboard state."""
    value = (value or "").strip().lower()
    if value in STATES:
        return value
    if "runaway" in value:
        return "runaway"
    if "high" in value:
        return "high"
    if "caution" in value or "warn" in value:
        return "caution"
    if "healthy" in value or value in {"ok", "good", "normal"}:
        return "healthy"
    return DEFAULT_STATE


def class_for(state: str | None) -> str:
    """Return CSS class for a normalized state."""
    return STATE_CLASS[normalize_state(state)]
