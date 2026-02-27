#!/usr/bin/env bash
# TruffleHog scanner wrapper — deep secret detection (git history + filesystem)
# Usage: trufflehog.sh [--scope-file <file>]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

SCOPE_FILE=""
OUTPUT_DIR="${SCAN_OUTPUT_DIR:-.}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scope-file) SCOPE_FILE="$2"; shift 2 ;;
    *) shift ;;
  esac
done

FINDINGS_FILE="${OUTPUT_DIR}/trufflehog-findings.jsonl"
> "$FINDINGS_FILE"

log_step "Running TruffleHog (deep secret detection)..."

RAW_OUTPUT=$(mktemp /tmp/cg-trufflehog-XXXXXX.json)
> "$RAW_OUTPUT"
EXIT_CODE=0

DOCKER_IMAGE="trufflesecurity/trufflehog:latest"

CONTAINER_SVC=$(get_container_service_for_tool "trufflehog" 2>/dev/null || true)

if [[ -n "$CONTAINER_SVC" ]]; then
  log_info "Running in project container ($CONTAINER_SVC)"
  $(get_compose_cmd) exec -T "$CONTAINER_SVC" trufflehog filesystem --json --no-update . \
    > "$RAW_OUTPUT" 2>/dev/null || EXIT_CODE=$?
elif docker_available; then
  docker run --rm -v "$(pwd):/workspace" -w /workspace \
    "$DOCKER_IMAGE" filesystem --json --no-update /workspace \
    > "$RAW_OUTPUT" 2>/dev/null || EXIT_CODE=$?
elif cmd_exists trufflehog; then
  trufflehog filesystem --json --no-update . \
    > "$RAW_OUTPUT" 2>/dev/null || EXIT_CODE=$?
else
  log_warn "TruffleHog not available, skipping"
  rm -f "$RAW_OUTPUT"
  exit 0
fi

# Parse output — TruffleHog outputs one JSON object per line (JSONL)
if [[ -f "$RAW_OUTPUT" ]] && [[ -s "$RAW_OUTPUT" ]]; then
  if cmd_exists python3; then
    python3 -c "
import json, sys
seen = set()
with open('$RAW_OUTPUT') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            # TruffleHog outputs SourceMetadata with Data containing file info
            source = obj.get('SourceMetadata', {}).get('Data', {})
            # Filesystem source has 'Filesystem' key
            fs_data = source.get('Filesystem', {})
            file_path = fs_data.get('file', '')
            line_num = fs_data.get('line', 0)
            # Git source has 'Git' key
            if not file_path:
                git_data = source.get('Git', {})
                file_path = git_data.get('file', '')
                line_num = git_data.get('line', 0)
            detector = obj.get('DetectorName', obj.get('detectorName', ''))
            raw = obj.get('Raw', '')
            # Deduplicate by detector + file + line
            key = f'{detector}:{file_path}:{line_num}'
            if key in seen:
                continue
            seen.add(key)
            finding = {
                'tool': 'trufflehog',
                'severity': 'high',
                'rule': detector,
                'message': f'Secret detected by {detector} detector',
                'file': file_path,
                'line': int(line_num) if line_num else 0,
                'autoFixable': False,
                'category': 'secrets'
            }
            print(json.dumps(finding))
        except (json.JSONDecodeError, KeyError):
            continue
" > "$FINDINGS_FILE"
  fi
fi

rm -f "$RAW_OUTPUT"

count=$(wc -l < "$FINDINGS_FILE" | tr -d ' ')
if [[ "$count" -gt 0 ]]; then
  log_warn "TruffleHog: found $count secret(s)!"
else
  log_ok "TruffleHog: no secrets found"
fi

echo "$FINDINGS_FILE"
