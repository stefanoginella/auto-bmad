---
name: 'auto-bmad-plan-lite'
description: 'Lite BMAD pre-implementation pipeline: only BMAD slash commands, no orchestration overhead'
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

# Lite Pre-Implementation Pipeline

Run the BMAD pre-implementation lifecycle as a minimal sequence of BMAD slash commands — no orchestration overhead, no reports, no git operations. For testing BMAD workflows.

Each step MUST run in its own **foreground Task tool call** (subagent_type: "general-purpose") so that each agent gets a fresh context window.

## User Input

The user MUST provide input alongside the command — a product idea, a description, a file path, or any context about what they want to build. Capture everything the user provides as {{USER_INPUT}}.

- If the input references a file (e.g., `@rough-idea.md`, a path), **read the file contents** and include them verbatim as part of {{USER_INPUT}}.
- **If no input is provided, STOP.** Tell the user that the plan-lite pipeline requires product context.

**CRITICAL — Tool usage rules:**
- **DO** use the Task tool (foreground, default mode) for each step. It blocks and returns the result.
- **DO NOT** use TeamCreate, SendMessage, TaskOutput, TaskCreate, or TaskList. This is a sequential pipeline, not a team collaboration.
- **DO NOT** launch multiple Task calls simultaneously. Wait for each to return before launching the next.
- **DO NOT** execute any step yourself — always delegate to a Task agent.

**Retry policy:** If a step fails, retry it **once**. If the retry also fails, stop the pipeline and report to the user which step failed and why.

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

# Pipeline Steps

After each step completes, print a 1-line progress update: `Step N/11: <step-name> — <status>`

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

9. **Check Implementation Readiness** *(always runs — never skip)*
   - **Task prompt:** `/bmad-bmm-check-implementation-readiness yolo — automatically fix all issues.`

## Phase 4: Sprint Setup

10. **Generate Project Context** *(always runs — never skip)*
    - **Task prompt:** `/bmad-bmm-generate-project-context yolo`

11. **Sprint Planning**
    - **Skip if:** sprint-status.yaml already exists. Log "Sprint plan already exists".
    - **Task prompt:** `/bmad-bmm-sprint-planning yolo`

# Done

Print: **Plan-lite pipeline complete.** Review generated artifacts in `{{planning_artifacts}}/` and `{{implementation_artifacts}}/`.
