---
name: auto-bmad
description: "Run the FULL BMAD build lane end-to-end — one story at a time, or an ENTIRE EPIC in one run with `epic`. Use when the user says 'auto-bmad', 'run auto-bmad', 'implement the next story', 'auto implement story X-Y', 'auto-bmad epic', 'implement the whole epic N', or wants the bmad-build-auto plan -> build -> follow-up review pipeline (+ risk-gated TEA + epic-boundary gates/retrospective) driven automatically on a branch with a PR at the end."
argument-hint: "[epic [--epic <N>] | --story <id> | setup | reprovision | reset-defaults | config-check | <overrides… e.g. approve spec, stop before review, start at phase 5, skip tea, dry run>]"
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
- auto-bmad is **not provisioned** for this project — the single condition: its runtime config `{output_folder}/auto-bmad/config.yaml` is absent (nothing else marks a project as provisioned; no agent files exist).

**On trigger:** load `{skill-root}/assets/module-setup.md` and complete it first — help-catalog registration; then the **first-run flow** in `references/state-and-resume.md` writes the runtime config and syncs the review layers into `_bmad/custom/bmad-build-auto.toml`.
- `setup`/`configure`/`install` always re-run registration even if already set up.

**If invoked with `reprovision`:** re-sync the managed review-layers region only — `python3 {skill-root}/scripts/build_auto_custom.py --project-root <project_root> --config {output_folder}/auto-bmad/config.yaml --apply` (`module-setup.md` → "Sync review layers"). The config must exist — otherwise "run `/auto-bmad setup` first". Config-only: report the JSON (`layers`, `warnings`, `errors`), then **stop**.

**If invoked with `reset-defaults [scope]`:** run the **restore-shipped-defaults** flow in `references/state-and-resume.md` → "reset-defaults".
- It is **config-only** (`profiles`, `phase_profiles`, the version stamp; re-syncs the review layers when the plan says so): report what changed, then **stop** — never start a pipeline.

**If invoked with `config-check`:** run the **config preview** in `references/state-and-resume.md` → "config-check".
- It reports what an update would add, everything you've changed vs the shipped defaults (including the heal-immune setup answers), then **offers to apply** the update. **Read-only until you confirm** — it writes only on the explicit "Update" choice (config heal + review-layers sync). Either way it **stops** — never starts a pipeline.

**Why the gate is layout-independent:** auto-bmad self-registers via its own `_bmad/abm/module-help.csv` + the live `_bmad/_config/bmad-help.csv` and its runtime config; it never writes the installer-owned central BMAD config (`_bmad/config.toml` + layers), so the gate keys off the runtime config only.

**Whether to start a pipeline after configuration:**
- If the user's only intent was `setup`/`configure`/`install`/`reprovision`/`reset-defaults`/`config-check` → stop after reporting what was written (or previewed); do **not** start a pipeline run.
- If configuration ran **only because it was missing** (a run-intent invocation on a fresh project) → the first-run stop applies: finish config + the review-layers sync, then **stop for a fresh session** rather than launch the pipeline.
- Otherwise → continue to the Procedure.

## The one rule

