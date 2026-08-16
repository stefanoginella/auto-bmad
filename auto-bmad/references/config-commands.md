# Config commands — first-run setup, reset-defaults, config-check

What it holds: the three interactive config flows (`setup`/`configure`/`install` first-run, `reset-defaults`, `config-check`) plus the drift-report rendering they share with the Phase 0 / E0 pre-run pause. The `config.yaml` schema itself stays in `state-and-resume.md`.
When it is loaded: an explicit config command (`setup` / `configure` / `install` / `reprovision` / `reset-defaults` / `config-check`); a missing `config.yaml` on a run-intent invocation; or the Phase 0 / E0 pre-run pause needing the drift-report rendering. A normal story run never reads it.

## First-run flow (config.yaml absent, or an explicit `setup`/`configure`/`install`)
This is the single interactive episode in normal operation. Use AskUserQuestion. It runs after the help-row registration (`assets/module-setup.md`) — `setup`/`configure`/`install` = that registration + this flow (incl. the review-layers sync in step 4). Nothing is rendered into the repo — no agent files, no restart caveat.
- **Existing config (explicit `setup`/`configure`/`install` on a provisioned project):** the same flow, prefilled with the current values. Step 0 keeps every existing key as it is (env-detects `code_review.cross_model_layer` only when the key is absent); the interview answers overwrite their own keys inside the setup blocks (`delegation`/`tea`/`git`/`code_review`/`build`) in place — every other key (e.g. `delegation.cli_phases`, `git.base_branch`) stays; step 4 leaves `profiles`/`phase_profiles`/`profiles_source_version` untouched (those are the Phase 0 heal / `reset-defaults` domain), then syncs + stops as usual.
- **Headless (`accept all defaults` / `--headless` passed through by `module-setup.md`):** no prompts — Quick depth; `tea.enabled` = whether `bmad-testarch-*` is installed; `framework_ci` = `done` when the step-0 probe finds both, else `skip` (never auto-run); everything else the seeded values. Still print the step-4 summary.

