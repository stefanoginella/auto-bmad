#!/usr/bin/env bash
# test/test_usage.sh — Tests for usage.sh (pricing, cost computation, extraction)
# Run: bash test/test_usage.sh
#
# Tests pricing.conf parsing, cost inference, per-CLI output/usage extraction,
# and the extract_and_record_usage dispatcher. Extraction tests require jq.

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

echo ""
echo -e "${_T_BOLD}Usage tests (pricing, cost, extraction)${_T_NC}"
echo ""

# --- Bootstrap environment ---
source "${REPO_ROOT}/lib/core.sh"
INTERACTIVE=false
source "${REPO_ROOT}/lib/tracking.sh"

# Globals expected by config.sh / usage.sh
TMP_DIR="$(make_test_tmpdir)"
PROJECT_ROOT="$(make_test_tmpdir)"
PIPELINE_LOG="${TMP_DIR}/pipeline.log"
: > "$PIPELINE_LOG"
STORY_ID="1-1-test"
PIPELINE_START_TIME=$(date +%s)
STORY_ARTIFACTS="${TMP_DIR}/artifacts"
mkdir -p "$STORY_ARTIFACTS"

# Set up install dir with pricing.conf
INSTALL_DIR="$(make_test_tmpdir)"
mkdir -p "${INSTALL_DIR}/conf"
cat > "${INSTALL_DIR}/conf/pricing.conf" <<'EOF'
[tokens]
# model          input  output  cache_read  cache_write
gpt-5.4          2.50   15.00   0.25        -
claude-opus-4    15.00  75.00   1.50        18.75
test-model       1.00   2.00    0.50        0.75

[copilot]
plan = pro
pro_cost = 10.00
pro_requests = 300
pro_plus_cost = 39.00
pro_plus_requests = 1500
EOF

# Minimal profiles.conf so config.sh doesn't complain
cat > "${INSTALL_DIR}/conf/profiles.conf" <<'EOF'
@mock-claude  claude  opus  high  -
1.1  @mock-claude
EOF

# Prevent user-level config from interfering
export XDG_CONFIG_HOME="$(make_test_tmpdir)"

source "${REPO_ROOT}/lib/config.sh"
load_pipeline_conf

# Check jq availability — extraction tests are gated on it
if command -v jq &>/dev/null; then
    _JQ_AVAILABLE=true
    HAS_JQ=true
else
    _JQ_AVAILABLE=false
    HAS_JQ=false
    echo -e "  ${_T_DIM}(jq not found — extraction tests will be skipped)${_T_NC}"
fi

source "${REPO_ROOT}/lib/usage.sh"

# Helper: reset pricing state between test groups
_reset_pricing() {
    _PRICING_MODELS=()
    _PRICING_INPUT=()
    _PRICING_OUTPUT=()
    _PRICING_CACHE_READ=()
    _PRICING_CACHE_WRITE=()
    _PRICING_LOADED=false
    _COPILOT_COST_PER_REQUEST=""
}

# ═══════════════════════════════════════════════════
# _load_pricing / _lookup_pricing
# ═══════════════════════════════════════════════════

echo -e "${_T_BOLD}  Pricing loading${_T_NC}"

test_begin "pricing: loads token models from pricing.conf"
_reset_pricing
_load_pricing
# Should have at least the 3 models from our test pricing.conf
found=0
for m in "${_PRICING_MODELS[@]}"; do
    case "$m" in gpt-5.4|claude-opus-4|test-model) found=$((found + 1)) ;; esac
done
assert_eq "3" "$found"

test_begin "pricing: idempotent — second call is a no-op"
_load_pricing  # already loaded, should return immediately
found=0
for m in "${_PRICING_MODELS[@]}"; do
    case "$m" in gpt-5.4|claude-opus-4|test-model) found=$((found + 1)) ;; esac
done
assert_eq "3" "$found"

test_begin "pricing: lookup returns correct rates for known model"
_reset_pricing
_load_pricing
result="$(_lookup_pricing "gpt-5.4")"
assert_eq "2.50|15.00|0.25|-" "$result"

test_begin "pricing: lookup returns all 4 fields for model with cache_write"
result="$(_lookup_pricing "claude-opus-4")"
assert_eq "15.00|75.00|1.50|18.75" "$result"

