# Per-story pipeline

The orchestrator runs these phases **in order** for a single story. The story primitive is `bmad-build-auto`, invoked twice per story — a **plan run** (Phase 3, `Halt after planning.` ⇒ spec at `ready-for-dev`) and a **build run** (Phase 5, `/bmad-build-auto <spec_path>` ⇒ implement → review → finalize → `done`; build-auto commits its own diff and never pushes) — plus a **follow-up review pass** (Phase 7, a fresh build-auto review pass on the `done` spec at a *different* model). Each phase runs this sequence:
1. Check its condition.
2. Delegate the named **`delegation.md` entry** (the hyphenated name in **bold backticks** below, e.g. **`build-run`**) to the profile `phase_profiles` assigns to the phase — or run the orchestrator-direct action.
   - Each phase also names its `phase_profiles` **key** — the underscored form, e.g. `→ build`. Resolve key → profile → model (+ effort where the host honors it) via config; the mapping lives only in config — **never** hardcode a profile name here.
   - `delegation.md` owns the exact `/bmad-*` command + prompt (assembled there: role line + body + shared tail).
   - Spawn it for the current host/tier per `delegation-runtime.md` — check `delegation.cli_phases` first (the phase key present ⇒ the external-CLI route of `cli-route.md`; still delegation).
3. Read the result.
   - `blocked` / `needs-human` → stop and report (outcome vocabulary below).
   - Otherwise → `python3 {skill-root}/scripts/state_update.py phase-done --state-file <state> --phase N --json -` with the folded `set` patch (`state-and-resume.md`).
4. **Commit the phase's artifacts + the state write in ONE commit** (`git-and-pr.md` → "Commits").

**Which phases enter `completed_phases`:**
- A phase whose own gates made it a no-op → still enters `completed_phases` (recorded as skipped).
- A phase excluded by an override window → does **not** enter (`overrides.md`).

**Commits:** each phase gives its `Commit:` **subject only** (normative here); the required body, the folded state write and the no-state-only-commit rule are `git-and-pr.md` → "Commits" / "Message body".

**Timing:** the script owns the clock math — never hand-rolled `date` arithmetic (`state-and-resume.md` → timing fields).
- Bracket each delegated phase: `python3 {skill-root}/scripts/state_update.py timing-start --state-file <state>` just before delegating (for a build-auto phase: **before** the clean-tree gate, never after it); `… timing-pause …` when it returns — just before the state write + commit.
- **Don't count time spent waiting on the user.** Around every `AskUserQuestion` (spec-approval halt, review halt, gate ask, merge prompt) invert the bracket — `timing-pause` before the prompt, `timing-start` after — so the wait lands on human/idle, not active. On a resume that re-opens a halt (spec-approval halt, Phase 7 `hitl_halt: stopped` re-open) skip the `timing-pause` — the prior session already paused and the anchor is null (`timing-pause` would exit 1) — and `timing-start` after the prompt as usual.
- `dropped_anchor: true` from `timing-start` = a prior session crashed mid-bracket; the dangling interval is discarded conservatively — expected on resume, not an error.

**Exception — Phase 0:** the state file does not exist until Phase 1's `init`, and every `state_update.py` subcommand except `init` (and `report-section --allow-missing-state`, SKILL.md Step 3's pre-init report fallback) refuses a missing file. Phase 0 is never bracketed and never writes state; every Phase-0 "record …" decision is **carried into Phase 1's `init --json` payload**.

**Clean-tree gate** — before EVERY build-auto invocation (the Phase 3 plan run, the Phase 5 build run, every Phase 7 follow-up / re-review pass): `git-and-pr.md` → "Clean-tree gate". Read it before the first invocation of the run.

**`commits[]`:** `git-and-pr.md` → "`commits[]`" (the sha-lag append + the `head_before` capture around every build-auto invocation). Append via a `set` patch `{"_append": {"commits": [...]}}`.

