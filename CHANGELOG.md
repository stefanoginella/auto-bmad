# Changelog

All notable changes to **auto-bmad** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> Maintainers: add notes under **[Unreleased]** as you go (under the right
> heading — Added/Changed/Deprecated/Removed/Fixed/Security). At release time
> `scripts/bump-version.py <patch|minor|major>` promotes that section to the new
> version, bumps both version files, commits, and tags. A release is **blocked**
> if `[Unreleased]` is empty. See CLAUDE.md → "Releasing".

## [Unreleased]

### Fixed

- **Delegate agents now load on Windows.** Rendered `ab-*` agent files were written via
  `Path.write_text`, whose text-mode `\n`→`\r\n` translation produced a `---\r` frontmatter fence
  that Claude Code's subagent parser silently rejects; they now emit LF on every platform.

### Changed

- **Verified against BMAD-METHOD 6.9.0.** The new minor ships no change to any skill auto-bmad
  delegates to or any contract it parses; compat markers advanced from 6.8.x.

## [0.25.1] - 2026-06-16

### Changed

- **`config-check` now shows your hand-edited setup answers too.** `delegation.cli_phases`,
  `tea.framework_ci`, a forced `git.mode` and the like — with a note that no heal ever touches them.
- **`config-check` now offers to apply the update at the end.** It asks whether to merge the new
  keys/profiles and restamp the version — append-only, so your edits survive; read-only until you confirm.

## [0.25.0] - 2026-06-16

### Added

- **`config-check` previews config/profile drift before a run.** Read-only: what an update would add
  (new profiles, settings, mappings) and what you've retuned vs the defaults — applies nothing.

### Changed

- **New config now pauses for review before a run.** When an update ships new profiles/settings the run
  pauses so you can customise first (epic: once at start); skip with `skip config-pause`.

## [0.24.0] - 2026-06-16

### Added

- **Reports now include a manual UAT checklist.** Concrete `action → expected result` checks for what
  a human can verify by hand at the current implementation state — per story, and one consolidated
  single-session checklist in epic mode; the section says so when nothing is manually testable.

### Changed

- **Epic mode auto-resolves review decisions instead of asking.** `[Review][Decision]` findings now
  proceed with the reviewer's recommended fix/defer/dismiss — no human ask, not even at epic end — and
  a Critical/High auto-decision ships the PR as a draft. Each is listed in the epic report's new
  Auto-decided section (epic-pipeline.md, delegation.md).
- **Epic mode no longer halts on an unconverged review.** The end-of-epic convergence halt is gone; an
  unconverged or lens-incomplete review ships a draft PR with the findings flagged for attention.

### Fixed

- **External-CLI delegates now wait on real process exit, not a fragile poll loop.** A new
  `cli_delegate.py --wait`/`--once` keys completion on an exit-code sentinel, so a routed step can run
  for hours without a wall-clock kill and stale watch loops no longer spin forever.
- **Runtime grep no longer misses instruction phrases split across a line wrap.** The orchestrator's
  nine AI-read instruction files are now one physical line per paragraph/list item, so no matched
  phrase straddles a hard wrap. Whitespace-only — not a word changed.

## [0.23.0] - 2026-06-14

### Added

- **Epic end reconciles deferred work before archiving it.** A new delegated pass marks any ledger
  item whose deferred work actually landed during the epic but went unmarked, so finished work stops
  being re-folded into future stories instead of lingering open forever. Conservative by design — it
  marks only on unambiguous evidence and keeps anything in doubt (pipeline.md, delegation.md).

## [0.22.1] - 2026-06-14

### Fixed

- **Setup no longer breaks on BMAD 6.8.x's TOML config layout.** auto-bmad self-registers via the
  shared help CSV + its own runtime config instead of writing the now-installer-owned central
  config, so first-run completes and delegate agents render on TOML-layout installs.

## [0.22.0] - 2026-06-14

### Added

- **`/auto-bmad epic` runs an entire epic in one run.** The autonomous create-story → dev-story loop
  per story (each with a thin review+fix), then one epic-wide integration review (the single human
  halt) on one `epic/N-slug` branch → one PR. Warns + confirms first; completes a half-done epic.

## [0.21.0] - 2026-06-14

### Added

- **Code review now runs a dedicated security review each story.** A high-signal security pass
  (Anthropic-style exclusions) hunts exploitable vulnerabilities every Phase 7 iteration; a
  Critical/High gates the loop. On by default (`code_review.security_review`).
- **README now records TEA (test-architecture) module compatibility.** A second compat badge and
  blockquote clause track the separately versioned `bmad-method-test-architecture-enterprise` skill
  line (currently 1.19.x), which ships the `testarch` skills auto-bmad runs. (README)

### Changed

- **Code-review triage no longer floods stories with low-severity noise.** Cosmetic, hypothetical,
  and already-guarded Low findings are now dismissed (and counted in the report); genuine Lows are
  still kept or deferred.

## [0.20.2] - 2026-06-13

### Changed

- **Clarified what version a custom-source install resolves.** A bare `--custom-source` URL tracks
  `main` HEAD; pin a release with an `@<tag>` suffix (BMAD's `--channel` flags don't apply to
  custom-source URLs). (README)

### Fixed

- **Codex delegates no longer fail inside nested containers/sandboxes.** They now run with full
  bypass-permissions (no inner OS sandbox) in every environment, matching the Claude/opencode delegates;
  run auto-bmad in an outer sandbox.

## [0.20.1] - 2026-06-11

### Fixed

- **CLI-routed delegates no longer fail to launch under zsh.** The orchestrator must serialize the
  helper's `argv` as literal tokens or a zsh array — never a `$OC` scalar, which zsh leaves unsplit.
  (delegation-runtime.md)