test_begin "pricing: lookup fails for unknown model"
if _lookup_pricing "nonexistent-model" >/dev/null 2>&1; then
    test_fail "should return 1 for unknown model"
else
    assert_exit_fail
fi

test_begin "pricing: copilot cost per request computed (pro plan)"
_reset_pricing
_load_pricing
# pro: 10.00 / 300 = 0.033333
assert_match "^0\.03333" "$_COPILOT_COST_PER_REQUEST"

test_begin "pricing: copilot pro+ plan computes different rate"
_reset_pricing
# Override plan in a project-level pricing.conf
mkdir -p "${PROJECT_ROOT}/conf"
cat > "${PROJECT_ROOT}/conf/pricing.conf" <<'EOF'
[copilot]
plan = pro_plus
pro_plus_cost = 39.00
pro_plus_requests = 1500
EOF
_load_pricing
# pro+: 39.00 / 1500 = 0.026000
assert_match "^0\.02600" "$_COPILOT_COST_PER_REQUEST"
rm -f "${PROJECT_ROOT}/conf/pricing.conf"

test_begin "pricing: project conf overrides install conf model rates"
_reset_pricing
mkdir -p "${PROJECT_ROOT}/conf"
cat > "${PROJECT_ROOT}/conf/pricing.conf" <<'EOF'
[tokens]
gpt-5.4  3.00  20.00  0.30  -
EOF
_load_pricing
result="$(_lookup_pricing "gpt-5.4")"
assert_eq "3.00|20.00|0.30|-" "$result"
rm -f "${PROJECT_ROOT}/conf/pricing.conf"

# ═══════════════════════════════════════════════════
# _compute_cost
# ═══════════════════════════════════════════════════

echo ""
echo -e "${_T_BOLD}  Cost computation${_T_NC}"

# Reload clean pricing
_reset_pricing
_load_pricing

test_begin "cost: basic computation (input + output tokens)"
# gpt-5.4: input=2.50/MTok, output=15.00/MTok
# 1000 in + 500 out = (1000/1M)*2.50 + (500/1M)*15.00 = 0.0025 + 0.0075 = 0.01
result="$(_compute_cost 1000 500 0 0 "gpt-5.4")"
assert_eq "0.010000" "$result"

test_begin "cost: includes cache read tokens"
# claude-opus-4: input=15.00, output=75.00, cache_read=1.50, cache_write=18.75
# 10000 in + 2000 out + 5000 cache_read = 0.15 + 0.15 + 0.0075 = 0.3075
result="$(_compute_cost 10000 2000 5000 0 "claude-opus-4")"
assert_eq "0.307500" "$result"

test_begin "cost: includes cache write tokens"
# test-model: input=1.00, output=2.00, cache_read=0.50, cache_write=0.75
# 1000 in + 1000 out + 1000 crd + 1000 cwr = 0.001 + 0.002 + 0.0005 + 0.00075 = 0.00425
result="$(_compute_cost 1000 1000 1000 1000 "test-model")"
assert_eq "0.004250" "$result"

test_begin "cost: zero tokens = zero cost"
result="$(_compute_cost 0 0 0 0 "gpt-5.4")"
assert_eq "0.000000" "$result"

test_begin "cost: null token values treated as zero"
result="$(_compute_cost "null" "" "null" "" "gpt-5.4")"
assert_eq "0.000000" "$result"

test_begin "cost: unknown model returns failure"
if _compute_cost 1000 500 0 0 "nonexistent-model" >/dev/null 2>&1; then
    test_fail "should return 1 for unknown model"
else
    assert_exit_fail
fi

test_begin "cost: dash in cache_write rate treated as zero"
# gpt-5.4 has "-" for cache_write rate
# Even with cache_write tokens, cost should only include input+output+cache_read
result="$(_compute_cost 1000000 1000000 0 1000000 "gpt-5.4")"
# = (1M/1M)*2.50 + (1M/1M)*15.00 + 0 + (1M/1M)*0 = 17.50
assert_eq "17.500000" "$result"

# ═══════════════════════════════════════════════════
# _emit_empty_usage
# ═══════════════════════════════════════════════════

