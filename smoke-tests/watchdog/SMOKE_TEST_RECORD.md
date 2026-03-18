# Smoke Test Record — Watchdog

**Version:** 1.0.0
**Date:** 2026-03-18 (updated post PROJ-2026-008)
**Tester:** Hendrik Homarus
**Commit:** 498820d

| Gate | Result | Notes |
|------|--------|-------|
| 1 Install | WARN | Bash script at `acme-ops/scripts/watchdog/hendrik_watchdog.sh`. No install script. Customer must configure manually. |
| 2 Version | WARN | No `--version` flag. VERSION file has 1.0.0, not surfaced at runtime. |
| 3 Happy Path | PASS | Script runs, acquires lockfile, runs loop. GATEWAY_STALL → `reb_emit "watchdog" "gateway_stall" "HIGH"`. Kickstart → `reb_emit "watchdog" "gateway_kickstart" "INFO"`. |
| 4 Failure Path | PASS | Lockfile prevents concurrent runs. Graceful exit on conflict. |
| 5 License Gate | PASS | Hard-block via acme_license.py. Exit 2 on missing/expired/invalid license. Clear operator message. |
| 6 Regression | PASS | 12/12 regression suite passing. |
| 7 Docs | WARN | Mintlify page at `/docs/products/watchdog/overview` — not re-verified post REB changes. |

**Overall: PASS**

**Post PROJ-2026-008 changes:**
- `reb_emit` bash helper added to script
- GATEWAY_STALL event → REB HIGH
- Gateway kickstart event → REB INFO
- `ops_events.log` writes preserved alongside REB (belt-and-suspenders for v1; ops_events.log retirement in v2)
