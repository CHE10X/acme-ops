# Smoke Test Record — DriftGuard

**Version:** 1.0.0
**Date:** 2026-03-18
**Tester:** Hendrik Homarus
**Commit:** 8548ffb

## What DriftGuard Actually Is

DriftGuard is delivered as a bash script + launchd plist (not a Python CLI).
- **Script:** `~/.openclaw/bin/gmail_sentinel_drift_guard_v2_phase3.sh`
- **Plist:** `~/Library/LaunchAgents/ai.openclaw.gmail_drift_guard_v2.plist`
- **Modes:** `audit` (detect drift) and `heal` (remediate safe drift)
- **Schedule:** every 30 minutes via launchd

The Mintlify docs describe the product concept (memory integrity monitoring). The deliverable is the script + plist + install instructions.

| Gate | Result | Notes |
|------|--------|-------|
| 1 Install | PASS | Install = write plist to `~/Library/LaunchAgents/`, `launchctl load -w`. Script is executable at install path. Install instructions exist in product docs. |
| 2 Version | WARN | No `--version` flag on the bash script. VERSION file in `acme-ops/scripts/driftguard/` has `1.0.0` but not surfaced at runtime. Bash script has no version arg. |
| 3 Happy Path | PASS | Script runs in `--mode audit`. Produces proof bundle, structured output, detects drift or confirms OK. Exit codes documented (0=OK, 2=DEGRADED, 3=DRIFT, 4=ERROR). |
| 4 Failure Path | PASS | Missing `--env` file → clean error. Exit code 4. No silent failure. |
| 5 License Gate | FAIL | No license enforcement wired. Script runs without any license check. Pre-identified gap. |
| 6 Regression | PASS | Service loaded and running. `launchctl print` confirms registration. Proof bundle validates on each run. |
| 7 Docs | PASS | Mintlify page at `/docs/driftguard/overview` — exists and accurately describes product concept and signals. |

**Overall: FAIL (Gate 5 only)**

**Findings requiring fix before activation:**
- **Gate 5 FAIL:** License gate not wired. Script executes without any license validation. Known pre-sprint gap — must be resolved before customer activation.
- **Gate 2 WARN:** `--version` not surfaced at runtime. Not blocking but required by doctrine for CLI products. For a bash script, acceptable to embed version as a comment and emit in `--help` or header output.

**Service status (2026-03-18):** Loaded via `launchctl load -w`. Registered as `gui/503/ai.openclaw.gmail_drift_guard_v2`. Fires every 30 min. Previously unloaded — reloaded this session.

**Previous mistake in this record:** Earlier erroneously marked as "CRITICAL: no implementation." That was wrong — the implementation lives in `~/.openclaw/bin/`, not in the workspace scripts directory. The `acme-ops/scripts/driftguard/` folder only contains a VERSION file because the script is installed to `~/.openclaw/bin/`.
