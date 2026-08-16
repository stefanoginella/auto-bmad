#!/usr/bin/env python3
"""auto-bmad's single story-source adapter: sprint-status reader, BMAD-status
flip, and bmad-build-auto spec discovery/reader. Dependency-free (stdlib only);
every mode prints ONE JSON object on stdout.

The orchestrator never parses ``sprint-status.yaml``, the epics documents, a
build-auto spec, or a retrospective document itself — it reads them ONLY
through this script, so every BMAD file-format assumption lives here.

Modes (exactly one per call):

``--resolve REF --sprint-status PATH [--planning-dir DIR]``
    Resolve an explicit ``--story`` argument to ONE sprint-status story entry.
    REF forms: ``E-S``, ``E.S``, ``E-Sx``, ``E.Sx`` (``x`` = the optional split
    suffix ``[a-z]``), the full key (``2-6a-digest-delivery``), or a slug/title
    fragment (case-insensitive substring of the key's slug part). Precedence:
    exact key > numeric (epic, story, suffix — a REF without a suffix matches
    only keys with an empty suffix; when only suffixed keys exist for (E,S) the
    result is ambiguous with the candidates listed) > substring. JSON:
    ``{ref, story_key, epic_num, story_num, story_suffix, slug, current_status,
    epic_status, epic_story_count, is_first_in_epic, is_last_in_epic,
    stories_after_in_epic, retrospective_status, title, epic_title,
    candidates: [], hard_stop, hard_stop_reason, error}``. Not found or
    ambiguous ⇒ ``hard_stop`` + exit 1 (also missing/empty/unreadable sprint
    file). Status values are read unquoted (``"review"`` ⇒ ``review``) and
    legacy aliases normalized (``STATUS_ALIASES``).

``--epic N --sprint-status PATH [--planning-dir DIR]``
    Enumerate epic N (``N`` or ``epic-N``): ``{epic_num, epic_status,
    epic_title, epic_story_count, epic_stories: [{key, story_num, story_suffix,
    slug, status, title, is_first_in_epic, is_last_in_epic,
    stories_after_in_epic}], retrospective_status, hard_stop, hard_stop_reason,
    error}`` sorted by (story_num, suffix). ``hard_stop`` when the arg is
    unparseable, the file is missing/empty, the epic has no stories, or the
    epic is already ``done`` (its stories are still listed). Never writes;
    exit 0 (the verdict is in the JSON) — EXCEPT an unreadable / non-UTF-8
    sprint file, which is an I/O failure, not a verdict: ``error`` +
    ``hard_stop`` + exit 1, like every other mode.

``--planning-dir DIR`` (optional on both readers)
    ``title`` / ``epic_title`` are read from the epics documents — every file
    under DIR (``os.walk``, sorted) whose basename matches ``epics*.md`` or
    ``epic-{e}*.md`` — with upstream ``sprint_plan.py``'s heading grammar
    mirrored exactly (``EPICS_DOC_EPIC_RE`` = ``^#{1,3}\\s*Epic\\s+(\\d+)\\s*:?\\s*
    (.*?)\\s*#*\\s*$``, ``EPICS_DOC_STORY_RE`` = ``^#{2,4}\\s*Story\\s+(\\d+)\\.
    (\\d+[a-z]?)\\s*:?\\s*(.*?)\\s*#*\\s*$``, both IGNORECASE; lines inside
    triple-backtick / ``~~~`` fences ignored). A story matches on (epic, story number
    incl. suffix); first match wins; not found / no ``--planning-dir`` ⇒
    ``null`` (the orchestrator falls back to the slug). Never a hard-stop.

``--mark-status KEY --to STATUS --sprint-status PATH [--allow-regress]``
    Script a BMAD-status flip (Phase 3 → ``ready-for-dev``, Phase 5 →
    ``in-progress`` then ``review``, Phase 8/9 → ``done``). STATUS ∈
    ``backlog|ready-for-dev|in-progress|review|done``. The value token of KEY's
    ``development_status`` line is replaced byte-preservingly (indent, key,
    inline ``# comment`` and every other line untouched; a ``"quoted"`` token
    is read unquoted and stays quoted), PLUS:
    (a) regress guard — ``STATUS_RANK[target] < STATUS_RANK[current]`` is
    refused (exit 1 ``refusing to regress KEY from X to Y (pass
    --allow-regress)``) unless ``--allow-regress``;
    (b) on every real write the top-level ``last_updated:`` scalar is rewritten
    to ``datetime.now().strftime("%m-%d-%Y %H:%M")`` (indent/comment/quoting
    style preserved — quoted iff it was quoted; an EMPTY value —
    ``last_updated:`` or ``last_updated:   # note`` — is rewritten like the
    absent case, ``last_updated: "<stamp>"``, keeping the comment); if absent
    it is inserted as ``last_updated: "<stamp>"`` on the line before
    ``development_status:``;
    (c) epic lift — ``--to in-progress`` lifts a ``backlog`` ``epic-{e}`` entry
    to ``in-progress``; ``--to done`` sets ``epic-{e}`` to ``done`` when every
    story of the epic is ``done`` after this flip (and the entry exists and is
    not ``done`` yet);
    (d) all edits are staged in ONE temp file and swapped atomically
    (``os.replace``); a staging failure reports ``error`` (exit 1) with the
    file byte-identical. Idempotent: ``already_at_status`` ⇒ nothing written
    (no stamp, no lift). JSON: ``{key, target_status, previous_status,
    sprint_updated, already_at_status, last_updated: {previous, new, added},
    epic_lift: {key, previous, new}|null, error}``. Exit 0 ok/no-op; 1 lookup,
    unreadable file, regress or write failure; 2 usage.

``--find-spec --impl-dir DIR --story-key KEY [--sprint-status PATH]``
    Locate the story's bmad-build-auto spec: candidates = files in DIR whose
    basename matches ``^spec-{e}-{s}{suffix}-.+\\.md$`` (with ``--sprint-status``,
    names that also match another story's spec regex are dropped); each
    candidate's frontmatter ``status`` + mtime are read; ranking: drop ``done``
    when a non-``done`` remains → drop ``blocked`` when a non-``blocked``
    remains → exactly one ⇒ found; several with the same slug stem modulo a
    ``-N`` collision suffix (build-auto appends ``-2``, ``-3``, … when a
    non-draft spec of that slug already exists) ⇒ newest mtime wins,
    ``siblings`` listed; several with different stems ⇒ ``ambiguous: true``
    (``hard_stop`` + exit 1); none ⇒ ``found: false``. An unreadable /
    non-UTF-8 candidate is kept with ``status: null`` + a ``warnings`` entry
    (never a crash). JSON: ``{story_key, impl_dir, candidates: [{path, status,
    mtime}], spec_path, status, found, ambiguous, siblings: [], hard_stop,
    hard_stop_reason, warnings: [], error}``.

``--spec PATH``
    Dependency-free reader of a build-auto spec (or a ``bmad-build-auto-result-*``
    skeleton). Frontmatter: scalars (``'quoted'``/``"quoted"``, ``# comments``,
    plain multi-line continuation), ``[]``/``[a, b]`` flow lists, ``- item``
    block lists (incl. a bare ``-`` with the item body on the next lines), and
    block lists of mappings with ``>-``/``|-`` block scalars (the ``deferred:``
    shape). JSON:
    ``{spec_path, exists, frontmatter: {title, type, created, status,
    review_loop_iteration, followup_review_recommended, baseline_revision,
    context: [], warnings: [], deferred: [{summary, evidence, location,
    severity}], deferred_count}, auto_run_result: {present, status,
    blocking_condition}, last_review_pass: {date, intent_gap, bad_spec, patch,
    defer, reject}|null, status, parse_warnings: [], error}``. ``status`` = the
    frontmatter status (AUTHORITATIVE); on a frontmatter parse failure it falls
    back to ``^status:\\s*['"]?([a-z-]+)`` and records a ``parse_warnings``
    entry. ``auto_run_result`` is optional corroboration: ``present`` = the
    ``## Auto Run Result`` heading exists; ``status`` / ``blocking_condition``
    = the ``Status:`` / ``Blocking condition:`` lines under it when present
    (else null). Upstream guarantees those two lines only in the HALT
    skeletons — and the no-spec one (``bmad-build-auto-result-*.md``,
    workflow.md HALT step 2) has NO H2, just ``# BMad Build Auto Result``
    followed by the two lines — so when the body has no H2 at all and the
    frontmatter is the skeleton signature (``status`` only), the two lines are
    read from the body directly (``present`` stays false). A ``status`` that
    disagrees with the frontmatter adds a ``parse_warnings`` entry, never
    overrides. ``last_review_pass`` = the LAST ``### … — Review pass`` block
    under ``## Review Triage Log``; each count is the leading integer of
    ``- <cat>: N…``; unparseable ⇒ null. Everything else under ``## Auto Run
    Result`` is advisory and NOT emitted. Missing file ⇒ ``exists: false`` +
    ``error`` + exit 1; unreadable / non-UTF-8 ⇒ ``exists: true`` + ``error``
    + exit 1.

``--retro-verdict --impl-dir DIR --epic N``
    Newest ``<impl>/epic-{N}-retro-*.md`` by mtime (searched recursively) ⇒
    ``{epic, doc, verdict, date, headless, found, warnings, error}``
    (frontmatter regex reads; ``verdict`` must be one of
    ``accepted|accepted-with-open-items|rejected`` else ``verdict: null`` +
    warning). Not found ⇒ ``found: false``, exit 0; unreadable / non-UTF-8
    doc ⇒ ``error`` + exit 1.

``--self-test``
    Runs the built-in fixtures (temp dirs) and exits 0/1.

Public helpers other scripts import (``deferred_ledger.py harvest`` via
``importlib``): ``read_spec(path)`` (the ``--spec`` JSON dict),
``parse_frontmatter(text)`` (→ ``(mapping, warnings)``).

Usage:
    story_plan.py --resolve REF --sprint-status PATH [--planning-dir DIR]
    story_plan.py --epic N --sprint-status PATH [--planning-dir DIR]
    story_plan.py --mark-status KEY --to STATUS --sprint-status PATH [--allow-regress]
    story_plan.py --find-spec --impl-dir DIR --story-key KEY [--sprint-status PATH]
    story_plan.py --spec PATH
    story_plan.py --retro-verdict --impl-dir DIR --epic N
    story_plan.py --self-test
"""
from __future__ import annotations

import argparse
import datetime as _dt
import fnmatch
import json
import os
import re
import sys
import tempfile

# --------------------------------------------------------------------------- #
# Grammar (mirrors upstream bmad-sprint-planning/scripts/sprint_plan.py)
# --------------------------------------------------------------------------- #
EPIC_RE = re.compile(r"^epic-(\d+)$")
RETRO_RE = re.compile(r"^epic-(\d+)-retrospective$")
# Story keys carry an optional split suffix: 2-6a-digest-delivery.
STORY_RE = re.compile(r"^(\d+)-(\d+)([a-z]?)-(.+)$")

# Legacy status aliases BMAD still honours (upstream LEGACY_STATUS).
STATUS_ALIASES = {"drafted": "ready-for-dev", "contexted": "in-progress"}

# The story status vocabulary the orchestrator may script, in lifecycle order.
STORY_STATUSES = ("backlog", "ready-for-dev", "in-progress", "review", "done")
STATUS_RANK = {status: rank for rank, status in enumerate(STORY_STATUSES)}

# Epics-document heading grammar (upstream EPIC_RE / STORY_RE / FENCE_RE).
EPICS_DOC_EPIC_RE = re.compile(r"^#{1,3}\s*Epic\s+(\d+)\s*:?\s*(.*?)\s*#*\s*$", re.IGNORECASE)
EPICS_DOC_STORY_RE = re.compile(r"^#{2,4}\s*Story\s+(\d+)\.(\d+[a-z]?)\s*:?\s*(.*?)\s*#*\s*$", re.IGNORECASE)
FENCE_RE = re.compile(r"^\s{0,3}(?:```|~~~)")

# last_updated stamp format (upstream DATE_FORMAT).
DATE_FORMAT = "%m-%d-%Y %H:%M"

# Retro-document verdict vocabulary (upstream retro-document.md frontmatter).
RETRO_VERDICTS = ("accepted", "accepted-with-open-items", "rejected")

# The one `--epic` hard stop that is an I/O failure rather than a verdict: the
# sprint file exists but cannot be read (permissions / non-UTF-8). `--epic`
# exits 0 on every verdict, but this one exits 1 like every other mode.
UNREADABLE_SPRINT_REASON = (
    "unreadable sprint-status.yaml; fix the file (UTF-8, readable) or re-run /bmad-sprint-planning"
)


# --------------------------------------------------------------------------- #
# sprint-status.yaml parsing
# --------------------------------------------------------------------------- #
def parse_development_status(text: str):
    """Return an ordered list of (key, status) from the development_status block."""
    entries = []
    in_block = False
    block_indent = None
    for raw in text.splitlines():
        stripped = raw.strip()
        if not in_block:
            if stripped == "development_status:" or re.match(r"^development_status:\s*$", raw):
                in_block = True
            continue
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if block_indent is None:
            block_indent = indent
        # A line dedented back to column 0 (or below block indent) ends the block.
        if indent < block_indent or indent == 0:
            break
        m = re.match(r"^\s*([^:#]+?):\s*([^#]*?)\s*(?:#.*)?$", raw)
        if not m:
            continue
        key, value = m.group(1).strip(), _unquote(m.group(2).strip())
        if not value:
            continue
        entries.append((key, STATUS_ALIASES.get(value, value)))
    return entries


def _unquote(token):
    """Strip ONE matching pair of surrounding quotes from a scalar token
    (``"review"`` / ``'review'`` ⇒ ``review``); anything else is returned as is."""
    t = token.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in ("'", '"'):
        return t[1:-1]
    return t


