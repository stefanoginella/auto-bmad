#!/usr/bin/env bash
# Shared utilities for code-guardian scripts
set -euo pipefail

# Colors (disabled if not a terminal or NO_COLOR set)
if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
  RED='\033[0;31m'
  YELLOW='\033[0;33m'
  GREEN='\033[0;32m'
  BLUE='\033[0;34m'
  CYAN='\033[0;36m'
  BOLD='\033[1m'
  RESET='\033[0m'
else
  RED='' YELLOW='' GREEN='' BLUE='' CYAN='' BOLD='' RESET=''
fi

log_info()  { echo -e "${BLUE}[info]${RESET} $*" >&2; }
log_ok()    { echo -e "${GREEN}[ok]${RESET} $*" >&2; }
log_warn()  { echo -e "${YELLOW}[warn]${RESET} $*" >&2; }
log_error() { echo -e "${RED}[error]${RESET} $*" >&2; }
log_step()  { echo -e "${CYAN}[step]${RESET} ${BOLD}$*${RESET}" >&2; }

# Check if a command exists
cmd_exists() { command -v "$1" &>/dev/null; }

# Check if Docker is available and running
docker_available() {
  cmd_exists docker && docker info &>/dev/null
}

# Check if docker compose is available (v2 plugin or standalone)
compose_available() {
  docker compose version &>/dev/null 2>&1 || docker-compose version &>/dev/null 2>&1
}

# Get the compose command ("docker compose" or "docker-compose")
get_compose_cmd() {
  if docker compose version &>/dev/null 2>&1; then
    echo "docker compose"
  elif docker-compose version &>/dev/null 2>&1; then
    echo "docker-compose"
  fi
}

# ── Project container detection ───────────────────────────────────────
# Cache file for container tool mappings (tool=service pairs, one per line)
_CG_CONTAINER_CACHE="${_CG_CONTAINER_CACHE:-}"

# Detect running project containers and probe them for tools.
# Writes a cache file mapping tool_binary → container_service.
# Usage: detect_container_tools [tool_binary ...]
# Call once with the list of binaries to check; results are cached.
detect_container_tools() {
  if [[ -n "$_CG_CONTAINER_CACHE" ]] && [[ -f "$_CG_CONTAINER_CACHE" ]]; then
    return 0  # already detected
  fi

  _CG_CONTAINER_CACHE=$(mktemp /tmp/cg-container-map-XXXXXX)
  export _CG_CONTAINER_CACHE

  if ! compose_available; then
    return 0  # no compose, empty cache
  fi

  # Check for compose file
  local compose_file=""
  for f in docker-compose.yml docker-compose.yaml compose.yml compose.yaml; do
    if [[ -f "$f" ]]; then
      compose_file="$f"
      break
    fi
  done
  [[ -z "$compose_file" ]] && return 0

  local compose_cmd
  compose_cmd=$(get_compose_cmd)

  # Get running services
  local services
  services=$($compose_cmd ps --services --filter "status=running" 2>/dev/null) || return 0
  [[ -z "$services" ]] && return 0

  local binaries_to_check=("$@")

  # For each running service, check which tool binaries are available
  while IFS= read -r service; do
    [[ -z "$service" ]] && continue
    for binary in "${binaries_to_check[@]}"; do
      # Use 'which' inside the container to check if the binary exists
      if $compose_cmd exec -T "$service" which "$binary" &>/dev/null 2>&1; then
        echo "${binary}=${service}" >> "$_CG_CONTAINER_CACHE"
        log_info "Found '$binary' in running container service: $service"
      fi
    done
  done <<< "$services"
}

# Check if a tool binary is available in a running project container.
# Returns the service name on stdout if found, empty string if not.
# Requires detect_container_tools to have been called first.
get_container_service_for_tool() {
  local binary="$1"
  if [[ -n "$_CG_CONTAINER_CACHE" ]] && [[ -f "$_CG_CONTAINER_CACHE" ]]; then
    grep "^${binary}=" "$_CG_CONTAINER_CACHE" 2>/dev/null | head -1 | cut -d'=' -f2
  fi
}

