#!/usr/bin/env bash
# lib/detection.sh — Story and epic detection from sprint-status.yaml
# Sourced by auto-bmad-story and auto-bmad-epic
#
# Requires: lib/core.sh sourced
# Reads globals: SPRINT_STATUS STORY_ID EPIC_ID IMPL_ARTIFACTS
#
# Exports:
#   detect_next_story       — set STORY_ID from sprint status
#   detect_next_epic        — set EPIC_ID from sprint status
#   collect_epic_stories    — set STORY_IDS STORY_STATUSES STORY_COUNT
#   validate_epic           — verify epic has remaining stories
#   extract_epic_id         — set EPIC_ID from STORY_ID
#   extract_short_id        — set STORY_SHORT_ID from STORY_ID
#   extract_story_num       — echo story number
#   _find_previous_story    — echo previous story ID
#   detect_previous_story   — set PREV_STORY_FILE (same-epic only)
#   is_epic_start           — true if first story in epic
#   is_epic_end             — true if last story in epic
#   detect_story_file_path  — set STORY_FILE_PATH
#   collect_epic_story_paths — echo newline-separated story file paths for epic

[[ -n "${_DETECTION_SH_LOADED:-}" ]] && return 0
_DETECTION_SH_LOADED=1

# --- Story Detection ---

