# Config, state, resume & first-run

Everything auto-bmad persists lives under `{project-root}/_bmad-output/auto-bmad/`. One section each below:
- `config.yaml` — project config, created on first run.
- `state/{key}.yaml` — one resumable state file per story.
- `retro-notes/epic-{e}.md` — accumulated notes feeding the epic retrospective.
- `reports/{key}.md` — per-story report log, appended each run.

## config.yaml
```yaml
version: 1
profiles_source_version: "0.25.2"  # abm version whose assets/agents/profiles.yaml seeded the profiles +
                                  # phase_profiles blocks below; re-stamped by the Phase 0 heal (ADDITIVE-only —
                                  # never overwrites user values; see assets/config-defaults.yaml header) or `reprovision`.
delegation:                # spawn mechanism — host/mode auto-detected each run
  host: auto               # auto (detect each run) | claude-code | codex | opencode | other
  mode: auto               # auto (derive from host) | custom-subagents | general-subagents | inline
  target_tools:            # tools to provision agents for; detected from installed skill dirs
    - claude-code          # (rules: module-setup.md) and confirmed at first run. May also list
    - codex                # `opencode`. More than one = run in any of those tools, no reconfig.
  cli_phases: {}           # OPT-IN per-phase external-CLI routing: keys = phase_profiles keys, value =
                           # claude|codex|opencode; empty/absent => every phase uses its tier. Hand-edited.
                           # Semantics: delegation-runtime.md "Per-phase external-CLI routing"; examples: assets/config-defaults.yaml.
tea:
  enabled: true            # set at first run after checking TEA skills exist
  framework_ci: prompt     # prompt | done | skip  (resolved at first run)
  gate_max_iterations: 2   # Phase 8 trace-gate remediation cap (automate + re-trace) before only waive/stop are offered
  story_trace_advisory:    # per-story, non-blocking trace pass — shifts coverage-gap visibility left on LONG epics
    enabled: true          # self-activating: dormant on short epics (see min_epic_stories), fires only on long high-risk stories
    min_epic_stories: 6    # only runs in epics with >= this many stories; short epics rely on the epic-end gate alone
    skip_last_stories: 3   # also skip the epic's last N stories (distance-to-gate, tea-policy.md §3) — their gap surfaces at the epic-end trace gate anyway. Absent in older configs => orchestrator defaults to 3
git:
  mode: auto               # auto -> detect; or force "remote" / "local"
  branch_prefix: "story/"
  epic_branch_prefix: "epic/"  # epic mode: the one branch a whole epic run commits to (epic/{e}-{slug}). Absent => orchestrator defaults to "epic/"
  base_branch: main        # auto-detected; written after first detection
  offer_merge: true        # Phase 9: ask the user whether to merge a clean-completion PR
  ci_wait_minutes: 30      # max wait for in-progress CI before deciding (used only when offer_merge is on)
code_review:
  max_iterations: 2
  security_review: true    # run the dedicated per-story security review inside the Phase 7 loop (auto-bmad-local; ab-security delegate). false => skip it. Absent => orchestrator defaults to true
  epic_review: true        # epic mode: run the Tier-B epic integration review (heavy adversarial pass; no halt — decisions auto-resolved, unconverged ships a draft). false => per-story thin review only. Absent => defaults to true
  tier_a_lenses: [auditor, security]  # epic mode: the per-story thin-review lens set (one pass, no loop/halt); security gated by security_review. Absent => defaults to [auditor, security]
  epic_diff_chunk_threshold_lines: 6000  # epic mode: chunk the Tier-B review when the epic diff exceeds this many lines (per-story sub-diffs + joint triage); 0 => never. Absent => defaults to 6000
# profiles + phase_profiles complete the file — single source: assets/agents/profiles.yaml
# (first run copies it in verbatim; edit it or this copy, then `/auto-bmad reprovision`;
# `/auto-bmad reset-defaults` re-seeds — see below). Codex model names ship as real defaults —
# retune them (in the asset) if your install differs; set opencode.model per profile for
# per-phase tiering + cross-vendor review diversity. Shape only:
profiles: {…}              # ab-deep | ab-standard | ab-alt-deep | ab-alt-standard, each:
                           #   {claude: {model, effort}, codex: {model, reasoning_effort},
                           #    opencode: {model, variant}} — opencode is model-only + ships model
                           #   BLANK (inherit your opencode default); variant is cli_phases-only.
                           #   CUSTOM profiles may be ADDED here (same field set incl. the persona
                           #   strings; name MUST start with `ab-`) — reprovision renders every
                           #   ab-* profile it finds; a whole-block reset-defaults prunes them
phase_profiles: {…}        # create_story, dev_story, code_review_review, code_review_review_secondary,
                           #   code_review_review_tertiary (the two extra reviewer slots are OPTIONAL —
                           #   blank "" => disabled; secondary ships on, tertiary ships blank),
                           #   code_review_security (dedicated security review; blank "" => primary profile),
                           #   code_review_fix, tea_triage, tea_per_story, tea_epic, tea_epic_audit,
                           #   retrospective, project_context, uat (git/PR work runs in the orchestrator
                           #   directly — no delegate profile). Values may name ANY profile in the
                           #   profiles block above — shipped or custom
```