## [0.20.0] - 2026-06-11

### Added

- **The Phase 7 halt can now run another review iteration.** Extends the loop past the cap one
  full-roster pass at a time; also offered at the re-ask as the in-pipeline fix loop. (pipeline.md)
- **The Phase 7 re-ask can now ship the PR as ready instead of draft.** Sets the `no_pr_draft`
  override so Phase 9 opens a non-draft PR; the run stays caveated. (pipeline.md, overrides.md)

### Changed

- **CLI-routed review lenses now run in parallel on every host.** Each routed reviewer's three
  lenses launch as concurrent background processes; the triage waits for all. (delegation-runtime.md)
- **In-tool review lenses now fan out in parallel on every host.** Codex and opencode parallel
  subagent fan-out is confirmed — the sequential-lens fallback is gone. (delegation-runtime.md)

### Fixed

- **Findings grouped under subheadings no longer escape the Phase 7 gate.** Deeper headings inside
  `### Review Findings` are internal grouping, not a section end; the deferred-work ledger parsers
  follow the same rule. (review_findings.py, deferred_ledger.py)
- **CLI-routed delegates no longer time out mid-run.** `cli_phases` invocations run in the
  background with a ≥30-minute allowance, beyond host foreground shell caps. (delegation-runtime.md)

## [0.19.0] - 2026-06-11

### Added

- **Custom delegate profiles.** Add your own `ab-*` profile to the config's `profiles` block (same
  field set as the shipped ones), map phases to it, and `/auto-bmad reprovision` renders it for
  every target tool. A whole-block `reset-defaults` still prunes custom profiles (confirmed first);
  a scoped reset leaves them intact.

### Changed

- **Generic-subagent and CLI-routed delegates now take their persona from your config.** Tier 2 and
  `cli_phases` prompts substitute `role_blurb`/`status_example` from the runtime config's `profiles`
  block (where retunes and custom profiles live), falling back to the shipped asset only when the
  config lacks the strings. (delegation-runtime.md)

### Fixed

- **opencode CLI routes no longer hard-stop on commands-based BMAD installs.** The `cli_phases`
  preflight now also recognizes BMAD slash-command files (`.opencode/command(s)/bmad-*.md`, project
  or user-global), not just `skills/` dirs.

## [0.18.0] - 2026-06-11

### Added

- **Optional third review model: `code_review_review_tertiary`.** Map the new `phase_profiles` slot
  to a profile to add a third independent reviewer to every review pass; ships blank (disabled).

### Changed

- **All configured review models now review every pass in parallel.** Each Phase 7 iteration fans
  the three review lenses out once per configured reviewer (3, 6, or 9 lens delegates) and a single
  triage — always at the primary profile — dedupes across all of them. The post-halt external-change
  re-review runs the same full roster.
- **The secondary review model is now optional.** Blank out `code_review_review_secondary` in
  `phase_profiles` for a single-model review; it still ships enabled (`ab-alt-deep`).
- **A review pass with only Low-severity findings now converges, whatever the count.** The
  ≤3-findings cap still applies when any finding is Medium or above; a first pass with findings
  still pulls the mandatory second review iteration.
- **The post-halt re-review of external changes is now single-shot.** Changes added during the
  Phase 7 halt still get committed and re-reviewed by the full roster; meaningful findings now
  re-ask once — continue (PR ships as a draft with the findings open) or stop — instead of the
  fix / fix-and-re-review / ignore rounds. Stop, fix, and re-run `/auto-bmad` to re-review fixes.
- **A crash mid review iteration now resumes by re-running the iteration.** The `review_gate`
  mid-iteration resume capsule is gone from the state schema; a stale field in an existing state
  file is preserved untouched and ignored.

### Removed

- **`code_review.alternate_models` is gone.** Review models no longer alternate by iteration — every
  configured reviewer runs on every pass. A stale key left in an existing config is ignored.
- **`code_review.skip_hitl_on_clean_convergence` is gone — a clean convergence always auto-continues.**
  The Phase 7 HITL halt now fires only when the review did not converge cleanly; there is no opt-out.
  A stale key left in an existing config is ignored (use the `stop after phase 7` override to force a
  stop on a given run).

## [0.17.3] - 2026-06-11

### Changed

- **Phase 7 HITL halt now skips by default on a clean convergence.** New installs no longer pause for
  a human when the review loop converges cleanly (no Critical/High, ≤3 minor findings, full lens
  coverage); the halt still fires on any non-converged, incomplete-lens, or Critical/High exit.
  Existing configs keep their current value — the append-only heal never overwrites it.
  (`code_review.skip_hitl_on_clean_convergence`)

## [0.17.2] - 2026-06-10

### Changed

- **Verified compatibility with BMAD 6.8.1-next.6.** The only upstream change since 6.8.1-next.5
  clarifies how `bmad-code-review` delivers the diff to its Blind Hunter lens; no contract auto-bmad
  parses or replicates moved. (README compat markers advanced)

## [0.17.1] - 2026-06-10

### Changed

- **A converged single review pass no longer ships as an unverified draft.** Setting
  `code_review.max_iterations: 1` now counts as explicit consent to a single-pass review. (review_loop.py, pipeline.md)

## [0.17.0] - 2026-06-10

### Added

- **State files are written by a deterministic script, not hand-rolled YAML.** New
  `state_update.py`: full-schema writes, timestamp stamping, a `started_at` guard, and all timing
  arithmetic; older state files migrate on their next write.

- **A crash mid-Phase-8 resumes at the first unfinished sub-step.** Per-sub-step `phase8_steps`
  markers; completed epic-end delegations never re-run.

