# Config, state, resume & first-run

Everything auto-bmad persists lives under `{output_folder}/auto-bmad/` (`{output_folder}` = `core.output_folder` from the BMAD central TOML config — read only through `preflight.py --central-config-only`, never by hand). One section each below:
- `config.yaml` — project config, created on first run.
- `state/{key}.yaml` — one resumable state file per story (epic mode adds the anchor `state/epic/epic-{e}.yaml`).
- `reports/{key}.md` — per-story report log, appended each run (epic mode: one `reports/epic-{e}.md`).

## config.yaml
```yaml
version: 1                          # schema version (nothing reads it; stale keys are handled by the removed-key policy below)
profiles_source_version: "0.27.2"   # abm version whose assets/profiles.yaml seeded the profiles + phase_profiles blocks below;
                                    #   restamped by the Phase 0 heal (ADDITIVE-only — never overwrites user values; see
                                    #   assets/config-defaults.yaml header) or a full `reset-defaults`
delegation:                         # spawn mechanism — host/mode re-detected every run (the stored values are inert)
  host: auto                        # auto | claude-code | codex | opencode | other
  mode: auto                        # auto (derive from host) | subagents | inline   (legacy value custom-subagents is read as subagents)
  cli_phases: {}                    # OPT-IN per-phase external-CLI routing: <phase_profiles key> -> claude|codex|opencode; empty/absent
                                    #   => every phase uses its tier. Setup answer (heal-immune), hand-edited. Semantics:
                                    #   delegation-runtime.md "Per-phase external-CLI routing"; examples: assets/config-defaults.yaml
tea:
  enabled: true                     # interviewed at first run (default yes iff bmad-testarch-* installed)
  framework_ci: prompt              # prompt | done | skip (resolved at first run)
  gate_max_iterations: 2            # Phase 8 trace-gate remediation cap (automate + re-trace) before only waive/stop are offered (constant default)
  story_trace_advisory:             # per-story, non-blocking trace pass — shifts coverage-gap visibility left on LONG epics (constant defaults)
    enabled: true                   # self-activating: dormant on short epics (see min_epic_stories), fires only on long high-risk stories
    min_epic_stories: 6             # only runs in epics with >= this many stories; short epics rely on the epic-end gate alone
    skip_last_stories: 3            # also skip the epic's last N stories (tea-policy.md §3) — their gap surfaces at the epic-end trace gate
git:
  mode: auto                        # auto -> detect | remote | local (Full setup; heal-immune)
  branch_prefix: "story/"           # constant default
  epic_branch_prefix: "epic/"       # epic mode: the one branch a whole epic run commits to (epic/{e}-{slug}) (constant default)
  base_branch: main                 # detected once; never asked; never healed
  offer_merge: true                 # Phase 9: ask whether to merge a clean-completion PR (constant default)
  ci_wait_minutes: 30               # max wait for in-progress CI before deciding (only when offer_merge is on) (constant default)
code_review:
  followup: recommended             # recommended | always | never — Phase 7 follow-up bmad-build-auto review pass on the done spec at the
                                    #   followup_review profile: recommended => only when the spec says followup_review_recommended: true;
                                    #   always => every story; never => skip (constant default)
  security_layer: true              # write the auto-bmad-security review layer into _bmad/custom/bmad-build-auto.toml (constant default)
  cross_model_layer: codex          # codex | claude | opencode | "" — external CLI for the auto-bmad-cross-model layer; ENV-DETECTED at first run
                                    #   (the first of codex, claude, opencode on PATH that is not the host, else ""); absent key => "";
                                    #   NOT in config-defaults.yaml (setup answer, heal-immune)
build:
  spec_approval: false              # opt-in per-story HITL halt between Phase 3 (plan) and Phase 4/5 (constant default; per-run override
                                    #   `approve spec`; never in epic mode)
profiles:                           # copied VERBATIM (block style) from assets/profiles.yaml at first run — model/effort ONLY, no persona
  ab-deep:                          #   strings (every delegation.md prompt is self-contained). Shown flow-style here for brevity:
    claude: {model: opus, effort: xhigh}               # claude.model = the Agent tool's per-call model; claude.effort is used ONLY by the
                                                       #   cli_phases route / cross-model layer (`claude -p --effort`)
    codex: {model: gpt-5.5, reasoning_effort: xhigh}   # both are per-call knobs of Codex's spawn_agent (and `codex exec` on the CLI route)
    opencode: {model: "", variant: ""}                 # BOTH used ONLY by the cli_phases route / cross-model layer (`opencode run -m/--variant`);
                                                       #   in-tool opencode subagents inherit the user's default model; ships BLANK (inherit)
  ab-standard: {…}                  # same field set — shipped values + what each profile drives: assets/profiles.yaml
  ab-alt-deep: {…}
  ab-alt-standard: {…}
  ab-security: {…}                  # + any CUSTOM profile (any name, same field set) — phase_profiles may name shipped or custom profiles
phase_profiles: {…}                 # build, followup_review, security_layer, cross_model_layer, tea_triage, tea_per_story, tea_epic,
                                    #   tea_epic_audit, retrospective, deferred_reconcile — the SINGLE phase->profile binding (pipeline.md /
                                    #   delegation.md name these keys, never raw profiles); git/PR work runs in the orchestrator directly —
                                    #   no delegate profile. delegation.cli_phases keys are exactly these keys
```
- **Retune paths** (write a pointer comment above the copied `profiles:` block naming both): edit the `profiles` / `phase_profiles` copy here, then `/auto-bmad reprovision` (re-syncs the review-layers TOML that bakes the `security_layer` / `cross_model_layer` models — see below); discard retunes with `/auto-bmad reset-defaults`.
- **Absent-key orchestrator fallbacks** (must equal `assets/config-defaults.yaml`): `code_review.followup: recommended`, `code_review.security_layer: true`, `build.spec_approval: false`, `git.branch_prefix: "story/"`, `git.epic_branch_prefix: "epic/"`, `git.offer_merge: true`, `git.ci_wait_minutes: 30`, `tea.gate_max_iterations: 2`, `tea.story_trace_advisory.{enabled: true, min_epic_stories: 6, skip_last_stories: 3}`, `delegation.cli_phases: {}`. Plus `code_review.cross_model_layer: ""` — an env-detected setup answer the asset deliberately omits (documented only in its header + step 0 below), so an absent key means the layer is off.
- **Removed keys (ignored).** Old configs may still carry them; `config_plan.py` ignores unknown keys and never strips them (`--check`/`--apply` report the stale ones informationally; `reset-defaults` prunes only the asset-block ones — stale `phase_profiles` mappings on `--reset both|phase_profiles`, stale per-profile sub-keys on `--reset both|profiles|<profile-name>`, whole stale profiles (`removed_profiles`, e.g. `ab-verification`) only on `--reset both|profiles`; setup-block keys are never pruned). This note is the ONE sanctioned place a shipped reference spells these names — never use, document as live, or accept them as input elsewhere: `delegation.target_tools`; `code_review.max_iterations`, `code_review.security_review`, `code_review.verification_gap`, `code_review.epic_review`, `code_review.tier_a_lenses`, `code_review.epic_diff_chunk_threshold_lines`; `phase_profiles` keys `create_story`, `dev_story`, `code_review_review`, `code_review_review_secondary`, `code_review_review_tertiary`, `code_review_security`, `code_review_verification`, `code_review_fix`, `project_context`, `uat`; profile `ab-verification`; per-profile `description` / `role_blurb` / `status_example` (persona strings — ignored if present; pruned by `--reset both|profiles|<profile-name>`). `delegation.mode: custom-subagents` in an old config is read as `subagents` (alias) and reported by `config-check` (`legacy_mode_alias`).

