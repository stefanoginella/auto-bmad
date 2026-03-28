#!/usr/bin/env bash
# test/test_runner.sh — Tests for runner.sh using mock CLIs
# Run: bash test/test_runner.sh
#
# Tests soft-fail detection, retry, fallback, and parallel review completion
# using mock CLI scripts that simulate success/failure/slow responses.

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

echo ""
echo -e "${_T_BOLD}Runner tests (mock CLIs)${_T_NC}"
echo ""

# --- Bootstrap environment ---
source "${REPO_ROOT}/lib/core.sh"
INTERACTIVE=false
source "${REPO_ROOT}/lib/tracking.sh"

# Prepend mock dir to PATH so mock CLIs are found
export PATH="${TEST_DIR}/mocks:${PATH}"

# Provide globals that runner.sh / config.sh / cli.sh / steps.sh expect
TMP_DIR="$(make_test_tmpdir)"
PIPELINE_LOG="${TMP_DIR}/pipeline.log"
: > "$PIPELINE_LOG"
STORY_ID="1-1-test"
PIPELINE_START_TIME=$(date +%s)
DRY_RUN=false
FROM_STEP=""
STEP_ORDER="1.1 1.2 1.3 2.1 2.2 3.1 3.2"
REVIEWS_MODE="full"
LAST_COMPLETED_STEP=""
_ABORT=false
CURRENT_STEP_LOG="${TMP_DIR}/step-current.log"
: > "$CURRENT_STEP_LOG"
COMMIT_BASELINE=""
HAS_JQ=false
SPINNER_FRAMES="⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
PROJECT_ROOT="$(make_test_tmpdir)"

# Mock INSTALL_DIR with minimal profiles
INSTALL_DIR="$(make_test_tmpdir)"
mkdir -p "${INSTALL_DIR}/conf"
cat > "${INSTALL_DIR}/conf/profiles.conf" <<'EOF'
@mock-claude   claude   opus   high   @mock-copilot
@mock-copilot  copilot  opus   high   -
@mock-codex    codex    gpt-5.4 high  @mock-claude

1.1   @mock-claude
1.2a  @mock-codex
1.2b  @mock-copilot
1.2c  @mock-claude
1.3   @mock-claude
2.1   @mock-claude
EOF

# Source config and remaining libs
source "${REPO_ROOT}/lib/config.sh"
load_pipeline_conf

# Step tracking functions (normally defined in auto-bmad-story)
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

# Stub functions that runner.sh calls but we don't need for unit tests
start_activity_monitor() { :; }
stop_activity_monitor()  { :; }
extract_and_record_usage() { :; }
extract_ai_output() { echo "mock output"; }

source "${REPO_ROOT}/lib/cli.sh"
source "${REPO_ROOT}/lib/steps.sh"
source "${REPO_ROOT}/lib/runner.sh"

# ═══════════════════════════════════════════════════
# _detect_soft_fail
# ═══════════════════════════════════════════════════

test_begin "soft-fail: exit code != 0 is a failure"
CURRENT_STEP_LOG="${TMP_DIR}/sf1.log"
: > "$CURRENT_STEP_LOG"
if _detect_soft_fail 1 60; then
    assert_exit_ok "hard fail detected"
else
    test_fail "should detect hard failure"
fi

test_begin "soft-fail: duration < MIN_STEP_DURATION is a failure"
CURRENT_STEP_LOG="${TMP_DIR}/sf2.log"
# Write enough bytes so it's not a size fail
head -c 500 /dev/zero 2>/dev/null | tr '\0' 'x' > "$CURRENT_STEP_LOG"
if _detect_soft_fail 0 2; then
    assert_exit_ok "too-fast detected"
else
    test_fail "should detect too-fast step"
fi

test_begin "soft-fail: output < MIN_LOG_BYTES is a failure"
CURRENT_STEP_LOG="${TMP_DIR}/sf3.log"
echo "tiny" > "$CURRENT_STEP_LOG"
if _detect_soft_fail 0 60; then
    assert_exit_ok "too-little-output detected"
else
    test_fail "should detect too-little output"
fi

