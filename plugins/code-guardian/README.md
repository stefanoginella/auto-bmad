# 🛡 Code Guardian — EXPERIMENTAL

[![Plugin](https://img.shields.io/badge/Claude_Code-Plugin-blueviolet)](https://docs.anthropic.com/en/docs/claude-code) [![Status](https://img.shields.io/badge/Status-Experimental-orange)]()

> **⚠️ EXPERIMENTAL** — This plugin is under active development. Scripts, commands, and output formats may change without notice. Test in non-critical projects first.

Deterministic security scanning layer for Claude Code.

Auto-detects your project's tech stack and runs appropriate open-source CLI tools (SAST, secret detection, dependency auditing, container and IaC scanning) to find and fix vulnerabilities. Every tool is free for private repositories, prefers local binaries, and produces a unified findings format so Claude can process results consistently. Docker is available as an opt-in fallback with pinned versions, read-only mounts, and network isolation. Two modes: **interactive** (review findings and choose what to fix) or **yolo** (auto-fix everything possible, then let Claude handle the rest).

> 🔧 The plugin ships 18 scanner wrappers and 4 orchestration scripts. The actual security analysis is deterministic (real CLI tools, not AI guessing) — Claude orchestrates the flow and handles the code-level fixes that tools can't auto-fix.

## 🚀 Commands

| Command | Description |
|---------|-------------|
| `/code-guardian:code-guardian-scan` | Main security scan — choose mode (interactive/yolo) and scope (codebase, uncommitted, unpushed) |
| `/code-guardian:code-guardian-setup` | Check which security tools are available for the detected stack, install missing ones |
| `/code-guardian:code-guardian-ci` | Generate CI security pipeline configuration for GitHub Actions, GitLab CI, or other systems |

## 🛠 Typical Workflow

1. **Run `/code-guardian:code-guardian-setup`** to check what security tools are available for your project's stack. The plugin auto-detects languages, frameworks, Docker, CI systems, and IaC, then reports which tools are installed locally, which have Docker images available (opt-in fallback), and which are missing with install commands.
2. **Run `/code-guardian:code-guardian-scan`** to kick off a security scan. You'll be asked to choose a mode and scope.
3. **Review the findings** — in interactive mode, findings are grouped by severity with a summary table. Choose to fix all high-severity issues, all auto-fixable issues, specific findings, or just report.
4. **Let the tools and Claude fix things** — tools with autofix support (Semgrep, ESLint, npm audit) handle what they can, and the security-fixer agent takes care of the rest with targeted code-level fixes.
5. **Run `/code-guardian:code-guardian-ci`** to add security scanning to your CI pipeline if you haven't already.

### Options

| Option | Values | Default | Description |
|--------|--------|---------|-------------|
| `--scope` | `codebase`, `uncommitted`, `unpushed` | `codebase` | What files to scan. `codebase` = all tracked files. `uncommitted` = staged + unstaged + untracked changes. `unpushed` = commits not yet pushed to remote. When scoped, dependency scanners (npm-audit, pip-audit, etc.) are skipped unless their lockfile/manifest is in the changed files. |
| `--tools` | comma-separated tool names | all available | Only run these specific tools (e.g. `--tools semgrep,gitleaks`). Others are skipped. |
| `--autofix` | — | off | Run tools with auto-fix flags and let the security-fixer agent handle the rest. |
| `--refresh` | — | off | Force re-detection of stack and tools, ignoring the 24-hour cache. |

These can also be set as persistent defaults in `.claude/code-guardian.config.json` — see [Configuration](#️-configuration) below. CLI arguments always override config values.

**Examples:**

```
/code-guardian:code-guardian-scan                              # scan everything, pick scope interactively
/code-guardian:code-guardian-scan --scope uncommitted          # only scan your local changes
/code-guardian:code-guardian-scan --scope unpushed             # scan commits not yet pushed
/code-guardian:code-guardian-scan --scope uncommitted --autofix  # auto-fix local changes
/code-guardian:code-guardian-scan --tools semgrep,gitleaks     # only run specific tools
```

## ⚙️ Configuration

Scan defaults can be persisted in `.claude/code-guardian.config.json` so you don't have to pass flags every time. Create it manually or run `/code-guardian:code-guardian-setup` to configure interactively.

```json
{
  "tools": ["semgrep", "gitleaks", "trivy"],
  "disabled": ["trufflehog"],
  "scope": "uncommitted",
  "autofix": false,
  "dockerFallback": false
}
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `tools` | `string[]` | all available | Only run these tools. Omit to run everything available. |
| `disabled` | `string[]` | none | Never run these tools, even if available. |
| `scope` | `string` | `"codebase"` | Default scan scope: `codebase`, `uncommitted`, or `unpushed`. |
| `autofix` | `boolean` | `false` | Auto-fix findings by default. |
| `dockerFallback` | `boolean` | `false` | Allow Docker images as fallback for tools not installed locally. |

**Precedence:** CLI flags always win over config values. `CG_DOCKER_FALLBACK=1` env var overrides the config `dockerFallback` setting. If both `tools` and `disabled` are set, `tools` takes precedence. Omitted keys use built-in defaults.

This file should be committed to the repo so the team shares the same scan defaults.

## 🔍 Scan Modes

### Interactive

Presents findings grouped by severity (high first), then by category. For each group you can:
- Fix all high severity
- Fix all auto-fixable
- Fix specific findings by number
- Skip and just report

### YOLO

Auto-fixes everything possible:
1. Runs tools with autofix flags (`semgrep --autofix`, `eslint --fix`, `npm audit fix`)
2. For remaining findings, Claude reads the affected files and applies code-level fixes
3. Re-scans to verify fixes
4. Reports final status: what was fixed, what remains

## 🧰 Supported Tools

All tools are free, open-source, and work on private repositories with no limitations.

| Category | Tool | Languages/Targets | Autofix | Docker Image |
|----------|------|-------------------|---------|--------------|
| SAST | Semgrep | Multi-language (30+) | Yes | `semgrep/semgrep` |
| SAST | Bandit | Python | No | `python:3-slim` |
| SAST | gosec | Go | No | `securego/gosec` |
| SAST | Brakeman | Ruby/Rails | No | `presidentbeef/brakeman` |
| SAST | ESLint (security) | JS/TS | Partial | — |
| SAST | PHPStan | PHP | No | `ghcr.io/phpstan/phpstan` |
| Secrets | Gitleaks | All | No | `zricethezav/gitleaks` |
| Secrets | TruffleHog | All (filesystem) | No | `trufflesecurity/trufflehog` |
| Dependencies | OSV-Scanner | All ecosystems | No | `ghcr.io/google/osv-scanner` |
| Dependencies | npm audit | JS/TS | Yes | — |
| Dependencies | pip-audit | Python | Yes | — |
| Dependencies | cargo-audit | Rust | No | — |
| Dependencies | bundler-audit | Ruby | No | — |
| Dependencies | govulncheck | Go | No | — |
| Container | Trivy | Images, FS, IaC | No | `aquasec/trivy` |
| Container | Hadolint | Dockerfiles | No | `hadolint/hadolint` |
| Container | Dockle | Docker images (manual) | No | `goodwithtech/dockle` |
| IaC | Checkov | Terraform, CFN, K8s | No | `bridgecrew/checkov` |

> Local installation is the recommended method for all tools. Tools with Docker images can optionally use Docker as a fallback when `dockerFallback` is enabled — see [Configuration](#️-configuration). Tools without a Docker image always require local installation. Run `/code-guardian:code-guardian-setup` to see what's needed and get install commands.

## 📦 Installation

One-command install via npx:

```bash
npx @stefanoginella/code-guardian
```

Or from the marketplace inside Claude Code:

```
/plugin marketplace add stefanoginella/claude-code-plugins
/plugin install code-guardian@stefanoginella-plugins --scope <project|user|local>
```

Scopes: `project` (shared with team), `user` (all your projects), `local` (personal, gitignored).

Or as a local plugin for development:

```bash
claude --plugin-dir /path/to/plugins/code-guardian
```

## 📋 Prerequisites

### Required

- `bash` — shell scripts
- `python3` — JSON parsing in scanner output processing

### Optional

- **Docker** — when explicitly opted in via `"dockerFallback": true` in config, the plugin can use official Docker images as a fallback for tools not installed locally. Docker images are pinned to specific versions, mounted read-only, and run with network isolation where possible. Without Docker or without opt-in, all tools must be installed locally.

### Security Tools

You don't need to install anything upfront. Run `/code-guardian:code-guardian-setup` and the plugin will:
1. Detect your stack
2. Show which tools are needed
3. Report which are installed locally vs. available via Docker
4. Show install commands for anything missing

Local installation is the primary execution method. Docker fallback is available as an opt-in alternative.

## 🏗 Architecture

```
code-guardian/
├── commands/              # Slash commands (scan, setup, ci)
├── agents/                # security-fixer agent for AI-assisted remediation
├── skills/                # Security scanning knowledge base
│   └── security-scanning/
│       ├── SKILL.md
│       └── references/
├── scripts/
│   ├── lib/               # Shared utilities and tool registry
│   │   ├── common.sh      # Colors, logging, Docker helpers, scope management
│   │   └── tool-registry.sh  # Stack → tools mapping, install commands, Docker images
│   ├── scanners/          # 18 individual scanner wrappers (unified JSONL output)
│   ├── detect-stack.sh    # Detects languages, frameworks, Docker, CI, IaC
│   ├── check-tools.sh     # Checks tool availability (local + Docker)
│   ├── scan.sh            # Main scan orchestrator
│   ├── generate-report.sh # Persistent markdown report generator
│   ├── ci-recommend.sh    # CI config generator
│   ├── read-config.sh     # Reads project config (.claude/code-guardian.config.json)
│   └── cache-state.sh     # Cache I/O for stack + tools detection results
└── .claude-plugin/
    └── plugin.json
```

### How the Deterministic Layer Works

Each scanner wrapper follows a local-first execution strategy:

1. **Local binary** (default) — If the tool is installed locally, it runs directly. Fastest option, zero overhead, respects your installed version and configuration.
2. **Docker image** (opt-in fallback) — If the tool isn't installed locally and Docker fallback is enabled (`"dockerFallback": true` in config or `CG_DOCKER_FALLBACK=1` env var), it runs via the tool's official Docker image with hardened security controls:
   - **Pinned versions** — Docker images use exact version tags from the tool registry, never `:latest`
   - **Read-only mounts** — Source code is mounted `:ro` (except for autofix mode in Semgrep)
   - **Network isolation** — `--network none` for tools that don't need network access (gitleaks, hadolint, checkov, gosec, brakeman, trufflehog, phpstan, osv-scanner, dockle)
   - **Minimal socket access** — Docker socket only mounted for image-scanning tools (trivy image mode, dockle)

After choosing the execution environment, each wrapper:
1. Runs the tool with appropriate flags for the requested scope
2. Parses the tool's native output (JSON/SARIF/text) into a unified JSONL format
3. Reports finding count to stderr, returns findings file path to stdout

The unified finding format:
```json
{"tool":"semgrep","severity":"high","rule":"rule-id","message":"description","file":"path/to/file","line":42,"autoFixable":true,"category":"sast"}
```

This means Claude always gets findings in the same shape regardless of which tool produced them — consistent processing, no tool-specific parsing logic in the AI layer.

### State Caching

The plugin caches stack detection and tool availability results in `.claude/code-guardian-cache.json` (already gitignored). This avoids re-running Docker checks and binary lookups on every command.

- **`setup`** writes the cache after detecting the stack and verifying tools
- **`scan`** and **`ci`** read from the cache if it's fresh (< 24 hours), skipping re-detection
- Cache is invalidated automatically if it's older than 24 hours or the project path changes
- Use `--refresh` on the scan command to bypass the cache and force re-detection

## 📝 Scan Reports

Each scan automatically saves a detailed markdown report to `.code-guardian/scan-reports/scan-report-YYYYMMDD-HHMMSS.md`. Reports are timestamped so multiple scans never overwrite each other.

**Report contents:**
- Header with date, scope, and scanners run
- Summary table with finding counts by severity
- Per-tool breakdown table
- Every finding as a `- [ ]` checkbox item, grouped by severity (high first), with tool, rule ID, message, file location, and auto-fixable flag
- Skipped tools (with install commands) and failed tools
- Scope-skipped dependency scanners (when using `--scope uncommitted` or `--scope unpushed`)

**Remediation tracking:** Open the report in any markdown editor and check off items (`- [x]`) as you fix them. The reports persist in your project directory — add `.code-guardian/` to `.gitignore` if you don't want them committed, or commit them to track remediation progress across the team.

## 🔐 Permissions

The scan command runs bash scripts that invoke Docker or local CLI tools. Claude Code will prompt you to approve these if they aren't already in your allow list. For smoother runs, consider adding these patterns to your project's `.claude/settings.json` under `permissions.allow`:

- `Bash(bash */code-guardian/scripts/*)`

## 📄 License

[MIT](../../LICENSE)
