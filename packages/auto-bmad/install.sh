#!/usr/bin/env bash
set -euo pipefail

PLUGIN_NAME="auto-bmad"
MARKETPLACE="stefanoginella-plugins"
MARKETPLACE_REPO="stefanoginella/claude-code-plugins"

# --- Color support ---
if [ "${NO_COLOR:-}" = "" ] && [ -t 1 ]; then
  GREEN='\033[0;32m'
  RED='\033[0;31m'
  YELLOW='\033[1;33m'
  BOLD='\033[1m'
  RESET='\033[0m'
else
  GREEN='' RED='' YELLOW='' BOLD='' RESET=''
fi

# --- Check claude CLI is available ---
if ! command -v claude &>/dev/null; then
  echo -e "${RED}Error: claude CLI not found.${RESET}" >&2
  echo "Install Claude Code first: https://docs.anthropic.com/en/docs/claude-code" >&2
  exit 1
fi

# --- Uninstall ---
if [ "${1:-}" = "--uninstall" ]; then
  echo "Uninstalling ${PLUGIN_NAME}..."
  claude plugin uninstall "${PLUGIN_NAME}@${MARKETPLACE}" 2>/dev/null && \
    echo -e "${GREEN}${PLUGIN_NAME} uninstalled.${RESET}" || \
    echo "${PLUGIN_NAME} is not installed."
  exit 0
fi

# --- Choose scope ---
echo ""
echo -e "${BOLD}Install scope:${RESET}"
echo "  1) project — shared with team via .claude/settings.json (default)"
echo "  2) user    — available across all your projects"
echo "  3) local   — this project only, personal, gitignored"
echo ""
printf "Choose scope [1]: "
read -r scope_choice

case "${scope_choice}" in
  2) SCOPE="user" ;;
  3) SCOPE="local" ;;
  *) SCOPE="project" ;;
esac

# --- Install ---
echo ""
echo -e "${BOLD}Installing ${PLUGIN_NAME} (scope: ${SCOPE})...${RESET}"
echo ""

# Add marketplace (idempotent)
echo "Adding marketplace ${MARKETPLACE_REPO}..."
claude plugin marketplace add "${MARKETPLACE_REPO}" 2>/dev/null || true

# Install plugin
echo "Installing plugin..."
if claude plugin install "${PLUGIN_NAME}@${MARKETPLACE}" --scope "${SCOPE}"; then
  echo ""
  echo -e "${GREEN}${BOLD}${PLUGIN_NAME} installed successfully.${RESET}"
  echo ""
  echo "Start Claude Code in this project directory to use the plugin."
  echo -e "Run ${YELLOW}npx @stefanoginella/${PLUGIN_NAME} --uninstall${RESET} to remove."
  echo ""
else
  echo ""
  echo -e "${RED}Installation failed.${RESET}" >&2
  echo "Try installing manually inside Claude Code:" >&2
  echo "  /plugin marketplace add ${MARKETPLACE_REPO}" >&2
  echo "  /plugin install ${PLUGIN_NAME}@${MARKETPLACE}" >&2
  exit 1
fi
