#!/usr/bin/env python3
"""Token budget accounting and enforcement primitives for Bonfire v2."""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

from bonfire.bonfire_logger import OPENCLAW_LOG_DIR, append_alert

BUDGET_STORE_PATH = Path(__file__).resolve().parent / "budget_store.json"
STATE_PATH = OPENCLAW_LOG_DIR / "bonfire_budget_state.json"

_HOURLY_WINDOW = 3600
_DAILY_WINDOW = 86400

_LOCK = threading.Lock()
_CACHE = {"ts": 0.0, "payload": {}}
_CACHE_TTL = 30.0

_AGENT_HISTORY = {
    "hourly": defaultdict(deque),
    "daily": defaultdict(deque),
}
_LANE_HISTORY = {
    "hourly": defaultdict(deque),
    "daily": defaultdict(deque),
}
_MODEL_HISTORY = {
    "hourly": defaultdict(deque),
}
_SESSION_HISTORY: Dict[str, deque] = {}

_ALERT_TRACKING = {
    "agent": set(),
    "session": set(),
    "cost": set(),
}
_COST_MODEL_RATES = {
    "claude-sonnet": {"input": 3.0, "output": 15.0},
    "gpt4": {"input": 10.0, "output": 30.0},
    "kimi": {"input": 1.0, "output": 3.0},
}
_HOURLY_COST_HISTORY = defaultdict(deque)


def _load_budget_store() -> dict:
    now = time.time()
    cached = _CACHE
    if cached.get("ts", 0) and now - cached["ts"] < _CACHE_TTL:
        return cached.get("payload", {})

    payload = {}
    try:
        with BUDGET_STORE_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, dict):
                payload = data
    except Exception:
        payload = {}

    if not payload:
        payload = {
            "agent_limits": {},
            "lane_limits": {},
            "model_limits": {},
            "defaults": {
                "agent": {
                    "hourly_tokens": 10000,
                    "daily_tokens": 50000,
                }
            },
            "alerts": {
                "agent_hourly_budget_pct": 80,
                "session_tokens": 20000,
                "hourly_cost_usd": 12,
            },
        }

    _CACHE["ts"] = now
    _CACHE["payload"] = payload
    return payload


def _alerts_config(payload: dict) -> dict:
    return payload.get("alerts", {}) or {}


def _clean_window(bucket: deque, now: float, window_secs: int) -> None:
    while bucket and now - bucket[0][0] > window_secs:
        bucket.popleft()


def _sum_window(bucket: deque, now: float, window_secs: int) -> float:
    _clean_window(bucket, now, window_secs)
    return float(sum(v for _ts, v in bucket))


def _append(bucket: deque, now: float, value: float) -> None:
    if value < 0:
        return
    try:
        bucket.append((now, float(value)))
    except Exception:
        bucket.append((now, 0.0))


def _agent_limits(payload: dict, agent_id: str) -> tuple[int, int]:
    defaults = payload.get("defaults", {}).get("agent", {}) if isinstance(payload.get("defaults", {}), dict) else {}
    config = payload.get("agent_limits", {}).get(agent_id, {}) if isinstance(payload.get("agent_limits", {}), dict) else {}
    hourly = int(config.get("hourly_tokens", defaults.get("hourly_tokens", 0) or 0))
    daily = int(config.get("daily_tokens", defaults.get("daily_tokens", 0) or 0))
    return max(hourly, 0), max(daily, 0)


def _lane_limits(payload: dict, lane: str) -> tuple[int, int]:
    limits = payload.get("lane_limits", {}) if isinstance(payload.get("lane_limits", {}), dict) else {}
    config = limits.get(lane, {}) if isinstance(limits.get(lane, {}), dict) else {}
    hourly = int(config.get("hourly_tokens", 0) or 0)
    daily = int(config.get("daily_tokens", 0) or 0)
    return max(hourly, 0), max(daily, 0)


