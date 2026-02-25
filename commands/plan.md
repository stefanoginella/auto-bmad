---
name: 'plan'
description: 'Run the full BMAD pre-implementation pipeline: analysis, planning, solutioning, and sprint setup'
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

# Pre-Implementation Pipeline

Run the complete BMAD pre-implementation lifecycle — from product brief through sprint planning — as a sequence of automated steps. This pipeline produces all the planning artifacts required before any story can be developed.

Each step MUST run in its own **foreground Task tool call** (subagent_type: "general-purpose") so that each agent gets a fresh context window. The Task tool in foreground mode blocks until the agent completes and returns its result directly — use this return value to determine success/failure before proceeding to the next step.

## User Input

The user MUST provide input alongside the command — a product idea, a description, a file path, or any context about what they want to build. Capture everything the user provides as {{USER_INPUT}}.

- If the input references a file (e.g., `@rough-idea.md`, a path), **read the file contents** and include them verbatim as part of {{USER_INPUT}}.
- **If no input is provided, STOP.** Do not proceed with the pipeline. Instead, tell the user that the plan pipeline requires product context to run autonomously, and suggest they either provide input inline, continue with any existing artifacts (if available), or run one of the preparation workflows first (see "Recommended Preparation Workflows" below).

{{USER_INPUT}} is **high-priority context** — it represents the user's intent and vision. Pass it to the early pipeline steps (product brief, PRD) so agents treat it as the primary input rather than inventing from scratch.

## Input Readiness Gate

Before running the pipeline, validate that {{USER_INPUT}} contains sufficient context for autonomous planning. Run a **foreground Task call** (subagent_type: "general-purpose") with this prompt:

**Input Readiness Check**:
```markdown
Evaluate the following user input for completeness as a foundation for an autonomous product planning pipeline. The pipeline will generate a product brief, PRD, UX design, architecture, test strategy, and epic decomposition — all without further human input.

### Step 1: Check Existing Artifacts

Before scoring, check for existing planning artifacts in `{{planning_artifacts}}/`:
- If `product-brief-*.md` exists → read it and credit its content toward dimensions 1-3
- If `prd.md` exists → read it and credit its content toward dimensions 1-4
- If `architecture.md` or `architecture/` exists → credit toward dimension 5
- If `ux-design-specification.md` or `ux-design-specification/` exists → credit toward dimension 2

Note which artifacts were found — they supplement the user input.

### Step 2: Score Weighted Dimensions

Score the input (combined with any existing artifacts found above) against these weighted dimensions. Each dimension is scored from 0 to its max: 0=missing, half=vague, max=clear.

| # | Dimension | Max | Why This Weight |
|---|-----------|-----|-----------------|
| 1 | **Problem Statement** — What problem does this solve? Who has it? | 3 | Everything downstream builds on this — fatal if wrong |
| 2 | **Target Users** — Who are the primary users? Any segments or personas? | 3 | Drives UX design, PRD personas, acceptance criteria |
| 3 | **Core Value Proposition** — Why would users choose this over alternatives? | 2 | Anchors PRD scope and architecture trade-offs |
| 4 | **Key Features / Scope** — What should the product do? What is in/out? | 2 | Directly shapes epics, stories, and architecture |
| 5 | **Technical Constraints** — Any tech stack preferences, integrations, or platform requirements? | 1 | Architect can infer reasonable defaults from features |
| 6 | **Success Criteria** — How will success be measured? What does "done" look like? | 1 | PM agent can derive metrics from problem + users |

For each dimension, note whether the score came from user input, an existing artifact, or both.

### Step 3: Assumption Audit

For every dimension scored below its maximum, list the **specific assumptions** the pipeline would need to make autonomously. Be concrete — do not write vague placeholders:
- BAD: "Would need to assume target users"
- GOOD: "Would assume target users are small business owners who manage their own newsletters, based on the product name and described features"

This gives the user a clear picture of what the AI will decide for them if they proceed as-is.

### Step 4: Produce Verdict

- **READY** (score ≥ 10/12): Input is sufficient. List any minor gaps and the assumptions the pipeline will make, but proceed.
- **NEEDS ENRICHMENT** (score ≥ 4 and ≤ 9): Input has significant gaps. List each gap with a specific question the user should answer. Then recommend the most relevant preparation workflow(s) — at most 2, targeted at the weakest dimensions:
  - Dimensions 1-2 weak (Problem/Users) → /bmad-cis-design-thinking (empathy-first user understanding) or /bmad-brainstorming (explore the problem space)
  - Dimension 3 weak (Value Prop) → /bmad-cis-innovation-strategy (find competitive angle) or /bmad-cis-storytelling (articulate the vision)
  - Dimension 4 weak (Features/Scope) → /bmad-brainstorming (generate feature ideas) or /bmad-party-mode (multi-agent feature exploration)
  - Dimension 5 weak (Technical) → /bmad-bmm-technical-research (research tech options)
  - Multiple dimensions weak → /bmad-party-mode (comprehensive multi-agent discussion) or /bmad-cis-design-thinking (structured end-to-end discovery)
  - User has rough notes that need deepening → /bmad-advanced-elicitation (structured challenge and refinement)
- **INSUFFICIENT** (score ≤ 3): Input is too sparse for any autonomous planning. List what is missing and strongly recommend starting with /bmad-brainstorming or /bmad-cis-design-thinking before attempting the plan pipeline.

End with a ## Step Summary containing: **Status** (READY/NEEDS ENRICHMENT/INSUFFICIENT), **Score** (N/12 with per-dimension breakdown), **Existing artifacts credited** (list or "none"), **Assumptions the pipeline would make** (from the audit), **Gaps** (list), **Recommended workflows** (if not READY, max 2 targeted at weakest dimensions).

User input to evaluate:

{{USER_INPUT}}

yolo
```

