---
name: 'epic-end'
description: 'Close an epic: aggregate story data, run retrospective, traceability gate, and prepare for next epic'
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
ELSE ask the user to provide the epic number to close and set {{EPIC_ID}} to the provided value.

Derive {{NEXT_EPIC_ID}} as `{{EPIC_ID}} + 1` (used for next-epic preview).

# Process

Close epic {{EPIC_ID}} by verifying completion, aggregating story data, running the retrospective, and assessing readiness for the next epic.

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
3. Create a recovery tag: `git tag -f pipeline-end-epic-{{EPIC_ID}}` so the pipeline can be rolled back with `git reset --hard pipeline-end-epic-{{EPIC_ID}}` if needed.
4. Read `{{implementation_artifacts}}/sprint-status.yaml` and verify:
   - The epic {{EPIC_ID}} exists and is `in-progress` or `done`.
   - If the retrospective is already marked `done`, warn and ask the user whether to re-run or skip.

## Failure & Recovery

If the pipeline fails after retries and stops:
1. Save a partial report (see Report section) noting which step failed.
2. Print the recovery tag: `To roll back all changes: git reset --hard pipeline-end-epic-{{EPIC_ID}}`
3. Print the partial report path so the user can review what happened.

Do NOT automatically roll back — leave the working tree as-is so the user can inspect and decide.

# Pipeline Introduction

Each step is a separate foreground Task call with these parameters:

| Parameter | Value |
|-----------|-------|
| `description` | The step name (e.g., "Epic 3 Traceability Gate") |
| `subagent_type` | `general-purpose` |
| `prompt` | The step's prompt text (in backticks below), with the Step Output Format appended |

## Step Output Format

Append the following to every Task prompt so the coordinator gets structured output for the report:

> When you are done, end your response with a `## Step Summary` section containing: **Status** (success/failure), **Duration** (wall-clock time from start to finish of your work, approximate), **What changed** (files created/modified/deleted), **Key decisions** (any non-obvious choices made), **Issues found & fixed** (count and brief description), **Remaining concerns** (if any).

## Handoff Protocol

Steps that produce values consumed by later steps MUST end their output with a `## Handoff` section (after `## Step Summary`) containing key-value pairs. The coordinator extracts these values and injects them into downstream step prompts.

Required handoffs:
- **Step 1 (Completion Check)** → `COMPLETION_STATUS: all_done | incomplete` and `INCOMPLETE_STORIES: <list or "none">` — coordinator uses this to decide whether to ask the user to proceed or stop
- **Step 2 (Aggregate Story Data)** → `AGGREGATE_SUMMARY: <structured summary>` — consumed by step 6 (retrospective) as input context
- **Step 3 (Traceability Gate)** → `GATE_RESULT: PASS | CONCERNS | FAIL` — consumed by step 6 (retrospective)
- **Step 5 (Final Test)** → `TEST_COUNT: <N>` — recorded in the report as the epic's ending test count

## Progress Reporting

After each step completes, the coordinator MUST print a 1-line progress update before launching the next step:

Format: `Step N/TOTAL: <step-name> — <status>`

TOTAL is 10 for this pipeline. This gives the user continuous visibility into pipeline progress.

## Checkpoint Commits

The coordinator creates checkpoint commits at key milestones using the bash command `git add -A && git commit -m "<message>"` directly. Use exact commit messages as shown — these are temporary markers that get squashed at the end. Checkpoints are marked with `>>> CHECKPOINT` below.

**Note:** Checkpoint commits intentionally bypass pre-commit hooks — they are temporary markers that get squashed into the final commit.

At the end of the pipeline, squash all checkpoint commits into a single clean commit.

# Pipeline Steps

## Completion Gate

1. **Epic {{EPIC_ID}} Completion Check**: `Read {{implementation_artifacts}}/sprint-status.yaml and check the status of every story in epic {{EPIC_ID}}. List each story with its current status. Report: (a) how many stories are "done" vs total, (b) any stories NOT marked "done" — list them with their current status. If all stories are done, report "All stories complete". If some are not done, list the incomplete stories so the coordinator can decide whether to proceed. End with a ## Handoff section containing COMPLETION_STATUS: all_done or incomplete, and INCOMPLETE_STORIES: <comma-separated list of story IDs, or "none">. yolo`

If the completion check reports incomplete stories, the coordinator asks the user:
- Proceed with the epic-end pipeline anyway (incomplete stories will be noted in the report)?
- Or stop and complete the remaining stories first?

## Story Data Aggregation

