#!/usr/bin/env python3
"""Tool-call wrappers with Bonfire events."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Callable, Optional

from bonfire.bonfire_logger import append_event
from bonfire.collector.session_tracker import get_or_start_session
from bonfire.runtime.agent_throttle import notify_tool_call
from bonfire.risk.agent_risk_score import record_tool_call as record_risk_tool_call
from bonfire.bonfire_logger import _iso_now


def emit_routing_signal(
    *,
    agent_id: str,
    session_id: str,
    model: str,
    predicted_tokens: int,
    lane: str,
    governor_action: str,
) -> None:
    append_event(
        {
            "timestamp": _iso_now(),
            "event": "router_signal",
            "agent_id": agent_id,
            "session_id": session_id,
            "model": model,
            "prompt_tokens": max(0, int(predicted_tokens)),
            "completion_tokens": 0,
            "total_tokens": max(0, int(predicted_tokens)),
            "tool_used": "model_router",
            "latency_ms": 0,
            "status": governor_action,
            "lane": lane,
        }
    )


def _to_int(v) -> int:
    try:
        return int(v)
    except Exception:
        return -1


def track_tool_call(
    tool_name: str,
    tool_fn: Callable[..., object],
    *,
    agent_id: str = "unknown",
    session_id: Optional[str] = None,
    token_before: Optional[Callable[[], int]] = None,
):
    def _wrapped(*args, **kwargs):
        sid = get_or_start_session(agent_id, session_id=session_id)
        before = token_before() if callable(token_before) else None
        t0 = time.perf_counter()
        status = "success"
        try:
            return tool_fn(*args, **kwargs)
        except Exception:
            status = "error"
            raise
        finally:
            elapsed = int((time.perf_counter() - t0) * 1000)
            after = token_before() if callable(token_before) else None
            b = _to_int(before)
            a = _to_int(after)
            append_event(
                {
                    "timestamp": _iso_now(),
                    "event": "tool_call",
                    "agent_id": agent_id,
                    "session_id": sid,
                    "model": "tool",
                    "prompt_tokens": b if b >= 0 else -1,
                    "completion_tokens": a if a >= 0 else -1,
                    "total_tokens": -1,
                    "tool_used": tool_name,
                    "latency_ms": elapsed,
                    "status": status,
                    "tokens_before": b if b >= 0 else None,
                    "tokens_after": a if a >= 0 else None,
                }
            )
            if b >= 0 and a >= 0:
                notify_tool_call(agent_id, sid, tool_name, a - b)
                try:
                    record_risk_tool_call(agent_id, sid)
                except Exception:
                    pass
    return _wrapped


@contextmanager

def tool_call_scope(
    tool_name: str,
    *,
    agent_id: str = "unknown",
    session_id: Optional[str] = None,
    token_before: Optional[Callable[[], int]] = None,
):
    sid = get_or_start_session(agent_id, session_id=session_id)
    before = token_before() if callable(token_before) else None
    t0 = time.perf_counter()
    status = "success"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        elapsed = int((time.perf_counter() - t0) * 1000)
        after = token_before() if callable(token_before) else None
        b = _to_int(before)
        a = _to_int(after)
        append_event(
            {
                "timestamp": _iso_now(),
                "event": "tool_call",
                "agent_id": agent_id,
                "session_id": sid,
                "model": "tool",
                "prompt_tokens": b if b >= 0 else -1,
                "completion_tokens": a if a >= 0 else -1,
                "total_tokens": -1,
                "tool_used": tool_name,
                "latency_ms": elapsed,
                "status": status,
                "tokens_before": b if b >= 0 else None,
                "tokens_after": a if a >= 0 else None,
            }
        )
        if b >= 0 and a >= 0:
            notify_tool_call(agent_id, sid, tool_name, a - b)
            try:
                record_risk_tool_call(agent_id, sid)
            except Exception:
                pass
