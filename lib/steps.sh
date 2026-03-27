#!/usr/bin/env bash
# lib/steps.sh — Step function implementations
# Sourced by auto-bmad-story
#
# Requires: lib/core.sh, lib/tracking.sh, lib/config.sh, lib/cli.sh, lib/usage.sh, lib/detection.sh sourced
# Reads globals: STORY_ID STORY_SHORT_ID EPIC_ID STORY_FILE_PATH PREV_STORY_FILE
#                STORY_ARTIFACTS TMP_DIR PIPELINE_LOG PIPELINE_REPORT PIPELINE_START_TIME
#                COMMIT_BASELINE PROJECT_ROOT STEP_ORDER cfg_cli cfg_model cfg_effort

[[ -n "${_STEPS_SH_LOADED:-}" ]] && return 0
_STEPS_SH_LOADED=1

# ============================================================
# Story-Specific Logging (depends on parse_step_config from CLI layer)
# ============================================================

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

log_dry() {
    local step_id="$1" step_name="$2"
    parse_step_config "$step_id"
    echo -e "  ${DIM}[DRY RUN]${NC} Step ${BOLD}${step_id}${NC} — ${step_name}"
    echo -e "    CLI: ${cfg_cli:-shell}  Model: ${cfg_model:-n/a}  Effort: ${cfg_effort:-n/a}"
}

# ============================================================
# Step Functions (prompts externalized to prompts/*.md)
# ============================================================

# --- Phase 0: Epic Start ---
step_0_1_test_design() { run_ai "0.1" "$(load_prompt "0.1-test-design.md" EPIC_ID "$EPIC_ID")"; }

# --- Phase 1: Story Preparation ---
step_1_1_create_story() {
    # Build carry-forward instruction when a previous story exists in this epic
    local carry_forward=""
    if [[ -n "$PREV_STORY_FILE" && -f "$PREV_STORY_FILE" ]]; then
        carry_forward="

IMPORTANT — Carry-forward from previous story: Before creating this story, read the previous story file at ${PREV_STORY_FILE} and check its \"Human Review Required\" section:
- \"Deferred to Future Stories\": incorporate any deferred items that fall within this story's scope into the tasks
- \"Manual Testing Required\": check for unchecked items (- [ ]) this story could address or automate
- \"Open Questions\": check for unresolved items (red circle Open) this story's context may resolve
Do NOT blindly copy all items — only incorporate what is relevant to this story's scope."
    fi

    run_ai "1.1" "$(load_prompt "1.1-create-story.md" \
        STORY_ID "$STORY_ID" \
        PREV_STORY_CARRY_FORWARD "$carry_forward")"
    detect_story_file_path
    if [[ -n "$STORY_FILE_PATH" ]]; then log_ok "Story file: ${STORY_FILE_PATH}"
    else log_warn "Could not detect story file path — will retry before finalization"; fi
}

step_1_3_spec_triage() {
    local review_files=""
    for f in "${TMP_DIR}"/1.2*-*.md; do [[ -f "$f" ]] && review_files="${review_files}
- ${f}"; done
    run_ai "1.3" "$(load_prompt "1.3-spec-triage.md" \
        REVIEW_FILES "$review_files" \
        TRIAGE_REPORT "${STORY_ARTIFACTS}/${STORY_SHORT_ID}-1.3-spec-triage.md")"
}

step_1_4_resolve_spec_findings() {
    run_ai "1.4" "$(load_prompt "1.4-resolve-spec.md" \
        TRIAGE_REPORT "${STORY_ARTIFACTS}/${STORY_SHORT_ID}-1.3-spec-triage.md" \
        STORY_ID "$STORY_ID")"
}

# --- Phase 2: TDD + Implementation ---
step_2_1_tdd_red() { run_ai "2.1" "$(load_prompt "2.1-tdd-red.md" STORY_ID "$STORY_ID")"; }
step_2_2_implementation() { run_ai "2.2" "$(load_prompt "2.2-implementation.md" STORY_ID "$STORY_ID")"; }

# --- Phase 3: Code Review ---
step_3_2_acceptance_auditor() {
    run_ai "3.2" "$(load_prompt "3.2-acceptance-audit.md" \
        STORY_ID "$STORY_ID" \
        STORY_FILE_PATH "$STORY_FILE_PATH" \
        COMMIT_BASELINE "$COMMIT_BASELINE" \
        AUDIT_REPORT "${STORY_ARTIFACTS}/${STORY_SHORT_ID}-3.2-code-acceptance.md")"
}

step_3_3_triage() {
    local review_files=""
    for f in "${TMP_DIR}"/3.1*-*.md; do [[ -f "$f" ]] && review_files="${review_files}
- ${f}"; done
    run_ai "3.3" "$(load_prompt "3.3-code-triage.md" \
        REVIEW_FILES "$review_files" \
        ACCEPTANCE_REPORT "${STORY_ARTIFACTS}/${STORY_SHORT_ID}-3.2-code-acceptance.md" \
        TRIAGE_REPORT "${STORY_ARTIFACTS}/${STORY_SHORT_ID}-3.3-code-triage.md")"
}

step_3_4_dev_fix() {
    run_ai "3.4" "$(load_prompt "3.4-dev-fix.md" \
        TRIAGE_REPORT "${STORY_ARTIFACTS}/${STORY_SHORT_ID}-3.3-code-triage.md" \
        ACCEPTANCE_REPORT "${STORY_ARTIFACTS}/${STORY_SHORT_ID}-3.2-code-acceptance.md")"
}