## First-run flow (config.yaml absent, or an explicit `setup`/`configure`/`install`)
This is the single interactive episode in normal operation. Use AskUserQuestion. It runs after the help-row registration (`assets/module-setup.md`) — `setup`/`configure`/`install` = that registration + this flow (incl. the review-layers sync in step 4). Nothing is rendered into the repo — no agent files, no restart caveat.
- **Existing config (explicit `setup`/`configure`/`install` on a provisioned project):** the same flow, prefilled with the current values. Step 0 keeps every existing key as it is (env-detects `code_review.cross_model_layer` only when the key is absent); the interview answers overwrite their own keys inside the setup blocks (`delegation`/`tea`/`git`/`code_review`/`build`) in place — every other key (e.g. `delegation.cli_phases`, `git.base_branch`) stays; step 4 leaves `profiles`/`phase_profiles`/`profiles_source_version` untouched (those are the Phase 0 heal / `reset-defaults` domain), then syncs + stops as usual.
- **Headless (`accept all defaults` / `--headless` passed through by `module-setup.md`):** no prompts — Quick depth; `tea.enabled` = whether `bmad-testarch-*` is installed; `framework_ci` = `done` when the step-0 probe finds both, else `skip` (never auto-run); everything else the seeded values. Still print the step-4 summary.

0. **Seed (non-interactive).** All of these are file-edited later, never interviewed.
   - `delegation.host` / `delegation.mode` = `auto`; `delegation.cli_phases: {}`.
   - Copy the `profiles` + `phase_profiles` blocks VERBATIM from `{skill-root}/assets/profiles.yaml`.
   - Seed `code_review.followup: recommended`, `code_review.security_layer: true`, `build.spec_approval: false`.
   - **Env-detect `code_review.cross_model_layer`:** the FIRST of `codex`, `claude`, `opencode` that is on PATH AND is not the detected host; else `""`. (A setup answer, not a shipped default — the heal never touches it; a user who wants a different tool sets it in the Full interview or in `config.yaml`.)
   - **Probe (once, both depths, headless too):** resolve host + tier per `delegation-runtime.md` → "Resolving host & mode" (config absent ⇒ pure detection), then run
     ```
     python3 {skill-root}/scripts/preflight.py --project-root <project_root> --host <host> --tier <tier> --detect-framework-ci
     ```
     (`--host`/`--tier` are required for `--detect-framework-ci`; `--central-config-only` cannot be combined with it.) Read ONLY `git.base_branch` (the seed for `git.base_branch`, step 4) and — when step 2 enables TEA — `framework.configs` (test-framework configs found) / `framework.ci_present` (CI workflow); its `hard_stop`/`hard_stop_reasons` (git tree, nesting, …) are Phase 0's concern, not the first-run flow's.
1. **Choose setup depth.** Ask **Quick** or **Full**.
   - **Quick** (recommended) — TEA only; the seeded values for everything else. Skip step 3.
   - **Full** — also git, review and build prefs.
