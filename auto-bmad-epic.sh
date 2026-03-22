#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# auto-bmad-epic.sh — Epic-Level BMAD Pipeline Orchestrator
#
# Thin wrapper that loops through all stories in an epic,
# delegating each to ./auto-bmad-story.sh, handling PR + CI
# between stories, and tracking epic-level metrics.
#
# Usage: ./auto-bmad-epic.sh [options]
#   --epic EPIC_ID       Target epic number (e.g., 1). Auto-detects if omitted.
#   --from-story ID      Resume from a specific story (e.g., 1-3-some-slug)
#   --dry-run            Preview the full epic plan without executing
#   --no-merge           Skip auto-PR/merge between stories (manual git)
#   --help               Show usage
# ============================================================

# --- Project Paths ---
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
IMPL_ARTIFACTS="${PROJECT_ROOT}/_bmad-output/implementation-artifacts"
SPRINT_STATUS="${IMPL_ARTIFACTS}/sprint-status.yaml"
STORY_SCRIPT="${PROJECT_ROOT}/auto-bmad-story.sh"
EPIC_ARTIFACTS=""
EPIC_LOG=""

# --- Configuration ---
PR_MERGE_TIMEOUT=900   # 15 minutes
PR_POLL_INTERVAL=30    # seconds

# --- Pipeline State ---
EPIC_ID=""
DRY_RUN=false
FROM_STORY=""
NO_MERGE=false
EPIC_START_TIME=""

# Story arrays (parallel indexed)
STORY_IDS=()
STORY_STATUSES=()
STORY_COUNT=0

# ============================================================
# Color & Logging (same style as auto-bmad-story.sh)
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
    echo -e "${BOLD}${CYAN}  $1${NC}"
    echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════════════════${NC}"
}

log_ok()    { echo -e "${GREEN}  ✓ $1${NC}"; }
log_warn()  { echo -e "${YELLOW}  ! $1${NC}"; }
log_error() { echo -e "${RED}  ✗ $1${NC}"; }
log_skip()  { echo -e "${DIM}  — Skipped: $1${NC}"; }

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
# In-memory per-story tracking (dynamic variables, bash 3.2 compat)
# ============================================================

# Sanitize story ID for use as variable name (replace - with _)
sanitize_id() { echo "${1//-/_}"; }

set_story_track_status()   { local k; k="$(sanitize_id "$1")"; printf -v "etrack_${k}_status"   '%s' "$2"; }
get_story_track_status()   { local k; k="$(sanitize_id "$1")"; local v="etrack_${k}_status";   echo "${!v:-pending}"; }
set_story_track_duration() { local k; k="$(sanitize_id "$1")"; printf -v "etrack_${k}_duration" '%s' "$2"; }
get_story_track_duration() { local k; k="$(sanitize_id "$1")"; local v="etrack_${k}_duration"; echo "${!v:-0}"; }

# ============================================================
# Epic & Story Detection
# ============================================================

