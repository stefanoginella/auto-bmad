#!/usr/bin/env python3
"""Resolve an external-CLI delegation for one auto-bmad pipeline phase.

Most auto-bmad steps run in an *in-tool* sub-agent (the three tiers in
``delegation-runtime.md``). As an **opt-in, per-phase** alternative, a phase can
instead be delegated to an **external CLI** — ``claude -p``, ``codex exec`` or
``opencode run`` — chosen by the ``delegation.cli_phases`` map in the runtime config::

    delegation:
      cli_phases:
        code_review_review_secondary: codex      # run this phase on `codex exec`
        retrospective: opencode                  # ...or on `opencode run` (any provider/model)

The value names the *tool* (``claude`` | ``codex`` | ``opencode``); model + effort come
from that tool's block of the phase's profile (``phase_profiles[phase]`` ->
``profiles[<profile>][<tool>]``), exactly the same values ``render-agents.py``
bakes into the in-tool delegate files. opencode is the exception: its ``model`` and
reasoning ``variant`` are BOTH optional (blank => inherit the user's opencode defaults).
Nothing here changes the profiles or the three existing tiers — a phase absent from
``cli_phases`` is reported ``routed: false`` and the orchestrator uses its normal tier.

This script does three things and prints ONE JSON object on stdout:

  * ``resolve()`` — PURE (no subprocess, no filesystem): from the config text it
    builds the tool, model, effort, the **argv** (without the prompt), the ``cwd``,
    an OS-temp **capture-log** path (NEVER inside the repo, so transient stdout can't
    be swept into a commit/PR), how the prompt is delivered (``prompt_via``:
    claude/codex pipe it to **stdin**; opencode does NOT read stdin, so the prompt is
    appended as the final positional **arg**), and how to read the structured result
    back (claude: parse ``.result`` from the JSON envelope; codex: read the ``-o``
    last-message file; opencode: ``extract_opencode_result()`` on the captured
    ``--format json`` event stream). It also emits the exact **``launch_cmd``** (a
    ``bash -c`` body: ``cd`` into the repo, deliver the prompt from ``prompt_file``,
    redirect stdout+stderr to ``capture_log``, then write ``$?`` to ``exit_file`` as a
    completion **sentinel**) — so the orchestrator never hand-rolls a redirect/sentinel
    that breaks under a non-bash host shell (zsh/fish). The per-tool divergence lives
    here, in tested code, not in orchestrator prose.
  * ``observe_once()`` / ``wait_for_delegate()`` (``--once`` / ``--wait``) — watch a
    DETACHED delegate to completion. **Process exit is the completion signal and total
    runtime is UNBOUNDED** (a ``dev_story`` / lens can run hours — never killed on a
    clock). Completion = the ``exit_file`` sentinel lands. The only wedge triggers are a
    crash (``--pid`` gone with no sentinel) and — **only when no ``--pid`` is given** —
    an idle backstop (``capture_log`` silent past ``--idle-timeout``: a *no-new-output*
    allowance, NOT a runtime cap). With a ``--pid`` a live process is never idle-wedged
    (``claude -p`` emits nothing until its final envelope, so log-silence ≠ liveness).
    ``--once`` classifies in a single shot (for a host that re-invokes the orchestrator
    when a background task exits — background the delegate, classify on wake); ``--wait``
    blocks in a poll loop and so MUST itself be launched backgrounded (a foreground wait
    hits the host's own ~10-min shell cap).
  * ``validate()`` — LIVE checks the orchestrator must pass before relying on a
    routed phase (it hard-stops up front, never mid-pipeline): the CLI binary is
    on PATH, that tool's BMAD skills are installed, and — for the *non-host* tool
    (the host the orchestrator runs in is authed by definition) — the CLI is
    actually logged in (``claude auth status`` / ``codex login status``; opencode
    is LENIENT — it supports keyless/local/config providers, so a clean
    ``opencode auth list`` exit passes and "0 credentials" never hard-stops).

Command shapes are spike-confirmed (see the plan / delegation-runtime.md):
  claude:   claude -p --model M --effort E --output-format json --dangerously-skip-permissions
  codex:    codex exec -m M -c model_reasoning_effort=E --dangerously-bypass-approvals-and-sandbox -C ROOT -o LASTMSG --ephemeral
  opencode: opencode run [-m M] [--variant V] --format json --dir ROOT --dangerously-skip-permissions <prompt-arg>

Usage:
    cli_delegate.py --phase PHASE --config FILE --project-root DIR \\
        [--story-key KEY] [--host claude-code|codex|opencode] [--no-auth-probe]
    cli_delegate.py --once --capture-log LOG [--exit-file F] [--pid N]
    cli_delegate.py --wait --capture-log LOG [--exit-file F] [--pid N] \\
        [--idle-timeout S] [--poll-interval S] [--max-wait S]   # MUST be backgrounded
    cli_delegate.py --self-test

Exit codes (resolve/validate): 0 = routed and all validations passed (or
routed:false, a clean "use the normal tier" answer); 1 = routed but a validation
failed (hard-stop); 2 = usage / resolution error (bad config, unknown phase,
missing profile block).
Exit codes (--once / --wait): 0 = the delegate exited (status ``exited`` — read
``result_source`` and apply the normal result-block check); 1 = a non-``exited``
verdict (``dead-no-sentinel`` / ``wedged-idle`` / ``max-wait`` = failed delegation
hard-stop; or ``running`` from ``--once`` = not done yet).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Sequence

# Phases that may be routed: the same keys as phase_profiles. (Git/finalize work
# is orchestrator-owned and never delegated, so it is not routable.)
TOOL_BINARY = {"claude": "claude", "codex": "codex", "opencode": "opencode"}
# host (delegation.host) <-> the tool name it IS, so we can skip the auth probe
# for the host the orchestrator already runs inside.
_HOST_TOOL = {"claude-code": "claude", "codex": "codex", "opencode": "opencode"}
_AUTH_PROBE_TIMEOUT = 20  # seconds — keep short so a wedged probe can't hang preflight
# Hard wall-clock cap for a single REVIEW delegate (a lens or the triage), applied in the launch_cmd
# via `timeout`. Bounds the opencode/GLM tool-stream wedge (observed: 20+ min CPU, 0 output, never
# terminates). Generous vs a real review pass (minutes) but finite. NOT applied to non-review phases
# (dev_story legitimately runs hours). See resolve() + _build_launch_cmd.
_REVIEW_DELEGATE_TIMEOUT_SECS = 1200  # 20 min
# opencode CLI surface (flags/dirs) AND the `run --format json` event schema are verified against
# this version: extract_opencode_result() targets the verified shape (top-level type=="text" events,
# part.text concatenated) with defensive fallbacks for any future schema drift.
_OPENCODE_CLI_VERSION = "1.16.2"


# --- dependency-free YAML-ish parsing (same style as config_plan.py / render-agents.py) ---

def _strip_comment(s: str) -> str:
    """Drop a trailing ` # comment` (must be preceded by whitespace)."""
    m = re.search(r"\s+#", s)
    if m:
        s = s[: m.start()]
    return s.rstrip()


def _strip_value(val: str) -> str:
    """Strip an inline trailing comment and surrounding quotes from a scalar."""
    val = _strip_comment(val).strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
        val = val[1:-1]
    return val.strip()


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _is_blank_or_comment(line: str) -> bool:
    s = line.strip()
    return (not s) or s.startswith("#")


def find_block(lines: Sequence[str], name: str) -> tuple[int, int] | None:
    """Locate a top-level ``name:`` block -> ``(header_idx, body_end)`` or None."""
    header: int | None = None
    for i, line in enumerate(lines):
        if _is_blank_or_comment(line):
            continue
        ind = _indent(line)
        stripped = _strip_comment(line.strip())
        if header is None:
            if ind == 0 and stripped == f"{name}:":
                header = i
            continue
        if ind == 0:
            return (header, i)
    return (header, len(lines)) if header is not None else None


def _parse_inline_map(body: str) -> dict:
    """Parse ``k: v, k2: v2`` (inside of a flow map) into a dict."""
    out: dict = {}
    for part in body.split(","):
        if ":" in part:
            k, _, v = part.partition(":")
            if k.strip():
                out[k.strip()] = _strip_value(v)
    return out


def parse_phase_profiles(lines: Sequence[str]) -> dict:
    """Parse the top-level ``phase_profiles:`` ``key: value`` map (indent 2)."""
    span = find_block(lines, "phase_profiles")
    out: dict = {}
    if span is None:
        return out
    header, end = span
    for i in range(header + 1, end):
        line = lines[i]
        if _is_blank_or_comment(line) or _indent(line) != 2:
            continue
        stripped = _strip_comment(line.strip())
        if ":" in stripped:
            k, _, v = stripped.partition(":")
            out[k.strip()] = _strip_value(v)
    return out


def parse_profiles(text: str) -> dict:
    """Extract the ``profiles:`` block (block or inline tool maps), dependency-free.

    Returns ``{profile: {scalar_key: value | tool: {key: value}}}``. Other
    top-level keys are ignored. Mirrors ``render-agents.py``'s parser so the two
    read the shipped/config profiles identically.
    """
    profiles: dict = {}
    in_block = False
    cur_profile: str | None = None
    cur_tool: str | None = None
    inline_re = re.compile(r"^([\w-]+):\s*\{(.*)\}\s*$")

    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = _indent(raw)
        stripped = _strip_comment(raw.strip())
        if not in_block:
            if indent == 0 and stripped == "profiles:":
                in_block = True
            continue
        if indent == 0:
            break
        if indent == 2 and stripped.endswith(":"):
            cur_profile = stripped[:-1].strip()
            profiles[cur_profile] = {}
            cur_tool = None
        elif indent == 4 and cur_profile is not None:
            m = inline_re.match(stripped)
            if m:
                profiles[cur_profile][m.group(1).strip()] = _parse_inline_map(m.group(2))
                cur_tool = None
            elif stripped.endswith(":"):
                cur_tool = stripped[:-1].strip()
                profiles[cur_profile][cur_tool] = {}
            elif ":" in stripped:
                key, _, val = stripped.partition(":")
                profiles[cur_profile][key.strip()] = _strip_value(val)
                cur_tool = None
        elif indent >= 6 and ":" in stripped and cur_profile is not None and cur_tool is not None:
            key, _, val = stripped.partition(":")
            profiles[cur_profile][cur_tool][key.strip()] = _strip_value(val)
    return profiles


def parse_cli_phases(lines: Sequence[str]) -> dict:
    """Parse ``delegation.cli_phases`` -> ``{phase: tool}`` (absent/empty => {}).

    Supports the block form::

        delegation:
          cli_phases:
            dev_story: codex

    and the inline form ``cli_phases: { dev_story: codex }`` / ``cli_phases: {}``.
    """
    span = find_block(lines, "delegation")
    if span is None:
        return {}
    header, end = span
    for i in range(header + 1, end):
        line = lines[i]
        if _is_blank_or_comment(line) or _indent(line) != 2:
            continue
        stripped = _strip_comment(line.strip())
        if not (stripped == "cli_phases:" or stripped.startswith("cli_phases:")):
            continue
        # Found the cli_phases key at indent 2.
        _, _, rest = stripped.partition(":")
        rest = rest.strip()
        if rest.startswith("{"):  # inline flow map (possibly empty `{}`)
            inner = rest.strip()[1:-1] if rest.endswith("}") else rest.strip()[1:]
            return _parse_inline_map(inner)
        # Block form: collect indent-4 `phase: tool` lines until the next
        # indent<=2 key (still inside the delegation block).
        out: dict = {}
        for j in range(i + 1, end):
            sub = lines[j]
            if _is_blank_or_comment(sub):
                continue
            if _indent(sub) <= 2:
                break
            if _indent(sub) == 4 and ":" in sub:
                k, _, v = _strip_comment(sub.strip()).partition(":")
                if k.strip():
                    out[k.strip()] = _strip_value(v)
        return out
    return {}


# --- resolution (PURE: no subprocess, no filesystem) ---

def _safe_name(s: str) -> str:
    """Filesystem-safe token for a capture filename."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", s) or "x"


