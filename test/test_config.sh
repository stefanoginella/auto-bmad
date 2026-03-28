#!/usr/bin/env bash
# test/test_config.sh — Unit tests for config cascade in lib/config.sh
# Run: bash test/test_config.sh

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

echo ""
echo -e "${_T_BOLD}Config cascade tests${_T_NC}"
echo ""

# --- Bootstrap minimal environment ---
source "${REPO_ROOT}/lib/core.sh"
INTERACTIVE=false
source "${REPO_ROOT}/lib/tracking.sh"

# We need to control INSTALL_DIR, PROJECT_ROOT, and _USER_CONF_DIR
# to test the three-layer cascade. Reset state before each group.

_reset_config_state() {
    # Unload config.sh so it can be re-sourced with fresh paths
    _CONFIG_SH_LOADED=""
    _PIPELINE_CONF_LOADED=false
    _PROFILES_LOADED=false
    _STEP_CONFIG_CACHE_LOADED=false

    # Reset all cfg_pip_* to empty so we can detect which layer set them
    cfg_pip_pr_safety=""
    cfg_pip_pr_poll_interval=""
    cfg_pip_pr_grace_polls=""
    cfg_pip_min_step_duration=""
    cfg_pip_min_log_bytes=""
    cfg_pip_preflight_max_age=""
    cfg_pip_spinner_quiet=""
    cfg_pip_branch_pattern=""
    cfg_pip_min_git_version=""
    cfg_pip_default_review_mode=""
    cfg_pip_parallel_stagger=""
    cfg_pip_min_reviewers=""
    cfg_pip_max_step_duration=""
    cfg_pip_max_output_rate=""
    cfg_pip_file_churn_threshold=""

    # Clear env overrides
    unset AUTO_BMAD_TIMEOUTS_PR_SAFETY 2>/dev/null || true
    unset AUTO_BMAD_THRESHOLDS_MIN_STEP_DURATION 2>/dev/null || true
    unset AUTO_BMAD_GIT_BRANCH_PATTERN 2>/dev/null || true
    unset AUTO_BMAD_GUARD_MAX_STEP_DURATION 2>/dev/null || true

    # Clear profile arrays
    _PROFILE_NAMES=()
    _PROFILE_CLIS=()
    _PROFILE_MODELS=()
    _PROFILE_EFFORTS=()
    _PROFILE_FALLBACKS=()
}

# ═══════════════════════════════════════════════════
# _parse_pipeline_file — single file parsing
# ═══════════════════════════════════════════════════

# Source config.sh once to get the functions
INSTALL_DIR="$REPO_ROOT"
PROJECT_ROOT="$REPO_ROOT"
source "${REPO_ROOT}/lib/config.sh"

test_begin "parse: reads [timeouts] section"
_reset_config_state
tmp="$(make_test_tmpdir)"
cat > "${tmp}/pipeline.conf" <<'EOF'
[timeouts]
pr_safety = 3600
pr_poll_interval = 15
EOF
_parse_pipeline_file "${tmp}/pipeline.conf"
assert_eq "3600" "$cfg_pip_pr_safety"

test_begin "parse: reads [thresholds] section"
_reset_config_state
cat > "${tmp}/pipeline.conf" <<'EOF'
[thresholds]
min_step_duration = 10
min_log_bytes = 500
min_reviewers = 3
EOF
_parse_pipeline_file "${tmp}/pipeline.conf"
assert_eq "10" "$cfg_pip_min_step_duration"

test_begin "parse: reads [guard] section"
_reset_config_state
cat > "${tmp}/pipeline.conf" <<'EOF'
[guard]
max_step_duration = 300
max_output_rate = 100000
file_churn_threshold = 5
EOF
_parse_pipeline_file "${tmp}/pipeline.conf"
assert_eq "300" "$cfg_pip_max_step_duration"

test_begin "parse: reads [git] section"
_reset_config_state
cat > "${tmp}/pipeline.conf" <<'EOF'
[git]
branch_pattern = feature/${STORY_ID}
min_git_version = 2.30
default_review_mode = fast
EOF
_parse_pipeline_file "${tmp}/pipeline.conf"
assert_eq 'feature/${STORY_ID}' "$cfg_pip_branch_pattern"