**Gate logic:**
- If verdict is **READY** → proceed to Pre-flight and the pipeline.
- If verdict is **NEEDS ENRICHMENT** or **INSUFFICIENT** → STOP the pipeline. Present the agent's gap analysis, assumption audit, and workflow recommendations to the user. Do not proceed until the user either enriches their input or explicitly overrides with "proceed anyway".

**CRITICAL — Tool usage rules:**
- **DO** use the Task tool (foreground, default mode) for each step. It blocks and returns the result.
- **DO NOT** use TeamCreate, SendMessage, TaskOutput, TaskCreate, or TaskList. This is a sequential pipeline, not a team collaboration.
- **DO NOT** launch multiple Task calls simultaneously. Wait for each to return before launching the next.
- **DO NOT** execute any step yourself — always delegate to a Task agent.

**Retry policy:** If a step fails, retry it **once**. If the retry also fails, stop the pipeline, save a partial report with the failure details, and report to the user which step failed and why.

**`yolo` suffix:** Every step prompt ends with `yolo` to bypass agent confirmation prompts for fully autonomous execution, using the available context to take the best decisions.

## Pre-flight: Artifact Detection

Before running, scan for existing planning artifacts to determine where to resume:

1. Clean `{project_root}/.tmp/` if it exists from a previous failed run.
2. Record the starting git commit hash as {{START_COMMIT_HASH}}.
3. Create a recovery tag: `git tag -f pipeline-start-plan` so the pipeline can be rolled back with `git reset --hard pipeline-start-plan` if needed.
4. Scan `{{planning_artifacts}}/` for existing files:
   - `product-brief-*.md` → product brief exists
   - `prd.md` → PRD exists
   - `ux-design-specification.md` or `ux-design-specification/` → UX spec exists
   - `architecture.md` or `architecture/` → architecture exists
   - `test-design-architecture.md` or `test-design-qa.md` → system-level test design exists
   - `epics.md` or `epics/` → epics exist
   - `implementation-readiness-report-*.md` → readiness check done