def _quote_like(token, new_value):
    """Wrap ``new_value`` in the same quote pair ``token`` used (if any)."""
    t = token.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in ("'", '"'):
        return t[0] + new_value + t[0]
    return new_value


def _read_text(path, newline=None):
    """Read a UTF-8 text file. Returns (text, None) or (None, error_message)
    — never raises on a missing/unreadable/non-UTF-8 file."""
    try:
        with open(path, "r", encoding="utf-8", newline=newline) as fh:
            return fh.read(), None
    except UnicodeDecodeError as exc:
        return None, f"{path} is not valid UTF-8 ({exc.reason} at byte {exc.start})"
    except OSError as exc:
        return None, f"cannot read {path}: {exc.strerror or exc}"


def classify(entries):
    """Split entries into epics {n: status}, stories [dict], retros {n: status}."""
    epics, stories, retros = {}, [], {}
    for key, status in entries:
        rm = RETRO_RE.match(key)
        em = EPIC_RE.match(key)
        sm = STORY_RE.match(key)
        if rm:
            retros[int(rm.group(1))] = status
        elif em:
            epics[int(em.group(1))] = status
        elif sm:
            stories.append(
                {
                    "key": key,
                    "epic_num": int(sm.group(1)),
                    "story_num": int(sm.group(2)),
                    "story_suffix": sm.group(3),
                    "slug": sm.group(4),
                    "status": status,
                }
            )
    return epics, stories, retros


def _story_sort_key(s):
    return (s["story_num"], s["story_suffix"])


def _load_sprint(sprint_status_path):
    """Read + parse a sprint file. Returns (text, epics, stories, retros,
    hard_stop_reason|None, error|None)."""
    if not sprint_status_path or not os.path.isfile(sprint_status_path):
        return None, {}, [], {}, "no sprint-status.yaml; run /bmad-sprint-planning first", (
            f"sprint-status file not found: {sprint_status_path}"
        )
    text, read_error = _read_text(sprint_status_path)
    if read_error:
        return None, {}, [], {}, UNREADABLE_SPRINT_REASON, read_error
    entries = parse_development_status(text)
    if not entries:
        return text, {}, [], {}, "empty/invalid sprint-status; run /bmad-sprint-planning", (
            "no development_status entries found"
        )
    epics, stories, retros = classify(entries)
    return text, epics, stories, retros, None, None


def _epic_facts(story, stories):
    """Positional facts of ``story`` inside its epic (sorted by story_num, suffix)."""
    same = sorted((s for s in stories if s["epic_num"] == story["epic_num"]), key=_story_sort_key)
    me = _story_sort_key(story)
    return {
        "epic_story_count": len(same),
        "is_first_in_epic": _story_sort_key(same[0]) == me,
        "is_last_in_epic": _story_sort_key(same[-1]) == me,
        "stories_after_in_epic": sum(1 for s in same if _story_sort_key(s) > me),
    }


# --------------------------------------------------------------------------- #
# Epics documents: story / epic titles (--planning-dir)
# --------------------------------------------------------------------------- #
def _epics_doc_files(planning_dir, epic_num):
    """Every file under planning_dir (os.walk, sorted) whose basename matches
    ``epics*.md`` or ``epic-{e}*.md``."""
    if not planning_dir or not os.path.isdir(planning_dir):
        return []
    patterns = ("epics*.md", f"epic-{epic_num}*.md")
    found = []
    for root, dirs, files in os.walk(planning_dir):
        dirs.sort()
        for name in sorted(files):
            if any(fnmatch.fnmatchcase(name, pat) for pat in patterns):
                found.append(os.path.join(root, name))
    return found


def read_epic_titles(planning_dir, epic_num):
    """Return (epic_title|None, {(story_num:int, suffix:str): title}) for epic
    ``epic_num`` from the epics documents. First match wins; empty ⇒ null."""
    epic_title = None
    stories = {}
    for path in _epics_doc_files(planning_dir, epic_num):
        text, read_error = _read_text(path)
        if read_error:
            continue  # unreadable / non-UTF-8 epics doc ⇒ skipped (titles fall back to null)
        lines = text.splitlines()
        in_fence = False
        for line in lines:
            if FENCE_RE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            em = EPICS_DOC_EPIC_RE.match(line)
            if em:
                if int(em.group(1)) == epic_num and epic_title is None and em.group(2).strip():
                    epic_title = em.group(2).strip()
                continue
            sm = EPICS_DOC_STORY_RE.match(line)
            if sm and int(sm.group(1)) == epic_num:
                num_m = re.match(r"^(\d+)([a-z]?)$", sm.group(2))
                if not num_m:
                    continue
                skey = (int(num_m.group(1)), num_m.group(2))
                title = sm.group(3).strip()
                if skey not in stories and title:
                    stories[skey] = title
    return epic_title, stories


# --------------------------------------------------------------------------- #
# --resolve
# --------------------------------------------------------------------------- #
_NUMERIC_REF_RE = re.compile(r"^(\d+)[-.](\d+)([a-z]?)$")


def build_resolve_result(sprint_status_path, ref, planning_dir=None):
    """Resolve REF to exactly one story entry. Returns (result, exit_code)."""
    result = {
        "ref": ref,
        "story_key": None,
        "epic_num": None,
        "story_num": None,
        "story_suffix": None,
        "slug": None,
        "current_status": None,
        "epic_status": None,
        "epic_story_count": None,
        "is_first_in_epic": None,
        "is_last_in_epic": None,
        "stories_after_in_epic": None,
        "retrospective_status": None,
        "title": None,
        "epic_title": None,
        "candidates": [],
        "hard_stop": False,
        "hard_stop_reason": None,
        "error": None,
    }

    def stop(reason, error=None):
        result["hard_stop"] = True
        result["hard_stop_reason"] = reason
        result["error"] = error or reason
        return result, 1

    _text, epics, stories, retros, hs_reason, error = _load_sprint(sprint_status_path)
    if hs_reason:
        return stop(hs_reason, error)

    ref_s = (ref or "").strip()
    if not ref_s:
        return stop("empty story reference")

    # 1. exact key
    matches = [s for s in stories if s["key"] == ref_s]
    # 2. numeric E-S / E.S / E-Sx / E.Sx
    if not matches:
        nm = _NUMERIC_REF_RE.match(ref_s)
        if nm:
            e, n, suf = int(nm.group(1)), int(nm.group(2)), nm.group(3)
            same_num = [s for s in stories if s["epic_num"] == e and s["story_num"] == n]
            matches = [s for s in same_num if s["story_suffix"] == suf]
            if not matches and same_num:
                # Only suffixed keys exist for (E,S): ambiguous, list them.
                result["candidates"] = [s["key"] for s in sorted(same_num, key=_story_sort_key)]
                return stop(
                    f"story reference '{ref_s}' is ambiguous — candidates: "
                    + ", ".join(result["candidates"])
                )
    # 3. slug substring (case-insensitive)
    if not matches:
        low = ref_s.lower()
        matches = [s for s in stories if low in s["slug"].lower()]

    if not matches:
        return stop(f"story '{ref_s}' not found in sprint-status")
    if len(matches) > 1:
        result["candidates"] = [s["key"] for s in matches]
        return stop(
            f"story reference '{ref_s}' is ambiguous — candidates: " + ", ".join(result["candidates"])
        )

    story = matches[0]
    result.update(
        {
            "story_key": story["key"],
            "epic_num": story["epic_num"],
            "story_num": story["story_num"],
            "story_suffix": story["story_suffix"],
            "slug": story["slug"],
            "current_status": story["status"],
            "epic_status": epics.get(story["epic_num"]),
            "retrospective_status": retros.get(story["epic_num"]),
        }
    )
    result.update(_epic_facts(story, stories))
    if planning_dir:
        epic_title, titles = read_epic_titles(planning_dir, story["epic_num"])
        result["epic_title"] = epic_title
        result["title"] = titles.get((story["story_num"], story["story_suffix"]))
    return result, 0


# --------------------------------------------------------------------------- #
# --epic
# --------------------------------------------------------------------------- #
def parse_epic_arg(epic_arg):
    m = re.match(r"^(?:epic-)?(\d+)$", str(epic_arg).strip())
    return int(m.group(1)) if m else None


def build_epic_result(sprint_status_path, epic_arg, planning_dir=None):
    """Enumerate every story in epic N ordered by (story_num, suffix). Never
    writes; the verdict (``hard_stop``) is in the JSON (exit 0)."""
    result = {
        "epic_num": None,
        "epic_status": None,
        "epic_title": None,
        "epic_story_count": None,
        "epic_stories": [],
        "retrospective_status": None,
        "hard_stop": False,
        "hard_stop_reason": None,
        "error": None,
    }

    epic_num = parse_epic_arg(epic_arg)
    if epic_num is None:
        result["error"] = f"could not parse --epic '{epic_arg}' (expected N or epic-N)"
        result["hard_stop"] = True
        result["hard_stop_reason"] = result["error"]
        return result
    result["epic_num"] = epic_num

    _text, epics, stories, retros, hs_reason, error = _load_sprint(sprint_status_path)
    if hs_reason:
        result["error"] = error
        result["hard_stop"] = True
        result["hard_stop_reason"] = hs_reason
        return result

    same_epic = sorted((s for s in stories if s["epic_num"] == epic_num), key=_story_sort_key)
    result["epic_status"] = epics.get(epic_num)
    result["retrospective_status"] = retros.get(epic_num)

    if not same_epic:
        result["hard_stop"] = True
        result["hard_stop_reason"] = f"epic {epic_num} has no stories in sprint-status"
        result["error"] = result["hard_stop_reason"]
        return result

    epic_title, titles = (None, {})
    if planning_dir:
        epic_title, titles = read_epic_titles(planning_dir, epic_num)
    result["epic_title"] = epic_title
    result["epic_story_count"] = len(same_epic)
    for s in same_epic:
        item = {
            "key": s["key"],
            "story_num": s["story_num"],
            "story_suffix": s["story_suffix"],
            "slug": s["slug"],
            "status": s["status"],
            "title": titles.get((s["story_num"], s["story_suffix"])),
        }
        item.update(_epic_facts(s, stories))
        item.pop("epic_story_count")
        result["epic_stories"].append(item)

    if result["epic_status"] == "done":
        result["hard_stop"] = True
        result["hard_stop_reason"] = f"epic {epic_num} is marked done"

    return result


# --------------------------------------------------------------------------- #
# --mark-status: byte-preserving sprint-status flip
# --------------------------------------------------------------------------- #
def _find_sprint_status_line(lines, key):
    """Locate KEY's line inside the development_status block, using the same
    block-boundary rules as parse_development_status. ``lines`` keep their
    line endings. Returns (index, match) or (None, None); the match groups are
    (prefix-through-colon+spacing, value, inline-comment-or-None)."""
    line_re = re.compile(r"^(\s*" + re.escape(key) + r":\s*)(.*?)(\s*#.*)?$")
    in_block = False
    block_indent = None
    for i, raw in enumerate(lines):
        body = raw.rstrip("\r\n")
        stripped = body.strip()
        if not in_block:
            if stripped == "development_status:" or re.match(r"^development_status:\s*$", body):
                in_block = True
            continue
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(body) - len(body.lstrip())
        if block_indent is None:
            block_indent = indent
        if indent < block_indent or indent == 0:
            break
        m = line_re.match(body)
        if m:
            return i, m
    return None, None


def _rewrite_line(lines, index, new_body):
    """Replace line ``index``'s body, preserving its original line ending."""
    old = lines[index]
    body = old.rstrip("\r\n")
    lines[index] = new_body + old[len(body):]


def _stage_write(path, content):
    """Write ``content`` to a temp file in ``path``'s directory and return the
    temp path. The caller commits with ``os.replace`` (atomic: same filesystem,
    never a truncate-then-write) or unlinks the temp on abort."""
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=directory, prefix="." + os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(content)
        # mkstemp creates 0600; carry the target's own mode so the replace
        # doesn't silently drop group/other bits from a user file.
        os.chmod(tmp, os.stat(path).st_mode & 0o7777)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return tmp


_LAST_UPDATED_RE = re.compile(r"^(last_updated:)(\s*)(.*)$")
_DEV_STATUS_LINE_RE = re.compile(r"^development_status:\s*(#.*)?$")


def _split_scalar_comment(value):
    """Split a raw scalar token into (quote_char|'' , inner_value, trailing) where
    ``trailing`` is any inline comment (with its leading whitespace)."""
    if value.startswith(("'", '"')):
        q = value[0]
        end = value.find(q, 1)
        if end != -1:
            return q, value[1:end], value[end + 1:]
        return "", value, ""
    if value.startswith("#"):
        # Comment only (the value is empty): keep it as trailing text.
        return "", "", value
    m = re.match(r"^(.*?)(\s+#.*)?$", value)
    return "", m.group(1).rstrip(), (m.group(2) or "")


def _find_top_level_line(lines, regex, first_dev_status_only=False):
    """Index + match of the first indent-0 line matching ``regex`` OUTSIDE the
    development_status block (top-level scalars only)."""
    in_block = False
    for i, raw in enumerate(lines):
        body = raw.rstrip("\r\n")
        if in_block:
            if body.strip() and (len(body) - len(body.lstrip())) == 0:
                in_block = False
            else:
                continue
        if _DEV_STATUS_LINE_RE.match(body):
            in_block = True
            if first_dev_status_only:
                return i, None
            continue
        m = regex.match(body)
        if m:
            return i, m
    return None, None


