# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

auto-bmad is a fully automated BMAD pipeline orchestrator that runs stories through 14+ steps across 7 phases using multiple AI CLIs (Claude, Codex/GPT-5.4, OpenCode/MiMo, Copilot) in parallel. Pure Bash (3.2+ compatible), no external dependencies beyond git, gh, jq (optional), and the AI CLIs. When `jq` is available, all AI steps use JSON output mode for token usage tracking and cost reporting.

## Commands

```bash
# Install / uninstall
make install                       # symlink to /usr/local/bin + shell completions
PREFIX=~/.local make install       # user-local install
make uninstall

# Validate shell syntax (no test suite exists)
bash -n auto-bmad-story && bash -n auto-bmad-epic && bash -n lib/*.sh

# Run
auto-bmad story                    # run next story
auto-bmad story --dry-run          # preview pipeline
auto-bmad epic --epic 1            # run full epic
```

## Architecture

Three entry points dispatch to a modular library system:

```
auto-bmad              CLI dispatcher (exec → story or epic)
auto-bmad-story        Story pipeline: 7 phases, 14+ steps with checkpoint commits
auto-bmad-epic         Epic orchestrator: loops stories, handles PR/CI/merge between them
```

### Libraries (`lib/`)

Each exports focused functions. Source order differs per entry point:

- **auto-bmad-story** sources: core → tracking → config → git → monitor → cli → runner → usage → detection → steps
- **auto-bmad-epic** sources: core → tracking → config → pr → usage → detection

| Library | Purpose |
|---------|---------|
| `core.sh` | Terminal output, colors, logging, `_confirm()` prompts |
| `tracking.sh` | Bash 3.2-compatible key-value store (`kv_set`/`kv_get`) using dynamic variable names |
| `config.sh` | Path detection, version checks, AI profile lookup from `conf/profiles.conf` |
| `cli.sh` | AI CLI abstraction — single `run_ai()` dispatches to claude/codex/copilot/opencode (story only) |
| `runner.sh` | DAG executor with soft-fail detection, retry, and profile-based fallback chains (story only) |
| `git.sh` | Branch creation, checkpoints, squash, 7 pre-flight gates (story only) |
| `detection.sh` | Story/epic auto-detection from `sprint-status.yaml` |
| `pr.sh` | PR lifecycle: create, enable auto-merge, poll CI, cleanup (epic only) |
| `usage.sh` | Token usage extraction, cost inference from `conf/pricing.conf`, JSONL accumulation, story + epic usage report generation (requires `jq`, graceful degradation without it) |
| `monitor.sh` | Background activity spinner with stall detection (story only) |
| `steps.sh` | Step function implementations, step logging helpers (`log_step`, `log_dry`), pipeline report generation (story only) |

### Configuration (`conf/`)

**`profiles.conf`** — Two-section format: profile definitions (`@name cli model effort fallback`) and step-to-profile mappings (`step_id @profile`). To change AI assignment for a step, point it at a different profile. To change a model globally, edit the profile definition.

**`pricing.conf`** — Two sections: `[tokens]` has per-model token rates for codex cost inference; `[copilot]` has premium request billing config (plan, cost, allowance). Claude and OpenCode report cost natively; Codex costs are inferred from tokens; Copilot costs are computed from `premiumRequests` in JSON output multiplied by plan cost per request.

### Prompt Templates (`prompts/`)

23 markdown files with `{{PLACEHOLDER}}` variables, loaded via `load_prompt()` and substituted with bash parameter expansion. Edit these to change AI instructions without touching shell code.

## Key Patterns

**Parallel reviews with structured triage:** Phase 1 runs 3 spec validators in parallel (1.2a-c); Phase 3 runs 6 code reviewers in parallel (3.1a-f). Results feed into a triage step that normalizes, deduplicates, and classifies findings (`patch`/`intent_gap`/`bad_spec`/`defer`/`reject`), followed by automated resolution.

**Retry + fallback:** `runner.sh` detects soft failures (exit code != 0, OR duration < 5s, OR output < 200 bytes). Flow: primary → retry primary → fallback profile → fail. Fallback chains cross providers but don't recurse.

**Git checkpointing:** Each phase commits a WIP checkpoint. On completion, all checkpoints are squashed into a single conventional commit. `--from-step` resumes from any checkpoint.

**Step ID scheme:** Numeric (`N.M`) = sequential. Letter suffix (`N.Ma`) = parallel slot. Next numeric after parallel (`N.M+1`) = synthesis/triage step.

**KEEP instructions:** Steps 3.4 (dev fix) and 3.5 (resolve spec) read the acceptance audit to identify passing criteria as KEEP items. Fixes must preserve passing behavior; if an amendment would invalidate a KEEP item, the conflict is flagged explicitly.

**Actionable item tracking:** Steps 1.4 and 3.5 write defer findings to the story Change Log with `[defer]` tags. Step 6.1 consolidates all actionable items into a "Human Review Required" section in the story file, with a rolling "Deferred to Future Stories" accumulator that carries forward across stories. Step 5.5 produces an Epic Exit Report aggregating all unresolved items at epic end. Step 1.1 reads the previous story's "Human Review Required" section to incorporate carry-forward items. The pipeline warns before Phase 1 if the previous story has unresolved items (`--acknowledge-previous` to skip).

## Code Conventions

- **Public functions:** `lowercase_with_underscores` (e.g., `run_ai`, `git_checkpoint`)
- **Private functions:** `_leading_underscore` (e.g., `_detect_soft_fail`, `_load_profiles`)
- **Step functions:** `step_N_M_name()` pattern (e.g., `step_1_3_spec_triage`, `step_3_2_acceptance_auditor`)
- **Global state variables:** UPPERCASE (`STORY_ID`, `DRY_RUN`, `PIPELINE_LOG`)
- **Config variables:** `cfg_` prefix (`cfg_cli`, `cfg_model`, `cfg_effort`, `cfg_fallback`)
- **Library guards:** idempotency via `[[ -n "${_LIB_SH_LOADED:-}" ]] && return 0`

## Development Notes

- All scripts use `set -euo pipefail`. Bash 3.2 compatibility is required (no associative arrays, no `declare -A`).
- The `tracking.sh` key-value store works around bash 3.2 limitations using dynamically-named variables (`_kv_step_1_3_status`).
- `auto-bmad` dispatcher uses `exec` to hand off directly — no subshell overhead.
- Pipeline artifacts go to `_bmad-output/implementation-artifacts/auto-bmad/{SHORT_ID}/`. Temporary artifacts go to a `TMP_DIR` that is cleaned on success.
- The epic script extracts conventional commit messages from the story file's `## Auto-bmad Completion` section (written by step 6.1).
- Phases 0, 4, and 5.1-5.3 are TEA-gated (skipped with `--skip-tea` or when TEA is not installed). Step 2.1 is also TEA-gated. Review phases (1.2-1.4, 3.x) are gated by `--skip-reviews` / `--fast-reviews`.
- `conf/profiles.conf` supports a legacy format (`step_id cli model effort`) alongside the `@profile` format for backward compatibility.


## Upstream Dependencies

The pipelines rely on BMAD BMM and TEA skills and workflows.

- [`bmad-method`](https://github.com/bmad-code-org/BMAD-METHOD/)
- [`TEA module`](https://github.com/bmad-code-org/bmad-method-test-architecture-enterprise)