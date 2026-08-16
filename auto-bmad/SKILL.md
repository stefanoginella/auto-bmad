---
name: auto-bmad
description: "Run the FULL BMAD build lane end-to-end — one story at a time, or an ENTIRE EPIC in one run with `epic`."
argument-hint: "[epic [--epic <N>] | --story <id> | setup | reprovision | reset-defaults | config-check | <overrides… e.g. approve spec, stop before review, start at phase 5, skip tea, dry run>]"
disable-model-invocation: true
---

# auto-bmad orchestrator

You drive the **entire BMAD build lane for ONE story** — `bmad-build-auto` plan → (opt-in spec approval) → build → follow-up review pass on a second model, plus risk-gated TEA and epic-boundary work — then stop and report. The user manually triggers the next one.

**Epic mode (`/auto-bmad epic [--epic <N>]`)** instead drives a **WHOLE epic** — every actionable story — in one run, then opens **one PR** (per `references/epic-pipeline.md`).
- The two modes share Step 0 (paths/config), the On-activation gate, the delegation mechanics, and the final report.
- Epic mode replaces Step 1's per-story preflight/target with the epic pipeline's **E0**, and Step 2's Phases 1–9 with the **E-steps** — the per-story phases become the epic's inner loop (E5).
- Epic mode warns + confirms up front — no per-story human halts (no spec-approval halt, no Phase 7 review halt; a per-story `blocked`/`needs-human` stops the whole epic).
- When `epic` is in the invocation, follow `epic-pipeline.md` from E0 onward; the per-story procedure below is the loop body.

## Output discipline
Work quietly — don't pre-announce or narrate routine reads/detections; just do them. Surface only what the user needs:
- decisions (with brief rationale);
- the first-run/config summary;
- interactive questions;
- blockers;
- the final report.

## On activation — register & configure first

Before the procedure, handle module registration and configuration.

**Resolve `{output_folder}` first** — one call, shared by this gate and Step 0:
```
python3 {skill-root}/scripts/preflight.py --project-root <project_root> --central-config-only
```
Obey its `hard_stop` before anything else — `python3` older than 3.11, or no `_bmad/config.toml` ⇒ **hard-stop**: "Not a BMAD project (no `_bmad/config.toml`). Run the BMAD installer (>= 6.11.0) first." Read `central_config.output_folder` (and `implementation_artifacts`, `planning_artifacts`, `project_name`) from its JSON. Nothing else in auto-bmad reads the central TOML.

**Trigger setup when EITHER holds:**
- invoked with `setup`, `configure`, or `install`; **or**
- auto-bmad is **not provisioned** for this project — the single condition: its runtime config `{output_folder}/auto-bmad/config.yaml` is absent (nothing else marks a project as provisioned; no agent files exist) — **and the invocation is run-intent** (bare, `--story`, `epic`, or overrides). The config-only commands (`reprovision`, `reset-defaults`, `config-check`) never trigger setup: on an unprovisioned project each prints "run `/auto-bmad setup` first" and stops (their own step 1).

**On trigger:** load `{skill-root}/assets/module-setup.md` and complete it first — help-catalog registration; then the **first-run flow** in `references/config-commands.md` writes the runtime config and syncs the review layers into `_bmad/custom/bmad-build-auto.toml`.
- `setup`/`configure`/`install` always re-run registration even if already set up.

**If invoked with `reprovision`:** re-sync the managed review-layers region only — `python3 {skill-root}/scripts/build_auto_custom.py --project-root <project_root> --config {output_folder}/auto-bmad/config.yaml --apply` (`module-setup.md` → "Sync review layers"). The config must exist — otherwise "run `/auto-bmad setup` first". Config-only: report the JSON (`layers`, `warnings`, `errors`), then **stop**.

**If invoked with `reset-defaults [scope]`:** run the **restore-shipped-defaults** flow in `references/config-commands.md` → "reset-defaults".
- It is **config-only** (`profiles`, `phase_profiles`, the version stamp; re-syncs the review layers when the plan says so): report what changed, then **stop** — never start a pipeline.

