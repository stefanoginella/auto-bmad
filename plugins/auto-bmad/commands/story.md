---
name: 'auto-bmad-story'
description: 'Develop a full BMAD story from start to finish using sequential agents'
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

# Detect Story ID

A story ID is composed by exactly 2 numbers: the epic number and the story number within that epic, separated by a dash, a dot, or a space. For example, "1-1" would be the first story in the first epic, "2-3" would be the third story in the second epic, and so on. A story ID can also be inferred from the path name if a path is provided when launching the workflow (e.g., `{{implementation_artifacts}}/1-2-authentication-system.yaml` would set the story ID to "1-2").

**IMPORTANT**: The dash (or dot/space) in a story ID is a SEPARATOR, not a range. `1-7` (or `1.7` or `1 7`) means "epic 1, story 7" — it does NOT mean "stories 1 through 7". This pipeline processes exactly ONE story per run. Never interpret a story ID as a range of stories.

IF user provides epic-story number (e.g. 1-1, 1-2, 2.1, 2.2, etc.) or a file path containing an epic-story pattern:
THEN set {{STORY_ID}} to the provided epic-story number (always a single story).
ELSE ask to provide a epic-story number to identify the story to work on and set {{STORY_ID}} to the provided value.

# Process

Run the BMAD story pipeline for story {{STORY_ID}} as a sequence of steps (create, validate, ATDD, develop, lint/test, NFR, test expansion, test review, code reviews, regression, E2E, trace, and commit).

Each step MUST run in its own **foreground Task tool call** (subagent_type: "general-purpose") so that each agent gets a fresh context window. The Task tool in foreground mode blocks until the agent completes and returns its result directly — use this return value to determine success/failure before proceeding to the next step.

**CRITICAL — Tool usage rules:**
- **DO** use the Task tool (foreground, default mode) for each step. It blocks and returns the result.
- **DO NOT** use TeamCreate, SendMessage, TaskOutput, TaskCreate, or TaskList. This is a sequential pipeline, not a team collaboration.
- **DO NOT** launch multiple Task calls simultaneously. Wait for each to return before launching the next.
- **DO NOT** execute any step yourself — always delegate to a Task agent.

**Retry policy:** If a step fails, retry it **once**. If the retry also fails, stop the pipeline, save a partial report with the failure details, and report to the user which step failed and why.

**`yolo` suffix:** Every step prompt ends with `yolo` to bypass agent confirmation prompts for fully autonomous execution, using the available context to take the best decisions. Quality is ensured by the multi-pass review and regression structure of the pipeline, not by per-step human approval.

## Pre-flight

1. Clean `{project_root}/.tmp/` if it exists from a previous failed run.
2. Record the starting git commit hash for the report as {{START_COMMIT_HASH}}
3. Create a recovery tag: `git tag -f pipeline-start-{{STORY_ID}}` so the entire pipeline can be rolled back with `git reset --hard pipeline-start-{{STORY_ID}}` if needed.

## Story File Path Resolution

After the "Create" step succeeds, extract `STORY_FILE` from its `## Handoff` section (see Handoff Protocol) and set {{STORY_FILE}} to that value. All subsequent steps use {{STORY_FILE}} instead of `story {{STORY_ID}}` to avoid redundant file discovery.

## Failure & Recovery

If the pipeline fails after retries and stops:
1. Save a partial report (see Report section) noting which step failed.
2. Print the recovery tag: `To roll back all changes: git reset --hard pipeline-start-{{STORY_ID}}`
3. Print the partial report path so the user can review what happened.

Do NOT automatically roll back — leave the working tree as-is so the user can inspect and decide.

# Pipeline Introduction

Each step is a separate foreground Task call with these parameters:

| Parameter | Value |
|-----------|-------|
| `description` | The step name (e.g., "Story 2-5 Create") |
| `subagent_type` | `general-purpose` |
| `prompt` | The step's prompt text (in backticks below), with the Step Output Format appended |

## Step Output Format

Append the following to every Task prompt so the coordinator gets structured output for the report:

> When you are done, end your response with a `## Step Summary` section containing: **Status** (success/failure), **Duration** (wall-clock time from start to finish of your work, approximate), **What changed** (files created/modified/deleted), **Key decisions** (any non-obvious choices made), **Issues found & fixed** (count and brief description), **Remaining concerns** (if any), **Migrations** (if any Alembic migrations were created, list the file path and what it does).

## Handoff Protocol

