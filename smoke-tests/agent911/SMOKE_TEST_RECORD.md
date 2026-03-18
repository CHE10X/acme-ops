# Smoke Test Record — Agent911

**Version:** 2.0.0
**Date:** 2026-03-18
**Tester:** Hendrik Homarus
**Commit:** 8548ffb

| Gate | Result | Notes |
|------|--------|-------|
| 1 Install | WARN | Script at `acme-ops/agent911/bin/agent911`. Not installed to `/usr/local/bin` — no global `agent911` command. Customer must run via `python3 path/to/agent911`. Install docs need update. |
| 2 Version | FAIL | `agent911 --version` not implemented. Running `agent911` returns usage block, not version string. `__version__ = "2.0.0"` exists in source but no `--version` flag wired to argparse. |
| 3 Happy Path | PASS | `python3 agent911 reconstruct-diagnose` → structured output: `doctrine_status: ok`, `memory_tree_status: ok`, `checkpoint_availability: 2`. Exit 0. |
| 4 Failure Path | PASS | `python3 agent911 badcommand` → usage block with available commands. No crash, no stack trace. |
| 5 License Gate | N/A | Not a licensed product (install script, not Stripe SKU with feature gating). |
| 6 Regression | PASS | Full regression suite passes (Commander/QM/Transmission layers that agent911 depends on all green). No dedicated agent911 harness exists — dependency harness coverage sufficient. |
| 7 Docs | WARN | Mintlify page at `/docs/products/agent911/overview` — not verified this sprint. |

**Overall: FAIL**

**Findings requiring fix before activation:**
- **Gate 2 FAIL:** Add `--version` to agent911 argparse. Wire to `__version__ = "2.0.0"`. Format: `Agent911 2.0.0`.
- **Gate 1 WARN:** Add install step to global PATH or document `python3` invocation explicitly in install docs.
