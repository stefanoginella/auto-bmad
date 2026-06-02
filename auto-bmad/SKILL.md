---
name: auto-bmad
description: "Run the FULL BMAD story implementation workflow end-to-end for one story at a time. Use when the user says 'auto-bmad', 'run auto-bmad', 'implement the next story', 'auto implement story X-Y', or wants the whole create-story -> dev-story -> code-review (+ TEA + epic-boundary) pipeline driven automatically on a branch with a PR at the end."
argument-hint: "[--story <id> | setup | reprovision | reset-defaults | <overrides…>]"
---

# auto-bmad orchestrator

You drive the **entire BMAD implementation workflow for ONE story**, then stop and report so
the user manually triggers the next one.

## Output discipline
Work quietly: don't pre-announce or narrate routine reads/detections ("Let me check…", "Now I'll
read…") — just do them. Surface only what the user needs: decisions (with brief rationale), the
first-run/config summary, interactive questions, blockers, and the final report. Terse beats
play-by-play; this is an autonomous orchestrator, not a running commentary.

## On activation — register & provision first

Before the procedure, handle module registration and delegate provisioning:
- If invoked with `setup`, `configure`, `install`, or `reprovision`, **or** if
  `{project-root}/_bmad/config.yaml` has no `abm` section → load
  `{skill-root}/assets/module-setup.md` and complete it first. It registers the module, writes
  config, and renders the tool-native delegate agents (`.claude/agents/ab-*.md` and/or
  `.codex/agents/ab-*.toml`) for the selected `target_tools`. `reprovision` runs only the
  agent-render step; `setup`/`configure` always re-run registration even if already registered.
- If invoked with `reset-defaults [scope]`, run the **restore-shipped-defaults** flow in
  `references/state-and-resume.md` → "reset-defaults": overwrite the asset-sourced
  `profiles`/`phase_profiles` from the shipped asset (after showing the diff and confirming), then
  re-render delegates if a profile changed. It needs a BMAD project + an existing `config.yaml`,
  is **config-only** (report what changed, then **stop** — never start a pipeline), and never
  touches the `delegation`/`tea`/`git`/`code_review` setup blocks.
- This requires a BMAD project; if `_bmad/` is absent, the Step 0.1 hard-stop applies.
- If the user's only intent was `setup`/`configure`/`reprovision`/`reset-defaults`, stop after
  reporting what was written/rendered — do **not** start a pipeline run. Otherwise continue to the
  Procedure — but
  if configuration ran **only because it was missing** (a run-intent invocation on a fresh
  project), the Procedure's first-run flow finishes the remaining config and then **stops for a
  fresh session** rather than launching the pipeline (see Step 0.3).

## The one rule

**You never do story work yourself.** Every BMAD step — create-story, dev-story, code-review,
every TEA skill, retrospective — runs inside a delegated sub-agent (the `ab-*` profiles).
**Git plus the orchestrator-owned finalize actions are yours: you run them directly, never via
a delegate** — see `references/git-and-pr.md` → "Ownership" for the exact list (git preflight,
branching, per-phase commits, push, PR, the Phase 9 BMAD-status flip on a clean completion, and
the opt-in merge prompt + `gh pr merge` execution). You hold the full pipeline context, so you
write commit/PR messages yourself; delegating any of that would only add a slow round-trip. Your
own actions are: reading config/state, running `scripts/story_plan.py`, deciding what to delegate,
the ownership list above, writing the state file, and producing the final report. If you ever
feel tempted to edit code, write a test, or run a `/bmad-*` skill directly — don't; delegate it.
(The **only** exception is `inline` delegation mode on a host with no subagent support — see
`references/delegation-runtime.md` — and even then you follow the exact same phase contract and
structured-result discipline.)

`{skill-root}` is this skill's own folder — resolve it to wherever this skill is installed
(e.g. `.claude/skills/auto-bmad/` or `.codex/skills/auto-bmad/`). Reference files live under
`{skill-root}/references/` and the helper scripts under `{skill-root}/scripts/`. Read a
reference file at the moment its step calls for it.

## Delegation mechanics

- **Pick the spawn method by host/tier — read `references/delegation-runtime.md`.** It uses
  `delegation.host` + `delegation.mode` from config: `custom-subagents` (Claude Code or Codex)
  runs each step in an isolated delegate at the profile's tuned model + thinking/reasoning
  effort; `general-subagents` uses the host's generic subagent without effort tuning; `inline`
  runs the step in this context as a last resort. `phase_profiles` maps each phase to a profile
  (`ab-xhigh`/`ab-high`/`ab-alt-xhigh`/`ab-alt-high`); `profiles` holds each profile's per-tool model +
  effort. The tool-native delegate files (`.claude/agents/ab-*.md`, `.codex/agents/ab-*.toml`)
  are rendered at setup by `scripts/render-agents.py` from those profiles.
- The delegate prompt is always the **exact** content from `references/delegation.md` for that
  step, with placeholders filled (story id, absolute file paths). Pass absolute paths — the
  delegate resolves BMAD's `{project-root}` from its cwd, but explicit paths remove ambiguity.
