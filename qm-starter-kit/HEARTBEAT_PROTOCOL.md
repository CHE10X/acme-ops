# QM Heartbeat Protocol
**Version:** 1.0.0  
**Status:** FROZEN ✅ — 2026-03-18  
**Reviewed by:** Archer (PROJ-2026-004)  
**Config:** `quartermaster_v1/qm_config.json`

---

## Overview

This document defines exactly what Quartermaster does on each heartbeat tick. All operational logic lives here — SOUL.md references this doc by name only.

QM reads from mission files. QM never reads TEAM_BOARD.md for dispatch decisions. TEAM_BOARD.md is an output QM renders.

---

## Heartbeat Sequence

Execute in order. Stop and alert Chip only if a genuine blocker requires human decision.

### Step 1 — Load Config
Read `quartermaster_v1/qm_config.json`. Use configured thresholds for all subsequent steps.

### Step 2 — Scan Mission Files
Read all active missions from `~/.openclaw/quartermaster/missions/`.

For each task in each mission:

**`running` + last_updated older than `stale_task_hours`:**
- Write nudge to owner's INBOX.md (with deduplication — see below)
- Update task `blocker_detail` with stall note
- Log enforcement action

**`needs_review`:**
- Write nudge to reviewing agent's INBOX.md (with deduplication)
- Log action

**`complete` + other tasks had this as dependency:**
- Write "you are unblocked" nudge to dependent task owner's INBOX.md
- Update dependent task status from `blocked` to `pending`

**`running` + last_updated older than `alert_chip_hours`:**
- Alert Chip via Slack DM: "Task [N] in [mission] stalled [X]hrs — owner [agent] not responding"

### Step 3 — Process Agent Project Requests
Read each agent's INBOX.md. Look for `QM_PROJECT_REQUEST:` YAML blocks.

For each valid request:
- Create entry in `workspace/archer/PROJECTS.md`
- Assign next sequential project code (`PROJ-YYYY-NNN`)
- Write confirmation to requesting agent's INBOX.md with project code
- Log action

For each malformed request:
- Write parse error back to agent INBOX.md with correct format
- Log rejection

### Step 4 — Render TEAM_BOARD
Write current mission state to `workspace/TEAM_BOARD.md` — agent task statuses, cross-agent dependencies, stall flags.

TEAM_BOARD.md is output only. QM writes it; agents update their own sections; humans read it. QM never reads it for dispatch decisions.

### Step 5 — Project Gate Check
For any work in mission files marked as completed this heartbeat:
- Verify a project code was declared
- If missing: write enforcement notice to agent INBOX.md
- Log violation to `enforcement_log.jsonl`

QM's own heartbeat actions are also subject to this check. No bypass.

---

## Deduplication Rule

Before writing any nudge to an agent INBOX.md:
1. Read last 50 lines of target INBOX.md
2. Check if identical nudge exists with timestamp within `nudge_cooldown_hours`
3. If yes → skip write, log skip
4. If no → write nudge, log write
5. If task has received `max_nudges_per_task` nudges → escalate to Chip instead

---

## Enforcement Log Format

File: `quartermaster_v1/logs/enforcement_log.jsonl`  
Format: one JSON object per line, with SHA256 of the line content appended.

```json
{"ts": "2026-03-18T12:00:00Z", "action": "nudge_written", "agent": "soren", "task_id": "t05", "project": "PROJ-2026-003", "sha256": "<hash>"}
{"ts": "2026-03-18T12:00:00Z", "action": "project_gate_violation", "agent": "hendrik", "description": "code change without project code", "sha256": "<hash>"}
{"ts": "2026-03-18T12:00:00Z", "action": "project_request_accepted", "agent": "soren", "project": "PROJ-2026-006", "sha256": "<hash>"}
```

Read interface: `qm audit [task-id|agent|project]` — filters log by the given dimension.
Retention: `audit_retention_days` from `qm_config.json`.

---

## Agent Project Self-Registration Format

Agents write this YAML block to their INBOX.md to request a project code:

```yaml
QM_PROJECT_REQUEST:
  name: "Friction Tax Audit"
  description: "Soren + Gerrit audit of team coordination overhead"
  owner: soren
  collaborators: [gerrit]
```

Required fields: `name`, `description`, `owner`.  
Optional: `collaborators`.  
On parse failure: QM writes error back to agent INBOX.md with correct format example.

---

## Authority Boundary

QM governs tasks assigned in its active mission files.  
QM does not touch tasks outside its mission files.  
TEAM_BOARD task queue is owned by QM — agents cannot add rows directly.  
Agent TEAM_BOARD sections (status, needs) are owned by each agent.

---

## Alert Escalation to Chip

Alert Chip only when:
- Task stalled beyond `alert_chip_hours` AND owner hasn't responded to nudge
- Parse failure on project request that agent can't self-resolve
- Mission-level blocker requiring human decision

Do NOT alert Chip for: routine nudges, deduplication skips, successful project registrations, TEAM_BOARD renders.
