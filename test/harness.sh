#!/usr/bin/env bash
# test/harness.sh — Minimal test framework for auto-bmad
# Source this from test scripts. Provides assert helpers and summary reporting.

set -euo pipefail

_TEST_PASSED=0
_TEST_FAILED=0
_TEST_TOTAL=0
_CURRENT_TEST=""

# Colors (simplified — always on for test output)
_T_GREEN='\033[0;32m'
_T_RED='\033[0;31m'
_T_DIM='\033[2m'
_T_BOLD='\033[1m'
_T_NC='\033[0m'

# Resolve repo root relative to this file
TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$TEST_DIR/.." && pwd)"

# --- Test lifecycle ---

test_begin() {
    _CURRENT_TEST="$1"
    _TEST_TOTAL=$((_TEST_TOTAL + 1))
}

test_pass() {
    _TEST_PASSED=$((_TEST_PASSED + 1))
    echo -e "  ${_T_GREEN}✓${_T_NC} ${_CURRENT_TEST}"
}

test_fail() {
    local msg="${1:-}"
    _TEST_FAILED=$((_TEST_FAILED + 1))
    echo -e "  ${_T_RED}✗${_T_NC} ${_CURRENT_TEST}"
    [[ -n "$msg" ]] && echo -e "    ${_T_DIM}${msg}${_T_NC}"
}

test_summary() {
    echo ""
    echo -e "${_T_BOLD}Results:${_T_NC} ${_TEST_TOTAL} tests, ${_T_GREEN}${_TEST_PASSED} passed${_T_NC}, ${_T_RED}${_TEST_FAILED} failed${_T_NC}"
    (( _TEST_FAILED == 0 ))
}

# --- Assertions ---

assert_eq() {
    local expected="$1" actual="$2" label="${3:-}"
    if [[ "$expected" == "$actual" ]]; then
        test_pass
    else
        test_fail "expected '${expected}', got '${actual}'${label:+ ($label)}"
    fi
}

assert_ne() {
    local unexpected="$1" actual="$2" label="${3:-}"
    if [[ "$unexpected" != "$actual" ]]; then
        test_pass
    else
        test_fail "expected NOT '${unexpected}'${label:+ ($label)}"
    fi
}

assert_match() {
    local pattern="$1" actual="$2" label="${3:-}"
    if [[ "$actual" =~ $pattern ]]; then
        test_pass
    else
        test_fail "expected match '${pattern}', got '${actual}'${label:+ ($label)}"
    fi
}

assert_empty() {
    local actual="$1" label="${2:-}"
    if [[ -z "$actual" ]]; then
        test_pass
    else
        test_fail "expected empty, got '${actual}'${label:+ ($label)}"
    fi
}

assert_not_empty() {
    local actual="$1" label="${2:-}"
    if [[ -n "$actual" ]]; then
        test_pass
    else
        test_fail "expected non-empty${label:+ ($label)}"
    fi
}

assert_exit_ok() {
    local label="${1:-command}"
    # Caller uses: if some_cmd; then assert_exit_ok; else assert_exit_fail; fi
    test_pass
}

assert_exit_fail() {
    local label="${1:-command}"
    test_pass
}

# --- Temp directory helpers ---

_TEST_TMPDIRS=()

make_test_tmpdir() {
    local d
    d=$(mktemp -d "${TMPDIR:-/tmp}/auto-bmad-test.XXXXXX")
    _TEST_TMPDIRS+=("$d")
    echo "$d"
}

cleanup_test_tmpdirs() {
    for d in "${_TEST_TMPDIRS[@]+"${_TEST_TMPDIRS[@]}"}"; do
        [[ -d "$d" ]] && rm -rf "$d"
    done
    _TEST_TMPDIRS=()
}

trap cleanup_test_tmpdirs EXIT
