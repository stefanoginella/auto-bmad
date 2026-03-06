---
name: 'auto-gds-plan'
description: 'Run the GDS pre-implementation pipeline: game vision, design, narrative, architecture, testing, and sprint setup'
---

# Load Configuration

Read `_bmad/gds/config.yaml` and set the following variables (resolve `{project-root}` to the actual project root path):

| Variable | Source | Example |
|----------|--------|---------|
| `{{output_folder}}` | gds `output_folder` | `_bmad-output` |
| `{{planning_artifacts}}` | gds `planning_artifacts` | `_bmad-output/planning-artifacts` |
| `{{implementation_artifacts}}` | gds `implementation_artifacts` | `_bmad-output/implementation-artifacts` |
| `{{auto_bmad_artifacts}}` | derived: `{{output_folder}}/auto-bmad-artifacts` | `_bmad-output/auto-bmad-artifacts` |

All paths in this command that reference BMAD output directories MUST use these variables — never hardcode `_bmad-output` paths.

# Load Project Context

Read `{{output_folder}}/project-context.md` if it exists. This gives you general context about the project — its purpose, stack, conventions, and current state. Use this context to make informed decisions throughout the pipeline.

# Pre-Implementation Pipeline

Run the GDS pre-implementation lifecycle as a minimal sequence of BMAD slash commands — lightweight orchestration with git safety.

Each step MUST run in its own **foreground Task tool call** (subagent_type: "general-purpose") so that each agent gets a fresh context window.

## User Input

The user MUST provide input alongside the command — a game idea, a description, a file path, or any context about what they want to build. Capture everything the user provides as {{USER_INPUT}}.

- If the input references a file (e.g., `@rough-idea.md`, a path), **read the file contents** and include them verbatim as part of {{USER_INPUT}}.
- **If no input is provided, STOP.** Tell the user that the plan pipeline requires game context.

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
   - `game-brief-*.md` — game brief exists
   - `gdd.md` or `gdd/` — GDD exists
   - `narrative-design.md` or `narrative-design/` — narrative design exists
   - `game-architecture.md` or `game-architecture/` — game architecture exists
   - `test-design-architecture.md` or `test-design-qa.md` — system-level test design exists
2. Scan `{{implementation_artifacts}}/` for:
   - `sprint-status.yaml` — sprint planning done
3. Scan for test framework configs (e.g., `jest.config.*`, `vitest.config.*`, game engine test configs, etc.) — test framework exists

Report which artifacts already exist and which steps will be skipped.

Set `{{USER_INPUT_INSTRUCTION}}` to: `The user provided the following vision for this game — treat it as the primary input and build the game brief around it:\n\n{{USER_INPUT}}`

# Pre-flight

Before running any steps, record:
- `{{START_TIME}}` — run `date -u +"%Y-%m-%dT%H:%M:%S"` via Bash and store the output
- `{{START_COMMIT_HASH}}` — run `git rev-parse --short HEAD` and store the result

# Pipeline Steps

After each successful step, the coordinator runs `git add -A && git commit --no-verify -m "wip(gds-plan): step N/8 <step-name> - done"` and prints a 1-line progress update: `Step N/8: <step-name> — <status>`. The coordinator must also track a running list of `(step_name, status, start_time, end_time)` — note the wall-clock time before and after each Task call to use in the final report.

## Phase 1: Vision

1. **Create Game Brief**
   - **Skip if:** game brief OR GDD already exists. Log "Game brief already exists" or "GDD already exists — game brief not needed".
   - **Task prompt:** `/bmad-gds-create-game-brief yolo — {{USER_INPUT_INSTRUCTION}}`

## Phase 2: Design

2. **Create GDD**
   - **Skip if:** GDD already exists. Log "GDD already exists".
   - **Task prompt:** `/bmad-gds-create-gdd ultrathink yolo — {{USER_INPUT_INSTRUCTION}}`

3. **Create Narrative Design**
   - **Skip if:** narrative design already exists. Also skip if the game has no narrative component (e.g., purely abstract puzzle game). Log reason.
   - **Task prompt:** `/bmad-gds-narrative ultrathink yolo`

## Phase 3: Solutioning

4. **Create Game Architecture**
   - **Skip if:** game architecture docs already exist. Log "Game architecture already exists".
   - **Task prompt:** `/bmad-gds-game-architecture ultrathink yolo`

