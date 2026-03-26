#!/usr/bin/env bash
# lib/runner.sh — Step execution engine (DAG executor)
# Sourced by auto-bmad-story
#
# Requires: lib/core.sh, lib/tracking.sh, lib/config.sh, lib/cli.sh, lib/monitor.sh sourced
# Reads globals: _ABORT DRY_RUN FROM_STEP STEP_ORDER REVIEWS_MODE TMP_DIR PIPELINE_LOG
#                PIPELINE_START_TIME STORY_ID CURRENT_STEP_LOG SPINNER_FRAMES
#
# Exports:
#   should_run_step <step_id>     — check if step should run (--from-step filtering)
#   run_step <id> <name> <cmd...> — execute a single step with tracking
#   run_parallel_reviews <entry...> — run parallel review steps with live status board

[[ -n "${_RUNNER_SH_LOADED:-}" ]] && return 0
_RUNNER_SH_LOADED=1

# --- Soft-fail Detection & Retry ---

# Soft-fail thresholds — loaded from conf/pipeline.conf via cfg_pip_* globals
MIN_STEP_DURATION="${cfg_pip_min_step_duration:-5}"
MIN_LOG_BYTES="${cfg_pip_min_log_bytes:-200}"

# Detect soft or hard failure after a step command returns.
# Returns 0 (= failure detected) when:
#   - exit_code != 0 (hard fail), OR
#   - duration < MIN_STEP_DURATION AND log output < MIN_LOG_BYTES (soft fail)
_detect_soft_fail() {
    local exit_code="$1" duration="$2"
    (( exit_code != 0 )) && return 0
    local log_size=0
    [[ -f "$CURRENT_STEP_LOG" ]] && log_size=$(wc -c < "$CURRENT_STEP_LOG" | tr -d ' ')
    (( duration < MIN_STEP_DURATION && log_size < MIN_LOG_BYTES ))
}

# Run a step command with retry + fallback.
# Usage: _run_with_retry <step_id> <command...>
#
# Flow: primary → retry primary → fallback (one shot) → fail
# Sets tracking fields: attempts, final_profile
_run_with_retry() {
    local step_id="$1"; shift

    parse_step_config "$step_id"
    local original_cli="$cfg_cli" original_model="$cfg_model"
    local original_effort="$cfg_effort" original_fallback="$cfg_fallback"
    local attempt=0 max_retries=1 using_fallback=false
    local final_profile="${original_cli}/${original_model}"

    # Tell run_ai to use current cfg_* globals (set by apply_profile on fallback)
    _RETRY_PROFILE_ACTIVE=true

    while true; do
        attempt=$((attempt + 1))

        # Reset log for each attempt so size check is fresh
        : > "$CURRENT_STEP_LOG"

        local start_time; start_time=$(date +%s)
        local exit_code=0
        "$@" || exit_code=$?
        local duration=$(( $(date +%s) - start_time ))

        if _detect_soft_fail "$exit_code" "$duration"; then
            local fail_type="soft"
            (( exit_code != 0 )) && fail_type="hard"

            if [[ "$using_fallback" == true ]]; then
                # Fallback also failed — give up
                log_warn "Fallback ${fail_type}-failed for ${step_id} (${duration}s)"
                set_step_attempts "$step_id" "$attempt"
                set_step_final_profile "$step_id" "$final_profile"
                _RETRY_PROFILE_ACTIVE=false
                return 1
            fi

            if (( attempt <= max_retries )); then
                log_warn "Step ${step_id} ${fail_type}-failed (${duration}s) — retry ${attempt}/${max_retries}"
                continue
            fi

            # Retries exhausted — try fallback
            if [[ "$original_fallback" != "-" && -n "$original_fallback" ]]; then
                log_warn "Retries exhausted for ${step_id} — falling back to ${original_fallback}"
                apply_profile "$original_fallback"
                final_profile="${cfg_cli}/${cfg_model}"
                using_fallback=true
                attempt=0
                max_retries=0   # fallback gets exactly one shot
                continue
            fi

            # No fallback available
            log_warn "Step ${step_id} failed with no fallback"
            set_step_attempts "$step_id" "$attempt"
            set_step_final_profile "$step_id" "$final_profile"
            _RETRY_PROFILE_ACTIVE=false
            return 1
        fi

        # Success
        set_step_attempts "$step_id" "$attempt"
        set_step_final_profile "$step_id" "$final_profile"
        _RETRY_PROFILE_ACTIVE=false
        return 0
    done
}

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

    if _run_with_retry "$step_id" "$@"; then
        stop_activity_monitor
        local end_time; end_time=$(date +%s)
        local duration=$((end_time - start_time))
        set_step_duration "$step_id" "$duration"
        set_step_status "$step_id" "ok"
        local final_info; final_info="$(get_step_final_profile "$step_id")"
        [[ -n "$final_info" && "$final_info" != "$model_info" ]] && model_info="${model_info}→${final_info}"
        local attempts; attempts="$(get_step_attempts "$step_id")"
        (( attempts > 1 )) && model_info="${model_info}(x${attempts})"
        _log_pipeline_entry "$step_id" "$model_info" "$duration" "ok" "$step_name"
        log_ok "Completed in $(format_duration $duration)"
    else
        stop_activity_monitor
        local end_time; end_time=$(date +%s)
        local duration=$((end_time - start_time))
        set_step_duration "$step_id" "$duration"
        set_step_status "$step_id" "FAILED"
        local final_info; final_info="$(get_step_final_profile "$step_id")"
        [[ -n "$final_info" && "$final_info" != "$model_info" ]] && model_info="${model_info}→${final_info}"
        local attempts; attempts="$(get_step_attempts "$step_id")"
        (( attempts > 1 )) && model_info="${model_info}(x${attempts})"
        _log_pipeline_entry "$step_id" "$model_info" "$duration" "FAILED" "$step_name"
        echo "# FAILED at step ${step_id} after $(format_duration $((end_time - PIPELINE_START_TIME))) wall time" >> "$PIPELINE_LOG"
        echo "# Resume: auto-bmad story --from-step ${step_id} --story ${STORY_ID}" >> "$PIPELINE_LOG"
        log_error "Step ${step_id} (${step_name}) FAILED after $(format_duration $duration)"
        log_error "Step log: ${CURRENT_STEP_LOG}"
        log_error "Resume: auto-bmad story --from-step ${step_id} --story ${STORY_ID}"
        exit 1
    fi
}

# Run parallel review steps. Failures are warnings, not fatal.
# Entry format: "step_id|name|file_prefix|ai_suffix" for review steps
#            or "step_id|name|func_name" for arbitrary functions
run_parallel_reviews() {
    [[ "$_ABORT" == true ]] && exit 130

    # --reviews none: skip entire function
    if [[ "$REVIEWS_MODE" == "none" ]]; then
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
        log_skip "Steps ${first_sid}–${last_sid} — --reviews none"
        return 0
    fi

    # --reviews fast: only run the first entry (GPT / suffix "a")
    if [[ "$REVIEWS_MODE" == "fast" ]]; then
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
        # _run_with_retry handles soft-fail detection, retry, and fallback.
        if [[ -n "$field4" ]]; then
            CURRENT_STEP_LOG="$step_log" _run_with_retry "$sid" run_review_step "$sid" "$field3" "$field4" >/dev/null &
        else
            CURRENT_STEP_LOG="$step_log" _run_with_retry "$sid" "$field3" >/dev/null &
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