## First-run flow (only when config.yaml is absent)
This is the single interactive episode in normal operation.
- Always confirm `target_tools`.
- Then offer **quick vs full** setup.
- Use AskUserQuestion.

0. **Seed delegation & profiles (non-interactive).** All of these are file-edited later, never interviewed.
   - Set `delegation.host`/`mode` to `auto`.
   - Seed `delegation.cli_phases: {}`.
   - Copy the `profiles` + `phase_profiles` defaults from `{skill-root}/assets/agents/profiles.yaml`.
   - Detect the live host.
   - Run `reprovision` (`scripts/render-agents.py`) before the pipeline starts — if the host needs `custom-subagents` but its agent files are missing.
1. **Confirm `target_tools` (always).** Detect from the installed skill dirs on disk and confirm with the user — exact rules: `assets/module-setup.md` → "Provision Delegate Agents" (Step 1).
   - Reuse the `abm` value `module-setup.md` just confirmed — if it already ran *this session*.
   - Run `reprovision` for the confirmed set — if it differs from what agents were rendered for.
2. **Choose setup depth.** Ask **Quick** or **Full**.
   - **Quick** (recommended) — `target_tools` + TEA only; sensible defaults for everything else. Skip step 4.
   - **Full** — also set git + code-review prefs.
3. **TEA (both depths).** Detect the TEA skills (`bmad-testarch-*`) and ask `tea.enabled`.
   - Default "yes" if present.
   - Default "no" if absent — don't offer yes when absent.
   - If enabled, resolve `framework_ci` via `preflight.py --detect-framework-ci` (`framework.configs` = test-framework configs found, `framework.ci_present` = CI workflow):
     - Both present → `framework_ci: done` silently.
     - Missing → **ask** to run one-time `/bmad-testarch-framework` + `/bmad-testarch-ci` now (delegate to `ab-standard`) or `skip` — never auto-run unasked, because it is heavy, infra-choosing setup.
4. **Full only — extra prefs** (each prefilled with the default shown):
   - `git.mode` (auto | remote | local; default auto).
   - `git.branch_prefix` (default `story/`).
   - `code_review.max_iterations` (default 2).
   - `git.base_branch` is auto-detected, never asked.
5. **Write `config.yaml`** with the seeded delegation/profiles, the confirmed `target_tools`, the answers, and detected `git`/`base_branch` values (Quick fills the step-4 fields with the defaults above).
   - Above the copied `profiles:` block, write a pointer comment naming both retune paths (*edit here + `/auto-bmad reprovision`*; *discard edits with `/auto-bmad reset-defaults`*).
   - Stamp `profiles_source_version` with the `module_version` from `{skill-root}/assets/module.yaml`.
   - **Then stop — do not start the pipeline this session** — because it would waste the context window that just did setup.
   - Report what was configured, then tell the user how to begin the first story:
     - **`custom-subagents` tier (Claude Code / Codex):** fully quit and relaunch the tool before `/auto-bmad` (a `/clear` or "new chat" is not enough) — see `delegation-runtime.md` → "Newly-rendered agents need a process restart".
     - **Other tiers:** a fresh session/context is enough — no project agents to load.

## reset-defaults — restore shipped profile defaults
`/auto-bmad reset-defaults [scope]` discards retunes in `config.yaml` and re-seeds the **asset-sourced** blocks from `{skill-root}/assets/agents/profiles.yaml`.
- It is also the one-shot fix for a `manual_review` item the heal won't auto-write — a sub-key missing from an existing profile.
- **Config-only:** report what changed, then stop — never start a pipeline.

**Scope** (the optional arg; bare = both asset blocks):
- *(omitted)* — both `profiles` and `phase_profiles`.
- `profiles` — every profile block.
  - Also **prunes** a profile present in the config but absent from the asset — the renamed/dropped remedy; pruned names return on `removed_profiles`.
  - Doesn't touch `phase_profiles` — so a *custom* mapping pointing at a pruned profile dangles (bare scope resets both).
- `<profile-name>` (e.g. `ab-standard`) — that one profile. Never prunes — a user-added profile is left intact.
- `phase_profiles` — the phase→profile mapping only.

**Boundary (state it to the user).** reset-defaults touches **only** `profiles`, `phase_profiles`, and the `profiles_source_version` stamp.
- It touches **never** `delegation`/`tea`/`git`/`code_review` — because those are setup answers, not shipped defaults, and reset *overwrites* where the Phase 0 heal only *appends*, so it would clobber them.
- Redoing those is `setup`/`configure`.

