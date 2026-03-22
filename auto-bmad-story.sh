#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# auto-bmad.sh — Shell-Based BMAD Story Pipeline
#
# Automates one story at a time through the full BMAD
# implementation workflow, using multiple AI CLIs for diversity.
#
# Usage: ./auto-bmad.sh [options]
#   --story STORY_ID     Override auto-detection
#   --from-step ID       Resume pipeline from step ID (e.g., 2a1, 7c)
#   --dry-run            Preview all steps without executing
#   --skip-epic-phases   Skip phases 0 and 6 even at epic boundaries
#   --json-log           Extract arbiter findings into review-log.json
#   --no-traces          Remove all pipeline artifacts after finalization
#   --help               Show usage
# ============================================================

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
BMAD_BUILD_TEA_VERSION="1.7.1"

# ============================================================
# CLI Tools
# ============================================================

TOOL_NAMES=(claude codex gemini opencode)

# ============================================================
# AI Profiles — reusable combinations of cli|model|effort
# ============================================================
# Format: "cli|model|effort"
#
# Effort flags:  claude:   --effort (low|medium|high|max)
#                codex:    -c model_reasoning_effort= (minimal|low|medium|high|xhigh)
#                opencode: --variant (low|medium|high|max)
#                gemini:   no effort flag available

AI_OPUS="claude|opus|max"                           # Claude Opus 4.6 — critical path, arbiters
AI_SONNET="claude|sonnet|high"                       # Claude Sonnet 4.6 — lightweight bookkeeping
AI_GPT="codex|gpt-5.4|xhigh"                       # Codex GPT 5.4 — mechanical steps, reviews
AI_GEMINI="gemini|gemini-3-pro-preview|"             # Gemini 3 Pro — parallel reviews
AI_MINIMAX="opencode|opencode/minimax-m2.5-free|max" # MiniMax M2.5 via OpenCode — parallel reviews
AI_MIMO="opencode|opencode/mimo-v2-pro-free|max"     # MiMo V2 Pro via OpenCode — parallel reviews

# ============================================================
# Step Configuration — assign AI profile per step
# ============================================================

step_config() {
    case "$1" in
        # Parallel review AIs (a=GPT, b=Gemini, c=MiniMax, d=MiMo)
        2a|3a|6a|7a)                 echo "$AI_GPT" ;;
        2b|3b|6b|7b)                 echo "$AI_GEMINI" ;;
        2c|3c|6c|7c)                 echo "$AI_MINIMAX" ;;
        2d|3d|6d|7d)                 echo "$AI_MIMO" ;;
        # Arbiters and critical path
        2e|3e|6e|8)                  echo "$AI_OPUS" ;;
        # Epic end parallel
        11a)                         echo "$AI_GPT" ;;
        11c)                         echo "$AI_GEMINI" ;;
        # Finalization — bookkeeping
        14b)                         echo "$AI_SONNET" ;;
        # Traceability & automation — structured, mechanical
        9|10)                        echo "$AI_SONNET" ;;
        # Everything else: Opus
        0|1|4|5|11b|12|13|14a)      echo "$AI_OPUS" ;;
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
STORY_ARTIFACTS=""
PIPELINE_LOG=""
CURRENT_STEP_LOG=""
METRICS_FILE=""
COMMIT_BASELINE=""  # SHA before pipeline — used for final squash
DRY_RUN=false
FROM_STEP=""
SKIP_EPIC_PHASES=false
SKIP_TEA=false
JSON_LOG=false
NO_TRACES=false
PIPELINE_START_TIME=""

# Step ordering for --from-step comparison
STEP_ORDER="0 1 2a 2b 2c 2d 2e 3a 3b 3c 3d 3e 4 5 6a 6b 6c 6d 6e 7a 7b 7c 7d 8 9 10 11a 11b 11c 12 13 14a 14b"

# In-memory step tracking via dynamic variables (bash 3.2 compat)
set_step_status()   { printf -v "track_${1}_status"   '%s' "$2"; }
get_step_status()   { local v="track_${1}_status";   echo "${!v:-skipped}"; }
set_step_duration() { printf -v "track_${1}_duration" '%s' "$2"; }
get_step_duration() { local v="track_${1}_duration"; echo "${!v:-0}"; }
set_step_name()     { printf -v "track_${1}_name"     '%s' "$2"; }
get_step_name()     { local v="track_${1}_name";     echo "${!v:-$1}"; }
set_step_start()    { printf -v "track_${1}_start"    '%s' "$2"; }
get_step_start()    { local v="track_${1}_start";    echo "${!v:-$2}"; }

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
}

log_step() {
    local step_id="$1" step_name="$2"
    parse_step_config "$step_id"
    local detail="${cfg_cli}"
    [[ -n "$cfg_model" ]] && detail="${detail}/${cfg_model}"
    [[ -n "$cfg_effort" ]] && detail="${detail}/${cfg_effort}"
    echo ""
    echo -e "${BOLD}${BLUE}>>> Step ${step_id}: ${step_name}${NC}  ${DIM}[${detail}]${NC}"
}

log_ok()   { echo -e "${GREEN}  ✓ $1${NC}"; }
log_warn() { echo -e "${YELLOW}  ! $1${NC}"; }
log_error(){ echo -e "${RED}  ✗ $1${NC}"; }
log_skip() { echo -e "${DIM}  — Skipped: $1${NC}"; }

