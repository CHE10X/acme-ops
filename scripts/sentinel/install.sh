#!/usr/bin/env bash
# =============================================================================
# Sentinel + Watchdog — Customer Install Script
# ACME Agent Supply — https://acmeagentsupply.com
#
# What this does:
#   1. Downloads the Watchdog heartbeat script
#   2. Installs a launchd plist (macOS) or cron job (Linux)
#   3. Starts the service immediately
#   4. Verifies it's running and prints status
#
# Usage:
#   curl -fsSL https://acmeagentsupply.com/install/sentinel | bash
#   OR with license key:
#   curl -fsSL https://acmeagentsupply.com/install/sentinel | ACME_LICENSE_KEY=xxx bash
#
# Supports: macOS 12+, Ubuntu/Debian 20.04+
# Requires: bash, curl, openclaw (already installed)
# =============================================================================

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
PRODUCT="Sentinel"
VERSION="1.0.0"
ACME_BASE="https://acmeagentsupply.com"
OC_DIR="$HOME/.openclaw"
WATCHDOG_DIR="$OC_DIR/watchdog"
SENTINEL_DIR="$OC_DIR/sentinel"
WATCHDOG_SCRIPT="$WATCHDOG_DIR/sentinel_watchdog.sh"
PLIST_LABEL="ai.openclaw.sentinel"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
CRON_MARKER="# acme-sentinel-watchdog"
LOG="$SENTINEL_DIR/install.log"
INTERVAL=300   # 5 minutes

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'

ok()   { echo -e "${GREEN}✓${RESET} $*"; }
info() { echo -e "${BLUE}→${RESET} $*"; }
warn() { echo -e "${YELLOW}⚠${RESET} $*"; }
fail() { echo -e "${RED}✗${RESET} $*"; exit 1; }
step() { echo -e "\n${BOLD}$*${RESET}"; }

# ── Detect OS ─────────────────────────────────────────────────────────────────
OS="unknown"
if [[ "$OSTYPE" == darwin* ]]; then
  OS="macos"
elif [[ -f /etc/debian_version ]] || [[ -f /etc/ubuntu_version ]]; then
  OS="linux"
elif [[ -f /etc/os-release ]]; then
  OS="linux"
fi

# ── Header ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}ACME Agent Supply — ${PRODUCT} Installer v${VERSION}${RESET}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Preflight ─────────────────────────────────────────────────────────────────
step "1. Preflight checks"

[[ "$OS" == "unknown" ]] && fail "Unsupported OS. Sentinel supports macOS and Linux."
ok "OS: $OS"

command -v openclaw >/dev/null 2>&1 || fail "openclaw not found. Install OpenClaw first: https://openclaw.ai"
OC_VERSION=$(openclaw --version 2>/dev/null | head -1 || echo "unknown")
ok "openclaw: $OC_VERSION"

# Verify license key if provided
if [[ -n "${ACME_LICENSE_KEY:-}" ]]; then
  info "Validating license key..."
  HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "X-License-Key: $ACME_LICENSE_KEY" \
    -H "X-Product: sentinel" \
    "${ACME_BASE}/api/license/verify" 2>/dev/null || echo "000")
  if [[ "$HTTP_STATUS" == "200" ]]; then
    ok "License key valid"
    echo "$ACME_LICENSE_KEY" > "$OC_DIR/.sentinel_license"
    chmod 600 "$OC_DIR/.sentinel_license"
  elif [[ "$HTTP_STATUS" == "000" ]]; then
    warn "Could not reach license server — proceeding (will validate on first run)"
  else
    fail "Invalid license key (HTTP $HTTP_STATUS). Check your key at acmeagentsupply.com/dashboard"
  fi
fi

# ── Create directories ────────────────────────────────────────────────────────
step "2. Setting up directories"
mkdir -p "$WATCHDOG_DIR" "$SENTINEL_DIR"
mkdir -p "$SENTINEL_DIR/signals" "$SENTINEL_DIR/alerts"
ok "Directories ready at $SENTINEL_DIR"

# Start install log
exec > >(tee -a "$LOG") 2>&1

# ── Write watchdog script ─────────────────────────────────────────────────────
step "3. Installing Sentinel watchdog script"

cat > "$WATCHDOG_SCRIPT" << 'WATCHDOG_EOF'
#!/usr/bin/env bash
# Sentinel Watchdog — runs every 5 minutes via launchd/cron
# DO NOT EDIT — managed by ACME Sentinel installer
set -euo pipefail

