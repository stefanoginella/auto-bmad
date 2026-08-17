#!/usr/bin/env python3
"""Deterministic auto-bmad state-file reader for the orchestrator.

Replaces the resume-detection shell the orchestrator used to improvise (raw
``for f in story-*.yaml`` glob loops, which both misname the files — state files
are ``{key}.yaml`` with no ``story-`` prefix — and abort under zsh/fish on an
unmatched glob). This script enumerates ``{state-dir}/*.yaml`` and reports which
auto-bmad pipelines are still in flight (``status != done``), so the orchestrator
calls a tool instead of writing shell.

Three modes, all emitting a single JSON object on stdout:

* **scan** (default): list every state file with its status, the in-flight ones
  (most-recently-updated first), and the resume ``target`` (the first in-flight
  story — finish in-flight work before starting anything new).
* **story** (``--story-key KEY``): check one exact ``{KEY}.yaml`` by path — never
  a glob — and report whether it exists and should be resumed (``status != done``).
* **finalize** (``--story-key KEY --finalize``): evaluate the Phase 9 draft
  predicate (``git-and-pr.md`` → "PR") from the story's state file. The four
  clauses: ``blockers`` non-empty; ``review_unverified`` true (build-auto's last
  review pass still recommended a follow-up review that was not run, or review
  was skipped); ``gate_decision`` is ``WAIVED``; ``ci_status`` in {failed,
  timeout} (case-insensitive, like the sibling clauses).
  ``ci_status`` comes from ``--ci-status`` when given (the live post-CI-wait
  value), else from the state file, else ``unknown`` — ``passed``/``none``/
  ``unknown`` do NOT fire clause 4 (``unknown`` means the wait never ran).
  Verdict: ``draft`` = any clause fired (then forced false by ``--no-pr-draft``,
  which changes ONLY ``draft``); ``clean_completion`` = no clause fired (never
  affected by ``--no-pr-draft``); ``flip_bmad_status`` = ``clean_completion``;
  ``reasons`` names each firing clause. Exit 0 = verdict delivered (draft or
  not), 1 = state file missing or unreadable (non-UTF-8 / I/O error — never a
  clean verdict derived from nothing), 2 = usage errors.

Every scan / epic-scan record and the story-mode result also carry the state's
top-level ``branch`` scalar (``null`` when absent) so the orchestrator can pass
``--expected-branch`` to the resume preflight without opening the state file.

All three modes accept ``--scope epic`` to operate on the **epic anchors** under
``<state-dir>/epic`` instead of the per-story files: ``--scope epic`` (scan) lists
the in-flight epic pipelines, each enriched with ``epic_num`` + ``active_story``
(the cursor) for the epic resume + the per-story "this story is owned by an
in-flight epic" guard; ``--scope epic --story-key epic-{e}`` resumes/finalizes one
epic anchor. The per-story scan ignores the ``epic/`` subdirectory (it lists only
``*.yaml`` files), so the two scopes never collide.

Dependency-free: state files are flat ``key: value`` YAML, so the few top-level
scalars we need (``status``, ``updated_at``, ``branch``) are read line by line —
the finalize mode additionally reads the ``blockers`` list (inline ``[]`` or
block items) and the ``review_unverified`` / ``gate_decision`` / ``ci_status``
scalars. In-flight ordering uses ``updated_at`` (ISO-8601, sorts
chronologically) with filesystem mtime as a tiebreaker.

Usage:
    state_plan.py --state-dir DIR
    state_plan.py --state-dir DIR --story-key 1-3-user-auth
    state_plan.py --state-dir DIR --story-key 1-3-user-auth --finalize \\
        [--ci-status passed|failed|timeout|none|unknown] [--no-pr-draft]
    state_plan.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

# Top-level scalar fields (no leading indentation), value optionally quoted and
# optionally trailed by a comment.
_SCALAR_RE = {
    "status": re.compile(r"^status:\s*(.*?)\s*(?:#.*)?$"),
    "updated_at": re.compile(r"^updated_at:\s*(.*?)\s*(?:#.*)?$"),
    "branch": re.compile(r"^branch:\s*(.*)$"),   # value may be quoted; comment-stripped quote-aware below
}


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def read_state_file(path: str):
    """Return {status, updated_at, branch} read from a flat state YAML (values may be None)."""
    fields: "dict[str, str | None]" = {"status": None, "updated_at": None, "branch": None}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.rstrip("\n")
                for name, pat in _SCALAR_RE.items():
                    if fields[name] is None:
                        m = pat.match(line)
                        if m:
                            val = _scalar_or_none(_strip_comment(m.group(1)))
                            fields[name] = val or None
                if all(v is not None for v in fields.values()):
                    break
    except (OSError, UnicodeDecodeError):
        pass  # unreadable / non-UTF-8 stray file: a record with null fields, never a traceback
    return fields


def _story_record(state_dir: str, filename: str):
    path = os.path.join(state_dir, filename)
    fields = read_state_file(path)
    status = fields["status"]
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0.0
    return {
        "story_key": filename[: -len(".yaml")],
        "status": status,
        "done": status == "done",
        "updated_at": fields["updated_at"],
        "branch": fields["branch"],
        "file": path,
        "_mtime": mtime,  # internal sort tiebreaker; stripped before output
    }


def _scan(state_dir: str):
    result = {
        "mode": "scan",
        "state_dir": state_dir,
        "state_dir_exists": os.path.isdir(state_dir),
        "stories": [],
        "in_flight": [],
        "in_flight_count": 0,
        "target": None,
        "target_status": None,
        "extra_in_flight": [],
        "resume": False,
    }
    if not result["state_dir_exists"]:
        return result

    records = []
    for name in os.listdir(state_dir):
        if name.endswith(".yaml") and os.path.isfile(os.path.join(state_dir, name)):
            records.append(_story_record(state_dir, name))

    # Most-recently-updated first: ISO updated_at (missing sorts last), mtime tiebreak.
    records.sort(key=lambda r: (r["updated_at"] or "", r["_mtime"]), reverse=True)

    in_flight = [r for r in records if not r["done"]]
    result["stories"] = [_public(r) for r in records]
    result["in_flight"] = [_public(r) for r in in_flight]
    result["in_flight_count"] = len(in_flight)
    if in_flight:
        result["target"] = in_flight[0]["story_key"]
        result["target_status"] = in_flight[0]["status"]
        result["extra_in_flight"] = [r["story_key"] for r in in_flight[1:]]
        result["resume"] = True
    return result


# --------------------------------------------------------------------------- #
# --scope epic: scan the epic anchors under <state-dir>/epic. A separate scan so
# the per-story _scan stays pure (it never sees the epic/ subdir — listdir keeps
# only *.yaml files). Enriches each record with epic_num + active_story (cursor).
# --------------------------------------------------------------------------- #
_EPIC_NUM_RE = re.compile(r"^epic_num:\s*(.*?)\s*(?:#.*)?$")
_ACTIVE_STORY_RE = re.compile(r"^active_story:\s*(.*?)\s*(?:#.*)?$")


def _read_epic_fields(path: str):
    """Read ``epic_num`` (int when numeric) and ``active_story`` (the loop cursor)
    from an epic anchor — the two fields the per-story reader doesn't track."""
    epic_num = None
    active_story = None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.rstrip("\n")
                if epic_num is None:
                    m = _EPIC_NUM_RE.match(line)
                    if m:
                        v = _scalar_or_none(m.group(1))
                        epic_num = int(v) if (v and v.isdigit()) else v
                if active_story is None:
                    m = _ACTIVE_STORY_RE.match(line)
                    if m:
                        active_story = _scalar_or_none(m.group(1))
                if epic_num is not None and active_story is not None:
                    break
    except (OSError, UnicodeDecodeError):
        pass  # unreadable / non-UTF-8 anchor: null cursor fields, never a traceback
    return epic_num, active_story


