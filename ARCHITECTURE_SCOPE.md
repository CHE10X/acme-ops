# ARCHITECTURE SCOPE
## acme-ops — Acme Reliability Platform

This repository contains the operational reliability platform for Acme.

---

## Components

| Component | Purpose |
|-----------|---------|
| **Bonfire** | Telemetry + routing observability |
| **RadCheck** | Reliability diagnostics and predictive risk |
| **OCTriage** | Deterministic proof bundles for incident investigation |
| **Agent911** | Recovery planner — diagnose, plan, execute, rollback |
| **openclaw watch** | Live operator monitoring surface |
| **openclaw health** | Reliability summary snapshot |

---

## Scope Rule

This repository contains **things customers run**.

Product-grade code only:
- Released components
- Operator tooling
- Install and packaging tooling
- Operator documentation

---

## What Belongs Here

- Bonfire telemetry system
- RadCheck v2/v3 diagnostics engine
- OCTriage proof bundle system
- Agent911 recovery planner
- `openclaw watch` / `openclaw health` operator commands
- Operator docs (`docs/operators/`)
- Release packaging and install tooling

## What Does Not Belong Here

- Internal experiments
- Architecture drafts
- Memory system
- Agent orchestration scaffolding
- Prototypes

Internal work lives in `homarus-eximius`.

---

## Repo Taxonomy

| Repo | Type | Purpose |
|------|------|---------|
| `acme-site` | Product | Customer-facing website |
| `acme-support` | Product | Support infrastructure |
| `octriageunit` | Product | OCTriage product |
| `acme-ops` | Product | Reliability platform (this repo) |
| `homarus-eximius` | Internal | Lab, brain, workshop |
| `Ernst-home` | Personal | Personal/home automation |
