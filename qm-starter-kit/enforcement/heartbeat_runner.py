#!/usr/bin/env python3
"""
QM Heartbeat Runner — implements HEARTBEAT_PROTOCOL.md
Called by QM's cron job on every heartbeat tick.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

WORKSPACE = Path("/Users/AGENT/.openclaw/workspace")
MISSIONS_DIR = Path.home() / ".openclaw" / "quartermaster" / "missions"
CONFIG_PATH = WORKSPACE / "quartermaster_v1" / "qm_config.json"
LOG_PATH = WORKSPACE / "quartermaster_v1" / "logs" / "enforcement_log.jsonl"

AGENT_INBOX = {
    "hendrik": WORKSPACE / "INBOX.md",
    "heike": WORKSPACE / "heike" / "INBOX.md",
    "soren": WORKSPACE / "soren" / "INBOX.md",
    "gerrit": WORKSPACE / "gerrit" / "INBOX.md",
    "gwen": WORKSPACE / "gwen" / "INBOX.md",
}

AGENT_WORKSPACE = {
    "hendrik": WORKSPACE,
    "heike": WORKSPACE / "heike",
    "soren": WORKSPACE / "soren",
    "gerrit": WORKSPACE / "gerrit",
    "gwen": WORKSPACE / "gwen",
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {"stale_task_hours": 4, "alert_chip_hours": 6,
            "nudge_cooldown_hours": 4, "max_nudges_per_task": 3}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def hours_since(ts_str: str) -> float:
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return (now_utc() - ts).total_seconds() / 3600
    except Exception:
        return 0.0


def deduplicate_check(inbox_path: Path, nudge: str, cooldown_hours: float) -> bool:
    """Return True if safe to write (no duplicate within cooldown)."""
    if not inbox_path.exists():
        return True
    lines = inbox_path.read_text().splitlines()[-50:]
    cutoff = now_utc() - timedelta(hours=cooldown_hours)
    # Simple check: if nudge text appears in recent lines, skip
    nudge_core = nudge[:80].strip()
    for line in lines:
        if nudge_core in line:
            return False
    return True


def write_inbox(agent: str, message: str, config: dict) -> bool:
    inbox = AGENT_INBOX.get(agent)
    if not inbox:
        return False
    if not deduplicate_check(inbox, message, config.get("nudge_cooldown_hours", 4)):
        log_action("nudge_skipped_duplicate", agent=agent, message=message[:80])
        return False
    inbox.parent.mkdir(parents=True, exist_ok=True)
    with inbox.open("a") as f:
        ts = now_utc().strftime("%Y-%m-%d %H:%M UTC")
        f.write(f"\n## [UNREAD] QM Heartbeat — {ts}\n\n{message}\n\n— Quartermaster\n")
    log_action("nudge_written", agent=agent, message=message[:80])
    return True


def log_action(action: str, **kwargs) -> None:
    import hashlib
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": now_utc().isoformat(), "action": action, **kwargs}
    content = json.dumps(entry)
    entry["sha256"] = hashlib.sha256(content.encode()).hexdigest()
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def load_missions() -> list[dict]:
    missions = []
    if not MISSIONS_DIR.exists():
        return missions
    for f in MISSIONS_DIR.glob("*.json"):
        try:
            missions.append(json.loads(f.read_text()))
        except Exception:
            pass
    return missions


def scan_missions(config: dict) -> list[str]:
    """Step 2: scan mission files, return alert messages for Chip."""
    chip_alerts = []
    missions = load_missions()
    stale_h = config.get("stale_task_hours", 4)
    alert_h = config.get("alert_chip_hours", 6)

    for mission in missions:
        if mission.get("status") != "active":
            continue
        tasks = mission.get("tasks", [])
        completed_ids = {t["task_id"] for t in tasks if t.get("status") == "complete"}

        for task in tasks:
            tid = task.get("task_id", "?")
            status = task.get("status", "")
            agent = task.get("assigned_agent", "")
            updated = task.get("updated_at", "")
            deps = task.get("dependencies", [])

            if status == "running" and updated:
                hrs = hours_since(updated)
                if hrs >= alert_h:
                    chip_alerts.append(
                        f"Task {tid} in {mission.get('name','?')} stalled {hrs:.1f}hrs — owner: {agent}"
                    )
                elif hrs >= stale_h:
                    write_inbox(agent,
                        f"Task `{tid}` has been running for {hrs:.1f} hours without an update. "
                        f"Please update status or flag a blocker.",
                        config)

            elif status == "needs_review":
                reviewer = task.get("reviewer", agent)
                write_inbox(reviewer,
                    f"Task `{tid}` from {agent} is ready for your review.",
                    config)

            elif status == "blocked" and all(d in completed_ids for d in deps) and deps:
                write_inbox(agent,
                    f"Task `{tid}` is now unblocked — all dependencies are complete. Ready to start.",
                    config)
                task["status"] = "pending"
                task["updated_at"] = now_utc().isoformat()

    return chip_alerts


PROJECT_REQUEST_RE = re.compile(
    r"QM_PROJECT_REQUEST:\s*\n"
    r"\s+name:\s*[\"']?(.+?)[\"']?\s*\n"
    r"\s+description:\s*[\"']?(.+?)[\"']?\s*\n"
    r"\s+owner:\s*(\w+)",
    re.MULTILINE
)


def process_project_requests(config: dict) -> None:
    """Step 3: scan agent INBOX files for QM_PROJECT_REQUEST blocks."""
    projects_path = WORKSPACE / "archer" / "PROJECTS.md"
    if not projects_path.exists():
        return

    # Find next project number
    content = projects_path.read_text()
    existing = re.findall(r"PROJ-2026-(\d+)", content)
    next_num = max((int(n) for n in existing), default=0) + 1

    for agent, inbox_path in AGENT_INBOX.items():
        if not inbox_path.exists():
            continue
        inbox_text = inbox_path.read_text()
        for match in PROJECT_REQUEST_RE.finditer(inbox_text):
            name = match.group(1).strip()
            desc = match.group(2).strip()
            owner = match.group(3).strip()
            code = f"PROJ-2026-{next_num:03d}"
            alias = name.lower().replace(" ", "-")[:20]

            # Add to PROJECTS.md
            new_row = f"| {code} | `{alias}` | {name} | {now_utc().strftime('%Y-%m-%d')} | Active | {desc} |\n"
            projects_path.write_text(
                content.replace(
                    "## Active Projects\n\n| Code |",
                    f"## Active Projects\n\n| Code |"
                )
            )
            # Simple append before first closed project or at end of active table
            lines = projects_path.read_text().splitlines()
            insert_after = next(
                (i for i, l in enumerate(lines) if "✅ Closed" in l or "## Closed" in l),
                len(lines) - 1
            )
            lines.insert(insert_after, new_row.rstrip())
            projects_path.write_text("\n".join(lines) + "\n")

            write_inbox(agent,
                f"Project request accepted. Code: `{code}` ({name}). You can now reference this project in your work.",
                config)
            log_action("project_request_accepted", agent=agent, project=code, name=name)
            next_num += 1

            # Remove the processed request from inbox
            updated = inbox_text.replace(match.group(0), f"<!-- QM: project {code} registered -->")
            inbox_path.write_text(updated)


def run() -> None:
    config = load_config()
    log_action("heartbeat_start")

    # Step 2: scan missions
    chip_alerts = scan_missions(config)

    # Step 3: process project requests
    process_project_requests(config)

    # Step 4: TEAM_BOARD render — placeholder (full render in separate task)
    log_action("team_board_render_skipped", reason="renderer not yet built")

    # Step 5: project gate check — logged via enforcement module when agents report work
    # (gate fires on task completion reports, not heartbeat sweep)

    if chip_alerts:
        for alert in chip_alerts:
            print(f"[ALERT FOR CHIP] {alert}")
        log_action("chip_alerts_fired", count=len(chip_alerts))
    else:
        print("HEARTBEAT_OK")

    log_action("heartbeat_complete")


if __name__ == "__main__":
    run()
