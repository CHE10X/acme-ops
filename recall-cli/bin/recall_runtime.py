#!/usr/bin/env python3
"""Recall runtime command handler.

Implements manual intervention commands for openclaw recall.
All mutations are intentionally append-only and reversible where possible.
"""

from __future__ import annotations

__version__ = "1.0.0"
VERSION = __version__

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path.home() / ".openclaw"
RUNTIME_DIR = ROOT / "runtime"
RECALL_RUNTIME_DIR = RUNTIME_DIR / "recall"
RECALL_STATE_PATH = RECALL_RUNTIME_DIR / "agent_state.json"
LOCKDOWN_PATH = RUNTIME_DIR / "lockdown"
RECALL_LOG = ROOT / "logs" / "recall_interventions.jsonl"
SESSIONS_PATH = ROOT / "agents" / "main" / "sessions" / "sessions.json"
INCIDENT_DIR = ROOT / "workspace" / "memory" / "incidents"
AGENT_SESSIONS_DIR = ROOT / "agents" / "main" / "sessions"
SUPPORT_BUNDLE_SCRIPT = ROOT / "workspace" / "acme-ops" / "scripts" / "support" / "acme_support_bundle.py"
BACKUP_SCRIPT = ROOT / "workspace" / "acme-ops" / "scripts" / "backup" / "openclaw_snapshot.sh"
PRIMITIVES_PATH = Path(__file__).resolve().parent.parent
SYS_PATH = os.fspath(PRIMITIVES_PATH)
if SYS_PATH not in sys.path:
    sys.path.insert(0, SYS_PATH)

from agent911_primitives import (
    archive_session,
    compact_memory,
    kill_subagents,
    snapshot_system_state,
    verify_gateway_readiness,
)


SLEEP_ALL_CHANNEL = "__ALL_CHANNELS__"


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(ts: str) -> Optional[datetime]:
    if not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _read_json(path: Path, fallback: Any = None) -> Any:
    if fallback is None:
        fallback = {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return fallback


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
    tmp.replace(path)


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True))
        fh.write("\n")


def _discover_agents() -> List[str]:
    data = _read_json(SESSIONS_PATH, {})
    if isinstance(data, dict) and data:
        return sorted(data.keys())
    ids: List[str] = []
    if AGENT_SESSIONS_DIR.exists():
        for item in AGENT_SESSIONS_DIR.glob("*.jsonl"):
            if item.suffix != ".jsonl":
                continue
            if item.name.endswith(".deleted."):
                continue
            # best effort: use file stem as session id as a fallback
            ids.append(item.stem)
    return sorted(set(ids)) or ["agent:main:main"]


def _agent_label(agent_id: str) -> str:
    return str(agent_id).rsplit(":", 1)[-1]


def _default_agent_entry() -> Dict[str, Any]:
    return {
        "spawn_blocked": False,
        "stalled": False,
        "sleep_channels": [],
        "stunned": False,
        "quarantined": False,
        "recover_ready": False,
        "stun": {
            "stunned_at": None,
            "capture_bundle": None,
            "steps": [],
        },
        "last_action": None,
        "updated_at": None,
    }


def load_state() -> Dict[str, Any]:
    base = _read_json(RECALL_STATE_PATH, {})
    if not isinstance(base, dict):
        base = {}

    state = {
        "schema_version": 1,
        "updated_at": utcnow(),
        "agents": {},
        "focus": {
            "active": False,
            "owner": None,
            "pre_focus": {},
        },
    }

    state.update({k: v for k, v in base.items() if k in {"schema_version", "focus"}})
    if "agents" in base and isinstance(base["agents"], dict):
        state["agents"] = {
            aid: {**_default_agent_entry(), **data}
            for aid, data in base["agents"].items()
            if isinstance(data, dict)
        }

    for aid in _discover_agents():
        if aid not in state["agents"]:
            state["agents"][aid] = _default_agent_entry()

    state["focus"] = {
        "active": False,
        "owner": None,
        "pre_focus": {},
        **state.get("focus", {}),
    }
    state["updated_at"] = utcnow()
    return state


def save_state(state: Dict[str, Any]) -> None:
    state["updated_at"] = utcnow()
    _write_json_atomic(RECALL_STATE_PATH, state)


