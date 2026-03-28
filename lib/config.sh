#!/usr/bin/env bash
# lib/config.sh — Path detection, version checks, and AI profile lookup
# Sourced by auto-bmad-story and auto-bmad-epic
#
# Requires: lib/core.sh sourced, INSTALL_DIR and PROJECT_ROOT set
#
# Exports:
#   _detect_impl_artifacts   — resolve IMPL_ARTIFACTS path from BMAD config
#   check_bmad_version       — validate installed BMad/TEA versions
#   BMAD_BUILD_VERSION       — expected BMad core version
#   BMAD_BUILD_TEA_VERSION   — expected TEA module version
#   TOOL_NAMES               — array of AI CLI tool names
#   step_config <step_id>    — echo "cli|model|effort" for a step
#   parse_step_config <id>   — set cfg_cli, cfg_model, cfg_effort globals
#   load_pipeline_conf       — populate cfg_pip_* from conf/pipeline.conf
#   _resolve_branch_name     — expand cfg_pip_branch_pattern for a story ID

[[ -n "${_CONFIG_SH_LOADED:-}" ]] && return 0
_CONFIG_SH_LOADED=1

# --- BMad Version Constants ---
BMAD_BUILD_VERSION="6.2.2"
BMAD_BUILD_TEA_VERSION="1.7.2"

# --- CLI Tools ---
TOOL_NAMES=(claude codex copilot opencode)

# --- jq availability (enables JSON usage tracking) ---
HAS_JQ=false
if command -v jq &>/dev/null; then
    HAS_JQ=true
fi

# --- Configuration Cascade ---
# Order: INSTALL_DIR/conf/ → ~/.config/auto-bmad/ → PROJECT_ROOT/conf/
# Later files override earlier ones. Env vars override all.
_USER_CONF_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/auto-bmad"

# Echo cascade of existing conf file paths for a given filename.
_conf_files() {
    local name="$1" f
    f="${INSTALL_DIR}/conf/${name}";    [[ -f "$f" ]] && echo "$f"
    f="${_USER_CONF_DIR}/${name}";      [[ -f "$f" ]] && echo "$f"
    if [[ "$PROJECT_ROOT" != "$INSTALL_DIR" ]]; then
        f="${PROJECT_ROOT}/conf/${name}"; [[ -f "$f" ]] && echo "$f"
    fi
}

# --- Pipeline Configuration (conf/pipeline.conf) ---
# Defaults — overridden by cascade + env vars
cfg_pip_pr_safety=7200
cfg_pip_pr_poll_interval=30
cfg_pip_pr_grace_polls=10
cfg_pip_min_step_duration=5
cfg_pip_min_log_bytes=200
cfg_pip_preflight_max_age=86400
cfg_pip_model_check_max_age=86400
cfg_pip_spinner_quiet=2
cfg_pip_branch_pattern='story/${STORY_ID}'
cfg_pip_min_git_version="2.25"
cfg_pip_default_review_mode=full
cfg_pip_parallel_stagger=2
cfg_pip_min_reviewers=2
cfg_pip_max_step_duration=2400
cfg_pip_max_output_rate=300000
cfg_pip_file_churn_threshold=20

_PIPELINE_CONF_LOADED=false

