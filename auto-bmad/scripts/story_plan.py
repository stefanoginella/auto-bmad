#!/usr/bin/env python3
"""Deterministic sprint-status reader for the auto-bmad orchestrator.

Parses a BMAD ``sprint-status.yaml`` and decides which story the pipeline should
work next (or inspects a story passed explicitly), including the epic-boundary
facts the orchestrator needs (first/last story of an epic, retrospective state).

Output is a single JSON object on stdout so the orchestrator never has to parse
YAML with an LLM. Dependency-free: the ``development_status`` block is a flat
``key: value`` map, so we read it line by line and preserve file order.

A second mode, ``--mark-status KEY --to STATUS`` (with ``--mark-done KEY`` kept
as an alias for ``--to done``), scripts a BMAD-status flip — Phase 5 write-back
to ``review`` and the Phase 9 flip to ``done`` (``pipeline.md``): it rewrites
KEY's ``development_status`` value to STATUS as a line-level edit — leading
whitespace, the key, and any inline ``#`` comment are preserved, every other
line byte-identical — and, with ``--story-file``, also flips the story file's
status line (``Status: x`` / ``**Status:** x`` / ``status: x``, key
case-insensitive, first match wins, only the value replaced). STATUS must be one
of ``backlog|ready-for-dev|in-progress|review|done``. Idempotent: a target
already at STATUS is not rewritten (``already_at_status`` true when nothing
needed writing, and ``already_done`` when that status is ``done``). Lookup
validation happens before any write; the write phase then renders both new
contents, stages each as a temp file in its target's directory, and commits
with back-to-back atomic ``os.replace`` calls — so a staging failure (e.g. an
unwritable directory) reports a JSON ``error`` (exit 1) with NEITHER file
changed, and no write can ever truncate a target. The only divergence window
left is the instant between the two replaces; the ``sprint_updated`` /
``story_file_updated`` flags always report exactly what was committed.
Exit 0 on success/no-op; 1 when the key or the Status line can't be found or
a write fails; 2 on usage errors.

A third mode, ``--epic N`` (N or ``epic-N``), enumerates every story in epic N
ordered by story number, each with its status, story-file path, and next BMAD
action — the reader the auto-bmad *epic* pipeline loops over. Like the default
reader it never writes and returns a single JSON object (exit 0); ``hard_stop``
is set when the epic is unknown/empty or already ``done``.

Usage:
    story_plan.py --sprint-status PATH [--story 1-3|1-3-slug] [--impl-dir DIR]
    story_plan.py --epic N --sprint-status PATH [--impl-dir DIR]
    story_plan.py --mark-status KEY --to STATUS --sprint-status PATH [--story-file PATH]
    story_plan.py --mark-done KEY --sprint-status PATH [--story-file PATH]
    story_plan.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile

EPIC_RE = re.compile(r"^epic-(\d+)$")
RETRO_RE = re.compile(r"^epic-(\d+)-retrospective$")
STORY_RE = re.compile(r"^(\d+)-(\d+)-(.+)$")

# Legacy status aliases BMAD still honours.
STATUS_ALIASES = {"drafted": "ready-for-dev", "contexted": "in-progress"}

# Story status -> the BMAD action that advances it.
ACTION_FOR_STATUS = {
    "backlog": "create-story",
    "ready-for-dev": "dev-story",
    "in-progress": "dev-story",
    "review": "code-review",
    "done": "done",
}


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
        # Inside the block.
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
        key, value = m.group(1).strip(), m.group(2).strip()
        if not value:
            continue
        entries.append((key, STATUS_ALIASES.get(value, value)))
    return entries


def classify(entries):
    epics, stories, retros = {}, [], {}
    for key, status in entries:
        em = EPIC_RE.match(key)
        rm = RETRO_RE.match(key)
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
                    "slug": sm.group(3),
                    "status": status,
                }
            )
    return epics, stories, retros


def pick_next(stories, retros):
    """Mirror BMAD sprint-status next-action precedence. Stories are in file order."""
    for want in ("in-progress", "review", "ready-for-dev", "backlog"):
        for s in stories:
            if s["status"] == want:
                return s, ACTION_FOR_STATUS[want]
    # All stories done -> first optional retrospective.
    for epic_num in sorted(retros):
        if retros[epic_num] == "optional":
            return None, "retrospective"
    return None, "done"


def match_explicit(stories, story_arg):
    m = re.match(r"^(\d+)-(\d+)(?:-(.+))?$", story_arg.strip())
    if not m:
        return None, f"could not parse --story '{story_arg}' (expected N-N or N-N-slug)"
    epic_num, story_num = int(m.group(1)), int(m.group(2))
    for s in stories:
        if s["epic_num"] == epic_num and s["story_num"] == story_num:
            return s, None
    return None, f"story {epic_num}-{story_num} not found in sprint-status"


def build_result(sprint_status_path, story_arg, impl_dir):
    result = {
        "story_key": None,
        "epic_num": None,
        "story_num": None,
        "story_file": None,
        "current_status": None,
        "epic_status": None,
        "epic_story_count": None,
        "is_first_in_epic": None,
        "is_last_in_epic": None,
        "stories_after_in_epic": None,
        "retrospective_status": None,
        "next_action": None,
        "hard_stop": False,
        "hard_stop_reason": None,
        "error": None,
    }

    if not os.path.isfile(sprint_status_path):
        result["error"] = f"sprint-status file not found: {sprint_status_path}"
        result["hard_stop"] = True
        result["hard_stop_reason"] = "no sprint-status.yaml; run /bmad-sprint-planning first"
        return result

    with open(sprint_status_path, "r", encoding="utf-8") as fh:
        text = fh.read()

    entries = parse_development_status(text)
    if not entries:
        result["error"] = "no development_status entries found"
        result["hard_stop"] = True
        result["hard_stop_reason"] = "empty/invalid sprint-status; run /bmad-sprint-planning"
        return result

    epics, stories, retros = classify(entries)

    if story_arg:
        target, err = match_explicit(stories, story_arg)
        if target is None:
            result["error"] = err
            result["hard_stop"] = True
            result["hard_stop_reason"] = err
            return result
        next_action = ACTION_FOR_STATUS.get(target["status"], "dev-story")
    else:
        target, next_action = pick_next(stories, retros)
        if target is None:
            result["next_action"] = next_action  # retrospective or done
            if next_action == "done":
                result["hard_stop"] = True
                result["hard_stop_reason"] = "all stories and retrospectives complete"
            return result

    epic_num = target["epic_num"]
    same_epic = [s for s in stories if s["epic_num"] == epic_num]
    min_story = min(s["story_num"] for s in same_epic)
    max_story = max(s["story_num"] for s in same_epic)

    result.update(
        {
            "story_key": target["key"],
            "epic_num": epic_num,
            "story_num": target["story_num"],
            "story_file": os.path.join(impl_dir, target["key"] + ".md") if impl_dir else target["key"] + ".md",
            "current_status": target["status"],
            "epic_status": epics.get(epic_num),
            "epic_story_count": len(same_epic),
            "is_first_in_epic": target["story_num"] == min_story,
            "is_last_in_epic": target["story_num"] == max_story,
            # Stories in this epic ordered after the target (higher story_num). 0 for the last
            # story, 1 for second-to-last, etc. — drives the trace-advisory "skip the last N
            # stories" distance gate (see tea-policy.md §3), which subsumes is_last_in_epic.
            "stories_after_in_epic": sum(1 for s in same_epic if s["story_num"] > target["story_num"]),
            "retrospective_status": retros.get(epic_num),
            "next_action": next_action,
        }
    )

    if result["epic_status"] == "done" and next_action == "create-story":
        result["hard_stop"] = True
        result["hard_stop_reason"] = f"epic {epic_num} is marked done; cannot create new story"

    return result


# --------------------------------------------------------------------------- #
# --epic: enumerate every story in one epic (ordered), for the epic pipeline.
# --------------------------------------------------------------------------- #
def parse_epic_arg(epic_arg):
    """Parse an --epic argument (``N`` or ``epic-N``) -> int, or None if invalid."""
    m = re.match(r"^(?:epic-)?(\d+)$", str(epic_arg).strip())
    return int(m.group(1)) if m else None


def build_epic_result(sprint_status_path, epic_arg, impl_dir):
    """Enumerate every story in epic N ordered by story_num — the list the
    auto-bmad epic pipeline loops over. Each story carries its key, status,
    absolute story_file, and next BMAD action. ``hard_stop`` is set when the
    epic arg is unparseable, the epic is unknown/empty, or it is already
    ``done`` (nothing to complete). Never writes; exit 0 (verdict in JSON)."""
    result = {
        "epic_num": None,
        "epic_status": None,
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

    if not os.path.isfile(sprint_status_path):
        result["error"] = f"sprint-status file not found: {sprint_status_path}"
        result["hard_stop"] = True
        result["hard_stop_reason"] = "no sprint-status.yaml; run /bmad-sprint-planning first"
        return result

    with open(sprint_status_path, "r", encoding="utf-8") as fh:
        text = fh.read()

    entries = parse_development_status(text)
    if not entries:
        result["error"] = "no development_status entries found"
        result["hard_stop"] = True
        result["hard_stop_reason"] = "empty/invalid sprint-status; run /bmad-sprint-planning"
        return result

    epics, stories, retros = classify(entries)
    same_epic = sorted(
        (s for s in stories if s["epic_num"] == epic_num),
        key=lambda s: s["story_num"],
    )
    result["epic_status"] = epics.get(epic_num)
    result["retrospective_status"] = retros.get(epic_num)

    if not same_epic:
        result["hard_stop"] = True
        result["hard_stop_reason"] = f"epic {epic_num} has no stories in sprint-status"
        result["error"] = result["hard_stop_reason"]
        return result

    result["epic_story_count"] = len(same_epic)
    result["epic_stories"] = [
        {
            "key": s["key"],
            "story_num": s["story_num"],
            "status": s["status"],
            "story_file": os.path.join(impl_dir, s["key"] + ".md") if impl_dir else s["key"] + ".md",
            "next_action": ACTION_FOR_STATUS.get(s["status"], "dev-story"),
        }
        for s in same_epic
    ]

    if result["epic_status"] == "done":
        result["hard_stop"] = True
        result["hard_stop_reason"] = f"epic {epic_num} is marked done"

    return result


# --------------------------------------------------------------------------- #
# --mark-done: flip one development_status entry (and optionally the story
# file's Status line) to done — byte-preserving everywhere else.
# --------------------------------------------------------------------------- #
# The story file's status line: `Status: x`, `**Status:** x`, or `status: x`
# (key case-insensitive). Group 1 = everything through the value's start,
# group 2 = the value (trailing whitespace dropped on rewrite).
_STORY_STATUS_RE = re.compile(r"^(\s*(?:\*\*status:\*\*|status:)\s*)(.*?)\s*$", re.IGNORECASE)


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
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        # mkstemp creates 0600; carry the target's own mode so the replace
        # doesn't silently drop group/other bits from a user file.
        os.chmod(tmp, os.stat(path).st_mode & 0o7777)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return tmp


# BMAD development_status values the orchestrator may script. LLM-only write-backs
# (bmad-dev-story step 9) are the root cause of recurring ready-for-dev↔review drift.
# Derived from ACTION_FOR_STATUS (the canonical status vocabulary) so a new or
# renamed status can't drift the two lists apart.
_ALLOWED_MARK_STATUSES = frozenset(ACTION_FOR_STATUS)


def mark_status(sprint_status_path, key, status, story_file=None):
    """Flip KEY's sprint-status entry (and optionally the story file's Status
    line) to ``status``. Returns (result, exit_code).

    Lookup failures (exit 1) happen before any write; writes stage both temp
    files first and commit with back-to-back atomic ``os.replace`` calls, so a
    write failure (exit 1, JSON ``error``) leaves every uncommitted target
    byte-identical — only the instant between the two replaces can observe a
    half-flip, and the ``*_updated`` flags report exactly what was committed.

    Used by Phase 5 (→ ``review`` / ``in-progress``) and Phase 9 (→ ``done``)
    so sprint-status write-back is scripted, not LLM-instruction-only.
    """
    target = (status or "").strip().lower()
    result = {
        "key": key,
        "target_status": target,
        "previous_status": None,
        "sprint_updated": False,
        "story_previous_status": None,
        "story_file_updated": False,
        "already_at_status": False,
        "error": None,
    }
    # Backward-compat alias used by older Phase-9 callers / self-tests.
    result["already_done"] = False

    if target not in _ALLOWED_MARK_STATUSES:
        result["error"] = (
            f"invalid status '{status}' — allowed: {sorted(_ALLOWED_MARK_STATUSES)}"
        )
        return result, 1

    if not os.path.isfile(sprint_status_path):
        result["error"] = f"sprint-status file not found: {sprint_status_path}"
        return result, 1

    with open(sprint_status_path, "r", encoding="utf-8") as fh:
        sprint_lines = fh.read().splitlines(keepends=True)

    sprint_idx, sprint_m = _find_sprint_status_line(sprint_lines, key)
    if sprint_idx is None:
        result["error"] = f"key '{key}' not found in development_status of {sprint_status_path}"
        return result, 1
    result["previous_status"] = sprint_m.group(2)
    sprint_needs_write = sprint_m.group(2).strip().lower() != target

    story_lines = None
    story_idx = None
    story_m = None
    story_needs_write = False
    if story_file:
        if not os.path.isfile(story_file):
            result["error"] = f"story file not found: {story_file}"
            return result, 1
        with open(story_file, "r", encoding="utf-8") as fh:
            story_lines = fh.read().splitlines(keepends=True)
        for i, raw in enumerate(story_lines):
            m = _STORY_STATUS_RE.match(raw.rstrip("\r\n"))
            if m:
                story_idx, story_m = i, m
                break
        if story_idx is None:
            result["error"] = f"no Status line found in {story_file}"
            return result, 1
        result["story_previous_status"] = story_m.group(2)
        story_needs_write = story_m.group(2).strip().lower() != target

    # All targets validated — write only what actually changes (idempotent).
    # Stage BOTH new contents as temp files first (any I/O error here aborts
    # with neither file changed), then commit with back-to-back atomic
    # os.replace calls so a crash can never truncate either target.
    staged = []  # (temp_path, final_path, result flag) in commit order
    try:
        if sprint_needs_write:
            _rewrite_line(
                sprint_lines,
                sprint_idx,
                sprint_m.group(1) + target + (sprint_m.group(3) or ""),
            )
            staged.append((_stage_write(sprint_status_path, "".join(sprint_lines)), sprint_status_path, "sprint_updated"))
        if story_needs_write:
            _rewrite_line(story_lines, story_idx, story_m.group(1) + target)
            staged.append((_stage_write(story_file, "".join(story_lines)), story_file, "story_file_updated"))
        for tmp, final_path, flag in staged:
            os.replace(tmp, final_path)
            result[flag] = True
    except OSError as exc:
        for tmp, _final, flag in staged:
            if not result[flag] and os.path.exists(tmp):
                os.unlink(tmp)
        result["error"] = f"write failed: {exc} (the sprint_updated/story_file_updated flags report what was committed)"
        return result, 1

    already = not (result["sprint_updated"] or result["story_file_updated"])
    result["already_at_status"] = already
    result["already_done"] = already and target == "done"
    return result, 0


def mark_done(sprint_status_path, key, story_file=None):
    """Flip KEY to ``done`` — Phase 9 BMAD-status flip. Thin wrapper over
    ``mark_status`` kept for backward-compatible CLI / callers."""
    return mark_status(sprint_status_path, key, "done", story_file)


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
  epic-1-retrospective: optional

  epic-2: backlog
  2-1-personality-system: backlog
"""


