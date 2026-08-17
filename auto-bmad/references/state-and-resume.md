# Config, state & resume

Everything auto-bmad persists lives under `{output_folder}/auto-bmad/` (`{output_folder}` = `core.output_folder` from the BMAD central TOML config — read only through `preflight.py --central-config-only`, never by hand). One section each below:
- `config.yaml` — project config, created on first run.
- `state/{key}.yaml` — one resumable state file per story (epic mode adds the anchor `state/epic/epic-{e}.yaml`).
- `reports/{key}.md` — per-story report log, appended each run (epic mode: one `reports/epic-{e}.md`).

`{key}` comes from the story source: sprint mode `{e}-{s}[a]-{slug}`, stories mode `spec-{spec_slug}-{id}` (epic anchor `spec-{spec_slug}`, epic report `reports/spec-{spec_slug}.md`). Everything below is written by the same scripts in both modes — the stories-mode deltas are marked inline, and the per-phase flow lives in `stories-mode.md`.

The interactive config commands that write this config — the first-run flow, `reset-defaults`, `config-check` — live in `config-commands.md`.

## config.yaml
```yaml
version: 1                          # schema version
profiles_source_version: "0.30.1"   # abm version whose assets/profiles.yaml seeded the profiles + phase_profiles blocks below;
                                    #   restamped by the Phase 0 additive heal or a full `reset-defaults`
delegation:                         # spawn mechanism — host/mode re-detected every run (stored values are inert)
  host: auto                        # auto | claude-code | codex | opencode | other
  mode: auto                        # auto (derive from host) | subagents | inline   (legacy custom-subagents reads as subagents)
  cli_phases: {}                    # OPT-IN per-phase external-CLI routing: <phase_profiles key> -> claude|codex|opencode; empty/absent
                                    #   => every phase uses its tier. Setup answer (heal-immune), hand-edited. Semantics:
                                    #   cli-route.md; examples: assets/config-defaults.yaml
tea:
  enabled: true                     # interviewed at first run (default yes iff bmad-testarch-* installed)
  framework_ci: prompt              # prompt | done | skip (resolved at first run)
  gate_max_iterations: 2            # Phase 8 trace-gate remediation cap (automate + re-trace) before only waive/stop (constant default)
  story_trace_advisory:             # per-story, non-blocking trace pass (constant defaults; rubric tea-policy.md §3)
    enabled: true                   # self-activating: dormant on short epics, fires only on long high-risk stories
    min_epic_stories: 6             # only runs in epics with >= this many stories
    skip_last_stories: 3            # also skip the epic's last N stories
git:
  mode: auto                        # auto -> detect | remote | local (Full setup; heal-immune)
  branch_prefix: "story/"           # constant default
  epic_branch_prefix: "epic/"       # epic mode's one branch, epic/{e}-{slug} (constant default)
  base_branch: main                 # detected once; never asked; never healed
  offer_merge: true                 # Phase 9: ask whether to merge a clean-completion PR (constant default)
  ci_wait_minutes: 30               # max wait for in-progress CI (only when offer_merge is on) (constant default)
code_review:
  followup: recommended             # recommended | always | never — Phase 7 follow-up bmad-build-auto review pass on the done spec at the
                                    #   followup_review profile: recommended => only when the spec says followup_review_recommended: true;
                                    #   always => every story; never => skip (constant default)
  security_layer: true              # write the auto-bmad-security review layer into _bmad/custom/bmad-build-auto.toml (constant default)
  cross_model_layer: codex          # codex | claude | opencode | "" — external CLI for the auto-bmad-cross-model layer; ENV-DETECTED
                                    #   at first run (first of codex, claude, opencode on PATH that is not the host, else "");
                                    #   absent key => ""; NOT in config-defaults.yaml (setup answer, heal-immune)
build:
  spec_approval: false              # opt-in per-story HITL halt between Phase 3 (plan) and Phase 4/5 (constant default; a run can also
                                    #   ask for it in its instructions; never in epic mode)
profiles:                           # copied VERBATIM (block style) from assets/profiles.yaml at first run — model/effort ONLY, no persona
  light:                            #   strings. Shown flow-style here for brevity:
    claude: {model: sonnet, effort: high}              # claude.model = the Agent tool's per-call model; claude.effort is used ONLY by the
                                                       #   cli_phases route / cross-model layer (`claude -p --effort`)
    codex: {model: gpt-5.6-luna, reasoning_effort: xhigh}   # both are per-call knobs of Codex's spawn_agent (and `codex exec`)
    opencode: {model: "", variant: ""}                 # BOTH used ONLY by the cli_phases route / cross-model layer (`opencode run -m/--variant`);
                                                       #   in-tool opencode subagents inherit the user's default model; ships BLANK (inherit)
  standard: {…}                     # same field set — shipped values + what each profile drives: assets/profiles.yaml
  critical: {…}                     # + any CUSTOM profile (any name, same field set) — phase_profiles may name shipped or custom profiles
phase_profiles: {…}                 # build, followup_review, security_layer, cross_model_layer, tea_triage, tea_per_story, tea_epic,
                                    #   tea_epic_audit, retrospective, deferred_reconcile — the SINGLE phase->profile binding
                                    #   (references name these keys, never raw profiles); git/PR work runs in the orchestrator
                                    #   directly — no delegate profile. delegation.cli_phases keys are exactly these keys
```
- **Retune paths** (write a pointer comment above the copied `profiles:` block naming both): edit the `profiles` / `phase_profiles` copy here, then `/auto-bmad reprovision` (re-syncs the review-layers TOML that bakes the `security_layer` / `cross_model_layer` models — see `config-commands.md`); discard retunes with `/auto-bmad reset-defaults`.
- **Absent-key orchestrator fallbacks** (must equal `assets/config-defaults.yaml`): `code_review.followup: recommended`, `code_review.security_layer: true`, `build.spec_approval: false`, `git.branch_prefix: "story/"`, `git.epic_branch_prefix: "epic/"`, `git.offer_merge: true`, `git.ci_wait_minutes: 30`, `tea.gate_max_iterations: 2`, `tea.story_trace_advisory.{enabled: true, min_epic_stories: 6, skip_last_stories: 3}`, `delegation.cli_phases: {}`. Plus `code_review.cross_model_layer: ""` — an env-detected setup answer the asset deliberately omits (documented only in its header + `config-commands.md` → First-run flow, step 0), so an absent key means the layer is off.
- **No config key for the story source.** Stories mode (a `bmad-spec` spec folder: `SPEC.md` + `stories.yaml` + `stories/{id}-*.md`) is chosen **per run** — the `--spec <folder>` flag, or the Phase 0 auto-detect + confirm when the project has no `sprint-status.yaml` — never a stored setting, so `config.yaml` and `assets/config-defaults.yaml` are unchanged. The auto-detect roots are `{output_folder}/specs`, `{planning_artifacts}` and `{implementation_artifacts}` (all three already in the preflight JSON). The resolved source is recorded per story in the state file (`story_source` / `spec_folder` / `story_id`). Per-phase flow: `stories-mode.md`.
- **Removed keys (ignored).** `config_plan.py` ignores unknown keys and never strips them; `reset-defaults` prunes only asset-block ones (`config-commands.md`). This note is the ONE sanctioned place a shipped reference spells these names — never use, document as live, or accept them as input elsewhere: `delegation.target_tools`; `code_review.max_iterations`, `code_review.security_review`, `code_review.verification_gap`, `code_review.epic_review`, `code_review.tier_a_lenses`, `code_review.epic_diff_chunk_threshold_lines`; `phase_profiles` keys `create_story`, `dev_story`, `code_review_review`, `code_review_review_secondary`, `code_review_review_tertiary`, `code_review_security`, `code_review_verification`, `code_review_fix`, `project_context`, `uat`; profiles `ab-verification`, `ab-deep`, `ab-standard`, `ab-alt-deep`, `ab-alt-standard`, `ab-security` (the append-only heal leaves them and their `phase_profiles` mappings in place until `reset-defaults`); per-profile `description` / `role_blurb` / `status_example` (persona strings — ignored if present). `delegation.mode: custom-subagents` in an old config is read as `subagents` (alias) and reported by `config-check` (`legacy_mode_alias`).