# Load pipeline.conf from cascade into cfg_pip_* globals.
# Idempotent — safe to call multiple times.
load_pipeline_conf() {
    [[ "$_PIPELINE_CONF_LOADED" == true ]] && return 0

    local f
    while IFS= read -r f; do
        _parse_pipeline_file "$f"
    done < <(_conf_files "pipeline.conf")

    # Environment variable overrides: AUTO_BMAD_<SECTION>_<KEY>
    # e.g. AUTO_BMAD_TIMEOUTS_PR_SAFETY overrides [timeouts] pr_safety
    cfg_pip_pr_safety="${AUTO_BMAD_TIMEOUTS_PR_SAFETY:-$cfg_pip_pr_safety}"
    cfg_pip_pr_poll_interval="${AUTO_BMAD_TIMEOUTS_PR_POLL_INTERVAL:-$cfg_pip_pr_poll_interval}"
    cfg_pip_pr_grace_polls="${AUTO_BMAD_TIMEOUTS_PR_GRACE_POLLS:-$cfg_pip_pr_grace_polls}"
    cfg_pip_min_step_duration="${AUTO_BMAD_THRESHOLDS_MIN_STEP_DURATION:-$cfg_pip_min_step_duration}"
    cfg_pip_min_log_bytes="${AUTO_BMAD_THRESHOLDS_MIN_LOG_BYTES:-$cfg_pip_min_log_bytes}"
    cfg_pip_preflight_max_age="${AUTO_BMAD_CACHE_PREFLIGHT_MAX_AGE:-$cfg_pip_preflight_max_age}"
    cfg_pip_model_check_max_age="${AUTO_BMAD_CACHE_MODEL_CHECK_MAX_AGE:-$cfg_pip_model_check_max_age}"
    cfg_pip_spinner_quiet="${AUTO_BMAD_MONITOR_SPINNER_QUIET:-$cfg_pip_spinner_quiet}"
    cfg_pip_branch_pattern="${AUTO_BMAD_GIT_BRANCH_PATTERN:-$cfg_pip_branch_pattern}"
    cfg_pip_min_git_version="${AUTO_BMAD_GIT_MIN_GIT_VERSION:-$cfg_pip_min_git_version}"
    cfg_pip_default_review_mode="${AUTO_BMAD_GIT_DEFAULT_REVIEW_MODE:-$cfg_pip_default_review_mode}"
    cfg_pip_parallel_stagger="${AUTO_BMAD_MONITOR_PARALLEL_STAGGER:-$cfg_pip_parallel_stagger}"
    cfg_pip_min_reviewers="${AUTO_BMAD_THRESHOLDS_MIN_REVIEWERS:-$cfg_pip_min_reviewers}"
    cfg_pip_max_step_duration="${AUTO_BMAD_GUARD_MAX_STEP_DURATION:-$cfg_pip_max_step_duration}"
    cfg_pip_max_output_rate="${AUTO_BMAD_GUARD_MAX_OUTPUT_RATE:-$cfg_pip_max_output_rate}"
    cfg_pip_file_churn_threshold="${AUTO_BMAD_GUARD_FILE_CHURN_THRESHOLD:-$cfg_pip_file_churn_threshold}"

    _PIPELINE_CONF_LOADED=true
}

# Parse a single pipeline.conf file into cfg_pip_* globals.
_parse_pipeline_file() {
    local file="$1"
    [[ -f "$file" ]] || return 0

    local section=""
    while IFS= read -r line; do
        # Strip comments and leading/trailing whitespace
        line="${line%%#*}"
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        [[ -z "$line" ]] && continue

        # Section header
        if [[ "$line" == "["*"]" ]]; then
            section="${line#[}"
            section="${section%]}"
            continue
        fi

        # key = value
        local key="${line%%=*}"
        local val="${line#*=}"
        key="${key%"${key##*[![:space:]]}"}"   # trim trailing space
        val="${val#"${val%%[![:space:]]*}"}"    # trim leading space

        case "${section}_${key}" in
            timeouts_pr_safety)          cfg_pip_pr_safety="$val" ;;
            timeouts_pr_poll_interval)   cfg_pip_pr_poll_interval="$val" ;;
            timeouts_pr_grace_polls)     cfg_pip_pr_grace_polls="$val" ;;
            thresholds_min_step_duration) cfg_pip_min_step_duration="$val" ;;
            thresholds_min_log_bytes)    cfg_pip_min_log_bytes="$val" ;;
            cache_preflight_max_age)     cfg_pip_preflight_max_age="$val" ;;
            cache_model_check_max_age)   cfg_pip_model_check_max_age="$val" ;;
            monitor_spinner_quiet)       cfg_pip_spinner_quiet="$val" ;;
            monitor_parallel_stagger)    cfg_pip_parallel_stagger="$val" ;;
            thresholds_min_reviewers)    cfg_pip_min_reviewers="$val" ;;
            guard_max_step_duration)     cfg_pip_max_step_duration="$val" ;;
            guard_max_output_rate)       cfg_pip_max_output_rate="$val" ;;
            guard_file_churn_threshold)  cfg_pip_file_churn_threshold="$val" ;;
            git_branch_pattern)          cfg_pip_branch_pattern="$val" ;;
            git_min_git_version)         cfg_pip_min_git_version="$val" ;;
            git_default_review_mode)     cfg_pip_default_review_mode="$val" ;;
        esac
    done < "$file"
}

# --- Path Detection ---

