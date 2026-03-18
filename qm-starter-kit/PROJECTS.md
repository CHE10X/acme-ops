# Project Registry
**Format:** `PROJ-YYYY-NNN` with a short alias  
**Owner:** [Your name]

Every agent action with side effects must be tied to a project code.
QM enforces this. No project code = QM blocks and logs the violation.

---

## Active Projects

| Code | Alias | Name | Opened | Status | Description |
|------|-------|------|--------|--------|-------------|
| *(add your first project here)* | | | | | |

---

## Closed Projects

*(none yet)*

---

## Opening a Project

To open a project, add a row above or have an agent submit a `QM_PROJECT_REQUEST` block to their INBOX.md:

```yaml
QM_PROJECT_REQUEST:
  name: "My First Project"
  description: "Brief description of the work"
  owner: agent-1
  collaborators: [agent-2]
```

QM will assign a code and confirm back to the agent.
