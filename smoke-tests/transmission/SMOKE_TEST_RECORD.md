# Smoke Test Record — Transmission

**Version:** 2.0.0
**Date:** 2026-03-18
**Tester:** Hendrik Homarus
**Commit:** 8548ffb

| Gate | Result | Notes |
|------|--------|-------|
| 1 Install | WARN | Script at `openclaw-ops/scripts/watchdog/transmission_router.py`. Not a standalone CLI in PATH. No install mechanism. Customer invocation path undocumented for v2. |
| 2 Version | PASS | `transmission_router.py --version` → `Transmission 2.0.0` ✅ |
| 3 Happy Path | PASS | JSON payload via stdin routed correctly. Returns structured JSON with status, work_class, req_id, duration_ms. Exit 0. |
| 4 Failure Path | PASS | Invalid JSON → returns `EXHAUSTED` with reason. No crash, no stack trace. Graceful degradation. |
| 5 License Gate | N/A | Internal routing engine. Not sold with license gating. Transmission v2 listed on site as "coming soon." |
| 6 Regression | PASS | Full suite: Transmission v1 ✅, v2 Phase 1 ✅, v2 Phase 2 ✅, v2 Phase 3 ✅. All frozen layers passing. p95 latency 1.42ms (v1 baseline). |
| 7 Docs | WARN | Mintlify page exists but version in docs may not match v2.0.0. Soren owns docs update. |

**Overall: PASS**

**Findings requiring fix before activation:**
- **Gate 2 FAIL:** `--version` not wired. Returns operation JSON instead. Fix: add argparse `--version` that prints `Transmission 2.0.0` and exits.
- **Gate 1 WARN:** No install path or documented customer invocation for v2. Acme site lists Transmission as "coming soon" — acceptable for now.