- After each delegated step, read the structured result. Append any **retro notes** to the epic
  retro-notes file — but skip `none`/empty/routine notes, so clean phases add nothing and the file
  stays usable across a long epic (see `references/state-and-resume.md`). Then checkpoint (commit)
  and update state. This is identical across tiers.

## Procedure

### Step 0 — Resolve paths & config
1. Confirm cwd is a BMAD project: `_bmad/` exists and `_bmad/bmm/config.yaml` is readable.
   If not → **hard-stop**: "Not a BMAD project (no `_bmad/`). Run the BMAD installer first."
2. Read `_bmad/bmm/config.yaml` for `implementation_artifacts`, `planning_artifacts`,
   `project_name` (resolve `{project-root}` to the absolute cwd).
3. Load auto-bmad config from `{project-root}/_bmad-output/auto-bmad/config.yaml`. If missing,
   run the **first-run flow** in `references/state-and-resume.md`, write the config, then **stop
   for a fresh session** per the same file's First-run stop (don't start the pipeline on the
   context that just did setup). On later runs the config already exists, so this stop does not
   apply — continue to Step 1. First-run is the main interactive moment; auto-bmad also asks when
   code review fails to converge within the iteration cap (Phase 7), when an epic trace gate
   returns `FAIL` (Phase 8), and at the very end on a clean-completion PR — whether to merge
   (Phase 9, opt-in via `git.offer_merge`).

### Step 1 — Preflight
Read `references/state-and-resume.md`, `references/pipeline.md` (Phase 0), and — if the
invocation carried any instructions — `references/overrides.md`, then:
0. **Parse invocation overrides** (if any): normalize them per `references/overrides.md`,
   **echo the interpretation plus the resolved phase window/skips to the user**, and record them
   in state under `overrides`. If `dry_run`, print the plan and stop here. (`skip tea` flips
   `tea.enabled` off for this run, affecting sub-steps 1 and 4 below.)
1. **Skill availability:** verify the BMAD skills required for the selected path exist
   (core always; TEA set only if `tea.enabled`; epic-end skills if this is a last story). Missing
   → **hard-stop** listing exactly which skills are absent and how to install them.
2. **Target story** (precedence when NO `--story` argument is given):
   a. **Resume an interrupted pipeline first:** run
      `python3 {skill-root}/scripts/state_plan.py --state-dir <output_folder>/auto-bmad/state`.
      If it reports `resume: true`, its `target` (the most-recently-updated in-flight story) wins —
      auto-bmad finishes in-flight work before starting anything new (note any `extra_in_flight`
      in the report; there should be at most one given "one story at a time"). Don't hand-roll a
      glob loop for this — see `state-and-resume.md` → "Target selection & resume logic".
   b. Otherwise run
      `python3 {skill-root}/scripts/story_plan.py --sprint-status <impl>/sprint-status.yaml --impl-dir <impl>`
      to pick the next actionable story. Its precedence is `in-progress → review →
      ready-for-dev → backlog → retrospective`, so it **resumes BMAD-level unfinished work
      before pulling a fresh backlog item** — it does not jump straight to backlog.
   With a `--story <arg>`: pass `--story <arg>` to the script (overrides the above). Either way,
   parse the JSON; if `hard_stop` is true → surface `hard_stop_reason` and stop.
3. **Resume check:** for the chosen `story_key`, run the same reader with
   `--story-key {story_key}` (exact-path lookup, no glob). `resume: true` ⇒ resume from the first
   phase not in `completed_phases` (and continue the review loop from `code_review_iterations`);
   otherwise initialize a fresh state file in Phase 1.
4. **Git preflight, project-context probe & triage** (per Phase 0 of the pipeline): **you run the
   git preflight and the project-context probe directly** — detect repo, clean tree, git mode,
   base branch; then probe for an existing `project-context.md` at the BMAD-canonical write path
   (`<output_folder>/project-context.md`) with a `find` fallback anywhere under `<project_root>`
   except `node_modules/`/`.venv/`/`.git/` (see Phase 0 for the exact invocation — it mirrors the
   `bmad-generate-project-context` skill's own discovery) and record
   `needs_project_context_bootstrap` in state. Then, **only if TEA enabled**, delegate the
   story-risk classification to the `tea_triage` profile to pick per-story TEA skills. Record
   the decisions in state.

### Step 2 — Run the pipeline
Execute Phases 1–9 exactly as specified in `references/pipeline.md`, in order, skipping phases
whose conditions don't apply (epic-start only if `is_first_in_epic`; TEA phases per triage and
`tea.enabled`; epic-end only if `is_last_in_epic`). **Also honor this run's overrides
(`references/overrides.md`):** run a phase only if it's inside the start/stop window and not in
`skip`; phases outside it are recorded as skipped with reason `override`. For each phase that runs:
- delegate to the profile named in the pipeline using the prompt from `references/delegation.md`
  (spawn it per `references/delegation-runtime.md`);
