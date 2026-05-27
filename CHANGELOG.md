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

### Changed

- Codex delegate defaults (`gpt-5.5`/`gpt-5.4`) are now treated as **real model
  names**, not placeholders. Setup no longer emits the "⚠️ Codex models are
  placeholders — confirm them" warning / "needs human" action; retuning the
  `profiles` block stays available but is no longer flagged as required.

### Fixed

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