**If invoked with `config-check`:** run the **config preview** in `references/config-commands.md` → "config-check".
- It reports what an update would add, everything you've changed vs the shipped defaults (including the heal-immune setup answers), then **offers to apply** the update. **Read-only until you confirm** — it writes only on the explicit "Update" choice (config heal + review-layers sync). Either way it **stops** — never starts a pipeline.

**Why the gate is layout-independent:** auto-bmad self-registers via its own `_bmad/abm/module-help.csv` + the live `_bmad/_config/bmad-help.csv` and its runtime config; it never writes the installer-owned central BMAD config (`_bmad/config.toml` + layers), so the gate keys off the runtime config only.

**Whether to start a pipeline after configuration:**
- If the user's only intent was `setup`/`configure`/`install`/`reprovision`/`reset-defaults`/`config-check` → stop after reporting what was written (or previewed); do **not** start a pipeline run.
- If configuration ran **only because it was missing** (a run-intent invocation on a fresh project) → **stop for a fresh session** instead of launching the pipeline (`references/config-commands.md` → "First-run flow", step 4).
- Otherwise → continue to the Procedure.

## The one rule

**You never do story work yourself.**
- Every BMAD step — the `bmad-build-auto` plan run, build run and follow-up review pass, every TEA skill, the deferred-work reconcile, the retrospective — runs inside a **delegated generic subagent** spawned at the phase profile's model (or via the `cli_phases` route).
- **You never read or edit story code, and never edit the spec.** Spec metadata comes only from `scripts/story_plan.py --spec` / `--find-spec`; story/epic titles from `--resolve` / `--epic --planning-dir`; the retro verdict from `--retro-verdict`; TEA values from the delegate's structured result — never from a TEA artifact. Never grep planning/impl markdown (filename-only `find` lookups are fine).
- **Git plus the orchestrator-owned bookkeeping are yours: you run them directly, never via a delegate** — git/PR work, the Phase 0 probes, the sprint-status write-back around build-auto, the Phase 7 halt handling, the Phase 8 ledger archive, the Phase 9 finalize writes, the retro verdict gate ask. The complete list is `references/git-and-pr.md` → "Ownership" — read it before Phase 1.
- You write commit/PR messages yourself.
- Your own actions are: reading config/state; running the helper scripts (`preflight.py`, `story_plan.py`, `state_plan.py`, `state_update.py`, `config_plan.py`, `build_auto_custom.py`, `deferred_ledger.py`, `cli_delegate.py`, `ci_wait.py`) and the upstream picker `uv run <sprint_plan_script> status`; deciding what to delegate; the ownership list; writing the state file; producing the final report.
- Tempted to edit code, write a test, edit the spec, or run a `/bmad-*` skill directly? **Don't** — delegate it.

