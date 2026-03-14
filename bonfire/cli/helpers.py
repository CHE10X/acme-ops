"""Shared helpers for Bonfire CLI commands."""

from __future__ import annotations

import importlib
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
dashboard_root = REPO_ROOT / "bonfire" / "dashboard"
BONFIRE_ROOT = Path(__file__).resolve().parents[1]
LOG_ROOT = Path.home() / ".openclaw" / "logs"
TOKENS_PATH = LOG_ROOT / "bonfire_tokens.jsonl"
HEALTH_PATH = LOG_ROOT / "bonfire_health.json"
ECONOMICS_PATH = LOG_ROOT / "bonfire_economics.json"
ALERTS_PATH = LOG_ROOT / "bonfire_alerts.log"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def fmt_int(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except Exception:
        return "unknown"


def fmt_float(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "unknown"


def fmt_usd(value: Any) -> str:
    try:
        return f"${float(value):,.6f}"
    except Exception:
        return "unknown"


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def load_transformers() -> Tuple[Optional[Any], Optional[str]]:
    try:
        module = importlib.import_module("bonfire.dashboard.app.lib.transformers")
        return module, None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def load_data_loader() -> Tuple[Optional[Any], Optional[str]]:
    try:
        module = importlib.import_module("bonfire.dashboard.app.lib.data_loader")
        return module, None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def call_transformer(name: str) -> Dict[str, Any]:
    transformers, _ = load_transformers()
    if not transformers:
        return {}
    try:
        fn = getattr(transformers, name)
    except Exception:
        return {}
    try:
        payload = fn()
    except Exception:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _parse_ts(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def recent_token_events(hours: float = 24.0, max_events: int = 2000) -> List[Dict[str, Any]]:
    data_loader, _ = load_data_loader()
    if data_loader:
        try:
            events, _ = data_loader.load_token_events(now=data_loader._now_utc(), lookback_hours=hours, max_lines=max_events)
            return [event for event in events if isinstance(event, dict)]
        except Exception:
            pass

    if not TOKENS_PATH.exists():
        return []

    cutoff = now_utc().timestamp() - (hours * 3600)
    events: List[Dict[str, Any]] = []
    try:
        with TOKENS_PATH.open("r", encoding="utf-8", errors="ignore") as fh:
            for raw in fh:
                try:
                    payload = json.loads(raw)
                except Exception:
                    continue
                if not isinstance(payload, dict):
                    continue
                ts = _parse_ts(payload.get("timestamp"))
                if ts is not None and ts.timestamp() < cutoff:
                    continue
                events.append(payload)
    except Exception:
        return []

    if max_events > 0:
        return events[-max_events:]
    return events


def recent_alert_events(hours: float = 24.0, limit: int = 200) -> List[Dict[str, Any]]:
    data_loader, _ = load_data_loader()
    if data_loader:
        try:
            events, _ = data_loader.load_alert_events(limit=limit, now=data_loader._now_utc(), lookback_hours=hours)
            return [event for event in events if isinstance(event, dict)]
        except Exception:
            pass

    if not ALERTS_PATH.exists():
        return []

    lines: List[str] = []
    try:
        with ALERTS_PATH.open("r", encoding="utf-8", errors="ignore") as fh:
            lines = [line.rstrip("\n") for line in fh if line.strip()]
    except Exception:
        return []

    if limit > 0:
        lines = lines[-limit:]
    return [{"timestamp": "unavailable", "severity": "unknown", "agent": None, "message": line} for line in lines]


def parse_agent_from_message(message: str) -> Optional[str]:
    if not isinstance(message, str):
        return None
    marker = "agent="
    idx = message.find(marker)
    if idx < 0:
        return None
    rest = message[idx + len(marker) :]
    value = rest.split(" ", 1)[0].strip()
    return value or None


def detect_dashboard_running(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.75):
            return True
    except Exception:
        return False


def launch_dashboard(host: str, port: int) -> Tuple[bool, str]:
    if detect_dashboard_running(host, port):
        return True, f"http://{host}:{port}"

    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    repo_str = str(REPO_ROOT)
    env["PYTHONPATH"] = f"{repo_str}:{existing}" if existing else repo_str

    try:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "bonfire.dashboard.app.server",
                "--host",
                str(host),
                "--port",
                str(port),
            ],
            cwd=str(dashboard_root),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except Exception as exc:
        return False, f"Dashboard failed to launch: {type(exc).__name__}: {exc}"

    for _ in range(20):
        if detect_dashboard_running(host, port):
            return True, f"http://{host}:{port}"
        if proc.poll() is not None:
            detail = ""
            try:
                stderr_out = proc.stderr.read().decode("utf-8", errors="ignore") if proc.stderr else ""
                detail = stderr_out.strip().splitlines()[-1] if stderr_out.strip() else ""
            except Exception:
                detail = ""
            if detail:
                return False, f"Dashboard failed to start: {detail}"
            return False, "Dashboard failed to start: server exited early."
        time.sleep(0.15)

    return False, "Dashboard failed to start: startup timeout."


def print_table(headers: List[Tuple[str, str]], rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return ""
    widths: List[int] = []
    for key, label in headers:
        width = len(label)
        for row in rows:
            width = max(width, len(str(row.get(key, ""))))
        widths.append(width)

    lines: List[str] = []
    head = "  ".join(label.ljust(widths[idx]) for idx, (_, label) in enumerate(headers))
    lines.append(head)
    lines.append("  ".join("-" * widths[idx] for idx in range(len(headers))))
    for row in rows:
        lines.append(
            "  ".join(str(row.get(key, "")).ljust(widths[idx]) for idx, (key, _) in enumerate(headers))
        )
    return "\n".join(lines)


def check_import(module_name: str) -> Tuple[bool, str]:
    try:
        importlib.import_module(module_name)
        return True, "OK"
    except Exception as exc:
        return False, f"FAIL ({type(exc).__name__}: {exc})"