5. **Test Framework Setup**
   - **Skip if:** test framework already configured. Log "Test framework already configured".
   - **Task prompt:** `/bmad-gds-gametest-framework yolo`

6. **Game Test Design**
   - **Skip if:** test-design-architecture.md and test-design-qa.md already exist. Log "System-level test design already exists".
   - **Task prompt:** `/bmad-gds-gametest-test-design ultrathink yolo — run in system-level mode using the GDD, game architecture docs, and epics as input. Focus on game-specific test scenarios: core gameplay loops, game systems interactions, state management, performance under load, and platform-specific behaviors.`

## Phase 4: Sprint Setup

7. **Generate Project Context**
   - **Task prompt:** `/bmad-gds-generate-project-context yolo`

8. **Sprint Planning**
   - **Skip if:** sprint-status.yaml already exists. Log "Sprint plan already exists".
   - **Task prompt:** `/bmad-gds-sprint-planning yolo`

# Pipeline Report

1. Record `{{END_TIME}}` — run `date -u +"%Y-%m-%dT%H:%M:%S"` via Bash and store the output.
2. Scan `{{output_folder}}/` recursively for files modified after `{{START_TIME}}` to build the artifact list.
3. Create `{{auto_bmad_artifacts}}/` directory if it doesn't exist.
4. Generate the report and save it to `{{auto_bmad_artifacts}}/gds-plan-report-YYYY-MM-DD-HHMMSS.md` (using `{{END_TIME}}` for the timestamp).
5. Print the full report to the user.

Use this template for the report:

```markdown
# Pipeline Report: gds-plan

| Field | Value |
|-------|-------|
| Pipeline | gds-plan |
| Start | {{START_TIME}} |
| End | {{END_TIME}} |
| Duration | <minutes>m |
| Initial Commit | {{START_COMMIT_HASH}} |

## Artifacts

- `<relative-path>` — new/updated

## Pipeline Outcome

| # | Step | Status | Duration | Summary |
|---|------|--------|----------|---------|
| 1 | Game Brief | done/skipped | Xm | <game vision/concept captured> |
| 2 | GDD | done/skipped | Xm | <key mechanics, scope summary, epic count> |
| 3 | Narrative Design | done/skipped | Xm | <story/lore scope, or why skipped (no narrative)> |
| 4 | Game Architecture | done/skipped | Xm | <engine/stack chosen, key systems (e.g. "Unity, ECS, state machine")> |
| 5 | Test Framework | done/skipped | Xm | <framework chosen> |
| 6 | Game Test Design | done/skipped | Xm | <test areas covered> |
| 7 | Project Context | done | Xm | <refreshed or newly generated> |
| 8 | Sprint Planning | done/skipped | Xm | <stories queued for first sprint> |

## Key Decisions & Learnings

- <short summary of important decisions made, issues encountered, or learnings from any step>
- <e.g. "Skipped narrative design — abstract puzzle game", "Architecture chose ECS over component hierarchy for scalability">

## Action Items

### Review
- [ ] Read through every generated artifact — GDD, game architecture, narrative design — before starting implementation
- [ ] GDD completeness — verify game mechanics, systems, and scope match the game vision
- [ ] Game architecture tech stack — confirm alignment with team skills and target platforms
- [ ] Narrative design — check consistency with gameplay and world-building goals
- [ ] Epic scoping/sizing — validate sprint capacity estimates
- [ ] Any skipped steps — if steps were skipped due to existing artifacts, verify those artifacts are still current and complete

### Attention
- [ ] <assumptions made in architecture — e.g. "assumes 2D engine", "chose tile-based over free-form movement">
- [ ] <missing game design elements — e.g. "no monetization model defined", "multiplayer sync TBD">
- [ ] <scope risks in sprint plan — e.g. "first sprint is ambitious", "dependency on asset pipeline not yet available">

### Next
- Start a new session with fresh context, then run `/auto-bmad-gds-epic-start <epic-number>` to prepare the first epic (test design)
- Then run `/auto-bmad-gds-story <epic-story>` for each story in the sprint (one story per session)
```

# Final Commit

1. `git reset --soft {{START_COMMIT_HASH}}` — squash all checkpoint commits, keep changes staged.
2. Commit with: `git add -A && git commit -m "chore: GDS plan — pre-implementation pipeline complete"`
3. Record the final git commit hash and print it to the user.

**From this point on, do NOT auto-commit.** Only commit when the user explicitly asks you to.