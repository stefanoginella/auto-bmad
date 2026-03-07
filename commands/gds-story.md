---
name: 'auto-gds-story'
description: 'Develop a full GDS story from start to finish using sequential agents'
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

# Detect Story ID

A story ID is composed by exactly 2 numbers: the epic number and the story number within that epic, separated by a dash, a dot, or a space. For example, "1-1" would be the first story in the first epic, "2-3" would be the third story in the second epic, and so on. A story ID can also be inferred from the path name if a path is provided when launching the workflow (e.g., `{{implementation_artifacts}}/1-2-authentication-system.yaml` would set the story ID to "1-2").

**IMPORTANT**: The dash (or dot/space) in a story ID is a SEPARATOR, not a range. `1-7` (or `1.7` or `1 7`) means "epic 1, story 7" — it does NOT mean "stories 1 through 7". This pipeline processes exactly ONE story per run. Never interpret a story ID as a range of stories.

IF user provides epic-story number (e.g. 1-1, 1-2, 2.1, 2.2, etc.) or a file path containing an epic-story pattern:
THEN set {{STORY_ID}} to the provided epic-story number (always a single story).
ELSE ask to provide a epic-story number to identify the story to work on and set {{STORY_ID}} to the provided value.

Set {{EPIC_ID}} and {{STORY_NUM}} by splitting {{STORY_ID}} on the dash/dot/space separator.

# Story Pipeline

Run the GDS story pipeline for story {{STORY_ID}} as a minimal sequence of BMAD slash commands — lightweight orchestration with git safety, no reports.

Each step MUST run in its own **foreground Task tool call** (subagent_type: "general-purpose") so that each agent gets a fresh context window.

**CRITICAL — Tool usage rules:**
- **DO** use the Task tool (foreground, default mode) for each step. It blocks and returns the result.
- **DO NOT** use TeamCreate, SendMessage, TaskOutput, TaskCreate, or TaskList. This is a sequential pipeline, not a team collaboration.
- **DO NOT** launch multiple Task calls simultaneously. Wait for each to return before launching the next.
- **DO NOT** execute any step, fix, or implement new code yourself — always delegate to a Task agent.

**Retry policy:** If a step fails, run `git reset --hard HEAD` to discard its partial changes, then retry **once**. If the retry also fails, stop the pipeline and tell the user:
- Which step failed and why
- Recovery commands: `git reset --hard {{START_COMMIT_HASH}}` to roll back the entire pipeline, or `git reset --hard HEAD` to retry the failed step.

## Pre-flight

Record before running any steps:
- `{{START_TIME}}` — run `date -u +"%Y-%m-%dT%H:%M:%S"` via Bash and store the output
- `{{START_COMMIT_HASH}}` — run `git rev-parse --short HEAD` and store the result

## Story File Path Resolution

After step 1 (Create) succeeds, glob `{{implementation_artifacts}}/{{STORY_ID}}-*.md` to find the story file and set {{STORY_FILE}} to its path. If the story file already existed (step 1 was skipped), set {{STORY_FILE}} the same way. All subsequent steps use {{STORY_FILE}}.

# Pipeline Steps

After each successful step, the coordinator runs `git add -A && git commit --no-verify -m "wip({{STORY_ID}}): step N/11 <step-name> - done"` and prints a 1-line progress update: `Step N/11: <step-name> — <status>`. The coordinator must also track a running list of `(step_name, status, start_time, end_time)` — note the wall-clock time before and after each Task call to use in the final report.

## Story Creation & Validation

1. **Story {{STORY_ID}} Create**
   - **Skip if:** a story file for {{STORY_ID}} already exists in `{{implementation_artifacts}}/` (glob for `{{STORY_ID}}-*.md`). Log "Story file already exists" with the file path. Set `{{STORY_FILE}}` to the existing file path.
   - **Task prompt:** `/bmad-gds-create-story story {{STORY_ID}} yolo`

