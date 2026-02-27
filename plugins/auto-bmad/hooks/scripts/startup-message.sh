#!/bin/bash
# SessionStart hook: plugin startup message.
#
# Outputs a systemMessage with plugin status and a link to the README.

set -euo pipefail

cat <<'EOF'
{
  "systemMessage": "The `auto-bmad` plugin is active. Check https://github.com/stefanoginella/claude-code-plugins/blob/main/plugins/auto-bmad/README.md for requirements, details and usage instructions."
}
EOF
exit 0
