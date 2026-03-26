#!/usr/bin/env bash
# lib/monitor.sh — Activity spinner with stall detection
# Sourced by auto-bmad-story
#
# Requires: lib/core.sh sourced (format_duration)
# Reads globals: CURRENT_STEP_LOG
#
# Exports:
#   start_activity_monitor <label>
#   stop_activity_monitor

[[ -n "${_MONITOR_SH_LOADED:-}" ]] && return 0
_MONITOR_SH_LOADED=1

SPINNER_FRAMES='⣾⣽⣻⢿⡿⣟⣯⣷'
_monitor_pid=""

_cleanup_monitor() {
    rm -f "/tmp/auto-bmad-monitor-$$"
    if [[ -n "$_monitor_pid" ]]; then
        kill "$_monitor_pid" 2>/dev/null || true
        wait "$_monitor_pid" 2>/dev/null || true
        _monitor_pid=""
    fi
}

start_activity_monitor() {
    local label="$1"
    local start_time
    start_time=$(date +%s)

    # Stop any existing monitor first
    _cleanup_monitor

    touch "/tmp/auto-bmad-monitor-$$"

    (
        set +e  # Don't exit on errors in monitor
        local i=0
        local last_log_size=0
        local last_change_time=$start_time
        local spinner_active=false

        [[ -f "$CURRENT_STEP_LOG" ]] && last_log_size=$(wc -c < "$CURRENT_STEP_LOG" 2>/dev/null | tr -d ' ')

        while [[ -f "/tmp/auto-bmad-monitor-$$" ]]; do
            local now
            now=$(date +%s)
            local elapsed=$((now - start_time))
            local idx=$((i % ${#SPINNER_FRAMES}))
            local frame="${SPINNER_FRAMES:idx:1}"

            # Check log file for new output
            local current_log_size=0
            [[ -f "$CURRENT_STEP_LOG" ]] && current_log_size=$(wc -c < "$CURRENT_STEP_LOG" 2>/dev/null | tr -d ' ')

            if [[ "$current_log_size" != "$last_log_size" ]]; then
                # Output detected — clear spinner if visible
                if [[ "$spinner_active" == true ]]; then
                    printf '\r\033[K' >&2
                    spinner_active=false
                fi
                last_log_size=$current_log_size
                last_change_time=$now
                warned_at=0
            fi

            local quiet_seconds=$((now - last_change_time))

            if (( quiet_seconds >= 2 )); then
                # No output for 2+ seconds — show spinner
                printf '\r  %s %s [%s]' "$frame" "$label" "$(format_duration $elapsed)" >&2
                spinner_active=true
            fi

            sleep 0.1
            i=$((i + 1))
        done

        # Clear spinner on exit
        if [[ "$spinner_active" == true ]]; then
            printf '\r\033[K' >&2
        fi
    ) &
    _monitor_pid=$!
}

stop_activity_monitor() {
    _cleanup_monitor
}
