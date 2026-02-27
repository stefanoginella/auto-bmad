#!/usr/bin/env bash
# Tool registry: maps stacks to tools, provides install commands and Docker images
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

# ── Tool definitions ──────────────────────────────────────────────────
# Format: TOOL_<name>_DOCKER, TOOL_<name>_INSTALL_<os>, TOOL_<name>_CATEGORY

# Semgrep — multi-language SAST
TOOL_SEMGREP_DOCKER="semgrep/semgrep:latest"
TOOL_SEMGREP_INSTALL_MACOS="pip3 install semgrep"
TOOL_SEMGREP_INSTALL_LINUX="pip3 install semgrep"
TOOL_SEMGREP_CATEGORY="sast"

# Trivy — vulnerability scanner (containers, fs, IaC)
TOOL_TRIVY_DOCKER="aquasec/trivy:latest"
TOOL_TRIVY_INSTALL_MACOS="brew install trivy"
TOOL_TRIVY_INSTALL_LINUX="curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin"
TOOL_TRIVY_CATEGORY="vulnerability"

# Gitleaks — secret detection
TOOL_GITLEAKS_DOCKER="zricethezav/gitleaks:latest"
TOOL_GITLEAKS_INSTALL_MACOS="brew install gitleaks"
TOOL_GITLEAKS_INSTALL_LINUX="curl -sSfL https://github.com/gitleaks/gitleaks/releases/latest/download/gitleaks-linux-amd64 -o /usr/local/bin/gitleaks && chmod +x /usr/local/bin/gitleaks"
TOOL_GITLEAKS_CATEGORY="secrets"

# Hadolint — Dockerfile linter
TOOL_HADOLINT_DOCKER="hadolint/hadolint:latest"
TOOL_HADOLINT_INSTALL_MACOS="brew install hadolint"
TOOL_HADOLINT_INSTALL_LINUX="curl -sSfL https://github.com/hadolint/hadolint/releases/latest/download/hadolint-Linux-x86_64 -o /usr/local/bin/hadolint && chmod +x /usr/local/bin/hadolint"
TOOL_HADOLINT_CATEGORY="container"

# Checkov — IaC scanner
TOOL_CHECKOV_DOCKER="bridgecrew/checkov:latest"
TOOL_CHECKOV_INSTALL_MACOS="pip3 install checkov"
TOOL_CHECKOV_INSTALL_LINUX="pip3 install checkov"
TOOL_CHECKOV_CATEGORY="iac"

# npm audit — JS/TS dependency audit
TOOL_NPM_AUDIT_DOCKER=""
TOOL_NPM_AUDIT_INSTALL_MACOS="(bundled with Node.js)"
TOOL_NPM_AUDIT_INSTALL_LINUX="(bundled with Node.js)"
TOOL_NPM_AUDIT_CATEGORY="dependency"

# pip-audit — Python dependency audit
TOOL_PIP_AUDIT_DOCKER=""
TOOL_PIP_AUDIT_INSTALL_MACOS="pip3 install pip-audit"
TOOL_PIP_AUDIT_INSTALL_LINUX="pip3 install pip-audit"
TOOL_PIP_AUDIT_CATEGORY="dependency"

# Bandit — Python SAST
TOOL_BANDIT_DOCKER=""
TOOL_BANDIT_INSTALL_MACOS="pip3 install bandit"
TOOL_BANDIT_INSTALL_LINUX="pip3 install bandit"
TOOL_BANDIT_CATEGORY="sast"

# gosec — Go SAST
TOOL_GOSEC_DOCKER="securego/gosec:latest"
TOOL_GOSEC_INSTALL_MACOS="brew install gosec"
TOOL_GOSEC_INSTALL_LINUX="curl -sfL https://raw.githubusercontent.com/securego/gosec/master/install.sh | sh -s -- -b /usr/local/bin"
TOOL_GOSEC_CATEGORY="sast"

# govulncheck — Go vulnerability checker
TOOL_GOVULNCHECK_DOCKER=""
TOOL_GOVULNCHECK_INSTALL_MACOS="go install golang.org/x/vuln/cmd/govulncheck@latest"
TOOL_GOVULNCHECK_INSTALL_LINUX="go install golang.org/x/vuln/cmd/govulncheck@latest"
TOOL_GOVULNCHECK_CATEGORY="dependency"

# cargo-audit — Rust dependency audit
TOOL_CARGO_AUDIT_DOCKER=""
TOOL_CARGO_AUDIT_INSTALL_MACOS="cargo install cargo-audit"
TOOL_CARGO_AUDIT_INSTALL_LINUX="cargo install cargo-audit"
TOOL_CARGO_AUDIT_CATEGORY="dependency"

# bundler-audit — Ruby dependency audit
TOOL_BUNDLER_AUDIT_DOCKER=""
TOOL_BUNDLER_AUDIT_INSTALL_MACOS="gem install bundler-audit"
TOOL_BUNDLER_AUDIT_INSTALL_LINUX="gem install bundler-audit"
TOOL_BUNDLER_AUDIT_CATEGORY="dependency"

# Brakeman — Ruby/Rails SAST
TOOL_BRAKEMAN_DOCKER="presidentbeef/brakeman:latest"
TOOL_BRAKEMAN_INSTALL_MACOS="gem install brakeman"
TOOL_BRAKEMAN_INSTALL_LINUX="gem install brakeman"
TOOL_BRAKEMAN_CATEGORY="sast"

# eslint (security plugin) — JS/TS security linting
TOOL_ESLINT_SECURITY_DOCKER=""
TOOL_ESLINT_SECURITY_INSTALL_MACOS="npm install -g eslint eslint-plugin-security"
TOOL_ESLINT_SECURITY_INSTALL_LINUX="npm install -g eslint eslint-plugin-security"
TOOL_ESLINT_SECURITY_CATEGORY="sast"

