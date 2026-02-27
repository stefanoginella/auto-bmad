#!/usr/bin/env bash
# Generate a persistent markdown scan report with checkbox items for remediation tracking
# Usage: generate-report.sh --findings-file <path> --scope <scope> [options...]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
source "${SCRIPT_DIR}/lib/tool-registry.sh"

FINDINGS_FILE=""
SCOPE="codebase"
BASE_REF=""
SCANNERS_RUN=""
SKIPPED_SCANNERS=""
SCOPE_SKIPPED_SCANNERS=""
FAILED_SCANNERS=""
SUMMARIES_JSON="[]"
TOTAL=0
HIGH=0
MEDIUM=0
LOW=0
TIMESTAMP=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --findings-file)          FINDINGS_FILE="$2"; shift 2 ;;
    --scope)                  SCOPE="$2"; shift 2 ;;
    --base-ref)               BASE_REF="$2"; shift 2 ;;
    --scanners-run)           SCANNERS_RUN="$2"; shift 2 ;;
    --skipped-scanners)       SKIPPED_SCANNERS="$2"; shift 2 ;;
    --scope-skipped-scanners) SCOPE_SKIPPED_SCANNERS="$2"; shift 2 ;;
    --failed-scanners)        FAILED_SCANNERS="$2"; shift 2 ;;
    --summaries-json)         SUMMARIES_JSON="$2"; shift 2 ;;
    --total)                  TOTAL="$2"; shift 2 ;;
    --high)                   HIGH="$2"; shift 2 ;;
    --medium)                 MEDIUM="$2"; shift 2 ;;
    --low)                    LOW="$2"; shift 2 ;;
    --timestamp)              TIMESTAMP="$2"; shift 2 ;;
    *) shift ;;
  esac
done

if [[ -z "$FINDINGS_FILE" ]]; then
  log_error "generate-report.sh: --findings-file is required"
  exit 1
fi

[[ -z "$TIMESTAMP" ]] && TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create report output directory
REPORT_DIR=".code-guardian/scan-reports"
mkdir -p "$REPORT_DIR"
REPORT_FILE="${REPORT_DIR}/scan-report-${TIMESTAMP}.md"

