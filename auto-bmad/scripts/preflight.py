#!/usr/bin/env python3
"""Phase 0 preflight for auto-bmad — ONE call replacing a dozen hand-rolled shell probes.

The orchestrator's Phase 0 (SKILL.md Step 0/1) needs a batch of environment facts
before any commit: the BMAD central TOML config (output folder + BMM artifact
dirs), the Python/uv toolchain build-auto needs, nested-subagent capability of the
host, git repo / clean tree / branch / base branch / git mode (``remote`` vs
``local``), the ``AGENTS.md`` context block, CI workflow presence, required-skill
availability, and (first-run only) test-framework config detection. Each was a
separate shell probe — and bare globs are fatal under zsh/fish (``nomatch`` ⇒
exit 1; see CLAUDE.md → "Shell globs") — so this script folds them all into one
deterministic call printing ONE JSON object on stdout. All filesystem walking is
``os.walk``/``pathlib`` (no shell, no globs); the only TOML reader is stdlib
``tomllib`` (Python >= 3.11 — itself a probed prerequisite, P2).

Two modes:

* ``--central-config-only`` (SKILL Step 0 / On-activation gate / module-setup):
  probes ONLY ``python`` (P2) and ``central_config`` (P1 + the ``modules.bmm``
  hard-stop) and returns the SAME JSON shape with every other block ``null``
  (``hard_stop_reasons`` limited to those). No host/tier, no git, no skills. This
  is how the orchestrator learns ``core.output_folder`` (⇒ the runtime config
  path) and the BMM artifact dirs BEFORE the runtime config — and therefore
  host/tier — is known. Nothing else in auto-bmad reads TOML.
* the full call (Phase 0 step 3) — every block below.

Encoded rules (the normative definitions live in the reference docs / spec §1):

* **python** (P2): ``sys.version_info >= (3, 11)`` AND ``import tomllib`` works;
  else hard-stop (the interpreter running THIS script must be able to read TOML).
* **central_config** (P1): mirrors upstream ``config_utils.load_central_config`` —
  ``_bmad/config.toml`` (required) → ``config.user.toml`` → ``custom/config.toml``
  → ``custom/config.user.toml``, highest-last; tables deep-merge; arrays whose
  items all carry ``code``/``id`` merge by that key (replace), other arrays append.
  The literal ``{project-root}`` token is substituted with the absolute project
  root in EVERY string value; the three path fields are made absolute (a relative
  value is joined onto the project root). Missing ``_bmad/config.toml`` ⇒
  ``present: false`` + hard-stop (not a BMAD project). Unparseable layer ⇒
  ``error`` + hard-stop. ``modules.bmm`` absent (core-only install) ⇒
  ``implementation_artifacts``/``planning_artifacts`` ``null`` + hard-stop.
  Missing ``core.output_folder`` ⇒ hard-stop (nothing downstream can run without it).
* **legacy_configs** (P11, warn only): ``_bmad/bmm/config.yaml`` and
  ``_bmad/core/config.yaml`` — the delegated BMAD skills still load them; one
  warning line per missing file.
* **tea_config** (P12, only with ``--tea-enabled``, warn only): ``_bmad/tea/config.yaml``.
* **uv** (P3): ``uv`` on PATH (``shutil.which``) + ``uv --version``; absent ⇒ hard-stop
  (bmad-build-auto renders through ``uv run`` and HALTs without it).
* **python311** (P4): ``uv python find '>=3.11' --no-python-downloads`` — exit 0 ⇒
  ``ok`` (``found`` = the interpreter path); non-zero (uv exits 2 when nothing
  matches) ⇒ absent ⇒ ``warn`` (uv downloads one on first use) UNLESS
  ``UV_PYTHON_DOWNLOADS`` ∈ {never, 0, false, off} ⇒ ``hard_stop``. Skipped
  (``warn``) when uv is not on PATH — P3 already stops.
* **agents_md** (P10, warn only): ``<root>/AGENTS.md`` contains both
  ``<!-- bmad:context -->`` and ``<!-- /bmad:context -->``.
* **nesting** (P6): the chain orchestrator (depth 0) → generic delegate subagent
  (depth 1) → build-auto's own subagents (depth 2) must work in the ``subagents``
  tier. Classification (spec §1.4):
  - ``--cli-phases`` containing BOTH ``build`` and ``followup_review`` ⇒ ``ok``
    regardless of host (build-auto only ever runs inside the external CLI).
  - tier ``inline`` ⇒ ``ok`` (build-auto's subagents are depth 1).
  - claude-code: env ``CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`` — unset, non-integer
    or ``< 1`` (ignored by Claude ⇒ default 3), or ``>= 2`` ⇒ ``ok``; parses as an
    integer equal to ``1`` ⇒ ``hard_stop``.
  - codex: ``$CODEX_HOME/config.toml`` (default ``~/.codex/config.toml``) then
    ``<root>/.codex/config.toml`` (project overrides user key-by-key) —
    ``features.multi_agent_v2 == true`` OR ``agents.max_depth >= 2`` ⇒ ``ok``;
    otherwise ``hard_stop``; an unparseable file ⇒ ``warn``.
  - opencode: ``~/.config/opencode/opencode.json``, ``$OPENCODE_CONFIG`` (if set),
    ``<root>/opencode.json``, ``<root>/.opencode/opencode.json`` (later wins; a
    ``.jsonc`` sibling is read right after each ``.json``; ``//`` line comments
    outside strings are stripped before ``json.loads``) — the highest layer that
    sets ``subagent_depth`` must be ``>= 2`` else ``hard_stop``; depth ok but no
    ``agent.general.permission.task == "allow"`` ⇒ ``warn``; unparseable file ⇒ ``warn``.
  - other ⇒ ``warn`` (unknown host — nested subagents unverified).
  ``fix`` carries the verbatim per-host remedy (``null`` when nothing to fix).
* **cross_model** (P8, only with ``--cross-model-tool``): the tool's binary must be
  on PATH (``codex``/``claude``/``opencode``), else hard-stop.
* **git** (P7, git-and-pr.md → "Mode detection (Phase 0)"):
  - ``is_repo``: ``git rev-parse --is-inside-work-tree`` succeeds.
  - ``tree_clean``: ``git status --porcelain`` output is empty;
    ``dirty_files_count`` = its non-empty line count. If the status probe FAILS
    (rc != 0 — e.g. timeout), both are ``null`` and ``status_error`` carries a
    stderr snippet — the gate fails CLOSED (hard stop), never reads as clean.
  - ``base_branch``: remote HEAD via ``git symbolic-ref refs/remotes/origin/HEAD``
    (``refs/remotes/origin/`` prefix stripped), else the current branch.
  - ``mode``: ``remote`` iff ``gh --version`` works AND ``gh auth status`` exits 0
    AND ``git remote -v`` shows a github.com remote — else ``local``.
  - hard-stops: not a repo; tree state unknown; dirty tree unless
    ``--expected-branch`` equals the current branch (the resume case);
    detached/unknown HEAD (even on a clean tree).
* **ci**: any ``*.yml``/``*.yaml`` under ``.github/workflows`` or a root ``.gitlab-ci.yml``.
* **skills** (P5): a required skill is present iff a DIRECTORY of that name exists
  under ANY ``--skills-dirs`` entry; each miss is a hard-stop
  ``required skill missing: <name>`` (+ an install hint: ``bmad-testarch-*`` ⇒
  ``--modules tea``, the 6.11 additions ``bmad-build-auto``/``bmad-sprint-planning``
  ⇒ ``(BMAD < 6.11? run npx bmad-method install --action update)``).
  ``sprint_plan_script`` = the first ``<skills-dir>/bmad-sprint-planning/scripts/sprint_plan.py``
  in ``--skills-dirs`` order (only probed when ``--skills-dirs`` is given); ``null``
  ⇒ hard-stop (suppressed when ``bmad-sprint-planning`` itself is already reported missing).
* **framework** (only with ``--detect-framework-ci``; first-run flow step 2):
  root-level ``playwright.config.*``, ``cypress.config.*``, ``jest.config.*``,
  ``vitest.config.*`` (final suffix .js/.cjs/.mjs/.ts/.cts/.mts/.json), ``pytest.ini``,
  ``pyproject.toml`` containing ``[tool.pytest``, ``setup.cfg`` containing ``[tool:pytest]``;
  ``ci_present`` mirrors ``ci.workflows_present``. ``null`` without the flag.
* **warnings**: the P10–P12 (+ P4/nesting warn) lines, in probe order.
* **hard_stop** / **hard_stop_reasons**: the union of every hard-stop above.

Output (every key always present; blocks not probed in this mode are ``null``)::

    {"python": {"version", "ok"},
     "central_config": {"present", "layers_read", "output_folder", "implementation_artifacts",
                        "planning_artifacts", "project_name", "error"},
     "legacy_configs": {"bmm_present", "core_present"},
     "tea_config": {"present"} | null,
     "uv": {"on_path", "path", "version"},
     "python311": {"status": "ok"|"warn"|"hard_stop", "found", "detail"},
     "agents_md": {"present", "has_context_block"},
     "nesting": {"host", "tier", "status": "ok"|"warn"|"hard_stop", "detail", "fix", "sources"},
     "cross_model": {"tool", "binary", "binary_on_path"},
     "git": {"is_repo", "current_branch", "tree_clean", "dirty_files_count", "status_error",
             "base_branch", "mode", "gh_installed", "gh_authed", "github_remote"},
     "ci": {"workflows_present"},
     "skills": {"checked", "missing", "sprint_plan_script"},
     "framework": {"configs", "ci_present"} | null,
     "warnings": [...], "hard_stop": bool, "hard_stop_reasons": [...]}

Usage::

    preflight.py --project-root DIR --host claude-code|codex|opencode|other --tier subagents|inline
                 [--expected-branch NAME] [--require-skills CSV --skills-dirs CSV]
                 [--detect-framework-ci] [--tea-enabled] [--cross-model-tool codex|claude|opencode]
                 [--cli-phases CSV]
    preflight.py --project-root DIR --central-config-only
    preflight.py --self-test

Exit codes: 0 = ran, no hard stop; 1 = ran, hard_stop true; 2 = usage error
(``{"status": "error", "message": ...}`` on stdout).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

try:  # P2 — guarded so an old interpreter yields a hard-stop reason, not a traceback.
    import tomllib
except ImportError:  # pragma: no cover — exercised only under python < 3.11
    tomllib = None  # type: ignore[assignment]

_PROBE_TIMEOUT = 20  # seconds — keep short so a wedged probe can't hang preflight

# A runner takes an argv and returns (returncode, stdout, stderr).
Runner = Callable[[Sequence[str]], "tuple[int, str, str]"]
# A which takes a binary name and returns its path or None (shutil.which shape).
Which = Callable[[str], "str | None"]

_WALK_EXCLUDES = {"node_modules", ".venv", ".git"}

_HOSTS = ("claude-code", "codex", "opencode", "other")
_TIERS = ("subagents", "inline")
_CROSS_MODEL_TOOLS = ("codex", "claude", "opencode")
# cross_model tool -> binary name on PATH.
_TOOL_BINARY = {"codex": "codex", "claude": "claude", "opencode": "opencode"}

_CENTRAL_LAYERS = (
    ("config.toml",),
    ("config.user.toml",),
    ("custom", "config.toml"),
    ("custom", "config.user.toml"),
)
_PROJECT_ROOT_TOKEN = "{project-root}"
_KEYED_MERGE_FIELDS = ("code", "id")

_AGENTS_MD_OPEN = "<!-- bmad:context -->"
_AGENTS_MD_CLOSE = "<!-- /bmad:context -->"

_UV_DOWNLOADS_OFF = {"never", "0", "false", "off"}
_CLAUDE_DEPTH_ENV = "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH"
_CLI_PHASES_EXEMPT = {"build", "followup_review"}
# The 6.11 additions whose absence most likely means an older BMAD.
_BMAD_611_SKILLS = {"bmad-build-auto", "bmad-sprint-planning"}

_FRAMEWORK_PREFIXES = (
    "playwright.config.",
    "cypress.config.",
    "jest.config.",
    "vitest.config.",
)

# Final extensions real framework configs use (jest also takes .json). Filtering on
# the FINAL suffix keeps multi-dot configs (jest.config.e2e.js) while rejecting
# stale copies (jest.config.js.bak, playwright.config.ts.orig).
_FRAMEWORK_CONFIG_SUFFIXES = {".js", ".cjs", ".mjs", ".ts", ".cts", ".mts", ".json"}

# --- verbatim texts (spec §1.1 / §1.4) ---

_MSG_PYTHON_OLD = (
    "python3 is <3.11 (auto-bmad reads _bmad/config.toml with tomllib) — install Python 3.11+"
    " (uv can: `uv python install 3.11`) and make it the `python3` on PATH"
)
_MSG_NOT_BMAD = (
    "not a BMAD project (no _bmad/config.toml) — run `npx bmad-method install` (BMAD >= 6.11.0) first"
)
_MSG_UV_MISSING = (
    "uv not on PATH — bmad-build-auto renders through `uv run`; install uv"
    " (https://docs.astral.sh/uv/) and re-run"
)
_MSG_PY311_WARN = "no Python >=3.11 found by uv — uv will download one on first use"
_MSG_AGENTS_MD = (
    "AGENTS.md has no <!-- bmad:context --> block — run /bmad-project-context setup"
    " so build-auto's implementers inherit your repo conventions"
)
_MSG_SPRINT_PLAN_SCRIPT = (
    "bmad-sprint-planning skill has no scripts/sprint_plan.py"
    " (BMAD < 6.11? run npx bmad-method install --action update)"
)
_MSG_UNKNOWN_HOST = "unknown host — nested subagents unverified"
_MSG_INLINE = "inline tier — build-auto's subagents run at depth 1"
_MSG_CLI_EXEMPT = (
    "bmad-build-auto runs only via the CLI route (cli_phases: build, followup_review)"
    " — no in-tool nesting needed"
)
_FIX_CLAUDE = (
    "unset CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH (default 3) or set it to 2 or more,"
    " then restart Claude Code"
)
_FIX_CODEX = (
    "add\n[agents]\nmax_depth = 2\nto ~/.codex/config.toml (or <project>/.codex/config.toml),"
    " or run `codex features enable multi_agent_v2`; then restart Codex."
    " (Keys verified against codex-cli 0.147.0 source; not in the public docs.)"
)
_FIX_OPENCODE = (
    'set "subagent_depth": 2 in opencode.json (project or ~/.config/opencode/opencode.json)'
    " and grant the Task tool to the subagent that spawns build-auto's subagents, e.g."
    ' "agent": {"general": {"permission": {"task": "allow"}}}'
    " (opencode denies task to subagents by default — verify against your opencode version)"
)
_MSG_OPENCODE_TASK_WARN = (
    "opencode: subagent_depth is >= 2 but no permission.task allow was found for the general"
    " subagent — nested spawns may be denied"
)


def real_runner(argv: Sequence[str], cwd: str | None = None) -> tuple[int, str, str]:
    """Run ``argv`` via subprocess; FileNotFoundError/timeout degrade to rc=127."""
    try:
        p = subprocess.run(
            list(argv), capture_output=True, text=True, cwd=cwd, timeout=_PROBE_TIMEOUT
        )
        return p.returncode, p.stdout, p.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        return 127, "", str(e)


# --- python (P2) ---

def classify_python() -> dict:
    """The interpreter running this script: version string + ok (>= 3.11 and tomllib present)."""
    vi = sys.version_info
    return {
        "version": f"{vi[0]}.{vi[1]}.{vi[2]}",
        "ok": vi >= (3, 11) and tomllib is not None,
    }


# --- central TOML config (P1) — mirrors upstream config_utils ---

class ConfigError(ValueError):
    """A present configuration layer cannot be used safely."""


def load_toml(path: Path, *, required: bool = False) -> dict:
    """Load a TOML table; absence is allowed only for optional layers."""
    if tomllib is None:
        raise ConfigError("tomllib unavailable (python < 3.11)")
    if not path.exists():
        if required:
            raise ConfigError(f"required TOML file not found: {path}")
        return {}
    if not path.is_file():
        raise ConfigError(f"TOML layer is not a file: {path}")
    try:
        with path.open("rb") as stream:
            parsed = tomllib.load(stream)
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"failed to parse {path}: {error}") from error
    except OSError as error:
        raise ConfigError(f"failed to read {path}: {error}") from error
    if not isinstance(parsed, dict):
        raise ConfigError(f"TOML layer did not parse to a table: {path}")
    return parsed


def _detect_keyed_merge_field(items: list) -> str | None:
    if not items or not all(isinstance(item, dict) for item in items):
        return None
    for candidate in _KEYED_MERGE_FIELDS:
        if all(candidate in item for item in items):
            for item in items:
                value = item[candidate]
                if not isinstance(value, str):
                    raise ConfigError(
                        f"keyed array identifier `{candidate}` must be a string, got {type(value).__name__}"
                    )
                if not value:
                    raise ConfigError(f"keyed array identifier `{candidate}` must not be empty")
            return candidate
    return None


def _merge_arrays(base: list, override: list) -> list:
    keyed_field = _detect_keyed_merge_field(base + override)
    if keyed_field is None:
        return list(base) + list(override)
    result: list = []
    index_by_key: dict[str, int] = {}
    for item in base:
        copied = dict(item)
        index_by_key[copied[keyed_field]] = len(result)
        result.append(copied)
    for item in override:
        copied = dict(item)
        key = copied[keyed_field]
        if key in index_by_key:
            result[index_by_key[key]] = copied
        else:
            index_by_key[key] = len(result)
            result.append(copied)
    return result


def structural_merge(base: Any, override: Any) -> Any:
    """Tables deep-merge, keyed table arrays merge by identity, other arrays append."""
    if isinstance(base, dict) and isinstance(override, dict):
        result = dict(base)
        for key, value in override.items():
            result[key] = structural_merge(result[key], value) if key in result else value
        return result
    if isinstance(base, list) and isinstance(override, list):
        return _merge_arrays(base, override)
    return override


def merge_layers(layers: Sequence[dict]) -> dict:
    merged: dict = {}
    for layer in layers:
        merged = structural_merge(merged, layer)
    return merged


def _substitute_root(value: Any, root: str) -> Any:
    """Replace the literal ``{project-root}`` token in every string value (recursively)."""
    if isinstance(value, str):
        return value.replace(_PROJECT_ROOT_TOKEN, root)
    if isinstance(value, dict):
        return {k: _substitute_root(v, root) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_root(v, root) for v in value]
    return value


def load_central_config(project_root: Path) -> tuple[dict, list[str]]:
    """Merge the four central layers (highest-last); returns (config, layers_read)."""
    bmad_dir = project_root / "_bmad"
    layers: list[dict] = []
    read: list[str] = []
    for i, parts in enumerate(_CENTRAL_LAYERS):
        path = bmad_dir.joinpath(*parts)
        table = load_toml(path, required=(i == 0))
        if path.is_file():
            read.append(str(path))
        layers.append(table)
    return _substitute_root(merge_layers(layers), str(project_root)), read


def _abs_path_value(value: Any, project_root: Path) -> str | None:
    """A path field: string ⇒ absolute (relative joins the root); anything else ⇒ null."""
    if not isinstance(value, str) or not value.strip():
        return None
    p = Path(value)
    return str(p if p.is_absolute() else project_root / p)


def classify_central_config(project_root: Path) -> tuple[dict, list[str]]:
    """The ``central_config`` block + its hard-stop reasons (P1 + modules.bmm)."""
    block: dict = {
        "present": (project_root / "_bmad" / "config.toml").is_file(),
        "layers_read": [],
        "output_folder": None,
        "implementation_artifacts": None,
        "planning_artifacts": None,
        "project_name": None,
        "error": None,
    }
    reasons: list[str] = []
    if not block["present"]:
        reasons.append(_MSG_NOT_BMAD)
        return block, reasons
    if tomllib is None:
        # P2 already hard-stops; without a TOML reader nothing more can be judged.
        block["error"] = "tomllib unavailable (python < 3.11) — central config not read"
        return block, reasons
    try:
        cfg, read = load_central_config(project_root)
    except ConfigError as e:
        block["error"] = str(e)
        reasons.append(f"could not read the BMAD central config: {e} — fix _bmad/config.toml (or its layers) and re-run")
        return block, reasons
    block["layers_read"] = read
    core = cfg.get("core") if isinstance(cfg.get("core"), dict) else {}
    modules = cfg.get("modules") if isinstance(cfg.get("modules"), dict) else {}
    bmm = modules.get("bmm") if isinstance(modules.get("bmm"), dict) else {}
    block["output_folder"] = _abs_path_value(core.get("output_folder"), project_root)
    block["implementation_artifacts"] = _abs_path_value(bmm.get("implementation_artifacts"), project_root)
    block["planning_artifacts"] = _abs_path_value(bmm.get("planning_artifacts"), project_root)
    name = core.get("project_name")
    block["project_name"] = name if isinstance(name, str) and name else None
    if block["output_folder"] is None:
        reasons.append("core.output_folder missing in _bmad/config.toml — re-run the BMAD installer")
    for field in ("implementation_artifacts", "planning_artifacts"):
        if block[field] is None:
            reasons.append(f"bmm module not configured in _bmad/config.toml (modules.bmm.{field} missing)")
    return block, reasons


# --- legacy YAML configs (P11) / TEA config (P12) ---

def classify_legacy_configs(project_root: Path) -> tuple[dict, list[str]]:
    block = {
        "bmm_present": (project_root / "_bmad" / "bmm" / "config.yaml").is_file(),
        "core_present": (project_root / "_bmad" / "core" / "config.yaml").is_file(),
    }
    warnings = [
        f"_bmad/{mod}/config.yaml missing — the delegated BMAD skills still load it; re-run the BMAD installer"
        for mod, key in (("bmm", "bmm_present"), ("core", "core_present"))
        if not block[key]
    ]
    return block, warnings


def classify_tea_config(project_root: Path) -> tuple[dict, list[str]]:
    present = (project_root / "_bmad" / "tea" / "config.yaml").is_file()
    warnings = [] if present else [
        "_bmad/tea/config.yaml missing — the delegated TEA skills still load it;"
        " re-run the BMAD installer with the tea module"
    ]
    return {"present": present}, warnings


# --- uv (P3) / Python >= 3.11 for uv (P4) ---

def classify_uv(run: Runner, which: Which) -> dict:
    path = which("uv")
    version = None
    if path:
        rc, out, _ = run(["uv", "--version"])
        if rc == 0:
            version = out.strip().splitlines()[0] if out.strip() else None
    return {"on_path": bool(path), "path": path, "version": version}


def classify_python311(run: Runner, uv_on_path: bool, env: Mapping[str, str]) -> dict:
    """``uv python find '>=3.11' --no-python-downloads``: exit 0 ⇒ ok; else warn/hard_stop."""
    if not uv_on_path:
        return {"status": "warn", "found": None, "detail": "uv not on PATH — probe skipped"}
    rc, out, err = run(["uv", "python", "find", ">=3.11", "--no-python-downloads"])
    if rc == 0:
        found = out.strip().splitlines()[0] if out.strip() else None
        return {"status": "ok", "found": found, "detail": out.strip() or "found"}
    detail = (err.strip() or out.strip() or f"exit {rc}").splitlines()[0][:300]
    downloads = env.get("UV_PYTHON_DOWNLOADS", "").strip().lower()
    if downloads in _UV_DOWNLOADS_OFF:
        return {"status": "hard_stop", "found": None, "detail": detail}
    return {"status": "warn", "found": None, "detail": detail}


def _python311_messages(block: dict, env: Mapping[str, str], uv_on_path: bool) -> tuple[list[str], list[str]]:
    """(warnings, hard_stop_reasons) for the python311 block."""
    if block["status"] == "ok":
        return [], []
    if not uv_on_path:
        return ["python >=3.11 probe skipped (uv not on PATH)"], []
    if block["status"] == "hard_stop":
        value = env.get("UV_PYTHON_DOWNLOADS", "").strip()
        return [], [
            "no Python >=3.11 available to uv and Python downloads are disabled"
            f" (UV_PYTHON_DOWNLOADS={value}) — run `uv python install 3.11`"
        ]
    return [_MSG_PY311_WARN], []


# --- AGENTS.md (P10) ---

def classify_agents_md(project_root: Path) -> dict:
    f = project_root / "AGENTS.md"
    if not f.is_file():
        return {"present": False, "has_context_block": False}
    try:
        text = f.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    return {"present": True, "has_context_block": _AGENTS_MD_OPEN in text and _AGENTS_MD_CLOSE in text}


# --- nesting (P6) ---

def parse_claude_depth(raw: str | None) -> int | None:
    """Claude Code's env parser: ``^[+-]?\\d+$`` after strip, values < 1 ignored ⇒ None."""
    if raw is None:
        return None
    s = raw.strip()
    if not re.fullmatch(r"[+-]?\d+", s):
        return None
    v = int(s)
    return v if v >= 1 else None


