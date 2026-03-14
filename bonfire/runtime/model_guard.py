#!/usr/bin/env python3
"""Model routing guardrails for lane-specific policies."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Tuple

_ROOT = Path.home() / ".openclaw" / "workspace" / "openclaw-ops"
# In-repo config path
CONFIG_PATH = Path(__file__).resolve().parents[1] / "policy" / "lane_policy.json"

_CACHE = {"ts": 0.0, "policy": {}}
_CACHE_TTL = 30


def _canonical_model(model: str) -> str:
    m = (model or "").lower()
    if "|" in m:
        m = m.split("|", 1)[1]
    if "/" in m:
        m = m.split("/", 1)[1]
    if "gpt-4" in m:
        return "gpt4"
    if "claude-sonnet" in m or "claude" in m:
        return "claude-sonnet"
    if "kimi" in m:
        return "kimi"
    return m or "unknown"


def _load_policy():
    now = time.time()
    if _CACHE.get("ts", 0.0) and now - _CACHE["ts"] < _CACHE_TTL:
        return _CACHE.get("policy", {})
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
            if isinstance(payload, dict):
                _CACHE["policy"] = payload
                _CACHE["ts"] = now
                return payload
    except Exception:
        pass
    return {
        "agents": {},
        "lanes": {
            "interactive": {"default_model": "claude-sonnet", "allowed_models": ["claude-sonnet", "kimi", "gpt4"]},
            "background": {"default_model": "kimi", "allowed_models": ["kimi", "claude-sonnet"], "deny_models": ["gpt4"]},
            "system": {"default_model": "claude-sonnet", "allowed_models": ["claude-sonnet", "kimi", "gpt4"]},
        },
        "model_alias": {
            "gpt4": ["gpt4", "gpt-4", "gpt-4.1-mini"],
            "claude-sonnet": ["claude", "claude-sonnet", "claude-sonnet-4-6"],
            "kimi": ["kimi", "kimi-k2", "kimi-v1"],
        },
    }


def _resolve_model_name(model: str) -> str:
    model = (model or "").lower().strip()
    policy = _load_policy()
    aliases = policy.get("model_alias", {})
    for canonical, values in aliases.items():
        for value in values:
            if value in model:
                return canonical
    return _canonical_model(model)


def enforce_model(agent_id: str, lane: str, model: str) -> Tuple[str, str]:
    policy = _load_policy()
    lane_cfg = policy.get("lanes", {}).get(lane, {})
    deny = set(lane_cfg.get("deny_models", []) or [])
    allowed = set(lane_cfg.get("allowed_models", []) or [])
    default_model = lane_cfg.get("default_model", "claude-sonnet")

    canonical = _resolve_model_name(model)
    if canonical in deny:
        return default_model, "downgrade"
    if allowed and canonical not in allowed:
        # choose first allowed as fallback
        return sorted(allowed)[0], "downgrade"
    return model, "allow"


def normalize_for_chain(model: str, lane: str | None = None) -> str:
    # Return model string that can be compared against provider/model entries quickly.
    model = model.lower().strip()
    if model in ("claude-sonnet", "claude"):
        return "claude-sonnet-4-6"
    if model in ("gpt4", "gpt-4", "gpt-4.1-mini", "gpt-4-mini"):
        return "gpt-4.1-mini"
    if model.startswith("kimi"):
        return "kimi-k2"
    # Keep existing requested model; governor can rewrite chain providers if unsupported.
    return model


def allowed_lanes_for_agent(agent_id: str):
    policy = _load_policy()
    return policy.get("agents", {}).get(agent_id, {}).get("allowed_lanes", ["interactive"]) or ["interactive"]
