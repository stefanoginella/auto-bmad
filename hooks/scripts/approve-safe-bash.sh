#!/bin/bash
# PreToolUse hook: auto-approve bash commands that match known-safe patterns.
#
# Reduces false-positive sandbox prompts for common safe commands (brace
# expansion, quoted flag characters, etc.) during autonomous pipeline execution.
#
# How it works:
#   - Extract the command from stdin JSON
#   - Check against exact matches (bare commands) and prefix matches (commands + args)
#   - If it matches → output permissionDecision: "allow"
#   - Otherwise     → exit 0 with no output (fall through to normal permissions)
#
# Customization:
#   Add project-local overrides in .claude/auto-bmad-safe-prefixes.txt
#   Lines starting with "= " are exact matches, all others are prefix matches.
#   Empty lines and lines starting with "#" are ignored.
#
# Note: this is a simple heuristic and not a full sandbox bypass.

set -euo pipefail

input=$(cat)
command=$(printf '%s' "$input" | jq -r '.tool_input.command // ""')

# Exit early if we couldn't extract a command
[ -z "$command" ] && exit 0

# Bare commands (exact match — safe without any arguments)
safe_exact=(
  "date"
  "docker compose build"
  "docker compose config"
  "docker compose down"
  "docker compose images"
  "docker compose logs"
  "docker compose ls"
  "docker compose ps"
  "docker compose pull"
  "docker compose top"
  "docker compose up"
  "docker compose version"
  "docker images"
  "docker ps"
  "docker version"
  "git diff"
  "git fetch"
  "git log"
  "git status"
  "ls"
  "pwd"
  "tree"
  "uname"
)

# Commands with arguments (prefix match — trailing space prevents partial word matches)
safe_prefixes=(
  "awk "
  "basename "
  "cat "
  "chmod "
  "cp "
  "cut "
  "date "
  "diff "
  "dirname "
  "docker compose build "
  "docker compose config "
  "docker compose exec "
  "docker compose logs "
  "docker compose ps "
  "docker compose pull "
  "docker compose top "
  "docker compose up "
  "docker inspect "
  "docker logs "
  "docker ps "
  "du "
  "echo "
  "file "
  "find "
  "git -C "
  "git add "
  "git commit "
  "git diff "
  "git diff-tree "
  "git fetch "
  "git log "
  "git rev-parse "
  "git show "
  "git status "
  "git tag "
  "grep "
  "head "
  "jq "
  "ls "
  "mkdir "
  "mv "
  "realpath "
  "sed "
  "semgrep "
  "sort "
  "stat "
  "tail "
  "timeout "
  "touch "
  "tr "
  "tree "
  "uname "
  "uniq "
  "wc "
  "which "
)

# Load project-local overrides if the file exists
custom_file="${CLAUDE_PROJECT_DIR:-.}/.claude/auto-bmad-safe-prefixes.txt"
if [ -f "$custom_file" ]; then
  while IFS= read -r line; do
    # Skip empty lines and comments
    [[ -z "$line" || "$line" == \#* ]] && continue
    # Lines starting with "= " are exact matches
    if [[ "$line" == "= "* ]]; then
      safe_exact+=("${line#= }")
    else
      safe_prefixes+=("$line")
    fi
  done < "$custom_file"
fi

match=false

# Check exact matches first
for exact in "${safe_exact[@]}"; do
  if [ "$command" = "$exact" ]; then
    match=true
    break
  fi
done

# Then check prefix matches
if [ "$match" = false ]; then
  for prefix in "${safe_prefixes[@]}"; do
    case "$command" in
      "$prefix"*) match=true; break ;;
    esac
  done
fi

if [ "$match" = true ]; then
  cat <<'EOF'
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "permissionDecisionReason": "Command matches plugin safe-prefix list"
  }
}
EOF
  exit 0
fi

# No match — fall through to normal permission handling
exit 0
