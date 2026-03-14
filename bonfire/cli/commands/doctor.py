"""bonfire doctor command."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

from bonfire.cli import helpers


SYMLINK_PATH = Path("/usr/local/bin/bonfire")


def _line(name: str, state: str, detail: str = "") -> str:
    suffix = f" ({detail})" if detail else ""
    return f"{name}: {state}{suffix}"


def _check_file(path: Path) -> Tuple[bool, str]:
    if not path.exists():
        return False, "missing"
    if not os.access(path, os.R_OK):
        return False, "unreadable"
    return True, "OK"


def run(argv: List[str]) -> int:
    del argv
    checks: List[Tuple[str, str]] = []

    entrypoint = helpers.BONFIRE_ROOT / "bin" / "bonfire"
    checks.append(("CLI entrypoint", "OK" if entrypoint.exists() else "FAIL (missing)"))

    telemetry_paths = [helpers.TOKENS_PATH, helpers.HEALTH_PATH, helpers.ECONOMICS_PATH, helpers.ALERTS_PATH]
    tele_ok = True
    missing = []
    for path in telemetry_paths:
        ok, detail = _check_file(path)
        if not ok:
            tele_ok = False
            missing.append(f"{path.name}:{detail}")
    checks.append(("Telemetry logs", "OK" if tele_ok else f"WARN ({', '.join(missing)})"))

    dashboard_server = helpers.BONFIRE_ROOT / "dashboard" / "app" / "server.py"
    checks.append(("Dashboard app", "OK" if dashboard_server.exists() else "FAIL (missing)"))

    import_ok, import_msg = helpers.check_import("bonfire.dashboard.app.server")
    checks.append(("Dashboard server", import_msg if import_ok else import_msg))

    router_files = [
        helpers.BONFIRE_ROOT / "router" / "model_router.py",
        helpers.BONFIRE_ROOT / "router" / "adaptive_router.py",
    ]
    checks.append(("Router files", "OK" if all(path.exists() for path in router_files) else "FAIL (missing files)"))

    key_modules = [
        "bonfire.router.model_router",
        "bonfire.governor.token_governor",
        "bonfire.predictor.predictor",
        "bonfire.optimizer.optimizer",
    ]
    module_failures = []
    for module_name in key_modules:
        ok, msg = helpers.check_import(module_name)
        if not ok:
            module_failures.append(f"{module_name}: {msg}")
    checks.append(("Key Bonfire modules", "OK" if not module_failures else f"FAIL ({'; '.join(module_failures)})"))

    if SYMLINK_PATH.exists() or SYMLINK_PATH.is_symlink():
        target = None
        try:
            target = SYMLINK_PATH.resolve(strict=False)
        except Exception:
            target = None
        checks.append(("Global command symlink", f"OK ({target})" if target else "OK"))
    else:
        checks.append(("Global command symlink", "WARN (missing)"))

    log_ok = helpers.LOG_ROOT.exists() and os.access(helpers.LOG_ROOT, os.R_OK)
    checks.append(("Logs readable", "OK" if log_ok else "FAIL (log directory unreadable)"))

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "bonfire.dashboard.app.server", "--help"],
            cwd=str(helpers.REPO_ROOT),
            env={**os.environ, "PYTHONPATH": f"{helpers.REPO_ROOT}:{os.environ.get('PYTHONPATH', '')}"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=8,
        )
        runnable = proc.returncode == 0
    except Exception as exc:
        runnable = False
        detail = f"{type(exc).__name__}: {exc}"
    else:
        detail = ""
    checks.append(("Dashboard command runnable", "OK" if runnable else f"FAIL ({detail or 'non-zero exit'})"))

    print("Bonfire Doctor")
    for name, result in checks:
        print(f"{name}: {result}")
    return 0
