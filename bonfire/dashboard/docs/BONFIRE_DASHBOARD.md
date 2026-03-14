# Bonfire Dashboard v1

## Purpose

This is a local-only, read-only operator dashboard for Bonfire telemetry and analytics.

- Uses only:
  - `~/.openclaw/logs/bonfire_tokens.jsonl`
  - `~/.openclaw/logs/bonfire_health.json`
  - `~/.openclaw/logs/bonfire_economics.json`
  - `~/.openclaw/logs/bonfire_alerts.log`
- Does not write back to Bonfire logs.
- Provides compact views for overview, agents, economics, and alerts.

## Run locally

From `~/.openclaw/workspace/openclaw-ops/bonfire/dashboard`:

```bash
python3 app/server.py --host 127.0.0.1 --port 8765
```

Open:

- `http://127.0.0.1:8765/`

## Endpoints

- `GET /api/overview`
- `GET /api/agents`
- `GET /api/economics`
- `GET /api/alerts`
- `GET /api/runaway`
- `GET /api/burnrate`
- `GET /api/model-timeline`
- `GET /api/heatmap`
- `GET /api/model-efficiency`
- `GET /api/loops`
- `GET /api/cost-anomalies`

All endpoints return compact JSON and never write files.

## Missing-file handling

- If a source file is absent, the UI shows a non-blocking availability message:
  - `no telemetry events found`
  - `health snapshot unavailable`
  - `economics snapshot unavailable`
  - `no alerts log found`
- Page still renders in partial-data mode.

## Notes

- Auto refresh every 15 seconds.
- Manual refresh button also available.
- Read-only and no auth by design.
