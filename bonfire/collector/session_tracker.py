#!/usr/bin/env python3
"""Session lifecycle tracking."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from hashlib import sha1
from typing import Dict, Optional

from bonfire.bonfire_logger import append_event, OPENCLAW_LOG_DIR, _iso_now

STATE_PATH = OPENCLAW_LOG_DIR / "bonfire_sessions_state.json"
DEFAULT_IDLE_SECONDS = 1800


def _read_state() -> Dict[str, dict]:
    if not STATE_PATH.exists():
        return {}
    try:
        with STATE_PATH.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
            return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_state(payload: Dict[str, dict]) -> None:
    try:
        OPENCLAW_LOG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        tmp.replace(STATE_PATH)
    except Exception:
        pass


def _gen_session_id(agent_id: str, seed_ms: Optional[int] = None) -> str:
    seed = seed_ms if seed_ms is not None else int(time.time() * 1000)
    return sha1(f"{agent_id}:{seed}".encode("utf-8")).hexdigest()[:10]


def _emit(event: str, agent_id: str, session_id: str, start_ts: float, now_ts: float, extra: Optional[dict] = None) -> None:
    duration = int((now_ts - start_ts) * 1000) if now_ts and start_ts else 0
    payload = {
        "timestamp": _iso_now(),
        "agent_id": agent_id,
        "session_id": session_id,
        "model": "session",
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "tool_used": "session_tracker",
        "latency_ms": 0,
        "status": event,
        "started_at_ms": int(start_ts * 1000),
        "session_duration": duration,
    }
    if extra:
        payload.update(extra)
    append_event(payload)


def get_or_start_session(agent_id: str, *, session_id: Optional[str] = None, now_ts: Optional[float] = None, idle_seconds: int = DEFAULT_IDLE_SECONDS) -> str:
    now_ts = float(time.time() if now_ts is None else now_ts)
    state = _read_state()
    entry = state.get(agent_id)

    if isinstance(entry, dict) and entry.get("session_id"):
        last_seen = float(entry.get("last_seen", entry.get("start_ts", now_ts)))
        if session_id and session_id != entry.get("session_id"):
            _emit("session_end", agent_id, entry.get("session_id", "unknown"), float(entry.get("start_ts", now_ts)), now_ts)
            entry = None
        if entry and now_ts - last_seen <= idle_seconds and not session_id:
            entry["last_seen"] = now_ts
            state[agent_id] = entry
            _write_state(state)
            return entry.get("session_id")
        if entry and session_id == entry.get("session_id"):
            entry["last_seen"] = now_ts
            state[agent_id] = entry
            _write_state(state)
            return session_id
        if entry and entry.get("session_id"):
            _emit("session_end", agent_id, entry.get("session_id", "unknown"), float(entry.get("start_ts", now_ts)), now_ts)

    new_session = session_id or _gen_session_id(agent_id, int(now_ts * 1000))
    state[agent_id] = {"session_id": new_session, "start_ts": now_ts, "last_seen": now_ts}
    _write_state(state)
    _emit("session_start", agent_id, new_session, now_ts, now_ts)
    return new_session


def touch_session(agent_id: str, session_id: Optional[str] = None) -> str:
    return get_or_start_session(agent_id, session_id=session_id)


def terminate_session(agent_id: str, session_id: Optional[str] = None) -> str:
    state = _read_state()
    now_ts = float(time.time())
    entry = state.get(agent_id)
    if not isinstance(entry, dict):
        sid = session_id or _gen_session_id(agent_id, int(now_ts * 1000))
        return sid
    sid = session_id or entry.get("session_id")
    start_ts = float(entry.get("start_ts", now_ts))
    if sid:
        _emit("session_end", agent_id, sid, start_ts, now_ts, {"termination": "governance"})
    state.pop(agent_id, None)
    _write_state(state)
    return str(sid)


def get_session_start(agent_id: str, session_id: Optional[str] = None) -> Optional[float]:
    entry = _read_state().get(agent_id)
    if not isinstance(entry, dict):
        return None
    if session_id and entry.get("session_id") != session_id:
        return None
    try:
        return float(entry.get("start_ts", 0.0))
    except Exception:
        return None


def get_active_sessions() -> Dict[str, dict]:
    payload = _read_state()
    now_ts = float(time.time())
    active = {}
    for agent_id, data in payload.items():
        if not (isinstance(data, dict) and data.get("session_id")):
            continue
        last_seen = float(data.get("last_seen", data.get("start_ts", now_ts)))
        if now_ts - last_seen > DEFAULT_IDLE_SECONDS:
            continue
        active[agent_id] = dict(data)
    return active