def mark_status(sprint_status_path, key, status, allow_regress=False, now=None):
    """Flip KEY's sprint-status entry to ``status``. Returns (result, exit_code).

    Lookup/guard failures (exit 1) happen before any write; the write stages
    the whole new file as one temp file and commits with a single atomic
    ``os.replace``, so a failure leaves the target byte-identical.
    """
    target = (status or "").strip().lower()
    result = {
        "key": key,
        "target_status": target,
        "previous_status": None,
        "sprint_updated": False,
        "already_at_status": False,
        "last_updated": {"previous": None, "new": None, "added": False},
        "epic_lift": None,
        "error": None,
    }

    if target not in STATUS_RANK:
        result["error"] = f"invalid status '{status}' — allowed: {list(STORY_STATUSES)}"
        return result, 1

    if not os.path.isfile(sprint_status_path):
        result["error"] = f"sprint-status file not found: {sprint_status_path}"
        return result, 1

    text, read_error = _read_text(sprint_status_path, newline="")
    if read_error:
        result["error"] = read_error
        return result, 1
    lines = text.splitlines(keepends=True)

    idx, m = _find_sprint_status_line(lines, key)
    if idx is None:
        result["error"] = f"key '{key}' not found in development_status of {sprint_status_path}"
        return result, 1
    previous_raw = _unquote(m.group(2))
    result["previous_status"] = previous_raw
    current = STATUS_ALIASES.get(previous_raw.lower(), previous_raw.lower())

    lu_idx, lu_m = _find_top_level_line(lines, _LAST_UPDATED_RE)
    if lu_m is not None:
        _q, prev_stamp, _trail = _split_scalar_comment(lu_m.group(3))
        result["last_updated"]["previous"] = prev_stamp or None

    if current == target:
        result["already_at_status"] = True
        return result, 0

    if current in STATUS_RANK and STATUS_RANK[target] < STATUS_RANK[current] and not allow_regress:
        result["error"] = f"refusing to regress {key} from {current} to {target} (pass --allow-regress)"
        return result, 1

    # --- stage every edit in memory ------------------------------------- #
    # The value token is replaced in place (a quoted token stays quoted).
    _rewrite_line(lines, idx, m.group(1) + _quote_like(m.group(2), target) + (m.group(3) or ""))

    # Epic lift (needs the parsed view of the whole block, with this flip applied).
    sm = STORY_RE.match(key)
    if sm:
        epic_num = int(sm.group(1))
        epic_key = f"epic-{epic_num}"
        e_idx, e_m = _find_sprint_status_line(lines, epic_key)
        if e_idx is not None:
            e_raw = _unquote(e_m.group(2))
            e_current = STATUS_ALIASES.get(e_raw.lower(), e_raw.lower())
            lift_to = None
            if target == "in-progress" and e_current == "backlog":
                lift_to = "in-progress"
            elif target == "done" and e_current != "done":
                _epics, stories, _retros = classify(parse_development_status("".join(lines)))
                mine = [s for s in stories if s["epic_num"] == epic_num]
                if mine and all(s["status"] == "done" for s in mine):
                    lift_to = "done"
            if lift_to:
                _rewrite_line(lines, e_idx, e_m.group(1) + _quote_like(e_m.group(2), lift_to) + (e_m.group(3) or ""))
                result["epic_lift"] = {"key": epic_key, "previous": e_raw, "new": lift_to}

    # last_updated stamp (top-level scalar; rewrite in place or insert).
    stamp = (now or _dt.datetime.now()).strftime(DATE_FORMAT)
    if lu_m is not None:
        q, prev, trailing = _split_scalar_comment(lu_m.group(3))
        spacing = lu_m.group(2) or " "  # never glue the value to the colon
        if not q and not prev:
            # Empty value (bare `last_updated:` or `last_updated:   # note`):
            # emit the absent-case shape and keep the comment, spaced off.
            q = '"'
            if trailing and not trailing[:1].isspace():
                trailing = spacing + trailing
            spacing = " "
        _rewrite_line(lines, lu_idx, lu_m.group(1) + spacing + q + stamp + q + trailing)
        result["last_updated"]["new"] = stamp
    else:
        d_idx, _ = _find_top_level_line(lines, _DEV_STATUS_LINE_RE, first_dev_status_only=True)
        if d_idx is None:
            d_idx = 0
        eol = "\r\n" if lines and lines[0].endswith("\r\n") else "\n"
        lines.insert(d_idx, f'last_updated: "{stamp}"{eol}')
        result["last_updated"]["new"] = stamp
        result["last_updated"]["added"] = True

    # --- one atomic swap --------------------------------------------------- #
    tmp = None
    try:
        tmp = _stage_write(sprint_status_path, "".join(lines))
        os.replace(tmp, sprint_status_path)
    except OSError as exc:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)
        result["error"] = f"write failed: {exc} (sprint-status left unchanged)"
        result["last_updated"] = {"previous": result["last_updated"]["previous"], "new": None, "added": False}
        result["epic_lift"] = None
        return result, 1
    result["sprint_updated"] = True
    return result, 0


# --------------------------------------------------------------------------- #
# Frontmatter parser (build-auto spec / retro doc)
# --------------------------------------------------------------------------- #
def _frontmatter_block(text):
    """Return (frontmatter_lines, body_text) or (None, text) when there is no
    closed ``---`` frontmatter at the top of the file."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i], "\n".join(lines[i + 1:])
    return None, text


def _typed(value):
    """Bare-scalar typing: null/bool/int, else the string itself."""
    low = value.lower()
    if low in ("null", "~", ""):
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    if re.match(r"^-?\d+$", value):
        return int(value)
    return value


def _parse_scalar(raw):
    """Parse an inline scalar: quoted ('' / \"\"), or bare with a trailing
    ``# comment`` stripped, then typed."""
    s = raw.strip()
    if s.startswith("'"):
        end = -1
        i = 1
        while i < len(s):
            if s[i] == "'":
                if i + 1 < len(s) and s[i + 1] == "'":
                    i += 2
                    continue
                end = i
                break
            i += 1
        if end != -1:
            return s[1:end].replace("''", "'")
        return s[1:]
    if s.startswith('"'):
        end = s.find('"', 1)
        while end != -1 and s[end - 1] == "\\":
            end = s.find('"', end + 1)
        inner = s[1:end] if end != -1 else s[1:]
        try:
            return json.loads('"' + inner + '"')
        except ValueError:
            return inner
    q, inner, _trail = _split_scalar_comment(s)
    return _typed(inner.strip())


def _parse_flow_list(raw):
    """``[]`` / ``[a, 'b c', "d"]`` → list of parsed scalars."""
    inner = raw.strip()[1:-1].strip()
    if not inner:
        return []
    items, buf, quote = [], "", None
    for ch in inner:
        if quote:
            buf += ch
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            buf += ch
        elif ch == ",":
            items.append(buf)
            buf = ""
        else:
            buf += ch
    items.append(buf)
    return [_parse_scalar(x) for x in items if x.strip()]


def _flow_list_prefix(raw):
    """Return the ``[...]`` flow-list token at the start of ``raw`` (quote-aware),
    tolerating a trailing ``# comment``; None when the bracket never closes."""
    quote = None
    for i, ch in enumerate(raw):
        if quote:
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "]":
            rest = raw[i + 1:].strip()
            if rest == "" or rest.startswith("#"):
                return raw[: i + 1]
            return None
    return None


_BLOCK_SCALAR_RE = re.compile(r"^([>|])([+-]?)(\d*)([+-]?)\s*(#.*)?$")


def _read_block_scalar(lines, i, parent_indent, indicator):
    """Collect the block-scalar body starting at line ``i`` (lines more
    indented than ``parent_indent``). Returns (value, next_index)."""
    style, chomp = indicator.group(1), indicator.group(2) or indicator.group(4)
    body = []
    j = i
    while j < len(lines):
        line = lines[j]
        if line.strip() == "":
            body.append("")
            j += 1
            continue
        ind = len(line) - len(line.lstrip())
        if ind <= parent_indent:
            break
        body.append(line)
        j += 1
    # Trailing blank lines are chomped unless keep (+).
    while body and body[-1] == "" and chomp != "+":
        body.pop()
    if not body:
        return "", j
    base = min(len(l) - len(l.lstrip()) for l in body if l.strip())
    stripped = [l[base:] if l.strip() else "" for l in body]
    if style == "|":
        value = "\n".join(stripped)
    else:  # folded: join non-blank lines with a space, blank line ⇒ newline
        out, para = [], []
        for l in stripped:
            if l == "":
                out.append(" ".join(para))
                para = []
            else:
                para.append(l.strip())
        out.append(" ".join(para))
        value = "\n".join(out)
    if chomp != "-":
        value += "\n"
    return value, j


_KV_RE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_-]*):(?:\s+(.*)|\s*)$")


def _is_list_item(line):
    """``- item`` or a bare ``-`` (the item body on the following lines)."""
    s = line.lstrip()
    return s.startswith("- ") or s.rstrip() == "-"


def _plain_scalar_with_continuation(lines, i, indent, raw):
    """A plain (unquoted, non-flow) scalar may continue on following lines
    that are indented deeper than ``indent``; fold them YAML-style (a blank
    line ⇒ newline, otherwise a single space). Returns (value, next_index)."""
    rv = raw.strip()
    if rv.startswith(("'", '"', "[")):
        return _parse_scalar(rv), i + 1
    q, head, _trail = _split_scalar_comment(rv)
    parts, para = [], [head.strip()] if head.strip() else []
    j = i + 1
    k = j
    while k < len(lines):
        line = lines[k]
        if line.strip() == "":
            k += 1
            continue
        ind = len(line) - len(line.lstrip())
        if ind <= indent or line.lstrip().startswith("#"):
            break
        # A blank line between continuation lines folds to a newline.
        if k > j and any(lines[x].strip() == "" for x in range(j, k)):
            parts.append(" ".join(para))
            para = []
        _q, seg, _t = _split_scalar_comment(line.strip())
        para.append(seg.strip())
        j = k + 1
        k += 1
    if j == i + 1:
        return _typed(head.strip()), i + 1
    parts.append(" ".join(para))
    return "\n".join(parts), j


def _parse_value_at(lines, i, indent, raw_value, warnings):
    """Parse the value of a ``key:`` at line ``i`` (key indent ``indent``,
    inline part ``raw_value``). Returns (value, next_index)."""
    rv = (raw_value or "").strip()
    if rv:
        bs = _BLOCK_SCALAR_RE.match(rv)
        if bs:
            return _read_block_scalar(lines, i + 1, indent, bs)
        if rv.startswith("["):
            fl = _flow_list_prefix(rv)
            if fl is not None:
                return _parse_flow_list(fl), i + 1
        if rv.startswith("#"):
            rv = ""
        else:
            return _plain_scalar_with_continuation(lines, i, indent, rv)
    # Empty inline value: a nested block follows (list / mapping) or null.
    j = i + 1
    while j < len(lines) and lines[j].strip() == "":
        j += 1
    if j >= len(lines):
        return None, j
    nxt = lines[j]
    n_ind = len(nxt) - len(nxt.lstrip())
    if n_ind == indent and _is_list_item(nxt):
        # YAML allows a block list at the parent key's own indent.
        return _parse_block_list(lines, j, n_ind, warnings)
    if n_ind <= indent:
        return None, i + 1
    if _is_list_item(nxt):
        return _parse_block_list(lines, j, n_ind, warnings)
    if _KV_RE.match(nxt):
        return _parse_mapping(lines, j, n_ind, warnings)
    warnings.append(f"unparseable block at frontmatter line {j + 1}: {nxt.strip()!r}")
    return None, j


def _parse_mapping(lines, i, indent, warnings):
    """Parse ``key: value`` lines at exactly ``indent`` until a dedent."""
    result = {}
    j = i
    while j < len(lines):
        line = lines[j]
        if line.strip() == "" or line.strip().startswith("#"):
            j += 1
            continue
        ind = len(line) - len(line.lstrip())
        if ind < indent:
            break
        if ind > indent:
            warnings.append(f"unexpected indent at frontmatter line {j + 1}: {line.strip()!r}")
            j += 1
            continue
        km = _KV_RE.match(line)
        if not km:
            break
        value, j = _parse_value_at(lines, j, indent, km.group(3), warnings)
        result[km.group(2)] = value
    return result, j


def _parse_block_list(lines, i, indent, warnings):
    """Parse ``- item`` lines at ``indent`` (items are scalars or mappings)."""
    items = []
    j = i
    while j < len(lines):
        line = lines[j]
        if line.strip() == "" or line.strip().startswith("#"):
            j += 1
            continue
        ind = len(line) - len(line.lstrip())
        if ind < indent or not _is_list_item(line):
            break
        if ind > indent:
            warnings.append(f"unexpected list indent at frontmatter line {j + 1}")
            j += 1
            continue
        rest = line[ind + 1:]  # after the dash
        rest_stripped = rest.lstrip()
        if rest_stripped.strip() == "":
            # Bare `-`: the item body (mapping / list / scalar) sits on the
            # following, deeper-indented lines — parse it as the "value" of a
            # zero-width key at this indent; nothing there ⇒ null item.
            value, j = _parse_value_at(lines, j, ind, "", warnings)
            items.append(value)
            continue
        item_indent = ind + 1 + (len(rest) - len(rest_stripped))
        km = _KV_RE.match(" " * item_indent + rest_stripped)
        if km:
            # A mapping item: first key on the dash line, then continuation keys
            # at item_indent. Splice the dash line into a virtual key line.
            virtual = lines[:j] + [" " * item_indent + rest_stripped] + lines[j + 1:]
            mapping, j = _parse_mapping(virtual, j, item_indent, warnings)
            items.append(mapping)
        else:
            bs = _BLOCK_SCALAR_RE.match(rest_stripped.strip())
            if bs:
                value, j = _read_block_scalar(lines, j + 1, ind, bs)
                items.append(value)
                continue
            if rest_stripped.strip().startswith("["):
                fl = _flow_list_prefix(rest_stripped.strip())
                if fl is not None:
                    items.append(_parse_flow_list(fl))
                    j += 1
                    continue
            value, j = _plain_scalar_with_continuation(lines, j, ind, rest_stripped)
            items.append(value)
    return items, j


