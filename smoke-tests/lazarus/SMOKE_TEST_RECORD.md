# Smoke Test Record — Lazarus

**Version:** 1.0.0
**Date:** 2026-03-18 (updated post PROJ-2026-008)
**Tester:** Hendrik Homarus
**Commit:** 498820d

| Gate | Result | Notes |
|------|--------|-------|
| 1 Install | WARN | Script at `acme-ops/scripts/lazarus/lazarus.py`. Not in PATH. Customer invokes via `python3`. No install script. |
| 2 Version | PASS | `lazarus.py --version` → `Lazarus 1.0.0` ✅ |
| 3 Happy Path | PASS | `--mode scan` runs readiness scan. `--mode watch` now available — subscribes to REB HIGH/CRITICAL events, triggers scan+plan, emits `readiness_complete`. All existing modes unchanged. |
| 4 Failure Path | PASS | `--mode badmode` → argparse error with valid choices listed (scan, plan, generate, validate, watch, all). Clean failure. |
| 5 License Gate | PASS | Hard-block via acme_license.py. Exit 2 on missing/expired/invalid license. Clear operator message. |
| 6 Regression | PASS | 12/12 regression suite passing. |
| 7 Docs | WARN | Mintlify page not verified post REB changes. `--mode watch` not documented yet — Soren to update. |

**Overall: PASS**

**Post PROJ-2026-008 changes:**
- `--mode watch` added: polls REB every 10s, triggers on HIGH/CRITICAL (hardcoded v1)
- Emits `readiness_scan_start` (INFO) at start of triggered scan
- Emits `readiness_complete` (INFO if lz_score ≥ 70, HIGH if < 70) with blueprint path + trigger source
- Mirrors blueprint to `~/.openclaw/lazarus/recovery_blueprint.json` for Agent911 compatibility
- Existing modes (scan/plan/generate/validate/all) unchanged