2. **Story {{STORY_ID}} Validate**
   - **Task prompt:** `/bmad-gds-create-story validate story {{STORY_ID}} yolo — fix all issues, recommendations and optimizations.`

3. **Story {{STORY_ID}} Adversarial Review**
   - **Task prompt:** `/bmad-review-adversarial-general {{STORY_FILE}} ultrathink yolo — review the story specification. Fix all issues found.`

## Development

4. **Story {{STORY_ID}} Develop**
   - **Task prompt:** `/bmad-gds-dev-story {{STORY_FILE}} ultrathink yolo`

## Reviews

5. **Story {{STORY_ID}} Edge-Case Hunt**
   - **Task prompt:** `/bmad-review-edge-case-hunter ultrathink yolo — run git diff {{START_COMMIT_HASH}} to get the production code changes as content. Fix all relevant findings by adding the suggested guards.`

6. **Story {{STORY_ID}} Code Review #1**
   - **Task prompt:** `/bmad-gds-code-review {{STORY_FILE}} ultrathink yolo — fix all critical, high, and medium issues. For low issues, report them but only fix if they have concrete evidence (file:line) — do not fix style preferences or hypothetical concerns as low findings.`

7. **Story {{STORY_ID}} Code Review #2**
   - **Task prompt:** `/bmad-gds-code-review {{STORY_FILE}} yolo — fix all critical, high, and medium issues. For low issues, report them but only fix if they have concrete evidence (file:line) — do not fix style preferences or hypothetical concerns as low findings.`

8. **Story {{STORY_ID}} Code Review #3**
   - **Task prompt:** `/bmad-gds-code-review {{STORY_FILE}} yolo — fix all critical, high, and medium issues. For low issues, report them but only fix if they have concrete evidence (file:line) — do not fix style preferences or hypothetical concerns as low findings.`

## Performance & Test Automation

9. **Story {{STORY_ID}} Performance**
   - **Task prompt:** `/bmad-gds-gametest-performance {{STORY_FILE}} yolo`

10. **Story {{STORY_ID}} Test Automate**
    - **Task prompt:** `/bmad-gds-gametest-automate {{STORY_FILE}} yolo — when expanding test coverage, focus on game-specific scenarios: gameplay loops, state transitions, system interactions, and edge cases in game logic.`

11. **Story {{STORY_ID}} Test Review**
    - **Task prompt:** `/bmad-gds-gametest-test-review {{STORY_FILE}} yolo — review game test quality, coverage of gameplay scenarios, and ensure test reliability across game states.`

# Story File Update

After the pipeline steps 11 is complete, the coordinator should check if the `{{STORY_FILE}}` has been updated  or if it looks incomplete. Especially look if it contains the findings and fixes from each review (split by review), if anything after `## Dev Agent Record` looks empty or has a placehoder text and if all completed tasks have been marked as done.

If something is missing, it should update the story file with that information before proceeding to the next step. This ensures that the story file remains the single source of truth for the story's implementation and review history, and that all relevant information is captured in one place for traceability and reporting purposes. Follow the same pattern as previous story files.

# Status Update

Before generating the report, the coordinator MUST check and update the story status:

1. Read `{{STORY_FILE}}` — if the story status is not updated to reflect completion of all pipeline steps, update it accordingly.
2. Read `{{implementation_artifacts}}/sprint-status.yaml` — if the story's status is not updated to reflect completion, update it accordingly.
3. Run `git add -A && git commit --no-verify -m "wip({{STORY_ID}}): update story and sprint status"` to checkpoint the status updates.

# Pipeline Report

1. Record `{{END_TIME}}` — run `date -u +"%Y-%m-%dT%H:%M:%S"` via Bash and store the output.
2. Scan `{{output_folder}}/` recursively for files modified after `{{START_TIME}}` to build the artifact list.
3. Create `{{auto_bmad_artifacts}}/` directory if it doesn't exist.
4. Generate the report and save it to `{{auto_bmad_artifacts}}/epic-{{EPIC_ID}}-story-{{STORY_NUM}}-YYYY-MM-DD-HHMMSS.md` (using `{{END_TIME}}` for the timestamp).
5. Print the full report to the user.