def strip_json_line_comments(text: str) -> str:
    """Drop ``//`` line comments that sit outside JSON strings (jsonc tolerance)."""
    out: list[str] = []
    in_str = False
    esc = False
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _nesting(host: str, tier: str, status: str, detail: str, fix: str | None, sources: list[str]) -> dict:
    return {"host": host, "tier": tier, "status": status, "detail": detail, "fix": fix, "sources": sources}


def _classify_claude_nesting(host: str, tier: str, env: Mapping[str, str]) -> dict:
    raw = env.get(_CLAUDE_DEPTH_ENV)
    sources = [f"env:{_CLAUDE_DEPTH_ENV}"]
    depth = parse_claude_depth(raw)
    if raw is None:
        return _nesting(host, tier, "ok", f"{_CLAUDE_DEPTH_ENV} unset — Claude Code default depth 3", None, sources)
    if depth is None:
        return _nesting(
            host, tier, "ok",
            f"{_CLAUDE_DEPTH_ENV}={raw!r} is ignored by Claude Code (non-integer or < 1) — default depth 3 applies",
            None, sources,
        )
    if depth >= 2:
        return _nesting(host, tier, "ok", f"{_CLAUDE_DEPTH_ENV}={depth} allows the depth-2 chain", None, sources)
    return _nesting(
        host, tier, "hard_stop",
        f"{_CLAUDE_DEPTH_ENV}=1 disables nested subagents — the delegate cannot spawn build-auto's subagents",
        _FIX_CLAUDE, sources,
    )


