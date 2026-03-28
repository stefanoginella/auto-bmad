#!/usr/bin/env bash
# test/run_all.sh — Run all test suites
# Usage: bash test/run_all.sh  OR  make test

set -euo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
failures=0

for suite in "${TEST_DIR}"/test_*.sh; do
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo " Running: $(basename "$suite")"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if bash "$suite"; then
        :
    else
        failures=$((failures + 1))
    fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if (( failures > 0 )); then
    echo " FAILED: ${failures} suite(s) had failures"
    exit 1
else
    echo " All suites passed"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
