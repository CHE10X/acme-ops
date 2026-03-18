# Smoke Test Record — Watchdog

**Version:** 1.0.0
**Date:** 2026-03-18
**Tester:** Hendrik Homarus
**Commit:** 8548ffb

| Gate | Result | Notes |
|------|--------|-------|
| 1 Install | WARN | `acme-ops/scripts/watchdog/hendrik_watchdog.sh` — bash script, no install mechanism. Customer must copy/configure manually. No documented install path. |
| 2 Version | WARN | No `--version` flag. VERSION file at `acme-ops/scripts/watchdog/VERSION` (1.0.0) not surfaced at runtime. |
| 3 Happy Path | PASS | `hendrik_watchdog.sh` is a bash watchdog loop. Starts, acquires lockfile, runs loop logic. Runs correctly when invoked directly. |
| 4 Failure Path | PASS | Lockfile prevents concurrent runs (`_LOCK_FILE` check with PID validation). Graceful exit on lock conflict. |
| 5 License Gate | FAIL | No license enforcement wired. Pre-identified gap. |
| 6 Regression | WARN | No dedicated watchdog regression harness. Not in daily suite. Functional scripts tested manually. |
| 7 Docs | WARN | Mintlify page at `/docs/products/watchdog/overview` — not verified this sprint. |

**Overall: FAIL**

**Findings requiring fix before activation:**
- **Gate 5 FAIL:** License gate not wired. Known pre-sprint gap.
- **Gate 1 WARN:** No install script or documented install path for customers.
- **Gate 2 WARN:** `--version` not surfaced at runtime.
