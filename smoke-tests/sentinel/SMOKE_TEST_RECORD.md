# Smoke Test Record — Sentinel

**Version:** 1.0.0
**Date:** 2026-03-18 (updated post PROJ-2026-008)
**Tester:** Hendrik Homarus
**Commit:** 498820d

| Gate | Result | Notes |
|------|--------|-------|
| 1 Install | PASS | `acme-ops/scripts/sentinel/install.sh` present. Install script structured with VERSION="1.0.0". |
| 2 Version | WARN | No `--version` CLI flag. VERSION in install.sh and VERSION file only. Not surfaced at runtime. |
| 3 Happy Path | PASS | `sentinel_attach_bridge.py` → structured JSON + REB emit (`source=sentinel event=attach_bridge`). `sentinel_funnel_alignment.py` → ALIGNMENT_OK + REB emit (`source=sentinel event=funnel_alignment`). Both exit 0. |
| 4 Failure Path | PASS | Bad args → argparse error, clean failure, no stack trace. |
| 5 License Gate | PASS | Hard-block via acme_license.py. Exit 2 on missing/expired/invalid license. Clear operator message. |
| 6 Regression | PASS | 12/12 regression suite passing. |
| 7 Docs | WARN | Mintlify page at `/docs/products/sentinel/overview` — not re-verified post REB changes. |

**Overall: PASS**

**Post PROJ-2026-008 changes:**
- REB emit added to `sentinel_attach_bridge.py`: emits `attach_bridge` event (INFO or HIGH based on confidence)
- REB emit added to `sentinel_funnel_alignment.py`: emits `funnel_alignment` event (INFO/WARN/HIGH based on alignment state)
- Graceful fallback: if reb.py unavailable, emit is silently skipped — Sentinel never fails due to REB
