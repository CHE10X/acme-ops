# Smoke Test Record — Triage

**Version:** 0.1.6 (OSS — octriageunit)
**Date:** 2026-03-18
**Tester:** Hendrik Homarus
**Commit:** 8548ffb

| Gate | Result | Notes |
|------|--------|-------|
| 1 Install | PASS | `octriage` and `octriageunit` installed at `/usr/local/bin`. Global CLI available. |
| 2 Version | PASS | `octriage --version` → `octriageunit 0.1.6` ✅ |
| 3 Happy Path | PASS | `octriage --help` returns safety guarantees, usage, and command list. Structured and clean. |
| 4 Failure Path | PASS | `octriage badcommand` → `Unknown argument: badcommand` + safety notes + usage. No stack trace. |
| 5 License Gate | N/A | OSS version (`octriage`) has no license gating. Commercial version (`acme-ops/triage-commercial/`) has license hooks — not tested this sprint (separate record needed). |
| 6 Regression | PASS | OSS octriageunit has its own proof bundle system. Functional and tested. |
| 7 Docs | WARN | `acmeagentsupply.com/docs` — triage page exists (Soren built it). Accuracy against 0.1.6 not verified. |

**Overall: PASS (OSS version)**

**Notes:**
- OSS/commercial split confirmed 2026-03-15. OSS = `octriageunit` (CHE10X/octriageunit, public). Commercial = `acme-ops/triage-commercial/` with paid hooks (watch_mode.py, RadCheck history, Observe panel).
- Commercial version needs separate smoke test record before its Stripe SKU activates.
- Version `0.1.6` is OSS — not synced to Acme product versioning doctrine (Acme smoke test lists it as 1.0.0). Clarify with Chip: does commercial triage start at 1.0.0 independent of OSS version?