Steps that produce values consumed by later steps MUST end their output with a `## Handoff` section (after `## Step Summary`) containing key-value pairs. The coordinator extracts these values and injects them into downstream step prompts.

Required handoffs:
- **Step 1 (Create)** → `STORY_FILE: <path>` — consumed by all subsequent steps
- **Step 7 (Post-Dev Test)** → `TEST_COUNT: <N>` — consumed by step 16 for regression check

## Progress Reporting

After each step completes, the coordinator MUST print a 1-line progress update before launching the next step:

Format: `Step N/TOTAL: <step-name> — <status>`

TOTAL is the number of pipeline steps for this run (typically 18, or 20 if trace gap recovery triggers). This gives the user continuous visibility into pipeline progress.

## Checkpoint Commits

The coordinator creates checkpoint commits at key milestones using the bash command `git add -A && git commit -m "<message>"` directly. Use exact commit messages as shown — these are temporary markers that get squashed at the end. Checkpoints are marked with `>>> CHECKPOINT` below.

**Note:** Checkpoint commits intentionally bypass pre-commit hooks — they are temporary markers that get squashed into the final commit. Linting and formatting are enforced explicitly by dedicated pipeline steps (5 and 13).

At the end of the pipeline, squash all checkpoint commits into a single clean commit.

# Pipeline Steps

## Lint & Test Prompt Templates

To reduce duplication, the following prompt fragments are referenced by multiple steps. Substitute `{{PHASE}}` with the step's phase name (e.g., "Post-Dev", "Regression").

**{{LINT_PROMPT}}**: `Run the project's linters, formatters, type-checkers, and migration integrity checks. This is a Docker-based project — all commands MUST run inside Docker containers (e.g., docker compose exec backend …, docker compose exec frontend …). NEVER run linters, formatters, or type-checkers directly on the host. Refer to {{output_folder}}/project-context.md or CLAUDE.md for exact commands. Automatically fix all issues - yolo`

**{{TEST_PROMPT}}**: `Run all tests and verify that all tests pass. This is a Docker-based project — all commands MUST run inside Docker containers (e.g., docker compose exec backend …, docker compose exec frontend …). NEVER run pytest, vitest, or any test runner directly on the host. Refer to {{output_folder}}/project-context.md or CLAUDE.md for exact commands. Automatically fix any failures - yolo`

## Skip Condition Evaluation

The coordinator evaluates all skip conditions **before** launching each Task, using pre-flight data and prior step outputs. If a skip condition is met, the coordinator logs the skip reason in the progress report and moves to the next step — no Task agent is launched.

When a step is skipped, the coordinator still records it in the report with status "skipped" and the reason.

## Story Creation & Validation

Do not proceed and create a checkpoint if the Step 2 (Story Validate) hasn't been executed.

1. **Story {{STORY_ID}} Create**
   - **Skip if:** a story file for {{STORY_ID}} already exists in `{{implementation_artifacts}}/` (glob for `{{STORY_ID}}-*.md`). Log "Story file already exists" with the file path. Set `{{STORY_FILE}}` to the existing file path.
   - **Task prompt:** `/bmad-bmm-create-story story {{STORY_ID}} yolo — End with a ## Handoff section containing STORY_FILE: <path to the created story file>.`

2. **Story {{STORY_ID}} Validate**: `/bmad-review-adversarial-general {{STORY_FILE}} yolo - review this story file against BMAD story creation standards. Validate completeness of acceptance criteria, technical context, task breakdown, and dependency declarations. Automatically fix all issues and optimization opportunities found.`

>>> CHECKPOINT: `wip({{STORY_ID}}): story created and validated`

## Test-First

3. **Story {{STORY_ID}} ATDD**: `/bmad-tea-testarch-atdd {{STORY_FILE}} yolo`

>>> CHECKPOINT: `wip({{STORY_ID}}): ATDD tests written`

## Development

4. **Story {{STORY_ID}} Develop**: `/bmad-bmm-dev-story {{STORY_FILE}} yolo — When implementing, if context7 MCP tools are available (resolve-library-id → query-docs), use them to look up current API patterns for libraries being used rather than relying on training data. Update {{STORY_FILE}} when you're done.`