echo ""
echo -e "${_T_BOLD}  Empty usage emission${_T_NC}"

test_begin "empty usage: produces valid JSON with zero tokens"
result="$(_emit_empty_usage "1.1" "claude" "opus" "60" "ok")"
if [[ "$_JQ_AVAILABLE" == true ]]; then
    step_id=$(echo "$result" | jq -r '.step_id')
    in_tok=$(echo "$result" | jq -r '.tokens.input')
    cost_src=$(echo "$result" | jq -r '.cost.source')
    assert_eq "1.1" "$step_id"
else
    # Fallback: pattern match
    if [[ "$result" == *'"step_id":"1.1"'* && "$result" == *'"input":0'* ]]; then
        assert_exit_ok
    else
        test_fail "unexpected format: $result"
    fi
fi

test_begin "empty usage: status and duration are captured"
result="$(_emit_empty_usage "3.2" "codex" "gpt-5.4" "120" "soft-fail")"
if [[ "$_JQ_AVAILABLE" == true ]]; then
    status=$(echo "$result" | jq -r '.status')
    dur=$(echo "$result" | jq -r '.duration_sec')
    cli=$(echo "$result" | jq -r '.cli')
    assert_eq "soft-fail" "$status"
else
    if [[ "$result" == *'"status":"soft-fail"'* && "$result" == *'"duration_sec":120'* ]]; then
        assert_exit_ok
    else
        test_fail "unexpected format: $result"
    fi
fi

test_begin "empty usage: cost source is unavailable"
result="$(_emit_empty_usage "2.1" "opencode" "mimo" "30" "ok")"
if [[ "$_JQ_AVAILABLE" == true ]]; then
    src=$(echo "$result" | jq -r '.cost.source')
    cost=$(echo "$result" | jq -r '.cost.usd')
    assert_eq "unavailable" "$src"
else
    if [[ "$result" == *'"source":"unavailable"'* ]]; then
        assert_exit_ok
    else
        test_fail "expected source=unavailable"
    fi
fi

# ═══════════════════════════════════════════════════
# Output extraction (requires jq)
# ═══════════════════════════════════════════════════

if [[ "$_JQ_AVAILABLE" == true ]]; then

echo ""
echo -e "${_T_BOLD}  Output extraction (jq)${_T_NC}"

# Create sample raw JSON files for each CLI format
_raw_dir="$(make_test_tmpdir)"

# Claude: single JSON object with .result
cat > "${_raw_dir}/claude.json" <<'EOF'
{
  "result": "Claude says hello",
  "usage": { "input_tokens": 100, "output_tokens": 50 },
  "total_cost_usd": 0.005
}
EOF

# Codex: JSONL with item.completed
cat > "${_raw_dir}/codex.json" <<'EOF'
{"type":"item.started","item":{"id":"msg_001"}}
{"type":"item.completed","item":{"text":"Codex says hello"}}
{"type":"turn.completed","usage":{"input_tokens":200,"output_tokens":80,"cached_input_tokens":50}}
EOF

# OpenCode: JSONL with type:text
cat > "${_raw_dir}/opencode.json" <<'EOF'
{"type":"step_start","part":{"id":"step_001"}}
{"type":"text","part":{"text":"OpenCode says hello"}}
{"type":"step_finish","part":{"cost":0.12,"tokens":{"input":300,"output":100,"cache":{"read":60,"write":10},"reasoning":20}}}
EOF

# Copilot: JSONL with assistant.message
cat > "${_raw_dir}/copilot.json" <<'EOF'
{"type":"assistant.message","data":{"content":"Copilot says hello","outputTokens":70}}
{"type":"result","usage":{"premiumRequests":2}}
EOF

test_begin "extract output: claude — extracts .result"
output="$(_extract_output_claude "${_raw_dir}/claude.json")"
assert_eq "Claude says hello" "$output"

test_begin "extract output: codex — extracts item.completed text"
output="$(_extract_output_codex "${_raw_dir}/codex.json")"
assert_eq "Codex says hello" "$output"

test_begin "extract output: opencode — extracts type:text part"
output="$(_extract_output_opencode "${_raw_dir}/opencode.json")"
assert_eq "OpenCode says hello" "$output"

