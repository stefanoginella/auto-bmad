# Contributing to auto-bmad

Thank you for your interest in contributing to auto-bmad!

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed
- The required BMAD plugins and Claude Code plugins listed in the [README](README.md#prerequisites)
- A BMAD-configured project to test pipelines against

## Development Setup

Test the plugin locally without installing it:

```bash
claude --plugin-dir /path/to/auto-bmad
```

This loads auto-bmad as a plugin for that session. Use `claude --debug` to see hook execution and plugin loading details.

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
4. Test the affected pipeline(s) end-to-end with a real project
5. Submit a pull request

## Plugin Structure

This is a Claude Code plugin. Key files:

```
.claude-plugin/plugin.json  — Plugin manifest (name, version, description)
commands/                   — Pipeline orchestration commands (markdown)
hooks/                      — Event-driven hooks (hooks.json + scripts)
```

- **`.claude-plugin/plugin.json`** — Bump the version when making meaningful changes
- **`commands/*.md`** — Each file is a slash command with YAML frontmatter (`name`, `description`) and a markdown body that instructs Claude
- **`hooks/hooks.json`** — Hook definitions following the [Claude Code hooks schema](https://docs.anthropic.com/en/docs/claude-code/hooks); prompt-based hooks are preferred for complex logic

## What Can Be Contributed

- **Command improvements** (`commands/`) — Pipeline step changes, new skip conditions, better prompts
- **Hook improvements** (`hooks/`) — Safe-bash prefix list updates, new hook types
- **Manifest updates** (`.claude-plugin/plugin.json`) — Version bumps, metadata
- **Documentation** — README, CONTRIBUTING, examples

## Guidelines

- Keep pipeline prompts clear and imperative — they are instructions for Claude agents, not documentation for humans
- Preserve the sequential pipeline structure (each step = one foreground Task call)
- Every pipeline step must include the Step Output Format and follow the Handoff Protocol
- Skip conditions should be evaluated by the coordinator before launching a Task
- Use `${CLAUDE_PLUGIN_ROOT}` in hooks for path portability
- Test changes against a real BMAD project before submitting

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
