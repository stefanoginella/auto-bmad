#!/bin/bash
# SessionStart hook: check for required BMAD plugin dependencies.
#
# Outputs a systemMessage reminding Claude about the required plugins
# so it can warn the user if pipelines are invoked without them.

set -euo pipefail

cat <<'EOF'
{
  "systemMessage": "The auto-bmad plugin is active. Its pipelines (/auto-bmad:plan, /auto-bmad:story, /auto-bmad:epic-start, /auto-bmad:epic-end) orchestrate the BMAD software development lifecycle.\n\nRequired BMAD modules (key commands to verify):\n- BMM (core BMAD): e.g. /bmad-bmm-create-prd, /bmad-bmm-dev-story, /bmad-bmm-code-review\n- TEA (Test Engineering Architect): e.g. /bmad-tea-testarch-atdd, /bmad-tea-testarch-trace\n\nOptional BMAD module:\n- CIS (Creative Intelligence Suite): e.g. /bmad-cis-design-thinking, /bmad-cis-innovation-strategy\n\nRequired Claude Code plugins: frontend-design (/frontend-design:frontend-design), commit-commands (/commit-commands:commit), claude-md-management (/claude-md-management:claude-md-improver).\n\nOptional but recommended: context7 MCP server (live documentation lookups during architecture and story development), semgrep CLI tool (security scanning in story pipeline — skipped if absent).\n\nThe pipelines expect BMAD config files in the project: _bmad/bmm/config.yaml and _bmad/tea/config.yaml. If any required plugin, module, or command is missing when a pipeline step tries to invoke it, the step will fail — warn the user early if you detect missing dependencies."
}
EOF
exit 0