0. **Seed (non-interactive).** All of these are file-edited later, never interviewed.
   - `delegation.host` / `delegation.mode` = `auto`; `delegation.cli_phases: {}`.
   - Copy the `profiles` + `phase_profiles` blocks VERBATIM from `{skill-root}/assets/profiles.yaml`.
   - Seed `code_review.followup: recommended`, `code_review.security_layer: true`, `build.spec_approval: false`.
   - **Env-detect `code_review.cross_model_layer`:** the FIRST of `codex`, `claude`, `opencode` that is on PATH AND is not the detected host; else `""`. (A setup answer, not a shipped default — the heal never touches it; change it in the Full interview or in `config.yaml`.)
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
     - Missing → **ask** to run the one-time `/bmad-testarch-framework` + `/bmad-testarch-ci` now (delegate the `testarch-framework + testarch-ci` entry in `delegation.md` at the `tea_per_story` profile's model; on success write `framework_ci: done`) or `skip` — never auto-run unasked. Offer it only when the step-2 detection found BOTH skill dirs (`bmad-testarch-framework`, `bmad-testarch-ci`); either missing ⇒ no offer, `framework_ci: skip` + the TEA install hint.
3. **Full only — extra prefs** (each prefilled with the seeded default):
   - `git.mode` (auto | remote | local; default auto) and `git.branch_prefix` (default `story/`).
   - **Follow-up review pass** — `code_review.followup`: *recommended (default)* / *always* / *never*.
   - **Extra review layers inside build-auto** (asked once; the answer writes the project-wide `_bmad/custom/bmad-build-auto.toml` managed region — say explicitly: "these layers also run for a manual `/bmad-build-auto`"): *Security + cross-model on `<tool>`* [offered only when some external CLI ≠ host is on PATH — `<tool>` = the step-0 detected tool, labelled "(recommended)"] / *Security only* / *None*. Sets `code_review.security_layer` + `code_review.cross_model_layer`; any other tool can be set later in `config.yaml` + `/auto-bmad reprovision`.
   - **Spec approval** — `build.spec_approval`: *No (default — unattended)* / *Yes (pause after each plan for approval)*.
   - `git.base_branch` is auto-detected (the step-0 probe), never asked. Quick fills all of these with the seeded values.
4. **Write `config.yaml`** with the seeded blocks, the answers, and `git.base_branch` = the step-0 probe's `git.base_branch` (`git.mode` stays the seeded/answered toggle).
   - Above the copied `profiles:` block, write the retune-paths pointer comment (`state-and-resume.md` → config.yaml).
   - Stamp `profiles_source_version` with the `module_version` from `{skill-root}/assets/module.yaml`.
   - **Then sync the review layers:**
     ```
     python3 {skill-root}/scripts/build_auto_custom.py --project-root <project_root> --config <output_folder>/auto-bmad/config.yaml --apply
     ```
     Surface its JSON (`layers`, `warnings`; `errors` / exit 2 ⇒ report the message — nothing was written — and still stop).
   - **Then stop — do not start the pipeline this session.** Report what was configured, then: "start a fresh session and run `/auto-bmad`".

## reset-defaults — restore shipped profile defaults
`/auto-bmad reset-defaults [scope]` discards retunes in `config.yaml` and re-seeds the **asset-sourced** blocks from `{skill-root}/assets/profiles.yaml`.
- It is also the one-shot fix for a `manual_review` item the heal won't auto-write — a sub-key missing from an existing profile.
- **Config-only:** report what changed, then stop — never start a pipeline.

**Scope** (the optional arg; bare = both asset blocks):
- *(omitted)* — both `profiles` and `phase_profiles`.
- `profiles` — every profile block.
  - Also **prunes** a profile present in the config but absent from the asset; pruned names return on `removed_profiles`. Stale per-profile sub-keys (the persona strings of the removed-keys note) are dropped too (`would_change` entries with `default: null`).
  - Doesn't touch `phase_profiles` — so a *custom* mapping pointing at a pruned profile dangles (bare scope resets both; a bare/`phase_profiles` reset also drops stale mappings).
- `<profile-name>` (e.g. `standard`) — that one profile. Never prunes — a user-added profile is left intact.
- `phase_profiles` — the phase→profile mapping only.

**Boundary (state it to the user).** reset-defaults touches **only** `profiles`, `phase_profiles`, and the `profiles_source_version` stamp.
- It **never** touches `delegation`/`tea`/`git`/`code_review`/`build` — those are setup answers, not shipped defaults; redo them with `setup`/`configure`.

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
- Run it before a story/epic to see the new profiles/settings an update shipped and decide whether to retune *before* they take effect. The same drift data drives the automatic Phase 0 / E0 **pre-run pause** (`pipeline.md`).
- **Config-only:** report (and, if you confirm, apply), then stop — never start a pipeline.

**Flow:**
1. Require `config.yaml` to exist. Absent → "auto-bmad isn't set up here yet — run `/auto-bmad setup`." and stop.
2. Read drift (read-only):
   ```
   python3 {skill-root}/scripts/config_plan.py --check --config <output_folder>/auto-bmad/config.yaml
   ```
3. Render the **drift report** exactly as "Drift report rendering" below specifies — the two sides (*New since v<config>* + *Your customisations*), preceded by a version line (`config v<config> → module v<module>`), read straight from the `--check` JSON — **never read code**.
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

## Drift report rendering
Shared by the `config-check` command above and the Phase 0 / E0 pre-run pause (`pipeline.md` → Phase 0 step 4, `epic-pipeline.md` → E0 step 4). From the `--check` JSON, two sides, omitting any empty sub-list or side:
- **New since v<config> (would be added):** *New profiles* — `name — <summary>` per `missing_profiles` (`missing_profile_summaries`); *New phase mappings* — `phase → profile` per `missing_phase_profiles`; *New settings* — `path = value` per `added_setup`; *Profile sub-keys you could set* — `profile.key` per `manual_review` (not auto-written).
- **Your customisations (preserved by the append-only heal):** *Profile retunes* — `profile.key = value  (default <default>)` per `customized_profiles`; *Custom profiles* — `name` per `custom_profiles`; *Remapped phases* — `phase = profile  (default <default>)` per `customized_phase_profiles`; *Settings* — `path = value  (default <default>)` per `kept_setup`.
- Then the informational stale surface (ignored by the heal, pruned only by `reset-defaults`): *Stale phase mappings (ignored)* from `stale_phase_profiles`; *Stale profile keys (ignored)* from `stale_profile_keys`; `legacy_mode_alias: true` ⇒ one line noting `delegation.mode` is read as `subagents`.
