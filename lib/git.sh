#!/usr/bin/env bash
# lib/git.sh — Git operations for story pipelines
# Sourced by auto-bmad-story (and indirectly by epic via story)
#
# Requires: lib/core.sh sourced, PROJECT_ROOT set
# Reads globals: DRY_RUN SKIP_GIT STORY_ID STORY_SHORT_ID COMMIT_BASELINE FROM_STEP EPIC_ID
#
# Exports:
#   git_checkpoint <label>        — WIP commit if changes exist
#   git_squash_pipeline           — soft-reset to COMMIT_BASELINE
#   extract_story_commit_msg      — extract commit msg from story file
#   check_git_branch              — ensure correct branch + post-checkout gates
#   preflight_git_checks          — 7-gate pre-flight (tools, tree, merge, freshness, shadow, divergence, conflict)
#   _resolve_branch_name <sid>    — expand cfg_pip_branch_pattern for a story ID
#
# Gate architecture (preflight_git_checks + check_git_branch):
#   Gate 0: Required tools       — hard gate, checks gh auth + git version
#   Gate 1: Dirty working tree   — soft [c/f/a], fix: git stash
#   Gate 2: Previous story merged — soft [c/a], advisory only (no auto-merge)
#   Gate 3: Main freshness       — soft [c/f/a], fix: git pull --ff-only
#   Gate 4: Remote branch shadow — soft [c/f/a], fix: git checkout --track
#   Gate 5: Branch divergence    — soft [c/f/a], fix: git rebase main (post-checkout)
#   Gate 6: Conflict dry-run     — soft [c/a], no auto-fix (post-checkout)

[[ -n "${_GIT_SH_LOADED:-}" ]] && return 0
_GIT_SH_LOADED=1

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

# Ensure we're on the correct story branch, or create one from main.
# Called after STORY_ID is known.
check_git_branch() {
    [[ "$SKIP_GIT" == "true" ]] && { log_skip "Git branch check — --skip-git"; return 0; }
    [[ "$DRY_RUN" == "true" ]] && { log_skip "Git branch check — --dry-run"; return 0; }

    local current_branch expected_branch
    expected_branch="$(_resolve_branch_name "$STORY_ID")"
    current_branch="$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null)" || {
        log_warn "Not a git repository — skipping branch check"
        return 0
    }

    # Already on the right branch
    if [[ "$current_branch" == "$expected_branch" ]]; then
        log_ok "On branch ${expected_branch}"
        _post_checkout_gates "$expected_branch"
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

    # Post-checkout gates (run after we're on the story branch)
    _post_checkout_gates "$expected_branch"
}

# Gates that run after branch selection, when on a story branch.
# Gate 5: Branch divergence from main
# Gate 6: Merge conflict dry-run
_post_checkout_gates() {
    local branch="$1"
    local main_ref
    main_ref="$(_resolve_main_ref)"

    local current_branch
    current_branch="$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null)"

    # Only run on story branches (not main)
    [[ "$current_branch" == "main" || "$current_branch" == "master" ]] && return 0
    # Skip for brand-new branches (no divergence possible)
    local behind_count
    behind_count="$(git -C "$PROJECT_ROOT" rev-list HEAD.."${main_ref}" --count 2>/dev/null || echo 0)"
    (( behind_count == 0 )) && return 0

    # ── Gate 5: Branch divergence from main (soft gate) ─────────
    echo ""
    log_warn "Branch ${current_branch} is ${behind_count} commit(s) behind ${main_ref}"
    echo -e "    Your branch may be missing recent changes from ${BOLD}${main_ref}${NC}."
    _confirm_cfa \
        "Branch behind main" \
        "git rebase ${main_ref}" \
        "git -C '$PROJECT_ROOT' rebase '${main_ref}'"

    # ── Gate 6: Merge conflict dry-run (soft gate, no auto-fix) ─
    # Try a no-commit merge to detect conflicts early
    if git -C "$PROJECT_ROOT" merge --no-commit --no-ff "$main_ref" &>/dev/null 2>&1; then
        git -C "$PROJECT_ROOT" merge --abort &>/dev/null 2>&1 || true
    else
        git -C "$PROJECT_ROOT" merge --abort &>/dev/null 2>&1 || true
        echo ""
        log_warn "Merge conflicts detected with ${main_ref}"
        echo -e "    Merging ${BOLD}${main_ref}${NC} into this branch will require conflict resolution."
        echo -e "    Resolve now to avoid surprises at PR time."
        _confirm_cfa \
            "Merge conflicts with main" \
            "" ""  # no auto-fix — conflicts need human judgment
    fi
}

