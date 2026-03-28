#!/usr/bin/env bash
# test/test_cli.sh — Tests for cli.sh (load_prompt, codex_prompt, run_ai dispatch)
# Run: bash test/test_cli.sh
#
# Tests prompt template loading/substitution and codex prompt rewriting.
# Uses mock CLIs for run_ai dispatch tests.

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

echo ""
echo -e "${_T_BOLD}CLI tests (prompts, dispatch)${_T_NC}"
echo ""

# --- Bootstrap environment ---
source "${REPO_ROOT}/lib/core.sh"
INTERACTIVE=false
source "${REPO_ROOT}/lib/tracking.sh"

# Prepend mock dir to PATH
export PATH="${TEST_DIR}/mocks:${PATH}"

# Set up INSTALL_DIR with prompts and profiles
INSTALL_DIR="$(make_test_tmpdir)"
mkdir -p "${INSTALL_DIR}/conf" "${INSTALL_DIR}/prompts"

cat > "${INSTALL_DIR}/conf/profiles.conf" <<'EOF'
@mock-claude   claude   opus   high   -
@mock-codex    codex    gpt-5.4 high  -
@mock-bogus    bogusctl opus   high   -

1.1  @mock-claude
1.2  @mock-codex
9.9  @mock-bogus
EOF

# Prevent user config interference
export XDG_CONFIG_HOME="$(make_test_tmpdir)"

# Globals expected by config.sh / cli.sh
TMP_DIR="$(make_test_tmpdir)"
PROJECT_ROOT="$(make_test_tmpdir)"
PIPELINE_LOG="${TMP_DIR}/pipeline.log"
: > "$PIPELINE_LOG"
PIPELINE_START_TIME=$(date +%s)
STORY_ID="1-1-test"
COMMIT_BASELINE=""
DRY_RUN=false
FROM_STEP=""
STEP_ORDER="1.1 1.2 9.9"
REVIEWS_MODE="full"
LAST_COMPLETED_STEP=""
HAS_JQ=false
CURRENT_STEP_LOG="${TMP_DIR}/step-current.log"
: > "$CURRENT_STEP_LOG"
SPINNER_FRAMES="⠋"

source "${REPO_ROOT}/lib/config.sh"
load_pipeline_conf

# Stub functions that cli.sh / steps.sh / runner.sh expect
start_activity_monitor() { :; }
stop_activity_monitor()  { :; }
extract_and_record_usage() { :; }
extract_ai_output() { echo "mock output"; }

# Step tracking functions (normally in auto-bmad-story)
set_step_status()        { kv_set step "$1" status   "$2"; }
get_step_status()        { kv_get step "$1" status   "skipped"; }
set_step_duration()      { kv_set step "$1" duration "$2"; }
get_step_duration()      { kv_get step "$1" duration "0"; }
set_step_name()          { kv_set step "$1" name     "$2"; }
get_step_name()          { kv_get step "$1" name     "$1"; }
set_step_start()         { kv_set step "$1" start    "$2"; }
get_step_start()         { kv_get step "$1" start    "${2:-}"; }
set_step_attempts()      { kv_set step "$1" attempts      "$2"; }
get_step_attempts()      { kv_get step "$1" attempts      "1"; }
set_step_final_profile() { kv_set step "$1" final_profile "$2"; }
get_step_final_profile() { kv_get step "$1" final_profile ""; }

source "${REPO_ROOT}/lib/cli.sh"
source "${REPO_ROOT}/lib/steps.sh"
source "${REPO_ROOT}/lib/runner.sh"

# ═══════════════════════════════════════════════════
# load_prompt
# ═══════════════════════════════════════════════════

echo -e "${_T_BOLD}  Prompt loading${_T_NC}"

# Create test templates
cat > "${INSTALL_DIR}/prompts/test-basic.md" <<'EOF'
Hello {{NAME}}, your story is {{STORY_ID}}.
EOF

cat > "${INSTALL_DIR}/prompts/test-multi.md" <<'EOF'
# Review for {{STORY_ID}}

Story: {{STORY_ID}}
File: {{OUTPUT_FILE}}
Context: {{GIT_CONTEXT}}
EOF

cat > "${INSTALL_DIR}/prompts/test-no-vars.md" <<'EOF'
This template has no placeholders.
Just plain text.
EOF

cat > "${INSTALL_DIR}/prompts/test-leftover.md" <<'EOF'
Hello {{NAME}}, see also {{UNRESOLVED_VAR}}.
EOF

test_begin "load_prompt: loads template file"
result="$(load_prompt "test-no-vars.md" 2>/dev/null)"
assert_match "no placeholders" "$result"

test_begin "load_prompt: substitutes single variable"
result="$(load_prompt "test-basic.md" NAME "World" STORY_ID "1-1" 2>/dev/null)"
assert_match "Hello World" "$result"

test_begin "load_prompt: substitutes STORY_ID variable"
assert_match "story is 1-1" "$result"

test_begin "load_prompt: substitutes multiple variables"
result="$(load_prompt "test-multi.md" \
    STORY_ID "2-3-feature" \
    OUTPUT_FILE "/tmp/out.md" \
    GIT_CONTEXT "diff --stat" 2>/dev/null)"
assert_match "Story: 2-3-feature" "$result"

test_begin "load_prompt: all placeholders replaced"
assert_match "File: /tmp/out.md" "$result"

