#!/usr/bin/env bash
# lib/cli.sh — AI CLI abstraction layer and model availability checks
# Sourced by auto-bmad-story
#
# Requires: lib/core.sh, lib/config.sh sourced (parse_step_config)
# Reads globals: CURRENT_STEP_LOG TMP_DIR STORY_ID COMMIT_BASELINE
#
# Exports:
#   codex_prompt <prompt>              — convert /slash to $slash for codex
#   run_ai <step_id> <prompt>          — invoke AI CLI for a step
#   run_review_step <id> <prefix> <suffix> — dispatch review slash command
#   check_model_availability           — parallel model availability check
#   _check_claude_model _check_codex_model _check_copilot_model _check_opencode_model

[[ -n "${_CLI_SH_LOADED:-}" ]] && return 0
_CLI_SH_LOADED=1

# Load and interpolate a prompt template from prompts/ directory.
# Usage: load_prompt "1.3-spec-triage.md" KEY1 "value1" KEY2 "value2"
# Replaces all {{KEY}} placeholders with corresponding values.
load_prompt() {
    local template="${INSTALL_DIR}/prompts/$1"
    if [[ ! -f "$template" ]]; then
        log_error "Prompt template not found: ${template}"
        return 1
    fi
    local content
    content="$(<"$template")"
    shift
    while [[ $# -ge 2 ]]; do
        content="${content//\{\{$1\}\}/$2}"
        shift 2
    done
    # Safety check: warn about any remaining unreplaced placeholders
    local leftover
    leftover=$(echo "$content" | grep -oE '\{\{[A-Z_]+\}\}' | sort -u | head -5) || true
    if [[ -n "$leftover" ]]; then
        log_warn "Unreplaced placeholders in ${template##*/}: $(echo "$leftover" | tr '\n' ' ')"
    fi
    echo "$content"
}

# Codex requires `$` instead of `/` for the leading slash command
codex_prompt() {
    local p="$1"
    [[ "$p" == /* ]] && p="\$${p:1}"
    echo "$p"
}

# run_ai <step_id> <prompt>
# When called from _run_with_retry, cfg_* globals are pre-set — skip re-parsing.
_RETRY_PROFILE_ACTIVE=false
run_ai() {
    local step_id="$1"
    local prompt="$2"
    [[ "$_RETRY_PROFILE_ACTIVE" != true ]] && parse_step_config "$step_id"

    # Write step header to per-step log
    {
        echo ""
        echo "═══ Step ${step_id} ═══════════════════════════════════════════"
        echo "CLI: ${cfg_cli} | Model: ${cfg_model} | Effort: ${cfg_effort:-n/a}"
        echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo "Prompt:"
        echo "$prompt"
        echo "───────────────────────────────────────────────────────────────"
    } >> "$CURRENT_STEP_LOG"

    # Raw JSON output file (used when HAS_JQ=true for usage tracking)
    local raw_json="${TMP_DIR}/step-${step_id}-raw.json"

    local exit_code=0
    if [[ "$HAS_JQ" == true ]]; then
        # --- JSON mode: capture structured output for usage extraction ---
        case "$cfg_cli" in
            claude)
                local cmd=(claude -p "$prompt" --model "$cfg_model" --dangerously-skip-permissions --output-format json)
                [[ -n "$cfg_effort" ]] && cmd+=(--effort "$cfg_effort")
                "${cmd[@]}" > "$raw_json" 2>&1 && exit_code=0 || exit_code=$?
                ;;
            codex)
                local cprompt; cprompt="$(codex_prompt "$prompt")"
                local cmd=(codex exec "$cprompt" -m "$cfg_model" --full-auto --json)
                [[ -n "$cfg_effort" ]] && cmd+=(-c "model_reasoning_effort=${cfg_effort}")
                "${cmd[@]}" > "$raw_json" 2>&1 && exit_code=0 || exit_code=$?
                ;;
            copilot)
                local cmd=(copilot -p "$prompt" --model "$cfg_model" --yolo --output-format json)
                if [[ -n "$cfg_effort" ]]; then
                    local eff="$cfg_effort"
                    [[ "$eff" == "max" ]] && eff="xhigh"
                    cmd+=(--effort "$eff")
                fi
                "${cmd[@]}" > "$raw_json" 2>&1 && exit_code=0 || exit_code=$?
                ;;
            opencode)
                local cmd=(opencode run "$prompt" -m "$cfg_model" --format json)
                [[ -n "$cfg_effort" ]] && cmd+=(--variant "$cfg_effort")
                "${cmd[@]}" > "$raw_json" 2>&1 && exit_code=0 || exit_code=$?
                ;;
            *)
                log_error "Unknown CLI: ${cfg_cli}"
                return 1
                ;;
        esac

        # Extract text output from JSON and append to step log
        extract_ai_output "$cfg_cli" "$raw_json" >> "$CURRENT_STEP_LOG"
    else
        # --- Text mode (no jq): original pipe-through behavior ---
        case "$cfg_cli" in
            claude)
                local cmd=(claude -p "$prompt" --model "$cfg_model" --dangerously-skip-permissions)
                [[ -n "$cfg_effort" ]] && cmd+=(--effort "$cfg_effort")
                "${cmd[@]}" 2>&1 | tee -a "$CURRENT_STEP_LOG" > /dev/null && exit_code=0 || exit_code=$?
                ;;
            codex)
                local cprompt; cprompt="$(codex_prompt "$prompt")"
                local cmd=(codex exec "$cprompt" -m "$cfg_model" --full-auto)
                [[ -n "$cfg_effort" ]] && cmd+=(-c "model_reasoning_effort=${cfg_effort}")
                "${cmd[@]}" 2>&1 | tee -a "$CURRENT_STEP_LOG" > /dev/null && exit_code=0 || exit_code=$?
                ;;
            copilot)
                local cmd=(copilot -p "$prompt" --model "$cfg_model" --yolo)
                if [[ -n "$cfg_effort" ]]; then
                    local eff="$cfg_effort"
                    [[ "$eff" == "max" ]] && eff="xhigh"
                    cmd+=(--effort "$eff")
                fi
                "${cmd[@]}" 2>&1 | tee -a "$CURRENT_STEP_LOG" > /dev/null && exit_code=0 || exit_code=$?
                ;;
            opencode)
                local cmd=(opencode run "$prompt" -m "$cfg_model")
                [[ -n "$cfg_effort" ]] && cmd+=(--variant "$cfg_effort")
                "${cmd[@]}" 2>&1 | tee -a "$CURRENT_STEP_LOG" > /dev/null && exit_code=0 || exit_code=$?
                ;;
            *)
                log_error "Unknown CLI: ${cfg_cli}"
                return 1
                ;;
        esac
    fi

    return "$exit_code"
}

# run_review_step <step_id> <file_prefix> <ai_suffix>
# Dispatches the appropriate slash command based on file_prefix.
# Individual review files go to TMP_DIR (discarded after triage synthesizes).
run_review_step() {
    local step_id="$1" file_prefix="$2" ai_suffix="$3"
    local f="${TMP_DIR}/${step_id}-${file_prefix}-${ai_suffix}.md"
    local template
    case "$file_prefix" in
        validate)        template="1.2-validate.md" ;;
        edge-cases)      template="3.1-edge-cases.md" ;;
        code-adversarial) template="3.1-code-adversarial.md" ;;
    esac
    # Code review steps get embedded git context; spec validation does not
    local git_context=""
    if [[ "$file_prefix" != "validate" ]] && type _capture_git_context &>/dev/null; then
        git_context="$(_capture_git_context review)"
    fi
    run_ai "$step_id" "$(load_prompt "$template" \
        STORY_ID "$STORY_ID" \
        COMMIT_BASELINE "$COMMIT_BASELINE" \
        OUTPUT_FILE "$f" \
        GIT_CONTEXT "$git_context")"
}

# --- Model Availability Checks ---

# Each _check_*_model function returns:
#   0 = model available
#   1 = model definitely not available
#   2 = cannot determine (listing unavailable)

_check_claude_model() {
    local model="$1"
    local cache_dir="${PROJECT_ROOT}/.tmp/auto-bmad/model-checks"
    local cache_file="${cache_dir}/claude_${model}"

    # Check cache — return cached result if younger than TTL
    if [[ -f "$cache_file" ]]; then
        local now mtime age
        now=$(date +%s)
        if mtime=$(stat -f %m "$cache_file" 2>/dev/null); then
            :
        else
            mtime=$(stat -c %Y "$cache_file" 2>/dev/null) || mtime=0
        fi
        age=$(( now - mtime ))
        if (( age < ${MODEL_CHECK_MAX_AGE:-86400} )); then
            local cached_rc=""
            cached_rc=$(<"$cache_file") || true
            case "$cached_rc" in
                0|1|2) return "$cached_rc" ;;
            esac
        fi
    fi

    # Live API probe (~$0.001)
    local output
    output=$(echo "." | claude -p --model "$model" --max-budget-usd 0.001 2>&1) || true
    local result=0
    if echo "$output" | grep -q "There's an issue with the selected model"; then
        result=1
    fi

    # Cache the result
    mkdir -p "$cache_dir"
    echo "$result" > "$cache_file"

    return "$result"
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

    # Collect unique cli:model pairs from @profile definitions in conf/profiles.conf
    _load_profiles
    local i cli model
    for ((i=0; i<${#_PROFILE_NAMES[@]}; i++)); do
        cli="${_PROFILE_CLIS[$i]}"
        model="${_PROFILE_MODELS[$i]}"
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
