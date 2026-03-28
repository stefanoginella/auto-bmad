#!/usr/bin/env bash
# test/test_detection.sh — Unit tests for lib/detection.sh
# Run: bash test/test_detection.sh

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

echo ""
echo -e "${_T_BOLD}Detection tests${_T_NC}"
echo ""

# --- Bootstrap minimal environment for detection.sh ---
# detection.sh needs core.sh (logging) and a few globals.
source "${REPO_ROOT}/lib/core.sh"
INTERACTIVE=false

# IMPL_ARTIFACTS needs to be a real directory for _resolve_story_file_path
_IMPL_DIR="$(make_test_tmpdir)"
IMPL_ARTIFACTS="$_IMPL_DIR"

source "${REPO_ROOT}/lib/detection.sh"

# Helper: write a sprint-status file and point SPRINT_STATUS at it
_tmp="$(make_test_tmpdir)"
_sf="${_tmp}/sprint-status.yaml"
SPRINT_STATUS="$_sf"

write_status() {
    cat > "$_sf"
}

# Helper: create fake story files in IMPL_ARTIFACTS
make_story_file() {
    touch "${_IMPL_DIR}/$1.md"
}

# ═══════════════════════════════════════════════════
# detect_next_story
# ═══════════════════════════════════════════════════

test_begin "detect_next_story: picks first backlog story"
write_status <<'EOF'
epic-1: in-progress
1-1-setup: done
1-2-auth: backlog
1-3-api: backlog
EOF
detect_next_story
assert_eq "1-2-auth" "$STORY_ID"

test_begin "detect_next_story: prefers in-progress over backlog"
write_status <<'EOF'
epic-1: in-progress
1-1-setup: done
1-2-auth: in-progress
1-3-api: backlog
EOF
detect_next_story
assert_eq "1-2-auth" "$STORY_ID"

test_begin "detect_next_story: picks first in-progress when multiple"
write_status <<'EOF'
epic-1: in-progress
1-1-setup: in-progress
1-2-auth: in-progress
EOF
detect_next_story
assert_eq "1-1-setup" "$STORY_ID"

test_begin "detect_next_story: skips done stories"
write_status <<'EOF'
epic-1: in-progress
1-1-setup: done
1-2-auth: done
1-3-api: backlog
EOF
detect_next_story
assert_eq "1-3-api" "$STORY_ID"

test_begin "detect_next_story: fails when all stories are done"
write_status <<'EOF'
epic-1: in-progress
1-1-setup: done
1-2-auth: done
EOF
if (detect_next_story) 2>/dev/null; then
    test_fail "should have exited non-zero"
else
    assert_exit_fail
fi

test_begin "detect_next_story: handles comments and blank lines"
write_status <<'EOF'
# Sprint 1

epic-1: in-progress

# Stories
1-1-setup: done
# 1-2-auth: backlog  (commented out)
1-3-api: backlog
EOF
detect_next_story
assert_eq "1-3-api" "$STORY_ID"

test_begin "detect_next_story: skips metadata keys"
write_status <<'EOF'
generated: 2026-01-01
last_updated: 2026-03-01
project: my-app
tracking_system: github
story_location: _bmad-output
development_status: active
epic-1: in-progress
1-1-setup: backlog
EOF
detect_next_story
assert_eq "1-1-setup" "$STORY_ID"

test_begin "detect_next_story: handles multi-epic status files"
write_status <<'EOF'
epic-1: done
1-1-setup: done
1-2-auth: done
epic-2: in-progress
2-1-dashboard: backlog
2-2-reports: backlog
EOF
detect_next_story
assert_eq "2-1-dashboard" "$STORY_ID"

# ═══════════════════════════════════════════════════
# extract_epic_id / extract_short_id / extract_story_num
# ═══════════════════════════════════════════════════

test_begin "extract_epic_id: extracts epic number"
STORY_ID="3-2-some-feature"
extract_epic_id
assert_eq "3" "$EPIC_ID"

test_begin "extract_short_id: extracts N-N format"
STORY_ID="3-2-some-feature"
extract_short_id
assert_eq "3-2" "$STORY_SHORT_ID"

test_begin "extract_story_num: returns story number"
STORY_ID="3-2-some-feature"
local_num="$(extract_story_num)"
assert_eq "2" "$local_num"

