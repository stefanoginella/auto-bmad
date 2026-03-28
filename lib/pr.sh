#!/usr/bin/env bash
# lib/pr.sh — PR lifecycle and git workflow for epic pipelines
# Sourced by auto-bmad-epic
#
# Requires: lib/core.sh, lib/git.sh sourced, PROJECT_ROOT set
# Reads globals: IMPL_ARTIFACTS EPIC_ID PR_SAFETY_TIMEOUT PR_POLL_INTERVAL PR_EMPTY_CHECKS_GRACE_POLLS
#   (PR_* values populated from conf/pipeline.conf by auto-bmad-epic)
#
# Exports:
#   ensure_on_main                              — switch to main branch
#   extract_commit_message <story_id>           — extract commit msg from story file
#   commit_and_create_pr <story_id>             — finalize commit, push, create PR, wait for merge
#   wait_for_merge <branch> <pr_url> <auto_merge>

[[ -n "${_PR_SH_LOADED:-}" ]] && return 0
_PR_SH_LOADED=1

ensure_on_main() {
    local current_branch
    current_branch="$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null)" || {
        log_warn "Not a git repository — skipping branch check"
        return 0
    }

    if [[ "$current_branch" == "main" || "$current_branch" == "master" ]]; then
        return 0
    fi

    # If on a story branch, try to switch to main/master
    if [[ "$current_branch" == story/* ]]; then
        local main_branch="main"
        git -C "$PROJECT_ROOT" show-ref --verify --quiet "refs/heads/main" 2>/dev/null \
            || main_branch="master"
        log_warn "On branch ${current_branch} — switching to ${main_branch}"
        git -C "$PROJECT_ROOT" checkout "$main_branch" 2>/dev/null || {
            log_error "Failed to switch to ${main_branch}. Resolve manually."
            exit 1
        }
        git -C "$PROJECT_ROOT" pull origin "$main_branch" --ff-only 2>/dev/null || true
        return 0
    fi

    log_warn "On unexpected branch: ${current_branch}"
    if ! _confirm "    Continue anyway? [y/N] "; then
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
        log_warn "No story file found for ${story_id} — using fallback commit message" >&2
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
        log_warn "No conventional commit message found in story file — using fallback" >&2
        echo "feat(epic-${EPIC_ID}): implement story ${story_id}"
    fi
}

commit_and_create_pr() {
    local story_id="$1"

    echo ""
    echo -e "  ${BOLD}${BLUE}>>> Git: Finalize commit & PR for ${story_id}${NC}"

    # Extract the real commit message from the story file
    local commit_msg
    commit_msg="$(extract_commit_message "$story_id")"

    # Stage any remaining changes and amend the WIP commit with the real message
    local has_changes=false
    if ! _git_is_clean; then
        has_changes=true
    fi

    if [[ "$has_changes" == "true" ]]; then
        git -C "$PROJECT_ROOT" add -A
    fi

    # Amend the WIP commit left by story script with the real commit message
    git -C "$PROJECT_ROOT" commit --amend -m "$(cat <<EOF
${commit_msg}
EOF
    )" --no-verify --quiet || {
        log_warn "Commit amend failed — trying fresh commit"
        git -C "$PROJECT_ROOT" commit -m "$(cat <<EOF
${commit_msg}
EOF
        )" --no-verify --quiet || log_warn "Commit failed (maybe nothing to commit)"
    }
    log_ok "Commit finalized"

    # Push branch
    local branch; branch="$(_resolve_branch_name "$story_id")"
    git -C "$PROJECT_ROOT" push -u origin "$branch" 2>&1 | tail -2
    log_ok "Pushed to origin/${branch}"

    # Create PR — use the first line of commit message as title
    local pr_title="${commit_msg%%$'\n'*}"
    local pr_url
    pr_url=$(gh pr create \
        --title "$pr_title" \
        --body "$(cat <<PREOF
## Summary

Auto-generated by auto-bmad-epic pipeline.
Story: ${story_id}. See story file for full details.
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
    local auto_merge=true
    gh pr merge --auto --squash "$branch" 2>&1 || {
        auto_merge=false
        log_warn "Auto-merge not available — will merge directly after CI passes"
    }

    # Poll for merge
    wait_for_merge "$branch" "$pr_url" "$auto_merge"
}

wait_for_merge() {
    local branch="$1"
    local pr_url="${2:-}"
    local auto_merge="${3:-true}"
    local elapsed=0
    local last_status_line=""
    local empty_checks_polls=0

    echo -e "  ${DIM}Waiting for CI checks...${NC}"

    while (( elapsed < PR_SAFETY_TIMEOUT )); do
        sleep "$PR_POLL_INTERVAL"
        elapsed=$((elapsed + PR_POLL_INTERVAL))

        # --- Check PR state ---
        local state
        state=$(gh pr view "$branch" --json state -q '.state' 2>/dev/null || echo "UNKNOWN")

        case "$state" in
            MERGED)
                [[ -n "$last_status_line" ]] && echo ""  # clear \r line
                log_ok "PR merged after $(format_duration $elapsed)"
                git -C "$PROJECT_ROOT" checkout main 2>/dev/null
                git -C "$PROJECT_ROOT" pull origin main --ff-only 2>/dev/null
                git -C "$PROJECT_ROOT" branch -d "$branch" 2>/dev/null || true
                return 0
                ;;
            CLOSED)
                [[ -n "$last_status_line" ]] && echo ""
                log_error "PR was closed without merging"
                return 1
                ;;
            UNKNOWN)
                log_warn "Could not check PR status (elapsed: $(format_duration $elapsed))"
                continue
                ;;
        esac

        # --- PR still open — inspect CI checks ---
        local total=0 passed=0 failed=0 pending=0 warnings=0
        local checks_output=""
        if ! checks_output=$(gh pr checks "$branch" --json state -q '.[].state' 2>/dev/null); then
            [[ -n "$last_status_line" ]] && echo ""
            log_warn "Could not read PR checks yet (elapsed: $(format_duration $elapsed))"
            continue
        fi

        if [[ -z "$checks_output" ]]; then
            empty_checks_polls=$((empty_checks_polls + 1))

            if [[ "$auto_merge" == "false" && $empty_checks_polls -ge $PR_EMPTY_CHECKS_GRACE_POLLS ]]; then
                [[ -n "$last_status_line" ]] && echo ""
                log_warn "No CI checks detected after $(format_duration $((empty_checks_polls * PR_POLL_INTERVAL))) — merging directly"
                gh pr merge --squash "$branch" 2>&1 || {
                    log_error "Direct merge failed"
                    [[ -n "$pr_url" ]] && echo -e "    PR: ${pr_url}"
                    return 1
                }
                continue
            fi

            last_status_line="  ${DIM}  CI: waiting for checks to appear — $(format_duration $elapsed) elapsed${NC}"
            printf "\r%-80s" ""  # clear previous line
            printf "\r%b" "$last_status_line"
            continue
        fi

        empty_checks_polls=0
        local cs
        while IFS= read -r cs; do
            [[ -z "$cs" ]] && continue
            (( total++ ))
            case "$cs" in
                SUCCESS)                                      (( passed++ )) ;;
                FAILURE|ERROR|ACTION_REQUIRED|TIMED_OUT)      (( failed++ )) ;;
                NEUTRAL|SKIPPED|STALE|CANCELLED)              (( warnings++ )) ;;
                *)                                            (( pending++ )) ;;
            esac
        done <<< "$checks_output"

        # --- Decision logic ---
        if (( failed > 0 && pending == 0 )); then
            [[ -n "$last_status_line" ]] && echo ""
            echo ""
            log_error "CI failed on PR for story ${branch#story/} (${failed} failed, ${passed} passed)"
            [[ -n "$pr_url" ]] && echo -e "    PR: ${pr_url}"
            echo ""
            echo -e "    Fix CI, merge the PR manually, then resume:"
            echo -e "    ${DIM}auto-bmad epic --epic ${EPIC_ID} --from-story <next-story>${NC}"

            # Track CI failure as a GitHub Issue for visibility
            gh issue create \
                --title "CI failed: story ${branch#story/}" \
                --label "ci-failure" \
                --body "$(cat <<ISSEOF
PR: ${pr_url:-unknown}
Failed: ${failed} checks, Passed: ${passed} checks
Epic: ${EPIC_ID:-unknown}

Resume after fixing:
\`auto-bmad epic --epic ${EPIC_ID} --from-story <next-story>\`
ISSEOF
                )" 2>/dev/null || true

            return 1

        elif (( pending == 0 && failed == 0 )); then
            if (( warnings > 0 )); then
                [[ -n "$last_status_line" ]] && echo ""
                log_warn "CI passed with warnings (${passed} passed, ${warnings} neutral/skipped)"
            fi
            if [[ "$auto_merge" == "false" ]]; then
                [[ -n "$last_status_line" ]] && echo ""
                log_ok "CI passed (${passed}/${total}) — merging"
                gh pr merge --squash "$branch" 2>&1 || {
                    log_error "Merge failed"
                    [[ -n "$pr_url" ]] && echo -e "    PR: ${pr_url}"
                    return 1
                }
            fi
            continue
        fi

        # --- Still pending — update status line ---
        last_status_line="  ${DIM}  CI: ${passed} passed, ${pending} pending, ${failed} failed — $(format_duration $elapsed) elapsed${NC}"
        printf "\r%-80s" ""  # clear previous line
        printf "\r%b" "$last_status_line"
    done

    [[ -n "$last_status_line" ]] && echo ""
    echo ""
    log_error "Safety timeout reached ($(format_duration $PR_SAFETY_TIMEOUT)) — CI may be stuck"
    [[ -n "$pr_url" ]] && echo -e "    PR: ${pr_url}"
    echo -e "    Check for stuck runners, then merge manually and resume with --from-story"

    # Track CI timeout as a GitHub Issue for visibility
    gh issue create \
        --title "CI timeout: story ${branch#story/}" \
        --label "ci-timeout" \
        --body "$(cat <<ISSEOF
PR: ${pr_url:-unknown}
Timeout after $(format_duration $PR_SAFETY_TIMEOUT)
Epic: ${EPIC_ID:-unknown}

Check for stuck runners, then merge manually and resume with --from-story.
ISSEOF
        )" 2>/dev/null || true

    return 1
}