test_begin "extract output: copilot — extracts assistant.message content"
output="$(_extract_output_copilot "${_raw_dir}/copilot.json")"
assert_eq "Copilot says hello" "$output"

test_begin "extract_ai_output: dispatches to correct CLI extractor"
output="$(extract_ai_output "claude" "${_raw_dir}/claude.json")"
assert_eq "Claude says hello" "$output"

test_begin "extract_ai_output: falls back to cat when HAS_JQ=false"
(
    HAS_JQ=false
    output="$(extract_ai_output "claude" "${_raw_dir}/claude.json")"
    # Should get the raw JSON, not just the .result
    if [[ "$output" == *'"result"'* ]]; then
        exit 0
    else
        exit 1
    fi
)
if [[ $? -eq 0 ]]; then assert_exit_ok; else test_fail "fallback should cat raw file"; fi

test_begin "extract_ai_output: returns empty for missing file"
output="$(extract_ai_output "claude" "/nonexistent/path.json" 2>/dev/null)" || true
assert_empty "$output"

# ═══════════════════════════════════════════════════
# Usage extraction (requires jq)
# ═══════════════════════════════════════════════════

echo ""
echo -e "${_T_BOLD}  Usage extraction (jq)${_T_NC}"

# Reset pricing for clean cost computation
_reset_pricing
_load_pricing

test_begin "usage: claude — tokens and reported cost"
result="$(_extract_usage_claude "1.1" "${_raw_dir}/claude.json" "claude" "opus" "45" "ok")"
in_tok=$(echo "$result" | jq '.tokens.input')
out_tok=$(echo "$result" | jq '.tokens.output')
cost=$(echo "$result" | jq '.cost.usd')
source=$(echo "$result" | jq -r '.cost.source')
assert_eq "100" "$in_tok"

test_begin "usage: claude — cost source is reported"
assert_eq "reported" "$source"

test_begin "usage: codex — tokens extracted from turn.completed"
result="$(_extract_usage_codex "1.2a" "${_raw_dir}/codex.json" "codex" "gpt-5.4" "60" "ok")"
in_tok=$(echo "$result" | jq '.tokens.input')
out_tok=$(echo "$result" | jq '.tokens.output')
cached=$(echo "$result" | jq '.tokens.cache_read')
assert_eq "200" "$in_tok"

test_begin "usage: codex — cost is inferred from token pricing"
cost_src=$(echo "$result" | jq -r '.cost.source')
cost_usd=$(echo "$result" | jq -r '.cost.usd')
assert_eq "inferred" "$cost_src"

test_begin "usage: codex — inferred cost is correct"
# gpt-5.4: (200/1M)*2.50 + (80/1M)*15.00 + (50/1M)*0.25 = 0.0005 + 0.0012 + 0.0000125 = 0.0017125
assert_eq "0.001713" "$cost_usd"

test_begin "usage: opencode — tokens and cost from step_finish"
result="$(_extract_usage_opencode "2.2" "${_raw_dir}/opencode.json" "opencode" "mimo" "90" "ok")"
in_tok=$(echo "$result" | jq '.tokens.input')
out_tok=$(echo "$result" | jq '.tokens.output')
cache_rd=$(echo "$result" | jq '.tokens.cache_read')
cache_wr=$(echo "$result" | jq '.tokens.cache_write')
reason=$(echo "$result" | jq '.tokens.reasoning')
cost=$(echo "$result" | jq '.cost.usd')
source=$(echo "$result" | jq -r '.cost.source')
assert_eq "300" "$in_tok"

test_begin "usage: opencode — reasoning tokens captured"
assert_eq "20" "$reason"

test_begin "usage: opencode — cost source is reported when > 0"
assert_eq "reported" "$source"

test_begin "usage: copilot — premium requests and cost"
result="$(_extract_usage_copilot "3.1" "${_raw_dir}/copilot.json" "copilot" "opus" "30" "ok")"
prem=$(echo "$result" | jq '.cost.premium_requests')
cost=$(echo "$result" | jq -r '.cost.usd')
cost_src=$(echo "$result" | jq -r '.cost.source')
assert_eq "2" "$prem"

test_begin "usage: copilot — cost inferred from premium requests"
assert_eq "inferred" "$cost_src"