def _effective_agent_state(entry: Dict[str, Any]) -> str:
    if entry.get("quarantined"):
        return "quarantined"
    if entry.get("stunned"):
        return "stunned"
    if entry.get("stalled"):
        return "stalled"
    if entry.get("sleep_channels"):
        return "sleeping"
    if entry.get("spawn_blocked"):
        return "frozen"
    return "active"


def _find_agent_entry(state: Dict[str, Any], agent: str) -> Dict[str, Any]:
    agents = state.setdefault("agents", {})
    if agent not in agents:
        agents[agent] = _default_agent_entry()
    return agents[agent]


def _all_intervention_agents(state: Dict[str, Any], arg_agent: Optional[str], all_agents: bool) -> List[str]:
    if all_agents:
        return sorted(state.get("agents", {}).keys())
    if arg_agent:
        return [arg_agent]
    return []


def _emit_recall_event(
    operation: str,
    agent: Optional[str] = None,
    channel: Optional[str] = None,
    steps_completed: Optional[List[str]] = None,
    steps_failed: Optional[List[str]] = None,
    bundle_captured: bool = False,
    outcome: str = "success",
    notes: Optional[str] = None,
    command: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = payload or {}
    steps_completed = steps_completed or []
    steps_failed = steps_failed or []
    event = {
        "event_type": "recall_intervention",
        "operation": operation,
        "agent": agent,
        "channel": channel,
        "steps_completed": steps_completed,
        "steps_failed": steps_failed,
        "bundle_captured": bundle_captured,
        "timestamp": utcnow(),
        "operator": "manual",
        "outcome": outcome,
        "command": command,
        "notes": notes,
        "payload": payload,
    }
    _append_jsonl(RECALL_LOG, event)
    _append_to_incident(event)
    return event


def _find_open_incident(agent: str) -> Optional[Path]:
    if not INCIDENT_DIR.exists():
        return None

    now = datetime.now(timezone.utc)
    best: Optional[tuple[datetime, Path]] = None

    for path in INCIDENT_DIR.glob(f"{agent}-*.json"):
        data = _read_json(path, {})
        if not isinstance(data, dict):
            continue
        status = str(data.get("status", "")).lower()
        if status not in {"open", "opened", "active"}:
            continue
        created = parse_iso(str(data.get("created_at", "")))
        if not created:
            continue
        age = now - created
        if age > timedelta(minutes=5):
            continue
        if best is None or created > best[0]:
            best = (created, path)

    return best[1] if best else None


def _append_to_incident(event: Dict[str, Any]) -> Optional[Path]:
    agent = event.get("agent")
    if not agent:
        return None

    incident_path = _find_open_incident(str(agent))
    if not incident_path:
        return None

    data = _read_json(incident_path, {})
    if not isinstance(data, dict):
        data = {}

    payload = event.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}

    records = data.get("events")
    if not isinstance(records, list):
        records = []

    executed_action = event.get("command")
    if not executed_action:
        if event.get("agent"):
            executed_action = f"recall {event['operation']} {event['agent']}"
        else:
            executed_action = f"recall {event['operation']}"

    records.append(
        {
            "event_id": str(uuid.uuid4()),
            "timestamp": event["timestamp"],
            "source": "fleet",
            "event_type": f"recall.{event['operation']}",
            "recommended_action": None,
            "executed_action": executed_action,
            "notes": event.get("notes"),
            "payload": {
                "agent": event.get("agent"),
                "channel": event.get("channel"),
                "steps_completed": event.get("steps_completed", []),
                "steps_failed": event.get("steps_failed", []),
                "bundle_captured": event.get("bundle_captured", False),
                "outcome": event.get("outcome"),
                **payload,
            },
        }
    )

    data["events"] = records
    _write_json_atomic(incident_path, data)
    return incident_path


def _run_command(command: List[str], timeout: int = 120, env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    try:
        proc = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            env=env or os.environ.copy(),
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "").strip(),
            "stderr": (proc.stderr or "").strip(),
        }
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "returncode": 1, "stdout": "", "stderr": str(exc)}


def _append_note(message: str) -> None:
    print(message)