test_begin "extract_story_num: handles hyphenated slugs"
STORY_ID="1-10-add-user-auth-flow"
extract_epic_id
assert_eq "1" "$EPIC_ID"
extract_short_id
# story_num check
local_num="$(extract_story_num)"
assert_eq "10" "$local_num"

# ═══════════════════════════════════════════════════
# resolve_full_story_id
# ═══════════════════════════════════════════════════

write_status <<'EOF'
epic-1: in-progress
1-1-auth-login: done
1-2-user-profile: backlog
epic-2: backlog
2-1-dashboard-setup: backlog
2-10-backup-disaster-recovery: backlog
EOF

test_begin "resolve_full_story_id: full ID passes through unchanged"
result="$(resolve_full_story_id "1-2-user-profile")"
assert_eq "1-2-user-profile" "$result"

test_begin "resolve_full_story_id: short ID resolves to full ID"
result="$(resolve_full_story_id "1-2")"
assert_eq "1-2-user-profile" "$result"

test_begin "resolve_full_story_id: short ID with two-digit story number"
result="$(resolve_full_story_id "2-10")"
assert_eq "2-10-backup-disaster-recovery" "$result"

test_begin "resolve_full_story_id: cross-epic short ID resolves correctly"
result="$(resolve_full_story_id "2-1")"
assert_eq "2-1-dashboard-setup" "$result"

test_begin "resolve_full_story_id: unknown short ID returns error"
if resolve_full_story_id "9-9" >/dev/null 2>&1; then
    test_fail "expected non-zero exit for unknown ID"
else
    test_pass
fi

# ═══════════════════════════════════════════════════
# detect_next_epic
# ═══════════════════════════════════════════════════

test_begin "detect_next_epic: picks in-progress epic"
write_status <<'EOF'
epic-1: done
epic-2: in-progress
2-1-dashboard: backlog
epic-3: backlog
EOF
detect_next_epic
assert_eq "2" "$EPIC_ID"

test_begin "detect_next_epic: falls back to first non-done"
write_status <<'EOF'
epic-1: done
epic-2: backlog
epic-3: backlog
EOF
detect_next_epic
assert_eq "2" "$EPIC_ID"

test_begin "detect_next_epic: prefers in-progress over backlog"
write_status <<'EOF'
epic-1: done
epic-2: backlog
epic-3: in-progress
EOF
detect_next_epic
assert_eq "3" "$EPIC_ID"

test_begin "detect_next_epic: fails when all epics done"
write_status <<'EOF'
epic-1: done
epic-2: done
EOF
if (detect_next_epic) 2>/dev/null; then
    test_fail "should have exited non-zero"
else
    assert_exit_fail
fi

# ═══════════════════════════════════════════════════
# collect_epic_stories
# ═══════════════════════════════════════════════════

test_begin "collect_epic_stories: collects correct stories"
write_status <<'EOF'
epic-1: in-progress
1-1-setup: done
1-2-auth: backlog
1-3-api: backlog
epic-2: backlog
2-1-dashboard: backlog
EOF
EPIC_ID="1"
collect_epic_stories
assert_eq "3" "$STORY_COUNT"
assert_eq "1-1-setup" "${STORY_IDS[0]}"
assert_eq "1-2-auth" "${STORY_IDS[1]}"
assert_eq "1-3-api" "${STORY_IDS[2]}"

test_begin "collect_epic_stories: captures statuses"
assert_eq "done" "${STORY_STATUSES[0]}"
assert_eq "backlog" "${STORY_STATUSES[1]}"

test_begin "collect_epic_stories: returns 0 for nonexistent epic"
EPIC_ID="99"
collect_epic_stories
assert_eq "0" "$STORY_COUNT"

# ═══════════════════════════════════════════════════
# validate_epic
# ═══════════════════════════════════════════════════

test_begin "validate_epic: passes when remaining stories exist"
write_status <<'EOF'
epic-1: in-progress
1-1-setup: done
1-2-auth: backlog
EOF
EPIC_ID="1"
collect_epic_stories
# Should not exit
validate_epic
assert_exit_ok

test_begin "validate_epic: fails when all stories done"
write_status <<'EOF'
epic-1: in-progress
1-1-setup: done
1-2-auth: done
EOF
EPIC_ID="1"
collect_epic_stories
if (validate_epic) 2>/dev/null; then
    test_fail "should have exited"