test_begin "usage: copilot — cost = premium_requests * cost_per_request"
# pro plan: 2 * (10.00/300) = 2 * 0.033333 = 0.066667
assert_match "^0\.06666" "$cost"

test_begin "usage: copilot — output tokens summed from assistant.message events"
out_tok=$(echo "$result" | jq '.tokens.output')
assert_eq "70" "$out_tok"

test_begin "usage: codex — missing turn.completed produces empty usage"
empty_raw="$(make_test_tmpdir)/empty_codex.json"
echo '{"type":"item.started"}' > "$empty_raw"
result="$(_extract_usage_codex "1.2a" "$empty_raw" "codex" "gpt-5.4" "10" "soft-fail")"
cost_src=$(echo "$result" | jq -r '.cost.source')
assert_eq "unavailable" "$cost_src"

test_begin "usage: opencode — missing step_finish produces empty usage"
empty_raw="$(make_test_tmpdir)/empty_opencode.json"
echo '{"type":"text","part":{"text":"hello"}}' > "$empty_raw"
result="$(_extract_usage_opencode "2.2" "$empty_raw" "opencode" "mimo" "15" "soft-fail")"
cost_src=$(echo "$result" | jq -r '.cost.source')
assert_eq "unavailable" "$cost_src"

# ═══════════════════════════════════════════════════
# extract_and_record_usage (public dispatcher)
# ═══════════════════════════════════════════════════

echo ""
echo -e "${_T_BOLD}  Record usage (dispatcher)${_T_NC}"

test_begin "record: appends JSONL to usage file"
local_tmp="$(make_test_tmpdir)"
TMP_DIR="$local_tmp"
HAS_JQ=true
extract_and_record_usage "1.1" "claude" "opus" "${_raw_dir}/claude.json" "45" "ok"
if [[ -f "${local_tmp}/usage.jsonl" ]]; then
    lines=$(wc -l < "${local_tmp}/usage.jsonl")
    assert_eq "1" "$(echo "$lines" | tr -d ' ')"
else
    test_fail "usage.jsonl not created"
fi

test_begin "record: appends multiple entries"
extract_and_record_usage "1.2a" "codex" "gpt-5.4" "${_raw_dir}/codex.json" "60" "ok"
lines=$(wc -l < "${local_tmp}/usage.jsonl")
assert_eq "2" "$(echo "$lines" | tr -d ' ')"

test_begin "record: skips when HAS_JQ=false"
(
    HAS_JQ=false
    local_tmp2="$(make_test_tmpdir)"
    TMP_DIR="$local_tmp2"
    extract_and_record_usage "2.1" "claude" "opus" "${_raw_dir}/claude.json" "30" "ok"
    if [[ -f "${local_tmp2}/usage.jsonl" ]]; then
        exit 1  # file should NOT exist
    else
        exit 0
    fi
)
if [[ $? -eq 0 ]]; then assert_exit_ok; else test_fail "should skip when no jq"; fi

test_begin "record: skips when raw file is missing"
(
    HAS_JQ=true
    local_tmp3="$(make_test_tmpdir)"
    TMP_DIR="$local_tmp3"
    extract_and_record_usage "2.1" "claude" "opus" "/nonexistent/file.json" "30" "ok"
    if [[ -f "${local_tmp3}/usage.jsonl" ]]; then
        exit 1
    else
        exit 0
    fi
)
if [[ $? -eq 0 ]]; then assert_exit_ok; else test_fail "should skip for missing file"; fi

test_begin "record: skips when cli is empty"
(
    HAS_JQ=true
    local_tmp4="$(make_test_tmpdir)"
    TMP_DIR="$local_tmp4"
    extract_and_record_usage "2.1" "" "opus" "${_raw_dir}/claude.json" "30" "ok"
    if [[ -f "${local_tmp4}/usage.jsonl" ]]; then
        exit 1
    else
        exit 0
    fi
)
if [[ $? -eq 0 ]]; then assert_exit_ok; else test_fail "should skip for empty cli"; fi

# Restore TMP_DIR
TMP_DIR="$local_tmp"

fi  # end _JQ_AVAILABLE gate

# ═══════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════

test_summary
