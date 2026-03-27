#!/usr/bin/env bash
# lib/core.sh — Shared terminal primitives, logging, and utilities
# Sourced by auto-bmad-story and auto-bmad-epic
#
# Exports:
#   INTERACTIVE           — true when stdin is a terminal
#   Colors: RED GREEN YELLOW BLUE MAGENTA CYAN BOLD DIM NC
#   _confirm <prompt>     — y/N prompt; returns 1 in non-interactive mode
#   _hide_cursor          — suppress cursor during pipeline output
#   _restore_cursor       — re-enable cursor visibility
#   log_phase <title>     — decorated section header (+ PIPELINE_LOG if set)
#   log_ok <msg>          — green checkmark
#   log_warn <msg>        — yellow warning
#   log_error <msg>       — red error
#   log_skip <msg>        — dim skip notice (+ PIPELINE_LOG if set)
#   format_duration <sec> — human-readable "Xh Xm Xs" / "Xm Xs" / "Xs"

[[ -n "${_CORE_SH_LOADED:-}" ]] && return 0
_CORE_SH_LOADED=1

# --- Interactive Detection ---
INTERACTIVE=false
[[ -t 0 ]] && INTERACTIVE=true

# Prompt the user with a y/N question. Returns 0 if "yes", 1 if "no".
# In non-interactive mode, always returns 1 (safe default: abort).
_confirm() {
    local prompt="$1"
    if [[ "$INTERACTIVE" == "true" ]]; then
        _restore_cursor
        echo -en "$prompt"
        read -r answer
        _hide_cursor
        [[ "$answer" =~ ^[Yy]$ ]]
    else
        echo -e "${prompt}N (non-interactive)"
        return 1
    fi
}

_hide_cursor()    { printf '\033[?25l'; }
_restore_cursor() { printf '\033[?25h'; }

# Three-option prompt: [c]ontinue / [f]ix / [a]bort
# Usage: _confirm_cfa "message" "fix command to display" "fix command to run"
#   - If only display command is given, fix_cmd defaults to it
#   - Returns 0 on continue or successful fix, exits on abort
#   - In non-interactive mode: always aborts (safe default)
_confirm_cfa() {
    local msg="$1" fix_display="${2:-}" fix_cmd="${3:-$2}"
    echo ""
    if [[ -n "$fix_display" ]]; then
        echo -e "    ${DIM}→ ${fix_display}${NC}"
        echo -e "    ${BOLD}[c]${NC}ontinue  ${BOLD}[f]${NC}ix  ${BOLD}[a]${NC}bort"
    else
        echo -e "    ${BOLD}[c]${NC}ontinue  ${BOLD}[a]${NC}bort"
    fi
    echo ""
    if [[ "$INTERACTIVE" != "true" ]]; then
        echo -e "    ${DIM}(non-interactive — aborting)${NC}"
        exit 1
    fi
    local choice
    _restore_cursor
    echo -en "    > "
    read -r choice
    _hide_cursor
    case "$choice" in
        [cC]) return 0 ;;
        [fF])
            if [[ -z "$fix_cmd" ]]; then
                log_warn "No auto-fix available"
                return 0
            fi
            echo ""
            echo -e "    ${DIM}Running: ${fix_display}${NC}"
            if bash -c "$fix_cmd"; then
                log_ok "Fixed"
                return 0
            else
                log_error "Fix failed"
                exit 1
            fi
            ;;
        *) exit 1 ;;
    esac
}

# Hard gate prompt: [f]ix / [a]bort (no continue option)
# Usage: _confirm_fa "fix command to display" "fix command to run"
_confirm_fa() {
    local fix_display="${1:-}" fix_cmd="${2:-$1}"
    echo ""
    if [[ -n "$fix_display" ]]; then
        echo -e "    ${DIM}→ ${fix_display}${NC}"
        echo -e "    ${BOLD}[f]${NC}ix  ${BOLD}[a]${NC}bort"
    else
        echo -e "    ${BOLD}[a]${NC}bort"
    fi
    echo ""
    if [[ "$INTERACTIVE" != "true" ]]; then
        echo -e "    ${DIM}(non-interactive — aborting)${NC}"
        exit 1
    fi
    local choice
    _restore_cursor
    echo -en "    > "
    read -r choice
    _hide_cursor
    case "$choice" in
        [fF])
            if [[ -z "$fix_cmd" ]]; then
                log_warn "No auto-fix available"
                exit 1
            fi
            echo ""
            echo -e "    ${DIM}Running: ${fix_display}${NC}"
            if bash -c "$fix_cmd"; then
                log_ok "Fixed"
                return 0
            else
                log_error "Fix failed"
                exit 1
            fi
            ;;
        *) exit 1 ;;
    esac
}

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# --- Logging ---

# Decorated section header. Optionally writes to PIPELINE_LOG if set.
# Shows total elapsed time when PIPELINE_START_TIME is available.
log_phase() {
    local _elapsed=""
    if [[ -n "${PIPELINE_START_TIME:-}" ]]; then
        _elapsed="  ${DIM}[elapsed $(format_duration $(( $(date +%s) - PIPELINE_START_TIME )))]${NC}"
    fi
    echo ""
    echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${CYAN}  $1${NC}${_elapsed}"
    echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════════════════${NC}"
    [[ -n "${PIPELINE_LOG:-}" ]] && printf "# ═══ %s ═══\n" "$1" >> "$PIPELINE_LOG" || true
}

log_ok()    { echo -e "${GREEN}  ✓ $1${NC}"; }
log_warn()  { echo -e "${YELLOW}  ! $1${NC}"; }
log_error() { echo -e "${RED}  ✗ $1${NC}"; }

log_skip() {
    echo -e "${DIM}  — Skipped: $1${NC}"
    [[ -n "${PIPELINE_LOG:-}" ]] && echo "# Skipped: $1" >> "$PIPELINE_LOG" || true
}

# --- Utilities ---

format_duration() {
    local s="$1"
    if (( s >= 3600 )); then
        printf '%dh%dm%ds' $((s/3600)) $((s%3600/60)) $((s%60))
    elif (( s >= 60 )); then
        printf '%dm%ds' $((s/60)) $((s%60))
    else
        printf '%ds' "$s"
    fi
}