# Resolve the default branch name (main or master).
_resolve_main_ref() {
    if git -C "$PROJECT_ROOT" show-ref --verify --quiet "refs/heads/main" 2>/dev/null; then
        echo "main"
    elif git -C "$PROJECT_ROOT" show-ref --verify --quiet "refs/heads/master" 2>/dev/null; then
        echo "master"
    else
        echo "main"
    fi
}

# Resolve branch name for a given story ID using cfg_pip_branch_pattern.
# Usage: _resolve_branch_name <story_id>
_resolve_branch_name() {
    local _sid="$1"
    local _tmpl="${cfg_pip_branch_pattern:-story/\${STORY_ID}}"
    local STORY_ID="$_sid"
    eval "echo \"${_tmpl}\""
}

# Validates git state before check_git_branch() selects/creates branches.
# Gates are ordered by dependency — earliest failures abort cheapest.
#
# Gate 0: Required tools      (hard — no fix)
# Gate 1: Dirty working tree  (soft — fix: git stash)
# Gate 2: Previous story PR   (soft — advisory only, no auto-merge)
# Gate 3: Main freshness      (soft — fix: git pull --ff-only)
# Gate 4: Remote branch shadow(soft — fix: git checkout --track)
preflight_git_checks() {
    [[ "$SKIP_GIT" == "true" ]] && { log_skip "Git pre-flight — --skip-git"; return 0; }
    [[ "$DRY_RUN" == "true" ]] && { log_skip "Git pre-flight — --dry-run"; return 0; }

    # Verify we're in a git repo
    git -C "$PROJECT_ROOT" rev-parse --git-dir &>/dev/null || {
        log_warn "Not a git repository — skipping git pre-flight"
        return 0
    }

    # ── Gate 0: Required tools (hard gate) ──────────────────────
    local gate0_errors=0

    if ! command -v gh &>/dev/null; then
        log_error "Required tool missing: gh (GitHub CLI)"
        echo -e "    ${DIM}Install: brew install gh && gh auth login${NC}"
        gate0_errors=$((gate0_errors + 1))
    elif ! gh auth status &>/dev/null 2>&1; then
        log_error "GitHub CLI not authenticated"
        echo -e "    ${DIM}Run: gh auth login${NC}"
        gate0_errors=$((gate0_errors + 1))
    else
        log_ok "gh authenticated"
    fi

    local git_version
    git_version="$(git --version 2>/dev/null | sed 's/[^0-9.]//g')"
    local git_major git_minor
    git_major="${git_version%%.*}"
    git_minor="${git_version#*.}"; git_minor="${git_minor%%.*}"
    local req_version="${cfg_pip_min_git_version:-2.25}"
    local req_major="${req_version%%.*}" req_minor="${req_version#*.}"
    req_minor="${req_minor%%.*}"
    if (( git_major < req_major )) || { (( git_major == req_major )) && (( git_minor < req_minor )); }; then
        log_error "git version ${git_version} too old (need >= ${req_version})"
        gate0_errors=$((gate0_errors + 1))
    else
        log_ok "git ${git_version}"
    fi

    if (( gate0_errors > 0 )); then
        echo ""
        log_error "Required tools check failed — cannot proceed"
        exit 1
    fi

    local current_branch
    current_branch="$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null)"
    local main_ref
    main_ref="$(_resolve_main_ref)"

    # ── Gate 1: Dirty working tree (soft gate) ──────────────────
    if ! git -C "$PROJECT_ROOT" diff --quiet 2>/dev/null || \
       ! git -C "$PROJECT_ROOT" diff --cached --quiet 2>/dev/null || \
       [[ -n "$(git -C "$PROJECT_ROOT" ls-files --others --exclude-standard 2>/dev/null)" ]]; then
        echo ""
        log_warn "Working tree has uncommitted changes"
        echo -e "    Uncommitted files may leak into the story branch."
        _confirm_cfa \
            "Dirty working tree" \
            "git stash push -m 'auto-bmad: pre-pipeline stash'" \
            "git -C '$PROJECT_ROOT' stash push -m 'auto-bmad: pre-pipeline stash'"
    fi

    # ── Gate 2: Previous story merged (soft gate) ───────────────
    local prev_story
    prev_story="$(_find_previous_story)"
    # Skip cross-epic check — previous epic's merge status is irrelevant
    if [[ -n "$prev_story" ]]; then
        local _prev_epic="${prev_story%%-*}"
        [[ "$_prev_epic" != "$EPIC_ID" ]] && prev_story=""
    fi
    if [[ -n "$prev_story" ]]; then
        local prev_branch
        prev_branch="$(_resolve_branch_name "$prev_story")"
        local prev_merged=false

        # Primary: check GitHub for a merged PR
        local pr_number
        pr_number="$(gh pr list --head "$prev_branch" --state merged --json number --jq '.[0].number' 2>/dev/null || echo "")"
        if [[ -n "$pr_number" ]]; then
            prev_merged=true
        fi

        # Fallback: check if prev branch is ancestor of main (covers manual merges)
        if [[ "$prev_merged" == "false" ]]; then
            if git -C "$PROJECT_ROOT" show-ref --verify --quiet "refs/heads/${prev_branch}" 2>/dev/null; then
                if git -C "$PROJECT_ROOT" merge-base --is-ancestor "refs/heads/${prev_branch}" "refs/heads/${main_ref}" 2>/dev/null; then
                    prev_merged=true
                fi
            else
                # Branch doesn't exist locally — check for squash commit on main
                local prev_epic="${prev_story%%-*}"
                local prev_remainder="${prev_story#*-}"
                local prev_num="${prev_remainder%%-*}"
                local short_id="${prev_epic}-${prev_num}"
                if git -C "$PROJECT_ROOT" log "$main_ref" --oneline --grep="(${short_id})" -1 2>/dev/null | grep -q .; then
                    prev_merged=true
                fi
            fi
        fi

        if [[ "$prev_merged" == "false" ]]; then
            echo ""
            log_warn "Previous story not merged: ${prev_story}"
            echo -e "    Story ${BOLD}${STORY_ID}${NC} may depend on work from ${BOLD}${prev_story}${NC}."
            echo -e "    No merged PR found and branch is not an ancestor of ${BOLD}${main_ref}${NC}."
            echo ""
            echo -e "    ${DIM}To merge manually:${NC}"
            echo -e "    ${DIM}  gh pr merge --squash \$(gh pr list --head ${prev_branch} --json number --jq '.[0].number')${NC}"
            _confirm_cfa \
                "Previous story not merged" \
                "" ""
        fi
    fi

    # ── Gate 3: Main freshness (soft gate) ──────────────────────
    if [[ "$current_branch" == "main" || "$current_branch" == "master" ]]; then
        git -C "$PROJECT_ROOT" fetch origin "$current_branch" --quiet 2>/dev/null || true
        local behind
        behind="$(git -C "$PROJECT_ROOT" rev-list HEAD..origin/"$current_branch" --count 2>/dev/null || echo 0)"
        if (( behind > 0 )); then
            echo ""
            log_warn "${current_branch} is ${behind} commit(s) behind origin/${current_branch}"
            echo -e "    You may be branching from stale code."
            _confirm_cfa \
                "Stale main" \
                "git pull origin ${current_branch} --ff-only" \
                "git -C '$PROJECT_ROOT' pull origin '${current_branch}' --ff-only"
        fi
    fi

    # ── Gate 4: Remote branch shadow (soft gate) ────────────────
    local expected_branch
    expected_branch="$(_resolve_branch_name "$STORY_ID")"
    if ! git -C "$PROJECT_ROOT" show-ref --verify --quiet "refs/heads/${expected_branch}" 2>/dev/null; then
        if git -C "$PROJECT_ROOT" ls-remote --exit-code origin "refs/heads/${expected_branch}" &>/dev/null 2>&1; then
            echo ""
            log_warn "Branch ${expected_branch} exists on remote but not locally"
            echo -e "    Someone may have already started this story."
            _confirm_cfa \
                "Remote branch shadow" \
                "git checkout --track origin/${expected_branch}" \
                "git -C '$PROJECT_ROOT' fetch origin '${expected_branch}' && git -C '$PROJECT_ROOT' checkout --track 'origin/${expected_branch}'"
        fi
    fi
}