2. **Epic {{EPIC_ID}} Aggregate Story Data**: `Collect all available data from epic {{EPIC_ID}} stories. Search for: (a) story report files matching story-{{EPIC_ID}}-*-report.md in {{auto_bmad_artifacts}}/ and {{implementation_artifacts}}/, (b) story spec files matching {{EPIC_ID}}-*-.md in {{implementation_artifacts}}/. From these, compile an aggregate summary: total stories delivered, total code review issues found and fixed (by severity if available), total tests written, NFR assessment results, traceability gate results, any remaining concerns or known gaps across all stories, and any migrations created. Present this as a structured data summary the coordinator can pass to subsequent steps. End with a ## Handoff section containing AGGREGATE_SUMMARY: <the structured summary>. yolo`

## Epic-Level Traceability Gate

3. **Epic {{EPIC_ID}} Traceability Gate**: `/bmad-tea-testarch-trace yolo — run in epic-level mode (gate_type: "epic") for epic {{EPIC_ID}}. Read all story files for this epic from {{implementation_artifacts}}/ (files matching {{EPIC_ID}}-*). Build an aggregate traceability matrix mapping every acceptance criterion across all stories to their test coverage. Apply the gate decision rules: P0 coverage must be 100%, overall coverage must be ≥80%, P1 coverage must be ≥80%. Report the gate decision (PASS/CONCERNS/FAIL) and list any uncovered acceptance criteria. End with a ## Handoff section containing GATE_RESULT: PASS, CONCERNS, or FAIL.`

>>> CHECKPOINT: `wip(epic-{{EPIC_ID}}-end): data aggregated, traceability gate complete`

## Regression Verification

4. **Epic {{EPIC_ID}} Final Lint**: `Run the project's linters, formatters, type-checkers, and migration integrity checks. This is a Docker-based project — all commands MUST run inside Docker containers (e.g., docker compose exec backend …, docker compose exec frontend …). NEVER run linters, formatters, or type-checkers directly on the host. Refer to {{output_folder}}/project-context.md or CLAUDE.md for exact commands. Automatically fix all issues. yolo`
5. **Epic {{EPIC_ID}} Final Test**: `Run all tests and verify that ALL tests pass — zero failures allowed. This is a Docker-based project — all commands MUST run inside Docker containers (e.g., docker compose exec backend …, docker compose exec frontend …). NEVER run pytest, vitest, or any test runner directly on the host. Refer to {{output_folder}}/project-context.md or CLAUDE.md for exact commands. Automatically fix any failures. Report the total test count and pass rate. End with a ## Handoff section containing TEST_COUNT: <total number of tests that ran>. yolo`

>>> CHECKPOINT: `wip(epic-{{EPIC_ID}}-end): final regression passing`

## Retrospective

6. **Epic {{EPIC_ID}} Retrospective**: `/bmad-bmm-retrospective epic {{EPIC_ID}} yolo — run the retrospective for epic {{EPIC_ID}}. Use the following aggregated context from the pipeline to inform the retro: {{AGGREGATE_SUMMARY}} [if step 2 found no story data, pass "No story reports or mission control data found — retro should rely on the codebase and sprint-status.yaml"]. Also consider: traceability gate result from step 3 ({{GATE_RESULT}}), final test count and pass rate from step 5 ({{FINAL_TEST_COUNT}}), and any incomplete stories from step 1 ({{INCOMPLETE_STORIES}}). The retro should cover: successes, challenges, key insights, action items, preparation tasks for the next epic, and team agreements.`

>>> CHECKPOINT: `wip(epic-{{EPIC_ID}}-end): retrospective complete`

## Sprint Status Update

7. **Epic {{EPIC_ID}} Status Update**: `Read {{implementation_artifacts}}/sprint-status.yaml and update: (a) epic-{{EPIC_ID}} status to "done", (b) epic-{{EPIC_ID}}-retrospective status to "done". Do not change any other statuses. Write the updated file. yolo`

## Next Epic Preview

8. **Epic {{EPIC_ID}} Next Epic Preview**: `Read {{planning_artifacts}}/epics.md (or epics/ directory) and find epic {{NEXT_EPIC_ID}}. If it exists, provide: (a) epic title and description, (b) number of stories and their IDs, (c) dependencies on completed epics — verify each dependency is met based on sprint-status.yaml, (d) any new technical requirements or patterns this epic introduces, (e) any action items from the epic {{EPIC_ID}} retrospective that must be addressed before starting epic {{NEXT_EPIC_ID}}. If epic {{NEXT_EPIC_ID}} does not exist, report "No next epic — this was the final epic in the sprint plan". yolo`

## Project Context Refresh