def _classify_codex_nesting(host: str, tier: str, project_root: Path, env: Mapping[str, str], home: Path) -> dict:
    codex_home = Path(env["CODEX_HOME"]) if env.get("CODEX_HOME") else home / ".codex"
    files = [codex_home / "config.toml", project_root / ".codex" / "config.toml"]
    if tomllib is None:
        return _nesting(host, tier, "warn", "tomllib unavailable — nesting could not be verified", None, [])
    merged: dict = {}
    sources: list[str] = []
    for f in files:
        if not f.is_file():
            continue
        try:
            table = load_toml(f)
        except ConfigError as e:
            return _nesting(host, tier, "warn", f"could not parse {f}: {e} — nesting could not be verified", None, sources)
        sources.append(str(f))
        merged = structural_merge(merged, table)
    features = merged.get("features") if isinstance(merged.get("features"), dict) else {}
    agents = merged.get("agents") if isinstance(merged.get("agents"), dict) else {}
    v2 = features.get("multi_agent_v2") is True
    max_depth = agents.get("max_depth")
    depth_ok = isinstance(max_depth, int) and not isinstance(max_depth, bool) and max_depth >= 2
    if v2:
        return _nesting(host, tier, "ok", "features.multi_agent_v2 = true (agents.max_depth ignored under V2)", None, sources)
    if depth_ok:
        return _nesting(host, tier, "ok", f"agents.max_depth = {max_depth} allows the depth-2 chain", None, sources)
    where = "absent" if max_depth is None else repr(max_depth)
    return _nesting(
        host, tier, "hard_stop",
        f"codex agents.max_depth is {where} (V1 default 1) and features.multi_agent_v2 is off"
        " — the delegate cannot spawn build-auto's subagents",
        _FIX_CODEX, sources,
    )


def _opencode_layer_files(project_root: Path, env: Mapping[str, str], home: Path) -> list[Path]:
    spots = [home / ".config" / "opencode" / "opencode.json"]
    if env.get("OPENCODE_CONFIG"):
        spots.append(Path(env["OPENCODE_CONFIG"]))
    spots.append(project_root / "opencode.json")
    spots.append(project_root / ".opencode" / "opencode.json")
    files: list[Path] = []
    for p in spots:
        files.append(p)
        if p.suffix == ".json":
            files.append(p.with_suffix(".jsonc"))
    return files


def _opencode_task_allowed(merged: dict) -> bool:
    agent = merged.get("agent") if isinstance(merged.get("agent"), dict) else {}
    general = agent.get("general") if isinstance(agent.get("general"), dict) else {}
    perm = general.get("permission") if isinstance(general.get("permission"), dict) else {}
    task = perm.get("task")
    if isinstance(task, str):
        return task == "allow"
    if isinstance(task, dict):
        return any(v == "allow" for v in task.values())
    return False


def _classify_opencode_nesting(host: str, tier: str, project_root: Path, env: Mapping[str, str], home: Path) -> dict:
    merged: dict = {}
    sources: list[str] = []
    depth: Any = None
    for f in _opencode_layer_files(project_root, env, home):
        if not f.is_file():
            continue
        try:
            data = json.loads(strip_json_line_comments(f.read_text(encoding="utf-8", errors="replace")))
        except (OSError, ValueError) as e:
            return _nesting(host, tier, "warn", f"could not parse {f}: {e} — nesting could not be verified", None, sources)
        if not isinstance(data, dict):
            return _nesting(host, tier, "warn", f"could not parse {f}: top level is not an object — nesting could not be verified", None, sources)
        sources.append(str(f))
        if "subagent_depth" in data:
            depth = data["subagent_depth"]  # highest layer that sets it wins
        merged = structural_merge(merged, data)
    depth_ok = isinstance(depth, int) and not isinstance(depth, bool) and depth >= 2
    if not depth_ok:
        where = "unset (default 1)" if depth is None else repr(depth)
        return _nesting(
            host, tier, "hard_stop",
            f"opencode subagent_depth is {where} — the delegate cannot spawn build-auto's subagents",
            _FIX_OPENCODE, sources,
        )
    if not _opencode_task_allowed(merged):
        return _nesting(host, tier, "warn", _MSG_OPENCODE_TASK_WARN, _FIX_OPENCODE, sources)
    return _nesting(host, tier, "ok", f"opencode subagent_depth = {depth} and agent.general.permission.task allows nested spawns", None, sources)


