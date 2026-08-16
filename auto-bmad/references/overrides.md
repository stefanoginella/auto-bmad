# Invocation overrides

The user can steer a single run by adding instructions to the invocation — natural language (primary) or flags. Examples: `/auto-bmad stop before review`, `/auto-bmad --story 1-3 approve spec`, `/auto-bmad start at phase 5`, `/auto-bmad skip TEA`, `/auto-bmad dry run`.

Parse the invocation text into the **normalized override set** below, **echo the interpretation back to the user before running**, and record it in state (`overrides:`) and the report. Overrides apply to **this run only** — never write them to `config.yaml`. Neither `--story` **nor `--epic`** is an override; both are **target selectors** (mutually exclusive — `--story` picks one story, `epic` / `--epic N` runs a whole epic; see "Epic mode" below).

## Phase map (names ↔ numbers)

| # | Phase | Common aliases |
|---|-------|----------------|
| 0 | Preflight & triage | preflight, triage |
| 1 | Branch | branch |
| 2 | Epic start (epic test design) | epic-start, test-design |
| 3 | Plan (build-auto plan run → spec) | plan, spec |
| 4 | Pre-dev TEA (ATDD) | atdd |
| 5 | Build (build-auto) | build, implement |
| 6 | Post-dev TEA (automate) | automate |
| 7 | Follow-up review (+ human halt, tail) | review, followup, code-review |
| 8 | Epic end (gates / reconcile / retro) | epic-end, gates, retro, retrospective |
| 9 | Finalize (push / PR / hand off) | finalize, pr |

## Normalized override set