log_dry() {
    local step_id="$1" step_name="$2"
    parse_step_config "$step_id"
    echo -e "  ${DIM}[DRY RUN]${NC} Step ${BOLD}${step_id}${NC} — ${step_name}"
    echo -e "    CLI: ${cfg_cli:-shell}  Model: ${cfg_model:-n/a}  Effort: ${cfg_effort:-n/a}"
}

format_duration() {
    local s="$1"
    if (( s >= 3600 )); then
        printf '%dh %dm %ds' $((s/3600)) $((s%3600/60)) $((s%60))
    elif (( s >= 60 )); then
        printf '%dm %ds' $((s/60)) $((s%60))
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
git_checkpoint() {
    local phase_label="$1"
    [[ "$DRY_RUN" == "true" ]] && return 0

    if git -C "$PROJECT_ROOT" diff --quiet && git -C "$PROJECT_ROOT" diff --cached --quiet && \
       [[ -z "$(git -C "$PROJECT_ROOT" ls-files --others --exclude-standard)" ]]; then
        return 0  # nothing to commit
    fi

    git -C "$PROJECT_ROOT" add -A
    git -C "$PROJECT_ROOT" commit -m "wip(${STORY_SHORT_ID}): ${phase_label}" --no-verify --quiet
}

# Squash all checkpoint commits made since COMMIT_BASELINE into a single commit.
# The final commit message is extracted from the story file (Auto-bmad Completion section)
# or falls back to a descriptive conventional-commit message.
git_squash_pipeline() {
    [[ "$DRY_RUN" == "true" ]] && return 0

    local current_head
    current_head="$(git -C "$PROJECT_ROOT" rev-parse HEAD 2>/dev/null)"

    # Nothing to squash if HEAD hasn't moved
    if [[ "$current_head" == "$COMMIT_BASELINE" ]]; then
        return 0
    fi

    # Try to extract the commit message from the story file.
    # The tech-writer writes a conventional-commit message inside a ``` block
    # in the "Auto-bmad Completion" section.
    local commit_msg=""
    if [[ -n "$STORY_FILE_PATH" && -f "$STORY_FILE_PATH" ]]; then
        commit_msg="$(sed -n '/## Auto-bmad Completion/,/^## /{ /^```/,/^```/{ /^```/d; p; }; }' "$STORY_FILE_PATH" 2>/dev/null | head -5)"
    fi

    # Fallback: derive a readable description from the story slug
    if [[ -z "$commit_msg" ]]; then
        # "1-1-monorepo-devcontainer-setup" → "monorepo devcontainer setup"
        local slug="${STORY_ID#*-*-}"          # strip "1-1-" prefix
        local description="${slug//-/ }"       # hyphens → spaces
        commit_msg="feat(${STORY_SHORT_ID}): ${description}"
    fi

    git -C "$PROJECT_ROOT" reset --soft "$COMMIT_BASELINE"
    git -C "$PROJECT_ROOT" commit -m "$commit_msg" --no-verify --quiet
    log_ok "Squashed pipeline commits into single commit"
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
            local cmd=(claude -p "$prompt" --model "$cfg_model" --dangerously-skip-permissions)
            [[ -n "$cfg_effort" ]] && cmd+=(--effort "$cfg_effort")
            "${cmd[@]}" 2>&1 | tee -a "$CURRENT_STEP_LOG" > /dev/null || true
            exit_code=${PIPESTATUS[0]}
            ;;
        codex)
            local cprompt; cprompt="$(codex_prompt "$prompt")"
            local cmd=(codex exec "$cprompt" -m "$cfg_model" --full-auto)
            [[ -n "$cfg_effort" ]] && cmd+=(-c "model_reasoning_effort=${cfg_effort}")
            "${cmd[@]}" 2>&1 | tee -a "$CURRENT_STEP_LOG" > /dev/null || true
            exit_code=${PIPESTATUS[0]}
            ;;
        gemini)
            gemini -p "$prompt" -m "$cfg_model" --yolo 2>&1 | tee -a "$CURRENT_STEP_LOG" > /dev/null || true
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
# Generic Review & Arbiter Functions
# ============================================================

# run_review_step <step_id> <file_prefix> <ai_suffix>
# Dispatches the appropriate slash command based on file_prefix
run_review_step() {
    local step_id="$1" file_prefix="$2" ai_suffix="$3"
    local f="${STORY_ARTIFACTS}/${STORY_SHORT_ID}--${step_id}-${file_prefix}-${ai_suffix}.md"
    local prompt
    case "$file_prefix" in
        validate)
            prompt="/bmad-create-story yolo - validate story ${STORY_ID}. Do not fix anything or edit any source files. Just report all issues, recommendations and optimizations and save them to ${f}" ;;
        adversarial)
            prompt="/bmad-review-adversarial-general yolo - review the story ${STORY_ID} specification. Do not fix anything or edit any source files. Just report all findings and save them to ${f}" ;;
        edge-cases)
            prompt="/bmad-review-edge-case-hunter yolo - files changed in story ${STORY_ID}. Do not fix anything or edit any source files. Just report all edge case findings and save them to ${f}" ;;
        review)
            prompt="/bmad-code-review yolo - story ${STORY_ID} - do not fix anything or edit any files. Just report back all critical, high, medium, and low issues and save them to ${f}" ;;
    esac
    run_ai "$step_id" "$prompt"
}

