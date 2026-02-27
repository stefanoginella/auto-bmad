# Contributing

Thank you for your interest in contributing! This repository is a Claude Code plugin marketplace containing two plugins: **auto-bmad** and **code-guardian**.

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed
- The required BMAD modules and Claude Code plugins listed in the [auto-bmad README](./plugins/auto-bmad/README.md#-prerequisites)
- A BMAD-configured project to test pipelines against (with `_bmad/bmm/config.yaml` and `_bmad/tea/config.yaml`)
- `jq` installed (used by hook scripts)

## Development Setup

After cloning, configure git to use the repo's hooks:

```bash
git config core.hooksPath .githooks
```

This enables the pre-commit hook that auto-syncs `package.json` versions when `plugin.json` changes.

Test a plugin locally without installing from the marketplace:

```bash
claude --plugin-dir /path/to/plugins/auto-bmad
claude --plugin-dir /path/to/plugins/code-guardian
```

This loads the plugin for that session. Add `--debug` to see hook execution and plugin loading details.

## Repository Structure

This repo has four layers: a marketplace definition at the root, individual plugins under `plugins/`, npm companion packages under `packages/`, and build/CI scripts.

```
.claude-plugin/
  marketplace.json            — Marketplace manifest (repo name, plugin registry)

plugins/
  auto-bmad/                  — BMAD pipeline orchestration plugin
    .claude-plugin/plugin.json
    commands/                 — Slash commands (plan, epic-start, story, epic-end)
    hooks/                    — Hook definitions and scripts
  code-guardian/              — Security scanning plugin
    .claude-plugin/plugin.json
    commands/                 — Slash commands (setup, scan, ci)
    hooks/                    — Hook definitions and scripts
    scripts/                  — Scanner wrappers and orchestration

packages/
  auto-bmad/                  — npm companion package (@stefanoginella/auto-bmad)
    package.json
    cli.js                    — npx entry point (wraps claude plugin install)
  code-guardian/              — npm companion package (@stefanoginella/code-guardian)
    package.json
    cli.js

scripts/
  prepublish.sh               — Syncs versions + copies README/LICENSE before npm publish
  sync-versions.sh            — Syncs plugin.json version → package.json

.githooks/
  pre-commit                  — Auto-syncs package.json versions on commit

.github/workflows/
  publish.yml                 — CI: auto-publish to npm on plugin.json version bump
```

### Key Files

- **`.claude-plugin/marketplace.json`** — Registers this repo as a marketplace and lists available plugins
- **`plugins/<name>/.claude-plugin/plugin.json`** — Plugin manifest; bump the version when making meaningful changes (source of truth for npm package versions)
- **`plugins/<name>/commands/*.md`** — Each file is a slash command with YAML frontmatter (`name`, `description`) and a markdown body that instructs Claude how to orchestrate a pipeline
- **`plugins/<name>/hooks/hooks.json`** — Hook definitions following the [Claude Code hooks schema](https://docs.anthropic.com/en/docs/claude-code/hooks)
- **`plugins/<name>/hooks/scripts/`** — Shell scripts invoked by hooks; use `${CLAUDE_PLUGIN_ROOT}` for path portability
- **`packages/<name>/cli.js`** — npm bin entry point; adds marketplace and installs plugin via `claude` CLI
- **`scripts/prepublish.sh`** — Run before `npm publish` to sync versions and copy README/LICENSE

## How to Contribute

### Reporting Issues

- Open an issue on GitHub with a clear description of the problem
- Include which pipeline command you were running (`plan`, `story`, `epic-start`, `epic-end`)
- Include the step number where the issue occurred, if applicable
- Paste any relevant error output

### Suggesting Features

- Open an issue describing the feature and its use case
- Explain which pipeline(s) it would affect

### Submitting Changes

1. Fork the repository
2. Create a branch for your change
3. Make your changes
4. Test the affected pipeline(s) end-to-end with a real BMAD project
5. Submit a pull request

## What Can Be Contributed

- **Command improvements** (`plugins/<name>/commands/`) — Pipeline step changes, new skip conditions, better prompts
- **Hook improvements** (`plugins/<name>/hooks/`) — Safe-bash prefix list updates, new hook scripts, new hook types
- **Manifest updates** (`plugins/<name>/.claude-plugin/plugin.json`) — Version bumps, metadata
- **Documentation** — README, CONTRIBUTING, examples
- **New plugins** — Add a new plugin under `plugins/`, register it in `.claude-plugin/marketplace.json`, and optionally add an npm companion package under `packages/`

## Design Patterns

If you're modifying or extending the pipelines, be aware of these conventions:

- **Sequential foreground Tasks** — Every pipeline step is a single foreground `Task` call that blocks until complete. No parallel agents.
- **Handoff protocol** — Steps that produce values for downstream steps emit a `## Handoff` section with key-value pairs. The coordinator extracts and injects these into subsequent steps.
- **Step Output Format** — Every subagent prompt includes a `## Step Summary` format (status, duration, what changed, key decisions, issues, remaining concerns).
- **Checkpoint and squash** — Intermediate `git add -A && git commit` checkpoints at phase boundaries, then `git reset --soft` and one clean commit at the end via `/commit-commands:commit`.
- **Recovery tags** — `git tag -f pipeline-start-*` at the beginning of every pipeline for rollback.
- **Filesystem boundary** — All temp files go to `{project_root}/.auto-bmad-tmp/`; never `/tmp` or `$TMPDIR`.
- **Config-driven paths** — Output paths are read from `_bmad/bmm/config.yaml` and `_bmad/tea/config.yaml`; never hardcoded.
- **`yolo` suffix** — Every subagent prompt ends with `yolo` to suppress confirmation dialogs during autonomous execution.

## Guidelines

- Keep pipeline prompts clear and imperative — they are instructions for Claude agents, not documentation for humans
- Preserve the sequential pipeline structure (each step = one foreground Task call)
- Every pipeline step must include the Step Output Format and follow the Handoff Protocol
- Skip conditions should be evaluated by the coordinator before launching a Task
- Use `${CLAUDE_PLUGIN_ROOT}` in hook scripts for path portability
- Test changes against a real BMAD project before submitting
- When adding entries to the safe-bash list in `approve-safe-bash.sh`, use exact matches for bare commands and prefix matches (with trailing space) for commands that take arguments

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](./LICENSE).
