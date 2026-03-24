#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# auto-bmad.sh — Shell-Based BMAD Story Pipeline
#
# Automates one story at a time through the full BMAD
# implementation workflow, using multiple AI CLIs for diversity.
# CLIs: claude, codex, copilot (GitHub Copilot CLI), opencode
#
# Usage: ./auto-bmad-story.sh [options]
#   --story STORY_ID     Override auto-detection
#   --from-step ID       Resume pipeline from step ID (e.g., 2a1, 7c)
#   --dry-run            Preview all steps without executing
#   --skip-cache         Bypass pre-flight cache and force full checks
#   --skip-epic-phases   Skip phases 0 and 5 even at epic boundaries
#   --skip-tea           Skip TEA phases even if TEA is installed
#   --skip-reviews       Skip all review phases (1.2-1.4, 3.x)
#   --fast-reviews       Run only 1 GPT reviewer per phase, skip triage+fix
#   --skip-git           Skip git write operations (branch, checkpoint, squash)
#   --no-traces          Remove pipeline artifacts after finalization
#   --safe-mode          Disable permission-bypass flags (AI tools prompt for approval)
#   --help               Show usage
# ============================================================

# --- Interactive Detection ---
# When stdin is not a terminal (piped, CI, etc.), interactive prompts
# default to "no" and abort rather than silently continuing.
INTERACTIVE=false
[[ -t 0 ]] && INTERACTIVE=true

# Prompt the user with a y/N question. Returns 0 if "yes", 1 if "no".
# In non-interactive mode, always returns 1 (safe default: abort).
_confirm() {
    local prompt="$1"
    if [[ "$INTERACTIVE" == "true" ]]; then
        echo -en "$prompt"
        read -r answer
        [[ "$answer" =~ ^[Yy]$ ]]
    else
        echo -e "${prompt}N (non-interactive)"
        return 1
    fi
}

# --- Abort Handling (CTRL+C kills the entire pipeline) ---
_ABORT=false

_restore_cursor() { tput cnorm 2>/dev/null || true; }

_handle_abort() {
    _ABORT=true
    stop_activity_monitor 2>/dev/null || true
    _restore_cursor
    echo ""
    echo -e "\033[1;31m ✘ Pipeline aborted by user (CTRL+C)\033[0m" >&2
    exit 130
}

trap '_handle_abort' INT

# --- Project Paths ---
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

# Detect implementation_artifacts from BMAD config, with hardcoded fallback
_detect_impl_artifacts() {
    local val=""
    local cfg
    for cfg in "${PROJECT_ROOT}/_bmad/bmm/config.yaml" "${PROJECT_ROOT}/_bmad/core/config.yaml"; do
        [[ -f "$cfg" ]] || continue
        val=$(grep -m1 '^implementation_artifacts:' "$cfg" 2>/dev/null | sed 's/^implementation_artifacts:[[:space:]]*//' | sed 's/^["'\''"]//;s/["'\''"]$//') || true
        [[ -n "$val" ]] && break
    done
    if [[ -n "$val" ]]; then
        # Replace {project-root} placeholder with actual PROJECT_ROOT
        echo "${val//\{project-root\}/$PROJECT_ROOT}"
    else
        echo "${PROJECT_ROOT}/_bmad-output/implementation-artifacts"
    fi
}

IMPL_ARTIFACTS="$(_detect_impl_artifacts)"
SPRINT_STATUS="${IMPL_ARTIFACTS}/sprint-status.yaml"
BMAD_MANIFEST="${PROJECT_ROOT}/_bmad/_config/manifest.yaml"

# BMad versions this script was built/tested against
BMAD_BUILD_VERSION="6.2.0"
BMAD_BUILD_TEA_VERSION="1.7.2"

# ============================================================
# CLI Tools
# ============================================================

TOOL_NAMES=(claude codex opencode)
# copilot (GitHub Copilot CLI) is supported but not assigned to any step

# ============================================================
# AI Profiles — reusable combinations of cli|model|effort
# ============================================================
# Format: "cli|model|effort"
#
# Effort flags:  claude:   --effort (low|medium|high|max)
#                codex:    -c model_reasoning_effort= (minimal|low|medium|high|xhigh)
#                opencode: --variant (low|medium|high|max)
#                copilot:  no effort flag available

AI_OPUS="claude|opus|max"                           # Claude Opus 4.6 — critical path, triage, acceptance audit
AI_OPUS_HIGH="claude|opus|high"                      # Claude Opus 4.6 / high — structured, non-critical
AI_SONNET="claude|sonnet|high"                       # Claude Sonnet 4.6 — lightweight bookkeeping
AI_GPT="codex|gpt-5.4|xhigh"                       # Codex GPT 5.4 — code reviews, edge cases
AI_GPT_HIGH="codex|gpt-5.4|high"                    # Codex GPT 5.4 / high — spec-level reviews
# AI_COPILOT="copilot|gemini-3-pro-preview|"           # Copilot Gemini 3 Pro — removed: low quality reviews
# AI_MINIMAX="opencode|opencode/minimax-m2.5-free|max" # MiniMax M2.5 via OpenCode — removed: low signal-to-noise ratio (26% accept rate in pipeline runs)
AI_MIMO="opencode|opencode/mimo-v2-pro-free|max"     # MiMo V2 Pro via OpenCode — parallel reviews

# ============================================================
# Step Configuration — assign AI profile per step
# ============================================================

step_config() {
    local step="$1"
    local suffix="${step: -1}"    # last char: a, b, c, d, or digit
    local phase="${step%%.*}"     # phase number

    # Phase 1 override: 3 validation reviews (one per AI)
    # a → GPT (spec-level) | b → MiMo | c → Claude/Opus
    if [[ "$phase" == "1" ]]; then
        case "$suffix" in
            a) echo "$AI_GPT_HIGH"; return ;;
            b) echo "$AI_MIMO"; return ;;
            c) echo "$AI_OPUS_HIGH"; return ;;
        esac
    fi

    # Phase 3 override: 6 review sessions (3 AIs × 2 types), no MiniMax
    # a,b → GPT | c,d → MiMo | e,f → Claude/Opus
    if [[ "$phase" == "3" ]]; then
        case "$suffix" in
            a|b) echo "$AI_GPT"; return ;;
            c|d) echo "$AI_MIMO"; return ;;
            e|f) echo "$AI_OPUS"; return ;;
        esac
    fi

    # Non-parallel steps
    case "$step" in
        # Phase 1: spec triage + fix (critical path)
        1.3|1.4)                     echo "$AI_OPUS" ;;
        # Phase 3: acceptance auditor, triage, dev fix, spec resolve (critical path)
        3.2|3.3|3.4|3.5)            echo "$AI_OPUS" ;;
        # Critical path: epic start, story creation, TDD, implementation
        0.1|1.1|2.1|2.2)            echo "$AI_OPUS" ;;
        # Traceability & automation — structured, mechanical
        4.1|4.2)                     echo "$AI_SONNET" ;;
        # Epic end parallel (individual assignments, not review sub-steps)
        5.1)                         echo "$AI_GPT" ;;
        5.2)                         echo "$AI_OPUS" ;;
        5.3)                         echo "$AI_MIMO" ;;
        # Reflective / documentation — structured, non-critical
        5.4|5.5|6.1)                 echo "$AI_OPUS_HIGH" ;;
        # Finalization — bookkeeping
        6.2)                         echo "$AI_SONNET" ;;
        *)                           echo "||" ;;
    esac
}

# Parse step config once into cfg_cli, cfg_model, cfg_effort
parse_step_config() {
    IFS='|' read -r cfg_cli cfg_model cfg_effort <<< "$(step_config "$1")"
}

# ============================================================
# Pipeline State
# ============================================================

STORY_ID=""
STORY_SHORT_ID=""   # numeric-only prefix (e.g. "1-1") — used for artifacts
EPIC_ID=""
STORY_FILE_PATH=""
STORY_ARTIFACTS=""   # permanent artifacts (triage reports, pipeline report)
TMP_DIR=""           # temp files (individual reviews, step logs) — cleaned on success
PIPELINE_LOG=""      # raw step log in TMP_DIR (temporary)
PIPELINE_REPORT=""   # structured markdown in STORY_ARTIFACTS (permanent)
CURRENT_STEP_LOG=""
COMMIT_BASELINE=""   # SHA before pipeline — used for final squash
DRY_RUN=false
FROM_STEP=""
SKIP_CACHE=false
SKIP_EPIC_PHASES=false
SKIP_TEA=false
SKIP_REVIEWS=false
FAST_REVIEWS=false
SKIP_GIT=false
NO_TRACES=false
SAFE_MODE=false
PIPELINE_START_TIME=""

# Step ordering for --from-step comparison (parallel sub-steps map to parent)
STEP_ORDER="0.1 1.1 1.2 1.3 1.4 2.1 2.2 3.1 3.2 3.3 3.4 3.5 4.1 4.2 5.1 5.2 5.3 5.4 5.5 6.1 6.2"

# Sanitize step IDs for use as bash variable names (replace . and - with _)
_sanitize_step_id() { local s="${1//./_}"; echo "${s//-/_}"; }

# In-memory step tracking via dynamic variables (bash 3.2 compat)
# Generic setter/getter — field is one of: status, duration, name, start
_set_step_field() { local k; k="$(_sanitize_step_id "$1")"; printf -v "track_${k}_$2" '%s' "$3"; }
_get_step_field() { local k; k="$(_sanitize_step_id "$1")"; local v="track_${k}_$2"; echo "${!v:-$3}"; }

set_step_status()   { _set_step_field "$1" status   "$2"; }
get_step_status()   { _get_step_field "$1" status   "skipped"; }
set_step_duration() { _set_step_field "$1" duration "$2"; }
get_step_duration() { _get_step_field "$1" duration "0"; }
set_step_name()     { _set_step_field "$1" name     "$2"; }
get_step_name()     { _get_step_field "$1" name     "$1"; }
set_step_start()    { _set_step_field "$1" start    "$2"; }
get_step_start()    { _get_step_field "$1" start    "$2"; }

# ============================================================
# Color & Logging
# ============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

log_phase() {
    echo ""
    echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${CYAN}  Phase $1 — $2${NC}"
    echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════════════════${NC}"
    [[ -n "$PIPELINE_LOG" ]] && printf "# ═══ Phase %s — %s ═══\n" "$1" "$2" >> "$PIPELINE_LOG" || true
}

# Format "cli/model" from cfg_* globals (call parse_step_config first)
_format_model_info() {
    local info="${cfg_cli}"
    [[ -n "$cfg_model" ]] && info="${info}/${cfg_model}"
    echo "$info"
}

# Append a step entry to PIPELINE_LOG
_log_pipeline_entry() {
    local step_id="$1" model_info="$2" duration="$3" status="$4" step_name="$5"
    printf "  %-6s  %-20s  %-22s  %-10s  %-8s  %s\n" \
        "$step_id" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$model_info" \
        "$(format_duration "$duration")" "$status" "$step_name" >> "$PIPELINE_LOG"
}

