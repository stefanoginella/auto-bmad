---
name: 'auto-bmad-epic-end-lite'
description: 'Lite BMAD epic end: trace, retrospective, and project context refresh only, no orchestration overhead'
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

# Lite Epic End Pipeline

Close epic {{EPIC_ID}} with BMAD slash commands only — traceability, retrospective, and project context refresh. No orchestration overhead, no reports, no git operations. For testing BMAD workflows.

Each step MUST run in its own **foreground Task tool call** (subagent_type: "general-purpose") so that each agent gets a fresh context window.

**CRITICAL — Tool usage rules:**
- **DO** use the Task tool (foreground, default mode) for each step. It blocks and returns the result.
- **DO NOT** use TeamCreate, SendMessage, TaskOutput, TaskCreate, or TaskList. This is a sequential pipeline, not a team collaboration.
- **DO NOT** launch multiple Task calls simultaneously. Wait for each to return before launching the next.
- **DO NOT** execute any step yourself — always delegate to a Task agent.

**Retry policy:** If a step fails, retry it **once**. If the retry also fails, stop the pipeline and report to the user which step failed and why.

# Pipeline Steps

After each step completes, print a 1-line progress update: `Step N/3: <step-name> — <status>`

1. **Epic {{EPIC_ID}} Trace** *(always runs — never skip)*
   - **Task prompt:** `/bmad-tea-testarch-trace yolo — run in epic-level mode for epic {{EPIC_ID}}.`

2. **Epic {{EPIC_ID}} Retrospective** *(always runs — never skip)*
   - **Task prompt:** `/bmad-bmm-retrospective epic {{EPIC_ID}} yolo`

3. **Epic {{EPIC_ID}} Project Context Refresh** *(always runs — never skip)*
   - **Task prompt:** `/bmad-bmm-generate-project-context yolo`

# Done

Print: **Epic-end-lite pipeline complete for epic {{EPIC_ID}}.** Review retrospective and updated project context.
