#!/usr/bin/env python3
"""Deterministic writer for auto-bmad's per-story state file and report sections.

Replaces the YAML/markdown the orchestrator used to hand-write after every phase. Every state
write re-emits the FULL ``state/{key}.yaml`` schema from ``references/state-and-resume.md`` —
every field always present with an explicit ``null``/``false``/``[]``/``{}`` default — and stamps
``updated_at`` (ISO-8601 UTC). Reading an older state file missing fields migrates it to the full
shape on the next write; unknown fields it already carries (epic-anchor extras such as
``stories_landed``, or fields an older schema wrote) are preserved verbatim after the schema
fields, never dropped. ``--self-test`` parses the live schema block out of
``../references/state-and-resume.md`` and asserts its field-name set equals this writer's — top
level plus the ``phase8_steps`` / ``build`` / ``retro`` sub-keys — so a doc edit that drifts the
schema fails loud (the lockstep pattern from ``config_plan.py``).

Subcommands (each emits a single JSON object on stdout):

* ``init``          — create the state file from a full ``--json`` payload. Stamps ``started_at``
                      ONCE; refuses (exit 1) if the file already exists — resume must never re-init.
* ``set``           — apply a JSON patch: one-level-deep merge for the map fields
                      (``story_trace``/``overrides``/``phase8_steps``/``build``/``retro`` — a map
                      value may itself be a flat list, e.g. ``build.warnings``, and round-trips);
                      reserved key ``_append`` extends list fields
                      (``{"_append": {"commits": ["a1b2c3d"]}}``); a list field takes only
                      a list (``null`` lands as its ``[]`` default) and ``build``/``retro``/
                      ``phase8_steps`` only a map (never ``null``); a patch that sets
                      ``status: "done"`` auto-stamps ``completed_at``; any attempt to CHANGE
                      ``started_at`` is refused (exit 1, error in JSON).
* ``phase-done``    — add ``--phase N`` to ``completed_phases`` (idempotent, kept sorted) and apply
                      an optional simultaneous ``--json`` patch (the folded write). The patch must
                      NOT contain ``completed_phases`` (exit 1) — the subcommand owns that field,
                      and a patch value would clobber the phase this very call records.
* ``timing-start``  — set ``timing_anchor`` to now-epoch. An anchor already set is a crash tail:
                      re-anchor and report ``dropped_anchor: true`` (the dangling interval is
                      conservatively discarded, never guessed into ``active_seconds``).
* ``timing-pause``  — add now−anchor to ``active_seconds`` and null the anchor; exit 1 if no anchor.
                      All clock arithmetic lives here — the orchestrator just brackets each phase
                      (and each AskUserQuestion prompt) with start/pause.
* ``report-section``— APPEND a ``## Report — <ISO ts> (<tag>)`` section to ``reports/{key}.md``,
                      rendering the state-and-resume.md "Section template" literally (same headings,
                      same order, ``(none)`` for empties). Story/Spec/Branch/Timing lines (spec path,
                      elapsed, ≈AI-run = active_seconds, ≈wait = elapsed−active, resumed N×) derive
                      from the state file; the prose snippets come from ``--json``, whose keys must
                      be from ``REPORT_PAYLOAD_KEYS`` — an unknown key is REJECTED (exit 2), because
                      every missing key renders ``(none)`` and a misspelled one would silently drop
                      its content from the committed report. Creates the file with a one-line H1 if
                      absent; NEVER overwrites existing sections — a full rewrite requires
                      ``--overwrite-confirmed``. ``--allow-missing-state`` covers the pre-init
                      hard-stop (Phase 0 — "always produce a report" before ``init`` ever ran):
                      renders against a default state keyed off the state file's name.
                      With ``--epic`` it renders the *epic-rollup* template instead (epic header +
                      per-story rollup + epic gate / TEA / retrospective + open-questions/deferred
                      checklist), keyed off the epic anchor, with its own
                      ``EPIC_REPORT_PAYLOAD_KEYS`` allowlist.

Exit codes: 0 ok; 1 contract violation (init-exists, started_at rewrite, pause-without-anchor,
a patch value the emit/parse round-trip or the timing math could not honor — un-re-readable map
keys, non-int INT fields, a non-list LIST field, a null/non-map ``phase8_steps``/``build``/``retro``,
off-schema ``phase8_steps``/``build``/``retro`` keys or markers, set+``_append`` overlap — and a
stored value a command cannot use: a non-int ``timing_anchor``/``active_seconds`` at
``timing-pause``/``report-section``, a non-list ``completed_phases`` at ``phase-done`` or a
non-list target at ``_append``, each answered with an exit-1 JSON that names the field to repair
with ``set``); 2 usage/parse error. Dependency-free (stdlib only); state parsing is a
small block-structured reader in the ``state_plan.py`` spirit — flat scalars, flat lists,
one-level maps (whose values may be scalars or flat lists).

Usage:
    state_update.py init           --state-file PATH --json -|FILE
    state_update.py set            --state-file PATH --json -|FILE
    state_update.py phase-done     --state-file PATH --phase N [--json -|FILE]
    state_update.py timing-start   --state-file PATH
    state_update.py timing-pause   --state-file PATH
    state_update.py report-section --report-file PATH --state-file PATH --json -|FILE
                                   [--epic] [--overwrite-confirmed] [--allow-missing-state]
    state_update.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


class ContractError(Exception):
    """A pipeline-contract violation (exit 1)."""


class UsageError(Exception):
    """Bad arguments / unparsable input / missing prerequisite file (exit 2)."""


# --------------------------------------------------------------------------- #
# Schema (lockstep with references/state-and-resume.md -> "## state/{key}.yaml")
# --------------------------------------------------------------------------- #
PHASE8_KEYS = ("trace_gate", "nfr", "test_review", "reconcile", "archive", "retro")
BUILD_KEYS = ("status", "blocking_condition", "followup_review_recommended",
              "review_loop_iteration", "deferred_count", "warnings")   # last bmad-build-auto result
RETRO_KEYS = ("doc", "verdict", "open_action_items")                    # epic-end retrospective

SCHEMA_ORDER = (
    "story_key", "epic_num", "story_num", "story_suffix", "branch", "status",
    "updated_at", "started_at", "completed_at", "active_seconds", "timing_anchor",
    "is_first_in_epic", "is_last_in_epic",
    "git_mode", "base_branch",
    "tea_risk", "tea_selected", "tea_rationale", "epic_story_count", "stories_after_in_epic",
    "completed_phases",
    "spec_path", "spec_approved", "build", "followup_passes", "hitl_halt",
    "review_unverified", "story_trace",
    "commits", "phase8_steps",
    "gate_decision", "gate_iterations", "deferred_work_archived",
    "retro", "bmad_status_flipped_at",
    "pr_url", "ci_run_url", "ci_status",
    "pr_merged", "merge_method", "merge_commit", "branch_deleted",
    "open_questions", "deferred_work", "blockers", "overrides", "constraints",
)

INT_FIELDS = {"epic_num", "story_num", "active_seconds", "timing_anchor", "epic_story_count",
              "stories_after_in_epic", "followup_passes", "gate_iterations",
              "deferred_work_archived", "bmad_status_flipped_at"}
BOOL_FIELDS = {"is_first_in_epic", "is_last_in_epic", "spec_approved", "review_unverified",
               "pr_merged", "branch_deleted"}
FLOW_LIST_FIELDS = {"tea_selected", "completed_phases", "commits"}   # short tokens: emit [a, b]
BLOCK_LIST_FIELDS = {"open_questions", "deferred_work", "blockers", "constraints"}  # free text
LIST_FIELDS = FLOW_LIST_FIELDS | BLOCK_LIST_FIELDS
MAP_FIELDS = {"story_trace", "overrides", "phase8_steps", "build", "retro"}
_MAP_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")   # what load_state's map reader can parse back
_PHASE8_MARKERS = (None, "done")                      # closed vocabulary (pipeline.md Phase 8) …
_PHASE8_TRACE_GATE_EXTRA = ("waived", "failed")       # … which trace_gate alone extends
_FIXED_MAP_KEYS = {"phase8_steps": PHASE8_KEYS, "build": BUILD_KEYS, "retro": RETRO_KEYS}


def default_build() -> dict:
    return {"status": None, "blocking_condition": None, "followup_review_recommended": False,
            "review_loop_iteration": 0, "deferred_count": 0, "warnings": []}


def default_retro() -> dict:
    return {"doc": None, "verdict": None, "open_action_items": 0}


def default_state() -> dict:
    """A fresh full-schema state dict (every field present with its explicit default)."""
    d = {k: None for k in SCHEMA_ORDER}
    d.update(status="in-progress", active_seconds=0)
    for k in BOOL_FIELDS:
        d[k] = False
    for k in LIST_FIELDS:
        d[k] = []
    for k in ("followup_passes", "gate_iterations", "deferred_work_archived"):
        d[k] = 0
    d["story_suffix"] = ""                      # "" when the key has no split suffix
    d["ci_status"] = "unknown"
    d["story_trace"] = None                     # null until the trace advisory runs
    d["overrides"] = {}
    d["phase8_steps"] = {k: None for k in PHASE8_KEYS}
    d["build"] = default_build()
    d["retro"] = default_retro()
    return d


def _now_epoch() -> int:
    return int(time.time())


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# YAML emit (we only ever write shapes we also parse: scalars, flat lists,
# one-level maps). Strings are double-quoted via json.dumps when not bare-safe.
# --------------------------------------------------------------------------- #
_RESERVED = {"null", "~", "true", "false", "yes", "no", "on", "off", "none"}
_BARE_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9 ._/+-]*[A-Za-z0-9._/+-])?")


def _emit_scalar(v) -> str:
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    s = str(v)
    if (_BARE_RE.fullmatch(s) and s.lower() not in _RESERVED
            and not re.fullmatch(r"-?\d+(\.\d+)?", s)):
        return s
    return json.dumps(s, ensure_ascii=False)


def _emit_inline(v) -> str:
    """A map-value or list-element: scalar, or a flat flow list; deeper nesting degrades to JSON."""
    if isinstance(v, list):
        return "[" + ", ".join(_emit_scalar(x) for x in v) + "]"
    if isinstance(v, dict):
        return _emit_scalar(json.dumps(v, ensure_ascii=False))
    return _emit_scalar(v)


def _emit_entry(lines: list, key: str, val) -> None:
    if isinstance(val, dict):
        if not val:
            lines.append(f"{key}: {{}}")
        else:
            lines.append(f"{key}:")
            for k, v in val.items():
                lines.append(f"  {k}: {_emit_inline(v)}")
    elif isinstance(val, list):
        if not val:
            lines.append(f"{key}: []")
        elif key in FLOW_LIST_FIELDS:
            lines.append(f"{key}: [" + ", ".join(_emit_inline(x) for x in val) + "]")
        else:
            lines.append(f"{key}:")
            for x in val:
                lines.append(f"  - {_emit_inline(x)}")
    else:
        lines.append(f"{key}: {_emit_scalar(val)}")


def dump_state(state: dict) -> str:
    lines = ["# auto-bmad per-story state — written by scripts/state_update.py (full stable schema;",
             "# see references/state-and-resume.md). Prose belongs in reports/{key}.md, not here."]
    for key in SCHEMA_ORDER:
        _emit_entry(lines, key, state.get(key))
    for key, val in state.items():                       # preserved unknown/extra fields
        if key not in SCHEMA_ORDER:
            _emit_entry(lines, key, val)
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# YAML parse (block-structured, state_plan.py spirit)
# --------------------------------------------------------------------------- #
def _typed(tok: str):
    if tok in ("", "null", "~"):
        return None
    if tok == "true":
        return True
    if tok == "false":
        return False
    if re.fullmatch(r"-?\d+", tok):
        return int(tok)
    return tok


def _parse_inline(s: str):
    """Parse a scalar / flow list / flow map value (trailing ` # comment` tolerated)."""
    s = s.strip()
    if not s:
        return None
    if s[0] == '"':
        esc, i = False, 1
        while i < len(s):
            if esc:
                esc = False
            elif s[i] == "\\":
                esc = True
            elif s[i] == '"':
                return json.loads(s[: i + 1])
            i += 1
        return s.strip('"')                              # unterminated; best effort
    if s[0] == "'":
        end = s.find("'", 1)
        return s[1:end] if end > 0 else s.strip("'")
    if s[0] == "[":
        body = s[1: s.rfind("]")] if "]" in s else s[1:]
        return [_parse_inline(p) for p in _split_flow(body)]
    if s[0] == "{":
        body = s[1: s.rfind("}")] if "}" in s else s[1:]
        out = {}
        for part in _split_flow(body):
            k, _, v = part.partition(":")
            out[k.strip().strip("'\"")] = _parse_inline(v)
        return out
    s = re.split(r"\s+#", s, maxsplit=1)[0].strip()      # strip trailing comment on bare scalars
    return _typed(s)


def _split_flow(body: str) -> list:
    """Split flow-collection elements on top-level commas, respecting quotes."""
    parts, cur, inq, esc = [], "", None, False
    for ch in body:
        if inq:
            cur += ch
            if esc:
                esc = False
            elif ch == "\\" and inq == '"':
                esc = True
            elif ch == inq:
                inq = None
        elif ch in "\"'":
            inq = ch
            cur += ch
        elif ch == ",":
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def _value_part_is_empty(rest: str) -> bool:
    rest = rest.strip()
    return (not rest) or rest.startswith("#")


def load_state(path: Path) -> dict:
    """Parse a state YAML into a dict (flat scalars, flat lists, one-level maps)."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    data: dict = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s or s.startswith("#") or (len(line) - len(line.lstrip(" "))) > 0:
            i += 1
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):(.*)$", line)
        if not m:
            i += 1
            continue
        key, rest = m.group(1), m.group(2)
        if not _value_part_is_empty(rest):
            data[key] = _parse_inline(rest)
            i += 1
            continue
        # Block body: indented `- item` lines (list) or `k: v` lines (one-level map).
        items: list = []
        mapping: dict = {}
        kind = None
        j = i + 1
        while j < len(lines):
            ln = lines[j]
            st = ln.strip()
            if not st or st.startswith("#"):
                j += 1
                continue
            if (len(ln) - len(ln.lstrip(" "))) == 0:
                break
            if st.startswith("- "):
                kind = "list"
                items.append(_parse_inline(st[2:]))
            elif st == "-":
                kind = "list"
                items.append(None)
            else:
                km = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):(.*)$", st)
                if km:
                    kind = "map"
                    mapping[km.group(1)] = _parse_inline(km.group(2))
            j += 1
        data[key] = items if kind == "list" else (mapping if kind == "map" else None)
        i = j
    return data


