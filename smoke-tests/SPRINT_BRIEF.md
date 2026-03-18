# Smoke Test Sprint — PROJ-2026-003
**Status:** Active  
**Due:** 2026-03-19 (24hr window from 2026-03-18 11:05 EDT)  
**Owner:** Hendrik  
**Alias:** `smoke-test`

---

## Objective

Run all 7 gates from `docs/process/PRE_RELEASE_SMOKE_TEST_DOCTRINE.md` against all 12 Acme products. Document results in per-product `SMOKE_TEST_RECORD.md` files.

---

## Products (12)

| # | Product | Version | Priority | Notes |
|---|---------|---------|----------|-------|
| 1 | RadCheck | 3.0.0 | HIGH | Live, taking money |
| 2 | Agent911 | 2.0.0 | HIGH | Live, taking money |
| 3 | Sentinel | 1.0.0 | HIGH | Live, taking money |
| 4 | SphinxGate | 1.0.0 | HIGH | Live, taking money |
| 5 | DriftGuard | 1.0.0 | HIGH | Live, taking money |
| 6 | Watchdog | 1.0.0 | HIGH | Live, taking money |
| 7 | Lazarus | 1.0.0 | HIGH | Live, taking money |
| 8 | Recall | 1.0.0 | HIGH | Installed, unlicensed |
| 9 | Bonfire | 1.0.0 | MED | Internal, not sold |
| 10 | Transmission | 2.0.0 | MED | On site as coming soon |
| 11 | Triage | 1.0.0 | MED | OSS + commercial split |
| 12 | Operator Bundle | N/A | LOW | Bundle — test components individually |

---

## Gate Summary (from doctrine)

| Gate | What | Mandatory? |
|------|------|-----------|
| 1 | Install test | Yes |
| 2 | `--version` returns correct string | Yes |
| 3 | Happy path completes, exit 0 | Yes |
| 4 | Bad inputs fail gracefully | Yes |
| 5 | License gate enforced | Yes (if applicable) |
| 6 | Regression harness passes | Yes |
| 7 | Mintlify docs exist and accurate | Public launch only |

---

## Output Per Product

Create `acme-ops/smoke-tests/<product>/SMOKE_TEST_RECORD.md` using the template in the doctrine doc.

---

## Known Gaps (pre-sprint)

- Gates 5 (license) not wired for: Sentinel, DriftGuard, SphinxGate, Watchdog, Lazarus — expect WARN/FAIL
- Gate 7 (docs) blocked for Transmission + Recall — Soren working on it
- Operator Bundle tests components individually — no bundle-level record needed

---

## Definition of Done

- All 12 `SMOKE_TEST_RECORD.md` files written
- PROJECTS.md updated: PROJ-2026-003 → Closed
- REGISTER.md updated with smoke test status per product
- Any FAIL findings logged to INBOX.md for Chip

**Due: 2026-03-19 by 11:05 EDT**