- **Report sections and retro notes are rendered deterministically.** `report-section` emits the
  literal template (append-only); `retro-append` writes nothing when there is nothing to say.

- **Phase 0 preflight is one deterministic script call.** `preflight.py` replaces ~8 hand-rolled
  shell probes with a single JSON answer and built-in hard-stop rules.

- **Phase 7's review-loop decisions are scripted, not prose.** New `review_loop.py`: diff prep,
  the continue/exit/halt gate, and a self-test pinning the full decision table.

- **Every code-review fix pass is verified before the next gate.** A post-fix re-check retries a
  half-done fix once, then escalates to `needs-human`.

- **`story_plan.py --mark-done` flips a story's BMAD status to `done`.** Idempotent and
  byte-preserving; replaces the Phase 9 hand-edit.

- **`state_plan.py --finalize` decides draft vs clean completion.** Evaluates the four
  draft-predicate clauses; `--no-pr-draft` changes only `draft`.

### Changed

- **Phase 9's CI wait runs as a deterministic script.** `ci_wait.py` polls `gh pr checks`, pins
  the `ci_status` verdict, and resolves the run URL by head SHA.

- **Phase 8 deferred-work archiving is script-driven, not a hand-edit.** `deferred_ledger.py`
  moves entries atomically (sha-guarded); only the keep-vs-move judgment stays with the LLM.

- **The per-story report field spec has a single home.** The `state-and-resume.md` Section
  template; SKILL.md Step 3 just points there.

- **The runtime reference docs are ~13% shorter with zero contracts lost.**

- **Code-review severity is read from the story file, not the reviewer's chat.** Triage tags
  every finding (`[Review][Patch][High] …`); an untagged finding counts as Critical/High.
  Takes effect on module update — no reprovision needed.

- **`skip code-review` now ships a draft PR and leaves the story at `review`.** Zero review
  passes sets `convergence_unverified`; `no_pr_draft` still forces a non-draft PR.

- **A run already caveated as a draft skips the Phase 9 CI wait.** `ci_status` stays `unknown`;
  the run is still linked.

- **A `review`/`in-progress` story with no auto-bmad state now asks before re-running the
  pipeline.** Enter at the matching phase, redo in full, or stop.

- **opencode runs the three review lenses sequentially.** Parallel fan-out is unverified there.

- **A story stuck at `review` after a caveated run gets move-on guidance.** Names the caveat and
  the `/auto-bmad <story-id>` escape.

- **Code-review temp dirs are cleaned up after each iteration.** Kept, with the path surfaced,
  on a `needs-human` exit.

- **The external-change re-review asks the script whether changes are meaningful.** New
  `review_loop.py converged` mode owns the threshold; pipeline.md's gate table is now a courtesy
  copy of the normative script.

- **A hard-stop before Phase 1 can still write its report.** `report-section
  --allow-missing-state`; Phase 0 decisions now ride in Phase 1's `init --json`.

### Fixed

- **An indented code fence can no longer swallow live ledger entries.** Fences are tracked at any
  indent with one shared open/close rule, removing the state-inversion bug class from `archive`.

- **Fenced examples no longer count as review findings or ledger entries.** `review_findings.py`
  shares `deferred_ledger.py`'s fence grammar (lockstep-pinned by self-test).

- **An earlier pass's bullets can no longer satisfy a later pass's persistence gate.** The
  reconciliation now gates on growth above `--baseline`, not the cumulative total.

- **A transient empty CI board after real checks no longer classifies `none`.** The grace window
  obeys the same never-`none`-after-real-checks rule as the cap verdict.

- **A `phase-done` patch can no longer silently drop the phase it records.** `completed_phases`
  in the folded patch is rejected before any write.

- **A misspelled report payload key fails loud instead of rendering `(none)`.** Unknown keys are
  rejected; the key↔heading map is documented next to the Section template.

- **A quoted comma in a blocker no longer splits it into two blockers.** A new round-trip
  self-test pins `state_plan.py`'s readers to `state_update.py`'s writer output.

- **Atomic file replaces no longer reset permissions or collide on a fixed temp name.**

- **A bold-wrapped severity tag after a space no longer reads as untagged.**
  `[Review][Patch] **[High]**` parses as High.

- **`gh pr merge` no longer predictably fails on protected branches after the finalize push.**
  On pending required checks it retries once with `--auto`.

- **A perfectly clean review pass no longer false-fails the reconciliation gate.**
  `--expect-min 0` accepts a story with no `### Review Findings` section.

- **A crash between Phase 2's sub-steps no longer skips the epic test design on resume.**

- **The story branch is created explicitly off the base branch.** An unrelated starting branch
  can no longer leak its commits into the story PR.

## [0.16.0] - 2026-06-09

### Added

- **Optional auto-continue past the Phase 7 review halt on a clean convergence.** New
  `code_review.skip_hitl_on_clean_convergence` (default `false`) — when `true`, the end-of-loop HITL
  halt is skipped if the loop converged cleanly, and still fires otherwise. Skipping forgoes the
  external-review recommendation and the Stop option for those stories.

### Changed

- **Delegate profiles renamed to role-tier names.** `ab-xhigh`/`ab-high`/`ab-alt-xhigh`/`ab-alt-high`
  became `ab-deep`/`ab-standard`/`ab-alt-deep`/`ab-alt-standard`, so a name no longer bakes in the
  Claude/Codex effort string (opencode has no effort knob, and effort is retunable). Existing projects
  keep running on their old config until you re-seed: `/auto-bmad reset-defaults` then `/auto-bmad reprovision`.