5. Scan `{{implementation_artifacts}}/` for:
   - `project-context.md` → project context exists
   - `sprint-status.yaml` → sprint planning done
6. Scan for test framework and CI:
   - Test framework configs (e.g., `playwright.config.*`, `cypress.config.*`, `vitest.config.*`, `pytest.ini`, `pyproject.toml`, with `[tool.pytest]`, etc) → test framework exists
   - CI configs (e.g., `.github/workflows/*.yml`, `.gitlab-ci.yml`, `azure-pipelines.yml`, etc) → CI exists

Report which artifacts already exist and which steps will be skipped. Then proceed from the **first missing artifact** in the pipeline order below.

If ALL artifacts exist, report that the pre-implementation pipeline is complete and no steps need to run.

## Failure & Recovery

If the pipeline fails after retries and stops:
1. Save a partial report (see Report section) noting which step failed.
2. Print the recovery tag: `To roll back all changes: git reset --hard pipeline-start-plan`
3. Print the partial report path so the user can review what happened.

Do NOT automatically roll back — leave the working tree as-is so the user can inspect and decide.

# Pipeline Introduction

Each step is a separate foreground Task call with these parameters:

| Parameter | Value |
|-----------|-------|
| `description` | The step name (e.g., "Create PRD") |
| `subagent_type` | `general-purpose` |
| `prompt` | The step's prompt text (in backticks below), with the Step Output Format appended |

## Step Output Format

Append the following to every Task prompt so the coordinator gets structured output for the report:

> When you are done, end your response with a `## Step Summary` section containing: **Status** (success/failure), **Duration** (wall-clock time from start to finish of your work, approximate), **What changed** (files created/modified/deleted), **Key decisions** (any non-obvious choices made), **Issues found & fixed** (count and brief description), **Remaining concerns** (if any).

## Handoff Protocol

Steps that produce values consumed by later steps MUST end their output with a `## Handoff` section (after `## Step Summary`) containing key-value pairs. The coordinator extracts these values and injects them into downstream step prompts.

Required handoffs:
- **Step 1 (Create Product Brief)** → `PRODUCT_BRIEF_PATH: <path>` — consumed by step 2 (PRD creation)
- **Step 10 (Check Implementation Readiness)** → `READINESS_RESULT: PASS | FAIL` and `BLOCKING_ISSUES: <list or "none">` — the coordinator uses this to decide whether to proceed to sprint setup

## Progress Reporting

After each step completes, the coordinator MUST print a 1-line progress update before launching the next step:

Format: `Step N/TOTAL: <step-name> — <status>`

TOTAL is the number of pipeline steps for this run (typically 13, fewer if artifacts already exist and steps are skipped). This gives the user continuous visibility into pipeline progress.

## Checkpoint Commits

The coordinator creates checkpoint commits at key milestones using the bash command `git add -A && git commit -m "<message>"` directly. Use exact commit messages as shown — these are temporary markers that get squashed at the end. Checkpoints are marked with `>>> CHECKPOINT` below.

**Note:** Checkpoint commits intentionally bypass pre-commit hooks — they are temporary markers that get squashed into the final commit.

At the end of the pipeline, squash all checkpoint commits into a single clean commit.

# Pipeline Steps

Set `{{USER_INPUT_INSTRUCTION}}` to: `The user provided the following vision for this product — treat it as the primary input and build the product brief around it:\n\n{{USER_INPUT}}`

## Skip Condition Evaluation

The coordinator evaluates all skip conditions **before** launching each Task, using the artifact flags from the Pre-flight scan. If a skip condition is met, the coordinator logs the skip reason in the progress report and moves to the next step — no Task agent is launched.

When a step is skipped, the coordinator still records it in the report with status "skipped" and the reason.

## Phase 1: Analysis (Optional)

