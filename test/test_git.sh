#!/usr/bin/env bash
# test/test_git.sh — Tests for git.sh (checkpoint, squash, commit msg, branch resolution)
# Run: bash test/test_git.sh
#
# Tests git operations using temporary git repos. Skips interactive gate tests
# (check_git_branch, preflight_git_checks) that require user prompts.

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

echo ""
echo -e "${_T_BOLD}Git tests (checkpoint, squash, commit msg)${_T_NC}"
echo ""

# --- Bootstrap environment ---
source "${REPO_ROOT}/lib/core.sh"
INTERACTIVE=false
source "${REPO_ROOT}/lib/tracking.sh"

# Minimal INSTALL_DIR with profiles.conf
INSTALL_DIR="$(make_test_tmpdir)"
mkdir -p "${INSTALL_DIR}/conf"
cat > "${INSTALL_DIR}/conf/profiles.conf" <<'EOF'
@mock-claude  claude  opus  high  -
1.1  @mock-claude
EOF

# Prevent user config interference
export XDG_CONFIG_HOME="$(make_test_tmpdir)"

# Globals expected by config.sh
PIPELINE_LOG=""
PIPELINE_START_TIME=$(date +%s)

source "${REPO_ROOT}/lib/config.sh"

# Don't source detection.sh here — git.sh calls _find_previous_story from it
# but only in preflight_git_checks which we don't test.
# Instead, stub _find_previous_story.
_find_previous_story() { echo ""; }

source "${REPO_ROOT}/lib/git.sh"

# --- Helper: create a fresh temp git repo ---
_make_git_repo() {
    local repo
    repo="$(make_test_tmpdir)"
    git -C "$repo" init --quiet
    git -C "$repo" config user.email "test@test.com"
    git -C "$repo" config user.name "Test"
    # Initial commit so HEAD exists
    echo "init" > "${repo}/README.md"
    git -C "$repo" add -A
    git -C "$repo" commit -m "initial commit" --quiet
    echo "$repo"
}

# ═══════════════════════════════════════════════════
# _git_is_clean
# ═══════════════════════════════════════════════════

echo -e "${_T_BOLD}  Working tree cleanliness${_T_NC}"

test_begin "git_is_clean: clean repo returns 0"
PROJECT_ROOT="$(_make_git_repo)"
if _git_is_clean; then
    assert_exit_ok
else
    test_fail "clean repo should return 0"
fi

test_begin "git_is_clean: unstaged changes detected"
echo "modified" >> "${PROJECT_ROOT}/README.md"
if _git_is_clean; then
    test_fail "should detect unstaged changes"
else
    assert_exit_fail
fi

test_begin "git_is_clean: staged changes detected"
PROJECT_ROOT="$(_make_git_repo)"
echo "new content" > "${PROJECT_ROOT}/staged.txt"
git -C "$PROJECT_ROOT" add staged.txt
if _git_is_clean; then
    test_fail "should detect staged changes"
else
    assert_exit_fail
fi

test_begin "git_is_clean: untracked files detected"
PROJECT_ROOT="$(_make_git_repo)"
echo "untracked" > "${PROJECT_ROOT}/new-file.txt"
if _git_is_clean; then
    test_fail "should detect untracked files"
else
    assert_exit_fail
fi

# ═══════════════════════════════════════════════════
# _resolve_main_ref
# ═══════════════════════════════════════════════════

echo ""
echo -e "${_T_BOLD}  Main ref resolution${_T_NC}"

test_begin "resolve_main_ref: returns 'main' when main branch exists"
PROJECT_ROOT="$(_make_git_repo)"
# Default branch is usually main; ensure it
git -C "$PROJECT_ROOT" branch -M main 2>/dev/null || true
result="$(_resolve_main_ref)"
assert_eq "main" "$result"

test_begin "resolve_main_ref: returns 'master' when only master exists"
PROJECT_ROOT="$(_make_git_repo)"
git -C "$PROJECT_ROOT" branch -M master
result="$(_resolve_main_ref)"
assert_eq "master" "$result"