step_3_5_resolve_code_spec_findings() {
    run_ai "3.5" "$(load_prompt "3.5-resolve-code-spec.md" \
        TRIAGE_REPORT "${STORY_ARTIFACTS}/${STORY_SHORT_ID}-3.3-code-triage.md" \
        ACCEPTANCE_REPORT "${STORY_ARTIFACTS}/${STORY_SHORT_ID}-3.2-code-acceptance.md" \
        STORY_ID "$STORY_ID")"
}

# --- Phase 4: Traceability & Automation ---
step_4_1_trace()    { run_ai "4.1" "$(load_prompt "4.1-trace.md" STORY_ID "$STORY_ID")"; }
step_4_2_automate() { run_ai "4.2" "$(load_prompt "4.2-automate.md" STORY_ID "$STORY_ID")"; }

# --- Phase 5: Epic End ---
step_5_1_epic_trace()       { run_ai "5.1" "$(load_prompt "5.1-epic-trace.md" EPIC_ID "$EPIC_ID")"; }
step_5_2_epic_nfr()         { run_ai "5.2" "$(load_prompt "5.2-epic-nfr.md" EPIC_ID "$EPIC_ID")"; }
step_5_3_epic_test_review() { run_ai "5.3" "$(load_prompt "5.3-epic-test-review.md" EPIC_ID "$EPIC_ID")"; }
step_5_4_retrospective()    { run_ai "5.4" "$(load_prompt "5.4-retrospective.md" EPIC_ID "$EPIC_ID")"; }
step_5_5_epic_exit_report() {
    local epic_story_paths
    epic_story_paths="$(collect_epic_story_paths)"
    local epic_exit_report="${STORY_ARTIFACTS}/${STORY_SHORT_ID}-5.5-epic-exit-report.md"
    run_ai "5.5" "$(load_prompt "5.5-epic-exit-report.md" \
        EPIC_ID "$EPIC_ID" \
        EPIC_STORY_PATHS "$epic_story_paths" \
        EPIC_EXIT_REPORT "$epic_exit_report")"
}
step_5_6_project_context()  { run_ai "5.6" "$(load_prompt "5.6-project-context.md")"; }

# --- Generate Pipeline Report (structured markdown) ---

generate_pipeline_report() {
    local total_compute=0
    local steps_ok=0 steps_failed=0 steps_retried=0 steps_fellback=0

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

        local attempts; attempts="$(get_step_attempts "$sid")"
        (( attempts > 1 )) && steps_retried=$((steps_retried + 1))
        local fp; fp="$(get_step_final_profile "$sid")"
        # Detect fallback by checking if model info in the log contains "→"
        [[ -n "$fp" ]] && parse_step_config "$sid" && \
            [[ "$fp" != "${cfg_cli}/${cfg_model}" ]] && steps_fellback=$((steps_fellback + 1))
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
        if (( steps_retried > 0 || steps_fellback > 0 )); then
            echo "| Retries | ${steps_retried} retried, ${steps_fellback} fell back |"
        fi
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

        # Placeholder for suggested review order (populated by tech-writer step 6.1)
        echo "## Suggested Review Order"
        echo ""
        echo "<!-- Populated by the tech-writer step. Organize stops by concern, not by file. -->"
        echo "<!-- For each stop: file:line reference and one-line framing of what to look for. -->"
        echo ""

    } > "$PIPELINE_REPORT"
}

# --- Phase 6: Finalization ---

step_6_1_document() {
    [[ -z "$STORY_FILE_PATH" ]] && detect_story_file_path

    # Build carry-forward instruction for rolling deferred accumulator
    local prev_deferred_instruction=""
    if [[ -n "$PREV_STORY_FILE" && -f "$PREV_STORY_FILE" ]]; then
        prev_deferred_instruction="
   ALSO include unresolved deferred items carried forward from the previous story. Read the previous story file at ${PREV_STORY_FILE} and check its \"Deferred to Future Stories\" section. Any items listed there that were NOT addressed by THIS story should be carried forward into this story's \"Deferred to Future Stories\" section. This creates a rolling accumulator — each story's deferred section is the complete list of outstanding deferred items for the epic so far."
    fi

    run_ai "6.1" "$(load_prompt "6.1-document.md" \
        STORY_ID "$STORY_ID" \
        STORY_REF "${STORY_FILE_PATH:-the story file for ${STORY_ID}}" \
        STORY_ARTIFACTS "$STORY_ARTIFACTS" \
        STORY_SHORT_ID "$STORY_SHORT_ID" \
        PIPELINE_REPORT "$PIPELINE_REPORT" \
        COMMIT_BASELINE "$COMMIT_BASELINE" \
        PREV_STORY_DEFERRED "$prev_deferred_instruction")"
}

step_6_2_close() {
    if [[ -z "$STORY_FILE_PATH" ]]; then
        detect_story_file_path
    fi

    local story_ref="${STORY_FILE_PATH:-the story file for ${STORY_ID}}"
    run_ai "6.2" "$(load_prompt "6.2-close-story.md" \
        STORY_ID "$STORY_ID" \
        STORY_REF "$story_ref")"
}