- **`reset-defaults` now prunes profiles the shipped asset dropped.** A whole-block reset (`profiles`
  or both) removes profile blocks absent from the asset so the config matches shipped exactly — the
  clean migration for a renamed profile — and the confirmation lists what it will delete. A
  single-profile reset still leaves a user-added profile untouched.

- **Fresh `config.yaml` now shows `cli_phases` usage examples.** The generated `delegation.cli_phases`
  comment carries a few copy-paste examples (e.g. routing the secondary review to another vendor via
  opencode), so opt-in per-phase external-CLI routing is discoverable without hunting the docs.

### Fixed

- **`code_review.max_iterations: 1` no longer ships an unverified review as a non-draft PR.** A
  single review pass that found work (or ran with a failed lens) now exits with
  `convergence_unverified` set, so Phase 9 opens a draft — matching the ≥ 2 cap-unconverged exit and
  the state schema. Only a perfectly-clean single pass ships non-draft. (pipeline.md)

- **`cli_phases` validation error no longer omits `opencode`.** A bad `cli_phases` tool now reports the
  full accepted set (`claude`, `codex`, `opencode`); the message previously listed only the first two
  despite opencode being a valid target.

## [0.15.0] - 2026-06-09

### Added

- **opencode is now a supported delegation host.** Delegate steps to opencode on any provider/model
  you've configured (Anthropic, DeepSeek, Qwen, a local model); agents render to `.opencode/agent/`
  and inherit your opencode default model unless you set `opencode.model` per profile — so the
  secondary reviewer can run on a different vendor for cross-model review diversity. opencode is also
  an opt-in per-phase `cli_phases` target.

## [0.14.0] - 2026-06-09

### Added

- **New setup-block defaults now reach an existing `config.yaml` on update.** The preflight
  config-drift heal also appends constant-default keys the config is missing in the
  `delegation`/`tea`/`git`/`code_review` blocks (e.g. `git.offer_merge`, `tea.story_trace_advisory`) —
  previously only `profiles`/`phase_profiles` self-healed, so a new setup key stayed invisible until a
  Full re-`configure`. Append-only: your existing values are never touched, and environment-detected
  fields (`git.base_branch`, `delegation.target_tools`, …) are deliberately left to runtime detection.

- **The heal now shows what it changed.** When it adds setup keys, the preflight prints the new
  keys (with values) and any of your customizations it kept — non-blocking, so the pipeline continues
  without a prompt (the additions are behavior-neutral, matching the defaults already in effect).

- **Any pipeline phase can now be delegated to an external CLI instead of an in-tool sub-agent.** Set
  `delegation.cli_phases` in `config.yaml` (e.g. `{ code_review_review_secondary: codex }`) to run a
  chosen phase via `claude -p` or `codex exec` for cross-tool diversity; model + effort come from that
  phase's profile. Opt-in and off by default — all phases use in-tool agents unless you route them.

## [0.13.6] - 2026-06-08

### Changed

- **Lower-stakes pipeline steps now run at reduced reasoning effort.** Cheaper and faster: the
  epic-end NFR and test-review gates drop one tier to `ab-high` (the blocking trace gate and the
  high-stakes steps — dev, create-story, primary review — keep full depth), and per-story risk
  triage + the epic retrospective drop to `medium`. **Upgraders:** the `tea_epic_audit` mapping is
  added automatically at preflight; the triage/retro effort drop reaches new projects only — run
  `/auto-bmad reset-defaults ab-alt-high` to adopt it in an existing project.
- **Default code-review iteration cap is now 2 (was 3).** `code_review.max_iterations` defaults to
  2 — the review loop runs at most two passes (one if the first pass is perfectly clean). Existing
  projects keep their configured value; raise it in `config.yaml` for deeper loops.
- **Long-epic trace advisory now skips the epic's last stories.** A new `skip_last_stories`
  (default 3) drops the advisory on an epic's last few stories — their coverage gaps surface at the
  epic-end trace gate that is about to run anyway — keeping it on the early/middle stories where an
  unnoticed gap is costliest.

## [0.13.5] - 2026-06-08

### Fixed

- **Code review now runs its three independent review lenses for real.** The orchestrator fans the
  review out itself (Blind Hunter, Edge Case Hunter, Acceptance Auditor, then triage) instead of
  delegating `/bmad-code-review` to one sub-agent that — barred from spawning its own subagents —
  silently collapsed all three into a single sequential pass, losing the parallel, context-isolated
  adversarial coverage (pipeline.md, delegation.md).

## [0.13.4] - 2026-06-08

### Changed

- **Code review now skips BMAD scaffolding and non-code files.** The delegated review scopes to the
  story by key and excludes `_bmad`, `_bmad-output`, cache files, and obvious non-code files from the
  branch diff, so findings focus on actual story code (delegation.md).

## [0.13.3] - 2026-06-07

### Changed

- **Every auto-bmad commit now carries a body, not just a subject.** Each per-phase commit is a full
  Conventional Commit — `type(scope): subject` plus a required body drawn from the phase's own facts,
  and a `BREAKING CHANGE:` footer when a delegate reports one — so story history reads consistently
  (git-and-pr.md).

## [0.13.2] - 2026-06-04

### Changed

- **A perfectly clean first code review now exits without a second pass.** When the first review pass
  finds 0 non-deferred findings, the loop skips the mandatory second opinion and goes straight to the
  human-in-the-loop halt; any first pass with ≥ 1 non-deferred finding still pulls the second review.

## [0.13.1] - 2026-06-04

### Changed

