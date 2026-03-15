# recall-cli

Manual intervention surface for OpenClaw operators. Register as `openclaw recall`.

## Command Surface

- `lockdown`: create `~/.openclaw/runtime/lockdown`
- `unlock`: remove lockdown file
- `status`: fleet snapshot, current lock-down status and recent interventions
- `log [agent]`: show recent `recall_interventions.jsonl` entries

## Agent commands

- `freeze <agent>` / `unfreeze <agent>`
- `stall <agent|--all>`
- `sleep <agent|--all> [--channel <id>]`
- `stun <agent> [--capture-bundle]`
- `quarantine <agent>`
- `wake <agent|--all> [--channel <id>]`
- `recover <agent>`
- `focus <agent>`
- `unfocus`

## Recovery command

- `reset` performs:
  1. optional OCTriage-like support bundle
  2. compact all agents
  3. snapshot
  4. backup
  5. restart gateway
  6. verify

All commands emit control-plane events to:
- `~/.openclaw/logs/recall_interventions.jsonl`

Stun operations use Agent911 primitives when available.

## Runtime state

- Runtime: `~/.openclaw/runtime/recall/agent_state.json`
- Lockdown: `~/.openclaw/runtime/lockdown`
- Intervention log: `~/.openclaw/logs/recall_interventions.jsonl`

## Control-plane event format

Every operation emits `event_type: recall_intervention` records with fields:
`operation`, `agent`, `channel`, `steps_completed`, `steps_failed`,
`bundle_captured`, `outcome`, and `timestamp`.

## Notes

- `unlock` removes `~/.openclaw/runtime/lockdown`.
- `unfocus` restores the stall + sleep state for all agents captured when focus was engaged.
- `recover` is a manual, operator-confirmed recovery flow and requires a prior `stun`.

## Files

- Runtime state: `~/.openclaw/runtime/recall/agent_state.json`
- Lockdown flag: `~/.openclaw/runtime/lockdown`
- Intervention log: `~/.openclaw/logs/recall_interventions.jsonl`
