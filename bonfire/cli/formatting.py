"""Formatting helpers for operator-readable CLI output."""

from __future__ import annotations

from typing import Any


def heading(title: str) -> str:
    return title.strip()


def kv(key: str, value: Any) -> str:
    return f"{key}: {value}"