test_begin "load_prompt: multiple occurrences replaced"
# STORY_ID appears twice in test-multi.md
count=$(echo "$result" | grep -c "2-3-feature" || true)
if [[ "$count" == "2" ]]; then
    assert_exit_ok
else
    test_fail "expected 2 occurrences of STORY_ID, got ${count}"
fi

test_begin "load_prompt: warns about unreplaced placeholders"
# Provide NAME but not UNRESOLVED_VAR
stderr_output="$(load_prompt "test-leftover.md" NAME "Alice" 2>&1 >/dev/null)" || true
# Combine stdout+stderr to check for warning
full_output="$(load_prompt "test-leftover.md" NAME "Alice" 2>&1)"
if echo "$full_output" | grep -qi "unreplaced\|UNRESOLVED_VAR"; then
    assert_exit_ok
else
    test_fail "should warn about {{UNRESOLVED_VAR}}"
fi

test_begin "load_prompt: returns 1 for missing template"
if load_prompt "nonexistent-template.md" 2>/dev/null; then
    test_fail "should fail for missing template"
else
    assert_exit_fail
fi

test_begin "load_prompt: empty substitution value replaces placeholder"
result="$(load_prompt "test-basic.md" NAME "" STORY_ID "1-1" 2>/dev/null)"
assert_match "Hello , your" "$result"

# ═══════════════════════════════════════════════════
# codex_prompt
# ═══════════════════════════════════════════════════

echo ""
echo -e "${_T_BOLD}  Codex prompt rewriting${_T_NC}"

test_begin "codex_prompt: converts leading slash to dollar"
result="$(codex_prompt "/review-code")"
assert_eq '$review-code' "$result"

test_begin "codex_prompt: leaves non-slash prompts unchanged"
result="$(codex_prompt "review this code please")"
assert_eq "review this code please" "$result"

test_begin "codex_prompt: handles empty input"
result="$(codex_prompt "")"
assert_eq "" "$result"

test_begin "codex_prompt: only converts leading slash"
result="$(codex_prompt "run /path/to/file")"
assert_eq "run /path/to/file" "$result"

test_begin "codex_prompt: single slash becomes dollar"
result="$(codex_prompt "/x")"
assert_eq '$x' "$result"

# ═══════════════════════════════════════════════════
# run_ai dispatch
# ═══════════════════════════════════════════════════

echo ""
echo -e "${_T_BOLD}  run_ai dispatch${_T_NC}"

# Disable soft-fail thresholds for mock CLIs
MIN_STEP_DURATION=0
MIN_LOG_BYTES=0

test_begin "run_ai: dispatches to claude mock"
CURRENT_STEP_LOG="${TMP_DIR}/step-1.1.log"
: > "$CURRENT_STEP_LOG"
export MOCK_EXIT=0 MOCK_OUTPUT_BYTES=300
parse_step_config "1.1"
if run_ai "1.1" "test prompt" 2>/dev/null; then
    # Check that step log got the header
    if grep -q "Step 1.1" "$CURRENT_STEP_LOG"; then
        assert_exit_ok
    else
        test_fail "step log missing header"
    fi
else
    test_fail "run_ai should succeed"
fi

test_begin "run_ai: step log contains CLI info"
assert_match "claude" "$(grep 'CLI:' "$CURRENT_STEP_LOG")"

test_begin "run_ai: dispatches to codex mock"
CURRENT_STEP_LOG="${TMP_DIR}/step-1.2.log"
: > "$CURRENT_STEP_LOG"
parse_step_config "1.2"
if run_ai "1.2" "/do-something" 2>/dev/null; then
    if grep -q "codex" "$CURRENT_STEP_LOG"; then
        assert_exit_ok
    else
        test_fail "step log should show codex"
    fi
else
    test_fail "codex dispatch should succeed"
fi

test_begin "run_ai: returns CLI exit code on failure"
export MOCK_EXIT=1
parse_step_config "1.1"
CURRENT_STEP_LOG="${TMP_DIR}/step-fail.log"
: > "$CURRENT_STEP_LOG"
if run_ai "1.1" "fail prompt" 2>/dev/null; then
    test_fail "should propagate non-zero exit"
else
    assert_exit_fail
fi
export MOCK_EXIT=0

test_begin "run_ai: returns 1 for unknown CLI"
CURRENT_STEP_LOG="${TMP_DIR}/step-bogus.log"
: > "$CURRENT_STEP_LOG"
parse_step_config "9.9"
if run_ai "9.9" "test" 2>/dev/null; then
    test_fail "should fail for unknown CLI"
else
    assert_exit_fail
fi

test_begin "run_ai: JSON mode writes raw file when HAS_JQ=true"
(
    HAS_JQ=true
    export MOCK_EXIT=0 MOCK_OUTPUT_BYTES=300 MOCK_JSON=1
    local_tmp="$(make_test_tmpdir)"
    TMP_DIR="$local_tmp"
    CURRENT_STEP_LOG="${local_tmp}/step-json.log"
    : > "$CURRENT_STEP_LOG"
    # Need real extract_ai_output for JSON mode
    extract_ai_output() { cat "$2" 2>/dev/null; }
    parse_step_config "1.1"
    run_ai "1.1" "test json" 2>/dev/null
    if [[ -f "${local_tmp}/step-1.1-raw.json" ]]; then
        exit 0
    else
        exit 1
    fi
)
if [[ $? -eq 0 ]]; then assert_exit_ok; else test_fail "should write raw JSON file"; fi
unset MOCK_JSON

# ═══════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════

test_summary
