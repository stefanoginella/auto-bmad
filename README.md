# auto-bmad — Automated BMAD Pipeline

Fully automated story and epic pipeline orchestration using multiple AI CLIs. Designed for unattended execution in a sandboxed environment (VM, container, etc).

> **Warning:** These scripts execute AI agents with full filesystem access (`--dangerously-skip-permissions`, `--full-auto`, `--yolo`). Run only in isolated environments.

## Overview

Two scripts work together:

| Script | Scope | What it does |
|--------|-------|-------------|
| `auto-bmad-story.sh` | One story | Runs a single story through the full BMAD pipeline (14+ steps, 7 phases) using multiple AI CLIs |
| `auto-bmad-epic.sh` | One epic | Loops through all stories in an epic, delegating each to the story script, with PR + CI between stories |

## Architecture

```
auto-bmad-epic.sh
  │
  ├── Story 1 ──→ auto-bmad-story.sh --story 1-1-slug
  │                 └── 14+ steps across 7 phases
  │                 └── 4 AI CLIs in parallel for reviews
  │
  ├── git: commit → push → PR → auto-merge (squash) → wait for CI
  │
  ├── Story 2 ──→ auto-bmad-story.sh --story 1-2-slug
  │                 └── ...
  │
  ├── git: commit → push → PR → auto-merge → wait for CI
  │
  └── Story N ──→ auto-bmad-story.sh --story 1-N-slug
                    └── ...
                    └── Phase 6: retrospective, NFR, project context
```

## Prerequisites

- **BMad framework** installed (`_bmad/` directory with matching version in manifest)
- **Sprint status** generated (`_bmad-output/implementation-artifacts/sprint-status.yaml`)
- **AI CLI tools** in PATH: `claude`, `codex`, `gemini`, `opencode`
- **GitHub CLI** (`gh`) authenticated (for PR creation between stories)
- **Git** repository with `main` branch

---

## auto-bmad-story.sh

Automates one story through the full BMAD implementation workflow.

### Usage

```bash
./auto-bmad-story.sh [options]

Options:
  --story STORY_ID       Override auto-detection (e.g., 1-2-database-schemas)
  --from-step STEP_ID    Resume from a specific step (e.g., 6a, 8)
  --dry-run              Preview all steps without executing
  --skip-epic-phases     Skip phases 0 and 6 even at epic boundaries
  --help                 Show usage
```

### Pipeline Phases

| Phase | Steps | Name | What happens |
|-------|-------|------|-------------|
| 0 | 0 | Epic Start | TEA Test Design at epic level. *Only runs on the first story in an epic.* |
| 1 | 1, 2a-2e, 3a-3e | Story Preparation | Create story, validate (4 AIs + arbiter), adversarial review (4 AIs + arbiter) |
| 2 | 4, 5 | TDD + Implementation | Generate failing acceptance tests (red phase), then implement (green phase) |
| 3 | 6a-6e | Edge Cases | 4 parallel edge case hunters + arbiter applies fixes |
| 4 | 7a-7d, 8 | Code Review | 4 parallel code reviewers + arbiter applies fixes |
| 5 | 9, 10 | Traceability | Testarch trace + test automation expansion |
| 6 | 11a-11c, 12, 13 | Epic End | Epic trace/NFR/test review, retrospective, project context. *Only runs on the last story in an epic.* |
| 7 | 14a, 14b | Finalization | Tech writer documents story, scrum master closes it |

### AI Profiles

Six AI profiles are assigned to different steps based on the task:

| Profile | CLI / Model | Effort | Used for |
|---------|-------------|--------|----------|
| `AI_OPUS` | Claude Opus 4.6 | max | Critical path, arbiters, implementation |
| `AI_SONNET` | Claude Sonnet 4.6 | high | Lightweight bookkeeping (traceability, closing) |
| `AI_GPT` | Codex GPT 5.4 | xhigh | Mechanical steps, parallel reviews |
| `AI_GEMINI` | Gemini 3 Pro | — | Parallel reviews |
| `AI_MINIMAX` | OpenCode MiniMax M2.5 | max | Parallel reviews |
| `AI_MIMO` | OpenCode MiMo V2 Pro | max | Parallel reviews |

### Multi-AI Review Pattern

Reviews (validation, adversarial, edge cases, code review) use a **4-way parallel review + arbiter** pattern:

1. Four AI CLIs review independently in parallel (GPT, Gemini, MiniMax, MiMo)
2. Each produces a findings report saved to the story artifacts directory
3. An arbiter (Claude Opus) cross-references all findings using consensus rules:
   - **4/4 agree**: fix immediately
   - **3/4 agree**: fix, good confidence
   - **2/4 agree**: evaluate both sides, fix if substantive
   - **1/4 flag**: only fix if clearly a real issue with concrete impact

### Git Workflow

The story script creates a `story/{STORY_ID}` branch from `main` at the start. After completion, the branch is left with all changes — merging is handled by the epic script or manually.

### Story Detection

Auto-detects the next story from `sprint-status.yaml`:
1. Prioritizes stories with status `in-progress` (resume interrupted work)
2. Falls back to the first story with status `backlog`
3. Epic boundary detection is automatic based on story position

### Artifacts

Per-story artifacts are saved to `_bmad-output/implementation-artifacts/auto-bmad/{SHORT_ID}-/`:
- Review findings from each AI (`*-validate-*.md`, `*-adversarial-*.md`, `*-edge-cases-*.md`, `*-review-*.md`)
- Pipeline metrics (`*--pipeline-metrics.md`)
- Pipeline log (deleted on success)

