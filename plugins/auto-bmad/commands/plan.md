---
name: 'auto-bmad-plan'
description: 'Run the BMAD pre-implementation pipeline: analysis, planning, solutioning, and sprint setup'
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

# Pre-Implementation Pipeline

Run the BMAD pre-implementation lifecycle as a minimal sequence of BMAD slash commands — lightweight orchestration with git safety.

Each step MUST run in its own **foreground Task tool call** (subagent_type: "general-purpose") so that each agent gets a fresh context window.

## User Input

The user MUST provide input alongside the command — a product idea, a description, a file path, or any context about what they want to build. Capture everything the user provides as {{USER_INPUT}}.

- If the input references a file (e.g., `@rough-idea.md`, a path), **read the file contents** and include them verbatim as part of {{USER_INPUT}}.
- **If no input is provided, STOP.** Tell the user that the plan pipeline requires product context.

**CRITICAL — Tool usage rules:**
- **DO** use the Task tool (foreground, default mode) for each step. It blocks and returns the result.
- **DO NOT** use TeamCreate, SendMessage, TaskOutput, TaskCreate, or TaskList. This is a sequential pipeline, not a team collaboration.
- **DO NOT** launch multiple Task calls simultaneously. Wait for each to return before launching the next.
- **DO NOT** execute any step, fix, or implement new code yourself — always delegate to a Task agent.

**Retry policy:** If a step fails, run `git reset --hard HEAD` to discard its partial changes, then retry **once**. If the retry also fails, stop the pipeline and tell the user:
- Which step failed and why
- Recovery commands: `git reset --hard {{START_COMMIT_HASH}}` to roll back the entire pipeline, or `git reset --hard HEAD` to retry the failed step.

## Artifact Scan

Before running, scan for existing artifacts to determine which steps to skip:

1. Scan `{{planning_artifacts}}/` for:
   - `product-brief-*.md` — product brief exists
   - `prd.md` — PRD exists
   - `ux-design-specification.md` or `ux-design-specification/` — UX spec exists
   - `architecture.md` or `architecture/` — architecture exists
   - `test-design-architecture.md` or `test-design-qa.md` — system-level test design exists
   - `epics.md` or `epics/` — epics exist
2. Scan `{{implementation_artifacts}}/` for:
   - `sprint-status.yaml` — sprint planning done
3. Scan for test framework configs (e.g., `playwright.config.*`, `vitest.config.*`, `pytest.ini`, etc.) — test framework exists

Report which artifacts already exist and which steps will be skipped.

Set `{{USER_INPUT_INSTRUCTION}}` to: `The user provided the following vision for this product — treat it as the primary input and build the product brief around it:\n\n{{USER_INPUT}}`

# Pre-flight

Before running any steps, record:
- `{{START_TIME}}` — current date+time in ISO 8601 format (e.g. `2026-02-26T14:30:00`)
- `{{START_COMMIT_HASH}}` — run `git rev-parse --short HEAD` and store the result

# Pipeline Steps

After each successful step, the coordinator runs `git add -A && git commit --no-verify -m "wip(plan): step N/11 <step-name> - done"` and prints a 1-line progress update: `Step N/11: <step-name> — <status>`. The coordinator must also track a running list of `(step_name, status, start_time, end_time)` — note the wall-clock time before and after each Task call to use in the final report.

## Phase 1: Analysis

1. **Create Product Brief**
   - **Skip if:** product brief OR PRD already exists. Log "Product brief already exists" or "PRD already exists — product brief not needed".
   - **Task prompt:** `/bmad-bmm-create-product-brief yolo — {{USER_INPUT_INSTRUCTION}}`

## Phase 2: Planning

2. **Create PRD**
   - **Skip if:** PRD already exists. Log "PRD already exists".
   - **Task prompt:** `/bmad-bmm-create-prd yolo — {{USER_INPUT_INSTRUCTION}}`

3. **Validate PRD**
   - **Skip if:** PRD already existed (was not created in step 2) AND downstream artifacts exist (architecture OR UX design specs). Log "PRD validation skipped — PRD predates this run and downstream artifacts already exist".
   - **Task prompt:** `/bmad-bmm-validate-prd yolo — automatically fix all issues and optimizations found.`

4. **Create UX Design**
   - **Skip if:** UX design specification already exists. Also skip if the project has no frontend or UI component. Log reason.
   - **Task prompt:** `/bmad-bmm-create-ux-design yolo`

## Phase 3: Solutioning

5. **Create Architecture**
   - **Skip if:** architecture docs already exist. Log "Architecture already exists".
   - **Task prompt:** `/bmad-bmm-create-architecture yolo`