# run_arbiter <step_id> <file_prefix> <fix_instruction> [consensus_rules] [agent_cmd]
# agent_cmd: optional slash command prefix (e.g., "/bmad-dev yolo -")
run_arbiter() {
    local step_id="$1" file_prefix="$2" fix_instruction="$3"
    local consensus_rules="${4:-}"
    local agent_cmd="${5:-}"

    if [[ -z "$consensus_rules" ]]; then
        consensus_rules="- Unanimous (4/4 agree): fix immediately, high confidence
- Strong consensus (3/4 agree): fix, good confidence
- Split (2/4 agree): evaluate the arguments from both sides, fix if the issue is substantive
- Single flag (1/4): only fix if it's clearly a real issue with a concrete impact, skip speculative or hypothetical concerns"
    fi

    # Derive reviewer step base from arbiter step_id
    local review_base
    case "$step_id" in
        *e) review_base="${step_id%e}" ;;
        8)  review_base="7" ;;
        *)  review_base="${step_id}" ;;
    esac

    local prompt_prefix=""
    [[ -n "$agent_cmd" ]] && prompt_prefix="${agent_cmd} "

    local arbiter_report="${STORY_ARTIFACTS}/${STORY_SHORT_ID}--${step_id}-arbiter-${file_prefix}.md"

    run_ai "$step_id" "${prompt_prefix}Read these review findings files (skip any that don't exist):
- ${STORY_ARTIFACTS}/${STORY_SHORT_ID}--${review_base}a-${file_prefix}-gpt.md
- ${STORY_ARTIFACTS}/${STORY_SHORT_ID}--${review_base}b-${file_prefix}-gemini.md
- ${STORY_ARTIFACTS}/${STORY_SHORT_ID}--${review_base}c-${file_prefix}-minimax.md
- ${STORY_ARTIFACTS}/${STORY_SHORT_ID}--${review_base}d-${file_prefix}-mimo.md

You are the arbiter. Cross-reference all findings using these rules:
${consensus_rules}

${fix_instruction}

Save your arbiter decision report to ${arbiter_report} with this structure:

1. **Header**: story ID, arbiter step, timestamp

2. **Decision summary table** (markdown) — one row per finding for quick scanning:

| # | Finding | Flagged By | Consensus | Action | Confidence |
|---|---------|------------|-----------|--------|------------|
| 1 | Brief description | GPT, Gemini, MiniMax | 3/4 | Fixed | High |
| 2 | Brief description | MiMo | 1/4 | Skipped | Low |

3. **Detailed rationale** — for each finding in the table, a short paragraph with:
   - The reviewers' arguments (agreements and disagreements)
   - Your reasoning for fixing or skipping
   - What was changed (if fixed)

4. **Summary**: total findings reviewed, fixes applied, items skipped, and any patterns or observations worth noting for future runs"

    # Extract JSON log from arbiter report if --json-log is enabled
    if [[ "$JSON_LOG" == "true" ]]; then
        extract_arbiter_json "$arbiter_report" "$step_id" "$file_prefix"
    fi
}

