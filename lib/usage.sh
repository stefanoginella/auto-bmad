#!/usr/bin/env bash
# lib/usage.sh — Token usage extraction, cost inference, and report generation
# Sourced by auto-bmad-story and auto-bmad-epic
#
# Requires: lib/core.sh, lib/config.sh sourced
# Reads globals: TMP_DIR STORY_ARTIFACTS STORY_ID EPIC_ID PIPELINE_START_TIME
#                IMPL_ARTIFACTS EPIC_ARTIFACTS HAS_JQ PROJECT_ROOT
#
# Exports:
#   extract_and_record_usage <step_id> <cli> <model> <raw_json_file> <duration> <status>
#   extract_ai_output <cli> <raw_json_file>  — stdout: text output from AI
#   generate_story_usage_report              — write usage-report.json
#   generate_epic_usage_report               — aggregate all story reports

[[ -n "${_USAGE_SH_LOADED:-}" ]] && return 0
_USAGE_SH_LOADED=1

# --- jq availability (set by config.sh or caller) ---
HAS_JQ="${HAS_JQ:-false}"

# --- Pricing data (parallel arrays, loaded once) ---
_PRICING_MODELS=()
_PRICING_INPUT=()
_PRICING_OUTPUT=()
_PRICING_CACHE_READ=()
_PRICING_CACHE_WRITE=()
_PRICING_LOADED=false

# Copilot premium request pricing (loaded from [copilot] section)
_COPILOT_COST_PER_REQUEST=""

# Load pricing.conf from cascade into parallel arrays + copilot config.
# Handles [tokens] and [copilot] sections. Later files override by model name.
_load_pricing() {
    [[ "$_PRICING_LOADED" == true ]] && return 0

    local copilot_plan="" copilot_cost="" copilot_requests=""
    local pro_cost="" pro_requests="" pro_plus_cost="" pro_plus_requests=""

    local conf_file
    while IFS= read -r conf_file; do
        local section=""
        while IFS= read -r line; do
            # Strip comments and whitespace
            line="${line%%#*}"
            line="${line#"${line%%[![:space:]]*}"}"
            line="${line%"${line##*[![:space:]]}"}"
            [[ -z "$line" ]] && continue

            # Section headers
            if [[ "$line" == "["*"]" ]]; then
                section="${line#[}"
                section="${section%]}"
                continue
            fi

            case "$section" in
                tokens|"")
                    # Token pricing: model  input  output  cache_read  cache_write
                    local model input output cache_read cache_write
                    read -r model input output cache_read cache_write <<< "$line"
                    # Override existing model entry
                    local i found=false
                    for ((i=0; i<${#_PRICING_MODELS[@]}; i++)); do
                        if [[ "${_PRICING_MODELS[$i]}" == "$model" ]]; then
                            _PRICING_INPUT[$i]="$input"
                            _PRICING_OUTPUT[$i]="$output"
                            _PRICING_CACHE_READ[$i]="$cache_read"
                            _PRICING_CACHE_WRITE[$i]="$cache_write"
                            found=true
                            break
                        fi
                    done
                    if [[ "$found" == false ]]; then
                        _PRICING_MODELS+=("$model")
                        _PRICING_INPUT+=("$input")
                        _PRICING_OUTPUT+=("$output")
                        _PRICING_CACHE_READ+=("$cache_read")
                        _PRICING_CACHE_WRITE+=("$cache_write")
                    fi
                    ;;
                copilot)
                    # Copilot config: key = value
                    local key="${line%%=*}" val="${line#*=}"
                    key="${key%"${key##*[![:space:]]}"}"
                    val="${val#"${val%%[![:space:]]*}"}"
                    case "$key" in
                        plan)              copilot_plan="$val" ;;
                        pro_cost)          pro_cost="$val" ;;
                        pro_requests)      pro_requests="$val" ;;
                        pro_plus_cost)     pro_plus_cost="$val" ;;
                        pro_plus_requests) pro_plus_requests="$val" ;;
                    esac
                    ;;
            esac
        done < "$conf_file"
    done < <(_conf_files "pricing.conf")

    # Bail if nothing was loaded at all
    [[ ${#_PRICING_MODELS[@]} -eq 0 && -z "$copilot_plan" ]] && return 1

    # Compute copilot cost per premium request from plan
    case "${copilot_plan:-pro}" in
        pro)
            copilot_cost="${pro_cost:-10.00}"
            copilot_requests="${pro_requests:-300}"
            ;;
        pro_plus|pro+)
            copilot_cost="${pro_plus_cost:-39.00}"
            copilot_requests="${pro_plus_requests:-1500}"
            ;;
    esac

    if [[ -n "$copilot_cost" && -n "$copilot_requests" ]]; then
        _COPILOT_COST_PER_REQUEST=$(awk "BEGIN { printf \"%.6f\", $copilot_cost / $copilot_requests }")
    fi

    _PRICING_LOADED=true
}