test_begin "parse: ignores comments and blank lines"
_reset_config_state
cat > "${tmp}/pipeline.conf" <<'EOF'
# This is a comment
[timeouts]
# Another comment
pr_safety = 9999

# blank lines above and below

pr_poll_interval = 42
EOF
_parse_pipeline_file "${tmp}/pipeline.conf"
assert_eq "9999" "$cfg_pip_pr_safety"

test_begin "parse: trims whitespace around = sign"
_reset_config_state
cat > "${tmp}/pipeline.conf" <<'EOF'
[thresholds]
min_step_duration   =   7
EOF
_parse_pipeline_file "${tmp}/pipeline.conf"
assert_eq "7" "$cfg_pip_min_step_duration"

# ═══════════════════════════════════════════════════
# Cascade: INSTALL_DIR → _USER_CONF_DIR → PROJECT_ROOT
# ═══════════════════════════════════════════════════

test_begin "cascade: install dir provides defaults"
_reset_config_state
_CONFIG_SH_LOADED=""
_PIPELINE_CONF_LOADED=false

local_install="$(make_test_tmpdir)"
local_user="$(make_test_tmpdir)"
local_project="$(make_test_tmpdir)"

mkdir -p "${local_install}/conf" "${local_user}" "${local_project}/conf"
cat > "${local_install}/conf/pipeline.conf" <<'EOF'
[timeouts]
pr_safety = 1000
pr_poll_interval = 10
[thresholds]
min_step_duration = 3
EOF

INSTALL_DIR="$local_install"
PROJECT_ROOT="$local_project"
_USER_CONF_DIR="$local_user"
# No user or project conf files — only install dir

load_pipeline_conf
assert_eq "1000" "$cfg_pip_pr_safety"

test_begin "cascade: user dir overrides install dir"
_reset_config_state
_PIPELINE_CONF_LOADED=false

cat > "${local_install}/conf/pipeline.conf" <<'EOF'
[timeouts]
pr_safety = 1000
pr_poll_interval = 10
EOF
cat > "${local_user}/pipeline.conf" <<'EOF'
[timeouts]
pr_safety = 2000
EOF

INSTALL_DIR="$local_install"
PROJECT_ROOT="$local_project"
_USER_CONF_DIR="$local_user"

load_pipeline_conf
assert_eq "2000" "$cfg_pip_pr_safety"

test_begin "cascade: user dir preserves non-overridden values from install"
# pr_poll_interval was only in install dir
assert_eq "10" "$cfg_pip_pr_poll_interval"

test_begin "cascade: project dir overrides both"
_reset_config_state
_PIPELINE_CONF_LOADED=false

cat > "${local_install}/conf/pipeline.conf" <<'EOF'
[timeouts]
pr_safety = 1000
pr_poll_interval = 10
[thresholds]
min_step_duration = 3
EOF
cat > "${local_user}/pipeline.conf" <<'EOF'
[timeouts]
pr_safety = 2000
EOF
cat > "${local_project}/conf/pipeline.conf" <<'EOF'
[timeouts]
pr_safety = 3000
[thresholds]
min_step_duration = 8
EOF

INSTALL_DIR="$local_install"
PROJECT_ROOT="$local_project"
_USER_CONF_DIR="$local_user"

load_pipeline_conf
assert_eq "3000" "$cfg_pip_pr_safety"

test_begin "cascade: project dir overrides user dir override"
assert_eq "8" "$cfg_pip_min_step_duration"

test_begin "cascade: middle layer still wins when top layer absent"
# pr_poll_interval: only in install (10) — not overridden
assert_eq "10" "$cfg_pip_pr_poll_interval"

# ═══════════════════════════════════════════════════
# Environment variable overrides
# ═══════════════════════════════════════════════════

test_begin "env override: AUTO_BMAD_TIMEOUTS_PR_SAFETY wins over all layers"
_reset_config_state
_PIPELINE_CONF_LOADED=false

cat > "${local_install}/conf/pipeline.conf" <<'EOF'
[timeouts]
pr_safety = 1000
EOF
cat > "${local_project}/conf/pipeline.conf" <<'EOF'
[timeouts]
pr_safety = 3000
EOF
# Remove user conf to simplify
rm -f "${local_user}/pipeline.conf"