def parse_frontmatter(text):
    """Parse a document's YAML frontmatter with the small dependency-free
    subset build-auto/retro docs use. Returns (mapping|None, warnings)."""
    warnings = []
    fm_lines, _body = _frontmatter_block(text)
    if fm_lines is None:
        return None, ["no closed --- frontmatter block"]
    try:
        mapping, _ = _parse_mapping(fm_lines, 0, 0, warnings)
    except Exception as exc:  # defensive: never crash the reader
        return None, [f"frontmatter parse error: {exc}"]
    return mapping, warnings


# --------------------------------------------------------------------------- #
# --spec
# --------------------------------------------------------------------------- #
_H2_RE = re.compile(r"^##\s+(.*?)\s*#*\s*$")
_REVIEW_PASS_RE = re.compile(r"^###\s+(.*?)\s*[—–-]+\s*Review pass\s*$", re.IGNORECASE)
_COUNT_RE = re.compile(r"^\s*[-*+]\s*\**(intent_gap|bad_spec|patch|defer|reject)\**\s*:\s*\**\s*(\d+)", re.IGNORECASE)
_RESULT_STATUS_RE = re.compile(r"^\s*(?:[-*+]\s*)?\**\s*Status\s*\**\s*:\s*\**\s*(.*?)\s*\**\s*$", re.IGNORECASE)
_RESULT_BLOCK_RE = re.compile(r"^\s*(?:[-*+]\s*)?\**\s*Blocking condition\s*\**\s*:\s*\**\s*(.*?)\s*\**\s*$", re.IGNORECASE)
_STATUS_FALLBACK_RE = re.compile(r"^status:\s*['\"]?([a-z-]+)", re.MULTILINE)
_NONE_WORDS = frozenset({"", "none", "(none)", "none.", "n/a", "-", "—", "null"})


def _sections(body_text):
    """Split the markdown body into {h2 title: [lines]} (first occurrence wins)."""
    sections = {}
    current = None
    in_fence = False
    for line in body_text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
        if not in_fence:
            hm = _H2_RE.match(line)
            if hm:
                current = hm.group(1)
                sections.setdefault(current, [])
                continue
        if current is not None:
            sections[current].append(line)
    return sections


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _normalize_deferred(items, warnings):
    out = []
    for n, item in enumerate(_as_list(items)):
        if not isinstance(item, dict):
            warnings.append(f"deferred item {n + 1} is not a mapping; kept as summary")
            out.append({"summary": None if item is None else str(item), "evidence": None, "location": None, "severity": None})
            continue
        entry = {}
        for k in ("summary", "evidence", "location", "severity"):
            v = item.get(k)
            if isinstance(v, str):
                v = v.strip()
            entry[k] = v if v not in (None, "") else None
        out.append(entry)
    return out


def read_spec(spec_path):
    """The ``--spec`` reader. Returns the JSON dict (see module docstring)."""
    result = {
        "spec_path": spec_path,
        "exists": False,
        "frontmatter": {
            "title": None,
            "type": None,
            "created": None,
            "status": None,
            "review_loop_iteration": None,
            "followup_review_recommended": None,
            "baseline_revision": None,
            "context": [],
            "warnings": [],
            "deferred": [],
            "deferred_count": 0,
        },
        "auto_run_result": {"present": False, "status": None, "blocking_condition": None},
        "last_review_pass": None,
        "status": None,
        "parse_warnings": [],
        "error": None,
    }
    if not spec_path or not os.path.isfile(spec_path):
        result["error"] = f"spec file not found: {spec_path}"
        return result
    result["exists"] = True
    text, read_error = _read_text(spec_path)
    if read_error:
        result["error"] = read_error
        return result
    warnings = result["parse_warnings"]

    fm, fm_warnings = parse_frontmatter(text)
    warnings.extend(fm_warnings)
    fmr = result["frontmatter"]
    if fm is not None:
        for k in ("title", "type", "created", "status", "review_loop_iteration",
                  "followup_review_recommended", "baseline_revision"):
            v = fm.get(k)
            if isinstance(v, str):
                v = v.strip()
            fmr[k] = v
        if isinstance(fmr["status"], str):
            fmr["status"] = fmr["status"].lower() or None
        fmr["context"] = [x for x in _as_list(fm.get("context")) if x is not None]
        fmr["warnings"] = [x for x in _as_list(fm.get("warnings")) if x is not None]
        fmr["deferred"] = _normalize_deferred(fm.get("deferred"), warnings)
        fmr["deferred_count"] = len(fmr["deferred"])
    else:
        sm = _STATUS_FALLBACK_RE.search(text)
        if sm:
            fmr["status"] = sm.group(1).lower()
            warnings.append("frontmatter unparseable — status read by regex fallback")
        else:
            warnings.append("frontmatter unparseable and no status: line found")
    result["status"] = fmr["status"]

    _fm_lines, body = _frontmatter_block(text)
    sections = _sections(body if _fm_lines is not None else text)

    # ## Auto Run Result — optional corroboration only.
    arr = result["auto_run_result"]
    arr_lines = sections.get("Auto Run Result")
    if arr_lines is not None:
        arr["present"] = True
        for line in arr_lines:
            if arr["status"] is None:
                sm = _RESULT_STATUS_RE.match(line)
                if sm and sm.group(1).strip():
                    arr["status"] = sm.group(1).strip().strip("`").lower()
                    continue
            if arr["blocking_condition"] is None:
                bm = _RESULT_BLOCK_RE.match(line)
                if bm:
                    val = bm.group(1).strip().strip("`")
                    arr["blocking_condition"] = None if val.lower() in _NONE_WORDS else val
    elif not sections and (fm is None or set(fm) <= {"status"}):
        # The no-spec HALT skeleton (`bmad-build-auto-result-*.md`, upstream
        # workflow.md HALT step 2) has NO `## Auto Run Result` heading — only
        # `# BMad Build Auto Result` (H1) followed by the two result lines.
        # Read them from the H2-less body (frontmatter = `status` only is the
        # skeleton signature); `present` stays false (no heading).
        for line in (body if _fm_lines is not None else text).splitlines():
            if arr["status"] is None:
                sm = _RESULT_STATUS_RE.match(line)
                if sm and sm.group(1).strip():
                    arr["status"] = sm.group(1).strip().strip("`").lower()
                    continue
            if arr["blocking_condition"] is None:
                bm = _RESULT_BLOCK_RE.match(line)
                if bm:
                    val = bm.group(1).strip().strip("`")
                    arr["blocking_condition"] = None if val.lower() in _NONE_WORDS else val
    if arr["status"] and result["status"] and arr["status"] != result["status"]:
        warnings.append(
            f"Auto Run Result Status '{arr['status']}' disagrees with frontmatter status "
            f"'{result['status']}' (frontmatter is authoritative)"
        )

    # ## Review Triage Log — the LAST "### … — Review pass" block.
    log_lines = sections.get("Review Triage Log")
    if log_lines:
        blocks = []
        for line in log_lines:
            pm = _REVIEW_PASS_RE.match(line)
            if pm:
                blocks.append({"date": pm.group(1).strip() or None, "lines": []})
            elif blocks:
                if line.startswith("### "):
                    blocks.append(None)  # a foreign h3 ends the pass block
                elif blocks[-1] is not None:
                    blocks[-1]["lines"].append(line)
        passes = [b for b in blocks if b]
        if passes:
            last = passes[-1]
            lrp = {"date": last["date"], "intent_gap": None, "bad_spec": None,
                   "patch": None, "defer": None, "reject": None}
            for line in last["lines"]:
                cm = _COUNT_RE.match(line)
                if cm:
                    cat = cm.group(1).lower()
                    if lrp[cat] is None:
                        lrp[cat] = int(cm.group(2))
            result["last_review_pass"] = lrp
    return result


# --------------------------------------------------------------------------- #
# --find-spec
# --------------------------------------------------------------------------- #
_COLLISION_SUFFIX_RE = re.compile(r"-\d+$")


def _spec_regex_for(epic_num, story_num, suffix):
    return re.compile(rf"^spec-{epic_num}-{story_num}{re.escape(suffix)}-.+\.md$")


def _spec_stem(basename):
    stem = basename[:-3] if basename.endswith(".md") else basename
    return _COLLISION_SUFFIX_RE.sub("", stem)


def build_find_spec_result(impl_dir, story_key, sprint_status_path=None):
    """Locate the story's build-auto spec in impl_dir. Returns (result, exit_code)."""
    result = {
        "story_key": story_key,
        "impl_dir": impl_dir,
        "candidates": [],
        "spec_path": None,
        "status": None,
        "found": False,
        "ambiguous": False,
        "siblings": [],
        "hard_stop": False,
        "hard_stop_reason": None,
        "warnings": [],
        "error": None,
    }
    sm = STORY_RE.match(story_key or "")
    if not sm:
        result["error"] = f"invalid story key '{story_key}' (expected E-S[a-z]-slug)"
        result["hard_stop"] = True
        result["hard_stop_reason"] = result["error"]
        return result, 1
    epic_num, story_num, suffix = int(sm.group(1)), int(sm.group(2)), sm.group(3)
    mine = _spec_regex_for(epic_num, story_num, suffix)

    if not impl_dir or not os.path.isdir(impl_dir):
        result["error"] = f"implementation_artifacts dir not found: {impl_dir}"
        return result, 0

    others = []
    if sprint_status_path:
        _t, _e, stories, _r, hs, _err = _load_sprint(sprint_status_path)
        if not hs:
            for s in stories:
                if (s["epic_num"], s["story_num"], s["story_suffix"]) != (epic_num, story_num, suffix):
                    others.append(_spec_regex_for(s["epic_num"], s["story_num"], s["story_suffix"]))

    names = sorted(n for n in os.listdir(impl_dir) if mine.match(n) and os.path.isfile(os.path.join(impl_dir, n)))
    names = [n for n in names if not any(o.match(n) for o in others)]

    cands = []
    for n in names:
        p = os.path.join(impl_dir, n)
        info = read_spec(p)
        if info["error"]:
            # Unreadable / non-UTF-8 candidate: kept with status null (never a crash).
            result["warnings"].append(f"could not read spec candidate: {info['error']}")
        cands.append({"path": p, "status": info["status"], "mtime": os.stat(p).st_mtime})
    result["candidates"] = list(cands)

    if not cands:
        return result, 0

    live = cands
    if any(c["status"] != "done" for c in live) and any(c["status"] == "done" for c in live):
        live = [c for c in live if c["status"] != "done"]
    if any(c["status"] != "blocked" for c in live) and any(c["status"] == "blocked" for c in live):
        live = [c for c in live if c["status"] != "blocked"]

    if len(live) == 1:
        chosen = live[0]
    else:
        stems = {_spec_stem(os.path.basename(c["path"])) for c in live}
        if len(stems) == 1:
            live = sorted(live, key=lambda c: c["mtime"], reverse=True)
            chosen = live[0]
            result["siblings"] = [c["path"] for c in live[1:]]
        else:
            result["ambiguous"] = True
            result["hard_stop"] = True
            result["hard_stop_reason"] = (
                f"ambiguous spec files for {story_key}: " + ", ".join(c["path"] for c in live)
            )
            return result, 1
    result["spec_path"] = chosen["path"]
    result["status"] = chosen["status"]
    result["found"] = True
    return result, 0


# --------------------------------------------------------------------------- #
# --retro-verdict
# --------------------------------------------------------------------------- #
def build_retro_verdict_result(impl_dir, epic_arg):
    result = {
        "epic": None,
        "doc": None,
        "verdict": None,
        "date": None,
        "headless": None,
        "found": False,
        "warnings": [],
        "error": None,
    }
    epic_num = parse_epic_arg(epic_arg)
    if epic_num is None:
        result["error"] = f"could not parse --epic '{epic_arg}' (expected N or epic-N)"
        return result, 2
    result["epic"] = epic_num
    if not impl_dir or not os.path.isdir(impl_dir):
        result["error"] = f"implementation_artifacts dir not found: {impl_dir}"
        return result, 0
    name_re = re.compile(rf"^epic-{epic_num}-retro-.+\.md$")
    docs = []
    for root, dirs, files in os.walk(impl_dir):
        dirs.sort()
        for n in files:
            if name_re.match(n):
                p = os.path.join(root, n)
                docs.append((os.stat(p).st_mtime, p))
    if not docs:
        return result, 0
    docs.sort(reverse=True)
    doc = docs[0][1]
    result["doc"] = doc
    result["found"] = True
    text, read_error = _read_text(doc)
    if read_error:
        result["error"] = read_error
        return result, 1
    fm_lines, _ = _frontmatter_block(text)
    if fm_lines is None:
        result["warnings"].append("retro document has no closed frontmatter block")
        return result, 0
    fm_text = "\n".join(fm_lines)

    def scalar(name):
        m = re.search(rf"^{name}:\s*(.*)$", fm_text, re.MULTILINE)
        if not m:
            return None
        v = _parse_scalar(m.group(1))
        return v

    verdict = scalar("verdict")
    if isinstance(verdict, str):
        verdict = verdict.strip().lower()
    if verdict in RETRO_VERDICTS:
        result["verdict"] = verdict
    else:
        result["warnings"].append(
            f"unrecognized verdict {verdict!r} (expected one of {', '.join(RETRO_VERDICTS)})"
        )
    date = scalar("date")
    result["date"] = str(date) if date is not None else None
    headless = scalar("headless")
    result["headless"] = headless if isinstance(headless, bool) else None
    return result, 0


# --------------------------------------------------------------------------- #
# Self-test
# --------------------------------------------------------------------------- #
_FIXTURE = """\
generated: 05-06-2025 21:30
last_updated: 05-06-2025 21:30
project: Demo
tracking_system: file-system

development_status:
  epic-1: in-progress
  1-1-user-authentication: done
  1-2-account-management: review
  1-3-plant-data-model: backlog
  1-30-plant-export: backlog
  epic-1-retrospective: optional

  epic-2: backlog
  2-1-personality-system: backlog
  2-6a-digest-delivery: ready-for-dev
  2-6b-digest-archive: backlog
"""