test_begin "resolve_main_ref: defaults to 'main' when neither exists"
PROJECT_ROOT="$(_make_git_repo)"
# Checkout a detached HEAD so neither main nor master exists as a branch name
local_sha="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
git -C "$PROJECT_ROOT" checkout --detach "$local_sha" 2>/dev/null
git -C "$PROJECT_ROOT" branch -D main 2>/dev/null || true
git -C "$PROJECT_ROOT" branch -D master 2>/dev/null || true
result="$(_resolve_main_ref)"
assert_eq "main" "$result"

# ═══════════════════════════════════════════════════
# git_checkpoint
# ═══════════════════════════════════════════════════

echo ""
echo -e "${_T_BOLD}  Checkpoint commits${_T_NC}"

test_begin "checkpoint: creates WIP commit when changes exist"
PROJECT_ROOT="$(_make_git_repo)"
git -C "$PROJECT_ROOT" branch -M main 2>/dev/null || true
DRY_RUN=false
SKIP_GIT=false
STORY_SHORT_ID="1-1"
LAST_COMPLETED_STEP=""
echo "code" > "${PROJECT_ROOT}/new-file.sh"
git_checkpoint "Phase 1"
# Should have a new commit with the WIP message
last_msg="$(git -C "$PROJECT_ROOT" log -1 --format=%s)"
assert_match "wip\(1-1\): Phase 1" "$last_msg"

test_begin "checkpoint: includes step marker when LAST_COMPLETED_STEP set"
echo "more code" >> "${PROJECT_ROOT}/new-file.sh"
LAST_COMPLETED_STEP="1.4"
git_checkpoint "Phase 1"
last_msg="$(git -C "$PROJECT_ROOT" log -1 --format=%s)"
assert_match "through 1.4" "$last_msg"

test_begin "checkpoint: skips when no changes"
before="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
git_checkpoint "Phase 2 (no changes)"
after="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
assert_eq "$before" "$after"

test_begin "checkpoint: skips in dry-run mode"
echo "dry-run change" > "${PROJECT_ROOT}/dry.txt"
DRY_RUN=true
before="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
git_checkpoint "Phase X"
after="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
assert_eq "$before" "$after"
DRY_RUN=false
# Clean up for next tests
rm -f "${PROJECT_ROOT}/dry.txt"

test_begin "checkpoint: skips when SKIP_GIT=true"
echo "skip-git change" > "${PROJECT_ROOT}/skip.txt"
SKIP_GIT=true
before="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
git_checkpoint "Phase Y"
after="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
assert_eq "$before" "$after"
SKIP_GIT=false
rm -f "${PROJECT_ROOT}/skip.txt"

# ═══════════════════════════════════════════════════
# git_squash_pipeline
# ═══════════════════════════════════════════════════

echo ""
echo -e "${_T_BOLD}  Pipeline squash${_T_NC}"

test_begin "squash: collapses multiple checkpoints into one commit"
PROJECT_ROOT="$(_make_git_repo)"
git -C "$PROJECT_ROOT" branch -M main 2>/dev/null || true
DRY_RUN=false
SKIP_GIT=false
STORY_SHORT_ID="2-1"
LAST_COMPLETED_STEP=""
COMMIT_BASELINE="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
# Create 3 checkpoint commits
echo "phase1" > "${PROJECT_ROOT}/p1.txt"
git_checkpoint "Phase 1"
echo "phase2" > "${PROJECT_ROOT}/p2.txt"
git_checkpoint "Phase 2"
echo "phase3" > "${PROJECT_ROOT}/p3.txt"
git_checkpoint "Phase 3"
# Should be 4 commits total (initial + 3 checkpoints)
count_before=$(git -C "$PROJECT_ROOT" rev-list --count HEAD)
assert_eq "4" "$count_before"

