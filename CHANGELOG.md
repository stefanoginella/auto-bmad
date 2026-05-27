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

- `argument-hint` frontmatter on the `auto-bmad` skill, so Claude Code shows the
  expected arguments (`--story <id>`, `setup`/`reprovision`, overrides) in the
  slash-command autocomplete popup. No effect on Codex, which doesn't read
  `argument-hint` for skills — harmless there.
- Phase 7 now resolves `[Review][Decision]` (decision-needed) review findings via
  batched `AskUserQuestion` (≤4 per call) **before** the fix pass — it never
  auto-guesses an ambiguous fix — and feeds the human-chosen directions into the
  `code_review_fix` delegate.

### Changed

- Codex delegate defaults (`gpt-5.5`/`gpt-5.4`) are now treated as **real model
  names**, not placeholders. Setup no longer emits the "⚠️ Codex models are
  placeholders — confirm them" warning / "needs human" action; retuning the
  `profiles` block stays available but is no longer flagged as required.
- The phase→profile mapping now lives **only** in config `phase_profiles`: the
  pipeline/delegation playbooks reference its keys (e.g. `create_story`,
  `code_review_review`) instead of raw profile names, removing the prior
  triplication. Added the missing `code_review_review_secondary` key (the even-
  iteration reviewer used when `code_review.alternate_models` is on) and a
  `phase_profiles:` defaults block to `assets/agents/profiles.yaml` so first-run
  actually has it to copy. `render-agents.py` ignores the new block.
- `assets/agents/profiles.yaml` is now the **single source** for the default
  `profiles` + `phase_profiles` values. The `config.yaml` schema in
  `state-and-resume.md` previously re-listed every model/effort and had already
  drifted from the asset (e.g. `ab-fast` codex `gpt-5.4-mini` vs `gpt-5.4`, and
  `xhigh` vs `high` effort on `ab-max`/`ab-xhigh`). The schema now shows just the
  *shape* and points at the asset, so the two can't drift.
- Corrected the documented Codex reasoning-effort set to `low|medium|high|xhigh`
  (gpt-5.x; `xhigh` is the ceiling) in `profiles.yaml` and `CLAUDE.md` — the prior
  `minimal|low|medium|high` wrongly omitted `xhigh`.
- Standardized delegation-prompt placeholders: `<...>` for filesystem paths,
  `{...}` for non-path fill-ins — so `{project_root}` is now `<project_root>`.
- Bumped the Codex `reasoning_effort` of the top-tier profiles `ab-max` and
  `ab-xhigh` from `high` to `xhigh` (the Codex gpt-5.x ceiling), restoring the
  Claude-side tiering on Codex; `ab-high`/`ab-fast` stay `high`. Re-run
  `/auto-bmad reprovision` to regenerate the Codex delegate `.toml` files.

### Fixed

- Code-review references pointed at an `[AI-Review]` tag that `bmad-code-review`
  never writes — it persists findings to a `### Review Findings` section as
  `[Review][Patch]` / `[Review][Decision]` / `[Review][Defer]`. The review and fix
  prompts and Phase 7 now reference the real artifact, so the fix pass reliably
  finds its work instead of hunting for a tag that isn't there.
- `scripts/bump-version.py` now creates an **annotated** tag (was lightweight), so
  `git push --follow-tags` actually pushes it and the release workflow fires.
- `scripts/render-agents.py` now tolerates **trailing comments on structural lines**
  (`profiles:`, the profile name, the tool key) in the profiles source. The
  documented `config.yaml` schema carries inline comments on those lines, which
  previously made the parser miss the `profiles:` block entirely and fail
  reprovisioning with "no 'profiles:' block found".

## [0.2.0] - 2026-05-27

### Added

- README **"Split a story across Claude Code and Codex"** section — a manual
  workaround that uses `stop before code-review` + resume to implement a story in
  one tool and code-review it in the other (either direction), leaning on
  auto-detected host and the resumable, commit-checkpointed pipeline.
- Preflight **provisioning-drift detection**. `render-agents.py --check` re-renders
  the delegate agents in memory and diffs them against the on-disk files (exit 1
  when stale). On a `custom-subagents` host the orchestrator runs it every preflight
  and **auto-reprovisions** — reporting it — when the agents are missing or stale
  after a module update or a `profiles` edit, so generated agents no longer drift
  unnoticed.

## [0.1.1] - 2026-05-27

First tagged release. The module had been published at `0.1.1` via the
`marketplace.json` manifest; this is the matching `v0.1.1` git tag, plus the
changelog and release tooling to keep versions traceable from here on.

### Added

- The **auto-bmad** BMAD module — an orchestrator skill that runs the full BMAD
  story workflow end-to-end, one story at a time, on Claude Code or Codex. It
  chains `create-story` → `dev-story` → `code-review` with risk-gated TEA phases
  and epic-boundary steps (test-design, ATDD, automate, traceability, NFR,
  test-review, project-context, retrospective).
- Each step runs in a delegated `ab-*` sub-agent; git/PR work is owned by the
  orchestrator. Tiered delegation: tuned `custom-subagents` (Claude
  `.claude/agents`, Codex `.codex/agents`, generated from a configurable
  `profiles` block) degrading to `general-subagents` and then `inline`.
- Resumable pipeline with isolated `story/X-Y-slug` branches, per-phase
  conventional-commit checkpoints, a PR + final report, per-story report logs,
  human-in-the-loop stops, and first-run/setup config at
  `_bmad-output/auto-bmad/config.yaml`.
- Distribution via the BMAD installer (custom Git source) and a Claude plugin
  `marketplace.json`.
- README **Updating** section: re-run the BMAD installer / `--action
  quick-update` / `@next`, the `/auto-bmad reprovision` follow-up, and the
  Claude-plugin update path.
- `CHANGELOG.md` (this file) and `scripts/bump-version.py` — a dependency-free
  release helper that promotes `[Unreleased]`, syncs the version in
  `marketplace.json` + `module.yaml`, commits, and tags.

[Unreleased]: https://github.com/stefanoginella/auto-bmad/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/stefanoginella/auto-bmad/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/stefanoginella/auto-bmad/releases/tag/v0.1.1
