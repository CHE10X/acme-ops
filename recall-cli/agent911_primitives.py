"""Recall -> Agent911 primitive adapters.

Recall intentionally delegates execution to Agent911 implementations where available.
This file intentionally prefers explicit TODO behavior over silent failures when the
expected primitive is missing.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

OPENCLAW_OPS = Path.home() / ".openclaw" / "workspace" / "openclaw-ops"
PRIMITIVE_ROOT = OPENCLAW_OPS / "agent911" / "recovery" / "primitives"


@dataclass
class PrimitiveResult:
    ok: bool
    command: List[str]
    returncode: int
    stdout: str
    stderr: str


def _run(command: List[str], cwd: Path | None = None, timeout: int = 120) -> PrimitiveResult:
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            env=os.environ.copy(),
        )
        return PrimitiveResult(
            ok=proc.returncode == 0,
            command=command,
            returncode=proc.returncode,
            stdout=(proc.stdout or "").strip(),
            stderr=(proc.stderr or "").strip(),
        )
    except Exception as exc:  # pragma: no cover - defensive
        return PrimitiveResult(
            ok=False,
            command=command,
            returncode=1,
            stdout="",
            stderr=str(exc),
        )


def _missing(name: str) -> PrimitiveResult:
    return PrimitiveResult(
        ok=False,
        command=[],
        returncode=1,
        stdout="",
        stderr=(
            f"TODO: Agent911 primitive unavailable for {name}. "
            "Recall must call Agent911 API directly in production runtime."
        ),
    )


def _has_module(name: str) -> bool:
    return (PRIMITIVE_ROOT / f"{name}.py").exists()


def _import_module(name: str):
    if not _has_module(name):
        return None
    spec = importlib.util.spec_from_file_location(
        f"agent911_primitive_{name}",
        str(PRIMITIVE_ROOT / f"{name}.py"),
    )
    if not spec or not spec.loader:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def kill_subagents(agent_id: str) -> Dict[str, Any]:
    """TODO: expected interface for Recall stun. Stub if implementation is absent."""
    module = _import_module("kill_subagents")
    if module and hasattr(module, "run_kill_subagents"):
        return module.run_kill_subagents(agent_id).__dict__
    if module and hasattr(module, "kill_subagents"):
        return module.kill_subagents(agent_id).__dict__
    return _missing(f"kill_subagents(agent_id={agent_id})").__dict__


def archive_session(agent_id: str) -> Dict[str, Any]:
    """TODO: expected interface for Recall stun. Stub if implementation is absent."""
    module = _import_module("archive_session")
    if module and hasattr(module, "run_archive_session"):
        return module.run_archive_session(agent_id).__dict__
    if module and hasattr(module, "archive_session"):
        return module.archive_session(agent_id).__dict__
    return _missing(f"archive_session(agent_id={agent_id})").__dict__


def compact_memory(agent_id: str) -> Dict[str, Any]:
    """TODO: expected interface for Recall stun / reset memory flush."""
    module = _import_module("compact_memory")
    if module and hasattr(module, "run_compact_memory"):
        return module.run_compact_memory(agent_id).__dict__
    if module and hasattr(module, "compact_memory"):
        return module.compact_memory(agent_id).__dict__
    return _missing(f"compact_memory(agent_id={agent_id})").__dict__


def snapshot_system_state() -> Dict[str, Any]:
    """TODO: expected interface for reset and future snapshots. Stub if absent."""
    if PRIMITIVE_ROOT and (PRIMITIVE_ROOT / "snapshot.py").exists():
        module = _import_module("snapshot")
        if module and hasattr(module, "run_snapshot"):
            return module.run_snapshot()
    return {
        **_missing("snapshot_system_state()").__dict__,
        "data": {},
    }


def verify_gateway_readiness() -> Dict[str, Any]:
    """Reuse existing Agent911 readiness verification if available."""
    module = _import_module("verify")
    if module and hasattr(module, "run_verify"):
        result = module.run_verify()
        return {
            "ok": bool(result.get("ok", False)),
            "returncode": int(result.get("returncode", 1)),
            "stdout": str(result.get("stdout", "")),
            "stderr": str(result.get("stderr", "")),
        }
    return {
        **_missing("verify_gateway_readiness()").__dict__,
    }
