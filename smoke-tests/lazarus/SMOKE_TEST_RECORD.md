# Smoke Test Record — Lazarus

**Version:** 1.0.0
**Date:** 2026-03-18
**Tester:** Hendrik Homarus
**Commit:** 8548ffb

| Gate | Result | Notes |
|------|--------|-------|
| 1 Install | WARN | Script at `acme-ops/scripts/lazarus/lazarus.py`. Not installed to PATH. Customer must invoke via `python3 path/to/lazarus.py`. No install script. |
| 2 Version | FAIL | `lazarus.py --version` → `unrecognized arguments: --version`. `__version__ = "1.0.0"` exists in source but argparse does not expose `--version` flag. |
| 3 Happy Path | PASS | `lazarus.py --mode scan` runs recovery readiness scan. Structured output with `LAZARUS PROTOCOL v1 — RECOVERY READINESS SCAN`. Exit 0. |
| 4 Failure Path | PASS | `lazarus.py --badarg` → argparse error with usage block. No stack trace. Clean failure. |
| 5 License Gate | FAIL | No license enforcement. Lazarus runs without any license check. Pre-identified gap. |
| 6 Regression | WARN | No dedicated lazarus regression harness. Not in daily suite. |
| 7 Docs | WARN | Mintlify page at `/docs/quickstart/5-minute` (bundled with quickstart, per fulfillmentLinks). Product-specific docs page not confirmed. |

**Overall: FAIL**

**Findings requiring fix before activation:**
- **Gate 2 FAIL:** Add `--version` to lazarus.py argparse. Wire to `__version__`. Format: `Lazarus 1.0.0`.
- **Gate 5 FAIL:** License gate not wired. Known pre-sprint gap.
- **Gate 1 WARN:** No install script. Documented `python3` invocation path needed.