INSTALL_DIR="$local_install"
PROJECT_ROOT="$local_project"
_USER_CONF_DIR="$local_user"
export AUTO_BMAD_TIMEOUTS_PR_SAFETY=9999

load_pipeline_conf
assert_eq "9999" "$cfg_pip_pr_safety"

test_begin "env override: AUTO_BMAD_THRESHOLDS_MIN_STEP_DURATION"
_reset_config_state
_PIPELINE_CONF_LOADED=false

cat > "${local_install}/conf/pipeline.conf" <<'EOF'
[thresholds]
min_step_duration = 5
EOF
rm -f "${local_project}/conf/pipeline.conf"

INSTALL_DIR="$local_install"
PROJECT_ROOT="$local_project"
_USER_CONF_DIR="$local_user"
export AUTO_BMAD_THRESHOLDS_MIN_STEP_DURATION=42

load_pipeline_conf
assert_eq "42" "$cfg_pip_min_step_duration"

test_begin "env override: AUTO_BMAD_GIT_BRANCH_PATTERN"
_reset_config_state
_PIPELINE_CONF_LOADED=false

cat > "${local_install}/conf/pipeline.conf" <<'EOF'
[git]
branch_pattern = story/${STORY_ID}
EOF

INSTALL_DIR="$local_install"
PROJECT_ROOT="$local_project"
_USER_CONF_DIR="$local_user"
export AUTO_BMAD_GIT_BRANCH_PATTERN='feat/${STORY_ID}'

load_pipeline_conf
assert_eq 'feat/${STORY_ID}' "$cfg_pip_branch_pattern"

# ═══════════════════════════════════════════════════
# Idempotency
# ═══════════════════════════════════════════════════

test_begin "load_pipeline_conf: idempotent (second call is no-op)"
# _PIPELINE_CONF_LOADED is now true from previous test
# Change the file — should NOT be re-read
cat > "${local_install}/conf/pipeline.conf" <<'EOF'
[timeouts]
pr_safety = 7777
EOF
load_pipeline_conf
# Should still have the value from the previous load, not 7777
assert_ne "7777" "$cfg_pip_pr_safety"

# ═══════════════════════════════════════════════════
# Defaults when no conf files exist
# ═══════════════════════════════════════════════════

test_begin "defaults: cfg_pip_* have sane defaults when no files exist"
_reset_config_state
_PIPELINE_CONF_LOADED=false

empty_install="$(make_test_tmpdir)"
empty_project="$(make_test_tmpdir)"
empty_user="$(make_test_tmpdir)"
mkdir -p "${empty_install}/conf" "${empty_project}/conf"
# No pipeline.conf anywhere

INSTALL_DIR="$empty_install"
PROJECT_ROOT="$empty_project"
_USER_CONF_DIR="$empty_user"
# Unset env vars
unset AUTO_BMAD_TIMEOUTS_PR_SAFETY 2>/dev/null || true
unset AUTO_BMAD_THRESHOLDS_MIN_STEP_DURATION 2>/dev/null || true
unset AUTO_BMAD_GIT_BRANCH_PATTERN 2>/dev/null || true
unset AUTO_BMAD_GUARD_MAX_STEP_DURATION 2>/dev/null || true

load_pipeline_conf
# Should get the hardcoded defaults from config.sh globals
# (they were reset to "" by _reset_config_state, but load_pipeline_conf
#  uses ${VAR:-default} from env-var overrides, which falls back to current value)
# The hardcoded defaults live in the cfg_pip_* declarations at module top
# Since we reset them, the env override falls back to empty string
# This is actually testing that the defaults survive — re-source config.sh
_reset_config_state
_CONFIG_SH_LOADED=""
_PIPELINE_CONF_LOADED=false
source "${REPO_ROOT}/lib/config.sh"
INSTALL_DIR="$empty_install"
PROJECT_ROOT="$empty_project"
_USER_CONF_DIR="$empty_user"
load_pipeline_conf
assert_eq "7200" "$cfg_pip_pr_safety"

# ═══════════════════════════════════════════════════
# _resolve_branch_name
# ═══════════════════════════════════════════════════

