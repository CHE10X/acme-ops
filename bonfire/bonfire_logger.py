#!/usr/bin/env python3
"""
Bonfire shared logger.

Writes append-only JSONL telemetry with local rotation:
- primary log: ~/.openclaw/logs/bonfire_tokens.jsonl
- rotate to ~/.openclaw/logs/bonfire_tokens_YYYYMMDD.jsonl when >50MB
"""

from __future__ import annotations

import json
import os
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Iterator, Optional


OPENCLAW_LOG_DIR = Path.home() / ".openclaw" / "logs"
TOKEN_LOG_PATH = OPENCLAW_LOG_DIR / "bonfire_tokens.jsonl"
ALERT_LOG_PATH = OPENCLAW_LOG_DIR / "bonfire_alerts.log"
SUMMARY_PATH = OPENCLAW_LOG_DIR / "bonfire_summary.json"
MAX_LOG_BYTES = 50 * 1024 * 1024


def _ensure_dir() -> None:
    OPENCLAW_LOG_DIR.mkdir(parents=True, exist_ok=True)

def _iso_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def _rotate_if_needed() -> None:
    if not TOKEN_LOG_PATH.exists():
        return
    if TOKEN_LOG_PATH.stat().st_size <= MAX_LOG_BYTES:
        return

    date_suffix = datetime.utcnow().strftime("%Y%m%d")
    base_name = f"bonfire_tokens_{date_suffix}.jsonl"
    rotated = OPENCLAW_LOG_DIR / base_name
    if not rotated.exists():
        try:
            TOKEN_LOG_PATH.rename(rotated)
            return
        except OSError:
            pass

    # Avoid clobbering if a same-day rotation already exists.
    index = 1
    while True:
        rotated = OPENCLAW_LOG_DIR / f"bonfire_tokens_{date_suffix}_{index}.jsonl"
        if not rotated.exists():
            break
        index += 1
    try:
        TOKEN_LOG_PATH.rename(rotated)
    except OSError:
        # Best effort: keep writing to current log if rename fails.
        pass

def append_event(event: Dict[str, object]) -> bool:
    """
    Append one telemetry event synchronously by writing directly to the log file.
    Returns True on success, False otherwise.
    """
    if not isinstance(event, dict):
        return False

    _ensure_dir()
    _rotate_if_needed()

    try:
        with TOKEN_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, separators=((",", ":"))))
            fh.write("\n")
            fh.flush() # Ensure the data is written immediately
        return True
    except Exception:
        # Telemetry must never block execution paths.
        # If writing fails, it returns False.
        return False


def iter_events(log_path: Optional[Path] = None) -> Iterator[Dict[str, object]]:
    path = log_path if log_path else TOKEN_LOG_PATH
    if not path.exists():
        return iter(())

    def _iter() -> Iterator[Dict[str, object]]:
        with path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    yield json.loads(raw)
                except Exception:
                    continue
    return _iter()


def append_alert(message: str) -> None:
    if not message:
        return
    _ensure_dir()
    line = f"{_iso_now()} {message}\n"
    try:
        with ALERT_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass


def atomic_write_json(path: Path, payload: Dict[str, object]) -> None:
    _ensure_dir()
    tmp = path.with_suffix(".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        tmp.replace(path)
    except Exception:
        # Never fail runtime on output writing issues.
        pass


def build_recent_windows(hours: int = 1) -> deque:
    now = datetime.utcnow()
    cutoff = now.timestamp() - (hours * 3600)
    recent = deque()
    for ev in iter_events():
        ts = ev.get("timestamp")
        if not isinstance(ts, str):
            continue
        try:
            parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            continue
        if parsed.timestamp() >= cutoff:
            recent.append(ev)
    return recent