OC_DIR="$HOME/.openclaw"
SENTINEL_DIR="$OC_DIR/sentinel"
LOG="$SENTINEL_DIR/sentinel.log"
SIGNALS_DIR="$SENTINEL_DIR/signals"
STATE_FILE="$SENTINEL_DIR/state.json"
LOCK_FILE="$SENTINEL_DIR/watchdog.lock"
LOCK_PID="$SENTINEL_DIR/watchdog.pid"

mkdir -p "$SENTINEL_DIR" "$SIGNALS_DIR"

# Lockfile — prevent concurrent runs
if [[ -f "$LOCK_FILE" ]]; then
  OLD_PID=$(cat "$LOCK_PID" 2>/dev/null || echo "")
  if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    exit 0
  fi
  rm -f "$LOCK_FILE" "$LOCK_PID"
fi
echo $$ > "$LOCK_PID"
touch "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE" "$LOCK_PID"' EXIT INT TERM

ts() { date '+%Y-%m-%d %H:%M:%S %Z'; }
log() { echo "[$(ts)] $*" >> "$LOG"; }

log "Sentinel run start (pid=$$)"

# ── Collect signals ──────────────────────────────────────────────────────────
GATEWAY_PORT="${OPENCLAW_PORT:-18789}"
GATEWAY_UP="false"
GATEWAY_LATENCY_MS=0

if command -v openclaw >/dev/null 2>&1; then
  START_MS=$(($(date +%s%N) / 1000000))
  if openclaw status --json >/dev/null 2>&1; then
    GATEWAY_UP="true"
    END_MS=$(($(date +%s%N) / 1000000))
    GATEWAY_LATENCY_MS=$((END_MS - START_MS))
  fi
fi

# Heartbeat file freshness
HEARTBEAT_FILE="$OC_DIR/watchdog/heartbeat.log"
HEARTBEAT_AGE_S=9999
if [[ -f "$HEARTBEAT_FILE" ]]; then
  LAST_MODIFIED=$(stat -f %m "$HEARTBEAT_FILE" 2>/dev/null || stat -c %Y "$HEARTBEAT_FILE" 2>/dev/null || echo 0)
  NOW=$(date +%s)
  HEARTBEAT_AGE_S=$((NOW - LAST_MODIFIED))
fi

# Disk pressure
DISK_USED_PCT=0
if command -v df >/dev/null 2>&1; then
  DISK_USED_PCT=$(df -h "$HOME" 2>/dev/null | awk 'NR==2{gsub(/%/,"",$5); print $5}' || echo 0)
fi

# Session log freshness
SESSION_LOG="$OC_DIR/agents/main/agent/events.log"
SESSION_AGE_S=9999
if [[ -f "$SESSION_LOG" ]]; then
  LAST_MODIFIED=$(stat -f %m "$SESSION_LOG" 2>/dev/null || stat -c %Y "$SESSION_LOG" 2>/dev/null || echo 0)
  NOW=$(date +%s)
  SESSION_AGE_S=$((NOW - LAST_MODIFIED))
fi

# ── Evaluate state ──────────────────────────────────────────────────────────
STATE="NOMINAL"
ALERTS=()

if [[ "$GATEWAY_UP" == "false" ]]; then
  STATE="ACTIVE"
  ALERTS+=("gateway_down")
  log "ALERT: gateway not responding"
fi

if [[ $HEARTBEAT_AGE_S -gt 900 ]]; then
  [[ "$STATE" == "NOMINAL" ]] && STATE="SUSPECT"
  ALERTS+=("heartbeat_stale:${HEARTBEAT_AGE_S}s")
  log "ALERT: heartbeat stale (${HEARTBEAT_AGE_S}s)"
fi

if [[ $DISK_USED_PCT -gt 90 ]]; then
  [[ "$STATE" == "NOMINAL" ]] && STATE="SUSPECT"
  ALERTS+=("disk_pressure:${DISK_USED_PCT}%")
  log "ALERT: disk pressure (${DISK_USED_PCT}%)"
fi

if [[ $SESSION_AGE_S -gt 1800 ]]; then
  [[ "$STATE" == "NOMINAL" ]] && STATE="SUSPECT"
  ALERTS+=("session_stale:${SESSION_AGE_S}s")