6. **Test Framework Setup**
   - **Skip if:** test framework already configured. Log "Test framework already configured".
   - **Task prompt:** `/bmad-tea-testarch-framework yolo`

7. **System-Level Test Design**
   - **Skip if:** test-design-architecture.md and test-design-qa.md already exist. Log "System-level test design already exists".
   - **Task prompt:** `/bmad-tea-testarch-test-design yolo — run in system-level mode using the PRD, architecture docs, and epics as input.`

8. **Create Epics & Stories**
   - **Skip if:** epics already exist. Log "Epics already exist".
   - **Task prompt:** `/bmad-bmm-create-epics-and-stories yolo`

9. **Check Implementation Readiness**
   - **Task prompt:** `/bmad-bmm-check-implementation-readiness yolo — automatically fix all issues.`

## Phase 4: Sprint Setup

10. **Generate Project Context**
    - **Task prompt:** `/bmad-bmm-generate-project-context yolo`

11. **Sprint Planning**
    - **Skip if:** sprint-status.yaml already exists. Log "Sprint plan already exists".
    - **Task prompt:** `/bmad-bmm-sprint-planning yolo`

# Final Commit

1. `git reset --soft {{START_COMMIT_HASH}}` — squash all checkpoint commits, keep changes staged.
2. Commit with: `git add -A && git commit -m "chore: BMAD plan — pre-implementation pipeline complete"`
3. Record the final git commit hash and print it to the user.

**From this point on, do NOT auto-commit.** Only commit when the user explicitly asks you to.

# Pipeline Report

1. Record `{{END_TIME}}` — current date+time in ISO 8601 format.
2. Scan `{{output_folder}}/` recursively for files modified after `{{START_TIME}}` to build the artifact list.
3. Create `{{auto_bmad_artifacts}}/` directory if it doesn't exist.
4. Generate the report and save it to `{{auto_bmad_artifacts}}/plan-report-YYYY-MM-DD-HHMMSS.md` (using `{{END_TIME}}` for the timestamp).
5. Print the full report to the user.

Use this template for the report:

```markdown
# Pipeline Report: plan

| Field | Value |
|-------|-------|
| Pipeline | plan |
| Start | {{START_TIME}} |
| End | {{END_TIME}} |
| Duration | <minutes>m |
| Initial Commit | {{START_COMMIT_HASH}} |

## Artifacts

- `<relative-path>` — new/updated

## Pipeline Outcome

| # | Step | Status | Duration | Summary |
|---|------|--------|----------|---------|
| 1 | Product Brief | done/skipped | Xm | <what product/vision was captured> |
| 2 | PRD | done/skipped | Xm | <key features count, scope summary> |
| 3 | Validate PRD | done/skipped | Xm | <issues found and fixed count> |
| 4 | UX Design | done/skipped | Xm | <pages/flows designed, or why skipped (no frontend)> |
| 5 | Architecture | done/skipped | Xm | <stack chosen, key patterns (e.g. "monolith, PostgreSQL, REST API")> |
| 6 | Test Framework | done/skipped | Xm | <framework chosen (e.g. "Playwright + Vitest")> |
| 7 | System Test Design | done/skipped | Xm | <test areas covered> |
| 8 | Epics & Stories | done/skipped | Xm | <epic count, total story count> |
| 9 | Impl Readiness | done/failed | Xm | <pass/fail, issues fixed count> |
| 10 | Project Context | done | Xm | <refreshed or newly generated> |
| 11 | Sprint Planning | done/skipped | Xm | <stories queued for first sprint> |

## Key Decisions & Learnings

- <short summary of important decisions made, issues encountered, or learnings from any step>
- <e.g. "Skipped UX design — project has no frontend", "Architecture chose serverless over containers for cost reasons">

## Action Items

### Review
- [ ] Read through every generated artifact — PRD, architecture, UX design, epics — before starting implementation
- [ ] PRD completeness — verify scope and feature list match the product vision
- [ ] Architecture tech stack — confirm alignment with team skills and infrastructure
- [ ] UX flows — check edge cases and error states
- [ ] Epic scoping/sizing — validate sprint capacity estimates
- [ ] Any skipped steps — if steps were skipped due to existing artifacts, verify those artifacts are still current and complete

### Attention
- [ ] <assumptions made in architecture — e.g. "assumes cloud deployment", "chose SQL over NoSQL based on data model">
- [ ] <missing NFRs — e.g. "no performance targets defined", "security requirements TBD">
- [ ] <scope risks in sprint plan — e.g. "first sprint is ambitious", "dependency on external API not yet available">

### Next
- Start a new session with fresh context, then run `/auto-bmad-epic-start <epic-number>` to prepare the first epic (test design)
- Then run `/auto-bmad-story <epic-story>` for each story in the sprint (one story per session)
```