def classify_nesting(
    host: str,
    tier: str,
    project_root: Path,
    cli_phases: Sequence[str] = (),
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> dict:
    """The ``nesting`` block per spec §1.4 (pure given env/home/filesystem)."""
    env = os.environ if env is None else env
    home = Path.home() if home is None else home
    if _CLI_PHASES_EXEMPT <= set(cli_phases):
        return _nesting(host, tier, "ok", _MSG_CLI_EXEMPT, None, [])
    if tier == "inline":
        return _nesting(host, tier, "ok", _MSG_INLINE, None, [])
    if host == "claude-code":
        return _classify_claude_nesting(host, tier, env)
    if host == "codex":
        return _classify_codex_nesting(host, tier, project_root, env, home)
    if host == "opencode":
        return _classify_opencode_nesting(host, tier, project_root, env, home)
    return _nesting(host, tier, "warn", _MSG_UNKNOWN_HOST, None, [])


# --- cross-model tool (P8) ---

def classify_cross_model(tool: str | None, which: Which) -> dict:
    if not tool:
        return {"tool": None, "binary": None, "binary_on_path": None}
    binary = _TOOL_BINARY.get(tool, tool)
    return {"tool": tool, "binary": binary, "binary_on_path": which(binary) is not None}


# --- git (P7) ---

def classify_git(run: Runner) -> dict:
    """Derive the ``git`` block from injected command results. Pure given ``run``."""
    rc, _, _ = run(["git", "rev-parse", "--is-inside-work-tree"])
    is_repo = rc == 0

    current_branch = None
    tree_clean: bool | None = True
    dirty_files_count: int | None = 0
    status_error = None
    base_branch = None
    if is_repo:
        rc, out, _ = run(["git", "branch", "--show-current"])
        current_branch = out.strip() or None if rc == 0 else None

        rc, out, err = run(["git", "status", "--porcelain"])
        if rc == 0:
            dirty_lines = [l for l in out.splitlines() if l.strip()]
            dirty_files_count = len(dirty_lines)
            tree_clean = dirty_files_count == 0
        else:
            # Fail CLOSED: an unevaluable tree must never read as clean.
            tree_clean = None
            dirty_files_count = None
            status_error = (err.strip() or f"exit {rc}").splitlines()[0][:200]

        rc, out, _ = run(["git", "symbolic-ref", "refs/remotes/origin/HEAD"])
        if rc == 0 and out.strip():
            ref = out.strip()
            prefix = "refs/remotes/origin/"
            base_branch = ref[len(prefix):] if ref.startswith(prefix) else ref
        else:
            base_branch = current_branch

    rc, _, _ = run(["gh", "--version"])
    gh_installed = rc == 0
    gh_authed = False
    if gh_installed:
        rc, _, _ = run(["gh", "auth", "status"])
        gh_authed = rc == 0

    github_remote = False
    if is_repo:
        rc, out, _ = run(["git", "remote", "-v"])
        github_remote = rc == 0 and "github.com" in out

    mode = "remote" if (gh_installed and gh_authed and github_remote) else "local"

    return {
        "is_repo": is_repo,
        "current_branch": current_branch,
        "tree_clean": tree_clean,
        "dirty_files_count": dirty_files_count,
        "status_error": status_error,
        "base_branch": base_branch,
        "mode": mode,
        "gh_installed": gh_installed,
        "gh_authed": gh_authed,
        "github_remote": github_remote,
    }


def classify_git_hard_stop(git: dict, expected_branch: str | None) -> list[str]:
    """Git hard-stop rules: not a repo; tree state unknown (fail closed); dirty off
    the expected branch; detached/unknown HEAD."""
    reasons: list[str] = []
    if not git["is_repo"]:
        reasons.append("not a git repo (run `git init` first — the local-branch flow needs a repo)")
        return reasons
    if git["tree_clean"] is None:
        # Fail CLOSED: the dirty-tree gate could not run, so we must not proceed.
        reasons.append(
            f"could not evaluate working tree (git status failed: {git['status_error']})"
            " — fix git and re-run preflight"
        )
    elif not git["tree_clean"]:
        # Dirty ON the expected story branch is fine — the resume case.
        if expected_branch is None or git["current_branch"] != expected_branch:
            where = f"on branch {git['current_branch']!r}" if git["current_branch"] else "with detached/unknown branch"
            reasons.append(
                f"working tree dirty ({git['dirty_files_count']} file(s)) {where}"
                + ("" if expected_branch is None else f", not the expected story branch {expected_branch!r}")
                + " — commit or stash first"
            )
    if git["current_branch"] is None:
        # Even on a clean tree: a null branch poisons base_branch downstream
        # (git switch -c <branch> <base>, gh pr create --base).
        reasons.append(
            "detached/unknown branch — check out a branch first (branching and the PR base need one)"
        )
    return reasons


# --- ci / skills / framework ---

def detect_ci(project_root: Path) -> dict:
    """Any *.yml/*.yaml under .github/workflows, or .gitlab-ci.yml at root."""
    workflows = project_root / ".github" / "workflows"
    present = False
    if workflows.is_dir():
        for dirpath, dirnames, filenames in os.walk(workflows):
            dirnames[:] = sorted(d for d in dirnames if d not in _WALK_EXCLUDES)
            if any(f.endswith((".yml", ".yaml")) for f in filenames):
                present = True
                break
    if not present and (project_root / ".gitlab-ci.yml").is_file():
        present = True
    return {"workflows_present": present}


def check_skills(required: Sequence[str], skills_dirs: Sequence[Path]) -> dict:
    """A skill is present iff a directory of that name exists under ANY skills dir;
    ``sprint_plan_script`` = the first ``bmad-sprint-planning/scripts/sprint_plan.py``
    in ``skills_dirs`` order, as an absolute path (``null`` when no dirs are given
    or none has it)."""
    checked = [s for s in required if s]
    missing = [
        name for name in checked
        if not any((d / name).is_dir() for d in skills_dirs)
    ]
    script = None
    for d in skills_dirs:
        cand = d / "bmad-sprint-planning" / "scripts" / "sprint_plan.py"
        if cand.is_file():
            script = str(cand.absolute())
            break
    return {"checked": checked, "missing": missing, "sprint_plan_script": script}


def classify_skills_hard_stop(skills: dict, skills_dirs_given: bool) -> list[str]:
    reasons: list[str] = []
    for name in skills["missing"]:
        if name in _BMAD_611_SKILLS:
            hint = " (BMAD < 6.11? run npx bmad-method install --action update)"
        elif name.startswith("bmad-testarch-"):
            hint = " — install it: npx bmad-method install --modules tea"
        else:
            hint = " — install it: npx bmad-method install --modules bmm"
        reasons.append(f"required skill missing: {name}{hint}")
    if skills_dirs_given and skills["sprint_plan_script"] is None and "bmad-sprint-planning" not in skills["missing"]:
        reasons.append(_MSG_SPRINT_PLAN_SCRIPT)
    return reasons


def detect_framework(project_root: Path, ci_present: bool) -> dict:
    """Test-framework configs at the project root (first-run flow step 2)."""
    configs: list[str] = []
    try:
        entries = sorted(p.name for p in project_root.iterdir() if p.is_file())
    except OSError:
        entries = []
    for name in entries:
        if name == "pytest.ini" or (
            name.startswith(_FRAMEWORK_PREFIXES)
            and Path(name).suffix in _FRAMEWORK_CONFIG_SUFFIXES
        ):
            configs.append(name)
    for name, marker in (("pyproject.toml", "[tool.pytest"), ("setup.cfg", "[tool:pytest]")):
        f = project_root / name
        if f.is_file():
            try:
                if marker in f.read_text(encoding="utf-8", errors="replace"):
                    configs.append(name)
            except OSError:
                pass
    return {"configs": configs, "ci_present": ci_present}


# --- assembly ---

_NULL_BLOCKS = (
    "legacy_configs", "tea_config", "uv", "python311", "agents_md", "nesting",
    "cross_model", "git", "ci", "skills", "framework",
)


def preflight(
    project_root: Path,
    *,
    central_config_only: bool = False,
    host: str | None = None,
    tier: str | None = None,
    expected_branch: str | None = None,
    require_skills: Sequence[str] = (),
    skills_dirs: Sequence[Path] = (),
    detect_framework_ci: bool = False,
    tea_enabled: bool = False,
    cross_model_tool: str | None = None,
    cli_phases: Sequence[str] = (),
    run: Runner | None = None,
    which: Which | None = None,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> dict:
    """Assemble the full preflight JSON object (pure given ``run``/``which``/``env``/``home`` + a filesystem)."""
    if run is None:
        run = lambda argv: real_runner(argv, cwd=str(project_root))  # noqa: E731
    which = shutil.which if which is None else which
    env = os.environ if env is None else env

    warnings: list[str] = []
    reasons: list[str] = []

    python = classify_python()
    if not python["ok"]:
        reasons.append(_MSG_PYTHON_OLD)
    central, cc_reasons = classify_central_config(project_root)
    reasons.extend(cc_reasons)

    result: dict = {"python": python, "central_config": central}
    if central_config_only:
        result.update({k: None for k in _NULL_BLOCKS})
        result.update({"warnings": warnings, "hard_stop": bool(reasons), "hard_stop_reasons": reasons})
        return result

    legacy, w = classify_legacy_configs(project_root)
    warnings.extend(w)
    tea_cfg = None
    if tea_enabled:
        tea_cfg, w = classify_tea_config(project_root)
        warnings.extend(w)

    uv = classify_uv(run, which)
    if not uv["on_path"]:
        reasons.append(_MSG_UV_MISSING)
    py311 = classify_python311(run, uv["on_path"], env)
    w, r = _python311_messages(py311, env, uv["on_path"])
    warnings.extend(w)
    reasons.extend(r)

    agents_md = classify_agents_md(project_root)
    if not agents_md["has_context_block"]:
        warnings.append(_MSG_AGENTS_MD)

    nesting = classify_nesting(host or "other", tier or "subagents", project_root, cli_phases, env, home)
    if nesting["status"] == "warn":
        warnings.append(f"nesting: {nesting['detail']}")
    elif nesting["status"] == "hard_stop":
        reasons.append(f"nested subagents unavailable on {nesting['host']}: {nesting['detail']}. Fix: {nesting['fix']}")

    cross = classify_cross_model(cross_model_tool, which)
    if cross["tool"] and not cross["binary_on_path"]:
        reasons.append(
            f"code_review.cross_model_layer = {cross['tool']} but `{cross['binary']}` is not on PATH"
            ' — install it, or set cross_model_layer: "" and run /auto-bmad reprovision'
        )

    git = classify_git(run)
    reasons.extend(classify_git_hard_stop(git, expected_branch))
    ci = detect_ci(project_root)
    skills = check_skills(require_skills, skills_dirs)
    reasons.extend(classify_skills_hard_stop(skills, bool(skills_dirs)))

    result.update({
        "legacy_configs": legacy,
        "tea_config": tea_cfg,
        "uv": uv,
        "python311": py311,
        "agents_md": agents_md,
        "nesting": nesting,
        "cross_model": cross,
        "git": git,
        "ci": ci,
        "skills": skills,
        "framework": detect_framework(project_root, ci["workflows_present"]) if detect_framework_ci else None,
        "warnings": warnings,
        "hard_stop": bool(reasons),
        "hard_stop_reasons": reasons,
    })
    return result


# --- self-test ---

def _fake_runner(table: dict) -> Runner:
    """Map an argv (joined) to (rc, stdout, stderr); unknown commands fail rc=127."""
    def run(argv: Sequence[str]) -> tuple[int, str, str]:
        return table.get(" ".join(argv), (127, "", "unknown command"))
    return run


def _fake_which(present: Sequence[str]) -> Which:
    return lambda name: f"/fake/bin/{name}" if name in present else None


_GIT_OK = {
    "git rev-parse --is-inside-work-tree": (0, "true\n", ""),
    "git branch --show-current": (0, "story/1-2-auth\n", ""),
    "git status --porcelain": (0, "", ""),
    "git symbolic-ref refs/remotes/origin/HEAD": (0, "refs/remotes/origin/main\n", ""),
    "git remote -v": (0, "origin\tgit@github.com:me/repo.git (fetch)\n", ""),
    "gh --version": (0, "gh version 2.0\n", ""),
    "gh auth status": (0, "Logged in\n", ""),
}
_UV_OK = {
    "uv --version": (0, "uv 0.12.4 (Homebrew 2026-08-13 aarch64-apple-darwin)\n", ""),
    "uv python find >=3.11 --no-python-downloads": (0, "/opt/py/bin/python3.14\n", ""),
}
_UV_NO_PY = {
    "uv --version": (0, "uv 0.12.4\n", ""),
    "uv python find >=3.11 --no-python-downloads": (
        2, "", "error: No interpreter found for Python >=3.11 in virtual environments, managed installations, or search path\n",
    ),
}
_ALL_OK = {**_GIT_OK, **_UV_OK}

_CENTRAL_TOML = """
[core]
project_name = "demo"
output_folder = "{project-root}/_bmad-output"

[modules.bmm]
planning_artifacts = "{project-root}/_bmad-output/planning-artifacts"
implementation_artifacts = "{project-root}/_bmad-output/implementation-artifacts"
project_knowledge = "{project-root}/docs"

[[agents]]
code = "pm"
description = "base pm"

[[agents]]
code = "dev"
description = "base dev"
"""


def _write_bmad_project(root: Path, *, layers: bool = True) -> None:
    (root / "_bmad" / "custom").mkdir(parents=True, exist_ok=True)
    (root / "_bmad" / "config.toml").write_text(_CENTRAL_TOML, encoding="utf-8")
    if layers:
        (root / "_bmad" / "config.user.toml").write_text('[core]\nuser_name = "Stefano"\n', encoding="utf-8")
        (root / "_bmad" / "custom" / "config.toml").write_text(
            '[[agents]]\ncode = "pm"\ndescription = "team pm"\n\n[[agents]]\ncode = "qa"\ndescription = "qa"\n',
            encoding="utf-8",
        )
        (root / "_bmad" / "custom" / "config.user.toml").write_text(
            '[core]\noutput_folder = "{project-root}/personal-out"\n', encoding="utf-8"
        )


def _run_self_test() -> int:
    import tempfile

    # --- python (this interpreter must satisfy P2 for the rest of the test) ---
    py = classify_python()
    assert py["ok"] is True and py["version"].count(".") == 2, py

    # --- structural merge (mirrors upstream config_utils) ---
    m = structural_merge({"a": {"x": 1, "y": 2}, "l": [1]}, {"a": {"y": 3, "z": 4}, "l": [2]})
    assert m == {"a": {"x": 1, "y": 3, "z": 4}, "l": [1, 2]}, m  # tables deep-merge, plain arrays append
    keyed = _merge_arrays([{"code": "pm", "v": 1}, {"code": "dev", "v": 1}], [{"code": "pm", "v": 2}, {"code": "qa", "v": 1}])
    assert [i["code"] for i in keyed] == ["pm", "dev", "qa"] and keyed[0]["v"] == 2, keyed  # replace by key, append new
    assert _merge_arrays([{"id": "a"}], [{"id": "a", "n": 1}]) == [{"id": "a", "n": 1}]
    assert structural_merge(1, "x") == "x" and structural_merge({"a": 1}, "s") == "s"
    try:
        _merge_arrays([{"code": ""}], [{"code": "x"}]); assert False, "empty key must raise"
    except ConfigError:
        pass
    try:
        _merge_arrays([{"code": 1}], [{"code": "x"}]); assert False, "non-str key must raise"
    except ConfigError:
        pass
    assert _substitute_root({"a": ["{project-root}/x", 1], "b": {"c": "{project-root}"}}, "/R") == {"a": ["/R/x", 1], "b": {"c": "/R"}}

    # --- Claude env parser semantics ---
    assert parse_claude_depth(None) is None and parse_claude_depth("") is None
    assert parse_claude_depth("abc") is None and parse_claude_depth("1.5") is None
    assert parse_claude_depth("0") is None and parse_claude_depth("-3") is None  # < 1 ignored
    assert parse_claude_depth(" 1 ") == 1 and parse_claude_depth("+2") == 2 and parse_claude_depth("3") == 3

    # --- jsonc comment stripping ---
    s = strip_json_line_comments('{"u": "https://x/y", // c\n "n": 2 // t\n}')
    assert json.loads(s) == {"u": "https://x/y", "n": 2}, s
    s = strip_json_line_comments('{"e": "a\\"//b", "k": 1}')
    assert json.loads(s) == {"e": 'a"//b', "k": 1}, s

    # --- git classification: happy remote path ---
    g = classify_git(_fake_runner(_GIT_OK))
    assert g["is_repo"] and g["tree_clean"] and g["dirty_files_count"] == 0, g
    assert g["current_branch"] == "story/1-2-auth", g
    assert g["base_branch"] == "main", g  # remote HEAD wins, prefix stripped
    assert g["mode"] == "remote" and g["gh_installed"] and g["gh_authed"] and g["github_remote"], g

    # No remote HEAD -> base falls back to the current branch.
    t = dict(_GIT_OK); t["git symbolic-ref refs/remotes/origin/HEAD"] = (1, "", "no ref")
    assert classify_git(_fake_runner(t))["base_branch"] == "story/1-2-auth"

    # mode=local when ANY of the three legs fails.
    for k, v in (
        ("gh --version", (127, "", "not found")),
        ("gh auth status", (1, "", "not logged in")),
        ("git remote -v", (0, "origin\tgit@gitlab.com:me/repo.git (fetch)\n", "")),
    ):
        t = dict(_GIT_OK); t[k] = v
        g2 = classify_git(_fake_runner(t))
        assert g2["mode"] == "local", (k, g2)
    # gh auth must not even be probed when gh isn't installed.
    t = dict(_GIT_OK); t["gh --version"] = (127, "", "")
    del t["gh auth status"]
    assert classify_git(_fake_runner(t))["gh_authed"] is False

    # Dirty tree: porcelain line count.
    t = dict(_GIT_OK); t["git status --porcelain"] = (0, " M a.py\n?? b.py\n", "")
    g3 = classify_git(_fake_runner(t))
    assert not g3["tree_clean"] and g3["dirty_files_count"] == 2, g3

    # Not a repo: git sub-probes skipped, defaults hold.
    t = {"git rev-parse --is-inside-work-tree": (128, "", "fatal"), "gh --version": (127, "", "")}
    g4 = classify_git(_fake_runner(t))
    assert not g4["is_repo"] and g4["current_branch"] is None and g4["base_branch"] is None, g4
    assert g4["mode"] == "local" and g4["github_remote"] is False, g4

    # status probe FAILURE -> tree state unknown (null), never "clean" (fail closed).
    t = dict(_GIT_OK); t["git status --porcelain"] = (127, "", "timed out after 20 seconds")
    g5 = classify_git(_fake_runner(t))
    assert g5["tree_clean"] is None and g5["dirty_files_count"] is None, g5
    assert "timed out" in g5["status_error"], g5
    t = dict(_GIT_OK); t["git status --porcelain"] = (128, "", "")
    assert classify_git(_fake_runner(t))["status_error"] == "exit 128"
    assert g["status_error"] is None and g3["status_error"] is None

    # Clean DETACHED head: branch null, tree still clean (hard-stop rule covers it).
    t = dict(_GIT_OK)
    t["git branch --show-current"] = (0, "", "")
    t["git symbolic-ref refs/remotes/origin/HEAD"] = (1, "", "no ref")
    g6 = classify_git(_fake_runner(t))
    assert g6["current_branch"] is None and g6["base_branch"] is None and g6["tree_clean"], g6

    # --- git hard-stop rules ---
    r = classify_git_hard_stop(g4, None)
    assert any("not a git repo" in x for x in r), r
    r = classify_git_hard_stop(g3, None)
    assert any("dirty" in x for x in r), r
    assert classify_git_hard_stop(g3, "story/9-9-other")
    assert classify_git_hard_stop(g3, "story/1-2-auth") == []  # resume case
    assert classify_git_hard_stop(g, None) == []
    r = classify_git_hard_stop(g5, None)
    assert any("could not evaluate working tree" in x and "timed out" in x for x in r), r
    assert classify_git_hard_stop(g5, "story/1-2-auth")
    r = classify_git_hard_stop(g6, None)
    assert any("detached/unknown branch" in x for x in r), r

    # --- skills hard-stop rules ---
    r = classify_skills_hard_stop({"checked": ["bmad-build-auto"], "missing": ["bmad-build-auto"], "sprint_plan_script": "/x"}, True)
    assert r == ["required skill missing: bmad-build-auto (BMAD < 6.11? run npx bmad-method install --action update)"], r
    r = classify_skills_hard_stop({"checked": ["bmad-testarch-atdd"], "missing": ["bmad-testarch-atdd"], "sprint_plan_script": "/x"}, True)
    assert r[0].startswith("required skill missing: bmad-testarch-atdd") and "--modules tea" in r[0], r
    r = classify_skills_hard_stop({"checked": ["bmad-retrospective"], "missing": ["bmad-retrospective"], "sprint_plan_script": "/x"}, True)
    assert r[0].startswith("required skill missing: bmad-retrospective") and "--modules bmm" in r[0], r
    # sprint_plan_script null with skills dirs given -> stop; suppressed when the skill itself is missing; not probed w/o dirs.
    assert classify_skills_hard_stop({"checked": [], "missing": [], "sprint_plan_script": None}, True) == [_MSG_SPRINT_PLAN_SCRIPT]
    r = classify_skills_hard_stop({"checked": ["bmad-sprint-planning"], "missing": ["bmad-sprint-planning"], "sprint_plan_script": None}, True)
    assert len(r) == 1 and r[0].startswith("required skill missing: bmad-sprint-planning"), r
    assert classify_skills_hard_stop({"checked": [], "missing": [], "sprint_plan_script": None}, False) == []

    # --- uv / python311 ---
    uv = classify_uv(_fake_runner(_UV_OK), _fake_which(["uv"]))
    assert uv == {"on_path": True, "path": "/fake/bin/uv", "version": "uv 0.12.4 (Homebrew 2026-08-13 aarch64-apple-darwin)"}, uv
    uv = classify_uv(_fake_runner({}), _fake_which([]))
    assert uv == {"on_path": False, "path": None, "version": None}, uv
    p = classify_python311(_fake_runner(_UV_OK), True, {})
    assert p["status"] == "ok" and p["found"] == "/opt/py/bin/python3.14", p
    p = classify_python311(_fake_runner(_UV_NO_PY), True, {})
    assert p["status"] == "warn" and p["found"] is None and "No interpreter found" in p["detail"], p
    assert _python311_messages(p, {}, True) == ([_MSG_PY311_WARN], [])
    for off in ("never", "0", "false", "OFF"):
        p = classify_python311(_fake_runner(_UV_NO_PY), True, {"UV_PYTHON_DOWNLOADS": off})
        assert p["status"] == "hard_stop", (off, p)
        w, r = _python311_messages(p, {"UV_PYTHON_DOWNLOADS": off}, True)
        assert w == [] and len(r) == 1 and f"(UV_PYTHON_DOWNLOADS={off})" in r[0] and "uv python install 3.11" in r[0], r
    p = classify_python311(_fake_runner(_UV_NO_PY), True, {"UV_PYTHON_DOWNLOADS": "automatic"})
    assert p["status"] == "warn", p
    p = classify_python311(_fake_runner({}), False, {"UV_PYTHON_DOWNLOADS": "never"})
    assert p["status"] == "warn" and "probe skipped" in p["detail"], p
    assert _python311_messages(p, {"UV_PYTHON_DOWNLOADS": "never"}, False) == (["python >=3.11 probe skipped (uv not on PATH)"], [])

    # --- cross_model ---
    assert classify_cross_model(None, _fake_which([])) == {"tool": None, "binary": None, "binary_on_path": None}
    assert classify_cross_model("codex", _fake_which(["codex"])) == {"tool": "codex", "binary": "codex", "binary_on_path": True}
    assert classify_cross_model("claude", _fake_which([]))["binary_on_path"] is False

    # --- filesystem rules in a sandbox ---
    with tempfile.TemporaryDirectory() as td:
        root = Path(td).resolve()
        home = root / "HOME"; home.mkdir()

        # central_config: no _bmad/config.toml -> not a BMAD project.
        cc, r = classify_central_config(root)
        assert cc["present"] is False and r == [_MSG_NOT_BMAD], (cc, r)
        # Base only: paths absolute with {project-root} substituted; layers_read = 1.
        _write_bmad_project(root, layers=False)
        cc, r = classify_central_config(root)
        assert r == [] and cc["present"] and cc["error"] is None, (cc, r)
        assert cc["layers_read"] == [str(root / "_bmad" / "config.toml")], cc
        assert cc["output_folder"] == str(root / "_bmad-output"), cc
        assert cc["implementation_artifacts"] == str(root / "_bmad-output" / "implementation-artifacts"), cc
        assert cc["planning_artifacts"] == str(root / "_bmad-output" / "planning-artifacts"), cc
        assert cc["project_name"] == "demo", cc
        # All four layers: highest-last wins (custom/config.user.toml overrides output_folder);
        # tables deep-merge; keyed arrays merge by `code`.
        _write_bmad_project(root, layers=True)
        cfg, read = load_central_config(root)
        assert len(read) == 4 and read[-1].endswith("custom/config.user.toml"), read
        assert cfg["core"]["user_name"] == "Stefano" and cfg["core"]["project_name"] == "demo", cfg
        assert [a["code"] for a in cfg["agents"]] == ["pm", "dev", "qa"] and cfg["agents"][0]["description"] == "team pm", cfg
        cc, r = classify_central_config(root)
        assert r == [] and cc["output_folder"] == str(root / "personal-out") and len(cc["layers_read"]) == 4, cc
        # Relative path value -> joined onto the root; empty -> null.
        (root / "_bmad" / "custom" / "config.user.toml").write_text('[core]\noutput_folder = "rel-out"\n', encoding="utf-8")
        cc, _ = classify_central_config(root)
        assert cc["output_folder"] == str(root / "rel-out"), cc
        # core-only install (no modules.bmm) -> two nulls + hard-stop naming implementation_artifacts.
        (root / "_bmad" / "custom" / "config.user.toml").write_text("", encoding="utf-8")
        (root / "_bmad" / "config.toml").write_text('[core]\noutput_folder = "{project-root}/o"\n', encoding="utf-8")
        cc, r = classify_central_config(root)
        assert cc["implementation_artifacts"] is None and cc["planning_artifacts"] is None, cc
        assert r[0] == "bmm module not configured in _bmad/config.toml (modules.bmm.implementation_artifacts missing)", r
        assert len(r) == 2 and "planning_artifacts missing" in r[1], r
        # Missing core.output_folder -> hard-stop.
        (root / "_bmad" / "config.toml").write_text('[modules.bmm]\nimplementation_artifacts = "a"\nplanning_artifacts = "b"\n', encoding="utf-8")
        cc, r = classify_central_config(root)
        assert cc["output_folder"] is None and any("core.output_folder missing" in x for x in r), (cc, r)
        # Unparseable layer -> error + hard-stop.
        (root / "_bmad" / "config.toml").write_text('[core\noutput_folder = 1\n', encoding="utf-8")
        cc, r = classify_central_config(root)
        assert cc["present"] and cc["error"] and "failed to parse" in cc["error"], cc
        assert len(r) == 1 and r[0].startswith("could not read the BMAD central config"), r
        try:
            load_toml(root / "_bmad" / "config.toml", required=True); assert False
        except ConfigError:
            pass
        try:
            load_toml(root / "_bmad" / "nope.toml", required=True); assert False
        except ConfigError:
            pass
        assert load_toml(root / "_bmad" / "nope.toml") == {}
        try:
            load_toml(root / "_bmad" / "custom"); assert False, "a directory is not a layer"
        except ConfigError:
            pass
        _write_bmad_project(root, layers=False)  # restore a good project for the rest
        # P2 path (simulated python < 3.11): tomllib absent -> python not ok, central config
        # unread (error, no bmm stop), codex nesting warn; nothing tracebacks.
        global tomllib
        real_tomllib, tomllib = tomllib, None
        try:
            assert classify_python()["ok"] is False
            cc, r = classify_central_config(root)
            assert cc["present"] and "tomllib unavailable" in cc["error"] and r == [], (cc, r)
            n = classify_nesting("codex", "subagents", root, [], {}, home)
            assert n["status"] == "warn" and "tomllib unavailable" in n["detail"], n
            res = preflight(root, central_config_only=True, run=_fake_runner({}), which=_fake_which([]), env={}, home=home)
            assert res["hard_stop_reasons"] == [_MSG_PYTHON_OLD], res
            try:
                load_toml(root / "_bmad" / "config.toml"); assert False
            except ConfigError:
                pass
        finally:
            tomllib = real_tomllib

        # legacy_configs / tea_config: two independent warnings; tea only when asked.
        lc, w = classify_legacy_configs(root)
        assert lc == {"bmm_present": False, "core_present": False} and len(w) == 2, (lc, w)
        assert w[0].startswith("_bmad/bmm/config.yaml missing") and w[1].startswith("_bmad/core/config.yaml missing"), w
        (root / "_bmad" / "bmm").mkdir(); (root / "_bmad" / "bmm" / "config.yaml").write_text("x")
        lc, w = classify_legacy_configs(root)
        assert lc["bmm_present"] and not lc["core_present"] and len(w) == 1 and "core" in w[0], (lc, w)
        (root / "_bmad" / "core").mkdir(); (root / "_bmad" / "core" / "config.yaml").write_text("x")
        assert classify_legacy_configs(root) == ({"bmm_present": True, "core_present": True}, [])
        tc, w = classify_tea_config(root)
        assert tc == {"present": False} and len(w) == 1 and "_bmad/tea/config.yaml missing" in w[0], (tc, w)
        (root / "_bmad" / "tea").mkdir(); (root / "_bmad" / "tea" / "config.yaml").write_text("x")
        assert classify_tea_config(root) == ({"present": True}, [])

        # agents_md: absent / present without block / open only / full block.
        assert classify_agents_md(root) == {"present": False, "has_context_block": False}
        (root / "AGENTS.md").write_text("# hi\n")
        assert classify_agents_md(root) == {"present": True, "has_context_block": False}
        (root / "AGENTS.md").write_text("<!-- bmad:context -->\nstuff\n")
        assert classify_agents_md(root)["has_context_block"] is False  # closing marker required
        (root / "AGENTS.md").write_text("x\n<!-- bmad:context -->\nstuff\n<!-- /bmad:context -->\n")
        assert classify_agents_md(root) == {"present": True, "has_context_block": True}

        # --- nesting: cli_phases exemption + inline tier (any host) ---
        n = classify_nesting("codex", "subagents", root, ["build", "followup_review"], {}, home)
        assert n["status"] == "ok" and n["detail"] == _MSG_CLI_EXEMPT and n["fix"] is None, n
        n = classify_nesting("codex", "subagents", root, ["followup_review", "build", "tea_epic"], {}, home)
        assert n["status"] == "ok" and n["detail"] == _MSG_CLI_EXEMPT, n
        # `build` alone does NOT exempt (codex with no config -> hard_stop).
        n = classify_nesting("codex", "subagents", root, ["build"], {}, home)
        assert n["status"] == "hard_stop", n
        n = classify_nesting("codex", "inline", root, [], {}, home)
        assert n["status"] == "ok" and n["detail"] == _MSG_INLINE and n["tier"] == "inline", n
        n = classify_nesting("claude-code", "inline", root, [], {_CLAUDE_DEPTH_ENV: "1"}, home)
        assert n["status"] == "ok", n
        n = classify_nesting("other", "subagents", root, [], {}, home)
        assert n["status"] == "warn" and n["detail"] == _MSG_UNKNOWN_HOST and n["fix"] is None, n

        # --- nesting: claude-code ---
        n = classify_nesting("claude-code", "subagents", root, [], {}, home)
        assert n["status"] == "ok" and "unset" in n["detail"] and n["sources"] == [f"env:{_CLAUDE_DEPTH_ENV}"], n
        for v in ("abc", "0", "-1", "1.5", ""):
            n = classify_nesting("claude-code", "subagents", root, [], {_CLAUDE_DEPTH_ENV: v}, home)
            assert n["status"] == "ok" and "ignored" in n["detail"], (v, n)
        for v in ("2", " 3 ", "+5"):
            n = classify_nesting("claude-code", "subagents", root, [], {_CLAUDE_DEPTH_ENV: v}, home)
            assert n["status"] == "ok" and "allows" in n["detail"], (v, n)
        n = classify_nesting("claude-code", "subagents", root, [], {_CLAUDE_DEPTH_ENV: "1"}, home)
        assert n["status"] == "hard_stop" and n["fix"] == _FIX_CLAUDE, n
        n = classify_nesting("claude-code", "subagents", root, [], {_CLAUDE_DEPTH_ENV: " 1 "}, home)
        assert n["status"] == "hard_stop", n

        # --- nesting: codex ---
        n = classify_nesting("codex", "subagents", root, [], {}, home)
        assert n["status"] == "hard_stop" and "absent" in n["detail"] and n["fix"] == _FIX_CODEX and n["sources"] == [], n
        (home / ".codex").mkdir()
        (home / ".codex" / "config.toml").write_text("[agents]\nmax_depth = 1\n", encoding="utf-8")
        n = classify_nesting("codex", "subagents", root, [], {}, home)
        assert n["status"] == "hard_stop" and "1" in n["detail"] and n["sources"] == [str(home / ".codex" / "config.toml")], n
        (home / ".codex" / "config.toml").write_text("[agents]\nmax_depth = 2\n", encoding="utf-8")
        n = classify_nesting("codex", "subagents", root, [], {}, home)
        assert n["status"] == "ok" and "max_depth = 2" in n["detail"] and n["fix"] is None, n
        # Project layer overrides the user layer key-by-key (max_depth back to 1 -> stop; then v2 rescues).
        (root / ".codex").mkdir()
        (root / ".codex" / "config.toml").write_text("[agents]\nmax_depth = 1\n", encoding="utf-8")
        n = classify_nesting("codex", "subagents", root, [], {}, home)
        assert n["status"] == "hard_stop" and len(n["sources"]) == 2, n
        (root / ".codex" / "config.toml").write_text("[features]\nmulti_agent_v2 = true\n", encoding="utf-8")
        n = classify_nesting("codex", "subagents", root, [], {}, home)
        assert n["status"] == "ok" and "multi_agent_v2" in n["detail"], n
        (root / ".codex" / "config.toml").write_text("[features]\nmulti_agent_v2 = false\n", encoding="utf-8")
        assert classify_nesting("codex", "subagents", root, [], {}, home)["status"] == "ok"  # user max_depth=2 still merged
        # A boolean/str max_depth is not an int >= 2.
        (root / ".codex" / "config.toml").write_text('[agents]\nmax_depth = "2"\n', encoding="utf-8")
        assert classify_nesting("codex", "subagents", root, [], {}, home)["status"] == "hard_stop"
        (root / ".codex" / "config.toml").write_text("[agents]\nmax_depth = true\n", encoding="utf-8")
        assert classify_nesting("codex", "subagents", root, [], {}, home)["status"] == "hard_stop"
        # Unparseable project file -> warn.
        (root / ".codex" / "config.toml").write_text("[agents\nmax_depth = 2\n", encoding="utf-8")
        n = classify_nesting("codex", "subagents", root, [], {}, home)
        assert n["status"] == "warn" and "could not parse" in n["detail"] and n["fix"] is None, n
        (root / ".codex" / "config.toml").unlink()
        # CODEX_HOME relocates the user config.
        alt = root / "alt-codex-home"; alt.mkdir()
        (alt / "config.toml").write_text("[agents]\nmax_depth = 3\n", encoding="utf-8")
        (home / ".codex" / "config.toml").write_text("[agents]\nmax_depth = 1\n", encoding="utf-8")
        n = classify_nesting("codex", "subagents", root, [], {"CODEX_HOME": str(alt)}, home)
        assert n["status"] == "ok" and n["sources"] == [str(alt / "config.toml")], n
        assert classify_nesting("codex", "subagents", root, [], {}, home)["status"] == "hard_stop"

        # --- nesting: opencode ---
        n = classify_nesting("opencode", "subagents", root, [], {}, home)
        assert n["status"] == "hard_stop" and "unset (default 1)" in n["detail"] and n["fix"] == _FIX_OPENCODE and n["sources"] == [], n
        oc_global = home / ".config" / "opencode"; oc_global.mkdir(parents=True)
        (oc_global / "opencode.json").write_text('{"subagent_depth": 1}', encoding="utf-8")
        n = classify_nesting("opencode", "subagents", root, [], {}, home)
        assert n["status"] == "hard_stop" and "1" in n["detail"] and n["sources"] == [str(oc_global / "opencode.json")], n
        # Project opencode.json (later layer) wins over global; task permission missing -> warn.
        (root / "opencode.json").write_text('{\n  // comment\n  "subagent_depth": 2, "$schema": "https://opencode.ai/config.json"\n}', encoding="utf-8")
        n = classify_nesting("opencode", "subagents", root, [], {}, home)
        assert n["status"] == "warn" and n["detail"] == _MSG_OPENCODE_TASK_WARN and n["fix"] == _FIX_OPENCODE, n
        assert n["sources"] == [str(oc_global / "opencode.json"), str(root / "opencode.json")], n
        # Task allow found in ANY layer (here the global one) -> ok.
        (oc_global / "opencode.json").write_text('{"subagent_depth": 1, "agent": {"general": {"permission": {"task": "allow"}}}}', encoding="utf-8")
        n = classify_nesting("opencode", "subagents", root, [], {}, home)
        assert n["status"] == "ok" and "subagent_depth = 2" in n["detail"], n
        # Glob-map form of permission.task also counts.
        (oc_global / "opencode.json").write_text('{"agent": {"general": {"permission": {"task": {"*": "allow"}}}}}', encoding="utf-8")
        assert classify_nesting("opencode", "subagents", root, [], {}, home)["status"] == "ok"
        (oc_global / "opencode.json").write_text('{"agent": {"general": {"permission": {"task": {"*": "deny"}}}}}', encoding="utf-8")
        assert classify_nesting("opencode", "subagents", root, [], {}, home)["status"] == "warn"
        # .opencode/opencode.json is the highest layer: setting depth 1 there -> hard_stop again.
        (root / ".opencode").mkdir()
        (root / ".opencode" / "opencode.json").write_text('{"subagent_depth": 1}', encoding="utf-8")
        n = classify_nesting("opencode", "subagents", root, [], {}, home)
        assert n["status"] == "hard_stop" and len(n["sources"]) == 3, n
        (root / ".opencode" / "opencode.json").unlink()
        # $OPENCODE_CONFIG layer sits between global and project.
        extra = root / "oc-extra.json"; extra.write_text('{"subagent_depth": 5}', encoding="utf-8")
        (root / "opencode.json").write_text('{"agent": {"general": {"permission": {"task": "allow"}}}}', encoding="utf-8")
        (oc_global / "opencode.json").write_text('{"subagent_depth": 1}', encoding="utf-8")
        n = classify_nesting("opencode", "subagents", root, [], {"OPENCODE_CONFIG": str(extra)}, home)
        assert n["status"] == "ok" and str(extra) in n["sources"], n
        assert classify_nesting("opencode", "subagents", root, [], {}, home)["status"] == "hard_stop"
        # A .jsonc sibling is read right after its .json.
        (root / "opencode.jsonc").write_text('{ "subagent_depth": 2 } // trailing', encoding="utf-8")
        n = classify_nesting("opencode", "subagents", root, [], {}, home)
        assert n["status"] == "ok" and n["sources"][-1] == str(root / "opencode.jsonc"), n
        (root / "opencode.jsonc").unlink()
        # Unparseable / non-object -> warn.
        (root / "opencode.json").write_text('{"subagent_depth": 2,,}', encoding="utf-8")
        n = classify_nesting("opencode", "subagents", root, [], {}, home)
        assert n["status"] == "warn" and "could not parse" in n["detail"] and n["fix"] is None, n
        (root / "opencode.json").write_text('[1, 2]', encoding="utf-8")
        assert "could not parse" in classify_nesting("opencode", "subagents", root, [], {}, home)["detail"]
        (root / "opencode.json").unlink()
        # Non-int depth (string / bool) is not ok.
        (oc_global / "opencode.json").write_text('{"subagent_depth": "2"}', encoding="utf-8")
        assert classify_nesting("opencode", "subagents", root, [], {}, home)["status"] == "hard_stop"
        (oc_global / "opencode.json").write_text('{"subagent_depth": true}', encoding="utf-8")
        assert classify_nesting("opencode", "subagents", root, [], {}, home)["status"] == "hard_stop"

        # ci: none -> .gitlab-ci.yml -> workflows yml/yaml.
        assert detect_ci(root) == {"workflows_present": False}
        (root / ".gitlab-ci.yml").write_text("stages: []\n")
        assert detect_ci(root)["workflows_present"] is True
        (root / ".gitlab-ci.yml").unlink()
        wf = root / ".github" / "workflows"; wf.mkdir(parents=True)
        (wf / "notes.txt").write_text("x")  # non-yaml doesn't count
        assert detect_ci(root)["workflows_present"] is False
        (wf / "release.yaml").write_text("on: push\n")
        assert detect_ci(root)["workflows_present"] is True

        # skills: present iff a dir of that name exists under ANY skills dir; sprint_plan_script first hit.
        d1 = root / ".claude" / "skills"; d2 = root / ".agents" / "skills"
        (d1 / "bmad-build-auto").mkdir(parents=True)
        (d2 / "bmad-sprint-planning" / "scripts").mkdir(parents=True)
        (d1 / "bmad-fake-file").write_text("not a dir")  # a FILE is not a skill
        s = check_skills(["bmad-build-auto", "bmad-sprint-planning", "bmad-retrospective", "bmad-fake-file"], [d1, d2])
        assert s["checked"] == ["bmad-build-auto", "bmad-sprint-planning", "bmad-retrospective", "bmad-fake-file"], s
        assert s["missing"] == ["bmad-retrospective", "bmad-fake-file"], s
        assert s["sprint_plan_script"] is None, s  # skill dir exists but no script (BMAD < 6.11 shape)
        (d2 / "bmad-sprint-planning" / "scripts" / "sprint_plan.py").write_text("# stub")
        s = check_skills([], [d1, d2])
        assert s == {"checked": [], "missing": [], "sprint_plan_script": str(d2 / "bmad-sprint-planning" / "scripts" / "sprint_plan.py")}, s
        (d1 / "bmad-sprint-planning" / "scripts").mkdir(parents=True)
        (d1 / "bmad-sprint-planning" / "scripts" / "sprint_plan.py").write_text("# stub")
        assert check_skills([], [d1, d2])["sprint_plan_script"].startswith(str(d1)), "first skills dir wins"
        assert check_skills([], [])["sprint_plan_script"] is None

        # framework: prefix configs + pytest markers, root-level only.
        fr = detect_framework(root, ci_present=True)
        assert fr == {"configs": [], "ci_present": True}, fr
        sub = root / "docs"; sub.mkdir()
        (root / "playwright.config.ts").write_text("x")
        (root / "vitest.config.mjs").write_text("x")
        (root / "pytest.ini").write_text("[pytest]\n")
        (root / "pyproject.toml").write_text("[tool.poetry]\nname='x'\n")  # no pytest table
        (root / "setup.cfg").write_text("[tool:pytest]\naddopts=-q\n")
        (sub / "jest.config.js").write_text("x")  # NOT at root -> ignored
        (root / "jest.config.js.bak").write_text("x")  # stale copy -> rejected
        (root / "playwright.config.ts.orig").write_text("x")  # stale copy -> rejected
        (root / "jest.config.e2e.js").write_text("x")  # multi-dot config -> counts
        fr = detect_framework(root, ci_present=False)
        assert fr["ci_present"] is False
        assert sorted(fr["configs"]) == [
            "jest.config.e2e.js", "playwright.config.ts", "pytest.ini", "setup.cfg", "vitest.config.mjs",
        ], fr
        (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
        assert "pyproject.toml" in detect_framework(root, False)["configs"]

        # --- full assembly with fake runner/which/env/home ---
        (d1 / "bmad-retrospective").mkdir()
        (root / "AGENTS.md").write_text("<!-- bmad:context -->\nx\n<!-- /bmad:context -->\n")
        (home / ".codex" / "config.toml").write_text("[agents]\nmax_depth = 2\n", encoding="utf-8")
        common = dict(run=_fake_runner(_ALL_OK), which=_fake_which(["uv", "claude", "codex"]), env={}, home=home)
        res = preflight(
            root, host="codex", tier="subagents",
            require_skills=["bmad-build-auto", "bmad-sprint-planning", "bmad-retrospective"],
            skills_dirs=[d1, d2], detect_framework_ci=True, tea_enabled=True, cross_model_tool="claude",
            **common,
        )
        assert set(res) == {
            "python", "central_config", "legacy_configs", "tea_config", "uv", "python311", "agents_md", "nesting",
            "cross_model", "git", "ci", "skills", "framework", "warnings", "hard_stop", "hard_stop_reasons",
        }, sorted(res)
        assert res["hard_stop"] is False and res["hard_stop_reasons"] == [], res["hard_stop_reasons"]
        assert res["warnings"] == [], res["warnings"]
        assert res["python"]["ok"] and res["central_config"]["output_folder"] == str(root / "_bmad-output")
        assert res["legacy_configs"] == {"bmm_present": True, "core_present": True} and res["tea_config"] == {"present": True}
        assert res["uv"]["on_path"] and res["python311"]["status"] == "ok"
        assert res["agents_md"] == {"present": True, "has_context_block": True}
        assert res["nesting"]["status"] == "ok" and res["nesting"]["host"] == "codex" and res["nesting"]["tier"] == "subagents"
        assert res["cross_model"] == {"tool": "claude", "binary": "claude", "binary_on_path": True}
        assert res["git"]["mode"] == "remote" and res["ci"]["workflows_present"] is True
        assert res["skills"]["missing"] == [] and res["skills"]["sprint_plan_script"].startswith(str(d1))
        assert res["framework"]["ci_present"] is True and "playwright.config.ts" in res["framework"]["configs"]
        json.dumps(res)

        # Every warn/hard-stop channel at once (still one JSON, ordered reasons).
        (root / "AGENTS.md").unlink()
        (root / "_bmad" / "tea" / "config.yaml").unlink()
        (root / "_bmad" / "core" / "config.yaml").unlink()
        res = preflight(
            root, host="opencode", tier="subagents",
            require_skills=["bmad-build-auto", "bmad-testarch-atdd"], skills_dirs=[d1, d2],
            tea_enabled=True, cross_model_tool="codex", cli_phases=["build"],
            run=_fake_runner({**_GIT_OK, **_UV_NO_PY}), which=_fake_which(["uv"]),
            env={"UV_PYTHON_DOWNLOADS": "never"}, home=home,
        )
        assert res["hard_stop"] is True, res
        reasons = res["hard_stop_reasons"]
        assert any("UV_PYTHON_DOWNLOADS=never" in x for x in reasons), reasons
        assert any(x.startswith("nested subagents unavailable on opencode:") and _FIX_OPENCODE in x for x in reasons), reasons
        assert any(x.startswith("code_review.cross_model_layer = codex but `codex` is not on PATH") for x in reasons), reasons
        assert any(x.startswith("required skill missing: bmad-testarch-atdd") for x in reasons), reasons
        assert res["framework"] is None and res["tea_config"] == {"present": False}
        w = res["warnings"]
        assert any("_bmad/core/config.yaml missing" in x for x in w) and not any("_bmad/bmm/config.yaml" in x for x in w), w
        assert any("_bmad/tea/config.yaml missing" in x for x in w) and _MSG_AGENTS_MD in w, w
        # uv missing -> P3 stop + python311 skipped (warn), never a duplicate python311 stop.
        res = preflight(root, host="claude-code", tier="inline", run=_fake_runner(_GIT_OK), which=_fake_which([]), env={"UV_PYTHON_DOWNLOADS": "never"}, home=home)
        assert _MSG_UV_MISSING in res["hard_stop_reasons"] and not any("uv python install" in x for x in res["hard_stop_reasons"]), res["hard_stop_reasons"]
        assert res["python311"]["status"] == "warn" and "python >=3.11 probe skipped (uv not on PATH)" in res["warnings"], res
        assert res["nesting"]["status"] == "ok" and res["nesting"]["detail"] == _MSG_INLINE
        assert res["cross_model"] == {"tool": None, "binary": None, "binary_on_path": None}
        # nesting hard_stop on claude-code surfaces the verbatim fix in the reason.
        res = preflight(root, host="claude-code", tier="subagents", run=_fake_runner(_ALL_OK), which=_fake_which(["uv"]), env={_CLAUDE_DEPTH_ENV: "1"}, home=home)
        assert any(x.startswith("nested subagents unavailable on claude-code:") and _FIX_CLAUDE in x for x in res["hard_stop_reasons"]), res
        # ...and the cli_phases exemption clears it even with the bad env.
        res = preflight(root, host="claude-code", tier="subagents", cli_phases=["build", "followup_review"], run=_fake_runner(_ALL_OK), which=_fake_which(["uv"]), env={_CLAUDE_DEPTH_ENV: "1"}, home=home)
        assert res["nesting"]["status"] == "ok" and res["hard_stop"] is False, res
        # nesting warn (other host) lands in warnings, not reasons.
        res = preflight(root, host="other", tier="subagents", run=_fake_runner(_ALL_OK), which=_fake_which(["uv"]), env={}, home=home)
        assert res["hard_stop"] is False and f"nesting: {_MSG_UNKNOWN_HOST}" in res["warnings"], res
        # No --skills-dirs: skills block empty, sprint_plan_script null, no stop for it.
        assert res["skills"] == {"checked": [], "missing": [], "sprint_plan_script": None}, res["skills"]

        # --- --central-config-only: null blocks + limited hard-stops ---
        res = preflight(root, central_config_only=True, run=_fake_runner({}), which=_fake_which([]), env={}, home=home)
        assert res["python"]["ok"] and res["central_config"]["present"], res
        for k in _NULL_BLOCKS:
            assert res[k] is None, (k, res[k])
        assert res["warnings"] == [] and res["hard_stop"] is False and res["hard_stop_reasons"] == [], res
        assert set(res) == {"python", "central_config", *_NULL_BLOCKS, "warnings", "hard_stop", "hard_stop_reasons"}
        (root / "_bmad" / "config.toml").unlink()
        res = preflight(root, central_config_only=True, run=_fake_runner({}), which=_fake_which([]), env={}, home=home)
        assert res["hard_stop"] is True and res["hard_stop_reasons"] == [_MSG_NOT_BMAD], res
        assert res["git"] is None and res["nesting"] is None
        # Full mode on a non-BMAD dir also stops (P1) — and still probes the rest.
        res = preflight(root, host="other", tier="inline", run=_fake_runner(_ALL_OK), which=_fake_which(["uv"]), env={}, home=home)
        assert _MSG_NOT_BMAD in res["hard_stop_reasons"] and res["git"] is not None, res
        _write_bmad_project(root, layers=False)

        # --- CLI wiring via subprocess: usage errors (exit 2) + central-config-only (exit 0/1) ---
        me = str(Path(__file__).resolve())
        def cli(*a: str) -> tuple[int, dict]:
            p = subprocess.run([sys.executable, me, *a], capture_output=True, text=True, timeout=60)
            return p.returncode, json.loads(p.stdout)
        rc, out = cli("--central-config-only")
        assert rc == 2 and out["status"] == "error" and "project_root" in out["message"], out
        rc, out = cli("--project-root", str(root / "nope"), "--central-config-only")
        assert rc == 2 and "not a directory" in out["message"], out
        rc, out = cli("--project-root", str(root))
        assert rc == 2 and "--host" in out["message"], out
        rc, out = cli("--project-root", str(root), "--host", "codex", "--tier", "subagents", "--require-skills", "bmad-build-auto")
        assert rc == 2 and "--skills-dirs" in out["message"], out
        rc, out = cli("--project-root", str(root), "--host", "codex", "--tier", "subagents", "--central-config-only")
        assert rc == 2 and "central-config-only" in out["message"], out
        rc, out = cli("--project-root", str(root), "--host", "vscode", "--tier", "subagents")
        assert rc == 2, out
        rc, out = cli("--project-root", str(root), "--central-config-only")
        assert rc == 0 and out["central_config"]["output_folder"] == str(root / "_bmad-output") and out["git"] is None, out
        (root / "_bmad" / "config.toml").unlink()
        rc, out = cli("--project-root", str(root), "--central-config-only")
        assert rc == 1 and out["hard_stop_reasons"] == [_MSG_NOT_BMAD], out
        _write_bmad_project(root, layers=False)

    # --- real end-to-end: temp git repo via the real subprocess runner (git/gh real; uv faked) ---
    with tempfile.TemporaryDirectory() as td:
        root = Path(td).resolve()
        home = root / "HOME"; home.mkdir()
        _write_bmad_project(root, layers=False)
        rc, _, err = real_runner(["git", "init", "-b", "main"], cwd=str(root))
        assert rc == 0, err
        for k, v in (("user.email", "t@t.t"), ("user.name", "t")):
            real_runner(["git", "config", k, v], cwd=str(root))
        (root / "a.txt").write_text("x")
        uv_fake = _fake_runner(_UV_OK)
        def run(argv: Sequence[str]) -> tuple[int, str, str]:
            return uv_fake(argv) if argv[0] == "uv" else real_runner(argv, cwd=str(root))
        common = dict(host="claude-code", tier="subagents", run=run, which=_fake_which(["uv"]), env={}, home=home)
        # Dirty (untracked a.txt + _bmad/), no remote -> hard stop, mode local, base=current=main.
        res = preflight(root, **common)
        assert res["git"]["is_repo"] and res["git"]["current_branch"] == "main", res
        assert res["git"]["base_branch"] == "main" and res["git"]["github_remote"] is False, res
        assert res["git"]["mode"] == "local", res
        assert not res["git"]["tree_clean"] and res["git"]["dirty_files_count"] == 2, res
        assert res["hard_stop"] and any("dirty" in x for x in res["hard_stop_reasons"]), res
        # Same dirt, but it IS the expected branch -> resume case, no stop.
        res = preflight(root, expected_branch="main", **common)
        assert res["hard_stop"] is False, res["hard_stop_reasons"]
        # Commit -> clean -> no stop; only the AGENTS.md advisory remains.
        real_runner(["git", "add", "."], cwd=str(root))
        rc, _, err = real_runner(["git", "commit", "-m", "init", "--no-gpg-sign"], cwd=str(root))
        assert rc == 0, err
        res = preflight(root, **common)
        assert res["git"]["tree_clean"] and res["hard_stop"] is False, res
        assert _MSG_AGENTS_MD in res["warnings"], res["warnings"]
        json.dumps(res)

    print("SELF-TEST PASSED (all assertions)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-call Phase 0 preflight: python/uv, central TOML config, nesting, git, AGENTS.md, CI, skills, framework."
    )
    parser.add_argument("--self-test", action="store_true", help="Run internal tests and exit.")
    parser.add_argument("--project-root", help="Project root (cwd for git probes; walk root; holds _bmad/).")
    parser.add_argument("--central-config-only", action="store_true",
                        help="Probe ONLY python + the central TOML config (SKILL Step 0 bootstrap read); every other block is null.")
    parser.add_argument("--host", help="Detected host: claude-code|codex|opencode|other (required unless --central-config-only).")
    parser.add_argument("--tier", help="Delegation tier in use: subagents|inline (required unless --central-config-only).")
    parser.add_argument("--expected-branch", help="The story branch a dirty tree is allowed on (resume case).")
    parser.add_argument("--require-skills", default="", help="CSV of required skill dir names; any miss is a hard stop.")
    parser.add_argument("--skills-dirs", default="", help="CSV of skills dirs to search (host-appropriate, orchestrator-supplied).")
    parser.add_argument("--detect-framework-ci", action="store_true", help="Also detect test-framework configs (first-run step 2); else framework is null.")
    parser.add_argument("--tea-enabled", action="store_true", help="Also probe _bmad/tea/config.yaml (warn only); else tea_config is null.")
    parser.add_argument("--cross-model-tool", help="code_review.cross_model_layer value (codex|claude|opencode); its binary must be on PATH.")
    parser.add_argument("--cli-phases", default="", help="CSV of delegation.cli_phases keys (both build and followup_review ⇒ nesting exempt).")
    args = parser.parse_args()

    if args.self_test:
        return _run_self_test()

    def usage_error(msg: str) -> int:
        print(json.dumps({"status": "error", "message": msg}))
        return 2

    if not args.project_root:
        return usage_error("missing required: ['project_root']")
    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        return usage_error(f"project root not a directory: {project_root}")

    if args.central_config_only:
        extras = [
            n for n in ("host", "tier", "expected_branch", "require_skills", "skills_dirs", "cross_model_tool", "cli_phases")
            if getattr(args, n)
        ] + [n for n in ("detect_framework_ci", "tea_enabled") if getattr(args, n)]
        if extras:
            return usage_error(f"--central-config-only takes no other probe options (got: {extras})")
        result = preflight(project_root, central_config_only=True)
        print(json.dumps(result, indent=2))
        return 1 if result["hard_stop"] else 0

    if not args.host or not args.tier:
        return usage_error("missing required: --host and --tier (or use --central-config-only)")
    if args.host not in _HOSTS:
        return usage_error(f"--host must be one of {list(_HOSTS)}, got {args.host!r}")
    if args.tier not in _TIERS:
        return usage_error(f"--tier must be one of {list(_TIERS)}, got {args.tier!r}")
    if args.cross_model_tool and args.cross_model_tool not in _CROSS_MODEL_TOOLS:
        return usage_error(f"--cross-model-tool must be one of {list(_CROSS_MODEL_TOOLS)}, got {args.cross_model_tool!r}")
    require_skills = [s.strip() for s in args.require_skills.split(",") if s.strip()]
    skills_dirs = [Path(s.strip()).expanduser() for s in args.skills_dirs.split(",") if s.strip()]
    if require_skills and not skills_dirs:
        return usage_error("--require-skills given without --skills-dirs")
    cli_phases = [s.strip() for s in args.cli_phases.split(",") if s.strip()]

    result = preflight(
        project_root,
        host=args.host,
        tier=args.tier,
        expected_branch=args.expected_branch,
        require_skills=require_skills,
        skills_dirs=skills_dirs,
        detect_framework_ci=args.detect_framework_ci,
        tea_enabled=args.tea_enabled,
        cross_model_tool=args.cross_model_tool or None,
        cli_phases=cli_phases,
    )
    print(json.dumps(result, indent=2))
    return 1 if result["hard_stop"] else 0


if __name__ == "__main__":
    sys.exit(main())
