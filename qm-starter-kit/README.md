# Quartermaster Starter Kit
**Product:** Quartermaster by Acme Agent Supply  
**Version:** 1.0.0  
**Setup time:** ~10 minutes

Quartermaster is the mission control layer for your OpenClaw agent team. It tracks work, moves tasks forward autonomously, enforces project discipline, and produces an auditable log of every agent action — without requiring you to coordinate between agents manually.

---

## What You Get

| Capability | Description |
|-----------|-------------|
| **Mission tracking** | Active missions with tasks, owners, dependencies, and status |
| **Autonomous dispatch** | QM nudges stalled agents and unblocks waiting tasks without operator intervention |
| **Project gate enforcement** | Every agent action with side effects requires a project code. QM blocks violations. |
| **Audit trail** | Tamper-detected log of every enforcement action. Queryable by task, agent, or project. |
| **TEAM_BOARD rendering** | Real-time team status board. QM owns it; agents update their own sections. |

---

## Setup

### Step 1 — Add QM to your OpenClaw agent config

```json
{
  "agents": {
    "list": [
      {
        "id": "quartermaster",
        "workspace": "/path/to/qm-starter-kit",
        "model": "google/gemini-2.5-flash-lite",
        "heartbeat": { "every": "30m" },
        "tools": { "deny": ["gateway"] }
      }
    ]
  }
}
```

### Step 2 — Configure your agents

Edit `qm_config.json`:
- Set `agents.list` to your agent IDs
- Adjust `stale_task_hours` and `alert_chip_hours` to your team's rhythm
- Enable/disable `project_gate` as needed

### Step 3 — Set up your agent INBOX files

Each agent needs an `INBOX.md` file in their workspace directory. QM writes nudges here; agents read and act on them.

### Step 4 — Create your first project

Add a row to `PROJECTS.md` or have an agent submit a project request via their INBOX (see `PROJECTS.md` for format).

### Step 5 — Verify QM is running

```
recall status          # Check fleet state
bonfire status         # Check observability
```

QM will fire on its first heartbeat and return `HEARTBEAT_OK` if everything is clean.

---

## Core Commands

| Command | What it does |
|---------|-------------|
| `status` | Current mission snapshot |
| `find [agent]` | Forensic sweep — where is this agent, what are they doing? |
| `stall [agent]` | Pause agent (keeps listening) — requires confirmation |
| `stun [agent]` | Hard stop agent — requires confirmation |
| `wake [agent]` | Resume stalled/stunned agent |
| `lockdown` | Pause ALL agents — emergency only, requires confirmation |
| `triage` | Stack reliability score |
| `bonfire` | Observability snapshot |

---

## Project Gate

Every agent action with side effects (code changes, config edits, new automations) must declare a project code. QM enforces this.

**Agents request project codes via INBOX:**
```yaml
QM_PROJECT_REQUEST:
  name: "My Project"
  description: "What this work accomplishes"
  owner: my-agent
```

QM assigns a code (`PROJ-YYYY-NNN`) and confirms back. No human required.

---

## Audit Log

Every enforcement action is logged to `logs/enforcement_log.jsonl` with per-line SHA256 for tamper detection.

**Query the log:**
```bash
python3 enforcement/audit.py                    # All entries
python3 enforcement/audit.py my-agent          # Filter by agent
python3 enforcement/audit.py PROJ-2026-001     # Filter by project
```

---

## Architecture Review Process (optional)

For teams that want adversarial architecture review before building:

See `docs/ARCHITECTURE_REVIEW_PROCESS.md` for the full process — including how to run a multi-model council review with Archer (GPT-5) as adversarial reviewer before any major build.

This is optional but recommended for teams building production agent systems.

---

## File Structure

```
qm-starter-kit/
├── README.md                          ← this file
├── SOUL.md                            ← QM identity + authority
├── BOOT.md                            ← startup sequence
├── HEARTBEAT_PROTOCOL.md              ← heartbeat operational spec
├── qm_config.json                     ← thresholds + gate config
├── PROJECTS.md                        ← project registry
├── missions/                          ← active mission files (add yours here)
├── enforcement/
│   ├── heartbeat_runner.py            ← heartbeat executor
│   └── audit.py                       ← audit log reader
├── logs/
│   └── enforcement_log.jsonl          ← tamper-detected audit trail
└── docs/
    └── ARCHITECTURE_REVIEW_PROCESS.md ← governance process doc
```

---

## Support

docs.acmeagentsupply.com · support@acmeagentsupply.com
