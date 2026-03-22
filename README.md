# auto-bmad

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE.md)
[![Language: Bash](https://img.shields.io/badge/Language-Bash-green.svg)]()
[![AI CLIs: 4](https://img.shields.io/badge/AI_CLIs-4-orange.svg)]()
[![BMad: 6.2.0](https://img.shields.io/badge/BMad-6.2.0-purple.svg)](https://github.com/bmad-code-org/BMAD-METHOD)
[![TEA: 1.7.1](https://img.shields.io/badge/TEA-1.7.1-red.svg)](https://github.com/bmad-code-org/bmad-method-test-architecture-enterprise)

Fully automated BMAD pipeline orchestration using multiple AI CLIs in parallel. Runs stories through 14+ steps across 7 phases with multi-AI consensus reviews — designed for unattended, sandboxed execution.

- **4 AI providers** (Claude, GPT, Gemini, OpenCode) running review steps in parallel
- **14+ pipeline steps** across 7 phases per story — from story creation to documentation
- **Consensus-based multi-AI reviews** with configurable arbiter (4-way fan-out + merge)
- **Full epic orchestration** with automatic PR, CI gating, and squash-merge between stories

> **Warning:** These scripts execute AI agents with full filesystem access (`--dangerously-skip-permissions`, `--full-auto`, `--yolo`). Run only in isolated environments (VM, container, etc).

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
| `auto-bmad-story.sh` | One story | Runs a single story through the full BMAD pipeline (14+ steps, 7 phases) using multiple AI CLIs |
| `auto-bmad-epic.sh` | One epic | Loops through all stories in an epic, delegating each to the story script, with PR + CI between stories |

### Architecture

```
auto-bmad-epic.sh
  │
  ├── Story 1 ──→ auto-bmad-story.sh
  │     ├─ Phase 0: Epic start (TEA test design)
  │     ├─ Phase 1: Story prep
  │     │     ├── 4 AIs review in parallel ──→ Arbiter (Opus)
  │     │     └── 4 AIs adversarial review ──→ Arbiter (Opus)
  │     ├─ Phase 2: TDD + implementation
  │     ├─ Phase 3: Edge cases (4 AIs ──→ Arbiter)
  │     ├─ Phase 4: Code review (4 AIs ──→ Arbiter)
  │     ├─ Phase 5: Traceability
  │     ├─ Phase 6: Epic end (retro, NFR, context)
  │     └─ Phase 7: Finalization (docs + close)
  │
  ├── git: commit → push → PR → squash-merge → CI ✓
  │
  ├── Story 2 ──→ auto-bmad-story.sh ...
  │
  └── Story N ──→ ...
```

### Multi-AI Review Pattern

Reviews (validation, adversarial, edge cases, code review) use a **4-way parallel review + arbiter** pattern:

1. Four AI CLIs review independently in parallel (GPT, Gemini, MiniMax, MiMo)
2. Each produces a findings report saved to the story artifacts directory
3. An arbiter (Claude Opus) cross-references all findings using consensus rules:

| Agreement | Action |
|-----------|--------|
| **4/4 agree** | Fix immediately — high confidence |
| **3/4 agree** | Fix — good confidence |
| **2/4 agree** | Evaluate both sides, fix if substantive |
| **1/4 flags** | Only fix if clearly a real issue with concrete impact |

## Prerequisites

### Required

- **Bash** 3.2+
- **Git** repository with a `main` branch
- **BMad framework** installed (`_bmad/` directory) — tested against BMad 6.2.0 / TEA 1.7.0
- **Sprint status** generated at `_bmad-output/implementation-artifacts/sprint-status.yaml`

### AI CLIs (all four needed for full parallel reviews)

- [`claude`](https://docs.anthropic.com/en/docs/claude-code) — Claude Code CLI
- [`codex`](https://github.com/openai/codex) — OpenAI Codex CLI
- [`gemini`](https://github.com/google-gemini/gemini-cli) — Google Gemini CLI
- [`opencode`](https://github.com/opencode-ai/opencode) — OpenCode CLI (MiniMax, MiMo)

### For auto-merge between stories

- [`gh`](https://cli.github.com/) — GitHub CLI, authenticated

> **Note:** Each story runs 14+ AI invocations across 4 providers. This is extremely token-hungry — budget accordingly.

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
  --from-step STEP_ID    Resume from a specific step (e.g., 6a, 8)
  --dry-run              Preview all steps without executing
  --skip-epic-phases     Skip phases 0 and 6 even at epic boundaries
  --json-log             Extract arbiter findings into review-log.json (JSONL)
  --no-traces            Remove all pipeline artifacts after finalization
                         (implies --json-log; JSON + pipeline logs are kept)
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

### Story Detection

Auto-detects the next story from `sprint-status.yaml`:
1. Prioritizes stories with status `in-progress` (resume interrupted work)
2. Falls back to the first story with status `backlog`
3. Epic boundary detection is automatic based on story position

### Git Workflow

The story script creates a `story/{STORY_ID}` branch from `main` at the start. During execution, each phase commits a checkpoint (`wip(1-1): phase N - name`) so work is recoverable if the pipeline fails mid-run. At the end, all checkpoint commits are squashed into a single commit using the conventional-commit message from the story file's Auto-bmad Completion section.

### Artifacts

Per-story artifacts are saved to `_bmad-output/implementation-artifacts/auto-bmad/{SHORT_ID}/`:
- Review findings from each AI (`*-validate-*.md`, `*-adversarial-*.md`, `*-edge-cases-*.md`, `*-review-*.md`)
- Arbiter decision reports (`*-arbiter-*.md`)
- Pipeline log (`pipeline.log`) — append-only run record with timestamps, CLI/model per step, phase markers, and a completion summary with wall/compute time and git diff stats

### Review JSON Log (`--json-log`)

Extracts structured data from arbiter decision tables into a JSONL file (`review-log.json`). Each line is a JSON object for one arbiter step:

```json
{"story":"1-1-auth","step":"2e","review_type":"validate","timestamp":"...","total":5,"fixed":3,"skipped":2,"verdict":"changes_made","findings":[...]}
```

Use this to evaluate review effectiveness across stories — track catch rates, fix/skip ratios, and consensus patterns. Requires `jq` for full output; falls back to raw JSONL without aggregation if `jq` is not installed.

### No Traces Mode (`--no-traces`)

Removes all pipeline-generated artifacts after finalization — review reports, arbiter reports, the entire `auto-bmad/{SHORT_ID}/` directory. Two files are preserved:
- `auto-bmad/review-log--{SHORT_ID}.json` — structured arbiter findings
- `auto-bmad/pipeline--{SHORT_ID}.log` — full pipeline run record

This is useful when the review reports have already been indexed into the story file (step 14a) and you don't want leftover pipeline files in the repo. Implies `--json-log`.

### Resume on Failure

Each phase is checkpointed as a git commit, so if the pipeline fails you won't lose prior phases. The script exits with a resume command:

```
Resume: ./auto-bmad-story.sh --from-step 6a --story 1-2-database-schemas
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

Both scripts extract the conventional commit message that the tech writer (step 14a) places in the story file's `## Auto-bmad Completion` section. The story script squashes all phase checkpoints into this single commit. Falls back to `feat(SHORT_ID): <description from slug>`.

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

Edit the six `AI_*` variables at the top of `auto-bmad-story.sh`. Format: `"cli|model|effort"`.

```bash
# Example: swap Gemini for a different model
AI_GEMINI="gemini|gemini-2.5-pro|"
```

### Step Assignment

Edit `step_config()` in `auto-bmad-story.sh` to reassign steps to different AI profiles. Step IDs use a consistent scheme:

- **Numeric** (0, 1, 4, 5, ...) — sequential steps, run one at a time
- **Letter suffix** (2a, 2b, 2c, 2d) — parallel slots within a phase (a=GPT, b=Gemini, c=MiniMax, d=MiMo)
- **`e` suffix** (2e, 3e, 6e) or step 8 — arbiter that runs after parallel slots complete

### Git / CI Configuration

Edit these variables at the top of `auto-bmad-epic.sh`:

| Variable | Default | Description |
|----------|---------|-------------|
| `PR_MERGE_TIMEOUT` | `900` (15 min) | Max seconds to wait for CI to pass on a PR |
| `PR_POLL_INTERVAL` | `30` | Seconds between CI status checks |

Use `--no-merge` to skip all git operations between stories for non-GitHub or manual workflows.

## Troubleshooting

### AI CLI not found

The scripts check for `claude`, `codex`, `gemini`, and `opencode` in PATH at startup. Verify each is installed:

```bash
for cli in claude codex gemini opencode; do command -v "$cli" >/dev/null && echo "$cli ✓" || echo "$cli ✗"; done
```

### BMAD version mismatch

The story script validates against BMad 6.2.0 / TEA 1.7.0. A mismatch produces a warning but does not block execution. Update the `BMAD_BUILD_VERSION` and `BMAD_BUILD_TEA_VERSION` variables if you are running a different BMad version.

### Story pipeline fails mid-step

Use `--from-step` to resume from the failed step:

```bash
./auto-bmad-story.sh --story 1-2-database-schemas --from-step 6a
```

### CI timeout on PR merge

Increase `PR_MERGE_TIMEOUT` in `auto-bmad-epic.sh`, or fix CI manually, merge the PR, then resume the epic:

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

# Resume a failed story from a specific step
./auto-bmad-story.sh --story 1-2-database-schemas --from-step 6a

# Preview a single story's pipeline
./auto-bmad-story.sh --story 1-2-database-schemas --dry-run

# Run with JSON review logging for effectiveness analysis
./auto-bmad-story.sh --json-log

# Run clean — no pipeline artifacts left behind
./auto-bmad-story.sh --no-traces
```

## Lineage

This project evolved from the original **auto-bmad** Claude Code plugin that lived in this same repository. The plugin approach was replaced with the current standalone shell scripts to support multi-CLI orchestration and epic-level automation.

An improved fork of the original plugin is maintained at [bramvera/auto-bmad](https://github.com/bramvera/auto-bmad).

## License

[MIT](LICENSE.md) — Copyright (c) 2026 Stefano Ginella