- **External-review changes are now re-reviewed, not just summarized.** On **Continue** at the Phase 7
  halt, auto-bmad delegates a fresh whole-story review (the alternate model) of anything you changed
  while paused — gated on findings read from the story file — and re-opens the halt offering
  fix / fix-and-re-review / ignore when they're meaningful (> 3 findings or any Critical/High). The
  orchestrator no longer reads the diff itself.

## [0.13.0] - 2026-06-03

### Changed

- **Code review always runs at least two review passes.** A clean first pass no longer exits the
  loop early, so a second opinion — the alternate model when `code_review.alternate_models` is on —
  always weighs in.
- **Code review converges on a finding-count gate, not severity heuristics.** A pass exits the loop
  when it found-and-fixed ≤ 3 non-deferred findings with no Critical/High; more than that (or any
  non-deferred Critical/High) re-reviews, up to `code_review.max_iterations`.
- **The code-review loop now ends at a human-in-the-loop halt on every run.** auto-bmad suggests an
  external review (a human, another model/AI) while the pipeline is paused, then on continue
  summarizes any changes you added before resuming (replaces the old cap-only prompt).

## [0.12.1] - 2026-06-03

### Changed

- **Project-context delegation prompts simplified** — terser first-time bootstrap (Phase 2) and
  epic-end refresh (Phase 8) intents.
- **Delegate prompts and agent contracts trimmed for concision** — a redundant `no-spec` example
  and verbose git-handling caveats dropped from the shared autonomy directive and the rendered
  `ab-*` agents; behavior unchanged (re-renders on the next `/auto-bmad reprovision`).

### Fixed

- **Fewer wasted code-review re-reviews from a `no-spec` first pass** — the delegation hands the
  skill the spec + branch diff as its invocation argument, so it resolves the story file as the spec
  (FULL review mode) on the first pass instead of dropping to `no-spec`. Takes effect on module
  update — no reprovision needed.

## [0.12.0] - 2026-06-02

### Added

- **Epic-end archives resolved deferred work out of the active ledger.** After the project-context
  refresh, fully-resolved entries move from `<impl>/deferred-work.md` to a sibling
  `deferred-work-resolved.md` — so create-story stops re-folding finished work into new stories,
  while the audit trail stays in-tree. Partial and still-open deferrals stay put.

## [0.11.1] - 2026-06-02

### Changed

- **Report sections now carry a disposition tag and resume-aware deltas.** Each `## Report` heading
  is tagged (`(final)` / `(final — caveated)` / `(halted — <reason>)`) and a resume section reports
  only its own phases with a `Continues:` back-reference — so a multi-run log is skim-readable from
  its outline and no section has to re-derive an earlier (possibly cross-tool) run's facts.
- **Code-review severity counts use one fixed format in reports.** Pinned to
  `Critical N / High N / Medium N / Low N` so every report section reads identically.

### Fixed

- **Report files no longer leak PR/CI/merge artifacts into the committed log.** "Chat-only" is now
  defined as the finalization *artifacts/links* (PR URL, CI run link, merge method + branch-deleted
  state, status-flip outcome); the one-line pipeline *disposition* — incl. a draft's summary reason
  — stays in the file's `Pipeline status` line. Resolves a spec contradiction that let those
  artifacts land in the committed report.

## [0.11.0] - 2026-06-02

### Added

- **`/auto-bmad reset-defaults` restores shipped profile defaults.** Discards your `config.yaml`
  retunes and re-seeds `profiles`/`phase_profiles` from the module asset — scope it to one profile,
  all profiles, or the phase mapping. Leaves your git/TEA/delegation setup untouched (config_plan.py).

### Fixed

- **Long-epic trace advisory now triggers from a deterministic story count** — the sprint-status
  reader emits `epic_story_count`, so the `min_epic_stories` gate is no longer eyeballed from YAML
  (story_plan.py).

## [0.10.3] - 2026-05-31

### Fixed

- **Code review now persists findings on the first pass** — no more wasted retry from a `no-spec`
  run. **Upgraders:** run `/auto-bmad reprovision` to re-render the agents with the new contract.

### Added

- **README now states BMAD compatibility** — a blockquote plus a `tested with BMAD 6.8.x` badge,
  tested against the BMAD-METHOD v6 skill line. Contract-based (skill names, `sprint-status.yaml`,
  `project-context.md` path, story `Status:`), not a pinned version, so routine BMAD patch/minor
  updates are expected to work.

## [0.10.2] - 2026-05-30

### Changed

- **Per-phase resume-state now folds into the phase commit, not its own `chore` commit** — cuts ~4
  noise commits per story. Standalone state-only bookkeeping commits are now forbidden.
  (`git-and-pr.md`, `pipeline.md`)
- **Phase 9 finalize collapses to one `chore(...): finalize` commit** instead of a mark-done /
  record-PR-metadata / record-CI chain; the post-merge record gets no commit of its own (the chat
  report owns merge details). State stays committed, so the branch remains self-resumable.

## [0.10.1] - 2026-05-30

### Changed

- **Retuned the delegate profiles to cut token cost; the set stays four.** Removed `ab-max`
  (`dev_story` moves to `ab-xhigh`); split `ab-alt` into `ab-alt-xhigh` (model-diversity secondary
  review) + `ab-alt-high` (triage/retro); `code_review_fix` drops from `ab-xhigh` to `ab-high`.
  **Upgraders:** run `/auto-bmad reprovision`, then repoint any `phase_profiles` still on the retired
  `ab-max`/`ab-alt` by hand.

## [0.10.0] - 2026-05-29

### Added