9. **Epic {{EPIC_ID}} Project Context Refresh**: `/bmad-bmm-generate-project-context yolo — rescan the codebase and regenerate {{output_folder}}/project-context.md to reflect the current state after all epic work.`
10. **Epic {{EPIC_ID}} Improve CLAUDE.md**: `/claude-md-management:claude-md-improver yolo — audit and improve CLAUDE.md using the freshly generated {{output_folder}}/project-context.md as reference. IMPORTANT: CLAUDE.md must NOT duplicate content that already exists in project-context.md, since project-context.md is automatically loaded by all BMAD workflows. Focus CLAUDE.md on high-level pointers, setup instructions, and anything NOT covered by project-context.md. Remove any overlapping rules, conventions, or patterns that are already in project-context.md.`

>>> CHECKPOINT: `wip(epic-{{EPIC_ID}}-end): status updated, next epic previewed, project context refreshed`

# Report

**Generate the report BEFORE the final commit** so it is included in the squashed commit alongside the artifacts.

Compile the report from the Step Summary sections collected from each agent. Use this template:

```markdown
# Epic {{EPIC_ID}} End Report

## Overview
- **Epic**: {{EPIC_ID}} — [epic title from epics.md]
- **Git start**: `{{START_COMMIT_HASH}}`
- **Pipeline result**: success | partial failure at step N
- **Stories**: N/M completed (list any incomplete)
- **Final test count**: {{FINAL_TEST_COUNT}}

## What Was Built
Brief description of what this epic delivered (2-4 sentences from the epic spec).

## Stories Delivered
| Story | Title | Status |
|-------|-------|--------|
| {{EPIC_ID}}-1 | ... | done/incomplete |
| {{EPIC_ID}}-2 | ... | done/incomplete |
| ... | ... | ... |

## Aggregate Code Review Findings
Combined across all story code reviews:

| Metric | Value |
|--------|-------|
| Total issues found | ... |
| Total issues fixed | ... |
| Critical | ... |
| High | ... |
| Medium | ... |
| Low | ... |
| Remaining unfixed | ... |

## Test Coverage
- **Total tests**: N (backend: X, frontend: Y)
- **Pass rate**: 100% (or details on failures)
- **Migrations**: list any Alembic migrations created across all stories

## Quality Gates
- **Epic Traceability**: {{GATE_RESULT}} — coverage % (P0: X%, P1: Y%, Overall: Z%)
- **Uncovered ACs**: list any acceptance criteria without test coverage
- **Final Lint**: pass/fail
- **Final Tests**: X/Y passing

## Retrospective Summary
Key takeaways from the retrospective:
- **Top successes**: ...
- **Top challenges**: ...
- **Key insights**: ...
- **Critical action items for next epic**: ...

## Pipeline Steps

For each step that ran:

### Step N: Step Name
- **Status**: success/failure/skipped
- **Duration**: approximate wall-clock time
- **What changed**: files created/modified/deleted
- **Key decisions**: any non-obvious choices made
- **Issues found & fixed**: count and description (if any)
- **Remaining concerns**: (if any)

## Project Context & CLAUDE.md
- **Project context**: refreshed | skipped
- **CLAUDE.md**: improved | skipped

## Next Epic Readiness
- **Next epic**: {{NEXT_EPIC_ID}} — [title] | No next epic
- **Dependencies met**: yes/no — list any unmet dependencies
- **Prep tasks**: list from retrospective action items
- **Recommended next step**: `auto-bmad-epic {{NEXT_EPIC_ID}}` | Project complete

## Known Risks & Tech Debt
Consolidated list of tech debt, known gaps, and risks carried forward.

---

## TL;DR
3-4 sentence executive summary: what was delivered, quality gate results, and readiness for next epic.
```

Save it as `epic-{{EPIC_ID}}-end-report.md` in `{{auto_bmad_artifacts}}/`.

# Final Commit

After the report is saved, squash all checkpoint commits and create one clean commit:

1. `git reset --soft {{START_COMMIT_HASH}}` — undoes all checkpoint commits but keeps all changes staged.
2. `/commit-commands:commit chore(epic-{{EPIC_ID}}): epic complete — retro done, ready for epic {{NEXT_EPIC_ID}}` — creates a single clean commit.
3. Record the final git commit hash as {{FINAL_COMMIT_HASH}} and print it to the user.
4. Clean up the recovery tag: `git tag -d pipeline-end-epic-{{EPIC_ID}}`

# Filesystem Boundary

Agents and coordinator MUST NOT write files outside the project root. For temporary files, use `{project_root}/.tmp/` (created on demand, cleaned by the coordinator after each step completes). Never use `/tmp`, `$TMPDIR`, or other system-level temp directories.