def _run_self_test():
    import contextlib
    import io
    import stat

    failures = []

    def check(name, cond):
        if not cond:
            failures.append(name)

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(_FIXTURE)
        path = f.name

    # Auto: first in-progress wins? none in-progress -> first review = 1-2.
    auto = build_result(path, None, "/impl")
    check("auto picks review story 1-2", auto["story_key"] == "1-2-account-management")
    check("auto next_action code-review", auto["next_action"] == "code-review")
    check("1-2 not first in epic", auto["is_first_in_epic"] is False)
    check("1-2 not last in epic", auto["is_last_in_epic"] is False)
    check("epic-1 status in-progress", auto["epic_status"] == "in-progress")
    check("epic-1 story count is 3", auto["epic_story_count"] == 3)
    check("1-2 has 1 story after it", auto["stories_after_in_epic"] == 1)
    check("retro status optional", auto["retrospective_status"] == "optional")
    check("story_file joined", auto["story_file"] == "/impl/1-2-account-management.md")

    # Explicit backlog story -> create-story; is_last_in_epic for 1-3.
    ex = build_result(path, "1-3", "/impl")
    check("explicit 1-3 key", ex["story_key"] == "1-3-plant-data-model")
    check("explicit 1-3 create-story", ex["next_action"] == "create-story")
    check("1-3 is last in epic", ex["is_last_in_epic"] is True)
    check("1-3 not first in epic", ex["is_first_in_epic"] is False)
    check("1-3 has 0 stories after it (last)", ex["stories_after_in_epic"] == 0)

    # Explicit first story of epic 2.
    ex2 = build_result(path, "2-1-personality-system", "/impl")
    check("2-1 first in epic", ex2["is_first_in_epic"] is True)
    check("2-1 last in epic", ex2["is_last_in_epic"] is True)
    check("epic-2 story count is 1", ex2["epic_story_count"] == 1)
    check("2-1 has 0 stories after it", ex2["stories_after_in_epic"] == 0)

    # Missing file hard-stops.
    miss = build_result("/no/such/file.yaml", None, "/impl")
    check("missing file hard_stop", miss["hard_stop"] is True)

    # Unknown explicit story errors.
    bad = build_result(path, "9-9", "/impl")
    check("unknown story hard_stop", bad["hard_stop"] is True)

    # ---- --epic enumeration mode ------------------------------------------ #
    ep1 = build_epic_result(path, "1", "/impl")
    check("epic-1: epic_num 1", ep1["epic_num"] == 1)
    check("epic-1: status in-progress", ep1["epic_status"] == "in-progress")
    check("epic-1: story count 3", ep1["epic_story_count"] == 3)
    check("epic-1: not hard_stop", ep1["hard_stop"] is False)
    check("epic-1: retro optional", ep1["retrospective_status"] == "optional")
    check(
        "epic-1: ordered by story_num",
        [s["key"] for s in ep1["epic_stories"]]
        == ["1-1-user-authentication", "1-2-account-management", "1-3-plant-data-model"],
    )
    check("epic-1: first story done", ep1["epic_stories"][0]["status"] == "done")
    check("epic-1: done -> next_action done", ep1["epic_stories"][0]["next_action"] == "done")
    check(
        "epic-1: story_file joined",
        ep1["epic_stories"][0]["story_file"] == "/impl/1-1-user-authentication.md",
    )
    check("epic-1: review -> code-review", ep1["epic_stories"][1]["next_action"] == "code-review")
    check("epic-1: backlog -> create-story", ep1["epic_stories"][2]["next_action"] == "create-story")

    # The ``epic-N`` form parses too; epic 2 has a single backlog story.
    ep2 = build_epic_result(path, "epic-2", "/impl")
    check("epic-2: parsed epic-N form", ep2["epic_num"] == 2)
    check("epic-2: story count 1", ep2["epic_story_count"] == 1)
    check("epic-2: single story", [s["key"] for s in ep2["epic_stories"]] == ["2-1-personality-system"])

    # Unknown / unparseable epic -> hard_stop, no stories.
    ep_missing = build_epic_result(path, "9", "/impl")
    check("epic-9 empty hard_stop", ep_missing["hard_stop"] is True and ep_missing["epic_stories"] == [])
    ep_bad = build_epic_result(path, "nope", "/impl")
    check("epic bad-arg hard_stop", ep_bad["hard_stop"] is True)

    os.unlink(path)

    # A done epic hard-stops (nothing to complete) but still lists its stories.
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write("development_status:\n  epic-3: done\n  3-1-foo: done\n  3-2-bar: done\n")
        done_path = f.name
    dep = build_epic_result(done_path, "3", "/impl")
    check("epic-3 done hard_stop", dep["hard_stop"] is True)
    check("epic-3 done reason", "done" in (dep["hard_stop_reason"] or ""))
    check("epic-3 done still lists stories", len(dep["epic_stories"]) == 2)
    os.unlink(done_path)

    # ---- mark-done mode --------------------------------------------------- #
    mark_fixture = """\
generated: 05-06-2025 21:30
project: Demo

development_status:
  epic-1: in-progress
  1-1-user-authentication: done
  1-2-account-management: review  # awaiting final pass
  1-3-plant-data-model: backlog
  epic-1-retrospective: optional
"""
    tmp_paths = []

    def fresh(body, suffix):
        with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False) as f:
            f.write(body)
            tmp_paths.append(f.name)
            return f.name

    def slurp(p):
        with open(p, "r", encoding="utf-8") as fh:
            return fh.read()

    # Happy path: only the target line's value token changes; inline comment,
    # indentation, and every other line are byte-identical.
    sp = fresh(mark_fixture, ".yaml")
    res, code = mark_done(sp, "1-2-account-management")
    check("mark-done: exit 0", code == 0)
    check("mark-done: key echoed", res["key"] == "1-2-account-management")
    check("mark-done: previous_status review", res["previous_status"] == "review")
    check("mark-done: sprint_updated", res["sprint_updated"] is True)
    check("mark-done: story fields null/false without --story-file", res["story_previous_status"] is None and res["story_file_updated"] is False)
    check("mark-done: not already_done", res["already_done"] is False)
    expected = mark_fixture.replace(
        "  1-2-account-management: review  # awaiting final pass",
        "  1-2-account-management: done  # awaiting final pass",
    )
    check("mark-done: byte-preserving (value token only)", slurp(sp) == expected)

    # Idempotent: already done => no write, file byte-identical, exit 0.
    sp = fresh(mark_fixture, ".yaml")
    res, code = mark_done(sp, "1-1-user-authentication")
    check("mark-done already: exit 0", code == 0)
    check("mark-done already: already_done", res["already_done"] is True)
    check("mark-done already: sprint not updated", res["sprint_updated"] is False)
    check("mark-done already: previous_status done", res["previous_status"] == "done")
    check("mark-done already: file untouched", slurp(sp) == mark_fixture)

    # Missing key / missing sprint file => exit 1, nothing written.
    sp = fresh(mark_fixture, ".yaml")
    res, code = mark_done(sp, "9-9-nope")
    check("mark-done missing key: exit 1", code == 1)
    check("mark-done missing key: error set", bool(res["error"]))
    check("mark-done missing key: file untouched", slurp(sp) == mark_fixture)
    res, code = mark_done("/no/such/sprint.yaml", "1-1-user-authentication")
    check("mark-done missing sprint file: exit 1", code == 1)

    # Story-file variants: each form flips, value-only, first match wins
    # (the later Dev Notes 'Status: review' is untouched).
    story_tpl = "# Story 1-3\n\n{line}\n\n## Dev Notes\nStatus: review\n"
    for line, prev, flipped in (
        ("Status: review", "review", "Status: done"),
        ("**Status:** Review", "Review", "**Status:** done"),
        ("status: in-progress", "in-progress", "status: done"),
    ):
        sp = fresh(mark_fixture, ".yaml")
        st = fresh(story_tpl.format(line=line), ".md")
        res, code = mark_done(sp, "1-3-plant-data-model", st)
        check(f"mark-done story '{line}': exit 0", code == 0)
        check(f"mark-done story '{line}': story_previous_status", res["story_previous_status"] == prev)
        check(f"mark-done story '{line}': story_file_updated", res["story_file_updated"] is True)
        check(f"mark-done story '{line}': value-only flip, first match wins", slurp(st) == story_tpl.format(line=flipped))

    # No Status line => exit 1 AND the sprint file untouched (validate-before-write).
    sp = fresh(mark_fixture, ".yaml")
    st = fresh("# Story\n\nno status anywhere\n", ".md")
    res, code = mark_done(sp, "1-3-plant-data-model", st)
    check("mark-done no Status line: exit 1", code == 1)
    check("mark-done no Status line: error set", bool(res["error"]))
    check("mark-done no Status line: sprint untouched", slurp(sp) == mark_fixture)

    # Sprint already done but story file still review => story flips, not already_done.
    sp = fresh(mark_fixture, ".yaml")
    st = fresh("Status: review\n", ".md")
    res, code = mark_done(sp, "1-1-user-authentication", st)
    check("mark-done mixed: exit 0", code == 0)
    check("mark-done mixed: sprint not updated", res["sprint_updated"] is False)
    check("mark-done mixed: story updated", res["story_file_updated"] is True)
    check("mark-done mixed: not already_done", res["already_done"] is False)

    # Both already done (status value case-insensitive) => already_done, no writes.
    st = fresh("STATUS: Done\n", ".md")
    res, code = mark_done(sp, "1-1-user-authentication", st)
    check("mark-done both done: exit 0", code == 0)
    check("mark-done both done: already_done", res["already_done"] is True)
    check("mark-done both done: story untouched", slurp(st) == "STATUS: Done\n")

    # The atomic replace preserves the target's mode (mkstemp's temp is 0600;
    # without the chmod the flip would silently drop group/other bits).
    sp = fresh(mark_fixture, ".yaml")
    st = fresh("Status: review\n", ".md")
    wide = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH
    os.chmod(sp, wide)
    os.chmod(st, wide)
    res, code = mark_done(sp, "1-3-plant-data-model", st)
    check("mark-done modes: exit 0", code == 0)
    check("mark-done modes: sprint mode preserved", os.stat(sp).st_mode & 0o7777 == wide)
    check("mark-done modes: story mode preserved", os.stat(st).st_mode & 0o7777 == wide)

    # Write failure (story file in a read-only DIRECTORY — directory perms,
    # not file perms, gate the atomic-replace path): JSON error + exit 1, and
    # BOTH files stay byte-identical even though the sprint flip was staged
    # first (stage-both-then-swap), with no temp litter left in either dir.
    # Skipped as root, which ignores directory write bits.
    if getattr(os, "geteuid", lambda: 0)() != 0:
        wr_dir = tempfile.mkdtemp(prefix="story_plan_wr_")
        ro_dir = tempfile.mkdtemp(prefix="story_plan_ro_")
        sp = os.path.join(wr_dir, "sprint-status.yaml")
        with open(sp, "w", encoding="utf-8") as f:
            f.write(mark_fixture)
        st = os.path.join(ro_dir, "1-3-plant-data-model.md")
        with open(st, "w", encoding="utf-8") as f:
            f.write("Status: review\n")
        os.chmod(ro_dir, stat.S_IRUSR | stat.S_IXUSR)  # owner read+exec, no write
        try:
            res, code = mark_done(sp, "1-3-plant-data-model", st)
        finally:
            os.chmod(ro_dir, stat.S_IRWXU)  # restore owner-only rwx for cleanup
        check("mark-done ro-dir: exit 1", code == 1)
        check("mark-done ro-dir: error set", bool(res["error"]))
        check("mark-done ro-dir: nothing flagged committed", res["sprint_updated"] is False and res["story_file_updated"] is False)
        check("mark-done ro-dir: sprint untouched", slurp(sp) == mark_fixture)
        check("mark-done ro-dir: story untouched", slurp(st) == "Status: review\n")
        check("mark-done ro-dir: no temp litter (sprint dir)", os.listdir(wr_dir) == ["sprint-status.yaml"])
        check("mark-done ro-dir: no temp litter (story dir)", os.listdir(ro_dir) == ["1-3-plant-data-model.md"])
        for p in (sp, st):
            os.unlink(p)
        os.rmdir(wr_dir)
        os.rmdir(ro_dir)

    # ---- mark-status mode (generalized flip, non-done targets) ------------ #
    # A non-done target flips both sources; already_done stays False (not done).
    sp = fresh(mark_fixture, ".yaml")
    st = fresh("Status: done\n", ".md")
    res, code = mark_status(sp, "1-2-account-management", "in-progress", st)
    check("mark-status flip: exit 0", code == 0)
    check("mark-status flip: target echoed", res["target_status"] == "in-progress")
    check("mark-status flip: sprint flipped", res["sprint_updated"] is True)
    check("mark-status flip: story flipped", res["story_file_updated"] is True)
    check("mark-status flip: not already_at_status", res["already_at_status"] is False)
    check("mark-status flip: already_done stays False (non-done target)", res["already_done"] is False)
    check("mark-status flip: value-only sprint edit", slurp(sp) == mark_fixture.replace(
        "  1-2-account-management: review  # awaiting final pass",
        "  1-2-account-management: in-progress  # awaiting final pass",
    ))
    check("mark-status flip: value-only story edit", slurp(st) == "Status: in-progress\n")

    # Idempotent at a non-done status: no write, exit 0, already_at_status True
    # while already_done stays False.
    sp = fresh(mark_fixture, ".yaml")
    res, code = mark_status(sp, "1-2-account-management", "review")
    check("mark-status idempotent: exit 0", code == 0)
    check("mark-status idempotent: already_at_status", res["already_at_status"] is True)
    check("mark-status idempotent: already_done False (target review)", res["already_done"] is False)
    check("mark-status idempotent: sprint not updated", res["sprint_updated"] is False)
    check("mark-status idempotent: file untouched", slurp(sp) == mark_fixture)

    # Invalid target => exit 1, error names the bad status, sprint file untouched
    # (validate-before-write).
    sp = fresh(mark_fixture, ".yaml")
    res, code = mark_status(sp, "1-2-account-management", "shipped")
    check("mark-status invalid: exit 1", code == 1)
    check("mark-status invalid: error names bad status", "shipped" in (res["error"] or ""))
    check("mark-status invalid: sprint untouched", slurp(sp) == mark_fixture)

    # done via mark_status matches the mark_done wrapper: already_done tracks target.
    sp = fresh(mark_fixture, ".yaml")
    res, code = mark_status(sp, "1-1-user-authentication", "done")
    check("mark-status done: already_at_status", res["already_at_status"] is True)
    check("mark-status done: already_done True (target done)", res["already_done"] is True)

    # CLI guards (main-level): --to targets a status, so it is rejected everywhere
    # except --mark-status — closing the footgun where `--mark-done KEY --to review`
    # silently flipped to done. Bad combos exit 2 (argparse usage error).
    sp = fresh(mark_fixture, ".yaml")

    def _main_exit(argv):
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                return main(argv)
        except SystemExit as exc:  # parser.error -> exit 2
            return exc.code

    check("cli: --mark-done rejects --to", _main_exit(
        ["--sprint-status", sp, "--mark-done", "1-3-plant-data-model", "--to", "review"]) == 2)
    check("cli: --mark-done + --to leaves sprint untouched", slurp(sp) == mark_fixture)
    check("cli: --mark-done and --mark-status mutually exclusive", _main_exit(
        ["--sprint-status", sp, "--mark-done", "1-3-plant-data-model",
         "--mark-status", "1-3-plant-data-model", "--to", "review"]) == 2)
    check("cli: --mark-status requires --to", _main_exit(
        ["--sprint-status", sp, "--mark-status", "1-3-plant-data-model"]) == 2)
    check("cli: bare --to without a mark flag rejected", _main_exit(
        ["--sprint-status", sp, "--to", "review"]) == 2)

    for p in tmp_paths:
        os.unlink(p)

    if failures:
        print("SELF-TEST FAILED:", ", ".join(failures), file=sys.stderr)
        return 1
    print("SELF-TEST PASSED (all assertions)")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="auto-bmad sprint-status reader")
    parser.add_argument("--sprint-status", help="path to sprint-status.yaml")
    parser.add_argument("--story", help="explicit story id (N-N or N-N-slug)")
    parser.add_argument("--epic", metavar="N", help="enumerate all stories in epic N (N or epic-N), for the epic pipeline")
    parser.add_argument("--impl-dir", default="", help="implementation_artifacts dir (for absolute story_file)")
    parser.add_argument("--mark-done", metavar="KEY", help="flip KEY's development_status entry to done (Phase 9 BMAD-status flip)")
    parser.add_argument(
        "--mark-status",
        metavar="KEY",
        help="flip KEY's development_status entry to --to STATUS (Phase 5 review write-back; preferred over LLM-only sync)",
    )
    parser.add_argument(
        "--to",
        metavar="STATUS",
        help="with --mark-status: target status (backlog|ready-for-dev|in-progress|review|done)",
    )
    parser.add_argument("--story-file", help="with --mark-done/--mark-status: also flip this story file's Status line")
    parser.add_argument("--self-test", action="store_true", help="run built-in fixtures and exit")
    args = parser.parse_args(argv)

    if args.self_test:
        return _run_self_test()

    if not args.sprint_status:
        parser.error("--sprint-status is required (or use --self-test)")

    if args.epic is not None:
        if args.mark_done or args.mark_status or args.story or args.story_file:
            parser.error("--epic cannot be combined with --story/--mark-done/--mark-status/--story-file")
        result = build_epic_result(args.sprint_status, args.epic, args.impl_dir)
        print(json.dumps(result, indent=2))
        return 0

    if args.mark_done and args.mark_status:
        parser.error("--mark-done and --mark-status are mutually exclusive")

    if args.mark_status:
        if not args.to:
            parser.error("--mark-status requires --to STATUS")
        result, code = mark_status(args.sprint_status, args.mark_status, args.to, args.story_file)
        print(json.dumps(result, indent=2))
        return code

    # --to targets a status, which only --mark-status honours. Reject it before the
    # --mark-done branch so `--mark-done KEY --to review` can't silently flip to done
    # (that branch ignores --to) — error out instead of surprising the caller.
    if args.to:
        parser.error("--to is only valid with --mark-status")

    if args.mark_done:
        result, code = mark_done(args.sprint_status, args.mark_done, args.story_file)
        print(json.dumps(result, indent=2))
        return code
    if args.story_file:
        parser.error("--story-file is only valid with --mark-done or --mark-status")

    result = build_result(args.sprint_status, args.story, args.impl_dir)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
