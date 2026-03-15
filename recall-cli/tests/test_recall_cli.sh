#!/usr/bin/env bash
set -euo pipefail

RUNTIME="/Users/AGENT/.openclaw/workspace/acme-ops/recall-cli/bin/recall_runtime.py"
LOG_FILE="$HOME/.openclaw/logs/recall_interventions.jsonl"
LOCKDOWN_FILE="$HOME/.openclaw/runtime/lockdown"
STATE_FILE="$HOME/.openclaw/runtime/recall/agent_state.json"

rm -f "$LOG_FILE"
rm -f "$LOCKDOWN_FILE"
mkdir -p "$HOME/.openclaw/runtime/recall"

python3 "$RUNTIME" lockdown
python3 "$RUNTIME" status
python3 "$RUNTIME" stall test-agent
python3 "$RUNTIME" wake test-agent
python3 "$RUNTIME" freeze test-agent
python3 "$RUNTIME" unfreeze test-agent
python3 "$RUNTIME" focus test-agent
python3 "$RUNTIME" unfocus
python3 "$RUNTIME" wake --all
python3 "$RUNTIME" sleep --all
python3 "$RUNTIME" wake --all
python3 "$RUNTIME" unlock

if [[ ! -f "$LOCKDOWN_FILE" ]]; then
  echo "PASS: lockdown was created and removed"
else
  echo "FAIL: lockdown file still present"
  exit 1
fi

if [[ ! -f "$STATE_FILE" ]]; then
  echo "FAIL: agent state not initialized"
  exit 1
fi

if [[ ! -f "$LOG_FILE" ]]; then
  echo "FAIL: recall intervention log not written"
  exit 1
fi

echo "PASS: recall cli smoke test completed"