## state/{key}.yaml
The state file is a **machine-readable contract**, not a prose log — the source of truth for resume.
- Updated after every phase; `state_update.py` owns every write.
- Every field is always emitted with an explicit `null`/`false`/`[]`/`{}`.
- Prose belongs in `reports/{key}.md`, not here.

```yaml
story_key: 2-6a-digest-delivery
epic_num: 2                 # null in stories mode (no epic integer — the spec folder is the epic)
story_num: 6                # null in stories mode
story_suffix: "a"           # split-story suffix from the key grammar ^(\d+)-(\d+)([a-z]?)-.+ ; "" when none; null in stories mode
story_source: sprint        # sprint (sprint-status.yaml + epics docs) | stories (a bmad-spec spec folder — stories-mode.md)
spec_folder: null           # stories mode: ABSOLUTE path of the spec folder (SPEC.md + stories.yaml + stories/); null in sprint mode
story_id: null              # stories mode: the stories.yaml entry id, a string ("1", "3-2"); null in sprint mode
branch: story/2-6a-digest-delivery
status: in-progress         # in-progress | done
updated_at: "2026-05-28T14:04:41Z"  # ISO-8601 UTC; stamped by state_update.py on every write
started_at: "2026-05-28T13:55:02Z"  # ISO-8601 UTC; stamped ONCE at the Phase 1 init, never rewritten (survives resume)
completed_at: null          # ISO-8601 UTC; set when status flips to done (Phase 9 finalize); null while in-progress
active_seconds: 0           # wall-clock spent EXECUTING phases (delegate runtime + orchestrator work up to the
                            #   pause; the state write + commit land after it), summed across sessions.
                            #   Script-owned via timing-start/-pause — never hand-add.
timing_anchor: null         # epoch seconds while a phase (or a bracketed user prompt) is executing; null when idle.
                            #   Non-null on resume = crash tail (timing notes below).
is_first_in_epic: false
is_last_in_epic: false
git_mode: remote
base_branch: main
tea_risk: high                   # low|med|high from Phase 0 triage (input: the epics doc entry); gates per-story TEA + the trace advisory
tea_selected: [atdd, automate]   # from triage; [] if trivial or TEA off; may also include trace-advisory (long-epic high-risk)
tea_rationale: "touches auth -> High risk"
epic_story_count: 12             # stories under epic {e} (from sprint-status; stories mode: entries in stories.yaml); gates the long-epic trace advisory
stories_after_in_epic: 7         # epic stories ordered after this one (0=last); with epic_story_count, drives the trace-advisory distance gate
completed_phases: [0, 1, 2, 3]   # phase numbers from pipeline.md; gate-false no-op phases land here too (a phase this run's instructions skipped does NOT); Phase 8 only once all six phase8_steps markers resolve
spec_path: null                  # absolute path of the story's bmad-build-auto spec (story_plan.py --find-spec after the Phase 3 halt); every later phase reads it from here
spec_approved: false             # true once the spec-approval halt was answered Approve, or immediately when approval is not required (build.spec_approval false and this run did not ask for approval); resume re-opens the halt while false and required
build:                           # last bmad-build-auto result for this story (Phase 5, refreshed by every Phase 7 pass) — from story_plan.py --spec
  status: null                   #   draft | ready-for-dev | in-progress | in-review | done | blocked | null (not yet run)
  blocking_condition: null       #   when blocked: the spec's `## Auto Run Result` `Blocking condition:` line, else the delegate's reported condition, else "(not stated)" (the frontmatter status is authoritative — pipeline.md Phase 5)
  followup_review_recommended: false
  review_loop_iteration: 0
  deferred_count: 0              #   items in the spec's frontmatter `deferred:` list
  warnings: []                   #   spec frontmatter `warnings` (e.g. oversized, multiple-goals) — a flat list inside the map; round-trips
