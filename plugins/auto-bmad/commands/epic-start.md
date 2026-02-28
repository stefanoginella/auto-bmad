---
name: 'auto-bmad-epic-start'
description: 'Prepare and start a new epic: epic-level test design'
---

# Load Configuration

Read `_bmad/bmm/config.yaml` and `_bmad/tea/config.yaml` and set the following variables (resolve `{project-root}` to the actual project root path):

| Variable | Source | Example |
|----------|--------|---------|
| `{{output_folder}}` | bmm `output_folder` | `_bmad-output` |
| `{{planning_artifacts}}` | bmm `planning_artifacts` | `_bmad-output/planning-artifacts` |
| `{{implementation_artifacts}}` | bmm `implementation_artifacts` | `_bmad-output/implementation-artifacts` |
| `{{test_artifacts}}` | tea `test_artifacts` | `_bmad-output/test-artifacts` |
| `{{auto_bmad_artifacts}}` | derived: `{{output_folder}}/auto-bmad-artifacts` | `_bmad-output/auto-bmad-artifacts` |

All paths in this command that reference BMAD output directories MUST use these variables — never hardcode `_bmad-output` paths.

# Load Project Context

Read `{{output_folder}}/project-context.md` if it exists. This gives you general context about the project — its purpose, stack, conventions, and current state. Use this context to make informed decisions throughout the pipeline.

# Detect Epic Number

An epic number is a single integer identifying the epic (e.g., `1`, `2`, `3`).

IF user provides an epic number:
THEN set {{EPIC_ID}} to the provided number.
ELSE ask the user to provide the epic number to start and set {{EPIC_ID}} to the provided value.

# Epic Start Pipeline

Prepare epic {{EPIC_ID}} with a single BMAD slash command — epic-level test design. Lightweight orchestration with git safety.

The step MUST run in its own **foreground Task tool call** (subagent_type: "general-purpose") so that the agent gets a fresh context window.

**CRITICAL — Tool usage rules:**
- **DO** use the Task tool (foreground, default mode) for the step. It blocks and returns the result.
- **DO NOT** use TeamCreate, SendMessage, TaskOutput, TaskCreate, or TaskList.
- **DO NOT** execute any step, fix, or implement new code yourself — always delegate to a Task agent.

**Retry policy:** If the step fails, run `git reset --hard HEAD` to discard its partial changes, then retry **once**. If the retry also fails, stop the pipeline and tell the user:
- Which step failed and why
- Recovery commands: `git reset --hard {{START_COMMIT_HASH}}` to roll back the entire pipeline, or `git reset --hard HEAD` to retry the failed step.

# Pre-flight

Before running any steps, record:
- `{{START_TIME}}` — current date+time in ISO 8601 format (e.g. `2026-02-26T14:30:00`)
- `{{START_COMMIT_HASH}}` — run `git rev-parse --short HEAD` and store the result

# Pipeline Steps

After each successful step, the coordinator runs `git add -A && git commit --no-verify -m "wip(epic-{{EPIC_ID}}-start): step N/1 <step-name> - done"` and prints a 1-line progress update: `Step 1/1: <step-name> — <status>`. The coordinator must also track `(step_name, status, start_time, end_time)` — note the wall-clock time before and after the Task call to use in the final report.

1. **Epic {{EPIC_ID}} Test Design**
   - **Task prompt:** `/bmad-tea-testarch-test-design yolo — run in epic-level mode for epic {{EPIC_ID}}.`

# Final Commit

1. `git reset --soft {{START_COMMIT_HASH}}` — squash all checkpoint commits, keep changes staged.
2. Commit with: `git add -A && git commit -m "chore(epic-{{EPIC_ID}}): epic start — test design complete"`
3. Record the final git commit hash and print it to the user.

**From this point on, do NOT auto-commit.** Only commit when the user explicitly asks you to.

# Pipeline Report

1. Record `{{END_TIME}}` — current date+time in ISO 8601 format.
2. Scan `{{output_folder}}/` recursively for files modified after `{{START_TIME}}` to build the artifact list.
3. Create `{{auto_bmad_artifacts}}/` directory if it doesn't exist.
4. Generate the report and save it to `{{auto_bmad_artifacts}}/epic-{{EPIC_ID}}-start-YYYY-MM-DD-HHMMSS.md` (using `{{END_TIME}}` for the timestamp).
5. Print the full report to the user.

Use this template for the report:

```markdown
# Pipeline Report: epic-start [Epic {{EPIC_ID}}]

| Field | Value |
|-------|-------|
| Pipeline | epic-start |
| Epic | {{EPIC_ID}} |
| Start | {{START_TIME}} |
| End | {{END_TIME}} |
| Duration | <minutes>m |
| Initial Commit | {{START_COMMIT_HASH}} |

## Artifacts

- `<relative-path>` — new/updated

## Pipeline Outcome

| # | Step | Status | Duration | Summary |
|---|------|--------|----------|---------|
| 1 | Epic Test Design | done/failed | Xm | <test areas planned, strategy summary> |

## Key Decisions & Learnings

- <short summary of important decisions made, issues encountered, or learnings from any step>

## Action Items

### Review
- [ ] Epic-level test design coverage and strategy
- [ ] Sprint backlog — confirm the stories queued for this epic are correctly scoped and prioritized before starting development

### Attention
- [ ] <testing assumptions — e.g. "assumes test database is available", "mock services needed for integration tests">
- [ ] <missing test scenarios — e.g. "no load testing planned", "error recovery paths not covered">
- [ ] <environment dependencies — e.g. "requires Docker for containerized tests", "needs API keys for third-party services">

### Next
- Start a new session with fresh context for each story, then run `/auto-bmad-story <epic-story>` (e.g. `/auto-bmad-story 1-1`, then `1-2`, etc.)
- After all stories are done, start a new session and run `/auto-bmad-epic-end <epic-number>` to close the epic
```
