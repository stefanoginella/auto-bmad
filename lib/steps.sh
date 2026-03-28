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
    local _elapsed=""
    if [[ -n "${PIPELINE_START_TIME:-}" ]]; then
        _elapsed="  ${DIM}[elapsed $(format_duration $(( $(date +%s) - PIPELINE_START_TIME )))]${NC}"
    fi
    echo ""
    echo -e "${BOLD}${BLUE}>>> Step ${step_id}: ${step_name}${NC}  ${DIM}[${detail}]${NC}${_elapsed}"
}

log_dry() {
    local step_id="$1" step_name="$2"
    parse_step_config "$step_id"
    echo -e "  ${DIM}[DRY RUN]${NC} Step ${BOLD}${step_id}${NC} — ${step_name}"
    echo -e "    CLI: ${cfg_cli:-shell}  Model: ${cfg_model:-n/a}  Effort: ${cfg_effort:-n/a}"
}

# ============================================================
# Review Anonymization — strip provider names before triage
# ============================================================

# Shuffle an array of labels using Fisher-Yates (Bash 3.2 compatible).
# Reads array name, writes shuffled result to the same variable.
_shuffle_labels() {
    local -a arr=("$@")
    local i j tmp n=${#arr[@]}
    for ((i = n - 1; i > 0; i--)); do
        j=$(( RANDOM % (i + 1) ))
        tmp="${arr[$i]}"
        arr[$i]="${arr[$j]}"
        arr[$j]="$tmp"
    done
    echo "${arr[@]}"
}

# Anonymize review files before passing to triage.
# Usage: _anonymize_reviews <step_prefix> <output_dir>
# Reads review files matching ${TMP_DIR}/${step_prefix}*-*.md,
# creates anonymized copies in output_dir with provider names replaced by
# neutral labels. Saves the mapping to ${TMP_DIR}/reviewer-mapping-${step_prefix}.txt
# Echoes newline-separated list of anonymized file paths (for {{REVIEW_FILES}}).
_anonymize_reviews() {
    local step_prefix="$1" output_dir="$2"
    local -a originals=()
    local f
    for f in "${TMP_DIR}"/${step_prefix}*-*.md; do
        [[ -f "$f" ]] && originals+=("$f")
    done

    [[ ${#originals[@]} -eq 0 ]] && return 0

    # Generate shuffled labels: Reviewer A, B, C, ...
    local -a all_labels=(A B C D E F G H)
    local -a shuffled
    IFS=' ' read -r -a shuffled <<< "$(_shuffle_labels "${all_labels[@]:0:${#originals[@]}}")"

    # Known provider/model identifiers to strip
    local -a provider_patterns=(
        "Claude" "claude" "Opus" "opus" "Sonnet" "sonnet"
        "GPT" "gpt" "Codex" "codex" "GPT-5.4" "gpt-5.4"
        "Copilot" "copilot"
        "OpenCode" "opencode" "MiMo" "mimo" "Kimi" "kimi"
        "Gemini" "gemini"
    )

    local mapping_file="${TMP_DIR}/reviewer-mapping-${step_prefix}.txt"
    : > "$mapping_file"
    local review_files=""

    local i=0
    for f in "${originals[@]}"; do
        local label="${shuffled[$i]}"
        local basename="${f##*/}"
        local anon_file="${output_dir}/anon-${label}-${step_prefix}.md"

        # Record mapping: label → original file
        echo "Reviewer ${label} = ${basename}" >> "$mapping_file"

        # Copy and replace provider names with the assigned label
        local content
        content="$(<"$f")"
        local pat
        for pat in "${provider_patterns[@]}"; do
            content="${content//$pat/Reviewer ${label}}"
        done
        echo "$content" > "$anon_file"

        review_files="${review_files}
- ${anon_file}"
        i=$((i + 1))
    done

    echo "$review_files"
}

# ============================================================
# Review Output Extraction — strip noise before triage
# ============================================================

# Extract the structured review report from a step log file using markers.
# Falls back to the full log if markers are not found.
# Usage: _extract_review_output <log_file> <output_file>
_extract_review_output() {
    local log_file="$1" output_file="$2"
    sed -n '/<!-- REVIEW_REPORT_START -->/,/<!-- REVIEW_REPORT_END -->/p' \
        "$log_file" | sed '1d;$d' > "$output_file"
    # Fall back to full log if markers not found or empty extraction
    [[ -s "$output_file" ]] || cp "$log_file" "$output_file"
}

# ============================================================
# Antipatterns Learning Loop — learn from triage across stories
# ============================================================

# Antipatterns file path — lives at ARTIFACT_DIR level (persists across stories within an epic).
# ARTIFACT_DIR is the parent of STORY_ARTIFACTS (e.g., _bmad-output/implementation-artifacts/auto-bmad/).
_antipatterns_file() {
    local artifact_base="${STORY_ARTIFACTS%/*}"
    echo "${artifact_base}/antipatterns.md"
}

# Extract verified findings from a triage report and append to antipatterns file.
# Looks for findings classified as patch, bad_spec, or defer in the decision table.
# Usage: _extract_antipatterns <triage_report> <phase_label>
_extract_antipatterns() {
    local triage_report="$1" phase_label="$2"
    [[ -f "$triage_report" ]] || return 0

    local ap_file
    ap_file="$(_antipatterns_file)"

    # Extract rows from the decision summary table that are patch, bad_spec, or defer
    local line
    while IFS= read -r line; do
        # Match table rows: | # | Finding | Category | ...
        # Category is in field 4 (0-indexed field 3 after split on |)
        local category=""
        category=$(echo "$line" | awk -F'|' '{gsub(/^[[:space:]]+|[[:space:]]+$/, "", $4); print $4}')
        case "$category" in
            patch|bad_spec|defer|intent_gap)
                local finding=""
                finding=$(echo "$line" | awk -F'|' '{gsub(/^[[:space:]]+|[[:space:]]+$/, "", $3); print $3}')
                [[ -z "$finding" ]] && continue
                # Deduplicate: skip if this finding title already exists
                if [[ -f "$ap_file" ]] && grep -qF "$finding" "$ap_file" 2>/dev/null; then
                    continue
                fi
                echo "- **[${category}]** (${STORY_ID}, ${phase_label}): ${finding}" >> "$ap_file"
                ;;
        esac
    done < <(grep '^|' "$triage_report" | grep -v '^|[[:space:]]*#\|^|[[:space:]]*-' || true)
}

# Build the antipatterns injection text for prompt placeholders.
# Returns the header + accumulated antipatterns, or empty string if none exist.
_build_antipatterns_injection() {
    local ap_file
    ap_file="$(_antipatterns_file)"
    if [[ -f "$ap_file" && -s "$ap_file" ]]; then
        local header_file="${INSTALL_DIR}/prompts/fragments/antipatterns-header.md"
        if [[ -f "$header_file" ]]; then
            printf '\n\n%s%s\n' "$(<"$header_file")" "$(<"$ap_file")"
        else
            printf '\n\n## Known Antipatterns\n\n%s\n' "$(<"$ap_file")"
        fi
    fi
}

# ============================================================
# Git Intelligence — pre-capture git state for prompt embedding
# ============================================================

# Capture relevant git context for embedding in prompts.
# Usage: _capture_git_context [mode]
#   mode: "review" — full diff for code reviewers
#         "impl"   — summary for implementation steps
#         "doc"    — commit log for documentation
_capture_git_context() {
    local mode="${1:-impl}"
    local context=""

    context+="## Git Context (auto-captured by pipeline)
"
    case "$mode" in
        review)
            context+="
### Changes Since Baseline (${COMMIT_BASELINE}..HEAD)
\`\`\`
$(git -C "$PROJECT_ROOT" diff --stat "$COMMIT_BASELINE" HEAD 2>/dev/null || echo "(no baseline)")
\`\`\`

### Full Diff
\`\`\`diff
$(git -C "$PROJECT_ROOT" diff "$COMMIT_BASELINE" HEAD 2>/dev/null | head -2000 || echo "(no diff)")
\`\`\`
"
            ;;
        impl)
            context+="
### Recent Commits
\`\`\`
$(git -C "$PROJECT_ROOT" log --oneline -5 2>/dev/null || echo "(no commits)")
\`\`\`

### Working Tree Status
\`\`\`
$(git -C "$PROJECT_ROOT" status --short 2>/dev/null || echo "(clean)")
\`\`\`
"
            ;;
        doc)
            context+="
### Story Commit History (${COMMIT_BASELINE}..HEAD)
\`\`\`
$(git -C "$PROJECT_ROOT" log --oneline "$COMMIT_BASELINE"..HEAD 2>/dev/null || echo "(no commits)")
\`\`\`

### Files Changed
\`\`\`
$(git -C "$PROJECT_ROOT" diff --stat "$COMMIT_BASELINE" HEAD 2>/dev/null || echo "(no changes)")
\`\`\`
"
            ;;
    esac

    printf '%s' "$context"
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

    local antipatterns
    antipatterns="$(_build_antipatterns_injection)"

    run_ai "1.1" "$(load_prompt "1.1-create-story.md" \
        STORY_ID "$STORY_ID" \
        PREV_STORY_CARRY_FORWARD "$carry_forward" \
        ANTIPATTERNS "$antipatterns")"
    detect_story_file_path
    if [[ -n "$STORY_FILE_PATH" ]]; then log_ok "Story file: ${STORY_FILE_PATH}"
    else log_warn "Could not detect story file path — will retry before finalization"; fi
}

step_1_3_spec_triage() {
    # Extract structured review outputs from step logs (strips noise)
    local f
    for f in "${TMP_DIR}"/1.2*-*.md; do
        [[ -f "$f" ]] && _extract_review_output "$f" "${f%.md}-extracted.md"
    done
    # Rename extracted files back so anonymization picks them up
    for f in "${TMP_DIR}"/1.2*-extracted.md; do
        [[ -f "$f" ]] && mv "$f" "${f%-extracted.md}.md"
    done

    # Anonymize reviewer identities before triage
    local anon_dir="${TMP_DIR}/anon-1.2"
    mkdir -p "$anon_dir"
    local review_files
    review_files="$(_anonymize_reviews "1.2" "$anon_dir")"

    local triage_report="${STORY_ARTIFACTS}/${STORY_SHORT_ID}-1.3-spec-triage.md"
    run_ai "1.3" "$(load_prompt "1.3-spec-triage.md" \
        REVIEW_FILES "$review_files" \
        TRIAGE_REPORT "$triage_report")"

    # Extract verified findings into the epic-level antipatterns file
    _extract_antipatterns "$triage_report" "Phase 1 — Spec Triage"
}

step_1_4_resolve_spec_findings() {
    run_ai "1.4" "$(load_prompt "1.4-resolve-spec.md" \
        TRIAGE_REPORT "${STORY_ARTIFACTS}/${STORY_SHORT_ID}-1.3-spec-triage.md" \
        STORY_ID "$STORY_ID")"
}

# --- Phase 2: TDD + Implementation ---
step_2_1_tdd_red() { run_ai "2.1" "$(load_prompt "2.1-tdd-red.md" STORY_ID "$STORY_ID")"; }
step_2_2_implementation() {
    local antipatterns
    antipatterns="$(_build_antipatterns_injection)"
    local git_context
    git_context="$(_capture_git_context impl)"
    run_ai "2.2" "$(load_prompt "2.2-implementation.md" \
        STORY_ID "$STORY_ID" \
        ANTIPATTERNS "$antipatterns" \
        GIT_CONTEXT "$git_context")"
}

# --- Phase 3: Code Review ---
step_3_2_acceptance_auditor() {
    run_ai "3.2" "$(load_prompt "3.2-acceptance-audit.md" \
        STORY_ID "$STORY_ID" \
        STORY_FILE_PATH "$STORY_FILE_PATH" \
        COMMIT_BASELINE "$COMMIT_BASELINE" \
        AUDIT_REPORT "${STORY_ARTIFACTS}/${STORY_SHORT_ID}-3.2-code-acceptance.md")"
}

step_3_3_triage() {
    # Extract structured review outputs from step logs (strips noise)
    local f
    for f in "${TMP_DIR}"/3.1*-*.md; do
        [[ -f "$f" ]] && _extract_review_output "$f" "${f%.md}-extracted.md"
    done
    for f in "${TMP_DIR}"/3.1*-extracted.md; do
        [[ -f "$f" ]] && mv "$f" "${f%-extracted.md}.md"
    done

    # Anonymize reviewer identities before triage
    local anon_dir="${TMP_DIR}/anon-3.1"
    mkdir -p "$anon_dir"
    local review_files
    review_files="$(_anonymize_reviews "3.1" "$anon_dir")"

    local triage_report="${STORY_ARTIFACTS}/${STORY_SHORT_ID}-3.3-code-triage.md"
    run_ai "3.3" "$(load_prompt "3.3-code-triage.md" \
        REVIEW_FILES "$review_files" \
        ACCEPTANCE_REPORT "${STORY_ARTIFACTS}/${STORY_SHORT_ID}-3.2-code-acceptance.md" \
        TRIAGE_REPORT "$triage_report")"

    # Extract verified findings into the epic-level antipatterns file
    _extract_antipatterns "$triage_report" "Phase 3 — Code Triage"
}

step_3_4_dev_fix() {
    local antipatterns
    antipatterns="$(_build_antipatterns_injection)"
    local git_context
    git_context="$(_capture_git_context impl)"
    run_ai "3.4" "$(load_prompt "3.4-dev-fix.md" \
        TRIAGE_REPORT "${STORY_ARTIFACTS}/${STORY_SHORT_ID}-3.3-code-triage.md" \
        ACCEPTANCE_REPORT "${STORY_ARTIFACTS}/${STORY_SHORT_ID}-3.2-code-acceptance.md" \
        ANTIPATTERNS "$antipatterns" \
        GIT_CONTEXT "$git_context")"
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

        # Reviewer anonymization mappings (for deanonymization in tech-writer step)
        local mapping_file
        for mapping_file in "${TMP_DIR}"/reviewer-mapping-*.txt; do
            if [[ -f "$mapping_file" ]]; then
                local prefix="${mapping_file##*reviewer-mapping-}"
                prefix="${prefix%.txt}"
                echo "## Reviewer Anonymization Mapping (${prefix})"
                echo ""
                echo "The following mapping was used during triage. Reviewer labels in triage reports correspond to these original review sessions:"
                echo ""
                while IFS= read -r map_line; do
                    echo "- ${map_line}"
                done < "$mapping_file"
                echo ""
            fi
        done

        # Placeholder for reviewer assessment (populated by tech-writer step 6.1)
        echo "## Reviewer Assessment"
        echo ""
        echo "<!-- Populated by the tech-writer step. Read both triage reports and the acceptance audit to fill in. Use the anonymization mappings above to deanonymize reviewer labels back to actual provider names. -->"
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

        # Placeholder for file list (populated by tech-writer step 6.1)
        echo "## File List"
        echo ""
        echo "<!-- Populated by the tech-writer step. List ALL files created, modified, or deleted across the entire pipeline. Check git diff --stat for completeness. Organize by category: new, modified, deleted, acceptance tests, pipeline artifacts. -->"
        echo ""

    } > "$PIPELINE_REPORT"
}

# --- Phase 6: Finalization ---

step_6_1_document() {
    [[ -z "$STORY_FILE_PATH" ]] && detect_story_file_path

    local git_context
    git_context="$(_capture_git_context doc)"

    run_ai "6.1" "$(load_prompt "6.1-document.md" \
        STORY_ID "$STORY_ID" \
        STORY_REF "${STORY_FILE_PATH:-the story file for ${STORY_ID}}" \
        STORY_ARTIFACTS "$STORY_ARTIFACTS" \
        STORY_SHORT_ID "$STORY_SHORT_ID" \
        PIPELINE_REPORT "$PIPELINE_REPORT" \
        COMMIT_BASELINE "$COMMIT_BASELINE" \
        GIT_CONTEXT "$git_context")"
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
