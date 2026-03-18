# Smoke Test Record — RadCheck

**Version:** 3.0.0
**Date:** 2026-03-18
**Tester:** Hendrik Homarus
**Commit:** 8548ffb

| Gate | Result | Notes |
|------|--------|-------|
| 1 Install | PASS | `openclaw plugins install radcheck-cli` installs cleanly. `radcheck` available in PATH post-install. |
| 2 Version | PASS | `radcheck --version` → `RadCheck 3.0.0` ✅ |
| 3 Happy Path | PASS | `radcheck score` returns score, status, and signals. Exit 0. Output human-readable and structured. |
| 4 Failure Path | PASS | `radcheck badcommand` → usage help + error message. No stack trace. |
| 5 License Gate | N/A | Free tier product. No license enforcement required. |
| 6 Regression | PASS | `test_reliability_score.py` — 5 assertion functions, all pass. Import path fix applied this session (added `__init__.py` + `sys.path` correction). |
| 7 Docs | WARN | Mintlify page at `/docs/products/radcheck/overview` — contents not verified this sprint. Soren owns docs. |

**Overall: PASS**

**Notes:**
- Gate 6 fix applied 2026-03-18: `__init__.py` added to `openclaw-ops/radcheck/` and `openclaw-ops/radcheck/analysis/` to make importable as package. Test path corrected to `parents[2]` (openclaw-ops root).
- Gate 2: version 3.0.0 is intentional — confirmed with Chip 2026-03-17. Versioning doctrine documented in ACME_PRODUCT_VERSIONING_DOCTRINE.md.