**Flow:**
1. Require `config.yaml` to exist. Absent → "Nothing to reset — run `/auto-bmad setup` first." and stop.
2. Plan (read-only):
   ```
   python3 {skill-root}/scripts/config_plan.py --reset <scope> --config <output_folder>/auto-bmad/config.yaml
   ```
   Empty `would_change`, empty `removed_profiles`, **and** no `version_restamp` → "Already at shipped defaults for `<scope>`." and stop.
3. **Confirm** with `AskUserQuestion`. This is the sole interactive moment.
   - Show the `current → default` diff (truncate long persona strings).
   - Call out **separately — never buried in the diff — any `removed_profiles`**: those blocks are deleted outright, so a user-added profile would be lost.
   - Options: **Reset** / **Cancel**.
   - Cancel → stop, write nothing.
4. On confirm, write by re-running with `--write` (backs the prior config up to `config.yaml.bak`, then overwrites). Report the backup path and any `version_restamp`:
   - A **full** reset restamps `profiles_source_version` to the module version.
   - A **scoped** reset leaves it.
5. **Re-render delegates iff the plan's `render_needed` is true** — the `ab-*` agent files are now stale. Use the **same reprovision path** the rest of the skill uses; don't re-derive it here:
   - Resolve host/tier per `delegation-runtime.md`.
   - Read `delegation.target_tools` from the config just written.
   - Run the `reprovision` action exactly as `module-setup.md` describes.
   - No-op off `custom-subagents`.
   - A `phase_profiles`-only reset never sets `render_needed`.
   - When agents were rendered, surface the **process-restart caveat** (`delegation-runtime.md` → "Newly-rendered agents need a process restart").
6. Report scope, what was reset, the backup path, restamp, and whether a relaunch is needed. Stop.

## config-check — preview pending config/profile updates (and optionally apply them)
`/auto-bmad config-check` reports how `config.yaml` differs from the shipped defaults — what an update would **add**, **everything you've changed**, and the heal-immune setup answers — then offers to bring the config up to date. **Read-only until you confirm.**
- Run it before a story/epic to see the new profiles/settings an update shipped and decide whether to retune *before* they take effect, or to update the config on demand. The same drift data drives the automatic Phase 0 / E0 **pre-run pause** (`pipeline.md`) — this command is the on-demand pull; the pause is the automatic push.
- **Config-only:** report (and, if you confirm, apply), then stop — never start a pipeline.

**Flow:**
1. Require `config.yaml` to exist. Absent → "auto-bmad isn't set up here yet — run `/auto-bmad setup`." and stop.
2. Read drift (read-only):
   ```
   python3 {skill-root}/scripts/config_plan.py --check --config <output_folder>/auto-bmad/config.yaml
   ```
3. Render the **drift report** exactly as `pipeline.md` → "Drift report rendering" specifies — the two sides (*New since v<config>* + *Your customisations*), preceded by a version line (`config v<config> → module v<module>`), read straight from the `--check` JSON — **never read code**.
   - `status: fresh` ⇒ the *New* side is empty (say "nothing new since v<module>"), but still render *Your customisations* so the user sees their retunes.
4. **Setup answers (config-check only — NOT the Phase 0 pause).** After the two sides, render the `--check` JSON's `setup_answers` so the user sees *every* deviation — including the heal-immune answers the two diff-sides structurally cannot compare (they have no shipped default):
   - Heading *Setup answers (no shipped default — untouched by any heal)* — one `path = value` per `setup_answers` entry (e.g. `delegation.cli_phases`, `tea.enabled`, `tea.framework_ci`, a forced `git.mode`).
   - Then the note: *Note: your hand-edited `delegation.cli_phases` and `tea.framework_ci` are setup answers, not drift — they have no shipped default to compare against, so they're never flagged as customisations and never touched by any heal (`reset-defaults` leaves them too; redo them via `setup`).*
   - **Omit this whole block — heading and note — when `setup_answers` is empty** (nothing heal-immune to surface).