_SPEC_FIXTURE = """\
---
title: 'Story 1.2: Account management'
type: 'feature' # feature | bugfix | refactor | chore
created: '2026-08-10'
status: 'done' # draft | ready-for-dev | in-progress | in-review | done | blocked
review_loop_iteration: 1 # incremented by step-04 before each review loopback
followup_review_recommended: true # set by step-04 on status: done
context: ['{project-root}/docs/standards.md'] # optional
warnings: [oversized] # optional: machine-readable warnings for orchestration
deferred:
  - summary: >-
      Legacy session store ignores TTL: sessions never expire
    evidence: |-
      `store.get()` at src/session.py:88 has no expiry check;
      the "ttl" column is written but never read.
    location: >- # optional — file:line or component
      src/session.py:88
    severity: medium # optional — high | medium | low
  - summary: >-
      Duplicate email check is case-sensitive
    evidence: |-
      users table has no lower(email) index; `Foo@x.io` and `foo@x.io` both insert.
baseline_revision: 0123456789abcdef0123456789abcdef01234567
---

<intent-contract>

## Intent

**Problem:** Users cannot manage their account.

**Approach:** Add an account page.

## Boundaries & Constraints

**Always:** keep the API stable.

**Block If:** the auth provider must change.

**Never:** touch billing.

</intent-contract>

## Code Map

- `src/account.py` -- account service

## Tasks & Acceptance

**Execution:**
- `src/account.py` -- add update endpoint -- needed by the page

**Acceptance Criteria:**
- Given a logged-in user, when they change their name, then the profile shows it

## Spec Change Log

### 2026-08-11 — bad_spec loopback 1
- finding: the AC omitted the empty-name case
- amended: Tasks & Acceptance
- KEEP: the endpoint shape

## Review Triage Log

### 2026-08-11 — Review pass
- intent_gap: 0
- bad_spec: 1: (high 0, medium 1, low 0)
- patch: 0
- defer: 0
- reject: 2: (high 0, medium 0, low 2)
- addressed_findings:
  - `[medium]` `[bad_spec]` empty-name AC missing — spec amended, code re-derived

### 2026-08-12 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 3: (high 1, medium 1, low 1)
- defer: 2: (high 0, medium 1, low 1)
- reject: 1: (high 0, medium 0, low 1)
- addressed_findings:
  - `[high]` `[patch]` name update skipped the CSRF check — fixed
  - `[medium]` `[patch]` no length limit on display name — fixed
  - `[low]` `[patch]` typo in the success toast — fixed

## Auto Run Result

Status: done
Blocking condition: none

- Summary: account page + update endpoint implemented.
- Files changed: `src/account.py` (endpoint), `web/account.html` (page)
- Review findings breakdown: 3 patched, 2 deferred, 1 rejected
- Follow-up review recommendation: true (patched: high 1, medium 1, low 1; score 4 + high)
- Verification performed: `pytest -q` passed (42 tests)
- Residual risks: none known

## Verification

**Commands:**
- `pytest -q` -- expected: all green
"""