test_begin "soft-fail: good exit + good duration + good output = success"
CURRENT_STEP_LOG="${TMP_DIR}/sf4.log"
head -c 500 /dev/zero 2>/dev/null | tr '\0' 'x' > "$CURRENT_STEP_LOG"
if _detect_soft_fail 0 60; then
    test_fail "should NOT detect failure"
else
    assert_exit_ok "no failure detected"
fi

# ═══════════════════════════════════════════════════
# should_run_step
# ═══════════════════════════════════════════════════

test_begin "should_run_step: runs all when FROM_STEP is empty"
FROM_STEP=""
if should_run_step "1.1"; then assert_exit_ok; else test_fail; fi

test_begin "should_run_step: skips steps before FROM_STEP"
FROM_STEP="2.1"
if should_run_step "1.1"; then test_fail "should skip 1.1"; else assert_exit_fail; fi

test_begin "should_run_step: runs steps at and after FROM_STEP"
FROM_STEP="2.1"
if should_run_step "2.1"; then assert_exit_ok; else test_fail "should run 2.1"; fi

test_begin "should_run_step: maps parallel sub-step to parent"
FROM_STEP="1.2"
STEP_ORDER="1.1 1.2 1.3"
if should_run_step "1.2a"; then assert_exit_ok; else test_fail "1.2a should map to 1.2"; fi

test_begin "should_run_step: skips parallel sub-step before FROM_STEP"
FROM_STEP="1.3"
STEP_ORDER="1.1 1.2 1.3"
if should_run_step "1.2a"; then test_fail "1.2a should be skipped"; else assert_exit_fail; fi

# Reset
FROM_STEP=""
STEP_ORDER="1.1 1.2 1.3 2.1 2.2 3.1 3.2"

# ═══════════════════════════════════════════════════
# Mock CLI integration: run_ai via run_step
# ═══════════════════════════════════════════════════

test_begin "run_step: succeeds with mock CLI (good output)"
CURRENT_STEP_LOG="${TMP_DIR}/step-1.1.log"
: > "$CURRENT_STEP_LOG"
export MOCK_EXIT=0 MOCK_DELAY=0 MOCK_OUTPUT_BYTES=500
# Disable soft-fail thresholds — mock CLIs complete instantly
MIN_STEP_DURATION=0
MIN_LOG_BYTES=0
# run_step exits on failure, so run in subshell; check status within it
if (
    run_step "1.1" "Test Step" run_ai "1.1" "do something" 2>/dev/null
    [[ "$(get_step_status "1.1")" == "ok" ]]
); then
    assert_exit_ok
else
    test_fail "run_step should succeed"
fi

test_begin "run_step: dry-run skips execution"
DRY_RUN=true
# dry-run returns 0 (no exit), safe to call directly
run_step "2.1" "Dry Step" run_ai "2.1" "do something" 2>/dev/null
status="$(get_step_status "2.1")"
assert_eq "dry-run" "$status"
DRY_RUN=false

# ═══════════════════════════════════════════════════
# _run_with_retry: retry on soft fail
# ═══════════════════════════════════════════════════

test_begin "retry: retries then succeeds"
MIN_STEP_DURATION=0
MIN_LOG_BYTES=0
CURRENT_STEP_LOG="${TMP_DIR}/step-retry.log"
: > "$CURRENT_STEP_LOG"
MOCK_STATE_DIR="$(make_test_tmpdir)"
export MOCK_STATE_DIR MOCK_FAIL_FIRST=1 MOCK_FAIL_EXIT=1 MOCK_DELAY=0 MOCK_OUTPUT_BYTES=500
# First call fails (exit 1), second call succeeds
parse_step_config "1.1"
if _run_with_retry "1.1" run_ai "1.1" "do something" 2>/dev/null; then
    attempts="$(get_step_attempts "1.1")"
    assert_eq "2" "$attempts"
else
    test_fail "should succeed after retry"
fi
unset MOCK_FAIL_FIRST MOCK_FAIL_EXIT