# extract_arbiter_json <report_file> <step_id> <review_type>
# Parses the arbiter's markdown decision table into JSON and appends to review-log.json
extract_arbiter_json() {
    local report="$1" step_id="$2" review_type="$3"
    local json_log="${STORY_ARTIFACTS}/review-log.json"

    [[ -f "$report" ]] || return 0

    # Parse markdown table rows: | # | Finding | Flagged By | Consensus | Action | Confidence |
    local findings_json
    findings_json=$(awk -F'|' '
    /^\| *[0-9]/ {
        for (i=2; i<=7; i++) {
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", $i)
            gsub(/"/, "\\\"", $i)
        }
        printf "{\"n\":%s,\"finding\":\"%s\",\"flagged_by\":\"%s\",\"consensus\":\"%s\",\"action\":\"%s\",\"confidence\":\"%s\"}\n", $2, $3, $4, $5, $6, $7
    }' "$report" 2>/dev/null)

    # Skip if no findings rows parsed
    [[ -z "$findings_json" ]] && return 0

    # Build entry — use jq if available, else construct manually
    local entry
    if command -v jq &>/dev/null; then
        entry=$(echo "$findings_json" | jq -s \
            --arg story "$STORY_ID" \
            --arg step "$step_id" \
            --arg type "$review_type" \
            --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
            '{story: $story, step: $step, review_type: $type, timestamp: $ts,
              total: length,
              fixed: [.[] | select(.action | test("fix";"i"))] | length,
              skipped: [.[] | select(.action | test("skip";"i"))] | length,
              verdict: (if ([.[] | select(.action | test("fix";"i"))] | length) > 0 then "changes_made" else "clean_pass" end),
              findings: .}')
    else
        # Fallback: raw JSONL without aggregation
        local count; count=$(echo "$findings_json" | wc -l | tr -d ' ')
        entry=$(printf '{"story":"%s","step":"%s","review_type":"%s","timestamp":"%s","total":%s,"findings":[%s]}' \
            "$STORY_ID" "$step_id" "$review_type" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
            "$count" "$(echo "$findings_json" | paste -sd, -)")
    fi

    # Append entry to the log (one JSON object per line — JSONL format)
    echo "$entry" >> "$json_log"
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
# Pre-flight Checks
# ============================================================

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
        echo -en "    Continue without TEA steps (0, 4, 9, 10, 11a-c)? [y/N] "
        read -r answer
        if [[ "$answer" =~ ^[Yy]$ ]]; then
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
    echo -en "    Continue anyway? [y/N] "
    read -r answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        log_warn "Proceeding with mismatched versions"
    else
        log_error "Aborted. Update BMad/modules or rebuild this script for the installed versions."
        exit 1
    fi
}

# Ensure we're on the correct story branch, or create one from main.
# Called after STORY_ID is known.
check_git_branch() {
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
            echo -en "    Continue on ${current_branch} anyway? [y/N] "
            read -r answer
            if [[ ! "$answer" =~ ^[Yy]$ ]]; then
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
    echo -en "    Continue on ${current_branch} anyway? [y/N] "
    read -r answer
    if [[ ! "$answer" =~ ^[Yy]$ ]]; then
        exit 1
    fi
}

preflight_checks() {
    local errors=0

    echo -e "${BOLD}Pre-flight checks${NC}"

    check_bmad_version

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

    if (( errors > 0 )); then
        echo ""
        log_error "${errors} pre-flight check(s) failed. Aborting."
        exit 1
    fi
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

    local from_pos=-1 step_pos=-1 pos=0
    for s in $STEP_ORDER; do
        [[ "$s" == "$FROM_STEP" ]] && from_pos=$pos
        [[ "$s" == "$step_id" ]] && step_pos=$pos
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

    # Per-step raw output log (deleted on success, kept on failure)
    CURRENT_STEP_LOG="${STORY_ARTIFACTS}/step-${step_id}.log"
    : > "$CURRENT_STEP_LOG"

    local start_time; start_time=$(date +%s)

    start_activity_monitor "$step_name"

    if "$@"; then
        stop_activity_monitor
        local end_time; end_time=$(date +%s)
        local duration=$((end_time - start_time))
        set_step_duration "$step_id" "$duration"
        set_step_status "$step_id" "ok"
        printf "  %-6s  %-8s  %-10s  %s\n" "$step_id" "$(format_duration $duration)" "ok" "$step_name" >> "$PIPELINE_LOG"
        rm -f "$CURRENT_STEP_LOG"
        log_ok "Completed in $(format_duration $duration)"
    else
        stop_activity_monitor
        local end_time; end_time=$(date +%s)
        local duration=$((end_time - start_time))
        set_step_duration "$step_id" "$duration"
        set_step_status "$step_id" "FAILED"
        printf "  %-6s  %-8s  %-10s  %s\n" "$step_id" "$(format_duration $duration)" "FAILED" "$step_name" >> "$PIPELINE_LOG"
        log_error "Step ${step_id} (${step_name}) FAILED after $(format_duration $duration)"
        log_error "Step log: ${CURRENT_STEP_LOG}"
        log_error "Resume: ./auto-bmad.sh --from-step ${step_id} --story ${STORY_ID}"
        exit 1
    fi
}

# Run parallel review steps. Failures are warnings, not fatal.
# Entry format: "step_id|name|file_prefix|ai_suffix" for review steps
#            or "step_id|name|func_name" for arbitrary functions
run_parallel_reviews() {
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

        # Each parallel step gets its own raw output log
        CURRENT_STEP_LOG="${STORY_ARTIFACTS}/step-${sid}.log"
        : > "$CURRENT_STEP_LOG"

        # Suppress terminal output — log file still gets full output via tee.
        if [[ -n "$field4" ]]; then
            run_review_step "$sid" "$field3" "$field4" >/dev/null &
        else
            "$field3" >/dev/null &
        fi
        pids+=($!)
        sids+=("$sid")
        snames+=("$sname")
        count=$((count + 1))
    done

    if [[ "$DRY_RUN" == "true" || $count -eq 0 ]]; then
        return 0
    fi

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

    local running=$count
    local spinner_idx=0

    while (( running > 0 )); do
        # Poll each background process
        for ((i=0; i<count; i++)); do
            [[ "${statuses[$i]}" != "running" ]] && continue
            if ! kill -0 "${pids[$i]}" 2>/dev/null; then
                local now; now=$(date +%s)
                local t0; t0=$(get_step_start "${sids[$i]}" "$now")
                local dur=$((now - t0))
                durations[$i]="$dur"
                set_step_duration "${sids[$i]}" "$dur"
                local step_log="${STORY_ARTIFACTS}/step-${sids[$i]}.log"
                if wait "${pids[$i]}" 2>/dev/null; then
                    statuses[$i]="ok"
                    set_step_status "${sids[$i]}" "ok"
                    printf "  %-6s  %-8s  %-10s  %s\n" "${sids[$i]}" "$(format_duration $dur)" "ok" "${snames[$i]}" >> "$PIPELINE_LOG"
                    rm -f "$step_log"
                else
                    statuses[$i]="FAILED"
                    set_step_status "${sids[$i]}" "FAILED"
                    printf "  %-6s  %-8s  %-10s  %s\n" "${sids[$i]}" "$(format_duration $dur)" "FAILED" "${snames[$i]}" >> "$PIPELINE_LOG"
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
                    local t0; t0=$(get_step_start "${sids[$i]}" "$(date +%s)")
                    local elapsed=$(( $(date +%s) - t0 ))
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

step_0_test_design() {
    run_ai "0" "/bmad-testarch-test-design yolo - run in epic-level mode for epic ${EPIC_ID}"
}

# --- Phase 1: Story Preparation ---

step_1_create_story() {
    run_ai "1" "/bmad-create-story yolo - story ${STORY_ID}"
    detect_story_file_path
    if [[ -n "$STORY_FILE_PATH" ]]; then
        log_ok "Story file: ${STORY_FILE_PATH}"
    else
        log_warn "Could not detect story file path — will retry before finalization"
    fi
}

# --- Phase 2: TDD + Implementation ---

step_4_tdd_red() {
    run_ai "4" "/bmad-testarch-atdd yolo - story ${STORY_ID} - Your scope is strictly TDD red phase: generate failing acceptance tests ONLY. Do not implement, create or modify any production code, API routes, UI components, database schemas, or application logic"
}

step_5_implementation() {
    run_ai "5" "/bmad-dev-story yolo - ${STORY_ID}"
}

# --- Phase 5: Traceability & Automation ---

step_9_trace() {
    run_ai "9" "/bmad-testarch-trace yolo - story ${STORY_ID}"
}

step_10_automate() {
    run_ai "10" "/bmad-testarch-automate yolo - story ${STORY_ID}"
}

# --- Phase 6: Epic End ---

step_11a_epic_trace() {
    run_ai "11a" "/bmad-testarch-trace yolo - run in epic-level mode for epic ${EPIC_ID}"
}

step_11b_epic_nfr() {
    run_ai "11b" "/bmad-testarch-nfr yolo - run in epic-level mode for epic ${EPIC_ID}"
}

step_11c_epic_test_review() {
    run_ai "11c" "/bmad-testarch-test-review yolo - run in epic-level mode for epic ${EPIC_ID}"
}

step_12_retrospective() {
    run_ai "12" "/bmad-retrospective yolo - epic ${EPIC_ID}"
}

step_13_project_context() {
    run_ai "13" "/bmad-generate-project-context yolo - if a project context file already exists, update it"
}

# --- Pipeline Metrics ---

generate_pipeline_metrics() {
    local metrics_file="${STORY_ARTIFACTS}/${STORY_SHORT_ID}--pipeline-metrics.md"
    local total_compute=0
    local steps_ok=0 steps_failed=0

    {
        echo "# Pipeline Metrics — ${STORY_ID}"
        echo ""
        echo "Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo ""
        echo "| Step | Name | CLI / Model | Duration | Status |"
        echo "|------|------|-------------|----------|--------|"

        for sid in $STEP_ORDER; do
            local status; status="$(get_step_status "$sid")"
            [[ "$status" == "skipped" || "$status" == "dry-run" ]] && continue

            local duration; duration="$(get_step_duration "$sid")"
            local name; name="$(get_step_name "$sid")"
            parse_step_config "$sid"
            local model_info="${cfg_cli}"
            [[ -n "$cfg_model" ]] && model_info="${model_info} / ${cfg_model}"

            local dur_str="—"
            if [[ "$duration" != "0" ]]; then
                dur_str="$(format_duration "$duration")"
                total_compute=$((total_compute + duration))
            fi

            [[ "$status" == "ok" ]] && steps_ok=$((steps_ok + 1))
            [[ "$status" == "FAILED" ]] && steps_failed=$((steps_failed + 1))

            echo "| ${sid} | ${name} | ${model_info} | ${dur_str} | ${status} |"
        done

        local wall_time=$(( $(date +%s) - PIPELINE_START_TIME ))
        local savings=$((total_compute - wall_time))
        (( savings < 0 )) && savings=0

        echo ""
        echo "## Timing"
        echo ""
        echo "- **Wall time:** $(format_duration $wall_time)"
        echo "- **Compute time:** $(format_duration $total_compute) (sum of step durations)"
        echo "- **Parallelism savings:** $(format_duration $savings)"
        echo "- **Steps completed:** ${steps_ok}"
        (( steps_failed > 0 )) && echo "- **Steps failed:** ${steps_failed}"

        echo ""
        echo "## Git Changes"
        echo ""
        echo '```'
        if [[ -n "$COMMIT_BASELINE" ]]; then
            git -C "$PROJECT_ROOT" diff --stat "$COMMIT_BASELINE" HEAD 2>/dev/null || echo "(no changes)"
        else
            git -C "$PROJECT_ROOT" diff --stat 2>/dev/null || echo "(no uncommitted changes)"
        fi
        echo '```'

    } > "$metrics_file"

    echo "$metrics_file"
}

# --- Phase 7: Finalization ---

step_14a_document() {
    if [[ -z "$STORY_FILE_PATH" ]]; then
        detect_story_file_path
    fi

    local story_ref="${STORY_FILE_PATH:-the story file for ${STORY_ID}}"
    local metrics_ref="${METRICS_FILE:-${STORY_ARTIFACTS}/${STORY_SHORT_ID}--pipeline-metrics.md}"
    run_ai "14a" "/bmad-tech-writer yolo - Finalize documentation for story ${STORY_ID}. The story file is at: ${story_ref}

Perform ALL of the following:

1. Read the story file and verify all sections that previous pipeline steps should have populated are present and up to date:
   - Status should be 'review' or later (not 'in-progress' or 'ready-for-dev')
   - All Tasks/Subtasks should be checked [x] (flag any that are unchecked)
   - Dev Agent Record: Agent Model Used, Completion Notes List, and Debug Log References should all be populated
   - File List must reflect ALL files created, modified, or deleted across the entire pipeline (not just implementation — check git status for any files the arbiters touched that are not listed)
   - Change Log must include entries for arbiter fixes from edge case and code review steps (if those steps ran)
   Fix anything that is missing or incomplete.

2. Add an '## Auto-bmad Pipeline Artifacts' section after the Dev Agent Record. This is a reference index ONLY — do not duplicate content already in the Dev Agent Record, Change Log, or the artifacts themselves. List each artifact file with a one-line outcome (pass/fail/N findings). Skip any that don't exist:
   - Validation reports: ${STORY_ARTIFACTS}/${STORY_SHORT_ID}--2{a,b,c,d}-validate-*.md
   - Validation arbiter: ${STORY_ARTIFACTS}/${STORY_SHORT_ID}--2e-arbiter-validate.md
   - Adversarial reports: ${STORY_ARTIFACTS}/${STORY_SHORT_ID}--3{a,b,c,d}-adversarial-*.md
   - Adversarial arbiter: ${STORY_ARTIFACTS}/${STORY_SHORT_ID}--3e-arbiter-adversarial.md
   - Edge case reports: ${STORY_ARTIFACTS}/${STORY_SHORT_ID}--6{a,b,c,d}-edge-cases-*.md
   - Edge case arbiter: ${STORY_ARTIFACTS}/${STORY_SHORT_ID}--6e-arbiter-edge-cases.md
   - Code reviews: ${STORY_ARTIFACTS}/${STORY_SHORT_ID}--7{a,b,c,d}-review-*.md
   - Code review arbiter: ${STORY_ARTIFACTS}/${STORY_SHORT_ID}--8-arbiter-review.md
   - Traceability: ${STORY_ARTIFACTS}/${STORY_SHORT_ID}--9-*.md
   - Test automation: ${STORY_ARTIFACTS}/${STORY_SHORT_ID}--10-*.md

3. Read the pipeline metrics file at ${metrics_ref} and embed its full contents (the step execution table AND the timing/git summary) into the story file as an '## Auto-bmad Pipeline Metrics' section. Copy the table and summary verbatim — do not summarize or reformat.

4. Add an '## Auto-bmad Completion' section with ONLY information not already captured in the Dev Agent Record or Change Log:
   - Open questions or concerns remaining after implementation
   - Notable decisions taken
   - Learnings from the pipeline run
   - Anything requiring manual testing not covered by automated tests
   - The commit message to use for all changes made in story ${STORY_ID} following Conventional Commits 1.0.0 specifications (<type>(<scope>): <subject> headline format with a <summary> in the body after a blank line) - https://www.conventionalcommits.org/en/v1.0.0/ Type should be one of: build, chore, ci, docs, feat, fix, perf, refactor, revert, style, test.
   Do NOT repeat completion notes, file lists, decision logs, or fix summaries — those are already in the Dev Agent Record and Change Log."
}

step_14b_close() {
    if [[ -z "$STORY_FILE_PATH" ]]; then
        detect_story_file_path
    fi

    local story_ref="${STORY_FILE_PATH:-the story file for ${STORY_ID}}"
    run_ai "14b" "/bmad-sm yolo - Close out story ${STORY_ID}. The story file is at: ${story_ref}

1. Set the story status to done in the story file if not already set.
2. Update _bmad-output/implementation-artifacts/sprint-status.yaml to set the story status to done if not already set."
}

# ============================================================
# Pipeline Orchestrator
# ============================================================

run_pipeline() {
    local story_file_ref="${STORY_FILE_PATH:-the implementation-artifacts directory}"

    # Record baseline commit for final squash
    COMMIT_BASELINE="$(git -C "$PROJECT_ROOT" rev-parse HEAD 2>/dev/null)"

    # --- Phase 0: Epic Start ---
    if is_epic_start && [[ "$SKIP_EPIC_PHASES" == "false" ]]; then
        if [[ "$SKIP_TEA" == "true" ]]; then
            log_skip "Phase 0 — TEA not installed"
        else
            log_phase "0" "Epic Start: Pre-Implementation"
            run_step "0" "TEA Test Design (epic-level)" step_0_test_design
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

    run_step "1" "Create Story" step_1_create_story

    # Step 2: Validate Story (4 AIs in parallel + arbiter)
    run_parallel_reviews \
        "2a|Validate Story (GPT)|validate|gpt" \
        "2b|Validate Story (Gemini)|validate|gemini" \
        "2c|Validate Story (MiniMax)|validate|minimax" \
        "2d|Validate Story (MiMo)|validate|mimo"

    run_step "2e" "Validate Story Arbiter (analyst)" run_arbiter "2e" "validate" \
        "Fix all confirmed issues in the story file at ${story_file_ref}." \
        "" "/bmad-analyst yolo -"

    # Step 3: Adversarial Review (4 AIs in parallel + arbiter)
    run_parallel_reviews \
        "3a|Adversarial Review (GPT)|adversarial|gpt" \
        "3b|Adversarial Review (Gemini)|adversarial|gemini" \
        "3c|Adversarial Review (MiniMax)|adversarial|minimax" \
        "3d|Adversarial Review (MiMo)|adversarial|mimo"

    run_step "3e" "Adversarial Review Arbiter (analyst)" run_arbiter "3e" "adversarial" \
        "Fix all confirmed issues in the story file at ${story_file_ref}." \
        "" "/bmad-analyst yolo -"

    git_checkpoint "phase 1 — story preparation"

    # --- Phase 2: TDD + Implementation ---
    log_phase "2" "TDD + Implementation"

    if [[ "$SKIP_TEA" == "true" ]]; then
        log_skip "Step 4 — TEA not installed"
    else
        run_step "4" "TDD Red Phase" step_4_tdd_red
    fi
    run_step "5" "Implementation" step_5_implementation

    git_checkpoint "phase 2 — implementation"

    # --- Phase 3: Edge Case Hunter (4 AIs in parallel) ---
    log_phase "3" "Edge Cases (4 Hunters)"

    run_parallel_reviews \
        "6a|Edge Cases (GPT)|edge-cases|gpt" \
        "6b|Edge Cases (Gemini)|edge-cases|gemini" \
        "6c|Edge Cases (MiniMax)|edge-cases|minimax" \
        "6d|Edge Cases (MiMo)|edge-cases|mimo"

    run_step "6e" "Edge Case Arbiter (dev)" run_arbiter "6e" "edge-cases" \
        "Fix all confirmed edge cases." \
        "- Unanimous (4/4 agree): fix immediately by adding the suggested guard
- Strong consensus (3/4 agree): fix, good confidence
- Split (2/4 agree): evaluate the arguments from both sides, fix if the edge case has real impact
- Single flag (1/4): only fix if it's a clearly unhandled case with concrete consequences, skip rare hypothetical scenarios" \
        "/bmad-dev yolo -"

    git_checkpoint "phase 3 — edge case fixes"

    # --- Phase 4: Code Review (4 AIs in parallel) ---
    log_phase "4" "Quadruple Code Review"

    run_parallel_reviews \
        "7a|Review (GPT)|review|gpt" \
        "7b|Review (Gemini)|review|gemini" \
        "7c|Review (MiniMax)|review|minimax" \
        "7d|Review (MiMo)|review|mimo"

    run_step "8" "Code Review Arbiter (dev)" run_arbiter "8" "review" \
        "Fix all confirmed critical, high, medium, and low issues." \
        "- Unanimous (4/4 agree): fix immediately, high confidence
- Strong consensus (3/4 agree): fix, good confidence
- Split (2/4 agree): evaluate the arguments from both sides, fix if the issue is substantive
- Single flag (1/4): only fix if it's clearly a real issue with concrete impact (e.g., security vulnerability, data loss, crash), skip stylistic or speculative concerns" \
        "/bmad-dev yolo -"

    git_checkpoint "phase 4 — code review fixes"

    # --- Phase 5: Traceability & Automation ---
    if [[ "$SKIP_TEA" == "true" ]]; then
        log_skip "Phase 5 — TEA not installed"
    else
        log_phase "5" "Traceability & Automation"

        run_step "9" "Testarch Trace" step_9_trace
        run_step "10" "Testarch Automate" step_10_automate
        git_checkpoint "phase 5 — traceability & automation"
    fi

    # --- Phase 6: Epic End ---
    if is_epic_end && [[ "$SKIP_EPIC_PHASES" == "false" ]]; then
        log_phase "6" "Epic End"

        if [[ "$SKIP_TEA" == "true" ]]; then
            log_skip "Steps 11a-c — TEA not installed"
        else
            run_parallel_reviews \
                "11a|Epic Trace|step_11a_epic_trace" \
                "11b|Epic NFR Assessment|step_11b_epic_nfr" \
                "11c|Epic Test Review|step_11c_epic_test_review"
        fi

        run_step "12" "Retrospective" step_12_retrospective
        run_step "13" "Generate Project Context" step_13_project_context
        git_checkpoint "phase 6 — epic end"
    else
        if [[ "$SKIP_EPIC_PHASES" == "true" ]]; then
            log_skip "Phase 6 — --skip-epic-phases"
        elif ! is_epic_end; then
            log_skip "Phase 6 — not last story in epic"
        fi
    fi

    # --- Phase 7: Finalization ---
    log_phase "7" "Finalization"

    # Generate metrics before the tech-writer runs so it can embed them
    if [[ "$DRY_RUN" != "true" ]]; then
        METRICS_FILE="$(generate_pipeline_metrics)"
        log_ok "Pipeline metrics: ${METRICS_FILE}"
    fi

    run_step "14a" "Document Story (tech-writer)" step_14a_document
    run_step "14b" "Close Story (SM)" step_14b_close

    git_checkpoint "phase 7 — finalization"

    # Squash all phase commits into a single commit
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

    printf "  ${BOLD}%-6s %-28s %-12s %-10s${NC}\n" "Step" "Name" "Duration" "Status"
    printf "  %-6s %-28s %-12s %-10s\n" "------" "----------------------------" "------------" "----------"

    for sid in $STEP_ORDER; do
        local status; status="$(get_step_status "$sid")"
        local duration; duration="$(get_step_duration "$sid")"
        local name; name="$(get_step_name "$sid")"

        [[ "$status" == "skipped" ]] && continue

        local dur_str="—"
        [[ "$duration" != "0" ]] && dur_str="$(format_duration "$duration")"

        local status_color=""
        case "$status" in
            ok)       status_color="${GREEN}" ;;
            FAILED)   status_color="${RED}" ;;
            dry-run)  status_color="${DIM}" ;;
            *)        status_color="${NC}" ;;
        esac

        printf "  %-6s %-28s %-12s ${status_color}%-10s${NC}\n" \
            "$sid" "$name" "$dur_str" "$status"
    done

    echo ""
    echo -e "  ${BOLD}Total: $(format_duration $total_duration)${NC}"

    if [[ "$DRY_RUN" != "true" ]]; then
        echo ""
        local final_sha
        final_sha="$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null)"
        echo -e "  ${GREEN}✓${NC} All changes committed: ${BOLD}${final_sha}${NC}"
        echo -e "  ${DIM}Commit message sourced from the story file Auto-bmad Completion section.${NC}"
    fi

    echo ""
}