# Run a tool in the best available environment.
# Priority: project container > standalone Docker image > local binary
# Usage: run_tool <local_cmd> <docker_image> <docker_args...>
# Returns 0 if ran, 1 if tool not available at all
run_tool() {
  local local_cmd="$1"
  local docker_image="$2"
  shift 2
  local tool_args=("$@")

  # 1. Check project containers first
  local container_service
  container_service=$(get_container_service_for_tool "$local_cmd")
  if [[ -n "$container_service" ]]; then
    local compose_cmd
    compose_cmd=$(get_compose_cmd)
    log_info "Running in project container ($container_service): $local_cmd"
    $compose_cmd exec -T "$container_service" "$local_cmd" "${tool_args[@]}"
    return $?
  fi

  # 2. Standalone Docker image
  if docker_available && [[ -n "$docker_image" ]]; then
    log_info "Running via Docker image: $docker_image"
    docker run --rm -v "$(pwd):/workspace" -w /workspace "$docker_image" "${tool_args[@]}"
    return $?
  fi

  # 3. Local binary
  if cmd_exists "$local_cmd"; then
    log_info "Running locally: $local_cmd"
    "$local_cmd" "${tool_args[@]}"
    return $?
  fi

  return 1
}

# Output a JSON finding to stdout
# Usage: emit_finding <tool> <severity> <rule> <message> <file> <line> <autofixable> <category>
emit_finding() {
  local tool="$1" severity="$2" rule="$3" message="$4" file="$5" line="$6" autofixable="$7" category="$8"
  # Escape JSON strings
  message="${message//\\/\\\\}"
  message="${message//\"/\\\"}"
  message="${message//$'\n'/\\n}"
  message="${message//$'\r'/}"
  rule="${rule//\\/\\\\}"
  rule="${rule//\"/\\\"}"
  printf '{"tool":"%s","severity":"%s","rule":"%s","message":"%s","file":"%s","line":%s,"autoFixable":%s,"category":"%s"}\n' \
    "$tool" "$severity" "$rule" "$message" "$file" "${line:-0}" "$autofixable" "$category"
}

# Get files in the requested scope
# Usage: get_scoped_files <scope> [base_ref]
# Scope: codebase, uncommitted, unpushed
get_scoped_files() {
  local scope="${1:-codebase}"
  local base_ref="${2:-}"

  case "$scope" in
    codebase)
      git ls-files 2>/dev/null || find . -type f -not -path './.git/*'
      ;;
    uncommitted|changes|all-changes)
      # All local uncommitted work: staged + unstaged + untracked
      {
        git diff --cached --name-only --diff-filter=ACMR 2>/dev/null
        git diff --name-only --diff-filter=ACMR 2>/dev/null
        git ls-files --others --exclude-standard 2>/dev/null
      } | sort -u
      ;;
    unpushed)
      if [[ -n "$base_ref" ]]; then
        git diff "${base_ref}...HEAD" --name-only --diff-filter=ACMR 2>/dev/null
      else
        # Try origin/main, then origin/master
        local default_branch
        default_branch=$(git remote show origin 2>/dev/null | grep 'HEAD branch' | awk '{print $NF}' || echo "main")
        git diff "origin/${default_branch}...HEAD" --name-only --diff-filter=ACMR 2>/dev/null
      fi
      ;;
    *)
      log_error "Unknown scope: $scope"
      return 1
      ;;
  esac
}

# Write scope files to a temp file and return its path
write_scope_file() {
  local scope="${1:-codebase}"
  local base_ref="${2:-}"
  local tmpfile
  tmpfile=$(mktemp /tmp/code-guardian-scope-XXXXXX)
  get_scoped_files "$scope" "$base_ref" > "$tmpfile"
  echo "$tmpfile"
}

# Filter file list by extensions
# Usage: filter_by_ext <file_list_file> <ext1> [ext2 ...]
filter_by_ext() {
  local file_list="$1"
  shift
  local pattern
  pattern=$(printf '|%s' "$@")
  pattern="${pattern:1}" # Remove leading |
  grep -iE "\.(${pattern})$" "$file_list" 2>/dev/null || true
}

# Create a JSON summary from findings file
# Usage: create_summary <findings_file> <tool_name>
create_summary() {
  local findings_file="$1"
  local tool_name="$2"
  local high=0 medium=0 low=0 info=0

  if [[ -f "$findings_file" ]] && [[ -s "$findings_file" ]]; then
    high=$(grep -c '"severity":"high"' "$findings_file" 2>/dev/null || echo 0)
    medium=$(grep -c '"severity":"medium"' "$findings_file" 2>/dev/null || echo 0)
    low=$(grep -c '"severity":"low"' "$findings_file" 2>/dev/null || echo 0)
    info=$(grep -c '"severity":"info"' "$findings_file" 2>/dev/null || echo 0)
  fi

  printf '{"tool":"%s","summary":{"high":%d,"medium":%d,"low":%d,"info":%d}}\n' \
    "$tool_name" "$high" "$medium" "$low" "$info"
}