2. **TEA (both depths).** Detect the TEA skills (`bmad-testarch-*`) and ask `tea.enabled`.
   - Default "yes" if present.
   - Default "no" if absent — don't offer yes when absent.
   - If enabled, resolve `framework_ci` from the step-0 probe's `framework.configs` / `framework.ci_present` (no second command):
     - Both present → `framework_ci: done` silently.
     - Missing → **ask** to run the one-time `/bmad-testarch-framework` + `/bmad-testarch-ci` now (delegate the `testarch-framework + testarch-ci` entry in `delegation.md` at the `tea_per_story` profile's model; on success write `framework_ci: done`) or `skip` — never auto-run unasked, because it is heavy, infra-choosing setup. Offer it only when the step-2 detection found BOTH skill dirs (`bmad-testarch-framework`, `bmad-testarch-ci`); either missing ⇒ no offer, `framework_ci: skip` + the TEA install hint.
3. **Full only — extra prefs** (each prefilled with the seeded default):
   - `git.mode` (auto | remote | local; default auto) and `git.branch_prefix` (default `story/`).
   - **Follow-up review pass** — `code_review.followup`: *recommended (default)* / *always* / *never*.
   - **Extra review layers inside build-auto** (asked once; the answer writes the project-wide `_bmad/custom/bmad-build-auto.toml` managed region — say explicitly: "these layers also run for a manual `/bmad-build-auto`"): *Security + cross-model on `<tool>`* [offered only when some external CLI ≠ host is on PATH — `<tool>` = the step-0 detected tool, labelled "(recommended)"] / *Security only* / *None*. Sets `code_review.security_layer` + `code_review.cross_model_layer`; any other tool can be set later in `config.yaml` + `/auto-bmad reprovision`.
   - **Spec approval** — `build.spec_approval`: *No (default — unattended)* / *Yes (pause after each plan for approval)*.
   - `git.base_branch` is auto-detected (the step-0 probe), never asked. Quick fills all of these with the seeded values.
4. **Write `config.yaml`** with the seeded blocks, the answers, and `git.base_branch` = the step-0 probe's `git.base_branch` (`git.mode` stays the seeded/answered toggle).
   - Above the copied `profiles:` block, write the retune-paths pointer comment (config.yaml section above).
   - Stamp `profiles_source_version` with the `module_version` from `{skill-root}/assets/module.yaml`.
   - **Then sync the review layers:**
     ```
     python3 {skill-root}/scripts/build_auto_custom.py --project-root <project_root> --config <output_folder>/auto-bmad/config.yaml --apply
     ```
     Surface its JSON (`layers`, `warnings`; `errors` / exit 2 ⇒ report the message — nothing was written — and still stop).
   - **Then stop — do not start the pipeline this session** (it would waste the context window that just did setup). Report what was configured, then: "start a fresh session and run `/auto-bmad`".

## reset-defaults — restore shipped profile defaults
`/auto-bmad reset-defaults [scope]` discards retunes in `config.yaml` and re-seeds the **asset-sourced** blocks from `{skill-root}/assets/profiles.yaml`.
- It is also the one-shot fix for a `manual_review` item the heal won't auto-write — a sub-key missing from an existing profile.
- **Config-only:** report what changed, then stop — never start a pipeline.

**Scope** (the optional arg; bare = both asset blocks):
- *(omitted)* — both `profiles` and `phase_profiles`.
- `profiles` — every profile block.
  - Also **prunes** a profile present in the config but absent from the asset — the renamed/dropped remedy; pruned names return on `removed_profiles`. Stale per-profile sub-keys (the persona strings of the removed-keys note) are dropped too (`would_change` entries with `default: null`).
  - Doesn't touch `phase_profiles` — so a *custom* mapping pointing at a pruned profile dangles (bare scope resets both; a bare/`phase_profiles` reset also drops stale mappings).
- `<profile-name>` (e.g. `ab-standard`) — that one profile. Never prunes — a user-added profile is left intact.
- `phase_profiles` — the phase→profile mapping only.

**Boundary (state it to the user).** reset-defaults touches **only** `profiles`, `phase_profiles`, and the `profiles_source_version` stamp.
- It touches **never** `delegation`/`tea`/`git`/`code_review`/`build` — because those are setup answers, not shipped defaults, and reset *overwrites* where the Phase 0 heal only *appends*, so it would clobber them.
- Redoing those is `setup`/`configure`.

**Flow:**
1. Require `config.yaml` to exist. Absent → "Nothing to reset — run `/auto-bmad setup` first." and stop.
2. Plan (read-only):
   ```
   python3 {skill-root}/scripts/config_plan.py --reset <scope> --config <output_folder>/auto-bmad/config.yaml
   ```
   (`status: error` + `valid_scopes` ⇒ unknown scope — surface and stop.) Empty `would_change`, empty `removed_profiles`, **and** no `version_restamp` → "Already at shipped defaults for `<scope>`." and stop.
3. **Confirm** with `AskUserQuestion`. This is the sole interactive moment.
   - Show the `current → default` diff from `would_change` (a `default: null` entry = a key the reset drops).
   - Call out **separately — never buried in the diff — any `removed_profiles`**: those blocks are deleted outright, so a user-added profile would be lost.
   - Options: **Reset** / **Cancel**.
   - Cancel → stop, write nothing.
4. On confirm, write by re-running with `--write` (backs the prior config up to `config.yaml.bak`, then overwrites; JSON `backup` = the path). Report the backup path and any `version_restamp`:
   - A **full** reset restamps `profiles_source_version` to the module version.
   - A **scoped** reset leaves it.
5. **Re-sync the review layers iff the plan's `layers_sync_needed` is true** — true when the plan changes or prunes any profile, or remaps `phase_profiles.security_layer` / `phase_profiles.cross_model_layer` (the two layers bake model + effort from the profiles those mappings name, so the managed TOML region is now stale). Use the same command as `reprovision`, never re-derive it:
   ```
   python3 {skill-root}/scripts/build_auto_custom.py --project-root <project_root> --config <output_folder>/auto-bmad/config.yaml --apply
   ```
   Surface its JSON (`layers`, `warnings`, `errors`). A `phase_profiles`-only reset that touches neither layer mapping never sets `layers_sync_needed`.
6. Report scope, what was reset, the backup path, restamp, and whether the review layers were re-synced. Stop.

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
   - After the two sides, add the informational stale surface (never part of the drift verdict, ignored by the heal, pruned only by `reset-defaults`): *Stale phase mappings (ignored)* from `stale_phase_profiles` and *Stale profile keys (ignored)* from `stale_profile_keys` (`{profile, key}` — e.g. an old persona string as `meta:<key>`); omit each heading when its list is empty. `legacy_mode_alias: true` ⇒ one line: *your `delegation.mode` still uses the legacy spelling — it is read as `subagents`; set it to `subagents` (or `auto`) when convenient.*
4. **Setup answers (config-check only — NOT the Phase 0 pause).** After that, render the `--check` JSON's `setup_answers` so the user sees *every* deviation — including the heal-immune answers the two diff-sides structurally cannot compare (they have no shipped default):
   - Heading *Setup answers (no shipped default — untouched by any heal)* — one `path = value` per `setup_answers` entry (`delegation.cli_phases`, `tea.enabled`, `tea.framework_ci`, `git.mode`, `code_review.cross_model_layer`).
   - Then the note: *Note: your hand-edited `delegation.cli_phases`, `tea.framework_ci` and `code_review.cross_model_layer` are setup answers, not drift — they have no shipped default to compare against, so they're never flagged as customisations and never touched by any heal (`reset-defaults` leaves them too; redo them via `setup`, or edit `config.yaml` + `/auto-bmad reprovision` for the cross-model tool).*
   - **Omit this whole block — heading and note — when `setup_answers` is empty** (nothing heal-immune to surface).
5. **Offer to apply** — the on-demand equivalent of the Phase 0 pre-run pause's "Apply defaults & continue":
   - **Pending predicate** — would `--apply` write anything: any of `missing_profiles` / `missing_phase_profiles` / `missing_setup` is non-empty, **OR** `version.drift` is true. (`manual_review` is NOT in it — the heal never auto-writes it; its fix is `reset-defaults`. Neither are the stale lists.)
   - **Predicate false** → nothing to apply; show the **How to act** guidance below and stop.
   - **Predicate true** → open an `AskUserQuestion` (the sole interactive moment):
     - **Update config to v<module> now** *(recommended)* — append the new keys/profiles/mappings and restamp `profiles_source_version`; **append-only, so every value you've set and every profile you've added is preserved**.
     - **Leave it — just previewing** — write nothing.
   - **Update** → re-run with `--apply`; confirm concisely from the `--apply` JSON — settings (`added_setup`) and preserved customisations (`kept_setup`) render exactly as the Phase 0 "Non-blocking live echo", plus the config-check-only adds the user already saw in step 3: added profiles/mappings (`reseeded_profiles` / `reseeded_phase_profiles`) and the `version_restamped` from→to. Then run the **same post-heal review-layers freshness step Phase 0 uses**: `build_auto_custom.py --check --project-root <project_root> --config <output_folder>/auto-bmad/config.yaml` — `needs_apply` ⇒ re-run it with `--apply` and echo the regenerated `layers`; `errors` ⇒ surface them (the sync is refused, nothing written). No agent-file step exists. Stop.
   - **Leave it** → show the **How to act** guidance below and stop.

**How to act** (shown whenever you don't apply):
- **Customise before applying** — edit the named keys in `config.yaml` (the heal is **append-only**, so a value you set / a profile block you add is preserved), then re-run `config-check` (or just run the story/epic; Phase 0 applies the rest).
- **Accept the new defaults** — apply now (step 5), or just run the story/epic (it auto-applies at the pre-run pause, or with `skip config-pause`).
- **Discard retunes** back to shipped values — `reset-defaults`.

- **Read-only until you confirm:** writes `config.yaml` (append-only) and re-syncs the review-layers TOML **only** on the explicit "Update" choice in step 5; the preview path never restamps and writes nothing. Never starts a pipeline.

## state/{key}.yaml
The state file is a **machine-readable contract**, not a prose log — the source of truth for resume.
- It is updated after every phase.
- `state_update.py` owns every write.
- Every field is always emitted with an explicit `null`/`false`/`[]`/`{}`.
- Prose belongs in `reports/{key}.md`, not here.

```yaml
story_key: 2-6a-digest-delivery
epic_num: 2
story_num: 6
story_suffix: "a"           # split-story suffix from the key grammar ^(\d+)-(\d+)([a-z]?)-.+ ; "" when none
branch: story/2-6a-digest-delivery
status: in-progress         # in-progress | done
updated_at: "2026-05-28T14:04:41Z"  # ISO-8601 UTC; stamped by state_update.py on every write
started_at: "2026-05-28T13:55:02Z"  # ISO-8601 UTC; stamped ONCE at the Phase 1 init, never rewritten (survives resume)
completed_at: null          # ISO-8601 UTC; set when status flips to done (Phase 9 finalize); null while in-progress
active_seconds: 0           # wall-clock spent EXECUTING phases (delegate runtime + orchestrator work up to
                            #   the pause; the state write + commit land after it), summed across sessions.
                            #   Script-owned via timing-start/-pause — never hand-add.
timing_anchor: null         # epoch seconds while a phase (or a bracketed user prompt) is executing; null when
                            #   idle. Non-null on resume = crash tail (timing notes below).
is_first_in_epic: false
is_last_in_epic: false
git_mode: remote
base_branch: main
tea_risk: high                   # low|med|high from Phase 0 triage (input: the epics doc entry); gates per-story TEA + the trace advisory
tea_selected: [atdd, automate]   # from triage; [] if trivial or TEA off; may also include trace-advisory (long-epic high-risk)
tea_rationale: "touches auth -> High risk"
epic_story_count: 12             # stories under epic {e} (from sprint-status); gates the long-epic trace advisory
stories_after_in_epic: 7         # epic stories ordered after this one (0=last); with epic_story_count, drives the trace-advisory distance gate
completed_phases: [0, 1, 2, 3]   # phase numbers from pipeline.md; gate-false no-op phases land here too (override-window skips do NOT); Phase 8 only once all six phase8_steps markers resolve
spec_path: null                  # absolute path of the story's bmad-build-auto spec (found by story_plan.py --find-spec after the Phase 3 halt); every later phase reads it from here
spec_approved: false             # true once the opt-in spec-approval halt was answered Approve, or immediately when approval is not required (build.spec_approval false and no `approve spec` override); resume re-opens the halt while false and required
build:                           # last bmad-build-auto result for this story (Phase 5, refreshed by every Phase 7 pass) — from story_plan.py --spec
  status: null                   #   draft | ready-for-dev | in-progress | in-review | done | blocked | null (not yet run)
  blocking_condition: null       #   when status is blocked: the spec's `## Auto Run Result` `Blocking condition:` line if present, else the condition the delegate reported, else "(not stated)" (the frontmatter status is authoritative; the result lines are optional — pipeline.md Phase 5)
  followup_review_recommended: false
  review_loop_iteration: 0
  deferred_count: 0              #   items in the spec's frontmatter `deferred:` list
  warnings: []                   #   spec frontmatter `warnings` (e.g. oversized, multiple-goals) — a flat list inside the map; round-trips
followup_passes: 0               # Phase 7 follow-up build-auto review passes run (incl. external-change re-reviews)
hitl_halt: null                  # Phase 7 halt outcome: "continued" | "stopped" | "skipped (clean)" | "auto-continued (epic — no halt)" | null (not yet reached)
review_unverified: false         # draft-predicate clause 2: `skip code-review`, or the spec still says followup_review_recommended: true after Phase 7's last pass (incl. followup: never) -> Phase 9 opens the PR as a draft
story_trace: null                # Phase 7 tail trace advisory: {verdict: PASS|CONCERNS|FAIL, uncovered: [..], ran: true}; non-null = done (resume marker); verdict is delegate-derived from the skill's coverage numbers — advisory only, never blocks/drafts
commits: [a1b2c3d, e4f5g6h]      # orchestrator commits (sha-lag rule) + build-auto's own commits (git log <head_before>..HEAD around every build-auto invocation — pipeline.md cross-phase rules)
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
  doc: null                      #   path of <impl>/epic-{e}-retro-<date>.md
  verdict: null                  #   accepted | accepted-with-open-items | rejected | null
  open_action_items: 0           #   open/in-progress action_items for this epic after the retro (sprint_plan.py status)
bmad_status_flipped_at: null     # 8 (pre-retro flip, last story) | 9 (finalize) | null — which phase flipped the sprint entry to done
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
overrides: {}                    # this run's normalized invocation overrides (see overrides.md); {} if none
constraints: []                  # caller-supplied constraints carried in via invocation (e.g. exact-string requirements); [] if none
```

The **timing** fields are script-owned — all clock arithmetic lives in `scripts/state_update.py`.
- Bracket work: `timing-start` before delegating a phase, `timing-pause` when it returns (just before the phase's state write + commit).
- Invert the bracket around any `AskUserQuestion` — pause before the prompt, start after — so user waits land on idle, not active. On a resume that re-opens a halt (spec-approval halt, Phase 7 `hitl_halt: stopped`) skip the `timing-pause` — the prior session already paused and the anchor is null — and `timing-start` after the prompt as usual.
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
- `completed_phases` — the epic **E-steps** as ints (`E0→0`, `E1→1`, `E2→2`, `E5→5`, `E8a→81`, `E8b→82`, `E_final→9`).
- `gate_decision` / `gate_iterations` — epic-end trace gate.
- `deferred_work_archived`.
- `review_unverified` — aggregated from the landed stories (any story's `review_unverified: true`, or the `skip code-review` override); drives the epic PR draft predicate.
- `retro` — the E8b retrospective block (`doc` / `verdict` / `open_action_items`), same shape as per story.
- `bmad_status_flipped_at` — `82` (E8b pre-retro batch flip) | `9` (E_final) | null.
- `pr_url` / `ci_run_url` / `ci_status`.
- `blockers` / `open_questions` / `deferred_work` — the epic rollup.
- The merge fields.
- `story_num` / `story_suffix` / `spec_path` / `build` / `hitl_halt` stay at their defaults — per-story concerns live in the per-story files.

Plus net-new epic fields that ride as **preserved extras** — NOT in the per-story `SCHEMA_ORDER`, so they cost no lockstep change (`state_update.py` keeps unknown fields verbatim):
- `active_story` — the loop cursor (the `{key}` being processed, or null before E5 / after E_final).
- `stories_landed` — the `{key}`s this run actually processed (drives the batch BMAD-status flip + the report rollup; E0-skipped stories never join it).
- `epic_slug` — the resolved branch/PR slug (stored so resume reuses it, never re-derives a different one).
- `stories_skipped` — the E0 skip verdicts (`"{key} — <reason>"`, e.g. `already done` or the E0 no-spec note); persisted so a resume never re-asks and E5 never enters them (never flipped, never in the rollup, listed under **Skipped**). Like `stories_landed`, a read-modify-write list — `_append` does not apply.
- `batch_flip_done` — idempotency marker for the E8b/E_final batch BMAD-status flip on resume.

Ownership split — full flow: `epic-pipeline.md`.
- The per-story `state/{key}.yaml` files still exist (one per story the loop touches) and own intra-story resume.
- The epic anchor owns *which story / which E-step*.

## Target selection & resume logic
No-arg `/auto-bmad` chooses the target story with this precedence (an explicit `--story <arg>` overrides both and targets that story directly — resolved with `story_plan.py --resolve <arg> --sprint-status <impl>/sprint-status.yaml --planning-dir <planning>`; `hard_stop` ⇒ surface the reason — not found, or ambiguous with its `candidates` — and stop):
1. **Incomplete auto-bmad pipeline first.** If any `state/*.yaml` has `status != done`, that story is the target — finish in-flight work before starting anything new.
   - State files are named `{key}.yaml` (e.g. `1-2-user-auth.yaml`) — **no `story-` prefix**.
   - The `story-{e}-{s}` form appears only in commit/PR scopes, never in a filename.
   - **Don't hand-roll shell for this** — never probe with raw shell globs (unmatched ⇒ `nomatch` abort under zsh/fish). Call the deterministic reader:
     ```
     python3 {skill-root}/scripts/state_plan.py --state-dir {output_folder}/auto-bmad/state
     ```
   - Parse its JSON:
     - `resume: true` ⇒ resume `target` (the most-recently-updated in-flight story; its record's `branch` feeds the resume preflight's `--expected-branch`); `extra_in_flight` lists any others to mention in the report.
     - `resume: false` (empty/absent dir, or all `done`) ⇒ fall through to the sprint-status pick.
   - Epic-ownership guard: `state_plan.py --state-dir … --scope epic` — an in-flight anchor whose `epic_num` matches the target's epic ⇒ hard-stop → `/auto-bmad epic --epic {e}`.
2. **Else the upstream sprint-status picker** (runs after the full preflight, which supplies `skills.sprint_plan_script`):
   ```
   uv run <sprint_plan_script> status --status-file <impl>/sprint-status.yaml --date "<now MM-DD-YYYY HH:MM>"
   ```
   - `ok: false` ⇒ hard-stop with its `error`. `all_done: true` (⇔ `recommendation` null) or `recommendation.story_key` null ⇒ hard-stop `all stories are done — nothing for auto-bmad to run` (+ ` (retrospective for epic N is still optional: run /bmad-retrospective -H N)` when `recommendation.skill == bmad-retrospective` — N = the epic number in `recommendation.reason` (`epic-N-retrospective`; the recommendation carries no epic field)).
   - Else target = `recommendation.story_key` (auto-bmad ignores `recommendation.skill`). Its precedence — `in-progress → review → ready-for-dev → backlog → retrospective` — resumes BMAD-level unfinished work first. Echo `risks` / `warnings` / `illegal` / `unrecognized` (warn: `sprint-status.yaml has illegal/unrecognized entries — run /bmad-sprint-planning validate`); keep `open_action_items` for the plan carry-over and the report.
3. Then always `story_plan.py --epic {e} --sprint-status <impl>/sprint-status.yaml --planning-dir <planning>` for the target's `is_first_in_epic` / `is_last_in_epic` / `epic_story_count` / `stories_after_in_epic` / `epic_status` / `retrospective_status` / `title` / `epic_title` (the `--resolve` output already carries the story fields; the `--epic` read is the single source in epic mode).

**Why a finished story doesn't re-stick (clean completions).**
- The sprint entry is flipped to `done` on a clean completion — Phase 8 (pre-retro flip, last story) or Phase 9 (`state_plan.py --finalize` ⇒ `flip_bmad_status: true`, run through `story_plan.py --mark-status {key} --to done`; mechanics: `pipeline.md`) — else the picker would re-recommend it. The state file goes `status: done` too.
- A **caveated** completion (draft PR / blocker / waived gate / CI red or timed-out) deliberately stays at `review` — it still needs a human, so the picker re-surfaces it (upstream priority: `review` before `ready-for-dev`/`backlog`).
- A re-run, finding state already `done`, reports it complete (rule below) instead of redoing the work.

Once the target `story_key` is known, check its state with the same reader — an exact `{key}` lookup, never a glob:
```
python3 {skill-root}/scripts/state_plan.py --state-dir {output_folder}/auto-bmad/state --story-key {key}
```
- `resume: true` (file exists, `status != done`) → **resume**:
  - Skip phases already in `completed_phases`.
  - Phase 3 routes by state `spec_path` + `story_plan.py --spec` status (the resume matrix in `pipeline.md` Phase 3): a null `spec_path` first probes `story_plan.py --find-spec`; a `draft` spec re-runs the plan; `ready-for-dev` skips the delegate; `blocked` ⇒ needs-human.
  - Spec-approval re-open rule: `3 ∈ completed_phases`, `spec_approved: false` and approval required (`build.spec_approval` or `approve spec`) ⇒ re-open the approval halt before Phase 4/5.
  - Phase 5 re-invokes build-auto with the spec path — build-auto routes by the spec's own status (`ready-for-dev` / `in-progress` / `in-review`); a `blocked` spec ⇒ needs-human (recovery text: `pipeline.md` Phase 5).
  - Phase 7: a follow-up pass is atomic — re-run it in full (never reconstruct a half-finished pass). `hitl_halt` null and a halt is due ⇒ re-open it. **`hitl_halt: stopped` with 7 ∉ `completed_phases` ⇒ re-open the halt** — reset `hitl_halt` to null and re-ask; choosing Continue then runs the git-only external-change check as usual, so edits made while stopped get their single re-review (mirrors the spec-approval Stop rule). That check — git-only, own-writes excluded, incl. the `stopped`-reopen `--since=<state updated_at>` HEAD-moved variant — is defined in `pipeline.md` Phase 7 step 3 (read `updated_at` BEFORE the re-open reset write).
  - Phase 8 resumes by its `phase8_steps` markers (first null sub-step) — except `trace_gate: failed`, a parked verdict, not a resolved one: re-delegate **`testarch-trace (epic gate)`** and re-apply its verdict handling under the same `gate_iterations` cap (`pipeline.md` Phase 8); a non-`FAIL` verdict removes the earlier FAIL entry from `blockers[]` and re-derives `gate_decision`.
  - **Blockers clear on resume.** A blocked phase's `blockers[]` entries (a Phase 3 plan-time block's result-file path; a Phase 8 trace-gate `FAIL` Stop) are live only while the block stands: when that phase later completes on resume — the Phase 3 plan succeeds, a Phase 5 / Phase 7 build-auto run returns `done`, a re-run epic trace gate returns non-`FAIL` or the human waives it (`trace_gate: waived`) — remove that phase's entries via `state_update.py set` (`blockers: [<list without them>]`) before its `phase-done` write. Epic mode's E5h rollup then carries only live blockers.
  - Re-detect git mode/branch (cheap) rather than trusting stale values if the branch is missing — the resume preflight gets `--expected-branch <state branch>` (`state_plan.py --story-key` emits `branch`).
- `exists: false` → start fresh (state file init in Phase 1) — **after the status-mismatch guard.**
  - Check the story's BMAD status from the `story_plan.py --resolve`/`--epic` read (`current_status` / the epic entry's `status`).
  - `backlog` ⇒ start fresh.
  - `ready-for-dev` ⇒ start fresh; Phase 3 first probes `story_plan.py --find-spec --impl-dir <impl> --story-key {key} --sprint-status <impl>/sprint-status.yaml` (a spec may pre-exist from a bare `/bmad-build-auto` run): found at `ready-for-dev` ⇒ adopt the spec (no plan delegate); at `draft` ⇒ draft-spec plan run; `blocked` ⇒ needs-human; `ambiguous: true` ⇒ hard-stop listing `candidates`; `found: false` ⇒ fresh plan.
  - **`review` or `in-progress` with NO state file** means the work happened outside auto-bmad (a hand-driven/brownfield story, or a lost state dir) — the full pipeline would re-plan and re-implement an already-built story. **ASK the user** (`AskUserQuestion`):
    - **Enter at the matching phase** *(recommended — `in-progress` ⇒ Phase 5 Build (needs `--find-spec` to find the spec; hard-stop otherwise), `review` ⇒ Phase 7 follow-up review (spec must be `done`; else Phase 5) — entering Phase 7 with no Phase 5 result seeds `build.*` from `story_plan.py --spec <spec_path>` and runs ONE pass regardless of the recommendation gate, `skip code-review` still wins (`pipeline.md` Phase 7); first validate that phase's `start_phase` prerequisites per `overrides.md`, hard-stop if they fail)*.
    - **Run the full pipeline anyway** (a deliberate redo).
    - **Stop**.
    - Record the chosen entry as `start_phase` in `overrides`.
  - **Sanctioned regress paths** — the ONLY places the orchestrator passes `story_plan.py --mark-status … --allow-regress`: "Run the full pipeline anyway" for an `in-progress`/`review` story (Phase 3 → `ready-for-dev`, Phase 5 → `in-progress`); entering Phase 5 for a `review` story whose spec is not `done`; a confirmed full re-run of a `done` story (below); a `start_phase` override that re-enters a phase whose target status is below the entry's current one. Any other `refusing to regress` exit is a hard-stop (the entry moved outside auto-bmad — surface the message).
- State `status: done` for the target (a completed run) → never redo silently: print the recorded report tail + `pr_url` and stop.
  - On a **no-arg** run this is the caveated case — the story sits at `review` (draft PR / blocker / waived gate / CI red), so the picker re-recommends it on every bare `/auto-bmad`. The stop text names the way forward explicitly: (1) resolve the recorded caveat, then flip the entry (`/auto-bmad --story {key}` re-opens Phase 9 only when the caveat is cleared, else it prints the same stop); (2) work another story: `/auto-bmad --story <next>` where `<next>` = the first `ready-for-dev`/`backlog` key after this one from `story_plan.py --epic {e}`, or, when the epic has none, "epic {e} has no unstarted stories — pick a key with `/auto-bmad --story <key>` or start the next epic with `/auto-bmad epic --epic <N>`". (`SKILL.md` lists this under not-silent stops.)
  - An explicit `--story {key}` on a `done` state ⇒ ask "already complete (PR …) — re-run the full pipeline anyway?" (Yes ⇒ the sanctioned regress path; No ⇒ stop).

Draft predicate: computed by `state_plan.py --finalize` (Phase 9); the four clauses are defined once in `git-and-pr.md` → "Draft predicate (clauses 1–4)" — the state fields it reads are above.

Git commits are the secondary safety net: even if the state file is lost, the per-phase commits on the story branch (and build-auto's own commits) show how far the pipeline got.

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
- **Epic mode** writes ONE epic report — `reports/epic-{e}.md`, via `state_update.py report-section --epic` (the epic-rollup template + its own `EPIC_REPORT_PAYLOAD_KEYS` allowlist): epic header, the per-story rollup, the skipped stories, the epic-gate + TEA outcomes, the retrospective verdict, and the aggregated open-questions / deferred checklist. It replaces the per-story reports (per-story detail lives in the per-story state files + the rollup), committed once pre-push as `docs(epic-{e}): pipeline report`. Same append + disposition-tag rules as above (`epic-pipeline.md` E_final).
  **`--json` payload keys (exact names — unknown keys are REJECTED):** `disposition_tag`, `pipeline_status`, `continues`, `epic_summary`, `story_rollup` (list — one line per landed story: build status / review passes / deferred / trace), `stories_skipped` (list — one line per story with its reason: `already done` or the E0 skip note), `epic_gate`, `tea`, `retro` (verdict + open action items + doc path), `overrides`, `open_questions` (list), `deferred_work` (list) + `deferred_archived_note`, `needs_human` (list), `next` (includes the `/bmad-project-context refresh` recommendation), `head_sha`.
  Rendered order: **Epic** / **Branch** / **Pipeline status** / **Continues** / **Summary** / **Timing** / **Stories** / **Skipped** / **Epic gate** / **TEA** / **Retrospective** / **Overrides** / **Open questions** / **Deferred work** / **⚠️ Needs human** / **Next**.

### Section template (use literally, in this order)
This template is the **single home** for the file portion's fields, heading order, and per-field semantics.
- `SKILL.md` Step 3 only points here.
- `state_update.py report-section` renders it literally:
  - Story/Branch/Timing lines (and the `resumed N×` count) derive from the state file + prior sections.
  - Prose snippets come from `--json`.
  - A heading is never dropped — an empty field keeps its heading with `(none)`.
- Timing-split semantics: the timing fields above.

**`--json` payload keys (exact names — the script REJECTS unknown keys, because a misspelled key would silently render its heading `(none)`):** `disposition_tag` (the heading tag), `pipeline_status`, `continues`, `phases_run`, `skipped`, `overrides`, `tea`, `build`, `review`, `retro`, `open_questions` (list), `deferred_work` (list) + `deferred_archived_note` (the Phase 8 reconcile + archive line appended under it), `needs_human` (list — the ⚠️ heading), `next`, `head_sha` (the Branch line's short SHA). The **Spec** line is not a payload key — it renders the state's `spec_path`.

Renderer defaults when a key is absent: `Overrides` → `none`, `Build` → `not run`, `Review` → `skipped`, `Retrospective` → `(none)`, `Continues` → `(none — first run)`, every list block → `(none)`.

```markdown
## Report — <ISO timestamp UTC> (<disposition tag — the closed vocabulary above: (final) / (final — caveated) / (halted — <reason>) — tagging the heading keeps the log skim-readable from its outline>)

**Story:** `{key}` (epic {e}, story {s}) — {first-in-epic? / last-in-epic? / mid-epic}.
**Spec:** `<spec_path>` (from state; `(none)` before Phase 3)
**Branch:** `<branch>` (HEAD `<short-sha>`).
**Pipeline status:** <one-line summary, e.g. ✅ clean completion / halted at Phase 5 (needs-human: build-auto blocked) / draft (CI red)>.
**Continues:** <on a resume, the prior section's ISO timestamp + its tag, e.g. `2026-05-29T15:05:06Z (halted — override stop_before: 7)`; `(none — first run)` on a first run — keep the line either way, like every other heading>.

**Timing:** started <ISO>; completed <ISO, or "in progress"> — elapsed <Hh Mm> (≈<Hh Mm> AI-run, ≈<Hh Mm> human/idle wait)<; resumed N× if >1 session>.

**Phases run:** <comma-joined Phase N list for THIS session, with profile/model in parens for delegated phases; on a resume this is the session delta — earlier phases live in the section named by `Continues:`>.
**Skipped:** <comma-joined Phase N list with reason in parens; this session>.

**Overrides:** <one line — the invocation overrides applied this run (phase window, skips, approve spec); "none" if no invocation overrides applied>.

**TEA:** <which skills ran and their one-line outcome; "disabled" if tea.enabled=false; epic-gate decision if last story; for the per-story trace advisory, its verdict + any uncovered ACs (advisory, non-blocking)>.

**Build:** <build-auto result: spec status; review_loop_iteration; deferred N (harvested to the ledger); warnings; commits by build-auto; "not run" if Phase 5 never ran>.

**Review:** <follow-up passes N (profile / cli route); last pass patch/bad_spec/defer/reject counts; followup still recommended?; HITL halt outcome (continued / stopped / skipped (clean) / auto-continued (epic — no halt)); review_unverified; "skipped" if no follow-up review>.

**Retrospective:** <epic-end only: verdict; N open action items (listed); doc path; "(none)" otherwise>.

**Open questions:** <numbered list, one per line — questions surfaced by any step; "(none)" if empty — keep the heading>.

**Deferred work:** <numbered list, one per line — anything intentionally postponed (also harvested into the durable cross-story `<impl>/deferred-work.md` ledger; cross-link it when items landed there); on the last story of an epic, add a line from Phase 8 covering the reconcile + archive (e.g. "marked 2 missed-completions; archived 6 resolved → deferred-work-resolved.md"; name each reconcile-marked item with its one-line evidence; omit the note if nothing was marked or moved); "(none)" if empty — keep the heading>.

**⚠️ Needs human:** <numbered list of blockers / manual actions. On a caveated completion these are required before the story can be considered done (it was left at `review`); on a clean completion the story is already `done` — list only genuine optional follow-ups (e.g. merging the open PR, the AGENTS.md block missing) and never imply the merge gates `done`; "(none)" if clean>.

**Next:** Human review: `/bmad-checkpoint-preview <pr_url | branch>` (spec: `<spec_path>`); then `/auto-bmad` (sprint_plan.py status recommends the next story). <epic end: "Project context: run /bmad-project-context refresh (recommended after an epic)."> — preview only; do NOT start the next story.
```
