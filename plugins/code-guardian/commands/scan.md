---
name: code-guardian-scan
description: Run security scan on the codebase using detected stack-appropriate tools
argument-hint: "[--scope codebase|uncommitted|unpushed] [--tools tool1,tool2,...] [--refresh] [--autofix]"
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
  - Glob
  - Grep
  - AskUserQuestion
---

# Security Scan Command

Run a comprehensive security scan using open-source CLI tools appropriate for the project's detected stack. Scans with whatever tools are available — missing tools are skipped and reported at the end.

## Configuration

The scan respects project-level configuration from `.claude/code-guardian.config.json`. CLI arguments always override config values. See `/code-guardian:code-guardian-setup` for details on the config file.

## Execution Flow

### Step 1: Parse Arguments

Parse from `$ARGUMENTS`:
- `--scope` (codebase, uncommitted, unpushed) — default: codebase (or config `scope`)
- `--tools` — comma-separated list of specific tools to run (e.g. `--tools semgrep,gitleaks`). Only these tools will run; all others are skipped. If omitted, uses config `tools` if set, otherwise all available tools run.
- `--refresh` — force re-detection, ignore cache
- `--autofix` — run tools with auto-fix flags and AI-fix remaining issues (or config `autofix`)

Config values (`tools`, `disabled`, `scope`, `autofix`) are loaded automatically by scan.sh. CLI args override them.

If scope not provided (neither CLI nor config), ask with AskUserQuestion:
- "What scope to scan?" — codebase (all tracked files), uncommitted (all local uncommitted work), unpushed (commits not yet pushed)
- If "unpushed", also ask: "Compare against which base?" — default branch, remote tracking branch, or custom ref

### Step 2: Detect Stack & Tools

Unless `--refresh` was passed, try cached results first:

```bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/cache-state.sh --read --max-age 86400
```

- **Exit 0** (fresh): Use cached `stack` and `tools`. Tell the user "Using cached detection results" and skip to Step 3.
- **Exit 1 or 2** (missing/stale): Run fresh detection:

```bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/detect-stack.sh .
echo '<stack_json>' | bash ${CLAUDE_PLUGIN_ROOT}/scripts/check-tools.sh
```

Display a brief summary: languages detected, tools available, tools skipped.

Cache the fresh results:
```bash
echo '<stack_json>' > /tmp/cg-stack.json
echo '<tools_json>' > /tmp/cg-tools.json
bash ${CLAUDE_PLUGIN_ROOT}/scripts/cache-state.sh --write \
  --stack-file /tmp/cg-stack.json --tools-file /tmp/cg-tools.json
```

### Step 3: Run Security Scan

```bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/scan.sh \
  --stack-json /tmp/cg-stack.json \
  --tools-json /tmp/cg-tools.json \
  --scope <scope> \
  [--base-ref <ref>] \
  [--autofix] \
  [--tools tool1,tool2,...]
```

Pass `--autofix` only if the user passed `--autofix`.
Pass `--tools` if the user passed `--tools`.

### Step 4: Process Results

Read the findings file from the scan output (each line is a JSON finding with: tool, severity, rule, message, file, line, autoFixable, category).

**If no findings**: Report success. Suggest CI scanning if none detected.

**If `--autofix` was used**:
1. Report what tools auto-fixed (semgrep --autofix, eslint --fix, npm audit fix, etc.)
2. For remaining findings tools couldn't auto-fix, use the **security-fixer** agent to apply code-level remediation. The agent reads the findings JSONL, understands each vulnerability type, and applies minimal targeted fixes.
3. Re-run scan to verify fixes
4. Report: auto-fixed, AI-fixed, remaining (with explanations)

**Otherwise (default)**:
1. Present findings grouped by severity (high first), then by category
2. Show a summary table:
   ```
   | # | Severity | Tool | Rule | File:Line | Auto-fixable |
   ```
3. Ask what to do:
   - "Fix all high severity"
   - "Fix all auto-fixable"
   - "Fix specific findings (by number)"
   - "Skip and just report"
4. For selected findings: run scanner with --autofix if auto-fixable, otherwise use the **security-fixer** agent for code-level fixes

### Step 5: Final Report

Always end with these sections:

1. **Findings summary** — counts by severity
2. **What was fixed** (if any fixes were applied)
3. **Remaining issues** (if any, with explanations)
4. **Skipped tools** — list any tools that were needed but not installed, with install commands:
   > The following tools were not available and their checks were skipped:
   > - `trivy` — install: `brew install trivy`
   > - `checkov` — install: `pip3 install checkov`
   >
   > Run `/code-guardian:code-guardian-setup` to see all tool status.
5. **CI recommendation** — if no CI security scanning detected, suggest `/code-guardian:code-guardian-ci`
6. **Scan report** — tell the user a detailed report was saved to disk (the path is in the `reportFile` field of the scan output JSON). Findings are listed as `- [ ]` checkbox items they can mark `[x]` as they remediate each issue. Example: "A detailed report has been saved to `<reportFile>`. Each finding is a checkbox you can mark off as you fix it."

## Scope & Dependency Scanners

Dependency audit tools (npm-audit, pip-audit, cargo-audit, bundler-audit, govulncheck, osv-scanner) scan lockfiles/manifests that are project-wide — the concept of "only check uncommitted files" doesn't apply to them.

When `--scope` is `uncommitted` or `unpushed`, dependency scanners are **automatically skipped** unless their manifest or lockfile (e.g. `package-lock.json`, `Cargo.lock`, `go.sum`) appears in the changed files. This prevents noisy, irrelevant dependency findings when scanning just your recent work.

When `--scope` is `codebase` (default), all scanners run as normal.

Skipped dependency scanners are reported in the final summary under "Skipped (no manifest in scope)".

## Important Notes

- Never modify files outside the project directory
- For secret findings, NEVER display the actual secret value in output
- When fixing code, explain what vulnerability you're addressing and why the fix works
- Prefer minimal, targeted fixes over large refactors
- After auto-fixes, verify the code still compiles/passes basic checks