**One carve-out — `inline` delegation mode** (see `references/delegation-runtime.md`): you run every step yourself under the same phase contract and structured-result discipline (build-auto's own subagents then run at depth 1).
- Even inline, the Phase 7 halt reads no code.
- On **Continue** you detect external-review changes with a git-only check and **delegate** their re-review as one more build-auto follow-up pass — never an inline read.

**`{skill-root}`** is this skill's own folder — resolve it to wherever this skill is installed (e.g. `.claude/skills/auto-bmad/` on Claude Code, or `.agents/skills/auto-bmad/` on Codex / opencode).
- Reference files live under `{skill-root}/references/`; helper scripts under `{skill-root}/scripts/`.
- Read a reference file at the moment its step calls for it.

## Delegation mechanics

- **Host, tier, nesting and the foreground rule — read `references/delegation-runtime.md`** before the first delegated step: it resolves `delegation.host` + `delegation.mode` into a tier (`subagents` / `inline`), maps each phase to a profile via `phase_profiles`, and owns the nested-subagent requirement Phase 0's `preflight.py` verifies (print `nesting.fix` verbatim on a hard-stop).
- **Before picking a tier, check `delegation.cli_phases`** — a phase listed there is delegated to an external CLI instead (`references/cli-route.md`, resolved with `scripts/cli_delegate.py`); default empty ⇒ all in-tool. Still delegation: you build the command and parse the result, never read code.
- **The delegate prompt is assembled from `references/delegation.md`** — role line + the entry's body (placeholders filled, always absolute paths) + the shared tail.
- **After each delegated step:** read the six-field result (`references/delegation.md`); read build-auto's outcome through `story_plan.py --spec <spec_path>`; then checkpoint (commit) and update state (via `state_update.py`). Identical across tiers.

## Procedure

### Step 0 — Resolve paths & config
1. Run the On-activation `preflight.py --central-config-only` call (above) if not already done this session; obey its `hard_stop`.
   - Not a BMAD project (no `_bmad/config.toml`) or `python3` < 3.11 → **hard-stop** with the message above.
2. Read `<output_folder>`, `<impl>` (`implementation_artifacts`), `<planning>` (`planning_artifacts`), `project_name` from `central_config` (already absolute).
3. Load auto-bmad config from `<output_folder>/auto-bmad/config.yaml`.
   - Missing → run the **first-run flow** in `references/config-commands.md`, write the config, sync the review layers, then **stop for a fresh session** per the same file's First-run stop.
   - Present → continue to Step 1.
   - First-run is the main interactive moment. auto-bmad can also pause at a few other points — each halt's options/conditions are in the note under Hard-stop conditions:
     - a config-drift review at preflight (Phase 0 / epic E0) — **only** when an update shipped new config/profiles; skippable with `skip config-pause`;
     - the previous epic's retro verdict gate (first story of an epic / E0; `skip retro-gate`);
     - the status-mismatch guard (a story at `review`/`in-progress` with no state file);
     - the spec-approval halt after the plan (Phase 3 → 5; opt-in via `build.spec_approval` / `approve spec`);
     - the post-follow-up-review halt (Phase 7);
     - a `FAIL` epic trace gate (Phase 8);
     - a clean-completion PR's merge prompt (Phase 9).

### Step 1 — Preflight & triage (Phase 0)
Read `references/state-and-resume.md` (target/resume) and `references/pipeline.md` Phase 0; `references/overrides.md` if the invocation carried instructions. Run **Phase 0 in its normative order** (`pipeline.md`) — every decision rides in Phase 1's `init --json`. Epic mode ⇒ `epic-pipeline.md` E0 instead.
- `dry_run` ⇒ the read-only steps only, then print the plan and stop before Phase 1 (`references/overrides.md`).
- **Epic-ownership guard:** a per-story target owned by an in-flight epic anchor **hard-stops, redirecting to `/auto-bmad epic --epic {e}`** (`references/state-and-resume.md`).

### Step 2 — Run the pipeline
**Epic mode** — if `epic` is in the invocation, execute the **E-steps** in `references/epic-pipeline.md` (E0…E_final) **instead of** Phases 1–9, then go to Step 3.
- Same delegation mechanics, same checkpoint/commit + timing discipline, same clean-tree gate before every build-auto invocation.
- No per-story halts — the Phase 7 halt is auto-continued; E8a's trace `FAIL` ask is suppressed.
- The per-story phase loop below is the epic's inner loop (E5).

**Otherwise (per-story run)** — execute Phases 1–9 exactly as specified in `references/pipeline.md`, in order.
- Skip phases whose conditions don't apply: epic-start only if `is_first_in_epic`; TEA phases per triage and `tea.enabled`; the Phase 7 follow-up pass per its gate (`code_review.followup` + the spec's `followup_review_recommended`); epic-end only if `is_last_in_epic`.
- **Also honor this run's overrides (`references/overrides.md`):** run a phase only if it's inside the start/stop window and not in `skip`; phases outside it are recorded as skipped with reason `override`.
- For each phase that runs:
  - delegate to the profile named in the pipeline per Delegation mechanics (build-auto invocations only after the clean-tree gate; capture `head_before` around them);
  - on a `blocked` / `needs-human` outcome (a build-auto `status: blocked` is `needs-human` with the blocking condition verbatim + the recovery text in `pipeline.md`) → **stop the pipeline** and jump to the report;
  - otherwise → checkpoint (commit per `references/git-and-pr.md`) and update state.

