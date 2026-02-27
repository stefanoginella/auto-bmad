#!/bin/bash
# SessionStart hook: check for required BMAD plugin dependencies.
#
# Outputs a systemMessage reminding Claude about the required plugins
# so it can warn the user if pipelines are invoked without them.

set -euo pipefail

cat <<'EOF'
{
  "systemMessage": "The `auto-bmad` plugin is active. Its pipelines (/auto-bmad:plan, /auto-bmad:story, /auto-bmad:epic-start, /auto-bmad:epic-end) orchestrate the BMAD software development lifecycle.\n\nCheck https://github.com/stefanoginella/claude-code-plugins/blob/main/plugins/auto-bmad/README.md for requirements, details and usage instructions."
}
EOF
exit 0