test_begin "_resolve_branch_name: default pattern"
cfg_pip_branch_pattern='story/${STORY_ID}'
result="$(_resolve_branch_name "1-2-auth")"
assert_eq "story/1-2-auth" "$result"

test_begin "_resolve_branch_name: custom pattern with \${STORY_ID}"
cfg_pip_branch_pattern='feature/${STORY_ID}/impl'
result="$(_resolve_branch_name "3-1-dashboard")"
assert_eq "feature/3-1-dashboard/impl" "$result"

test_begin "_resolve_branch_name: pattern with \$STORY_ID (no braces)"
cfg_pip_branch_pattern='fix/$STORY_ID'
result="$(_resolve_branch_name "2-1-bug")"
assert_eq "fix/2-1-bug" "$result"

test_begin "_resolve_branch_name: empty pattern falls back to default"
cfg_pip_branch_pattern=''
result="$(_resolve_branch_name "1-1-init")"
assert_eq "story/1-1-init" "$result"

# ═══════════════════════════════════════════════════
# Profile loading and resolution
# ═══════════════════════════════════════════════════

test_begin "profiles: loads @-prefixed definitions"
_reset_config_state
_CONFIG_SH_LOADED=""
_PIPELINE_CONF_LOADED=false

prof_install="$(make_test_tmpdir)"
prof_project="$(make_test_tmpdir)"
mkdir -p "${prof_install}/conf" "${prof_project}/conf"

cat > "${prof_install}/conf/profiles.conf" <<'EOF'
@test-profile  claude  opus  high  -
1.1  @test-profile
EOF

INSTALL_DIR="$prof_install"
PROJECT_ROOT="$prof_project"
_USER_CONF_DIR="$(make_test_tmpdir)"
source "${REPO_ROOT}/lib/config.sh"

result="$(_resolve_profile "@test-profile")"
assert_eq "claude|opus|high|-" "$result"

test_begin "profiles: step_config resolves via profile"
result="$(step_config "1.1")"
assert_eq "claude|opus|high|-" "$result"

test_begin "profiles: project conf overrides install profile"
_reset_config_state
_CONFIG_SH_LOADED=""
_PROFILES_LOADED=false
_STEP_CONFIG_CACHE_LOADED=false

cat > "${prof_install}/conf/profiles.conf" <<'EOF'
@myprof  claude  opus  high  -
1.1  @myprof
EOF
cat > "${prof_project}/conf/profiles.conf" <<'EOF'
@myprof  codex  gpt-5.4  xhigh  -
EOF

INSTALL_DIR="$prof_install"
PROJECT_ROOT="$prof_project"
source "${REPO_ROOT}/lib/config.sh"

result="$(_resolve_profile "@myprof")"
assert_eq "codex|gpt-5.4|xhigh|-" "$result"

test_begin "profiles: fallback chain resolves"
_reset_config_state
_CONFIG_SH_LOADED=""
_PROFILES_LOADED=false

cat > "${prof_install}/conf/profiles.conf" <<'EOF'
@primary    claude  opus  max  @backup
@backup     copilot claude-opus-4.6  high  -
1.1  @primary
EOF
rm -f "${prof_project}/conf/profiles.conf"

INSTALL_DIR="$prof_install"
PROJECT_ROOT="$prof_project"
source "${REPO_ROOT}/lib/config.sh"

result="$(_resolve_profile "@primary")"
assert_eq "claude|opus|max|@backup" "$result"

test_begin "profiles: parse_step_config sets globals"
_reset_config_state
_CONFIG_SH_LOADED=""
_PROFILES_LOADED=false
_STEP_CONFIG_CACHE_LOADED=false

cat > "${prof_install}/conf/profiles.conf" <<'EOF'
@primary    claude  opus  max  @backup
@backup     copilot claude-opus-4.6  high  -
1.1  @primary
EOF
rm -f "${prof_project}/conf/profiles.conf"

INSTALL_DIR="$prof_install"
PROJECT_ROOT="$prof_project"
source "${REPO_ROOT}/lib/config.sh"

parse_step_config "1.1"
assert_eq "claude" "$cfg_cli"

test_begin "profiles: unknown profile returns |||"
result="$(_resolve_profile "@nonexistent")"
assert_eq "|||" "$result"

# ═══════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════

test_summary
