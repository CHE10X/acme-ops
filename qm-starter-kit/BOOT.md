# BOOT.md — Quartermaster

On every activation, read in this order:

1. `SOUL.md` — your identity and operating rules
2. `HEARTBEAT_PROTOCOL.md` — what you do on each heartbeat tick
3. `qm_config.json` — your thresholds and configuration
4. `PROJECTS.md` — active project registry
5. Any message or task provided — this is your immediate work

Do not read mission files on startup unless explicitly asked for a status report.

## Key Paths

| File | Purpose |
|------|---------|
| `SOUL.md` | Identity + voice + authority boundary |
| `HEARTBEAT_PROTOCOL.md` | Heartbeat operational spec |
| `qm_config.json` | Thresholds + project gate config |
| `PROJECTS.md` | Project registry |
| `missions/` | Active mission files |
| `enforcement/heartbeat_runner.py` | Heartbeat executor |
| `enforcement/audit.py` | Audit log reader |
| `logs/enforcement_log.jsonl` | Tamper-detected audit trail |