**Git/PR work is orchestrator-owned, not delegated** — `git-and-pr.md` → "Ownership". The git-only phases (0 preflight, 1 branch, 9 finalize) carry no `phase_profiles` key; only their non-git parts (Phase 0's TEA triage) are delegated.

**Outcome vocabulary:** `blocked` (a skill/tool could not proceed) and `needs-human` (a human must act) both stop the pipeline → report. A build-auto `status: blocked` (a missing secret/credential, a required external service, a manual action, `no subagents`, non-convergence) is reported as **`needs-human`** with the blocking condition verbatim plus the recovery text at the end of this file ("Recovery after a build-auto `blocked`").

**Blocked handling** (Phases 3, 5, 7) — the shared procedure; each phase adds only its own delta:
1. `blocking_condition` precedence: the spec's `auto_run_result.blocking_condition` → else the condition the delegate reported in its Status → else `(not stated)`.
2. Commit every pending file as `chore(story-{e}-{s}): <plan|build|review> blocked (<blocking condition | reason>)` — in the **subject** take the condition's **first line** only, trimmed to keep the subject ≤ ~72 chars (foreign text is unbounded and would break it); the full condition goes in the commit body and in state.
3. State `set` `build{status: blocked, blocking_condition}` — the phase does **NOT** enter `completed_phases`.
4. Outcome **`needs-human`** with the blocking condition verbatim + the recovery text; stop.
5. Never leave the run's leftover file (a plan-time result file, an intent-gap patch) untracked for the next clean-tree gate to sweep under a `pipeline state` subject.

**No-code rule + untrusted inputs:** `SKILL.md` → The one rule. Probes use `find`/`test`/Python, never a bare glob.

Placeholders (incl. `<state>`): the `delegation.md` glossary.

---

## Phase 0 — Preflight & triage  *(orchestrator; TEA triage: `tea_triage`)*
Runs during SKILL Step 1 (before any commit). No state, no commit; every decision rides in Phase 1's `init --json`. **The step order below is normative** — every step's inputs come only from earlier steps.

**Precondition:** the `--central-config-only` call + the runtime-config locate — `SKILL.md` → On activation / Step 0.

0. **Overrides:** normalize per `overrides.md`, echo the interpretation. `dry_run`: the read-only window is steps 1–7 and 9 below (step 8's `tea-triage` does not run) and the stop is before Phase 1 — semantics `overrides.md`. Epic mode: the same rule at E0 (`epic-pipeline.md`).
1. **Host/tier:** resolve per `delegation-runtime.md` → "Resolving host & mode" (config + detection); resolve any `delegation.cli_phases` route with `cli_delegate.py` (`cli-route.md`; `ok:false` ⇒ hard-stop with its `errors`).
2. **Target/resume pre-read** (no `uv`, no git — only the state dir and `sprint-status.yaml`):
   - `--story <arg>` (accepts `E-S`, `E.S`, `E-Sx`, a full key, or a slug fragment) ⇒ `python3 {skill-root}/scripts/story_plan.py --resolve <arg> --sprint-status <impl>/sprint-status.yaml --planning-dir <planning>` (`hard_stop` ⇒ surface `hard_stop_reason` — not found / ambiguous with `candidates` — and stop); then `python3 {skill-root}/scripts/state_plan.py --state-dir <output_folder>/auto-bmad/state --story-key {key}` ⇒ `resume`, `status`, `branch`.
   - no arg ⇒ `state_plan.py --state-dir <output_folder>/auto-bmad/state` — `resume: true` ⇒ target = its `target` (+ that record's `branch`; note `extra_in_flight`); else the target is picked at step 5.
   - **Epic-ownership guard:** `state_plan.py --state-dir … --scope epic` — an in-flight anchor whose `epic_num` matches the target's epic ⇒ hard-stop → `/auto-bmad epic --epic {e}`.
3. **ONE full preflight call:**
   ```
   python3 {skill-root}/scripts/preflight.py --project-root <project_root> --host <host> --tier <tier> \
     --require-skills <csv> --skills-dirs <csv> [--tea-enabled — when tea.enabled] [--cross-model-tool <code_review.cross_model_layer> — when non-empty] \
     [--cli-phases <keys of delegation.cli_phases>] [--expected-branch <branch — only when step 2 found a resume target>]
   ```
   - `--require-skills`: core `bmad-build-auto,bmad-sprint-planning,bmad-retrospective` (always); when `tea.enabled` and not `skip tea`, add `bmad-testarch-test-design,bmad-testarch-atdd,bmad-testarch-automate,bmad-testarch-trace,bmad-testarch-nfr,bmad-testarch-test-review`. Never require any v6-shims skill.
   - `--skills-dirs` per host: claude-code `<root>/.claude/skills`; codex `<root>/.agents/skills,<root>/.codex/skills,~/.codex/skills`; opencode `<root>/.opencode/skills,~/.config/opencode/skills,<root>/.claude/skills,<root>/.agents/skills`; other ⇒ all of the above.
   - Obey `hard_stop` / `hard_stop_reasons`: python, uv, Python 3.11 with downloads disabled, central TOML, `nesting` (print `nesting.fix` verbatim), `cross_model` binary, `skills.missing`, git (`git-and-pr.md` → "Mode detection").
   - Surface `warnings` (`AGENTS.md` block, legacy `_bmad/<bmm|core>/config.yaml`, `_bmad/tea/config.yaml`, uv/nesting warns) in the Phase 0 echo and again in the report's Needs human list as optional follow-ups.
   - Keep `skills.sprint_plan_script` for step 5 and `git.{mode, current_branch}` for Phase 1; `<base_branch>` is always the runtime config's. Read the JSON's fields — never re-derive them in shell.
4. **Config-drift heal + review**, then **review-layers freshness** — the only provisioning check:
   - Reconcile `config.yaml` against the shipped assets — the `profiles`/`phase_profiles` blocks AND the constant-default setup keys (`delegation`/`tea`/`git`/`code_review`/`build`):
     ```
     python3 {skill-root}/scripts/config_plan.py --check --config <output_folder>/auto-bmad/config.yaml
     ```
     - `status: fresh` (exit 0) → continue.
     - `status: drift` (exit 1) splits by the **pause predicate** — any of `missing_profiles`, `missing_phase_profiles`, `missing_setup` non-empty (new config the heal will ADD).
       - **Reviewable drift** (predicate true) → **pre-run pause** (below), UNLESS `skip config-pause` is in effect. *Epic mode handles this once at E0 (`epic-pipeline.md`).*
       - **No reviewable drift** (only an older `profiles_source_version` and/or `manual_review` items) → **auto-apply** (`--apply`) to restamp; surface `manual_review` in the report; continue. No pause. (`manual_review` is never in the predicate; the fix for it is `reset-defaults`.)
     - **Pre-run pause** — the ONE deliberate Phase-0 halt, only on reviewable drift: `AskUserQuestion` showing the **drift report** (rendering: `config-commands.md` → "Drift report rendering"), read straight from the `--check` JSON — never read code. Options: **Apply defaults & continue** (re-run with `--apply`; print `Applied — config.yaml now matches v<module_version>; continuing.`) / **Stop — let me edit `config.yaml` first** (print the config path + the exact re-invoke command, note that the heal is **append-only so edits survive**, then stop — Phase 0 wrote no state, so this is a clean pre-run stop, not a resumable halt).
     - **The additive heal** (`--apply`) appends only MISSING keys — never overwriting a user value — and restamps `profiles_source_version`. Run it **before** the review-layers freshness check.
     - **Non-blocking live echo** — on the **auto-apply** paths only (version/`manual_review`-only drift, or `skip config-pause` bypass), when `--apply`'s `added_setup` is non-empty: lead line `config.yaml updated to match v<module_version>`; *Added N new setting(s) (defaults; behaviour unchanged)* — one `path = value` per `added_setup`; *Kept your M customisation(s)* — one `path = value  (default <default>)` per `kept_setup` (omit when empty); closer `→ continuing pipeline…`. Never an `AskUserQuestion` on these paths; show nothing when `added_setup` is empty. Surfacing is preflight-only (the report template has no config-heal heading).
   - **Review-layers freshness:** `python3 {skill-root}/scripts/build_auto_custom.py --check --project-root <project_root> --config <output_folder>/auto-bmad/config.yaml` — `needs_apply` (exit 1: `stale`/`missing`) ⇒ re-run with `--apply` and echo `⚠ review-layers TOML was stale — regenerated _bmad/custom/bmad-build-auto.toml` (swept into the Phase 1 init commit — or, on a resume, the next clean-tree gate / the Phase 9 report commit); `errors` (exit 2 — invalid TOML, one of our layer ids defined outside the managed region) ⇒ hard-stop naming the file and ids. Never a human stop.
5. **Story pick** (only when step 2 produced no target — no `--story`, nothing in flight):
   ```
   uv run <sprint_plan_script> status --status-file <impl>/sprint-status.yaml --date "<now MM-DD-YYYY HH:MM>"
   ```
   (`<sprint_plan_script>` = `skills.sprint_plan_script`, step 3.) Parse:
   - `ok: false` ⇒ hard-stop with its `error`.
   - `all_done: true` (⇔ `recommendation` null) OR `recommendation.story_key` null ⇒ hard-stop `all stories are done — nothing for auto-bmad to run` (+ ` (retrospective for epic N is still optional: run /bmad-retrospective -H N)` when `recommendation.skill == bmad-retrospective` — N = the epic number in `recommendation.reason` (`epic-N-retrospective`; the recommendation carries no epic field)).
   - Else target = `recommendation.story_key` (auto-bmad ignores `recommendation.skill`).
   - Echo `risks`, `warnings`, `illegal`, `unrecognized` (warn: `sprint-status.yaml has illegal/unrecognized entries — run /bmad-sprint-planning validate`). Keep `open_action_items` for the plan carry-over (Phase 3) and the report.
   - Then `state_plan.py --state-dir … --story-key {key}` for the picked key (`status: done` ⇒ the `done` rule of `state-and-resume.md` → "Target selection": a caveated completion parked at `review` — print the report tail + PR link + the explicit next command, then stop).

   Then **always**: `python3 {skill-root}/scripts/story_plan.py --epic {e} --sprint-status <impl>/sprint-status.yaml --planning-dir <planning>` for the target's `is_first_in_epic`, `is_last_in_epic`, `epic_story_count`, `stories_after_in_epic`, `epic_status`, `retrospective_status`, `title`, `epic_title` (the `--resolve` output already carries the story fields; the `--epic` read is the single source in epic mode).
   - Per-story, its `hard_stop: true` with reason `epic {e} is marked done` is **informational** (exit 0; `epic_stories` and the story fields are still populated — a confirmed re-run is sanctioned); only an exit 1 (unreadable sprint-status) hard-stops here.
   - If `is_first_in_epic` and the pick above did not run this session (`--story`, or a resume that has not completed Phase 3), run `uv run <sprint_plan_script> status --status-file <impl>/sprint-status.yaml --date "<now …>"` once anyway, solely to keep `open_action_items` for the Phase 3 carry-over (ignore its `recommendation`; `ok: false` still hard-stops).
6. **Status-mismatch guard** (`state-and-resume.md` → "Target selection") when the target has no state file; a `status: done` state ⇒ the `done` rule there.
7. **Retro verdict gate** (per-story when `is_first_in_epic`; epic mode at E0): `python3 {skill-root}/scripts/story_plan.py --retro-verdict --impl-dir <impl> --epic {e-1}` — `found` and `verdict: rejected` ⇒ `AskUserQuestion` (not bracketed — no state file yet, per the Phase 0 exception): "Epic {e-1}'s retrospective verdict is **rejected** (`<doc>`). Start epic {e} anyway?" — **Proceed** / **Stop — resolve epic {e-1} first**. Suppressed by `skip retro-gate`. (Skip when `e-1 < 1`.) Skip on a resume (step 2 returned `resume: true`).
8. **TEA triage** (only if `tea.enabled` and not `skip tea`): delegate **`tea-triage`** → `tea_triage`. Input = the epics document's entry for Story {e}.{s} (the spec does not exist yet; no re-triage later). Classify per `tea-policy.md` §2 and add `trace-advisory` per its §3 (`epic_story_count` / `stories_after_in_epic` from step 5); record `tea_risk`, `tea_selected`, `tea_rationale`. Not `tea.enabled` ⇒ `tea_selected: []`, `tea_risk: null`. On a resume with Phase 0 already in `completed_phases`, reuse the recorded `tea_risk`/`tea_selected`/`tea_rationale` — don't re-delegate.
9. **Story title** `{title}` = the `title` field of the step 2/5 `story_plan.py --resolve` / `--epic --planning-dir` read; `null` ⇒ fallback `{slug}` with `-` → space. Never grep the epics document.

No commit, no state — carry `story_suffix`, `overrides`, `tea_risk`, `tea_selected`, `tea_rationale`, `epic_story_count`, `stories_after_in_epic`, `is_first_in_epic`, `is_last_in_epic`, `git_mode`, `base_branch` into Phase 1's `init --json`. Hard-stop and not-silent-ask lists: `SKILL.md`.

## Phase 1 — Branch  *(orchestrator)*
- Ensure we are NOT on the base branch. `git switch -c {git.branch_prefix}{e}-{s}-{slug} <base_branch>`; on resume `git switch <branch>` if it exists (`git-and-pr.md` → "Branching").
- `python3 {skill-root}/scripts/state_update.py init --state-file <state> --json -` with every Phase-0 decision (list above). It refuses (exit 1) if the file exists — a **resume** never re-inits, so `started_at`/`active_seconds` span all sessions.
- When Phase 2 will not run, write Phase 3's `timing-start` before the commit (fold-forward rule).
- Commit: `chore(story-{e}-{s}): start auto-bmad pipeline` (may also carry a Phase 0 auto-applied `_bmad/custom/bmad-build-auto.toml` / healed `config.yaml`).

## Phase 2 — Epic-start setup  *(conditional; one sub-step)*  → `tea_epic`
- Only if `is_first_in_epic` AND `tea.enabled` (and not `skip tea`): delegate **`testarch-test-design (epic level)`** for epic `{e}`.
- Commit: `test(epic-{e}): epic-level test design` (folds Phase 3's `timing-start`).
- Gate false ⇒ no-op, recorded in `completed_phases`.

## Phase 3 — Plan  → `build`
Sprint-status timing: the entry goes to `ready-for-dev` at the END of Phase 3; `in-progress` is Phase 5's FIRST action — which the fold-forward rule may execute inside the Phase 3 `plan spec` commit when Phase 5 follows immediately (step 5). The plan halt itself never flips to `in-progress`.
1. **Clean-tree gate** (header).
2. **Route by state/spec (resume matrix):**

   | state `spec_path` | spec status (`story_plan.py --spec <spec_path>`) | action |
   |---|---|---|
   | null (fresh) | — | first `python3 {skill-root}/scripts/story_plan.py --find-spec --impl-dir <impl> --story-key {key} --sprint-status <impl>/sprint-status.yaml` (a spec may pre-exist from a bare `/bmad-build-auto` run): `found` ⇒ `set spec_path` and route by ITS status per the rows below (`ready-for-dev` ⇒ adopt, no plan delegate; `draft` ⇒ draft-spec plan run; `blocked` ⇒ needs-human; further-advanced ⇒ the hard-stop row); `ambiguous: true` ⇒ hard-stop listing `candidates`; `found: false` ⇒ delegate **`build-plan`** (fresh intent) |
   | set | `draft` | delegate **`build-plan`** (draft-spec variant — `/bmad-build-auto <spec_path>` + `Halt after planning.`; build-auto resumes planning with the preserved intent contract) |
   | set | `ready-for-dev` | plan already done (crash after the halt) — skip the delegate, continue at step 3 |
   | set | `blocked` | `needs-human` (recovery text — set the spec back to `draft`) |
   | set | `in-progress` / `in-review` / `done` | hard-stop `spec <path> already advanced to <status> outside auto-bmad — resume with \`/auto-bmad --story {key} start at phase 5\` (in-progress / in-review) or 7 (done)` |

   Fresh-intent text (verbatim except placeholders):
   ```
   Story {e}.{s} "{title}" (sprint-status key `{key}`, epic {e}). Branch `{branch}` is the intended branch for this work. Halt after planning.
   ```
   plus `{carry_over_block}` when it applies (per-story: `is_first_in_epic` and epic {e-1} has open action items in `sprint_plan.py status` (read at Phase 0 step 5) → `open_action_items` filtered `epic == e-1`; epic mode: every story). Capture `head_before` before the delegate (header rule; the plan run commits nothing). The delegate returns the HALT status; then:
3. **Locate the spec after the halt:** `python3 {skill-root}/scripts/story_plan.py --find-spec --impl-dir <impl> --story-key {key} --sprint-status <impl>/sprint-status.yaml`
   - `ambiguous: true` ⇒ **hard-stop** listing `candidates`.
   - `found` ⇒ record `spec_path` (`state_update.py set`); `status` must be `ready-for-dev` (`blocked` ⇒ needs-human, recovery text).
   - `found: false` (build-auto HALTed `blocked` before writing a spec) ⇒ **Blocked handling** (header) with subject verb `plan`. Phase-3 deltas:
     - the HALT protocol wrote an untracked `<impl>/bmad-build-auto-result-<slug-or-timestamp>.md` — that is the leftover file the `plan blocked` commit must carry;
     - record its path (from the delegate's Status, else a filename-only `find <impl> -name 'bmad-build-auto-result-*.md' -newer <state>`) in `blockers[]` and the report; when a later plan succeeds, remove that entry from `blockers[]` before the `phase-done` write (`state-and-resume.md` → "Blockers clear on resume");
     - a re-run re-enters Phase 3 with a fresh intent — the result file is inert.
4. **Sprint flip:** `python3 {skill-root}/scripts/story_plan.py --mark-status {key} --to ready-for-dev --sprint-status <impl>/sprint-status.yaml` (idempotent; stamps `last_updated`). Add `--allow-regress` only on the sanctioned regress paths (`state-and-resume.md`); any other `refusing to regress` exit is a hard-stop — surface the message.
5. **State + commit:** `phase-done --phase 3` with `spec_path`, `build.status: ready-for-dev`, `spec_approved: <true unless approval is required>`, `commits[]` (sha-lag). Commit **`docs(story-{e}-{s}): plan spec`** — the untracked spec, any `epic-{e}-context.md` build-auto compiled, sprint-status, state. If neither Phase 4 nor the approval halt will run, write Phase 5's `timing-start` + `in-progress` flip (Phase 5 step 1) before this commit (fold-forward rule).
6. **Spec-approval halt** (only when `build.spec_approval: true` or override `approve spec`; never in epic mode): `timing-pause`; `AskUserQuestion`: "Spec ready: `<spec_path>` (`ready-for-dev`). Approve it for implementation?" — **Approve — continue** / **Stop — I'll edit the spec first**.
   - Approve ⇒ `set spec_approved: true`, `timing-start` for Phase 4/5.
   - Stop ⇒ report `(halted — spec approval pending)`, outcome `stopped`. Re-run `/auto-bmad --story {key}` to resume: the resume re-opens this halt; if the tree is then dirty on the story branch **outside auto-bmad's own writes** (exclusion set: Phase 7 step 3), first stage everything and commit the human's edits git-only as `docs(story-{e}-{s}): spec edits (human)`; own-writes-only dirt just folds into the next commit / clean-tree gate.
   - Resume rule: `3 ∈ completed_phases` and `spec_approved: false` and approval required ⇒ re-open the halt before Phase 4/5.

## Phase 4 — Pre-dev TEA  *(only if `tea.enabled` AND `atdd ∈ tea_selected`)*  → `tea_per_story`
- Delegate **`testarch-atdd`** with `<spec_path>`.
- Commit: `test(story-{e}-{s}): ATDD acceptance scaffolds (red)` — MANDATORY before Phase 5 (build-auto needs a clean tree); folds Phase 5's `in-progress` flip + `timing-start`.
- The checklist lands at `atdd-checklist-<spec basename>.md` (TEA derives `story_key` from the filename — cosmetic).

## Phase 5 — Build  → `build`
1. **Sprint flip + clean-tree gate:** `python3 {skill-root}/scripts/story_plan.py --mark-status {key} --to in-progress --sprint-status <impl>/sprint-status.yaml` (also lifts `epic-{e}` `backlog` → `in-progress`) — folded per the fold-forward rule; then the clean-tree gate (`timing-start` already written; subject `chore(story-{e}-{s}): mark in-progress` if a commit is needed). Pass `--allow-regress` only on the sanctioned regress paths (`state-and-resume.md`); any other `refusing to regress` exit is a hard-stop.
2. **Delegate:** capture `head_before = git rev-parse HEAD`; delegate **`build-run`** (`/bmad-build-auto <spec_path>`) → `build` (or `cli_phases.build`).
3. **Read the result:** `python3 {skill-root}/scripts/story_plan.py --spec <spec_path>` ⇒ the `build` block; also `git status --porcelain`. **The frontmatter `status` is authoritative**; `auto_run_result.{status, blocking_condition}` are optional corroboration.
   - `status == done`: dirty tree ⇒ warning `build-auto left N file(s) uncommitted` (swept into the mark-review commit); `commits[] += git log --format=%h <head_before>..HEAD`. Then `python3 {skill-root}/scripts/story_plan.py --mark-status {key} --to review --sprint-status <impl>/sprint-status.yaml`; state `phase-done --phase 5` with `build{status: done, blocking_condition: null, followup_review_recommended, review_loop_iteration, deferred_count, warnings}` (all from `--spec`); commit **`chore(story-{e}-{s}): mark review`** (sprint flip + state [+ stragglers]) — body: build-auto's summary line, patched/deferred counts, `followup_review_recommended`, warnings. Folds Phase 7's `timing-start` when Phase 6 will not run.
   - `status == blocked` (or the delegate reports `needs-human`/`blocked` without a HALT, e.g. a render failure) ⇒ **Blocked handling** (header) with subject verb `build`.
   - any other status (`in-progress` / `in-review` — the run ended without a HALT) ⇒ as blocked with `blocking_condition: "no terminal HALT (status <x>)"` and the hint to re-run (build-auto resumes at implement/review from the spec status).
4. **No orchestrator feat commit** — build-auto authors the code commits. The PR title stays `feat(story-{e}-{s}): <title>`.

## Phase 6 — Post-dev TEA  *(only if `tea.enabled` AND `automate ∈ tea_selected`)*  → `tea_per_story`
- Delegate **`testarch-automate`** with `<spec_path>`.
- Commit: `test(story-{e}-{s}): expand automated coverage` (folds Phase 7's `timing-start` when Phase 7 will run).

## Phase 7 — Follow-up review  → `followup_review`  *(+ HITL halt + tail)*
**Gate** (decidable right after Phase 5): run a pass iff NOT `skip code-review` AND (`code_review.followup == always` OR (`followup == recommended` AND `build.followup_review_recommended == true`)). `followup: never` ⇒ no pass. `skip code-review` (incl. a phase-7 skip normalized to it, `overrides.md`) ⇒ no pass and `review_unverified: true`.
**Entry at Phase 7 without a Phase 5 result** (`5 ∉ completed_phases`, `build.status` null — the guard's `review` ⇒ Phase 7 route or a `start_phase: 7` override): first seed `build.*` from `python3 {skill-root}/scripts/story_plan.py --spec <spec_path>` (`set` `build{status, blocking_condition: null, followup_review_recommended, review_loop_iteration, deferred_count, warnings}`), then run ONE pass **regardless of the recommendation gate** — that is what entering at the review means (mirrors the epic adopt path); `skip code-review` still wins.

1. **Pass** (each pass = `timing-start` → clean-tree gate → `head_before = git rev-parse HEAD` → delegate **`followup-review`** (`/bmad-build-auto <spec_path>` on the `done` spec) → `python3 {skill-root}/scripts/story_plan.py --spec <spec_path>` → `commits[] += git log --format=%h <head_before>..HEAD` → `followup_passes += 1`):
   - `done` ⇒ refresh `build.followup_review_recommended`, `build.review_loop_iteration`, `build.deferred_count`, `build.warnings` (state) and keep `last_review_pass` (the `--spec` JSON's last `## Review Triage Log` entry — `patch` / `bad_spec` / `defer` / `reject`) in session memory for the halt/report — it is not a state field.
   - `blocked` ⇒ **Blocked handling** (header) with subject verb `review`. Phase-7 delta: an `intent gap` HALT reverts the code and leaves an untracked patch file in `<impl>` — that is the leftover the `review blocked` commit must carry.
   - build-auto commits its own patches; the orchestrator commits only state (folded into the next commit, or via the clean-tree gate before another pass).
   - A CLI-routed pass (`cli_phases.followup_review`) uses a distinct `--label` per pass (`cli-route.md`).
2. **`review_unverified`** (draft-predicate clause 2) := true iff any of: `skip code-review`; OR the spec's `followup_review_recommended` is still `true` after Phase 7's last pass (incl. `followup: never`, where the build's own recommendation was never acted on). Written on the Phase 7 folded state write; the epic anchor aggregates it (E5h).
3. **HITL halt** (per-story mode only; epic mode ⇒ `hitl_halt: "auto-continued (epic — no halt)"`, no ask):
   - **Skip** iff no pass ran in this phase AND `review_unverified` is false ⇒ `hitl_halt: "skipped (clean)"`; go to the tail.
   - Else `timing-pause`, then `AskUserQuestion` (≤ 4 options), summarizing: passes run this phase, `last_review_pass` counts (patch / bad_spec / defer / reject), whether the spec still says `followup_review_recommended`, and `review_unverified`; recommend an external review of the branch while paused:
     - **Run another review pass** — loop back to step 1 (unbounded, human-driven; each pass is a fresh build-auto review at `followup_review`).
     - **Continue** — the external-change check below.
     - **Continue — ship as ready (ignore review caveats)** [shown only when `review_unverified` is true] — sets `overrides.no_pr_draft: true` (state + report), `hitl_halt: continued`; then the same external-change check.
     - **Stop the pipeline now** — `hitl_halt: stopped`; report `(halted — stopped at review halt)`; outcome `stopped`; commits stay on the branch, nothing pushed, no PR. On the next `/auto-bmad --story {key}` the resume RE-OPENS this halt (`state-and-resume.md`); choosing Continue then runs the external-change check.
   - **Own-writes exclusion set** (normative definition): auto-bmad's own files never count as an external change — `<output_folder>/auto-bmad/` (state, reports, config) and `<project_root>/_bmad/custom/bmad-build-auto.toml`; on a resume the halt's state write and the SKILL Step 3 fallback report are dirty by design.
   - **On Continue — the external-change check** (git-only; the orchestrator never reads the code):
     - **Changed?** := `git status --porcelain -- . ':(exclude)<output_folder>/auto-bmad' ':(exclude)<project_root>/_bmad/custom/bmad-build-auto.toml'` non-empty, OR HEAD moved (`git rev-parse HEAD` ≠ the HEAD when the halt opened this session).
       - On a halt re-opened after `stopped`, HEAD moved := `git log --format=%h --since=<state updated_at, read BEFORE the re-open reset write> HEAD -- . ':(exclude)<output_folder>/auto-bmad' ':(exclude)<project_root>/_bmad/custom/bmad-build-auto.toml'` non-empty (the human's own commits while stopped).
     - **Nothing changed** ⇒ just continue (own-writes dirt folds into the tail commit).
     - **Changed** ⇒ stage everything and commit as `fix(story-{e}-{s}): external review changes`, then run ONE re-review pass (same mechanism as step 1, same profile) and read the new `last_review_pass`.
     - **Meaningful** := `patch > 0` OR `bad_spec > 0` OR the spec's `followup_review_recommended` is true ⇒ re-ask ONCE (same options; a second Continue does not re-review again this run); else continue.
   - `hitl_halt: continued`. `timing-start` after each prompt. Phase 7 enters `completed_phases` only after the halt resolves (a skipped halt counts as resolved) **and** the tail below.
4. **Tail** (per-story and epic; resume-safe):
   a. **Trace advisory** (only if `trace-advisory ∈ tea_selected` and not `skip trace-advisory` — `skip tea` ⇒ `tea_selected: []`, so no advisory; skip if `story_trace` is already non-null): delegate **`testarch-trace (story advisory)`** → `tea_per_story` with `<spec_path>` (`allow_gate: false`). Record `story_trace: {verdict, uncovered: [...], ran: true}` (verdict delegate-derived). Advisory only — no ask, no remediation, no draft forcing, no `blockers[]` entry; surface uncovered ACs in the report's **TEA** line and the PR body.
   b. **Deferred harvest:** `python3 {skill-root}/scripts/deferred_ledger.py harvest --ledger <impl>/deferred-work.md --spec <spec_path> --story-key {key}` (idempotent by (spec basename, summary); no-op when `deferred_count == 0`). Read `harvested` / `skipped_existing` for the report's **Deferred work** line.
   c. **Commit + state:** `phase-done --phase 7` (`review_unverified`, `hitl_halt`, `followup_passes`, `build.*`, `story_trace`, `commits[]`). Commit `test(story-{e}-{s}): trace coverage advisory` when the advisory ran (also carries the harvest + state); else, if the harvest changed the ledger, `docs(story-{e}-{s}): harvest deferred work` (state folded); else the Phase 7 state write folds into the next commit (Phase 8 docs / Phase 9 report).

## Phase 8 — Epic end  *(only if `is_last_in_epic`)*
Six sub-steps with markers `phase8_steps.{trace_gate, nfr, test_review, reconcile, archive, retro}`.
- Each marker records `done` in its folded state write when the sub-step ran OR when its gate was false (`trace_gate` also `waived`/`failed`).
- Resume enters at the **first null marker** — except `trace_gate: failed`, a parked verdict, not a resolved one: a re-run re-opens step 1 (re-delegate **`testarch-trace (epic gate)`** and re-apply its verdict handling under the same `gate_iterations` cap; a non-`FAIL` verdict or a Waive removes the earlier FAIL entry from `blockers[]` — `set blockers: [<list without it>]` — and re-derives `gate_decision`).
- Phase 8 joins `completed_phases` only once all six markers resolve.
- ONE commit at the end: **`docs(epic-{e}): gate, deferred-work reconcile + archive, retrospective`** (carries the pre-retro flip); trace-gate remediation commits separately as it runs (step 1).
1. **TEA gates** (only if `tea.enabled` and not `skip tea`; else mark `trace_gate`/`nfr`/`test_review` `done`).
   - Delegate **`testarch-trace (epic gate)`** → `tea_epic` (blocking; `gate_type: epic`, `allow_gate: true`), then **`testarch-nfr (epic gate)`** + **`testarch-test-review (epic gate)`** → `tea_epic_audit` (advisory; `{epic_test_files}` is the git-only per-mode list built per `delegation.md` — an empty list with no suite fallback ⇒ mark `test_review: done` and report, mode-aware).
   - Verdict, rationale, uncovered list and the `gate-decision.json` path come from the delegate's structured result (state `gate_decision` + session memory for the report/PR body) — the orchestrator never opens a TEA artifact.
   - Handle the **trace** verdict before nfr/test-review:
     - `PASS` → continue.
     - `CONCERNS` → advisory: continue, record it, surface it in the report + PR body (no halt, no draft).
     - `NOT_EVALUATED` (the skill reports its gate as not eligible) → as CONCERNS: record `gate_decision: NOT_EVALUATED` + the skill's rationale, surface it in the report + PR body (no ask, no draft, no remediation loop).
     - `WAIVED` (from the skill) → continue; ships as a **draft** (draft-predicate clause 3).
   - `FAIL` → **ASK** (`AskUserQuestion`, bracketed): summarize the uncovered requirements/ACs, then:
     - **Remediate & re-gate** *(recommended; offered only while `gate_iterations < tea.gate_max_iterations`, default 2)* — delegate **`testarch-automate`** at epic scope → `tea_epic` targeting the reported gaps; `gate_iterations += 1`; commit `test(epic-{e}): close trace coverage gaps (gate iter {i})`; re-run **`testarch-trace (epic gate)`** and re-apply this handling. If the gaps are scope/spec drift rather than missing tests, tell the user `/bmad-correct-course` is the right heavier step — never auto-run it.
     - **Waive & continue** — `gate_decision: WAIVED`, `trace_gate: waived`; record the rationale + uncovered items in `deferred_work`/`open_questions`; Phase 9 opens a **draft** PR with the waiver + gaps in the body; if an earlier Stop recorded the `epic {e} trace gate FAILED — …` entry, remove it from `blockers[]` (`set blockers: [<list without it>]`) — the waiver replaces the block.
     - **Stop now** — keep `gate_decision: FAIL`, `trace_gate: failed`; add a `blockers[]` entry (`epic {e} trace gate FAILED — {n} requirements lack test coverage`; removed when a re-run gate returns non-`FAIL` — header rule / `state-and-resume.md` → "Blockers clear on resume"); report the gaps as `needs-human` with the way forward: close the coverage gaps, then re-run `/auto-bmad --story {key}` — the gate re-runs (header); skip the remaining phases (commits stay on the branch, nothing pushed).
   - Any other verdict, or none in the delegate's result ⇒ handle exactly as `FAIL` (same ASK, same cap) with rationale `unrecognised trace verdict: <value | none>`.
   - Cap reached and still `FAIL` ⇒ re-ask with Waive / Stop only. Run nfr + test-review on every path except **Stop**.
2. **Reconcile** *(delegated — `deferred_reconcile`; BEFORE the archive)*: `python3 {skill-root}/scripts/deferred_ledger.py plan --ledger <impl>/deferred-work.md`. Skip (`reconcile: done`) when the ledger is absent/empty or **every** entry's `marker_hint == resolved`; else delegate **`deferred-reconcile`** — it verifies each unmarked/partial entry against the code and marks only what is unambiguously fully resolved. Capture the count marked + each item's one-line evidence for the report's **Deferred work** field (`deferred_archived_note`, with step 3's archive line). The orchestrator never reads the code or the ledger here.
3. **Archive** *(orchestrator-direct)*:
   - Re-run `deferred_ledger.py plan --ledger <impl>/deferred-work.md` (step 2 changed the sha).
   - Judge each entry on its own `text` (`marker_hint` is a heuristic aid, never the decision):
     - **move only** a bullet that clearly states ALL of its deferred work is done (a leading `✅`, `RESOLVED`, "resolved in …", "closed", "addressed in …");
     - **keep** any entry with an open remainder ("X portion done; Y owned by story Z"), any unmarked entry, and anything uncertain — the entry must vouch for itself.
   - Then `python3 {skill-root}/scripts/deferred_ledger.py archive --ledger <impl>/deferred-work.md --archive <impl>/deferred-work-resolved.md --ids <move ids> --expect-sha <ledger_sha256>` (a stale sha / unknown id exits 1 with no writes — re-plan and re-judge; skip `archive` when the move set is empty; heading-less bmad-build entries archive under the script's synthetic heading).
   - Record `moved` in state (`deferred_work_archived`) and the report; `archive: done`.
4. **Pre-retro BMAD-status flip** (skipped on `skip retrospective`) — before the retro, so the headless retro does not judge the epic unfinished: `python3 {skill-root}/scripts/state_plan.py --state-dir <output_folder>/auto-bmad/state --story-key {key} --finalize` WITHOUT `--ci-status`; `flip_bmad_status: true` (clauses 1–3 clean) ⇒ `python3 {skill-root}/scripts/story_plan.py --mark-status {key} --to done --sprint-status <impl>/sprint-status.yaml` now (lifts `epic-{e}` to `done` when every story is `done`) and `set bmad_status_flipped_at: 8`; else leave `review`. A later CI failure (Phase 9 clause 4) does NOT regress the entry — the caveat lives in the PR draft state + report ("BMAD status flipped before the retrospective; CI later failed").
5. **Retrospective** (`retrospective`; skip on `skip retrospective` ⇒ `retro: done`): delegate **`retrospective`** (`/bmad-retrospective -H {e}`); then `python3 {skill-root}/scripts/story_plan.py --retro-verdict --impl-dir <impl> --epic {e}` ⇒ `retro.doc`, `retro.verdict`; re-run `uv run <sprint_plan_script> status …` ⇒ `retro.open_action_items` = count of `open_action_items` with `epic == {e}` (the list feeds the report + PR body). `verdict: rejected` ⇒ report / PR body / merge-prompt line `⚠️ Retrospective verdict: rejected — <doc>`; it does NOT enter the draft predicate; it gates the NEXT epic's start (Phase 0 step 7). Marker `retro: done`.
6. **Report advice line** (rendered in `next`): `Project context: run /bmad-project-context refresh (recommended after an epic).`

## Phase 9 — Finalize  *(orchestrator)*
1. **Ensure committed:** no dirty tree OTHER THAN auto-bmad's own writes — the own-writes exclusion set of Phase 7 step 3, unchanged (here it covers a pending Phase 7/8 folded state write, or a Phase 0 auto-applied heal / layers regen on a resume that entered at Phase 8/9); those fold into the report commit. Any other dirty file ⇒ hard-stop `unexpected uncommitted changes before finalize: <files>`.
2. **Report file before push** (so it ships in the PR):
   ```
   python3 {skill-root}/scripts/state_update.py report-section --report-file <output_folder>/auto-bmad/reports/{key}.md --state-file <state> --json -
   ```
   Payload keys: `state-and-resume.md` → "Section template" (tag + session-delta rules there too). Commit: `docs(story-{e}-{s}): pipeline report`.
3. **Mode `remote`:** push, PR (`gh pr create … [--draft]` per the pre-CI predicate — `state_plan.py --finalize` without `--ci-status`), CI wait (`ci_wait.py`), draft conversion — all per `git-and-pr.md` → "PR". Capture `pr_url`, `ci_run_url`, `ci_status`. **Mode `local`** (or a `skip pr` override): skip push/PR; leave the branch in place and say so in the chat report; no CI wait, no merge prompt.
4. **Draft predicate + flip:** `python3 {skill-root}/scripts/state_plan.py --state-dir <output_folder>/auto-bmad/state --story-key {key} --finalize [--ci-status passed|failed|timeout|none] [--no-pr-draft]` (the live post-wait `ci_status` when Phase 9 waited; `--no-pr-draft` when that override is active — it changes only `draft`, never `clean_completion`). `flip_bmad_status: true` AND `bmad_status_flipped_at` null ⇒ `python3 {skill-root}/scripts/story_plan.py --mark-status {key} --to done --sprint-status <impl>/sprint-status.yaml` (`bmad_status_flipped_at: 9`); caveated (`reasons` names the clauses) ⇒ leave as is (`review` — or `done` if the pre-retro flip already ran). Then ONE `set` patch: `status: done` (auto-stamps `completed_at`), `pr_url`, `ci_run_url`, `ci_status`, `branch`, `blockers`, `bmad_status_flipped_at`; commit `chore(story-{e}-{s}): finalize (mark done + BMAD status)`; push (mode `remote`).
5. **Merge prompt** — conditions, prompt, execution and the state fields it writes: `git-and-pr.md` → "Merging the PR".
6. **Hand back to SKILL Step 3** — it owns the chat-only lines.

---

## Recovery after a build-auto `blocked`  *(needs-human — report + chat, verbatim template)*
```
build-auto stopped with status `blocked` — blocking condition: <verbatim>.
Spec: <spec_path> (frontmatter status: blocked). What to do:
1. Fix the cause (see the spec's `## Auto Run Result` and, for `intent gap`, the saved patch it references).
2. Edit the spec's frontmatter `status:` to resume at the right step —
   `draft` (re-plan; only after a planning-time block), `in-progress` (re-implement), or `in-review` (re-run only the review).
3. Re-run `/auto-bmad --story {key}` — the pipeline resumes at the phase that was blocked and passes the same spec.
Special cases: `no subagents` ⇒ nested subagents are not enabled for this host (see the preflight fix text);
`missing previous-story continuity decision` ⇒ finish or resume the previous story of this epic first;
`finalization left repository dirty` ⇒ commit or discard the leftover files, then set the spec to `in-review`.
```
Epic mode: step 3 reads `Re-run /auto-bmad epic --epic {e}`.
Resume mapping when the human re-runs: Phase 5 (spec `ready-for-dev` / `in-progress` / `in-review`) and Phase 7 (spec `done`) re-invoke build-auto with the spec path; Phase 3 (spec `draft`) re-invokes the plan run. A plan-time block with no spec (`bmad-build-auto-result-*.md` only) re-enters Phase 3 with a fresh intent; the `Spec:` line then names that result file instead.