### Step 3 — Final report
Always produce a report (even on hard-stop). The report is **split**:
- a story-level **file portion** that lands in the PR diff;
- a **chat-only** wrapper for the PR/CI/merge **artifacts**.

The one-line *disposition* is **not** in that wrapper — it lives in the file's `Pipeline status` line. Both halves are always printed to the user.

- **File portion** — the persistent log under `<output_folder>/auto-bmad/reports/{key}.md` (epic mode: `reports/epic-{e}.md`, rendered with `report-section --epic`):
  - On a clean path Phase 9 / E_final already wrote + committed it **before push** (`docs(story-{e}-{s}): pipeline report` / `docs(epic-{e}): pipeline report`) — Step 3 does not re-write it.
  - On any path that didn't reach that pre-push write (a hard-stop in Phases 0–8, `needs-human`, a `stopped` halt, or an override that ended the run early) → Step 3 writes it now as a fallback: append a new `## Report — <ISO timestamp>` section, tagged `(halted — <reason>)` on this pre-finalize path, preserving any earlier sections; **no commit** (the human commits alongside their fix).
  - On a hard-stop BEFORE Phase 1's `init` (no state file yet — e.g. dirty tree, missing skill) → pass `--allow-missing-state` to `report-section`: it renders against a default state instead of erroring, so the report still lands.
  - Appends, never overwrites — incl. on resume; the one confirmed-overwrite exception (`--overwrite-confirmed`) is in `references/state-and-resume.md` → "reports/{key}.md".
- **Chat-only** — printed at the end of every run; not written to the file: the full file portion, **plus** the artifact lines listed under "Chat-only — additional lines" below.

**File portion — fields:** the file portion's fields, heading order, and per-field semantics live in `references/state-and-resume.md` → "Section template" — the **single home**, rendered literally by `scripts/state_update.py report-section` (payload keys are exact; unknown keys are rejected). Don't restate or restructure them here.

**Chat-only — additional lines.** Not committed — the finalization **artifacts/links** (why: `references/state-and-resume.md` → "reports/{key}.md"). They add the PR/CI/merge specifics on top of the disposition the file's `Pipeline status` line already carries.
- **Final status:** clean (BMAD-level flipped to `done`) vs caveated (left at `review`: draft PR / recorded blocker / waived gate / CI red or timed-out) — or "`done` (pre-retro), PR draft: <reason>" when the Phase 8 pre-retro flip ran and a later clause fired.
  - On a clean completion that was **not** merged → frame the open PR's merge as the human's remaining (optional, non-blocking) step.
  - On a successful merge → say so plainly ("Merged via merge commit; branch deleted") — no further action.
- **PR:** link (or "local branch only — no GitHub remote/`gh`"), draft? why.
  - On a merge → merge method + branch-deleted state.
  - On a failed merge attempt → the `gh` error verbatim.
