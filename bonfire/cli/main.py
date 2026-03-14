"""Bonfire CLI command router."""

from __future__ import annotations

import importlib
import sys
from typing import Callable, Dict, List

COMMAND_MODULES: Dict[str, str] = {
    "status": "bonfire.cli.commands.status",
    "watch": "bonfire.cli.commands.watch",
    "dashboard": "bonfire.cli.commands.dashboard",
    "alerts": "bonfire.cli.commands.alerts",
    "cost": "bonfire.cli.commands.cost",
    "risk": "bonfire.cli.commands.risk",
    "forecast": "bonfire.cli.commands.forecast",
    "efficiency": "bonfire.cli.commands.efficiency",
    "burnrate": "bonfire.cli.commands.burnrate",
    "runaway": "bonfire.cli.commands.runaway",
    "models": "bonfire.cli.commands.models",
    "doctor": "bonfire.cli.commands.doctor",
    "logs": "bonfire.cli.commands.logs",
}

COMMAND_HELP: Dict[str, str] = {
    "status": "overall Bonfire health summary",
    "watch": "live terminal view of Bonfire activity",
    "dashboard": "start local Bonfire dashboard",
    "alerts": "recent Bonfire alerts",
    "cost": "current cost view",
    "risk": "risk and governance view",
    "forecast": "predicted usage and cost",
    "efficiency": "model efficiency comparison",
    "burnrate": "token burn velocity",
    "runaway": "runaway detector summary",
    "models": "model routing decisions",
    "doctor": "installation and usability diagnostics",
    "logs": "recent Bonfire logs",
}


def _help() -> str:
    names = "\n".join(f"  {name:<10} {COMMAND_HELP.get(name, '')}" for name in COMMAND_MODULES)
    return (
        "Bonfire CLI v1\n"
        "Usage:\n"
        "  bonfire <command> [args]\n\n"
        "Commands:\n"
        f"{names}\n"
    )


def _load_runner(command: str) -> Callable[[List[str]], int]:
    module_name = COMMAND_MODULES[command]
    module = importlib.import_module(module_name)
    runner = getattr(module, "run", None)
    if not callable(runner):
        raise RuntimeError(f"Command module missing run(): {module_name}")
    return runner


def main(argv: List[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(_help().rstrip())
        return 1

    command = args[0].strip().lower()
    if command in {"-h", "--help", "help"}:
        print(_help().rstrip())
        return 0

    if command not in COMMAND_MODULES:
        print(f"Unknown command: {command}")
        print(_help().rstrip())
        return 2

    try:
        runner = _load_runner(command)
        return int(runner(args[1:]))
    except Exception as exc:
        print(f"Bonfire command failed: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