detect_next_epic() {
    if [[ ! -f "$SPRINT_STATUS" ]]; then
        log_error "Sprint status file not found: ${SPRINT_STATUS}"
        exit 1
    fi

    local in_progress_epic="" first_non_done_epic=""

    while IFS=: read -r key status; do
        key="${key#"${key%%[![:space:]]*}"}"; key="${key%"${key##*[![:space:]]}"}"
        status="${status#"${status%%[![:space:]]*}"}"; status="${status%"${status##*[![:space:]]}"}"

        # Match epic-N entries only
        [[ "$key" =~ ^epic-([0-9]+)$ ]] || continue
        local eid="${BASH_REMATCH[1]}"

        if [[ "$status" == "in-progress" && -z "$in_progress_epic" ]]; then
            in_progress_epic="$eid"
        fi
        if [[ "$status" != "done" && -z "$first_non_done_epic" ]]; then
            first_non_done_epic="$eid"
        fi
    done < "$SPRINT_STATUS"

    if [[ -n "$in_progress_epic" ]]; then
        EPIC_ID="$in_progress_epic"
    elif [[ -n "$first_non_done_epic" ]]; then
        EPIC_ID="$first_non_done_epic"
    else
        log_error "No epics with status 'in-progress' or 'backlog' found in sprint-status.yaml"
        exit 1
    fi
}

collect_epic_stories() {
    STORY_IDS=()
    STORY_STATUSES=()

    while IFS=: read -r key status; do
        key="${key#"${key%%[![:space:]]*}"}"; key="${key%"${key##*[![:space:]]}"}"
        status="${status#"${status%%[![:space:]]*}"}"; status="${status%"${status##*[![:space:]]}"}"

        # Match stories: {EPIC_ID}-{NUM}-{slug}
        [[ "$key" =~ ^${EPIC_ID}-[0-9]+- ]] || continue

        STORY_IDS+=("$key")
        STORY_STATUSES+=("$status")
    done < "$SPRINT_STATUS"

    STORY_COUNT=${#STORY_IDS[@]}
}

validate_epic() {
    if (( STORY_COUNT == 0 )); then
        log_error "No stories found for epic ${EPIC_ID} in sprint-status.yaml"
        exit 1
    fi

    local remaining=0
    for status in "${STORY_STATUSES[@]}"; do
        [[ "$status" != "done" ]] && remaining=$((remaining + 1))
    done

    if (( remaining == 0 )); then
        log_error "All stories in epic ${EPIC_ID} are already done"
        exit 1
    fi
}

# ============================================================
# Pre-flight Checks
# ============================================================

preflight_checks() {
    local errors=0

    echo -e "${BOLD}Pre-flight checks${NC}"

    if [[ -f "$SPRINT_STATUS" ]]; then
        log_ok "Sprint status file exists"
    else
        log_error "Sprint status file missing: ${SPRINT_STATUS}"
        errors=$((errors + 1))
    fi

    if [[ -x "$STORY_SCRIPT" ]]; then
        log_ok "Story script exists and is executable"
    elif [[ -f "$STORY_SCRIPT" ]]; then
        log_warn "Story script exists but is not executable — will fix"
        chmod +x "$STORY_SCRIPT"
        log_ok "Story script made executable"
    else
        log_error "Story script not found: ${STORY_SCRIPT}"
        errors=$((errors + 1))
    fi

    if command -v gh &>/dev/null; then
        log_ok "gh CLI found"
    else
        if [[ "$NO_MERGE" == "true" ]]; then
            log_warn "gh CLI not found (ok with --no-merge)"
        else
            log_error "gh CLI not found in PATH (required for PR creation)"
            errors=$((errors + 1))
        fi
    fi

    if command -v git &>/dev/null; then
        log_ok "git found"
    else
        log_error "git not found in PATH"
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
# Git & PR Workflow
# ============================================================

ensure_on_main() {
    local current_branch
    current_branch="$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null)" || {
        log_warn "Not a git repository — skipping branch check"
        return 0
    }

    if [[ "$current_branch" == "main" || "$current_branch" == "master" ]]; then
        return 0
    fi

    # If on a story branch, try to switch to main
    if [[ "$current_branch" == story/* ]]; then
        log_warn "On branch ${current_branch} — switching to main"
        git -C "$PROJECT_ROOT" checkout main 2>/dev/null || {
            log_error "Failed to switch to main. Resolve manually."
            exit 1
        }
        git -C "$PROJECT_ROOT" pull origin main --ff-only 2>/dev/null || true
        return 0
    fi

    log_warn "On unexpected branch: ${current_branch}"
    echo -en "    Continue anyway? [y/N] "
    read -r answer
    if [[ ! "$answer" =~ ^[Yy]$ ]]; then
        exit 1
    fi
}

# Extract conventional commit message from story file's Auto-bmad Completion section
extract_commit_message() {
    local story_id="$1"
    local story_file=""

    # Find the story file
    story_file=$(find "$IMPL_ARTIFACTS" -maxdepth 1 -name "${story_id}*.md" \
        ! -name "*--*" -type f 2>/dev/null | head -1)

    if [[ -z "$story_file" ]]; then
        echo "feat(epic-${EPIC_ID}): implement story ${story_id}"
        return
    fi

    # Extract commit message from Auto-bmad Completion section
    local in_section=false msg=""
    while IFS= read -r line; do
        if [[ "$line" =~ ^##[[:space:]]+Auto-bmad\ Completion ]]; then
            in_section=true
            continue
        fi
        if [[ "$in_section" == "true" && "$line" =~ ^## ]]; then
            break
        fi
        if [[ "$in_section" == "true" ]]; then
            # Look for conventional commit pattern
            if [[ "$line" =~ ^(feat|fix|chore|refactor|test|docs|build|ci|perf|style|revert)\( ]]; then
                msg="$line"
                # Read continuation lines (body after blank line)
                while IFS= read -r next_line; do
                    if [[ "$next_line" =~ ^## ]]; then
                        break
                    fi
                    msg="${msg}
${next_line}"
                done
                break
            fi
            # Also match if inside a code block
            if [[ "$line" =~ ^\`\`\` ]]; then
                while IFS= read -r next_line; do
                    if [[ "$next_line" =~ ^\`\`\` ]]; then
                        break
                    fi
                    if [[ -z "$msg" && "$next_line" =~ ^(feat|fix|chore|refactor|test|docs|build|ci|perf|style|revert)\( ]]; then
                        msg="$next_line"
                    elif [[ -n "$msg" ]]; then
                        msg="${msg}
${next_line}"
                    fi
                done
                [[ -n "$msg" ]] && break
            fi
        fi
    done < "$story_file"

    if [[ -n "$msg" ]]; then
        # Trim trailing whitespace/blank lines
        echo "$msg" | sed -e :a -e '/^[[:space:]]*$/d;N;ba' -e 's/[[:space:]]*$//'
    else
        echo "feat(epic-${EPIC_ID}): implement story ${story_id}"
    fi
}

commit_and_create_pr() {
    local story_id="$1"

    echo ""
    echo -e "  ${BOLD}${BLUE}>>> Git: Commit & PR for ${story_id}${NC}"

    # Check for uncommitted changes
    local has_changes=false
    if ! git -C "$PROJECT_ROOT" diff --quiet 2>/dev/null || \
       ! git -C "$PROJECT_ROOT" diff --cached --quiet 2>/dev/null || \
       [[ -n "$(git -C "$PROJECT_ROOT" ls-files --others --exclude-standard 2>/dev/null)" ]]; then
        has_changes=true
    fi

    if [[ "$has_changes" == "true" ]]; then
        local commit_msg
        commit_msg="$(extract_commit_message "$story_id")"

        git -C "$PROJECT_ROOT" add -A
        git -C "$PROJECT_ROOT" commit -m "$(cat <<EOF
${commit_msg}
EOF
        )" || {
            log_warn "Commit failed (maybe nothing to commit)"
        }
        log_ok "Changes committed"
    else
        log_ok "No uncommitted changes"
    fi

    # Push branch
    local branch="story/${story_id}"
    git -C "$PROJECT_ROOT" push -u origin "$branch" 2>&1 | tail -2
    log_ok "Pushed to origin/${branch}"

    # Create PR
    local pr_url
    pr_url=$(gh pr create \
        --title "feat(epic-${EPIC_ID}): ${story_id}" \
        --body "$(cat <<'PREOF'
## Summary

Auto-generated by auto-bmad-epic pipeline.
See story file for full details.
PREOF
        )" \
        --head "$branch" \
        2>&1) || {
        # PR might already exist
        pr_url=$(gh pr view "$branch" --json url -q '.url' 2>/dev/null || echo "")
        if [[ -z "$pr_url" ]]; then
            log_error "Failed to create PR for ${branch}"
            return 1
        fi
        log_warn "PR already exists"
    }
    log_ok "PR: ${pr_url}"

    # Enable auto-merge (squash)
    gh pr merge --auto --squash "$branch" 2>&1 || {
        log_warn "Auto-merge not enabled — repository may not have auto-merge configured"
        echo -e "    ${DIM}Falling back to direct merge after CI passes${NC}"
    }

    # Poll for merge
    wait_for_merge "$branch" "$pr_url"
}

wait_for_merge() {
    local branch="$1"
    local pr_url="${2:-}"
    local elapsed=0

    echo -e "  ${DIM}Waiting for CI + merge (timeout: $(format_duration $PR_MERGE_TIMEOUT))...${NC}"

    while (( elapsed < PR_MERGE_TIMEOUT )); do
        sleep "$PR_POLL_INTERVAL"
        elapsed=$((elapsed + PR_POLL_INTERVAL))

        local state
        state=$(gh pr view "$branch" --json state -q '.state' 2>/dev/null || echo "UNKNOWN")

        case "$state" in
            MERGED)
                log_ok "PR merged after $(format_duration $elapsed)"
                git -C "$PROJECT_ROOT" checkout main 2>/dev/null
                git -C "$PROJECT_ROOT" pull origin main --ff-only 2>/dev/null
                git -C "$PROJECT_ROOT" branch -d "$branch" 2>/dev/null || true
                return 0
                ;;
            CLOSED)
                log_error "PR was closed without merging"
                return 1
                ;;
            UNKNOWN)
                log_warn "Could not check PR status (elapsed: $(format_duration $elapsed))"
                ;;
            *)
                # Still open — check if CI failed
                local check_status
                check_status=$(gh pr checks "$branch" --json state -q '.[].state' 2>/dev/null | sort -u || echo "")
                if echo "$check_status" | grep -q "FAILURE"; then
                    echo ""
                    log_error "CI failed on PR for story ${branch#story/}"
                    [[ -n "$pr_url" ]] && echo -e "    PR: ${pr_url}"
                    echo ""
                    echo -e "    Fix CI, merge the PR manually, then resume:"
                    echo -e "    ${DIM}./auto-bmad-epic.sh --epic ${EPIC_ID} --from-story <next-story>${NC}"
                    return 1
                fi
                printf "  ${DIM}  ...waiting (%s elapsed)${NC}\r" "$(format_duration $elapsed)"
                ;;
        esac
    done

    echo ""
    log_error "Timed out waiting for PR merge ($(format_duration $PR_MERGE_TIMEOUT))"
    [[ -n "$pr_url" ]] && echo -e "    PR: ${pr_url}"
    echo -e "    Merge manually, then resume with --from-story"
    return 1
}

# ============================================================
# Retrospective Summary
# ============================================================

print_retro_summary() {
    local retro_file
    retro_file=$(find "$IMPL_ARTIFACTS" -maxdepth 1 -name "epic-${EPIC_ID}-retro-*.md" \
        -type f 2>/dev/null | sort -r | head -1)

    if [[ -z "$retro_file" ]]; then
        log_warn "No retrospective file found for epic ${EPIC_ID}"
        return
    fi

    log_phase "Retrospective Summary — Epic ${EPIC_ID}"
    echo -e "  ${DIM}Source: ${retro_file}${NC}"
    echo ""

    # Check for significant discovery alert
    if grep -qi "SIGNIFICANT DISCOVERY" "$retro_file" 2>/dev/null; then
        echo -e "  ${BOLD}${YELLOW}⚠ SIGNIFICANT DISCOVERY ALERT detected!${NC}"
        echo -e "  ${YELLOW}  Review the full retrospective before starting the next epic.${NC}"
        echo ""
    fi

    # Extract and display action items
    local in_actions=false found_actions=false
    while IFS= read -r line; do
        if [[ "$line" =~ [Aa]ction\ [Ii]tems ]]; then
            in_actions=true
            echo -e "  ${BOLD}Action Items:${NC}"
            continue
        fi
        if [[ "$in_actions" == "true" ]]; then
            # Stop at next major section
            if [[ "$line" =~ ^## ]]; then
                break
            fi
            # Print non-empty lines
            if [[ -n "${line// /}" ]]; then
                echo -e "    ${line}"
                found_actions=true
            fi
        fi
    done < "$retro_file"

    if [[ "$found_actions" == "false" ]]; then
        echo -e "  ${DIM}No action items found in retrospective.${NC}"
    fi

    # Extract and display critical path items
    local in_critical=false found_critical=false
    while IFS= read -r line; do
        if [[ "$line" =~ [Cc]ritical\ [Pp]ath ]]; then
            in_critical=true
            echo ""
            echo -e "  ${BOLD}Critical Path:${NC}"
            continue
        fi
        if [[ "$in_critical" == "true" ]]; then
            if [[ "$line" =~ ^## ]]; then
                break
            fi
            if [[ -n "${line// /}" ]]; then
                echo -e "    ${line}"
                found_critical=true
            fi
        fi
    done < "$retro_file"

    echo ""
    echo -e "  ${DIM}Full retrospective: ${retro_file}${NC}"
}

# ============================================================
# Epic-Level Metrics
# ============================================================

generate_epic_metrics() {
    local metrics_file="${EPIC_ARTIFACTS}/epic-${EPIC_ID}-metrics.md"
    local total_wall=$(( $(date +%s) - EPIC_START_TIME ))
    local stories_done=0 stories_failed=0 stories_skipped=0

    {
        echo "# Epic Pipeline Metrics — Epic ${EPIC_ID}"
        echo ""
        echo "Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo ""
        echo "| # | Story | Duration | Status |"
        echo "|---|-------|----------|--------|"

        local i=0
        for sid in "${STORY_IDS[@]}"; do
            i=$((i + 1))
            local status; status="$(get_story_track_status "$sid")"
            local duration; duration="$(get_story_track_duration "$sid")"

            local dur_str="—"
            [[ "$duration" != "0" ]] && dur_str="$(format_duration "$duration")"

            case "$status" in
                done)    stories_done=$((stories_done + 1)) ;;
                FAILED)  stories_failed=$((stories_failed + 1)) ;;
                skipped) stories_skipped=$((stories_skipped + 1)) ;;
            esac

            echo "| ${i} | ${sid} | ${dur_str} | ${status} |"
        done

        echo ""
        echo "## Timing"
        echo ""
        echo "- **Total wall time:** $(format_duration $total_wall) (includes CI wait between stories)"
        echo "- **Stories completed:** ${stories_done}/${STORY_COUNT}"
        (( stories_failed > 0 )) && echo "- **Stories failed:** ${stories_failed}"
        (( stories_skipped > 0 )) && echo "- **Stories skipped:** ${stories_skipped}"

    } > "$metrics_file"

    echo "$metrics_file"
}

# ============================================================
# Summary
# ============================================================

print_epic_summary() {
    local total_wall=$(( $(date +%s) - EPIC_START_TIME ))

    echo ""
    log_phase "Epic Pipeline Summary — Epic ${EPIC_ID}"
    echo ""

    printf "  ${BOLD}%-4s %-35s %-12s %-10s${NC}\n" "#" "Story" "Duration" "Status"
    printf "  %-4s %-35s %-12s %-10s\n" "----" "-----------------------------------" "------------" "----------"

    local i=0
    for sid in "${STORY_IDS[@]}"; do
        i=$((i + 1))
        local status; status="$(get_story_track_status "$sid")"
        local duration; duration="$(get_story_track_duration "$sid")"

        local dur_str="—"
        [[ "$duration" != "0" ]] && dur_str="$(format_duration "$duration")"

        local status_color=""
        case "$status" in
            done)     status_color="${GREEN}" ;;
            FAILED)   status_color="${RED}" ;;
            skipped)  status_color="${DIM}" ;;
            dry-run)  status_color="${DIM}" ;;
            *)        status_color="${NC}" ;;
        esac

        printf "  %-4s %-35s %-12s ${status_color}%-10s${NC}\n" \
            "$i" "$sid" "$dur_str" "$status"
    done

    echo ""
    echo -e "  ${BOLD}Total: $(format_duration $total_wall)${NC}"
    echo ""
}

# ============================================================
# Main Pipeline
# ============================================================

run_epic() {
    local skip_until_found=true
    [[ -z "$FROM_STORY" ]] && skip_until_found=false

    local i=0
    for idx in "${!STORY_IDS[@]}"; do
        local sid="${STORY_IDS[$idx]}"
        local sstatus="${STORY_STATUSES[$idx]}"
        i=$((i + 1))

        # Handle --from-story: skip until we find the target
        if [[ "$skip_until_found" == "true" ]]; then
            if [[ "$sid" == "$FROM_STORY" ]]; then
                skip_until_found=false
            else
                set_story_track_status "$sid" "skipped"
                log_skip "Story ${i}/${STORY_COUNT}: ${sid} (before --from-story)"
                continue
            fi
        fi

        # Skip done stories
        if [[ "$sstatus" == "done" ]]; then
            set_story_track_status "$sid" "skipped"
            log_skip "Story ${i}/${STORY_COUNT}: ${sid} (already done)"
            continue
        fi

        echo ""
        echo -e "${BOLD}${MAGENTA}───────────────────────────────────────────────────────────${NC}"
        echo -e "${BOLD}${MAGENTA}  Story ${i} of ${STORY_COUNT}: ${sid}${NC}"
        echo -e "${BOLD}${MAGENTA}───────────────────────────────────────────────────────────${NC}"

        # Dry run: just preview
        if [[ "$DRY_RUN" == "true" ]]; then
            echo -e "  ${DIM}[DRY RUN] Would run: ./auto-bmad-story.sh --story ${sid} --dry-run${NC}"
            set_story_track_status "$sid" "dry-run"
            continue
        fi

        # Ensure we're on main before the story script creates its branch
        ensure_on_main

        # Run the story pipeline
        local story_start; story_start=$(date +%s)
        local story_exit=0

        "$STORY_SCRIPT" --story "$sid" 2>&1 | tee -a "$EPIC_LOG" || true
        story_exit=${PIPESTATUS[0]}

        local story_end; story_end=$(date +%s)
        local story_duration=$((story_end - story_start))
        set_story_track_duration "$sid" "$story_duration"

        if (( story_exit != 0 )); then
            set_story_track_status "$sid" "FAILED"

            echo ""
            log_phase "Epic ${EPIC_ID} — STORY FAILED"
            echo ""
            echo -e "  Failed story:      ${BOLD}${sid}${NC} (story ${i} of ${STORY_COUNT})"
            echo -e "  Duration:          $(format_duration $story_duration)"

            local completed=0
            for s in "${STORY_IDS[@]}"; do
                [[ "$(get_story_track_status "$s")" == "done" ]] && completed=$((completed + 1))
            done
            echo -e "  Stories completed: ${completed}/${STORY_COUNT}"
            echo ""
            echo -e "  ${BOLD}Resume (story):${NC}  ${DIM}./auto-bmad-story.sh --story ${sid} --from-step <step>${NC}"
            echo -e "  ${BOLD}Resume (epic):${NC}   ${DIM}./auto-bmad-epic.sh --epic ${EPIC_ID} --from-story ${sid}${NC}"
            echo ""

            # Generate partial metrics
            generate_epic_metrics > /dev/null
            exit 1
        fi

        set_story_track_status "$sid" "done"
        log_ok "Story ${sid} completed in $(format_duration $story_duration)"

        # PR + merge between stories (not after the last one)
        if (( i < STORY_COUNT )) && [[ "$NO_MERGE" == "false" ]]; then
            commit_and_create_pr "$sid" || {
                echo ""
                log_error "PR/merge failed for story ${sid}"

                # Find next story for resume instructions
                local next_idx=$((idx + 1))
                while (( next_idx < STORY_COUNT )); do
                    if [[ "${STORY_STATUSES[$next_idx]}" != "done" ]]; then
                        break
                    fi
                    next_idx=$((next_idx + 1))
                done

                if (( next_idx < STORY_COUNT )); then
                    echo -e "  ${BOLD}Resume:${NC}  ${DIM}./auto-bmad-epic.sh --epic ${EPIC_ID} --from-story ${STORY_IDS[$next_idx]}${NC}"
                fi
                exit 1
            }
        elif (( i == STORY_COUNT )) && [[ "$NO_MERGE" == "false" ]]; then
            # Last story — still commit and PR, but don't need to wait for next story
            commit_and_create_pr "$sid" || {
                log_warn "Final story PR/merge failed — merge manually"
            }
        fi
    done

    if [[ "$skip_until_found" == "true" ]]; then
        log_error "Story ${FROM_STORY} not found in epic ${EPIC_ID}"
        exit 1
    fi
}

# ============================================================
# CLI Argument Parsing
# ============================================================

show_help() {
    cat <<HELPEOF
auto-bmad-epic.sh — Epic-Level BMAD Pipeline Orchestrator

Loops through all stories in an epic, delegating each to
./auto-bmad-story.sh, with PR + CI between stories.

Usage: ./auto-bmad-epic.sh [options]

Options:
  --epic EPIC_ID       Target epic number (e.g., 1). Auto-detects if omitted.
  --from-story ID      Resume from a specific story (e.g., 1-3-some-slug)
  --dry-run            Preview the full epic plan without executing
  --no-merge           Skip auto-PR/merge between stories (manual git)
  --help               Show this help message

Examples:
  ./auto-bmad-epic.sh                             # Run next epic
  ./auto-bmad-epic.sh --dry-run                   # Preview the pipeline
  ./auto-bmad-epic.sh --epic 2                    # Run epic 2
  ./auto-bmad-epic.sh --epic 1 --from-story 1-3-ci-pipeline  # Resume
  ./auto-bmad-epic.sh --no-merge                  # No auto-PR between stories
HELPEOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --epic)        EPIC_ID="$2"; shift 2 ;;
            --from-story)  FROM_STORY="$2"; shift 2 ;;
            --dry-run)     DRY_RUN=true; shift ;;
            --no-merge)    NO_MERGE=true; shift ;;
            --help|-h)     show_help; exit 0 ;;
            *)
                log_error "Unknown argument: $1"
                echo ""
                show_help
                exit 1
                ;;
        esac
    done
}

# ============================================================
# Main
# ============================================================

main() {
    parse_args "$@"

    preflight_checks

    if [[ -z "$EPIC_ID" ]]; then
        detect_next_epic
    fi

    collect_epic_stories
    validate_epic

    # Verify we're on main (unless dry run)
    if [[ "$DRY_RUN" != "true" ]]; then
        ensure_on_main
    fi

    EPIC_ARTIFACTS="${IMPL_ARTIFACTS}/auto-bmad/epic-${EPIC_ID}"
    EPIC_LOG="${EPIC_ARTIFACTS}/epic-pipeline.log"
    if [[ "$DRY_RUN" != "true" ]]; then
        mkdir -p "$EPIC_ARTIFACTS"
    fi

    EPIC_START_TIME=$(date +%s)

    # Count remaining stories
    local remaining=0
    for status in "${STORY_STATUSES[@]}"; do
        [[ "$status" != "done" ]] && remaining=$((remaining + 1))
    done

    echo ""
    echo -e "${BOLD}${MAGENTA}╔═══════════════════════════════╗${NC}"
    echo -e "${BOLD}${MAGENTA}║   Auto-BMAD Epic Pipeline     ║${NC}"
    echo -e "${BOLD}${MAGENTA}╚═══════════════════════════════╝${NC}"
    echo ""
    echo -e "  Epic:       ${BOLD}${EPIC_ID}${NC}"
    echo -e "  Stories:    ${BOLD}${STORY_COUNT} total, ${remaining} remaining${NC}"
    [[ "$DRY_RUN" == "true" ]]  && echo -e "  Mode:       ${YELLOW}DRY RUN${NC}"
    [[ "$NO_MERGE" == "true" ]] && echo -e "  Merge:      ${YELLOW}DISABLED${NC}"
    [[ -n "$FROM_STORY" ]]      && echo -e "  Resume:     from story ${BOLD}${FROM_STORY}${NC}"
    echo -e "  Artifacts:  ${DIM}${EPIC_ARTIFACTS}/${NC}"
    echo ""

    echo -e "  ${BOLD}Stories:${NC}"
    local i=0
    for idx in "${!STORY_IDS[@]}"; do
        i=$((i + 1))
        local sid="${STORY_IDS[$idx]}"
        local sstatus="${STORY_STATUSES[$idx]}"
        local marker="  "
        [[ "$sstatus" == "done" ]] && marker="${DIM}✓ "
        [[ "$sid" == "$FROM_STORY" ]] && marker="${YELLOW}► "
        echo -e "    ${marker}${i}. ${sid} ${DIM}(${sstatus})${NC}"
    done

    run_epic

    # Generate metrics
    if [[ "$DRY_RUN" != "true" ]]; then
        local metrics_file
        metrics_file="$(generate_epic_metrics)"
        log_ok "Epic metrics: ${metrics_file}"
    fi

    print_epic_summary

    # Print retrospective summary if this was a full run (not dry run)
    if [[ "$DRY_RUN" != "true" ]]; then
        print_retro_summary
    fi

    # Clean up epic log on success
    if [[ "$DRY_RUN" != "true" ]]; then
        rm -f "$EPIC_LOG"
    fi
}

main "$@"