- on a `blocked` / `needs-human` outcome, **stop the pipeline** and jump to the report;
- otherwise checkpoint (commit per `references/git-and-pr.md` — **unless `skip git-commits` is in
  effect**), append retro notes, update state.

### Step 3 — Final report
Always produce a report (even on hard-stop). The report is **split**: a story-level **file
portion** that lands in the PR diff, and a **chat-only** wrapper for PR/CI/merge details that
exist elsewhere already (git, GitHub, sprint-status). Both are always printed to the user.

- **File portion** (the persistent log under `{project-root}/_bmad-output/auto-bmad/reports/{key}.md`):
  on a clean path this file was already written + committed in Phase 9 **before push**
  (`docs(story-{e}-{s}): pipeline report`) so it ships in the PR — Step 3 does not re-write it
  in that case. On any path that didn't reach the Phase 9 pre-push write (a hard-stop in
  Phases 0–8, `needs-human`, or an override that ended the run early), Step 3 writes it now as
  a fallback (append a new `## Report — <ISO timestamp>` section, preserving any earlier
  sections; **no commit** — the tree is already in needs-human state and the human will commit
  alongside their fix). Never overwrite on resume — earlier runs' sections carry context we
  must not lose. The ONLY time you overwrite is a deliberate full re-run of an already-`done`
  story, after explicit user confirmation; if declined, append.
- **Chat-only** (printed at the end of every run; not written to the file): the full file
  portion below, **plus** the PR / CI / merge / final-status lines listed underneath.

**File portion — fields** (story-level outputs preserved across runs; use the exact heading
order and field labels from `references/state-and-resume.md` → "Section template" — no
restructuring per run, so PR reviewers always find each field in the same place):
- **Story:** key, branch (HEAD short sha).
- **Pipeline status:** one-line summary (clean completion / halted at Phase N / draft (reason) / …).
- **Timing:** `started_at`/`completed_at` (or "in progress"), total elapsed, and the best-effort
  AI-run vs human/idle-wait split (`active_seconds` vs `elapsed − active_seconds`); note resume count if >1.
- **Phases run / Skipped:** the Phase N list each line, with profile in parens for delegated phases.
- **Overrides:** any invocation overrides applied this run (phase window, skips, caps); "none" if none.
- **TEA:** which skills ran and outcomes; epic gate decision if last story; "disabled" if `tea.enabled=false`.
- **Code review:** iterations run; per-iteration verdict + severity counts.
- **Open questions** surfaced by any step ("(none)" if empty — keep the heading).
- **Deferred work** (anything intentionally postponed; also appended to the durable cross-story
  `<impl>/deferred-work.md` ledger). "(none)" if empty — keep the heading.
- **Planning drift** (epic-end only): planning assumptions the retrospective proved wrong + the
  recommended re-sync (document-project → generate-project-context → `/bmad-prd` update;
  `/bmad-correct-course` if structural). Non-blocking, never auto-run. "(none)" if clean or not epic-end.
- **⚠️ Needs human:** blockers / manual actions. On a **caveated** completion these are required
  before the story can be considered done (it was left at `review`). On a **clean** completion the
  story is already `done`; list only genuine follow-ups (e.g. merging the open PR is optional and
  on the human's own time) — do not imply the merge gates `done`. "(none)" if clean.
- **Next:** the next story `story_plan.py` would pick (preview only — do NOT start it).

**Chat-only — additional lines** (not committed; retrievable from git/GitHub/sprint-status later):
- **Final status:** clean (BMAD-level flipped to `done`) vs caveated (left at `review`: draft PR /
  recorded blocker / waived gate / CI red or timed-out). On a clean completion that was **not**
  merged, frame the open PR's merge as the human's remaining (optional, non-blocking) step. On a
  successful merge, say so plainly ("Merged via merge commit; branch deleted") — no further action.
- **PR:** link (or "local branch only — no GitHub remote/`gh`"), draft? why. On a merge: merge
  method + branch-deleted state; on a failed merge attempt: the `gh` error verbatim.
- **CI:** link to the CI run the PR/push triggered + its final status (`passed`/`failed`/`timeout`
  if the merge prompt was on and Phase 9 waited; `queued/in_progress` otherwise). Omit if no
  workflows.

## Hard-stop conditions (surface clearly, then report & exit)
Not a BMAD project; missing required skill; no `sprint-status.yaml` / no epics; ambiguous or
not-found `--story`; epic already `done`; dirty working tree on the wrong branch; merge/rebase
conflict; a delegated step returns `blocked`/`needs-human` (missing secret/credential, required
external service, or manual action). Never push past a hard-stop — report and let the human act.

(Note: three pipeline situations are NOT silent hard-stops — each **asks the user** what to do:
code review not converging within `max_iterations` (Phase 7); a `FAIL` epic trace gate
(Phase 8 — remediate & re-gate / waive / stop); and the end-of-pipeline merge prompt on a
clean-completion PR (Phase 9 — merge commit (default) / rebase / squash / don't merge, plus a
delete-branch sub-question — opt-in via `git.offer_merge`, default on).)
