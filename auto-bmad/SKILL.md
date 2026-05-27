---
name: auto-bmad
description: "Run the FULL BMAD story implementation workflow end-to-end for one story at a time. Use when the user says 'auto-bmad', 'run auto-bmad', 'implement the next story', 'auto implement story X-Y', or wants the whole create-story -> dev-story -> code-review (+ TEA + epic-boundary) pipeline driven automatically on a branch with a PR at the end."
argument-hint: "[--story <id> | setup | reprovision | <overrides…>]"
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
- This requires a BMAD project; if `_bmad/` is absent, the Step 0.1 hard-stop applies.
- If the user's only intent was `setup`/`configure`/`reprovision`, stop after reporting what was
  written/rendered — do **not** start a pipeline run. Otherwise continue to the Procedure — but
  if configuration ran **only because it was missing** (a run-intent invocation on a fresh
  project), the Procedure's first-run flow finishes the remaining config and then **stops for a
  fresh session** rather than launching the pipeline (see Step 0.3).

## The one rule

**You never do story work yourself.** Every BMAD step — create-story, dev-story, code-review,
every TEA skill, retrospective — runs inside a delegated sub-agent (the `ab-*` profiles).
**Git is yours, though: you run all git/PR operations directly, never via a delegate** — repo/mode
preflight, branching, per-phase commits, push, and PR. You hold the full pipeline context, so you
write the commit and PR messages yourself; delegating git would only add a slow round-trip. So
your own actions are: reading config/state, running `scripts/story_plan.py`, deciding what to
delegate, **all git/PR work** (per `references/git-and-pr.md`), writing the state file, and
producing the final report. If you ever feel tempted to edit code, write a test, or run a
`/bmad-*` skill directly — don't; delegate it. (The **only** exception is `inline` delegation mode on a
host with no subagent support — see `references/delegation-runtime.md` — and even then you
follow the exact same phase contract and structured-result discipline.)

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
  (`ab-max`/`ab-xhigh`/`ab-high`/`ab-fast`); `profiles` holds each profile's per-tool model +
  effort. The tool-native delegate files (`.claude/agents/ab-*.md`, `.codex/agents/ab-*.toml`)
  are rendered at setup by `scripts/render-agents.py` from those profiles.
- The delegate prompt is always the **exact** content from `references/delegation.md` for that
  step, with placeholders filled (story id, absolute file paths). Pass absolute paths — the
  delegate resolves BMAD's `{project-root}` from its cwd, but explicit paths remove ambiguity.
- After each delegated step, read the structured result. Append its **retro notes** to the epic
  retro-notes file. Then checkpoint (commit) and update state. This is identical across tiers.

## Procedure

### Step 0 — Resolve paths & config
1. Confirm cwd is a BMAD project: `_bmad/` exists and `_bmad/bmm/config.yaml` is readable.
   If not → **hard-stop**: "Not a BMAD project (no `_bmad/`). Run the BMAD installer first."
2. Read `_bmad/bmm/config.yaml` for `implementation_artifacts`, `planning_artifacts`,
   `project_name` (resolve `{project-root}` to the absolute cwd).
3. Load auto-bmad config from `{project-root}/_bmad-output/auto-bmad/config.yaml`. If missing,
   run the **first-run flow** in `references/state-and-resume.md`, then write the config.
   (First-run is normally the only interactive moment; the one other place auto-bmad may ask is
   when code review fails to converge within the iteration cap — see Phase 7.)
   **After first-time configuration completes** (this first-run write, plus any module
   registration done earlier this session), **stop — do not start the pipeline this session.**
   Report what was configured and tell the user to open a **new session with fresh context** and
   run `/auto-bmad` to begin the first story. If the config already existed (normal later runs),
   this stop does not apply — continue to Step 1.

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
   a. **Resume an interrupted pipeline first:** if any `state/*.yaml` has `status != done`,
      that story wins — auto-bmad finishes in-flight work before starting anything new (there
      should be at most one given "one story at a time"; if several, take the most recently
      modified and note the others in the report).
   b. Otherwise run
      `python3 {skill-root}/scripts/story_plan.py --sprint-status <impl>/sprint-status.yaml --impl-dir <impl>`
      to pick the next actionable story. Its precedence is `in-progress → review →
      ready-for-dev → backlog → retrospective`, so it **resumes BMAD-level unfinished work
      before pulling a fresh backlog item** — it does not jump straight to backlog.
   With a `--story <arg>`: pass `--story <arg>` to the script (overrides the above). Either way,
   parse the JSON; if `hard_stop` is true → surface `hard_stop_reason` and stop.
3. **Resume check:** if a non-`done` state file exists for the chosen `story_key`, resume from
   the first phase not in `completed_phases` (and continue the review loop from
   `code_review_iterations`). Otherwise initialize a fresh state file in Phase 1.
4. **Git preflight & triage** (per Phase 0 of the pipeline): **you run the git preflight directly**
   — detect repo, clean tree, git mode, base branch. Then, **only if TEA enabled**, delegate the
   story-risk classification to `ab-fast` to pick per-story TEA skills. Record the decisions in state.

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
Always produce a single report (even on hard-stop). **Append it** as a new timestamped section
(`## Report — <ISO timestamp>`) to `{project-root}/_bmad-output/auto-bmad/reports/{key}.md`,
**preserving any existing sections**, and print the same content to the user. Never overwrite on
resume — earlier runs' reports carry context we must not lose. The ONLY time you overwrite the
file is a deliberate full re-run of an already-`done` story, and only after explicit user
confirmation. The report contains:
- **Story:** key, final status, branch.
- **Overrides:** any invocation overrides applied this run (phase window, skips, caps) — omit if none.
- **PR:** link (or "local branch only — no GitHub remote/`gh`"), draft? why.
- **CI:** link to the CI run the PR/push triggered + its status, if the repo has workflows (omit if none).
- **TEA:** which skills ran and outcomes; epic gate decision if last story.
- **Open questions** surfaced by any step.
- **Deferred work** (anything intentionally postponed).
- **⚠️ Needs human:** blockers / manual actions required before this can be considered done.
- **Next:** the next story `story_plan.py` would pick (preview only — do NOT start it).

## Hard-stop conditions (surface clearly, then report & exit)
Not a BMAD project; missing required skill; no `sprint-status.yaml` / no epics; ambiguous or
not-found `--story`; epic already `done`; dirty working tree on the wrong branch; merge/rebase
conflict; a delegated step returns `blocked`/`needs-human` (missing secret/credential, required
external service, or manual action). Never push past a hard-stop — report and let the human act.

(Note: code review NOT converging within `max_iterations` is NOT a silent hard-stop — Phase 7
**asks the user** what to do.)