def _capture_dir() -> Path:
    """OS temp dir for capture logs — NEVER inside the repo."""
    return Path(tempfile.gettempdir()) / "auto-bmad-cli"


def resolve(
    phase: str,
    config_text: str,
    project_root: str,
    story_key: str = "story",
    label: str | None = None,
) -> dict:
    """Build the external-CLI plan for ``phase`` from the config text. Pure.

    Returns ``{"routed": False, ...}`` when the phase is not in
    ``delegation.cli_phases`` (the orchestrator then uses the normal tier), or a
    full plan dict (tool/model/effort/argv/cwd/capture/result-source) when it is.
    On a resolution error (unknown phase, bad tool, missing profile block) the
    dict carries a non-empty ``errors`` list and ``routed`` reflects the intent.
    """
    lines = config_text.splitlines()
    cli_phases = parse_cli_phases(lines)
    if phase not in cli_phases:
        return {"routed": False, "phase": phase}

    errors: list[str] = []
    tool_raw = cli_phases[phase].strip()
    tool = "claude" if tool_raw == "claude-code" else tool_raw
    if tool not in TOOL_BINARY:
        errors.append(f"cli_phases[{phase}] = {tool_raw!r}; expected 'claude', 'codex' or 'opencode'")

    phase_profiles = parse_phase_profiles(lines)
    profile = phase_profiles.get(phase)
    if not profile:
        errors.append(f"no phase_profiles mapping for '{phase}'")

    profiles = parse_profiles(config_text)
    model = effort = None
    if profile and tool in TOOL_BINARY:
        prof = profiles.get(profile)
        if not prof:
            errors.append(f"profile '{profile}' not found in profiles block")
        else:
            tool_block = prof.get(tool)
            if not tool_block:
                errors.append(f"profile '{profile}' has no '{tool}' block")
            elif tool == "opencode":
                # opencode is MULTI-PROVIDER and MODEL-ONLY: both the model and the reasoning
                # `variant` are OPTIONAL. A blank model => the routed `opencode run` inherits the
                # user's opencode default model; a blank variant => the model's default reasoning.
                # So — unlike claude/codex — a missing value is NOT an error here.
                model = tool_block.get("model") or None
                effort = tool_block.get("variant") or None  # opencode's `--variant` knob
            else:
                model = tool_block.get("model")
                # claude uses `effort`; codex uses `reasoning_effort`.
                effort_key = "effort" if tool == "claude" else "reasoning_effort"
                effort = tool_block.get(effort_key)
                if not model:
                    errors.append(f"profile '{profile}.{tool}.model' missing")
                if not effort:
                    errors.append(f"profile '{profile}.{tool}.{effort_key}' missing")

    root = str(Path(project_root))
    cap_dir = _capture_dir()
    # `label` keeps capture paths distinct when one phase spawns several delegates
    # (the code-review fan-out: 3 lenses + triage all share phase + story_key).
    base = f"{_safe_name(story_key)}-{_safe_name(phase)}"
    if label:
        base += f"-{_safe_name(label)}"
    capture_log = str(cap_dir / f"{base}.log")
    # The orchestrator writes the assembled prompt to `prompt_file` (also OUTSIDE the repo) and the
    # detached child writes its exit status to `exit_file` as the completion sentinel — both consumed
    # by `launch_cmd` (built below) and by `--wait`/`--once`.
    exit_file = str(cap_dir / f"{base}.exit")
    prompt_file = str(cap_dir / f"{base}.prompt")

    plan: dict = {
        "routed": True,
        "phase": phase,
        "tool": tool,
        "profile": profile,
        "model": model,
        "effort": effort,
        "cwd": root,
        "prompt_via": "stdin",
        "capture_log": capture_log,
        "exit_file": exit_file,
        "prompt_file": prompt_file,
        "errors": errors,
    }

    if errors:
        plan["ok"] = False
        return plan

    if tool == "claude":
        plan["argv"] = [
            "claude", "-p",
            "--model", model,
            "--effort", effort,
            "--output-format", "json",
            "--dangerously-skip-permissions",
        ]
        # The JSON envelope lands in capture_log; the structured block is `.result`.
        plan["result_source"] = capture_log
        plan["result_format"] = "json"
        plan["result_field"] = "result"
        plan["error_field"] = "is_error"
    elif tool == "codex":
        last_msg = str(cap_dir / f"{base}.lastmsg")
        plan["argv"] = [
            "codex", "exec",
            "-m", model,
            "-c", f"model_reasoning_effort={effort}",
            # Full bypass: no inner OS sandbox, no approval prompts — parity with the claude/opencode
            # delegates' --dangerously-skip-permissions, and REQUIRED in a nested container, where
            # codex's workspace-write sandbox spawns bubblewrap and can't create a namespace.
            "--dangerously-bypass-approvals-and-sandbox",
            "-C", root,
            "-o", last_msg,
            "--ephemeral",
        ]
        # `-o` writes ONLY the agent's final message — the clean structured block.
        plan["result_source"] = last_msg
        plan["result_format"] = "text"
        plan["result_field"] = None
        plan["error_field"] = None
    else:  # opencode
        # opencode run does NOT read the prompt from stdin (verified) — the orchestrator appends the
        # assembled prompt as the final positional `message` arg (prompt_via="arg"). `--dir` pins the
        # working tree, so no `cd` is needed (unlike `claude -p`). `--variant` is opencode's
        # provider-specific reasoning-effort knob; BOTH `-m` and `--variant` are omitted when blank,
        # so the run falls back to the user's opencode default model / the model's default reasoning.
        argv = ["opencode", "run"]
        if model:
            argv += ["-m", model]
        if effort:
            argv += ["--variant", effort]
        argv += ["--format", "json", "--dir", root, "--dangerously-skip-permissions"]
        plan["argv"] = argv
        plan["prompt_via"] = "arg"
        # `--format json` streams newline-delimited JSON events to stdout (capture_log). The event
        # schema is undocumented/version-specific, so the orchestrator extracts the final message via
        # extract_opencode_result() rather than a fixed field — result_field/error_field are None and
        # an empty/unparseable extraction IS the failure signal.
        plan["result_source"] = capture_log
        plan["result_format"] = "opencode-json"
        plan["result_field"] = None
        plan["error_field"] = None

    # Hard wall-clock cap for REVIEW delegates only (lenses/triage): bounds the opencode/GLM
    # tool-stream wedge (observed 20+ min, 0 output). dev_story and other long phases get no cap
    # (timeout_secs=0) — they legitimately run hours. See _build_launch_cmd.
    timeout_secs = _REVIEW_DELEGATE_TIMEOUT_SECS if phase.startswith("code_review_review") else 0
    plan["timeout_secs"] = timeout_secs
    plan["launch_cmd"] = _build_launch_cmd(
        plan["argv"], root, capture_log, exit_file, prompt_file, plan["prompt_via"], timeout_secs
    )
    return plan


