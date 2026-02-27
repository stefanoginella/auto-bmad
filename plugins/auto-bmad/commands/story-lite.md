---
name: 'auto-bmad-story-lite'
description: 'Lite BMAD story pipeline: only BMAD slash commands, no orchestration overhead'
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

# Detect Story ID

A story ID is composed by exactly 2 numbers: the epic number and the story number within that epic, separated by a dash, a dot, or a space. For example, "1-1" would be the first story in the first epic, "2-3" would be the third story in the second epic, and so on. A story ID can also be inferred from the path name if a path is provided when launching the workflow (e.g., `{{implementation_artifacts}}/1-2-authentication-system.yaml` would set the story ID to "1-2").

**IMPORTANT**: The dash (or dot/space) in a story ID is a SEPARATOR, not a range. `1-7` (or `1.7` or `1 7`) means "epic 1, story 7" — it does NOT mean "stories 1 through 7". This pipeline processes exactly ONE story per run. Never interpret a story ID as a range of stories.

IF user provides epic-story number (e.g. 1-1, 1-2, 2.1, 2.2, etc.) or a file path containing an epic-story pattern:
THEN set {{STORY_ID}} to the provided epic-story number (always a single story).
ELSE ask to provide a epic-story number to identify the story to work on and set {{STORY_ID}} to the provided value.

# Lite Story Pipeline

Run the BMAD story pipeline for story {{STORY_ID}} as a minimal sequence of BMAD slash commands — lightweight orchestration with git safety, no reports.

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
- `{{START_TIME}}` — current date+time in ISO 8601 format (e.g. `2026-02-26T14:30:00`)
- `{{START_COMMIT_HASH}}` — run `git rev-parse --short HEAD` and store the result

## Story File Path Resolution

After step 1 (Create) succeeds, glob `{{implementation_artifacts}}/{{STORY_ID}}-*.md` to find the story file and set {{STORY_FILE}} to its path. If the story file already existed (step 1 was skipped), set {{STORY_FILE}} the same way. All subsequent steps use {{STORY_FILE}}.

# Pipeline Steps

After each successful step, the coordinator runs `git add -A && git commit --no-verify -m "wip({{STORY_ID}}): step N/12 <step-name> - done"` and prints a 1-line progress update: `Step N/12: <step-name> — <status>`. The coordinator must also track a running list of `(step_name, status, start_time, end_time)` — note the wall-clock time before and after each Task call to use in the final report.

## Story Creation & Validation

1. **Story {{STORY_ID}} Create**
   - **Skip if:** a story file for {{STORY_ID}} already exists in `{{implementation_artifacts}}/` (glob for `{{STORY_ID}}-*.md`). Log "Story file already exists" with the file path. Set `{{STORY_FILE}}` to the existing file path.
   - **Task prompt:** `/bmad-bmm-create-story story {{STORY_ID}} yolo`

2. **Story {{STORY_ID}} Validate**
   - **Task prompt:** `/bmad-bmm-create-story validate story {{STORY_ID}} yolo — fix all issues, recommendations and optimizations.`

## Test-First

3. **Story {{STORY_ID}} ATDD**
   - **Task prompt:** `/bmad-tea-testarch-atdd {{STORY_FILE}} yolo`

## Development

4. **Story {{STORY_ID}} Develop**
   - **Task prompt:** `/bmad-bmm-dev-story {{STORY_FILE}} yolo`

## Code Reviews

5. **Story {{STORY_ID}} Code Review #1**
   - **Task prompt:** `/bmad-bmm-code-review {{STORY_FILE}} yolo — fix all critical, high, medium and low issues.`

6. **Story {{STORY_ID}} Code Review #2**
   - **Task prompt:** `/bmad-bmm-code-review {{STORY_FILE}} yolo — fix all critical, high, medium and low issues.`

7. **Story {{STORY_ID}} Code Review #3**
   - **Task prompt:** `/bmad-bmm-code-review {{STORY_FILE}} yolo — fix all critical, high, medium and low issues.`

## NFR Gate

8. **Story {{STORY_ID}} NFR**
   - **Task prompt:** `/bmad-tea-testarch-nfr {{STORY_FILE}} yolo`

## E2E Tests

9. **Story {{STORY_ID}} E2E**
   - **Task prompt:** `/bmad-bmm-qa-generate-e2e-tests {{STORY_FILE}} yolo`

## Traceability & Test Automation

10. **Story {{STORY_ID}} Trace**
   - **Task prompt:** `/bmad-tea-testarch-trace {{STORY_FILE}} yolo`

11. **Story {{STORY_ID}} Test Automate**
   - **Task prompt:** `/bmad-tea-testarch-automate {{STORY_FILE}} yolo`

12. **Story {{STORY_ID}} Test Review**
   - **Task prompt:** `/bmad-tea-testarch-test-review {{STORY_FILE}} yolo`

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

# Pipeline Report

1. Record `{{END_TIME}}` — current date+time in ISO 8601 format.
2. Scan `{{output_folder}}/` recursively for files modified after `{{START_TIME}}` to build the artifact list.
3. Create `{{auto_bmad_artifacts}}/` directory if it doesn't exist.
4. Generate the report and save it to `{{auto_bmad_artifacts}}/pipeline-report-story-lite-{{STORY_ID}}-YYYY-MM-DD-HHMMSS.md` (using `{{END_TIME}}` for the timestamp).
5. Print the full report to the user.

Use this template for the report:

```markdown
# Pipeline Report: story-lite [{{STORY_ID}}]

| Field | Value |
|-------|-------|
| Pipeline | story-lite |
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
| 3 | ATDD | done | Xm | <acceptance tests written count> |
| 4 | Develop | done | Xm | <files created/modified, key implementation summary> |
| 5 | Code Review #1 | done | Xm | <issues found/fixed count by severity> |
| 6 | Code Review #2 | done | Xm | <issues found/fixed count by severity> |
| 7 | Code Review #3 | done | Xm | <issues found/fixed count by severity> |
| 8 | NFR | done | Xm | <NFR assessment result (pass/concerns)> |
| 9 | E2E | done | Xm | <e2e tests generated count> |
| 10 | Trace | done | Xm | <traceability coverage %> |
| 11 | Test Automate | done | Xm | <tests automated count> |
| 12 | Test Review | done | Xm | <test quality verdict> |

## Key Decisions & Learnings

- <short summary of important decisions made, issues encountered, or learnings from any step>
- <e.g. "Code review #2 found SQL injection in auth module — fixed", "ATDD tests required mock service setup">

## Action Items

### Review
- [ ] Story implementation matches acceptance criteria
- [ ] Code review findings that were auto-fixed — verify fixes are correct

### Test
- [ ] Run the app and exercise the implemented feature
- [ ] Run test suites locally (`npm test`, `npx playwright test`, etc.)
- [ ] Verify edge cases from story spec

### Attention
- [ ] <NFR concerns flagged — e.g. "auth endpoint has no rate limiting", "no caching on frequently accessed data">
- [ ] <traceability gaps — e.g. "2 acceptance criteria not covered by tests">
- [ ] <test coverage gaps — e.g. "error handling paths not tested">
```