followup_passes: 0               # Phase 7 follow-up build-auto review passes run (incl. external-change re-reviews)
hitl_halt: null                  # Phase 7 halt outcome: "continued" | "stopped" | "skipped (clean)" | "auto-continued (epic — no halt)" | null (not yet reached)
review_unverified: false         # draft-predicate clause 2: this run skipped the follow-up review, or the spec still says followup_review_recommended: true after Phase 7's last pass (incl. followup: never) -> Phase 9 opens the PR as a draft
story_trace: null                # Phase 7 tail trace advisory: {verdict: PASS|CONCERNS|FAIL, uncovered: [..], ran: true}; non-null = done (resume marker); verdict is delegate-derived from the skill's coverage numbers — advisory only, never blocks/drafts
commits: [a1b2c3d, e4f5g6h]      # orchestrator commits (sha-lag rule) + build-auto's own (git log <head_before>..HEAD around every build-auto invocation — git-and-pr.md → "commits[]")
phase8_steps:                    # per-sub-step epic-end resume markers, recorded in each sub-step's folded state write:
  trace_gate: null               #   null (not yet run) | done; trace_gate may also be waived | failed (failed = parked, not resolved: resume re-opens the gate — resume rules below). A mid-Phase-8 crash
  nfr: null                      #   resumes at the first null instead of re-running completed delegations; Phase 8 joins
  test_review: null              #   completed_phases only once all six markers resolve (ran, or its gate was false)
  reconcile: null                #   delegated pre-archive pass: mark ledger items whose deferred work fully landed but went unmarked
  archive: null
  retro: null
gate_decision: null              # PASS|CONCERNS|FAIL|WAIVED|NOT_EVALUATED (last story only)
gate_iterations: 0               # Phase 8 trace-gate remediation passes run (automate+re-trace); capped by tea.gate_max_iterations; resume continues mid-loop
deferred_work_archived: 0        # Phase 8 (last story only): count of resolved entries moved from deferred-work.md to the deferred-work-resolved.md archive
retro:                           # epic-end retrospective (last story only)
  doc: null                      #   path of <impl>/epic-{e}-retro-<date>.md (stories mode: {spec_folder}/RETROSPECTIVE.md)
  verdict: null                  #   accepted | accepted-with-open-items | rejected | null
  open_action_items: 0           #   open/in-progress action_items for this epic after the retro (sprint_plan.py status); null in stories mode (no scripted source)
bmad_status_flipped_at: null     # 8 (pre-retro flip, last story) | 9 (finalize) | null — which phase flipped the sprint entry to done;
                                 #   ALWAYS null in stories mode (build-auto owns the story file's status — nothing to flip)
pr_url: null
ci_run_url: null                 # link to the CI run the PR/push triggered, if the repo has workflows
ci_status: unknown               # passed|failed|timeout|none|unknown — set only when Phase 9 waited (offer_merge on); else 'unknown'
pr_merged: false                 # true only if the user chose a merge style in Phase 9's merge prompt and `gh pr merge` succeeded
merge_method: null               # squash|merge|rebase|null — null if not merged or prompt was skipped
merge_commit: null               # full SHA of the merge commit on the base branch, or null
branch_deleted: false            # true if --delete-branch was used in the successful merge
open_questions: []
deferred_work: []
blockers: []                     # each: short human-action description; a blocked phase's entries are removed when that phase completes on resume ("Blockers clear on resume" below)
overrides: {}                    # free-form record of this run's instructions (SKILL.md -> Run instructions) plus orchestrator-set
                                 #   entry markers (e.g. start_phase, no_pr_draft); {} if none