def _model_limits(payload: dict, model: str) -> int:
    limits = payload.get("model_limits", {}) if isinstance(payload.get("model_limits", {}), dict) else {}
    canonical_model = _canonical_model(model)
    model_cfg = limits.get(canonical_model, {}) if isinstance(limits.get(canonical_model, {}), dict) else {}
    return max(int(model_cfg.get("hourly_tokens", 0) or 0), 0)


def _emit_budget_spike_alert(bucket_key: str, token_total: int, limit: int) -> None:
    payload = _load_budget_store()
    threshold_pct = int(_alerts_config(payload).get("agent_hourly_budget_pct", 80))
    if not threshold_pct:
        return

    if limit <= 0:
        return

    if bucket_key in _ALERT_TRACKING["agent"]:
        return

    if token_total >= (limit * threshold_pct) // 100 and token_total < limit:
        _ALERT_TRACKING["agent"].add(bucket_key)
        append_alert(
            f"BUDGET warning agent_hourly_threshold_reached bucket={bucket_key} usage={token_total} limit={limit} pct={threshold_pct}%"
        )


def _emit_session_alert(session_id: str, total: int, threshold: int) -> None:
    key = f"{session_id}:{total//100}"  # coarse de-dupe key
    if key in _ALERT_TRACKING["session"]:
        return
    _ALERT_TRACKING["session"].add(key)
    append_alert(
        f"BUDGET session_threshold_exceeded session={session_id} tokens={total} threshold={threshold}"
    )


def _session_bucket(session_id: str) -> deque:
    b = _SESSION_HISTORY.get(session_id)
    if b is None:
        b = deque()
        _SESSION_HISTORY[session_id] = b
    return b


def _canonical_model(model: str) -> str:
    m = (model or "").lower()
    if "claude" in m:
        return "claude-sonnet"
    if "gpt-4" in m or "gpt4" in m:
        return "gpt4"
    if "kimi" in m:
        return "kimi"
    return m