fi

# ── Write state ──────────────────────────────────────────────────────────────
NOW_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
ALERTS_JSON=$(printf '"%s",' "${ALERTS[@]+"${ALERTS[@]}"}" | sed 's/,$//')

cat > "$STATE_FILE" << STATE_EOF
{
  "state": "$STATE",
  "checked_at": "$NOW_ISO",
  "gateway_up": $GATEWAY_UP,
  "gateway_latency_ms": $GATEWAY_LATENCY_MS,
  "heartbeat_age_s": $HEARTBEAT_AGE_S,
  "disk_used_pct": $DISK_USED_PCT,
  "session_age_s": $SESSION_AGE_S,
  "alerts": [$ALERTS_JSON],
  "version": "1.0.0"
}
STATE_EOF

# ── Archive signal ──────────────────────────────────────────────────────────
cp "$STATE_FILE" "$SIGNALS_DIR/$(date -u +%Y%m%dT%H%M%S).json"

# Prune signals older than 7 days
find "$SIGNALS_DIR" -name "*.json" -mtime +7 -delete 2>/dev/null || true

log "Sentinel run complete: state=$STATE alerts=${#ALERTS[@]}"
WATCHDOG_EOF

chmod +x "$WATCHDOG_SCRIPT"
ok "Watchdog script installed at $WATCHDOG_SCRIPT"

# ── Install persistent daemon ─────────────────────────────────────────────────
step "4. Installing persistent daemon"

if [[ "$OS" == "macos" ]]; then
  info "Installing launchd plist..."

  # Unload existing if present
  if launchctl list "$PLIST_LABEL" >/dev/null 2>&1; then
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    info "Unloaded existing $PLIST_LABEL"
  fi

  cat > "$PLIST_PATH" << PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${PLIST_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${WATCHDOG_SCRIPT}</string>
  </array>
  <key>StartInterval</key>
  <integer>${INTERVAL}</integer>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <false/>
  <key>StandardOutPath</key>
  <string>${SENTINEL_DIR}/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${SENTINEL_DIR}/launchd.err.log</string>
</dict>
</plist>
PLIST_EOF

  launchctl load "$PLIST_PATH"
  ok "launchd service installed and started (every ${INTERVAL}s)"

elif [[ "$OS" == "linux" ]]; then
  info "Installing cron job..."

  # Remove existing sentinel cron if present
  (crontab -l 2>/dev/null | grep -v "$CRON_MARKER" || true) | crontab -

  # Add new cron entry
  CRON_ENTRY="*/5 * * * * $WATCHDOG_SCRIPT >> $SENTINEL_DIR/sentinel.log 2>&1 $CRON_MARKER"
  (crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -
  ok "cron job installed (every 5 minutes)"
fi

# ── First run ─────────────────────────────────────────────────────────────────
step "5. Running first health check"
info "Running Sentinel now..."
bash "$WATCHDOG_SCRIPT" || true

if [[ -f "$SENTINEL_DIR/state.json" ]]; then
  STATE_VAL=$(python3 -c "import json,sys; d=json.load(open('$SENTINEL_DIR/state.json')); print(d.get('state','UNKNOWN'))" 2>/dev/null || echo "UNKNOWN")
  ALERTS_VAL=$(python3 -c "import json,sys; d=json.load(open('$SENTINEL_DIR/state.json')); a=d.get('alerts',[]); print(', '.join(a) if a else 'none')" 2>/dev/null || echo "unknown")
  ok "First run complete"
  echo ""
  echo -e "  State:  ${BOLD}${STATE_VAL}${RESET}"
  echo -e "  Alerts: ${ALERTS_VAL}"
  echo -e "  Log:    ${SENTINEL_DIR}/sentinel.log"
else
  warn "State file not found — check $SENTINEL_DIR/sentinel.log"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}${BOLD}Sentinel installed successfully.${RESET}"
echo ""
echo "  Monitoring:  Every 5 minutes, always on"
echo "  State file:  $SENTINEL_DIR/state.json"
echo "  Logs:        $SENTINEL_DIR/sentinel.log"
echo ""
echo "  Check status anytime:"
echo -e "  ${BOLD}cat ~/.openclaw/sentinel/state.json${RESET}"
echo ""
echo "  Docs: https://acmeagentsupply.com/docs/sentinel"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
