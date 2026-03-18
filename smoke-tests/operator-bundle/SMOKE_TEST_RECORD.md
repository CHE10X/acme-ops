# Smoke Test Record — Operator Bundle

**Version:** N/A (bundle)
**Date:** 2026-03-18
**Tester:** Hendrik Homarus
**Commit:** 8548ffb

| Gate | Result | Notes |
|------|--------|-------|
| 1 Install | N/A | Bundle — no standalone install. Installs components. |
| 2 Version | N/A | Bundle has no version of its own. Component versions apply. |
| 3 Happy Path | SEE COMPONENTS | Bundle delivers Sentinel + SphinxGate + DriftGuard + Watchdog. Each has its own record. |
| 4 Failure Path | SEE COMPONENTS | Deferred to component records. |
| 5 License Gate | FAIL | Bundle-level license gate not wired. Each component individually fails Gate 5. Blocking for customer activation. |
| 6 Regression | SEE COMPONENTS | Component-level regression applies. |
| 7 Docs | WARN | Mintlify quickstart at `/docs/quickstart/5-minute` covers bundle. Accuracy not verified this sprint. |

**Overall: FAIL (component failures propagate)**

**Notes:**
- Per doctrine: Operator Bundle tests components individually. No bundle-level record needed beyond this summary.
- Gate 5 is a blocking failure for all bundle components. Until license gating is wired into Sentinel, SphinxGate, DriftGuard, and Watchdog, the bundle cannot be customer-activated.
- Stripe SKU: `prod_U56ukpVLBM5p89`. Do not activate until component Gates 5 pass.
