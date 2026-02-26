---
name: 'auto-bmad-epic-start'
description: 'Prepare and start a new epic: resolve previous retro actions, establish baseline, and plan'
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

# Detect Epic Number

An epic number is a single integer identifying the epic (e.g., `1`, `2`, `3`).

IF user provides an epic number:
THEN set {{EPIC_ID}} to the provided number.
ELSE ask the user to provide the epic number to start and set {{EPIC_ID}} to the provided value.

Derive {{PREV_EPIC_ID}} as `{{EPIC_ID}} - 1` (used to check the previous epic's state). If {{EPIC_ID}} is 1, there is no previous epic.

# Process

Prepare and start epic {{EPIC_ID}} by resolving previous-epic cleanup, establishing a green baseline, and planning the epic's work.

Each step MUST run in its own **foreground Task tool call** (subagent_type: "general-purpose") so that each agent gets a fresh context window. The Task tool in foreground mode blocks until the agent completes and returns its result directly — use this return value to determine success/failure before proceeding to the next step.

**CRITICAL — Tool usage rules:**
- **DO** use the Task tool (foreground, default mode) for each step. It blocks and returns the result.
- **DO NOT** use TeamCreate, SendMessage, TaskOutput, TaskCreate, or TaskList. This is a sequential pipeline, not a team collaboration.
- **DO NOT** launch multiple Task calls simultaneously. Wait for each to return before launching the next.
- **DO NOT** execute any step yourself — always delegate to a Task agent.

**Retry policy:** If a step fails, retry it **once**. If the retry also fails, stop the pipeline, save a partial report with the failure details, and report to the user which step failed and why.

**`yolo` suffix:** Every step prompt ends with `yolo` to bypass agent confirmation prompts for fully autonomous execution, using the available context to take the best decisions.

## Pre-flight

1. Clean `{project_root}/.tmp/` if it exists from a previous failed run.
2. Record the starting git commit hash as {{START_COMMIT_HASH}}.
3. Create a recovery tag: `git tag -f pipeline-start-epic-{{EPIC_ID}}` so the pipeline can be rolled back with `git reset --hard pipeline-start-epic-{{EPIC_ID}}` if needed.
4. Read `{{implementation_artifacts}}/sprint-status.yaml` and verify:
   - The epic {{EPIC_ID}} exists in the sprint plan.
   - The epic is not already marked `done`.
   - If the epic is already `in-progress`, warn but continue (this may be a resume).

## Failure & Recovery

If the pipeline fails after retries and stops:
1. Save a partial report (see Report section) noting which step failed.
2. Print the recovery tag: `To roll back all changes: git reset --hard pipeline-start-epic-{{EPIC_ID}}`
3. Print the partial report path so the user can review what happened.

Do NOT automatically roll back — leave the working tree as-is so the user can inspect and decide.

# Pipeline Introduction

Each step is a separate foreground Task call with these parameters:

| Parameter | Value |
|-----------|-------|
| `description` | The step name (e.g., "Epic 3 Lint Baseline") |
| `subagent_type` | `general-purpose` |
| `prompt` | The step's prompt text (in backticks below), with the Step Output Format appended |

## Step Output Format

Append the following to every Task prompt so the coordinator gets structured output for the report:

> When you are done, end your response with a `## Step Summary` section containing: **Status** (success/failure), **Duration** (wall-clock time from start to finish of your work, approximate), **What changed** (files created/modified/deleted), **Key decisions** (any non-obvious choices made), **Issues found & fixed** (count and brief description), **Remaining concerns** (if any).

## Handoff Protocol

Steps that produce values consumed by later steps MUST end their output with a `## Handoff` section (after `## Step Summary`) containing key-value pairs. The coordinator extracts these values and injects them into downstream step prompts.

Required handoffs:
- **Step 1 (Previous Retro Check)** → `ACTION_ITEMS: <list>` or `ACTION_ITEMS: none` — consumed by step 2 to determine what to fix
- **Step 4 (Test Baseline)** → `TEST_COUNT: <N>` — recorded in the report as the epic's starting test count

## Progress Reporting

After each step completes, the coordinator MUST print a 1-line progress update before launching the next step:

Format: `Step N/TOTAL: <step-name> — <status>`

TOTAL is the number of pipeline steps for this run (typically 7, fewer if {{EPIC_ID}} is 1 and previous-epic steps are skipped). This gives the user continuous visibility into pipeline progress.

## Checkpoint Commits

The coordinator creates checkpoint commits at key milestones using the bash command `git add -A && git commit -m "<message>"` directly. Use exact commit messages as shown — these are temporary markers that get squashed at the end. Checkpoints are marked with `>>> CHECKPOINT` below.

**Note:** Checkpoint commits intentionally bypass pre-commit hooks — they are temporary markers that get squashed into the final commit.

At the end of the pipeline, squash all checkpoint commits into a single clean commit.

# Pipeline Steps

## Skip Condition Evaluation

The coordinator evaluates all skip conditions **before** launching each Task, using pre-flight data and prior step outputs. If a skip condition is met, the coordinator logs the skip reason in the progress report and moves to the next step — no Task agent is launched.

When a step is skipped, the coordinator still records it in the report with status "skipped" and the reason.

## Previous Epic Gate

1. **Epic {{EPIC_ID}} Previous Retro Check**
   - **Skip if:** {{EPIC_ID}} is 1 (no previous epic). Log "First epic — no previous retro to check". Set `{{ACTION_ITEMS}}` to `"none"`.
   - **Task prompt:** `Read {{implementation_artifacts}}/sprint-status.yaml and check the status of epic-{{PREV_EPIC_ID}} and its retrospective. Then search for the retro file at {{auto_bmad_artifacts}}/epic-{{PREV_EPIC_ID}}-retro-*.md and {{implementation_artifacts}}/epic-{{PREV_EPIC_ID}}-retro-*.md. Report: (a) whether epic {{PREV_EPIC_ID}} is marked done, (b) whether a retrospective file exists, (c) if a retro exists, extract all Action Items, Preparation Tasks, and Team Agreements from it. Also collect any story reports (story-{{PREV_EPIC_ID}}-*-report.md in {{auto_bmad_artifacts}}/ and {{implementation_artifacts}}/) and summarize aggregate findings: total code review issues found/fixed, any remaining concerns, any tech debt items. Present a consolidated list of actionable items for the coordinator. End with a ## Handoff section containing ACTION_ITEMS: <numbered list of items, or "none" if no action items found>. yolo`

Based on the retro check output, the coordinator categorizes action items by priority:
- **Critical**: Must be resolved before starting epic {{EPIC_ID}} (e.g., broken tests, blocking tech debt).
- **Recommended**: Should be addressed but non-blocking (e.g., design patterns to establish, process improvements).
- **Nice-to-have**: Low-priority cleanup items.

2. **Epic {{EPIC_ID}} Tech Debt Cleanup**
   - **Skip if:** step 1 was skipped OR step 1 reported no action items (empty list or `ACTION_ITEMS: none`). Log "No action items to resolve — skipping tech debt cleanup".
   - **Task prompt:** `The following critical and recommended action items were identified from the epic {{PREV_EPIC_ID}} retrospective. Address each one: {{ACTION_ITEMS}}. Fix broken tests, resolve tech debt, and implement any critical preparation tasks. For recommended items, implement what can be done quickly and note anything deferred. Refer to {{output_folder}}/project-context.md or CLAUDE.md for project conventions. yolo`

>>> CHECKPOINT: `wip(epic-{{EPIC_ID}}): previous epic action items resolved`

## Baseline Verification

3. **Epic {{EPIC_ID}} Lint Baseline**
   - **Skip if:** {{EPIC_ID}} is 1 (no code exists yet to lint). Log "First epic — no code to lint". Set baseline lint status to "N/A".
   - **Task prompt:** `Run the project's linters, formatters, type-checkers, and migration integrity checks. This is a Docker-based project — all commands MUST run inside Docker containers (e.g., docker compose exec backend …, docker compose exec frontend …). NEVER run linters, formatters, or type-checkers directly on the host. Refer to {{output_folder}}/project-context.md or CLAUDE.md for exact commands. Automatically fix all issues. The goal is a completely green baseline before starting any new epic work. yolo`
4. **Epic {{EPIC_ID}} Test Baseline**
   - **Skip if:** {{EPIC_ID}} is 1 (no tests exist yet). Log "First epic — no tests to run". Set `{{BASELINE_TEST_COUNT}}` to `0`.
   - **Task prompt:** `Run all tests and verify that ALL tests pass — zero failures allowed. This is a Docker-based project — all commands MUST run inside Docker containers (e.g., docker compose exec backend …, docker compose exec frontend …). NEVER run pytest, vitest, or any test runner directly on the host. Refer to {{output_folder}}/project-context.md or CLAUDE.md for exact commands. Automatically fix any failures. Report the total test count and pass rate. End with a ## Handoff section containing TEST_COUNT: <total number of tests that ran>. yolo`

>>> CHECKPOINT: `wip(epic-{{EPIC_ID}}): green baseline established`

## Epic Planning

5. **Epic {{EPIC_ID}} Overview Review**: `Read the epic {{EPIC_ID}} section from {{planning_artifacts}}/epics.md (or epics/ directory). For each story in the epic, analyze: (a) story count and IDs, (b) acceptance criteria count per story — flag any story with more than 8 ACs as oversized and recommend splitting, (c) dependency chains between stories — identify which must be sequential vs. can be parallel, (d) any dependencies on other epics (should already be met by completed epics). Also read the architecture docs to identify any design patterns or components this epic introduces that should be established early. Present a prioritized story order with rationale. yolo`

6. **Epic {{EPIC_ID}} Sprint Status Update**: `Read {{implementation_artifacts}}/sprint-status.yaml and update epic-{{EPIC_ID}} status from "backlog" to "in-progress". Do not change any other statuses. Write the updated file. yolo`

>>> CHECKPOINT: `wip(epic-{{EPIC_ID}}): epic planned and sprint status updated`

## Epic-Level Test Design (Optional)

7. **Epic {{EPIC_ID}} Test Design**
   - **Skip if:** the epic has 3 or fewer stories **and** no inter-story dependencies were identified (coordinator checks both story count and dependency chains from the step 5 overview output). Log "Small epic with no cross-story dependencies — story-level ATDD is sufficient".
   - **Task prompt:** `/bmad-tea-testarch-test-design yolo — run in epic-level mode for epic {{EPIC_ID}}. Read the epic and its stories from {{planning_artifacts}}/epics.md. Produce a risk-based test plan at {{planning_artifacts}}/test-design-epic-{{EPIC_ID}}.md. If a system-level test design already exists (test-design-architecture.md, test-design-qa.md), use it as context.`

>>> CHECKPOINT: `wip(epic-{{EPIC_ID}}): test design complete`

# Report

**Generate the report BEFORE the final commit** so it is included in the squashed commit alongside the artifacts.

Compile the report from the Step Summary sections collected from each agent. Use this template:

```markdown
# Epic {{EPIC_ID}} Start Report

## Overview
- **Epic**: {{EPIC_ID}} — [epic title from epics.md]
- **Git start**: `{{START_COMMIT_HASH}}`
- **Pipeline result**: success | partial failure at step N
- **Previous epic retro**: reviewed | no retro found | N/A (first epic)
- **Baseline test count**: {{BASELINE_TEST_COUNT}}

## Previous Epic Action Items
If a retro was reviewed, list each action item and its resolution:

| # | Action Item | Priority | Resolution |
|---|------------|----------|------------|
| 1 | ... | Critical/Recommended/Nice-to-have | Fixed / Deferred / N/A |

## Baseline Status
- **Lint**: pass/fail — details
- **Tests**: X/Y passing (Z fixed during cleanup)
- **Migrations**: consistent/issues

## Epic Analysis
- **Stories**: N stories (list IDs and titles)
- **Oversized stories** (>8 ACs): list any flagged for splitting
- **Dependencies**: inter-story and cross-epic dependencies
- **Design patterns needed**: any architectural patterns to establish early
- **Recommended story order**: prioritized sequence with rationale

## Test Design
- **Epic test plan**: path | skipped (small epic)
- **Key risks identified**: list from test design

## Pipeline Steps

For each step that ran:

### Step N: Step Name
- **Status**: success/failure/skipped
- **Duration**: approximate wall-clock time
- **What changed**: files created/modified/deleted
- **Key decisions**: any non-obvious choices made
- **Issues found & fixed**: count and description (if any)
- **Remaining concerns**: (if any)

## Ready to Develop
Checklist of readiness conditions:
- [ ] All critical retro actions resolved
- [ ] Lint and tests green (zero failures)
- [ ] Sprint status updated (epic in-progress)
- [ ] Story order established

## Next Steps
First story to implement and any preparation notes.

---

## TL;DR
3-4 sentence executive summary: what was prepared, baseline status, and whether the epic is ready to start.
```

Save it as `epic-{{EPIC_ID}}-start-report.md` in `{{auto_bmad_artifacts}}/`.

# Final Commit

After the report is saved, squash all checkpoint commits and create one clean commit:

1. `git reset --soft {{START_COMMIT_HASH}}` — undoes all checkpoint commits but keeps all changes staged.
2. `/commit-commands:commit chore(epic-{{EPIC_ID}}): epic start — baseline green, retro actions resolved` — creates a single clean commit.
3. Record the final git commit hash as {{FINAL_COMMIT_HASH}} and print it to the user.
4. Clean up the recovery tag: `git tag -d pipeline-start-epic-{{EPIC_ID}}`

# Filesystem Boundary

Agents and coordinator MUST NOT write files outside the project root. For temporary files, use `{project_root}/.tmp/` (created on demand, cleaned by the coordinator after each step completes). Never use `/tmp`, `$TMPDIR`, or other system-level temp directories.
