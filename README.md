# auto-bmad - Automate your BMAD pipelines with multiple AIs

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE.md)
[![Bash: 3.2+](https://img.shields.io/badge/Bash-3.2%2B-green.svg)]()
[![Platform: macOS | Linux | WSL](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux%20%7C%20WSL-lightgrey.svg)]()
[![BMad: 6.2.2](https://img.shields.io/badge/BMad-6.2.2-purple.svg)](https://github.com/bmad-code-org/BMAD-METHOD)
[![TEA: 1.7.2](https://img.shields.io/badge/TEA-1.7.2-teal.svg)](https://github.com/bmad-code-org/bmad-method-test-architecture-enterprise)

Fully automated and very opinionated BMAD pipeline orchestration using multiple AI CLIs in parallel. Runs stories through 14+ steps across 7 phases with structured triage reviews — designed for unattended, sandboxed execution.

> **Note:** This is a personal tool, built to fit a specific workflow. It is highly opinionated, under constant development, and may be unstable. Use at your own risk.

- **4 AI providers** (Claude, GPT/Codex, OpenCode/MiMo, Copilot) running review steps in parallel
- **14+ pipeline steps** across 7 phases per story — from story creation to documentation
- **3-way spec validation + 6-way code reviews** with structured triage and automated resolution
- **Full epic orchestration** with automatic PR, CI gating, and squash-merge between stories

> **Warning:** By default, these scripts execute AI agents with full filesystem access (`--dangerously-skip-permissions`, `--full-auto`, `--yolo`). Run only in isolated environments (VM, container, etc).

## Table of Contents

- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Shell Completion](#shell-completion)
- [Story Pipeline](#story-pipeline-auto-bmad-storysh)
- [Epic Pipeline](#epic-pipeline-auto-bmad-epicsh)
- [Sprint Status Format](#sprint-status-format)
- [Diagnostic Commands](#diagnostic-commands)
- [Customization](#customization)
  - [Configuration Cascade](#configuration-cascade)
- [Troubleshooting](#troubleshooting)
- [Examples](#examples)
- [Lineage](#lineage)
- [License](#license)

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/user/auto-bmad.git
cd auto-bmad
make install                    # symlinks to /usr/local/bin, installs shell completions
# — or for user-local install —
PREFIX=~/.local make install

# 2. Run from any BMAD project directory
cd /path/to/your/project
auto-bmad story                 # run next story
auto-bmad epic                  # run full epic
```

No files need to be copied into your project. The scripts resolve their own install directory (even through symlinks) and load `lib/`, `conf/`, and `prompts/` from there. Project-specific overrides can be placed in `conf/` within the project root — see [Configuration Cascade](#configuration-cascade).

The story script auto-detects the next story from `sprint-status.yaml`. The epic script loops through all stories in an epic, handling PR + CI + merge between them. See [How It Works](#how-it-works) for the full picture.

## How It Works

This project is opinionated — it assumes a specific git workflow (branch-per-story, squash-merge PRs, CI gates) and uses multiple AI CLIs simultaneously. The pipeline is modular: two entry-point scripts source shared libraries from `lib/`, read AI profile assignments from `conf/profiles.conf`, and load prompt templates from `prompts/`. All internal assets are resolved from the install directory (via symlink), so scripts can run from any project directory without copying files.

A unified `auto-bmad` CLI dispatches to pipeline scripts and diagnostic commands:

| Command | Scope | What it does |
|---------|-------|-------------|
| `auto-bmad story` | One story | Runs a single story through the full BMAD pipeline (14+ steps, 7 phases) |
| `auto-bmad epic` | One epic | Loops through all stories, with PR + CI between them |
| `auto-bmad status` | Diagnostic | Shows current story, branch, epic progress at a glance |
| `auto-bmad quickstart` | Setup | First-run wizard — checks tools, profiles, and project readiness |
| `auto-bmad validate` | Diagnostic | Validates sprint-status.yaml structure and content |
| `auto-bmad config` | Diagnostic | Shows resolved configuration cascade, pipeline.conf, profiles, and tools |

### Architecture

```
auto-bmad <command>  →  dispatches to underlying scripts
  │
auto-bmad-epic
  │
  ├── Story 1 ──→ auto-bmad-story
  │     ├─ Phase 0: Epic start (TEA test design)
  │     ├─ Phase 1: Story prep
  │     │     ├── 3 parallel spec validations (GPT, MiMo, Claude)
  │     │     ├── Spec Triage (Opus) — normalize, dedup, classify
  │     │     └── Resolve findings (Opus/analyst) — patch + bad_spec + intent_gap
  │     ├─ Phase 2: TDD + implementation
  │     ├─ Phase 3: Code review
  │     │     ├── 6 parallel code reviews (3 AIs × edge-cases + adversarial)
  │     │     ├── Acceptance Auditor (Opus)
  │     │     ├── Triage (Opus) — normalize, dedup, classify
  │     │     ├── Dev fix (Opus) — patch items only
  │     │     ├── KEEP re-audit (Opus) — verify passing criteria still hold
  │     │     └── Resolve spec findings (Opus/analyst) — bad_spec + intent_gap
  │     ├─ Phase 4: Traceability
  │     ├─ Phase 5: Epic end (retro, NFR, exit report, context)
  │     └─ Phase 6: Finalization (docs + close)
  │
  ├── git: commit → push → PR → squash-merge → CI ✓
  │
  ├── Story 2 ──→ auto-bmad-story ...
  │
  └── Story N ──→ ...
```

### Multi-AI Review Pattern

Both spec reviews (Phase 1) and code reviews (Phase 3) use structured triage:

1. **Parallel reviews** — Phase 1: 3 validation reviews (GPT, MiMo, Claude). Phase 3: 6 code reviews (3 AIs × edge-cases + adversarial)
2. **Triage** (Opus) — normalizes, deduplicates, and classifies findings into:

| Category | Meaning | Action |
|----------|---------|--------|
| **patch** | Issue fixable without human input | Fixed automatically |
| **intent_gap** | Spec/intent is incomplete | Auto-resolved from upstream artifacts, or flagged as unresolvable |
| **bad_spec** | Upstream spec is wrong or ambiguous | Auto-resolved by amending story from upstream context |
| **defer** | Pre-existing issue, not caused by this change | Noted for future attention |
| **reject** | Noise, false positive, or handled elsewhere | Dropped |

3. **Resolve** / **Fix** — the analyst resolves `patch`, `bad_spec`, and `intent_gap` findings automatically using upstream artifacts (epic, architecture, PRD). Any `intent_gap` that cannot be filled from existing artifacts is marked **unresolvable** and surfaced in the pipeline summary. In Phase 3, the dev fixes `patch` items (code bugs) first, then the analyst resolves `bad_spec` and `intent_gap` (spec-level issues surfaced by code review).

Phase 3 adds an **Acceptance Auditor** (Opus) before triage that verifies every acceptance criterion against the implementation: PASS / PARTIAL / FAIL / UNTESTABLE.

Triage evaluates on **argument quality**, not reviewer count. A single reviewer demonstrating a concrete bug outweighs four reviewers raising vague concerns. The spec triage is additionally conservative — findings that add NEW requirements not present in the epic or architecture are classified as `intent_gap` or `reject`, not `patch`, preventing scope creep.

## Prerequisites

### Required

- **Bash** 3.2+
- **Git** repository with a `main` branch
- **BMad framework** installed (`_bmad/` directory) — tested against BMad 6.2.0 / TEA 1.7.2
- **Sprint status** generated at `_bmad-output/implementation-artifacts/sprint-status.yaml`

### AI CLIs (all four needed for full parallel reviews)

- [`claude`](https://docs.anthropic.com/en/docs/claude-code) — Claude Code CLI
- [`codex`](https://github.com/openai/codex) — OpenAI Codex CLI
- [`copilot`](https://docs.github.com/copilot/how-tos/copilot-cli) — GitHub Copilot CLI (fallback provider)
- [`opencode`](https://github.com/opencode-ai/opencode) — OpenCode CLI (MiMo)

### For auto-merge between stories

- [`gh`](https://cli.github.com/) — GitHub CLI, authenticated

### Optional

- [`jq`](https://jqlang.github.io/jq/) — enables JSON usage tracking and cost reporting per step/story/epic

> **Note:** Each story runs 14+ AI invocations across 4 providers. This is extremely token-hungry — budget accordingly. When `jq` is installed, each step outputs JSON for automatic token and cost tracking (see [Artifacts](#artifacts)).

## Installation

### Via `make install` (recommended)

```bash
git clone https://github.com/user/auto-bmad.git
cd auto-bmad
make install                    # symlinks auto-bmad to /usr/local/bin, installs completions
```

For a user-local install (no sudo):

```bash
PREFIX=~/.local make install
```

This creates a symlink from `$(PREFIX)/bin/auto-bmad` back to the repo, so updates are immediately available. Shell completions are copied to the standard bash/zsh completion directories.

To remove:

```bash
make uninstall                  # or: PREFIX=~/.local make uninstall
```

To run the test suite:

```bash
make test                       # or: bash test/run_all.sh
```

### Manual install

Symlink the `auto-bmad` dispatcher somewhere in your PATH. The scripts resolve their own install directory through symlinks, so `lib/`, `conf/`, and `prompts/` are loaded from where the repo lives — nothing needs to be copied into your project.

```bash
ln -s "$(pwd)/auto-bmad" /usr/local/bin/auto-bmad
```

### Verify

```bash
auto-bmad help                  # if installed via make
auto-bmad quickstart            # check tool readiness
auto-bmad story --help
auto-bmad epic --help
```

## Shell Completion

Tab completion for subcommands and flags is installed automatically by `make install`. If your shell doesn't pick it up, source it manually:

```bash
# bash — add to ~/.bashrc
source /usr/local/share/bash-completion/completions/auto-bmad

# zsh — ensure the completion dir is in fpath, then:
autoload -Uz compinit && compinit
```

Completions cover:
- Subcommands: `auto-bmad <TAB>` → `story`, `epic`, `status`, `quickstart`, `validate`, `config`, ...
- Per-command flags: `auto-bmad story <TAB>` → `--story`, `--from-step`, `--dry-run`, ...
- Flag values: `auto-bmad story --reviews <TAB>` → `full`, `fast`, `none`
- Step IDs: `auto-bmad story --from-step <TAB>` → `0.1`, `1.1`, `1.2`, ...

## Story Pipeline (`auto-bmad-story`)

Automates one story through the full BMAD implementation workflow.

### Usage

```bash
auto-bmad story [options]       # via wrapper
./auto-bmad-story [options]  # direct

Options:
  --story STORY_ID       Override auto-detection (e.g., 1-2-database-schemas)
  --from-step STEP_ID    Resume from a specific step (e.g., 3.1, 6.1)
  --dry-run              Preview all steps without executing
  --skip-cache           Bypass pre-flight cache and force full checks
  --skip-tea             Skip TEA phases even if installed (0, 2.1, 4.x, 5.1-5.3)
  --reviews MODE         Review mode: full (default), fast (1 GPT only), none
  --skip-git             Skip git write ops (branch, checkpoint, squash)
  --no-traces            Remove pipeline artifacts after finalization
                         (pipeline report is kept)
  --debug                Keep temp files for debugging
  --help                 Show usage
```

### Pipeline Phases

| Phase | Steps | Name | What happens |
|-------|-------|------|-------------|
| 0 | 0.1 | Epic Start | TEA Test Design at epic level. *Only runs on the first story in an epic.* |
| 1 | 1.1, 1.2a-c, 1.3, 1.4 | Story Preparation | Create story, 3 parallel spec validations (GPT, MiMo, Claude), triage, resolve findings |
| 2 | 2.1, 2.2 | TDD + Implementation | Generate failing acceptance tests (red phase), then implement (green phase) |
| 3 | 3.1a-f, 3.2, 3.3, 3.4, 3.4b, 3.5 | Code Review | 6 parallel code reviews (3 AIs × 2 types), acceptance audit, triage, dev fix, KEEP re-audit, resolve spec findings |
| 4 | 4.1, 4.2 | Traceability | Testarch trace + test automation expansion |
| 5 | 5.1-5.3, 5.4, 5.5, 5.6 | Epic End | Epic trace/NFR/test review, retrospective, epic exit report, project context. *Only runs on the last story in an epic.* |
| 6 | 6.1, 6.2 | Finalization | Tech writer documents story, scrum master closes it |

### AI Profiles

Six named profiles are defined in `conf/profiles.conf` and referenced by steps via `@name`. Each profile specifies a CLI, model, effort level, and a fallback profile for automatic recovery:

| Profile | CLI / Model | Effort | Fallback | Used for |
|---------|-------------|--------|----------|----------|
| `@claude-opus-max` | Claude Opus | max | `@copilot-opus-max` | Critical path: triage, fix, implementation |
| `@claude-opus-high` | Claude Opus | high | `@copilot-opus-high` | Structured: spec reviews, retro, docs |
| `@claude-sonnet-high` | Claude Sonnet | high | `@copilot-sonnet-high` | Lightweight: traceability, closing |
| `@codex-gpt54-high` | Codex GPT 5.4 | high | `@copilot-gpt54-high` | Spec-level reviews |
| `@codex-gpt54-xhigh` | Codex GPT 5.4 | xhigh | `@copilot-gpt54-xhigh` | Code reviews, edge cases |
| `@opencode-mimo-max` | OpenCode MiMo V2 Pro | max | `@copilot-opus-max` | Parallel reviews |
| `@copilot-*` | Copilot (various models) | varies | cross-provider | Fallback provider for all primary profiles |

### Retry & Fallback

Steps that fail silently (completing in under 5 seconds with minimal output) or return a non-zero exit code are automatically retried:

1. **Retry** — same profile, one attempt
2. **Fallback** — switch to the fallback profile, one attempt
3. **Fail** — if both exhaust, sequential steps stop the pipeline (with `--from-step` resume), parallel reviews degrade gracefully

Fallback chains cross providers (codex/opencode fall back to claude) but do not recurse — a fallback's own fallback is never consulted. Retried and fell-back steps are annotated in the pipeline report and terminal summary.

**Runtime guards** also protect against runaway steps. A step is terminated if it exceeds the duration cap (`max_step_duration`), floods output (`max_output_rate`), or enters an edit loop (`file_churn_threshold`). Guard-terminated steps follow the same retry → fallback → fail path. See [Pipeline Configuration](#pipeline-configuration) for thresholds.

### Story Detection

Auto-detects the next story from `sprint-status.yaml`:
1. Prioritizes stories with status `in-progress` (resume interrupted work)
2. Falls back to the first story with status `backlog`
3. Epic boundary detection is automatic based on story position

### Git Workflow

The story script creates a `story/{STORY_ID}` branch from `main` at the start. During execution, each phase commits a checkpoint (`wip(1-1): phase N - name`) so work is recoverable if the pipeline fails mid-run. At the end, all checkpoint commits are squashed into a single commit using the conventional-commit message from the story file's Auto-bmad Completion section.

### Artifacts

Per-story artifacts are saved to `_bmad-output/implementation-artifacts/auto-bmad/{SHORT_ID}/`:
- Spec triage (`*-1.3-spec-triage.md`) — classified spec findings with resolution status
- Code acceptance audit (`*-3.2-code-acceptance.md`) — AC compliance matrix (PASS / PARTIAL / FAIL per criterion)
- Code triage (`*-3.3-code-triage.md`) — classified code findings with reviewer signal assessment and overlap matrix
- Pipeline report (`*-6.1-pipeline-report.md`) — timestamps, CLI/model per step, wall/compute time, git diff stats
- Usage report (`usage-report.md`) — per-step token counts, cost (reported/inferred), premium requests, with totals by CLI and model. Requires `jq`.

### Review Modes

Phase 1 runs 3 parallel spec validations; Phase 3 runs 6 parallel code reviews (3 AIs × 2 types). Both use structured triage with automated resolution. The `--reviews` flag controls this:

| Mode | Behavior |
|------|----------|
| `--reviews full` (default) | 3 spec validators + 6 code reviewers, full triage + automated fix |
| `--reviews fast` | 1 GPT reviewer per phase, triage + fix skipped. Good for iteration. |
| `--reviews none` | Skip all review phases. Pipeline: create → implement → document → close. |

### No Traces Mode (`--no-traces`)

Removes all pipeline-generated artifacts after finalization — review reports, triage reports, the entire `auto-bmad/{SHORT_ID}/` directory. The pipeline report is preserved at `auto-bmad/pipeline-report--{SHORT_ID}.md`.

This is useful when the review reports have already been indexed into the story file and you don't want leftover pipeline files in the repo.

### Resume on Failure

Each phase is checkpointed as a git commit, so if the pipeline fails you won't lose prior phases. The script exits with a resume command:

```
Resume: auto-bmad story --from-step 3.1 --story 1-2-database-schemas
```

See [Troubleshooting](#troubleshooting) for common failure scenarios.

## Epic Pipeline (`auto-bmad-epic`)

Thin orchestration wrapper that runs all stories in an epic sequentially.

### Usage

```bash
auto-bmad epic [options]       # via wrapper
./auto-bmad-epic [options]  # direct

Options:
  --epic EPIC_ID         Target epic number (e.g., 1). Auto-detects if omitted.
  --from-story ID        Resume from a specific story (e.g., 1-3-some-slug)
  --to-story ID          Stop after this story (e.g., 1-5-deploy)
  --dry-run              Preview the full epic plan without executing
  --no-merge             Skip auto-PR/merge between stories (manual git)
  --help                 Show usage

Story pass-through flags (forwarded to auto-bmad-story):
  --skip-cache           Bypass story-script pre-flight cache
  --skip-tea             Skip TEA phases even if installed
  --reviews MODE         Review mode: full (default), fast (1 GPT only), none
  --skip-git             Skip git write ops (branch, checkpoint, squash)
  --no-traces            Remove pipeline artifacts after finalization
  --debug                Keep temp files for debugging
```

### What It Does

1. **Parses `sprint-status.yaml`** to collect all stories for the target epic
2. **Loops sequentially** — calls `auto-bmad-story --story STORY_ID` for each
3. **PR + auto-merge between stories** — after each story completes:
   - Commits changes on the story branch
   - Pushes and creates a PR via `gh`
   - Enables auto-merge (squash)
   - Polls CI check states every 30s until all checks resolve
   - Syncs `sprint-status.yaml` — marks story `done`, marks epic `done` when all stories complete
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
  → update sprint-status.yaml (story → done, epic → done if all complete)
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

  Resume (story):  auto-bmad story --story 1-3-ci-pipeline --from-step <step>
  Resume (epic):   auto-bmad epic --epic 1 --from-story 1-3-ci-pipeline
```

**CI failure on PR:**
```
  ✗ CI failed on PR for story 1-2-database-schemas (2 failed, 3 passed)
    PR: https://github.com/.../pull/42

    Fix CI, merge the PR manually, then resume:
    auto-bmad epic --epic 1 --from-story 1-3-ci-pipeline
```

A GitHub Issue is automatically created (labeled `ci-failure` or `ci-timeout`) so the failure is trackable and assignable. This is fire-and-forget — if `gh` auth is unavailable, the pipeline continues as normal.

### Retrospective Summary

After the last story completes (which triggers the retrospective via Phase 5), the epic script parses the retrospective file and prints:
- Action items with owners and deadlines
- Critical path blockers
- Significant discovery alerts (if the retrospective flagged issues that may invalidate the next epic)

This is informational — no blocking gate. Review before starting the next epic.

### Artifacts

Epic-level artifacts go to `_bmad-output/implementation-artifacts/auto-bmad/epic-{N}/`:
- `epic-{N}-metrics.md` — per-story timing table and totals
- `epic-usage-report.md` — aggregated token/cost data across all stories, with breakdowns by CLI and model. Requires `jq`.
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

## Diagnostic Commands

Four commands help with setup, debugging, and pipeline monitoring — none modify files or run pipelines.

### `auto-bmad status`

One-screen overview of current pipeline state: active story, branch, epic progress, previous story merge status, and unresolved deferred items.

```bash
auto-bmad status
```

### `auto-bmad quickstart`

Interactive first-run setup wizard. Checks all AI CLIs, git version, GitHub auth, jq availability, BMAD project structure, and profile configuration. Offers to run a dry-run if everything looks good.

```bash
auto-bmad quickstart
```

### `auto-bmad validate`

Validates `sprint-status.yaml` for structural issues: invalid statuses, duplicate IDs, undeclared epics, malformed entries.

```bash
auto-bmad validate                     # default location
auto-bmad validate /path/to/file.yaml  # custom path
```

### `auto-bmad config`

Dumps all resolved configuration: cascade paths, pipeline.conf values (with override sources), profile definitions, tool paths.

```bash
auto-bmad config
```

## Customization

Configuration lives in dedicated files — no need to edit the shell scripts themselves.

### AI Profiles & Step Assignment

Edit `conf/profiles.conf` to change which AI model runs each step. The file has two sections:

**Profile definitions** — named `@profiles` with CLI, model, effort, and fallback:

```
# @name                   cli       model    effort   fallback
@claude-opus-max          claude    opus     max      @claude-sonnet-high
@codex-gpt54-high         codex     gpt-5.4  high     @claude-opus-high
```

**Step mappings** — assign a `@profile` to each step ID:

```
1.1     @claude-opus-max
1.2a    @codex-gpt54-high
```

To change a model globally, edit the profile definition. To change a single step's assignment, point it at a different profile. The legacy format (`step_id cli model effort`) is still supported for backward compatibility.

Step IDs use a consistent scheme:

- **Numeric** (N.M) — sequential steps, run one at a time
- **Letter suffix** (N.Ma, N.Mb, ...) — parallel slots within a phase. Phase 1: a=GPT, b=MiMo, c=Claude. Phase 3: a,b=GPT, c,d=MiMo, e,f=Claude.
- **Sequential after parallel** (N.M+1) — synthesis step that runs after parallel slots complete (triage, fix)

### Prompt Templates

All step prompts live in `prompts/*.md` as plain text with `{{PLACEHOLDER}}` variables. Edit these to change what instructions the AI receives for each step — no shell code to touch.

### Configuration Cascade

All three `conf/` files (`pipeline.conf`, `profiles.conf`, `pricing.conf`) support a 3-tier override cascade. Later tiers override values from earlier tiers:

| Tier | Location | Purpose |
|------|----------|---------|
| 1. Install defaults | `INSTALL_DIR/conf/` | Shipped with auto-bmad |
| 2. User overrides | `~/.config/auto-bmad/` | Per-user preferences (respects `$XDG_CONFIG_HOME`) |
| 3. Project overrides | `PROJECT_ROOT/conf/` | Per-project tuning (check into repo or gitignore) |

For example, to use a different Copilot plan for a specific project:

```bash
# In your project root
mkdir -p conf
cat > conf/pricing.conf << 'EOF'
[copilot]
plan = pro_plus
EOF
```

Or to override a profile for all your projects:

```bash
mkdir -p ~/.config/auto-bmad
cat > ~/.config/auto-bmad/profiles.conf << 'EOF'
# Override @claude-opus-max to use sonnet instead
@claude-opus-max  claude  sonnet  max  @copilot-sonnet-high
EOF
```

Run `auto-bmad config` to see the resolved cascade and final values.

### Pipeline Configuration

Edit `conf/pipeline.conf` to tune operator-facing defaults. Override via the cascade above, or via environment variables (`AUTO_BMAD_<SECTION>_<KEY>`):

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| `[timeouts]` | `pr_safety` | `7200` (2h) | Backstop for stuck CI runners |
| `[timeouts]` | `pr_poll_interval` | `30` | Seconds between CI status checks |
| `[timeouts]` | `pr_grace_polls` | `10` | Polls to wait for CI checks to appear |
| `[thresholds]` | `min_step_duration` | `5` | Soft-fail: steps faster than this are suspect |
| `[thresholds]` | `min_log_bytes` | `200` | Soft-fail: steps with less output are suspect |
| `[thresholds]` | `min_reviewers` | `2` | Minimum successful parallel reviews before triage proceeds |
| `[guard]` | `max_step_duration` | `2400` (40m) | Per-step duration cap before termination (0 = disabled) |
| `[guard]` | `max_output_rate` | `300000` | Max log output bytes per 10s window before flagging runaway |
| `[guard]` | `file_churn_threshold` | `20` | Diff changes this many times = runaway (0 = disabled) |
| `[cache]` | `preflight_max_age` | `86400` | Seconds before pre-flight results are re-checked |
| `[monitor]` | `parallel_stagger` | `2` | Seconds between parallel review launches (reduces contention) |
| `[git]` | `branch_pattern` | `story/${STORY_ID}` | Branch naming template |
| `[git]` | `default_review_mode` | `full` | Default when `--reviews` not specified |

Environment variables take highest precedence, above all cascade tiers.

## Troubleshooting

### AI CLI not found

The scripts check for `claude`, `codex`, `copilot`, and `opencode` in PATH at startup. Verify each is installed:

```bash
for cli in claude codex copilot opencode; do command -v "$cli" >/dev/null && echo "$cli ✓" || echo "$cli ✗"; done
```

### BMAD version mismatch

The story script validates against BMad / TEA versions. A mismatch produces a warning but does not block execution. Update the `BMAD_BUILD_VERSION` and `BMAD_BUILD_TEA_VERSION` variables in `lib/config.sh` if you are running a different BMad version.

### Story pipeline fails mid-step

Use `--from-step` to resume from the failed step:

```bash
auto-bmad story --story 1-2-database-schemas --from-step 3.1
```

### CI failure or stuck checks

If CI fails, the epic script stops immediately with a link to the PR and creates a GitHub Issue labeled `ci-failure` for tracking. If CI appears stuck (runners hung, orphaned checks), the 2-hour safety timeout will eventually fire and create a `ci-timeout` issue. Fix CI manually, merge the PR, then resume:

```bash
auto-bmad epic --epic 1 --from-story 1-3-ci-pipeline
```

### sprint-status.yaml not found

Both scripts expect this file at `_bmad-output/implementation-artifacts/sprint-status.yaml`. Generate it through the BMad framework before running auto-bmad.

## Examples

```bash
# Check readiness before first run
auto-bmad quickstart

# Show current pipeline state
auto-bmad status

# Validate sprint-status.yaml
auto-bmad validate

# Show resolved configuration
auto-bmad config

# Preview what the next epic would do
auto-bmad epic --dry-run

# Run epic 1 end-to-end
auto-bmad epic --epic 1

# Run a range of stories within an epic
auto-bmad epic --epic 1 --from-story 1-3-ci --to-story 1-5-deploy

# Resume epic after a story failure
auto-bmad epic --epic 1 --from-story 1-3-ci-pipeline

# Run without auto-PR (manual git between stories)
auto-bmad epic --epic 1 --no-merge

# Run a single story manually
auto-bmad story --story 1-2-database-schemas

# Resume a failed story from code review
auto-bmad story --story 1-2-database-schemas --from-step 3.1

# Preview a single story's pipeline
auto-bmad story --story 1-2-database-schemas --dry-run

# Quick run — single GPT reviewer, triage+fix skipped
auto-bmad story --reviews fast

# Minimal pipeline — create, implement, close (no reviews or TEA)
auto-bmad story --reviews none --skip-tea

# Run clean — no pipeline artifacts left behind
auto-bmad story --no-traces

# Epic with fast reviews for all stories
auto-bmad epic --epic 1 --reviews fast
```

## Lineage

This project evolved from the original **auto-bmad** Claude Code plugin that lived in this same repository. The plugin approach was replaced with the current standalone shell scripts to support multi-CLI orchestration and epic-level automation.

An improved fork of the original plugin is maintained at [bramvera/auto-bmad](https://github.com/bramvera/auto-bmad).

## License

[MIT](LICENSE.md) — Copyright (c) 2026 Stefano Ginella