- **CI:** link to the CI run the PR/push triggered + its final status (`passed`/`failed`/`timeout` if the merge prompt was on and Phase 9 waited; `queued/in_progress` otherwise). Omit if no workflows.
- **Next step:** `Human review: /bmad-checkpoint-preview <pr_url>` (mode `local` / no PR ⇒ `<branch>`; mention `<spec_path>` only as a second hint — checkpoint-preview's diff-based modes need a PR/branch argument). Epic end adds `Project context: run /bmad-project-context refresh (recommended after an epic).`

## Hard-stop conditions (surface clearly, then report & exit)
Each of these is a hard-stop (the preflight ones come from `preflight.py` — surface its `hard_stop_reasons` verbatim):
- Not a BMAD project — no `_bmad/config.toml` (BMAD >= 6.11.0), or `modules.bmm` not configured in it.
- `python3` on PATH older than 3.11 (auto-bmad reads the central TOML with `tomllib`).
- `uv` not on PATH (bmad-build-auto renders through `uv run`); or no Python >= 3.11 available to `uv` while Python downloads are disabled (`UV_PYTHON_DOWNLOADS=never`).
- Missing required skill (`bmad-build-auto`, `bmad-sprint-planning`, `bmad-retrospective`, the TEA set when enabled) — or `bmad-sprint-planning` without `scripts/sprint_plan.py` (BMAD < 6.11).
- Nested subagents not enabled for this host under the `subagents` tier — print `nesting.fix` verbatim (Claude Code `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`; Codex `[agents] max_depth` / `multi_agent_v2`; opencode `subagent_depth`).
- `code_review.cross_model_layer` names a tool whose binary is not on PATH.
- No `sprint-status.yaml` / empty `development_status`; `all stories are done — nothing for auto-bmad to run` (see the not-silent stops).
- Ambiguous or not-found `--story` or `--epic`; an ambiguous spec match (`story_plan.py --find-spec` ⇒ `ambiguous: true`).
- Both `--story` and `epic` in one invocation (pick one); an unknown override or `skip git-commits` (`overrides.md`).
- A bare per-story run whose target is owned by an in-flight epic anchor (redirect to `/auto-bmad epic --epic {e}`).
- **Epic mode only** (`epic` / `--epic <N>`): the epic is already `done`, or has no story for auto-bmad to run. Per-story, `story_plan.py --epic`'s `epic {e} is marked done` verdict is informational (a confirmed re-run of a `done` story in a `done` epic is sanctioned — `pipeline.md` Phase 0 step 5).
- Dirty working tree off the story branch; detached HEAD; merge/rebase conflict; unexpected uncommitted changes before finalize.
- `skip branch` while on the base branch (unless `dry_run`) — `git-and-pr.md`: nothing lands on base.
- The review-layers TOML (`_bmad/custom/bmad-build-auto.toml`) invalid, or one of auto-bmad's layer ids defined outside the managed region.
- A delegated step returns `blocked`/`needs-human` — incl. a build-auto `status: blocked` (missing secret/credential, required external service, manual action, `no subagents`, non-convergence).

Never push past a hard-stop — report and let the human act.

**These pipeline situations are NOT silent hard-stops** — each **asks the user** what to do:
- A config-drift review at preflight (Phase 0 / epic E0) — apply the new defaults & continue, or stop to edit `config.yaml` first. **Conditional** (only when an update shipped new config) and skippable with `skip config-pause`; epic pauses once at E0, then runs unattended.
- The previous epic's retro verdict gate (first story of an epic / E0) — the newest `epic-{e-1}-retro-*.md` says `rejected`: **Proceed** / **Stop — resolve epic {e-1} first** (`skip retro-gate`).
- The status-mismatch guard — a story at `review`/`in-progress` with no state file: enter at the matching phase / run the full pipeline anyway / stop (`state-and-resume.md`).
- An explicit `--story` on a completed (`done`-state) story — "already complete (PR …) — re-run the full pipeline anyway?".
- The spec-approval halt (Phase 3 → 5; opt-in via `build.spec_approval` or `approve spec`; never in epic mode) — approve & continue, or stop to edit the spec (the next run re-opens the halt).
- The post-follow-up-review halt (Phase 7) — run another review pass, continue (optionally after an external review; external changes get ONE delegated re-review), continue as ready (non-draft override, only when the review is unverified), or stop. Skipped when no pass ran and the review is verified; always auto-continued in epic mode.
- A `FAIL` epic trace gate (Phase 8) — remediate & re-gate / waive / stop (epic mode remediates mechanically, no ask).
- The end-of-pipeline merge prompt on a clean-completion PR (Phase 9 / E_final) — merge commit (default) / rebase / squash / don't merge, plus a delete-branch sub-question. Opt-in via `git.offer_merge`, default on.
- Epic E0 adds its unattended-run confirm, adopt and base-readiness asks (`epic-pipeline.md`).

**Not-silent STOPS** (no question — print the explicit next command, then stop):
- A no-arg pick that lands on a completed caveated story (state `done`, sprint entry parked at `review`) — the `done` rule in `state-and-resume.md` → "Target selection": report tail + PR link + how to clear the caveat or pick another story.
- `all stories are done — nothing for auto-bmad to run` (+ the optional `/bmad-retrospective -H N` hint when the picker recommends it).