- **Phase 0 now detects and heals runtime-config drift**, so a module update's new config keys
  actually reach existing projects. New `scripts/config_plan.py` (`--check`/`--apply`) additively
  appends only the keys the config is missing — never overwriting a retune — and restamps the
  version; Phase 0 auto-applies on drift and reports it. A sub-key missing from an existing profile
  is flagged `manual_review`, not auto-written.
- **Per-story trace coverage advisory for long epics** (`tea.story_trace_advisory`, default on,
  `min_epic_stories: 6`). A non-blocking `bmad-testarch-trace` at the Phase 7 tail surfaces a story's
  uncovered acceptance criteria while context is fresh, instead of waiting for the epic-end gate. It
  self-activates only on a high-risk, not-last story in an epic of ≥6 stories and never halts;
  `skip trace-advisory` opts a run out.

### Fixed

- **`/auto-bmad` now detects when a reprovision/re-seed is needed after a module update.** The old
  `render-agents.py --check` only diffed the four agent files and reported `fresh` even when the
  config had drifted behind the asset; the new Phase 0 config-drift step makes the detection real.

## [0.9.0] - 2026-05-29

### Added

- **Phase 8 now surfaces retrospective-detected planning drift.** When the retro flags a
  PRD/architecture/epic-scope assumption the build disproved, the orchestrator lifts it into a new
  **Planning drift** report field and recommends the upstream re-sync path. Non-blocking and never
  auto-run — it names the step, the human decides.
- **`scripts/state_plan.py` — a deterministic reader for auto-bmad's `state/{key}.yaml` files**, so
  resume detection calls a tool instead of improvising shell. A default scan reports in-flight
  pipelines and the resume target; `--story-key` does a single-story check. Dependency-free, exits 0
  on an empty dir, has a `--self-test`.

### Changed

- **Retuned two profile assignments for better effort fit.** `project_context` (Phase 2/8
  `project-context.md`) moved from `ab-alt` to `ab-high` — high-leverage durable output. Phase 0 risk
  triage split into its own `tea_triage` key on `ab-alt`; ATDD/automate stay on `tea_per_story` →
  `ab-high`. Requires `/auto-bmad reprovision`.

### Fixed

- **Realigned the four delegate persona strings to the actual `phase_profiles` mapping.** Each
  profile's baked-in self-description had drifted from what it's invoked for; they now honestly
  enumerate each profile's real duties. Requires `/auto-bmad reprovision`.
- **Resume/state probes no longer misfire on shell globs or a phantom `story-` filename prefix.**
  State files are named `{key}.yaml` (no `story-` prefix), and an unmatched glob aborts under
  zsh/fish; the docs now give a `find`-based enumeration plus an exact-path check, and ban bare globs.

## [0.8.0] - 2026-05-29

### Added

- **Per-story run-time tracking with an AI-run vs human-wait split.** State gains `started_at`,
  `completed_at`, and `active_seconds`; the report's new **Timing** line shows total elapsed,
  approximate AI-run time, and human/idle wait. Best-effort host wall-clock, not token-compute time.

### Changed

- **Phase 8 `project-context.md` refresh now folds in the epic's retro notes + deferred work**, so
  durable rules that aren't inferable from code carry into the next epic's stories via
  `persistent_facts` (previously a blind code scan).
- **First-in-epic create-story now reads the prior epic's retrospective forward sections**, carrying
  the transient epic-specific prep that durable `project-context.md` doesn't hold.

## [0.7.0] - 2026-05-29

### Added

- **create-story now folds in prior deferred work.** When `<impl>/deferred-work.md` exists, the
  create-story delegate reads it and folds scope-overlapping deferrals into the Story Context. No
  stock BMAD or TEA skill reads that ledger, so this is the only path carrying deferrals into new
  stories.

## [0.6.1] - 2026-05-29

### Fixed

- **Phase 7 reconciliation gate no longer false-fails on the reviewer's bullet format.**
  `review_findings.py` keyed on a rigid checkbox rendering, but the LLM-owned `### Review Findings`
  section legitimately uses bold prose; the matcher now keys only on the `[Review][Type]` tag,
  treating the checkbox and severity tag as optional.

### Changed

- **Trimmed duplicated rationale across the reference docs (no behavior change).** Collapsed repeated
  "why" explanations to a single canonical home with pointers; every pipeline contract is unchanged.
- **Dropped hardcoded model names from the module-setup provisioning note**, so `profiles.yaml` stays
  the single source and the doc can't drift on a retune.

## [0.6.0] - 2026-05-28

### Added

- **Phase 0 project-context probe + Phase 2 bootstrap sub-step.** auto-bmad now detects a missing
  `project-context.md` at preflight and bootstraps it before create-story (committed
  `docs(project-context): bootstrap`). Previously the file was only built at epic-end, so early
  greenfield stories skipped `persistent_facts` injection. `skip project-context-bootstrap` opts out.
- **create-story now ingests the epic's accumulated retro notes when present.** The Phase 3 delegate
  reads `retro-notes/epic-{e}.md` and treats prior bullets as epic-wide constraints reflected in the
  Story Context, turning a write-only file into an in-epic feedback loop.
- **`profiles_source_version` field in `config.yaml`.** First-run stamps the installed
  `module_version` so a future update can detect a stale-defaults snapshot without losing retunes.
  Advisory only.

### Changed

- **State-file schema is now a stable contract — every field is always emitted.** Fields that
  previously appeared only on a merge (`pr_merged`, `merge_method`, …) now always emit, using
  explicit `null`/`false`/`unknown`. Added `updated_at` so resume can tell how stale a state file is.
- **`reports/{key}.md` sections now follow a fixed template** — same headings in the same order,
  empty sections kept with "(none)" — so PR reviewers find each field in a predictable place.