Use this template for the report:

```markdown
# Pipeline Report: epic {{EPIC_ID}} story {{STORY_NUM}}

| Field | Value |
|-------|-------|
| Pipeline | gds-story |
| Story | {{STORY_ID}} |
| Start | {{START_TIME}} |
| End | {{END_TIME}} |
| Duration | <minutes>m |
| Initial Commit | {{START_COMMIT_HASH}} |

## Artifacts

- `<relative-path>` — new/updated

## Pipeline Outcome

| # | Step | Status | Duration | Summary |
|---|------|--------|----------|---------|
| 1 | Story Create | done/skipped | Xm | <story title/scope> |
| 2 | Story Validate | done | Xm | <issues found and fixed count> |
| 3 | Adversarial Review | done | Xm | <issues found/fixed count by severity> |
| 4 | Develop | done | Xm | <files created/modified, key implementation summary> |
| 5 | Edge-Case Hunt | done | Xm | <unhandled paths found/fixed count> |
| 6 | Code Review #1 | done | Xm | <issues found/fixed count by severity> |
| 7 | Code Review #2 | done | Xm | <issues found/fixed count by severity> |
| 8 | Code Review #3 | done | Xm | <issues found/fixed count by severity> |
| 9 | Performance | done | Xm | <performance assessment result (pass/concerns)> |
| 10 | Test Automate | done | Xm | <tests automated count, game scenarios covered> |
| 11 | Test Review | done | Xm | <test quality verdict, coverage gaps flagged> |

## Key Decisions & Learnings

- <short summary of important decisions made, issues encountered, or learnings from any step>
- <e.g. "Code review #2 found state desync in multiplayer — fixed", "Performance test revealed frame drops in particle system">

## Action Items

### Review
- [ ] Verify story implementation matches acceptance criteria — spot-check key gameplay flows
- [ ] Audit auto-fixed code review findings — confirm fixes are correct, not just silencing warnings

### Verify
- [ ] Run full test suite locally and confirm green
- [ ] Playtest the feature — happy path only, focus on game feel and interaction quality
- [ ] Check game states that automated tests can't catch (animations, visual effects, audio sync, input responsiveness)

### Attention
- [ ] <performance concerns flagged — e.g. "frame rate drops during particle effects", "memory leak in asset loading">
- [ ] <gameplay edge cases — e.g. "untested state when player pauses during transition">
- [ ] <test coverage gaps — e.g. "multiplayer sync scenarios not automated">

### Next
- Start a new session with fresh context, then run `/auto-bmad-gds-story <next-story>` for the next story in the sprint
- After all stories in the epic are done, start a new session and run `/auto-bmad-gds-epic-end <epic-number>` to close the epic
```

# Final Commit

1. `git reset --soft {{START_COMMIT_HASH}}` — squash all checkpoint commits, keep changes staged.
2. Read {{STORY_FILE}} to determine the story type and what was built, then commit:

```
git add -A && git commit -m "<type>({{STORY_ID}}): <one-line summary>

<2-5 line summary or list of what was implemented>"
```

Derive `<type>` from the story using this table (default to `feat` if ambiguous):

| Type | When to use |
|------|------------|
| `feat` | New user-facing feature or capability |
| `fix` | Bug fix |
| `refactor` | Code restructuring, no behavior change |
| `perf` | Performance improvement |
| `chore` | Dependencies, configs, tooling, maintenance |
| `docs` | Documentation only |
| `test` | Tests only, no production code |
| `style` | Formatting, whitespace, no logic change |
| `ci` | CI/CD pipeline changes |
| `build` | Build system or external dependency changes |

The one-line summary should describe the user-facing outcome, not "story complete".

**From this point on, do NOT auto-commit.** Only commit when the user explicitly asks you to.