# ============================================================
# CLI Argument Parsing & Main
# ============================================================

show_help() {
    cat <<HELPEOF
auto-bmad.sh — BMAD Story Pipeline Orchestrator

Automates one story at a time through the full BMAD implementation
workflow using multiple AI CLIs (claude, codex, gemini, opencode).

Usage: ./auto-bmad.sh [options]

Options:
  --story STORY_ID       Override auto-detection of next story
  --from-step STEP_ID    Resume pipeline from a specific step
                         Valid IDs: ${STEP_ORDER}
  --dry-run              Preview all steps without executing
  --skip-epic-phases     Skip phases 0 (epic start) and 6 (epic end)
  --json-log             Extract arbiter findings into review-log.json (JSONL)
  --no-traces            Remove all pipeline artifacts after finalization
                         (implies --json-log; JSON log is kept)
  --help                 Show this help message

AI Profiles (edit at top of script):
  AI_OPUS    = Claude Opus 4.6 / max effort   — critical path + arbiters
  AI_SONNET  = Claude Sonnet 4.6 / high       — lightweight bookkeeping
  AI_GPT     = Codex GPT 5.4 / xhigh reason  — mechanical steps + reviews
  AI_GEMINI  = Gemini 3 Pro Preview           — parallel reviews
  AI_MINIMAX = OpenCode MiniMax M2.5 / max    — parallel reviews
  AI_MIMO    = OpenCode MiMo V2 Pro / max     — parallel reviews

Examples:
  ./auto-bmad.sh                          # Run next story
  ./auto-bmad.sh --dry-run                # Preview the pipeline
  ./auto-bmad.sh --story 2-3-some-story   # Run a specific story
  ./auto-bmad.sh --from-step 6a --story 1-1-auth  # Resume from step 6a
HELPEOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run)        DRY_RUN=true; shift ;;
            --from-step)      FROM_STEP="$2"; shift 2 ;;
            --story)          STORY_ID="$2"; shift 2 ;;
            --skip-epic-phases) SKIP_EPIC_PHASES=true; shift ;;
            --json-log)       JSON_LOG=true; shift ;;
            --no-traces)      NO_TRACES=true; JSON_LOG=true; shift ;;
            --help|-h)        show_help; exit 0 ;;
            *)
                log_error "Unknown argument: $1"
                echo ""
                show_help
                exit 1
                ;;
        esac
    done
}