1. **Create Product Brief**
   - **Skip if:** product brief OR PRD already exists (from pre-flight). Log "Product brief already exists" or "PRD already exists — product brief not needed". Set `{{PRODUCT_BRIEF_PATH}}` to the existing product brief path, or `"N/A"` if skipped due to existing PRD.
   - **Task prompt:** `/bmad-bmm-create-product-brief yolo — {{USER_INPUT_INSTRUCTION}} End with a ## Handoff section containing PRODUCT_BRIEF_PATH: <path to the created product brief>.`

>>> CHECKPOINT: `wip(plan): product brief created`

## Phase 2: Planning

2. **Create PRD**
   - **Skip if:** PRD already exists (from pre-flight). Log "PRD already exists".
   - **Task prompt:** `/bmad-bmm-create-prd yolo — Use the product brief at {{PRODUCT_BRIEF_PATH}} as the primary input. {{USER_INPUT_INSTRUCTION}}`

3. **Validate PRD**
   - **Skip if:** PRD already existed (was not created in step 2) AND (architecture OR UX design specs already exist). Log "PRD validation skipped — PRD predates this run and downstream artifacts already exist".
   - **Task prompt:** `/bmad-bmm-validate-prd yolo — validate {{planning_artifacts}}/prd.md against PRD standards. Automatically fix all issues and optimizations found.`

>>> CHECKPOINT: `wip(plan): PRD created and validated`

4. **Create UX Design**
   - **Skip if:** UX design specification already exists (from pre-flight). Log "UX design already exists". Also skip if the project has no frontend or UI component — log "No UX design needed — backend-only project".
   - **Task prompt:** `/bmad-bmm-create-ux-design yolo`

>>> CHECKPOINT: `wip(plan): UX design created`

## Phase 3: Solutioning

5. **Create Architecture**
   - **Skip if:** architecture docs already exist (from pre-flight). Log "Architecture already exists".
   - **Task prompt:** `/bmad-bmm-create-architecture yolo — If context7 MCP tools are available (resolve-library-id → query-docs), use them to verify that recommended library APIs and integration patterns are current. Use any available security guidance tools to review the architecture for security concerns.`

>>> CHECKPOINT: `wip(plan): architecture created`

### TEA Pre-Check: Local Development Environment

Before running TEA steps, the coordinator determines whether local development uses Docker/containers. Set {{DOCKER_DEV}} = true if ANY of the following are found:

1. **Files in the repo**: `docker-compose.yml`, `compose.yml`, `Dockerfile`, `.devcontainer/` in project root or subdirectories.
2. **Planning artifacts mention Docker-based local dev**: Scan the PRD (`{{planning_artifacts}}/prd.md`), architecture docs (`{{planning_artifacts}}/architecture.md` or `{{planning_artifacts}}/architecture/`), and any existing project-context for references to Docker, Docker Compose, containers, or devcontainers as the local development approach.

If neither source indicates Docker → set {{DOCKER_DEV}} = false.

This flag is passed to Steps 6 and 7 below.

### TEA: Test Infrastructure

6. **Test Framework Setup**
   - **Skip if:** test framework already configured (from pre-flight). Log "Test framework already configured".
   - **Task prompt:** `/bmad-tea-testarch-framework yolo — scaffold the test infrastructure based on the project's tech stack. If {{DOCKER_DEV}} is true: This project uses Docker for local development. Do NOT generate local helper scripts (e.g., scripts/ci-local.sh, scripts/burn-in.sh, scripts/test-changed.sh) that assume native host tooling (uv, npm, playwright installed on the host). All test commands must work inside Docker containers or be omitted entirely. Test documentation (tests/README.md) should reference Docker-based test execution, not native commands.`