5. **Story {{STORY_ID}} Frontend Polish**
   - **Skip if:** the story file's `ui_impact` field is explicitly `false`, or the field is absent and the story's acceptance criteria and tasks clearly involve no user-facing UI changes (coordinator reads `{{STORY_FILE}}` to check). Log "No frontend polish needed — backend-only story".
   - **Task prompt:** `/frontend-design:frontend-design yolo — Review and polish the frontend components created or modified by story {{STORY_ID}}. Read {{STORY_FILE}} for context on what was built. Focus on the components touched by this story — improve visual quality, interaction polish, and design consistency while preserving all existing functionality and acceptance criteria.`

## Post-Development Verification

6. **Story {{STORY_ID}} Post-Dev Lint & Typecheck**: `{{LINT_PROMPT}}`
7. **Story {{STORY_ID}} Post-Dev Test Verification**: `{{TEST_PROMPT}} and specifically verify that the ATDD acceptance tests now pass. End with a ## Handoff section containing TEST_COUNT: <total number of tests that ran>.`

>>> CHECKPOINT: `wip({{STORY_ID}}): development complete, lint and tests passing`

## Early NFR Gate

8. **Story {{STORY_ID}} NFR**: `/bmad-tea-testarch-nfr {{STORY_FILE}} yolo`

## Test Expansion & Review

9. **Story {{STORY_ID}} Test Automate**: `/bmad-tea-testarch-automate {{STORY_FILE}} yolo - if any acceptance criteria are not yet covered by automated tests, generate tests to fill those gaps.`
10. **Story {{STORY_ID}} Test Review**: `/bmad-tea-testarch-test-review {{STORY_FILE}} yolo - review the story's test suite for completeness, relevance, and quality. Automatically fix any issues found.`

>>> CHECKPOINT: `wip({{STORY_ID}}): NFR checked, test suite expanded and reviewed`

## Code Reviews (iterative)

11. **Story {{STORY_ID}} Code Review #1**: `/bmad-bmm-code-review {{STORY_FILE}} yolo - automatically fix all critical, high, medium, and low severity issues. Update {{STORY_FILE}} when you're done. In your Step Summary, report the exact count of issues found per severity level (critical/high/medium/low).`
12. **Story {{STORY_ID}} Code Review #2**: `/bmad-bmm-code-review {{STORY_FILE}} yolo - automatically fix all critical, high, medium, and low severity issues. Update {{STORY_FILE}} when you're done. In your Step Summary, report the exact count of issues found per severity level (critical/high/medium/low).`
13. **Story {{STORY_ID}} Code Review #3**: `/bmad-bmm-code-review {{STORY_FILE}} yolo - automatically fix all critical, high, medium, and low severity issues. Additionally, use any available security guidance tools to check for OWASP top 10 vulnerabilities, authentication/authorization flaws, and injection risks. Update {{STORY_FILE}} when you're done. In your Step Summary, report the exact count of issues found per severity level (critical/high/medium/low).`

## Security Scan

14. **Story {{STORY_ID}} Security Scan**
   - **Skip if:** `semgrep` is not installed (coordinator runs `which semgrep` before launching the Task; if it exits non-zero, skip). Log "semgrep not installed — skipping security scan".
   - **Task prompt:** `Run semgrep security scan on all files created or modified by this story. Check for OWASP top 10 vulnerabilities, injection flaws, insecure patterns, and security anti-patterns. Automatically fix all issues found. Refer to the story file at {{STORY_FILE}} for context on what was built. yolo`

## Post-Review Regression

15. **Story {{STORY_ID}} Regression Lint & Typecheck**: `{{LINT_PROMPT}}`
16. **Story {{STORY_ID}} Regression Test**: `{{TEST_PROMPT}} The post-dev test count was {{POST_DEV_TEST_COUNT}}. Verify the total test count has NOT decreased — if it has, STOP and report a test count regression (tests may have been deleted or disabled by code review fixes). End with a ## Handoff section containing TEST_COUNT: <total number of tests that ran>.`

>>> CHECKPOINT: `wip({{STORY_ID}}): code reviews complete, security scanned, regression passing`

## Quality Gates

17. **Story {{STORY_ID}} E2E**
    - **Skip if:** the story file's `ui_impact` field is explicitly `false`, or the field is absent and the story's acceptance criteria and tasks clearly involve no user-facing UI changes (coordinator reads `{{STORY_FILE}}` to check). Log "No E2E tests needed — backend-only story".
    - **Task prompt:** `/bmad-bmm-qa-generate-e2e-tests {{STORY_FILE}} yolo — generate E2E tests for this story's user-facing UI changes.`
18. **Story {{STORY_ID}} Trace**: `/bmad-tea-testarch-trace {{STORY_FILE}} yolo — if traceability analysis reveals acceptance criteria with no test coverage, list the gaps explicitly in your Step Summary under **Uncovered ACs** so the report captures them.`