main() {
    trap 'stop_activity_monitor 2>/dev/null || true' EXIT
    parse_args "$@"

    preflight_checks

    if [[ -z "$STORY_ID" ]]; then
        detect_next_story
    fi
    extract_epic_id
    extract_short_id

    check_git_branch

    STORY_ARTIFACTS="${IMPL_ARTIFACTS}/auto-bmad/${STORY_SHORT_ID}"
    PIPELINE_LOG="${STORY_ARTIFACTS}/pipeline.log"
    mkdir -p "$STORY_ARTIFACTS"

    # Initialize summary log (lightweight — full output goes to per-step logs)
    printf "# Pipeline Summary — %s\n# Started: %s\n# %-6s  %-8s  %-10s  %s\n" \
        "$STORY_ID" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        "Step" "Duration" "Status" "Detail" \
        > "$PIPELINE_LOG"

    PIPELINE_START_TIME=$(date +%s)

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
    [[ "$DRY_RUN" == "true" ]] && echo -e "  Mode:       ${YELLOW}DRY RUN${NC}"
    [[ "$JSON_LOG" == "true" ]] && echo -e "  JSON log:   ${GREEN}Enabled${NC}"
    [[ "$NO_TRACES" == "true" ]] && echo -e "  No traces:  ${YELLOW}Pipeline artifacts will be removed${NC}"
    [[ "$SKIP_TEA" == "true" ]] && echo -e "  TEA:        ${YELLOW}Skipped (not installed)${NC}"
    [[ -n "$FROM_STEP" ]] && echo -e "  Resume:     from step ${BOLD}${FROM_STEP}${NC}"
    echo -e "  Artifacts:  ${DIM}${STORY_ARTIFACTS}/${NC}"

    run_pipeline

    print_summary

    # Step logs are kept only on failure — clean up any stragglers on success
    rm -f "${STORY_ARTIFACTS}"/step-*.log 2>/dev/null || true

    # --no-traces: remove all pipeline-generated artifacts, keep only the JSON log
    if [[ "$NO_TRACES" == "true" ]]; then
        local json_log="${STORY_ARTIFACTS}/review-log.json"
        local json_backup=""

        # Preserve the JSON log if it exists
        if [[ -f "$json_log" ]]; then
            json_backup="$(mktemp)"
            cp "$json_log" "$json_backup"
        fi

        # Remove all pipeline artifacts
        rm -rf "$STORY_ARTIFACTS"

        # Restore JSON log to impl artifacts root (not nested in removed dir)
        if [[ -n "$json_backup" ]]; then
            local final_log="${IMPL_ARTIFACTS}/auto-bmad/review-log--${STORY_SHORT_ID}.json"
            mkdir -p "$(dirname "$final_log")"
            mv "$json_backup" "$final_log"
            echo -e "  ${GREEN}✓${NC} Review log: ${final_log}"
        fi

        echo -e "  ${DIM}Pipeline artifacts removed (--no-traces)${NC}"
    fi
}

main "$@"