def _run_self_test():
    import contextlib
    import io
    import shutil
    import stat
    import time

    failures = []

    def check(name, cond):
        if not cond:
            failures.append(name)

    root = tempfile.mkdtemp(prefix="story_plan_selftest_")

    def write(rel, body):
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(body)
        return p

    def slurp(p):
        with open(p, "r", encoding="utf-8", newline="") as fh:
            return fh.read()

    sp = write("sprint-status.yaml", _FIXTURE)

    # ---- grammar --------------------------------------------------------- #
    m = STORY_RE.match("2-6a-digest-delivery")
    check("grammar: split key parses", m and m.group(3) == "a" and m.group(4) == "digest-delivery")
    m = STORY_RE.match("1-30-plant-export")
    check("grammar: plain key has empty suffix", m and m.group(3) == "" and m.group(2) == "30")
    check("grammar: STATUS_RANK order", STATUS_RANK["backlog"] < STATUS_RANK["ready-for-dev"] < STATUS_RANK["in-progress"] < STATUS_RANK["review"] < STATUS_RANK["done"])

    # ---- --resolve -------------------------------------------------------- #
    r, code = build_resolve_result(sp, "1-2")
    check("resolve E-S: exit 0", code == 0)
    check("resolve E-S: key", r["story_key"] == "1-2-account-management")
    check("resolve E-S: fields", r["epic_num"] == 1 and r["story_num"] == 2 and r["story_suffix"] == "" and r["slug"] == "account-management")
    check("resolve E-S: status/epic/retro", r["current_status"] == "review" and r["epic_status"] == "in-progress" and r["retrospective_status"] == "optional")
    check("resolve E-S: epic facts", r["epic_story_count"] == 4 and r["is_first_in_epic"] is False and r["is_last_in_epic"] is False and r["stories_after_in_epic"] == 2)
    check("resolve E-S: title null without planning dir", r["title"] is None and r["epic_title"] is None)
    r, _ = build_resolve_result(sp, "1.3")
    check("resolve E.S: 1.3 not 1.30", r["story_key"] == "1-3-plant-data-model")
    r, _ = build_resolve_result(sp, "1-30")
    check("resolve E-S: 1-30 is last with 0 after", r["story_key"] == "1-30-plant-export" and r["is_last_in_epic"] is True and r["stories_after_in_epic"] == 0)
    r, _ = build_resolve_result(sp, "1-1-user-authentication")
    check("resolve full key: first in epic", r["is_first_in_epic"] is True and r["stories_after_in_epic"] == 3)
    r, code = build_resolve_result(sp, "2.6a")
    check("resolve E.Sx: split key", code == 0 and r["story_key"] == "2-6a-digest-delivery" and r["story_suffix"] == "a")
    check("resolve E.Sx: 6a before 6b", r["is_last_in_epic"] is False and r["stories_after_in_epic"] == 1)
    r, code = build_resolve_result(sp, "2-6b")
    check("resolve E-Sx: 6b last", code == 0 and r["is_last_in_epic"] is True)
    r, code = build_resolve_result(sp, "2-6")
    check("resolve E-S with only suffixed keys: ambiguous exit 1", code == 1 and r["hard_stop"] is True)
    check("resolve ambiguous: candidates listed", r["candidates"] == ["2-6a-digest-delivery", "2-6b-digest-archive"])
    r, code = build_resolve_result(sp, "Digest")
    check("resolve substring: ambiguous across two", code == 1 and sorted(r["candidates"]) == ["2-6a-digest-delivery", "2-6b-digest-archive"])
    r, code = build_resolve_result(sp, "PLANT-EXPORT")
    check("resolve substring: case-insensitive unique", code == 0 and r["story_key"] == "1-30-plant-export")
    r, code = build_resolve_result(sp, "9-9")
    check("resolve not found: hard_stop exit 1", code == 1 and r["hard_stop"] is True and "not found" in r["hard_stop_reason"])
    r, code = build_resolve_result(os.path.join(root, "nope.yaml"), "1-2")
    check("resolve missing file: hard_stop exit 1", code == 1 and r["hard_stop"] is True)
    empty = write("empty.yaml", "generated: x\n")
    r, code = build_resolve_result(empty, "1-2")
    check("resolve empty file: hard_stop exit 1", code == 1 and "empty/invalid" in r["hard_stop_reason"])

    # ---- --planning-dir titles -------------------------------------------- #
    plan = os.path.join(root, "planning")
    write("planning/epics.md", """\
# Epics

## Epic 1: Plant Care Core

### Story 1.1: User Authentication
As a user…

### Story 1.3: Plant Data Model ##
### Story 1.30: Plant Export

```md
### Story 1.2: FENCED SHOULD BE IGNORED
```

## Epic 2 — Digest

### Story 2.6a: Digest Delivery
#### Story 2.6b: Digest Archive
""")
    write("planning/epic-2-notes.md", "# Epic 2: Digest Notes\n\n### Story 2.1: Personality System\n")
    write("planning/other.md", "### Story 1.2: WRONG FILE\n")
    r, _ = build_resolve_result(sp, "1-3", plan)
    check("titles: 1.3 (not 1.30), trailing hashes stripped", r["title"] == "Plant Data Model")
    check("titles: epic_title", r["epic_title"] == "Plant Care Core")
    r, _ = build_resolve_result(sp, "1-30", plan)
    check("titles: 1.30", r["title"] == "Plant Export")
    r, _ = build_resolve_result(sp, "1-2", plan)
    check("titles: fenced heading ignored, non-matching file skipped ⇒ null", r["title"] is None)
    r, _ = build_resolve_result(sp, "2.6a", plan)
    check("titles: suffix story 2.6a", r["title"] == "Digest Delivery")
    r, _ = build_resolve_result(sp, "2-1", plan)
    check("titles: epic-2*.md file read", r["title"] == "Personality System")
    check("titles: epic-2 title first match wins (sorted walk: epic-2-notes.md before epics.md)", r["epic_title"] == "Digest Notes")
    r, _ = build_resolve_result(sp, "1-2", os.path.join(root, "no-such-planning"))
    check("titles: missing planning dir ⇒ null, no hard-stop", r["title"] is None and r["hard_stop"] is False)
    bad_plan = os.path.join(root, "planning-bad")
    os.makedirs(bad_plan)
    with open(os.path.join(bad_plan, "epics.md"), "wb") as fh:
        fh.write(b"## Epic 1: Caf\xe9\n### Story 1.2: X\n")
    r, _ = build_resolve_result(sp, "1-2", bad_plan)
    check("titles: non-UTF-8 epics doc skipped ⇒ null, no crash", r["title"] is None and r["hard_stop"] is False)

    # ---- --epic ---------------------------------------------------------- #
    ep = build_epic_result(sp, "1", plan)
    check("epic-1: basics", ep["epic_num"] == 1 and ep["epic_status"] == "in-progress" and ep["epic_story_count"] == 4 and ep["hard_stop"] is False)
    check("epic-1: epic_title", ep["epic_title"] == "Plant Care Core")
    check("epic-1: order", [s["key"] for s in ep["epic_stories"]] == ["1-1-user-authentication", "1-2-account-management", "1-3-plant-data-model", "1-30-plant-export"])
    check("epic-1: first/last flags", ep["epic_stories"][0]["is_first_in_epic"] is True and ep["epic_stories"][-1]["is_last_in_epic"] is True and ep["epic_stories"][1]["is_first_in_epic"] is False)
    check("epic-1: stories_after", [s["stories_after_in_epic"] for s in ep["epic_stories"]] == [3, 2, 1, 0])
    check("epic-1: titles", [s["title"] for s in ep["epic_stories"]] == ["User Authentication", None, "Plant Data Model", "Plant Export"])
    check("epic-1: no v6 fields", "story_file" not in ep["epic_stories"][0] and "next_action" not in ep["epic_stories"][0])
    ep2 = build_epic_result(sp, "epic-2")
    check("epic-2: epic-N form + suffix order", ep2["epic_num"] == 2 and [s["key"] for s in ep2["epic_stories"]] == ["2-1-personality-system", "2-6a-digest-delivery", "2-6b-digest-archive"])
    check("epic-2: suffix field", ep2["epic_stories"][1]["story_suffix"] == "a" and ep2["epic_stories"][1]["story_num"] == 6)
    check("epic-2: title null without planning dir", ep2["epic_title"] is None and ep2["epic_stories"][0]["title"] is None)
    check("epic-9: hard_stop", build_epic_result(sp, "9")["hard_stop"] is True)
    check("epic bad arg: hard_stop", build_epic_result(sp, "nope")["hard_stop"] is True)
    check("epic missing file: hard_stop", build_epic_result(os.path.join(root, "nope.yaml"), "1")["hard_stop"] is True)
    done_sp = write("done.yaml", "development_status:\n  epic-3: done\n  3-1-foo: done\n  3-2-bar: done\n")
    dep = build_epic_result(done_sp, "3")
    check("epic-3 done: hard_stop but lists stories", dep["hard_stop"] is True and "done" in dep["hard_stop_reason"] and len(dep["epic_stories"]) == 2)

    # ---- --mark-status ---------------------------------------------------- #
    mark_fixture = """\
generated: 05-06-2025 21:30
last_updated: 05-06-2025 21:30
project: Demo

development_status:
  epic-1: in-progress
  1-1-user-authentication: done
  1-2-account-management: review  # awaiting final pass
  1-3-plant-data-model: backlog
  epic-1-retrospective: optional

  epic-2: backlog
  2-1-personality-system: backlog
  2-6a-digest-delivery: ready-for-dev
"""
    fixed_now = _dt.datetime(2026, 8, 16, 9, 5)
    stamp = "08-16-2026 09:05"

    def fresh(body, name="ms.yaml"):
        return write(name, body)

    # Happy path: value token + last_updated only; comment/indent preserved.
    p = fresh(mark_fixture)
    res, code = mark_status(p, "1-2-account-management", "done", now=fixed_now)
    check("mark: exit 0", code == 0)
    check("mark: previous/updated", res["previous_status"] == "review" and res["sprint_updated"] is True and res["already_at_status"] is False)
    check("mark: last_updated json", res["last_updated"] == {"previous": "05-06-2025 21:30", "new": stamp, "added": False})
    check("mark: no epic lift (1-3 still backlog)", res["epic_lift"] is None)
    expected = mark_fixture.replace("last_updated: 05-06-2025 21:30", f"last_updated: {stamp}").replace(
        "  1-2-account-management: review  # awaiting final pass",
        "  1-2-account-management: done  # awaiting final pass",
    )
    check("mark: byte-preserving (value token + stamp only)", slurp(p) == expected)
    check("mark: no JSON legacy keys", "story_file_updated" not in res and "already_done" not in res)

    # Idempotent: no write, no stamp, no lift.
    p = fresh(mark_fixture)
    res, code = mark_status(p, "1-1-user-authentication", "done", now=fixed_now)
    check("mark idempotent: exit 0 already_at_status", code == 0 and res["already_at_status"] is True and res["sprint_updated"] is False)
    check("mark idempotent: no stamp", res["last_updated"]["new"] is None and res["last_updated"]["added"] is False and res["last_updated"]["previous"] == "05-06-2025 21:30")
    check("mark idempotent: file untouched", slurp(p) == mark_fixture)

    # Regress guard.
    p = fresh(mark_fixture)
    res, code = mark_status(p, "1-2-account-management", "ready-for-dev", now=fixed_now)
    check("mark regress: exit 1", code == 1)
    check("mark regress: message", res["error"] == "refusing to regress 1-2-account-management from review to ready-for-dev (pass --allow-regress)")
    check("mark regress: file untouched", slurp(p) == mark_fixture)
    res, code = mark_status(p, "1-2-account-management", "ready-for-dev", allow_regress=True, now=fixed_now)
    check("mark regress allowed: exit 0 flipped", code == 0 and res["sprint_updated"] is True and "1-2-account-management: ready-for-dev  # awaiting" in slurp(p))
    # A legacy alias value ranks by its normalized status (drafted == ready-for-dev).
    p = fresh(mark_fixture.replace("2-6a-digest-delivery: ready-for-dev", "2-6a-digest-delivery: drafted"))
    res, code = mark_status(p, "2-6a-digest-delivery", "backlog", now=fixed_now)
    check("mark regress: alias normalized", code == 1 and "from ready-for-dev to backlog" in res["error"])
    res, code = mark_status(p, "2-6a-digest-delivery", "ready-for-dev", now=fixed_now)
    check("mark alias == target: already_at_status", code == 0 and res["already_at_status"] is True and "drafted" in slurp(p))

    # Invalid target / missing key / missing file.
    p = fresh(mark_fixture)
    res, code = mark_status(p, "1-2-account-management", "shipped")
    check("mark invalid: exit 1 names status", code == 1 and "shipped" in res["error"] and slurp(p) == mark_fixture)
    res, code = mark_status(p, "9-9-nope", "done")
    check("mark missing key: exit 1", code == 1 and bool(res["error"]) and slurp(p) == mark_fixture)
    res, code = mark_status(os.path.join(root, "nope.yaml"), "1-1-user-authentication", "done")
    check("mark missing file: exit 1", code == 1)

    # last_updated styles: quoted stays quoted (with comment); absent ⇒ inserted before development_status.
    p = fresh(mark_fixture.replace("last_updated: 05-06-2025 21:30", 'last_updated: "05-06-2025 21:30"  # stamp'))
    res, code = mark_status(p, "1-3-plant-data-model", "ready-for-dev", now=fixed_now)
    check("mark stamp quoted: preserved", code == 0 and f'last_updated: "{stamp}"  # stamp\n' in slurp(p))
    p = fresh(mark_fixture.replace("last_updated: 05-06-2025 21:30", "last_updated: '05-06-2025 21:30'"))
    mark_status(p, "1-3-plant-data-model", "ready-for-dev", now=fixed_now)
    check("mark stamp single-quoted: preserved", f"last_updated: '{stamp}'\n" in slurp(p))
    p = fresh(mark_fixture.replace("last_updated: 05-06-2025 21:30\n", ""))
    res, code = mark_status(p, "1-3-plant-data-model", "ready-for-dev", now=fixed_now)
    check("mark stamp absent: added", code == 0 and res["last_updated"] == {"previous": None, "new": stamp, "added": True})
    check("mark stamp absent: inserted before development_status", f'project: Demo\n\nlast_updated: "{stamp}"\ndevelopment_status:\n' in slurp(p))
    # A `last_updated` key INSIDE development_status must not be mistaken for the top-level one.
    p = fresh(mark_fixture.replace("last_updated: 05-06-2025 21:30\n", "").replace("  epic-2: backlog\n", "  epic-2: backlog\n  last_updated: weird\n"))
    res, code = mark_status(p, "1-3-plant-data-model", "ready-for-dev", now=fixed_now)
    check("mark stamp: nested key ignored, top-level added", res["last_updated"]["added"] is True and "  last_updated: weird\n" in slurp(p))

    # Empty `last_updated:` value ⇒ rewritten like the absent case (space after the colon, quoted).
    p = fresh(mark_fixture.replace("last_updated: 05-06-2025 21:30", "last_updated:"))
    res, code = mark_status(p, "1-3-plant-data-model", "ready-for-dev", now=fixed_now)
    check("mark stamp empty: previous null, not added", code == 0 and res["last_updated"] == {"previous": None, "new": stamp, "added": False})
    check("mark stamp empty: valid mapping line", f'\nlast_updated: "{stamp}"\nproject: Demo\n' in slurp(p))
    # Empty value with an inline comment ⇒ comment kept, spaced off the stamp.
    p = fresh(mark_fixture.replace("last_updated: 05-06-2025 21:30", "last_updated:   # note"))
    res, code = mark_status(p, "1-3-plant-data-model", "ready-for-dev", now=fixed_now)
    check("mark stamp comment-only: previous null", code == 0 and res["last_updated"]["previous"] is None)
    check("mark stamp comment-only: comment kept", f'\nlast_updated: "{stamp}"   # note\n' in slurp(p))
    # Empty quoted value / no space after the colon ⇒ a space is always emitted.
    p = fresh(mark_fixture.replace("last_updated: 05-06-2025 21:30", 'last_updated:""'))
    mark_status(p, "1-3-plant-data-model", "ready-for-dev", now=fixed_now)
    check("mark stamp glued empty quotes: spaced + quoted", f'\nlast_updated: "{stamp}"\n' in slurp(p))

    # Quoted status tokens (hand-edited files; upstream's ruamel reader accepts them).
    quoted = mark_fixture.replace("1-1-user-authentication: done", '1-1-user-authentication: "done"').replace(
        "1-2-account-management: review  #", "1-2-account-management: 'review'  #")
    p = fresh(quoted)
    r, code = build_resolve_result(p, "1-2")
    check("quoted status: resolve unquotes", code == 0 and r["current_status"] == "review")
    check("quoted status: epic listing unquotes", build_epic_result(p, "1")["epic_stories"][0]["status"] == "done")
    res, code = mark_status(p, "1-1-user-authentication", "done", now=fixed_now)
    check("quoted status: already_at_status", code == 0 and res["already_at_status"] is True and res["previous_status"] == "done" and slurp(p) == quoted)
    res, code = mark_status(p, "1-2-account-management", "ready-for-dev", now=fixed_now)
    check("quoted status: regress guard sees the value", code == 1 and "from review to ready-for-dev" in res["error"] and slurp(p) == quoted)
    res, code = mark_status(p, "1-2-account-management", "done", now=fixed_now)
    check("quoted status: flip keeps the quote style", code == 0 and res["previous_status"] == "review" and "  1-2-account-management: 'done'  # awaiting final pass\n" in slurp(p))
    res, code = mark_status(p, "1-3-plant-data-model", "done", now=fixed_now)
    check("quoted status: epic lift fires across quoted siblings", res["epic_lift"] == {"key": "epic-1", "previous": "in-progress", "new": "done"} and "  epic-1: done\n" in slurp(p))
    p = fresh(mark_fixture.replace("epic-2: backlog", 'epic-2: "backlog"'))
    res, code = mark_status(p, "2-1-personality-system", "in-progress", now=fixed_now)
    check("quoted epic entry: lift keeps quotes, previous unquoted", res["epic_lift"] == {"key": "epic-2", "previous": "backlog", "new": "in-progress"} and '  epic-2: "in-progress"\n' in slurp(p))

    # Epic lift both ways.
    p = fresh(mark_fixture)
    res, code = mark_status(p, "2-1-personality-system", "in-progress", now=fixed_now)
    check("lift in-progress: epic-2 backlog → in-progress", res["epic_lift"] == {"key": "epic-2", "previous": "backlog", "new": "in-progress"} and "  epic-2: in-progress\n" in slurp(p))
    res, code = mark_status(p, "2-6a-digest-delivery", "in-progress", now=fixed_now)
    check("lift in-progress: already lifted ⇒ null", res["epic_lift"] is None)
    p = fresh(mark_fixture.replace("1-2-account-management: review", "1-2-account-management: done"))
    res, code = mark_status(p, "1-3-plant-data-model", "done", allow_regress=False, now=fixed_now)
    check("lift done: last story done ⇒ epic-1 done", res["epic_lift"] == {"key": "epic-1", "previous": "in-progress", "new": "done"} and "  epic-1: done\n" in slurp(p))
    p = fresh(mark_fixture)
    res, code = mark_status(p, "1-3-plant-data-model", "done", now=fixed_now)
    check("lift done: 1-2 still review ⇒ no lift", res["epic_lift"] is None and "  epic-1: in-progress\n" in slurp(p))
    p = fresh("development_status:\n  4-1-solo: review\n")
    res, code = mark_status(p, "4-1-solo", "done", now=fixed_now)
    check("lift done: no epic entry ⇒ null, still flips + stamps", code == 0 and res["epic_lift"] is None and res["last_updated"]["added"] is True and "  4-1-solo: done\n" in slurp(p))

    # Non-UTF-8 sprint file: every reader returns JSON + exit 1, never a traceback.
    bad_sp = os.path.join(root, "bad-utf8.yaml")
    with open(bad_sp, "wb") as fh:
        fh.write(b"development_status:\n  1-1-foo: done\n  # caf\xe9\n")
    r, code = build_resolve_result(bad_sp, "1-1")
    check("unreadable sprint: resolve hard_stop exit 1", code == 1 and r["hard_stop"] is True and "UTF-8" in r["error"])
    ep_bad = build_epic_result(bad_sp, "1")
    check("unreadable sprint: epic hard_stop", ep_bad["hard_stop"] is True and "UTF-8" in ep_bad["error"])
    res, code = mark_status(bad_sp, "1-1-foo", "done", now=fixed_now)
    check("unreadable sprint: mark exit 1, untouched", code == 1 and "UTF-8" in res["error"] and res["sprint_updated"] is False and open(bad_sp, "rb").read().endswith(b"caf\xe9\n"))
    r, code = build_find_spec_result(os.path.join(root, "impl"), "1-1-foo", bad_sp)
    check("unreadable sprint: find-spec still runs (no other-story filter)", code == 0 and r["found"] is False and r["hard_stop"] is False)

    # CRLF preserved.
    p = fresh(mark_fixture.replace("\n", "\r\n"))
    res, code = mark_status(p, "1-3-plant-data-model", "ready-for-dev", now=fixed_now)
    body = slurp(p)
    check("mark crlf: preserved", code == 0 and "\r\n" in body and "\n" not in body.replace("\r\n", ""))

    # Mode preserved by the atomic replace.
    p = fresh(mark_fixture)
    wide = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH
    os.chmod(p, wide)
    mark_status(p, "1-3-plant-data-model", "ready-for-dev", now=fixed_now)
    check("mark modes: preserved", os.stat(p).st_mode & 0o7777 == wide)

    # Atomicity: read-only directory ⇒ error, file byte-identical, no temp litter.
    if getattr(os, "geteuid", lambda: 0)() != 0:
        ro_dir = os.path.join(root, "ro")
        os.makedirs(ro_dir)
        rp = os.path.join(ro_dir, "sprint-status.yaml")
        with open(rp, "w", encoding="utf-8") as fh:
            fh.write(mark_fixture)
        os.chmod(ro_dir, stat.S_IRUSR | stat.S_IXUSR)
        try:
            res, code = mark_status(rp, "1-3-plant-data-model", "ready-for-dev", now=fixed_now)
        finally:
            os.chmod(ro_dir, stat.S_IRWXU)
        check("mark ro-dir: exit 1 error", code == 1 and bool(res["error"]) and res["sprint_updated"] is False)
        check("mark ro-dir: file untouched, no litter", slurp(rp) == mark_fixture and os.listdir(ro_dir) == ["sprint-status.yaml"])
        check("mark ro-dir: no lift/stamp claimed", res["epic_lift"] is None and res["last_updated"]["new"] is None)

    # ---- --spec ---------------------------------------------------------- #
    spec_p = write("impl/spec-1-2-account-management.md", _SPEC_FIXTURE)
    s = read_spec(spec_p)
    fm = s["frontmatter"]
    check("spec: exists", s["exists"] is True and s["error"] is None)
    check("spec: scalars", fm["title"] == "Story 1.2: Account management" and fm["type"] == "feature" and fm["created"] == "2026-08-10")
    check("spec: status authoritative", s["status"] == "done" and fm["status"] == "done")
    check("spec: ints/bools", fm["review_loop_iteration"] == 1 and fm["followup_review_recommended"] is True)
    check("spec: baseline_revision", fm["baseline_revision"] == "0123456789abcdef0123456789abcdef01234567")
    check("spec: flow lists", fm["context"] == ["{project-root}/docs/standards.md"] and fm["warnings"] == ["oversized"])
    check("spec: deferred_count", fm["deferred_count"] == 2 and len(fm["deferred"]) == 2)
    d0, d1 = fm["deferred"]
    check("spec: deferred[0] folded summary", d0["summary"] == "Legacy session store ignores TTL: sessions never expire")
    check("spec: deferred[0] literal evidence", d0["evidence"] == '`store.get()` at src/session.py:88 has no expiry check;\nthe "ttl" column is written but never read.')
    check("spec: deferred[0] location (comment on indicator line)", d0["location"] == "src/session.py:88")
    check("spec: deferred[0] severity (inline comment stripped)", d0["severity"] == "medium")
    check("spec: deferred[1] optional fields null", d1["summary"] == "Duplicate email check is case-sensitive" and d1["location"] is None and d1["severity"] is None)
    check("spec: deferred[1] evidence with backticks/colons", d1["evidence"] == "users table has no lower(email) index; `Foo@x.io` and `foo@x.io` both insert.")
    check("spec: auto_run_result", s["auto_run_result"] == {"present": True, "status": "done", "blocking_condition": None})
    check("spec: last review pass is the LAST block", s["last_review_pass"] == {"date": "2026-08-12", "intent_gap": 0, "bad_spec": 0, "patch": 3, "defer": 2, "reject": 1})
    check("spec: no parse warnings", s["parse_warnings"] == [])

    # Same spec, ready-for-dev after the plan halt: no result lines ⇒ nulls; frontmatter authoritative.
    rfd = _SPEC_FIXTURE.replace("status: 'done'", "status: 'ready-for-dev'").split("## Review Triage Log")[0]
    rfd += "## Review Triage Log\n\n## Auto Run Result\n\n"
    rp = write("impl/spec-9-1-rfd.md", rfd)
    s = read_spec(rp)
    check("spec rfd: status ready-for-dev", s["status"] == "ready-for-dev")
    check("spec rfd: result heading present, lines null", s["auto_run_result"] == {"present": True, "status": None, "blocking_condition": None})
    check("spec rfd: no review pass ⇒ null", s["last_review_pass"] is None)
    check("spec rfd: deferred still parsed", s["frontmatter"]["deferred_count"] == 2)

    # Blocked spec with a blocking condition + a disagreeing result status.
    blocked = _SPEC_FIXTURE.replace("status: 'done'", "status: 'blocked'").replace(
        "Status: done\nBlocking condition: none", "**Status:** in-review\n- Blocking condition: intent gap")
    bp = write("impl/spec-9-2-blocked.md", blocked)
    s = read_spec(bp)
    check("spec blocked: frontmatter wins", s["status"] == "blocked")
    check("spec blocked: result status read + disagreement warning", s["auto_run_result"]["status"] == "in-review" and any("disagrees" in w for w in s["parse_warnings"]))
    check("spec blocked: blocking condition verbatim", s["auto_run_result"]["blocking_condition"] == "intent gap")

    # No-spec skeleton result file (upstream HALT protocol) and empty deferred.
    skel = write("impl/bmad-build-auto-result-x.md", "---\nstatus: blocked\n---\n\n# BMad Build Auto Result\n\n## Auto Run Result\n\nStatus: blocked\nBlocking condition: unclear intent\n")
    s = read_spec(skel)
    check("spec skeleton: status + blocking condition", s["status"] == "blocked" and s["auto_run_result"]["blocking_condition"] == "unclear intent" and s["frontmatter"]["deferred"] == [] and s["frontmatter"]["title"] is None)
    check("spec skeleton (folder+id, H2 present): present true", s["auto_run_result"]["present"] is True)
    # The no-spec HALT skeleton as upstream actually writes it (workflow.md HALT step 2):
    # H1 only, no `## Auto Run Result` ⇒ present false, but the two lines are still read.
    skel_h1 = write("impl/bmad-build-auto-result-y.md", "---\nstatus: blocked\n---\n\n# BMad Build Auto Result\n\nStatus: blocked\nBlocking condition: missing previous-story continuity decision\n")
    s = read_spec(skel_h1)
    check("spec skeleton H1-only: status + blocking condition read, present false", s["status"] == "blocked" and s["auto_run_result"] == {"present": False, "status": "blocked", "blocking_condition": "missing previous-story continuity decision"} and s["parse_warnings"] == [])
    # A real spec without the H2 (frontmatter has more than `status`) does NOT scan the body.
    nosec = write("impl/spec-9-7-noh2.md", "---\ntitle: 'T'\nstatus: 'in-progress'\n---\n\nStatus: done\nBlocking condition: bogus\n")
    s = read_spec(nosec)
    check("spec no-H2 non-skeleton: body lines ignored", s["auto_run_result"] == {"present": False, "status": None, "blocking_condition": None} and s["status"] == "in-progress")
    # Non-UTF-8 spec ⇒ exists true + error (exit 1 via the CLI), no traceback.
    bad_spec = os.path.join(root, "impl", "spec-9-8-bad.md")
    with open(bad_spec, "wb") as fh:
        fh.write(b"---\nstatus: done\n---\n\xff\xfe\n")
    s = read_spec(bad_spec)
    check("spec non-UTF-8: exists + error, status null", s["exists"] is True and "UTF-8" in s["error"] and s["status"] is None)
    # LLM-written variance: a bare `-` item, a plain multi-line value (blank line ⇒ newline),
    # a scalar list item with continuation — the WHOLE list survives.
    var = write("impl/spec-9-9-variance.md", "---\nstatus: done\ndeferred:\n  -\n    summary: alone on its own lines\n    severity: low\n  - summary: this is a long\n      continued summary\n\n      second paragraph\n    severity: high  # trailing\n  - summary: >-\n      canonical\n  -\n    - nested\n      scalar\n  -\nwarnings:\n  - one\n    more\n  - [a, b]\n---\n")
    s = read_spec(var)
    d = s["frontmatter"]["deferred"]
    check("spec variance: five items kept", s["frontmatter"]["deferred_count"] == 5 and len(d) == 5)
    check("spec variance: bare-dash mapping item", d[0] == {"summary": "alone on its own lines", "evidence": None, "location": None, "severity": "low"})
    check("spec variance: plain multi-line folded, blank ⇒ newline, comment stripped", d[1]["summary"] == "this is a long continued summary\nsecond paragraph" and d[1]["severity"] == "high")
    check("spec variance: canonical item unaffected", d[2]["summary"] == "canonical")
    check("spec variance: bare-dash nested list ⇒ non-mapping warning, kept as summary", d[3]["summary"] == "['nested scalar']" and any("not a mapping" in w for w in s["parse_warnings"]))
    check("spec variance: trailing bare dash ⇒ null item kept", d[4]["summary"] is None)
    check("spec variance: warnings list continuation + flow item", s["frontmatter"]["warnings"] == ["one more", ["a", "b"]])

    # A `deferred: []` template default.
    tpl = write("impl/spec-9-3-tpl.md", "---\ntitle: 'T'\nstatus: 'draft'\ndeferred: [] # append-only\n---\n\nbody\n")
    s = read_spec(tpl)
    check("spec template: deferred [] ⇒ empty, count 0", s["frontmatter"]["deferred"] == [] and s["frontmatter"]["deferred_count"] == 0 and s["status"] == "draft")
    check("spec template: no result heading", s["auto_run_result"] == {"present": False, "status": None, "blocking_condition": None})

    # A zero-indent block list (YAML-legal, LLM-written) still parses; the key after it survives.
    zi = write("impl/spec-9-6-zero-indent.md", "---\nstatus: done\ndeferred:\n- summary: >-\n    Zero indent item\n  severity: low\nbaseline_revision: abc\n---\n")
    s = read_spec(zi)
    check("spec zero-indent list: parsed + following key kept", s["frontmatter"]["deferred_count"] == 1 and s["frontmatter"]["deferred"][0]["summary"] == "Zero indent item" and s["frontmatter"]["deferred"][0]["severity"] == "low" and s["frontmatter"]["baseline_revision"] == "abc")

    # Frontmatter parse failure ⇒ regex fallback + warning.
    broken = write("impl/spec-9-4-broken.md", "---\nstatus: 'in-progress'\ntitle: x\n\nno closing fence\n")
    s = read_spec(broken)
    check("spec broken: fallback status + warning", s["status"] == "in-progress" and any("fallback" in w for w in s["parse_warnings"]))
    s = read_spec(os.path.join(root, "impl", "missing.md"))
    check("spec missing: exists false + error", s["exists"] is False and bool(s["error"]))
    # parse_frontmatter helper (imported by deferred_ledger.py harvest).
    pf, pw = parse_frontmatter(_SPEC_FIXTURE)
    check("parse_frontmatter: deferred list of mappings", isinstance(pf, dict) and len(pf["deferred"]) == 2 and pf["deferred"][1]["summary"].startswith("Duplicate"))
    # A triage-log heading with an ASCII hyphen and a bold count still parses.
    hy = _SPEC_FIXTURE.replace("### 2026-08-12 — Review pass", "### 2026-08-13 - Review pass").replace("- patch: 3:", "- **patch**: 3:")
    hp = write("impl/spec-9-5-hyphen.md", hy)
    s = read_spec(hp)
    check("spec hyphen heading: parsed", s["last_review_pass"]["date"] == "2026-08-13" and s["last_review_pass"]["patch"] == 3)

    # ---- --find-spec ----------------------------------------------------- #
    impl = os.path.join(root, "impl")
    fs_sp = write("fs-sprint.yaml", "development_status:\n  epic-1: in-progress\n  1-3-plant-data-model: backlog\n  1-30-plant-export: backlog\n  2-6a-digest-delivery: backlog\n")

    def touch(rel, status, mtime):
        p = write(rel, f"---\ntitle: 't'\nstatus: '{status}'\n---\n\nbody\n")
        os.utime(p, (mtime, mtime))
        return p

    t0 = time.time() - 1000
    # single candidate
    a = touch("fs/spec-1-3-plant-data-model.md", "ready-for-dev", t0)
    fs_dir = os.path.join(root, "fs")
    r, code = build_find_spec_result(fs_dir, "1-3-plant-data-model", fs_sp)
    check("find: single", code == 0 and r["found"] is True and r["spec_path"] == a and r["status"] == "ready-for-dev" and r["ambiguous"] is False)
    # 1-30 spec must not leak into 1-3 (and vice versa)
    b = touch("fs/spec-1-30-plant-export.md", "ready-for-dev", t0)
    r, _ = build_find_spec_result(fs_dir, "1-3-plant-data-model", fs_sp)
    check("find: 1-3 vs 1-30 separated", r["spec_path"] == a and len(r["candidates"]) == 1)
    r, _ = build_find_spec_result(fs_dir, "1-30-plant-export", fs_sp)
    check("find: 1-30 own spec", r["spec_path"] == b)
    # -2 collision sibling: newest mtime wins, sibling listed
    a2 = touch("fs/spec-1-3-plant-data-model-2.md", "draft", t0 + 10)
    r, code = build_find_spec_result(fs_dir, "1-3-plant-data-model", fs_sp)
    check("find: -2 sibling newest wins", code == 0 and r["spec_path"] == a2 and r["siblings"] == [a] and r["found"] is True)
    # done dropped when a non-done remains
    touch("fs/spec-1-3-plant-data-model.md", "done", t0)
    r, _ = build_find_spec_result(fs_dir, "1-3-plant-data-model", fs_sp)
    check("find: done dropped, draft chosen", r["spec_path"] == a2 and r["siblings"] == [] and r["status"] == "draft")
    # done-only ⇒ found (the done spec) — the orchestrator routes by status
    os.unlink(a2)
    r, _ = build_find_spec_result(fs_dir, "1-3-plant-data-model", fs_sp)
    check("find: done-only ⇒ found with status done", r["found"] is True and r["status"] == "done" and r["spec_path"] == a)
    # blocked + redo (different stem) ⇒ blocked dropped, redo chosen
    os.unlink(a)
    bl = touch("fs/spec-1-3-plant-model.md", "blocked", t0)
    redo = touch("fs/spec-1-3-plant-data-model-redo.md", "draft", t0 + 5)
    r, code = build_find_spec_result(fs_dir, "1-3-plant-data-model", fs_sp)
    check("find: blocked dropped when a non-blocked remains", code == 0 and r["spec_path"] == redo)
    # blocked-only ⇒ found (blocked)
    os.unlink(redo)
    r, code = build_find_spec_result(fs_dir, "1-3-plant-data-model", fs_sp)
    check("find: blocked-only ⇒ found blocked", r["found"] is True and r["status"] == "blocked")
    # two live specs with different stems ⇒ ambiguous hard-stop exit 1
    x1 = touch("fs/spec-1-3-plant-data-model.md", "ready-for-dev", t0)
    x2 = touch("fs/spec-1-3-plant-model.md", "ready-for-dev", t0)
    r, code = build_find_spec_result(fs_dir, "1-3-plant-data-model", fs_sp)
    check("find: different stems ⇒ ambiguous exit 1", code == 1 and r["ambiguous"] is True and r["hard_stop"] is True and r["found"] is False and len(r["candidates"]) == 2)
    check("find: hard_stop_reason lists both", x1 in r["hard_stop_reason"] and x2 in r["hard_stop_reason"])
    # suffix key
    c = touch("fs/spec-2-6a-digest-delivery.md", "ready-for-dev", t0)
    touch("fs/spec-2-6-digest.md", "ready-for-dev", t0)
    r, code = build_find_spec_result(fs_dir, "2-6a-digest-delivery", fs_sp)
    check("find: suffix key matches only its own", code == 0 and r["spec_path"] == c and len(r["candidates"]) == 1)
    # none / missing dir / bad key
    r, code = build_find_spec_result(fs_dir, "3-1-nothing")
    check("find: none ⇒ found false, no hard-stop", code == 0 and r["found"] is False and r["hard_stop"] is False and r["candidates"] == [])
    r, code = build_find_spec_result(os.path.join(root, "no-impl"), "3-1-nothing")
    check("find: missing dir ⇒ found false + error", code == 0 and r["found"] is False and bool(r["error"]))
    r, code = build_find_spec_result(fs_dir, "bogus")
    check("find: bad key ⇒ hard_stop exit 1", code == 1 and r["hard_stop"] is True)
    # without --sprint-status the reader still works
    r, code = build_find_spec_result(fs_dir, "2-6a-digest-delivery")
    check("find: no sprint file ok", code == 0 and r["spec_path"] == c)
    check("find: no warnings on clean candidates", r["warnings"] == [])
    # A non-UTF-8 candidate is kept with status null + a warning; a readable sibling still wins.
    bad_c = os.path.join(fs_dir, "spec-5-1-bad.md")
    with open(bad_c, "wb") as fh:
        fh.write(b"---\nstatus: draft\n---\n\xff\n")
    r, code = build_find_spec_result(fs_dir, "5-1-bad")
    check("find: unreadable single candidate ⇒ found, status null, warning", code == 0 and r["found"] is True and r["status"] is None and r["candidates"][0]["status"] is None and any("could not read" in w for w in r["warnings"]))
    if getattr(os, "geteuid", lambda: 0)() != 0:
        unread = touch("fs/spec-5-2-unread.md", "ready-for-dev", t0)
        os.chmod(unread, 0)
        try:
            r, code = build_find_spec_result(fs_dir, "5-2-unread")
        finally:
            os.chmod(unread, stat.S_IRUSR | stat.S_IWUSR)
        check("find: permission-denied candidate ⇒ status null + warning, no crash", code == 0 and r["found"] is True and r["status"] is None and r["warnings"])

    # ---- --retro-verdict --------------------------------------------------- #
    rdir = os.path.join(root, "retro")
    r, code = build_retro_verdict_result(rdir, "1")
    check("retro: missing dir ⇒ not found", code == 0 and r["found"] is False)
    os.makedirs(rdir)
    r, code = build_retro_verdict_result(rdir, "1")
    check("retro: none ⇒ found false", code == 0 and r["found"] is False and r["verdict"] is None)
    old = write("retro/epic-1-retro-2026-08-01.md", "---\nepic: 1\ndate: 2026-08-01\nverdict: accepted\ncriteria: declared\nheadless: false\n---\n# Retro\n")
    new = write("retro/epic-1-retro-2026-08-14.md", "---\nepic: 1\ndate: '2026-08-14'\nverdict: rejected\ncriteria: profiled\nheadless: true\n---\n# Retro\n")
    os.utime(old, (t0, t0))
    os.utime(new, (t0 + 100, t0 + 100))
    write("retro/epic-10-retro-2026-08-14.md", "---\nepic: 10\nverdict: accepted\n---\n")
    r, code = build_retro_verdict_result(rdir, "1")
    check("retro: newest by mtime, epic-10 not confused", code == 0 and r["doc"] == new and r["verdict"] == "rejected" and r["found"] is True)
    check("retro: date/headless", r["date"] == "2026-08-14" and r["headless"] is True and r["epic"] == 1)
    os.utime(old, (t0 + 200, t0 + 200))
    r, _ = build_retro_verdict_result(rdir, "epic-1")
    check("retro: mtime flip picks the other doc; epic-N arg", r["doc"] == old and r["verdict"] == "accepted" and r["headless"] is False)
    bad = write("retro/epic-2-retro-x.md", "---\nepic: 2\nverdict: approved\n---\n")
    r, _ = build_retro_verdict_result(rdir, "2")
    check("retro: bad verdict ⇒ null + warning", r["verdict"] is None and r["warnings"] and r["found"] is True)
    r, code = build_retro_verdict_result(rdir, "nope")
    check("retro: bad epic arg ⇒ exit 2", code == 2)
    bad_r = os.path.join(rdir, "epic-3-retro-x.md")
    with open(bad_r, "wb") as fh:
        fh.write(b"---\nverdict: accepted\n---\n\xff\n")
    r, code = build_retro_verdict_result(rdir, "3")
    check("retro: non-UTF-8 doc ⇒ error exit 1, found true, verdict null", code == 1 and "UTF-8" in r["error"] and r["found"] is True and r["verdict"] is None)

    # ---- CLI guards -------------------------------------------------------- #
    def _main(argv):
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                code = main(argv)
        except SystemExit as exc:
            return exc.code, out.getvalue()
        return code, out.getvalue()

    code, out = _main(["--resolve", "1-2", "--sprint-status", sp])
    check("cli: resolve ok json", code == 0 and json.loads(out)["story_key"] == "1-2-account-management")
    code, out = _main(["--resolve", "9-9", "--sprint-status", sp])
    check("cli: resolve not found exit 1", code == 1 and json.loads(out)["hard_stop"] is True)
    code, out = _main(["--epic", "1", "--sprint-status", sp, "--planning-dir", plan])
    check("cli: epic ok", code == 0 and json.loads(out)["epic_title"] == "Plant Care Core")
    code, _ = _main(["--resolve", "1-2"])
    check("cli: resolve requires --sprint-status", code == 2)
    code, _ = _main(["--mark-status", "1-2-account-management", "--sprint-status", sp])
    check("cli: mark-status requires --to", code == 2)
    code, _ = _main(["--resolve", "1-2", "--sprint-status", sp, "--to", "done"])
    check("cli: --to only with --mark-status", code == 2)
    code, _ = _main(["--resolve", "1-2", "--sprint-status", sp, "--allow-regress"])
    check("cli: --allow-regress only with --mark-status", code == 2)
    code, _ = _main(["--resolve", "1-2", "--epic", "1", "--sprint-status", sp])
    check("cli: two modes rejected", code == 2)
    code, _ = _main(["--sprint-status", sp])
    check("cli: no mode rejected", code == 2)
    code, _ = _main(["--find-spec", "--story-key", "1-3-x"])
    check("cli: find-spec requires --impl-dir", code == 2)
    code, _ = _main(["--find-spec", "--impl-dir", fs_dir])
    check("cli: find-spec requires --story-key", code == 2)
    code, out = _main(["--find-spec", "--impl-dir", fs_dir, "--story-key", "2-6a-digest-delivery", "--sprint-status", fs_sp])
    check("cli: find-spec ok", code == 0 and json.loads(out)["found"] is True)
    code, out = _main(["--find-spec", "--impl-dir", fs_dir, "--story-key", "1-3-plant-data-model"])
    check("cli: find-spec ambiguous exit 1", code == 1 and json.loads(out)["ambiguous"] is True)
    code, out = _main(["--spec", spec_p])
    check("cli: spec ok", code == 0 and json.loads(out)["status"] == "done")
    code, out = _main(["--spec", os.path.join(root, "nope.md")])
    check("cli: spec missing exit 1", code == 1 and json.loads(out)["exists"] is False)
    code, out = _main(["--spec", bad_spec])
    check("cli: spec unreadable exit 1 + json", code == 1 and json.loads(out)["exists"] is True and json.loads(out)["error"])
    code, out = _main(["--resolve", "1-1", "--sprint-status", bad_sp])
    check("cli: unreadable sprint ⇒ json exit 1", code == 1 and json.loads(out)["hard_stop"] is True)
    code, out = _main(["--epic", "1", "--sprint-status", bad_sp])
    check("cli: epic on unreadable sprint ⇒ json exit 1",
          code == 1 and json.loads(out)["hard_stop"] is True and "UTF-8" in json.loads(out)["error"])
    code, out = _main(["--epic", "9", "--sprint-status", sp])
    check("cli: epic verdict (no stories) stays exit 0",
          code == 0 and json.loads(out)["hard_stop"] is True)
    code, out = _main(["--mark-status", "1-1-foo", "--to", "done", "--sprint-status", bad_sp])
    check("cli: mark-status on unreadable sprint ⇒ json exit 1",
          code == 1 and "UTF-8" in json.loads(out)["error"])
    code, out = _main(["--retro-verdict", "--impl-dir", rdir, "--epic", "3"])
    check("cli: unreadable retro doc ⇒ json exit 1", code == 1 and json.loads(out)["error"])
    code, _ = _main(["--retro-verdict", "--impl-dir", rdir])
    check("cli: retro-verdict requires --epic", code == 2)
    code, out = _main(["--retro-verdict", "--impl-dir", rdir, "--epic", "1"])
    check("cli: retro-verdict ok", code == 0 and json.loads(out)["found"] is True)
    code, _ = _main(["--retro-verdict", "--epic", "1"])
    check("cli: retro-verdict requires --impl-dir", code == 2)
    code, _ = _main(["--spec", spec_p, "--planning-dir", plan])
    check("cli: --planning-dir only with resolve/epic", code == 2)
    ms = fresh(mark_fixture, "cli-ms.yaml")
    code, out = _main(["--mark-status", "1-2-account-management", "--to", "done", "--sprint-status", ms])
    check("cli: mark-status ok", code == 0 and json.loads(out)["sprint_updated"] is True)
    code, out = _main(["--mark-status", "1-2-account-management", "--to", "backlog", "--sprint-status", ms])
    check("cli: mark-status regress exit 1", code == 1 and "refusing to regress" in json.loads(out)["error"])
    code, out = _main(["--mark-status", "1-2-account-management", "--to", "backlog", "--sprint-status", ms, "--allow-regress"])
    check("cli: mark-status --allow-regress", code == 0 and json.loads(out)["sprint_updated"] is True)

    shutil.rmtree(root, ignore_errors=True)

    if failures:
        print("SELF-TEST FAILED:", ", ".join(failures), file=sys.stderr)
        return 1
    print("SELF-TEST PASSED (all assertions)")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv=None):
    parser = argparse.ArgumentParser(description="auto-bmad story-source adapter (sprint-status / build-auto spec reader + status flip)")
    parser.add_argument("--resolve", metavar="REF", help="resolve an explicit story reference (E-S, E.S, E-Sx, full key, or slug fragment)")
    parser.add_argument("--epic", metavar="N", help="enumerate epic N (N or epic-N); with --retro-verdict: the epic number to read")
    parser.add_argument("--mark-status", metavar="KEY", help="flip KEY's development_status entry to --to STATUS")
    parser.add_argument("--to", metavar="STATUS", help="with --mark-status: target status (backlog|ready-for-dev|in-progress|review|done)")
    parser.add_argument("--allow-regress", action="store_true", help="with --mark-status: allow a lower-ranked target status")
    parser.add_argument("--find-spec", action="store_true", help="locate the story's bmad-build-auto spec (needs --impl-dir + --story-key)")
    parser.add_argument("--spec", metavar="PATH", help="read a bmad-build-auto spec (frontmatter + Auto Run Result + last review pass)")
    parser.add_argument("--retro-verdict", action="store_true", help="read the newest epic-N-retro-*.md verdict (needs --impl-dir + --epic)")
    parser.add_argument("--sprint-status", metavar="PATH", help="path to sprint-status.yaml")
    parser.add_argument("--planning-dir", metavar="DIR", help="with --resolve/--epic: planning_artifacts dir (story/epic titles from the epics docs)")
    parser.add_argument("--impl-dir", metavar="DIR", help="with --find-spec/--retro-verdict: implementation_artifacts dir")
    parser.add_argument("--story-key", metavar="KEY", help="with --find-spec: the sprint-status story key")
    parser.add_argument("--self-test", action="store_true", help="run built-in fixtures and exit")
    args = parser.parse_args(argv)

    if args.self_test:
        return _run_self_test()

    modes = []
    if args.resolve is not None:
        modes.append("resolve")
    if args.mark_status is not None:
        modes.append("mark-status")
    if args.find_spec:
        modes.append("find-spec")
    if args.spec is not None:
        modes.append("spec")
    if args.retro_verdict:
        modes.append("retro-verdict")
    if args.epic is not None and not args.retro_verdict:
        modes.append("epic")
    if len(modes) != 1:
        parser.error("exactly one mode is required: --resolve | --epic | --mark-status | --find-spec | --spec | --retro-verdict | --self-test")
    mode = modes[0]

    if args.to is not None and mode != "mark-status":
        parser.error("--to is only valid with --mark-status")
    if args.allow_regress and mode != "mark-status":
        parser.error("--allow-regress is only valid with --mark-status")
    if args.planning_dir is not None and mode not in ("resolve", "epic"):
        parser.error("--planning-dir is only valid with --resolve/--epic")
    if args.impl_dir is not None and mode not in ("find-spec", "retro-verdict"):
        parser.error("--impl-dir is only valid with --find-spec/--retro-verdict")
    if args.story_key is not None and mode != "find-spec":
        parser.error("--story-key is only valid with --find-spec")
    if args.sprint_status is not None and mode in ("spec", "retro-verdict"):
        parser.error("--sprint-status is not valid with --spec/--retro-verdict")

    def emit(result, code=0):
        print(json.dumps(result, indent=2))
        return code

    if mode == "resolve":
        if not args.sprint_status:
            parser.error("--resolve requires --sprint-status")
        return emit(*build_resolve_result(args.sprint_status, args.resolve, args.planning_dir))
    if mode == "epic":
        if not args.sprint_status:
            parser.error("--epic requires --sprint-status")
        epic_result = build_epic_result(args.sprint_status, args.epic, args.planning_dir)
        # Every verdict (unknown epic, no stories, epic already done) is exit 0
        # — the verdict is in the JSON. An UNREADABLE sprint file is not a
        # verdict but an I/O failure: exit 1, like every other mode.
        return emit(epic_result, 1 if epic_result["hard_stop_reason"] == UNREADABLE_SPRINT_REASON else 0)
    if mode == "mark-status":
        if not args.sprint_status:
            parser.error("--mark-status requires --sprint-status")
        if not args.to:
            parser.error("--mark-status requires --to STATUS")
        return emit(*mark_status(args.sprint_status, args.mark_status, args.to, args.allow_regress))
    if mode == "find-spec":
        if not args.impl_dir or not args.story_key:
            parser.error("--find-spec requires --impl-dir DIR and --story-key KEY")
        return emit(*build_find_spec_result(args.impl_dir, args.story_key, args.sprint_status))
    if mode == "spec":
        result = read_spec(args.spec)
        return emit(result, 0 if result["exists"] and not result["error"] else 1)
    if mode == "retro-verdict":
        if not args.impl_dir or args.epic is None:
            parser.error("--retro-verdict requires --impl-dir DIR and --epic N")
        return emit(*build_retro_verdict_result(args.impl_dir, args.epic))
    parser.error("no mode selected")  # unreachable
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
