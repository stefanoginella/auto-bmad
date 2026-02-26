# auto-bmad: Automated (and opinionated) BMAD pipeline orchestration for Claude Code.

`auto-bmad` provides four sequential pipeline commands that drive the full BMAD software development lifecycle — from planning through story delivery — plus a safe-bash auto-approval hook for frictionless autonomous execution.

The pipelines augment the core BMAD workflow with additional non-BMAD steps for a more thorough development process: frontend design polish, semgrep security scanning, CLAUDE.md maintenance, and various readiness checks.

## Commands

| Command | Description |
|---------|-------------|
| `/auto-bmad:plan` | Run the full pre-implementation pipeline: product brief, PRD, UX, architecture, test framework, CI, epics, test design, sprint planning |
| `/auto-bmad:epic-start` | Start a new epic: resolve previous retro actions, establish green baseline, plan story order |
| `/auto-bmad:story` | Develop a full story: create, validate, ATDD, develop, lint, test, code review, security scan, regression, E2E, trace |
| `/auto-bmad:epic-end` | Close an epic: aggregate data, traceability gate, retrospective, next epic preview |

## Prerequisites

### BMAD Method 

The whole pipeline is based on the [BMAD Method](https://github.com/bmad-code-org/BMAD-METHOD) workflow and relies on specific BMAD modules.

#### Required BMAD Modules

- **TEA** — Test Engineering Architect

#### Optional BMAD Modules

- **CIS** — Creative Intelligence Suite

### Required Claude Code Plugins

These plugins provide the BMAD commands invoked by the pipelines:

- **frontend-design** — `/frontend-design:frontend-design` (story UI polish step)
- **commit-commands** — `/commit-commands:commit` (final commit in all pipelines)
- **claude-md-management** — `/claude-md-management:claude-md-improver` (CLAUDE.md maintenance in plan and epic-end)

### Optional (but recommended) Claude Code Plugins

- **context7** (MCP server) — Live documentation lookups for library APIs. Used during architecture creation (plan) and story development (story). Without it, agents rely on training data instead of current docs.
- **semgrep** (CLI tool) — Security scanning in the story pipeline. Without it, the security scan step is skipped.

### Project Requirements

The pipelines expect BMAD configuration files in the project:

- `_bmad/bmm/config.yaml` — BMM configuration (output folders, artifact paths)
- `_bmad/tea/config.yaml` — TEA configuration (test artifact paths)

These files are normally created by the BMAD CLI when initializing BMAD in a project. The pipelines rely on the standard structure and paths defined by these configs, so custom configurations may require pipeline adjustments.

## Hooks

### Safe Bash Auto-Approval (PreToolUse)

Auto-approves bash commands matching a known-safe prefix list to reduce false-positive sandbox prompts during autonomous pipeline execution. This is a lightweight heuristic, not a full sandbox bypass.

**Default safe list:**

**Exact matches** (bare commands, no arguments):

`date` · `docker compose build` · `docker compose config` · `docker compose down` · `docker compose images` · `docker compose logs` · `docker compose ls` · `docker compose ps` · `docker compose pull` · `docker compose top` · `docker compose up` · `docker compose version` · `docker images` · `docker ps` · `docker version` · `git diff` · `git fetch` · `git log` · `git status` · `ls` · `pwd` · `tree` · `uname`

**Prefix matches** (command + any arguments):

`awk` · `basename` · `cat` · `chmod` · `cp` · `cut` · `date` · `diff` · `dirname` · `docker compose build` · `docker compose config` · `docker compose exec` · `docker compose logs` · `docker compose ps` · `docker compose pull` · `docker compose top` · `docker compose up` · `docker inspect` · `docker logs` · `docker ps` · `du` · `echo` · `file` · `find` · `git -C` · `git add` · `git commit` · `git diff` · `git diff-tree` · `git fetch` · `git log` · `git rev-parse` · `git show` · `git status` · `git tag` · `grep` · `head` · `jq` · `ls` · `mkdir` · `mv` · `realpath` · `sed` · `semgrep` · `sort` · `stat` · `tail` · `timeout` · `touch` · `tr` · `tree` · `uname` · `uniq` · `wc` · `which`

**Customizing the safe list:** Create `.claude/auto-bmad-safe-prefixes.txt` in your project to add entries without modifying the plugin:

```
# Lines starting with "= " are exact matches (bare commands)
# All other lines are prefix matches (must end with a trailing space)
# Empty lines and comments (#) are ignored

= docker compose restart
npm install
npx vitest
```

### Dependency Check (SessionStart)

Outputs a system message at session start listing the required BMAD plugins, so Claude can warn early if a pipeline is invoked without the necessary dependencies.

## Permissions

The pipelines run various bash commands (depending on the project), `WebSearch`, `WebFetch`, `Skill(commit-commands:commit)`, `mcp__plugin_context7_context7__resolve-library-id`, `mcp__plugin_context7_context7__query-docs` that Claude Code will prompt you to approve if they are not already approved. When prompted, you can choose to allow the command and add it to your project's allow list in `.claude/settings.json` or `.claude/settings.local.json`. For the first few runs in a new project, expect several approval prompts as the allow list builds up. After that, things stabilize and the pipelines run fully autonomously.

Alternatively, you can run Claude Code in "dangerously skip permissions" mode (`--dangerously-skip-permissions`), but do so at your own risk — ideally in an isolated environment like a VM or container.

## Installation

### From marketplace (recommended)

```
/plugin marketplace add stefanoginella/auto-bmad
```

Then install the plugin from the **Discover** tab:

```
/plugin
```

Or install directly:

```
/plugin install auto-bmad@auto-bmad-marketplace
```

### As a local plugin (development)

```bash
claude --plugin-dir /path/to/auto-bmad
```

## License

[MIT](./LICENSE)
