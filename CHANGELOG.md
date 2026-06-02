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

[Unreleased]: https://github.com/stefanoginella/auto-bmad/compare/v0.10.3...HEAD
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
