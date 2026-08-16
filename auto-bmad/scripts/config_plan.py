#!/usr/bin/env python3
"""Detect (and additively heal) drift between auto-bmad's shipped config defaults
and a project's runtime ``config.yaml``.

The runtime config (``{output_folder}/auto-bmad/config.yaml``) is seeded **once**
at first run by copying the ``profiles:`` and ``phase_profiles:`` blocks from
``assets/profiles.yaml`` verbatim, and stamping ``profiles_source_version``
with the module version. A later module update ships NEW keys (e.g. a new
``phase_profiles`` mapping like ``followup_review``) into the asset — but nothing
ever re-touches the runtime copy, so the project silently runs on a stale snapshot.

Nothing else reads ``phase_profiles`` before a phase resolves its profile at spawn
time, so a phase whose mapping is missing from the runtime config has no profile to
resolve, and no other check flags it. This script closes that gap: it diffs the
asset's ``profiles`` / ``phase_profiles`` *keys* against the runtime config's, and
compares ``profiles_source_version`` against the installed ``module_version``.

Two modes (plus ``--reset``, see below):
  --check   read-only; report what drifted. Exit 0 fresh, 1 drift, 2 usage error.
  --apply   additively heal: append asset keys the config is MISSING (never touch
            or overwrite a key the user already has — retunes are preserved), then
            restamp ``profiles_source_version``. Writes the config in place.

What ``--apply`` heals automatically (the realistic, safe-to-append cases):
  * ``phase_profiles`` keys present in the asset but absent from the config
    (appended as ``  key: value`` lines at the end of that block);
  * whole ``profiles`` entries present in the asset but absent from the config
    (the asset's raw block is copied verbatim to the end of the ``profiles:`` block);
  * **constant-default setup-block keys** (``delegation``/``tea``/``git``/``code_review``/``build``)
    present in the second asset ``assets/config-defaults.yaml`` but absent from the config,
    at any depth — a missing scalar, a missing sub-block, or a missing whole block (see
    ``plan_setup``). The setup blocks are otherwise SETUP ANSWERS with no asset source, so a
    new setup key shipped by an update never reaches an existing config; this closes that gap.
    Append-only like the above (a key already present is never touched), and that asset
    deliberately excludes environment-detected fields (``git.base_branch``,
    ``code_review.cross_model_layer``, ...) so the heal can't bake in a wrong static guess.
What it reports but does NOT rewrite (``manual_review`` — rare, value-bearing, and
a mid-block insert would risk mangling a user-edited profile): sub-keys missing
from a profile that already exists in the config (e.g. the asset added a new tool
block to an existing profile). The orchestrator surfaces these.

Stale keys — a removed ``phase_profiles`` mapping or a per-profile sub-key the asset's
profile shape no longer carries (an old persona string, say) — are IGNORED, never stripped
by ``--check``/``--apply``: reported informationally as ``stale_phase_profiles`` /
``stale_profile_keys`` (not part of the drift verdict); only ``--reset`` prunes them.
Unknown top-level keys and unknown setup-block keys are likewise left alone.

Profile names are free-form: any name works (custom profiles are first-class — the heal
passes them through untouched, ``custom_profiles`` reports them, a whole-block reset prunes
them, a single-profile reset keeps them). Profiles carry model/effort blocks ONLY
(``claude.model``/``claude.effort``, ``codex.model``/``codex.reasoning_effort``,
``opencode.model``/``opencode.variant``) — no persona text.

``--reset [SCOPE] [--write]`` restores the shipped ``profiles`` / ``phase_profiles`` (never
the setup blocks); its JSON carries ``layers_sync_needed`` — true when the plan changes any
profile (or prunes one) or remaps ``phase_profiles.security_layer`` /
``phase_profiles.cross_model_layer``, i.e. when the review-layers TOML that bakes those
profiles' models must be re-synced (``build_auto_custom.py --apply``).

Parsing is dependency-free (same block-structured spirit as ``cli_delegate.py`` /
``story_plan.py``) so no PyYAML is needed. Output: a single JSON object on stdout.

Usage:
    config_plan.py --check --config FILE [--asset-profiles FILE] [--asset-config-defaults FILE] [--module-yaml FILE | --module-version X.Y.Z]
    config_plan.py --apply --config FILE [--asset-profiles FILE] [--asset-config-defaults FILE] [--module-yaml FILE | --module-version X.Y.Z]
    config_plan.py --reset [SCOPE] [--write] --config FILE [--asset-profiles FILE] [--module-yaml FILE | --module-version X.Y.Z]
    config_plan.py --self-test
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path


class ConfigIOError(Exception):
    """A config/asset file could not be read or written (missing, unreadable, not UTF-8).

    Raised by ``_read_text``/``_write_text`` so ``main()`` can turn any of them into the
    documented ``{"status": "error", ...}`` JSON + exit 2 instead of a traceback.
    """


def _read_text(path: Path) -> str:
    """Read a text file WITHOUT newline translation (``newline=""``).

    Byte preservation: the default universal-newlines read would turn a CRLF config's
    ``\\r\\n`` into ``\\n``, and writing it back would silently rewrite every line ending of
    a file this script only appends to. Keeping the endings verbatim means the untouched
    lines round-trip byte-for-byte. Raises ``ConfigIOError`` on an unreadable / non-UTF-8 file.
    """
    try:
        with open(path, "r", encoding="utf-8", newline="") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ConfigIOError(f"cannot read {path}: {type(exc).__name__}: {exc}") from exc


def _write_text(path: Path, text: str) -> None:
    """Write text back WITHOUT newline translation (the ``_read_text`` counterpart)."""
    try:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    except (OSError, UnicodeEncodeError, ValueError) as exc:
        raise ConfigIOError(f"cannot write {path}: {type(exc).__name__}: {exc}") from exc


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
    """Locate a top-level ``name:`` block.

    Returns ``(header_idx, body_end)`` where the body is ``lines[header_idx+1:body_end]``
    and ``body_end`` is the first non-blank, non-comment, indent-0 line after the
    header (or ``len(lines)``). Blank lines and full-line comments are transparent —
    they never terminate a block. Returns ``None`` if the block is absent.
    """
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


def _last_content_idx(lines: Sequence[str], start: int, end: int) -> int | None:
    """Index of the last non-blank, indent>0 line in ``lines[start:end]``."""
    last = None
    for i in range(start, end):
        if not _is_blank_or_comment(lines[i]) and _indent(lines[i]) > 0:
            last = i
    return last


def parse_phase_profiles(lines: Sequence[str], span: tuple[int, int] | None) -> dict:
    """Parse ``key: value`` mappings (indent 2) inside the phase_profiles block."""
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


def parse_profiles_blocks(lines: Sequence[str], span: tuple[int, int] | None) -> dict:
    """Parse the profiles block into ``name -> {start, end, keys}``.

    ``start``/``end`` bound the profile's raw lines (``end`` exclusive, trailing
    blank/comment lines trimmed) so a whole missing profile can be copied verbatim.
    ``keys`` is the set of structural sub-keys present (``meta:<k>`` for a per-profile
    scalar — the shipped asset carries none, but an upgraded config may still hold stale
    persona strings; ``<tool>:<k>`` for a tool sub-key like ``claude:model``) — used to
    spot sub-keys an existing profile is missing, and stale ones it still carries.
    """
    profiles: dict = {}
    if span is None:
        return profiles
    header, end = span

    order: list[str] = []
    starts: dict[str, int] = {}
    cur: str | None = None
    cur_tool: str | None = None
    for i in range(header + 1, end):
        line = lines[i]
        if _is_blank_or_comment(line):
            continue
        ind = _indent(line)
        stripped = _strip_comment(line.strip())
        if ind == 2 and stripped.endswith(":"):
            cur = stripped[:-1].strip()
            cur_tool = None
            order.append(cur)
            starts[cur] = i
            profiles[cur] = {"start": i, "end": end, "keys": set()}
        elif ind == 4 and cur is not None:
            if stripped.endswith(":") and not stripped.lstrip().startswith("{"):
                cur_tool = stripped[:-1].strip()
                profiles[cur]["keys"].add(f"{cur_tool}:")
            elif ":" in stripped:
                key, _, val = stripped.partition(":")
                val = val.strip()
                if val.startswith("{"):  # inline tool map: tool: {model: .., effort: ..}
                    tool = key.strip()
                    profiles[cur]["keys"].add(f"{tool}:")
                    for part in val.strip("{} ").split(","):
                        if ":" in part:
                            sk = part.partition(":")[0]
                            profiles[cur]["keys"].add(f"{tool}:{sk.strip()}")
                    cur_tool = None
                else:  # per-profile scalar metadata
                    profiles[cur]["keys"].add(f"meta:{key.strip()}")
                    cur_tool = None
        elif ind >= 6 and cur is not None and cur_tool is not None and ":" in stripped:
            key = stripped.partition(":")[0]
            profiles[cur]["keys"].add(f"{cur_tool}:{key.strip()}")

    # Trim each profile's end to the line after its last content line.
    for idx, name in enumerate(order):
        block_end = starts[order[idx + 1]] if idx + 1 < len(order) else end
        last = _last_content_idx(lines, starts[name], block_end)
        profiles[name]["end"] = (last + 1) if last is not None else starts[name] + 1
    return profiles


def _last_nonblank(lines: Sequence[str], start: int, end: int) -> int | None:
    """Index of the last non-blank, non-comment line in ``lines[start:end]`` (any indent)."""
    last = None
    for i in range(start, end):
        if not _is_blank_or_comment(lines[i]):
            last = i
    return last


def parse_tree(lines: Sequence[str], start: int, end: int, indent: int) -> dict:
    """Recursively parse an indent-structured mapping region into an ordered tree.

    Returns ``name -> node`` (insertion order preserved) for the keys at exactly ``indent``
    in ``lines[start:end]``. Each node is
    ``{line, end, indent, kind, children}`` where ``line`` is the ``key:`` header index,
    ``end`` is the exclusive end of that key's subtree (trailing blanks/comments trimmed),
    ``kind`` is ``"map"`` (has indent+2 children) or ``"scalar"`` (leaf — an inline value,
    ``{}``/empty, or a list body, none of which we merge *into*), and ``children`` is the
    recursively-parsed sub-tree (empty for a scalar).

    Dependency-free and block-structured (same spirit as ``parse_profiles_blocks``); used to
    additively heal the setup blocks (delegation/tea/git/code_review/build) whose only source of
    new-key defaults is ``assets/config-defaults.yaml``.
    """
    headers: list[int] = []
    for i in range(start, end):
        if _is_blank_or_comment(lines[i]):
            continue
        if _indent(lines[i]) == indent and ":" in _strip_comment(lines[i].strip()):
            headers.append(i)
    nodes: dict = {}
    for idx, h in enumerate(headers):
        sib = headers[idx + 1] if idx + 1 < len(headers) else end
        last = _last_nonblank(lines, h, sib)
        sub_end = (last + 1) if last is not None else h + 1
        name = _strip_comment(lines[h].strip()).partition(":")[0].strip()
        children = parse_tree(lines, h + 1, sub_end, indent + 2)
        nodes[name] = {
            "line": h,
            "end": sub_end,
            "indent": indent,
            "kind": "map" if children else "scalar",
            "children": children,
        }
    return nodes


def _plan_merge(cfg_lines: Sequence[str], cfg_nodes: dict, setup_lines: Sequence[str],
                setup_nodes: dict, parent_anchor: int, child_indent: int,
                healed: list, prefix: str) -> list:
    """Recursive core of ``plan_setup`` — see it for the contract.

    Missing direct children of this level are gathered into ONE verbatim block inserted after
    ``parent_anchor``; for a child that exists in both as a *map*, recurse so a key missing
    deeper down (e.g. a new scalar inside an existing ``story_trace_advisory``) is healed in
    place. A child present as a scalar (or a kind mismatch) is left untouched — never overwritten.
    """
    inserts: list = []
    missing_block: list[str] = []
    for name, a_node in setup_nodes.items():
        path = f"{prefix}{name}"
        c_node = cfg_nodes.get(name)
        if c_node is None:
            missing_block.extend(setup_lines[a_node["line"]: a_node["end"]])
            healed.append(path)
        elif a_node["kind"] == "map" and c_node["kind"] == "map":
            sub_anchor = _last_nonblank(cfg_lines, c_node["line"], c_node["end"])
            sub_anchor = sub_anchor if sub_anchor is not None else c_node["line"]
            inserts += _plan_merge(cfg_lines, c_node["children"], setup_lines, a_node["children"],
                                   sub_anchor, child_indent + 2, healed, path + ".")
    if missing_block:
        inserts.append((parent_anchor, child_indent, missing_block))
    return inserts


def plan_setup(cfg_lines: Sequence[str], setup_lines: Sequence[str]) -> tuple[list, list]:
    """Plan the additive heal of the setup blocks from ``config-defaults.yaml``.

    Returns ``(inserts, healed_paths)`` where ``inserts`` is a list of
    ``(anchor_idx, child_indent, [new_lines])`` (each inserted AFTER ``anchor_idx``) and
    ``healed_paths`` is the dotted paths that would be added (``git.offer_merge`` etc.).

    Append-only: a key already present in the config — at any depth — is never touched, so a
    user's customised setup answer is preserved; only keys the config is MISSING are added,
    copied verbatim from the asset (so each carries the asset's default value + inline comment).
    Reset, by contrast, overwrites and so stays scoped to the asset-sourced profiles blocks;
    appending a never-seen setup key cannot lose a customisation, which is why it is safe here.
    """
    cfg_nodes = parse_tree(cfg_lines, 0, len(cfg_lines), 0)
    setup_nodes = parse_tree(setup_lines, 0, len(setup_lines), 0)
    top_anchor = _last_nonblank(cfg_lines, 0, len(cfg_lines))
    if top_anchor is None:
        top_anchor = len(cfg_lines) - 1 if cfg_lines else 0
    healed: list = []
    inserts = _plan_merge(cfg_lines, cfg_nodes, setup_lines, setup_nodes, top_anchor, 0, healed, "")
    return inserts, healed


def _leaf_value(lines: Sequence[str], node: dict) -> str:
    """The scalar value on a node's ``key: value`` line (comment + surrounding quotes stripped)."""
    return _strip_value(_strip_comment(lines[int(node["line"])].strip()).partition(":")[2])


def _resolve_node(nodes: dict, path: str) -> dict | None:
    """Walk a dotted ``a.b.c`` path through a parse_tree mapping; ``None`` if any hop is absent."""
    cur: dict | None = None
    node_map = nodes
    for part in path.split("."):
        cur = node_map.get(part)
        if cur is None:
            return None
        node_map = cur.get("children", {})
    return cur


def _node_value_summary(lines: Sequence[str], node: dict) -> str:
    """Human-readable value for a node: the scalar, or a compact ``{k: v, ...}`` for a map."""
    if node["kind"] != "map":
        return _leaf_value(lines, node)
    inner = ", ".join(f"{k}: {_node_value_summary(lines, c)}" for k, c in node["children"].items())
    return "{" + inner + "}"


def _flatten_leaves(lines: Sequence[str], nodes: dict, prefix: str = "") -> dict:
    """Dotted scalar-leaf path -> value for a parse_tree mapping (recurses into sub-maps)."""
    out: dict = {}
    for name, node in nodes.items():
        path = f"{prefix}{name}"
        if node["kind"] == "map":
            out.update(_flatten_leaves(lines, node["children"], path + "."))
        else:
            out[path] = _leaf_value(lines, node)
    return out


def setup_detail(cfg_lines: Sequence[str], setup_lines: Sequence[str], missing_paths: list) -> tuple:
    """Build the two human-facing lists for the Phase 0 echo (non-blocking disclosure).

    Returns ``(added, kept)``:
      * ``added`` — ``[{path, value}]`` for each node the heal would add (``missing_paths``),
        with a value summary (scalar, or compact ``{k: v, ...}`` for a whole sub-/block);
      * ``kept`` — ``[{path, value, default}]`` for every asset leaf the config ALREADY carries
        with a value that differs from the shipped default — i.e. the user's customisations the
        append-only heal preserves. Asset keys only, so an interviewed/detected field the asset
        omits (``git.base_branch``, ``tea.enabled``) is never mislabelled a "customisation".
    """
    setup_nodes = parse_tree(setup_lines, 0, len(setup_lines), 0)
    cfg_nodes = parse_tree(cfg_lines, 0, len(cfg_lines), 0)
    added = [{"path": p, "value": (_node_value_summary(setup_lines, n) if (n := _resolve_node(setup_nodes, p)) else None)}
             for p in missing_paths]
    kept = []
    for path, default in _flatten_leaves(setup_lines, setup_nodes).items():
        node = _resolve_node(cfg_nodes, path)
        if node is not None and node["kind"] != "map":
            cur = _leaf_value(cfg_lines, node)
            if cur != default:
                kept.append({"path": path, "value": cur, "default": default})
    return added, kept


# Heal-immune behavioural setup answers: interviewed / hand-edited fields that ``config-defaults.yaml``
# DELIBERATELY OMITS (no universal-constant default — see that asset's header), so they can never appear
# in ``added_setup``/``kept_setup`` (those only diff asset-sourced leaves). ``cli_phases`` ships ``{}`` in
# the asset but a hand-set MAP can't be diffed against the scalar default either; ``git.mode`` is the
# forced detect|remote|local toggle (a forced ``local``/``remote`` is a deliberate behavioural choice).
# config-check surfaces their CURRENT values separately so the user sees every deliberate deviation —
# with the note that the heal never touches them. ``code_review.cross_model_layer`` is env-DETECTED at
# first run (the first external CLI on PATH that is not the host, else "") but is a real behavioural
# choice thereafter (which tool reviews cross-model, or none), so it is echoed too. PURELY-detected env
# facts (delegation.host/mode, git.base_branch) are excluded on purpose: they are environment state
# re-derived each run, not a chosen "deviation". Allowlist, not a rule, so the surface stays small +
# stable; lockstep with the note in references/state-and-resume.md (config-check).
SETUP_ANSWER_PATHS = ("delegation.cli_phases", "tea.enabled", "tea.framework_ci", "git.mode",
                      "code_review.cross_model_layer")


def collect_setup_answers(cfg_lines: Sequence[str]) -> list:
    """Current ``[{path, value}]`` for each ``SETUP_ANSWER_PATHS`` field present in the config.

    Read-only and asset-independent (the allowlist IS the contract). Absent fields are skipped — a
    setup answer the config never wrote (e.g. ``cli_phases`` omitted entirely) is nothing to surface.
    A map value (a populated ``cli_phases``) is summarised ``{k: v, ...}`` like the other echoes.
    """
    cfg_nodes = parse_tree(cfg_lines, 0, len(cfg_lines), 0)
    out: list = []
    for path in SETUP_ANSWER_PATHS:
        node = _resolve_node(cfg_nodes, path)
        if node is not None:
            out.append({"path": path, "value": _node_value_summary(cfg_lines, node)})
    return out


# The pre-0.27 spelling of the tier value the orchestrator now calls `subagents`. A config seeded by
# an older release still carries it; the orchestrator reads it as `subagents`, so it is TOLERATED —
# never healed, never stripped, never part of the drift verdict. Reported so config-check can say so.
LEGACY_MODE_ALIAS = "custom-subagents"


def detect_legacy_mode_alias(cfg_lines: Sequence[str]) -> bool:
    """True when ``delegation.mode`` is the legacy ``custom-subagents`` spelling (informational)."""
    nodes = parse_tree(cfg_lines, 0, len(cfg_lines), 0)
    node = _resolve_node(nodes, "delegation.mode")
    if node is None or node["kind"] == "map":
        return False
    return _leaf_value(cfg_lines, node) == LEGACY_MODE_ALIAS


def _read_version(text: str, key: str) -> str | None:
    for line in text.splitlines():
        if _indent(line) == 0:
            stripped = _strip_comment(line.strip())
            if stripped.startswith(f"{key}:"):
                return _strip_value(stripped.partition(":")[2])
    return None


def _ver_tuple(v: str | None) -> tuple:
    if not v:
        return ()
    out: list[int] = []
    for part in str(v).split("."):
        num = "".join(ch for ch in part if ch.isdigit())
        out.append(int(num) if num else 0)
    return tuple(out)


def analyze(config_text: str, asset_text: str, config_version: str | None,
            module_version: str | None, setup_text: str | None = None) -> dict:
    """Diff the asset's profiles/phase_profiles keys against the config's.

    When ``setup_text`` (the ``config-defaults.yaml`` asset) is supplied, also diff its
    constant-default setup-block keys (delegation/tea/git/code_review/build): the dotted paths the config
    is MISSING go in ``missing_setup`` (these heal append-only via ``apply()``), and the two
    human-facing lists for the Phase 0 echo go in ``added_setup`` (``[{path, value}]``) and
    ``kept_setup`` (``[{path, value, default}]`` — the user's preserved setup customisations).

    ``setup_answers`` (``[{path, value}]``, always computed — asset-independent) carries the CURRENT
    values of the heal-immune behavioural answers (``SETUP_ANSWER_PATHS``) the asset omits, so
    config-check can show every deviation the two diff-lists structurally can't (see that constant).

    ``legacy_mode_alias`` (bool, informational — never part of the drift verdict) is true when the
    config still spells ``delegation.mode`` the pre-0.27 way (``custom-subagents``), which the
    orchestrator reads as ``subagents``.

    The "what you've customised vs shipped defaults" axis for the PROFILE surface (read-only, for
    the ``config-check`` preview — the heal never touches it) goes in three lists:
    ``customized_profiles`` (``[{profile, key, value, default}]`` — a profile **model/effort** leaf
    retuned away from the asset default; per-profile ``meta:`` scalars are excluded — the asset ships
    none, and a stale persona string left in an upgraded config is not a retune),
    ``custom_profiles`` (``[name]`` — whole profiles the user ADDED that the asset doesn't ship; any
    name is valid), and ``customized_phase_profiles``
    (``[{key, value, default}]`` — a phase remapped to a non-default profile). ``missing_profiles``
    additionally carries ``missing_profile_summaries`` (``{name: "claude: …/…, …"}``) so a
    not-yet-present new profile can show the defaults it would ship with.

    Stale surface (informational — never part of the drift verdict, ignored by the heal, pruned
    only by ``--reset``): ``stale_phase_profiles`` (``[key]`` — mappings the config has that the
    asset no longer ships) and ``stale_profile_keys`` (``[{profile, key}]`` — sub-keys a config
    profile carries that the asset's profile shape does not, in the same key vocabulary as
    ``manual_review``/``customized_profiles``: ``meta:<k>`` for a per-profile persona scalar such
    as ``meta:role_blurb``, ``<tool>:<k>`` for a tool sub-key; a custom profile is compared
    against the shipped field set).
    """
    cfg_lines = config_text.splitlines(keepends=True)
    asset_lines = asset_text.splitlines(keepends=True)

    setup_answers = collect_setup_answers(cfg_lines)
    legacy_mode_alias = detect_legacy_mode_alias(cfg_lines)

    missing_setup: list = []
    added_setup: list = []
    kept_setup: list = []
    if setup_text is not None:
        setup_lines = setup_text.splitlines(keepends=True)
        _, missing_setup = plan_setup(cfg_lines, setup_lines)
        added_setup, kept_setup = setup_detail(cfg_lines, setup_lines, missing_setup)

    cfg_pp = parse_phase_profiles(cfg_lines, find_block(cfg_lines, "phase_profiles"))
    asset_pp = parse_phase_profiles(asset_lines, find_block(asset_lines, "phase_profiles"))
    missing_pp = {k: v for k, v in asset_pp.items() if k not in cfg_pp}

    cfg_prof = parse_profiles_blocks(cfg_lines, find_block(cfg_lines, "profiles"))
    asset_prof = parse_profiles_blocks(asset_lines, find_block(asset_lines, "profiles"))
    missing_profiles = [name for name in asset_prof if name not in cfg_prof]
    missing_profile_summaries = {name: _profile_summary(asset_lines, asset_prof[name])
                                 for name in missing_profiles}
    manual_review: list[dict] = []
    for name, ainfo in asset_prof.items():
        if name in cfg_prof:
            a_vals = _profile_leaf_values(asset_lines, ainfo["start"], ainfo["end"])
            for key in sorted(ainfo["keys"] - cfg_prof[name]["keys"]):
                if key.endswith(":"):  # a tool *block* header alone — its sub-keys cover it
                    continue
                # A missing sub-key whose ASSET value is BLANK needs no action: the absent sub-block
                # behaves identically to the shipped blank default (e.g. opencode.model: "" => the
                # delegate inherits the user's opencode default model). Flagging it would nag every
                # run — manual_review feeds status:drift (see check_file) — for zero benefit. Only
                # surface missing sub-keys that carry a REAL default value to restore.
                if a_vals.get(key, "") == "":
                    continue
                manual_review.append({"profile": name, "missing_key": key})

    # --- The "what you've customised vs shipped defaults" axis (read-only; for the config-check
    # preview). Mirrors kept_setup (which covers the delegation/tea/git/code_review/build setup leaves)
    # for the asset-sourced PROFILE surface. A present-but-different value is a customisation; a
    # MISSING key is NOT (that is manual_review's job — never double-report it here). ---
    customized_profiles: list[dict] = []
    for name, ainfo in asset_prof.items():
        if name not in cfg_prof:
            continue
        a_vals = _profile_leaf_values(asset_lines, ainfo["start"], ainfo["end"])
        c_vals = _profile_leaf_values(cfg_lines, cfg_prof[name]["start"], cfg_prof[name]["end"])
        for key, dv in a_vals.items():
            # Per-profile meta scalars are EXCLUDED (the shipped asset carries none — profiles are
            # model/effort only — so this only guards a future/custom asset). "Customised a profile"
            # means a model/effort retune: mirror missing_profile_summaries, report only the tool tiers.
            if key.startswith("meta:"):
                continue
            cv = c_vals.get(key)
            if cv is not None and cv != dv:
                customized_profiles.append({"profile": name, "key": key, "value": cv, "default": dv})
    custom_profiles = [name for name in cfg_prof if name not in asset_prof]
    customized_phase_profiles = [{"key": k, "value": cfg_pp[k], "default": asset_pp[k]}
                                 for k in asset_pp if k in cfg_pp and cfg_pp[k] != asset_pp[k]]

    # --- Stale surface (informational). A removed phase mapping / persona sub-key left in an upgraded
    # config is harmless: the orchestrator simply never reads it. Report it so config-check can show
    # "ignored" leftovers and point at `reset-defaults` — never strip it here (append-only heal). ---
    stale_phase_profiles = [k for k in cfg_pp if k not in asset_pp]
    shipped_shape: set = set().union(*(i["keys"] for i in asset_prof.values())) if asset_prof else set()
    stale_profile_keys: list[dict] = []
    for name, cinfo in cfg_prof.items():
        shape = asset_prof[name]["keys"] if name in asset_prof else shipped_shape
        for key in sorted(cinfo["keys"] - shape):
            if key.endswith(":"):  # a tool *block* header alone — its sub-keys cover it
                continue
            stale_profile_keys.append({"profile": name, "key": key})

    cver = _ver_tuple(config_version)
    mver = _ver_tuple(module_version)
    version_drift = bool(module_version) and config_version != module_version
    config_older = bool(module_version) and (not config_version or cver < mver)

    needs_reseed = bool(missing_pp or missing_profiles)
    return {
        "missing_phase_profiles": missing_pp,
        "missing_profiles": missing_profiles,
        "missing_profile_summaries": missing_profile_summaries,
        "missing_setup": missing_setup,
        "added_setup": added_setup,
        "kept_setup": kept_setup,
        "setup_answers": setup_answers,
        "legacy_mode_alias": legacy_mode_alias,
        "customized_profiles": customized_profiles,
        "custom_profiles": custom_profiles,
        "customized_phase_profiles": customized_phase_profiles,
        "stale_phase_profiles": stale_phase_profiles,
        "stale_profile_keys": stale_profile_keys,
        "manual_review": manual_review,
        "version": {
            "config": config_version,
            "module": module_version,
            "drift": version_drift,
            "config_older": config_older,
        },
        "needs_reseed": needs_reseed,
        "_asset_profiles": asset_prof,  # internal, for apply()
        "_asset_lines": asset_lines,    # internal, for apply()
    }


def _ensure_newline(lines: list[str], idx: int) -> None:
    if lines and not lines[idx].endswith("\n"):
        lines[idx] = lines[idx] + "\n"


def apply(config_text: str, asset_text: str, config_version: str | None,
          module_version: str | None, setup_text: str | None = None) -> dict:
    """Additively heal the config: append missing keys, restamp the version.

    Heals three append-only axes (never overwriting an existing value): missing whole
    ``profiles`` blocks + missing ``phase_profiles`` keys (from ``asset_text`` /
    ``profiles.yaml``), and, when ``setup_text`` (``config-defaults.yaml``) is supplied,
    missing constant-default setup-block keys (delegation/tea/git/code_review/build) at any depth.
    """
    info = analyze(config_text, asset_text, config_version, module_version, setup_text)
    lines = config_text.splitlines(keepends=True)
    asset_lines = info["_asset_lines"]
    asset_prof = info["_asset_profiles"]

    # Each insert is (insert-after index, child indent, new lines). The indent is the sort
    # tiebreak for the rare case where two inserts share an anchor (a block AND its trailing
    # sub-block both gain a key): shallower applied first => deeper ends nearest the anchor,
    # so the deeper line attaches to the inner block and the shallower starts a new outer key.
    inserts: list[tuple[int, int, list[str]]] = []
    # A config that lacks a `profiles:` / `phase_profiles:` HEADER entirely has nothing to anchor an
    # insert on, so the block is (re)created at EOF instead — mirroring reset's trailing path. Without
    # it the reseeded_* lists would claim keys apply() never actually wrote.
    trailing: list[str] = []

    # Missing whole profiles -> copy the asset's raw block to the profiles block end.
    if info["missing_profiles"]:
        span = find_block(lines, "profiles")
        block: list[str] = []
        for name in info["missing_profiles"]:
            p = asset_prof[name]
            block.append("\n")
            block.extend(asset_lines[p["start"]: p["end"]])
        if span is not None:
            header, end = span
            anchor = _last_content_idx(lines, header + 1, end)
            anchor = anchor if anchor is not None else header
            inserts.append((anchor, 2, block))
        else:  # no `profiles:` block at all — recreate it at EOF (drop the leading separator)
            trailing += ["\n", "profiles:\n"] + block[1:]

    # Missing phase_profiles keys -> append `  key: value` lines to that block end.
    if info["missing_phase_profiles"]:
        span = find_block(lines, "phase_profiles")
        block = [f"  {k}: {v}\n" for k, v in info["missing_phase_profiles"].items()]
        if span is not None:
            header, end = span
            anchor = _last_content_idx(lines, header + 1, end)
            anchor = anchor if anchor is not None else header
            inserts.append((anchor, 2, block))
        else:  # no `phase_profiles:` block at all — recreate it at EOF
            trailing += ["\n", "phase_profiles:\n"] + block

    # Missing setup-block keys (delegation/tea/git/code_review/build) -> append-only, nested-aware.
    healed_setup: list = []
    if setup_text is not None:
        setup_inserts, healed_setup = plan_setup(lines, setup_text.splitlines(keepends=True))
        inserts.extend(setup_inserts)

    # Apply bottom-up so earlier indices stay valid; for a shared anchor, shallower first.
    for anchor, _, block in sorted(inserts, key=lambda t: (t[0], -t[1]), reverse=True):
        _ensure_newline(lines, anchor)
        lines[anchor + 1: anchor + 1] = block

    # Recreated whole blocks land after every anchored insert, so plan and write agree.
    if trailing:
        if lines:
            _ensure_newline(lines, len(lines) - 1)
        if not trailing[-1].endswith("\n"):
            trailing[-1] = trailing[-1] + "\n"
        lines.extend(trailing)

    # Restamp profiles_source_version (content-based, robust to the splices above).
    restamped = None
    if module_version and config_version != module_version:
        restamped = _restamp_version(lines, module_version)

    return {
        "new_text": "".join(lines),
        "reseeded_phase_profiles": info["missing_phase_profiles"],
        "reseeded_profiles": info["missing_profiles"],
        "reseeded_setup": healed_setup,
        "added_setup": info["added_setup"],
        "kept_setup": info["kept_setup"],
        "manual_review": info["manual_review"],
        "version_restamped": restamped,
    }


def _restamp_version(lines: list[str], new_version: str) -> dict:
    """Set/insert top-level ``profiles_source_version``, preserving a trailing comment."""
    for i, line in enumerate(lines):
        if _indent(line) != 0:
            continue
        stripped = _strip_comment(line.strip())
        if stripped.startswith("profiles_source_version:"):
            old = _strip_value(stripped.partition(":")[2])
            comment = ""
            m = re.search(r"\s+#", line.rstrip("\n"))
            if m:
                comment = "  " + line.rstrip("\n")[m.start():].strip()
            lines[i] = f'profiles_source_version: "{new_version}"{comment}\n'
            return {"from": old, "to": new_version}
    # Absent: insert after the top-level `version:` line, else at the very top.
    for i, line in enumerate(lines):
        if _indent(line) == 0 and _strip_comment(line.strip()).startswith("version:"):
            _ensure_newline(lines, i)
            lines.insert(i + 1, f'profiles_source_version: "{new_version}"\n')
            return {"from": None, "to": new_version}
    lines.insert(0, f'profiles_source_version: "{new_version}"\n')
    return {"from": None, "to": new_version}


# --------------------------------------------------------------------------- #
# reset: restore shipped defaults (the inverse of the additive --apply heal).  #
# --apply only APPENDS missing keys; it never reverts a user's edited value.   #
# reset OVERWRITES the profiles / phase_profiles blocks back to the asset      #
# (a whole-block scope also PRUNES profiles the asset no longer ships), scoped, #
# and NEVER touches the setup blocks (delegation / tea / git /                 #
# code_review / build). config-defaults.yaml DOES ship defaults for them, so    #
# the additive heal can append a constant-default key they lack — but reset is  #
# an OVERWRITE, and overwriting a setup block would clobber a user's setup      #
# answer (an interviewed/detected value the heal deliberately leaves alone).    #
# Append can't lose an answer; overwrite can — so only --apply enters those.    #
# --------------------------------------------------------------------------- #

RESET_BLOCK_SCOPES = ("both", "profiles", "phase_profiles")

# The phase_profiles keys whose profile the review-layers TOML (`_bmad/custom/bmad-build-auto.toml`,
# managed by build_auto_custom.py) bakes model + effort from. Remapping one of these (or changing
# any profile) means that TOML is stale until re-synced => `layers_sync_needed`.
LAYER_PHASE_KEYS = ("security_layer", "cross_model_layer")


def _profile_leaf_values(lines: Sequence[str], start: int, end: int) -> dict:
    """Leaf ``key -> value`` map for one profile's ``lines[start:end]``.

    Keys mirror ``parse_profiles_blocks`` (``meta:<k>`` for a per-profile scalar,
    ``<tool>:<k>`` for a tool sub-key) but carry the *value* too — so a reset can
    report a precise ``current -> default`` diff. ``start`` is the ``  name:``
    header line; sub-keys sit at indent 4, tool sub-keys at indent >= 6.
    """
    out: dict = {}
    cur_tool: str | None = None
    for i in range(start + 1, end):
        line = lines[i]
        if _is_blank_or_comment(line):
            continue
        ind = _indent(line)
        stripped = _strip_comment(line.strip())
        if ind == 4:
            if stripped.endswith(":") and not stripped.startswith("{"):
                cur_tool = stripped[:-1].strip()
            elif ":" in stripped:
                key, _, val = stripped.partition(":")
                val = val.strip()
                if val.startswith("{"):  # inline tool map: tool: {model: .., effort: ..}
                    tool = key.strip()
                    for part in val.strip("{} ").split(","):
                        if ":" in part:
                            sk, _, sv = part.partition(":")
                            out[f"{tool}:{sk.strip()}"] = _strip_value(sv)
                    cur_tool = None
                else:  # per-profile scalar metadata
                    out[f"meta:{key.strip()}"] = _strip_value(val)
                    cur_tool = None
        elif ind >= 6 and cur_tool is not None and ":" in stripped:
            key, _, val = stripped.partition(":")
            out[f"{cur_tool}:{key.strip()}"] = _strip_value(val)
    return out


def _profile_summary(lines: Sequence[str], info: dict) -> str:
    """A compact per-tool ``model/effort`` summary for one profile block.

    Used only for the drift PREVIEW/pause echo — so a NEW (still-missing) profile surfaces the
    defaults it would ship with, not just its name, letting the user decide whether to retune
    before the heal applies it. A tool with no model AND no effort (opencode's blank default ⇒
    inherit) is omitted; a blank model with an effort renders ``(inherit)/<effort>``.
    """
    vals = _profile_leaf_values(lines, info["start"], info["end"])
    parts: list[str] = []
    for tool in ("claude", "codex", "opencode"):
        model = vals.get(f"{tool}:model", "")
        effort = (vals.get(f"{tool}:effort") or vals.get(f"{tool}:reasoning_effort")
                  or vals.get(f"{tool}:variant") or "")
        if not model and not effort:
            continue
        label = model or "(inherit)"
        parts.append(f"{tool}: {label}/{effort}" if effort else f"{tool}: {label}")
    return " · ".join(parts)


def reset(config_text: str, asset_text: str, config_version: str | None,
          module_version: str | None, scope: str | None) -> dict:
    """Restore the asset's defaults for ``scope`` into the config.

    ``scope`` is one of ``profiles`` (all profile blocks), ``phase_profiles``
    (the phase->profile mapping), a single ``<profile-name>``, or ``None``/``both``
    (both asset blocks). Returns a plan + the rewritten text; callers decide
    whether to write. On an unrecognised scope returns ``{"error": ...}``.

    A whole-block scope (``profiles``/``both``) also **prunes**: a profile present in
    the config but absent from the asset is removed so the config's profile set matches
    the shipped asset (the remedy for a renamed/dropped profile). The pruned names are
    returned on ``removed_profiles`` — destructive, so callers surface it for confirmation.
    A single ``<profile-name>`` scope never prunes (a user-added profile is left intact).

    Restamp rule: only a **full** reset (``both``) restamps ``profiles_source_version``
    to ``module_version`` — a partial reset can't honestly claim the whole
    asset-sourced surface matches that version, so it leaves the stamp.

    ``layers_sync_needed`` is true iff the plan changes any profile leaf (incl. dropping a
    stale sub-key), prunes a profile, or remaps ``phase_profiles.security_layer`` /
    ``phase_profiles.cross_model_layer`` — the surface the review-layers TOML bakes model +
    effort from (``build_auto_custom.py --apply`` must then re-run). Other phase remaps
    are read at spawn time and need no sync.
    """
    cfg_lines = config_text.splitlines(keepends=True)
    asset_lines = asset_text.splitlines(keepends=True)

    asset_prof = parse_profiles_blocks(asset_lines, find_block(asset_lines, "profiles"))
    cfg_prof = parse_profiles_blocks(cfg_lines, find_block(cfg_lines, "profiles"))

    sc = "both" if scope is None else scope
    if sc not in RESET_BLOCK_SCOPES and sc not in asset_prof:
        return {
            "error": "unknown_scope",
            "scope": scope,
            "valid_scopes": sorted(RESET_BLOCK_SCOPES) + sorted(asset_prof),
        }

    is_full = sc == "both"
    do_phase = sc in ("both", "phase_profiles")
    prune = sc in ("both", "profiles")             # whole-block scopes reconcile to the asset set
    if sc in ("both", "profiles"):
        target_profiles = list(asset_prof)         # all asset-known profiles
    elif sc in asset_prof:
        target_profiles = [sc]                      # one named profile
    else:
        target_profiles = []                        # phase_profiles-only

    would_change: list[dict] = []

    # --- profile diffs (current -> default per leaf key) ---
    for name in target_profiles:
        a_info = asset_prof[name]
        a_vals = _profile_leaf_values(asset_lines, a_info["start"], a_info["end"])
        if name in cfg_prof:
            c_info = cfg_prof[name]
            c_vals = _profile_leaf_values(cfg_lines, c_info["start"], c_info["end"])
        else:
            c_vals = {}
        for k, dv in a_vals.items():
            cv = c_vals.get(k)
            if cv != dv:
                would_change.append({"profile": name, "key": k, "current": cv, "default": dv})
        for k, cv in c_vals.items():
            if k not in a_vals:  # config-only sub-key the reset will drop
                would_change.append({"profile": name, "key": k, "current": cv, "default": None})

    # --- profiles the config has but the asset doesn't: a whole-block reset prunes them so the
    # config's profile set matches the shipped asset (a renamed/removed profile no longer lingers).
    # Reported on a dedicated channel — destructive, so the orchestrator surfaces it in the confirm. ---
    removed_profiles = [n for n in cfg_prof if n not in asset_prof] if prune else []

    # --- phase_profiles diff ---
    if do_phase:
        cfg_pp = parse_phase_profiles(cfg_lines, find_block(cfg_lines, "phase_profiles"))
        asset_pp = parse_phase_profiles(asset_lines, find_block(asset_lines, "phase_profiles"))
        for k, dv in asset_pp.items():
            cv = cfg_pp.get(k)
            if cv != dv:
                would_change.append({"block": "phase_profiles", "key": k, "current": cv, "default": dv})
        for k, cv in cfg_pp.items():
            if k not in asset_pp:
                would_change.append({"block": "phase_profiles", "key": k, "current": cv, "default": None})

    layers_sync_needed = (
        any("profile" in c for c in would_change)
        or bool(removed_profiles)
        or any(c.get("block") == "phase_profiles" and c["key"] in LAYER_PHASE_KEYS
               for c in would_change)
    )

    # --- build the rewritten text ---
    # In-place/anchored edits (start < end_exclusive) applied bottom-up; whole-block
    # (re)creation, used only if the config lacks a `profiles:`/`phase_profiles:` header,
    # is appended at EOF afterwards so plan and write never disagree.
    edits: list[tuple[int, int, list[str]]] = []
    trailing: list[str] = []

    if prune:
        # Whole-block reset (both / profiles): replace the config's entire profile region with the
        # asset's profile blocks verbatim, in ONE splice. This resets every value, drops config-only
        # profiles (the prune), and adopts the asset's clean layout — no edit-interleaving with the
        # per-profile appends below. `min(start)..max(end)` spans the asset's profile blocks only
        # (its leading file header + the trailing phase_profiles comment sit outside that range).
        asset_body: list[str] = (
            list(asset_lines[min(i["start"] for i in asset_prof.values()):
                             max(i["end"] for i in asset_prof.values())])
            if asset_prof else []
        )
        if cfg_prof:
            first_c = min(i["start"] for i in cfg_prof.values())
            last_c = max(i["end"] for i in cfg_prof.values())
            edits.append((first_c, last_c, asset_body))
        else:  # config has a `profiles:` header but no blocks, or none at all
            span = find_block(cfg_lines, "profiles")
            if span is not None:
                edits.append((span[0] + 1, span[0] + 1, asset_body))
            else:
                trailing += ["profiles:\n"] + asset_body
    else:
        # Scoped single-profile reset: swap that one block in place (or append it if absent).
        # No pruning — a config-only profile the user added is intentionally left untouched.
        in_config = [n for n in target_profiles if n in cfg_prof]
        missing = [n for n in target_profiles if n not in cfg_prof]
        for name in in_config:
            c = cfg_prof[name]
            a = asset_prof[name]
            edits.append((c["start"], c["end"], list(asset_lines[a["start"]: a["end"]])))
        if missing:
            block: list[str] = []
            for name in missing:
                a = asset_prof[name]
                block.append("\n")
                block.extend(asset_lines[a["start"]: a["end"]])
            span = find_block(cfg_lines, "profiles")
            if span is not None:
                header, end = span
                anchor = _last_content_idx(cfg_lines, header + 1, end)
                anchor = anchor if anchor is not None else header
                _ensure_newline(cfg_lines, anchor)
                edits.append((anchor + 1, anchor + 1, block))
            else:  # no `profiles:` block at all — recreate it at EOF
                trailing += ["profiles:\n"] + block

    if do_phase:
        a_span = find_block(asset_lines, "phase_profiles")
        if a_span is not None:
            a_h, a_e = a_span
            body = list(asset_lines[a_h + 1: a_e])
            c_span = find_block(cfg_lines, "phase_profiles")
            if c_span is not None:
                c_h, c_e = c_span
                edits.append((c_h + 1, c_e, body))
            else:  # no `phase_profiles:` block at all — recreate it at EOF
                trailing += (["\n"] if trailing else []) + ["phase_profiles:\n"] + body

    # Apply bottom-up so earlier indices stay valid; guard the splice boundary.
    for start, stop, repl in sorted(edits, key=lambda t: t[0], reverse=True):
        if repl and not repl[-1].endswith("\n"):
            repl = repl[:-1] + [repl[-1] + "\n"]
        cfg_lines[start:stop] = repl
    if trailing:
        if cfg_lines:
            _ensure_newline(cfg_lines, len(cfg_lines) - 1)
        if not trailing[-1].endswith("\n"):
            trailing[-1] = trailing[-1] + "\n"
        cfg_lines.extend(trailing)

    restamped = None
    if is_full and module_version and config_version != module_version:
        restamped = _restamp_version(cfg_lines, module_version)

    return {
        "scope": sc,
        "would_change": would_change,
        "removed_profiles": removed_profiles,
        "layers_sync_needed": layers_sync_needed,
        "version_restamp": restamped,
        "new_text": "".join(cfg_lines),
    }


def reset_to_file(config_path: Path, asset_path: Path, module_version: str | None,
                  scope: str | None, write: bool) -> dict:
    config_text = _read_text(config_path)
    asset_text = _read_text(asset_path)
    config_version = _read_version(config_text, "profiles_source_version")
    res = reset(config_text, asset_text, config_version, module_version, scope)
    if res.get("error"):
        return {"status": "error", "message": f"unknown reset scope: {res['scope']!r}",
                "valid_scopes": res["valid_scopes"], "config_path": str(config_path)}

    changed = bool(res["would_change"]) or bool(res["removed_profiles"]) or bool(res["version_restamp"])
    backup = None
    if write and changed:
        backup = str(config_path) + ".bak"
        _write_text(Path(backup), config_text)
        _write_text(config_path, res["new_text"])

    status = "reset" if (write and changed) else ("noop" if write else "reset-plan")
    return {
        "status": status,
        "scope": res["scope"],
        "would_change": res["would_change"],
        "removed_profiles": res["removed_profiles"],
        "layers_sync_needed": res["layers_sync_needed"],
        "version_restamp": res["version_restamp"],
        "backup": backup,
        "config_path": str(config_path),
    }


def _default_asset_profiles() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "profiles.yaml"


def _default_setup_defaults() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "config-defaults.yaml"


def _read_setup_text(setup_path: Path | None) -> str | None:
    """Read the config-defaults asset, or ``None`` if it is absent (heal degrades gracefully)."""
    path = setup_path if setup_path is not None else _default_setup_defaults()
    return _read_text(path) if path.is_file() else None


def _default_module_yaml() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "module.yaml"


def _public(info: dict) -> dict:
    """Strip the internal underscore-prefixed keys from an analyze() result."""
    return {k: v for k, v in info.items() if not k.startswith("_")}


def _run_self_test() -> int:
    asset = _default_asset_profiles()
    assert asset.is_file(), f"shipped profiles.yaml missing at {asset}"
    asset_text = asset.read_text(encoding="utf-8")
    a_lines = asset_text.splitlines(keepends=True)

    # ----------------------------------------------------------------------- #
    # Shipped asset invariants (lockstep with references/state-and-resume.md).  #
    # ----------------------------------------------------------------------- #
    # The asset must define EXACTLY the ten phase_profiles keys ...
    a_pp = parse_phase_profiles(a_lines, find_block(a_lines, "phase_profiles"))
    PHASE_KEYS = ("build", "followup_review", "security_layer", "cross_model_layer", "tea_triage",
                  "tea_per_story", "tea_epic", "tea_epic_audit", "retrospective", "deferred_reconcile")
    assert set(a_pp) == set(PHASE_KEYS), f"asset phase_profiles must be exactly {PHASE_KEYS}: {sorted(a_pp)}"
    assert set(LAYER_PHASE_KEYS).issubset(set(a_pp)), LAYER_PHASE_KEYS
    # ... and EXACTLY the five shipped profiles, each model/effort ONLY (no persona strings — D12).
    a_prof = parse_profiles_blocks(a_lines, find_block(a_lines, "profiles"))
    PROFILE_NAMES = ("ab-deep", "ab-standard", "ab-alt-deep", "ab-alt-standard", "ab-security")
    LEAF_KEYS = ("claude:model", "claude:effort", "codex:model", "codex:reasoning_effort",
                 "opencode:model", "opencode:variant")
    assert set(a_prof) == set(PROFILE_NAMES), f"asset profiles must be exactly {PROFILE_NAMES}: {sorted(a_prof)}"
    for name in PROFILE_NAMES:
        keys = a_prof[name]["keys"]
        for lk in LEAF_KEYS:
            # opencode.model/variant ship BLANK — the keys must be recognised even with an empty value.
            assert lk in keys, f"asset profile {name} missing {lk}: {sorted(keys)}"
        assert not any(k.startswith("meta:") for k in keys), \
            f"asset profile {name} must carry NO per-profile persona/meta scalar (model/effort only): {sorted(keys)}"
        assert keys - {"claude:", "codex:", "opencode:"} == set(LEAF_KEYS), \
            f"asset profile {name} shape drifted from the documented six leaves: {sorted(keys)}"
        vals = _profile_leaf_values(a_lines, a_prof[name]["start"], a_prof[name]["end"])
        assert vals["claude:model"] and vals["claude:effort"] and vals["codex:model"] and vals["codex:reasoning_effort"], vals
        assert vals["opencode:model"] == "" and vals["opencode:variant"] == "", f"opencode must ship BLANK (inherit): {vals}"
    # Every phase maps to a shipped profile.
    for k, v in a_pp.items():
        assert v in a_prof, f"phase_profiles.{k} -> unknown profile {v!r}"
    # No stale names may survive in the shipped asset (removed-key policy).
    for gone in ("ab-verification", "description:", "role_blurb:", "status_example:", "create_story", "dev_story",
                 "project_context", "uat:", "code_review_"):
        assert gone not in asset_text, f"removed name {gone!r} must not appear in the shipped profiles.yaml"

    # find_block: blank lines / comments are transparent; next top-level key ends it.
    sample = "version: 1\nphase_profiles:\n  a: x\n\n  # note\n  b: y\ngit:\n  mode: auto\n".splitlines(keepends=True)
    sp = find_block(sample, "phase_profiles")
    assert sp is not None and parse_phase_profiles(sample, sp) == {"a": "x", "b": "y"}, sp

    # --- fixture helpers: retune / drop ONE tool leaf of ONE profile by position (robust to inline
    # comments in the asset — an ab-deep leaf line may carry a trailing `# …` note). ---
    def _leaf_line(text: str, profile: str, tool: str, key: str) -> tuple[list[str], int]:
        ls = text.splitlines(keepends=True)
        prof = parse_profiles_blocks(ls, find_block(ls, "profiles"))
        p = prof[profile]
        cur_tool = None
        for i in range(p["start"] + 1, p["end"]):
            if _is_blank_or_comment(ls[i]):
                continue
            ind, s = _indent(ls[i]), _strip_comment(ls[i].strip())
            if ind == 4 and s.endswith(":"):
                cur_tool = s[:-1].strip()
            elif ind >= 6 and cur_tool == tool and s.partition(":")[0].strip() == key:
                return ls, i
        raise AssertionError(f"fixture: {profile}.{tool}.{key} not found")

    def _set_leaf(text: str, profile: str, tool: str, key: str, value: str) -> str:
        ls, i = _leaf_line(text, profile, tool, key)
        ls[i] = f"      {key}: {value}\n"
        return "".join(ls)

    def _drop_leaf(text: str, profile: str, tool: str, key: str) -> str:
        ls, i = _leaf_line(text, profile, tool, key)
        del ls[i]
        return "".join(ls)

    def _leaf(text: str, profile: str) -> dict:
        ls = text.splitlines(keepends=True)
        prof = parse_profiles_blocks(ls, find_block(ls, "profiles"))
        return _profile_leaf_values(ls, prof[profile]["start"], prof[profile]["end"])

    # --- A config seeded from an OLDER snapshot: persona strings (removed keys), a stale phase
    # mapping (`dev_story`), missing new mappings + profiles, older version. ---
    stale_cfg = (
        'version: 1\n'
        'profiles_source_version: "0.8.0"  # seeded snapshot\n'
        'delegation:\n'
        '  host: auto\n'
        'profiles:\n'
        '  ab-deep:\n'
        '    description: "deep"\n'
        '    role_blurb: "deep work"\n'
        '    status_example: "ok"\n'
        '    claude:\n'
        '      model: haiku\n'        # user RETUNE — must be preserved
        '      effort: low\n'
        '    codex:\n'
        '      model: gpt-x\n'
        '      reasoning_effort: medium\n'
        '    opencode:\n'
        '      model: ""\n'
        '      variant: ""\n'
        '  ab-standard:\n'
        '    description: "infra"\n'
        '    claude:\n'
        '      model: opus\n'
        '      effort: high\n'
        '    codex:\n'
        '      model: gpt-x\n'
        '      reasoning_effort: high\n'
        '    opencode:\n'
        '      model: ""\n'
        '      variant: ""\n'
        'phase_profiles:\n'
        '  build: ab-deep\n'
        '  dev_story: ab-deep\n'      # REMOVED mapping left behind — ignored, never stripped by the heal
        'git:\n'
        '  mode: auto\n'
    )

    info = analyze(stale_cfg, asset_text, "0.8.0", "0.9.0")
    pub = _public(info)
    assert "tea_triage" in pub["missing_phase_profiles"], pub["missing_phase_profiles"]
    assert pub["missing_phase_profiles"]["tea_triage"] == "ab-alt-standard", pub
    assert pub["missing_phase_profiles"]["followup_review"] == "ab-alt-deep", pub
    assert "build" not in pub["missing_phase_profiles"], pub["missing_phase_profiles"]
    # ab-alt-deep / ab-alt-standard / ab-security absent from the stale config => whole missing profiles.
    assert set(pub["missing_profiles"]) == {"ab-alt-deep", "ab-alt-standard", "ab-security"}, pub["missing_profiles"]
    # missing_profile_summaries: every missing profile shows the model/effort defaults it would ship with.
    assert set(pub["missing_profile_summaries"]) == set(pub["missing_profiles"]), pub["missing_profile_summaries"]
    assert all("claude:" in s for s in pub["missing_profile_summaries"].values()), pub["missing_profile_summaries"]
    # customised-vs-default (PROFILE axis): ab-deep's claude.model retune (haiku, default opus) is surfaced.
    assert any(c == {"profile": "ab-deep", "key": "claude:model", "value": "haiku", "default": "opus"}
               for c in pub["customized_profiles"]), pub["customized_profiles"]
    # Persona meta keys are never a "customisation" (the asset ships none).
    assert not any(c["key"].startswith("meta:") for c in pub["customized_profiles"]), pub["customized_profiles"]
    # A missing key is manual_review, never a "customisation" (no double-report).
    assert not any(c["profile"] == "ab-alt-deep" for c in pub["customized_profiles"]), pub["customized_profiles"]
    assert pub["custom_profiles"] == [] and pub["customized_phase_profiles"] == [], pub
    # Stale surface: the removed mapping + the persona strings are REPORTED (informational) ...
    assert pub["stale_phase_profiles"] == ["dev_story"], pub["stale_phase_profiles"]
    assert {"profile": "ab-deep", "key": "meta:role_blurb"} in pub["stale_profile_keys"], pub["stale_profile_keys"]
    assert {(s["profile"], s["key"]) for s in pub["stale_profile_keys"]} == {
        ("ab-deep", "meta:description"), ("ab-deep", "meta:role_blurb"), ("ab-deep", "meta:status_example"),
        ("ab-standard", "meta:description")}, pub["stale_profile_keys"]
    # ... and stale persona keys never leak into manual_review (that list is asset-keys-missing only).
    assert not any(m["missing_key"].startswith("meta:") for m in pub["manual_review"]), pub["manual_review"]
    assert pub["needs_reseed"] is True, pub
    assert pub["version"]["drift"] is True and pub["version"]["config_older"] is True, pub

    # --- apply(): additive heal. ---
    res = apply(stale_cfg, asset_text, "0.8.0", "0.9.0")
    healed = res["new_text"]
    assert res["version_restamped"] == {"from": "0.8.0", "to": "0.9.0"}, res["version_restamped"]
    assert 'profiles_source_version: "0.9.0"  # seeded snapshot' in healed, "comment not preserved"

    h_lines = healed.splitlines(keepends=True)
    h_pp = parse_phase_profiles(h_lines, find_block(h_lines, "phase_profiles"))
    for k, v in a_pp.items():
        assert h_pp.get(k) == v, f"phase_profiles not healed for {k}: got {h_pp.get(k)}"
    # The heal is append-only: the stale mapping + persona strings SURVIVE (never stripped) ...
    assert h_pp.get("dev_story") == "ab-deep", "heal must never strip a stale phase mapping"
    assert 'role_blurb: "deep work"' in healed, "heal must never strip a stale persona key"
    # ... the user retune is preserved: ab-deep.claude.model stays haiku, NOT reset to the asset's opus.
    h_prof = parse_profiles_blocks(h_lines, find_block(h_lines, "profiles"))
    assert set(PROFILE_NAMES).issubset(set(h_prof)), sorted(h_prof)
    assert "model: haiku" in healed and "effort: low" in healed, "user retune clobbered"
    # The healed asset profiles are copied verbatim (their header comments ride along).
    assert "lighter-weight" in healed, "ab-alt-standard block not copied verbatim"
    # Other config blocks survive intact.
    assert "delegation:" in healed and "git:" in healed and "mode: auto" in healed, healed

    # Re-analyzing the healed config against the same asset => fully fresh (the stale surface is
    # still reported, but it is informational and NOT part of the drift verdict).
    info2 = analyze(healed, asset_text, "0.9.0", "0.9.0")
    assert not info2["needs_reseed"], _public(info2)
    assert not info2["missing_phase_profiles"] and not info2["missing_profiles"], _public(info2)
    assert info2["version"]["drift"] is False, info2["version"]
    assert not info2["manual_review"], info2["manual_review"]
    assert info2["stale_phase_profiles"] == ["dev_story"], info2["stale_phase_profiles"]

    # A config built straight from the asset (just stamped) is fully fresh, with an EMPTY stale surface.
    fresh_from_asset = 'profiles_source_version: "0.9.0"\n' + asset_text
    info_fresh = analyze(fresh_from_asset, asset_text, "0.9.0", "0.9.0")
    assert not info_fresh["needs_reseed"], _public(info_fresh)
    assert not info_fresh["manual_review"], info_fresh["manual_review"]
    assert info_fresh["version"]["drift"] is False, info_fresh["version"]
    assert info_fresh["stale_phase_profiles"] == [] and info_fresh["stale_profile_keys"] == [], _public(info_fresh)

    # --- custom profiles are first-class — ANY name (no `ab-` prefix rule): a config that ADDS
    # profiles (and remaps a phase to one) must read fully fresh — no drift nag on any run — and
    # the additive heal must pass both the profiles and the remapped phase through untouched.
    # (Reset semantics for customs — whole-block prunes, scoped keeps — are pinned further down.) ---
    custom_block = (
        '  ab-ultradeep:\n'
        '    claude:\n      model: opus\n      effort: max\n'
        '    codex:\n      model: gpt-x\n      reasoning_effort: xhigh\n'
        '    opencode:\n      model: ""\n      variant: ""\n'
        '  team-fast:\n'                       # a non-`ab-` name is just as valid
        '    role_blurb: "leftover persona"\n'  # a persona scalar on a custom profile => stale (ignored)
        '    claude:\n      model: haiku\n      effort: low\n'
        '    codex:\n      model: gpt-x\n      reasoning_effort: low\n'
        '    opencode:\n      model: ""\n      variant: ""\n'
    )
    cfg_custom = fresh_from_asset.replace("\nprofiles:\n", "\nprofiles:\n" + custom_block, 1)
    cfg_custom = cfg_custom.replace("  build: ab-deep", "  build: ab-ultradeep", 1)
    cfg_custom = cfg_custom.replace("  tea_triage: ab-alt-standard", "  tea_triage: team-fast", 1)
    assert "ab-ultradeep" in cfg_custom and "build: ab-ultradeep" in cfg_custom and "tea_triage: team-fast" in cfg_custom, \
        "fixture: custom profiles not injected"
    info_cust = analyze(cfg_custom, asset_text, "0.9.0", "0.9.0")
    assert not info_cust["needs_reseed"], _public(info_cust)
    assert not info_cust["manual_review"], f"a custom profile must never be flagged: {info_cust['manual_review']}"
    # config-check's "what you've customised" axis: the added profiles + the remapped phases surface,
    # while the (default-valued) shipped profiles report no leaf retune.
    assert info_cust["custom_profiles"] == ["ab-ultradeep", "team-fast"], info_cust["custom_profiles"]
    assert {"key": "build", "value": "ab-ultradeep", "default": "ab-deep"} in info_cust["customized_phase_profiles"], info_cust["customized_phase_profiles"]
    assert {"key": "tea_triage", "value": "team-fast", "default": "ab-alt-standard"} in info_cust["customized_phase_profiles"], info_cust["customized_phase_profiles"]
    assert info_cust["customized_profiles"] == [], info_cust["customized_profiles"]
    # A custom profile is compared against the shipped field set: its persona scalar is stale, nothing else.
    assert info_cust["stale_profile_keys"] == [{"profile": "team-fast", "key": "meta:role_blurb"}], info_cust["stale_profile_keys"]
    assert info_cust["stale_phase_profiles"] == [], info_cust["stale_phase_profiles"]
    res_cust = apply(cfg_custom, asset_text, "0.9.0", "0.9.0")
    assert "ab-ultradeep" in res_cust["new_text"] and "team-fast" in res_cust["new_text"], "heal dropped a custom profile"
    assert "build: ab-ultradeep" in res_cust["new_text"] and "tea_triage: team-fast" in res_cust["new_text"], \
        "heal reverted a custom phase mapping"

    # --- manual_review: an existing profile missing a sub-key the asset has. ---
    # Drop ONLY ab-deep's claude.effort from an otherwise-complete config.
    cfg_subkey = _drop_leaf(fresh_from_asset, "ab-deep", "claude", "effort")
    assert cfg_subkey != fresh_from_asset, "fixture: ab-deep claude.effort line not dropped"
    info3 = analyze(cfg_subkey, asset_text, "0.9.0", "0.9.0")
    assert not info3["needs_reseed"], _public(info3)  # all profiles + phase_profiles still present
    assert not info3["missing_profiles"], info3["missing_profiles"]
    assert any(m["profile"] == "ab-deep" and m["missing_key"] == "claude:effort" for m in info3["manual_review"]), info3["manual_review"]
    # manual_review alone is not auto-reseeded, and apply() leaves the profile untouched.
    res3 = apply(cfg_subkey, asset_text, "0.9.0", "0.9.0")
    assert not res3["reseeded_profiles"], res3
    assert "claude:effort" in {m["missing_key"] for m in res3["manual_review"]}, res3

    # --- blank-default suppression: a config lacking the whole opencode sub-blocks must NOT nag. ---
    # opencode.model/variant ship BLANK, so a missing opencode block == the blank default == inherit;
    # flagging it as manual_review would feed status:drift (see check_file) on EVERY run for an
    # existing user, for zero action. So blank-default missing sub-keys are suppressed — while a
    # missing sub-key with a REAL default value is still flagged (info3 above proves that path).
    # Build a COMPLETE current-version config without opencode by stripping the opencode sub-blocks
    # (header + indented children/comments) out of the shipped asset.
    pre_lines, skip = [], False
    for ln in a_lines:
        s, ind = ln.strip(), len(ln) - len(ln.lstrip(" "))
        if s == "opencode:" and ind == 4:
            skip = True
            continue
        if skip:
            if s == "" or ind > 4:  # children / comment-continuation of the opencode block
                continue
            skip = False
        pre_lines.append(ln)
    pre_full = 'profiles_source_version: "0.9.0"\n' + "".join(pre_lines)
    assert not any(_strip_comment(ln.strip()) == "opencode:" for ln in pre_full.splitlines()), \
        "fixture: opencode blocks not fully stripped"
    info_pre = analyze(pre_full, asset_text, "0.9.0", "0.9.0")
    # Every profile/phase_profile is present (no reseed), the version matches, and manual_review is
    # EMPTY — the stripped (blank-default) opencode sub-keys contribute nothing. Since check_file folds
    # manual_review into status:drift, an empty manual_review here is exactly what keeps such a config
    # from nagging each run. (Setup-block drift is a separate axis tested below.)
    assert not info_pre["needs_reseed"], _public(info_pre)
    assert not info_pre["version"]["drift"], info_pre["version"]
    assert not info_pre["manual_review"], \
        f"blank-default opencode keys must NOT be flagged (would nag every run): {info_pre['manual_review']}"

    # --- version stamp absent entirely (very old config) => inserted after `version:`. ---
    no_stamp = "version: 1\nprofiles:\n  ab-deep:\n    claude:\n      model: opus\n      effort: xhigh\n"
    res4 = apply(no_stamp, asset_text, None, "0.9.0")
    assert res4["version_restamped"] == {"from": None, "to": "0.9.0"}, res4["version_restamped"]
    assert re.search(r'version: 1\nprofiles_source_version: "0\.9\.0"', res4["new_text"]), res4["new_text"][:120]

    # --- no module version supplied => no version drift signalled, no restamp. ---
    info5 = analyze(healed, asset_text, "0.9.0", None)
    assert info5["version"]["drift"] is False and info5["version"]["config_older"] is False, info5["version"]
    res5 = apply(healed, asset_text, "0.9.0", None)
    assert res5["version_restamped"] is None, res5["version_restamped"]

    # --- end-to-end via the file-driven check()/apply_to_file() on a temp dir. ---
    with tempfile.TemporaryDirectory() as td:
        cfgp = Path(td) / "config.yaml"
        cfgp.write_text(stale_cfg, encoding="utf-8")
        chk = check_file(cfgp, asset, "0.9.0")
        assert chk["status"] == "drift" and chk["needs_reseed"], chk
        app = apply_to_file(cfgp, asset, "0.9.0")
        assert app["status"] == "applied", app
        chk2 = check_file(cfgp, asset, "0.9.0")
        # Fresh despite the (informational) stale surface — stale keys are NOT part of the pause predicate.
        assert chk2["status"] == "fresh", chk2
        assert chk2["stale_phase_profiles"] == ["dev_story"] and chk2["stale_profile_keys"], chk2
        assert apply_to_file(cfgp, asset, "0.9.0")["status"] == "noop", "second apply must be a noop"

    # ----------------------------------------------------------------------- #
    # reset: restore shipped defaults (the inverse of the additive heal).      #
    # ----------------------------------------------------------------------- #
    def _mk_cfg(version: str, body: str) -> str:
        return (
            'version: 1\n'
            f'profiles_source_version: "{version}"\n'
            'delegation:\n  host: auto\n'
            'git:\n  mode: auto\n'
            'tea:\n  enabled: true\n'
        ) + body

    # ab-deep retuned (model+effort) and one phase mapping retuned, on top of the asset.
    retuned_body = _set_leaf(_set_leaf(asset_text, "ab-deep", "claude", "model", "haiku"), "ab-deep", "claude", "effort", "low")
    assert _leaf(retuned_body, "ab-deep")["claude:model"] == "haiku", "fixture: ab-deep claude block not retuned"
    retuned_body = retuned_body.replace("  build: ab-deep", "  build: ab-alt-standard", 1)
    assert "build: ab-alt-standard" in retuned_body, "fixture: build mapping not retuned"
    cfg_r = _mk_cfg("0.8.0", retuned_body)

    # Full reset: restores values, restamps, flags the layers sync (a profile changed), preserves non-asset blocks.
    full = reset(cfg_r, asset_text, "0.8.0", "0.9.0", None)
    assert not full.get("error"), full
    assert full["layers_sync_needed"] is True, full
    assert "render_needed" not in full, "render_needed is gone (D12) — the key is layers_sync_needed"
    assert full["version_restamp"] == {"from": "0.8.0", "to": "0.9.0"}, full["version_restamp"]
    changed = {(c.get("profile"), c.get("block"), c["key"]) for c in full["would_change"]}
    assert ("ab-deep", None, "claude:model") in changed, changed
    assert ("ab-deep", None, "claude:effort") in changed, changed
    assert (None, "phase_profiles", "build") in changed, changed
    ht = full["new_text"]
    h_vals = _leaf(ht, "ab-deep")
    assert h_vals["claude:model"] == "opus" and h_vals["claude:effort"] == "xhigh", h_vals
    h_lines2 = ht.splitlines(keepends=True)
    assert parse_phase_profiles(h_lines2, find_block(h_lines2, "phase_profiles")) == a_pp, "phase_profiles not restored"
    assert "delegation:" in ht and "git:" in ht and "enabled: true" in ht, "non-asset blocks dropped"
    assert 'profiles_source_version: "0.9.0"' in ht, "stamp not restamped on full reset"
    full2 = reset(ht, asset_text, "0.9.0", "0.9.0", None)  # idempotent
    assert not full2["would_change"] and full2["version_restamp"] is None, full2
    assert full2["layers_sync_needed"] is False, full2

    # Scoped (single profile): only that profile changes; OTHER retunes survive; stamp untouched.
    two = _set_leaf(_set_leaf(retuned_body, "ab-standard", "claude", "model", "sonnet"), "ab-standard", "claude", "effort", "low")
    one = reset(_mk_cfg("0.8.0", two), asset_text, "0.8.0", "0.9.0", "ab-deep")
    assert one["version_restamp"] is None, "scoped reset must NOT restamp"
    assert {c.get("profile") for c in one["would_change"]} == {"ab-deep"}, one["would_change"]
    assert one["layers_sync_needed"] is True, one
    ot = one["new_text"]
    o_x, o_h = _leaf(ot, "ab-deep"), _leaf(ot, "ab-standard")
    assert o_x["claude:model"] == "opus", "ab-deep not restored"
    assert o_h["claude:model"] == "sonnet" and o_h["claude:effort"] == "low", "ab-standard retune clobbered by scoped reset"
    assert 'profiles_source_version: "0.8.0"' in ot, "scoped reset changed the stamp"
    assert "build: ab-alt-standard" in ot, "scoped profile reset must not touch phase_profiles"

    # phase_profiles-only reset: mapping restored, profiles untouched, stamp left. layers_sync_needed is
    # true ONLY when a LAYER mapping (security_layer / cross_model_layer) changes — the review-layers
    # TOML bakes model+effort from those two profiles; any other remap is read at spawn time.
    pres = reset(_mk_cfg("0.8.0", asset_text.replace("  tea_triage: ab-alt-standard", "  tea_triage: ab-standard", 1)),
                 asset_text, "0.8.0", "0.9.0", "phase_profiles")
    assert pres["layers_sync_needed"] is False, pres
    assert pres["version_restamp"] is None, pres
    assert {(c.get("block"), c["key"]) for c in pres["would_change"]} == {("phase_profiles", "tea_triage")}, pres["would_change"]
    pt = pres["new_text"]
    assert parse_phase_profiles(pt.splitlines(keepends=True), find_block(pt.splitlines(keepends=True), "phase_profiles")) == a_pp, "phase_profiles not restored"
    for layer_key, other in (("security_layer", "ab-deep"), ("cross_model_layer", "ab-deep")):
        remapped = asset_text.replace(f"  {layer_key}: {a_pp[layer_key]}", f"  {layer_key}: {other}", 1)
        assert f"{layer_key}: {other}" in remapped, f"fixture: {layer_key} not remapped"
        lp = reset(_mk_cfg("0.9.0", remapped), asset_text, "0.9.0", "0.9.0", "phase_profiles")
        assert lp["layers_sync_needed"] is True, f"remapping {layer_key} must flag a layers sync: {lp}"
        assert {(c.get("block"), c["key"]) for c in lp["would_change"]} == {("phase_profiles", layer_key)}, lp["would_change"]
    # A stale (removed) mapping is pruned by a phase_profiles reset — reported with default None.
    st = reset(_mk_cfg("0.9.0", asset_text.replace("phase_profiles:\n", "phase_profiles:\n  dev_story: ab-deep\n", 1)),
               asset_text, "0.9.0", "0.9.0", "phase_profiles")
    assert {"block": "phase_profiles", "key": "dev_story", "current": "ab-deep", "default": None} in st["would_change"], st["would_change"]
    assert "dev_story" not in st["new_text"], "stale phase mapping survived a phase_profiles reset"
    assert st["layers_sync_needed"] is False, st

    # reset <profile> is the remedy for a manual_review (missing sub-key) that --apply won't write.
    cfg_drop = _mk_cfg("0.9.0", _drop_leaf(asset_text, "ab-deep", "claude", "effort"))
    assert any(m["profile"] == "ab-deep" and m["missing_key"] == "claude:effort"
               for m in analyze(cfg_drop, asset_text, "0.9.0", "0.9.0")["manual_review"]), "fixture: missing sub-key not detected"
    fixed = reset(cfg_drop, asset_text, "0.9.0", "0.9.0", "ab-deep")["new_text"]
    assert not analyze(fixed, asset_text, "0.9.0", "0.9.0")["manual_review"], "reset did not heal the missing sub-key"

    # A whole-block reset ('profiles'/both) PRUNES a config-only profile so the set matches the
    # shipped asset (the rename/remove remedy); a single <profile-name> reset never prunes.
    mini = (
        'version: 1\nprofiles_source_version: "0.9.0"\n'
        'profiles:\n'
        '  ab-deep:\n    description: "x"\n    claude:\n      model: haiku\n      effort: low\n'
        '    codex:\n      model: gpt-x\n      reasoning_effort: low\n'
        '  ab-custom:\n    description: "mine"\n    claude:\n      model: opus\n      effort: medium\n'
        'phase_profiles:\n  build: ab-deep\n'
    )
    rprof = reset(mini, asset_text, "0.9.0", "0.9.0", "profiles")
    assert rprof["removed_profiles"] == ["ab-custom"], rprof["removed_profiles"]
    assert rprof["layers_sync_needed"] is True, "pruning a profile must flag a layers sync"
    rt = rprof["new_text"]
    r_lines = rt.splitlines(keepends=True)
    rp = parse_profiles_blocks(r_lines, find_block(r_lines, "profiles"))
    assert "ab-custom" not in rp and "ab-custom" not in rt, "config-only profile not pruned by 'profiles' reset"
    assert set(rp) == set(PROFILE_NAMES), sorted(rp)
    assert _leaf(rt, "ab-deep")["claude:model"] == "opus", "ab-deep not reset"
    assert parse_phase_profiles(r_lines, find_block(r_lines, "phase_profiles")) == {"build": "ab-deep"}, "phase_profiles touched by 'profiles' scope"
    # A single <profile-name> reset leaves the user-added profile intact (no prune on a scoped reset).
    rone = reset(mini, asset_text, "0.9.0", "0.9.0", "ab-deep")
    assert rone["removed_profiles"] == [], "single-profile reset must not prune"
    r1 = rone["new_text"].splitlines(keepends=True)
    rs = parse_profiles_blocks(r1, find_block(r1, "profiles"))
    assert "ab-custom" in rs, "single-profile reset clobbered a user-added profile"
    rc = _leaf(rone["new_text"], "ab-custom")
    assert rc["claude:model"] == "opus" and rc["claude:effort"] == "medium", "ab-custom altered by scoped reset"
    assert reset(mini, asset_text, "0.9.0", "0.9.0", "ab-nope").get("error") == "unknown_scope", "unknown profile accepted as scope"
    assert reset(mini, asset_text, "0.9.0", "0.9.0", "ab-custom").get("error") == "unknown_scope", "config-only profile is not an asset scope"

    # Upgrade migration (0.26 -> 0.27): a config carrying the dropped `ab-verification` profile and
    # persona strings on a shipped profile. A whole-block reset prunes BOTH: the profile lands on
    # `removed_profiles`, each persona key on `would_change` with `default: None`; the result reads
    # fully fresh with an EMPTY stale surface.
    upgraded = asset_text.replace(
        "\nprofiles:\n  ab-deep:",
        '\nprofiles:\n  ab-verification:\n    description: "old lens"\n    claude:\n      model: opus\n'
        '      effort: high\n    codex:\n      model: gpt-x\n      reasoning_effort: high\n'
        '  ab-deep:\n    description: "deep"\n    role_blurb: "deep work"\n    status_example: "ok"', 1)
    assert "ab-verification" in upgraded and 'role_blurb: "deep work"' in upgraded, "fixture: upgrade leftovers not injected"
    up_info = analyze(_mk_cfg("0.9.0", upgraded), asset_text, "0.9.0", "0.9.0")
    assert up_info["custom_profiles"] == ["ab-verification"], up_info["custom_profiles"]   # merely custom to the heal
    assert {"profile": "ab-deep", "key": "meta:role_blurb"} in up_info["stale_profile_keys"], up_info["stale_profile_keys"]
    up = reset(_mk_cfg("0.9.0", upgraded), asset_text, "0.9.0", "0.9.0", None)
    assert up["removed_profiles"] == ["ab-verification"], up["removed_profiles"]
    assert {"profile": "ab-deep", "key": "meta:role_blurb", "current": "deep work", "default": None} in up["would_change"], up["would_change"]
    assert up["layers_sync_needed"] is True, up
    assert "ab-verification" not in up["new_text"] and "role_blurb" not in up["new_text"], "upgrade leftovers survived a full reset"
    up_after = analyze(up["new_text"], asset_text, "0.9.0", "0.9.0")
    assert up_after["stale_profile_keys"] == [] and up_after["custom_profiles"] == [] and not up_after["manual_review"], _public(up_after)

    # Rename migration: every config profile name differs from the asset. A full reset prunes them
    # all and seeds the asset set — config ends fully on new names.
    renamed = asset_text
    for cur, old in (("  ab-deep:", "  zz-old-a:"), ("  ab-standard:", "  zz-old-b:"),
                     ("  ab-alt-deep:", "  zz-old-c:"), ("  ab-alt-standard:", "  zz-old-d:")):
        renamed = renamed.replace(cur, old, 1)
    assert renamed.count("zz-old-") == 4, "fixture: profile headers not all renamed"
    mig = reset(_mk_cfg("0.8.0", renamed), asset_text, "0.8.0", "0.9.0", None)
    assert set(mig["removed_profiles"]) == {"zz-old-a", "zz-old-b", "zz-old-c", "zz-old-d"}, mig["removed_profiles"]
    assert "zz-old-" not in mig["new_text"], "orphan old-named blocks survived the migration reset"
    mig_lines = mig["new_text"].splitlines(keepends=True)
    mig_prof = parse_profiles_blocks(mig_lines, find_block(mig_lines, "profiles"))
    assert set(mig_prof) == set(PROFILE_NAMES), sorted(mig_prof)
    assert parse_phase_profiles(mig_lines, find_block(mig_lines, "phase_profiles")) == a_pp, "phase_profiles not reset in migration"

    # A config missing an entire asset block has it recreated — plan and write agree.
    no_pp = _mk_cfg("0.8.0", asset_text[:asset_text.index("phase_profiles:")])
    assert find_block(no_pp.splitlines(keepends=True), "phase_profiles") is None, "fixture: phase_profiles still present"
    rec = reset(no_pp, asset_text, "0.8.0", "0.9.0", None)
    assert any(c.get("block") == "phase_profiles" for c in rec["would_change"]), "plan omits the missing block"
    rl = rec["new_text"].splitlines(keepends=True)
    assert parse_phase_profiles(rl, find_block(rl, "phase_profiles")) == a_pp, "missing phase_profiles not recreated"
    # ... likewise a config with no `profiles:` block at all.
    no_prof = _mk_cfg("0.8.0", asset_text[asset_text.index("phase_profiles:"):])
    assert find_block(no_prof.splitlines(keepends=True), "profiles") is None, "fixture: profiles still present"
    rec2 = reset(no_prof, asset_text, "0.8.0", "0.9.0", "profiles")
    r2l = rec2["new_text"].splitlines(keepends=True)
    assert set(parse_profiles_blocks(r2l, find_block(r2l, "profiles"))) == set(PROFILE_NAMES), "missing profiles block not recreated"

    # File-driven: read-only plan writes nothing; --write backs up then resets; re-run is a noop.
    with tempfile.TemporaryDirectory() as td:
        cp = Path(td) / "config.yaml"
        cp.write_text(cfg_r, encoding="utf-8")
        plan = reset_to_file(cp, asset, "0.9.0", scope=None, write=False)
        assert plan["status"] == "reset-plan" and plan["would_change"] and plan["backup"] is None, plan
        assert plan["layers_sync_needed"] is True and "render_needed" not in plan, plan
        assert not (Path(str(cp) + ".bak")).exists(), "read-only plan must not write a .bak"
        done = reset_to_file(cp, asset, "0.9.0", scope=None, write=True)
        assert done["status"] == "reset" and done["backup"] == str(cp) + ".bak", done
        assert Path(done["backup"]).read_text(encoding="utf-8") == cfg_r, "backup must hold the original"
        assert reset_to_file(cp, asset, "0.9.0", scope=None, write=True)["status"] == "noop", "second reset should be a noop"
        assert reset_to_file(cp, asset, "0.9.0", scope="ab-nope", write=False)["status"] == "error", "bad scope must error"

    # Pure prune through reset_to_file: the asset profiles already at shipped values (empty
    # would_change) + scope 'profiles' (no restamp), so `removed_profiles` is the SOLE trigger of the
    # write — the headline "I added a custom profile, reset-defaults should drop it" path.
    with tempfile.TemporaryDirectory() as tdp:
        extra = asset_text.replace(
            "\nprofiles:\n",
            '\nprofiles:\n  ab-extra:\n    claude:\n      model: opus\n'
            '      effort: low\n    codex:\n      model: gpt-x\n      reasoning_effort: low\n', 1)
        cpp = Path(tdp) / "config.yaml"
        cpp.write_text(_mk_cfg("0.9.0", extra), encoding="utf-8")
        pl = reset_to_file(cpp, asset, "0.9.0", scope="profiles", write=False)
        assert pl["would_change"] == [] and pl["removed_profiles"] == ["ab-extra"], pl
        wr = reset_to_file(cpp, asset, "0.9.0", scope="profiles", write=True)
        assert wr["status"] == "reset", f"removed_profiles alone must trigger a write, got {wr['status']}"
        assert wr["removed_profiles"] == ["ab-extra"], wr
        assert "ab-extra" not in cpp.read_text(encoding="utf-8"), "orphan survived a confirmed prune"

    # ----------------------------------------------------------------------- #
    # Setup-block additive heal (config-defaults.yaml). The delegation/tea/git/  #
    # code_review/build blocks have no profiles-style asset, so new setup keys   #
    # never reached an existing config; plan_setup/apply close that gap,        #
    # append-only.                                                              #
    # ----------------------------------------------------------------------- #
    setup_asset = _default_setup_defaults()
    assert setup_asset.is_file(), f"shipped config-defaults.yaml missing at {setup_asset}"
    setup_text = setup_asset.read_text(encoding="utf-8")
    s_nodes = parse_tree(setup_text.splitlines(keepends=True), 0, len(setup_text.splitlines(keepends=True)), 0)

    # The asset carries EXACTLY the five setup blocks ...
    assert set(s_nodes) == {"delegation", "tea", "git", "code_review", "build"}, sorted(s_nodes)
    # ... and INCLUDES the constant-default setup keys ...
    assert "cli_phases" in s_nodes["delegation"]["children"], "asset missing delegation.cli_phases"
    for k in ("branch_prefix", "epic_branch_prefix", "offer_merge", "ci_wait_minutes"):
        assert k in s_nodes["git"]["children"], f"asset missing git.{k}"
    assert "gate_max_iterations" in s_nodes["tea"]["children"], "asset missing tea.gate_max_iterations"
    sta = s_nodes["tea"]["children"].get("story_trace_advisory")
    assert sta and {"enabled", "min_epic_stories", "skip_last_stories"}.issubset(set(sta["children"])), "asset story_trace_advisory shape"
    assert set(s_nodes["code_review"]["children"]) == {"followup", "security_layer"}, sorted(s_nodes["code_review"]["children"])
    assert set(s_nodes["build"]["children"]) == {"spec_approval"}, sorted(s_nodes["build"]["children"])
    # Removed keys must never be re-healed into configs (a stale copy in a user config is harmless —
    # the orchestrator just stops reading it). Removed-key guards:
    assert "target_tools" not in s_nodes["delegation"]["children"], "asset must NOT carry delegation.target_tools (removed — no rendered agents)"
    for k in ("max_iterations", "security_review", "verification_gap", "epic_review", "tier_a_lenses",
              "epic_diff_chunk_threshold_lines", "alternate_models", "skip_hitl_on_clean_convergence"):
        assert k not in s_nodes["code_review"]["children"], f"asset must NOT carry removed key code_review.{k}"

    # ... and DELIBERATELY EXCLUDES environment-detected / interviewed fields, so the heal can
    # never bake in a wrong static guess for one (the safety invariant — enforced here in code).
    assert "base_branch" not in s_nodes["git"]["children"], "asset must NOT carry git.base_branch (detected)"
    assert "mode" not in s_nodes["git"]["children"], "asset must NOT carry git.mode (detect toggle)"
    for k in ("host", "mode"):
        assert k not in s_nodes["delegation"]["children"], f"asset must NOT carry delegation.{k}"
    for k in ("enabled", "framework_ci"):
        assert k not in s_nodes["tea"]["children"], f"asset must NOT carry tea.{k} (interviewed)"
    assert "cross_model_layer" not in s_nodes["code_review"]["children"], \
        "asset must NOT carry code_review.cross_model_layer (env-detected at first run; absent key => blank)"

    # Anchor the literal DEFAULT VALUES — the set assertions above pin which keys exist, these
    # pin that their values still match the state-and-resume.md schema + orchestrator fallbacks
    # (the lockstep the asset header warns about). Cheap guard against a silent value edit.
    for kv in ("cli_phases: {}", 'branch_prefix: "story/"', 'epic_branch_prefix: "epic/"', "offer_merge: true",
               "ci_wait_minutes: 30", "gate_max_iterations: 2", "enabled: true", "min_epic_stories: 6",
               "skip_last_stories: 3", "followup: recommended", "security_layer: true", "spec_approval: false"):
        assert kv in setup_text, f"asset default drifted from the documented schema: expected `{kv}`"

    def _heal(cfg: str) -> tuple:
        res = apply(cfg, asset_text, "0.9.0", "0.9.0", setup_text)
        return res["new_text"], res["reseeded_setup"]

    def _setup_nodes(text: str) -> dict:
        ls = text.splitlines(keepends=True)
        return parse_tree(ls, 0, len(ls), 0)

    base = 'version: 1\nprofiles_source_version: "0.9.0"\n'  # minimal non-setup head

    # Case 1 — whole top-level setup blocks absent => recreated (appended at EOF).
    c1 = base + 'delegation:\n  host: auto\n  cli_phases: {}\n'  # no tea/git/code_review/build
    h1, paths1 = _heal(c1)
    n1 = _setup_nodes(h1)
    assert {"git", "tea", "code_review", "build"}.issubset(set(n1)), f"missing top blocks not recreated: {sorted(n1)}"
    assert {"git", "tea", "code_review", "build"}.issubset(set(paths1)), f"whole-block heals not reported: {paths1}"
    assert "delegation" not in paths1, "delegation present yet reported as healed"
    assert {"branch_prefix", "offer_merge", "ci_wait_minutes"}.issubset(set(n1["git"]["children"])), n1["git"]["children"].keys()
    assert n1["build"]["children"]["spec_approval"]["kind"] == "scalar", n1["build"]
    assert _leaf_value(h1.splitlines(keepends=True), n1["build"]["children"]["spec_approval"]) == "false", h1
    assert _leaf_value(h1.splitlines(keepends=True), n1["code_review"]["children"]["followup"]) == "recommended", h1

    # Case 2 — a scalar missing from an existing block => appended in that block; a detected value
    # the asset omits (base_branch) is left exactly as the user had it.
    c2 = base + 'git:\n  mode: auto\n  base_branch: develop\n'
    h2, paths2 = _heal(c2)
    n2 = _setup_nodes(h2)
    assert {"offer_merge", "ci_wait_minutes", "branch_prefix"}.issubset(set(n2["git"]["children"])), n2["git"]["children"].keys()
    assert {"git.offer_merge", "git.ci_wait_minutes"}.issubset(set(paths2)), paths2
    assert "base_branch: develop" in h2, "user's detected base_branch must be preserved"

    # Case 3 — a whole sub-block missing from an existing block => appended in that block; an
    # interviewed answer the asset omits (tea.enabled=false) is never reset to the default.
    c3 = base + 'tea:\n  enabled: false\n'
    h3, paths3 = _heal(c3)
    n3 = _setup_nodes(h3)
    sta3 = n3["tea"]["children"].get("story_trace_advisory")
    assert sta3 and sta3["kind"] == "map", "story_trace_advisory sub-block not added"
    assert {"enabled", "min_epic_stories", "skip_last_stories"}.issubset(set(sta3["children"])), sta3["children"].keys()
    assert "tea.story_trace_advisory" in paths3, paths3
    assert "enabled: false" in h3, "tea.enabled customisation lost"

    # Case 4 + collision — a scalar missing INSIDE an existing sub-block that is the block's LAST
    # child, while the block itself also gains a key. Both heal, with correct nesting + ordering.
    c4 = (base + 'tea:\n  enabled: true\n  story_trace_advisory:\n'
          '    enabled: true\n    min_epic_stories: 6\n')   # missing skip_last_stories + gate_max_iterations
    h4, paths4 = _heal(c4)
    n4 = _setup_nodes(h4)
    assert "skip_last_stories" in n4["tea"]["children"]["story_trace_advisory"]["children"], "deep scalar not healed"
    assert "gate_max_iterations" in n4["tea"]["children"], "block-level scalar not healed alongside the deep one"
    assert {"tea.gate_max_iterations", "tea.story_trace_advisory.skip_last_stories"}.issubset(set(paths4)), paths4
    # The deep scalar must stay INSIDE the sub-block (indent 4); the shallow one becomes a new tea
    # key (indent 2) AFTER it — so skip_last_stories appears before gate_max_iterations.
    assert h4.index("skip_last_stories") < h4.index("gate_max_iterations"), "collision insert mis-ordered"
    assert "    skip_last_stories" in h4, "deep scalar not at indent 4"
    assert "  gate_max_iterations" in h4 and "    gate_max_iterations" not in h4, "block scalar not at indent 2"

    # Append-only: a user's customised setup value is NEVER overwritten by the heal.
    c5 = (base + 'git:\n  mode: auto\n  offer_merge: false\n  ci_wait_minutes: 90\n'
          'code_review:\n  followup: always\n  cross_model_layer: claude\n'
          'build:\n  spec_approval: true\n')
    h5, paths5 = _heal(c5)
    assert "offer_merge: false" in h5, "offer_merge:false overwritten"
    assert "ci_wait_minutes: 90" in h5, "ci_wait_minutes:90 overwritten"
    assert "followup: always" in h5 and "spec_approval: true" in h5, "code_review/build customisation overwritten"
    assert "cross_model_layer: claude" in h5, "an interviewed answer the asset omits must survive untouched"
    assert "git.offer_merge" not in paths5 and "git.ci_wait_minutes" not in paths5, paths5
    assert "code_review.followup" not in paths5 and "build.spec_approval" not in paths5, paths5
    assert "git.branch_prefix" in paths5 and "code_review.security_layer" in paths5, "a still-missing key was not healed"

    # Idempotency: a config already carrying every setup key heals to nothing, and --check agrees.
    full_setup = base + setup_text   # head + the asset's blocks verbatim = every setup key present
    assert _heal(full_setup)[1] == [], "fully-populated config should heal nothing"
    assert analyze(full_setup, asset_text, "0.9.0", "0.9.0", setup_text)["missing_setup"] == [], "fresh config flagged"
    mp = analyze(c2, asset_text, "0.9.0", "0.9.0", setup_text)["missing_setup"]
    assert {"git.offer_merge", "git.ci_wait_minutes"}.issubset(set(mp)), mp

    # added_setup / kept_setup — the two human-facing lists for the Phase 0 echo (show-don't-block).
    a2 = analyze(c2, asset_text, "0.9.0", "0.9.0", setup_text)
    off = next(x for x in a2["added_setup"] if x["path"] == "git.offer_merge")
    assert off["value"] == "true", off                          # scalar value surfaced
    assert {x["path"] for x in a2["kept_setup"]} == set(), "c2 carries no asset-key customisation"
    assert "git.base_branch" not in {x["path"] for x in a2["added_setup"]}, "a detected field must never be 'added'"
    bld = next(x for x in a2["added_setup"] if x["path"] == "build")
    assert bld["value"] == "{spec_approval: false}", bld        # whole missing block summarised

    a3 = analyze(c3, asset_text, "0.9.0", "0.9.0", setup_text)
    sta_added = next(x for x in a3["added_setup"] if x["path"] == "tea.story_trace_advisory")
    assert sta_added["value"] == "{enabled: true, min_epic_stories: 6, skip_last_stories: 3}", sta_added  # whole sub-block summarised

    a5 = analyze(c5, asset_text, "0.9.0", "0.9.0", setup_text)
    kept5 = {x["path"]: (x["value"], x["default"]) for x in a5["kept_setup"]}
    assert kept5.get("git.offer_merge") == ("false", "true"), kept5   # customisation kept, with its default shown
    assert kept5.get("git.ci_wait_minutes") == ("90", "30"), kept5
    assert kept5.get("code_review.followup") == ("always", "recommended"), kept5
    assert kept5.get("build.spec_approval") == ("true", "false"), kept5
    assert "git.branch_prefix" not in kept5, "a missing key is 'added', never 'kept'"
    assert "code_review.cross_model_layer" not in kept5, "a non-asset (interviewed) key is never 'kept'"

    # kept detection reaches a customised leaf INSIDE a sub-block; a leaf equal to default is not kept.
    c7 = (base + 'tea:\n  gate_max_iterations: 2\n  story_trace_advisory:\n'
          '    enabled: true\n    min_epic_stories: 8\n    skip_last_stories: 3\n')
    kept7 = {x["path"]: (x["value"], x["default"]) for x in analyze(c7, asset_text, "0.9.0", "0.9.0", setup_text)["kept_setup"]}
    assert kept7.get("tea.story_trace_advisory.min_epic_stories") == ("8", "6"), kept7
    assert "tea.gate_max_iterations" not in kept7, "a leaf equal to default must not be reported as 'kept'"

    # setup_answers — the heal-immune behavioural answers (cli_phases / tea.enabled / tea.framework_ci /
    # git.mode / code_review.cross_model_layer) the asset omits, so they never surface in
    # added_setup/kept_setup. config-check shows them so the user sees EVERY deviation; absent fields
    # are skipped; a populated cli_phases is summarised as a map.
    assert set(SETUP_ANSWER_PATHS) == {"delegation.cli_phases", "tea.enabled", "tea.framework_ci", "git.mode",
                                       "code_review.cross_model_layer"}, SETUP_ANSWER_PATHS
    sa_cfg = (base + 'delegation:\n  host: auto\n  cli_phases:\n    followup_review: opencode\n'
              'tea:\n  enabled: false\n  framework_ci: skip\n'
              'git:\n  mode: local\n  base_branch: main\n'
              'code_review:\n  followup: recommended\n  security_layer: true\n  cross_model_layer: codex\n')
    sa = {x["path"]: x["value"] for x in analyze(sa_cfg, asset_text, "0.9.0", "0.9.0", setup_text)["setup_answers"]}
    assert sa.get("delegation.cli_phases") == "{followup_review: opencode}", sa
    assert sa.get("tea.enabled") == "false" and sa.get("tea.framework_ci") == "skip", sa
    assert sa.get("git.mode") == "local", sa                          # a forced git mode is a deviation
    assert sa.get("code_review.cross_model_layer") == "codex", sa      # the detected/chosen cross-model tool
    assert "git.base_branch" not in sa, "a purely-detected env fact must not surface as a setup answer"
    assert "code_review.followup" not in sa, "an asset-sourced key rides added/kept, not setup_answers"
    # An empty cli_phases surfaces as `{}`; a blank cross_model_layer ("" => layer disabled) surfaces as
    # an empty value; a config that omits an answer entirely surfaces nothing.
    sa_empty = {x["path"]: x["value"] for x in analyze(base + 'delegation:\n  cli_phases: {}\ncode_review:\n  cross_model_layer: ""\n',
                                                        asset_text, "0.9.0", "0.9.0", setup_text)["setup_answers"]}
    assert sa_empty == {"delegation.cli_phases": "{}", "code_review.cross_model_layer": ""}, sa_empty   # tea.* absent => not surfaced
    assert collect_setup_answers(base.splitlines(keepends=True)) == [], "no setup answers => empty list"
    # setup_answers is asset-independent (computed even with no config-defaults asset) and rides --check.
    assert analyze(sa_cfg, asset_text, "0.9.0", "0.9.0", None)["setup_answers"], "setup_answers must not depend on setup_text"

    # Cross-axis collision — a missing phase_profiles key AND a missing whole top-level setup block
    # (build), with phase_profiles as the file's LAST block, so BOTH inserts anchor on the same
    # EOF line. The pp key must stay inside phase_profiles (indent 2); the setup block starts fresh
    # (indent 0) AFTER it — i.e. the tiebreak keeps the deeper insert nearest the anchor.
    xcfg = (
        'profiles_source_version: "0.8.0"\n'
        'delegation:\n  cli_phases: {}\n'
        'tea:\n  gate_max_iterations: 2\n  story_trace_advisory:\n'
        '    enabled: true\n    min_epic_stories: 6\n    skip_last_stories: 3\n'
        'git:\n  branch_prefix: "story/"\n  epic_branch_prefix: "epic/"\n  offer_merge: true\n  ci_wait_minutes: 30\n'
        'code_review:\n  followup: recommended\n  security_layer: true\n'
        # no build block; profiles + phase_profiles (last) follow, with one pp key dropped:
        + asset_text.replace("  retrospective: ab-alt-standard", "  # (retrospective dropped)", 1)
    )
    assert "retrospective: ab-alt-standard" not in xcfg, "fixture: pp key not actually dropped"
    xh = apply(xcfg, asset_text, "0.8.0", "0.9.0", setup_text)["new_text"]
    assert "build" in _setup_nodes(xh), "missing top-level setup block not recreated (cross-axis)"
    xpp = parse_phase_profiles(xh.splitlines(keepends=True), find_block(xh.splitlines(keepends=True), "phase_profiles"))
    assert xpp.get("retrospective") == "ab-alt-standard", "phase_profiles key not re-seeded (cross-axis)"
    assert xh.index("retrospective: ab-alt-standard") < xh.index("\nbuild:"), "collision mis-ordered: pp key escaped its block"
    assert analyze(xh, asset_text, "0.9.0", "0.9.0", setup_text)["missing_setup"] == [], "cross-axis heal left setup drift"

    # File-driven, the orchestrator's ACTUAL trigger: a config at the CURRENT version (profiles fresh)
    # missing ONLY a setup key must still read as `drift` via check_file -> --apply heals it -> fresh.
    # This is the user's literal scenario: already upgraded, a setup key still absent. The config also
    # carries every REMOVED setup key an upgraded 0.26 config still holds (delegation.target_tools + the
    # old code_review.* knobs): the heal must IGNORE them — never flag, never strip, never echo.
    REMOVED_SETUP = ("delegation.target_tools", "code_review.max_iterations", "code_review.security_review",
                     "code_review.verification_gap", "code_review.epic_review", "code_review.tier_a_lenses",
                     "code_review.epic_diff_chunk_threshold_lines", "code_review.alternate_models",
                     "code_review.skip_hitl_on_clean_convergence")
    with tempfile.TemporaryDirectory() as td:
        cfgp = Path(td) / "config.yaml"
        cur = ('profiles_source_version: "0.9.0"\n' + asset_text          # profiles/phase_profiles fresh
               + '\ndelegation:\n  host: auto\n  mode: custom-subagents\n'  # legacy tier alias — tolerated
               '  target_tools: [claude, codex]\n  cli_phases: {}\n'
               'tea:\n  gate_max_iterations: 2\n  story_trace_advisory:\n'
               '    enabled: true\n    min_epic_stories: 6\n    skip_last_stories: 3\n'
               'git:\n  branch_prefix: "story/"\n  epic_branch_prefix: "epic/"\n'
               '  ci_wait_minutes: 30\n'   # <- git.offer_merge missing
               'code_review:\n  followup: recommended\n  security_layer: true\n'
               '  max_iterations: 2\n  security_review: true\n  verification_gap: true\n'
               '  epic_review: true\n  tier_a_lenses: [auditor, security]\n'
               '  epic_diff_chunk_threshold_lines: 6000\n  alternate_models: true\n'
               '  skip_hitl_on_clean_convergence: false\n'
               'build:\n  spec_approval: false\n')
        cfgp.write_text(cur, encoding="utf-8")
        chk = check_file(cfgp, asset, "0.9.0", setup_asset)
        assert chk["version"]["drift"] is False, "fixture must isolate the setup-only path (no version drift)"
        assert chk["status"] == "drift", f"same-version config missing a setup key must read as drift: {chk}"
        assert chk["missing_setup"] == ["git.offer_merge"], chk["missing_setup"]
        echoed = {x["path"] for x in chk["added_setup"]} | {x["path"] for x in chk["kept_setup"]} | {x["path"] for x in chk["setup_answers"]}
        assert not (echoed & set(REMOVED_SETUP)), f"removed keys must never be echoed: {echoed & set(REMOVED_SETUP)}"
        app = apply_to_file(cfgp, asset, "0.9.0", setup_asset)
        assert app["reseeded_setup"] == ["git.offer_merge"], app
        after = cfgp.read_text(encoding="utf-8")
        for stale_line in ("target_tools: [claude, codex]", "max_iterations: 2", "security_review: true",
                           "verification_gap: true", "epic_review: true", "tier_a_lenses: [auditor, security]",
                           "epic_diff_chunk_threshold_lines: 6000", "alternate_models: true",
                           "skip_hitl_on_clean_convergence: false", "mode: custom-subagents"):
            assert stale_line in after, f"heal must never strip a stale key: {stale_line}"
        assert check_file(cfgp, asset, "0.9.0", setup_asset)["status"] == "fresh", "heal did not clear the setup-only drift"

    # A config with NO config-defaults asset available: the setup heal degrades gracefully (skipped).
    with tempfile.TemporaryDirectory() as td:
        cfgp = Path(td) / "config.yaml"
        cfgp.write_text('profiles_source_version: "0.9.0"\n' + asset_text, encoding="utf-8")
        chk_nosetup = check_file(cfgp, asset, "0.9.0", Path(td) / "absent-config-defaults.yaml")
        assert chk_nosetup["status"] == "fresh" and chk_nosetup["missing_setup"] == [], chk_nosetup

    # ----------------------------------------------------------------------- #
    # apply() on a config with NO `profiles:` / `phase_profiles:` HEADER: the   #
    # block is RECREATED at EOF (reset's trailing path), so the reseeded_*      #
    # lists never claim keys the write did not produce.                        #
    # ----------------------------------------------------------------------- #
    headless = 'version: 1\nprofiles_source_version: "0.8.0"\ngit:\n  mode: auto\n'
    hl_lines = headless.splitlines(keepends=True)
    assert find_block(hl_lines, "profiles") is None and find_block(hl_lines, "phase_profiles") is None, \
        "fixture: headless config still carries an asset block"
    res_hl = apply(headless, asset_text, "0.8.0", "0.9.0")
    t_hl = res_hl["new_text"]
    l_hl = t_hl.splitlines(keepends=True)
    got_prof = parse_profiles_blocks(l_hl, find_block(l_hl, "profiles"))
    got_pp = parse_phase_profiles(l_hl, find_block(l_hl, "phase_profiles"))
    # Everything the result CLAIMS was reseeded is actually in the written text.
    assert set(res_hl["reseeded_profiles"]) == set(PROFILE_NAMES), res_hl["reseeded_profiles"]
    assert set(got_prof) == set(res_hl["reseeded_profiles"]), \
        f"reseeded_profiles claimed but not written: {sorted(set(res_hl['reseeded_profiles']) - set(got_prof))}"
    assert res_hl["reseeded_phase_profiles"] == a_pp, res_hl["reseeded_phase_profiles"]
    assert got_pp == res_hl["reseeded_phase_profiles"], \
        f"reseeded_phase_profiles claimed but not written: {got_pp}"
    assert "mode: auto" in t_hl, "recreation clobbered an existing block"
    # ... and the recreated config re-reads as fully fresh (idempotent second apply).
    info_hl = analyze(t_hl, asset_text, "0.9.0", "0.9.0")
    assert not info_hl["needs_reseed"] and not info_hl["manual_review"], _public(info_hl)
    assert apply(t_hl, asset_text, "0.9.0", "0.9.0")["reseeded_profiles"] == [], "second apply must reseed nothing"
    # Same for a config missing only ONE of the two headers (profiles present, phase_profiles gone).
    only_prof = 'profiles_source_version: "0.9.0"\n' + asset_text[:asset_text.index("phase_profiles:")]
    assert find_block(only_prof.splitlines(keepends=True), "phase_profiles") is None, "fixture: phase_profiles present"
    res_op = apply(only_prof, asset_text, "0.9.0", "0.9.0")
    op_lines = res_op["new_text"].splitlines(keepends=True)
    assert parse_phase_profiles(op_lines, find_block(op_lines, "phase_profiles")) == a_pp, "phase_profiles not recreated"
    assert res_op["reseeded_phase_profiles"] == a_pp, res_op["reseeded_phase_profiles"]

    # ----------------------------------------------------------------------- #
    # legacy_mode_alias: informational only (the pre-0.27 `custom-subagents`).  #
    # ----------------------------------------------------------------------- #
    legacy_cfg = base + "delegation:\n  host: auto\n  mode: custom-subagents\n"
    assert analyze(legacy_cfg, asset_text, "0.9.0", "0.9.0", setup_text)["legacy_mode_alias"] is True, "legacy alias not detected"
    for mode_line in ("  mode: subagents\n", "  mode: inline\n", ""):
        cfg_m = base + "delegation:\n  host: auto\n" + mode_line
        assert analyze(cfg_m, asset_text, "0.9.0", "0.9.0", setup_text)["legacy_mode_alias"] is False, mode_line
    # It rides --check, and never changes the verdict on an otherwise-fresh config.
    with tempfile.TemporaryDirectory() as td:
        cfgp = Path(td) / "config.yaml"
        fresh_legacy = ('profiles_source_version: "0.9.0"\n' + asset_text + setup_text).replace(
            "\ndelegation:\n", "\ndelegation:\n  host: auto\n  mode: custom-subagents\n", 1)
        assert "mode: custom-subagents" in fresh_legacy, "fixture: legacy alias not injected"
        cfgp.write_text(fresh_legacy, encoding="utf-8")
        chk_legacy = check_file(cfgp, asset, "0.9.0", setup_asset)
        assert chk_legacy["legacy_mode_alias"] is True, chk_legacy["legacy_mode_alias"]
        assert chk_legacy["status"] == "fresh", f"legacy alias must not create drift: {chk_legacy}"

    # ----------------------------------------------------------------------- #
    # Byte preservation: CRLF configs round-trip (read/write use newline="").   #
    # ----------------------------------------------------------------------- #
    with tempfile.TemporaryDirectory() as td:
        cfgp = Path(td) / "config.yaml"
        crlf_src = ('profiles_source_version: "0.9.0"\n' + asset_text
                    + "delegation:\n  cli_phases: {}\ngit:\n  mode: auto\n  ci_wait_minutes: 30\n")
        cfgp.write_bytes(crlf_src.replace("\n", "\r\n").encode("utf-8"))
        assert "\r\n" in _read_text(cfgp), "_read_text must NOT translate CRLF away"
        assert "\r\n" not in cfgp.read_text(encoding="utf-8"), "fixture: universal-newlines read would hide the CRLFs"
        app_crlf = apply_to_file(cfgp, asset, "0.9.0", setup_asset)
        assert app_crlf["status"] == "applied" and app_crlf["reseeded_setup"], app_crlf
        raw = cfgp.read_bytes()
        assert b"git:\r\n  mode: auto\r\n  ci_wait_minutes: 30\r\n" in raw, "existing CRLF lines were rewritten to LF"
        assert raw.count(b"\r\n") >= crlf_src.count("\n") - 1, "the file was silently converted to LF"
        assert check_file(cfgp, asset, "0.9.0", setup_asset)["status"] == "fresh", "CRLF heal did not clear the drift"

    # ----------------------------------------------------------------------- #
    # main() end-to-end via subprocess: exit codes + one JSON object on stdout. #
    # ----------------------------------------------------------------------- #
    def _cli(argv: list, expect: int) -> dict:
        proc = subprocess.run([sys.executable, str(Path(__file__).resolve())] + argv,
                              capture_output=True, text=True)
        assert proc.returncode == expect, f"{argv} -> {proc.returncode} (want {expect})\n{proc.stdout}\n{proc.stderr}"
        assert "Traceback" not in proc.stderr, f"{argv} raised:\n{proc.stderr}"
        return json.loads(proc.stdout)

    with tempfile.TemporaryDirectory() as td:
        fresh_p = Path(td) / "fresh.yaml"
        fresh_p.write_text('profiles_source_version: "9.9.9"\n' + asset_text + setup_text, encoding="utf-8")
        drift_p = Path(td) / "drift.yaml"
        drift_p.write_text(stale_cfg, encoding="utf-8")
        bad_p = Path(td) / "bad.yaml"
        bad_p.write_bytes(b'profiles_source_version: "9.9.9"\n\xff\xfe not utf-8\n')

        # usage error: no mode flag at all.
        assert _cli([], 2)["status"] == "error", "bare invocation must be a usage error"
        assert _cli(["--check"], 2)["status"] == "error", "--check without --config must be a usage error"
        # --check: fresh => 0, drift => 1.
        out_fresh = _cli(["--check", "--config", str(fresh_p), "--module-version", "9.9.9"], 0)
        assert out_fresh["status"] == "fresh", out_fresh
        out_drift = _cli(["--check", "--config", str(drift_p), "--module-version", "9.9.9"], 1)
        assert out_drift["status"] == "drift", out_drift
        # --reset with an unknown scope => 2 (plan error, nothing written).
        out_scope = _cli(["--reset", "ab-nope", "--config", str(fresh_p), "--module-version", "9.9.9"], 2)
        assert out_scope["status"] == "error" and out_scope["valid_scopes"], out_scope
        # An unreadable / non-UTF-8 config => error JSON + 2 on every mode, never a traceback.
        for mode in (["--check"], ["--apply"], ["--reset"]):
            out_bad = _cli(mode + ["--config", str(bad_p), "--module-version", "9.9.9"], 2)
            assert out_bad["status"] == "error" and "cannot read" in out_bad["message"], (mode, out_bad)
        assert bad_p.read_bytes().endswith(b"not utf-8\n"), "an unreadable config must never be rewritten"

    print("SELF-TEST PASSED (all assertions)")
    return 0


def check_file(config_path: Path, asset_path: Path, module_version: str | None,
               setup_path: Path | None = None) -> dict:
    config_text = _read_text(config_path)
    asset_text = _read_text(asset_path)
    setup_text = _read_setup_text(setup_path)
    config_version = _read_version(config_text, "profiles_source_version")
    info = _public(analyze(config_text, asset_text, config_version, module_version, setup_text))
    non_fresh = (info["needs_reseed"] or info["version"]["drift"]
                 or bool(info["manual_review"]) or bool(info["missing_setup"]))
    info["status"] = "drift" if non_fresh else "fresh"
    info["config_path"] = str(config_path)
    info["asset_path"] = str(asset_path)
    return info


def apply_to_file(config_path: Path, asset_path: Path, module_version: str | None,
                  setup_path: Path | None = None) -> dict:
    config_text = _read_text(config_path)
    asset_text = _read_text(asset_path)
    setup_text = _read_setup_text(setup_path)
    config_version = _read_version(config_text, "profiles_source_version")
    res = apply(config_text, asset_text, config_version, module_version, setup_text)
    changed = bool(res["reseeded_phase_profiles"] or res["reseeded_profiles"]
                   or res["reseeded_setup"] or res["version_restamped"])
    if changed:
        _write_text(config_path, res["new_text"])
    return {
        "status": "applied" if changed else "noop",
        "reseeded_phase_profiles": res["reseeded_phase_profiles"],
        "reseeded_profiles": res["reseeded_profiles"],
        "reseeded_setup": res["reseeded_setup"],
        "added_setup": res["added_setup"],
        "kept_setup": res["kept_setup"],
        "version_restamped": res["version_restamped"],
        "manual_review": res["manual_review"],
        "config_path": str(config_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect/heal auto-bmad runtime config drift vs the shipped asset.")
    parser.add_argument("--self-test", action="store_true", help="Run internal tests and exit.")
    parser.add_argument("--check", action="store_true", help="Report drift (read-only). Exit 1 if drift.")
    parser.add_argument("--apply", action="store_true", help="Additively heal the config in place.")
    parser.add_argument(
        "--reset", nargs="?", const="both", metavar="SCOPE",
        help="Restore asset defaults for SCOPE: 'profiles' (all profile blocks), 'phase_profiles', "
             "a single <profile-name>, or omit SCOPE for both asset blocks. A whole-block scope "
             "('profiles'/both) also prunes profiles absent from the asset; a single <profile-name> "
             "never prunes. Read-only plan unless --write. Never touches delegation/tea/git/code_review/build.")
    parser.add_argument("--write", action="store_true", help="With --reset: write the result (backs up to <config>.bak first).")
    parser.add_argument("--config", help="Runtime config.yaml to inspect/heal.")
    parser.add_argument("--asset-profiles", help="Shipped profiles.yaml. Default: assets/profiles.yaml next to this script.")
    parser.add_argument("--asset-config-defaults", help="Shipped config-defaults.yaml (setup-block defaults). Default: assets/config-defaults.yaml next to this script; absent => setup heal skipped.")
    parser.add_argument("--module-yaml", help="module.yaml to read module_version from. Default: assets/module.yaml next to this script.")
    parser.add_argument("--module-version", help="Override the module version (else read from --module-yaml).")
    args = parser.parse_args()

    if args.self_test:
        return _run_self_test()

    if not (args.check or args.apply or args.reset is not None):
        print(json.dumps({"status": "error", "message": "one of --check / --apply / --reset / --self-test is required"}))
        return 2
    if not args.config:
        print(json.dumps({"status": "error", "message": "--config is required"}))
        return 2

    config_path = Path(args.config)
    if not config_path.is_file():
        print(json.dumps({"status": "error", "message": f"config not found: {config_path}"}))
        return 2
    asset_path = Path(args.asset_profiles) if args.asset_profiles else _default_asset_profiles()
    if not asset_path.is_file():
        print(json.dumps({"status": "error", "message": f"asset profiles not found: {asset_path}"}))
        return 2

    setup_path = Path(args.asset_config_defaults) if args.asset_config_defaults else None

    # Every file touch below can fail on an unreadable / non-UTF-8 / unwritable file. Report it as
    # the documented error JSON + exit 2 (never a traceback) — the orchestrator parses stdout.
    try:
        module_version = args.module_version
        if not module_version:
            myaml = Path(args.module_yaml) if args.module_yaml else _default_module_yaml()
            if myaml.is_file():
                module_version = _read_version(_read_text(myaml), "module_version")

        if args.reset is not None:
            result = reset_to_file(config_path, asset_path, module_version, scope=args.reset, write=args.write)
            print(json.dumps(result, indent=2))
            return 2 if result["status"] == "error" else 0

        if args.apply:
            result = apply_to_file(config_path, asset_path, module_version, setup_path)
            print(json.dumps(result, indent=2))
            return 0

        result = check_file(config_path, asset_path, module_version, setup_path)
        print(json.dumps(result, indent=2))
        return 1 if result["status"] == "drift" else 0
    except ConfigIOError as exc:
        print(json.dumps({"status": "error", "message": str(exc), "config_path": str(config_path)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
