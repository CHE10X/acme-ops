#!/usr/bin/env python3
"""Runaway agent detection and cooldown controls."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import datetime
import threading

from bonfire.bonfire_logger import append_alert, append_event


_LOCK = threading.Lock()
_RUNAWAY_CFG = {
    "requests_per_minute": 120,
    "token_growth_per_min": 8000,
    "tool_loop_count_per_min": 20,
    "session_duration_limit_s": 14400,
    "cooldown_seconds": 60,
}


_agent_req_times = defaultdict(deque)
_agent_token_times = defaultdict(deque)
_agent_tool_calls = defaultdict(deque)


def _norm(v: str) -> str:
    return (v or "unknown").strip().lower()


def _prune(bucket: deque, now: float, window: float = 60.0) -> None:
    while bucket and now - bucket[0][0] > window:
        bucket.popleft()


def check_agent(agent_id: str, session_id: str | None = None, session_duration_s: float = 0.0, pending_tokens: int = 0) -> dict:
    now = time.time()
    with _LOCK:
        rids = _agent_req_times[agent_id]
        tids = _agent_token_times[agent_id]
        tcs = _agent_tool_calls[agent_id]

        rids.append((now, 1))
        tids.append((now, max(0, int(pending_tokens))))
        _prune(rids, now)
        _prune(tids, now)
        _prune(tcs, now)

        req_per_min = sum(1 for _ts, _ in rids)
        tok_per_min = sum(v for _ts, v in tids)
        tool_per_min = len(tcs)

        if req_per_min > _RUNAWAY_CFG["requests_per_minute"]:
            append_alert(f"RUNAWAY req_rate_exceeded agent={_norm(agent_id)} requests_per_min={req_per_min}")
            return {
                "action": "delay",
                "status": "RUNAWAY_AGENT_PAUSED",
                "delay_seconds": _RUNAWAY_CFG["cooldown_seconds"],
                "reason": "requests_per_minute",
            }

        if tok_per_min > _RUNAWAY_CFG["token_growth_per_min"]:
            append_alert(f"RUNAWAY token_growth_exceeded agent={_norm(agent_id)} tokens_per_min={tok_per_min}")
            append_event(
                {
                    "event": "runaway_detected",
                    "agent_id": agent_id,
                    "session_id": session_id or "unknown",
                    "model": "runtime",
                    "prompt_tokens": tok_per_min,
                    "completion_tokens": 0,
                    "total_tokens": tok_per_min,
                    "tool_used": "agent_throttle",
                    "latency_ms": 0,
                    "status": "terminate_session",
                }
            )
            return {
                "action": "terminate",
                "status": "RUNAWAY_AGENT_TERMINATED",
                "reason": "token_growth_rate",
            }

        if tool_per_min > _RUNAWAY_CFG["tool_loop_count_per_min"]:
            append_alert(f"RUNAWAY tool_loop_exceeded agent={_norm(agent_id)} tool_calls_per_min={tool_per_min}")
            return {
                "action": "delay",
                "status": "RUNAWAY_TOOL_LOOP",
                "delay_seconds": _RUNAWAY_CFG["cooldown_seconds"],
                "reason": "tool_loop_detected",
            }

        if session_duration_s > _RUNAWAY_CFG["session_duration_limit_s"]:
            append_alert(f"RUNAWAY session_timeout agent={_norm(agent_id)} duration_s={int(session_duration_s)}")
            return {
                "action": "terminate",
                "status": "RUNAWAY_SESSION_TERMINATED",
                "reason": "session_duration_limit",
            }

        return {"action": "allow"}


def notify_tool_call(agent_id: str, session_id: str | None = None, tool_name: str = "tool", delta_tokens: int = 0) -> None:
    now = time.time()
    with _LOCK:
        _agent_tool_calls[agent_id].append((now, max(0, int(delta_tokens))))
        _prune(_agent_tool_calls[agent_id], now)


def update_thresholds(**kwargs):
    for key, value in kwargs.items():
        if key in _RUNAWAY_CFG:
            try:
                _RUNAWAY_CFG[key] = int(value)
            except Exception:
                pass