def _scan_epics(epic_dir: str):
    """Scan the epic anchors under ``epic_dir`` (``<state-dir>/epic``): mirror
    ``_scan`` but enrich each record with ``epic_num`` + ``active_story`` and pick
    the most-recently-updated in-flight epic as the resume ``target``."""
    result = {
        "mode": "epic-scan",
        "state_dir": epic_dir,
        "state_dir_exists": os.path.isdir(epic_dir),
        "epics": [],
        "in_flight": [],
        "in_flight_count": 0,
        "target": None,
        "target_status": None,
        "target_epic_num": None,
        "target_active_story": None,
        "extra_in_flight": [],
        "resume": False,
    }
    if not result["state_dir_exists"]:
        return result

    records = []
    for name in os.listdir(epic_dir):
        if name.endswith(".yaml") and os.path.isfile(os.path.join(epic_dir, name)):
            rec = _story_record(epic_dir, name)
            epic_num, active_story = _read_epic_fields(os.path.join(epic_dir, name))
            rec["epic_key"] = rec["story_key"]
            rec["epic_num"] = epic_num
            rec["active_story"] = active_story
            records.append(rec)

    records.sort(key=lambda r: (r["updated_at"] or "", r["_mtime"]), reverse=True)

    in_flight = [r for r in records if not r["done"]]
    result["epics"] = [_public(r) for r in records]
    result["in_flight"] = [_public(r) for r in in_flight]
    result["in_flight_count"] = len(in_flight)
    if in_flight:
        t = in_flight[0]
        result["target"] = t["story_key"]
        result["target_status"] = t["status"]
        result["target_epic_num"] = t["epic_num"]
        result["target_active_story"] = t["active_story"]
        result["extra_in_flight"] = [r["story_key"] for r in in_flight[1:]]
        result["resume"] = True
    return result


def _story(state_dir: str, story_key: str):
    path = os.path.join(state_dir, story_key + ".yaml")
    exists = os.path.isfile(path)
    fields = read_state_file(path) if exists else {"status": None, "branch": None}
    status = fields["status"]
    return {
        "mode": "story",
        "state_dir": state_dir,
        "story_key": story_key,
        "file": path,
        "exists": exists,
        "status": status,
        "branch": fields["branch"],
        "resume": exists and status != "done",
    }


def _public(record):
    return {k: v for k, v in record.items() if not k.startswith("_")}


def build_result(state_dir: str, story_key=None):
    return _story(state_dir, story_key) if story_key else _scan(state_dir)


