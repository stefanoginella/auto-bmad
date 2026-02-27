#!/usr/bin/env bash
set -euo pipefail

# Syncs version from plugin.json → package.json (no file copying).
# Usage:
#   bash scripts/sync-versions.sh              # all plugins
#   bash scripts/sync-versions.sh auto-bmad    # single plugin

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLUGINS_DIR="${REPO_ROOT}/plugins"
PACKAGES_DIR="${REPO_ROOT}/packages"

sync_version() {
  local name="$1"
  local plugin_json="${PLUGINS_DIR}/${name}/.claude-plugin/plugin.json"
  local package_json="${PACKAGES_DIR}/${name}/package.json"

  if [ ! -f "${plugin_json}" ]; then
    echo "Error: ${plugin_json} not found" >&2
    return 1
  fi
  if [ ! -f "${package_json}" ]; then
    echo "Error: ${package_json} not found" >&2
    return 1
  fi

  local version
  version=$(grep '"version"' "${plugin_json}" | sed 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')

  # Update version in package.json using sed (in-place)
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/\"version\":[[:space:]]*\"[^\"]*\"/\"version\": \"${version}\"/" "${package_json}"
  else
    sed -i "s/\"version\":[[:space:]]*\"[^\"]*\"/\"version\": \"${version}\"/" "${package_json}"
  fi

  echo "${name}: ${version}"
}

# --- Main ---
if [ $# -gt 0 ]; then
  sync_version "$1"
else
  for pkg_dir in "${PACKAGES_DIR}"/*/; do
    name=$(basename "${pkg_dir}")
    if [ -d "${PLUGINS_DIR}/${name}" ]; then
      sync_version "${name}"
    fi
  done
fi