log_step() {
    local step_id="$1" step_name="$2"
    parse_step_config "$step_id"
    local detail="$(_format_model_info)"
    [[ -n "$cfg_effort" ]] && detail="${detail}/${cfg_effort}"
    echo ""
    echo -e "${BOLD}${BLUE}>>> Step ${step_id}: ${step_name}${NC}  ${DIM}[${detail}]${NC}"
}

log_ok()   { echo -e "${GREEN}  ✓ $1${NC}"; }
log_warn() { echo -e "${YELLOW}  ! $1${NC}"; }
log_error(){ echo -e "${RED}  ✗ $1${NC}"; }
log_skip() {
    echo -e "${DIM}  — Skipped: $1${NC}"
    [[ -n "$PIPELINE_LOG" ]] && echo "# Skipped: $1" >> "$PIPELINE_LOG" || true
}

log_dry() {
    local step_id="$1" step_name="$2"
    parse_step_config "$step_id"
    echo -e "  ${DIM}[DRY RUN]${NC} Step ${BOLD}${step_id}${NC} — ${step_name}"
    echo -e "    CLI: ${cfg_cli:-shell}  Model: ${cfg_model:-n/a}  Effort: ${cfg_effort:-n/a}"
}

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

# ============================================================
# Activity Monitor (spinner + stall detection)
# ============================================================

SPINNER_FRAMES='⣾⣽⣻⢿⡿⣟⣯⣷'
_monitor_pid=""

_cleanup_monitor() {
    rm -f "/tmp/auto-bmad-monitor-$$"
    if [[ -n "$_monitor_pid" ]]; then
        kill "$_monitor_pid" 2>/dev/null || true
        wait "$_monitor_pid" 2>/dev/null || true
        _monitor_pid=""
    fi
}

