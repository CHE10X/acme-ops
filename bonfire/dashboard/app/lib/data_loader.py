#!/usr/bin/env python3
"""Dashboard-only read helpers for Bonfire artifacts."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

LOG_ROOT = Path.home() / ".openclaw" / "logs"
TOKENS_PATH = LOG_ROOT / "bonfire_tokens.jsonl"
HEALTH_PATH = LOG_ROOT / "bonfire_health.json"
ECONOMICS_PATH = LOG_ROOT / "bonfire_economics.json"
ALERTS_PATH = LOG_ROOT / "bonfire_alerts.log"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _is_dict(payload: Any) -> bool:
    return isinstance(payload, dict)


def _to_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value > 10**12:
            return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _safe_json_load(raw: str) -> Optional[dict]:
    raw = (raw or "").strip()
    if not raw or raw.startswith("#"):
        return None
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _load_json(path: Path) -> Tuple[Optional[dict], Optional[float], Optional[str], str]:
    if not path.exists():
        return None, None, "missing", str(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if _is_dict(payload):
            return payload, path.stat().st_mtime, None, str(path)
        return None, path.stat().st_mtime, "malformed", str(path)
    except Exception as exc:
        return None, None, f"read_error:{type(exc).__name__}", str(path)


def _iter_jsonl_lines(path: Path) -> Iterable[str]:
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for raw in fh:
            yield raw


def load_token_events(
    now: Optional[datetime] = None,
    lookback_hours: Optional[float] = None,
    max_lines: Optional[int] = None,
) -> Tuple[List[dict], str | None]:
    if not TOKENS_PATH.exists():
        return [], "missing"
    return list(_iter_token_events(now=now, lookback_hours=lookback_hours, max_lines=max_lines)), None


def _iter_token_events(
    now: Optional[datetime] = None,
    lookback_hours: Optional[float] = None,
    max_lines: Optional[int] = None,
) -> Iterable[dict]:
    if now is None:
        now = _now_utc()
    cutoff = now - timedelta(hours=lookback_hours) if lookback_hours else None
    count = 0
    try:
        for raw in _iter_jsonl_lines(TOKENS_PATH):
            payload = _safe_json_load(raw)
            if not payload:
                continue
            ts = _to_datetime(payload.get("timestamp")) or _to_datetime(payload.get("started_at_ms"))
            payload["parsed_ts"] = ts
            if cutoff is not None and ts is not None and ts < cutoff:
                continue
            yield payload
            count += 1
            if max_lines and count >= max_lines:
                break
    except Exception:
        return []


def _severity_for_alert(message: str) -> str:
    value = message.lower()
    if any(token in value for token in ("runaway", "terminate", "cooldown", "panic", "throttle", "rejected", "exceeded")):
        return "runaway"
    if any(token in value for token in ("reject", "blocked", "block", "budget", "quota", "error", "deny")):
        return "high"
    if any(token in value for token in ("downgrad", "predictive", "delay", "mitigat", "moving")):
        return "caution"
    return "healthy"


def _is_intervention(message: str) -> bool:
    return any(token in message.lower() for token in ("reject", "downgrad", "throttle", "cooldown", "terminate", "delay"))


def _is_token_spike(message: str) -> bool:
    return any(token in message.lower() for token in ("spike", "4x", "burst", "token", "prediction"))


def load_alert_events(
    limit: int = 250,
    now: Optional[datetime] = None,
    lookback_hours: Optional[float] = None,
) -> Tuple[List[dict], str | None]:
    if not ALERTS_PATH.exists():
        return [], "missing"
    if now is None:
        now = _now_utc()
    cutoff = now - timedelta(hours=lookback_hours) if lookback_hours else None
    events: List[dict] = []
    try:
        with ALERTS_PATH.open("r", encoding="utf-8", errors="ignore") as fh:
            if limit and limit > 0:
                lines = fh.readlines()[-limit:]
            else:
                lines = fh.readlines()
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            parts = line.split(" ", 1)
            ts = None
            message = line
            if len(parts) == 2 and re.match(r"\d{4}-\d{2}-\d{2}T", parts[0]):
                ts = _to_datetime(parts[0])
                message = parts[1]
            if cutoff is not None and ts is not None and ts < cutoff:
                continue
            sev = _severity_for_alert(message)
            match = re.search(r"\bagent=([\w.-]+)", line)
            events.append(
                {
                    "timestamp": (ts.isoformat().replace("+00:00", "Z") if ts else "unavailable"),
                    "parsed_ts": ts,
                    "raw": line,
                    "message": message,
                    "severity": sev,
                    "agent": match.group(1) if match else None,
                    "intervention": _is_intervention(message),
                    "token_spike": _is_token_spike(message),
                }
            )
        return events, None
    except Exception:
        return [], "read_error"


def load_health_snapshot() -> Tuple[dict, str | None]:
    payload, _, error, _ = _load_json(HEALTH_PATH)
    if error is not None or not _is_dict(payload):
        return {}, error
    return payload or {}, None


def load_economics_snapshot() -> Tuple[dict, str | None]:
    payload, _, error, _ = _load_json(ECONOMICS_PATH)
    if error is not None or not _is_dict(payload):
        return {}, error
    return payload or {}, None


def derive_agent_from_events(events: Iterable[dict]) -> List[str]:
    return sorted({str(event.get("agent_id", "unknown")) for event in events if event.get("agent_id")})


def load_source_status() -> Dict[str, Dict[str, Any]]:
    status = {}
    for path in (TOKENS_PATH, HEALTH_PATH, ECONOMICS_PATH, ALERTS_PATH):
        if not path.exists():
            status[path.name] = {"available": False, "status": "missing"}
            continue
        status[path.name] = {
            "available": True,
            "status": "ok",
            "mtime": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    return status


def top_models_and_models_by_agent(events: Iterable[dict]) -> Tuple[Dict[str, int], Dict[str, Dict[str, int]], Dict[str, int]]:
    by_agent_model: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_agent_total: Dict[str, int] = defaultdict(int)
    by_model: Dict[str, int] = defaultdict(int)
    for event in events:
        agent = str(event.get("agent_id", "unknown"))
        model = str(event.get("model", "unknown"))
        tokens = int(event.get("total_tokens", 0) or 0)
        by_agent_model[agent][model] += tokens
        by_agent_total[agent] += tokens
        by_model[model] += tokens
    return {a: dict(m) for a, m in by_agent_model.items()}, by_agent_total, by_model
