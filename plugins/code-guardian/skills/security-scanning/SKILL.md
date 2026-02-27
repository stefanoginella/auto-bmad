---
name: security-scanning
description: "Provides knowledge about code-guardian's security scanning tools, result interpretation, and vulnerability fix patterns. Auto-activates when users ask about security scanning, vulnerability remediation, SAST tools, secret detection, dependency auditing, or container security in the context of code-guardian. Use when the user asks `how do I fix this vulnerability`, `what security tools should I use`, `explain this security finding`, or `how does code-guardian work`."
---

# Security Scanning Knowledge

## code-guardian Overview

code-guardian is a deterministic security scanning plugin for Claude Code. It detects the project stack and runs appropriate open-source CLI tools. All tools are free for private repositories.

### Commands
- `/code-guardian:code-guardian-scan` — Main security scan (interactive or yolo mode)
- `/code-guardian:code-guardian-setup` — Check and install required tools
- `/code-guardian:code-guardian-ci` — Generate CI security pipeline config

### How It Works
1. `detect-stack.sh` identifies languages, frameworks, Docker, CI, IaC
2. `check-tools.sh` verifies tool availability (Docker-first, local fallback)
3. `scan.sh` orchestrates running relevant scanners
4. Each scanner outputs unified JSONL findings
5. Claude (or security-fixer agent) applies fixes

## Tool Reference

### Multi-Language SAST
**Semgrep** — Pattern-based static analysis. Supports 30+ languages. Has autofix.
- Runs: `semgrep --config auto` (uses community rules)
- Autofix: `semgrep --config auto --autofix`
- Docker: `semgrep/semgrep:latest`

### Secret Detection
**Gitleaks** — Scans git history and working tree for secrets (API keys, passwords, tokens).
- Docker: `zricethezav/gitleaks:latest`
- No autofix (secrets must be rotated manually)

**TruffleHog** — Deep secret detection across filesystem and git history using detector-based verification.
- Docker: `trufflesecurity/trufflehog:latest`
- No autofix (secrets must be rotated manually)
- Complements Gitleaks with different detection heuristics

### Dependency Vulnerability Scanning
| Tool | Language | Autofix |
|------|----------|---------|
| `npm audit` | JS/TS | Yes (`npm audit fix`) |
| `pip-audit` | Python | Yes (`--fix`) |
| `cargo-audit` | Rust | No |
| `bundler-audit` | Ruby | No |
| `govulncheck` | Go | No |
| `osv-scanner` | All ecosystems | No |

### Container Security
**Trivy** — Scans container images, filesystems, IaC for vulnerabilities.
- Modes: `fs` (filesystem), `image` (Docker image), `config` (IaC)
- Docker: `aquasec/trivy:latest`

**Hadolint** — Dockerfile linter. Checks for best practice violations.
- Docker: `hadolint/hadolint:latest`

**Dockle** — Container image linter. Checks CIS benchmarks.
- Docker: `goodwithtech/dockle:latest`

### Language-Specific SAST
| Tool | Language | Autofix |
|------|----------|---------|
| Bandit | Python | No |
| gosec | Go | No |
| Brakeman | Ruby/Rails | No |
| ESLint (security) | JS/TS | Partial |
| PHPStan | PHP | No |

### IaC Security
**Checkov** — Scans Terraform, CloudFormation, Kubernetes, Helm for misconfigurations.
- Docker: `bridgecrew/checkov:latest`

## Unified Finding Format

All scanners output JSONL with this schema:
```json
{
  "tool": "scanner-name",
  "severity": "high|medium|low|info",
  "rule": "rule-identifier",
  "message": "human-readable description",
  "file": "relative/path/to/file",
  "line": 42,
  "autoFixable": true,
  "category": "sast|secrets|dependency|container|iac"
}
```

## Common Vulnerability Fix Patterns

For detailed fix patterns, see `references/fix-patterns.md`.

## Scan Scope Options

| Scope | What It Scans |
|-------|---------------|
| `codebase` | All tracked files |
| `uncommitted` | All local uncommitted work (staged + unstaged + untracked) |
| `unpushed` | All changes since diverging from base |