def _int_coercible(v) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return True
    return isinstance(v, str) and bool(re.fullmatch(r"-?\d+", v.strip()))


def _coerce(key: str, val):
    """Light type repair for hand-edited/legacy values."""
    if val is None:
        if key in LIST_FIELDS:                        # a list field's documented default is []
            return []
        if key in MAP_FIELDS and key != "story_trace":   # …and a map's (bar the nullable trace) is a map
            return dict(default_state()[key])
        return None
    if key in INT_FIELDS and isinstance(val, str) and re.fullmatch(r"-?\d+", val.strip()):
        return int(val)
    if key == "completed_phases" and isinstance(val, list):   # legacy quoted ints: ["0", "1"]
        return [int(x) if isinstance(x, str) and re.fullmatch(r"-?\d+", x.strip()) else x
                for x in val]
    if key in BOOL_FIELDS and isinstance(val, str):
        if val.strip().lower() == "true":
            return True
        if val.strip().lower() == "false":
            return False
    return val


def full_state(raw: dict) -> dict:
    """Merge a (possibly older/partial) raw read over the full-schema defaults; keep extras."""
    state = default_state()
    for k, v in raw.items():
        if k in MAP_FIELDS and isinstance(v, dict) and isinstance(state.get(k), dict):
            merged = dict(state[k])
            merged.update(v)
            state[k] = merged
        elif k in MAP_FIELDS and isinstance(state.get(k), dict):
            # A hand-edited / legacy `build: null` (or a stray scalar) in a map whose
            # documented default is a full map: keep the default so the next write
            # re-emits every sub-key with its explicit default (file-shape invariant;
            # story_trace is the one nullable map and has no dict default).
            continue
        elif k in SCHEMA_ORDER:
            state[k] = _coerce(k, v)
        else:
            state[k] = v                                 # unknown field: preserve verbatim
    return state


def _read_existing(state_file: Path) -> dict:
    if not state_file.is_file():
        raise UsageError(f"state file not found: {state_file} (run `init` first)")
    return full_state(load_state(state_file))


def _atomic_write(path: Path, text: str) -> None:
    # Same shape as deferred_ledger.py / story_plan.py: a UNIQUE mkstemp temp
    # (a fixed sibling name lets two concurrent runs clobber each other
    # mid-write), the target's mode carried across the replace, and the temp
    # unlinked on any failure.
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        try:
            # mkstemp creates 0600; carry an existing target's mode so the
            # replace doesn't silently drop group/other bits from a user file.
            os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        except OSError:
            pass  # fresh target (first write of a state/report file): keep mkstemp's default
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_state(state_file: Path, state: dict) -> None:
    state["updated_at"] = _now_iso()
    _atomic_write(state_file, dump_state(state))


# --------------------------------------------------------------------------- #
# Patch semantics (shared by init / set / phase-done)
# --------------------------------------------------------------------------- #
def _validate_patch(patch: dict) -> None:
    """Reject keys/values the emit/parse round-trip or the timing math could not honor."""
    for k, v in patch.items():
        if not _MAP_KEY_RE.fullmatch(str(k)):
            # The top-level reader uses the same identifier regex, so a
            # non-identifier field would be emitted but dropped on re-read.
            raise ContractError(
                f"field name {k!r} would not survive a rewrite — keys must match "
                "[A-Za-z_][A-Za-z0-9_]*")
        if isinstance(v, dict):
            # ANY map (schema field or preserved unknown) must re-read: a key the
            # map reader can't parse back is silently dropped, and a map whose
            # keys ALL fail collapses to null on the next write.
            for sub in v:
                if not _MAP_KEY_RE.fullmatch(str(sub)):
                    raise ContractError(
                        f"{k} key {sub!r} would not survive a rewrite — map keys must match "
                        "[A-Za-z_][A-Za-z0-9_]*")
        elif k in _FIXED_MAP_KEYS:
            # phase8_steps / build / retro are never null on disk: every sub-key is
            # always emitted with its explicit default (a null would let a later
            # partial merge write a map missing sub-keys).
            raise ContractError(f"{k} must be a map (never null), got {v!r}")
        elif k in MAP_FIELDS and v is not None:
            raise ContractError(f"{k} must be a map (or null), got {v!r}")
        if k in LIST_FIELDS and v is not None and not isinstance(v, list):
            # A scalar in a list field is emitted as a scalar and read back as one:
            # phase-done would then crash on it and _append would iterate a string.
            raise ContractError(f"{k} must be a list (or null -> []), got {v!r}")
        if k in _FIXED_MAP_KEYS and isinstance(v, dict):
            # phase8_steps / build / retro have a closed key set: a typo'd sub-key
            # would ride along silently while the real one stayed at its default.
            for sub in v:
                if sub not in _FIXED_MAP_KEYS[k]:
                    raise ContractError(
                        f"unknown {k} key {sub!r} — expected one of: "
                        + ", ".join(_FIXED_MAP_KEYS[k]))
        if k == "phase8_steps" and isinstance(v, dict):
            for sub, marker in v.items():
                allowed = _PHASE8_MARKERS + (_PHASE8_TRACE_GATE_EXTRA if sub == "trace_gate" else ())
                if marker not in allowed:
                    raise ContractError(
                        f"phase8_steps.{sub} marker {marker!r} is off-vocabulary — expected "
                        + " | ".join("null" if m is None else m for m in allowed))
        if k in INT_FIELDS and v is not None and not _int_coercible(v):
            raise ContractError(f"{k} must be an integer (or null), got {v!r}")


def _stored_list(state: dict, key: str) -> list:
    """A stored LIST_FIELD value as a list (null -> []); ContractError if a hand-edit left a
    scalar there (``completed_phases: 3`` / ``commits: abc``) — never iterate/guess it."""
    val = state.get(key)
    if val is None:
        return []
    if isinstance(val, list):
        return list(val)
    raise ContractError(f"{key} in the state file is not a list: {val!r} — repair it with `set`")


