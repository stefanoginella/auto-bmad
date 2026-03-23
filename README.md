# auto-bmad

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE.md)
[![Language: Bash](https://img.shields.io/badge/Language-Bash-green.svg)]()
[![AI CLIs: 4](https://img.shields.io/badge/AI_CLIs-4-orange.svg)]()
[![BMad: 6.2.0](https://img.shields.io/badge/BMad-6.2.0-purple.svg)](https://github.com/bmad-code-org/BMAD-METHOD)
[![TEA: 1.7.1](https://img.shields.io/badge/TEA-1.7.1-red.svg)](https://github.com/bmad-code-org/bmad-method-test-architecture-enterprise)

Fully automated BMAD pipeline orchestration using multiple AI CLIs in parallel. Runs stories through 14+ steps across 7 phases with structured triage reviews — designed for unattended, sandboxed execution.

- **3 AI providers** (Claude, GPT, MiMo) running review steps in parallel
- **14+ pipeline steps** across 7 phases per story — from story creation to documentation
- **6-way parallel reviews** (spec + code) with structured triage and automated fix
- **Full epic orchestration** with automatic PR, CI gating, and squash-merge between stories

> **Warning:** By default, these scripts execute AI agents with full filesystem access (`--dangerously-skip-permissions`, `--full-auto`, `--yolo`). Run only in isolated environments (VM, container, etc), or use `--safe-mode` to let each AI tool prompt for permissions.

## Table of Contents

- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Story Pipeline](#story-pipeline-auto-bmad-storysh)
- [Epic Pipeline](#epic-pipeline-auto-bmad-epicsh)
- [Sprint Status Format](#sprint-status-format)
- [Customization](#customization)
- [Troubleshooting](#troubleshooting)
- [Examples](#examples)
- [Lineage](#lineage)
- [License](#license)

## Quick Start

```bash
# 1. Clone and copy (or symlink) scripts into your BMAD project root
git clone https://github.com/user/auto-bmad.git
cp -p auto-bmad/auto-bmad-story.sh auto-bmad/auto-bmad-epic.sh /path/to/your/project/

# 2. Edit the AI profiles and step assignments at the top of auto-bmad-story.sh

# 3. Run a single story
./auto-bmad-story.sh

# 4. Run an entire epic
./auto-bmad-epic.sh
```

The story script auto-detects the next story from `sprint-status.yaml`. The epic script loops through all stories in an epic, handling PR + CI + merge between them. See [How It Works](#how-it-works) for the full picture.

## How It Works

This project is opinionated — it assumes a specific git workflow (branch-per-story, squash-merge PRs, CI gates) and uses multiple AI CLIs simultaneously. The entire pipeline is defined in two shell scripts with plain configuration at the top — edit the AI profiles, step assignments, or git workflow to fit your setup.

Two scripts work together:

| Script | Scope | What it does |
|--------|-------|-------------|
| `auto-bmad-story.sh` | One story | Runs a single story through the full BMAD pipeline (14+ steps, 7 phases) using multiple AI CLIs in parallel |
| `auto-bmad-epic.sh` | One epic | Loops through all stories in an epic, delegating each to the story script, with PR + CI between stories |

### Architecture

```
auto-bmad-epic.sh
  │
  ├── Story 1 ──→ auto-bmad-story.sh
  │     ├─ Phase 0: Epic start (TEA test design)
  │     ├─ Phase 1: Story prep
  │     │     ├── 6 parallel spec reviews (3 AIs × validate + adversarial)
  │     │     ├── Spec Triage (Opus) — normalize, dedup, classify
  │     │     └── Fix patch items (Opus/analyst)
  │     ├─ Phase 2: TDD + implementation
  │     ├─ Phase 3: Code review
  │     │     ├── 6 parallel code reviews (3 AIs × edge-cases + adversarial)
  │     │     ├── Acceptance Auditor (Opus)
  │     │     ├── Triage (Opus) — normalize, dedup, classify
  │     │     └── Dev fix (Opus) — patch items only
  │     ├─ Phase 4: Traceability
  │     ├─ Phase 5: Epic end (retro, NFR, context)
  │     └─ Phase 6: Finalization (docs + close)
  │
  ├── git: commit → push → PR → squash-merge → CI ✓
  │
  ├── Story 2 ──→ auto-bmad-story.sh ...
  │
  └── Story N ──→ ...
```

### Multi-AI Review Pattern

Both spec reviews (Phase 1) and code reviews (Phase 3) use the same structured triage pattern:

1. **6 parallel reviews** — 3 AIs (GPT, MiMo, Claude) each run two review types in parallel
2. **Triage** (Opus) — normalizes and deduplicates all findings across all 6 reviews, then classifies each into:

| Category | Meaning | Action |
|----------|---------|--------|
| **patch** | Issue fixable without human input | Fixed automatically |
| **intent_gap** | Spec/intent is incomplete | Flagged for human review |
| **bad_spec** | Upstream spec is wrong or ambiguous | Flagged for spec amendment |
| **defer** | Pre-existing issue, not caused by this change | Noted for future attention |
| **reject** | Noise, false positive, or handled elsewhere | Dropped |

3. **Fix** — automatically fixes all `patch` items (analyst for spec, dev for code)

Phase 3 adds an **Acceptance Auditor** (Opus) before triage that verifies every acceptance criterion against the implementation: PASS / PARTIAL / FAIL / UNTESTABLE.

Triage evaluates on **argument quality**, not reviewer count. A single reviewer demonstrating a concrete bug outweighs four reviewers raising vague concerns. The spec triage is additionally conservative — findings that add NEW requirements not present in the epic or architecture are classified as `intent_gap` or `reject`, not `patch`, preventing scope creep. The triage report includes a reviewer signal assessment and overlap matrix for tuning the reviewer lineup over time.

## Prerequisites

### Required

- **Bash** 3.2+
- **Git** repository with a `main` branch
- **BMad framework** installed (`_bmad/` directory) — tested against BMad 6.2.0 / TEA 1.7.1
- **Sprint status** generated at `_bmad-output/implementation-artifacts/sprint-status.yaml`

### AI CLIs (all three needed for full parallel reviews)

- [`claude`](https://docs.anthropic.com/en/docs/claude-code) — Claude Code CLI
- [`codex`](https://github.com/openai/codex) — OpenAI Codex CLI
- [`opencode`](https://github.com/opencode-ai/opencode) — OpenCode CLI (MiMo)

### For auto-merge between stories

- [`gh`](https://cli.github.com/) — GitHub CLI, authenticated

> **Note:** Each story runs 14+ AI invocations across 3 providers. This is extremely token-hungry — budget accordingly.

## Installation

The scripts must live in the root of your BMAD project (they derive `PROJECT_ROOT` from their own location).

```bash
# Clone
git clone https://github.com/user/auto-bmad.git

# Copy scripts into your project root (preserves executable bit)
cp -p auto-bmad/auto-bmad-story.sh auto-bmad/auto-bmad-epic.sh /path/to/your/project/

# — or symlink to stay in sync with upstream —
ln -s "$(pwd)/auto-bmad/auto-bmad-story.sh" /path/to/your/project/auto-bmad-story.sh
ln -s "$(pwd)/auto-bmad/auto-bmad-epic.sh" /path/to/your/project/auto-bmad-epic.sh

# Verify
./auto-bmad-story.sh --help
./auto-bmad-epic.sh --help
```

## Story Pipeline (`auto-bmad-story.sh`)

Automates one story through the full BMAD implementation workflow.

### Usage

```bash
./auto-bmad-story.sh [options]

Options:
  --story STORY_ID       Override auto-detection (e.g., 1-2-database-schemas)
  --from-step STEP_ID    Resume from a specific step (e.g., 3.1, 6.1)
  --dry-run              Preview all steps without executing
  --skip-epic-phases     Skip phases 0 and 5 even at epic boundaries
  --skip-tea             Skip TEA phases even if installed (0, 2.1, 4.x, 5.1-5.3)
  --skip-reviews         Skip all review phases (1.2-1.4, 3.x)
  --fast-reviews         Run only 1 GPT reviewer per phase, skip triage+fix
  --skip-git             Skip git write ops (branch, checkpoint, squash)
  --no-traces            Remove pipeline artifacts after finalization
                         (pipeline report is kept)
  --safe-mode            Disable permission-bypass flags (AI tools prompt for approval)
  --help                 Show usage
```

### Pipeline Phases

| Phase | Steps | Name | What happens |
|-------|-------|------|-------------|
| 0 | 0.1 | Epic Start | TEA Test Design at epic level. *Only runs on the first story in an epic.* |
| 1 | 1.1, 1.2a-f, 1.3, 1.4 | Story Preparation | Create story, 6 parallel spec reviews (3 AIs × validate + adversarial), triage, fix patch items |
| 2 | 2.1, 2.2 | TDD + Implementation | Generate failing acceptance tests (red phase), then implement (green phase) |
| 3 | 3.1a-f, 3.2, 3.3, 3.4 | Code Review | 6 parallel code reviews (3 AIs × 2 types), acceptance audit, triage, dev fix |
| 4 | 4.1, 4.2 | Traceability | Testarch trace + test automation expansion |
| 5 | 5.1-5.3, 5.4, 5.5 | Epic End | Epic trace/NFR/test review, retrospective, project context. *Only runs on the last story in an epic.* |
| 6 | 6.1, 6.2 | Finalization | Tech writer documents story, scrum master closes it |

### AI Profiles

Six AI profiles are assigned to different steps based on the task:

| Profile | CLI / Model | Effort | Used for |
|---------|-------------|--------|----------|
| `AI_OPUS` | Claude Opus 4.6 | max | Critical path: triage, fix, implementation |
| `AI_OPUS_HIGH` | Claude Opus 4.6 | high | Structured, non-critical: spec reviews, code reviews, retro, docs |
| `AI_SONNET` | Claude Sonnet 4.6 | high | Lightweight bookkeeping: traceability, closing |
| `AI_GPT` | Codex GPT 5.4 | xhigh | Code reviews, edge cases |
| `AI_GPT_HIGH` | Codex GPT 5.4 | high | Spec-level reviews (pre-implementation) |
| `AI_MIMO` | OpenCode MiMo V2 Pro | max | Parallel reviews |

### Story Detection

Auto-detects the next story from `sprint-status.yaml`:
1. Prioritizes stories with status `in-progress` (resume interrupted work)
2. Falls back to the first story with status `backlog`
3. Epic boundary detection is automatic based on story position

### Git Workflow

The story script creates a `story/{STORY_ID}` branch from `main` at the start. During execution, each phase commits a checkpoint (`wip(1-1): phase N - name`) so work is recoverable if the pipeline fails mid-run. At the end, all checkpoint commits are squashed into a single commit using the conventional-commit message from the story file's Auto-bmad Completion section.

### Artifacts

Per-story artifacts are saved to `_bmad-output/implementation-artifacts/auto-bmad/{SHORT_ID}/`:
- Spec triage (`*-1.3-spec-triage.md`) — classified spec findings with reviewer signal assessment and overlap matrix
- Code acceptance audit (`*-3.2-code-acceptance.md`) — AC compliance matrix (PASS / PARTIAL / FAIL per criterion)
- Code triage (`*-3.3-code-triage.md`) — classified code findings with reviewer signal assessment and overlap matrix
- Pipeline report (`pipeline-report.md`) — timestamps, CLI/model per step, wall/compute time, git diff stats

### Review Modes

Both Phase 1 (spec) and Phase 3 (code) run 6 parallel reviews (3 AIs × 2 types) with structured triage and automated fix. Two flags control this:

- **`--fast-reviews`** — Run only the first GPT reviewer per phase, skip triage+fix steps. Good for iteration.
- **`--skip-reviews`** — Skip all review phases entirely. Pipeline becomes: create story → implement → document → close. Supersedes `--fast-reviews` if both are passed.

### Safe Mode (`--safe-mode`)

Disables the permission-bypass flags (`--dangerously-skip-permissions`, `--full-auto`, `--yolo`) so each AI CLI uses its native permission prompting. The pipeline will pause at each step for user approval instead of running unattended.

Useful for:
- **First run on a new codebase** — review what each AI step does before trusting it
- **After model updates** — verify behavior hasn't shifted
- **Combined with `--skip-git`** — the most conservative possible run (`--safe-mode --skip-git`)

### No Traces Mode (`--no-traces`)

Removes all pipeline-generated artifacts after finalization — review reports, triage reports, the entire `auto-bmad/{SHORT_ID}/` directory. The pipeline report is preserved at `auto-bmad/pipeline-report--{SHORT_ID}.md`.

This is useful when the review reports have already been indexed into the story file and you don't want leftover pipeline files in the repo.

### Resume on Failure

Each phase is checkpointed as a git commit, so if the pipeline fails you won't lose prior phases. The script exits with a resume command:

```
Resume: ./auto-bmad-story.sh --from-step 3.1 --story 1-2-database-schemas
```

See [Troubleshooting](#troubleshooting) for common failure scenarios.

## Epic Pipeline (`auto-bmad-epic.sh`)

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

Story pass-through flags (forwarded to auto-bmad-story.sh):
  --skip-epic-phases     Skip phases 0 (epic start) and 5 (epic end)
  --skip-tea             Skip TEA phases even if installed
  --skip-reviews         Skip all review phases (1.2-1.4, 3.x)
  --fast-reviews         Run only 1 GPT reviewer per phase, skip triage+fix
  --skip-git             Skip git write ops (branch, checkpoint, squash)
  --no-traces            Remove pipeline artifacts after finalization
  --safe-mode            Disable permission-bypass flags (AI tools prompt for approval)
```

### What It Does

1. **Parses `sprint-status.yaml`** to collect all stories for the target epic
2. **Loops sequentially** — calls `./auto-bmad-story.sh --story STORY_ID` for each
3. **PR + auto-merge between stories** — after each story completes:
   - Commits changes on the story branch
   - Pushes and creates a PR via `gh`
   - Enables auto-merge (squash)
   - Polls CI check states every 30s until all checks resolve
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
  (phase checkpoints already squashed into single commit by story script)
  → git push -u origin story/1-1-slug
  → gh pr create --title "feat(epic-1): 1-1-slug"
  → gh pr merge --auto --squash
  → poll until merged (15 min timeout)
  → git checkout main && git pull
  → git branch -d story/1-1-slug
Next story starts from main
```

With `--no-merge`: skips all git operations between stories. Use this for manual git control or non-GitHub workflows.

### Commit Messages

Both scripts extract the conventional commit message that the tech writer (step 6.1) places in the story file's `## Auto-bmad Completion` section. The story script squashes all phase checkpoints into this single commit. Falls back to `feat(SHORT_ID): <description from slug>`.

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
  ✗ CI failed on PR for story 1-2-database-schemas (2 failed, 3 passed)
    PR: https://github.com/.../pull/42

    Fix CI, merge the PR manually, then resume:
    ./auto-bmad-epic.sh --epic 1 --from-story 1-3-ci-pipeline
```

### Retrospective Summary

After the last story completes (which triggers the retrospective via Phase 5), the epic script parses the retrospective file and prints:
- Action items with owners and deadlines
- Critical path blockers
- Significant discovery alerts (if the retrospective flagged issues that may invalidate the next epic)

This is informational — no blocking gate. Review before starting the next epic.

### Artifacts

Epic-level artifacts go to `_bmad-output/implementation-artifacts/auto-bmad/epic-{N}/`:
- `epic-{N}-metrics.md` — per-story timing table and totals
- `epic-pipeline.log` — full log (deleted on success)

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

Both scripts keep all configuration in clearly marked blocks at the top — fork and edit to fit your setup.

### AI Profiles

Edit the `AI_*` variables at the top of `auto-bmad-story.sh`. Format: `"cli|model|effort"`.

```bash
# Example: swap MiMo for a different OpenCode model
AI_MIMO="opencode|opencode/some-other-model|max"
```

### Step Assignment

Edit `step_config()` in `auto-bmad-story.sh` to reassign steps to different AI profiles. Step IDs use a consistent scheme:

- **Numeric** (N.M) — sequential steps, run one at a time
- **Letter suffix** (N.Ma, N.Mb, ...) — parallel slots within a phase. Phases 1 and 3: a,b=GPT, c,d=MiMo, e,f=Claude.
- **Sequential after parallel** (N.M+1) — synthesis step that runs after parallel slots complete (triage, fix)

### Git / CI Configuration

Edit these variables at the top of `auto-bmad-epic.sh`:

| Variable | Default | Description |
|----------|---------|-------------|
| `PR_SAFETY_TIMEOUT` | `7200` (2 hours) | Backstop for stuck CI runners — not the normal control flow |
| `PR_POLL_INTERVAL` | `30` | Seconds between CI status checks |

Use `--no-merge` to skip all git operations between stories for non-GitHub or manual workflows.

## Troubleshooting

### AI CLI not found

The scripts check for `claude`, `codex`, and `opencode` in PATH at startup. Verify each is installed:

```bash
for cli in claude codex opencode; do command -v "$cli" >/dev/null && echo "$cli ✓" || echo "$cli ✗"; done
```

### BMAD version mismatch

The story script validates against BMad / TEA versions. A mismatch produces a warning but does not block execution. Update the `BMAD_BUILD_VERSION` and `BMAD_BUILD_TEA_VERSION` variables if you are running a different BMad version.

### Story pipeline fails mid-step

Use `--from-step` to resume from the failed step:

```bash
./auto-bmad-story.sh --story 1-2-database-schemas --from-step 3.1
```

### CI failure or stuck checks

If CI fails, the epic script stops immediately with a link to the PR. If CI appears stuck (runners hung, orphaned checks), the 2-hour safety timeout will eventually fire. Fix CI manually, merge the PR, then resume:

```bash
./auto-bmad-epic.sh --epic 1 --from-story 1-3-ci-pipeline
```

### sprint-status.yaml not found

Both scripts expect this file at `_bmad-output/implementation-artifacts/sprint-status.yaml`. Generate it through the BMad framework before running auto-bmad.

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

# Resume a failed story from code review
./auto-bmad-story.sh --story 1-2-database-schemas --from-step 3.1

# Preview a single story's pipeline
./auto-bmad-story.sh --story 1-2-database-schemas --dry-run

# Quick run — single GPT reviewer, triage+fix skipped
./auto-bmad-story.sh --fast-reviews

# Minimal pipeline — create, implement, close (no reviews or TEA)
./auto-bmad-story.sh --skip-reviews --skip-tea

# Run clean — no pipeline artifacts left behind
./auto-bmad-story.sh --no-traces

# Epic with fast reviews for all stories
./auto-bmad-epic.sh --epic 1 --fast-reviews

# Safe mode — AI tools prompt for permissions instead of auto-approving
./auto-bmad-story.sh --safe-mode

# Cautious first run — safe mode + no git writes
./auto-bmad-story.sh --safe-mode --skip-git
```

## Lineage

This project evolved from the original **auto-bmad** Claude Code plugin that lived in this same repository. The plugin approach was replaced with the current standalone shell scripts to support multi-CLI orchestration and epic-level automation.

An improved fork of the original plugin is maintained at [bramvera/auto-bmad](https://github.com/bramvera/auto-bmad).

## License

[MIT](LICENSE.md) — Copyright (c) 2026 Stefano Ginella