start_activity_monitor() {
    local label="$1"
    local start_time
    start_time=$(date +%s)

    # Stop any existing monitor first
    _cleanup_monitor

    touch "/tmp/auto-bmad-monitor-$$"

    (
        set +e  # Don't exit on errors in monitor
        local i=0
        local last_log_size=0
        local last_change_time=$start_time
        local spinner_active=false

        [[ -f "$CURRENT_STEP_LOG" ]] && last_log_size=$(wc -c < "$CURRENT_STEP_LOG" 2>/dev/null | tr -d ' ')

        while [[ -f "/tmp/auto-bmad-monitor-$$" ]]; do
            local now
            now=$(date +%s)
            local elapsed=$((now - start_time))
            local idx=$((i % ${#SPINNER_FRAMES}))
            local frame="${SPINNER_FRAMES:idx:1}"

            # Check log file for new output
            local current_log_size=0
            [[ -f "$CURRENT_STEP_LOG" ]] && current_log_size=$(wc -c < "$CURRENT_STEP_LOG" 2>/dev/null | tr -d ' ')

            if [[ "$current_log_size" != "$last_log_size" ]]; then
                # Output detected — clear spinner if visible
                if [[ "$spinner_active" == true ]]; then
                    printf '\r\033[K' >&2
                    spinner_active=false
                fi
                last_log_size=$current_log_size
                last_change_time=$now
                warned_at=0
            fi

            local quiet_seconds=$((now - last_change_time))

            if (( quiet_seconds >= 2 )); then
                # No output for 2+ seconds — show spinner
                printf '\r  %s %s [%s]' "$frame" "$label" "$(format_duration $elapsed)" >&2
                spinner_active=true
            fi

            sleep 0.1
            i=$((i + 1))
        done

        # Clear spinner on exit
        if [[ "$spinner_active" == true ]]; then
            printf '\r\033[K' >&2
        fi
    ) &
    _monitor_pid=$!
}

stop_activity_monitor() {
    _cleanup_monitor
}

# ============================================================
# Git Checkpoints (per-phase commits + final squash)
# ============================================================

# Save a checkpoint commit after a phase completes.
# Skipped if there are no changes to commit.
# Uses --no-verify because these are temporary WIP commits that get squashed
# into a single final commit by git_squash_pipeline(). Running hooks on
# intermediate checkpoints would waste time and fail on partial work.
git_checkpoint() {
    local phase_label="$1"
    [[ "$DRY_RUN" == "true" || "$SKIP_GIT" == "true" ]] && return 0

    if git -C "$PROJECT_ROOT" diff --quiet && git -C "$PROJECT_ROOT" diff --cached --quiet && \
       [[ -z "$(git -C "$PROJECT_ROOT" ls-files --others --exclude-standard)" ]]; then
        return 0  # nothing to commit
    fi

    git -C "$PROJECT_ROOT" add -A
    git -C "$PROJECT_ROOT" commit -m "wip(${STORY_SHORT_ID}): ${phase_label}" --no-verify --quiet
}

# Squash all checkpoint commits made since COMMIT_BASELINE into a single WIP commit.
# The real commit message is left for the epic script or manual finalization.
git_squash_pipeline() {
    [[ "$DRY_RUN" == "true" || "$SKIP_GIT" == "true" ]] && return 0

    local current_head
    current_head="$(git -C "$PROJECT_ROOT" rev-parse HEAD 2>/dev/null)"

    # Nothing to squash if HEAD hasn't moved
    if [[ "$current_head" == "$COMMIT_BASELINE" ]]; then
        return 0
    fi

    # --no-verify: the squashed commit aggregates already-validated checkpoint
    # commits. Pre-commit hooks will run when this branch is PR'd / merged.
    git -C "$PROJECT_ROOT" reset --soft "$COMMIT_BASELINE"
    git -C "$PROJECT_ROOT" commit -m "wip(${STORY_SHORT_ID}): pipeline complete — ready for review" --no-verify --quiet
    log_ok "Squashed pipeline commits into WIP commit (finalize with epic script or manually)"
}

# Extract commit message from story file's Auto-bmad Completion section.
# Used by print_summary for copy-paste commands and by epic script for final commit.
extract_story_commit_msg() {
    local msg=""
    if [[ -n "$STORY_FILE_PATH" && -f "$STORY_FILE_PATH" ]]; then
        msg="$(sed -n '/## Auto-bmad Completion/,/^## /{ /^```/,/^```/{ /^```/d; p; }; }' "$STORY_FILE_PATH" 2>/dev/null)"
    fi
    if [[ -z "$msg" ]]; then
        local slug="${STORY_ID#*-*-}"
        local description="${slug//-/ }"
        msg="feat(${STORY_SHORT_ID}): ${description}"
    fi
    echo "$msg"
}

# ============================================================
# Output Rendering (markdown + rolling display)
# ============================================================

# ============================================================
# CLI Abstraction Layer
# ============================================================

# Codex requires `$` instead of `/` for the leading slash command
codex_prompt() {
    local p="$1"
    [[ "$p" == /* ]] && p="\$${p:1}"
    echo "$p"
}

# run_ai <step_id> <prompt>
run_ai() {
    local step_id="$1"
    local prompt="$2"
    parse_step_config "$step_id"

    # Write step header and raw output to per-step log (not the summary)
    {
        echo ""
        echo "═══ Step ${step_id} ═══════════════════════════════════════════"
        echo "CLI: ${cfg_cli} | Model: ${cfg_model} | Effort: ${cfg_effort:-n/a}"
        echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo "Prompt:"
        echo "$prompt"
        echo "───────────────────────────────────────────────────────────────"
    } >> "$CURRENT_STEP_LOG"

    local exit_code=0
    case "$cfg_cli" in
        claude)
            local cmd=(claude -p "$prompt" --model "$cfg_model")
            [[ "$SAFE_MODE" != true ]] && cmd+=(--dangerously-skip-permissions)
            [[ -n "$cfg_effort" ]] && cmd+=(--effort "$cfg_effort")
            "${cmd[@]}" 2>&1 | tee -a "$CURRENT_STEP_LOG" > /dev/null || true
            exit_code=${PIPESTATUS[0]}
            ;;
        codex)
            local cprompt; cprompt="$(codex_prompt "$prompt")"
            local cmd=(codex exec "$cprompt" -m "$cfg_model")
            [[ "$SAFE_MODE" != true ]] && cmd+=(--full-auto)
            [[ -n "$cfg_effort" ]] && cmd+=(-c "model_reasoning_effort=${cfg_effort}")
            "${cmd[@]}" 2>&1 | tee -a "$CURRENT_STEP_LOG" > /dev/null || true
            exit_code=${PIPESTATUS[0]}
            ;;
        copilot)
            local cmd=(copilot -p "$prompt" --model "$cfg_model")
            [[ "$SAFE_MODE" != true ]] && cmd+=(--yolo)
            "${cmd[@]}" 2>&1 | tee -a "$CURRENT_STEP_LOG" > /dev/null || true
            exit_code=${PIPESTATUS[0]}
            ;;
        opencode)
            local cmd=(opencode run "$prompt" -m "$cfg_model")
            [[ -n "$cfg_effort" ]] && cmd+=(--variant "$cfg_effort")
            "${cmd[@]}" 2>&1 | tee -a "$CURRENT_STEP_LOG" > /dev/null || true
            exit_code=${PIPESTATUS[0]}
            ;;
        *)
            log_error "Unknown CLI: ${cfg_cli}"
            return 1
            ;;
    esac

    return "$exit_code"
}

# ============================================================
# Generic Review Functions
# ============================================================

# run_review_step <step_id> <file_prefix> <ai_suffix>
# Dispatches the appropriate slash command based on file_prefix.
# Individual review files go to TMP_DIR (discarded after triage synthesizes).
run_review_step() {
    local step_id="$1" file_prefix="$2" ai_suffix="$3"
    local f="${TMP_DIR}/${step_id}-${file_prefix}-${ai_suffix}.md"
    local prompt
    case "$file_prefix" in
        validate)
            prompt="/bmad-create-story yolo - validate story ${STORY_ID}. Do not fix anything or edit any source files. Just report all issues, recommendations and optimizations and save them to ${f}" ;;
        edge-cases)
            prompt="/bmad-review-edge-case-hunter yolo - review all code changes for story ${STORY_ID} (commits ${COMMIT_BASELINE}..HEAD). Do not fix anything or edit any source files. Just report all edge case findings and save them to ${f}" ;;
        code-adversarial)
            prompt="/bmad-review-adversarial-general yolo - review all code changes for story ${STORY_ID} (commits ${COMMIT_BASELINE}..HEAD). Focus on the implementation code, not the specification. Do not fix anything or edit any source files. Just report all findings and save them to ${f}" ;;
    esac
    run_ai "$step_id" "$prompt"
}

# ============================================================
# Story & Epic Detection
# ============================================================

detect_next_story() {
    if [[ ! -f "$SPRINT_STATUS" ]]; then
        log_error "Sprint status file not found: ${SPRINT_STATUS}"
        exit 1
    fi

    local found="" in_progress_found=""

    while IFS=: read -r key status; do
        # Inline trim — avoid subshell forks per line
        key="${key#"${key%%[![:space:]]*}"}"; key="${key%"${key##*[![:space:]]}"}"
        status="${status#"${status%%[![:space:]]*}"}"; status="${status%"${status##*[![:space:]]}"}"

        case "$key" in
            \#*|""|epic-*|generated*|last_updated*|project*|tracking_system*|story_location*|development_status*) continue ;;
        esac

        [[ "$key" =~ ^[0-9]+-[0-9]+- ]] || continue

        if [[ "$status" == "in-progress" && -z "$in_progress_found" ]]; then
            in_progress_found="$key"
        fi

        if [[ "$status" == "backlog" && -z "$found" ]]; then
            found="$key"
        fi
    done < "$SPRINT_STATUS"

    if [[ -n "$in_progress_found" ]]; then
        STORY_ID="$in_progress_found"
    elif [[ -n "$found" ]]; then
        STORY_ID="$found"
    else
        echo ""
        log_error "No stories with status 'in-progress' or 'backlog' found in sprint-status.yaml"
        exit 1
    fi
}

extract_epic_id() {
    EPIC_ID="${STORY_ID%%-*}"
}

# Extract numeric prefix "1-2" from "1-2-some-slug"
extract_short_id() {
    local epic="${STORY_ID%%-*}"
    local remainder="${STORY_ID#*-}"
    local story_num="${remainder%%-*}"
    STORY_SHORT_ID="${epic}-${story_num}"
}

extract_story_num() {
    local remainder="${STORY_ID#*-}"
    echo "${remainder%%-*}"
}

is_epic_start() {
    local story_num
    story_num="$(extract_story_num)"
    [[ "$story_num" == "1" ]]
}

is_epic_end() {
    local found_current=false
    while IFS=: read -r key _status; do
        key="${key#"${key%%[![:space:]]*}"}"; key="${key%"${key##*[![:space:]]}"}"
        if [[ "$found_current" == "true" ]]; then
            if [[ "$key" == "epic-${EPIC_ID}-retrospective" ]]; then
                return 0
            else
                return 1
            fi
        fi
        if [[ "$key" == "$STORY_ID" ]]; then
            found_current=true
        fi
    done < "$SPRINT_STATUS"
    return 1
}

detect_story_file_path() {
    local match
    match=$(find "$IMPL_ARTIFACTS" -maxdepth 1 -name "${STORY_ID}*.md" \
        ! -name "*--*" -type f 2>/dev/null | head -1)

    if [[ -n "$match" ]]; then
        STORY_FILE_PATH="$match"
    else
        local prefix
        prefix="$(echo "$STORY_ID" | cut -d'-' -f1-2)"
        match=$(find "$IMPL_ARTIFACTS" -maxdepth 1 -name "${prefix}-*" \
            ! -name "*--*" -type f -name "*.md" 2>/dev/null | head -1)
        STORY_FILE_PATH="${match:-}"
    fi
}

# ============================================================
# Pre-flight Checks (cached for 24h in .tmp/auto-bmad)
# ============================================================

PREFLIGHT_CACHE="${PROJECT_ROOT}/.tmp/auto-bmad/preflight-cache"
PREFLIGHT_CACHE_MAX_AGE=86400   # 24 hours

_preflight_cache_valid() {
    [[ -f "$PREFLIGHT_CACHE" ]] || return 1
    local now mtime age
    now=$(date +%s)
    # macOS stat -f %m, GNU stat -c %Y
    if mtime=$(stat -f %m "$PREFLIGHT_CACHE" 2>/dev/null); then
        :
    else
        mtime=$(stat -c %Y "$PREFLIGHT_CACHE" 2>/dev/null) || return 1
    fi
    age=$(( now - mtime ))
    (( age < PREFLIGHT_CACHE_MAX_AGE ))
}

_preflight_cache_write() {
    mkdir -p "$(dirname "$PREFLIGHT_CACHE")"
    touch "$PREFLIGHT_CACHE"
}

check_bmad_version() {
    if [[ ! -f "$BMAD_MANIFEST" ]]; then
        log_warn "BMad manifest not found — cannot verify versions"
        return 0
    fi

    # Parse installed BMad version (first version: field) and TEA module version
    local installed_version="" tea_version="" in_tea=false
    while IFS= read -r line; do
        line="${line%$'\r'}"
        # Strip leading whitespace for matching
        local stripped="${line#"${line%%[![:space:]]*}"}"
        # Handle YAML list items: "- name: value"
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
        # Extract key: value pairs
        local key="${stripped%%:*}"
        local value="${stripped#*:}"
        value="${value#"${value%%[![:space:]]*}"}"
        # Top-level version (first occurrence, before any module)
        if [[ "$key" == "version" && -z "$installed_version" ]]; then
            installed_version="$value"
        fi
        if [[ "$in_tea" == true && "$key" == "version" ]]; then
            tea_version="$value"
            in_tea=false
        fi
    done < "$BMAD_MANIFEST"

    # Check BMad core version
    local mismatches=()
    if [[ -z "$installed_version" ]]; then
        log_warn "Could not detect installed BMad version from manifest"
    elif [[ "$installed_version" == "$BMAD_BUILD_VERSION" ]]; then
        log_ok "BMad version ${installed_version}"
    else
        mismatches+=("BMad core: installed ${installed_version}, expected ${BMAD_BUILD_VERSION}")
    fi

    # Check TEA module
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

# Ensure we're on the correct story branch, or create one from main.
# Called after STORY_ID is known.
check_git_branch() {
    [[ "$SKIP_GIT" == "true" ]] && { log_skip "Git branch check — --skip-git"; return 0; }
    [[ "$DRY_RUN" == "true" ]] && { log_skip "Git branch check — --dry-run"; return 0; }

    local current_branch expected_branch="story/${STORY_ID}"
    current_branch="$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null)" || {
        log_warn "Not a git repository — skipping branch check"
        return 0
    }

    # Already on the right branch
    if [[ "$current_branch" == "$expected_branch" ]]; then
        log_ok "On branch ${expected_branch}"
        return 0
    fi

    # On main → create and switch
    if [[ "$current_branch" == "main" || "$current_branch" == "master" ]]; then
        # Resuming implies work already exists on a branch
        if [[ -n "$FROM_STEP" ]]; then
            echo ""
            log_warn "Resuming from step ${FROM_STEP} but on ${current_branch} instead of ${expected_branch}"
            echo -e "    Expected branch ${BOLD}${expected_branch}${NC} for an in-progress story."
            echo ""
            if ! _confirm "    Continue on ${current_branch} anyway? [y/N] "; then
                echo -e "    ${DIM}To switch: git checkout ${expected_branch}${NC}"
                exit 1
            fi
            return 0
        fi

        echo ""
        echo -e "  ${BOLD}Creating branch:${NC} ${GREEN}${expected_branch}${NC} (from ${current_branch})"
        if git -C "$PROJECT_ROOT" checkout -b "$expected_branch"; then
            log_ok "Created and switched to new branch ${expected_branch}"
        else
            log_error "Failed to create branch ${expected_branch}"
            exit 1
        fi
        return 0
    fi

    # On a different story branch
    if [[ "$current_branch" == story/* ]]; then
        echo ""
        log_error "Wrong story branch!"
        echo -e "    Current:  ${BOLD}${current_branch}${NC}"
        echo -e "    Expected: ${BOLD}${expected_branch}${NC}"
        echo ""
        echo -e "    Options:"
        echo -e "      ${DIM}git checkout main${NC}                    # go back to main"
        echo -e "      ${DIM}git checkout ${expected_branch}${NC}      # switch to existing branch"
        echo -e "      ${DIM}gh pr create${NC}                         # PR the current branch first"
        exit 1
    fi

    # On some other branch — ambiguous, let the user decide
    echo ""
    log_warn "Unexpected branch: ${current_branch}"
    echo -e "    Expected to be on ${BOLD}main${NC} or ${BOLD}${expected_branch}${NC}"
    echo ""
    if ! _confirm "    Continue on ${current_branch} anyway? [y/N] "; then
        exit 1
    fi
}

# ============================================================
# Model Availability Checks
# ============================================================

# Each _check_*_model function returns:
#   0 = model available
#   1 = model definitely not available
#   2 = cannot determine (listing unavailable)

_check_claude_model() {
    local model="$1"
    # claude validates model before API call; --max-budget-usd 0.001
    # causes fast exit for valid models (budget exceeded) while invalid
    # models fail immediately with a specific error message.
    local output
    output=$(echo "." | claude -p --model "$model" --max-budget-usd 0.001 2>&1)
    if echo "$output" | grep -q "There's an issue with the selected model"; then
        return 1
    fi
    return 0
}

_check_codex_model() {
    local model="$1"
    local cache="$HOME/.codex/models_cache.json"
    if [[ -f "$cache" ]]; then
        if grep -q "\"slug\": \"${model}\"" "$cache" 2>/dev/null; then
            return 0
        fi
        return 1
    fi
    return 2
}

_check_copilot_model() {
    local model="$1"
    # copilot validates --model before doing anything else; invalid models
    # produce "argument 'X' is invalid. Allowed choices are ..." and exit non-zero.
    # Use --help as a no-op target so valid models don't start a session.
    local output
    output=$(copilot --model "$model" --help 2>&1)
    local rc=$?
    if echo "$output" | grep -q "is invalid\|Allowed choices"; then
        return 1
    fi
    [[ $rc -eq 0 ]] && return 0
    return 2
}

_check_opencode_model() {
    local model="$1"
    if opencode models 2>/dev/null | grep -qF "$model"; then
        return 0
    fi
    return 1
}

check_model_availability() {
    echo -e "\n  ${BOLD}Model availability${NC}"

    local tmpdir
    tmpdir=$(mktemp -d)
    local checked=""
    local pairs=()

    # Collect unique cli:model pairs from all AI profiles
    local profile cli model _effort
    for profile in "$AI_OPUS" "$AI_OPUS_HIGH" "$AI_SONNET" "$AI_GPT" "$AI_GPT_HIGH" "$AI_MIMO"; do
        IFS='|' read -r cli model _effort <<< "$profile"
        [[ -z "$cli" || -z "$model" ]] && continue
        local pair="${cli}:${model}"
        case " $checked " in *" ${pair} "*) continue ;; esac
        checked="${checked} ${pair}"
        command -v "$cli" &>/dev/null || continue
        pairs+=("$pair")
    done

    # Launch all model checks in parallel
    for pair in "${pairs[@]}"; do
        local cli="${pair%%:*}" model="${pair#*:}"
        local safe="${pair//:/_}"; safe="${safe//\//__}"
        (
            local rc=2
            case "$cli" in
                claude)   _check_claude_model "$model";   rc=$? ;;
                codex)    _check_codex_model "$model";    rc=$? ;;
                copilot)  _check_copilot_model "$model";  rc=$? ;;
                opencode) _check_opencode_model "$model"; rc=$? ;;
            esac
            echo "$rc" > "${tmpdir}/${safe}"
        ) &
    done

    # Spinner while waiting for parallel checks
    local i=0
    while [[ $(jobs -rp | wc -l) -gt 0 ]]; do
        local idx=$((i % ${#SPINNER_FRAMES}))
        printf '\r  %s Checking models...' "${SPINNER_FRAMES:idx:1}" >&2
        sleep 0.1
        i=$((i + 1))
    done
    printf '\r\033[K' >&2
    wait

    # Collect results
    local errors=0 warnings=0
    for pair in "${pairs[@]}"; do
        local cli="${pair%%:*}" model="${pair#*:}"
        local safe="${pair//:/_}"; safe="${safe//\//__}"
        local r
        r=$(cat "${tmpdir}/${safe}" 2>/dev/null) || r=2
        case "$r" in
            0) log_ok "${cli}/${model}" ;;
            1) log_error "${cli}/${model} — not available"
               errors=$((errors + 1)) ;;
            *) log_warn "${cli}/${model} — could not verify"
               warnings=$((warnings + 1)) ;;
        esac
    done

    rm -rf "$tmpdir"
    [[ $warnings -gt 0 ]] && log_warn "${warnings} model(s) could not be verified"
    return "$errors"
}

preflight_checks() {
    local cache_mode="full"
    if [[ "$SKIP_CACHE" == "true" ]]; then
        cache_mode="bypass"
    elif _preflight_cache_valid; then
        cache_mode="cached"
    fi

    echo ""
    echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════════════════${NC}"
    case "$cache_mode" in
        cached)
        echo -e "${BOLD}${CYAN}  Pre-flight Checks ${DIM}(cached — less than 24h old)${NC}"
            ;;
        bypass)
            echo -e "${BOLD}${CYAN}  Pre-flight Checks ${DIM}(cache bypassed --skip-cache)${NC}"
            ;;
        *)
            echo -e "${BOLD}${CYAN}  Pre-flight Checks${NC}"
            ;;
    esac
    echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════════════════${NC}"

    check_bmad_version
    [[ "$cache_mode" == "cached" ]] && return 0

    local errors=0

    if [[ -f "$SPRINT_STATUS" ]]; then
        log_ok "Sprint status file exists"
    else
        log_error "Sprint status file missing: ${SPRINT_STATUS}"
        errors=$((errors + 1))
    fi

    local tool
    for tool in "${TOOL_NAMES[@]}"; do
        if command -v "$tool" &>/dev/null; then
            log_ok "${tool} found"
        else
            log_error "${tool} not found in PATH"
            errors=$((errors + 1))
        fi
    done

    if [[ -d "$IMPL_ARTIFACTS" ]]; then
        log_ok "Implementation artifacts directory exists"
    else
        log_error "Implementation artifacts directory missing: ${IMPL_ARTIFACTS}"
        errors=$((errors + 1))
    fi

    # Check model availability for each CLI (runs in parallel)
    check_model_availability
    errors=$((errors + $?))

    if (( errors > 0 )); then
        echo ""
        log_error "${errors} pre-flight check(s) failed. Aborting."
        exit 1
    fi

    _preflight_cache_write
    echo ""
}

# ============================================================
# Step Runner & Error Handling
# ============================================================

should_run_step() {
    local step_id="$1"
    if [[ -z "$FROM_STEP" ]]; then
        return 0
    fi

    # Map parallel sub-steps (e.g. 1.2a) to parent step (1.2) for ordering
    local effective_id="$step_id"
    if [[ "$step_id" =~ ^[0-9]+\.[0-9]+[a-f]$ ]]; then
        effective_id="${step_id%[a-f]}"
    fi

    local from_pos=-1 step_pos=-1 pos=0
    for s in $STEP_ORDER; do
        [[ "$s" == "$FROM_STEP" ]] && from_pos=$pos
        [[ "$s" == "$effective_id" ]] && step_pos=$pos
        pos=$((pos + 1))
    done

    if (( from_pos == -1 )); then
        log_error "Unknown step ID for --from-step: ${FROM_STEP}"
        exit 1
    fi

    (( step_pos >= from_pos ))
}

# run_step <step_id> <step_name> <command...>
run_step() {
    [[ "$_ABORT" == true ]] && exit 130

    local step_id="$1" step_name="$2"
    shift 2

    set_step_name "$step_id" "$step_name"

    if ! should_run_step "$step_id"; then
        return 0
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        log_dry "$step_id" "$step_name"
        set_step_status "$step_id" "dry-run"
        set_step_duration "$step_id" "0"
        return 0
    fi

    log_step "$step_id" "$step_name"

    # Per-step raw output log — lives in TMP_DIR, cleaned at pipeline end
    CURRENT_STEP_LOG="${TMP_DIR}/step-${step_id}.log"
    : > "$CURRENT_STEP_LOG"

    parse_step_config "$step_id"
    local model_info; model_info="$(_format_model_info)"

    local start_time; start_time=$(date +%s)

    start_activity_monitor "$step_name"

    if "$@"; then
        stop_activity_monitor
        local end_time; end_time=$(date +%s)
        local duration=$((end_time - start_time))
        set_step_duration "$step_id" "$duration"
        set_step_status "$step_id" "ok"
        _log_pipeline_entry "$step_id" "$model_info" "$duration" "ok" "$step_name"
        log_ok "Completed in $(format_duration $duration)"
    else
        stop_activity_monitor
        local end_time; end_time=$(date +%s)
        local duration=$((end_time - start_time))
        set_step_duration "$step_id" "$duration"
        set_step_status "$step_id" "FAILED"
        _log_pipeline_entry "$step_id" "$model_info" "$duration" "FAILED" "$step_name"
        echo "# FAILED at step ${step_id} after $(format_duration $((end_time - PIPELINE_START_TIME))) wall time" >> "$PIPELINE_LOG"
        echo "# Resume: ./auto-bmad-story.sh --from-step ${step_id} --story ${STORY_ID}" >> "$PIPELINE_LOG"
        log_error "Step ${step_id} (${step_name}) FAILED after $(format_duration $duration)"
        log_error "Step log: ${CURRENT_STEP_LOG}"
        log_error "Resume: ./auto-bmad-story.sh --from-step ${step_id} --story ${STORY_ID}"
        exit 1
    fi
}

# Run parallel review steps. Failures are warnings, not fatal.
# Entry format: "step_id|name|file_prefix|ai_suffix" for review steps
#            or "step_id|name|func_name" for arbitrary functions
run_parallel_reviews() {
    [[ "$_ABORT" == true ]] && exit 130

    # --skip-reviews: skip entire function
    if [[ "$SKIP_REVIEWS" == "true" ]]; then
        for entry in "$@"; do
            local sid sname
            IFS='|' read -r sid sname _ _ <<< "$entry"
            set_step_name "$sid" "$sname"
            set_step_status "$sid" "skipped"
            set_step_duration "$sid" "0"
        done
        local first_sid last_sid
        IFS='|' read -r first_sid _ _ _ <<< "$1"
        IFS='|' read -r last_sid _ _ _ <<< "${!#}"
        log_skip "Steps ${first_sid}–${last_sid} — --skip-reviews"
        return 0
    fi

    # --fast-reviews: only run the first entry (GPT / suffix "a")
    if [[ "$FAST_REVIEWS" == "true" ]]; then
        local first_entry="$1"
        shift
        for entry in "$@"; do
            local sid sname
            IFS='|' read -r sid sname _ _ <<< "$entry"
            set_step_name "$sid" "$sname"
            set_step_status "$sid" "skipped"
            set_step_duration "$sid" "0"
        done
        set -- "$first_entry"
    fi

    local -a pids=() sids=() snames=()
    local count=0

    for entry in "$@"; do
        local sid sname field3 field4
        IFS='|' read -r sid sname field3 field4 <<< "$entry"

        if ! should_run_step "$sid"; then
            continue
        fi

        set_step_name "$sid" "$sname"

        if [[ "$DRY_RUN" == "true" ]]; then
            log_dry "$sid" "$sname"
            set_step_status "$sid" "dry-run"
            set_step_duration "$sid" "0"
            continue
        fi

        # Record start time for duration tracking
        set_step_start "$sid" "$(date +%s)"

        # Each parallel step gets its own raw output log in TMP_DIR.
        # CURRENT_STEP_LOG is captured per-iteration before backgrounding so
        # each subshell inherits the correct path (avoids race with the loop
        # reassigning the variable for the next iteration).
        local step_log="${TMP_DIR}/step-${sid}.log"
        : > "$step_log"

        # Suppress terminal output — log file still gets full output via tee.
        if [[ -n "$field4" ]]; then
            CURRENT_STEP_LOG="$step_log" run_review_step "$sid" "$field3" "$field4" >/dev/null &
        else
            CURRENT_STEP_LOG="$step_log" "$field3" >/dev/null &
        fi
        pids+=($!)
        sids+=("$sid")
        snames+=("$sname")
        count=$((count + 1))
    done

    if [[ "$DRY_RUN" == "true" || $count -eq 0 ]]; then
        return 0
    fi

    # --- Print group header (e.g. ">>> Steps 2a–2d: Validate Story (parallel)") ---
    local first_sid="${sids[0]}" last_sid="${sids[$((count-1))]}"
    local group_name="${snames[0]}"
    group_name="${group_name% (*}"          # strip trailing " (GPT)" etc.
    echo ""
    echo -e "${BOLD}${BLUE}>>> Steps ${first_sid}–${last_sid}: ${group_name} (parallel)${NC}"

    # --- Live status board: poll PIDs and redraw in-place ---

    # Print placeholder lines for the board
    printf '\033[?25l'  # hide cursor
    for ((i=0; i<count; i++)); do echo ""; done

    # Status tracking
    local -a statuses=() durations=()
    for ((i=0; i<count; i++)); do
        statuses+=("running")
        durations+=("0")
    done

    # Pre-cache model info per step (avoids re-parsing in poll loop)
    local -a model_infos=()
    for ((i=0; i<count; i++)); do
        parse_step_config "${sids[$i]}"
        model_infos+=("$(_format_model_info)")
    done

    local running=$count
    local spinner_idx=0

    while (( running > 0 )); do
        local now; now=$(date +%s)

        # Poll each background process
        for ((i=0; i<count; i++)); do
            [[ "${statuses[$i]}" != "running" ]] && continue
            if ! kill -0 "${pids[$i]}" 2>/dev/null; then
                local t0; t0=$(get_step_start "${sids[$i]}" "$now")
                local dur=$((now - t0))
                durations[$i]="$dur"
                set_step_duration "${sids[$i]}" "$dur"
                if wait "${pids[$i]}" 2>/dev/null; then
                    statuses[$i]="ok"
                    set_step_status "${sids[$i]}" "ok"
                    _log_pipeline_entry "${sids[$i]}" "${model_infos[$i]}" "$dur" "ok" "${snames[$i]}"
                else
                    statuses[$i]="FAILED"
                    set_step_status "${sids[$i]}" "FAILED"
                    _log_pipeline_entry "${sids[$i]}" "${model_infos[$i]}" "$dur" "FAILED" "${snames[$i]}"
                fi
                running=$((running - 1))
            fi
        done

        # Redraw board in-place
        echo -ne "\033[${count}A"
        local frame="${SPINNER_FRAMES:spinner_idx%${#SPINNER_FRAMES}:1}"
        for ((i=0; i<count; i++)); do
            echo -ne "\033[2K"
            case "${statuses[$i]}" in
                running)
                    local t0; t0=$(get_step_start "${sids[$i]}" "$now")
                    local elapsed=$(( now - t0 ))
                    echo -e "  ${frame} ${snames[$i]}  ${DIM}$(format_duration $elapsed)${NC}"
                    ;;
                ok)
                    echo -e "  ${GREEN}✓${NC} ${snames[$i]}  ${GREEN}$(format_duration "${durations[$i]}")${NC}"
                    ;;
                FAILED)
                    echo -e "  ${YELLOW}!${NC} ${snames[$i]}  ${YELLOW}failed after $(format_duration "${durations[$i]}")${NC}"
                    ;;
            esac
        done

        (( running > 0 )) && sleep 0.1
        spinner_idx=$((spinner_idx + 1))
    done

    printf '\033[?25h'  # restore cursor
    return 0
}

# ============================================================
# Step Functions
# ============================================================

# --- Phase 0: Epic Start ---

step_0_1_test_design() {
    run_ai "0.1" "/bmad-testarch-test-design yolo - run in epic-level mode for epic ${EPIC_ID}"
}

# --- Phase 1: Story Preparation ---

step_1_1_create_story() {
    run_ai "1.1" "/bmad-create-story yolo - story ${STORY_ID}"
    detect_story_file_path
    if [[ -n "$STORY_FILE_PATH" ]]; then
        log_ok "Story file: ${STORY_FILE_PATH}"
    else
        log_warn "Could not detect story file path — will retry before finalization"
    fi
}

step_1_3_spec_triage() {
    local triage_report="${STORY_ARTIFACTS}/${STORY_SHORT_ID}-1.3-spec-triage.md"

    # Build dynamic list of review files from Phase 1.2
    local review_files=""
    local f
    for f in "${TMP_DIR}"/1.2*-*.md; do
        [[ -f "$f" ]] && review_files="${review_files}
- ${f}"
    done

    run_ai "1.3" "You are the Spec Triage Analyst. Read ALL of the following spec validation review files (skip any that don't exist):
${review_files}

Cross-reference findings across all validation reviews. Your job:

1. **Normalize**: convert each finding into a consistent format (id, source, title, detail, location)
2. **Deduplicate**: merge overlapping findings (same issue flagged by multiple reviewers). Use the most specific finding as the base.
3. **Classify** each unique finding into exactly one category:
   - **intent_gap** — spec/intent is incomplete; cannot resolve from existing information
   - **bad_spec** — upstream spec (epic, architecture, PRD) is wrong or ambiguous; should be amended
   - **patch** — story issue fixable without human input (contradictions, wrong values, missing details inferable from architecture/epic)
   - **defer** — pre-existing issue not caused by this story
   - **reject** — noise, false positive, stylistic preference, or scope expansion disguised as quality improvement

IMPORTANT: Be conservative with 'patch'. If a finding adds NEW requirements, tasks, or acceptance criteria not present in the epic or architecture, classify it as 'intent_gap' or 'reject' — not 'patch'. Only classify as 'patch' when the fix corrects something that is clearly wrong or inconsistent within the existing scope.

Drop all reject findings but record the count.

Save your triage report to ${triage_report} with this structure:

1. **Header**: story ID, step 1.3, timestamp

2. **Decision summary table** (markdown) — one row per finding:

| # | Finding | Category | Reviewers | Confidence | Rationale |
|---|---------|----------|-----------|------------|-----------|

3. **Detailed rationale** — for each finding, a short paragraph with:
   - The reviewers' arguments
   - Your reasoning for the classification
   - For 'patch' items: what specifically needs to be fixed
   - For 'bad_spec' items: what is wrong or ambiguous in the upstream spec
   - For 'intent_gap' items: what information is missing and where it should come from

4. **Classification counts**: total findings, per-category counts, reject count"
}

step_1_4_resolve_spec_findings() {
    local triage_report="${STORY_ARTIFACTS}/${STORY_SHORT_ID}-1.3-spec-triage.md"
    run_ai "1.4" "/bmad-analyst yolo - Read the spec triage report at ${triage_report}.

Resolve ALL items classified as 'patch', 'bad_spec', or 'intent_gap' in the decision summary table. For each finding, follow the appropriate strategy:

**patch** — Fix directly in the story file:
1. Read the detailed rationale to understand what needs to change
2. Fix the issue in the story file
3. Verify the fix is consistent with the rest of the story

**bad_spec** — The upstream spec (epic, architecture, PRD) is wrong or ambiguous:
1. Read the relevant upstream artifacts (epic, architecture, PRD) to understand the full context
2. Amend the story to resolve the ambiguity, picking the interpretation most consistent with upstream intent
3. Add a Change Log entry with: [bad_spec] tag, finding ID, what was ambiguous, which upstream artifact informed the decision, what was changed in the story, and the rationale

**intent_gap** — The captured intent is incomplete:
1. Search upstream artifacts (epic, architecture, PRD, project context) for information that fills the gap
2. If fillable from existing artifacts: amend the story and add a Change Log entry with: [intent_gap] tag, finding ID, what was missing, which upstream artifact provided the answer, what was added to the story, and the reasoning
3. If NOT fillable (the information simply does not exist in any upstream artifact): do NOT invent new requirements. Instead, append to the triage report a section '## Unresolvable Findings' listing each unfillable intent_gap with: finding ID, title, what is missing, and why it cannot be inferred. Then move on.

**defer** — Skip (pre-existing, not this story's concern).

CONSTRAINT: When resolving bad_spec or intent_gap, you may ONLY use information already present in upstream artifacts. Do NOT invent new requirements, tasks, or acceptance criteria.

After all resolutions, briefly note what you changed for each item and its category."
}

# --- Phase 2: TDD + Implementation ---

step_2_1_tdd_red() {
    run_ai "2.1" "/bmad-testarch-atdd yolo - story ${STORY_ID} - Your scope is strictly TDD red phase: generate failing acceptance tests ONLY. Do not implement, create or modify any production code, API routes, UI components, database schemas, or application logic"
}

step_2_2_implementation() {
    run_ai "2.2" "/bmad-dev-story yolo - ${STORY_ID}"
}

# --- Phase 3: Code Review ---

step_3_2_acceptance_auditor() {
    local audit_report="${STORY_ARTIFACTS}/${STORY_SHORT_ID}-3.2-code-acceptance.md"
    run_ai "3.2" "Read the story file for ${STORY_ID} at ${STORY_FILE_PATH} and all code changes (commits ${COMMIT_BASELINE}..HEAD).

You are the Acceptance Auditor. Verify that the implementation satisfies every acceptance criterion in the story.

For each acceptance criterion:
1. Identify the specific code/test that satisfies it
2. Grade: PASS (clearly satisfied), PARTIAL (partially satisfied), FAIL (not satisfied), UNTESTABLE (cannot verify from code alone)
3. Note any gaps or concerns

Save your acceptance audit report to ${audit_report} with this structure:

1. **Header**: story ID, step 3.2, timestamp

2. **Acceptance criteria matrix** (markdown table):

| # | Criterion | Status | Evidence | Notes |
|---|-----------|--------|----------|-------|

3. **Coverage gaps**: any criteria not fully covered by tests or implementation

4. **Summary**: total criteria, pass/partial/fail/untestable counts, overall assessment"
}

step_3_3_triage() {
    local triage_report="${STORY_ARTIFACTS}/${STORY_SHORT_ID}-3.3-code-triage.md"

    # Build dynamic list of review files from Phase 3.1
    local review_files=""
    local f
    for f in "${TMP_DIR}"/3.1*-*.md; do
        [[ -f "$f" ]] && review_files="${review_files}
- ${f}"
    done

    local acceptance_report="${STORY_ARTIFACTS}/${STORY_SHORT_ID}-3.2-code-acceptance.md"

    run_ai "3.3" "You are the Triage Analyst. Read ALL of the following review findings files (skip any that don't exist):
${review_files}

Also read the acceptance audit report (if it exists):
- ${acceptance_report}

Cross-reference all findings across all reviews. Your job:

1. **Normalize**: convert each finding into a consistent format (id, source, title, detail, location)
2. **Deduplicate**: group overlapping findings (same underlying issue flagged by different reviewers or review types) into single entries. Use the most specific finding as the base. Track all original sources.
3. **Classify** each unique finding into exactly one category:
   - **intent_gap** — spec/intent is incomplete; cannot resolve from existing information
   - **bad_spec** — spec is wrong or ambiguous; should be amended
   - **patch** — code issue fixable without human input
   - **defer** — pre-existing issue not caused by current change
   - **reject** — noise, false positive, or handled elsewhere

Evaluate on argument quality — not reviewer count. A single reviewer demonstrating a concrete bug outweighs four reviewers raising vague concerns. Record how many reviewers flagged each finding as useful context, not decision criteria.

Drop all reject findings but record the count.

Save your triage report to ${triage_report} with this structure:

1. **Header**: story ID, step 3.3, timestamp

2. **Decision summary table** (markdown) — one row per finding:

| # | Finding | Category | Flagged By | Confidence | Rationale |
|---|---------|----------|------------|------------|-----------|

3. **Detailed rationale** — for each finding in the table, a short paragraph with:
   - The reviewers' arguments (agreements and disagreements)
   - Your reasoning for the classification
   - For 'patch' items: what specifically needs to be fixed

4. **Reviewer signal assessment** — for each review session that produced a file:

| Reviewer | Type | Findings | Survived | Unique | Dupes | Signal | Notes |
|----------|------|----------|----------|--------|-------|--------|-------|

Where: Survived = not rejected, Unique = only this reviewer caught it, Dupes = also flagged by others, Signal = high/medium/low

5. **Overlap matrix** — which reviewers agreed on which findings:

| Finding | GPT-EC | GPT-Adv | MiMo-EC | MiMo-Adv | Claude-EC | Claude-Adv | Auditor |
|---------|--------|---------|---------|----------|-----------|------------|---------|

6. **Classification counts**: total findings, per-category counts, reject count

7. **Acceptance audit integration**: any acceptance criteria gaps that align with review findings"
}

step_3_4_dev_fix() {
    local triage_report="${STORY_ARTIFACTS}/${STORY_SHORT_ID}-3.3-code-triage.md"
    run_ai "3.4" "/bmad-dev yolo - Read the triage report at ${triage_report}.

Fix ALL items classified as 'patch' in the decision summary table. For each patch item:
1. Read the detailed rationale to understand what needs to change
2. Implement the fix
3. Verify the fix doesn't break existing tests

Skip items classified as 'intent_gap', 'bad_spec', 'defer', or 'reject' — those require spec-level resolution, not code fixes.

After all fixes, briefly note what you changed for each patch item."
}

step_3_5_resolve_code_spec_findings() {
    local triage_report="${STORY_ARTIFACTS}/${STORY_SHORT_ID}-3.3-code-triage.md"
    run_ai "3.5" "/bmad-analyst yolo - Read the code triage report at ${triage_report}.

Resolve ALL items classified as 'bad_spec' or 'intent_gap' in the decision summary table. These are spec-level issues surfaced during code review — the dev has already fixed 'patch' items in step 3.4 and code is already implemented.

IMPORTANT: Since implementation is already complete, every story amendment must be thoroughly documented so reviewers can trace what changed, why, and whether the existing code still aligns.

**bad_spec** — The spec led to incorrect or ambiguous implementation:
1. Read the relevant upstream artifacts (epic, architecture, PRD) to understand the full context
2. Amend the story file to clarify the spec, picking the interpretation most consistent with upstream intent
3. Add a Change Log entry with: [bad_spec:post-impl] tag, finding ID, what was ambiguous in the original spec, which upstream artifact informed the decision, the exact story sections modified (quote old → new), and whether the current implementation (including any step 3.4 fixes) is consistent with the resolution — flag any inconsistency explicitly
4. If the implementation diverges from the amended spec, note this clearly as a follow-up action item in the Change Log — do NOT modify code

**intent_gap** — Code review found the captured intent is incomplete:
1. Search upstream artifacts (epic, architecture, PRD, project context) for information that fills the gap
2. If fillable from existing artifacts: amend the story and add a Change Log entry with: [intent_gap:post-impl] tag, finding ID, what was missing, which upstream artifact provided the answer, the exact story sections modified (quote old → new), and whether the current implementation covers this gap — flag if it does not
3. If NOT fillable: do NOT invent new requirements. Instead, append to the triage report a section '## Unresolvable Findings' listing each unfillable intent_gap with: finding ID, title, what is missing, and why it cannot be inferred. Then move on.

Skip 'patch' (already fixed by dev), 'defer', and 'reject' items.

CONSTRAINT: You may ONLY use information already present in upstream artifacts. Do NOT invent new requirements, tasks, or acceptance criteria. Do NOT modify any code — only amend the story file and document changes.

After all resolutions, briefly note what you changed for each item and its category."
}

# --- Phase 4: Traceability & Automation ---

step_4_1_trace() {
    run_ai "4.1" "/bmad-testarch-trace yolo - story ${STORY_ID}"
}

step_4_2_automate() {
    run_ai "4.2" "/bmad-testarch-automate yolo - story ${STORY_ID}"
}

# --- Phase 5: Epic End ---

step_5_1_epic_trace() {
    run_ai "5.1" "/bmad-testarch-trace yolo - run in epic-level mode for epic ${EPIC_ID}"
}

step_5_2_epic_nfr() {
    run_ai "5.2" "/bmad-testarch-nfr yolo - run in epic-level mode for epic ${EPIC_ID}"
}

step_5_3_epic_test_review() {
    run_ai "5.3" "/bmad-testarch-test-review yolo - run in epic-level mode for epic ${EPIC_ID}"
}

step_5_4_retrospective() {
    run_ai "5.4" "/bmad-retrospective yolo - epic ${EPIC_ID}"
}

step_5_5_project_context() {
    run_ai "5.5" "/bmad-generate-project-context yolo - if a project context file already exists, update it"
}

# --- Generate Pipeline Report (structured markdown) ---

generate_pipeline_report() {
    local total_compute=0
    local steps_ok=0 steps_failed=0

    # Collect all step IDs including parallel sub-steps by scanning the raw log
    local all_step_ids=""
    if [[ -f "$PIPELINE_LOG" ]]; then
        all_step_ids=$(awk '/^  [0-9]/ { print $1 }' "$PIPELINE_LOG" 2>/dev/null)
    fi

    # Calculate totals from tracked steps (STEP_ORDER + any sub-steps that ran)
    for sid in $STEP_ORDER $all_step_ids; do
        local status; status="$(get_step_status "$sid")"
        [[ "$status" == "skipped" || "$status" == "dry-run" || "$status" == "" ]] && continue

        local duration; duration="$(get_step_duration "$sid")"
        if [[ "$duration" != "0" ]]; then
            total_compute=$((total_compute + duration))
        fi

        [[ "$status" == "ok" ]] && steps_ok=$((steps_ok + 1))
        [[ "$status" == "FAILED" ]] && steps_failed=$((steps_failed + 1))
    done

    local wall_time=$(( $(date +%s) - PIPELINE_START_TIME ))
    local savings=$((total_compute - wall_time))
    (( savings < 0 )) && savings=0

    local final_sha=""
    if [[ -n "$COMMIT_BASELINE" ]]; then
        final_sha="$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null)"
    fi

    local branch_name
    branch_name="$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'n/a')"

    {
        echo "# Pipeline Report — ${STORY_ID}"
        echo ""
        echo "## Summary"
        echo ""
        echo "| Metric | Value |"
        echo "|--------|-------|"
        echo "| Story | ${STORY_ID} |"
        echo "| Branch | ${branch_name} |"
        echo "| Started | $(grep -m1 '^# Started:' "$PIPELINE_LOG" 2>/dev/null | sed 's/^# Started: //' || echo 'n/a') |"
        echo "| Finished | $(date -u +%Y-%m-%dT%H:%M:%SZ) |"
        echo "| Wall Time | $(format_duration $wall_time) |"
        echo "| Compute Time | $(format_duration $total_compute) |"
        echo "| Parallelism Savings | $(format_duration $savings) |"
        echo "| Steps | ${steps_ok} ok, ${steps_failed} failed |"
        [[ -n "$final_sha" ]] && echo "| Commit | ${final_sha} (WIP) |"
        echo ""
        echo "## Step Log"
        echo ""
        echo "| Step | Timestamp | Model | Duration | Status | Name |"
        echo "|------|-----------|-------|----------|--------|------|"

        # Parse the raw pipeline log entries into markdown table rows
        if [[ -f "$PIPELINE_LOG" ]]; then
            while IFS= read -r line; do
                # Match step entry lines: "  STEP_ID  TIMESTAMP  MODEL  DURATION  STATUS  NAME"
                if [[ "$line" =~ ^[[:space:]]+([0-9][^[:space:]]*)[[:space:]]+([0-9T:Z-]+)[[:space:]]+([^[:space:]]+)[[:space:]]+([^[:space:]]+)[[:space:]]+(ok|FAILED)[[:space:]]+(.+)$ ]]; then
                    printf "| %s | %s | %s | %s | %s | %s |\n" \
                        "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}" \
                        "${BASH_REMATCH[4]}" "${BASH_REMATCH[5]}" "${BASH_REMATCH[6]}"
                fi
            done < "$PIPELINE_LOG"
        fi

        echo ""

        # Git changes section
        if [[ -n "$COMMIT_BASELINE" ]]; then
            echo "## Git Changes"
            echo ""
            echo '```'
            git -C "$PROJECT_ROOT" diff --stat "$COMMIT_BASELINE" HEAD 2>/dev/null || echo "(no changes)"
            echo '```'
            echo ""
        fi

        # Placeholder for reviewer assessment (populated by tech-writer step 6.1)
        echo "## Reviewer Assessment"
        echo ""
        echo "<!-- Populated by the tech-writer step. Read both triage reports and the acceptance audit to fill in: -->"
        echo ""
        echo "| Model | Phase | Findings | Accepted | Signal | Notes |"
        echo "|-------|-------|----------|----------|--------|-------|"
        echo ""
        echo "### Aggregate Model Performance"
        echo ""
        echo "| Model | Total Findings | Accepted | Accept Rate | Avg Signal |"
        echo "|-------|---------------|----------|-------------|------------|"
        echo ""

    } > "$PIPELINE_REPORT"
}

# --- Phase 6: Finalization ---

step_6_1_document() {
    if [[ -z "$STORY_FILE_PATH" ]]; then
        detect_story_file_path
    fi

    local story_ref="${STORY_FILE_PATH:-the story file for ${STORY_ID}}"
    run_ai "6.1" "/bmad-tech-writer yolo - Finalize documentation for story ${STORY_ID}. The story file is at: ${story_ref}

Perform ALL of the following:

1. Read the story file and verify all sections that previous pipeline steps should have populated are present and up to date:
   - Status should be 'review' or later (not 'in-progress' or 'ready-for-dev')
   - All Tasks/Subtasks should be checked [x] (flag any that are unchecked)
   - Dev Agent Record: Agent Model Used, Completion Notes List, and Debug Log References should all be populated
   - File List must reflect ALL files created, modified, or deleted across the entire pipeline (not just implementation — check git status for any files the triage fixes touched that are not listed)
   - Change Log must include entries for spec triage patch fixes (Phase 1, if those steps ran) and code triage patch fixes (Phase 3, if those steps ran)
   Fix anything that is missing or incomplete.

2. Add an '## Auto-bmad Pipeline Artifacts' section after the Dev Agent Record. This is a reference index ONLY — do not duplicate content already in the Dev Agent Record, Change Log, or the artifacts themselves. List each artifact with a one-line outcome (pass/fail/N findings). Skip any that don't exist:
   - Pipeline report: ${STORY_ARTIFACTS}/${STORY_SHORT_ID}-6.1-pipeline-report.md
   - Spec triage: ${STORY_ARTIFACTS}/${STORY_SHORT_ID}-1.3-spec-triage.md
   - Code acceptance audit: ${STORY_ARTIFACTS}/${STORY_SHORT_ID}-3.2-code-acceptance.md
   - Code triage: ${STORY_ARTIFACTS}/${STORY_SHORT_ID}-3.3-code-triage.md

3. Read the pipeline report at ${PIPELINE_REPORT} and populate the 'Reviewer Assessment' section:
   - Read the reviewer signal assessment section from both triage reports (spec triage 1.3 and code triage 3.3, if they exist)
   - Fill in the per-phase table (Model | Phase | Findings | Accepted | Signal | Notes)
   - Fill in the aggregate table (Model | Total Findings | Accepted | Accept Rate | Avg Signal)
   - Remove the HTML comment placeholder

4. Add an '## Auto-bmad Completion' section with ONLY information not already captured in the Dev Agent Record or Change Log:

   ### Pipeline Summary
   - Duration, models used, result (steps passed, files changed), link to pipeline-report.md

   ### Review Summary
   A summary table:
   | Phase | Step | Findings | Patch | Defer | Intent Gap | Bad Spec | Report |
   With one row per review artifact (spec triage, acceptance audit, code triage) linking to the file.

   ### Notable Decisions
   Key decisions made during the pipeline (not already in Change Log).

   ### Pipeline Learnings
   Useful observations from the pipeline run.

   ### Manual Testing Required
   Checklist of items requiring manual verification (as checkboxes).

   ### Open Questions
   Anything unresolved.

   ### Commit Message
   The commit message for all changes in story ${STORY_ID} inside a code block, following Conventional Commits 1.0.0 (<type>(<scope>): <subject> headline with <summary> body after a blank line). Type: build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test.

   Do NOT repeat completion notes, file lists, decision logs, or fix summaries — those are already in the Dev Agent Record and Change Log."
}

step_6_2_close() {
    if [[ -z "$STORY_FILE_PATH" ]]; then
        detect_story_file_path
    fi

    local story_ref="${STORY_FILE_PATH:-the story file for ${STORY_ID}}"
    run_ai "6.2" "/bmad-sm yolo - Close out story ${STORY_ID}. The story file is at: ${story_ref}

1. Set the story status to done in the story file if not already set.
2. Update _bmad-output/implementation-artifacts/sprint-status.yaml to set the story status to done if not already set."
}

# ============================================================
# Pipeline Orchestrator
# ============================================================

run_pipeline() {
    local story_file_ref="${STORY_FILE_PATH:-the implementation-artifacts directory}"

    # COMMIT_BASELINE is set in main() before log init (resume path needs it from log header)

    # --- Phase 0: Epic Start ---
    if is_epic_start && [[ "$SKIP_EPIC_PHASES" == "false" ]]; then
        if [[ "$SKIP_TEA" == "true" ]]; then
            log_skip "Phase 0 — TEA not installed"
        else
            log_phase "0" "Epic Start: Pre-Implementation"
            run_step "0.1" "TEA Test Design (epic-level)" step_0_1_test_design
            git_checkpoint "phase 0 — epic start"
        fi
    else
        if [[ "$SKIP_EPIC_PHASES" == "true" ]]; then
            log_skip "Phase 0 — --skip-epic-phases"
        elif ! is_epic_start; then
            log_skip "Phase 0 — not first story in epic"
        fi
    fi

    # --- Phase 1: Story Preparation ---
    log_phase "1" "Story Preparation"

    run_step "1.1" "Create Story" step_1_1_create_story

    # Step 1.2: Spec Validation Reviews (3 AIs in parallel)
    run_parallel_reviews \
        "1.2a|Validate Story (GPT)|validate|gpt" \
        "1.2b|Validate Story (MiMo)|validate|mimo" \
        "1.2c|Validate Story (Claude)|validate|claude"

    # Steps 1.3-1.4: Triage → Fix (skipped with --skip-reviews or --fast-reviews)
    if [[ "$SKIP_REVIEWS" == "false" && "$FAST_REVIEWS" == "false" ]]; then
        run_step "1.3" "Spec Triage" step_1_3_spec_triage
        run_step "1.4" "Resolve Spec Findings (analyst)" step_1_4_resolve_spec_findings
    else
        log_skip "Steps 1.3–1.4 — $([[ "$SKIP_REVIEWS" == "true" ]] && echo "--skip-reviews" || echo "--fast-reviews")"
    fi

    git_checkpoint "phase 1 — story preparation"

    # --- Phase 2: TDD + Implementation ---
    log_phase "2" "TDD + Implementation"

    if [[ "$SKIP_TEA" == "true" ]]; then
        log_skip "Step 2.1 — TEA not installed"
    else
        run_step "2.1" "TDD Red Phase" step_2_1_tdd_red
    fi
    run_step "2.2" "Implementation" step_2_2_implementation

    git_checkpoint "phase 2 — implementation"

    # --- Phase 3: Code Review ---
    log_phase "3" "Code Review"

    # Step 3.1: Parallel Reviews (3 AIs × 2 review types = 6 sessions)
    run_parallel_reviews \
        "3.1a|Edge Cases (GPT)|edge-cases|gpt" \
        "3.1b|Adversarial (GPT)|code-adversarial|gpt" \
        "3.1c|Edge Cases (MiMo)|edge-cases|mimo" \
        "3.1d|Adversarial (MiMo)|code-adversarial|mimo" \
        "3.1e|Edge Cases (Claude)|edge-cases|claude" \
        "3.1f|Adversarial (Claude)|code-adversarial|claude"

    # Steps 3.2-3.5: acceptance audit → triage → dev fix → resolve spec findings
    if [[ "$SKIP_REVIEWS" == "false" ]]; then
        run_step "3.2" "Acceptance Auditor" step_3_2_acceptance_auditor
        run_step "3.3" "Triage" step_3_3_triage
        run_step "3.4" "Fix Patch Items (dev)" step_3_4_dev_fix
        run_step "3.5" "Resolve Spec Findings (analyst)" step_3_5_resolve_code_spec_findings
    else
        log_skip "Steps 3.2–3.5 — --skip-reviews"
    fi

    git_checkpoint "phase 3 — code review fixes"

    # --- Phase 4: Traceability & Automation ---
    if [[ "$SKIP_TEA" == "true" ]]; then
        log_skip "Phase 4 — TEA not installed"
    else
        log_phase "4" "Traceability & Automation"

        run_step "4.1" "Testarch Trace" step_4_1_trace
        run_step "4.2" "Testarch Automate" step_4_2_automate
        git_checkpoint "phase 4 — traceability & automation"
    fi

    # --- Phase 5: Epic End ---
    if is_epic_end && [[ "$SKIP_EPIC_PHASES" == "false" ]]; then
        log_phase "5" "Epic End"

        if [[ "$SKIP_TEA" == "true" ]]; then
            log_skip "Steps 5.1–5.3 — TEA not installed"
        else
            run_parallel_reviews \
                "5.1|Epic Trace|step_5_1_epic_trace" \
                "5.2|Epic NFR Assessment|step_5_2_epic_nfr" \
                "5.3|Epic Test Review|step_5_3_epic_test_review"
        fi

        run_step "5.4" "Retrospective" step_5_4_retrospective
        run_step "5.5" "Generate Project Context" step_5_5_project_context
        git_checkpoint "phase 5 — epic end"
    else
        if [[ "$SKIP_EPIC_PHASES" == "true" ]]; then
            log_skip "Phase 5 — --skip-epic-phases"
        elif ! is_epic_end; then
            log_skip "Phase 5 — not last story in epic"
        fi
    fi

    # --- Phase 6: Finalization ---
    log_phase "6" "Finalization"

    # Generate pipeline report before the tech-writer runs so it can read it
    if [[ "$DRY_RUN" != "true" ]]; then
        generate_pipeline_report
        log_ok "Pipeline report: ${PIPELINE_REPORT}"
    fi

    run_step "6.1" "Document Story (tech-writer)" step_6_1_document
    run_step "6.2" "Close Story (SM)" step_6_2_close

    git_checkpoint "phase 6 — finalization"

    # Squash all phase commits into a single WIP commit
    git_squash_pipeline
}

# ============================================================
# Summary
# ============================================================

print_summary() {
    local pipeline_end_time; pipeline_end_time=$(date +%s)
    local total_duration=$((pipeline_end_time - PIPELINE_START_TIME))

    echo ""
    echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${CYAN}  Pipeline Summary — Story ${STORY_ID}${NC}"
    echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""

    printf "  ${BOLD}%-5s %-37s %-12s %-7s${NC}\n" "Step" "Name" "Duration" "Status"
    printf "  %-5s %-37s %-12s %-7s\n" "-----" "-------------------------------------" "------------" "-------"

    for sid in $STEP_ORDER; do
        local status; status="$(get_step_status "$sid")"
        local duration; duration="$(get_step_duration "$sid")"
        local name; name="$(get_step_name "$sid")"

        [[ "$status" == "skipped" ]] && continue

        local dur_str="-"
        [[ "$duration" != "0" ]] && dur_str="$(format_duration "$duration")"

        local status_color=""
        case "$status" in
            ok)       status_color="${GREEN}" ;;
            FAILED)   status_color="${RED}" ;;
            dry-run)  status_color="${DIM}" ;;
            *)        status_color="${NC}" ;;
        esac

        printf "  %-5s %-37s %-12s ${status_color}%-7s${NC}\n" \
            "$sid" "$name" "$dur_str" "$status"
    done

    echo ""
    echo -e "  ${BOLD}Total: $(format_duration $total_duration)${NC}"

    if [[ "$DRY_RUN" != "true" ]]; then
        echo ""
        local final_sha
        final_sha="$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null)"
        echo -e "  ${GREEN}✓${NC} WIP commit: ${BOLD}${final_sha}${NC}"
        echo -e "  ${DIM}Pipeline report: ${PIPELINE_REPORT}${NC}"

        # Surface unresolved spec findings (intent_gap/bad_spec that couldn't be auto-resolved)
        local spec_triage="${STORY_ARTIFACTS}/${STORY_SHORT_ID}-1.3-spec-triage.md"
        local code_triage="${STORY_ARTIFACTS}/${STORY_SHORT_ID}-3.3-code-triage.md"
        local unresolved_count=0
        local triage_file
        for triage_file in "$spec_triage" "$code_triage"; do
            if [[ -f "$triage_file" ]]; then
                local n
                n=$(grep -c '## Unresolvable Findings' "$triage_file" 2>/dev/null || true)
                if [[ "$n" -gt 0 ]]; then
                    # Count individual findings under the Unresolvable section
                    local items
                    items=$(sed -n '/## Unresolvable Findings/,/^## /p' "$triage_file" 2>/dev/null | grep -c '^\*\*\|^- \*\*\|^[0-9]' || true)
                    unresolved_count=$((unresolved_count + items))
                fi
            fi
        done
        if [[ "$unresolved_count" -gt 0 ]]; then
            echo ""
            echo -e "  ${YELLOW}⚠  ${unresolved_count} unresolvable finding(s) require manual review${NC}"
            echo -e "  ${DIM}Check triage reports for details: ${STORY_ARTIFACTS}/${NC}"
        fi

        # Print copy-paste manual finalization commands
        local commit_msg
        commit_msg="$(extract_story_commit_msg)"
        local branch_name="story/${STORY_ID}"

        echo ""
        echo -e "${BOLD}${CYAN}───────────────────────────────────────────────────────────${NC}"
        echo -e "${BOLD}${CYAN}  Manual Finalization${NC}"
        echo -e "${BOLD}${CYAN}───────────────────────────────────────────────────────────${NC}"
        echo ""
        echo -e "  ${DIM}# Amend WIP commit with the real commit message:${NC}"
        local escaped_msg="${commit_msg//\"/\\\"}"
        echo "  git commit --amend -m \"${escaped_msg}\""
        echo ""
        echo -e "  ${DIM}# Push and create PR:${NC}"
        echo "  git push -u origin ${branch_name}"
        echo "  gh pr create --title \"${commit_msg%%$'\n'*}\" --body \"Story ${STORY_SHORT_ID}. See story file for details.\""
        echo ""
    fi
}

# ============================================================
# CLI Argument Parsing & Main
# ============================================================

show_help() {
    cat <<HELPEOF
auto-bmad-story.sh — BMAD Story Pipeline Orchestrator

Automates one story at a time through the full BMAD implementation
workflow using multiple AI CLIs (claude, codex, copilot, opencode).

Usage: ./auto-bmad-story.sh [options]

Options:
  --story STORY_ID       Override auto-detection of next story
  --from-step STEP_ID    Resume pipeline from a specific step
                         Valid IDs: ${STEP_ORDER}
  --dry-run              Preview all steps without executing
  --skip-cache           Bypass pre-flight cache and force full checks
  --skip-epic-phases     Skip phases 0 (epic start) and 5 (epic end)
  --skip-tea             Skip TEA phases even if installed (0, 2.1, 4.x, 5.1-5.3)
  --skip-reviews         Skip all review phases (1.2-1.4, 3.x)
  --fast-reviews         Run only 1 GPT reviewer per phase, skip triage+fix
  --skip-git             Skip git write ops (branch, checkpoint, squash)
  --no-traces            Remove pipeline artifacts after finalization
  --safe-mode            Disable permission-bypass flags (AI tools prompt for approval)
                         (pipeline report is kept)
  --help                 Show this help message

Step Numbering:
  Phase N → steps N.1, N.2, ...
  Parallel sub-steps: N.Ma–N.Mc (spec) or N.Ma–N.Mf (code) review models
  --from-step uses parent step ID (e.g., 3.1 reruns entire parallel group)

  Phase 0: Epic Start     (0.1 TEA)
  Phase 1: Preparation    (1.1 create, 1.2a-c validation reviews, 1.3 triage, 1.4 resolve)
  Phase 2: Implementation (2.1 TDD, 2.2 impl)
  Phase 3: Code Review    (3.1a-f parallel reviews, 3.2 acceptance audit, 3.3 triage, 3.4 fix, 3.5 resolve)
  Phase 4: Traceability   (4.1 trace, 4.2 automate)
  Phase 5: Epic End       (5.1-5.3 parallel, 5.4 retro, 5.5 context)
  Phase 6: Finalization   (6.1 document, 6.2 close)

AI Profiles (edit at top of script):
  AI_OPUS      = Claude Opus 4.6 / max effort   — critical path, triage, acceptance audit, dev fix
  AI_OPUS_HIGH = Claude Opus 4.6 / high effort  — structured, non-critical (spec reviews, retro, docs)
  AI_SONNET    = Claude Sonnet 4.6 / high        — lightweight bookkeeping
  AI_GPT       = Codex GPT 5.4 / xhigh reason   — code reviews + edge cases
  AI_GPT_HIGH  = Codex GPT 5.4 / high reason    — spec-level reviews (pre-implementation)
  # AI_COPILOT = Copilot Gemini 3 Pro Preview     — available but not assigned (low quality reviews)
  # AI_MINIMAX — removed (low signal-to-noise ratio)
  AI_MIMO      = OpenCode MiMo V2 Pro / max      — parallel reviews

Examples:
  ./auto-bmad-story.sh                                    # Run next story
  ./auto-bmad-story.sh --dry-run                          # Preview the pipeline
  ./auto-bmad-story.sh --skip-cache                       # Force full pre-flight checks
  ./auto-bmad-story.sh --story 2-3-some-story             # Run a specific story
  ./auto-bmad-story.sh --from-step 3.1 --story 1-1-auth   # Resume from code review
  ./auto-bmad-story.sh --fast-reviews                      # Quick run: 1 GPT reviewer, triage+fix skipped
  ./auto-bmad-story.sh --skip-reviews --skip-tea           # Minimal: create → implement → close
  ./auto-bmad-story.sh --skip-git                          # No branch/checkpoint/squash
  ./auto-bmad-story.sh --safe-mode                         # AI tools prompt for permissions
HELPEOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run)        DRY_RUN=true; shift ;;
            --from-step)      FROM_STEP="$2"; shift 2 ;;
            --skip-cache)     SKIP_CACHE=true; shift ;;
            --story)
                STORY_ID="$2"
                if [[ ! "$STORY_ID" =~ ^[0-9]+-[0-9]+ ]]; then
                    log_error "Invalid story ID format: ${STORY_ID} (expected: N-N or N-N-slug)"
                    exit 1
                fi
                shift 2 ;;
            --skip-epic-phases) SKIP_EPIC_PHASES=true; shift ;;
            --skip-tea)         SKIP_TEA=true; shift ;;
            --skip-reviews)     SKIP_REVIEWS=true; shift ;;
            --fast-reviews)     FAST_REVIEWS=true; shift ;;
            --skip-git)         SKIP_GIT=true; shift ;;
            --no-traces)        NO_TRACES=true; shift ;;
            --safe-mode)        SAFE_MODE=true; shift ;;
            --help|-h)        show_help; exit 0 ;;
            *)
                log_error "Unknown argument: $1"
                echo ""
                show_help
                exit 1
                ;;
        esac
    done
    # --skip-reviews supersedes --fast-reviews
    if [[ "$SKIP_REVIEWS" == "true" ]]; then FAST_REVIEWS=false; fi
}

main() {
    trap 'stop_activity_monitor 2>/dev/null || true; _restore_cursor; [[ "$_ABORT" == true ]] && exit 130 || true' EXIT
    parse_args "$@"

    tput civis 2>/dev/null || true   # hide cursor for cleaner output

    preflight_checks

    if [[ -z "$STORY_ID" ]]; then
        detect_next_story
    fi
    extract_epic_id
    extract_short_id

    check_git_branch

    STORY_ARTIFACTS="${IMPL_ARTIFACTS}/auto-bmad/${STORY_SHORT_ID}"
    TMP_DIR="${PROJECT_ROOT}/.tmp/auto-bmad/${STORY_SHORT_ID}"
    PIPELINE_LOG="${TMP_DIR}/pipeline.log"
    PIPELINE_REPORT="${STORY_ARTIFACTS}/${STORY_SHORT_ID}-6.1-pipeline-report.md"
    mkdir -p "$STORY_ARTIFACTS" "$TMP_DIR"

    # Record baseline commit for final squash (captured early so resume path can persist it)
    COMMIT_BASELINE="$(git -C "$PROJECT_ROOT" rev-parse HEAD 2>/dev/null)"

    # Initialize raw pipeline log in TMP_DIR — temporary, converted to report at finalization
    local branch_name
    branch_name="$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'n/a')"

    if [[ -n "$FROM_STEP" && -f "$PIPELINE_LOG" ]]; then
        # ── RESUME PATH: preserve existing log, restore original start time + baseline ──
        local orig_started
        orig_started="$(grep -m1 '^# Started:' "$PIPELINE_LOG" | sed 's/^# Started: //')"
        if [[ -n "$orig_started" ]]; then
            PIPELINE_START_TIME=$(date -jf "%Y-%m-%dT%H:%M:%SZ" "$orig_started" +%s 2>/dev/null \
                               || date -d "$orig_started" +%s 2>/dev/null \
                               || date +%s)
        else
            PIPELINE_START_TIME=$(date +%s)
        fi

        local orig_baseline
        orig_baseline="$(grep -m1 '^# Baseline:' "$PIPELINE_LOG" | sed 's/^# Baseline: //')"
        [[ -n "$orig_baseline" ]] && COMMIT_BASELINE="$orig_baseline"

        # Strip prior failure/resume footer, append resume marker
        sed -i '' '/^# FAILED at step/d; /^# Resume:/d' "$PIPELINE_LOG"
        printf "# Resumed from: %s at %s\n" "$FROM_STEP" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$PIPELINE_LOG"
    else
        # ── FRESH PATH: new pipeline log ──
        {
            printf "# Pipeline — %s\n" "$STORY_ID"
            printf "# Started: %s\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
            printf "# Branch: %s\n" "$branch_name"
            printf "# Baseline: %s\n" "${COMMIT_BASELINE:-n/a}"
            printf "#\n"
            printf "# %-6s  %-20s  %-22s  %-10s  %-8s  %s\n" \
                "Step" "Timestamp" "CLI/Model" "Duration" "Status" "Name"
        } > "$PIPELINE_LOG"
        PIPELINE_START_TIME=$(date +%s)
    fi

    echo ""
    echo -e "${BOLD}${MAGENTA}╔═════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${MAGENTA}║                Auto-BMAD Story Pipeline                 ║${NC}"
    echo -e "${BOLD}${MAGENTA}╚═════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  Story:      ${BOLD}${STORY_ID}${NC}"
    echo -e "  Branch:     ${BOLD}$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'n/a')${NC}"
    echo -e "  Epic:       ${BOLD}${EPIC_ID}${NC}"
    echo -e "  Epic start: $(is_epic_start && echo -e "${GREEN}Yes (first story)${NC}" || echo "No")"
    echo -e "  Epic end:   $(is_epic_end && echo -e "${GREEN}Yes (last story)${NC}" || echo "No")"
    [[ "$DRY_RUN" == "true" ]]      && echo -e "  Mode:       ${YELLOW}DRY RUN${NC}"
    [[ "$SKIP_CACHE" == "true" ]]   && echo -e "  Cache:      ${YELLOW}Bypassed (--skip-cache)${NC}"
    [[ "$SKIP_REVIEWS" == "true" ]]  && echo -e "  Reviews:    ${YELLOW}Skipped${NC}"
    [[ "$FAST_REVIEWS" == "true" ]]  && echo -e "  Reviews:    ${YELLOW}Fast (GPT only, triage+fix skipped)${NC}"
    [[ "$SKIP_TEA" == "true" ]]      && echo -e "  TEA:        ${YELLOW}Skipped${NC}"
    [[ "$SKIP_GIT" == "true" ]]      && echo -e "  Git:        ${YELLOW}Disabled (no branch, checkpoint, or squash)${NC}"
    [[ "$NO_TRACES" == "true" ]]     && echo -e "  No traces:  ${YELLOW}Artifacts removed after finalization${NC}"
    [[ "$SAFE_MODE" == "true" ]]     && echo -e "  Safe mode:  ${YELLOW}AI tools will prompt for permissions${NC}"
    [[ -n "$FROM_STEP" ]]            && echo -e "  Resume:     from step ${BOLD}${FROM_STEP}${NC}"
    echo -e "  Artifacts:  ${DIM}${STORY_ARTIFACTS}/${NC}"

    run_pipeline

    print_summary

    # Clean up temp directory on success (individual reviews, step logs, raw pipeline log)
    if [[ -d "$TMP_DIR" && "$TMP_DIR" == *"/.tmp/auto-bmad/"* ]]; then
        rm -rf "$TMP_DIR"
        echo -e "  ${DIM}Temp files cleaned: ${TMP_DIR}${NC}"
    fi

    # --no-traces: remove all pipeline-generated artifacts, keep pipeline report
    if [[ "$NO_TRACES" == "true" ]]; then
        local report_backup=""

        # Preserve pipeline report if it exists
        if [[ -f "$PIPELINE_REPORT" ]]; then
            report_backup="$(mktemp)"
            cp "$PIPELINE_REPORT" "$report_backup"
        fi

        # Remove all pipeline artifacts (guard against empty/dangerous paths)
        if [[ -z "$STORY_ARTIFACTS" || "$STORY_ARTIFACTS" != *"/auto-bmad/"* ]]; then
            log_error "Refusing to rm -rf: STORY_ARTIFACTS path looks invalid: ${STORY_ARTIFACTS}"
            return 1
        fi
        rm -rf "$STORY_ARTIFACTS"

        # Restore pipeline report to impl artifacts root (not nested in removed dir)
        if [[ -n "$report_backup" ]]; then
            mkdir -p "${IMPL_ARTIFACTS}/auto-bmad"
            local final_report="${IMPL_ARTIFACTS}/auto-bmad/pipeline-report--${STORY_SHORT_ID}.md"
            mv "$report_backup" "$final_report"
            echo -e "  ${GREEN}✓${NC} Pipeline report: ${final_report}"
        fi

        echo -e "  ${DIM}Pipeline artifacts removed (--no-traces)${NC}"
    fi
}

main "$@"
