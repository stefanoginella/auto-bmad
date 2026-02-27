# 🛡 Code Guardian — EXPERIMENTAL

[![Plugin](https://img.shields.io/badge/Claude_Code-Plugin-blueviolet)](https://docs.anthropic.com/en/docs/claude-code) [![Status](https://img.shields.io/badge/Status-Experimental-orange)]()

> **⚠️ EXPERIMENTAL** — This plugin is under active development. Scripts, commands, and output formats may change without notice. Test in non-critical projects first.

Deterministic security scanning layer for Claude Code.

Auto-detects your project's tech stack and runs appropriate open-source CLI tools (SAST, secret detection, dependency auditing, container and IaC scanning) to find and fix vulnerabilities. Every tool is free for private repositories, runs via Docker when available, and produces a unified findings format so Claude can process results consistently. Two modes: **interactive** (review findings and choose what to fix) or **yolo** (auto-fix everything possible, then let Claude handle the rest).

> 🔧 The plugin ships 18 scanner wrappers and 4 orchestration scripts. The actual security analysis is deterministic (real CLI tools, not AI guessing) — Claude orchestrates the flow and handles the code-level fixes that tools can't auto-fix.

## 🚀 Commands

| Command | Description |
|---------|-------------|
| `/code-guardian:code-guardian-scan` | Main security scan — choose mode (interactive/yolo) and scope (codebase, uncommitted, unpushed) |
| `/code-guardian:code-guardian-setup` | Check which security tools are available for the detected stack, install missing ones |
| `/code-guardian:code-guardian-ci` | Generate CI security pipeline configuration for GitHub Actions, GitLab CI, or other systems |

## 🛠 Typical Workflow

1. **Run `/code-guardian:code-guardian-setup`** to check what security tools are available for your project's stack. The plugin auto-detects languages, frameworks, Docker, CI systems, and IaC, then reports which tools are available (via Docker or local binary) and which are missing with install commands.
2. **Run `/code-guardian:code-guardian-scan`** to kick off a security scan. You'll be asked to choose a mode and scope.
3. **Review the findings** — in interactive mode, findings are grouped by severity with a summary table. Choose to fix all high-severity issues, all auto-fixable issues, specific findings, or just report.
4. **Let the tools and Claude fix things** — tools with autofix support (Semgrep, ESLint, npm audit) handle what they can, and the security-fixer agent takes care of the rest with targeted code-level fixes.
5. **Run `/code-guardian:code-guardian-ci`** to add security scanning to your CI pipeline if you haven't already.

> ℹ️ **Scope options**: `codebase` (all tracked files), `uncommitted` (all local uncommitted work — staged + unstaged + untracked), or `unpushed` (all commits not yet pushed, compared against a base ref you choose).

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
| SAST | Bandit | Python | No | — |
| SAST | gosec | Go | No | `securego/gosec` |
| SAST | Brakeman | Ruby/Rails | No | `presidentbeef/brakeman` |
| SAST | ESLint (security) | JS/TS | Partial | — |
| SAST | PHPStan | PHP | No | `ghcr.io/phpstan/phpstan` |
| Secrets | Gitleaks | All | No | `zricethezav/gitleaks` |
| Secrets | TruffleHog | All (filesystem + git) | No | `trufflesecurity/trufflehog` |
| Dependencies | OSV-Scanner | All ecosystems | No | `ghcr.io/google/osv-scanner` |
| Dependencies | npm audit | JS/TS | Yes | — |
| Dependencies | pip-audit | Python | Yes | — |
| Dependencies | cargo-audit | Rust | No | — |
| Dependencies | bundler-audit | Ruby | No | — |
| Dependencies | govulncheck | Go | No | — |
| Container | Trivy | Images, FS, IaC | No | `aquasec/trivy` |
| Container | Hadolint | Dockerfiles | No | `hadolint/hadolint` |
| Container | Dockle | Docker images | No | `goodwithtech/dockle` |
| IaC | Checkov | Terraform, CFN, K8s | No | `bridgecrew/checkov` |

> ⚠️ Tools without a Docker image require local installation. The plugin will tell you exactly what to install and how — or you can run `/code-guardian:code-guardian-setup` to walk through it interactively.

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

### Recommended

- **Docker** — the plugin prefers running tools via their official Docker images. This avoids installation headaches, ensures consistent versions, and keeps your system clean. Without Docker, tools must be installed locally.

### Security Tools

You don't need to install anything upfront. Run `/code-guardian:code-guardian-setup` and the plugin will:
1. Detect your stack
2. Show which tools are needed
3. Report which are available via Docker or locally
4. Show install commands for anything missing

Tools with Docker images work out of the box if Docker is running — no local installation needed.

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
│   │   ├── common.sh      # Colors, logging, container detection, scope management
│   │   └── tool-registry.sh  # Stack → tools mapping, install commands, Docker images
│   ├── scanners/          # 18 individual scanner wrappers (unified JSONL output)
│   ├── detect-stack.sh    # Detects languages, frameworks, Docker, CI, IaC
│   ├── check-tools.sh     # Checks tool availability (container + Docker + local)
│   ├── scan.sh            # Main scan orchestrator
│   ├── ci-recommend.sh    # CI config generator
│   └── cache-state.sh     # Cache I/O for stack + tools detection results
└── .claude-plugin/
    └── plugin.json
```

### How the Deterministic Layer Works

Each scanner wrapper follows a three-tier execution strategy:

1. **Project container** — If docker-compose services are running, the plugin probes them for tool binaries. If semgrep is already installed in your `app` or `dev` container, it runs there. No extra images pulled, no re-installation.
2. **Standalone Docker image** — If the tool isn't in a running container but Docker is available, it runs via the tool's official Docker image (pulled on demand).
3. **Local binary** — Falls back to a locally installed binary if neither container option is available.

This means if your `docker-compose.yml` already has a service with security tools installed, code-guardian will find and use them automatically — no duplication.

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

The plugin caches stack detection and tool availability results in `.claude/code-guardian-cache.json` (already gitignored). This avoids re-running container probing, Docker checks, and binary lookups on every command.

- **`setup`** writes the cache after detecting the stack and verifying tools
- **`scan`** and **`ci`** read from the cache if it's fresh (< 24 hours), skipping re-detection
- Cache is invalidated automatically if it's older than 24 hours or the project path changes
- Use `--refresh` on the scan command to bypass the cache and force re-detection

## 🔐 Permissions

The scan command runs bash scripts that invoke Docker or local CLI tools. Claude Code will prompt you to approve these if they aren't already in your allow list. For smoother runs, consider adding these patterns to your project's `.claude/settings.json` under `permissions.allow`:

- `Bash(bash */code-guardian/scripts/*)`

> ⚠️ Alternatively, you can run Claude Code in `--dangerously-skip-permissions` mode, but do so at your own risk — this disables **all** permission checks. Only use it in an isolated environment.

## 📄 License

[MIT](../../LICENSE)
