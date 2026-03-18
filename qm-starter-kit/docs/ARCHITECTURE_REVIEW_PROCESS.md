# Architecture Review Process
**Status:** ACTIVE — established 2026-03-18  
**Authors:** Chip Ernst + Hendrik Homarus  
**Proven on:** PROJ-2026-001 (Dependency Map), PROJ-2026-002 (Bonfire/Transmission)

---

## The Problem This Solves

Claude reviews Claude. Echo chamber. Blind spots persist. Bad architecture decisions get frozen into doctrine without independent challenge.

This process introduces **Archer** — a GPT-5 council agent — as the adversarial second opinion. Different model family, different blind spots, same workspace.

---

## The Cast

| Role | Agent | Model | Channel | Purpose |
|------|-------|-------|---------|---------|
| **Builder** | Hendrik | Claude | Telegram | Builds, researches, synthesizes, implements |
| **Council** | Archer | GPT-5 | #architecture (Slack) | Adversarial review, verdict, sign-off |
| **Operator** | Chip | Human | Telegram + Slack | Triggers, decides, closes |

**Rule:** Archer and Hendrik never share a channel. Hendrik relays Archer's verdicts via file. Chip is the relay.

---

## The Workflow

### Step 1 — Open a Project
Chip or Hendrik opens a project in `workspace/archer/PROJECTS.md`:
```
PROJ-YYYY-NNN | alias | Name | Date | Active | Description
```

Every project gets a **short alias** (e.g. `depmap`, `bonfire-tx`). Chip never types a full project code.

### Step 2 — Pre-populate the Brief
Hendrik writes `workspace/archer/projects/PROJ-YYYY-NNN-<alias>.md` with:
- The question being reviewed
- All relevant context (both sides of a debate, code locations, prior decisions)
- Specific questions for Archer to answer

**Rule:** Archer should never have to ask "what are we reviewing?" The brief answers that before he wakes up.

### Step 3 — Trigger Archer
Chip types the alias in `#architecture`:
```
review 004
```
Archer resolves alias → reads project brief → produces verdict.

### Step 4 — Archer's Verdict
Archer responds in #architecture with:
1. **Verdict** — one sentence (Pass / Pass with conditions / Fail / Block)
2. **Issues** — numbered, specific
3. **Recommendations** — numbered, opinionated, actionable
4. **Open questions** — only genuinely unresolved ones

### Step 5 — Hendrik Reasons the Verdict ← THE CONTROL LOOP
Chip types `verdict in` to Hendrik on Telegram.  
Hendrik **does not just execute** — Hendrik reasons the verdict:

- **Agree:** "Archer flagged X. He's right because [reason]. Implementation plan: [plan]."
- **Disagree:** "Archer flagged X. I push back because [reason]. Proposed alternative: [alternative]."
- **Gap:** "Archer missed Y — here's what he didn't see in the codebase: [context]. This changes the approach."

Hendrik presents the reasoning to Chip. Chip approves the implementation plan.

**This step is mandatory.** Hendrik is not a relay. Archer's verdict is an input to Hendrik's reasoning, not a direct execution order.

### Deviation Rule
If Hendrik's reasoning constitutes a **material deviation** from Archer's recommendations:

1. Hendrik must make the case back to Archer in #architecture — not to Chip.
2. Archer responds: accepts the argument, rejects it, or modifies the recommendation.
3. If Archer and Hendrik remain deadlocked → Chip referees. Chip's call is final.
4. **Hendrik may not proceed with a deviation until Archer accepts it or Chip overrides.**

A material deviation is: implementing something Archer said to block, skipping a gate Archer said was required, or choosing a fundamentally different approach than Archer recommended.

A non-material deviation is: implementation details Archer didn't specify, tooling choices within an approved approach, sequencing of work within a sprint.

### Step 6 — Build Method Selection
Before building, Hendrik asks Chip:

> "Archer has approved the build packet for [project]. How do you want this built?
> a) Codex — autonomous build agent, best for well-specced mechanical work
> b) Claude Code — interactive coding session, best for complex reasoning during build
> c) Hendrik — I build it directly, best for ops/config/lightweight work
> d) [other] — if a specific tool or agent is better suited"

Chip selects. Hendrik proceeds accordingly.