# Detect implementation_artifacts from BMAD config, with hardcoded fallback.
# Expects PROJECT_ROOT to be set.
_detect_impl_artifacts() {
    local val=""
    local cfg
    for cfg in "${PROJECT_ROOT}/_bmad/bmm/config.yaml" "${PROJECT_ROOT}/_bmad/core/config.yaml"; do
        [[ -f "$cfg" ]] || continue
        val=$(grep -m1 '^implementation_artifacts:' "$cfg" 2>/dev/null | sed 's/^implementation_artifacts:[[:space:]]*//' | sed 's/^["'\''"]//;s/["'\''"]$//') || true
        [[ -n "$val" ]] && break
    done
    if [[ -n "$val" ]]; then
        echo "${val//\{project-root\}/$PROJECT_ROOT}"
    else
        echo "${PROJECT_ROOT}/_bmad-output/implementation-artifacts"
    fi
}

# --- Version Checks ---

check_bmad_version() {
    local manifest="${BMAD_MANIFEST:-${PROJECT_ROOT}/_bmad/_config/manifest.yaml}"
    if [[ ! -f "$manifest" ]]; then
        log_warn "BMad manifest not found — cannot verify versions"
        return 0
    fi

    local installed_version="" tea_version="" in_tea=false
    while IFS= read -r line; do
        line="${line%$'\r'}"
        local stripped="${line#"${line%%[![:space:]]*}"}"
        if [[ "$stripped" == "- name:"* ]]; then
            local mod_name="${stripped#*- name:}"
            mod_name="${mod_name#"${mod_name%%[![:space:]]*}"}"
            if [[ "$mod_name" == "tea" ]]; then
                in_tea=true
            else
                in_tea=false
            fi
            continue
        fi
        local key="${stripped%%:*}"
        local value="${stripped#*:}"
        value="${value#"${value%%[![:space:]]*}"}"
        if [[ "$key" == "version" && -z "$installed_version" ]]; then
            installed_version="$value"
        fi
        if [[ "$in_tea" == true && "$key" == "version" ]]; then
            tea_version="$value"
            in_tea=false
        fi
    done < "$manifest"

    local mismatches=()
    if [[ -z "$installed_version" ]]; then
        log_warn "Could not detect installed BMad version from manifest"
    elif [[ "$installed_version" == "$BMAD_BUILD_VERSION" ]]; then
        log_ok "BMad version ${installed_version}"
    else
        mismatches+=("BMad core: installed ${installed_version}, expected ${BMAD_BUILD_VERSION}")
    fi

    if [[ -z "$tea_version" ]]; then
        log_warn "TEA module not installed"
        if _confirm "    Continue without TEA steps (0, 2.1, 4.x, 5.1-5.3)? [y/N] "; then
            SKIP_TEA=true
            log_warn "TEA steps will be skipped"
        else
            log_error "Aborted. Install TEA module: npx bmad-method install bmad-method-test-architecture-enterprise"
            exit 1
        fi
    elif [[ "$tea_version" == "$BMAD_BUILD_TEA_VERSION" ]]; then
        log_ok "TEA module version ${tea_version}"
    else
        mismatches+=("TEA module: installed ${tea_version}, expected ${BMAD_BUILD_TEA_VERSION}")
    fi

    if [[ ${#mismatches[@]} -eq 0 ]]; then
        return 0
    fi

    echo ""
    log_warn "Version mismatch detected!"
    for m in "${mismatches[@]}"; do
        echo -e "    ${YELLOW}→${NC} ${m}"
    done
    echo ""
    if [[ "$INTERACTIVE" != "true" ]]; then
        log_warn "Non-interactive — proceeding with mismatched versions"
        return 0
    fi
    if _confirm "    Continue anyway? [y/N] "; then
        log_warn "Proceeding with mismatched versions"
    else
        log_error "Aborted. Update BMad/modules or rebuild this script for the installed versions."
        exit 1
    fi
}

# --- Branch Name Resolution ---

# Resolve branch name for a given story ID using cfg_pip_branch_pattern.
# Usage: _resolve_branch_name <story_id>
_resolve_branch_name() {
    local _sid="$1"
    # Avoid ${var:-fallback} — bash 3.2 misparses when value contains '}'
    local _tmpl="${cfg_pip_branch_pattern}"
    [[ -z "$_tmpl" ]] && _tmpl='story/${STORY_ID}'
    # Safe substitution — no eval, no arbitrary code execution
    # Handle both ${STORY_ID} and $STORY_ID template forms
    local _result="${_tmpl//\$\{STORY_ID\}/$_sid}"
    echo "${_result//\$STORY_ID/$_sid}"
}

# --- AI Profile Lookup ---

# Profile storage — parallel arrays keyed by @name (bash 3.2 compatible)
# Populated by _load_profiles, read by _resolve_profile.
_PROFILE_NAMES=()
_PROFILE_CLIS=()
_PROFILE_MODELS=()
_PROFILE_EFFORTS=()
_PROFILE_FALLBACKS=()
_PROFILES_LOADED=false

# Load @-prefixed profile definitions from profiles.conf cascade.
# Later files override earlier ones by @name. Idempotent.
_load_profiles() {
    [[ "$_PROFILES_LOADED" == true ]] && return 0

    local f
    while IFS= read -r f; do
        while IFS= read -r line; do
            [[ "$line" =~ ^[[:space:]]*# ]] && continue
            [[ -z "${line// /}" ]] && continue
            [[ "$line" != @* ]] && continue
            local name cli model effort fallback
            read -r name cli model effort fallback <<< "$line"
            # Override existing profile if already loaded
            local i found=false
            for ((i=0; i<${#_PROFILE_NAMES[@]}; i++)); do
                if [[ "${_PROFILE_NAMES[$i]}" == "$name" ]]; then
                    _PROFILE_CLIS[$i]="$cli"
                    _PROFILE_MODELS[$i]="$model"
                    _PROFILE_EFFORTS[$i]="$effort"
                    _PROFILE_FALLBACKS[$i]="${fallback:--}"
                    found=true
                    break
                fi
            done
            if [[ "$found" == false ]]; then
                _PROFILE_NAMES+=("$name")
                _PROFILE_CLIS+=("$cli")
                _PROFILE_MODELS+=("$model")
                _PROFILE_EFFORTS+=("$effort")
                _PROFILE_FALLBACKS+=("${fallback:--}")
            fi
        done < "$f"
    done < <(_conf_files "profiles.conf")

    _PROFILES_LOADED=true
}

# Resolve a @profile_name to "cli|model|effort|fallback".
# Returns "|||" if not found.
_resolve_profile() {
    local name="$1"
    _load_profiles
    local i
    for ((i=0; i<${#_PROFILE_NAMES[@]}; i++)); do
        if [[ "${_PROFILE_NAMES[$i]}" == "$name" ]]; then
            echo "${_PROFILE_CLIS[$i]}|${_PROFILE_MODELS[$i]}|${_PROFILE_EFFORTS[$i]}|${_PROFILE_FALLBACKS[$i]}"
            return
        fi
    done
    echo "|||"
}

# Look up the AI profile for a step from profiles.conf cascade.
# Returns "cli|model|effort|fallback". Falls back to "|||" if step not found.
# Last match wins across cascade files. Results are cached per step ID.
_STEP_CONFIG_CACHE_LOADED=false
step_config() {
    local step="$1"
    _load_profiles

    # Build cache on first call — parse all step mappings once
    if [[ "$_STEP_CONFIG_CACHE_LOADED" != true ]]; then
        local f line sid profile_or_cli field3 field4
        while IFS= read -r f; do
            while IFS= read -r line; do
                [[ "$line" =~ ^[[:space:]]*# ]] && continue
                [[ -z "${line// /}" ]] && continue
                [[ "$line" == @* ]] && continue   # skip profile definitions
                read -r sid profile_or_cli field3 field4 <<< "$line"
                local resolved
                if [[ "$profile_or_cli" == @* ]]; then
                    resolved="$(_resolve_profile "$profile_or_cli")"
                else
                    resolved="${profile_or_cli}|${field3}|${field4}|-"
                fi
                # Last match wins — kv_set overwrites
                kv_set _stepcfg "$sid" val "$resolved"
            done < "$f"
        done < <(_conf_files "profiles.conf")
        _STEP_CONFIG_CACHE_LOADED=true
    fi

    echo "$(kv_get _stepcfg "$step" val "|||")"
}

# Parse step config once into cfg_cli, cfg_model, cfg_effort, cfg_fallback globals.
# Note: the subshell is separated from the IFS='|' read to avoid a bash 3.2 bug
# where IFS leaks into command substitutions on the same line.
parse_step_config() {
    local _sc; _sc="$(step_config "$1")"
    IFS='|' read -r cfg_cli cfg_model cfg_effort cfg_fallback <<< "$_sc"
}

# Apply a specific @profile, overriding cfg_* globals.
# Used by retry wrapper to switch to fallback profile.
apply_profile() {
    local _ap; _ap="$(_resolve_profile "$1")"
    IFS='|' read -r cfg_cli cfg_model cfg_effort cfg_fallback <<< "$_ap"
}
