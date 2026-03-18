# Smoke Test Record — SphinxGate

**Version:** 1.0.0
**Date:** 2026-03-18
**Tester:** Hendrik Homarus
**Commit:** 8548ffb

| Gate | Result | Notes |
|------|--------|-------|
| 1 Install | WARN | No install script found. Scripts at `acme-ops/scripts/watchdog/sphinxgate_*.py`. Customer install path undocumented. |
| 2 Version | WARN | No `--version` flag. VERSION file exists at `acme-ops/scripts/watchdog/VERSION` (1.0.0) but not surfaced at runtime. |
| 3 Happy Path | FAIL | `sphinxgate_proof.py` partial execution — errors with `AttributeError: 'ModelRouter' object has no attribute '_is_claude'` at line 52. Proof script broken by model_router refactor. |
| 4 Failure Path | WARN | Not independently tested due to Gate 3 failure. Core logic not reachable. |
| 5 License Gate | FAIL | No license enforcement wired. Pre-identified gap. |
| 6 Regression | WARN | `sphinxgate_v1_freeze_proof.py` and `sphinxgate_telemetry_proof.py` exist but not included in daily regression suite. Not confirmed passing. |
| 7 Docs | WARN | Mintlify page at `/docs/products/sphinxgate/overview` — not verified this sprint. |

**Overall: FAIL**

**Findings requiring fix before activation:**
- **Gate 3 FAIL:** `sphinxgate_proof.py` broken — `_is_claude` method missing from ModelRouter after refactor. Fix required.
- **Gate 5 FAIL:** License gate not wired. Known pre-sprint gap.
- **Gate 6 WARN:** SphinxGate proofs not in daily regression suite. Add to `qa/run_regression_suite.sh`.
- **Gate 1 WARN:** No install script or documented install path.