# --------------------------------------------------------------------------- #
# --finalize: the Phase 9 draft-predicate / clean-completion evaluator
# (git-and-pr.md -> "PR"; the four clauses are the normative definition).
# --------------------------------------------------------------------------- #
_FINALIZE_SCALAR_RE = {
    "review_unverified": re.compile(r"^review_unverified:\s*(.*?)\s*(?:#.*)?$"),
    "gate_decision": re.compile(r"^gate_decision:\s*(.*?)\s*(?:#.*)?$"),
    "ci_status": re.compile(r"^ci_status:\s*(.*?)\s*(?:#.*)?$"),
}
_BLOCKERS_RE = re.compile(r"^blockers:\s*(.*)$")
_LIST_ITEM_RE = re.compile(r"^\s*-\s+(.*)$")


def _strip_comment(value: str) -> str:
    """Drop a trailing ``# comment`` — but never a ``#`` inside a quoted string
    (the state writer double-quotes any value containing ``#``, so a bare ``#``
    is always a comment while a quoted one is payload)."""
    quote = None
    esc = False
    for i, c in enumerate(value):
        if esc:
            esc = False
        elif quote == '"' and c == "\\":
            esc = True
        elif quote:
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c == "#":
            return value[:i].strip()
    return value.strip()

# ci_status values that fire clause 4 (matched case-insensitively, like the
# sibling clauses). passed/none/unknown do NOT — `unknown` means the CI wait
# never ran (offer_merge off, or the run disabled the merge prompt).
_CI_FIRES = ("failed", "timeout")


def _scalar_or_none(value: str):
    value = _unquote(value)
    return None if value.lower() in ("", "null", "~") else value


def _split_flow(body: str) -> list:
    """Split flow-list elements on top-level commas, respecting quotes — the
    same rule as state_update.py's ``_split_flow`` (the writer's own parser;
    the self-test round-trips this reader against the writer's output)."""
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


def read_finalize_fields(path: str):
    """Read the draft-predicate inputs from a flat state YAML: the ``blockers``
    list (inline ``[...]`` or block ``- item`` form) plus the
    ``review_unverified`` / ``gate_decision`` / ``ci_status`` scalars."""
    fields = {"review_unverified": None, "gate_decision": None, "ci_status": None,
              "read_error": None}
    blockers: "list[str]" = []
    in_blockers = False
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        # Unreadable / non-UTF-8: the caller must NOT derive a clean verdict from
        # nothing (it would flip the story to done) — surface the error instead.
        fields["read_error"] = f"{type(exc).__name__}: {exc}"
        lines = []
    for line in lines:
        if in_blockers:
            m = _LIST_ITEM_RE.match(line)
            if m:
                item = _unquote(_strip_comment(m.group(1)))
                if item:
                    blockers.append(item)
                continue
            if not line.strip() or line.strip().startswith("#"):
                continue
            in_blockers = False  # block ended; fall through to this line
        bm = _BLOCKERS_RE.match(line)
        if bm:
            val = _strip_comment(bm.group(1))
            if val.startswith("["):
                # Quote-aware split: a comma INSIDE a quoted blocker is payload
                # ("rotate key, then redeploy" is ONE blocker), never a separator.
                inner = val[1:val.rfind("]")] if "]" in val else val[1:]
                blockers.extend(p for p in (_unquote(x) for x in _split_flow(inner)) if p)
            elif not val:
                in_blockers = True  # block-list form: items follow
            else:
                scalar = _scalar_or_none(val)
                if scalar is not None:
                    blockers.append(scalar)  # unexpected scalar; count it
            continue
        for name, pat in _FINALIZE_SCALAR_RE.items():
            if fields[name] is None:
                m = pat.match(line)
                if m:
                    fields[name] = _scalar_or_none(m.group(1))
    fields["blockers"] = blockers
    return fields


def build_finalize_result(state_dir: str, story_key: str, ci_status=None, no_pr_draft=False):
    """Evaluate the draft predicate for one story. Returns (result, exit_code):
    0 = verdict delivered (draft or not), 1 = state file missing or unreadable."""
    path = os.path.join(state_dir, story_key + ".yaml")
    result = {
        "mode": "finalize",
        "state_dir": state_dir,
        "story_key": story_key,
        "file": path,
        "blockers": [],
        "blocker_count": 0,
        "gate_decision": None,
        "ci_status": None,
        "ci_status_source": None,
        "no_pr_draft": bool(no_pr_draft),
        "clauses": {
            "blocker": False,
            "review_unverified": False,
            "gate_waived": False,
            "ci_failed_or_timeout": False,
        },
        "draft": False,
        "clean_completion": False,
        "flip_bmad_status": False,
        "reasons": [],
        "error": None,
    }
    if not os.path.isfile(path):
        result["error"] = f"state file not found: {path}"
        return result, 1

    fields = read_finalize_fields(path)
    if fields["read_error"]:
        result["error"] = f"state file unreadable: {path} ({fields['read_error']})"
        return result, 1
    blockers = fields["blockers"]
    gate = fields["gate_decision"]

    # Live --ci-status (post-CI-wait) wins; else the state file; else unknown.
    if ci_status:
        ci, ci_source = ci_status, "arg"
    elif fields["ci_status"]:
        ci, ci_source = fields["ci_status"], "state"
    else:
        ci, ci_source = "unknown", "default"

    clauses = {
        "blocker": len(blockers) > 0,
        "review_unverified": (fields["review_unverified"] or "").lower() == "true",
        "gate_waived": (gate or "").upper() == "WAIVED",
        "ci_failed_or_timeout": ci.lower() in _CI_FIRES,
    }
    any_clause = any(clauses.values())

    reasons = []
    if clauses["blocker"]:
        reasons.append(f"{len(blockers)} blocker(s) recorded")
    if clauses["review_unverified"]:
        reasons.append("review_unverified is true (build-auto's last review pass still recommended a follow-up review that was not run, or review was skipped)")
    if clauses["gate_waived"]:
        reasons.append("gate_decision is WAIVED (epic trace gate shipped despite coverage gaps)")
    if clauses["ci_failed_or_timeout"]:
        reasons.append(f"ci_status is '{ci}' (CI failed or timed out)")

    result.update(
        {
            "blockers": blockers,
            "blocker_count": len(blockers),
            "gate_decision": gate,
            "ci_status": ci,
            "ci_status_source": ci_source,
            "clauses": clauses,
            # --no-pr-draft forces ONLY draft to false: the PR
            # ships non-draft, but the completion is still caveated.
            "draft": any_clause and not no_pr_draft,
            "clean_completion": not any_clause,
            "flip_bmad_status": not any_clause,
            "reasons": reasons,
        }
    )
    return result, 0