**Rule:** Hendrik never assumes the build method. Always ask after Archer approval.

### Step 7 — Implement
Hendrik (or the selected builder) builds per the approved plan. Runs regression proofs. All tests must pass.

### Step 8 — Archer Freeze Sign-Off (`freeze <alias>`)
Chip triggers `freeze <alias>` in #architecture.  
Archer reviews the implementation against his original concerns — not a rubber stamp, but confirmation that his issues were actually addressed.  
Archer returns: Approved to freeze / Conditional / Block.

### Step 9 — Close
Archer approves.  
Hendrik updates PROJECTS.md status to Closed, commits, done.

---

## Project Brief Template

```markdown
# PROJ-YYYY-NNN — [Name]
**Alias:** `alias`
**Opened:** YYYY-MM-DD
**Question:** [The specific architectural question being decided]

---

## Context
[Everything Archer needs. Both sides. Code locations. Prior decisions. No fluff.]

## Specific Questions for Archer
1. [Question 1]
2. [Question 2]
3. [Question 3]
```

---

## Archer's Response Format

Archer always responds in this structure. No deviations.

```
Verdict: [Pass / Pass with conditions / Fail]

Issues
1. [Issue — what it is, why it matters]
2. ...

Recommendations
1. [Specific action — opinionated, not "consider"]
2. ...

Open Questions (only if genuinely unresolved)
1. ...
```

---

## Cost Tracking

Archer is pay-per-use (GPT-5). Every session is billed to a project.  
QM reports Archer's cost breakdown every 3 hours if sessions have run.  
Cost log: `workspace/archer/cost_log.jsonl`  
Report script: `workspace/archer/archer_cost_report.py`

---

## File Locations

| File | Purpose |
|------|---------|
| `workspace/archer/SOUL.md` | Archer's identity and operating rules |
| `workspace/archer/BOOT.md` | What Archer reads on activation |
| `workspace/archer/PROJECTS.md` | Project registry with aliases |
| `workspace/archer/projects/PROJ-*.md` | Per-project context briefs |
| `workspace/archer/verdicts/PROJ-*.md` | Archer's verdicts (written after each review) |
| `workspace/archer/cost_log.jsonl` | Per-session cost log |

---

---

## Red Team Reviews (Project Type: `rt-<product>`)

Same loop as architecture reviews. Different question.

**Architecture review:** "Is this design right?"  
**Red team:** "Does this break? What scenarios weren't tested?"

### Trigger

Chip types in #architecture:
```
redteam bonfire
```

Archer resolves `rt-bonfire` → reads red team brief → produces attack report.

### Red Team Brief Template

```markdown
# RT-PROJ-YYYY-NNN — Red Team: [Product]
**Alias:** `rt-<product>`
**Opened:** YYYY-MM-DD
**Target:** [Product name + frozen version/commit]

---

## What's Frozen
[Spec doc location, freeze commit, proof harness location]

## Proof Coverage (what IS tested)
[List existing proof scenarios — what Codex built and proved]

## Known Gaps (already flagged)
[Anything already marked uncertain or untested]

## Production Context (if available)
[Real usage patterns, edge cases seen, operator feedback]

## Archer's Mission
Find what the proofs don't cover. Produce a structured attack report.
Do NOT re-run existing proofs. Find the missing ones.
```

### Red Team Verdict Format

```
Verdict: [Clean / Gaps found / Critical gaps]

Attack Scenarios Not Covered
1. [Scenario — inputs, expected behavior, why it might fail]
2. ...

Recommended New Proofs
1. [Specific test to add — exact scenario, pass criteria]
2. ...

Critical Gaps (block launch)
1. [If any — scenario that could cause data loss, security issue, or silent failure]
```

### Alias Convention

| Alias | Maps to |
|-------|---------|
| `rt-bonfire` | Red team Bonfire telemetry pipeline |
| `rt-transmission` | Red team Transmission router |
| `rt-recall` | Red team Recall CLI |
| `rt-dispatch` | Red team Dispatch v2 |

New aliases added to PROJECTS.md when opened.

### When to Run

- Before any product moves from internal to customer-facing
- After a major freeze (new frozen layer)
- Quarterly against all frozen layers that have production usage
- When a customer reports unexpected behavior

### When NOT to Run