**You never do story work yourself.**
- Every BMAD step — the `bmad-build-auto` plan run, build run and follow-up review pass, every TEA skill, the deferred-work reconcile, the retrospective — runs inside a **delegated generic subagent** spawned at the phase profile's model (or via the `cli_phases` route).
- **You never read or edit story code, and never edit the spec.** Spec metadata comes only from `scripts/story_plan.py --spec` / `--find-spec`; story/epic titles from `--resolve` / `--epic --planning-dir`; the retro verdict from `--retro-verdict`; TEA values from the delegate's structured result — never from a TEA artifact. Never grep planning/impl markdown (filename-only `find` lookups are fine).
- **Git plus the orchestrator-owned bookkeeping are yours: you run them directly, never via a delegate** — exact list in `references/git-and-pr.md` → "Ownership": git/PR work (preflight, branching, per-phase commits, the clean-tree gate before every build-auto invocation, push, PR, CI wait, merge prompt); the Phase 0 probes (`preflight.py` incl. uv/Python 3.11/nesting/TOML/`AGENTS.md`, the config-drift heal, the review-layers TOML sync); the sprint-status write-back around build-auto (`story_plan.py --mark-status`, incl. the epic lift, the Phase 8 pre-retro flip and the Phase 9 flip); the Phase 7 halt handling (git-only external-change detection — the re-review itself is a delegated build-auto pass); the Phase 8 ledger archive (+ the Phase 7 tail harvest); the Phase 9 finalize writes; the retro verdict gate ask.
- You write commit/PR messages yourself.
- Your own actions are: reading config/state; running the helper scripts (`preflight.py`, `story_plan.py`, `state_plan.py`, `state_update.py`, `config_plan.py`, `build_auto_custom.py`, `deferred_ledger.py`, `cli_delegate.py`, `ci_wait.py`) and the upstream picker `uv run <sprint_plan_script> status`; deciding what to delegate; the ownership list; writing the state file; producing the final report.
- Tempted to edit code, write a test, edit the spec, or run a `/bmad-*` skill directly? **Don't** — delegate it.

