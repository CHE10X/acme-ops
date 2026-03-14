## Bonfire v2 — Token Governance (OpenClaw local-first)

Bonfire now provides local telemetry **and** governance:
- token telemetry and session lifecycle tracking
- model routing guardrails
- budget enforcement by agent, lane, and model
- runaway-agent detection and cooldown/termination
- cost estimation and operator dashboards

Data paths:
- events: `~/.openclaw/logs/bonfire_tokens.jsonl`
- rotated tokens: `~/.openclaw/logs/bonfire_tokens_YYYYMMDD.jsonl`
- alerts: `~/.openclaw/logs/bonfire_alerts.log`
- summaries: `~/.openclaw/logs/bonfire_summary.json`
- cost report: `~/.openclaw/logs/bonfire_costs.json`

### Governance integration

- `scripts/watchdog/model_router.py` now calls governor preflight before routing.
- Lane policy and lane defaults come from:
  - `bonfire/policy/lane_policy.json`
- Model/routing budgets come from:
  - `bonfire/budgets/budget_store.json`
- Budget state is tracked in process memory and updated by `collector/token_hook.py`.

### Runtime events

Each model/tool event records:
- `timestamp`, `agent_id`, `session_id`, `model`
- `prompt_tokens`, `completion_tokens`, `total_tokens`
- `tool_used`, `latency_ms`, `status`
- governance route metadata (`lane`, `session_runway`) when available

### CLI commands (`./bin/bonfire`)

- `status`  
  Agent usage, model usage, spikes, active sessions
- `budgets`  
  Active budget consumption and configured limits
- `alerts`  
  Recent real-time alerts
- `cost`  
  Cost summary by agent/model/day/hour

### Governance behavior

- If a request exceeds policy, Bonfire emits alert and applies one mitigation:
  - reject (`TOKEN_BUDGET_EXCEEDED`)
  - lane move (interactive -> background)
  - model downgrade
  - delay cooldown (runaway throttle)
  - terminate session (runaway pattern)
- Governor is fail-open: telemetry failure must not block model execution.
