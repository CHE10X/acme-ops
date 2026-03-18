# Smoke Test Record — Bonfire

**Version:** 1.0.0
**Date:** 2026-03-18
**Tester:** Hendrik Homarus
**Commit:** 8548ffb

| Gate | Result | Notes |
|------|--------|-------|
| 1 Install | PASS | `bonfire` installed at `/usr/local/bin/bonfire`. Global CLI available. |
| 2 Version | PASS | `bonfire --version` → `Bonfire 1.0.0` ✅ |
| 3 Happy Path | WARN | `bonfire status` returns structure (router: active, governor: active) but predictor and optimizer show `unknown`. Pipeline partially broken — token_hook.py not wired to gateway. All-zeros on token metrics. |
| 4 Failure Path | PASS | `bonfire badcommand` → `Unknown command: badcommand` + usage. Clean failure. |
| 5 License Gate | N/A | Internal tool, not sold via Stripe. |
| 6 Regression | WARN | No dedicated bonfire regression harness. Archer red team pending per sprint brief. Not in daily regression suite. |
| 7 Docs | N/A | Internal tool. No Mintlify docs page required. |

**Overall: WARN — not blocking (internal tool)**

**Known issues:**
- **Gate 3 WARN:** `token_hook.py` not wired to gateway model dispatch. Bonfire pipeline broken — predictor/optimizer metrics are `unknown`. Fix in progress (INBOX item).
- **Gate 6 WARN:** No standalone regression harness. Archer red team review pending before production use.
- Governor preflight integration with Transmission confirmed wired (14/14 proofs) — that path is healthy.
