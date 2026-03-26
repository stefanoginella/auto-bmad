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
#   is_epic_start           — true if first story in epic
#   is_epic_end             — true if last story in epic
#   detect_story_file_path  — set STORY_FILE_PATH

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
            else
                return 1
            fi
        fi
        if [[ "$key" == "$STORY_ID" ]]; then
            found_current=true
        fi
    done < "$SPRINT_STATUS"
    return 1
}

detect_story_file_path() {
    local match
    match=$(find "$IMPL_ARTIFACTS" -maxdepth 1 -name "${STORY_ID}*.md" \
        ! -name "*--*" -type f 2>/dev/null | head -1)

    if [[ -n "$match" ]]; then
        STORY_FILE_PATH="$match"
    else
        local prefix
        prefix="$(echo "$STORY_ID" | cut -d'-' -f1-2)"
        match=$(find "$IMPL_ARTIFACTS" -maxdepth 1 -name "${prefix}-*" \
            ! -name "*--*" -type f -name "*.md" 2>/dev/null | head -1)
        STORY_FILE_PATH="${match:-}"
    fi
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