- **Phase 9 merge prompt now defaults to "Merge commit"** (order: Merge commit / Rebase / Squash /
  Don't merge). auto-bmad's per-phase commits carry signal that squashing would collapse, so the
  history-preserving options lead.
- **Phase 9 now commits the per-story report before push, so it ships in the PR diff.** The report is
  now story-level only; PR URL, CI status, merge method, and the status-flip outcome stay chat-only,
  so the file never needs re-touching after the PR/CI/merge resolve.

## [0.5.0] - 2026-05-28

### Added

- **End-of-pipeline merge prompt (opt-in, default on).** On a clean-completion PR, Phase 9 waits for
  CI then asks whether to merge (and to delete the branch), running the chosen `gh pr merge` itself.
  Gated by `git.offer_merge` and `git.ci_wait_minutes: 30`; `skip merge-prompt` opts out. CI
  red/timed-out now leaves the story at `review` with a draft PR.

### Changed

- **Delegate templates collapsed to one shared body per tool — no more Claude↔Codex drift.** The
  eight per-profile templates were ~80% identical and had started drifting; now one shared body per
  tool is filled with per-profile metadata from `profiles.yaml`, and `render-agents.py --self-test`
  asserts cross-tool agreement. Run `/auto-bmad reprovision` to pick up the new bodies.
- **Reference duplication consolidated — each canonical fact has one home (pointer-only, no behavior
  change).** The restart warning, Phase 9 CI/merge deferrals, the first-run stop, and a new
  "Ownership" list of orchestrator-owned actions each now live in exactly one place.

### Fixed

- **README "Updating" no longer recommends `--action quick-update`, which silently skips auto-bmad.**
  auto-bmad installs as a custom-source module, which `quick-update` skips; the section now documents
  `--action update --custom-source <repo-url> --yes`, which re-clones and rewrites the manifest
  source.

## [0.4.0] - 2026-05-27

### Changed

- **Retro notes are now terse, signal-only, and skipped when empty**, so the epic retro-notes file
  stays small. Delegates default notes to `none` and add at most a one-line bullet for genuinely
  retrospective-worthy items; the orchestrator appends nothing for `none`/routine. Run
  `/auto-bmad reprovision`.
- **Phase 7 code-review loop now keeps iterating on a cluster of Mediums, not just Critical/High.** A
  pass exits only when it found no Critical/High and at most one Medium; two or more Mediums re-review.

### Fixed

- **A finished story now advances instead of stalling waiting for a human merge.** Phase 9 flips the
  BMAD-level status to `done` on a clean completion (decoupling `done` from the human's merge), so
  `story_plan.py` stops re-selecting the just-finished `review` story. Caveated completions stay at
  `review`.
- **Deferred code-review findings are persisted to the durable `deferred-work.md` ledger again.** The
  `code-review` prompt now makes appending defers to `<impl>/deferred-work.md` part of the
  deliverable, Phase 7 appends user-deferred decisions to the same ledger, and `review_findings.py`
  gains `--deferred-work-file`/`--story-key` to fail reconciliation on a shortfall.
- **Code review now enforces that findings are persisted to the story file.** `/bmad-code-review`
  silently runs `no-spec` (writing nothing to `### Review Findings`) when the story file isn't bound
  as its spec; the prompt now binds it and forbids the fallback, and a new Phase 7 reconciliation gate
  re-delegates once on a mismatch before escalating to `needs-human`.
- **First-run setup and `reprovision` now tell the user to fully restart the tool** (quit &
  relaunch), not just clear context — project delegate agents are scanned only at process launch, so
  a mid-session render stayed unregistered and the first delegation failed.
- **A fresh-on-disk delegate reporting "Agent type not found" is now read as restart-needed**, not a
  cue to degrade to `general-subagents` — degrading would run the whole pipeline untuned.
- **Auto-reprovision-on-stale no longer claims to self-heal without a restart** — it heals the
  on-disk files, but a running process keeps the agent definitions it loaded at launch.

## [0.3.1] - 2026-05-27

### Fixed

- **Resume detection now enumerates `state/*.yaml` with `find` (or Python), not a raw glob loop.** On
  a first run `state/` is empty and an unmatched glob aborts under zsh/fish (`nomatch`); `find`
  yields empty output + exit 0 everywhere.

## [0.3.0] - 2026-05-27

### Added

- **`argument-hint` frontmatter on the `auto-bmad` skill**, so Claude Code shows the expected
  arguments in slash-command autocomplete. No effect on Codex (harmless).
- **Phase 7 now resolves `[Review][Decision]` findings via batched `AskUserQuestion` before the fix
  pass** — it never auto-guesses an ambiguous fix — feeding the human's choices into the
  `code_review_fix` delegate.
- **A `FAIL` epic trace gate now halts and asks the user** (remediate & re-gate / waive & continue /
  stop) instead of being captured-and-ignored. Bounded by `tea.gate_max_iterations` (default 2); new
  `gate_iterations` state field tracks the loop. `CONCERNS` stays advisory.

### Changed

- **The per-step `/bmad-*` command + prompt now live only in `delegation.md`** — `pipeline.md`
  references each step by name, and the placeholder glossary is defined once.
- **Codex delegate defaults (`gpt-5.5`/`gpt-5.4`) are now treated as real model names, not
  placeholders.** Setup no longer warns to confirm them; retuning stays available.
- **The phase→profile mapping now lives only in config `phase_profiles`.** Playbooks reference its
  keys; added the missing `code_review_review_secondary` key and a defaults block to `profiles.yaml`.
- **`profiles.yaml` is now the single source for the default `profiles` + `phase_profiles`.** The
  `config.yaml` schema doc now shows just the shape and points at the asset, so the two can't drift.
- **Corrected the documented Codex reasoning-effort set to `low|medium|high|xhigh`** (`xhigh` is the
  ceiling).
- **Standardized delegation-prompt placeholders** — `<...>` for filesystem paths, `{...}` for
  non-path fill-ins.
- **Bumped top-tier Codex `reasoning_effort` (`ab-max`/`ab-xhigh`) from `high` to `xhigh`**,
  restoring the Claude-side tiering on Codex. Re-run `/auto-bmad reprovision`.
- **Renamed the `ab-fast` profile to `ab-alt`** (it's the alternate reviewer, not necessarily
  faster). Upgraders run `/auto-bmad reprovision`; old `ab-fast` files can be deleted.

### Fixed

- **Code-review references now point at the real `### Review Findings` artifact**, not an
  `[AI-Review]` tag `bmad-code-review` never writes, so the fix pass reliably finds its work.
- **`bump-version.py` now creates an annotated tag** (was lightweight), so `git push --follow-tags`
  pushes it and the release workflow fires.
- **`render-agents.py` now tolerates trailing comments on structural lines** in the profiles source,
  which previously made it miss the `profiles:` block and fail reprovisioning.

## [0.2.0] - 2026-05-27

### Added

- **README "Split a story across Claude Code and Codex" section** — a manual `stop before
  code-review` + resume workaround to implement a story in one tool and review it in the other.
- **Preflight provisioning-drift detection.** `render-agents.py --check` re-renders the agents in
  memory and diffs them against disk; on a `custom-subagents` host the orchestrator auto-reprovisions
  when agents are missing or stale.

## [0.1.1] - 2026-05-27

First tagged release — the matching `v0.1.1` git tag for the module already published via the
`marketplace.json` manifest, plus the changelog and release tooling.

### Added

- **The auto-bmad BMAD module** — an orchestrator skill that runs the full BMAD story workflow
  end-to-end, one story at a time, on Claude Code or Codex, chaining `create-story` → `dev-story` →
  `code-review` with risk-gated TEA phases and epic-boundary steps.
- **Tiered delegation.** Each step runs in a delegated `ab-*` sub-agent (git/PR owned by the
  orchestrator); tuned `custom-subagents` degrade to `general-subagents` then `inline`.
- **Resumable pipeline** with isolated `story/X-Y-slug` branches, per-phase conventional-commit
  checkpoints, a PR + final report, human-in-the-loop stops, and first-run config.
- **Distribution** via the BMAD installer (custom Git source) and a Claude plugin `marketplace.json`,
  plus a README "Updating" section, `CHANGELOG.md`, and the `scripts/bump-version.py` release helper.

[Unreleased]: https://github.com/stefanoginella/auto-bmad/compare/v0.25.1...HEAD
[0.25.1]: https://github.com/stefanoginella/auto-bmad/compare/v0.25.0...v0.25.1
[0.25.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.24.0...v0.25.0
[0.24.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.23.0...v0.24.0
[0.23.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.22.1...v0.23.0
[0.22.1]: https://github.com/stefanoginella/auto-bmad/compare/v0.22.0...v0.22.1
[0.22.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.21.0...v0.22.0
[0.21.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.20.2...v0.21.0
[0.20.2]: https://github.com/stefanoginella/auto-bmad/compare/v0.20.1...v0.20.2
[0.20.1]: https://github.com/stefanoginella/auto-bmad/compare/v0.20.0...v0.20.1
[0.20.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.19.0...v0.20.0
[0.19.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.18.0...v0.19.0
[0.18.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.17.3...v0.18.0
[0.17.3]: https://github.com/stefanoginella/auto-bmad/compare/v0.17.2...v0.17.3
[0.17.2]: https://github.com/stefanoginella/auto-bmad/compare/v0.17.1...v0.17.2
[0.17.1]: https://github.com/stefanoginella/auto-bmad/compare/v0.17.0...v0.17.1
[0.17.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.16.0...v0.17.0
[0.16.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.15.0...v0.16.0
[0.15.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.14.0...v0.15.0
[0.14.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.13.6...v0.14.0
[0.13.6]: https://github.com/stefanoginella/auto-bmad/compare/v0.13.5...v0.13.6
[0.13.5]: https://github.com/stefanoginella/auto-bmad/compare/v0.13.4...v0.13.5
[0.13.4]: https://github.com/stefanoginella/auto-bmad/compare/v0.13.3...v0.13.4
[0.13.3]: https://github.com/stefanoginella/auto-bmad/compare/v0.13.2...v0.13.3
[0.13.2]: https://github.com/stefanoginella/auto-bmad/compare/v0.13.1...v0.13.2
[0.13.1]: https://github.com/stefanoginella/auto-bmad/compare/v0.13.0...v0.13.1
[0.13.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.12.1...v0.13.0
[0.12.1]: https://github.com/stefanoginella/auto-bmad/compare/v0.12.0...v0.12.1
[0.12.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.11.1...v0.12.0
[0.11.1]: https://github.com/stefanoginella/auto-bmad/compare/v0.11.0...v0.11.1
[0.11.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.10.3...v0.11.0
[0.10.3]: https://github.com/stefanoginella/auto-bmad/compare/v0.10.2...v0.10.3
[0.10.2]: https://github.com/stefanoginella/auto-bmad/compare/v0.10.1...v0.10.2
[0.10.1]: https://github.com/stefanoginella/auto-bmad/compare/v0.10.0...v0.10.1
[0.10.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/stefanoginella/auto-bmad/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/stefanoginella/auto-bmad/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/stefanoginella/auto-bmad/releases/tag/v0.1.1
