# Smoke Test Record — Sentinel

**Version:** 1.0.0
**Date:** 2026-03-18
**Tester:** Hendrik Homarus
**Commit:** 8548ffb

| Gate | Result | Notes |
|------|--------|-------|
| 1 Install | PASS | `acme-ops/scripts/sentinel/install.sh` exists with VERSION="1.0.0". Install script present and structured. |
| 2 Version | WARN | No `--version` CLI flag. Version only in `install.sh` as `VERSION="1.0.0"` and `acme-ops/scripts/sentinel/VERSION` file. Not surfaced at runtime. |
| 3 Happy Path | PASS | `sentinel_attach_bridge.py` returns structured JSON output (confidence, severity, reasons). `sentinel_funnel_alignment.py` returns `ALIGNMENT_OK` with elapsed ms and state. Both exit 0. |
| 4 Failure Path | PASS | Bad args → `argparse` error. No stack trace to operator. Clean failure. |
| 5 License Gate | FAIL | No license enforcement wired. Sentinel runs without any license check. Pre-identified gap in sprint brief. |
| 6 Regression | PASS | `sentinel_attach_bridge` and `sentinel_funnel_alignment` proofs pass. |
| 7 Docs | WARN | Mintlify page at `/docs/products/sentinel/overview` — not verified this sprint. |

**Overall: FAIL**

**Findings requiring fix before activation:**
- **Gate 5 FAIL:** License gate not wired. This is a known pre-sprint gap — must be resolved before customer activation.
- **Gate 2 WARN:** Add `--version` to runtime scripts. Not blocking but required by doctrine.