test_begin "squash: reduces to baseline+1 commit"
git_squash_pipeline 2>/dev/null
count_after=$(git -C "$PROJECT_ROOT" rev-list --count HEAD)
# Should be 2: initial + squashed
assert_eq "2" "$count_after"

test_begin "squash: preserves all file changes"
# All 3 phase files should exist
if [[ -f "${PROJECT_ROOT}/p1.txt" && -f "${PROJECT_ROOT}/p2.txt" && -f "${PROJECT_ROOT}/p3.txt" ]]; then
    assert_exit_ok
else
    test_fail "squash lost file changes"
fi

test_begin "squash: final commit message is pipeline complete"
last_msg="$(git -C "$PROJECT_ROOT" log -1 --format=%s)"
assert_match "pipeline complete" "$last_msg"

test_begin "squash: no-op when HEAD == COMMIT_BASELINE"
PROJECT_ROOT="$(_make_git_repo)"
COMMIT_BASELINE="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
before="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
git_squash_pipeline 2>/dev/null
after="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
assert_eq "$before" "$after"

test_begin "squash: skips in dry-run mode"
PROJECT_ROOT="$(_make_git_repo)"
COMMIT_BASELINE="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
echo "change" > "${PROJECT_ROOT}/file.txt"
git_checkpoint "Phase 1"
DRY_RUN=true
head_before="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
git_squash_pipeline 2>/dev/null
head_after="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
# HEAD should NOT change in dry-run
assert_eq "$head_before" "$head_after"
DRY_RUN=false

# ═══════════════════════════════════════════════════
# extract_story_commit_msg
# ═══════════════════════════════════════════════════

echo ""
echo -e "${_T_BOLD}  Commit message extraction${_T_NC}"

test_begin "commit msg: extracts from story file code block"
STORY_FILE_PATH="$(make_test_tmpdir)/story.md"
cat > "$STORY_FILE_PATH" <<'EOF'
# Story

Some content.

## Auto-bmad Completion

```
feat(1-1): add user authentication
```

## Change Log
EOF
STORY_ID="1-1-auth"
STORY_SHORT_ID="1-1"
msg="$(extract_story_commit_msg)"
assert_eq "feat(1-1): add user authentication" "$msg"

test_begin "commit msg: extracts multi-line message"
cat > "$STORY_FILE_PATH" <<'EOF'
## Auto-bmad Completion

```
feat(2-3): implement data pipeline

- Added CSV parser
- Integrated with S3 bucket
```

## Change Log
EOF
msg="$(extract_story_commit_msg)"
assert_match "feat\(2-3\): implement data pipeline" "$msg"

test_begin "commit msg: fallback when no completion section"
cat > "$STORY_FILE_PATH" <<'EOF'
# Story
Just a story, no completion section.
EOF
STORY_ID="3-2-user-dashboard"
STORY_SHORT_ID="3-2"
msg="$(extract_story_commit_msg)"
assert_eq "feat(3-2): user dashboard" "$msg"

test_begin "commit msg: fallback when story file missing"
STORY_FILE_PATH="/nonexistent/story.md"
STORY_ID="1-4-fix-login"
STORY_SHORT_ID="1-4"
msg="$(extract_story_commit_msg)"
assert_eq "feat(1-4): fix login" "$msg"

test_begin "commit msg: fallback when STORY_FILE_PATH is empty"
STORY_FILE_PATH=""
STORY_ID="2-1-api-refactor"
STORY_SHORT_ID="2-1"
msg="$(extract_story_commit_msg)"
assert_eq "feat(2-1): api refactor" "$msg"

test_begin "commit msg: fallback preserves multi-segment slugs"
STORY_FILE_PATH=""
STORY_ID="5-3-add-dark-mode-toggle"
STORY_SHORT_ID="5-3"
msg="$(extract_story_commit_msg)"
assert_eq "feat(5-3): add dark mode toggle" "$msg"

# ═══════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════

test_summary