constraints: []                  # caller-supplied constraints carried in via invocation (e.g. exact-string requirements); [] if none
```

The **timing** fields are script-owned — all clock arithmetic lives in `scripts/state_update.py`. When to bracket (and how to invert a bracket around a user prompt): `pipeline.md` → "Timing".
- A non-null `timing_anchor` on resume is a crash tail: the next `timing-start` re-anchors and conservatively discards the dangling interval (reported as `dropped_anchor: true`).
- Report derivation (`state_update.py report-section`) — best-effort host wall-clock, not token-compute time:
  - **elapsed** = `completed_at − started_at` (includes resume gaps).
  - **AI-run time** ≈ `active_seconds`.
  - **human/idle wait** ≈ `elapsed − active_seconds`.

## state/epic/epic-{e}.yaml  (epic mode; stories mode: state/epic/spec-{spec_slug}.yaml)
The **epic anchor** — one per epic run, the cursor + epic-level bookkeeping for `/auto-bmad epic`.
- It lives under the `epic/` **subdirectory** so the per-story `state_plan.py` scan (which lists only `state/*.yaml`) cannot see it.
- The epic resume scan is `state_plan.py --scope epic`.
- It reuses the **same per-story schema** and the same `state_update.py` writers (`init` / `set` / `phase-done` / `timing-*` / `report-section --epic`) — there is no separate state schema.

Meaningful reused fields:
- `story_key: epic-{e}`, `epic_num`, `status`, `branch` (`epic/{e}-{slug}`).
- The timing fields.
- `completed_phases` — the epic **E-steps** as ints (`E0→0`, `E1→1`, `E2→2`, `E5→5`, `E8a→81`, `E8b→82`, `E_final→9`).
- `gate_decision` / `gate_iterations` — epic-end trace gate.
- `deferred_work_archived`.
- `review_unverified` — aggregated from the landed stories (any story's `review_unverified: true`, or a run that skipped the follow-up review); drives the epic PR draft predicate.
- `retro` — the E8b retrospective block (`doc` / `verdict` / `open_action_items`), same shape as per story.
- `bmad_status_flipped_at` — `82` (E8b pre-retro batch flip) | `9` (E_final) | null.
- `pr_url` / `ci_run_url` / `ci_status`.
- `blockers` / `open_questions` / `deferred_work` — the epic rollup.
- The merge fields.
- `story_num` / `story_suffix` / `spec_path` / `build` / `hitl_halt` stay at their defaults — per-story concerns live in the per-story files.

Plus net-new epic fields that ride as **preserved extras** — not in the per-story `SCHEMA_ORDER` (`state_update.py` keeps unknown fields verbatim):
- `active_story` — the loop cursor (the `{key}` being processed, or null before E5 / after E_final).
- `stories_landed` — the `{key}`s this run actually processed (drives the batch BMAD-status flip + the report rollup; E0-skipped stories never join it).
- `epic_slug` — the resolved branch/PR slug (stored so resume reuses it, never re-derives a different one).
- `stories_skipped` — the E0 skip verdicts (`"{key} — <reason>"`, e.g. `already done` or the E0 no-spec note); persisted so a resume never re-asks and E5 never enters them (never flipped, never in the rollup, listed under **Skipped**). Like `stories_landed`, a read-modify-write list — `_append` does not apply.
- `batch_flip_done` — idempotency marker for the E8b/E_final batch BMAD-status flip on resume.

**Stories-mode anchor** (`story_source: stories`): same schema, same writers, same E-step `completed_phases` — only the naming and three fields differ.
- File `state/epic/spec-{spec_slug}.yaml`, `story_key: spec-{spec_slug}`, `epic_num: null`, `story_source: stories`, `spec_folder` (absolute), `epic_slug: {spec_slug}`, `branch: {git.epic_branch_prefix}{spec_slug}` — `{spec_slug}` = the spec folder's basename minus a leading `spec-`. Epic report: `reports/spec-{spec_slug}.md`.
- `active_story` / `stories_landed` / `stories_skipped` hold `spec-{spec_slug}-{id}` keys; `batch_flip_done` stays vacuously true (there is no BMAD status to flip) and `bmad_status_flipped_at` stays null.
- The epic-ownership guard matches on `spec_folder`, not `epic_num` (which is null in both places).

Ownership split (full flow: `epic-pipeline.md`; stories-mode E-steps: `stories-mode.md`): the per-story `state/{key}.yaml` files still exist (one per story the loop touches) and own intra-story resume; the anchor owns *which story / which E-step*.

## Target selection & resume logic
`--story` and `epic` are mutually exclusive — both in one invocation ⇒ hard-stop `` `--story` picks one story; `epic` runs a whole epic — pick one ``.

An explicit `--story <arg>` overrides the precedence below and targets that story directly: `story_plan.py --resolve <arg> --sprint-status <impl>/sprint-status.yaml --planning-dir <planning>` (stories mode: `--resolve <arg> --spec-folder <DIR>`); `hard_stop` ⇒ surface the reason (not found, or ambiguous with its `candidates`) and stop.

No-arg `/auto-bmad` chooses the target story with this precedence:
1. **Incomplete auto-bmad pipeline first.** If any `state/*.yaml` has `status != done`, that story is the target — finish in-flight work before starting anything new.
   - State files are named `{key}.yaml` (e.g. `1-2-user-auth.yaml`, or `spec-digest-delivery-3-2.yaml` in stories mode) — **no `story-` prefix**; the `story-{e}-{s}` / `story-{spec_slug}-{id}` form appears only in commit/PR scopes.
   - **Don't hand-roll shell for this** (no bare globs). Call the deterministic reader:
     ```
     python3 {skill-root}/scripts/state_plan.py --state-dir {output_folder}/auto-bmad/state
     ```
   - Parse its JSON:
     - `resume: true` ⇒ resume `target` (the most-recently-updated in-flight story; its record's `branch` feeds the resume preflight's `--expected-branch`); `extra_in_flight` lists any others to mention in the report.
     - `resume: false` (empty/absent dir, or all `done`) ⇒ fall through to the sprint-status pick.
   - Epic-ownership guard: `state_plan.py --state-dir … --scope epic` — an in-flight anchor whose `epic_num` matches the target's epic ⇒ hard-stop → `/auto-bmad epic --epic {e}`.
2. **Else the upstream sprint-status picker** — the call, its JSON contract and its hard-stops: `pipeline.md` Phase 0 step 5 (it runs after the full preflight, which supplies `skills.sprint_plan_script`). Its own precedence is `in-progress → review → ready-for-dev → backlog → retrospective`; step 1 still wins over it.
3. Then always the `story_plan.py --epic {e}` read — `pipeline.md` Phase 0 step 5.

**Stories mode** (`story_source: stories`; the per-phase flow lives in `stories-mode.md` — don't duplicate it here) keeps that precedence with two substitutions:
1. **In-flight state still wins** — the same `state_plan.py` scan. Stories-mode state files are `state/spec-{spec_slug}-{id}.yaml`, so **the key prefix alone tells the modes apart**: `spec-{spec_slug}-{id}` starts with `spec-`, and the sprint key grammar `^(\d+)-(\d+)([a-z]?)-.+` requires a leading digit — the two can never collide. A scan may return either kind, so branch on the source, never on the key shape: every `state_plan.py` record — the scan's `target`/`extra_in_flight` entries, a `--story-key` read and an `--scope epic` anchor — carries `story_source` / `spec_folder` / `story_id`. A state file written before stories mode existed has none of them and reports all three `null` ⇒ treat it as `sprint`.
2. **Else `story_plan.py --stories --spec-folder <DIR>`** (the `--epic` mirror) → `next_story_key` = the first `stories.yaml` entry, in list order, whose status is not `done` (`all_done: true` ⇒ no target). There is **no upstream picker** — `sprint_plan.py status` is sprint-only.
An explicit `--story <arg>` resolves through `story_plan.py --resolve <arg> --spec-folder <DIR>` (exact id → exact `spec-{spec_slug}-{id}` key → case-insensitive title/slug substring; several ⇒ hard-stop with `candidates`).

Once the target `story_key` is known, check its state with the same reader — an exact `{key}` lookup, never a glob:
```
python3 {skill-root}/scripts/state_plan.py --state-dir {output_folder}/auto-bmad/state --story-key {key}
```
- `resume: true` (file exists, `status != done`) → **resume**:
  - Skip phases already in `completed_phases`.
  - Phase 3: the resume matrix in `pipeline.md` P3.2.
  - Spec-approval halt: re-opened before Phase 4/5 per `pipeline.md` Phase 3 step 6.
  - Phase 5 re-invokes build-auto with the spec path — build-auto routes by the spec's own status (`ready-for-dev` / `in-progress` / `in-review`); a `blocked` spec ⇒ needs-human (recovery text: `pipeline.md` Phase 5).
  - Phase 7: a follow-up pass is atomic — re-run it in full (never reconstruct a half-finished pass). `hitl_halt` null and a halt is due ⇒ re-open it. **`hitl_halt: stopped` with 7 ∉ `completed_phases` ⇒ re-open the halt** — reset `hitl_halt` to null and re-ask; choosing Continue then runs the external-change check as usual, so edits made while stopped get their single re-review (mirrors the spec-approval Stop rule). That check is defined in `pipeline.md` Phase 7 step 3.
  - Phase 8 resumes by its `phase8_steps` markers (first null sub-step) — except `trace_gate: failed`, a parked verdict, not a resolved one: re-delegate **`testarch-trace (epic gate)`** and re-apply its verdict handling under the same `gate_iterations` cap (`pipeline.md` Phase 8); a non-`FAIL` verdict removes the earlier FAIL entry from `blockers[]` and re-derives `gate_decision`.
  - **Blockers clear on resume.** A blocked phase's `blockers[]` entries (a Phase 3 plan-time block's result-file path; a Phase 8 trace-gate `FAIL` Stop) are live only while the block stands: when that phase later completes on resume — the Phase 3 plan succeeds, a Phase 5 / Phase 7 build-auto run returns `done`, a re-run epic trace gate returns non-`FAIL` or the human waives it (`trace_gate: waived`) — remove that phase's entries via `state_update.py set` (`blockers: [<list without them>]`) before its `phase-done` write. Epic mode's E5h rollup then carries only live blockers.
  - Re-detect git mode/branch (cheap) rather than trusting stale values if the branch is missing — the resume preflight gets `--expected-branch <state branch>` (`state_plan.py --story-key` emits `branch`).
- `exists: false` → start fresh (state file init in Phase 1) — **after the status-mismatch guard.**
  - Check the story's BMAD status from the `story_plan.py --resolve`/`--epic` read (`current_status` / the epic entry's `status`).
  - `backlog` ⇒ start fresh.
  - `ready-for-dev` ⇒ start fresh; Phase 3 first probes `story_plan.py --find-spec` (a spec may pre-exist from a bare `/bmad-build-auto` run) and routes by its status — the resume matrix in `pipeline.md` P3.2.
  - **`review` or `in-progress` with NO state file** means the work happened outside auto-bmad (a hand-driven/brownfield story, or a lost state dir) — the full pipeline would re-plan and re-implement an already-built story. **ASK the user** (`AskUserQuestion`):
    - **Enter at the matching phase** *(recommended)* — `in-progress` ⇒ Phase 5 Build, `review` ⇒ Phase 7 follow-up review. **Validate the entry first and hard-stop with a precise message if it fails** (read spec facts only through `story_plan.py`; never open the spec yourself):
      - **Phase 5** — the story's build-auto spec must exist at `ready-for-dev` or later (never `draft`/`blocked`): `python3 {skill-root}/scripts/story_plan.py --find-spec --impl-dir <impl> --story-key {key} --sprint-status <impl>/sprint-status.yaml` (`found: false` ⇒ hard-stop; `ambiguous: true` ⇒ hard-stop listing `candidates`); record `spec_path` in state.
      - **Phase 7** — same spec requirement, plus the spec's `status` (`--spec <spec_path>`) is `done` and the sprint entry is `review` (`--resolve` → `current_status`); a `review` entry whose spec is not `done` enters at Phase 5 instead.
      - Entering Phase 7 with no Phase 5 result seeds `build.*` from `story_plan.py --spec <spec_path>` and runs ONE pass regardless of the recommendation gate; an instruction to skip the follow-up review still wins (`pipeline.md` Phase 7).
    - **Run the full pipeline anyway** (a deliberate redo).
    - **Stop**.
    - Record the chosen entry as `start_phase` in the state's `overrides` map (an orchestrator-set entry marker, not a user instruction).
  - **Stories mode: the guard reads the STORY FILE.** There is no sprint entry, so the vocabulary is the id-keyed story file's frontmatter `status` — `draft | ready-for-dev | in-progress | in-review | done | blocked`, and **no file at all = not started**. Read it only through `story_plan.py --find-spec --spec-folder <DIR> --story-id <id>` (then `--spec <spec_path>`) — never by opening the file. Branch mapping: no file or `draft` ⇒ start fresh; `ready-for-dev` ⇒ start fresh (Phase 3 routes by the spec); `in-progress` ⇒ the Phase 5 ask above; `in-review` ⇒ the `review` ask above (Phase 7 entry); `blocked` ⇒ needs-human stop, never an auto-entry; `done` ⇒ the `done` rule below.
  - **Sanctioned regress paths (sprint mode only** — stories mode never calls `--mark-status`; `bmad-build-auto` owns the story file's status, so there is nothing to regress and `bmad_status_flipped_at` stays null**)** — the ONLY places the orchestrator passes `story_plan.py --mark-status … --allow-regress`: "Run the full pipeline anyway" for an `in-progress`/`review` story (Phase 3 → `ready-for-dev`, Phase 5 → `in-progress`); entering Phase 5 for a `review` story whose spec is not `done`; a confirmed full re-run of a `done` story (below); an entry that re-enters a phase whose target status is below the entry's current one. Any other `refusing to regress` exit is a hard-stop (the entry moved outside auto-bmad — surface the message).
- State `status: done` for the target (a completed run) → never redo silently: print the recorded report tail + `pr_url` and stop.
  - A clean completion flips the sprint entry to `done` at Phase 8 (pre-retro, last story) or Phase 9, so the picker moves on; a **caveated** one deliberately stays at `review`, so the picker re-surfaces it.
  - On a **no-arg** run this is the caveated case — the story sits at `review` (draft PR / blocker / waived gate / CI red), so the picker re-recommends it on every bare `/auto-bmad`. The stop text names the way forward explicitly: (1) resolve the recorded caveat, then flip the entry (`/auto-bmad --story {key}` re-opens Phase 9 only when the caveat is cleared, else it prints the same stop); (2) work another story: `/auto-bmad --story <next>` where `<next>` = the first `ready-for-dev`/`backlog` key after this one from `story_plan.py --epic {e}`, or, when the epic has none, "epic {e} has no unstarted stories — pick a key with `/auto-bmad --story <key>` or start the next epic with `/auto-bmad epic --epic <N>`". (`SKILL.md` lists this under not-silent stops.)
  - An explicit `--story {key}` on a `done` state ⇒ ask "already complete (PR …) — re-run the full pipeline anyway?" (Yes ⇒ the sanctioned regress path; No ⇒ stop).
  - **Stories mode:** a caveated completion is NOT re-surfaced by the picker — `bmad-build-auto` already left the story file at `done`, so the caveat lives only in the state file and the report's `(final — caveated)` tag + `⚠️ Needs human` list. A re-run needs an explicit `/auto-bmad --spec <folder> --story <id>` (same confirm as above; no status regress — there is none to make).

Git commits are the secondary safety net: even if the state file is lost, the per-phase commits on the branch (and build-auto's own) show how far the pipeline got.

Draft predicate: computed by `state_plan.py --finalize` (Phase 9); the four clauses are defined once in `git-and-pr.md` → "Draft predicate (clauses 1–4)" — the state fields it reads are above. In stories mode pass `--finalize --story-source stories`: the clauses, `draft` and `clean_completion` are unchanged, `flip_bmad_status` is forced `false`, and `reasons` carries the note `stories mode: no BMAD-status flip (build-auto owns the story-file status)` — a `reasons` entry is therefore not the same as a fired clause; read `clauses` for the predicate.

## reports/{key}.md
The per-story report is a **log**, not a single overwritten document.
- It carries only the **story-level** outputs that aren't recorded elsewhere — this run's instructions, TEA outcomes, open questions, deferred work, blockers, next-story preview.
- The finalization **artifacts** (PR URL, CI run link, merge method + branch-deleted state, BMAD-status-flip outcome) are **chat-only**, so the file is written **once** pre-push and never re-touched after PR/CI/merge resolve.
- The one-line **disposition** is NOT chat-only: it belongs in the `Pipeline status` line and covers clean / caveated / halted, plus a draft's summary reason.
- Clean path: written + committed in **Phase 9 before push** (`docs(story-{e}-{s}): pipeline report`; stories mode `docs(story-{spec_slug}-{id}): …`) so it ships in the PR diff (`pipeline.md` Phase 9; `git-and-pr.md` → "Ownership"). Any path that didn't reach that pre-push write gets the `SKILL.md` Step 3 fallback — same content, no commit.
- Each run (first completion OR resume) **appends** a new `## Report — <ISO timestamp>` section via `state_update.py report-section` — the script never overwrites existing sections.
- **Each section is a session delta, not a cumulative rollup** — `Phases run` / `Skipped` cover this session alone; a resume carries a `Continues:` back-reference. Don't re-derive an earlier (possibly cross-tool) run's TEA counts or review tally into a later section.
- **Tag the `## Report` heading with this section's terminal disposition** — read the last tag to know where the story stands. Closed vocabulary: `(final)` (clean, BMAD status flipped `done`), `(final — caveated)` (finalized but left at `review`: draft PR / blocker / waived gate / CI red), `(halted — <reason>)` for a stop before Phase 9 (`needs-human`, or `stopped: <the run instruction that ended it>` — quote the instruction as the user gave it). Lineage is not in the tag — a prior section plus the `Continues:` line already mark a resume. (A clause-4 caveat — CI red/timeout — resolves only *after* the pre-push write, so it shows up in the chat report and in a later resume section's tag, never in the section written before push.)
- The **only** overwrite is a deliberate full re-run of an already-`done` story, after explicit user confirmation ("overwrite the existing report log for {key}?") — only then pass `--overwrite-confirmed` (without the flag the script always appends); if declined, append instead.
- **Epic mode** writes ONE epic report — `reports/epic-{e}.md` (stories mode: `reports/spec-{spec_slug}.md`, whose **Epic:** line reads `spec {spec_slug}`), via `state_update.py report-section --epic` (the epic-rollup template + its own `EPIC_REPORT_PAYLOAD_KEYS` allowlist): epic header, the per-story rollup, the skipped stories, the epic-gate + TEA outcomes, the retrospective verdict, and the aggregated open-questions / deferred checklist. It replaces the per-story reports, committed once pre-push as `docs(epic-{e}): pipeline report`. Same append + disposition-tag rules as above (`epic-pipeline.md` E_final).
  **`--json` payload keys (exact names — unknown keys are REJECTED):** `disposition_tag`, `pipeline_status`, `continues`, `epic_summary`, `story_rollup` (list — one line per landed story: build status / review passes / deferred / trace), `stories_skipped` (list — one line per story with its reason: `already done` or the E0 skip note), `epic_gate`, `tea`, `retro` (verdict + open action items + doc path), `overrides`, `open_questions` (list), `deferred_work` (list) + `deferred_archived_note`, `needs_human` (list), `next` (includes the `/bmad-project-context refresh` recommendation), `head_sha`.
  Rendered order: **Epic** / **Branch** / **Pipeline status** / **Continues** / **Summary** / **Timing** / **Stories** / **Skipped** / **Epic gate** / **TEA** / **Retrospective** / **Overrides** / **Open questions** / **Deferred work** / **⚠️ Needs human** / **Next**.

### Section template (use literally, in this order)
This template is the **single home** for the file portion's fields, heading order, and per-field semantics.
- `state_update.py report-section` renders it literally:
  - Story/Branch/Timing lines (and the `resumed N×` count) derive from the state file + prior sections.
  - Prose snippets come from `--json`.
  - A heading is never dropped — an empty field keeps its heading with `(none)`.
- Timing-split semantics: the timing fields above.

**`--json` payload keys (exact names — the script REJECTS unknown keys, because a misspelled key would silently render its heading `(none)`):** `disposition_tag` (the heading tag), `pipeline_status`, `continues`, `phases_run`, `skipped`, `overrides`, `tea`, `build`, `review`, `retro`, `open_questions` (list), `deferred_work` (list) + `deferred_archived_note` (the Phase 8 reconcile + archive line appended under it), `needs_human` (list — the ⚠️ heading), `next`, `head_sha` (the Branch line's short SHA). The **Spec** line is not a payload key — it renders the state's `spec_path`.

Renderer defaults when a key is absent: `Overrides` → `none`, `Build` → `not run`, `Review` → `skipped`, `Retrospective` → `(none)`, `Continues` → `(none — first run)`, every list block → `(none)`.

```markdown
## Report — <ISO timestamp UTC> (<disposition tag — the closed vocabulary above: (final) / (final — caveated) / (halted — <reason>) — tagging the heading keeps the log skim-readable from its outline>)

**Story:** `{key}` (epic {e}, story {s}) — {first-in-epic? / last-in-epic? / mid-epic}.   <!-- stories mode: `spec-{spec_slug}-{id}` (spec {spec_slug}, story {id}) — same line, rendered from story_source -->
**Spec:** `<spec_path>` (from state; `(none)` before Phase 3)
**Branch:** `<branch>` (HEAD `<short-sha>`).
**Pipeline status:** <one-line summary, e.g. ✅ clean completion / halted at Phase 5 (needs-human: build-auto blocked) / draft (CI red)>.
**Continues:** <on a resume, the prior section's ISO timestamp + its tag, e.g. `2026-05-29T15:05:06Z (halted — stopped: stop before the review)`; `(none — first run)` on a first run — keep the line either way, like every other heading>.

**Timing:** started <ISO>; completed <ISO, or "in progress"> — elapsed <Hh Mm> (≈<Hh Mm> AI-run, ≈<Hh Mm> human/idle wait)<; resumed N× if >1 session>.

**Phases run:** <comma-joined Phase N list for THIS session, with profile/model in parens for delegated phases; on a resume this is the session delta — earlier phases live in the section named by `Continues:`>.
**Skipped:** <comma-joined Phase N list with reason in parens; this session>.

**Overrides:** <one line — this run's instructions as you interpreted them, plus any orchestrator-set entry marker; "none" if the invocation carried none>.

**TEA:** <which skills ran and their one-line outcome; "disabled" if tea.enabled=false; epic-gate decision if last story; for the per-story trace advisory, its verdict + any uncovered ACs (advisory, non-blocking)>.

**Build:** <build-auto result: spec status; review_loop_iteration; deferred N (harvested to the ledger); warnings; commits by build-auto; "not run" if Phase 5 never ran>.

**Review:** <follow-up passes N (profile / cli route); last pass patch/bad_spec/defer counts + reject (≤ 6.11.0) or dismissals (≥ 6.11.1); followup still recommended?; HITL halt outcome (continued / stopped / skipped (clean) / auto-continued (epic — no halt)); review_unverified; "skipped" if no follow-up review>.

**Retrospective:** <epic-end only: verdict; N open action items (listed); doc path; "(none)" otherwise>.

**Open questions:** <numbered list, one per line — questions surfaced by any step; "(none)" if empty — keep the heading>.

**Deferred work:** <numbered list, one per line — anything intentionally postponed (also harvested into the durable cross-story `<impl>/deferred-work.md` ledger; cross-link it when items landed there); on the last story of an epic, add a line from Phase 8 covering the reconcile + archive (e.g. "marked 2 missed-completions; archived 6 resolved → deferred-work-resolved.md"; name each reconcile-marked item with its one-line evidence; omit the note if nothing was marked or moved); "(none)" if empty — keep the heading>.

**⚠️ Needs human:** <numbered list of blockers / manual actions. On a caveated completion these are required before the story can be considered done (it was left at `review`); on a clean completion the story is already `done` — list only genuine optional follow-ups (e.g. merging the open PR, the AGENTS.md block missing) and never imply the merge gates `done`; "(none)" if clean>.

**Next:** Human review: `/bmad-checkpoint-preview <pr_url | branch>` (spec: `<spec_path>`); then `/auto-bmad` (sprint_plan.py status recommends the next story; stories mode: `/auto-bmad --spec <folder>` picks the next stories.yaml entry). <epic end: "Project context: run /bmad-project-context refresh (recommended after an epic)."> — preview only; do NOT start the next story.
```