- `start_phase: <0–9>` — begin here; treat earlier phases as skipped. **Validate prerequisites** (below) and hard-stop if they're missing.
- `stop_before: <phase>` / `stop_after: <phase>` — end the run at that boundary, then go straight to the report (Step 3).
- `skip: [...]` — any of: a phase number/name, or the features `pr`, `tea`, `code-review`, `retrospective`, `branch`, `merge-prompt`, `trace-advisory`, `config-pause`, `retro-gate`.
- `spec_approval: true` — from `approve spec`: pause after Phase 3 for a human OK on the spec (same as `build.spec_approval: true`, this run only). Per-story only — rejected in epic mode.
- `git_mode: local` — force local mode (no push/PR), regardless of detection.
- `no_pr_draft: true` — open a normal (non-draft) PR even if caveats were recorded. (Also set mid-run by the Phase 7 halt's **Continue — ship as ready** option — see `pipeline.md`.)
- `dry_run: true` — run only Phase 0's **read-only** steps (no `--apply`, no `AskUserQuestion`, no delegate/`tea-triage`, no commit — drift / status-mismatch / retro-gate facts print as notes), print the plan (resolved target story, phase window/skips, per-phase profiles), then stop before Phase 1 (`pipeline.md` Phase 0 step 0). Epic mode: same rule at E0, stopping before E1.

## Not supported on the build lane (hard-stop)

- **`skip git-commits`** — hard-stop with exactly: `skip git-commits is not supported on the build lane (bmad-build-auto commits its own work); use git_mode local / skip pr to keep everything local`.
- **Any other override text** (including skips of features this lane no longer has) — hard-stop `unknown override: <text>` and list the accepted vocabulary above. Never ignore override text silently.

## How each maps to the pipeline

- **start_phase / stop_*:** define the active window.
  - Run a phase only if it's within `[start_phase, stop_after]` (inclusive) and before any `stop_before`.
  - Phases outside the window are recorded as skipped in state with the reason `override`.
  - A `start_phase` that re-enters a phase whose sprint-status write-back is **below** the entry's current status is a sanctioned regress path — that flip passes `story_plan.py --mark-status … --allow-regress` (`state-and-resume.md`). Any other `refusing to regress` exit stays a hard-stop.
- **skip pr** / **git_mode local:** Phase 9 pushes/opens nothing; the branch is left in place and noted in the report.
- **skip tea:** treat `tea.enabled` as false for this run.
  - No Phase 0 TEA triage; skips Phases 4 and 6, Phase 2 (epic test design), the Phase 8 TEA gates, and the Phase 7 tail trace advisory.
  - The retrospective still runs.
- **skip 7 / skip review / skip followup (any phase-7 skip):** normalized to `skip code-review` — echo it as `skip code-review` in the override echo and state; no follow-up pass, `review_unverified: true` (draft-predicate clause 2), and the Phase 7 halt + tail (trace advisory, deferred harvest) still run.
- **skip code-review:** no Phase 7 follow-up pass AND `review_unverified: true`.
  - `review_unverified` is draft-predicate clause 2 ⇒ the PR opens as a **draft** and the story stays at `review`.
  - Combine with `no_pr_draft` to ship non-draft anyway — the story still stays at `review`.
  - The Phase 7 halt still opens (its **Continue — ship as ready** option sets `no_pr_draft` interactively) and the Phase 7 tail (trace advisory, deferred harvest) still runs.
  - ⚠️ The second-model quality gate is removed — flag prominently. build-auto's built-in review still ran in Phase 5.
- **skip retrospective:** skip only Phase 8's retrospective sub-step **and** its pre-retro BMAD-status flip (the entry then flips at Phase 9 as usual).
- **skip trace-advisory:** suppress only the Phase 7 tail per-story trace advisory for this run, even when its conditions hold (see `tea-policy.md` §3).
  - The epic-end trace gate is unaffected.
- **skip config-pause:** suppress the Phase 0 (epic: E0) config-drift **review pause** for this run.
  - When an update shipped new config/profiles, auto-apply the additive heal + show the non-blocking echo (the pre-pause behaviour) instead of pausing to review.
  - For unattended runs that don't want to stop on the first post-update invocation.
  - The heal still runs — only the pause is skipped; nothing is reset and no customisation is touched (it stays append-only).
- **skip retro-gate:** suppress the Phase 0 (epic: E0) ask that fires when the previous epic's newest retrospective verdict is `rejected`. The run proceeds as if the human answered **Proceed**.
- **skip branch:** stay on the current branch (do not create `story/...`).
  - Only sensible with a clean intent like a dry run, or when the user is already on the right branch.
  - **Hard-stop** when `git.current_branch == git.base_branch` (preflight JSON) unless `dry_run` is also set — `git-and-pr.md`: nothing ever lands on base. Message: `` `skip branch` on the base branch would commit story work to `<base_branch>` — switch to a story branch first or drop `skip branch` ``.
  - Off-base: warn only.
- **skip merge-prompt:** same shape as `git.offer_merge: false`, just for this run.
  - Phase 9 still pushes and opens the PR.
  - It does **not** wait for CI.
  - It does **not** ask whether to merge.
  - `ci_status` is recorded as `unknown`; the existing draft-predicate clauses 1–3 (no CI gate) decide draft vs non-draft.
  - The PR stays open for the human to merge on their own time.
- **spec_approval:** Phase 3 ends with the spec-approval halt — `pipeline.md` Phase 3 step 6.
- **no_pr_draft:** adjusts only the Phase 9 draft decision (`state_plan.py --finalize --no-pr-draft`); every caveat still lands in the report and PR body.

## Epic mode (`/auto-bmad epic`)

`epic` / `--epic N` is a **target selector** (like `--story`), not an override: it runs a whole epic via `epic-pipeline.md`. `--story` and `epic` are **mutually exclusive** — hard-stop if both are given ("`--story` picks one story; `epic` runs a whole epic — pick one").

Overrides that **compose** with epic mode (echo + apply the same way):
- `dry_run` — runs only the read-only E0 steps (no `--apply`, no `AskUserQuestion`, no commit), prints the epic plan + the ordered story list + per-step profiles, then stops before E1.
- `skip tea`.
- `skip merge-prompt`.
- `git_mode local` (and `skip pr` — same effect at E_final).
- `no_pr_draft` — the epic PR opens non-draft; the epic still stays caveated.
- `skip config-pause` — suppresses the **E0** config-drift review pause (auto-apply + echo instead); the rest of the epic is unattended regardless.
- `skip retro-gate` — suppresses the **E0** previous-epic retro verdict ask.
- `skip code-review`:
  - Skips **every** story's Phase 7 follow-up pass.
  - AND sets `review_unverified` on the epic anchor (draft epic PR; the stories stay caveated).
  - Flag it even more prominently than per story — it compounds across the epic.
- `skip retrospective` — skips E8b's retrospective (and the pre-retro batch flip; E_final flips instead).
- `skip trace-advisory` — suppresses every story's Phase 7 tail advisory.

Overrides that **do NOT map** — reject in epic mode with a precise message:
- The per-story **phase window** (`start_phase` / `stop_before` / `stop_after`).
- Phase-number `skip`s.
- `approve spec` — epic mode never halts between plan and build.
- `skip branch` — E1 always creates the epic branch.
- Reason: the phase map above is per-**story**-run; epic mode runs **E-steps** (`epic-pipeline.md`), a different axis, unattended between E0 and E_final.

Resume an interrupted epic with `/auto-bmad epic --epic N` — the epic anchor drives where it picks up.

## Prerequisite validation for `start_phase`

Starting mid-pipeline requires the earlier outputs to already exist. Before skipping ahead, check the applicable prerequisite(s) below and **hard-stop with a precise message** if any is missing. Read spec facts only through `story_plan.py`; never open the spec yourself.
- start at **4 (atdd)** or later → the story's build-auto spec must exist at `ready-for-dev` or later (never `draft`/`blocked`): `python3 {skill-root}/scripts/story_plan.py --find-spec --impl-dir <impl> --story-key {key} --sprint-status <impl>/sprint-status.yaml` (`found: false` ⇒ hard-stop; `ambiguous: true` ⇒ hard-stop listing `candidates`); record `spec_path` in state (or reuse the state's `spec_path` and read `--spec <spec_path>` for the status).
- start at **5 (build)** or later → same.
- start at **7 (review)** or later → the spec's `status` (`--spec <spec_path>`) is `done` and the sprint entry is `review` (`--resolve` → `current_status`, or the `--epic` read's `epic_stories[].status`; `--find-spec`'s `status` is the spec's frontmatter status, not the sprint entry).
  - Entering Phase 7 with no Phase 5 result (this override, or the status-mismatch guard's `review` ⇒ Phase 7 route) is handled by `pipeline.md` Phase 7's "Entry at Phase 7 without a Phase 5 result" rule — the `build.*` seed, the one unconditional pass, and the `skip code-review` precedence.
- start at **9 (finalize)** → there must be commits on the story branch to push.

Prefer the normal resume path (`state-and-resume.md`) over `start_phase` when a state file exists. Use `start_phase` for deliberate manual control.

## Echo format (always show before executing)

> **Overrides for this run:** start=Phase 5 (build); stop after Phase 7; approve spec = n/a (window).
> **Phases that will run:** 5 → 6 → 7. **Will not run:** 0–4, 8, 9.

If `dry_run`, print this plan (plus the resolved target story and per-phase profiles) after Phase 0's read-only steps and stop before Phase 1 — nothing is applied, asked, delegated or committed.
