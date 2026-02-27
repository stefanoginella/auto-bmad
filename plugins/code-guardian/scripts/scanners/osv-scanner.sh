#!/usr/bin/env bash
# OSV-Scanner wrapper — universal dependency vulnerability scanning
# Scans lockfiles across all ecosystems (npm, pip, go, cargo, bundler, maven, nuget, composer, etc.)
# Usage: osv-scanner.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

OUTPUT_DIR="${SCAN_OUTPUT_DIR:-.}"

FINDINGS_FILE="${OUTPUT_DIR}/osv-scanner-findings.jsonl"
> "$FINDINGS_FILE"

log_step "Running OSV-Scanner (universal dependency vulnerabilities)..."

RAW_OUTPUT=$(mktemp /tmp/cg-osv-scanner-XXXXXX.json)
EXIT_CODE=0

DOCKER_IMAGE="ghcr.io/google/osv-scanner:latest"

CONTAINER_SVC=$(get_container_service_for_tool "osv-scanner" 2>/dev/null || true)

if [[ -n "$CONTAINER_SVC" ]]; then
  log_info "Running in project container ($CONTAINER_SVC)"
  $(get_compose_cmd) exec -T "$CONTAINER_SVC" osv-scanner --format json -r . \
    > "$RAW_OUTPUT" 2>/dev/null || EXIT_CODE=$?
elif docker_available; then
  docker run --rm -v "$(pwd):/workspace" -w /workspace \
    "$DOCKER_IMAGE" --format json -r /workspace \
    > "$RAW_OUTPUT" 2>/dev/null || EXIT_CODE=$?
elif cmd_exists osv-scanner; then
  osv-scanner --format json -r . \
    > "$RAW_OUTPUT" 2>/dev/null || EXIT_CODE=$?
else
  log_warn "OSV-Scanner not available, skipping"
  rm -f "$RAW_OUTPUT"
  exit 0
fi

# Parse output
if [[ -f "$RAW_OUTPUT" ]] && [[ -s "$RAW_OUTPUT" ]]; then
  if cmd_exists python3; then
    python3 -c "
import json, sys
try:
    data = json.load(open('$RAW_OUTPUT'))
    results = data.get('results', [])
    for result in results:
        source_path = result.get('source', {}).get('path', '')
        for pkg in result.get('packages', []):
            pkg_info = pkg.get('package', {})
            pkg_name = pkg_info.get('name', '')
            pkg_version = pkg_info.get('version', '')
            for vuln in pkg.get('vulnerabilities', []):
                vuln_id = vuln.get('id', '')
                summary = vuln.get('summary', vuln.get('details', ''))
                # Determine severity from database_specific or severity array
                sev = 'medium'
                severity_list = vuln.get('severity', [])
                if severity_list:
                    score_str = severity_list[0].get('score', '')
                    # CVSS score string — extract numeric part if present
                    try:
                        # Try parsing as CVSS vector; fall back to numeric
                        if '/' in score_str:
                            # CVSS vector like CVSS:3.1/AV:N/AC:L/... — extract base score
                            pass
                        else:
                            score = float(score_str)
                            if score >= 7.0:
                                sev = 'high'
                            elif score >= 4.0:
                                sev = 'medium'
                            else:
                                sev = 'low'
                    except (ValueError, TypeError):
                        pass
                # Check database_specific severity
                db_sev = vuln.get('database_specific', {}).get('severity', '').upper()
                if db_sev in ('CRITICAL', 'HIGH'):
                    sev = 'high'
                elif db_sev == 'MODERATE' or db_sev == 'MEDIUM':
                    sev = 'medium'
                elif db_sev == 'LOW':
                    sev = 'low'
                # Check if a fix version exists
                auto_fixable = False
                for affected in vuln.get('affected', []):
                    for r in affected.get('ranges', []):
                        for event in r.get('events', []):
                            if 'fixed' in event:
                                auto_fixable = True
                                break
                finding = {
                    'tool': 'osv-scanner',
                    'severity': sev,
                    'rule': vuln_id,
                    'message': f'{pkg_name}@{pkg_version}: {summary[:200]}' if summary else f'{pkg_name}@{pkg_version}: {vuln_id}',
                    'file': source_path,
                    'line': 0,
                    'autoFixable': auto_fixable,
                    'category': 'dependency'
                }
                print(json.dumps(finding))
except Exception as e:
    print(json.dumps({'error': str(e)}), file=sys.stderr)
" > "$FINDINGS_FILE"
  fi
fi

rm -f "$RAW_OUTPUT"

count=$(wc -l < "$FINDINGS_FILE" | tr -d ' ')
if [[ "$count" -gt 0 ]]; then
  log_warn "OSV-Scanner: found $count vulnerability(s)"
else
  log_ok "OSV-Scanner: no vulnerabilities found"
fi

echo "$FINDINGS_FILE"