**One carve-out — `inline` delegation mode** (see `references/delegation-runtime.md`): you run every step yourself under the same phase contract and structured-result discipline (build-auto's own subagents then run at depth 1).
- Even inline, the Phase 7 halt reads no code.
- On **Continue** you detect external-review changes with a git-only check and **delegate** their re-review as one more build-auto follow-up pass — never an inline read.

**`{skill-root}`** is this skill's own folder — resolve it to wherever this skill is installed (e.g. `.claude/skills/auto-bmad/`, `.codex/skills/auto-bmad/`, or `.opencode/skills/auto-bmad/`).
- Reference files live under `{skill-root}/references/`; helper scripts under `{skill-root}/scripts/`.
- Read a reference file at the moment its step calls for it.

## Delegation mechanics

- **Pick the spawn method by host/tier — read `references/delegation-runtime.md`.** That file:
  - resolves `delegation.host` + `delegation.mode` from config into a tier — `subagents` (a generic host subagent at the phase profile's model: per-call model on Claude Code and Codex, per-call effort on Codex only, opencode inherits the user's model) or `inline` (this context, last resort);
  - maps each phase to a profile via `phase_profiles` (ten keys) and takes each profile's per-tool model + effort from `profiles` (`assets/profiles.yaml` copied into the runtime config; no persona text, no rendered agent files);
  - states the **nested-subagent requirement** of the `subagents` tier — orchestrator → delegate → build-auto's own subagents (depth 2) — which Phase 0's `preflight.py` verifies per host (`nesting.status`; print `nesting.fix` verbatim on a hard-stop);
  - mandates **foreground** spawns — the orchestrator spawns each delegate synchronously, and every prompt tells the delegate to spawn build-auto's subagents synchronously too.
- **Opt-in external-CLI routing — before picking a tier, check `delegation.cli_phases`.**
  - A phase listed there is delegated to an external CLI (`claude -p` / `codex exec` / `opencode run`) instead of an in-tool subagent (routing `build`/`followup_review` runs build-auto inside that CLI).
  - Resolve it with `scripts/cli_delegate.py` (see `references/delegation-runtime.md` → "Per-phase external-CLI routing").
  - Still delegation — you build the command and parse the result, never read code.
  - Default is empty (all in-tool).
- **The delegate prompt is always the exact content from `references/delegation.md` for that step** — role line first, shared autonomy directive last, placeholders filled (story id, file paths — always pass absolute paths).
- **After each delegated step:** read the six-field structured result (Outcome / Files changed / Status / Open questions / Deferred work / Blockers); read build-auto's outcome through `story_plan.py --spec <spec_path>`; then checkpoint (commit) and update state (via `state_update.py`). This is identical across tiers.

## Procedure

### Step 0 — Resolve paths & config
1. Run the On-activation `preflight.py --central-config-only` call (above) if not already done this session; obey its `hard_stop`.
   - Not a BMAD project (no `_bmad/config.toml`) or `python3` < 3.11 → **hard-stop** with the message above.
2. Read `<output_folder>`, `<impl>` (`implementation_artifacts`), `<planning>` (`planning_artifacts`), `project_name` from `central_config` (already absolute).
3. Load auto-bmad config from `<output_folder>/auto-bmad/config.yaml`.
   - Missing → run the **first-run flow** in `references/state-and-resume.md`, write the config, sync the review layers, then **stop for a fresh session** per the same file's First-run stop.
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
First read `references/state-and-resume.md` and `references/pipeline.md` (Phase 0). Read `references/overrides.md` too if the invocation carried any instructions. Then run **Phase 0 in its normative step order** — every step's inputs come only from earlier steps (no state, no commit; every decision rides in Phase 1's `init --json`):
0. **Parse invocation overrides** (if any).
   - Normalize them per `references/overrides.md`; **echo the interpretation plus the resolved phase window/skips to the user.**
   - Carry them into Phase 1's `init --json` under `overrides` — no state file exists yet (pipeline.md, the Phase 0 exception).
   - If `dry_run` → still run the **read-only** sub-steps 1–7 and 9 below (no `--apply`, no `AskUserQuestion`, no delegate, no commit — print any drift / status-mismatch / retro-gate fact as a note; sub-step 8's `tea-triage` does not run), then print the plan (the resolved target story, the phase window/skips, the per-phase profiles) and stop before Phase 1. Epic mode: the same rule at E0 (`epic-pipeline.md`).
   - `skip tea` flips `tea.enabled` off for this run — affecting sub-steps 3 and 8 below.
1. **Host/tier** — resolve per `references/delegation-runtime.md` (config + detection); resolve any `delegation.cli_phases` route with `cli_delegate.py` (`ok: false` ⇒ hard-stop with its `errors`).
2. **Target/resume pre-read** (no `uv`, no git — only the state dir and `sprint-status.yaml`):
   - With `--story <arg>`: `python3 {skill-root}/scripts/story_plan.py --resolve <arg> --sprint-status <impl>/sprint-status.yaml --planning-dir <planning>` (`E-S`, `E.S`, `E-Sx`, a full key, or a slug fragment; `hard_stop` ⇒ surface `hard_stop_reason` — not found / ambiguous with `candidates` — and stop); then `python3 {skill-root}/scripts/state_plan.py --state-dir <output_folder>/auto-bmad/state --story-key {key}` ⇒ `resume`, `status`, `branch`.
   - No arg: `state_plan.py --state-dir <output_folder>/auto-bmad/state` — `resume: true` ⇒ its `target` wins (+ that record's `branch`; note any `extra_in_flight` in the report); else the target is picked at sub-step 5. Don't hand-roll a glob loop — `state-and-resume.md` → "Target selection & resume logic".
   - **Epic mode** (`epic` in the invocation): follow `epic-pipeline.md` E0 from here (epic-anchor resume pre-read via `state_plan.py --scope epic`; `{e}` = `--epic <N>`, else the picker's recommendation). Sub-steps 3–9 below and Step 2's Phases 1–9 do **not** run — the E-steps replace them.
   - **Per-story runs — epic-ownership guard:** `state_plan.py --state-dir <output_folder>/auto-bmad/state --scope epic` — an in-flight epic anchor whose `epic_num` matches the target's epic ⇒ **hard-stop, redirecting to `/auto-bmad epic --epic {e}`** (finishing one story alone would split that epic's single PR).
3. **ONE full `preflight.py` call** — `--project-root <project_root> --host <host> --tier <tier> --require-skills <csv> --skills-dirs <per host> [--tea-enabled] [--cross-model-tool <code_review.cross_model_layer>] [--cli-phases <keys of delegation.cli_phases>] [--expected-branch <branch> — only when sub-step 2 found a resume target]` (exact CSVs in `pipeline.md` Phase 0 step 3).
   - Required skills: core `bmad-build-auto,bmad-sprint-planning,bmad-retrospective` (always — so the CSV is computable before the pick) + the six `bmad-testarch-*` skills when `tea.enabled`. Never any v6-shims skill.
   - Obey `hard_stop` / `hard_stop_reasons` (Python/uv/central TOML/nesting — print `nesting.fix` verbatim/cross-model binary/`skills.missing` with the install hint/git rules); surface `warnings` (`AGENTS.md` block, legacy `_bmad/<bmm|core>/config.yaml`, TEA config, uv/nesting warns) now and in the report's Needs human list; keep `skills.sprint_plan_script` and the `git` block.
4. **Config-drift heal + review, then review-layers freshness** — `config_plan.py --check` → the pre-run pause only on reviewable drift (`skip config-pause`), else auto-apply; then `build_auto_custom.py --check` → auto `--apply` when stale (`errors` ⇒ hard-stop). Mechanics: `pipeline.md` Phase 0 step 4.
5. **Story pick** (only when sub-step 2 produced no target): `uv run <sprint_plan_script> status --status-file <impl>/sprint-status.yaml --date "<now MM-DD-YYYY HH:MM>"` — target = `recommendation.story_key` (its precedence `in-progress → review → ready-for-dev → backlog` resumes BMAD-level unfinished work first); `ok: false` / `all_done` / null key ⇒ the hard-stops below; keep `open_action_items`; then `state_plan.py --story-key {key}` for the picked key (`status: done` ⇒ the not-silent stop below). Then **always** `story_plan.py --epic {e} --sprint-status <impl>/sprint-status.yaml --planning-dir <planning>` for `is_first_in_epic` / `is_last_in_epic` / `epic_story_count` / `stories_after_in_epic` / `title` / `epic_title`.
6. **Resume check / status-mismatch guard** — `resume: true` ⇒ resume from the first phase not in `completed_phases` (`state-and-resume.md` resume rules: Phase 3 by the resume matrix, Phase 5/7 re-invoke build-auto with `<spec_path>`, halts re-open). Otherwise a fresh state file in Phase 1 — after the **status-mismatch guard** (a story at `review`/`in-progress` with no state file asks the user; `status: done` state ⇒ the `done` rule).
7. **Retro verdict gate** (first story of an epic): `story_plan.py --retro-verdict --impl-dir <impl> --epic {e-1}` — `rejected` ⇒ ask **Proceed** / **Stop** (`skip retro-gate`).
8. **TEA triage** (only if `tea.enabled`): delegate **`tea-triage`** → `tea_triage` on the story's epic entry; classify per `references/tea-policy.md`; record `tea_risk` / `tea_selected` / `tea_rationale`. On a resume with Phase 0 already in `completed_phases`, reuse the recorded values — don't re-delegate.
9. **Story title** `{title}` from the `--resolve` / `--epic` read (`null` ⇒ `{slug}` with `-` → space). Never grep the epics document.

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
  - Never overwrite on resume.
  - The ONLY overwrite is a deliberate full re-run of an already-`done` story, after explicit user confirmation (`--overwrite-confirmed`) — if declined, append.
- **Chat-only** — printed at the end of every run; not written to the file: the full file portion, **plus** the artifact lines listed under "Chat-only — additional lines" below.

**File portion — fields:** the file portion's fields, heading order, and per-field semantics live in `references/state-and-resume.md` → "Section template" — the **single home**, rendered literally by `scripts/state_update.py report-section` (payload keys are exact; unknown keys are rejected). Don't restate or restructure them here.

**Chat-only — additional lines.** Not committed — the finalization **artifacts/links**, retrievable from git/GitHub/sprint-status later. They add the PR/CI/merge specifics on top of the disposition the file's `Pipeline status` line already carries; the disposition itself is not chat-only.
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
- Epic E0 adds its adopt and base-readiness asks (`epic-pipeline.md`).

**Not-silent STOPS** (no question — print the explicit next command, then stop):
- A no-arg pick that lands on a completed caveated story (state `done`, sprint entry parked at `review`) — the `done` rule in `state-and-resume.md` → "Target selection": report tail + PR link + how to clear the caveat or pick another story.
- `all stories are done — nothing for auto-bmad to run` (+ the optional `/bmad-retrospective -H N` hint when the picker recommends it).
