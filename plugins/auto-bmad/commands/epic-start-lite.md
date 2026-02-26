---
name: 'auto-bmad-epic-start-lite'
description: 'Lite BMAD epic start: epic-level test design only, no orchestration overhead'
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

# Lite Epic Start Pipeline

Prepare epic {{EPIC_ID}} with a single BMAD slash command — epic-level test design. No orchestration overhead, no reports, no git operations. For testing BMAD workflows.

The step MUST run in its own **foreground Task tool call** (subagent_type: "general-purpose") so that the agent gets a fresh context window.

**CRITICAL — Tool usage rules:**
- **DO** use the Task tool (foreground, default mode) for the step. It blocks and returns the result.
- **DO NOT** use TeamCreate, SendMessage, TaskOutput, TaskCreate, or TaskList.
- **DO NOT** execute any step yourself — always delegate to a Task agent.

**Retry policy:** If the step fails, retry it **once**. If the retry also fails, stop and report to the user.

# Pipeline Steps

1. **Epic {{EPIC_ID}} Test Design** *(always runs — never skip)*
   - **Task prompt:** `/bmad-tea-testarch-test-design yolo — run in epic-level mode for epic {{EPIC_ID}}.`

# Done

Print: **Epic-start-lite pipeline complete for epic {{EPIC_ID}}.** Review the test design in `{{planning_artifacts}}/`.