7. **CI Setup**
   - **Skip if:** CI configuration already exists (from pre-flight). Log "CI already configured".
   - **Task prompt:** `/bmad-tea-testarch-ci yolo — generate CI pipeline configuration based on the project's tech stack and test framework. IMPORTANT constraints for this project: **Solo developer on GitHub free tier (2,000 min/month budget).** Trigger: weekly schedule cron ONLY (e.g., Sunday 2 AM UTC) to catch environment drift. Do NOT add push or pull_request triggers. E2E shards: maximum 2 (not 4). Burn-in: schedule-only with 5 iterations max (not 10). Keep total estimated pipeline runtime under 30 minutes per run. Add a YAML comment at the top noting how to enable push/PR triggers when the project grows to multiple contributors. If {{DOCKER_DEV}} is true: Do NOT generate local helper scripts (scripts/ci-local.sh, scripts/burn-in.sh, scripts/test-changed.sh) that assume native host tooling. If local CI mirroring scripts are needed, they must use docker compose exec or be omitted.`

>>> CHECKPOINT: `wip(plan): test framework and CI configured`

### Epic Decomposition

8. **Create Epics & Stories**
   - **Skip if:** epics already exist (from pre-flight). Log "Epics already exist".
   - **Task prompt:** `/bmad-bmm-create-epics-and-stories yolo — If the project uses Docker, ensure the first story in the first epic includes full Docker setup (compose.yaml, Dockerfiles, health checks) so that all subsequent stories can run inside containers.`

### TEA: Test Design

9. **System-Level Test Design**
   - **Skip if:** test-design-architecture.md and test-design-qa.md already exist (from pre-flight). Log "System-level test design already exists".
   - **Task prompt:** `/bmad-tea-testarch-test-design yolo — run in system-level mode using the PRD, architecture docs, and epics as input. Produce test-design-architecture.md, test-design-qa.md, and test-design-handoff.md in {{planning_artifacts}}/.`

10. **Check Implementation Readiness** *(always runs — never skip)*
    - **Task prompt:** `/bmad-bmm-check-implementation-readiness yolo — validate alignment across PRD, UX, Architecture, and Epics. Automatically fix all issues. End with a ## Handoff section containing READINESS_RESULT: PASS or FAIL, and BLOCKING_ISSUES: <list of blocking issues, or "none">.`

>>> CHECKPOINT: `wip(plan): epics created, test design complete, readiness validated`

## Phase 4 Prep: Sprint Setup

11. **Generate Project Context** *(always runs — always regenerate)*
    - **Task prompt:** `/bmad-bmm-generate-project-context yolo — scan the codebase and generate {{output_folder}}/project-context.md with AI-optimized rules, conventions, and patterns. Update if it already exists.`

12. **Improve CLAUDE.md** *(always runs)*
    - **Task prompt:** `/claude-md-management:claude-md-improver yolo — audit and improve CLAUDE.md using the freshly generated {{output_folder}}/project-context.md as reference. IMPORTANT: CLAUDE.md must NOT duplicate content that already exists in project-context.md, since project-context.md is automatically loaded by all BMAD workflows. Focus CLAUDE.md on high-level pointers, setup instructions, and anything NOT covered by project-context.md. Remove any overlapping rules, conventions, or patterns that are already in project-context.md.`

13. **Sprint Planning**
    - **Skip if:** sprint-status.yaml already exists (from pre-flight). Log "Sprint plan already exists".
    - **Task prompt:** `/bmad-bmm-sprint-planning yolo — generate sprint-status.yaml from the epics.`

>>> CHECKPOINT: `wip(plan): project context generated, CLAUDE.md improved, sprint planned`

# Report

**Generate the report BEFORE the final commit** so it is included in the squashed commit alongside the artifacts.

Compile the report from the Step Summary sections collected from each agent. Use this template:

```markdown
# Pre-Implementation Pipeline Report

## Overview
- **User input**: {{USER_INPUT}}
- **Input readiness**: READY/NEEDS ENRICHMENT/INSUFFICIENT — score N/12 (per-dimension breakdown)
- **Artifacts credited**: list of existing artifacts that supplemented user input, or "none"
- **Assumptions made**: key assumptions the pipeline proceeded with (from the assumption audit)
- **Git start**: `{{START_COMMIT_HASH}}`
- **Pipeline result**: success | partial failure at step N
- **Steps run**: N of 13 (M skipped — artifacts already existed)

## Artifacts Produced
List each artifact created or validated, with file path:
- [ ] Product Brief: path | skipped (already existed) | skipped (not needed)
- [ ] PRD: path | skipped
- [ ] PRD Validation: pass/fail
- [ ] UX Design: path | skipped
- [ ] Architecture: path | skipped
- [ ] Test Framework: configured | skipped
- [ ] CI Pipeline: path | skipped
- [ ] Epics: path | skipped
- [ ] Test Design (system): paths | skipped
- [ ] Readiness Report: path — {{READINESS_RESULT}} (blocking issues: {{BLOCKING_ISSUES}})
- [ ] Project Context: path
- [ ] CLAUDE.md: improved | skipped
- [ ] Sprint Status: path | skipped

## Pipeline Steps

For each step that ran:

### Step N: Step Name
- **Status**: success/failure/skipped
- **Duration**: approximate wall-clock time
- **What changed**: files created/modified/deleted
- **Key decisions**: any non-obvious choices made
- **Issues found & fixed**: count and description (if any)
- **Remaining concerns**: (if any)

## Readiness Gate
Summary of the implementation readiness check results. List any blocking issues.

## Known Gaps
Anything that needs manual attention before starting epic development.

---

## TL;DR
3-4 sentence executive summary: what was planned, whether all gates passed, and any action items requiring human attention.
```

Save it as `plan-pipeline-report.md` in `{{auto_bmad_artifacts}}/`.

# Final Commit

After the report is saved, squash all checkpoint commits and create one clean commit:

1. `git reset --soft {{START_COMMIT_HASH}}` — undoes all checkpoint commits but keeps all changes staged.
2. `/commit-commands:commit chore(plan): pre-implementation pipeline complete` — creates a single clean commit with all artifacts + report.
3. Record the final git commit hash as {{FINAL_COMMIT_HASH}} and print it to the user.
4. Clean up the recovery tag: `git tag -d pipeline-start-plan`

# Next Steps Recommendation

After the final commit, present the user with a recommended review workflow. The pipeline produced artifacts autonomously — the user should now review and refine them before starting implementation.

Print the following:

---

**Pipeline complete.** Before starting epic development, consider reviewing the generated artifacts with these commands:

**Holistic review (recommended first step):**
- `/bmad-party-mode` — Multi-agent group discussion to challenge assumptions, spot inconsistencies, and stress-test the plan across all artifacts

**Targeted artifact reviews:**
- `/bmad-review-adversarial-general <artifact>` — Cynical review of any specific artifact (PRD, architecture, epics, etc.)
- `/bmad-bmm-edit-prd` — Iteratively refine the PRD if gaps were found
- `/bmad-bmm-validate-prd` — Re-validate the PRD after manual edits
- `/bmad-bmm-check-implementation-readiness` — Re-run readiness check after any changes

**Deep dives by domain:**
- `/bmad-bmm-create-ux-design` — Refine UX design interactively (if auto-generated version needs work)
- `/bmad-bmm-create-architecture` — Revisit architecture decisions with the architect agent
- `/bmad-bmm-create-epics-and-stories` — Adjust epic/story breakdown if scope changed

**Research & ideation (if the plan surfaced questions):**
- `/bmad-bmm-technical-research <topic>` — Deep-dive on a specific technical decision
- `/bmad-bmm-domain-research <domain>` — Research industry context or competitor approaches
- `/bmad-brainstorming` — Explore alternative approaches to any area of concern
- `/bmad-cis-design-thinking` — Re-examine user needs if target user assumptions feel weak
- `/bmad-cis-innovation-strategy` — Challenge the value proposition and competitive positioning

**When satisfied, start building:**
- `/auto-bmad:epic-start 1` — Begin the first epic

---

# Filesystem Boundary

Agents and coordinator MUST NOT write files outside the project root. For temporary files, use `{project_root}/.tmp/` (created on demand, cleaned by the coordinator after each step completes). Never use `/tmp`, `$TMPDIR`, or other system-level temp directories.