# Dockle — container image linter
TOOL_DOCKLE_DOCKER="goodwithtech/dockle:latest"
TOOL_DOCKLE_INSTALL_MACOS="brew install goodwithtech/r/dockle"
TOOL_DOCKLE_INSTALL_LINUX="curl -sSfL https://github.com/goodwithtech/dockle/releases/latest/download/dockle_Linux-64bit.tar.gz | tar xz -C /usr/local/bin"
TOOL_DOCKLE_CATEGORY="container"

# TruffleHog — secret detection (OSS)
TOOL_TRUFFLEHOG_DOCKER="trufflesecurity/trufflehog:latest"
TOOL_TRUFFLEHOG_INSTALL_MACOS="brew install trufflehog"
TOOL_TRUFFLEHOG_INSTALL_LINUX="curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh | sh -s -- -b /usr/local/bin"
TOOL_TRUFFLEHOG_CATEGORY="secrets"

# OSV-Scanner — universal dependency vulnerability scanner
TOOL_OSV_SCANNER_DOCKER="ghcr.io/google/osv-scanner:latest"
TOOL_OSV_SCANNER_INSTALL_MACOS="brew install osv-scanner"
TOOL_OSV_SCANNER_INSTALL_LINUX="curl -sSfL https://github.com/google/osv-scanner/releases/latest/download/osv-scanner_linux_amd64 -o /usr/local/bin/osv-scanner && chmod +x /usr/local/bin/osv-scanner"
TOOL_OSV_SCANNER_CATEGORY="dependency"

# PHPStan — PHP static analysis
TOOL_PHPSTAN_DOCKER="ghcr.io/phpstan/phpstan:latest"
TOOL_PHPSTAN_INSTALL_MACOS="composer global require phpstan/phpstan"
TOOL_PHPSTAN_INSTALL_LINUX="composer global require phpstan/phpstan"
TOOL_PHPSTAN_CATEGORY="sast"

# ── Stack to tool mapping ─────────────────────────────────────────────
# Returns tool names relevant for a given stack component
# Usage: get_tools_for_stack <stack_component>
get_tools_for_stack() {
  local component="$1"
  case "$component" in
    javascript|typescript|nodejs)
      echo "semgrep gitleaks trufflehog npm-audit eslint-security osv-scanner"
      ;;
    python)
      echo "semgrep gitleaks trufflehog bandit pip-audit osv-scanner"
      ;;
    go)
      echo "semgrep gitleaks trufflehog gosec govulncheck osv-scanner"
      ;;
    rust)
      echo "semgrep gitleaks trufflehog cargo-audit osv-scanner"
      ;;
    ruby)
      echo "semgrep gitleaks trufflehog bundler-audit brakeman osv-scanner"
      ;;
    java|kotlin)
      echo "semgrep gitleaks trufflehog trivy osv-scanner"
      ;;
    php)
      echo "semgrep gitleaks trufflehog phpstan osv-scanner"
      ;;
    csharp|dotnet)
      echo "semgrep gitleaks trufflehog osv-scanner"
      ;;
    docker)
      echo "trivy hadolint dockle"
      ;;
    terraform|cloudformation|kubernetes|iac)
      echo "checkov trivy"
      ;;
    *)
      echo "semgrep gitleaks trufflehog"
      ;;
  esac
}

# Get the local binary name for a tool
get_tool_binary() {
  local tool="$1"
  case "$tool" in
    npm-audit) echo "npm" ;;
    pip-audit) echo "pip-audit" ;;
    cargo-audit) echo "cargo-audit" ;;
    bundler-audit) echo "bundler-audit" ;;
    eslint-security) echo "eslint" ;;
    osv-scanner) echo "osv-scanner" ;;
    phpstan) echo "phpstan" ;;
    *) echo "$tool" ;;
  esac
}

# Get Docker image for a tool (empty string if no Docker image)
get_tool_docker_image() {
  local tool="$1"
  local var_name
  var_name="TOOL_$(echo "$tool" | tr '[:lower:]-' '[:upper:]_')_DOCKER"
  echo "${!var_name:-}"
}

# Get install command for a tool
get_tool_install_cmd() {
  local tool="$1"
  local os
  os=$(uname -s)
  local suffix="LINUX"
  [[ "$os" == "Darwin" ]] && suffix="MACOS"
  local var_name
  var_name="TOOL_$(echo "$tool" | tr '[:lower:]-' '[:upper:]_')_INSTALL_${suffix}"
  echo "${!var_name:-}"
}

# Get tool category
get_tool_category() {
  local tool="$1"
  local var_name
  var_name="TOOL_$(echo "$tool" | tr '[:lower:]-' '[:upper:]_')_CATEGORY"
  echo "${!var_name:-unknown}"
}

# Check if a tool is available (project container, Docker image, or local)
# Returns: "container:<service>", "docker", "local", or "unavailable"
# NOTE: call detect_container_tools() before this for container detection to work
check_tool_availability() {
  local tool="$1"
  local binary docker_image
  binary=$(get_tool_binary "$tool")
  docker_image=$(get_tool_docker_image "$tool")

  # 1. Check running project containers
  local container_service
  container_service=$(get_container_service_for_tool "$binary" 2>/dev/null || true)
  if [[ -n "$container_service" ]]; then
    echo "container:${container_service}"
    return
  fi

  # 2. Standalone Docker image
  if [[ -n "$docker_image" ]] && docker_available; then
    echo "docker"
    return
  fi

  # 3. Local binary
  if cmd_exists "$binary"; then
    echo "local"
    return
  fi

  echo "unavailable"
}