# Look up pricing for a model. Echoes "input|output|cache_read|cache_write"
# Returns 1 if model not found.
_lookup_pricing() {
    local model="$1"
    _load_pricing
    local i
    for ((i=0; i<${#_PRICING_MODELS[@]}; i++)); do
        if [[ "${_PRICING_MODELS[$i]}" == "$model" ]]; then
            echo "${_PRICING_INPUT[$i]}|${_PRICING_OUTPUT[$i]}|${_PRICING_CACHE_READ[$i]}|${_PRICING_CACHE_WRITE[$i]}"
            return 0
        fi
    done
    return 1
}

# Compute cost from tokens and pricing rates.
# Usage: _compute_cost <input_tok> <output_tok> <cache_read_tok> <cache_write_tok> <model>
# Echoes cost in USD (decimal). Returns 1 if pricing unavailable.
_compute_cost() {
    local in_tok="$1" out_tok="$2" cache_rd="$3" cache_wr="$4" model="$5"
    local pricing
    pricing="$(_lookup_pricing "$model")" || return 1
    local p_in p_out p_crd p_cwr
    IFS='|' read -r p_in p_out p_crd p_cwr <<< "$pricing"

    # Replace "-" with 0
    [[ "$p_in" == "-" ]]  && p_in=0
    [[ "$p_out" == "-" ]] && p_out=0
    [[ "$p_crd" == "-" ]] && p_crd=0
    [[ "$p_cwr" == "-" ]] && p_cwr=0
    [[ "$in_tok" == "null" || -z "$in_tok" ]]   && in_tok=0
    [[ "$out_tok" == "null" || -z "$out_tok" ]]  && out_tok=0
    [[ "$cache_rd" == "null" || -z "$cache_rd" ]] && cache_rd=0
    [[ "$cache_wr" == "null" || -z "$cache_wr" ]] && cache_wr=0

    # cost = (tokens / 1_000_000) * rate_per_MTok
    # Use awk for floating point
    awk "BEGIN {
        cost = ($in_tok / 1000000.0) * $p_in + \
               ($out_tok / 1000000.0) * $p_out + \
               ($cache_rd / 1000000.0) * $p_crd + \
               ($cache_wr / 1000000.0) * $p_cwr
        printf \"%.6f\", cost
    }"
}

# --- Per-CLI Text Extraction ---
# Each function reads the raw JSON file and outputs the AI's text response.

_extract_output_claude() {
    local raw="$1"
    # Claude --output-format json: single JSON object with .result field
    jq -r '.result // empty' "$raw" 2>/dev/null
}

_extract_output_codex() {
    local raw="$1"
    # Codex --json: JSONL stream, text in item.completed events
    grep '"type":"item.completed"' "$raw" 2>/dev/null | \
        jq -r '.item.text // empty' 2>/dev/null
}

_extract_output_opencode() {
    local raw="$1"
    # OpenCode --format json: JSONL stream, text in "type":"text" events
    grep '"type":"text"' "$raw" 2>/dev/null | \
        jq -r '.part.text // empty' 2>/dev/null
}

_extract_output_copilot() {
    local raw="$1"
    # Copilot --output-format json: JSONL stream, text in assistant.message events
    grep '"type":"assistant.message"' "$raw" 2>/dev/null | \
        jq -r '.data.content // empty' 2>/dev/null
}

# Public dispatcher: extract text output from raw JSON file.
# Usage: extract_ai_output <cli> <raw_json_file>
extract_ai_output() {
    local cli="$1" raw="$2"
    if [[ "$HAS_JQ" != true || ! -f "$raw" ]]; then
        # Fallback: raw file might still be readable text
        cat "$raw" 2>/dev/null
        return
    fi
    "_extract_output_${cli}" "$raw"
}

# --- Per-CLI Usage Extraction ---
# Each function reads the raw JSON and outputs a normalized JSONL line.

_extract_usage_claude() {
    local step_id="$1" raw="$2" cli="$3" model="$4" duration="$5" status="$6"
    # Claude reports: .usage.input_tokens, .usage.output_tokens,
    #   .usage.cache_read_input_tokens, .usage.cache_creation_input_tokens,
    #   .total_cost_usd, .modelUsage.*.costUSD
    local result
    result=$(jq -c --arg sid "$step_id" --arg cli "$cli" --arg model "$model" \
       --argjson dur "$duration" --arg st "$status" '
    {
        step_id: $sid,
        cli: $cli,
        model: $model,
        tokens: {
            input: (.usage.input_tokens // 0),
            output: (.usage.output_tokens // 0),
            cache_read: (.usage.cache_read_input_tokens // 0),
            cache_write: (.usage.cache_creation_input_tokens // 0),
            reasoning: 0
        },
        cost: {
            usd: (.total_cost_usd // 0),
            source: "reported"
        },
        duration_sec: $dur,
        status: $st
    }' "$raw" 2>/dev/null) || {
        _emit_empty_usage "$step_id" "$cli" "$model" "$duration" "$status"
        return
    }
    echo "$result"
}

_extract_usage_codex() {
    local step_id="$1" raw="$2" cli="$3" model="$4" duration="$5" status="$6"
    # Codex: last line (turn.completed) has .usage.input_tokens, .output_tokens, .cached_input_tokens
    local usage_line
    usage_line=$(grep '"type":"turn.completed"' "$raw" 2>/dev/null | tail -1)
    if [[ -z "$usage_line" ]]; then
        _emit_empty_usage "$step_id" "$cli" "$model" "$duration" "$status"
        return
    fi

    local in_tok out_tok cached_tok
    in_tok=$(echo "$usage_line" | jq -r '.usage.input_tokens // 0' 2>/dev/null) || in_tok=0
    out_tok=$(echo "$usage_line" | jq -r '.usage.output_tokens // 0' 2>/dev/null) || out_tok=0
    cached_tok=$(echo "$usage_line" | jq -r '.usage.cached_input_tokens // 0' 2>/dev/null) || cached_tok=0

    # Ensure numeric values — fall back to empty usage on parse failure
    [[ "$in_tok" =~ ^[0-9]+$ ]] || in_tok=0
    [[ "$out_tok" =~ ^[0-9]+$ ]] || out_tok=0
    [[ "$cached_tok" =~ ^[0-9]+$ ]] || cached_tok=0

    local cost_usd="0" cost_source="unavailable"
    local inferred
    if inferred=$(_compute_cost "$in_tok" "$out_tok" "$cached_tok" "0" "$model"); then
        cost_usd="$inferred"
        cost_source="inferred"
    fi

    printf '{"step_id":"%s","cli":"%s","model":"%s","tokens":{"input":%s,"output":%s,"cache_read":%s,"cache_write":0,"reasoning":0},"cost":{"usd":%s,"source":"%s"},"duration_sec":%s,"status":"%s"}\n' \
        "$step_id" "$cli" "$model" "$in_tok" "$out_tok" "$cached_tok" \
        "$cost_usd" "$cost_source" "$duration" "$status"
}

_extract_usage_opencode() {
    local step_id="$1" raw="$2" cli="$3" model="$4" duration="$5" status="$6"
    # OpenCode: step_finish event has .part.cost and .part.tokens
    local finish_line
    finish_line=$(grep '"type":"step_finish"' "$raw" 2>/dev/null | tail -1)
    if [[ -z "$finish_line" ]]; then
        _emit_empty_usage "$step_id" "$cli" "$model" "$duration" "$status"
        return
    fi

    local result
    result=$(echo "$finish_line" | jq -c --arg sid "$step_id" --arg cli "$cli" --arg model "$model" \
       --argjson dur "$duration" --arg st "$status" '
    {
        step_id: $sid,
        cli: $cli,
        model: $model,
        tokens: {
            input: (.part.tokens.input // 0),
            output: (.part.tokens.output // 0),
            cache_read: (.part.tokens.cache.read // 0),
            cache_write: (.part.tokens.cache.write // 0),
            reasoning: (.part.tokens.reasoning // 0)
        },
        cost: {
            usd: (.part.cost // 0),
            source: (if (.part.cost // 0) > 0 then "reported" else "unavailable" end)
        },
        duration_sec: $dur,
        status: $st
    }' 2>/dev/null) || {
        _emit_empty_usage "$step_id" "$cli" "$model" "$duration" "$status"
        return
    }
    echo "$result"
}

_extract_usage_copilot() {
    local step_id="$1" raw="$2" cli="$3" model="$4" duration="$5" status="$6"
    # Copilot bills by premium requests, not tokens.
    # The result event reports .usage.premiumRequests consumed.
    # Cost = premiumRequests × cost_per_request (from [copilot] section of pricing.conf)
    local result_line
    result_line=$(grep '"type":"result"' "$raw" 2>/dev/null | tail -1)

    local premium_reqs=0 out_tok=0
    if [[ -n "$result_line" ]]; then
        premium_reqs=$(echo "$result_line" | jq -r '.usage.premiumRequests // 0' 2>/dev/null)
    fi

    # Sum outputTokens from all assistant.message events (for analytics, not costing)
    out_tok=$(grep '"type":"assistant.message"' "$raw" 2>/dev/null | \
        jq -r '.data.outputTokens // 0' 2>/dev/null | \
        awk '{s+=$1} END {print s+0}')

    # Compute cost from premium requests
    _load_pricing
    local cost_usd="0" cost_source="unavailable"
    if [[ -n "$_COPILOT_COST_PER_REQUEST" && "$premium_reqs" != "0" ]]; then
        cost_usd=$(awk "BEGIN { printf \"%.6f\", $premium_reqs * $_COPILOT_COST_PER_REQUEST }")
        cost_source="inferred"
    fi

    printf '{"step_id":"%s","cli":"%s","model":"%s","tokens":{"input":null,"output":%s,"cache_read":null,"cache_write":null,"reasoning":null},"cost":{"usd":%s,"source":"%s","premium_requests":%s},"duration_sec":%s,"status":"%s"}\n' \
        "$step_id" "$cli" "$model" "$out_tok" \
        "$cost_usd" "$cost_source" "$premium_reqs" "$duration" "$status"
}

# Emit a zero-usage entry when extraction fails.
_emit_empty_usage() {
    local step_id="$1" cli="$2" model="$3" duration="$4" status="$5"
    printf '{"step_id":"%s","cli":"%s","model":"%s","tokens":{"input":0,"output":0,"cache_read":0,"cache_write":0,"reasoning":0},"cost":{"usd":0,"source":"unavailable"},"duration_sec":%s,"status":"%s"}\n' \
        "$step_id" "$cli" "$model" "$duration" "$status"
}

# --- Public: Record Usage for a Step ---

# Extract usage from raw JSON and append to the JSONL accumulator.
# Called after each run_ai() completes.
# Usage: extract_and_record_usage <step_id> <cli> <model> <raw_json_file> <duration> <status>
extract_and_record_usage() {
    [[ "$HAS_JQ" != true ]] && return 0
    local step_id="$1" cli="$2" model="$3" raw="$4" duration="$5" status="$6"
    local usage_file="${TMP_DIR}/usage.jsonl"

    [[ ! -f "$raw" ]] && return 0

    "_extract_usage_${cli}" "$step_id" "$raw" "$cli" "$model" "$duration" "$status" >> "$usage_file"
}

# --- Report Generation ---

# Generate per-story usage report JSON.
# Reads: TMP_DIR/usage.jsonl → STORY_ARTIFACTS/usage-report.json
generate_story_usage_report() {
    [[ "$HAS_JQ" != true ]] && return 0
    local usage_file="${TMP_DIR}/usage.jsonl"
    [[ ! -f "$usage_file" ]] && return 0

    local report="${STORY_ARTIFACTS}/usage-report.json"
    mkdir -p "$(dirname "$report")"

    jq -s --arg sid "${STORY_ID:-unknown}" --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        --argjson wall "$(( $(date +%s) - PIPELINE_START_TIME ))" '
    {
        story_id: $sid,
        timestamp: $ts,
        wall_time_sec: $wall,
        steps: .,
        totals: {
            input_tokens: (map(.tokens.input // 0) | add),
            output_tokens: (map(.tokens.output // 0) | add),
            cache_read_tokens: (map(.tokens.cache_read // 0) | add),
            cache_write_tokens: (map(.tokens.cache_write // 0) | add),
            reasoning_tokens: (map(.tokens.reasoning // 0) | add),
            premium_requests: (map(.cost.premium_requests // 0) | add),
            total_cost_usd: (map(.cost.usd // 0) | add),
            cost_by_source: {
                reported: (map(select(.cost.source == "reported") | .cost.usd // 0) | add // 0),
                inferred: (map(select(.cost.source == "inferred") | .cost.usd // 0) | add // 0)
            },
            compute_time_sec: (map(.duration_sec) | add),
            steps_run: length,
            by_cli: (group_by(.cli) | map({
                cli: .[0].cli,
                steps: length,
                input_tokens: (map(.tokens.input // 0) | add),
                output_tokens: (map(.tokens.output // 0) | add),
                premium_requests: (map(.cost.premium_requests // 0) | add),
                cost_usd: (map(.cost.usd // 0) | add)
            })),
            by_model: (group_by(.model) | map({
                model: .[0].model,
                steps: length,
                input_tokens: (map(.tokens.input // 0) | add),
                output_tokens: (map(.tokens.output // 0) | add),
                premium_requests: (map(.cost.premium_requests // 0) | add),
                cost_usd: (map(.cost.usd // 0) | add)
            }))
        }
    }' "$usage_file" > "$report" 2>/dev/null

    log_ok "Usage report: ${report}"
}

# Generate epic-level aggregate usage report.
# Scans STORY_ARTIFACTS dirs for usage-report.json files.
# Writes: EPIC_ARTIFACTS/epic-usage-report.json
generate_epic_usage_report() {
    [[ "$HAS_JQ" != true ]] && return 0
    local epic_artifacts="${EPIC_ARTIFACTS:-${IMPL_ARTIFACTS}/auto-bmad/epic-${EPIC_ID}}"
    local auto_bmad_dir="${IMPL_ARTIFACTS}/auto-bmad"
    local -a reports=()

    # Find all story usage reports under the auto-bmad directory
    while IFS= read -r f; do
        [[ -f "$f" ]] && reports+=("$f")
    done < <(find "$auto_bmad_dir" -name "usage-report.json" -maxdepth 2 2>/dev/null | sort)

    [[ ${#reports[@]} -eq 0 ]] && return 0

    local report="${epic_artifacts}/epic-usage-report.json"
    mkdir -p "$(dirname "$report")"

    jq -s --arg eid "${EPIC_ID:-unknown}" --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '
    {
        epic_id: $eid,
        timestamp: $ts,
        stories: [.[].story_id],
        story_reports: .,
        totals: {
            total_input_tokens: ([.[].totals.input_tokens] | add),
            total_output_tokens: ([.[].totals.output_tokens] | add),
            total_cache_read_tokens: ([.[].totals.cache_read_tokens] | add),
            total_cache_write_tokens: ([.[].totals.cache_write_tokens] | add),
            total_reasoning_tokens: ([.[].totals.reasoning_tokens] | add),
            total_premium_requests: ([.[].totals.premium_requests] | add),
            total_cost_usd: ([.[].totals.total_cost_usd] | add),
            cost_by_source: {
                reported: ([.[].totals.cost_by_source.reported] | add),
                inferred: ([.[].totals.cost_by_source.inferred] | add)
            },
            total_compute_sec: ([.[].totals.compute_time_sec] | add),
            total_wall_sec: ([.[].wall_time_sec] | add),
            stories_run: length,
            total_steps: ([.[].totals.steps_run] | add),
            by_cli: (
                [.[].totals.by_cli[]] | group_by(.cli) | map({
                    cli: .[0].cli,
                    steps: (map(.steps) | add),
                    input_tokens: (map(.input_tokens) | add),
                    output_tokens: (map(.output_tokens) | add),
                    premium_requests: (map(.premium_requests) | add),
                    cost_usd: (map(.cost_usd) | add)
                })
            ),
            by_model: (
                [.[].totals.by_model[]] | group_by(.model) | map({
                    model: .[0].model,
                    steps: (map(.steps) | add),
                    input_tokens: (map(.input_tokens) | add),
                    output_tokens: (map(.output_tokens) | add),
                    premium_requests: (map(.premium_requests) | add),
                    cost_usd: (map(.cost_usd) | add)
                })
            )
        }
    }' "${reports[@]}" > "$report" 2>/dev/null

    log_ok "Epic usage report: ${report}"
}