else
    assert_exit_fail
fi

test_begin "validate_epic: fails when no stories for epic"
STORY_COUNT=0
STORY_STATUSES=()
if (validate_epic) 2>/dev/null; then
    test_fail "should have exited"
else
    assert_exit_fail
fi

# ═══════════════════════════════════════════════════
# _find_previous_story / is_epic_start / is_epic_end
# ═══════════════════════════════════════════════════

test_begin "_find_previous_story: returns previous story"
write_status <<'EOF'
epic-1: in-progress
1-1-setup: done
1-2-auth: in-progress
1-3-api: backlog
EOF
STORY_ID="1-2-auth"
prev="$(_find_previous_story)"
assert_eq "1-1-setup" "$prev"

test_begin "_find_previous_story: returns empty for first story"
STORY_ID="1-1-setup"
prev="$(_find_previous_story)"
assert_empty "$prev"

test_begin "is_epic_start: true for story 1"
STORY_ID="1-1-setup"
if is_epic_start; then assert_exit_ok; else test_fail "should be epic start"; fi

test_begin "is_epic_start: false for story 2"
STORY_ID="1-2-auth"
if is_epic_start; then test_fail "should not be epic start"; else assert_exit_fail; fi

test_begin "is_epic_end: true when next entry is retrospective"
write_status <<'EOF'
epic-1: in-progress
1-1-setup: done
1-2-auth: in-progress
epic-1-retrospective: backlog
EOF
STORY_ID="1-2-auth"
EPIC_ID="1"
if is_epic_end; then assert_exit_ok; else test_fail "should be epic end"; fi

test_begin "is_epic_end: false when more stories follow"
write_status <<'EOF'
epic-1: in-progress
1-1-setup: done
1-2-auth: in-progress
1-3-api: backlog
EOF
STORY_ID="1-2-auth"
EPIC_ID="1"
if is_epic_end; then test_fail "should not be epic end"; else assert_exit_fail; fi

test_begin "is_epic_end: true when story is last with no retrospective"
write_status <<'EOF'
epic-1: in-progress
1-1-setup: done
1-2-auth: in-progress
EOF
STORY_ID="1-2-auth"
EPIC_ID="1"
if is_epic_end; then assert_exit_ok; else test_fail "should be epic end"; fi

# ═══════════════════════════════════════════════════
# validate_sprint_status
# ═══════════════════════════════════════════════════

test_begin "validate_sprint_status: accepts valid file"
write_status <<'EOF'
epic-1: in-progress
1-1-setup: done
1-2-auth: backlog
epic-1-retrospective: backlog
EOF
if validate_sprint_status "$_sf" >/dev/null 2>&1; then
    assert_exit_ok
else
    test_fail "valid file rejected"
fi

test_begin "validate_sprint_status: rejects invalid status"
write_status <<'EOF'
epic-1: in-progress
1-1-setup: invalid-status
EOF
if validate_sprint_status "$_sf" >/dev/null 2>&1; then
    test_fail "should reject invalid status"
else
    assert_exit_fail
fi

test_begin "validate_sprint_status: accepts 'optional' and 'ready-for-dev' and 'review'"
write_status <<'EOF'
epic-1: in-progress
1-1-setup: optional
1-2-auth: ready-for-dev
1-3-api: review
EOF
if validate_sprint_status "$_sf" >/dev/null 2>&1; then
    assert_exit_ok
else
    test_fail "valid statuses rejected"
fi

test_begin "validate_sprint_status: warns on duplicate stories"
write_status <<'EOF'
epic-1: in-progress
1-1-setup: backlog
1-1-setup: done
EOF
if validate_sprint_status "$_sf" >/dev/null 2>&1; then
    test_fail "should reject duplicate"
else
    assert_exit_fail
fi

# ═══════════════════════════════════════════════════
# _resolve_story_file_path / detect_story_file_path
# ═══════════════════════════════════════════════════

test_begin "detect_story_file_path: finds exact match"
make_story_file "1-2-auth-feature"
STORY_ID="1-2-auth-feature"
detect_story_file_path
assert_match "1-2-auth-feature.md" "$STORY_FILE_PATH"