def _build_launch_cmd(
    argv: Sequence[str],
    cwd: str,
    capture_log: str,
    exit_file: str,
    prompt_file: str,
    prompt_via: str,
    timeout_secs: int = 0,
) -> str:
    """The exact ``bash -c`` body the orchestrator backgrounds for a routed delegate.

    It ``cd``s into the repo, runs the delegate delivering the prompt from ``prompt_file``
    (stdin for claude/codex; final positional arg for opencode), redirects stdout+stderr to
    ``capture_log``, then writes the child's exit status to ``exit_file`` — the completion
    sentinel ``--wait``/``--once`` watch for. Emitted HERE, in tested code (every token
    ``shlex.quote``d), so the sentinel mechanism never rides the host's interactive shell:
    ``( … ) & pid=$!`` / ``$?`` are bash/zsh-isms that break under fish, so the orchestrator
    just runs ``bash -c "$launch_cmd"`` (backgrounded) regardless of host shell.
    """
    q = shlex.quote
    cmd = " ".join(q(a) for a in argv)
    # Optional hard wall-clock cap. Only set for review delegates (see resolve()) — a wedged
    # opencode/GLM tool-stream otherwise hangs forever (observed: 20+ min, 0 output). NOT set for
    # dev_story etc., which legitimately run hours. `timeout -k 30` SIGKILLs 30s after SIGTERM if
    # the child ignores TERM; the brace-group's `echo $?` then records 124 (timeout) as the
    # delegate's exit status, which the waiter surfaces as a failed delegation.
    runner = f"timeout -k 30 {int(timeout_secs)} {cmd}" if timeout_secs and timeout_secs > 0 else cmd
    if prompt_via == "arg":
        # opencode: the prompt is the final positional `message` arg (it does NOT read stdin).
        inner = f"cd {q(cwd)} && {runner} \"$(cat {q(prompt_file)})\""
    else:
        # claude/codex: the prompt is piped on stdin.
        inner = f"cd {q(cwd)} && {runner} < {q(prompt_file)}"
    # `echo $?` captures the brace-group's status (the delegate's), AFTER its redirect closes.
    return f"{{ {inner} ; }} > {q(capture_log)} 2>&1 ; echo $? > {q(exit_file)}"


# --- opencode result extraction (defensive; the JSON event schema is undocumented) ---

def _collect_opencode_text(node, acc: list) -> None:
    """Recursively gather candidate assistant-text strings from an opencode JSON event/object.

    Heuristic — the ``opencode run --format json`` event schema is version-specific and
    undocumented, so we don't assert a shape: we collect the string value of any ``"text"`` key
    and any string-valued ``"content"`` key, anywhere in the tree. The caller takes the LAST
    non-empty result as the final assistant message (a user/echoed message sorts first; the
    assistant's final answer sorts last), and hard-stops if there is none.
    """
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("text", "content") and isinstance(v, str):
                acc.append(v)
            else:
                _collect_opencode_text(v, acc)
    elif isinstance(node, list):
        for item in node:
            _collect_opencode_text(item, acc)


