# Smoke Test Record — Agent911

**Version:** 2.0.0
**Date:** 2026-03-18 (updated post PROJ-2026-008)
**Tester:** Hendrik Homarus
**Commit:** 498820d

| Gate | Result | Notes |
|------|--------|-------|
| 1 Install | WARN | Script at `acme-ops/agent911/bin/agent911`. Not in PATH. Customer invokes via `python3`. No global install. |
| 2 Version | PASS | `agent911 --version` → `Agent911 2.0.0` ✅ |
| 3 Happy Path | PASS | `reconstruct-diagnose` → structured output (doctrine_status OK, memory_tree OK, checkpoint_availability). `check_lazarus_readiness()` present as precondition in execute path. REB emit on recovery_start and recovery_complete. |
| 4 Failure Path | PASS | Bad command → usage block with available commands. Fallback path verified: if no Lazarus blueprint within 60s, proceeds with best-effort recovery. Fallback does not block recovery. |
| 5 License Gate | N/A | Not a licensed product (install script, no Stripe feature gating). |
| 6 Regression | PASS | 12/12 regression suite passing. |
| 7 Docs | WARN | Mintlify page at `/docs/products/agent911/overview` — Lazarus precondition not documented yet. Soren to update. |

**Overall: PASS**

**Post PROJ-2026-008 changes:**
- `check_lazarus_readiness(timeout_s=60)` added — polls REB for `readiness_complete` events before execute
- Fallback: if no blueprint within 60s → proceeds with best-effort recovery (current behavior preserved)
- REB emit on `recovery_start` (HIGH) and `recovery_complete` (INFO)
- REB failures silently swallowed — never block recovery paths
- sys.path fix: repo-relative import (hardcoded path removed)
