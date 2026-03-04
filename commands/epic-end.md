---
name: 'auto-bmad-epic-end'
description: 'Close an epic: trace, retrospective, resolve retro actions, and project context refresh'
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
ELSE ask the user to provide the epic number to close and set {{EPIC_ID}} to the provided value.

# Epic End Pipeline

Close epic {{EPIC_ID}} with BMAD slash commands only — traceability, retrospective, retro action resolution, and project context refresh. Lightweight orchestration with git safety, no reports beyond the pipeline report.

Each step MUST run in its own **foreground Task tool call** (subagent_type: "general-purpose") so that each agent gets a fresh context window.

**CRITICAL — Tool usage rules:**
- **DO** use the Task tool (foreground, default mode) for each step. It blocks and returns the result.
- **DO NOT** use TeamCreate, SendMessage, TaskOutput, TaskCreate, or TaskList. This is a sequential pipeline, not a team collaboration.
- **DO NOT** launch multiple Task calls simultaneously. Wait for each to return before launching the next.
- **DO NOT** execute any step, fix, or implement new code yourself — always delegate to a Task agent.

**Retry policy:** If a step fails, run `git reset --hard HEAD` to discard its partial changes, then retry **once**. If the retry also fails, stop the pipeline and tell the user:
- Which step failed and why
- Recovery commands: `git reset --hard {{START_COMMIT_HASH}}` to roll back the entire pipeline, or `git reset --hard HEAD` to retry the failed step.

# Pre-flight

Before running any steps, record:
- `{{START_TIME}}` — current date+time in ISO 8601 format (e.g. `2026-02-26T14:30:00`)
- `{{START_COMMIT_HASH}}` — run `git rev-parse --short HEAD` and store the result

# Pipeline Steps

After each successful step, the coordinator runs `git add -A && git commit --no-verify -m "wip(epic-{{EPIC_ID}}-end): step N/4 <step-name> - done"` and prints a 1-line progress update: `Step N/4: <step-name> — <status>`. The coordinator must also track a running list of `(step_name, status, start_time, end_time)` — note the wall-clock time before and after each Task call to use in the final report.

1. **Epic {{EPIC_ID}} Trace**
   - **Task prompt:** `/bmad-tea-testarch-trace yolo — run in epic-level mode for epic {{EPIC_ID}}.`

2. **Epic {{EPIC_ID}} Retrospective**
   - **Task prompt:** `/bmad-bmm-retrospective epic {{EPIC_ID}} yolo - and fix all implementable action items required before the next epic, mark them as done/resolved, and defer any non-implementable items with a clear explanation.`

4. **Epic {{EPIC_ID}} Project Context Refresh**
   - **Task prompt:** `/bmad-bmm-generate-project-context yolo`

# Final Commit

1. `git reset --soft {{START_COMMIT_HASH}}` — squash all checkpoint commits, keep changes staged.
2. Commit with: `git add -A && git commit -m "chore(epic-{{EPIC_ID}}): epic end — retro done, actions resolved"`
3. Record the final git commit hash and print it to the user.

**From this point on, do NOT auto-commit.** Only commit when the user explicitly asks you to.

# Pipeline Report

1. Record `{{END_TIME}}` — current date+time in ISO 8601 format.
2. Scan `{{output_folder}}/` recursively for files modified after `{{START_TIME}}` to build the artifact list.
3. Create `{{auto_bmad_artifacts}}/` directory if it doesn't exist.
4. Generate the report and save it to `{{auto_bmad_artifacts}}/epic-{{EPIC_ID}}-end-YYYY-MM-DD-HHMMSS.md` (using `{{END_TIME}}` for the timestamp).
5. Print the full report to the user.

Use this template for the report:

```markdown
# Pipeline Report: epic-end [Epic {{EPIC_ID}}]

| Field | Value |
|-------|-------|
| Pipeline | epic-end |
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
| 1 | Trace | done/failed | Xm | <traceability coverage for the epic> |
| 2 | Retrospective | done/failed | Xm | <top takeaway or improvement identified> |
| 4 | Project Context | done/failed | Xm | <refreshed with epic outcomes> |

## Key Decisions & Learnings

- <short summary of important decisions made, issues encountered, or learnings from any step>

## Action Items

### Review
- [ ] Retrospective findings — validate insights and action items
- [ ] Updated project context — verify accuracy of current state
- [ ] Final squashed commit — review the diff (`git show HEAD`) to confirm all epic changes are correct and complete

### Attention
- [ ] <deferred retro action items — process/team items that couldn't be auto-resolved, e.g. "improve estimation accuracy", "more pair programming">
- [ ] <traceability gaps — e.g. "3 stories lack full requirement coverage", "acceptance criteria partially tested">

### Next
- If more epics remain, start a new session with fresh context and run `/auto-bmad-epic-start <next-epic-number>` to prepare the next epic
- If all epics are done, the project is complete — consider a final end-to-end review
```