def extract_opencode_result(raw: str) -> tuple[str | None, str | None]:
    """Pull the final assistant message out of ``opencode run`` output. Returns ``(message, error)``.

    Schema-aware, verified against opencode 1.16.2 ``run --format json``: the output is newline-
    delimited JSON events (JSONL); the assistant's reply arrives as events with top-level
    ``type == "text"`` whose ``part.text`` holds a COMPLETE text segment (``part.time.start/end``
    mark it done — it is NOT a streamed delta). A multi-part / multi-step reply yields several such
    events; we concatenate their ``part.text`` in order to reconstruct the full message. Non-text
    events (``step_start`` / ``step_finish`` / tool calls) are ignored.

    Degrades gracefully: if no ``type:"text"`` event is found (a future schema shift, or a single
    whole-JSON value) it falls back to collecting any ``text``/``content`` leaf; if the output isn't
    JSON at all it treats the whole capture as plain text (the ``default`` format). ``message`` is
    ``None`` only when nothing usable could be extracted — the orchestrator then hard-stops the
    routed phase (the same way a claude ``is_error`` / empty ``.result`` is treated), rather than
    silently delegating an empty result.
    """
    if not raw or not raw.strip():
        return None, "empty opencode output (the routed `opencode run` produced nothing)"

    # Parse the JSONL event stream (one JSON object per line). Non-JSON lines are ignored.
    events: list = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except (ValueError, TypeError):
            continue

    if not events:
        # Not JSONL: try the whole capture as one JSON value; else it's `default` plain text.
        try:
            whole = json.loads(raw)
        except (ValueError, TypeError):
            return raw.strip(), None
        events = whole if isinstance(whole, list) else [whole]

    # Primary (verified schema): assistant text = part.text of every top-level type=="text" event,
    # concatenated in order.
    parts = [
        e["part"]["text"]
        for e in events
        if isinstance(e, dict) and e.get("type") == "text"
        and isinstance(e.get("part"), dict) and isinstance(e["part"].get("text"), str)
    ]
    msg = "".join(parts).strip()
    if msg:
        return msg, None

    # Fallback (schema drift): collect any text/content leaf anywhere; last non-empty wins.
    acc: list = []
    for e in events:
        _collect_opencode_text(e, acc)
    acc = [t.strip() for t in acc if isinstance(t, str) and t.strip()]
    if acc:
        return acc[-1], None

    return None, (
        "could not extract a final assistant message from opencode's JSON output — the event "
        f"format may differ from what this parser expects (verified against opencode "
        f"{_OPENCODE_CLI_VERSION}); re-run this phase in-tool or update extract_opencode_result()"
    )


# --- live validation (subprocess + filesystem) ---

def _skills_dirs(tool: str, project_root: Path) -> list[Path]:
    if tool == "claude":
        return [project_root / ".claude" / "skills"]
    if tool == "opencode":
        # opencode loads skills (Anthropic SKILL.md standard) from `skills/*/SKILL.md` under the
        # project's `.opencode/` or the user-global config dir (note: plural `skills`, unlike the
        # singular `agent/` dir). Some BMAD opencode installs instead expose the skills as
        # slash-command files (`command*/bmad-*.md`) — a working route, so accept that layout too
        # (docs use singular `command/`; real installs have been seen with plural `commands/`).
        return [
            project_root / ".opencode" / "skills",
            Path.home() / ".config" / "opencode" / "skills",
            project_root / ".opencode" / "command",
            project_root / ".opencode" / "commands",
            Path.home() / ".config" / "opencode" / "command",
            Path.home() / ".config" / "opencode" / "commands",
        ]
    # codex skills can live in either project layout, or the user-global dir.
    return [
        project_root / ".agents" / "skills",
        project_root / ".codex" / "skills",
        Path.home() / ".codex" / "skills",
    ]


def _has_bmad_skills(d: Path) -> bool:
    try:
        return d.is_dir() and any(d.glob("bmad-*"))
    except OSError:
        return False


def _probe_auth(tool: str) -> tuple[str, str | None]:
    """Return (status, error). status in ok|failed|unknown."""
    try:
        if tool == "claude":
            p = subprocess.run(
                ["claude", "auth", "status"],
                capture_output=True, text=True, timeout=_AUTH_PROBE_TIMEOUT,
            )
            if p.returncode != 0:
                return "failed", (p.stderr or p.stdout or "").strip()[:200]
            try:
                logged = bool(json.loads(p.stdout).get("loggedIn"))
            except (ValueError, AttributeError):
                logged = '"loggedIn": true' in p.stdout or '"loggedIn":true' in p.stdout
            return ("ok", None) if logged else ("failed", "not logged in")
        elif tool == "codex":
            p = subprocess.run(
                ["codex", "login", "status"],
                capture_output=True, text=True, timeout=_AUTH_PROBE_TIMEOUT,
            )
            out = (p.stdout or "") + (p.stderr or "")
            if p.returncode == 0 and "logged in" in out.lower():
                return "ok", None
            return "failed", out.strip()[:200] or "not logged in"
        else:  # opencode
            # opencode is LENIENT on auth: it supports keyless/local/config providers (an
            # openai-compatible `baseURL` in opencode.json, a local LM Studio, etc.), so a "0
            # credentials" listing does NOT mean unauthenticated — there is no reliable
            # logged-out signal short of running the model. Treat a clean `auth list` exit as ok;
            # never hard-stop a routed opencode phase on a false "not authed".
            p = subprocess.run(
                ["opencode", "auth", "list"],
                capture_output=True, text=True, timeout=_AUTH_PROBE_TIMEOUT,
            )
            if p.returncode == 0:
                return "ok", None
            return "failed", (p.stderr or p.stdout or "").strip()[:200] or "auth list failed"
    except FileNotFoundError:
        return "unknown", "binary not found"
    except subprocess.TimeoutExpired:
        return "unknown", f"auth probe timed out after {_AUTH_PROBE_TIMEOUT}s"
    except OSError as e:  # pragma: no cover - environment dependent
        return "unknown", str(e)[:200]


def validate(
    plan: dict,
    project_root: str,
    host: str | None = None,
    run_auth_probe: bool = True,
) -> dict:
    """Live preflight checks for a routed plan: binary on PATH, skills installed,
    and (for the non-host tool) the CLI is authed. Returns a ``validation`` dict
    and sets ``plan['ok']`` / appends to ``plan['errors']``.
    """
    tool = plan["tool"]
    root = Path(project_root)
    errors: list[str] = list(plan.get("errors") or [])

    binary = TOOL_BINARY.get(tool)
    binary_path = shutil.which(binary) if binary else None
    if not binary_path:
        errors.append(f"CLI binary '{binary}' not on PATH (route {plan['phase']} needs it)")

    dirs = _skills_dirs(tool, root)
    present_dirs = [str(d) for d in dirs if _has_bmad_skills(d)]
    if not present_dirs:
        errors.append(
            f"no BMAD skills found for '{tool}' in any of: {[str(d) for d in dirs]}"
        )

    is_host_tool = host is not None and _HOST_TOOL.get(host) == tool
    if is_host_tool:
        auth, auth_err = "skipped (host tool)", None
    elif not run_auth_probe:
        auth, auth_err = "skipped (probe disabled)", None
    elif not binary_path:
        auth, auth_err = "unknown", "binary not on PATH"
    else:
        auth, auth_err = _probe_auth(tool)
        if auth == "failed":
            errors.append(f"'{tool}' CLI is not authenticated ({auth_err}); run its login first")

    validation = {
        "binary_on_path": bool(binary_path),
        "binary_path": binary_path,
        "skills_present": bool(present_dirs),
        "skills_dirs_checked": [str(d) for d in dirs],
        "skills_dirs_found": present_dirs,
        "auth": auth,
        "auth_error": auth_err,
    }
    plan["validation"] = validation
    plan["errors"] = errors
    plan["ok"] = not errors
    return plan


# --- watching a detached delegate to completion (process-exit primary; idle backstop) ---