test_begin "retry: falls back to secondary profile after retries exhausted"
MIN_STEP_DURATION=0
MIN_LOG_BYTES=0
CURRENT_STEP_LOG="${TMP_DIR}/step-fallback.log"
: > "$CURRENT_STEP_LOG"
MOCK_STATE_DIR="$(make_test_tmpdir)"
# Fail 3 times: attempt 1 (primary), attempt 2 (retry), attempt 3 (fallback)
# _run_with_retry: primary x2 then fallback x1
export MOCK_STATE_DIR MOCK_FAIL_FIRST=2 MOCK_FAIL_EXIT=1 MOCK_DELAY=0 MOCK_OUTPUT_BYTES=500
parse_step_config "1.1"  # @mock-claude with fallback @mock-copilot
if _run_with_retry "1.1" run_ai "1.1" "do something" 2>/dev/null; then
    final="$(get_step_final_profile "1.1")"
    # Should show the fallback profile's cli/model
    assert_match "copilot" "$final"
else
    test_fail "should succeed with fallback"
fi
unset MOCK_FAIL_FIRST MOCK_FAIL_EXIT

test_begin "retry: fails completely when fallback also fails"
MIN_STEP_DURATION=0
MIN_LOG_BYTES=0
CURRENT_STEP_LOG="${TMP_DIR}/step-allfail.log"
: > "$CURRENT_STEP_LOG"
MOCK_STATE_DIR="$(make_test_tmpdir)"
# Fail all attempts: primary x2 + fallback x1 = 3 total
export MOCK_STATE_DIR MOCK_FAIL_FIRST=99 MOCK_FAIL_EXIT=1 MOCK_DELAY=0 MOCK_OUTPUT_BYTES=500
parse_step_config "1.1"
if _run_with_retry "1.1" run_ai "1.1" "do something" 2>/dev/null; then
    test_fail "should fail completely"
else
    assert_exit_fail "all attempts exhausted"
fi
unset MOCK_FAIL_FIRST MOCK_FAIL_EXIT MOCK_STATE_DIR

# ═══════════════════════════════════════════════════
# Mock CLI: verify canned output
# ═══════════════════════════════════════════════════

test_begin "mock claude: produces expected output size"
export MOCK_OUTPUT_BYTES=300 MOCK_EXIT=0
output="$(claude -p "test" 2>/dev/null)"
len=${#output}
# Allow some tolerance for line endings
if (( len >= 280 && len <= 350 )); then
    assert_exit_ok
else
    test_fail "expected ~300 bytes, got ${len}"
fi

test_begin "mock codex: JSON mode produces valid-ish JSON"
export MOCK_OUTPUT_BYTES=100 MOCK_EXIT=0 MOCK_JSON=1
output="$(codex exec "test" 2>/dev/null)"
if echo "$output" | grep -q '"status"'; then
    assert_exit_ok
else
    test_fail "JSON output missing expected fields"
fi
unset MOCK_JSON

test_begin "mock copilot: exits with requested code"
export MOCK_EXIT=42 MOCK_OUTPUT_BYTES=100
if copilot -p "test" 2>/dev/null; then
    test_fail "should exit 42"
else
    assert_exit_fail "non-zero exit"
fi
export MOCK_EXIT=0

test_begin "mock opencode: fail-first counter works"
MOCK_STATE_DIR="$(make_test_tmpdir)"
export MOCK_STATE_DIR MOCK_FAIL_FIRST=2 MOCK_FAIL_EXIT=1 MOCK_OUTPUT_BYTES=100
# Call 1: fail
if opencode run "test" 2>/dev/null; then fail1=false; else fail1=true; fi
# Call 2: fail
if opencode run "test" 2>/dev/null; then fail2=false; else fail2=true; fi
# Call 3: succeed
if opencode run "test" 2>/dev/null; then fail3=false; else fail3=true; fi
if [[ "$fail1" == true && "$fail2" == true && "$fail3" == false ]]; then
    assert_exit_ok
else
    test_fail "expected fail,fail,pass — got ${fail1},${fail2},${fail3}"
fi
unset MOCK_FAIL_FIRST MOCK_FAIL_EXIT MOCK_STATE_DIR

# ═══════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════

test_summary