# Build install commands JSON for skipped/failed tools
install_cmds_json="{}"
for tool_list_var in SKIPPED_SCANNERS FAILED_SCANNERS; do
  tool_list="${!tool_list_var}"
  [[ -z "$tool_list" ]] && continue
  IFS=',' read -ra tools <<< "$tool_list"
  for tool in "${tools[@]}"; do
    [[ -z "$tool" ]] && continue
    cmd=$(get_tool_install_cmd "$tool")
    [[ -z "$cmd" ]] && continue
    # Append to JSON object via python3
    install_cmds_json=$(python3 -c "
import json, sys
d = json.loads(sys.argv[1])
d[sys.argv[2]] = sys.argv[3]
print(json.dumps(d))
" "$install_cmds_json" "$tool" "$cmd")
  done
done

# Generate the markdown report via python3
python3 - "$FINDINGS_FILE" "$SCOPE" "$BASE_REF" "$SCANNERS_RUN" \
  "$SKIPPED_SCANNERS" "$SCOPE_SKIPPED_SCANNERS" "$FAILED_SCANNERS" \
  "$SUMMARIES_JSON" "$TOTAL" "$HIGH" "$MEDIUM" "$LOW" \
  "$TIMESTAMP" "$install_cmds_json" "$REPORT_FILE" << 'PYEOF'
import json, sys, os
from datetime import datetime

findings_file   = sys.argv[1]
scope           = sys.argv[2]
base_ref        = sys.argv[3]
scanners_run    = sys.argv[4]
skipped         = sys.argv[5]
scope_skipped   = sys.argv[6]
failed          = sys.argv[7]
summaries_json  = sys.argv[8]
total           = int(sys.argv[9])
high            = int(sys.argv[10])
medium          = int(sys.argv[11])
low             = int(sys.argv[12])
timestamp       = sys.argv[13]
install_cmds    = json.loads(sys.argv[14])
report_file     = sys.argv[15]

# Parse timestamp for display
try:
    dt = datetime.strptime(timestamp, "%Y%m%d_%H%M%S")
    date_display = dt.strftime("%Y-%m-%d %H:%M:%S")
except ValueError:
    date_display = timestamp

# Parse comma-separated lists
def parse_csv(s):
    return [x.strip() for x in s.split(",") if x.strip()] if s else []

scanners_list       = parse_csv(scanners_run)
skipped_list        = parse_csv(skipped)
scope_skipped_list  = parse_csv(scope_skipped)
failed_list         = parse_csv(failed)

# Parse summaries
try:
    summaries = json.loads(summaries_json)
except (json.JSONDecodeError, ValueError):
    summaries = []

# Read findings
findings = []
if os.path.isfile(findings_file):
    with open(findings_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                findings.append(json.loads(line))
            except json.JSONDecodeError:
                continue

# Build report
lines = []
lines.append("# Code Guardian Scan Report")
lines.append("")
scope_display = scope
if base_ref:
    scope_display += f" (base: {base_ref})"
lines.append(f"**Date**: {date_display}  ")
lines.append(f"**Scope**: {scope_display}  ")
lines.append(f"**Scanners run**: {', '.join(scanners_list) if scanners_list else 'none'}")
lines.append("")

# Summary table
lines.append("## Summary")
lines.append("")
lines.append("| Severity | Count |")
lines.append("|----------|-------|")
lines.append(f"| High     | {high} |")
lines.append(f"| Medium   | {medium} |")
lines.append(f"| Low      | {low} |")
info_count = total - high - medium - low
if info_count > 0:
    lines.append(f"| Info     | {info_count} |")
lines.append(f"| **Total** | **{total}** |")
lines.append("")

# Per-tool breakdown
if summaries:
    lines.append("### Per-Tool Breakdown")
    lines.append("")
    lines.append("| Tool | High | Medium | Low | Info | Total |")
    lines.append("|------|------|--------|-----|------|-------|")
    for s in summaries:
        tool_name = s.get("tool", "unknown")
        sm = s.get("summary", {})
        h = sm.get("high", 0)
        m = sm.get("medium", 0)
        lo = sm.get("low", 0)
        i = sm.get("info", 0)
        t = h + m + lo + i
        lines.append(f"| {tool_name} | {h} | {m} | {lo} | {i} | {t} |")
    lines.append("")

# Findings with checkboxes
lines.append("## Findings")
lines.append("")
if not findings:
    lines.append("No security issues found.")
    lines.append("")
else:
    lines.append("> Check off items as you fix them: change `- [ ]` to `- [x]`")
    lines.append("")

    # Group by severity
    severity_order = ["high", "medium", "low", "info"]
    grouped = {}
    for f in findings:
        sev = f.get("severity", "info").lower()
        grouped.setdefault(sev, []).append(f)

    for sev in severity_order:
        items = grouped.get(sev, [])
        if not items:
            continue
        lines.append(f"### {sev.upper()}")
        lines.append("")
        for f in items:
            tool    = f.get("tool", "?")
            rule    = f.get("rule", "")
            message = f.get("message", "").replace("\n", " ").strip()
            file_   = f.get("file", "")
            line_no = f.get("line", 0)
            fixable = f.get("autoFixable", False)

            location = file_
            if line_no:
                location = f"{file_}:{line_no}"

            suffix = " *(auto-fixable)*" if fixable else ""
            rule_part = f"`{rule}` -- " if rule else ""
            lines.append(f"- [ ] **{sev.upper()}** [{tool}] {rule_part}{message} (`{location}`){suffix}")
        lines.append("")

# Skipped tools
if skipped_list:
    lines.append("## Skipped Tools")
    lines.append("")
    for tool in skipped_list:
        cmd = install_cmds.get(tool, "")
        if cmd:
            lines.append(f"- `{tool}` — install: `{cmd}`")
        else:
            lines.append(f"- `{tool}`")
    lines.append("")

# Failed tools
if failed_list:
    lines.append("## Failed Tools")
    lines.append("")
    for tool in failed_list:
        cmd = install_cmds.get(tool, "")
        if cmd:
            lines.append(f"- `{tool}` — install: `{cmd}`")
        else:
            lines.append(f"- `{tool}`")
    lines.append("")

# Scope-skipped scanners
if scope_skipped_list:
    lines.append("## Skipped (Scoped)")
    lines.append("")
    lines.append("Dependency scanners skipped because no manifest/lockfile was in the changed files:")
    lines.append("")
    for tool in scope_skipped_list:
        lines.append(f"- `{tool}`")
    lines.append("")

# Footer
lines.append("---")
lines.append("*Generated by code-guardian*")
lines.append("")

with open(report_file, "w") as f:
    f.write("\n".join(lines))
PYEOF

echo "$REPORT_FILE"