# Why pid-primary, not log-silence: `claude -p --output-format json` emits NOTHING until its single
# final envelope, so "capture_log went quiet" is NOT evidence the delegate wedged — it is the normal
# shape of a long run. Process liveness is the real signal; the idle backstop is a degraded fallback
# used ONLY when the orchestrator could not capture a pid.
_WAIT_REASON = {
    "exited": (
        "the delegate process exited (sentinel written) — read result_source and apply the normal "
        "result-block failure check (empty/.is_error/empty -o is still a failed delegation)"
    ),
    "dead-no-sentinel": (
        "the delegate PID is gone but wrote no exit sentinel — it crashed or was killed before "
        "completing; failed delegation, hard-stop (surface capture_log)"
    ),
    "wedged-idle": (
        "no exit sentinel and capture_log was silent past --idle-timeout with no --pid to confirm "
        "liveness — treated as wedged; failed delegation, hard-stop (surface capture_log)"
    ),
    "max-wait": (
        "the optional --max-wait absolute cap was reached before the delegate exited; hard-stop "
        "(surface capture_log) or re-run with a larger cap"
    ),
    "running": (
        "no exit sentinel yet and (no --pid given, or the PID is still alive) — still in progress. "
        "On a host that re-invoked you when the background task exited, a 'running' here means the "
        "task died without writing a sentinel: treat it as dead-no-sentinel"
    ),
}