test_begin "detect_story_file_path: finds prefix match"
make_story_file "2-1-dashboard-v2"
STORY_ID="2-1-dashboard"
# Should still match via prefix
result="$(_resolve_story_file_path "2-1-dashboard")"
assert_not_empty "$result"

# ═══════════════════════════════════════════════════
# update_sprint_status
# ═══════════════════════════════════════════════════

test_begin "update_sprint_status: updates story status"
write_status <<'EOF'
epic-1: in-progress
1-1-setup: done
1-2-auth: in-progress
1-3-api: backlog
EOF
update_sprint_status "1-2-auth" "done"
result="$(grep "1-2-auth" "$_sf")"
assert_match "done" "$result"

test_begin "update_sprint_status: preserves indentation"
write_status <<'EOF'
development_status:
  epic-1: in-progress
  1-1-setup: done
  1-2-auth: in-progress
EOF
update_sprint_status "1-2-auth" "done"
result="$(grep "1-2-auth" "$_sf")"
assert_eq "  1-2-auth: done" "$result"

test_begin "update_sprint_status: preserves other lines"
write_status <<'EOF'
epic-1: in-progress
1-1-setup: backlog
1-2-auth: in-progress
1-3-api: backlog
EOF
update_sprint_status "1-2-auth" "done"
result="$(grep "1-1-setup" "$_sf")"
assert_match "backlog" "$result"
result="$(grep "1-3-api" "$_sf")"
assert_match "backlog" "$result"

test_begin "update_sprint_status: updates epic key"
write_status <<'EOF'
epic-1: in-progress
1-1-setup: done
EOF
update_sprint_status "epic-1" "done"
result="$(grep "^epic-1:" "$_sf")"
assert_match "done" "$result"

test_begin "update_sprint_status: returns 1 for unknown key"
write_status <<'EOF'
epic-1: in-progress
1-1-setup: done
EOF
if update_sprint_status "9-9-nonexistent" "done"; then
    test_fail "should return 1 for unknown key"
else
    assert_exit_fail
fi

test_begin "update_sprint_status: returns 1 for missing file"
_saved_ss="$SPRINT_STATUS"
SPRINT_STATUS="/nonexistent/path/sprint-status.yaml"
if update_sprint_status "1-1-setup" "done"; then
    test_fail "should return 1 for missing file"
else
    assert_exit_fail
fi
SPRINT_STATUS="$_saved_ss"

test_begin "update_sprint_status: refreshes last_updated"
write_status <<'EOF'
last_updated: 2020-01-01T00:00:00Z
epic-1: in-progress
1-1-setup: backlog
EOF
update_sprint_status "1-1-setup" "done"
result="$(grep "last_updated" "$_sf")"
assert_not_empty "$result"
# Should no longer be the old date
if [[ "$result" == *"2020-01-01"* ]]; then
    test_fail "last_updated was not refreshed"
else
    assert_exit_ok
fi

# ═══════════════════════════════════════════════════
# all_epic_stories_done
# ═══════════════════════════════════════════════════

test_begin "all_epic_stories_done: true when all done"
write_status <<'EOF'
epic-1: in-progress
1-1-setup: done
1-2-auth: done
1-3-api: done
EOF
EPIC_ID=1
if all_epic_stories_done; then assert_exit_ok; else test_fail "all stories are done"; fi

test_begin "all_epic_stories_done: false when some not done"
write_status <<'EOF'
epic-1: in-progress
1-1-setup: done
1-2-auth: in-progress
1-3-api: backlog
EOF
EPIC_ID=1
if all_epic_stories_done; then test_fail "not all stories are done"; else assert_exit_fail; fi

test_begin "all_epic_stories_done: cross-epic isolation"
write_status <<'EOF'
epic-1: in-progress
1-1-setup: done
1-2-auth: done
epic-2: backlog
2-1-dashboard: backlog
EOF
if all_epic_stories_done 1; then assert_exit_ok; else test_fail "epic 1 should be all done"; fi
if all_epic_stories_done 2; then test_fail "epic 2 is not done"; else assert_exit_fail; fi

test_begin "all_epic_stories_done: false for empty epic"
write_status <<'EOF'
epic-3: backlog
EOF
if all_epic_stories_done 3; then test_fail "empty epic should not be done"; else assert_exit_fail; fi

# ═══════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════

test_summary
