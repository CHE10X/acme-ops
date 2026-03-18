# Smoke Test Record — InfraWatch (was DriftGuard)

**Version:** 1.0.0
**Date:** 2026-03-18 (updated post PROJ-2026-008)
**Tester:** Hendrik Homarus
**Commit:** 498820d

## What InfraWatch Is

InfraWatch (renamed from DriftGuard) detects configuration and infrastructure drift in your agent stack — unexpected changes to ingest chains, daemon configs, launchd plists, and routing that could silently degrade reliability.

Delivered as bash script + launchd plist:
- **Script:** `~/.openclaw/bin/gmail_sentinel_drift_guard_v2_phase3.sh`
- **Plist:** `~/Library/LaunchAgents/ai.openclaw.gmail_drift_guard_v2.plist`
- **Modes:** `audit` (detect drift), `heal` (remediate safe drift)
- **Schedule:** every 30 minutes via launchd

| Gate | Result | Notes |
|------|--------|-------|
| 1 Install | PASS | Script executable, launchd plist present and loaded. Service registered and running. |
| 2 Version | PASS | Output strings updated: "INFRAWATCH: OK / DEGRADED / DRIFT DETECTED". Rename confirmed in code. |
| 3 Happy Path | PASS | `--mode audit` runs, detects drift state, emits REB event (`source=infrawatch event=config_drift severity=HIGH`). Exit code correct per drift level. |
| 4 Failure Path | PASS | Bad args → argparse error. Clean failure. |
| 5 License Gate | PASS | Hard-block via acme_license.py. Exit 2 on missing/expired/invalid license. Clear operator message. |
| 6 Regression | PASS | 12/12 regression suite passing. |
| 7 Docs | PASS | Mintlify page updated by Soren. Stripe SKU updated to InfraWatch (2026-03-18, Soren). |

**Overall: PASS**

**Post PROJ-2026-008 changes:**
- Renamed DriftGuard → InfraWatch in script output strings and product docs
- REB emit added: config_drift event at end of each audit run
- Stripe SKU `prod_U56nqUJd9LlJqQ` renamed to InfraWatch (Soren, 2026-03-18)
- Memory integrity framing removed — InfraWatch is infra/config layer only
- launchd plist label unchanged (`ai.openclaw.gmail_drift_guard_v2`) for operator continuity