def _record_hourly_cost(agent_id: str, model: str, tokens: int) -> float:
    canonical = _canonical_model(model)
    rates = _COST_MODEL_RATES.get(canonical)
    if not rates:
        return 0.0
    # fallback to equal split when unknown output/input.
    half = max(tokens // 2, 0)
    in_t = half
    out_t = tokens - half
    input_rate = rates.get("input", 0.0)
    output_rate = rates.get("output", rates.get("input_output", 0.0))
    return (in_t / 1_000_000) * input_rate + (out_t / 1_000_000) * output_rate


def precheck(agent_id: str, lane: str, model: str, session_id: str | None, estimated_tokens: int) -> dict:
    """Evaluate whether a request can be attempted without breaching budgets."""
    try:
        return _precheck_locked(agent_id, lane, model, session_id, estimated_tokens)
    except Exception:
        # FAIL OPEN
        return {
            "action": "allow",
            "status": "GOVERNOR_FALLBACK_ALLOW",
            "agent_id": agent_id,
            "lane": lane,
            "model": model,
            "reason": "governor_failure",
            "mitigation": "none",
            "estimated_tokens": estimated_tokens,
        }


def _precheck_locked(agent_id: str, lane: str, model: str, session_id: str | None, estimated_tokens: int) -> dict:
    with _LOCK:
        model = _canonical_model(model)
        payload = _load_budget_store()
        now = time.time()

        if not isinstance(estimated_tokens, (int, float)):
            estimated_tokens = 0
        estimated_tokens = max(int(estimated_tokens), 0)

        agent_hour_key = f"agent:{agent_id}:{int(now // _HOURLY_WINDOW)}"
        lane_hour_key = f"lane:{lane}:{int(now // _HOURLY_WINDOW)}"
        model_hour_key = f"model:{model}:{int(now // _HOURLY_WINDOW)}"

        agent_hour_bucket = _AGENT_HISTORY["hourly"][agent_id]
        agent_day_bucket = _AGENT_HISTORY["daily"][agent_id]
        lane_hour_bucket = _LANE_HISTORY["hourly"][lane]
        lane_day_bucket = _LANE_HISTORY["daily"][lane]
        model_hour_bucket = _MODEL_HISTORY["hourly"][model]

        agent_hour_used = _sum_window(agent_hour_bucket, now, _HOURLY_WINDOW)
        lane_hour_used = _sum_window(lane_hour_bucket, now, _HOURLY_WINDOW)
        model_hour_used = _sum_window(model_hour_bucket, now, _HOURLY_WINDOW)
        agent_day_used = _sum_window(agent_day_bucket, now, _DAILY_WINDOW)
        lane_day_used = _sum_window(lane_day_bucket, now, _DAILY_WINDOW)

        agent_hour_limit, agent_day_limit = _agent_limits(payload, agent_id)
        lane_hour_limit, lane_day_limit = _lane_limits(payload, lane)
        model_hour_limit = _model_limits(payload, model)

        # unlimited values use 0
        if agent_hour_limit > 0 and agent_hour_used + estimated_tokens > agent_hour_limit:
            return {
                "action": "reject",
                "status": "TOKEN_BUDGET_EXCEEDED",
                "agent_id": agent_id,
                "lane": lane,
                "model": model,
                "estimated_tokens": estimated_tokens,
                "usage": {
                    "agent_hour": agent_hour_used,
                    "agent_hour_limit": agent_hour_limit,
                    "agent_day": agent_day_used,
                    "agent_day_limit": agent_day_limit,
                },
                "mitigation": "terminate",
                "reason": "agent_hourly_budget_exceeded",
            }

        if lane_hour_limit > 0 and lane_hour_used + estimated_tokens > lane_hour_limit:
            # In interactive overload, allow fallback to background lane.
            if lane == "background":
                return {
                    "action": "reject",
                    "status": "TOKEN_BUDGET_EXCEEDED",
                    "agent_id": agent_id,
                    "lane": lane,
                    "model": model,
                    "estimated_tokens": estimated_tokens,
                    "usage": {
                        "lane_hour": lane_hour_used,
                        "lane_hour_limit": lane_hour_limit,
                    },
                    "mitigation": "none",
                    "reason": "lane_hourly_budget_exceeded",
                }
            return {
                "action": "move_to_lane",
                "status": "LANE_BUDGET_EXCEEDED",
                "agent_id": agent_id,
                "lane": "background",
                "model": model,
                "estimated_tokens": estimated_tokens,
                "usage": {
                    "lane_hour": lane_hour_used,
                    "lane_hour_limit": lane_hour_limit,
                },
                "mitigation": "move_lane",
                "reason": "lane_hourly_budget_exceeded",
            }

        if lane_day_limit > 0 and lane_day_used + estimated_tokens > lane_day_limit:
            if lane == "background":
                return {
                    "action": "reject",
                    "status": "TOKEN_BUDGET_EXCEEDED",
                    "agent_id": agent_id,
                    "lane": lane,
                    "model": model,
                    "estimated_tokens": estimated_tokens,
                    "usage": {
                        "lane_day": lane_day_used,
                        "lane_day_limit": lane_day_limit,
                    },
                    "mitigation": "none",
                    "reason": "lane_daily_budget_exceeded",
                }
            return {
                "action": "move_to_lane",
                "status": "LANE_BUDGET_EXCEEDED",
                "agent_id": agent_id,
                "lane": "background",
                "model": model,
                "estimated_tokens": estimated_tokens,
                "usage": {
                    "lane_day": lane_day_used,
                    "lane_day_limit": lane_day_limit,
                },
                "mitigation": "move_lane",
                "reason": "lane_daily_budget_exceeded",
            }

        if model_hour_limit > 0 and model_hour_used + estimated_tokens > model_hour_limit:
            return {
                "action": "downgrade",
                "status": "MODEL_BUDGET_EXCEEDED",
                "agent_id": agent_id,
                "lane": lane,
                "model": model,
                "estimated_tokens": estimated_tokens,
                "usage": {
                    "model_hour": model_hour_used,
                    "model_hour_limit": model_hour_limit,
                },
                "mitigation": "downgrade",
                "reason": "model_hourly_budget_exceeded",
            }

        if agent_day_limit > 0 and agent_day_used + estimated_tokens > agent_day_limit:
            return {
                "action": "reject",
                "status": "TOKEN_BUDGET_EXCEEDED",
                "agent_id": agent_id,
                "lane": lane,
                "model": model,
                "estimated_tokens": estimated_tokens,
                "usage": {
                    "agent_day": agent_day_used,
                    "agent_day_limit": agent_day_limit,
                },
                "mitigation": "none",
                "reason": "agent_daily_budget_exceeded",
            }

        if session_id:
            session_bucket = _session_bucket(session_id)
            _clean_window(session_bucket, now, _HOURLY_WINDOW * 24)
            if len(session_bucket) == 0:
                _session_bucket(session_id).append((now, 0))

        # non-blocking alert when near budget in normal path
        _emit_budget_spike_alert(agent_hour_key, agent_hour_used, agent_hour_limit)

        return {
            "action": "allow",
            "status": "ALLOW",
            "agent_id": agent_id,
            "lane": lane,
            "model": model,
            "estimated_tokens": estimated_tokens,
            "usage": {
                "agent_hour": agent_hour_used,
                "agent_hour_limit": agent_hour_limit,
                "lane_hour": lane_hour_used,
                "lane_hour_limit": lane_hour_limit,
                "model_hour": model_hour_used,
                "model_hour_limit": model_hour_limit,
            },
            "mitigation": "none",
            "reason": "ok",
        }


def record_usage(agent_id: str, lane: str, model: str, session_id: str | None, tokens: int) -> None:
    """Record post-request token burn."""
    try:
        with _LOCK:
            model = _canonical_model(model)
            payload = _load_budget_store()
            now = time.time()
            try:
                tokens = int(tokens)
            except Exception:
                tokens = 0
            if tokens < 0:
                return

            _append(_AGENT_HISTORY["hourly"][agent_id], now, tokens)
            _append(_AGENT_HISTORY["daily"][agent_id], now, tokens)
            _append(_LANE_HISTORY["hourly"][lane], now, tokens)
            _append(_LANE_HISTORY["daily"][lane], now, tokens)
            _append(_MODEL_HISTORY["hourly"][model], now, tokens)

            if session_id:
                _append(_session_bucket(session_id), now, tokens)
                limit = int(_alerts_config(payload).get("session_tokens", 20000) or 20000)
                session_total = _sum_window(_session_bucket(session_id), now, _HOURLY_WINDOW * 24)
                if session_total >= limit:
                    _emit_session_alert(session_id, session_total, limit)

            # Cost threshold alerting
            cost = _record_hourly_cost(agent_id, model, tokens)
            hour_bucket_key = f"{agent_id}:{int(now // _HOURLY_WINDOW)}"
            _append(_HOURLY_COST_HISTORY[hour_bucket_key], now, cost)
            hour_cost = _sum_window(_HOURLY_COST_HISTORY[hour_bucket_key], now, _HOURLY_WINDOW)
            hourly_cost_limit = float(_alerts_config(payload).get("hourly_cost_usd", 0.0) or 0.0)
            if hourly_cost_limit > 0.0 and hour_cost >= hourly_cost_limit:
                cost_key = f"{hour_bucket_key}:{int(hour_cost)}"
                if cost_key not in _ALERT_TRACKING["cost"]:
                    _ALERT_TRACKING["cost"].add(cost_key)
                    append_alert(
                        f"BUDGET hourly_cost_limit_exceeded bucket={hour_bucket_key} cost=${hour_cost:.2f} threshold=${hourly_cost_limit:.2f}"
                    )

            _persist_state(now)
    except Exception:
        # Fail-open: telemetry must never block execution.
        pass


def _persist_state(now: float) -> None:
    try:
        OPENCLAW_LOG_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "agent_hour": {
                k: list(v) for k, v in _AGENT_HISTORY["hourly"].items() if v
            },
            "agent_day": {
                k: list(v) for k, v in _AGENT_HISTORY["daily"].items() if v
            },
            "lane_hour": {
                k: list(v) for k, v in _LANE_HISTORY["hourly"].items() if v
            },
            "lane_day": {
                k: list(v) for k, v in _LANE_HISTORY["daily"].items() if v
            },
            "model_hour": {
                k: list(v) for k, v in _MODEL_HISTORY["hourly"].items() if v
            },
            "session_hour": {
                k: list(v) for k, v in _SESSION_HISTORY.items() if v
            },
        }
        tmp = STATE_PATH.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        tmp.replace(STATE_PATH)
    except Exception:
        pass