5. **Offer to apply** — the on-demand equivalent of the Phase 0 pre-run pause's "Apply defaults & continue":
   - **Pending predicate** — would `--apply` write anything: any of `missing_profiles` / `missing_phase_profiles` / `missing_setup` is non-empty, **OR** `version.drift` is true. (`manual_review` is NOT in it — the heal never auto-writes it; its fix is `reset-defaults`.)
   - **Predicate false** → nothing to apply; show the **How to act** guidance below and stop.
   - **Predicate true** → open an `AskUserQuestion` (the sole interactive moment):
     - **Update config to v<module> now** *(recommended)* — append the new keys/profiles/mappings and restamp `profiles_source_version`; **append-only, so every value you've set and every profile you've added is preserved**.
     - **Leave it — just previewing** — write nothing.
   - **Update** → re-run with `--apply`; confirm concisely from the `--apply` JSON — settings (`added_setup`) and preserved customisations (`kept_setup`) render exactly as the Phase 0 "Non-blocking live echo", plus the config-check-only adds the user already saw in step 3: added profiles/mappings (`reseeded_profiles` / `reseeded_phase_profiles`) and the `version_restamped` from→to. Then run the **same post-heal provisioning-freshness step Phase 0 uses** (`render-agents.py --check`, `pipeline.md`) — auto-reprovision any missing/stale `ab-*` agent (a no-op off `custom-subagents` and when nothing's stale), and on a re-render surface the **process-restart caveat** (`delegation-runtime.md` → "Newly-rendered agents need a process restart"). Stop.
   - **Leave it** → show the **How to act** guidance below and stop.

**How to act** (shown whenever you don't apply):
- **Customise before applying** — edit the named keys in `config.yaml` (the heal is **append-only**, so a value you set / a profile block you add is preserved), then re-run `config-check` (or just run the story/epic; Phase 0 applies the rest).
- **Accept the new defaults** — apply now (step 5), or just run the story/epic (it auto-applies at the pre-run pause, or with `skip config-pause`).
- **Discard retunes** back to shipped values — `reset-defaults`.

- **Read-only until you confirm:** writes `config.yaml` (append-only) and re-renders agents **only** on the explicit "Update" choice in step 5; the preview path restamps and renders nothing. Never starts a pipeline.

## state/{key}.yaml
The state file is a **machine-readable contract**, not a prose log — the source of truth for resume.
- It is updated after every phase.
- `state_update.py` owns every write.
- Every field is always emitted with an explicit `null`/`false`/`[]`/`{}`.
- Prose belongs in `reports/{key}.md`, not here.

```yaml
story_key: 1-2-user-auth
epic_num: 1
story_num: 2
branch: story/1-2-user-auth
status: in-progress         # in-progress | done
updated_at: "2026-05-28T14:04:41Z"  # ISO-8601 UTC; set by the orchestrator after every phase write
started_at: "2026-05-28T13:55:02Z"  # ISO-8601 UTC; stamped ONCE at the Phase 1 write, never rewritten (survives resume)
completed_at: null          # ISO-8601 UTC; set when status flips to done (Phase 9 finalize); null while in-progress
active_seconds: 0           # wall-clock spent EXECUTING phases (delegate runtime + orchestrator work up to
                            #   the pause; the state write + commit land after it), summed across sessions.
                            #   Script-owned via timing-start/-pause — never hand-add.
timing_anchor: null         # epoch seconds while a phase (or a bracketed user prompt) is executing; null when
                            #   idle. Non-null on resume = crash tail (timing notes below).
is_first_in_epic: false
is_last_in_epic: false
needs_project_context_bootstrap: false  # decided at Phase 0 (carried into Phase 1's init --json — no state file exists during Phase 0); flipped to false by Phase 2's bootstrap sub-step
git_mode: remote
base_branch: main
tea_risk: high                   # low|med|high from Phase 0 triage; gates per-story TEA + the long-epic trace advisory
tea_selected: [atdd, automate]   # from triage; [] if trivial or TEA off; may also include trace-advisory (long-epic high-risk)
tea_rationale: "touches auth -> High risk"
epic_story_count: 12             # stories under epic {e} (from sprint-status); gates the long-epic trace advisory
stories_after_in_epic: 7         # epic stories ordered after this one (0=last); with epic_story_count, drives the trace-advisory distance gate (skip the last skip_last_stories)
completed_phases: [0, 1, 2, 3, 4, 5, 6] # phase numbers from pipeline.md; gate-false no-op phases land here too (override-window skips do NOT); Phase 2 only once BOTH its sub-step gates resolved (ran, or gate false)
code_review_iterations: 1      # the review-loop iteration currently in progress (1-based); a mid-iteration resume re-runs this iteration from step 1 (one redundant review pass is the cost of a rare crash — there is no mid-iteration capsule). A value ABOVE code_review.max_iterations is a user-granted extension from the step-4 halt — gate it as the final iteration (--max-iterations {code_review_iterations}, pipeline.md step 3)
code_review_loop_done: false   # set true when the review loop exits (converged or capped); flipped back to false when the user extends the loop at the step-4 halt; on resume, true => re-open the Phase 7 HITL halt instead of re-iterating — UNLESS the step-4 skip gate applies (convergence_unverified=false, a clean convergence), in which case proceed to the Phase 7 tail without re-opening
hitl_halt: null                # Phase 7 step-4 outcome once the loop is done: "continued" | "stopped" | "skipped (clean convergence)" | "auto-continued (epic — no halt)" (epic mode never opens the halt) | null (not yet reached; also reset to null when the user extends the loop at the halt — it resolves at the next exit)
external_review_iterations: 0  # Phase 7 post-halt re-reviews of external-review changes run on Continue (single-shot — at most one per run; resumes can accumulate more); 0 if none
convergence_unverified: false  # true if the review loop hit max_iterations while the last pass still hadn't converged (review_loop.py's convergence rule: a non-deferred Critical/High/untagged finding, or >3 non-deferred findings that aren't all Low) (Phase 7); ALSO set when a post-halt re-review surfaced meaningful external-change findings and the user chose to continue with them open, or Phase 7 was skipped by the `skip code-review` override (zero review passes), or — in EPIC mode — any `[Review][Decision]` was auto-resolved at Critical/High severity (a best-guess on a high-severity item ships as a draft for human review; epic-pipeline.md E5f/E_review) -> Phase 9 opens the PR as a draft. CLEARED when the user extends the loop at the step-4 halt — the extended pass re-verifies it and the gate re-decides
story_trace: null              # Phase 7 tail trace advisory result, or null if not selected / not yet run:
                               #   {verdict: PASS|CONCERNS|FAIL, uncovered: [..], ran: true}. Advisory only — never blocks/drafts; non-null = done (resume marker)
commits: [a1b2c3d, e4f5g6h]
phase8_steps:                # per-sub-step epic-end resume markers, recorded in each sub-step's folded state
  trace_gate: null           #   write: null (not yet run) | done; trace_gate may also be waived | failed.
  nfr: null                  #   A mid-Phase-8 crash resumes at the first null instead of re-running completed
  test_review: null          #   delegations; Phase 8 joins completed_phases only once all seven markers resolve
  project_context: null      #   (ran, or its gate was false).
  reconcile: null            #   delegated pre-archive pass: mark ledger items whose deferred work fully landed but went unmarked
  archive: null
  retro: null
gate_decision: null          # PASS|CONCERNS|FAIL|WAIVED (last story only)
gate_iterations: 0           # Phase 8 trace-gate remediation passes run (automate+re-trace); capped by tea.gate_max_iterations; resume continues mid-loop
deferred_work_archived: 0    # Phase 8 (last story only): count of resolved entries moved from deferred-work.md to the deferred-work-resolved.md archive
pr_url: null
ci_run_url: null             # link to the CI run the PR/push triggered, if the repo has workflows
ci_status: unknown           # passed|failed|timeout|none|unknown — set only when Phase 9 waited (offer_merge on); else 'unknown'
pr_merged: false             # true only if the user chose a merge style in Phase 9's merge prompt and `gh pr merge` succeeded
merge_method: null           # squash|merge|rebase|null — null if not merged or prompt was skipped
merge_commit: null           # full SHA of the merge commit on the base branch, or null
branch_deleted: false        # true if --delete-branch was used in the successful merge
open_questions: []
deferred_work: []
blockers: []                 # each: short human-action description
overrides: {}                # this run's normalized invocation overrides (see overrides.md); {} if none
constraints: []              # caller-supplied constraints carried in via invocation (e.g. exact-string requirements); [] if none
```

The **timing** fields are script-owned — all clock arithmetic lives in `scripts/state_update.py`.
- Bracket work: `timing-start` before delegating a phase, `timing-pause` when it returns (just before the phase's state write + commit).
- Invert the bracket around any `AskUserQuestion` — pause before the prompt, start after — so user waits land on idle, not active.
- A non-null `timing_anchor` on resume is a crash tail: the next `timing-start` re-anchors and conservatively discards the dangling interval (reported as `dropped_anchor: true`).
- Report derivation (`state_update.py report-section`) — best-effort host wall-clock, not token-compute time:
  - **elapsed** = `completed_at − started_at` (includes resume gaps).
  - **AI-run time** ≈ `active_seconds`.
  - **human/idle wait** ≈ `elapsed − active_seconds`.

## state/epic/epic-{e}.yaml  (epic mode)
The **epic anchor** — one per epic run, the cursor + epic-level bookkeeping for `/auto-bmad epic`.
- It lives under the `epic/` **subdirectory** so the per-story `state_plan.py` scan cannot see it — that scan lists only `state/*.yaml` files, never a subdir.
- The epic resume scan is `state_plan.py --scope epic`.
- It reuses the **same per-story schema** and the same `state_update.py` writers (`init` / `set` / `phase-done` / `timing-*` / `report-section --epic`) — there is no separate state schema.

Meaningful reused fields:
- `story_key: epic-{e}`, `epic_num`, `status`, `branch` (`epic/{e}-{slug}`).
- The timing fields.
- `completed_phases` — the epic **E-steps** as ints.
- `gate_decision` / `gate_iterations` — epic-end trace gate.
- `deferred_work_archived`.
- `convergence_unverified` — aggregated up from the per-story thin reviews + the Tier-B integration review; drives the epic PR draft predicate.
- `pr_url` / `ci_run_url` / `ci_status`.
- `blockers` / `open_questions` / `deferred_work` — the epic rollup.
- The merge fields.
- `story_num` stays null.

Plus net-new epic fields that ride as **preserved extras** — NOT in the per-story `SCHEMA_ORDER`, so they cost no lockstep change (`state_update.py` keeps unknown fields verbatim):
- `active_story` — the loop cursor (the `{key}` being processed, or null before E5 / after E_final).
- `stories_landed` — the `{key}`s this run actually processed (drives the batch BMAD-status flip + the report rollup).
- `epic_slug` — the resolved branch/PR slug (stored so resume reuses it, never re-derives a different one).
- `auto_decisions` — the `[Review][Decision]` items this epic auto-resolved with the triage's recommendation (Tier A + E_review), each a one-line `"<title> [<sev>] → <fix|defer|dismiss>: <direction> (<context>)"`; rendered into the E_final report's `auto_decided` section. A Critical/High entry also set `convergence_unverified` (the epic PR ships a draft — `epic-pipeline.md` E5f).
- `uat_items` — the per-story manual UAT one-liners accumulated across the loop; E5 appends each landed story's `[{key}]`-tagged check items in the SAME `set` write as `stories_landed` (so a crash between them can't double-append on resume). The E_final `uat (epic)` consolidation delegate composes them into the single-session checklist rendered in the epic report's **UAT** section.
- `batch_flip_done` / `integration_review_done` — idempotency markers for E_final / E_review on resume.

Ownership split — full flow: `epic-pipeline.md`.
- The per-story `state/{key}.yaml` files still exist (one per story the loop touches) and own intra-story resume.
- The epic anchor owns *which story / which E-step*.

## Target selection & resume logic
No-arg `/auto-bmad` chooses the target story with this precedence (an explicit `--story <arg>` overrides both and targets that story directly):
1. **Incomplete auto-bmad pipeline first.** If any `state/*.yaml` has `status != done`, that story is the target — finish in-flight work before starting anything new.
   - State files are named `{key}.yaml` (e.g. `1-2-user-auth.yaml`) — **no `story-` prefix**.
   - The `story-{e}-{s}` form appears only in commit/PR scopes, never in a filename.
   - **Don't hand-roll shell for this** — never probe with raw shell globs (unmatched ⇒ `nomatch` abort under zsh/fish). Call the deterministic reader:
     ```
     python3 {skill-root}/scripts/state_plan.py --state-dir {output_folder}/auto-bmad/state
     ```
   - Parse its JSON:
     - `resume: true` ⇒ resume `target` (the most-recently-updated in-flight story); `extra_in_flight` lists any others to mention in the report.
     - `resume: false` (empty/absent dir, or all `done`) ⇒ fall through to `story_plan.py`.
2. **Else `story_plan.py`** picks the next actionable story — its precedence (`in-progress → review → ready-for-dev → backlog → retrospective`) resumes BMAD-level unfinished work first.

**Why a finished story doesn't re-stick (clean completions).**
- Phase 9 flips the BMAD-level status (story file `Status:` + the `sprint-status.yaml` entry) to `done` on a clean completion — else `story_plan.py` would re-pick it (`state_plan.py --finalize` ⇒ `flip_bmad_status: true`, run by `story_plan.py --mark-done`; mechanics: `pipeline.md` Phase 9).
- A **caveated** completion (draft PR / blocker / waived gate / CI red or timed-out) deliberately stays at `review` — it still needs a human, so it re-surfaces.
- A re-run, finding state already `done`, reports it complete (rule below) instead of redoing the work.

Once the target `story_key` is known, check its state with the same reader — an exact `{key}` lookup, never a glob:
```
python3 {skill-root}/scripts/state_plan.py --state-dir {output_folder}/auto-bmad/state --story-key {key}
```
- `resume: true` (file exists, `status != done`) → **resume**:
  - Skip phases already in `completed_phases`.
  - If Phase 7 is in progress (`code_review_loop_done` false), re-run iteration `code_review_iterations` in full from step 1 — a fresh review pass.
    - An iteration above `code_review.max_iterations` is a user-granted extension from the step-4 halt: gate it as the final iteration (pipeline.md step 3).
    - Never reconstruct a half-finished iteration from the story file — post-fix check-offs would fake a clean pass, and one redundant pass is the cost of a rare mid-iteration crash.
  - If `code_review_loop_done` is already `true`, re-open the Phase 7 HITL halt rather than re-iterating — the re-opened halt re-runs its git-only change check, so external changes made between runs get their single-shot re-review.
    - But if the step-4 skip gate applies — `convergence_unverified` false, a clean convergence — proceed to the Phase 7 tail without re-opening.
  - Re-detect git mode/branch (cheap) rather than trusting stale values if the branch is missing.
- `exists: false` → start fresh (state file init in Phase 1) — **after the status-mismatch guard.**
  - Check the story's BMAD status from the `story_plan.py` read (`current_status` / `next_action`).
  - `backlog`/`ready-for-dev` ⇒ start fresh.
  - **`review` or `in-progress` with NO state file** means the work happened outside auto-bmad (a hand-driven/brownfield story, or a lost state dir) — the full pipeline would re-create and re-implement an already-built story. **ASK the user** (`AskUserQuestion`):
    - **Enter at the matching phase** *(recommended — `in-progress` ⇒ Phase 5 dev-story, `review` ⇒ Phase 7 code-review; first validate that phase's `start_phase` prerequisites per `overrides.md`, hard-stop if they fail)*.
    - **Run the full pipeline anyway** (a deliberate redo).
    - **Stop**.
    - Record the chosen entry as `start_phase` in `overrides`.
- A `done` status → tell the user it's already complete and show the recorded `pr_url`; do not redo it (unless they explicitly force a re-run).
  - On a **no-arg** run — a *caveated* completion parked at `review` keeps being re-picked — also name the way forward: resolve the recorded caveat (then flip the BMAD status to `done`), or work another story via `/auto-bmad <story-id>`.

Git commits are the secondary safety net: even if the state file is lost, the per-phase commits on the story branch show how far the pipeline got.

## retro-notes/epic-{e}.md
The cross-story scratchpad the epic retrospective reads — **signal only, not a log.** After each phase, hand the agent's **Retro notes** to the deterministic writer — never append by hand:
```
python3 {skill-root}/scripts/state_update.py retro-append --retro-file <output_folder>/auto-bmad/retro-notes/epic-{e}.md --story-key {key} --json -
```
(`--json` is `{"lines": [...]}`; the script manages the one `## Story {key}` heading per story). Keep it small so it stays usable across a multi-story epic:
- **Skip empty notes** — most phases run clean: filter routine "did the work" text with your own judgment and send `none` (the script drops empty/`none` lines and then writes nothing); only genuine signal lands here.
- **One terse line per item** — a deviation / non-obvious decision / surprise / risk / deferred item; never a paragraph, never a recap of what the story file already records.

Handed to `/bmad-retrospective` at epic end as primary input — the cross-step context (autonomy choices, why things were done a certain way) the story file alone doesn't capture.

## reports/{key}.md
The per-story report is a **log**, not a single overwritten document.
- It carries only the **story-level** outputs that aren't recorded elsewhere — overrides, TEA outcomes, open questions, deferred work, blockers, next-story preview.
- The finalization **artifacts** are **chat-only** — already retrievable from git/GitHub/sprint-status.
  - These are: PR URL, CI run link, merge method + branch-deleted state, and the BMAD-status-flip outcome.
  - So the file is written **once** pre-push, never re-touched after PR/CI/merge resolve.
- The one-line **disposition** is NOT chat-only — it is a summary, not an artifact.
  - It belongs in the `Pipeline status` line.
  - It covers clean / caveated / halted, plus a draft's summary reason.
- Clean path: written + committed in **Phase 9 before push** (`docs(story-{e}-{s}): pipeline report`) so it ships in the PR diff (`pipeline.md` Phase 9; `git-and-pr.md` → "Ownership"). Any path that didn't reach that pre-push write gets the `SKILL.md` Step 3 fallback — same content, no commit (the tree is already needs-human; the human commits it alongside their fix).
- Each run (first completion OR resume) **appends** a new `## Report — <ISO timestamp>` section via `state_update.py report-section` — the script never overwrites existing sections; prior sections may hold context a resume must never clobber.
- **Each section is a session delta, not a cumulative rollup** — `Phases run` / `Skipped` cover this session alone; a resume carries a `Continues:` back-reference. Don't re-derive an earlier (possibly cross-tool) run's TEA counts or review tally into a later section.
- **Tag the `## Report` heading with this section's terminal disposition** — read the last tag to know where the story stands. Closed vocabulary: `(final)` (clean, BMAD status flipped `done`), `(final — caveated)` (finalized but left at `review`: draft PR / blocker / waived gate / CI red), `(halted — <reason>)` for a stop before Phase 9 (`needs-human`, `override stop_before: <phase>`, `override stop_after: <phase>` — the override tokens spelled as in `overrides.md`). Lineage is not in the tag — a prior section plus the `Continues:` line already mark a resume. (A clause-4 caveat — CI red/timeout — resolves only *after* the pre-push write, so it shows up in the chat report and in a later resume section's tag, never in the section written before push.)
- The **only** overwrite is a deliberate full re-run of an already-`done` story, after explicit user confirmation ("overwrite the existing report log for {key}?") — only then pass `--overwrite-confirmed` (without the flag the script always appends); if declined, append instead.
- **Epic mode** writes ONE epic report — `reports/epic-{e}.md`, via `state_update.py report-section --epic` (the epic-rollup template + its own `EPIC_REPORT_PAYLOAD_KEYS` allowlist): epic header, the per-story rollup, the integration-review + epic-gate verdicts, a single-session **UAT** checklist (`uat` — composed across all stories by the E_final `uat (epic)` consolidation), an **Auto-decided (epic mode)** section (`auto_decided` — every `[Review][Decision]` the run auto-resolved with the triage's recommendation, Tier A + E_review), and the aggregated open-findings / deferred checklist. It replaces the per-story reports (per-story detail lives in the per-story state files + the rollup), committed once pre-push as `docs(epic-{e}): pipeline report`. Same append + disposition-tag rules as above (`epic-pipeline.md` E_final).

### Section template (use literally, in this order)
This template is the **single home** for the file portion's fields, heading order, and per-field semantics.
- `SKILL.md` Step 3 only points here.
- `state_update.py report-section` renders it literally:
  - Story/Branch/Timing lines (and the `resumed N×` count) derive from the state file + prior sections.
  - Prose snippets come from `--json`.
  - A heading is never dropped — an empty field keeps its heading with `(none)`.
- Timing-split semantics: the timing fields above.

**`--json` payload keys (exact names — the script REJECTS unknown keys, because a misspelled key would silently render its heading `(none)`):** `disposition_tag` (the heading tag), `pipeline_status`, `continues`, `phases_run`, `skipped`, `overrides`, `tea`, `code_review`, `uat` (list), `open_questions` (list), `deferred_work` (list) + `deferred_archived_note` (the Phase 8 reconcile + archive line appended under it), `planning_drift`, `needs_human` (list — the ⚠️ heading), `next`, `head_sha` (the Branch line's short SHA).

```markdown
## Report — <ISO timestamp UTC> (<disposition tag — the closed vocabulary above: (final) / (final — caveated) / (halted — <reason>) — tagging the heading keeps the log skim-readable from its outline>)

**Story:** `{key}` (epic {e}, story {s}) — {first-in-epic? / last-in-epic? / mid-epic}.
**Branch:** `<branch>` (HEAD `<short-sha>`).
**Pipeline status:** <one-line summary, e.g. ✅ clean completion / halted at Phase 5 (needs-human) / draft (CI red)>.
**Continues:** <on a resume, the prior section's ISO timestamp + its tag, e.g. `2026-05-29T15:05:06Z (halted — override stop_before: 7)`; `(none — first run)` on a first run — keep the line either way, like every other heading>.

**Timing:** started <ISO>; completed <ISO, or "in progress"> — elapsed <Hh Mm> (≈<Hh Mm> AI-run, ≈<Hh Mm> human/idle wait)<; resumed N× if >1 session>.

**Phases run:** <comma-joined Phase N list for THIS session, with profile in parens for delegated phases; on a resume this is the session delta — earlier phases live in the section named by `Continues:`>.
**Skipped:** <comma-joined Phase N list with reason in parens; this session>.

**Overrides:** <one line — the invocation overrides applied this run (phase window, skips, caps); "none" if no invocation overrides applied>.

**TEA:** <which skills ran and their one-line outcome; "disabled" if tea.enabled=false; epic-gate decision if last story; for the per-story trace advisory, its verdict + any uncovered ACs (advisory, non-blocking)>.

**Code review:** <iterations run; one line each: per-iteration verdict + severity counts in the fixed form `Critical N / High N / Medium N / Low N`; then the end-of-loop HITL-halt outcome (continued / stopped / skipped (clean convergence)); and, if external-review changes triggered a post-halt re-review, its verdict/counts and the user's continue / stop decision; "skipped" if no review>.

**UAT:** <numbered manual User-Acceptance-Testing checklist — what a human can exercise BY HAND at THIS implementation state; one item per line, each an action → expected result, scoped to the acceptance criteria actually satisfied (never aspirational / full-feature steps). The producing `uat` delegate (Phase 9 head per story; E5 per story + the E_final consolidation in epic mode) ALWAYS returns ≥1 item: when nothing is manually testable yet (pure internal refactor, infra-only, no human-observable surface) it returns ONE line saying exactly that + the reason. "(none)" renders only when the step did not run — a halt before Phase 9 / E_final, or the `skip uat` override>.

**Open questions:** <numbered list, one per line — questions surfaced by any step; "(none)" if empty — keep the heading>.

**Deferred work:** <numbered list, one per line — anything intentionally postponed (also appended to the durable cross-story `<impl>/deferred-work.md` ledger; cross-link it when items landed there); on the last story of an epic, add a line from Phase 8 covering the reconcile + archive (e.g. "marked 2 missed-completions; archived 6 resolved → deferred-work-resolved.md"; name each reconcile-marked item with its one-line evidence; omit the note if nothing was marked or moved); "(none)" if empty — keep the heading>.

**Planning drift:** <epic-end only — planning assumptions the retrospective proved wrong + the recommended re-sync (document-project → generate-project-context → /bmad-prd update; /bmad-correct-course if structural); non-blocking, never auto-run; "(none)" if clean or not epic-end>.

**⚠️ Needs human:** <numbered list of blockers / manual actions. On a caveated completion these are required before the story can be considered done (it was left at `review`); on a clean completion the story is already `done` — list only genuine optional follow-ups (e.g. merging the open PR, on the human's own time) and never imply the merge gates `done`; "(none)" if clean>.

**Next:** <one line — the story `story_plan.py` would pick next; preview only — do NOT start it>.
```