def apply_patch(state: dict, patch: dict, allow_started_at: bool = False) -> dict:
    """Apply a JSON patch in place. Returns {'changed': [...], 'appended': {field: n}}.

    All validation runs BEFORE any mutation, so a rejected patch never half-applies
    (callers write the file only after this returns — it stays untouched on rejection).
    """
    if not isinstance(patch, dict):
        raise UsageError("--json payload must be a JSON object")
    patch = dict(patch)
    appended: dict = {}
    ap = patch.pop("_append", None)
    if ap is not None:
        if not isinstance(ap, dict):
            raise UsageError("_append must map list-field names to lists")
        for field, vals in ap.items():
            if field not in LIST_FIELDS:
                raise UsageError(f"_append target is not a list field: {field}")
            if not isinstance(vals, list):
                raise UsageError(f"_append values for {field} must be a list")
            if field in patch:
                raise ContractError(
                    f"key {field} appears in both the patch and _append — "
                    "the direct set would clobber the appended values")
    _validate_patch(patch)
    if ap:
        for field, vals in ap.items():
            state[field] = _stored_list(state, field) + vals
            appended[field] = len(vals)
    changed = []
    for k, v in patch.items():
        if k == "started_at" and not allow_started_at:
            if v != state.get("started_at"):
                raise ContractError(
                    "refusing to change started_at — it is stamped once at init and never rewritten")
            continue
        if k in MAP_FIELDS and isinstance(v, dict) and isinstance(state.get(k), dict):
            merged = dict(state[k])
            merged.update(v)
            state[k] = merged
        else:
            state[k] = _coerce(k, v)                     # store int-coercible strings as ints
        changed.append(k)
    if patch.get("status") == "done" and "completed_at" not in patch and not state.get("completed_at"):
        state["completed_at"] = _now_iso()
        changed.append("completed_at")
    return {"changed": sorted(set(changed)), "appended": appended}


# --------------------------------------------------------------------------- #
# Subcommands
# --------------------------------------------------------------------------- #
def cmd_init(state_file: Path, payload: dict) -> dict:
    if state_file.exists():
        raise ContractError(
            f"state file already exists: {state_file} — resume must never re-init (use `set`)")
    state = default_state()
    apply_patch(state, payload, allow_started_at=True)
    if not state.get("started_at"):
        state["started_at"] = _now_iso()
    write_state(state_file, state)
    return {"ok": True, "action": "init", "state_file": str(state_file),
            "story_key": state.get("story_key"), "started_at": state["started_at"]}


def cmd_set(state_file: Path, patch: dict) -> dict:
    state = _read_existing(state_file)
    info = apply_patch(state, patch)
    write_state(state_file, state)
    return {"ok": True, "action": "set", "state_file": str(state_file),
            "changed": info["changed"], "appended": info["appended"],
            "status": state.get("status"), "completed_at": state.get("completed_at")}


def cmd_phase_done(state_file: Path, phase: int, patch: dict | None) -> dict:
    state = _read_existing(state_file)
    if patch and "completed_phases" in patch:
        # The patch is applied after the append below, so a completed_phases
        # value would silently clobber the phase this very call records.
        raise ContractError(
            "phase-done owns completed_phases — drop it from the patch "
            "(the phase argument is the only way this command records one)")
    phases = [p for p in _stored_list(state, "completed_phases")
              if isinstance(p, int) and not isinstance(p, bool)]
    already = phase in phases
    if not already:
        phases.append(phase)
    state["completed_phases"] = sorted(set(phases))
    info = apply_patch(state, patch) if patch else {"changed": [], "appended": {}}
    write_state(state_file, state)
    return {"ok": True, "action": "phase-done", "state_file": str(state_file),
            "phase": phase, "already_done": already,
            "completed_phases": state["completed_phases"],
            "changed": info["changed"], "appended": info["appended"]}


def cmd_timing_start(state_file: Path) -> dict:
    state = _read_existing(state_file)
    dropped = state.get("timing_anchor") is not None
    state["timing_anchor"] = _now_epoch()
    write_state(state_file, state)
    return {"ok": True, "action": "timing-start", "state_file": str(state_file),
            "timing_anchor": state["timing_anchor"], "dropped_anchor": dropped}


def _stored_int(state: dict, key: str):
    """A stored INT_FIELD value as int|None; ContractError if corrupt beyond _coerce's repair."""
    val = _coerce(key, state.get(key))
    if val is None or (isinstance(val, int) and not isinstance(val, bool)):
        return val
    raise ContractError(f"{key} in the state file is not an integer: {val!r} — repair the file")


def cmd_timing_pause(state_file: Path) -> dict:
    state = _read_existing(state_file)
    anchor = _stored_int(state, "timing_anchor")
    if anchor is None:
        raise ContractError("timing-pause without an anchor — call timing-start first")
    delta = max(0, _now_epoch() - anchor)
    state["active_seconds"] = (_stored_int(state, "active_seconds") or 0) + delta
    state["timing_anchor"] = None
    write_state(state_file, state)
    return {"ok": True, "action": "timing-pause", "state_file": str(state_file),
            "added_seconds": delta, "active_seconds": state["active_seconds"]}


# ----- report-section -------------------------------------------------------- #
def _fmt_dur(seconds) -> str:
    seconds = max(0, int(seconds))
    h, m = divmod(seconds // 60, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def _parse_iso(ts: str):
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _timing_line(state: dict, resumed: int) -> str:
    started = state.get("started_at")
    start_dt = _parse_iso(started) if started else None
    if start_dt is None:
        return "**Timing:** (none — started_at not recorded)."
    completed = state.get("completed_at")
    end_dt = _parse_iso(completed) if completed else None
    completed_text = completed if end_dt else "in progress"
    end = end_dt or _parse_iso(_now_iso()) or datetime.now(timezone.utc)
    elapsed = int((end - start_dt).total_seconds())
    active = _stored_int(state, "active_seconds") or 0    # corrupt -> ContractError, not a traceback
    wait = max(0, elapsed - active)
    suffix = f"; resumed {resumed}×" if resumed >= 1 else ""
    return (f"**Timing:** started {started}; completed {completed_text} — elapsed "
            f"{_fmt_dur(elapsed)} (≈{_fmt_dur(active)} AI-run, ≈{_fmt_dur(wait)} human/idle wait)"
            f"{suffix}.")


def _prose(payload: dict, key: str, default: str) -> str:
    v = payload.get(key)
    if isinstance(v, list):
        v = ", ".join(str(x) for x in v)
    v = (str(v).strip() if v is not None else "")
    return v or default


def _list_block(label: str, items, trailing: str = "") -> list:
    if isinstance(items, str):                  # a single prose line: one item, not per-char
        items = [items]
    clean = [str(x).strip() for x in (items or []) if str(x).strip()]
    if not clean and not trailing:
        return [f"{label} (none)"]
    out = [label]
    out += [f"{i}. {it}" for i, it in enumerate(clean, 1)]
    if trailing:
        out.append(trailing)
    return out


def _story_label(state: dict) -> str:
    """``story_num`` plus the split suffix when the key carries one (``6`` / ``6a``)."""
    return f"{state.get('story_num')}{state.get('story_suffix') or ''}"


def _short_sha(sha) -> str:
    s = str(sha or "").strip()
    if not s:
        return "unknown"
    return s[:7] if re.fullmatch(r"[0-9a-fA-F]{7,}", s) else s


# The full report-section payload vocabulary (state-and-resume.md names these
# next to the Section template). Unknown keys are REJECTED, not ignored: every
# template line renders "(none)" for a missing key, so a misspelled key would
# silently drop its content from the committed, PR-visible report.
REPORT_PAYLOAD_KEYS = frozenset((
    "disposition_tag", "pipeline_status", "continues", "phases_run", "skipped",
    "overrides", "tea", "build", "review", "retro", "open_questions", "deferred_work",
    "deferred_archived_note", "needs_human", "next", "head_sha",
))


def render_section(state: dict, payload: dict, timestamp: str, resumed: int) -> str:
    unknown = sorted(set(payload) - REPORT_PAYLOAD_KEYS)
    if unknown:
        raise UsageError(
            "unknown report-section payload key(s): " + ", ".join(unknown)
            + " — every missing key renders '(none)', so a misnamed one would "
            "silently drop its content; valid keys: " + ", ".join(sorted(REPORT_PAYLOAD_KEYS)))
    tag = str(payload.get("disposition_tag") or "").strip().strip("()")
    if not tag:
        raise UsageError("report-section payload needs a non-empty disposition_tag")
    first, last = bool(state.get("is_first_in_epic")), bool(state.get("is_last_in_epic"))
    pos = ("first-and-last-in-epic" if first and last
           else "first-in-epic" if first else "last-in-epic" if last else "mid-epic")
    lines = [
        f"## Report — {timestamp} ({tag})",
        "",
        f"**Story:** `{state.get('story_key')}` (epic {state.get('epic_num')}, "
        f"story {_story_label(state)}) — {pos}.",
        f"**Spec:** `{state.get('spec_path')}`" if state.get("spec_path") else "**Spec:** (none)",
        f"**Branch:** `{state.get('branch') or '(unknown)'}` "
        f"(HEAD `{_short_sha(payload.get('head_sha'))}`).",
        f"**Pipeline status:** {_prose(payload, 'pipeline_status', '(none)')}",
        f"**Continues:** {_prose(payload, 'continues', '(none — first run)')}",
        "",
        _timing_line(state, resumed),
        "",
        f"**Phases run:** {_prose(payload, 'phases_run', '(none)')}",
        f"**Skipped:** {_prose(payload, 'skipped', '(none)')}",
        "",
        f"**Overrides:** {_prose(payload, 'overrides', 'none')}",
        "",
        f"**TEA:** {_prose(payload, 'tea', '(none)')}",
        "",
        f"**Build:** {_prose(payload, 'build', 'not run')}",
        "",
        f"**Review:** {_prose(payload, 'review', 'skipped')}",
        "",
        f"**Retrospective:** {_prose(payload, 'retro', '(none)')}",
        "",
        *_list_block("**Open questions:**", payload.get("open_questions")),
        "",
        *_list_block("**Deferred work:**", payload.get("deferred_work"),
                     str(payload.get("deferred_archived_note") or "").strip()),
        "",
        *_list_block("**⚠️ Needs human:**", payload.get("needs_human")),
        "",
        f"**Next:** {_prose(payload, 'next', '(none)')}",
    ]
    return "\n".join(lines) + "\n"


# The epic-mode report payload vocabulary (the single epic report, NOT per story).
# Same reject-unknown discipline as REPORT_PAYLOAD_KEYS: a misspelled list key would
# silently drop its content from the committed, PR-visible epic report.
EPIC_REPORT_PAYLOAD_KEYS = frozenset((
    "disposition_tag", "pipeline_status", "continues", "epic_summary",
    "story_rollup", "stories_skipped", "epic_gate", "tea", "retro",
    "overrides", "open_questions", "deferred_work", "deferred_archived_note",
    "needs_human", "next", "head_sha",
))


def render_epic_section(state: dict, payload: dict, timestamp: str, resumed: int) -> str:
    """Render the epic-rollup report section (one epic, all its stories) — the
    epic analog of render_section, keyed off the epic anchor state file."""
    unknown = sorted(set(payload) - EPIC_REPORT_PAYLOAD_KEYS)
    if unknown:
        raise UsageError(
            "unknown epic report-section payload key(s): " + ", ".join(unknown)
            + " — every missing key renders '(none)', so a misnamed one would "
            "silently drop its content; valid keys: " + ", ".join(sorted(EPIC_REPORT_PAYLOAD_KEYS)))
    tag = str(payload.get("disposition_tag") or "").strip().strip("()")
    if not tag:
        raise UsageError("epic report-section payload needs a non-empty disposition_tag")
    count = state.get("epic_story_count")
    count_text = f"{count} stories" if count else "stories"
    lines = [
        f"## Report — {timestamp} ({tag})",
        "",
        f"**Epic:** `{state.get('epic_num')}` — {count_text}.",
        f"**Branch:** `{state.get('branch') or '(unknown)'}` "
        f"(HEAD `{_short_sha(payload.get('head_sha'))}`).",
        f"**Pipeline status:** {_prose(payload, 'pipeline_status', '(none)')}",
        f"**Continues:** {_prose(payload, 'continues', '(none — first run)')}",
        "",
        f"**Summary:** {_prose(payload, 'epic_summary', '(none)')}",
        "",
        _timing_line(state, resumed),
        "",
        *_list_block("**Stories:**", payload.get("story_rollup")),
        "",
        *_list_block("**Skipped:**", payload.get("stories_skipped")),
        "",
        f"**Epic gate:** {_prose(payload, 'epic_gate', '(none)')}",
        "",
        f"**TEA:** {_prose(payload, 'tea', '(none)')}",
        "",
        f"**Retrospective:** {_prose(payload, 'retro', '(none)')}",
        "",
        f"**Overrides:** {_prose(payload, 'overrides', 'none')}",
        "",
        *_list_block("**Open questions:**", payload.get("open_questions")),
        "",
        *_list_block("**Deferred work:**", payload.get("deferred_work"),
                     str(payload.get("deferred_archived_note") or "").strip()),
        "",
        *_list_block("**⚠️ Needs human:**", payload.get("needs_human")),
        "",
        f"**Next:** {_prose(payload, 'next', '(none)')}",
    ]
    return "\n".join(lines) + "\n"


def cmd_report_section(report_file: Path, state_file: Path, payload: dict,
                       overwrite_confirmed: bool,
                       allow_missing_state: bool = False,
                       epic: bool = False) -> dict:
    if allow_missing_state and not state_file.is_file():
        # Pre-init hard-stop (Phase 0): the state file is only created by
        # Phase 1's `init`, but "always produce a report" still holds. Render
        # against a default state keyed off the state file's name; Story/
        # Branch/Timing lines show their not-started defaults.
        state = default_state()
        state["story_key"] = state_file.stem
    else:
        state = _read_existing(state_file)
    timestamp = _now_iso()
    existing = report_file.read_text(encoding="utf-8") if report_file.is_file() else ""
    prior_sections = 0 if overwrite_confirmed else sum(
        1 for ln in existing.splitlines() if ln.startswith("## Report — "))
    # The epic-rollup template (one epic, all its stories) vs the per-story one.
    section = (render_epic_section if epic else render_section)(state, payload, timestamp, prior_sections)
    title = f"# auto-bmad {'epic ' if epic else ''}report log — {state.get('story_key')}\n"
    if overwrite_confirmed or not existing.strip():
        content = title + "\n" + section
    else:
        content = existing.rstrip("\n") + "\n\n" + section
    _atomic_write(report_file, content)
    return {"ok": True, "action": "report-section", "section_written": True,
            "report_file": str(report_file), "timestamp": timestamp,
            "disposition_tag": f"({str(payload.get('disposition_tag')).strip().strip('()')})",
            "overwrote": bool(overwrite_confirmed and existing.strip())}


# --------------------------------------------------------------------------- #
# Lockstep: parse the live schema block out of references/state-and-resume.md
# --------------------------------------------------------------------------- #
def _doc_schema_fields() -> tuple:
    """Return (top-level fields, {map_field: [sub-keys]}) parsed from the doc's fenced
    ``state/{key}.yaml`` block — the 2-space sub-keys are collected for every map
    field with a closed key set (``phase8_steps`` / ``build`` / ``retro``)."""
    doc = Path(__file__).resolve().parent.parent / "references" / "state-and-resume.md"
    text = doc.read_text(encoding="utf-8")
    sec = text.index("## state/{key}.yaml")
    fence = text.index("```yaml", sec)
    body_start = text.index("\n", fence) + 1
    body = text[body_start: text.index("```", body_start)]
    fields: list = []
    subkeys: dict = {k: [] for k in _FIXED_MAP_KEYS}
    current = None
    for line in body.splitlines():
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):", line)
        if m:
            fields.append(m.group(1))
            current = m.group(1) if m.group(1) in subkeys else None
            continue
        if current:
            sm = re.match(r"^  ([A-Za-z_][A-Za-z0-9_]*):", line)
            if sm:
                subkeys[current].append(sm.group(1))
            elif line.strip() and not line.lstrip().startswith("#"):
                current = None
    return fields, subkeys