def get_runtime_snapshot() -> dict:
    payload = _load_budget_store()
    now = time.time()
    with _LOCK:
        agents = {}
        for aid in set(_AGENT_HISTORY["hourly"].keys()) | set(_AGENT_HISTORY["daily"].keys()):
            hourly_limit, daily_limit = _agent_limits(payload, aid)
            hourly_used = _sum_window(_AGENT_HISTORY["hourly"][aid], now, _HOURLY_WINDOW)
            daily_used = _sum_window(_AGENT_HISTORY["daily"][aid], now, _DAILY_WINDOW)
            agents[aid] = {
                "hourly": {"used": hourly_used, "limit": hourly_limit},
                "daily": {"used": daily_used, "limit": daily_limit},
            }

        lanes = {}
        for lane in set(_LANE_HISTORY["hourly"].keys()) | set(_LANE_HISTORY["daily"].keys()):
            hourly_limit, daily_limit = _lane_limits(payload, lane)
            lanes[lane] = {
                "hourly": {
                    "used": _sum_window(_LANE_HISTORY["hourly"][lane], now, _HOURLY_WINDOW),
                    "limit": hourly_limit,
                },
                "daily": {
                    "used": _sum_window(_LANE_HISTORY["daily"][lane], now, _DAILY_WINDOW),
                    "limit": daily_limit,
                },
            }

        models = {}
        for model in _MODEL_HISTORY["hourly"].keys():
            limit = _model_limits(payload, model)
            models[model] = {
                "hourly": {
                    "used": _sum_window(_MODEL_HISTORY["hourly"][model], now, _HOURLY_WINDOW),
                    "limit": limit,
                }
            }

    return {
        "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "agents": agents,
        "lanes": lanes,
        "models": models,
        "hourly_window_sec": _HOURLY_WINDOW,
        "daily_window_sec": _DAILY_WINDOW,
    }


def get_all_alerts_config() -> dict:
    return _alerts_config(_load_budget_store())


def get_budgets_snapshot() -> Tuple[dict, dict]:
    payload = _load_budget_store()
    return payload, get_runtime_snapshot()


def _cleanup() -> None:
    now = time.time()
    with _LOCK:
        for bucket in _AGENT_HISTORY["hourly"].values():
            _clean_window(bucket, now, _HOURLY_WINDOW)
        for bucket in _AGENT_HISTORY["daily"].values():
            _clean_window(bucket, now, _DAILY_WINDOW)
        for bucket in _LANE_HISTORY["hourly"].values():
            _clean_window(bucket, now, _HOURLY_WINDOW)
        for bucket in _LANE_HISTORY["daily"].values():
            _clean_window(bucket, now, _DAILY_WINDOW)
        for bucket in _MODEL_HISTORY["hourly"].values():
            _clean_window(bucket, now, _HOURLY_WINDOW)
        for bucket in _SESSION_HISTORY.values():
            _clean_window(bucket, now, _HOURLY_WINDOW * 24)