### Resume on Failure

If a step fails, the script exits with a resume command:

```
Resume: ./auto-bmad-story.sh --from-step 6a --story 1-2-database-schemas
```

---

## auto-bmad-epic.sh

Thin orchestration wrapper that runs all stories in an epic sequentially.

### Usage

```bash
./auto-bmad-epic.sh [options]

Options:
  --epic EPIC_ID         Target epic number (e.g., 1). Auto-detects if omitted.
  --from-story ID        Resume from a specific story (e.g., 1-3-some-slug)
  --dry-run              Preview the full epic plan without executing
  --no-merge             Skip auto-PR/merge between stories (manual git)
  --help                 Show usage
```

### What It Does

1. **Parses `sprint-status.yaml`** to collect all stories for the target epic
2. **Loops sequentially** — calls `./auto-bmad-story.sh --story STORY_ID` for each
3. **PR + auto-merge between stories** — after each story completes:
   - Commits changes on the story branch
   - Pushes and creates a PR via `gh`
   - Enables auto-merge (squash)
   - Polls for CI to pass (30s interval, 15-minute timeout)
   - Switches to `main` after merge
4. **Tracks epic-level metrics** — per-story durations, total wall time
5. **Prints retrospective summary** — after the last story, parses the retrospective output for action items and significant discovery alerts

### Epic Detection

When `--epic` is omitted:
1. Finds the first epic with `in-progress` status in sprint-status.yaml
2. Falls back to the first epic with `backlog` status

### Story Filtering

- Stories with status `done` are skipped
- `--from-story` skips all stories before the specified one (for resuming)

### Git Workflow Between Stories

```
Story completes on story/1-1-slug branch
  → git add -A && git commit (extracts commit message from story file)
  → git push -u origin story/1-1-slug
  → gh pr create --title "feat(epic-1): 1-1-slug"
  → gh pr merge --auto --squash
  → poll until merged (15 min timeout)
  → git checkout main && git pull
  → git branch -d story/1-1-slug
Next story starts from main
```

With `--no-merge`: skips all git operations between stories. Use this for manual git control.

### Commit Messages

The script attempts to extract the conventional commit message that the tech writer (step 14a) places in the story file's `## Auto-bmad Completion` section. Falls back to `feat(epic-N): implement story STORY_ID`.

### Failure Handling

**Story pipeline failure:**
```
Epic 1 — STORY FAILED

  Failed story:      1-3-ci-pipeline (story 3 of 5)
  Stories completed: 2/5

  Resume (story):  ./auto-bmad-story.sh --story 1-3-ci-pipeline --from-step <step>
  Resume (epic):   ./auto-bmad-epic.sh --epic 1 --from-story 1-3-ci-pipeline
```

**CI failure on PR:**
```
CI failed on PR for story 1-2-database-schemas
  PR URL: https://github.com/.../pull/42

  Fix CI, merge the PR manually, then resume:
  ./auto-bmad-epic.sh --epic 1 --from-story 1-3-ci-pipeline
```

### Retrospective Summary

After the last story completes (which triggers the retrospective via Phase 6), the epic script parses the retrospective file and prints:
- Action items with owners and deadlines
- Critical path blockers
- Significant discovery alerts (if the retrospective flagged issues that may invalidate the next epic)

This is informational — no blocking gate. Review before starting the next epic.

### Artifacts

Epic-level artifacts go to `_bmad-output/implementation-artifacts/auto-bmad/epic-{N}/`:
- `epic-{N}-metrics.md` — per-story timing table and totals
- `epic-pipeline.log` — full log (deleted on success)

---

## Examples

```bash
# Preview what the next epic would do
./auto-bmad-epic.sh --dry-run

# Run epic 1 end-to-end
./auto-bmad-epic.sh --epic 1

# Resume epic after a story failure
./auto-bmad-epic.sh --epic 1 --from-story 1-3-ci-pipeline

# Run without auto-PR (manual git between stories)
./auto-bmad-epic.sh --epic 1 --no-merge

# Run a single story manually
./auto-bmad-story.sh --story 1-2-database-schemas

# Resume a failed story from a specific step
./auto-bmad-story.sh --story 1-2-database-schemas --from-step 6a

# Preview a single story's pipeline
./auto-bmad-story.sh --story 1-2-database-schemas --dry-run
```

## Sprint Status Format

Both scripts read from `sprint-status.yaml`:

```yaml
epic-1: in-progress
1-1-monorepo-setup: done
1-2-database-schemas: in-progress
1-3-ci-pipeline: backlog
epic-1-retrospective: optional

epic-2: backlog
2-1-source-crud: backlog
2-2-health-monitoring: backlog
epic-2-retrospective: optional
```

**Status values:**

| Type | Statuses |
|------|----------|
| Epic | `backlog` → `in-progress` → `done` |
| Story | `backlog` → `ready-for-dev` → `in-progress` → `review` → `done` |
| Retrospective | `optional` ↔ `done` |

## Customization

### AI Profiles

Edit the six `AI_*` variables at the top of `auto-bmad-story.sh` to change which models handle which tasks. Format: `"cli|model|effort"`.

### Step Assignment

Edit `step_config()` in `auto-bmad-story.sh` to reassign steps to different AI profiles.

### CI Timeout

Edit `PR_MERGE_TIMEOUT` in `auto-bmad-epic.sh` (default: 900 seconds / 15 minutes).

### Poll Interval

Edit `PR_POLL_INTERVAL` in `auto-bmad-epic.sh` (default: 30 seconds).