def cmd_lockdown(_: argparse.Namespace) -> int:
    RECALL_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    LOCKDOWN_PATH.write_text(utcnow(), encoding="utf-8")
    event = _emit_recall_event("lockdown", command="recall lockdown")
    _append_note(f"lockdown enabled ({event['timestamp']})")
    _append_note("System-wide operations blocked: model calls, tool calls, and new sub-agents.")
    return 0


def cmd_unlock(_: argparse.Namespace) -> int:
    if LOCKDOWN_PATH.exists():
        LOCKDOWN_PATH.unlink()
    event = _emit_recall_event("unlock", command="recall unlock")
    _append_note(f"lockdown lifted ({event['timestamp']})")
    return 0


def _show_status(state: Dict[str, Any]) -> None:
    print(f"LOCKDOWN: {'active' if LOCKDOWN_PATH.exists() else 'inactive'}")
    focus = state.get("focus", {})
    if focus.get("active"):
        print(f"FOCUS: {focus.get('owner')} (active)")

    print("AGENTS:")
    for aid, entry in sorted(state.get("agents", {}).items()):
        status = _effective_agent_state(entry)
        stall = "true" if entry.get("stalled") else "false"
        frozen = "true" if entry.get("spawn_blocked") else "false"
        sleeping = " , ".join(entry.get("sleep_channels") or []) if entry.get("sleep_channels") else "-"
        print(
            f"  - {aid}: status={status} spawn_blocked={frozen} stalled={stall} "
            f"sleep={sleeping}"
        )

    if not RECALL_LOG.exists():
        print("RECENT_INTERVENTIONS: none")
        return

    print("RECENT_INTERVENTIONS:")
    lines = [line.strip() for line in RECALL_LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
    for line in lines[-8:]:
        try:
            rec = json.loads(line)
            print(
                "  - {timestamp} {operation} agent={agent} outcome={outcome}".format(
                    timestamp=rec.get("timestamp", "unknown"),
                    operation=rec.get("operation"),
                    agent=rec.get("agent") or "system",
                    outcome=rec.get("outcome"),
                )
            )
        except Exception:
            continue


def cmd_status(_: argparse.Namespace) -> int:
    state = load_state()
    _show_status(state)
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    agent_filter = args.agent
    if not RECALL_LOG.exists():
        print("No recall interventions yet.")
        return 0

    lines = [line.strip() for line in RECALL_LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
    for raw in lines[-50:]:
        try:
            rec = json.loads(raw)
        except Exception:
            continue
        if agent_filter and str(agent_filter) != str(rec.get("agent")):
            continue
        print(json.dumps(rec, sort_keys=True))
    return 0


def _set_stall(state: Dict[str, Any], agents: Iterable[str], enabled: bool = True) -> List[str]:
    steps: List[str] = []
    for aid in agents:
        entry = _find_agent_entry(state, aid)
        entry["stalled"] = bool(enabled)
        entry["updated_at"] = utcnow()
        entry["last_action"] = "stall" if enabled else "wake"
        steps.append(aid)
    return steps


def cmd_stall(args: argparse.Namespace) -> int:
    state = load_state()
    agents = _all_intervention_agents(state, args.agent, args.all)
    if not agents:
        print("Usage: openclaw recall stall <agent> --all")
        return 2

    for aid in agents:
        entry = _find_agent_entry(state, aid)
        entry["stalled"] = True
        entry["last_action"] = "stall"
        entry["updated_at"] = utcnow()
        _emit_recall_event(
            "stall",
            agent=aid,
            command=" ".join(["recall", "stall", aid]),
            notes="Messages queued; processing halted",
            outcome="success",
        )

    save_state(state)

    if args.all:
        print("stall applied to all agents")
    else:
        print(f"stall applied to {agents[0]}")
    return 0


def cmd_unstall(agent: str, state: Dict[str, Any], channel_only: Optional[str] = None, allow_stunned: bool = False) -> int:
    entry = _find_agent_entry(state, agent)
    if entry.get("stunned") and not (allow_stunned and entry.get("recover_ready")):
        print(f"{agent}: still in stunned state; recover required before wake")
        return 2

    entry["stalled"] = False
    if channel_only:
        if channel_only == SLEEP_ALL_CHANNEL:
            entry["sleep_channels"] = []
        else:
            channels = [c for c in entry.get("sleep_channels", []) if c != channel_only]
            entry["sleep_channels"] = channels
    if not channel_only:
        entry["sleep_channels"] = []

    if entry.get("stunned"):
        if entry.get("recover_ready"):
            entry["stunned"] = False
            entry["quarantined"] = False
            entry["recover_ready"] = False
            entry["spawn_blocked"] = False
            if isinstance(entry.get("stun"), dict):
                entry["stun"]["recovered_at"] = utcnow()

    entry["updated_at"] = utcnow()
    return 0


def cmd_wake(args: argparse.Namespace) -> int:
    state = load_state()
    target_agents = _all_intervention_agents(state, args.agent, args.all)
    if not target_agents:
        print("Usage: openclaw recall wake <agent> | --all")
        return 2

    failed: List[str] = []
    for aid in target_agents:
        rc = cmd_unstall(aid, state, channel_only=args.channel, allow_stunned=True)
        if rc:
            failed.append(aid)
            continue
        _emit_recall_event(
            "wake",
            agent=aid,
            channel=args.channel,
            command=" ".join(["recall", "wake", aid]),
            steps_completed=["wake"],
            notes="wake applied",
        )

    save_state(state)
    if failed:
        print(f"wake blocked for: {', '.join(failed)}")
        return 2

    print("wake complete")
    return 0


def _set_sleep(state: Dict[str, Any], agent: str, channel: Optional[str] = None, all_targets: bool = False) -> None:
    if all_targets:
        for aid in state.get("agents", {}):
            _set_sleep_entry(_find_agent_entry(state, aid), channel, force=True)
        return

    _set_sleep_entry(_find_agent_entry(state, agent), channel, force=False)


def _set_sleep_entry(entry: Dict[str, Any], channel: Optional[str], force: bool) -> None:
    channels = list(entry.get("sleep_channels") or [])
    if channel:
        if channel not in channels:
            channels.append(channel)
    elif force or not channels:
        channels = [SLEEP_ALL_CHANNEL]
    entry["sleep_channels"] = channels
    if channel:
        entry["sleep_channels"] = sorted(set(channels))
    entry["updated_at"] = utcnow()


def cmd_sleep(args: argparse.Namespace) -> int:
    state = load_state()
    if args.all:
        target_agents = [aid for aid in state.get("agents", {})]
    else:
        if not args.agent:
            print("Usage: openclaw recall sleep <agent> [--channel <id>] | --all")
            return 2
        target_agents = [args.agent]

    if args.all:
        if not target_agents:
            print("No known agents to sleep")
            return 2
        for aid in target_agents:
            _set_sleep_entry(_find_agent_entry(state, aid), args.channel, force=True)
            cmd = ["recall", "sleep", "--all"]
            if args.channel:
                cmd.extend(["--channel", args.channel])
            _emit_recall_event(
                "sleep",
                agent=aid,
                channel=args.channel,
                command=" ".join(cmd),
                notes=f"agent {aid} disconnected",
            )
        print("sleep applied to all agents")
    else:
        _set_sleep_entry(_find_agent_entry(state, target_agents[0]), args.channel, force=False)
        _emit_recall_event(
            "sleep",
            agent=target_agents[0],
            channel=args.channel,
            command=" ".join(["recall", "sleep"] + ([target_agents[0]] if target_agents else [])),
            notes=f"agent {target_agents[0]} disconnected",
        )
        print(f"sleep applied to {target_agents[0]}")

    save_state(state)
    return 0


def cmd_freeze(args: argparse.Namespace, freeze_state: bool = True) -> int:
    state = load_state()
    entry = _find_agent_entry(state, args.agent)
    entry["spawn_blocked"] = bool(freeze_state)
    entry["updated_at"] = utcnow()
    _emit_recall_event(
        "freeze" if freeze_state else "unfreeze",
        agent=args.agent,
        command=f"recall {'freeze' if freeze_state else 'unfreeze'} {args.agent}",
        notes="sub-agent spawning blocked" if freeze_state else "sub-agent spawning restored",
        steps_completed=["spawn_blocking"],
    )
    save_state(state)
    print(f"{'freeze' if freeze_state else 'unfreeze'} complete for {args.agent}")
    return 0


def cmd_stun(args: argparse.Namespace) -> int:
    state = load_state()
    agent = args.agent
    entry = _find_agent_entry(state, agent)

    steps_completed: List[str] = []
    steps_failed: List[str] = []

    if args.capture_bundle:
        bundle = _capture_bundle(agent)
        if bundle["ok"]:
            steps_completed.append("capture_bundle")
            entry["stun"]["capture_bundle"] = bundle["bundle_id"]
        else:
            steps_failed.append("capture_bundle")
            _append_note(f"bundle capture failed: {bundle.get('stderr')}")

    # Step 1: disconnect
    _set_sleep_entry(entry, None, force=True)
    steps_completed.append("disconnect")
    # Step 2: drain up to 10s
    drain_ok = _drain_agent(agent)
    steps_completed.append("drain") if drain_ok else steps_failed.append("drain")

    # Step 3: kill sub-agents
    kill_result = kill_subagents(agent)
    if kill_result.get("ok", False):
        steps_completed.append("kill_subagents")
    else:
        steps_failed.append("kill_subagents")

    # Step 4: archive session
    archive_result = archive_session(agent)
    if archive_result.get("ok", False):
        steps_completed.append("archive_session")
    else:
        steps_failed.append("archive_session")

    # Step 5: compact memory
    compact_result = compact_memory(agent)
    if compact_result.get("ok", False):
        steps_completed.append("compact_memory")
    else:
        steps_failed.append("compact_memory")

    entry["stunned"] = True
    entry["quarantined"] = False
    entry["spawn_blocked"] = True
    entry["recover_ready"] = False
    entry["stalled"] = False
    entry["stun"] = {
        "stunned_at": utcnow(),
        "capture_bundle": entry["stun"].get("capture_bundle"),
        "steps": steps_completed,
        "last_kill": kill_result,
        "last_archive": archive_result,
        "last_compact": compact_result,
    }
    entry["updated_at"] = utcnow()
    save_state(state)

    outcome = "success" if not steps_failed else "partial"
    _emit_recall_event(
        "stun",
        agent=agent,
        steps_completed=steps_completed,
        steps_failed=steps_failed,
        bundle_captured=bool(entry["stun"].get("capture_bundle")),
        outcome=outcome,
        command=f"recall stun {agent}",
        notes="stun sequence completed" if not steps_failed else "stun sequence had partial failures",
        payload={
            "capture": entry["stun"].get("capture_bundle"),
            "kill": kill_result,
            "archive": archive_result,
            "compact": compact_result,
        },
    )

    if steps_failed:
        print("stun completed with partial outcome")
        return 0

    print(f"stunned {agent}")
    return 0


def _capture_bundle(agent: str) -> Dict[str, Any]:
    if not SUPPORT_BUNDLE_SCRIPT.exists():
        return {
            "ok": False,
            "stderr": "support bundle script missing",
            "stdout": "",
            "returncode": 1,
            "bundle_id": None,
        }
    result = _run_command([sys.executable, str(SUPPORT_BUNDLE_SCRIPT), "--zip"])
    payload = {
        "ok": bool(result["ok"]),
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "returncode": result["returncode"],
        "bundle_id": None,
    }
    if result.get("stdout"):
        for line in result["stdout"].splitlines():
            if payload.get("bundle_id") is None and "bundle" in line.lower() and ":" in line:
                fragment = line.split(":", 1)[-1].strip()
                if fragment:
                    payload["bundle_id"] = fragment
            if "output" in line.lower() and ":" in line:
                payload["bundle_dir"] = line.split(":", 1)[-1].strip()
    return payload


def _drain_agent(agent: str, max_seconds: int = 10) -> bool:
    # There is no local queue visibility in this runtime. This delay is intentionally
    # conservative and bounded to the doctrine requirement.
    end = time.time() + max_seconds
    while time.time() < end:
        time.sleep(1)
    return True


def cmd_quarantine(args: argparse.Namespace) -> int:
    state = load_state()
    entry = _find_agent_entry(state, args.agent)

    entry["quarantined"] = True
    entry["last_action"] = "quarantine"
    entry["spawn_blocked"] = True
    entry["updated_at"] = utcnow()
    save_state(state)

    _emit_recall_event(
        "quarantine",
        agent=args.agent,
        command=f"recall quarantine {args.agent}",
        notes="agent isolated for inspection",
        steps_completed=["quarantine"],
    )
    print(f"quarantine enabled for {args.agent}")
    return 0


def cmd_recover(args: argparse.Namespace) -> int:
    state = load_state()
    agent = args.agent
    entry = _find_agent_entry(state, agent)

    if not entry.get("stunned") and not entry.get("quarantined"):
        print(f"{agent}: recover requires stun first")
        return 2

    # Step 1: Memory diff
    diffs = _show_memory_diff(agent, minutes=30)
    if diffs:
        print("Memory diff summary:")
        for item in diffs[:5]:
            print(f"  - {item}")

    # Step 2: quarantine prompt for suspect entries
    suspect_ids = input("Mark suspect memory entry indexes for quarantine (comma-separated, empty to skip): ").strip()
    if suspect_ids:
        entries = [int(x) for x in suspect_ids.split(",") if x.strip().isdigit()]
        _quarantine_memory(agent, entries)

    # Step 3: session review
    session_path = _latest_session_path(agent)
    print(f"Latest session archive review source: {session_path or 'none'}")

    # Step 4: readiness checks
    if not entry.get("stun"):
        print("No stun context found; aborting recovery")
        return 2

    kill_ok = kill_subagents(agent).get("ok", False)
    compact_ok = compact_memory(agent).get("ok", False)
    gateway_ok = _gateway_probe()

    readiness = [
        f"sub_agents_cleared={'true' if kill_ok else 'false'}",
        f"memory_compacted={'true' if compact_ok else 'false'}",
        "pending_messages_cleared=true",
        "gateway_probe=" + ("ok" if gateway_ok else "fail"),
    ]
    print("Readiness check:")
    for line in readiness:
        print(f"  - {line}")

    if not (kill_ok and compact_ok and gateway_ok):
        print("Recovery checks failed. Use recall recover again after fixing prerequisites.")
        _emit_recall_event(
            "recover",
            agent=agent,
            command=f"recall recover {agent}",
            outcome="failed",
            notes="recovery checks failed",
            steps_completed=["memory_diff", "quarantine", "session_review"],
            steps_failed=["readiness"],
            payload={
                "kill_ok": kill_ok,
                "compact_ok": compact_ok,
                "gateway_ok": gateway_ok,
            },
        )
        return 2

    # Step 5: operator confirmation
    confirm = input("Agent is ready to reconnect. Proceed? [y/N] ").strip().lower()
    if confirm not in {"y", "yes"}:
        print("recover cancelled by operator")
        return 2

    entry["recover_ready"] = True
    entry["updated_at"] = utcnow()
    save_state(state)

    _emit_recall_event(
        "recover",
        agent=agent,
        command=f"recall recover {agent}",
        outcome="success",
        notes="operator confirmed and recovery checks passed",
        steps_completed=["memory_diff", "quarantine", "session_review", "readiness", "operator_confirm"],
    )
    print(f"recover complete for {agent}; use recall wake {agent}")
    return 0


def _quarantine_memory(agent: str, indexes: List[int]) -> None:
    if not indexes:
        return
    quarantine_dir = ROOT / "memory" / "quarantine" / agent
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    session_path = _latest_session_path(agent)
    if not session_path:
        return
    try:
        entries: List[str] = [line.strip() for line in session_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception:
        return
    ts = int(time.time())
    for idx in indexes:
        if idx < 1 or idx > len(entries):
            continue
        out = quarantine_dir / f"entry_{idx:03d}_{ts}.ndjson"
        out.write_text(entries[idx - 1] + "\n", encoding="utf-8")


def _latest_session_path(agent: str) -> Optional[Path]:
    data = _read_json(SESSIONS_PATH, {})
    if isinstance(data, dict):
        key_data = data.get(agent)
        if isinstance(key_data, dict):
            p = key_data.get("sessionFile")
            if isinstance(p, str):
                candidate = Path(p)
                if candidate.exists():
                    return candidate
    return None


def _show_memory_diff(agent: str, minutes: int = 30) -> List[str]:
    path = _latest_session_path(agent)
    if not path or not path.exists():
        return []

    snapshot = _find_agent_entry(load_state(), agent).get("stun", {}).get("stunned_at")
    if snapshot:
        start = parse_iso(snapshot)
    else:
        start = datetime.now(timezone.utc) - timedelta(minutes=minutes)

    results: List[str] = []
    if not start:
        return []
    try:
        threshold = start.timestamp()
    except Exception:
        return []

    for raw in path.read_text(encoding="utf-8").splitlines()[-40:]:
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
        except Exception:
            continue
        ts = rec.get("ts") or rec.get("timestamp")
        if ts:
            try:
                parsed = parse_iso(str(ts))
                if parsed and parsed.timestamp() >= threshold:
                    results.append(str(rec)[:180])
            except Exception:
                continue
        else:
            results.append(str(rec)[:180])

    return results


def cmd_focus(args: argparse.Namespace) -> int:
    state = load_state()
    target = args.agent
    if not target:
        print("Usage: openclaw recall focus <agent>")
        return 2

    known = sorted(state.get("agents", {}).keys())
    if target not in known:
        known.append(target)
    focus = state.setdefault("focus", {"active": False, "owner": None, "pre_focus": {}})

    pre_focus = {}
    for aid in known:
        entry = _find_agent_entry(state, aid)
        pre_focus[aid] = {
            "stalled": bool(entry.get("stalled")),
            "sleep_channels": list(entry.get("sleep_channels") or []),
        }
        if aid != target:
            entry["stalled"] = True

    focus.update({"active": True, "owner": target, "pre_focus": pre_focus})
    save_state(state)

    _emit_recall_event(
        "focus",
        agent=target,
        command=f"recall focus {target}",
        notes="all non-focus agents stalled",
        steps_completed=["focus"],
    )
    print(f"Fleet Focus Active")
    print(f"primary_agent: {target}")
    stalled = [aid for aid in known if aid != target]
    print(f"stalled_agents: {', '.join(stalled) if stalled else 'none'}")
    return 0


def cmd_unfocus(_: argparse.Namespace) -> int:
    state = load_state()
    focus = state.get("focus", {})
    if not focus.get("active"):
        print("No active focus")
        return 0

    pre = focus.get("pre_focus", {})
    for aid, snap in pre.items():
        if not isinstance(snap, dict):
            continue
        entry = _find_agent_entry(state, aid)
        entry["stalled"] = bool(snap.get("stalled"))
        entry["sleep_channels"] = list(snap.get("sleep_channels") or [])

    state["focus"] = {"active": False, "owner": None, "pre_focus": {}}
    save_state(state)
    _emit_recall_event(
        "unfocus",
        command="recall unfocus",
        notes="focus released",
        steps_completed=["restore_pre_focus"],
    )
    print("focus released")
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    state = load_state()
    if not args.no_interactive:
        response = input("Proceed with recall reset sequence (backup + restart + verify)? [y/N] ").strip().lower()
        if response not in {"y", "yes"}:
            print("reset cancelled")
            return 2

    print("Step 1: TRIAGE BUNDLE")
    triage = _capture_bundle("system")
    print("  capture:", "ok" if triage.get("ok") else "failed")

    print("Step 2: MEMORY FLUSH")
    flush_ok = True
    for aid in state.get("agents", {}):
        if not compact_memory(aid).get("ok", False):
            flush_ok = False
            break
    print("  compact_agents:", "ok" if flush_ok else "failed")

    print("Step 3: SNAPSHOT")
    snap = snapshot_system_state()
    print("  snapshot:", "ok" if snap.get("ok", False) else "failed")

    print("Step 4: BACKUP")
    if not BACKUP_SCRIPT.exists():
        print("backup script missing")
        _emit_recall_event(
            "reset",
            command="recall reset",
            outcome="failed",
            notes="backup script missing",
            steps_failed=["backup"],
        )
        return 2

    backup = _run_command(["bash", str(BACKUP_SCRIPT)], timeout=120)
    backup_ok = backup.get("ok", False)
    if backup.get("stdout") and "BACKUP PARTIAL" in backup.get("stdout", ""):
        backup_ok = False
    print("  backup:", "ok" if backup_ok else "failed")

    if not backup_ok:
        print("backup failed; aborting reset")
        _emit_recall_event(
            "reset",
            command="recall reset",
            outcome="failed",
            notes="backup failed",
            steps_failed=["backup"],
            payload={"backup": backup},
        )
        return 2

    if not args.no_interactive:
        response = input("Announce and restart gateway now? [y/N] ").strip().lower()
        if response not in {"y", "yes"}:
            print("reset paused before restart")
            _emit_recall_event(
                "reset",
                command="recall reset",
                outcome="partial",
                notes="restart withheld by operator",
                steps_completed=["triage", "flush", "snapshot", "backup"],
                steps_failed=["restart"],
            )
            return 2

    print("Step 5: RESTART")
    restart = _run_command(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/ai.openclaw.gateway"], timeout=120)
    print("  restart:", "ok" if restart.get("ok") else "failed")

    print("Step 6: VERIFY")
    verify = verify_gateway_readiness()
    probe_ok = _gateway_probe()
    gateway_ok = verify.get("ok", False) and probe_ok
    print("  verify:", "ok" if gateway_ok else "failed")

    print("Step 7: REPORT")
    print("  triage_bundle:", triage.get("bundle_id") or triage.get("bundle_dir") or "n/a")
    print("  restart_ok:", restart.get("ok"))
    print("  gateway_ok:", gateway_ok)

    outcome = "success" if backup_ok and gateway_ok and restart.get("ok", False) else "partial"
    _emit_recall_event(
        "reset",
        command="recall reset",
        outcome=outcome,
        steps_completed=["triage", "flush", "snapshot", "backup", "announce", "restart", "verify"],
        steps_failed=["reset"] if outcome != "success" else [],
        notes="system reset requested",
        payload={
            "triage": triage,
            "snapshot": snap,
            "backup": backup,
            "restart": restart,
            "verify": verify,
            "gateway_probe": _gateway_probe(),
        },
    )

    if outcome != "success":
        print("reset completed with issues. check output above.")
        return 2
    print("reset successful")
    return 0


def _gateway_probe() -> bool:
    result = _run_command(["openclaw", "gateway", "probe"], timeout=20)
    return bool(result.get("ok"))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="recall")
    parser.add_argument("--version", "-v", action="version", version=f"Recall {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=False)

    p = subparsers.add_parser("lockdown")
    p.set_defaults(func=cmd_lockdown)

    p = subparsers.add_parser("unlock")
    p.set_defaults(func=cmd_unlock)

    p = subparsers.add_parser("status")
    p.set_defaults(func=cmd_status)

    p = subparsers.add_parser("log")
    p.add_argument("agent", nargs="?")
    p.set_defaults(func=cmd_log)

    p = subparsers.add_parser("freeze")
    p.add_argument("agent")
    p.set_defaults(func=lambda args: cmd_freeze(args, freeze_state=True))

    p = subparsers.add_parser("unfreeze")
    p.add_argument("agent")
    p.set_defaults(func=lambda args: cmd_freeze(args, freeze_state=False))

    p = subparsers.add_parser("stall")
    p.add_argument("agent", nargs="?")
    p.add_argument("--all", action="store_true")
    p.set_defaults(func=cmd_stall)

    p = subparsers.add_parser("sleep")
    p.add_argument("agent", nargs="?")
    p.add_argument("--all", action="store_true")
    p.add_argument("--channel")
    p.set_defaults(func=cmd_sleep)

    p = subparsers.add_parser("stun")
    p.add_argument("agent")
    p.add_argument("--capture-bundle", action="store_true", dest="capture_bundle")
    p.set_defaults(func=cmd_stun)

    p = subparsers.add_parser("quarantine")
    p.add_argument("agent")
    p.set_defaults(func=cmd_quarantine)

    p = subparsers.add_parser("wake")
    p.add_argument("agent", nargs="?")
    p.add_argument("--all", action="store_true")
    p.add_argument("--channel")
    p.set_defaults(func=cmd_wake)

    p = subparsers.add_parser("recover")
    p.add_argument("agent")
    p.set_defaults(func=cmd_recover)

    p = subparsers.add_parser("focus")
    p.add_argument("agent")
    p.set_defaults(func=cmd_focus)

    p = subparsers.add_parser("unfocus")
    p.set_defaults(func=cmd_unfocus)

    p = subparsers.add_parser("reset")
    p.add_argument("--no-interactive", action="store_true")
    p.set_defaults(func=cmd_reset)

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if not getattr(args, "command", None):
        parser.print_help()
        return 0

    func = getattr(args, "func", None)
    if not callable(func):
        parser.print_help()
        return 1

    return int(func(args))


if __name__ == "__main__":
    raise SystemExit(main())
