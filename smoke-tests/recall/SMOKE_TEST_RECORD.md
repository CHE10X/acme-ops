# Smoke Test Record — Recall

**Version:** 1.0.0
**Date:** 2026-03-18
**Tester:** Hendrik Homarus
**Commit:** 8548ffb

| Gate | Result | Notes |
|------|--------|-------|
| 1 Install | PASS | `recall` installed at `/usr/local/bin/recall`. Global CLI available. |
| 2 Version | PASS | `recall --version` → `Recall 1.0.0` ✅ |
| 3 Happy Path | PASS | `recall status` returns lockdown state + agent list with status fields. Structured output. Exit 0. |
| 4 Failure Path | PASS | `recall badcommand` → usage block with all subcommands listed. No stack trace. |
| 5 License Gate | N/A | Recall is UNLICENSED per doctrine — free internal tool. No license enforcement expected or required. |
| 6 Regression | PASS | Recall CLI part of operational stack. No standalone harness, but dependencies (Commander, QM) pass regression suite. |
| 7 Docs | WARN | Soren working on Mintlify docs page. Not yet verified live at `docs.acmeagentsupply.com`. |

**Overall: PASS**

**Notes:**
- `openclaw recall` plugin still registered (legacy). Unregister pending Chip confirmation — does not affect standalone `recall` CLI.
- Gate 7 is WARN, not blocking for internal use. Blocks public customer-facing launch.