- On products with no frozen spec (nothing to attack against)
- On products with no production usage yet (insufficient real-world context)
- As a substitute for the regression cron (cron catches drift; red team catches gaps)

---

---

## Build Packet Review (Project Type: `bp-<product>`)

**Question:** "What will Codex misinterpret? What's underspecified? What edge cases are missing from the proofs?"

Run this BEFORE sending a build packet to Codex. Cheaper to fix a spec than to fix frozen code.

### Trigger
```
bp transmission-v3
```

### Brief Must Include
- The full build packet doc
- Proof scenarios already defined
- Any known ambiguities or open decisions

### Verdict Format
```
Verdict: [Ready to build / Needs clarification / Block]

Underspecified Items
1. [What's missing — what will Codex guess wrong]

Missing Proof Scenarios
1. [Test case not covered — inputs, expected behavior]

Blocking Issues (must fix before build)
1. [If any]
```

---

## Pre-Freeze Sign-Off (Project Type: `freeze-<product>`)

**Question:** "Does the spec match what was actually built? Does the code do what the doc says?"

Run this AFTER Codex builds, BEFORE freezing. Catches spec/code divergence that proofs don't catch.

### Trigger
```
freeze transmission-v3
```

### Brief Must Include
- The frozen spec doc
- Key implementation files (code locations)
- Proof harness output (pass/fail)
- Any deviations already known

### Verdict Format
```
Verdict: [Approved to freeze / Conditional / Block]

Spec vs Code Divergences
1. [Doc says X, code does Y, proofs test neither]

Conditions for Freeze (if conditional)
1. [What must be resolved before freeze]

Blocking Issues
1. [If any — freeze must not proceed]
```

---

## Build Process Gatekeeping

Archer enforces a strict build and freeze review process. He will block progression to the next stage if prerequisites are unmet or reviews are outstanding.

**Review Sequence enforced by Archer:**
1. **Build Packet Review (`bp <product>`):** Must be `Verdict: Ready to build` before Hendrik sends the build packet to Codex.
2. **Pre-Freeze Sign-Off (`freeze <product>`):** Must be `Verdict: Approved to freeze` or `Conditional` before Hendrik can mark the product as frozen in `REGISTER.md`.

**Enforcement:**
- If an upstream review is outstanding or failed, Archer will `Verdict: Block` the current review.
- **Pushback format:** `Verdict: Block. Prerequisite unmet. [Review Type] ([Project Code]) outstanding/failed. Resolve before proceeding.`

This ensures every product is thoroughly vetted by the designated council (Archer) before critical lifecycle stages.

- Not a rubber stamp. Archer will fail things.
- Not a replacement for Hendrik's judgment. Archer reviews; Hendrik implements.
- Not for ops work. Archer reviews architecture, doctrine, and design decisions only.
- Not for every decision. Reserve Archer for things worth the cost: freezes, convergence decisions, patent-adjacent work, anything that affects multiple layers.

---

## What Makes It Work

1. **The brief is pre-populated.** Archer never spins on "what are we reviewing?"
2. **The alias is short.** Chip types `bonfire-tx`, not `PROJ-2026-002`.
3. **The verdict is structured.** No walls of text. Issues → Recommendations → Open questions.
4. **The file is the relay.** Archer writes to `verdicts/`, Hendrik reads on trigger. No copy-paste required.
5. **Separation of channels.** Archer and Hendrik never share a room. No echo chamber, no conflicting signals.
6. **Fail-open everywhere.** Archer's absence never blocks work. He's council, not gatekeeper.

---

## How We Established This (2026-03-18)

1. Old Archer (ChatGPT subscription) hit his limit and went unreliable
2. Brought Archer in-house on GPT-5 via OpenClaw agent config
3. Created #architecture Slack channel — his home, separate from #product (Soren)
4. First review: dependency map (PROJ-2026-001) — Archer found RadCheck direction was backwards
5. Second review: Bonfire/Transmission router divergence (PROJ-2026-002) — Archer ruled Transmission canonical, governor must be wired
6. Hendrik implemented per verdict: 14/14 proofs, p95=1.77ms
7. Archer signed off. Both projects closed same morning.

The whole loop — open project, brief, trigger, verdict, implement, close — took under 2 hours per project.

---

*Document what works. This works.*
