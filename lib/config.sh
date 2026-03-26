#!/usr/bin/env bash
# lib/config.sh — Path detection, version checks, and AI profile lookup
# Sourced by auto-bmad-story and auto-bmad-epic
#
# Requires: lib/core.sh sourced, PROJECT_ROOT set
#
# Exports:
#   _detect_impl_artifacts   — resolve IMPL_ARTIFACTS path from BMAD config
#   check_bmad_version       — validate installed BMad/TEA versions
#   BMAD_BUILD_VERSION       — expected BMad core version
#   BMAD_BUILD_TEA_VERSION   — expected TEA module version
#   TOOL_NAMES               — array of AI CLI tool names
#   step_config <step_id>    — echo "cli|model|effort" for a step
#   parse_step_config <id>   — set cfg_cli, cfg_model, cfg_effort globals

[[ -n "${_CONFIG_SH_LOADED:-}" ]] && return 0
_CONFIG_SH_LOADED=1

# --- BMad Version Constants ---
BMAD_BUILD_VERSION="6.2.1"
BMAD_BUILD_TEA_VERSION="1.7.2"

# --- CLI Tools ---
TOOL_NAMES=(claude codex copilot opencode)

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
    if _confirm "    Continue anyway? [y/N] "; then
        log_warn "Proceeding with mismatched versions"
    else
        log_error "Aborted. Update BMad/modules or rebuild this script for the installed versions."
        exit 1
    fi
}

# --- AI Profile Lookup ---

# Profile config file path
_PROFILES_CONF="${PROJECT_ROOT}/conf/profiles.conf"

# Profile storage — parallel arrays keyed by @name (bash 3.2 compatible)
# Populated by _load_profiles, read by _resolve_profile.
_PROFILE_NAMES=()
_PROFILE_CLIS=()
_PROFILE_MODELS=()
_PROFILE_EFFORTS=()
_PROFILE_FALLBACKS=()
_PROFILES_LOADED=false

# Load @-prefixed profile definitions from conf/profiles.conf.
# Call once after sourcing; idempotent.
_load_profiles() {
    [[ "$_PROFILES_LOADED" == true ]] && return 0
    [[ ! -f "$_PROFILES_CONF" ]] && return 1

    while IFS= read -r line; do
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "${line// /}" ]] && continue
        [[ "$line" != @* ]] && continue
        local name cli model effort fallback
        read -r name cli model effort fallback <<< "$line"
        _PROFILE_NAMES+=("$name")
        _PROFILE_CLIS+=("$cli")
        _PROFILE_MODELS+=("$model")
        _PROFILE_EFFORTS+=("$effort")
        _PROFILE_FALLBACKS+=("${fallback:--}")
    done < "$_PROFILES_CONF"

    _PROFILES_LOADED=true
}

# Resolve a @profile_name to "cli|model|effort|fallback".
# Returns "|||" if not found.
_resolve_profile() {
    local name="$1"
    local i
    for ((i=0; i<${#_PROFILE_NAMES[@]}; i++)); do
        if [[ "${_PROFILE_NAMES[$i]}" == "$name" ]]; then
            echo "${_PROFILE_CLIS[$i]}|${_PROFILE_MODELS[$i]}|${_PROFILE_EFFORTS[$i]}|${_PROFILE_FALLBACKS[$i]}"
            return
        fi
    done
    echo "|||"
}

# Look up the AI profile for a step from conf/profiles.conf.
# Returns "cli|model|effort|fallback". Falls back to "|||" if step not found.
step_config() {
    local step="$1"
    _load_profiles
    if [[ -f "$_PROFILES_CONF" ]]; then
        local line
        while IFS= read -r line; do
            [[ "$line" =~ ^[[:space:]]*# ]] && continue
            [[ -z "${line// /}" ]] && continue
            [[ "$line" == @* ]] && continue   # skip profile definitions
            local sid profile_or_cli field3 field4
            read -r sid profile_or_cli field3 field4 <<< "$line"
            if [[ "$sid" == "$step" ]]; then
                if [[ "$profile_or_cli" == @* ]]; then
                    # Resolve @profile reference
                    _resolve_profile "$profile_or_cli"
                else
                    # Legacy format: step_id cli model effort (no fallback)
                    echo "${profile_or_cli}|${field3}|${field4}|-"
                fi
                return
            fi
        done < "$_PROFILES_CONF"
    fi
    echo "|||"
}

# Parse step config once into cfg_cli, cfg_model, cfg_effort, cfg_fallback globals.
parse_step_config() {
    IFS='|' read -r cfg_cli cfg_model cfg_effort cfg_fallback <<< "$(step_config "$1")"
}

# Apply a specific @profile, overriding cfg_* globals.
# Used by retry wrapper to switch to fallback profile.
apply_profile() {
    local profile="$1"
    IFS='|' read -r cfg_cli cfg_model cfg_effort cfg_fallback <<< "$(_resolve_profile "$profile")"
}