def _pid_alive(pid: int) -> bool:
    """True iff a process with this PID currently exists (POSIX signal-0 probe)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # exists, owned by another user
        return True
    except OSError:
        return False
    return True


def _read_exit_code(path: Path) -> int | None:
    """Read the launch wrapper's exit-code sentinel, or None if it is absent/empty/unparsed.

    None means "not exited yet" — including the sub-millisecond window where the file exists but
    ``echo $?`` has not finished writing it (so a half-written sentinel never reads as a clean exit).
    """
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return None
    if not text:
        return None
    try:
        return int(text.split()[0])
    except (ValueError, IndexError):
        return None


def _wait_decision(
    sentinel_ready: bool,
    sentinel_code: int | None,
    pid_supplied: bool,
    pid_alive: bool,
    idle_seconds: float,
    idle_timeout: float,
    elapsed: float,
    max_wait: float,
) -> tuple[str, int | None]:
    """One step of the watch decision. PURE — no clock, no filesystem, no sleep.

    Priority — completion ALWAYS wins over any wedge heuristic, and the sentinel short-circuits
    pid-liveness so a recycled PID can never fake an exit:
      1. sentinel present+parsed -> ("exited", code)        [total runtime UNBOUNDED]
      2. pid supplied & dead      -> ("dead-no-sentinel", None)   [crash before the sentinel]
      3. --max-wait cap hit (opt-in, 0 = unbounded) -> ("max-wait", None)
      4. NO pid & idle past backstop -> ("wedged-idle", None)     [degraded fallback only]
      5. otherwise -> ("continue", None)

    With a pid supplied AND alive, idle-silence is NEVER a wedge (clause 4 is gated on ``not
    pid_supplied``): a live process is presumed working, bounded only by the optional --max-wait.
    """
    if sentinel_ready:
        return ("exited", sentinel_code)
    if pid_supplied and not pid_alive:
        return ("dead-no-sentinel", None)
    if max_wait > 0 and elapsed >= max_wait:
        return ("max-wait", None)
    if not pid_supplied and idle_seconds >= idle_timeout:
        return ("wedged-idle", None)
    return ("continue", None)


def _verdict(
    status: str, code: int | None, waited: float, idle: float,
    capture_log: str, exit_file: str, pid: int | None,
) -> dict:
    return {
        "status": status,
        "ok": status == "exited",
        "exit_code": code,
        "waited_seconds": round(waited, 1),
        "idle_seconds": round(idle, 1),
        "capture_log": capture_log,
        "exit_file": exit_file,
        "pid": pid,
        "reason": _WAIT_REASON[status],
    }


def _snapshot(cap: Path, sentinel: Path, pid: int | None, started: float, now: float):
    """Observe the delegate once: (sentinel_ready, code, pid_supplied, pid_alive, idle_seconds)."""
    code = _read_exit_code(sentinel)
    sentinel_ready = code is not None
    try:
        mtime = cap.stat().st_mtime
    except OSError:
        mtime = None
    # Idle is measured from the last capture-log write; before any write, from `started`.
    idle_ref = mtime if mtime is not None else started
    idle_seconds = max(0.0, now - idle_ref)
    pid_supplied = pid is not None
    pid_alive = _pid_alive(pid) if (pid_supplied and pid is not None) else False
    return sentinel_ready, code, pid_supplied, pid_alive, idle_seconds


def observe_once(
    capture_log: str, exit_file: str | None = None, pid: int | None = None, _clock=None,
) -> dict:
    """Classify a delegate in a SINGLE shot (no loop): exited / dead-no-sentinel / running.

    For a host that re-invokes the orchestrator when a background task exits: background the
    delegate itself, then call this on wake — no second long-lived watcher needed.
    """
    clock = _clock or time.time
    cap = Path(capture_log)
    sentinel = Path(exit_file) if exit_file else Path(capture_log + ".exit")
    now = clock()
    sr, code, ps, pa, idle = _snapshot(cap, sentinel, pid, now, now)
    if sr:
        status, dcode = "exited", code
    elif ps and not pa:
        status, dcode = "dead-no-sentinel", None
    else:
        status, dcode = "running", None
    return _verdict(status, dcode, 0.0, idle, capture_log, str(sentinel), pid)


def wait_for_delegate(
    capture_log: str,
    exit_file: str | None = None,
    pid: int | None = None,
    idle_timeout: float = 1800.0,
    poll_interval: float = 5.0,
    max_wait: float = 0.0,
    _clock=None,
    _sleep=None,
) -> dict:
    """Block in a poll loop until the delegate exits (or wedges), then return a verdict dict.

    MUST be launched backgrounded by the orchestrator — a foreground wait would hit the host's
    own ~10-min shell cap and kill itself (and likely the child) long before a real delegate
    finishes. ``_clock``/``_sleep`` are injection seams for the self-test (no real sleeping).
    """
    clock = _clock or time.time
    sleep = _sleep or time.sleep
    cap = Path(capture_log)
    sentinel = Path(exit_file) if exit_file else Path(capture_log + ".exit")
    started = clock()
    while True:
        now = clock()
        sr, code, ps, pa, idle = _snapshot(cap, sentinel, pid, started, now)
        decision, dcode = _wait_decision(
            sr, code, ps, pa, idle, idle_timeout, now - started, max_wait
        )
        if decision != "continue":
            return _verdict(decision, dcode, now - started, idle, capture_log, str(sentinel), pid)
        sleep(poll_interval)


def _run_self_test() -> int:
    # A representative config: two profiles, a phase map, and a cli_phases route
    # in BLOCK form. claude-routed + codex-routed phases exercise both arms.
    cfg = (
        "version: 1\n"
        "delegation:\n"
        "  host: auto\n"
        "  mode: auto\n"
        "  target_tools:\n"
        "    - claude-code\n"
        "    - codex\n"
        "  cli_phases:\n"
        "    dev_story: codex\n"
        "    create_story: claude\n"
        "    tea_triage: opencode\n"        # opencode arm: model + variant set (via ab-deep)
        "    tea_per_story: opencode\n"     # opencode arm: blank model + variant (via ab-blank)
        "tea:\n"
        "  enabled: true\n"
        "profiles:\n"
        "  ab-deep:\n"
        "    description: \"big\"\n"
        "    claude:\n"
        "      model: opus\n"
        "      effort: xhigh\n"
        "    codex:\n"
        "      model: gpt-5.5\n"
        "      reasoning_effort: xhigh\n"
        "    opencode:\n"
        "      model: anthropic/claude-opus-4-5\n"
        "      variant: high\n"
        "  ab-blank:\n"
        "    description: \"inherit\"\n"
        "    opencode:\n"
        "      model: \"\"\n"
        "      variant: \"\"\n"
        "phase_profiles:\n"
        "  create_story: ab-deep\n"
        "  dev_story: ab-deep\n"
        "  retrospective: ab-deep\n"
        "  tea_triage: ab-deep\n"
        "  tea_per_story: ab-blank\n"
    )

    # cli_phases / phase_profiles parsing.
    lines = cfg.splitlines()
    assert parse_cli_phases(lines) == {
        "dev_story": "codex", "create_story": "claude",
        "tea_triage": "opencode", "tea_per_story": "opencode",
    }
    assert parse_phase_profiles(lines)["dev_story"] == "ab-deep"

    # --- codex arm ---
    cx = resolve("dev_story", cfg, "/proj", story_key="1-2-auth")
    assert cx["routed"] and not cx["errors"], cx
    assert cx["tool"] == "codex" and cx["model"] == "gpt-5.5" and cx["effort"] == "xhigh", cx
    a = cx["argv"]
    assert a[:2] == ["codex", "exec"], a
    assert "-m" in a and a[a.index("-m") + 1] == "gpt-5.5", a
    # codex effort is set via `-c model_reasoning_effort=`, NEVER `--effort`.
    assert "-c" in a and "model_reasoning_effort=xhigh" in a, a
    assert "--effort" not in a, a
    # codex bypasses approvals AND its OS sandbox (no `-s` mode): workspace-write/read-only spawn
    # bubblewrap, which can't create a namespace inside a nested container.
    assert "--dangerously-bypass-approvals-and-sandbox" in a, a
    assert "-s" not in a, a
    assert "-C" in a and a[a.index("-C") + 1] == "/proj", a
    assert "-o" in a and "--ephemeral" in a, a
    assert cx["result_source"].endswith(".lastmsg") and cx["result_format"] == "text", cx

    # --- claude arm ---
    cl = resolve("create_story", cfg, "/proj", story_key="1-2-auth")
    assert cl["tool"] == "claude" and cl["model"] == "opus" and cl["effort"] == "xhigh", cl
    a = cl["argv"]
    assert a[:2] == ["claude", "-p"], a
    assert "--model" in a and a[a.index("--model") + 1] == "opus", a
    # claude effort is `--effort`, NEVER codex's `-c model_reasoning_effort=`.
    assert "--effort" in a and a[a.index("--effort") + 1] == "xhigh", a
    assert not any(str(x).startswith("model_reasoning_effort=") for x in a), a
    assert "--output-format" in a and "json" in a and "--dangerously-skip-permissions" in a, a
    assert cl["result_format"] == "json" and cl["result_field"] == "result", cl
    assert cl["error_field"] == "is_error", cl
    assert cl["result_source"] == cl["capture_log"], cl

    # --- opencode arm (model + variant SET) ---
    oc = resolve("tea_triage", cfg, "/proj", story_key="1-2-auth")
    assert oc["routed"] and not oc["errors"], oc
    assert oc["tool"] == "opencode" and oc["model"] == "anthropic/claude-opus-4-5" and oc["effort"] == "high", oc
    a = oc["argv"]
    assert a[:2] == ["opencode", "run"], a
    assert "-m" in a and a[a.index("-m") + 1] == "anthropic/claude-opus-4-5", a
    # opencode effort is `--variant`, NEVER claude's `--effort` or codex's `-c model_reasoning_effort=`.
    assert "--variant" in a and a[a.index("--variant") + 1] == "high", a
    assert "--effort" not in a, a
    assert not any(str(x).startswith("model_reasoning_effort=") for x in a), a
    assert "--dir" in a and a[a.index("--dir") + 1] == "/proj", a
    assert "--format" in a and "json" in a and "--dangerously-skip-permissions" in a, a
    # opencode does NOT read stdin — the prompt is appended as a positional arg.
    assert oc["prompt_via"] == "arg", oc
    assert oc["result_format"] == "opencode-json" and oc["result_source"] == oc["capture_log"], oc
    assert oc["result_field"] is None and oc["error_field"] is None, oc

    # --- opencode arm (BLANK model + BLANK variant) => -m / --variant OMITTED, still ok (inherit) ---
    ocb = resolve("tea_per_story", cfg, "/proj", story_key="1-2-auth")
    assert ocb["routed"] and not ocb["errors"], ocb  # blank values are NOT an error for opencode
    assert ocb["tool"] == "opencode" and ocb["model"] is None and ocb["effort"] is None, ocb
    assert "-m" not in ocb["argv"] and "--variant" not in ocb["argv"], ocb["argv"]
    assert ocb["argv"][:2] == ["opencode", "run"], ocb["argv"]
    assert "--dir" in ocb["argv"] and ocb["prompt_via"] == "arg", ocb

    # --- sentinel paths + launch_cmd (the bash -c body the orchestrator backgrounds) ---
    tmp = str(_capture_dir())
    for p in (cx, cl, oc, ocb):
        assert p["exit_file"].endswith(".exit") and p["exit_file"].startswith(tmp), p
        assert p["prompt_file"].endswith(".prompt") and p["prompt_file"].startswith(tmp), p
        assert p["exit_file"] != p["capture_log"] != p["prompt_file"], p
        lc = p["launch_cmd"]
        # cd into the repo, redirect both streams to capture_log, write $? to the sentinel.
        assert lc.startswith("{ cd ") and "; } > " in lc and "2>&1 ; echo $? > " in lc, lc
        assert p["capture_log"] in lc and p["exit_file"] in lc and p["prompt_file"] in lc, lc
    # claude/codex deliver the prompt on STDIN (`< prompt_file`); opencode as a positional arg.
    assert f"< {shlex.quote(cx['prompt_file'])}" in cx["launch_cmd"], cx["launch_cmd"]
    assert f"< {shlex.quote(cl['prompt_file'])}" in cl["launch_cmd"], cl["launch_cmd"]
    assert "cat " in oc["launch_cmd"] and " < " not in oc["launch_cmd"], oc["launch_cmd"]
    # A space in the cwd is shell-quoted, not split, so the cd survives.
    spaced = resolve("dev_story", cfg, "/tmp/my proj", story_key="k")
    assert "cd '/tmp/my proj'" in spaced["launch_cmd"], spaced["launch_cmd"]

    # --- extract_opencode_result: validated against a REAL opencode 1.16.2 `run --format json`
    # capture (OpenCode Zen / MiMo V2.5; opaque IDs abbreviated, structure verbatim). Assistant
    # text = part.text of the top-level type=="text" event(s); step_start/step_finish are ignored.
    real = (
        '{"type":"step_start","sessionID":"ses_x","part":{"id":"prt_a","messageID":"msg_1","sessionID":"ses_x","snapshot":"f1c4","type":"step-start"}}\n'
        '{"type":"text","timestamp":1781014936653,"sessionID":"ses_x","part":{"id":"prt_b","messageID":"msg_1","sessionID":"ses_x","type":"text","text":"PONG","time":{"start":1781014936622,"end":1781014936650}}}\n'
        '{"type":"step_finish","sessionID":"ses_x","part":{"id":"prt_c","reason":"stop","messageID":"msg_1","type":"step-finish","tokens":{"total":24862,"input":18703,"output":5},"cost":0}}\n'
    )
    msg, err = extract_opencode_result(real)
    assert err is None and msg == "PONG", (msg, err)
    # Multi-part / multi-step reply: every type=="text" part.text is concatenated IN ORDER (not
    # "last wins") — a streamed delta would break a last-only parser, complete segments don't.
    multi = (
        '{"type":"step_start","part":{"type":"step-start"}}\n'
        '{"type":"text","part":{"type":"text","text":"Outcome: done\\n"}}\n'
        '{"type":"text","part":{"type":"text","text":"Status: ok"}}\n'
        '{"type":"step_finish","part":{"type":"step-finish","tokens":{"total":1}}}\n'
    )
    msg, err = extract_opencode_result(multi)
    assert err is None and msg == "Outcome: done\nStatus: ok", (msg, err)
    # `default` (formatted) output is plain text => the whole capture is the message.
    msg, err = extract_opencode_result("just plain text result\n")
    assert err is None and msg == "just plain text result", (msg, err)
    # Fallback path: no top-level type=="text" event => collect any text/content leaf (last wins).
    msg, err = extract_opencode_result('{"message":{"parts":[{"type":"text","text":"final answer"}]}}')
    assert err is None and msg == "final answer", (msg, err)
    # Empty output => error + no message (the orchestrator hard-stops, never delegates empty).
    msg, err = extract_opencode_result("   \n")
    assert msg is None and err, (msg, err)
    # JSON present but no extractable assistant text => error (schema may have shifted).
    msg, err = extract_opencode_result('{"type":"status","done":true}')
    assert msg is None and err and "opencode" in err, (msg, err)

    # EXPLICIT claude-vs-codex argv divergence (the helper's reason to exist).
    assert ("--effort" in cl["argv"]) and ("--effort" not in cx["argv"])
    assert any(str(x).startswith("model_reasoning_effort=") for x in cx["argv"])
    assert not any(str(x).startswith("model_reasoning_effort=") for x in cl["argv"])

    # Capture logs live OUTSIDE the repo, under the OS temp dir.
    tmp = str(_capture_dir())
    assert cx["capture_log"].startswith(tmp) and "/proj" not in cx["capture_log"], cx
    assert cl["capture_log"].startswith(tmp), cl
    # Distinct files per (story, phase).
    assert cx["capture_log"] != cl["capture_log"]
    assert cx["result_source"] != cx["capture_log"]  # codex parses the -o file, not stdout

    # `label` keeps fan-out delegates' capture paths distinct (same phase + story).
    l1 = resolve("create_story", cfg, "/proj", story_key="k", label="blind-hunter")
    l2 = resolve("create_story", cfg, "/proj", story_key="k", label="edge-case")
    assert l1["capture_log"] != l2["capture_log"], (l1["capture_log"], l2["capture_log"])
    assert "blind-hunter" in l1["capture_log"], l1["capture_log"]

    # Unrouted phase -> use the normal tier.
    assert resolve("retrospective", cfg, "/proj") == {"routed": False, "phase": "retrospective"}

    # Inline cli_phases form, including empty.
    inline = "delegation:\n  cli_phases: { dev_story: claude, retrospective: codex }\n"
    assert parse_cli_phases(inline.splitlines()) == {"dev_story": "claude", "retrospective": "codex"}
    assert parse_cli_phases("delegation:\n  cli_phases: {}\n".splitlines()) == {}
    assert parse_cli_phases("delegation:\n  host: auto\n".splitlines()) == {}  # no cli_phases key

    # Resolution errors: bad tool, missing profile block, unknown phase mapping.
    bad_tool = cfg.replace("dev_story: codex", "dev_story: gpt5")
    r = resolve("dev_story", bad_tool, "/proj")
    assert r["routed"] and r["ok"] is False and any("expected 'claude', 'codex' or 'opencode'" in e for e in r["errors"]), r

    no_block = (
        "delegation:\n  cli_phases:\n    dev_story: codex\n"
        "profiles:\n  ab-deep:\n    claude:\n      model: opus\n      effort: xhigh\n"
        "phase_profiles:\n  dev_story: ab-deep\n"
    )  # ab-deep has no codex block
    r = resolve("dev_story", no_block, "/proj")
    assert r["ok"] is False and any("no 'codex' block" in e for e in r["errors"]), r

    no_map = "delegation:\n  cli_phases:\n    dev_story: codex\nprofiles:\n  ab-deep:\n    codex:\n      model: m\n      reasoning_effort: high\n"
    r = resolve("dev_story", no_map, "/proj")  # no phase_profiles mapping
    assert r["ok"] is False and any("no phase_profiles mapping" in e for e in r["errors"]), r

    # --- validate(): offline-deterministic paths (no real auth probe) ---
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / ".agents" / "skills" / "bmad-create-story").mkdir(parents=True)
        # Host-tool route skips the auth probe; codex skills found in .agents/skills.
        plan = resolve("dev_story", cfg, str(root), story_key="k")
        v = validate(plan, str(root), host="codex", run_auth_probe=False)
        assert v["validation"]["skills_present"] is True, v
        assert v["validation"]["auth"] == "skipped (host tool)", v
        # binary_on_path depends on the test env; ok reflects only present errors.

        # Missing skills dir -> error.
        with tempfile.TemporaryDirectory() as td2:
            plan2 = resolve("dev_story", cfg, td2, story_key="k")
            v2 = validate(plan2, td2, host="codex", run_auth_probe=False)
            assert v2["validation"]["skills_present"] is False, v2
            assert any("no BMAD skills" in e for e in v2["errors"]), v2
            assert v2["ok"] is False

        # Non-host tool with probe disabled -> auth reported as skipped, not failed.
        plan3 = resolve("create_story", cfg, str(root), story_key="k")
        (root / ".claude" / "skills" / "bmad-create-story").mkdir(parents=True)
        v3 = validate(plan3, str(root), host="codex", run_auth_probe=False)
        assert v3["validation"]["auth"] == "skipped (probe disabled)", v3

        # opencode: skills are looked up under `.opencode/skills/`; a host=opencode route skips
        # the auth probe (the host the orchestrator runs in is authed by definition).
        (root / ".opencode" / "skills" / "bmad-retrospective").mkdir(parents=True)
        plan_oc = resolve("tea_triage", cfg, str(root), story_key="k")
        v_oc = validate(plan_oc, str(root), host="opencode", run_auth_probe=False)
        assert v_oc["validation"]["skills_present"] is True, v_oc
        assert v_oc["validation"]["auth"] == "skipped (host tool)", v_oc
        assert any(str(d).endswith(".opencode/skills") for d in v_oc["validation"]["skills_dirs_checked"]), v_oc

        # opencode commands-based BMAD install (no skills dir): `command(s)/bmad-*.md` files
        # also count as present — a miss here would hard-stop a working route.
        with tempfile.TemporaryDirectory() as td3:
            cmd_dir = Path(td3) / ".opencode" / "commands"
            cmd_dir.mkdir(parents=True)
            (cmd_dir / "bmad-review-adversarial-general.md").write_text("# cmd", encoding="utf-8")
            plan_cmd = resolve("tea_triage", cfg, td3, story_key="k")
            v_cmd = validate(plan_cmd, td3, host="opencode", run_auth_probe=False)
            assert v_cmd["validation"]["skills_present"] is True, v_cmd
            assert any(str(d).endswith(".opencode/commands") for d in v_cmd["validation"]["skills_dirs_found"]), v_cmd

    # --- watch logic: _wait_decision (pure) + observe_once/wait_for_delegate (injected clock) ---
    # Sentinel wins over everything — even a 'dead' pid reads as a clean exit, not a crash.
    assert _wait_decision(True, 0, True, False, 9e9, 1.0, 9e9, 0.0) == ("exited", 0)
    assert _wait_decision(True, 7, False, False, 0.0, 1800.0, 0.0, 0.0) == ("exited", 7)
    # pid supplied & DEAD with no sentinel -> crash.
    assert _wait_decision(False, None, True, False, 0.0, 1800.0, 0.0, 0.0) == ("dead-no-sentinel", None)
    # pid supplied & ALIVE & silent for ages -> NOT wedged (claude -p emits nothing until the end).
    assert _wait_decision(False, None, True, True, 9e9, 1800.0, 9e9, 0.0) == ("continue", None)
    # NO pid & idle past the backstop -> wedged-idle (the degraded fallback).
    assert _wait_decision(False, None, False, False, 1801.0, 1800.0, 1801.0, 0.0) == ("wedged-idle", None)
    # NO pid but still within the idle window -> continue.
    assert _wait_decision(False, None, False, False, 10.0, 1800.0, 10.0, 0.0) == ("continue", None)
    # --max-wait cap hit (even with a live pid) -> max-wait; 0 means unbounded (never trips).
    assert _wait_decision(False, None, True, True, 0.0, 1800.0, 100.0, 50.0) == ("max-wait", None)
    assert _wait_decision(False, None, True, True, 0.0, 1800.0, 1e9, 0.0) == ("continue", None)

    with tempfile.TemporaryDirectory() as wd:
        cap = Path(wd) / "d.log"
        ex = Path(wd) / "d.exit"
        # observe_once: nothing yet, no pid -> running (not ok).
        r = observe_once(str(cap), exit_file=str(ex))
        assert r["status"] == "running" and r["ok"] is False, r
        # sentinel present -> exited + code; a nonzero code is STILL 'exited' (the caller then
        # applies the result-block check — process-exit and delegate-success are separate).
        ex.write_text("0\n", encoding="utf-8")
        assert observe_once(str(cap), exit_file=str(ex))["exit_code"] == 0
        ex.write_text("7\n", encoding="utf-8")
        r = observe_once(str(cap), exit_file=str(ex))
        assert r["status"] == "exited" and r["exit_code"] == 7 and r["ok"] is True, r
        # default exit_file = <capture_log>.exit when not passed (fresh basename, no sentinel yet).
        assert observe_once(str(Path(wd) / "fresh"))["status"] == "running"  # fresh.exit absent

        # wait_for_delegate happy path: sentinel lands on the 2nd poll. Injected clock+sleep (no real
        # sleeping); capture_log absent => idle is clock-driven, huge idle_timeout => never trips.
        ex2, cap2 = Path(wd) / "w.exit", Path(wd) / "w.log"
        ticks = iter([0.0, 1.0, 2.0, 3.0, 4.0])
        state = {"n": 0}

        def _sleep_writes_sentinel(_):
            state["n"] += 1
            if state["n"] == 2:
                ex2.write_text("0\n", encoding="utf-8")

        r = wait_for_delegate(
            str(cap2), exit_file=str(ex2), idle_timeout=9e9, poll_interval=0.0,
            _clock=lambda: next(ticks), _sleep=_sleep_writes_sentinel,
        )
        assert r["status"] == "exited" and r["ok"] and r["exit_code"] == 0, r

        # wait_for_delegate wedged-idle: no pid, no sentinel, small idle_timeout, clock advances.
        ticks3 = iter([0.0, 5.0, 12.0])
        r = wait_for_delegate(
            str(Path(wd) / "i.log"), exit_file=str(Path(wd) / "i.exit"), idle_timeout=10.0,
            poll_interval=0.0, _clock=lambda: next(ticks3), _sleep=lambda _: None,
        )
        assert r["status"] == "wedged-idle" and not r["ok"], r

    # _read_exit_code: empty/half-written sentinel reads as "not exited" (None), not a clean 0.
    with tempfile.TemporaryDirectory() as rd:
        empty = Path(rd) / "e.exit"
        empty.write_text("", encoding="utf-8")
        assert _read_exit_code(empty) is None
        assert _read_exit_code(Path(rd) / "missing.exit") is None
        (Path(rd) / "ok.exit").write_text("0\n", encoding="utf-8")
        assert _read_exit_code(Path(rd) / "ok.exit") == 0

    print("SELF-TEST PASSED (all assertions)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve an external-CLI delegation for one auto-bmad phase."
    )
    parser.add_argument("--self-test", action="store_true", help="Run internal tests and exit.")
    parser.add_argument("--wait", action="store_true", help="Block until a detached routed delegate exits, then print a verdict JSON. MUST be launched BACKGROUNDED (a foreground wait hits the host's ~10-min shell cap). Prefer --once on a host that re-invokes you when a background task exits.")
    parser.add_argument("--once", action="store_true", help="Classify a delegate ONCE and exit immediately (no loop): exited / dead-no-sentinel / running. For notify-capable hosts — background the delegate itself, then call --once on wake.")
    parser.add_argument("--capture-log", help="Delegate capture-log path (from resolve()); required by --wait/--once.")
    parser.add_argument("--exit-file", help="Exit-code sentinel path (from resolve(); defaults to <capture-log>.exit).")
    parser.add_argument("--pid", type=int, help="PID of the detached delegate (its bash -c subshell). With it, a crash-without-sentinel is detected and log-silence never triggers a false wedge.")
    parser.add_argument("--idle-timeout", type=float, default=1800.0, help="NO-pid fallback only: declare 'wedged-idle' after this many seconds of NO new capture-log output. A SILENCE allowance, NOT a runtime cap. Ignored when --pid is given. Default 1800 (30 min).")
    parser.add_argument("--poll-interval", type=float, default=5.0, help="--wait poll cadence in seconds (default 5).")
    parser.add_argument("--max-wait", type=float, default=0.0, help="Optional absolute safety cap in seconds (0 = unbounded — the default, so a multi-hour delegate is never killed on a clock). Set a generous value (hours) as a final backstop against a truly hung delegate.")
    parser.add_argument("--phase", help="Pipeline phase key (e.g. dev_story, code_review_review).")
    parser.add_argument("--config", help="Path to the runtime config.yaml.")
    parser.add_argument("--project-root", help="Project root (cwd for the child; codex -C).")
    parser.add_argument("--story-key", default="story", help="Story key, for unique capture filenames.")
    parser.add_argument("--label", help="Extra capture-filename suffix; use a distinct one per fan-out delegate (e.g. blind-hunter) so their capture logs don't collide.")
    parser.add_argument("--host", help="Resolved host (claude-code|codex|opencode); skips the auth probe for the host tool. Any other value (e.g. 'auto') ⇒ probe always.")
    parser.add_argument("--no-auth-probe", action="store_true", help="Skip the live auth probe (resolution + binary/skills only).")
    parser.add_argument("--mkdir", action="store_true", help="Create the temp capture dir so the orchestrator's redirect succeeds.")
    args = parser.parse_args()

    if args.self_test:
        return _run_self_test()

    if args.wait or args.once:
        if not args.capture_log:
            print(json.dumps({"status": "error", "message": "--wait/--once require --capture-log"}))
            return 2
        if args.once:
            result = observe_once(args.capture_log, exit_file=args.exit_file, pid=args.pid)
        else:
            result = wait_for_delegate(
                args.capture_log, exit_file=args.exit_file, pid=args.pid,
                idle_timeout=args.idle_timeout, poll_interval=args.poll_interval,
                max_wait=args.max_wait,
            )
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1

    missing = [n for n in ("phase", "config", "project_root") if not getattr(args, n)]
    if missing:
        print(json.dumps({"status": "error", "message": f"missing required: {missing}"}))
        return 2

    cfg_path = Path(args.config)
    if not cfg_path.is_file():
        print(json.dumps({"status": "error", "message": f"config not found: {cfg_path}"}))
        return 2

    plan = resolve(args.phase, cfg_path.read_text(encoding="utf-8"), args.project_root, args.story_key, args.label)
    if not plan.get("routed"):
        print(json.dumps(plan, indent=2))
        return 0
    if plan.get("ok") is False:  # resolution error already recorded
        print(json.dumps(plan, indent=2))
        return 2

    validate(plan, args.project_root, host=args.host, run_auth_probe=not args.no_auth_probe)
    if args.mkdir:
        _capture_dir().mkdir(parents=True, exist_ok=True)
    print(json.dumps(plan, indent=2))
    return 0 if plan.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