### Trace Gap Recovery

If step 18 reports uncovered acceptance criteria, run one recovery pass:

19. **Story {{STORY_ID}} Trace Gap Fill**: `/bmad-tea-testarch-automate {{STORY_FILE}} yolo - generate tests ONLY for these specific uncovered acceptance criteria: [list ACs from step 18 output]. Do not duplicate existing tests.`

Then re-run traceability:

20. **Story {{STORY_ID}} Trace Re-check**: `/bmad-tea-testarch-trace {{STORY_FILE}} yolo`

If gaps remain after re-check, note them in the report as known gaps but do not loop further.

# Report

**Generate the report BEFORE the final commit** so it is included in the squashed commit alongside the code.

Compile the report from the Step Summary sections collected from each agent. Use this template:

```markdown
# Story {{STORY_ID}} Report

## Overview
- **Story file**: {{STORY_FILE}}
- **Git start**: `{{START_COMMIT_HASH}}`
- **Pipeline result**: success | partial failure at step N
- **Migrations**: list any Alembic migration files created (file path + what it does), or "None"

## What Was Built
Brief description of what this story implemented (1-3 sentences from the story spec).

## Acceptance Criteria Coverage
List each acceptance criterion from the story file and its coverage status:
- [ ] AC1: description — covered by: test file(s) | not yet covered
- [ ] AC2: description — covered by: test file(s) | not yet covered
- ...

## Files Changed
Consolidated list of all files created/modified/deleted, grouped by directory. For each file, note whether it was created (new), modified, or deleted.

## Pipeline Steps

For each step, list:

### Step N: Step Name
- **Status**: success/failure
- **Duration**: approximate wall-clock time
- **What changed**: files created/modified/deleted
- **Key decisions**: any non-obvious choices made
- **Issues found & fixed**: count and description (if any)
- **Remaining concerns**: (if any)

## Test Coverage
- Tests generated (ATDD, automated, E2E) — list test files
- Coverage summary (which acceptance criteria are covered — reference the AC checklist above)
- Any gaps
- **Test count**: post-dev {{POST_DEV_TEST_COUNT}} → regression {{REGRESSION_TEST_COUNT}} (delta: +N or REGRESSION)

## Code Review Findings
Per-pass summary with issue counts:

| Pass | Critical | High | Medium | Low | Total Found | Fixed | Remaining |
|------|----------|------|--------|-----|-------------|-------|-----------|
| #1   | ...      | ...  | ...    | ... | ...         | ...   | ...       |
| #2   | ...      | ...  | ...    | ... | ...         | ...   | ...       |
| #3   | ...      | ...  | ...    | ... | ...         | ...   | ...       |

## Quality Gates
- **Frontend Polish**: applied/skipped — details
- **NFR**: pass/fail — details
- **Security Scan (semgrep)**: pass/fail — issues found and fixed
- **E2E**: pass/skip/fail — details
- **Traceability**: pass/fail — link to matrix output

## Known Risks & Gaps
Anything the developer should watch out for, review manually, or address in a follow-up. Include any non-converging code review findings.

## Manual Verification
Omit this section if the story has no UI impact. Otherwise, provide step-by-step actions to test and verify the story from the UI.

---

## TL;DR
3-4 sentence executive summary: what was built, whether the pipeline passed cleanly, and any action items requiring human attention.
```

Save it as `story-{{STORY_ID}}-report.md` in the `{{auto_bmad_artifacts}}/` folder.

# Final Commit

After the report is saved, squash all checkpoint commits and create one clean commit:

1. `git reset --soft {{START_COMMIT_HASH}}` — undoes all checkpoint commits but keeps all changes staged.
2. `/commit-commands:commit <type>({{STORY_ID}}): story complete` — creates a single clean commit with all code + report. Derive `<type>` from the story spec's `type` field if present (feat, fix, chore, refactor); default to `feat` if no type is specified.
3. Record the final git commit hash as {{FINAL_COMMIT_HASH}} and print it to the user.
4. Clean up the recovery tag: `git tag -d pipeline-start-{{STORY_ID}}`

# Filesystem Boundary

Agents and coordinator MUST NOT write files outside the project root. For temporary files, use `{project_root}/.tmp/` (created on demand, cleaned by the coordinator after each step completes). Never use `/tmp`, `$TMPDIR`, or other system-level temp directories.