detect_next_story() {
    if [[ ! -f "$SPRINT_STATUS" ]]; then
        log_error "Sprint status file not found: ${SPRINT_STATUS}"
        exit 1
    fi

    local found="" in_progress_found=""

    while IFS=: read -r key status; do
        key="${key#"${key%%[![:space:]]*}"}"; key="${key%"${key##*[![:space:]]}"}"
        status="${status#"${status%%[![:space:]]*}"}"; status="${status%"${status##*[![:space:]]}"}"

        case "$key" in
            \#*|""|epic-*|generated*|last_updated*|project*|tracking_system*|story_location*|development_status*) continue ;;
        esac

        [[ "$key" =~ ^[0-9]+-[0-9]+- ]] || continue

        if [[ "$status" == "in-progress" && -z "$in_progress_found" ]]; then
            in_progress_found="$key"
        fi

        if [[ "$status" == "backlog" && -z "$found" ]]; then
            found="$key"
        fi
    done < "$SPRINT_STATUS"

    if [[ -n "$in_progress_found" ]]; then
        STORY_ID="$in_progress_found"
    elif [[ -n "$found" ]]; then
        STORY_ID="$found"
    else
        echo ""
        log_error "No stories with status 'in-progress' or 'backlog' found in sprint-status.yaml"
        exit 1
    fi
}

extract_epic_id() {
    EPIC_ID="${STORY_ID%%-*}"
}

extract_short_id() {
    local epic="${STORY_ID%%-*}"
    local remainder="${STORY_ID#*-}"
    local story_num="${remainder%%-*}"
    STORY_SHORT_ID="${epic}-${story_num}"
}

extract_story_num() {
    local remainder="${STORY_ID#*-}"
    echo "${remainder%%-*}"
}

_find_previous_story() {
    local prev=""
    while IFS=: read -r key _status; do
        key="${key#"${key%%[![:space:]]*}"}"; key="${key%"${key##*[![:space:]]}"}"
        case "$key" in
            \#*|""|epic-*|generated*|last_updated*|project*|tracking_system*|story_location*|development_status*) continue ;;
        esac
        [[ "$key" =~ ^[0-9]+-[0-9]+- ]] || continue
        if [[ "$key" == "$STORY_ID" ]]; then
            echo "$prev"
            return 0
        fi
        prev="$key"
    done < "$SPRINT_STATUS"
    echo ""
}

# Detect previous story in the same epic and resolve its file path.
# Sets PREV_STORY_FILE to the path, or empty string if first story in epic.
detect_previous_story() {
    local prev_id
    prev_id="$(_find_previous_story)"
    PREV_STORY_FILE=""

    # Empty or not same epic → no previous story
    if [[ -z "$prev_id" ]]; then
        return 0
    fi
    local prev_epic="${prev_id%%-*}"
    if [[ "$prev_epic" != "$EPIC_ID" ]]; then
        return 0
    fi

    PREV_STORY_FILE="$(_resolve_story_file_path "$prev_id")"
}

is_epic_start() {
    local story_num
    story_num="$(extract_story_num)"
    [[ "$story_num" == "1" ]]
}

is_epic_end() {
    local found_current=false
    while IFS=: read -r key _status; do
        key="${key#"${key%%[![:space:]]*}"}"; key="${key%"${key##*[![:space:]]}"}"
        if [[ "$found_current" == "true" ]]; then
            if [[ "$key" == "epic-${EPIC_ID}-retrospective" ]]; then
                return 0
            # Another story in the same epic follows — not the end
            elif [[ "$key" =~ ^${EPIC_ID}-[0-9]+- ]]; then
                return 1
            fi
            # Skip non-story lines (comments, metadata) and keep looking
            continue
        fi
        if [[ "$key" == "$STORY_ID" ]]; then
            found_current=true
        fi
    done < "$SPRINT_STATUS"
    # If we found the current story but no more stories followed → epic end
    [[ "$found_current" == "true" ]]
}

detect_story_file_path() {
    STORY_FILE_PATH="$(_resolve_story_file_path "$STORY_ID")"
}

# --- Story File Path Resolution (for arbitrary story IDs) ---

# Resolve a story ID to its file path in IMPL_ARTIFACTS.
# Usage: _resolve_story_file_path "1-2-some-story"
# Prints the path or empty string.
_resolve_story_file_path() {
    local sid="$1"
    local match
    match=$(find "$IMPL_ARTIFACTS" -maxdepth 1 -name "${sid}*.md" \
        ! -name "*--*" -type f 2>/dev/null | head -1)

    if [[ -n "$match" ]]; then
        echo "$match"
        return 0
    fi

    local prefix
    prefix="$(echo "$sid" | cut -d'-' -f1-2)"
    match=$(find "$IMPL_ARTIFACTS" -maxdepth 1 -name "${prefix}-*" \
        ! -name "*--*" -type f -name "*.md" 2>/dev/null | head -1)
    echo "${match:-}"
}

# --- Collect Epic Story Paths ---

# Returns newline-separated list of story file paths for the given epic.
# Reads EPIC_ID and SPRINT_STATUS globals.
collect_epic_story_paths() {
    local paths=""
    local sid
    while IFS=: read -r key _status; do
        key="${key#"${key%%[![:space:]]*}"}"; key="${key%"${key##*[![:space:]]}"}"
        [[ "$key" =~ ^${EPIC_ID}-[0-9]+- ]] || continue
        local fpath
        fpath="$(_resolve_story_file_path "$key")"
        if [[ -n "$fpath" ]]; then
            [[ -n "$paths" ]] && paths="${paths}
"
            paths="${paths}${fpath}"
        fi
    done < "$SPRINT_STATUS"
    echo "$paths"
}

# --- Sprint Status Validation ---

# Validate sprint-status.yaml structure and content.
# Returns 0 if valid, 1 if errors found. Prints issues to stdout.
validate_sprint_status() {
    local status_file="${1:-$SPRINT_STATUS}"
    local errors=0 warnings=0 line_num=0
    local -a seen_stories=() seen_epics=()
    local valid_statuses="backlog in-progress done optional ready-for-dev review"

    if [[ ! -f "$status_file" ]]; then
        log_error "Sprint status file not found: ${status_file}"
        return 1
    fi

    echo -e "${BOLD}Validating:${NC} ${status_file}"
    echo ""

    while IFS= read -r raw_line; do
        line_num=$((line_num + 1))

        # Strip comments and blank lines
        local line="${raw_line%%#*}"
        line="${line#"${line%%[![:space:]]*}"}"; line="${line%"${line##*[![:space:]]}"}"
        [[ -z "$line" ]] && continue

        # Must contain a colon
        if [[ "$line" != *:* ]]; then
            log_warn "Line ${line_num}: missing colon separator: ${raw_line}"
            warnings=$((warnings + 1))
            continue
        fi

        local key status
        key="${line%%:*}"
        status="${line#*:}"
        key="${key#"${key%%[![:space:]]*}"}"; key="${key%"${key##*[![:space:]]}"}"
        status="${status#"${status%%[![:space:]]*}"}"; status="${status%"${status##*[![:space:]]}"}"

        # Skip metadata keys
        case "$key" in
            generated*|last_updated*|project*|tracking_system*|story_location*|development_status*) continue ;;
        esac

        # Epic header (epic-N)
        if [[ "$key" =~ ^epic-[0-9]+$ ]]; then
            local eid="${key#epic-}"
            # Check for duplicate
            local _dup
            for _dup in "${seen_epics[@]+"${seen_epics[@]}"}"; do
                if [[ "$_dup" == "$eid" ]]; then
                    log_error "Line ${line_num}: duplicate epic: ${key}"
                    errors=$((errors + 1))
                fi
            done
            seen_epics+=("$eid")

            # Validate status
            if [[ " $valid_statuses " != *" $status "* ]]; then
                log_error "Line ${line_num}: invalid status '${status}' for ${key} (expected: ${valid_statuses})"
                errors=$((errors + 1))
            fi
            continue
        fi

        # Retrospective entry (epic-N-retrospective)
        if [[ "$key" =~ ^epic-[0-9]+-retrospective$ ]]; then
            if [[ " $valid_statuses " != *" $status "* ]]; then
                log_error "Line ${line_num}: invalid status '${status}' for ${key} (expected: ${valid_statuses})"
                errors=$((errors + 1))
            fi
            continue
        fi

        # Story entry (N-N-slug)
        if [[ "$key" =~ ^[0-9]+-[0-9]+- ]]; then
            # Check format: must have at least 3 segments
            if [[ ! "$key" =~ ^[0-9]+-[0-9]+-[a-zA-Z0-9] ]]; then
                log_warn "Line ${line_num}: story ID '${key}' has unusual format (expected: N-N-slug)"
                warnings=$((warnings + 1))
            fi

            # Check for duplicate
            local _dup
            for _dup in "${seen_stories[@]+"${seen_stories[@]}"}"; do
                if [[ "$_dup" == "$key" ]]; then
                    log_error "Line ${line_num}: duplicate story: ${key}"
                    errors=$((errors + 1))
                fi
            done
            seen_stories+=("$key")

            # Validate status
            if [[ " $valid_statuses " != *" $status "* ]]; then
                log_error "Line ${line_num}: invalid status '${status}' for ${key} (expected: ${valid_statuses})"
                errors=$((errors + 1))
            fi

            # Check epic exists
            local story_epic="${key%%-*}"
            local _found=false
            local _e
            for _e in "${seen_epics[@]+"${seen_epics[@]}"}"; do
                [[ "$_e" == "$story_epic" ]] && { _found=true; break; }
            done
            if [[ "$_found" == "false" ]]; then
                log_warn "Line ${line_num}: story ${key} references epic ${story_epic} which hasn't been declared yet"
                warnings=$((warnings + 1))
            fi
            continue
        fi

        # Unknown entry
        log_warn "Line ${line_num}: unrecognized entry: ${key}"
        warnings=$((warnings + 1))
    done < "$status_file"

    # Summary
    echo ""
    echo -e "  ${BOLD}Summary:${NC} ${#seen_epics[@]} epic(s), ${#seen_stories[@]} story/stories"
    if (( errors == 0 && warnings == 0 )); then
        log_ok "Sprint status is valid"
        return 0
    fi
    (( warnings > 0 )) && log_warn "${warnings} warning(s)"
    if (( errors > 0 )); then
        log_error "${errors} error(s) — fix before running pipeline"
        return 1
    fi
    return 0
}

# --- Epic Detection ---

detect_next_epic() {
    if [[ ! -f "$SPRINT_STATUS" ]]; then
        log_error "Sprint status file not found: ${SPRINT_STATUS}"
        exit 1
    fi

    local in_progress_epic="" first_non_done_epic=""

    while IFS=: read -r key status; do
        key="${key#"${key%%[![:space:]]*}"}"; key="${key%"${key##*[![:space:]]}"}"
        status="${status#"${status%%[![:space:]]*}"}"; status="${status%"${status##*[![:space:]]}"}"

        [[ "$key" =~ ^epic-([0-9]+)$ ]] || continue
        local eid="${BASH_REMATCH[1]}"

        if [[ "$status" == "in-progress" && -z "$in_progress_epic" ]]; then
            in_progress_epic="$eid"
        fi
        if [[ "$status" != "done" && -z "$first_non_done_epic" ]]; then
            first_non_done_epic="$eid"
        fi
    done < "$SPRINT_STATUS"

    if [[ -n "$in_progress_epic" ]]; then
        EPIC_ID="$in_progress_epic"
    elif [[ -n "$first_non_done_epic" ]]; then
        EPIC_ID="$first_non_done_epic"
    else
        log_error "No epics with status 'in-progress' or 'backlog' found in sprint-status.yaml"
        exit 1
    fi
}

collect_epic_stories() {
    STORY_IDS=()
    STORY_STATUSES=()

    while IFS=: read -r key status; do
        key="${key#"${key%%[![:space:]]*}"}"; key="${key%"${key##*[![:space:]]}"}"
        status="${status#"${status%%[![:space:]]*}"}"; status="${status%"${status##*[![:space:]]}"}"

        [[ "$key" =~ ^${EPIC_ID}-[0-9]+- ]] || continue

        STORY_IDS+=("$key")
        STORY_STATUSES+=("$status")
    done < "$SPRINT_STATUS"

    STORY_COUNT=${#STORY_IDS[@]}
}

validate_epic() {
    if (( STORY_COUNT == 0 )); then
        log_error "No stories found for epic ${EPIC_ID} in sprint-status.yaml"
        exit 1
    fi

    local remaining=0
    for status in "${STORY_STATUSES[@]}"; do
        [[ "$status" != "done" ]] && remaining=$((remaining + 1))
    done

    if (( remaining == 0 )); then
        log_error "All stories in epic ${EPIC_ID} are already done"
        exit 1
    fi
}