# --------------------------------------------------------------------------- #
# Self-test
# --------------------------------------------------------------------------- #
def _run_self_test():
    import tempfile

    failures = []

    def check(name, cond):
        if not cond:
            failures.append(name)

    tmp = tempfile.mkdtemp(prefix="state_plan_")
    state_dir = os.path.join(tmp, "state")
    os.makedirs(state_dir)

    def write(name, body):
        with open(os.path.join(state_dir, name), "w", encoding="utf-8") as fh:
            fh.write(body)

    write("1-1-user-auth.yaml", 'story_key: 1-1-user-auth\nbranch: story/1-1-user-auth\nstatus: done\nupdated_at: "2026-05-20T08:00:00Z"\n')
    write("1-2-account-mgmt.yaml", 'story_key: 1-2-account-mgmt\nbranch: "story/1-2-account-mgmt"  # quoted\nstatus: in-progress  # mid-review\nupdated_at: "2026-05-22T10:00:00Z"\n')
    write("1-3-plant-model.yaml", "story_key: 1-3-plant-model\nstatus: in-progress\nupdated_at: '2026-05-23T09:00:00Z'\n")
    write("malformed.yaml", "story_key: malformed\n# no status line at all\n")
    write("notes.txt", "not a state file\n")

    scan = build_result(state_dir)
    check("scan: state_dir_exists", scan["state_dir_exists"] is True)
    check("scan: counts yaml only (4)", len(scan["stories"]) == 4)
    check("scan: in_flight excludes done", scan["in_flight_count"] == 3)
    check("scan: resume true", scan["resume"] is True)
    check("scan: target most-recent updated_at (1-3)", scan["target"] == "1-3-plant-model")
    check("scan: target_status carried", scan["target_status"] == "in-progress")
    check("scan: extras are the other in-flight", set(scan["extra_in_flight"]) == {"1-2-account-mgmt", "malformed"})
    check("scan: in_flight order most-recent-first", [s["story_key"] for s in scan["in_flight"]][:2] == ["1-3-plant-model", "1-2-account-mgmt"])
    check("scan: done story flagged done", any(s["done"] and s["story_key"] == "1-1-user-auth" for s in scan["stories"]))
    check("scan: inline comment stripped from status", any(s["story_key"] == "1-2-account-mgmt" and s["status"] == "in-progress" for s in scan["stories"]))
    check("scan: malformed has null status", any(s["story_key"] == "malformed" and s["status"] is None for s in scan["stories"]))
    check("scan: no internal mtime leaks to output", all(not any(k.startswith("_") for k in s) for s in scan["stories"]))
    check("scan: branch carried (quoted + comment stripped)", any(s["story_key"] == "1-2-account-mgmt" and s["branch"] == "story/1-2-account-mgmt" for s in scan["stories"]))
    check("scan: branch null when absent", any(s["story_key"] == "1-3-plant-model" and s["branch"] is None for s in scan["stories"]))
    check("scan: in_flight records carry branch", all("branch" in s for s in scan["in_flight"]))

    # A non-UTF-8 stray file in the state dir must not kill the scan (a record
    # with null fields, still one JSON object) — nor story mode on that key.
    with open(os.path.join(state_dir, "bad-bytes.yaml"), "wb") as fh:
        fh.write(b"story_key: bad-bytes\nstatus: in-progress\xff\xfe\n\xff\n")
    binscan = build_result(state_dir)
    json.dumps(binscan)  # must serialize
    check("scan: non-UTF-8 file yields a null-status record", any(s["story_key"] == "bad-bytes" and s["status"] is None and s["branch"] is None for s in binscan["stories"]))
    check("scan: non-UTF-8 file does not disturb the target", binscan["target"] == "1-3-plant-model")
    binstory = build_result(state_dir, "bad-bytes")
    check("story: non-UTF-8 file exists with null status", binstory["exists"] is True and binstory["status"] is None)
    os.unlink(os.path.join(state_dir, "bad-bytes.yaml"))

    # Story mode: exact-path lookup, no glob.
    done = build_result(state_dir, "1-1-user-auth")
    check("story: done exists", done["exists"] is True)
    check("story: done status", done["status"] == "done")
    check("story: done not resumed", done["resume"] is False)
    check("story: branch emitted", done["branch"] == "story/1-1-user-auth")

    live = build_result(state_dir, "1-2-account-mgmt")
    check("story: in-progress resumed", live["resume"] is True)
    check("story: in-progress status", live["status"] == "in-progress")
    check("story: quoted branch unquoted", live["branch"] == "story/1-2-account-mgmt")

    nobranch = build_result(state_dir, "1-3-plant-model")
    check("story: branch null when absent", nobranch["branch"] is None)

    missing = build_result(state_dir, "9-9-nope")
    check("story: missing not exists", missing["exists"] is False)
    check("story: missing status null", missing["status"] is None)
    check("story: missing branch null", missing["branch"] is None)
    check("story: missing not resumed", missing["resume"] is False)

    # Absent state dir (first run): empty, no resume, exit 0.
    empty = build_result(os.path.join(tmp, "does-not-exist"))
    check("scan: absent dir not exists", empty["state_dir_exists"] is False)
    check("scan: absent dir no resume", empty["resume"] is False)
    check("scan: absent dir zero in-flight", empty["in_flight_count"] == 0)

    # ---- --scope epic: epic-anchor scan over <state-dir>/epic -------------- #
    epic_dir = os.path.join(state_dir, "epic")
    os.makedirs(epic_dir)
    with open(os.path.join(epic_dir, "epic-1.yaml"), "w", encoding="utf-8") as fh:
        fh.write('story_key: epic-1\nepic_num: 1\nstatus: done\nactive_story: null\nupdated_at: "2026-05-20T08:00:00Z"\n')
    with open(os.path.join(epic_dir, "epic-2.yaml"), "w", encoding="utf-8") as fh:
        fh.write('story_key: epic-2\nepic_num: 2\nbranch: epic/2-widgets\nstatus: in-progress\nactive_story: 2-3-widget\nupdated_at: "2026-05-25T12:00:00Z"\n')
    epscan = _scan_epics(epic_dir)
    check("epic-scan: mode", epscan["mode"] == "epic-scan")
    check("epic-scan: lists 2 epics", len(epscan["epics"]) == 2)
    check("epic-scan: one in-flight (epic-1 done)", epscan["in_flight_count"] == 1)
    check("epic-scan: target most-recent in-flight epic-2", epscan["target"] == "epic-2")
    check("epic-scan: target_epic_num int 2", epscan["target_epic_num"] == 2)
    check("epic-scan: target_active_story is the cursor", epscan["target_active_story"] == "2-3-widget")
    check("epic-scan: resume true", epscan["resume"] is True)
    check("epic-scan: done epic null active_story", any(e["epic_key"] == "epic-1" and e["active_story"] is None for e in epscan["epics"]))
    check("epic-scan: no internal mtime leak", all(not any(k.startswith("_") for k in e) for e in epscan["epics"]))
    check("epic-scan: records carry branch", any(e["epic_key"] == "epic-2" and e["branch"] == "epic/2-widgets" for e in epscan["epics"]))
    check("epic-scan: branch null when absent", any(e["epic_key"] == "epic-1" and e["branch"] is None for e in epscan["epics"]))

    # A non-UTF-8 anchor: null cursor fields, scan still returns JSON.
    with open(os.path.join(epic_dir, "epic-9.yaml"), "wb") as fh:
        fh.write(b"story_key: epic-9\nepic_num: 9\xff\nactive_story: \xfe\n")
    binep = _scan_epics(epic_dir)
    json.dumps(binep)
    check("epic-scan: non-UTF-8 anchor yields null fields", any(e["epic_key"] == "epic-9" and e["status"] is None and e["epic_num"] is None and e["active_story"] is None for e in binep["epics"]))
    check("epic-scan: non-UTF-8 anchor does not disturb the target", binep["target"] == "epic-2")
    os.unlink(os.path.join(epic_dir, "epic-9.yaml"))

    # The epic/ subdir is invisible to the per-story scan (no collision).
    rescan = build_result(state_dir)
    check("epic subdir invisible to per-story scan", all(not s["story_key"].startswith("epic-") for s in rescan["stories"]))

    # An epic anchor resumes/finalizes via the epic subdir as the state dir.
    epstory = build_result(epic_dir, "epic-2")
    check("epic anchor resume via subdir", epstory["exists"] is True and epstory["resume"] is True)
    check("epic anchor story mode carries branch", epstory["branch"] == "epic/2-widgets")
    epfin, epcode = build_finalize_result(epic_dir, "epic-1")
    check("epic finalize reads the anchor", epcode == 0 and epfin["story_key"] == "epic-1")

    # Absent epic/ subdir: no resume (first epic run).
    noepic = _scan_epics(os.path.join(tmp, "no-epic-dir"))
    check("epic-scan: absent dir no resume", noepic["state_dir_exists"] is False and noepic["resume"] is False)

    for name in os.listdir(epic_dir):
        os.unlink(os.path.join(epic_dir, name))
    os.rmdir(epic_dir)

    # ---- finalize mode ---------------------------------------------------- #
    fin_dir = os.path.join(tmp, "fin")
    os.makedirs(fin_dir)

    def write_fin(key, **over):
        body = {
            "review_unverified": "false",
            "gate_decision": "null",
            "ci_status": "passed",
            "blockers": "[]",
        }
        body.update(over)
        lines = [f"story_key: {key}", "status: done", 'updated_at: "2026-06-01T10:00:00Z"']
        for k in ("review_unverified", "gate_decision", "ci_status"):
            lines.append(f"{k}: {body[k]}")
        if body["blockers"] is None:  # block-list form
            lines.append("blockers:")
            lines.append('  - "rotate the API key manually"')
            lines.append("  - second item  # urgent")
        else:
            lines.append(f"blockers: {body['blockers']}")
        lines.append("open_questions: []")
        with open(os.path.join(fin_dir, key + ".yaml"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")

    # No clauses: clean completion, flip, no draft, no reasons.
    write_fin("2-1-clean")
    res, code = build_finalize_result(fin_dir, "2-1-clean")
    check("finalize clean: exit 0", code == 0)
    check("finalize clean: no clause fires", not any(res["clauses"].values()))
    check("finalize clean: not draft", res["draft"] is False)
    check("finalize clean: clean_completion", res["clean_completion"] is True)
    check("finalize clean: flip_bmad_status", res["flip_bmad_status"] is True)
    check("finalize clean: no reasons", res["reasons"] == [])
    check("finalize clean: ci from state", res["ci_status"] == "passed" and res["ci_status_source"] == "state")

    # Clause 1 — blockers (block-list form, comment stripped, items counted).
    write_fin("2-2-blocked", blockers=None)
    res, code = build_finalize_result(fin_dir, "2-2-blocked")
    check("finalize blocker: exit 0 (verdict delivered)", code == 0)
    check("finalize blocker: clause fires alone", res["clauses"] == {"blocker": True, "review_unverified": False, "gate_waived": False, "ci_failed_or_timeout": False})
    check("finalize blocker: count 2", res["blocker_count"] == 2 and res["blockers"][0] == "rotate the API key manually")
    check("finalize blocker: draft", res["draft"] is True)
    check("finalize blocker: not clean", res["clean_completion"] is False and res["flip_bmad_status"] is False)
    check("finalize blocker: one reason", len(res["reasons"]) == 1 and "blocker" in res["reasons"][0])

    # Clause 1 — inline flow list also counts.
    write_fin("2-2b-inline", blockers='["needs db migration", manual deploy]')
    res, _ = build_finalize_result(fin_dir, "2-2b-inline")
    check("finalize inline blockers: count 2", res["blocker_count"] == 2)
    check("finalize inline blockers: draft", res["draft"] is True)

    # Clause 1 — a comma INSIDE a quoted inline blocker is payload, not a
    # separator: one blocker, text intact (the quote-blind split counted 2
    # mangled items here).
    write_fin("2-2e-comma", blockers='["rotate key, then redeploy", plain]')
    res, _ = build_finalize_result(fin_dir, "2-2e-comma")
    check("finalize inline quoted comma: count 2", res["blocker_count"] == 2)
    check("finalize inline quoted comma: item intact",
          res["blockers"] == ["rotate key, then redeploy", "plain"])

    # Clause 1 — a quoted '#' is payload, not a comment (the state writer
    # double-quotes any value containing '#'; comment stripping must respect it).
    with open(os.path.join(fin_dir, "2-2c-hash.yaml"), "w", encoding="utf-8") as fh:
        fh.write('story_key: 2-2c-hash\nstatus: done\nreview_unverified: false\n'
                 'gate_decision: null\nci_status: passed\nblockers:\n'
                 '  - "fix issue #123 upstream"\n  - "rotate key #2"  # urgent\n')
    res, _ = build_finalize_result(fin_dir, "2-2c-hash")
    check("finalize quoted-#: items intact",
          res["blockers"] == ["fix issue #123 upstream", "rotate key #2"])
    with open(os.path.join(fin_dir, "2-2d-hash.yaml"), "w", encoding="utf-8") as fh:
        fh.write('story_key: 2-2d-hash\nstatus: done\nreview_unverified: false\n'
                 'gate_decision: null\nci_status: passed\n'
                 'blockers: ["fix issue #123 upstream"]  # one left\n')
    res, _ = build_finalize_result(fin_dir, "2-2d-hash")
    check("finalize quoted-# inline: item intact",
          res["blockers"] == ["fix issue #123 upstream"])

    # Lockstep round-trip with the WRITER: whatever state_update.py emits, this
    # reader must parse back verbatim — every emit-rule change there must fail
    # loud here, not silently misread the Phase 9 draft predicate.
    import importlib.util as _ilu
    _su_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state_update.py")
    _spec = _ilu.spec_from_file_location("state_update", _su_path)
    assert _spec is not None and _spec.loader is not None, _su_path
    _su = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_su)
    _rt = _su.default_state()
    _rt.update(
        story_key="2-2f-roundtrip", status="review", review_unverified=True,
        branch="story/2-2f-roundtrip", gate_decision="WAIVED", ci_status="timeout",
        blockers=['rotate key, then redeploy', 'fix issue #123 upstream', "plain"],
    )
    # the writer must not emit the retired review-loop clause field at all
    check("writer round-trip: no legacy clause field emitted",
          "convergence_unverified" not in _su.dump_state(_rt))
    with open(os.path.join(fin_dir, "2-2f-roundtrip.yaml"), "w", encoding="utf-8") as fh:
        fh.write(_su.dump_state(_rt))
    res, code = build_finalize_result(fin_dir, "2-2f-roundtrip")
    check("writer round-trip: exit 0", code == 0)
    check("writer round-trip: blockers verbatim",
          res["blockers"] == ['rotate key, then redeploy', 'fix issue #123 upstream', 'plain'])
    check("writer round-trip: scalars verbatim",
          res["gate_decision"] == "WAIVED" and res["ci_status"] == "timeout"
          and res["clauses"]["review_unverified"] is True)
    check("writer round-trip: all four clauses fire",
          all(res["clauses"].values()) and res["draft"] is True)
    _rs = read_state_file(os.path.join(fin_dir, "2-2f-roundtrip.yaml"))
    check("writer round-trip: resume reader agrees", _rs.get("status") == "review")
    check("writer round-trip: branch verbatim", _rs.get("branch") == "story/2-2f-roundtrip")
    _rt2 = _su.default_state()
    _rt2.update(story_key="2-2g-roundtrip", branch="story/2-2g #odd", review_unverified=False)
    with open(os.path.join(fin_dir, "2-2g-roundtrip.yaml"), "w", encoding="utf-8") as fh:
        fh.write(_su.dump_state(_rt2))
    _rs2 = read_state_file(os.path.join(fin_dir, "2-2g-roundtrip.yaml"))
    check("writer round-trip: quoted-# branch verbatim", _rs2.get("branch") == "story/2-2g #odd")
    res, _ = build_finalize_result(fin_dir, "2-2g-roundtrip")
    check("writer round-trip: default state is clean", res["clean_completion"] is True and not any(res["clauses"].values()))

    # Clause 2 — review_unverified.
    write_fin("2-3-unverified", review_unverified="true")
    res, _ = build_finalize_result(fin_dir, "2-3-unverified")
    check("finalize unverified: clause fires alone", res["clauses"] == {"blocker": False, "review_unverified": True, "gate_waived": False, "ci_failed_or_timeout": False})
    check("finalize unverified: draft, not clean", res["draft"] is True and res["clean_completion"] is False)
    check("finalize unverified: reason names the field", any(r.startswith("review_unverified is true") for r in res["reasons"]))
    # a pre-0.27 state file that only carries the retired review-loop flag does NOT
    # fire clause 2 (the field is preserved as an extra by the writer, never re-read here)
    with open(os.path.join(fin_dir, "2-3b-legacy.yaml"), "w", encoding="utf-8") as fh:
        fh.write("story_key: 2-3b-legacy\nstatus: done\nconvergence_unverified: true\n"
                 "gate_decision: null\nci_status: passed\nblockers: []\n")
    res, _ = build_finalize_result(fin_dir, "2-3b-legacy")
    check("finalize legacy flag ignored: clean", res["clean_completion"] is True and res["clauses"]["review_unverified"] is False)

    # Clause 3 — gate WAIVED.
    write_fin("2-4-waived", gate_decision="WAIVED")
    res, _ = build_finalize_result(fin_dir, "2-4-waived")
    check("finalize waived: clause fires alone", res["clauses"] == {"blocker": False, "review_unverified": False, "gate_waived": True, "ci_failed_or_timeout": False})
    check("finalize waived: gate_decision carried", res["gate_decision"] == "WAIVED")
    check("finalize waived: draft, no flip", res["draft"] is True and res["flip_bmad_status"] is False)

    # Clause 3 negative — PASS does not fire.
    write_fin("2-4b-pass", gate_decision="PASS")
    res, _ = build_finalize_result(fin_dir, "2-4b-pass")
    check("finalize gate PASS: clean", res["clean_completion"] is True)

    # Clause 4 — a hand-edited uppercase state value still fires (normalized
    # like the sibling clauses).
    write_fin("2-5a-upper", ci_status="FAILED")
    res, _ = build_finalize_result(fin_dir, "2-5a-upper")
    check("finalize ci FAILED uppercase: fires", res["clauses"]["ci_failed_or_timeout"] is True)
    check("finalize ci FAILED uppercase: draft, not clean", res["draft"] is True and res["clean_completion"] is False)

    # Clause 4 — ci_status from the state file (timeout).
    write_fin("2-5-timeout", ci_status="timeout")
    res, _ = build_finalize_result(fin_dir, "2-5-timeout")
    check("finalize ci timeout: clause fires alone", res["clauses"] == {"blocker": False, "review_unverified": False, "gate_waived": False, "ci_failed_or_timeout": True})
    check("finalize ci timeout: draft", res["draft"] is True)

    # Clause 4 — live --ci-status wins over the state file (both directions).
    res, _ = build_finalize_result(fin_dir, "2-1-clean", ci_status="failed")
    check("finalize ci arg failed: fires over passed state", res["clauses"]["ci_failed_or_timeout"] is True and res["ci_status_source"] == "arg")
    write_fin("2-6-stale-failed", ci_status="failed")
    res, _ = build_finalize_result(fin_dir, "2-6-stale-failed", ci_status="passed")
    check("finalize ci arg passed: clears stale failed state", res["clauses"]["ci_failed_or_timeout"] is False and res["clean_completion"] is True)

    # Clause 4 negatives — unknown (wait never ran) and none do NOT fire.
    write_fin("2-7-unknown", ci_status="unknown")
    res, _ = build_finalize_result(fin_dir, "2-7-unknown")
    check("finalize ci unknown: does not fire", res["clauses"]["ci_failed_or_timeout"] is False and res["clean_completion"] is True)
    with open(os.path.join(fin_dir, "2-8-no-ci.yaml"), "w", encoding="utf-8") as fh:
        fh.write("story_key: 2-8-no-ci\nstatus: done\nblockers: []\nreview_unverified: false\ngate_decision: null\n")
    res, _ = build_finalize_result(fin_dir, "2-8-no-ci")
    check("finalize ci absent: defaults unknown, no fire", res["ci_status"] == "unknown" and res["ci_status_source"] == "default" and res["clean_completion"] is True)
    res, _ = build_finalize_result(fin_dir, "2-1-clean", ci_status="none")
    check("finalize ci none: does not fire", res["clauses"]["ci_failed_or_timeout"] is False)

    # --no-pr-draft: forces draft false ONLY; clean_completion/flip unaffected.
    res, code = build_finalize_result(fin_dir, "2-2-blocked", no_pr_draft=True)
    check("finalize no-pr-draft: exit 0", code == 0)
    check("finalize no-pr-draft: draft forced false", res["draft"] is False)
    check("finalize no-pr-draft: still not clean", res["clean_completion"] is False and res["flip_bmad_status"] is False)
    check("finalize no-pr-draft: clause + reason still reported", res["clauses"]["blocker"] is True and len(res["reasons"]) == 1)
    res, _ = build_finalize_result(fin_dir, "2-1-clean", no_pr_draft=True)
    check("finalize no-pr-draft on clean: unchanged", res["draft"] is False and res["clean_completion"] is True)

    # A non-UTF-8 state file: still a JSON verdict (no clause can fire from it), exit 0.
    with open(os.path.join(fin_dir, "2-9-bad-bytes.yaml"), "wb") as fh:
        fh.write(b"story_key: 2-9-bad-bytes\nblockers: [\xff]\nci_status: failed\xfe\n")
    res, code = build_finalize_result(fin_dir, "2-9-bad-bytes")
    json.dumps(res)
    check("finalize non-UTF-8: exit 1 with an error, never a traceback", code == 1 and "unreadable" in (res["error"] or ""))
    check("finalize non-UTF-8: no clean verdict from unreadable content", res["clean_completion"] is False and res["flip_bmad_status"] is False)

    # Missing state file => exit 1.
    res, code = build_finalize_result(fin_dir, "9-9-nope")
    check("finalize missing: exit 1", code == 1)
    check("finalize missing: error set", bool(res["error"]))

    for name in os.listdir(fin_dir):
        os.unlink(os.path.join(fin_dir, name))
    os.rmdir(fin_dir)
    for name in os.listdir(state_dir):
        os.unlink(os.path.join(state_dir, name))
    os.rmdir(state_dir)
    os.rmdir(tmp)

    if failures:
        print("SELF-TEST FAILED:", ", ".join(failures), file=sys.stderr)
        return 1
    print("SELF-TEST PASSED (all assertions)")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="auto-bmad state-file reader")
    parser.add_argument("--state-dir", help="the {output_folder}/auto-bmad/state directory")
    parser.add_argument("--story-key", help="check one exact {key}.yaml instead of scanning all")
    parser.add_argument("--scope", choices=["story", "epic"], default="story", help="state scope: per-story files under --state-dir (default), or the epic anchors under <state-dir>/epic")
    parser.add_argument("--finalize", action="store_true", help="evaluate the Phase 9 draft predicate / clean-completion verdict for --story-key")
    parser.add_argument("--ci-status", choices=["passed", "failed", "timeout", "none", "unknown"], help="with --finalize: the live post-CI-wait value (overrides the state file)")
    parser.add_argument("--no-pr-draft", action="store_true", help="with --finalize: the no_pr_draft flag — forces draft=false, never touches clean_completion")
    parser.add_argument("--self-test", action="store_true", help="run built-in fixtures and exit")
    args = parser.parse_args(argv)

    if args.self_test:
        return _run_self_test()

    if not args.state_dir:
        parser.error("--state-dir is required (or use --self-test)")

    # --scope epic operates on the epic anchors under <state-dir>/epic; default
    # scope is the per-story files directly under --state-dir.
    effective_dir = os.path.join(args.state_dir, "epic") if args.scope == "epic" else args.state_dir

    if args.finalize:
        if not args.story_key:
            parser.error("--finalize requires --story-key")
        result, code = build_finalize_result(effective_dir, args.story_key, args.ci_status, args.no_pr_draft)
        print(json.dumps(result, indent=2))
        return code
    if args.ci_status or args.no_pr_draft:
        parser.error("--ci-status/--no-pr-draft are only valid with --finalize")

    if args.scope == "epic" and not args.story_key:
        result = _scan_epics(effective_dir)
    else:
        result = build_result(effective_dir, args.story_key)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
