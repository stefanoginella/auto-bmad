#!/usr/bin/env bash
# lib/tracking.sh — Generic key-value store via dynamic variables (bash 3.2 compat)
# Sourced by auto-bmad-story and auto-bmad-epic
#
# Exports:
#   kv_set <namespace> <key> <field> <value>
#   kv_get <namespace> <key> <field> [default] → stdout
#
# Usage:
#   kv_set step "1.3" status "ok"
#   kv_get step "1.3" status "skipped"     → "ok"
#   kv_set story "1-2-auth" duration "342"
#   kv_get story "1-2-auth" duration "0"   → "342"

[[ -n "${_TRACKING_SH_LOADED:-}" ]] && return 0
_TRACKING_SH_LOADED=1

# Sanitize arbitrary key for use as bash variable name.
# Replaces . and - with _ (covers both step IDs like "1.3" and story IDs like "1-2-auth-flow").
_kv_sanitize() { local s="${1//./_}"; echo "${s//-/_}"; }

kv_set() {
    local ns="$1" key="$2" field="$3" value="$4"
    local safe; safe="$(_kv_sanitize "$key")"
    printf -v "_kv_${ns}_${safe}_${field}" '%s' "$value"
}

kv_get() {
    local ns="$1" key="$2" field="$3" default="${4:-}"
    local safe; safe="$(_kv_sanitize "$key")"
    local varname="_kv_${ns}_${safe}_${field}"
    echo "${!varname:-$default}"
}