# --------------------------------------------------------------------------- #
# Self-test
# --------------------------------------------------------------------------- #
def _run_self_test() -> int:  # noqa: C901 — fixture-driven, intentionally exhaustive
    import contextlib
    import io
    import tempfile

    g = globals()
    real_epoch, real_iso = _now_epoch, _now_iso
    clock = {"epoch": 1_700_000_000, "iso": "2026-05-28T13:55:02Z"}
    g["_now_epoch"] = lambda: clock["epoch"]
    g["_now_iso"] = lambda: clock["iso"]
    try:
        with tempfile.TemporaryDirectory(prefix="state_update_") as td:
            tmp = Path(td)

            # --- lockstep with the live doc schema block -------------------- #
            doc_fields, doc_sub = _doc_schema_fields()
            assert set(doc_fields) == set(SCHEMA_ORDER), (
                "schema drift vs state-and-resume.md: doc-only="
                f"{sorted(set(doc_fields) - set(SCHEMA_ORDER))} writer-only="
                f"{sorted(set(SCHEMA_ORDER) - set(doc_fields))}")
            assert len(doc_fields) == len(set(doc_fields)), "duplicate field in doc schema block"
            assert tuple(doc_fields) == SCHEMA_ORDER, (
                f"doc field ORDER drifted from SCHEMA_ORDER: {doc_fields}")
            assert tuple(doc_sub["phase8_steps"]) == PHASE8_KEYS, (
                f"phase8_steps sub-keys drifted: {doc_sub['phase8_steps']}")
            assert tuple(doc_sub["build"]) == BUILD_KEYS, f"build sub-keys drifted: {doc_sub['build']}"
            assert tuple(doc_sub["retro"]) == RETRO_KEYS, f"retro sub-keys drifted: {doc_sub['retro']}"
            # removed review-loop / project-context / retro-notes fields must stay gone
            for gone in ("code_review_iterations", "code_review_loop_done",
                         "external_review_iterations", "convergence_unverified",
                         "needs_project_context_bootstrap"):
                assert gone not in SCHEMA_ORDER and gone not in doc_fields, gone
                assert gone not in INT_FIELDS and gone not in BOOL_FIELDS, gone
            assert "project_context" not in PHASE8_KEYS
            assert set(default_build()) == set(BUILD_KEYS) and set(default_retro()) == set(RETRO_KEYS)
            assert INT_FIELDS <= set(SCHEMA_ORDER) and BOOL_FIELDS <= set(SCHEMA_ORDER)
            assert MAP_FIELDS <= set(SCHEMA_ORDER) and LIST_FIELDS <= set(SCHEMA_ORDER)
            assert not (INT_FIELDS & BOOL_FIELDS) and not (MAP_FIELDS & LIST_FIELDS)
            assert set(_FIXED_MAP_KEYS) <= MAP_FIELDS
            dflt = default_state()
            assert dflt["story_suffix"] == "" and dflt["spec_path"] is None, dflt
            assert dflt["spec_approved"] is False and dflt["review_unverified"] is False, dflt
            assert dflt["followup_passes"] == 0 and dflt["bmad_status_flipped_at"] is None, dflt
            assert dflt["hitl_halt"] is None and dflt["build"]["warnings"] == [], dflt
            assert dflt["retro"] == {"doc": None, "verdict": None, "open_action_items": 0}, dflt

            # --- init: full shape, started_at stamped once ------------------ #
            sf = tmp / "state" / "1-2-user-auth.yaml"
            res = cmd_init(sf, {"story_key": "1-2-user-auth", "epic_num": 1, "story_num": 2,
                                "branch": "story/1-2-user-auth", "is_last_in_epic": True,
                                "git_mode": "remote", "base_branch": "main",
                                "tea_risk": "high", "tea_selected": ["atdd", "automate"],
                                "tea_rationale": "touches auth -> High risk",
                                "epic_story_count": 12, "stories_after_in_epic": 0,
                                "overrides": {"start_phase": "5"}})
            assert res["ok"] and res["started_at"] == "2026-05-28T13:55:02Z", res
            text = sf.read_text(encoding="utf-8")
            for k in SCHEMA_ORDER:
                assert re.search(rf"^{k}:", text, re.M), f"init dropped schema field {k}"
            assert re.search(r'^story_suffix: ""$', text, re.M), "empty suffix must be an explicit \"\""
            st = full_state(load_state(sf))
            assert st["status"] == "in-progress" and st["active_seconds"] == 0, st
            assert st["timing_anchor"] is None and st["completed_at"] is None, st
            assert st["phase8_steps"] == {k: None for k in PHASE8_KEYS}, st["phase8_steps"]
            assert st["build"] == default_build() and st["retro"] == default_retro(), st
            assert st["story_suffix"] == "" and st["spec_path"] is None, st
            assert st["tea_selected"] == ["atdd", "automate"], st["tea_selected"]
            assert st["ci_status"] == "unknown" and st["overrides"] == {"start_phase": "5"}, st
            # re-init refused (contract: resume must never re-init)
            try:
                cmd_init(sf, {"story_key": "1-2-user-auth"})
                raise AssertionError("re-init must raise ContractError")
            except ContractError:
                pass

            # --- set: merge, _append, started_at guard, done stamp ---------- #
            cmd_set(sf, {"followup_passes": 1, "overrides": {"skip": "tea"},
                         "spec_path": "/abs/impl/spec-1-2-user-auth.md",
                         "_append": {"commits": ["a1b2c3d"],
                                     "open_questions": ["Should X use Y: or Z?"]}})
            st = full_state(load_state(sf))
            assert st["overrides"] == {"start_phase": "5", "skip": "tea"}, st["overrides"]
            assert st["commits"] == ["a1b2c3d"], st["commits"]
            assert st["open_questions"] == ["Should X use Y: or Z?"], st["open_questions"]
            assert st["spec_path"] == "/abs/impl/spec-1-2-user-auth.md", st["spec_path"]
            cmd_set(sf, {"_append": {"commits": ["e4f5g6h"]}})
            st = full_state(load_state(sf))
            assert st["commits"] == ["a1b2c3d", "e4f5g6h"], st["commits"]
            assert st["followup_passes"] == 1, st
            try:
                cmd_set(sf, {"started_at": "1999-01-01T00:00:00Z"})
                raise AssertionError("started_at rewrite must raise ContractError")
            except ContractError:
                pass
            cmd_set(sf, {"started_at": st["started_at"]})        # equal value: no-op, allowed
            # one-level map merge + nullable map + map with a list value
            cmd_set(sf, {"phase8_steps": {"trace_gate": "waived"},
                         "story_trace": {"verdict": "CONCERNS",
                                         "uncovered": ["AC3: rate limit"], "ran": True}})
            st = full_state(load_state(sf))
            assert st["phase8_steps"]["trace_gate"] == "waived", st["phase8_steps"]
            assert st["phase8_steps"]["retro"] is None, st["phase8_steps"]
            assert st["story_trace"] == {"verdict": "CONCERNS",
                                         "uncovered": ["AC3: rate limit"], "ran": True}, st["story_trace"]
            # build / retro: one-level merge keeps the untouched sub-keys; a list value
            # inside a MAP field (build.warnings) round-trips through emit/parse
            cmd_set(sf, {"build": {"status": "done", "review_loop_iteration": 2,
                                   "warnings": ["oversized", "multiple-goals"],
                                   "deferred_count": 3}})
            st = full_state(load_state(sf))
            assert st["build"] == {"status": "done", "blocking_condition": None,
                                   "followup_review_recommended": False,
                                   "review_loop_iteration": 2, "deferred_count": 3,
                                   "warnings": ["oversized", "multiple-goals"]}, st["build"]
            bl = next(ln for ln in sf.read_text(encoding="utf-8").splitlines()
                      if ln.startswith("  warnings:"))
            assert bl == "  warnings: [oversized, multiple-goals]", bl
            cmd_set(sf, {"build": {"status": "blocked",
                                   "blocking_condition": "unclear intent: which API? #2",
                                   "warnings": []}})
            st = full_state(load_state(sf))
            assert st["build"]["status"] == "blocked" and st["build"]["warnings"] == [], st["build"]
            assert st["build"]["blocking_condition"] == "unclear intent: which API? #2", st["build"]
            assert st["build"]["review_loop_iteration"] == 2, "merge must keep untouched sub-keys"
            cmd_set(sf, {"retro": {"doc": "/abs/impl/epic-1-retro-2026-05-28.md",
                                   "verdict": "accepted-with-open-items", "open_action_items": 2},
                         "hitl_halt": "auto-continued (epic — no halt)",
                         "review_unverified": True, "bmad_status_flipped_at": 8,
                         "spec_approved": True, "story_suffix": "a"})
            st = full_state(load_state(sf))
            assert st["retro"] == {"doc": "/abs/impl/epic-1-retro-2026-05-28.md",
                                   "verdict": "accepted-with-open-items",
                                   "open_action_items": 2}, st["retro"]
            assert st["hitl_halt"] == "auto-continued (epic — no halt)", st["hitl_halt"]
            assert st["review_unverified"] is True and st["spec_approved"] is True, st
            assert st["bmad_status_flipped_at"] == 8 and st["story_suffix"] == "a", st
            # unknown field (an epic-anchor extra, or a field an older schema wrote) is kept verbatim
            cmd_set(sf, {"batch_flip_done": True})
            cmd_set(sf, {"git_mode": "remote"})
            st = full_state(load_state(sf))
            assert st["batch_flip_done"] is True, "extra field dropped on rewrite"
            try:
                cmd_set(sf, {"_append": {"status": ["x"]}})
                raise AssertionError("_append to a non-list field must raise UsageError")
            except UsageError:
                pass
            # status: done auto-stamps completed_at
            clock["iso"] = "2026-05-28T16:01:02Z"
            out = cmd_set(sf, {"status": "done"})
            assert out["completed_at"] == "2026-05-28T16:01:02Z", out

            # --- phase-done: sorted, idempotent, folded patch ---------------- #
            sf2 = tmp / "state" / "1-3-plant-model.yaml"
            cmd_init(sf2, {"story_key": "1-3-plant-model", "epic_num": 1, "story_num": 3})
            cmd_phase_done(sf2, 7, {"followup_passes": 1, "hitl_halt": "continued"})
            r = cmd_phase_done(sf2, 3, None)
            assert r["completed_phases"] == [3, 7], r
            r = cmd_phase_done(sf2, 7, None)
            assert r["already_done"] and r["completed_phases"] == [3, 7], r
            st2 = full_state(load_state(sf2))
            assert st2["followup_passes"] == 1 and st2["hitl_halt"] == "continued", st2
            # a folded patch carrying completed_phases would clobber the phase
            # this very call records — rejected before any write
            before2 = sf2.read_text(encoding="utf-8")
            try:
                cmd_phase_done(sf2, 8, {"completed_phases": [0, 1]})
                raise AssertionError("completed_phases in a phase-done patch must raise")
            except ContractError as exc:
                assert "completed_phases" in str(exc), exc
            assert sf2.read_text(encoding="utf-8") == before2, "rejection must not write"

            # --- timing: bracket, crash tail, pause-without-anchor ----------- #
            clock["epoch"] = 1000
            r = cmd_timing_start(sf2)
            assert r["timing_anchor"] == 1000 and r["dropped_anchor"] is False, r
            clock["epoch"] = 1060
            r = cmd_timing_pause(sf2)
            assert r["added_seconds"] == 60 and r["active_seconds"] == 60, r
            assert full_state(load_state(sf2))["timing_anchor"] is None
            try:
                cmd_timing_pause(sf2)
                raise AssertionError("pause without anchor must raise ContractError")
            except ContractError:
                pass
            clock["epoch"] = 2000
            cmd_timing_start(sf2)                       # ... crash here (anchor left dangling)
            clock["epoch"] = 2300
            r = cmd_timing_start(sf2)                   # resume: re-anchor, drop the tail
            assert r["dropped_anchor"] is True and r["timing_anchor"] == 2300, r
            clock["epoch"] = 2400
            r = cmd_timing_pause(sf2)
            assert r["added_seconds"] == 100 and r["active_seconds"] == 160, r

            # --- migration: older partial file -> full shape on next write --- #
            # (a pre-0.27 file: fields the schema no longer lists ride along as
            # preserved extras — never dropped, never re-interpreted)
            old = tmp / "state" / "9-9-legacy.yaml"
            old.parent.mkdir(parents=True, exist_ok=True)
            old.write_text("story_key: 9-9-legacy\nstatus: in-progress  # mid\n"
                           'updated_at: "2026-01-01T00:00:00Z"\n'
                           'started_at: "2026-01-01T00:00:00Z"\n'
                           "completed_phases: [0, 1]\nactive_seconds: 120\n"
                           "code_review_iterations: 2\nconvergence_unverified: true\n"
                           "phase8_steps:\n  trace_gate: done\n  project_context: done\n"
                           "legacy_note: keep me\n", encoding="utf-8")
            cmd_set(old, {"git_mode": "local"})
            mtext = old.read_text(encoding="utf-8")
            for k in SCHEMA_ORDER:
                assert re.search(rf"^{k}:", mtext, re.M), f"migration missed field {k}"
            mst = full_state(load_state(old))
            assert mst["completed_phases"] == [0, 1] and mst["active_seconds"] == 120, mst
            assert mst["started_at"] == "2026-01-01T00:00:00Z", mst
            assert mst["legacy_note"] == "keep me", "unknown legacy field dropped"
            assert mst["code_review_iterations"] == 2 and mst["convergence_unverified"] is True, (
                "pre-0.27 fields must be preserved verbatim as extras")
            assert mst["review_unverified"] is False, "a legacy field must not feed the new one"
            assert mst["build"] == default_build() and mst["retro"] == default_retro(), mst
            # a legacy phase8 sub-key already in the file is tolerated on read (merge keeps
            # it; the patch validator only guards NEW writes) and the six live markers resolve
            assert mst["phase8_steps"]["trace_gate"] == "done", mst["phase8_steps"]
            assert all(k in mst["phase8_steps"] for k in PHASE8_KEYS), mst["phase8_steps"]

            # --- report-section ---------------------------------------------- #
            rf = tmp / "reports" / "1-2-user-auth.md"
            payload = {"disposition_tag": "final",
                       "pipeline_status": "✅ clean completion.",
                       "phases_run": "Phase 0, Phase 1, Phase 3 (build / ab-deep), Phase 5 (build / ab-deep).",
                       "skipped": "Phase 2 (not epic start), Phase 4 (atdd not selected).",
                       "overrides": "none.", "tea": "automate ran — 6 tests added.",
                       "build": "build-auto: done; review_loop_iteration 2; deferred 3 (harvested "
                                "to ledger); warnings: none; commits by build-auto: 2.",
                       "review": "follow-up passes 1 (followup_review / ab-alt-deep); last pass "
                                 "patch 1 / bad_spec 0 / defer 0 / reject 0; followup still "
                                 "recommended: no; HITL: continued; review_unverified: false.",
                       "retro": "verdict accepted-with-open-items; 2 open action items "
                                "(AI-1 rotate keys; AI-2 index tuning); "
                                "/abs/impl/epic-1-retro-2026-05-28.md",
                       "open_questions": [], "deferred_work": ["Index tuning deferred to 1-4"],
                       "deferred_archived_note": "Phase 8 archived 2 resolved → deferred-work-resolved.md.",
                       "needs_human": [],
                       "next": "Human review: `/bmad-checkpoint-preview https://github.com/o/r/pull/7` "
                               "(spec: `/abs/impl/spec-1-2-user-auth.md`); then `/auto-bmad`.",
                       "head_sha": "a1b2c3d4e5f6"}
            clock["iso"] = "2026-05-28T16:05:00Z"
            r = cmd_report_section(rf, sf, payload, False)
            assert r["section_written"] and r["timestamp"] == "2026-05-28T16:05:00Z", r
            rt = rf.read_text(encoding="utf-8")
            assert rt.startswith("# auto-bmad report log — 1-2-user-auth\n"), rt.splitlines()[0]
            assert "## Report — 2026-05-28T16:05:00Z (final)" in rt, rt
            # story_suffix "a" (set above) renders into the story label
            assert "**Story:** `1-2-user-auth` (epic 1, story 2a) — last-in-epic." in rt, rt
            assert "**Spec:** `/abs/impl/spec-1-2-user-auth.md`" in rt, rt
            assert "**Branch:** `story/1-2-user-auth` (HEAD `a1b2c3d`)." in rt, rt
            assert "**Continues:** (none — first run)" in rt, rt
            # elapsed 13:55:02->16:01:02 = 2h 06m; AI-run 0m; wait 2h 06m; no resume suffix
            assert ("**Timing:** started 2026-05-28T13:55:02Z; completed 2026-05-28T16:01:02Z — "
                    "elapsed 2h 06m (≈0m AI-run, ≈2h 06m human/idle wait).") in rt, rt
            assert "**Build:** build-auto: done; review_loop_iteration 2" in rt, rt
            assert "**Review:** follow-up passes 1" in rt, rt
            assert "**Retrospective:** verdict accepted-with-open-items" in rt, rt
            assert "**Open questions:** (none)" in rt, rt
            assert "1. Index tuning deferred to 1-4" in rt, rt
            assert "Phase 8 archived 2 resolved" in rt, rt
            assert "**⚠️ Needs human:** (none)" in rt, rt
            assert "/bmad-checkpoint-preview" in rt, rt
            labels = ["## Report — ", "**Story:**", "**Spec:**", "**Branch:**",
                      "**Pipeline status:**", "**Continues:**", "**Timing:**", "**Phases run:**",
                      "**Skipped:**", "**Overrides:**", "**TEA:**", "**Build:**", "**Review:**",
                      "**Retrospective:**", "**Open questions:**", "**Deferred work:**",
                      "**⚠️ Needs human:**", "**Next:**"]
            idxs = [rt.index(lb) for lb in labels]
            assert idxs == sorted(idxs), "section headings out of template order"
            for dead in ("**Code review:**", "**UAT:**", "**Planning drift:**"):
                assert dead not in rt, f"removed heading still rendered: {dead}"
            # second append: prior section preserved, resumed 1×, in-progress timing branch
            cmd_set(sf, {"completed_at": None, "active_seconds": 4200})
            clock["iso"] = "2026-05-28T17:55:02Z"
            cmd_report_section(rf, sf, {"disposition_tag": "halted — needs-human",
                                        "needs_human": ["Set the STRIPE_KEY secret"]}, False)
            rt2 = rf.read_text(encoding="utf-8")
            assert rt2.count("## Report — ") == 2 and "(final)" in rt2, "earlier section clobbered"
            assert "(halted — needs-human)" in rt2, rt2
            assert ("completed in progress — elapsed 4h 00m (≈1h 10m AI-run, "
                    "≈2h 50m human/idle wait); resumed 1×.") in rt2, rt2
            # renderer defaults: Build `not run`, Review `skipped`, Retrospective `(none)`,
            # Overrides `none`
            assert "**Build:** not run" in rt2 and "**Review:** skipped" in rt2, rt2
            assert "**Retrospective:** (none)" in rt2 and "**Overrides:** none" in rt2, rt2
            assert "1. Set the STRIPE_KEY secret" in rt2, rt2
            # overwrite requires the flag; with it, the file is rebuilt from scratch
            r = cmd_report_section(rf, sf, {"disposition_tag": "final"}, True)
            assert r["overwrote"] is True, r
            rt3 = rf.read_text(encoding="utf-8")
            assert rt3.count("## Report — ") == 1 and "needs-human" not in rt3, rt3
            assert "resumed" not in rt3, "overwrite must reset the resume count"
            try:
                cmd_report_section(rf, sf, {}, False)
                raise AssertionError("missing disposition_tag must raise UsageError")
            except UsageError:
                pass
            # an unknown payload key must be REJECTED, not silently rendered '(none)'
            # (a misspelled list key would drop its content from the committed report)
            before_rt = rf.read_text(encoding="utf-8")
            try:
                cmd_report_section(rf, sf, {"disposition_tag": "final",
                                            "blockers": ["misnamed needs_human"]}, False)
                raise AssertionError("unknown payload key must raise UsageError")
            except UsageError as exc:
                assert "blockers" in str(exc) and "needs_human" in str(exc), exc
            assert rf.read_text(encoding="utf-8") == before_rt, "rejection must not write"
            # the removed per-story keys are unknown now (allowlist discipline)
            for dead_key in ("code_review", "uat", "planning_drift"):
                try:
                    cmd_report_section(rf, sf, {"disposition_tag": "final", dead_key: "x"}, False)
                    raise AssertionError(f"removed payload key {dead_key} must be rejected")
                except UsageError as exc:
                    assert dead_key in str(exc), exc
            # pre-init hard-stop: --allow-missing-state renders against a default
            # state (story key from the state file name); without it, exit 2 path
            rf0 = tmp / "reports" / "0-9-prestop.md"
            sf0 = tmp / "state" / "0-9-prestop.yaml"
            try:
                cmd_report_section(rf0, sf0, {"disposition_tag": "halted"}, False)
                raise AssertionError("missing state without the flag must raise UsageError")
            except UsageError:
                pass
            r = cmd_report_section(rf0, sf0, {"disposition_tag": "halted — hard-stop",
                                              "pipeline_status": "⛔ dirty tree.",
                                              "needs_human": ["commit or stash, then re-run"]},
                                   False, allow_missing_state=True)
            assert r["section_written"], r
            rt0 = rf0.read_text(encoding="utf-8")
            assert rt0.startswith("# auto-bmad report log — 0-9-prestop\n"), rt0
            assert "(halted — hard-stop)" in rt0 and "⛔ dirty tree." in rt0, rt0
            assert "**Spec:** (none)" in rt0, rt0                 # no spec before Phase 3
            assert "**Timing:** (none — started_at not recorded)." in rt0, rt0
            assert "1. commit or stash, then re-run" in rt0, rt0
            assert not sf0.exists(), "report fallback must never create the state file"

            # --- report-section --epic (the epic-rollup template) ------------ #
            esf = tmp / "state" / "epic" / "epic-1.yaml"
            clock["iso"] = "2026-05-28T13:55:02Z"
            cmd_init(esf, {"story_key": "epic-1", "epic_num": 1,
                           "branch": "epic/1-account-system", "epic_story_count": 4,
                           "epic_slug": "account-system",
                           "active_story": None, "stories_landed": ["1-2-mgmt", "1-3-model"],
                           "batch_flip_done": False})
            # the net-new epic fields ride as preserved extras (no SCHEMA_ORDER change)
            est = full_state(load_state(esf))
            assert est["stories_landed"] == ["1-2-mgmt", "1-3-model"], est.get("stories_landed")
            assert est["active_story"] is None and est["epic_num"] == 1, est
            assert est["epic_slug"] == "account-system" and est["batch_flip_done"] is False, est
            cmd_set(esf, {"review_unverified": True, "bmad_status_flipped_at": 82,
                          "retro": {"verdict": "rejected", "open_action_items": 4},
                          "batch_flip_done": True})
            est = full_state(load_state(esf))
            assert est["bmad_status_flipped_at"] == 82 and est["batch_flip_done"] is True, est
            assert est["retro"]["verdict"] == "rejected" and est["retro"]["open_action_items"] == 4
            erf = tmp / "reports" / "epic-1.md"
            epic_payload = {
                "disposition_tag": "final",
                "pipeline_status": "✅ clean epic completion.",
                "epic_summary": "Delivered the account system across 4 stories.",
                "story_rollup": ["`1-2-mgmt` — build done; review passes 1; deferred 0; trace PASS.",
                                 "`1-3-model` — build done; review passes 1; deferred 2; trace CONCERNS."],
                "stories_skipped": ["`1-1-auth` — already done",
                                    "`1-4-audit` — in-progress outside auto-bmad and has no "
                                    "build-auto spec — skipped"],
                "epic_gate": "trace PASS; nfr CONCERNS; test-review PASS.",
                "tea": "epic automate: 14 tests.",
                "retro": "verdict rejected; 4 open action items; /abs/impl/epic-1-retro-2026-05-28.md",
                "open_questions": [],
                "deferred_work": ["Index tuning -> next epic"],
                "deferred_archived_note": "Archived 3 resolved.",
                "needs_human": ["⚠️ Retrospective verdict: rejected — /abs/impl/epic-1-retro-2026-05-28.md"],
                "next": "`/auto-bmad epic --epic 2`. Project context: run /bmad-project-context "
                        "refresh (recommended after an epic).",
                "head_sha": "abcdef1234"}
            clock["iso"] = "2026-05-28T15:00:00Z"
            r = cmd_report_section(erf, esf, epic_payload, False, epic=True)
            assert r["section_written"], r
            et = erf.read_text(encoding="utf-8")
            assert et.startswith("# auto-bmad epic report log — epic-1\n"), et.splitlines()[0]
            assert "## Report — 2026-05-28T15:00:00Z (final)" in et, et
            assert "**Epic:** `1` — 4 stories." in et, et
            assert "**Branch:** `epic/1-account-system` (HEAD `abcdef1`)." in et, et
            assert "1. `1-2-mgmt` — build done; review passes 1; deferred 0; trace PASS." in et, et
            assert "**Skipped:**\n1. `1-1-auth` — already done\n2. `1-4-audit`" in et, et
            assert "**Epic gate:** trace PASS" in et, et
            assert "**Retrospective:** verdict rejected; 4 open action items" in et, et
            assert "1. Index tuning -> next epic" in et and "Archived 3 resolved." in et, et
            assert "1. ⚠️ Retrospective verdict: rejected" in et, et
            assert "/bmad-project-context refresh" in et, et
            elabels = ["## Report — ", "**Epic:**", "**Branch:**", "**Pipeline status:**",
                       "**Continues:**", "**Summary:**", "**Timing:**", "**Stories:**",
                       "**Skipped:**", "**Epic gate:**", "**TEA:**", "**Retrospective:**",
                       "**Overrides:**", "**Open questions:**", "**Deferred work:**",
                       "**⚠️ Needs human:**", "**Next:**"]
            eidxs = [et.index(lb) for lb in elabels]
            assert eidxs == sorted(eidxs), "epic section headings out of template order"
            for dead in ("**Integration review:**", "**UAT:**", "**Auto-decided", "**Planning drift:**"):
                assert dead not in et, f"removed epic heading still rendered: {dead}"
            # a prose stories_skipped renders as ONE item, not per character
            cmd_report_section(erf, esf, {"disposition_tag": "x",
                                          "stories_skipped": "`1-1-auth` — already done"},
                               False, epic=True)
            et2 = erf.read_text(encoding="utf-8")
            assert "**Skipped:**\n1. `1-1-auth` — already done\n" in et2, et2
            # the per-story template has no story_rollup key (epic-only) — rejected there
            psf = tmp / "state" / "ps-1.yaml"
            cmd_init(psf, {"story_key": "ps-1", "epic_num": 1, "story_num": 1})
            try:
                cmd_report_section(tmp / "reports" / "ps-1.md", psf,
                                   {"disposition_tag": "x", "story_rollup": ["y"]}, False)
                raise AssertionError("story_rollup is epic-only; per-story payload must reject it")
            except UsageError as exc:
                assert "story_rollup" in str(exc), exc
            # the epic template rejects a per-story-only payload key (allowlist discipline)
            try:
                cmd_report_section(erf, esf, {"disposition_tag": "x", "phases_run": "Phase 5"},
                                   False, epic=True)
                raise AssertionError("a per-story key in an epic payload must raise UsageError")
            except UsageError as exc:
                assert "phases_run" in str(exc), exc
            # …and the removed epic keys are unknown now
            for dead_key in ("integration_review", "uat", "auto_decided", "planning_drift"):
                try:
                    cmd_report_section(erf, esf, {"disposition_tag": "x", dead_key: ["y"]},
                                       False, epic=True)
                    raise AssertionError(f"removed epic payload key {dead_key} must be rejected")
                except UsageError as exc:
                    assert dead_key in str(exc), exc

            # --- CLI surface: single JSON object on stdout + exit codes ------- #
            def run_cli(argv):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = main(argv)
                out = buf.getvalue().strip()
                return rc, (json.loads(out) if out else None)

            jf = tmp / "payload.json"
            jf.write_text(json.dumps({"story_key": "2-1-cli", "epic_num": 2, "story_num": 1}),
                          encoding="utf-8")
            sf3 = tmp / "state" / "2-1-cli.yaml"
            rc, out = run_cli(["init", "--state-file", str(sf3), "--json", str(jf)])
            assert rc == 0 and out["ok"] and out["action"] == "init", (rc, out)
            rc, out = run_cli(["init", "--state-file", str(sf3), "--json", str(jf)])
            assert rc == 1 and out["ok"] is False, (rc, out)          # init-exists -> 1
            rc, out = run_cli(["timing-pause", "--state-file", str(sf3)])
            assert rc == 1 and "anchor" in out["error"], (rc, out)    # pause-without-anchor -> 1
            bad = tmp / "bad.json"
            bad.write_text("{not json", encoding="utf-8")
            rc, out = run_cli(["set", "--state-file", str(sf3), "--json", str(bad)])
            assert rc == 2 and out["ok"] is False, (rc, out)          # parse error -> 2
            rc, out = run_cli(["set", "--state-file", str(tmp / "absent.yaml"), "--json", str(jf)])
            assert rc == 2, (rc, out)                                 # missing state file -> 2
            # --json - reads stdin
            stdin_save = sys.stdin
            sys.stdin = io.StringIO(json.dumps({"_append": {"blockers": ["needs API key"]}}))
            try:
                rc, out = run_cli(["set", "--state-file", str(sf3), "--json", "-"])
            finally:
                sys.stdin = stdin_save
            assert rc == 0 and out["appended"] == {"blockers": 1}, (rc, out)
            rc, out = run_cli(["phase-done", "--state-file", str(sf3), "--phase", "5"])
            assert rc == 0 and out["completed_phases"] == [5], (rc, out)
            # the retro-notes writer is gone: its old subcommand is an argparse error (exit 2)
            err_buf = io.StringIO()
            with contextlib.redirect_stderr(err_buf):
                try:
                    main(["retro-append", "--retro-file", str(tmp / "r.md"),
                          "--story-key", "2-1-cli", "--json", str(jf)])
                    raise AssertionError("retro-append must no longer parse")
                except SystemExit as exc:
                    assert exc.code == 2, exc.code
            rc, out = run_cli(["report-section", "--report-file", str(tmp / "reports" / "2-1-cli.md"),
                               "--state-file", str(sf3), "--json", str(jf)])
            assert rc == 2 and "story_key" in out["error"], (rc, out)  # unknown report key -> 2

            # --- patch validation + emit round-trips (findings F1–F6) ---------- #
            def cli_json(payload, *argv0):
                pf = tmp / "f.json"
                pf.write_text(json.dumps(payload), encoding="utf-8")
                return run_cli([*argv0, "--json", str(pf)])

            sfv = tmp / "state" / "3-1-validate.yaml"
            cmd_init(sfv, {"story_key": "3-1-validate", "epic_num": 3, "story_num": 1})
            pristine = sfv.read_text(encoding="utf-8")
            # F1: a map key the reader regex can't parse back is rejected, file untouched
            rc, out = cli_json({"overrides": {"max-followup-passes": 5}},
                               "set", "--state-file", str(sfv))
            assert rc == 1 and "max-followup-passes" in out["error"], (rc, out)
            assert sfv.read_text(encoding="utf-8") == pristine, "F1 rejection must not write"
            rc, out = cli_json({"overrides": {"good_key": 1, "bad key": 2}},
                               "set", "--state-file", str(sfv))
            assert rc == 1 and "bad key" in out["error"], (rc, out)   # mixed keys: still rejected
            assert sfv.read_text(encoding="utf-8") == pristine, "mixed-key rejection must not write"
            try:                                          # init's patch validates the same way
                cmd_init(tmp / "state" / "never.yaml", {"story_trace": {"AC 1": "covered"}})
                raise AssertionError("init with an un-re-readable map key must raise ContractError")
            except ContractError:
                pass
            assert not (tmp / "state" / "never.yaml").exists()
            # …an UNKNOWN preserved field gets the same key checks (top-level + map keys):
            rc, out = cli_json({"custom_metrics": {"build-time": 42}},
                               "set", "--state-file", str(sfv))
            assert rc == 1 and "build-time" in out["error"], (rc, out)
            rc, out = cli_json({"build-time": 42}, "set", "--state-file", str(sfv))
            assert rc == 1 and "build-time" in out["error"], (rc, out)
            assert sfv.read_text(encoding="utf-8") == pristine, "unknown-field rejection must not write"
            # …and a MAP field set to a non-map shape is rejected (a flat scalar would
            # wipe the phase8 resume markers / the build result):
            rc, out = cli_json({"phase8_steps": "done"}, "set", "--state-file", str(sfv))
            assert rc == 1 and "phase8_steps" in out["error"], (rc, out)
            rc, out = cli_json({"build": "done"}, "set", "--state-file", str(sfv))
            assert rc == 1 and "build" in out["error"], (rc, out)
            assert sfv.read_text(encoding="utf-8") == pristine, "non-map rejection must not write"
            # …a typo'd build / retro sub-key is rejected (closed key sets, like phase8_steps)
            rc, out = cli_json({"build": {"satus": "done"}}, "set", "--state-file", str(sfv))
            assert rc == 1 and "satus" in out["error"], (rc, out)
            rc, out = cli_json({"retro": {"verdicts": "accepted"}}, "set", "--state-file", str(sfv))
            assert rc == 1 and "verdicts" in out["error"], (rc, out)
            assert sfv.read_text(encoding="utf-8") == pristine, "sub-key rejection must not write"
            rc, out = cli_json({"build": {"status": "in-review", "followup_review_recommended": True},
                                "retro": {"verdict": "accepted"}}, "set", "--state-file", str(sfv))
            assert rc == 0, (rc, out)                     # the documented sub-keys pass
            # F2: legacy quoted ints in completed_phases are coerced, not dropped
            leg = tmp / "state" / "9-8-quoted.yaml"
            leg.write_text('story_key: 9-8-quoted\nstarted_at: "2026-01-01T00:00:00Z"\n'
                           'completed_phases: ["0", "1", junk]\n', encoding="utf-8")
            r = cmd_phase_done(leg, 2, None)
            assert r["completed_phases"] == [0, 1, 2], r  # quoted ints kept; real junk dropped
            # F3: non-int-coercible INT_FIELD patch rejected at set time …
            rc, out = cli_json({"timing_anchor": "soon"}, "set", "--state-file", str(sfv))
            assert rc == 1 and "timing_anchor" in out["error"], (rc, out)
            rc, out = cli_json({"bmad_status_flipped_at": "nine"}, "set", "--state-file", str(sfv))
            assert rc == 1 and "bmad_status_flipped_at" in out["error"], (rc, out)
            rc, out = cli_json({"active_seconds": "120", "bmad_status_flipped_at": "9"},
                               "set", "--state-file", str(sfv))
            assert rc == 0, (rc, out)                     # int-coercible string: stored as int
            stv = full_state(load_state(sfv))
            assert stv["active_seconds"] == 120 and stv["bmad_status_flipped_at"] == 9, stv
            # … and a hand-corrupted stored anchor pauses with a clean ContractError JSON
            sfv.write_text(sfv.read_text(encoding="utf-8").replace(
                "timing_anchor: null", "timing_anchor: half past nine"), encoding="utf-8")
            rc, out = run_cli(["timing-pause", "--state-file", str(sfv)])
            assert rc == 1 and out["ok"] is False and "timing_anchor" in out["error"], (rc, out)
            cmd_timing_start(sfv)                         # recovery: re-anchor still works
            # F4: phase8_steps typo'd key / off-vocabulary marker rejected
            rc, out = cli_json({"phase8_steps": {"trace_gates": "done"}},
                               "set", "--state-file", str(sfv))
            assert rc == 1 and "trace_gates" in out["error"], (rc, out)
            rc, out = cli_json({"phase8_steps": {"project_context": "done"}},
                               "set", "--state-file", str(sfv))
            assert rc == 1 and "project_context" in out["error"], (rc, out)  # removed sub-step
            rc, out = cli_json({"phase8_steps": {"nfr": "waived"}},
                               "set", "--state-file", str(sfv))
            assert rc == 1 and "waived" in out["error"], (rc, out)    # waived is trace_gate-only
            rc, out = cli_json({"phase8_steps": {"trace_gate": "waived", "retro": "done",
                                                 "nfr": None}},
                               "set", "--state-file", str(sfv))
            assert rc == 0, (rc, out)                     # the documented vocabulary passes
            # F5: direct set + _append of the same field in one patch is rejected
            before = sfv.read_text(encoding="utf-8")
            rc, out = cli_json({"commits": ["zzz"], "_append": {"commits": ["a1"]}},
                               "set", "--state-file", str(sfv))
            assert rc == 1 and "commits" in out["error"], (rc, out)
            assert sfv.read_text(encoding="utf-8") == before, "F5 rejection must not write"
            # F6: a dict element in a flow list degrades to a JSON string and round-trips
            cmd_set(sfv, {"commits": ["a1b2c3d", {"sha": "e4f5", "n": 2}]})
            cline = next(ln for ln in sfv.read_text(encoding="utf-8").splitlines()
                         if ln.startswith("commits:"))
            assert "{'" not in cline, cline               # no Python repr in the file
            els = full_state(load_state(sfv))["commits"]
            assert els[0] == "a1b2c3d" and json.loads(els[1]) == {"sha": "e4f5", "n": 2}, els
            # F7: a list value inside a MAP field with quoted/awkward elements round-trips too
            cmd_set(sfv, {"build": {"warnings": ["oversized", "needs: review", "x #1", ""]}})
            wl = full_state(load_state(sfv))["build"]["warnings"]
            assert wl == ["oversized", "needs: review", "x #1", ""], wl

            # --- stored-shape guards (findings V1–V4) ---------------------------- #
            # V1: a LIST field patched with a scalar is rejected before any write
            # (set, init and phase-done's folded patch alike); null means [] on disk
            sfl = tmp / "state" / "4-1-lists.yaml"
            cmd_init(sfl, {"story_key": "4-1-lists", "epic_num": 4, "story_num": 1})
            pristine_l = sfl.read_text(encoding="utf-8")
            for bad_list in ({"completed_phases": 3}, {"commits": "abc"},
                             {"tea_selected": "atdd"}, {"blockers": "needs key"},
                             {"open_questions": {"q": 1}}):
                rc, out = cli_json(bad_list, "set", "--state-file", str(sfl))
                key = next(iter(bad_list))
                assert rc == 1 and key in out["error"] and "list" in out["error"], (rc, out)
            assert sfl.read_text(encoding="utf-8") == pristine_l, "V1 rejection must not write"
            rc, out = cli_json({"commits": "abc"}, "phase-done", "--state-file", str(sfl),
                               "--phase", "3")
            assert rc == 1 and "commits" in out["error"], (rc, out)
            assert sfl.read_text(encoding="utf-8") == pristine_l, "V1 folded rejection must not write"
            try:
                cmd_init(tmp / "state" / "never2.yaml", {"story_key": "x", "commits": "abc"})
                raise AssertionError("init with a scalar list field must raise ContractError")
            except ContractError:
                pass
            assert not (tmp / "state" / "never2.yaml").exists()
            rc, out = cli_json({"commits": None, "tea_selected": ["atdd"]},
                               "set", "--state-file", str(sfl))
            assert rc == 0, (rc, out)
            assert re.search(r"^commits: \[\]$", sfl.read_text(encoding="utf-8"), re.M), (
                "a null list patch must land as the explicit [] default")
            # V1b: a hand-corrupted stored list -> phase-done / _append answer with an
            # exit-1 JSON naming the field (no traceback); `set` repairs it
            sfl.write_text(sfl.read_text(encoding="utf-8").replace(
                "completed_phases: []", "completed_phases: 3").replace(
                "commits: []", "commits: abc"), encoding="utf-8")
            rc, out = run_cli(["phase-done", "--state-file", str(sfl), "--phase", "3"])
            assert rc == 1 and out["ok"] is False and "completed_phases" in out["error"], (rc, out)
            rc, out = cli_json({"_append": {"commits": ["a1"]}}, "set", "--state-file", str(sfl))
            assert rc == 1 and out["ok"] is False and "commits" in out["error"], (rc, out)
            rc, out = cli_json({"completed_phases": [3], "commits": []},
                               "set", "--state-file", str(sfl))
            assert rc == 0, (rc, out)                     # repair path
            rc, out = run_cli(["phase-done", "--state-file", str(sfl), "--phase", "5"])
            assert rc == 0 and out["completed_phases"] == [3, 5], (rc, out)
            rc, out = cli_json({"_append": {"commits": ["a1"]}}, "set", "--state-file", str(sfl))
            assert rc == 0 and out["appended"] == {"commits": 1}, (rc, out)
            # a legacy `commits: null` line reads as [] and is re-emitted as []
            legl = tmp / "state" / "9-7-nulllist.yaml"
            legl.write_text('story_key: 9-7-nulllist\nstarted_at: "2026-01-01T00:00:00Z"\n'
                            "commits: null\nblockers: ~\n", encoding="utf-8")
            assert full_state(load_state(legl))["commits"] == [], "null list must read as []"
            cmd_set(legl, {"_append": {"blockers": ["needs key"]}})
            lt = legl.read_text(encoding="utf-8")
            assert re.search(r"^commits: \[\]$", lt, re.M), lt
            assert full_state(load_state(legl))["blockers"] == ["needs key"], lt
            # V2: report-section with a hand-corrupted active_seconds -> exit-1 JSON, no traceback
            sfr = tmp / "state" / "4-2-timing.yaml"
            cmd_init(sfr, {"story_key": "4-2-timing", "epic_num": 4, "story_num": 2})
            sfr.write_text(sfr.read_text(encoding="utf-8").replace(
                "active_seconds: 0", "active_seconds: lots"), encoding="utf-8")
            rfr = tmp / "reports" / "4-2-timing.md"
            rc, out = cli_json({"disposition_tag": "final"}, "report-section",
                               "--report-file", str(rfr), "--state-file", str(sfr))
            assert rc == 1 and out["ok"] is False and "active_seconds" in out["error"], (rc, out)
            assert not rfr.exists(), "a rejected report-section must not write the report"
            rc, out = cli_json({"active_seconds": 60}, "set", "--state-file", str(sfr))
            assert rc == 0, (rc, out)                     # repair, then the report renders
            rc, out = cli_json({"disposition_tag": "final"}, "report-section",
                               "--report-file", str(rfr), "--state-file", str(sfr))
            assert rc == 0 and out["section_written"], (rc, out)
            assert "≈1m AI-run" in rfr.read_text(encoding="utf-8")
            # V3: build / retro / phase8_steps are never null — a null patch is rejected …
            sfm = tmp / "state" / "4-3-maps.yaml"
            cmd_init(sfm, {"story_key": "4-3-maps", "epic_num": 4, "story_num": 3})
            pristine_m = sfm.read_text(encoding="utf-8")
            for fixed in ("build", "retro", "phase8_steps"):
                rc, out = cli_json({fixed: None}, "set", "--state-file", str(sfm))
                assert rc == 1 and fixed in out["error"] and "map" in out["error"], (rc, out)
            assert sfm.read_text(encoding="utf-8") == pristine_m, "V3 rejection must not write"
            rc, out = cli_json({"story_trace": None, "overrides": None},
                               "set", "--state-file", str(sfm))
            assert rc == 0, (rc, out)                     # story_trace stays nullable …
            mtxt0 = sfm.read_text(encoding="utf-8")
            assert re.search(r"^story_trace: null$", mtxt0, re.M), mtxt0
            assert re.search(r"^overrides: \{\}$", mtxt0, re.M), "null overrides must land as {}"
            # … and a legacy/hand-edited `build: null` (or a stray scalar) re-emits the
            # full default map on the next write, so a partial merge never lands on disk
            legm = tmp / "state" / "9-6-nullmap.yaml"
            legm.write_text('story_key: 9-6-nullmap\nstarted_at: "2026-01-01T00:00:00Z"\n'
                            "build: null\nretro: pending\nphase8_steps: null\n",
                            encoding="utf-8")
            lm = full_state(load_state(legm))
            assert lm["build"] == default_build() and lm["retro"] == default_retro(), lm
            assert lm["phase8_steps"] == {k: None for k in PHASE8_KEYS}, lm["phase8_steps"]
            cmd_set(legm, {"build": {"status": "done"}})
            lm = full_state(load_state(legm))
            assert lm["build"] == {**default_build(), "status": "done"}, lm["build"]
            mtxt = legm.read_text(encoding="utf-8")
            for sub in BUILD_KEYS:
                assert re.search(rf"^  {sub}:", mtxt, re.M), f"build.{sub} missing on disk"
            for sub in RETRO_KEYS:
                assert re.search(rf"^  {sub}:", mtxt, re.M), f"retro.{sub} missing on disk"

        print("SELF-TEST PASSED (all assertions)")
        return 0
    finally:
        g["_now_epoch"] = real_epoch
        g["_now_iso"] = real_iso


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _load_json_arg(spec: str | None) -> dict | None:
    if spec is None:
        return None
    try:
        raw = sys.stdin.read() if spec == "-" else Path(spec).read_text(encoding="utf-8")
    except OSError as exc:
        raise UsageError(f"cannot read --json {spec}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UsageError(f"--json is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise UsageError("--json payload must be a JSON object")
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic writer for auto-bmad state files and report sections.")
    parser.add_argument("--self-test", action="store_true", help="run built-in fixtures and exit")
    sub = parser.add_subparsers(dest="cmd")

    def add(name, state=True, js=None, **extra):
        p = sub.add_parser(name)
        if state:
            p.add_argument("--state-file", required=True)
        if js is not None:
            p.add_argument("--json", dest="json_arg", required=js, metavar="-|FILE")
        for arg, kw in extra.items():
            p.add_argument(f"--{arg.replace('_', '-')}", **kw)
        return p

    add("init", js=True)
    add("set", js=True)
    add("phase-done", js=False, phase={"type": int, "required": True})
    add("timing-start")
    add("timing-pause")
    add("report-section", js=True,
        report_file={"required": True},
        epic={"action": "store_true",
              "help": "render the epic-rollup template (one epic, all its stories) "
                      "keyed off the epic anchor, not the per-story template"},
        overwrite_confirmed={"action": "store_true"},
        allow_missing_state={"action": "store_true",
                             "help": "pre-init hard-stop (Phase 0): render with a "
                                     "default state instead of erroring"})

    args = parser.parse_args(argv)
    if args.self_test:
        return _run_self_test()
    if not args.cmd:
        parser.error("a subcommand is required (or --self-test)")

    try:
        payload = _load_json_arg(getattr(args, "json_arg", None))
        if args.cmd == "init":
            result = cmd_init(Path(args.state_file), payload)
        elif args.cmd == "set":
            result = cmd_set(Path(args.state_file), payload)
        elif args.cmd == "phase-done":
            result = cmd_phase_done(Path(args.state_file), args.phase, payload)
        elif args.cmd == "timing-start":
            result = cmd_timing_start(Path(args.state_file))
        elif args.cmd == "timing-pause":
            result = cmd_timing_pause(Path(args.state_file))
        else:  # report-section
            result = cmd_report_section(Path(args.report_file), Path(args.state_file),
                                        payload, args.overwrite_confirmed,
                                        args.allow_missing_state, args.epic)
    except ContractError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    except UsageError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
