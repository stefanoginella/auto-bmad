#!/usr/bin/env python3
"""Deterministic mechanics for auto-bmad's deferred-work ledger.

The active ledger ``<impl>/deferred-work.md`` is auto-bmad's cross-story
memory of deferred review findings: it feeds the pipeline reports and PR
bodies (and the humans who read them). Nothing upstream reads it (BMAD 6.11)
and nothing feeds it forward into the next epic's planning — so its two
maintenance jobs are auto-bmad's alone:

* **Phase 7 tail — ``harvest``**: bmad-build-auto never writes the ledger; it
  records each deferred review finding in the story spec's frontmatter
  ``deferred:`` list. ``harvest`` copies those items into the ledger
  (idempotently) so the ledger stays the one place deferred work is listed.
* **Phase 8 — ``plan`` / ``archive``**: at epic end the orchestrator trims the
  ledger — entries that vouch for their own full resolution move to the
  sibling archive ``deferred-work-resolved.md`` so finished work stops
  re-surfacing in reports and PR bodies. The KEEP-vs-MOVE **judgment stays
  with the LLM** (the self-vouching rule and the keep-on-doubt asymmetry are
  normative in pipeline.md); this script owns the mechanics that must not be
  left to a generative rewrite of two markdown files: reading the ledger into
  addressable entries, and moving exactly the chosen entries atomically.

An **entry** is one top-level (column-0) bullet — plus its continuation
lines and nested bullets — in either of two shapes:

(a) a bullet under a ``## Deferred from: <source> (<date>)`` heading (the
    shape upstream ``bmad-code-review`` appends, and the shape ``harvest``
    writes); the entry's ``heading`` is that heading line;
(b) a bullet OUTSIDE any such heading whose first line is
    ``- source_spec: …`` (upstream ``bmad-build``'s heading-less block —
    ``- source_spec: `<spec>` / summary: … / evidence: …`` appended at EOF);
    such an entry is reported with the synthetic ``heading:
    "## Deferred from: bmad-build (unsectioned)"`` and ``archive`` appends
    it under that literal heading in the archive file.

Any other bullet outside a deferral section (title/intro bullets, ``## Notes``)
is prose and is preserved verbatim. A section ends at the next heading at its
own level or shallower; a DEEPER heading (``### context`` under a ``##``
section) is section-internal structure and the bullets after it are still
entries. Fenced code blocks (``` or ~~~, CommonMark-style) are tracked:
``## …`` / ``- …`` lines inside a fence are literal content, never a section
or entry boundary, and an unclosed fence runs to end of file as content of
the current entry/section. Note that a ``- source_spec:`` block bmad-build
appends AFTER a harvested heading is, by the section rule, an entry of that
section (it stays an entry either way; only its ``heading`` differs).

Usage:
    deferred_ledger.py plan    --ledger PATH
    deferred_ledger.py archive --ledger PATH --archive PATH --ids 2,5,9
                               --expect-sha SHA
    deferred_ledger.py harvest --ledger PATH --spec SPEC_PATH --story-key KEY
                               [--archive PATH] [--date YYYY-MM-DD] [--dry-run]
    deferred_ledger.py --self-test

``plan`` (read-only) prints::

    {"ledger_present": bool, "ledger_sha256": str|null,
     "entries": [{"id": int, "heading": str, "text": str,
                  "source_spec": str|null, "summary": str|null,
                  "marker_hint": "resolved"|"partial"|"open"}]}

``id`` is a stable integer index in document order — valid only against this
``ledger_sha256``. ``source_spec`` / ``summary`` are the values of the entry's
own ``source_spec:`` / ``summary:`` lines when present (wrapping backticks
and quotes stripped; a ``>-``/``|-`` block scalar is folded to one line),
else ``null`` — free-text bullets have neither. ``marker_hint`` is a
HEURISTIC AID ONLY, computed from the
entry's OWN text (an entry is never hinted ``resolved`` because a *different*
entry mentions it): ``resolved`` if the entry carries a resolution marker (a
leading ``✅``, ``RESOLVED``, "resolved in", "closed", "addressed in",
"done in" — case-insensitive) and no open-remainder signal; ``partial`` if it
has both a marker and a remainder signal ("remainder", "still open",
"portion", "owned by", "partially"); else ``open``. The LLM makes the final
call per pipeline.md; the hint just focuses its read. A missing or empty
ledger prints ``{"ledger_present": false, "entries": []}`` and exits 0.

``archive`` moves the entries named by ``--ids`` from the ledger to the
archive: each is appended under a matching ``## Deferred from:`` heading there
(the archive is created with a one-line H1 title if absent; an existing
identical heading is reused, else the heading is appended; a heading-less
entry goes under the synthetic heading above), removed from the
ledger, and any ledger ``## Deferred from:`` heading left with zero entries is
dropped. The ledger's title and intro prose are preserved verbatim. Both files
are written via temp-file + ``os.replace`` (archive first, so a crash between
the two writes leaves the entry in both files, never lost). Re-running the
same ``archive`` after such a crash is safe: an entry whose text (normalized
for trailing whitespace) already sits under the target archive heading is not
appended again — it counts in ``deduped`` (and still in ``moved``) and the
ledger-side removal proceeds. ``--expect-sha`` must equal the current ledger
sha256 (take it from ``plan``); a mismatch — the file changed since planning —
or an unknown id exits 1 with NO writes. Prints::

    {"moved": int, "deduped": int, "headings_created": int,
     "headings_removed": int, "ledger_sha256_after": str}

``harvest`` reads the build-auto spec's frontmatter ``deferred:`` list (via
the sibling ``story_plan.py``'s ``read_spec`` — imported with ``importlib``;
the one cross-script import, lockstep-self-tested) and appends one entry per
item under the heading ``## Deferred from: build-auto review of KEY (<date>)``
(``--date`` defaults to today, ``YYYY-MM-DD``; the heading is created at EOF
when absent for that key/date and reused when the identical heading exists)::

    - source_spec: `<spec basename>`
      summary: <summary, single line>
      evidence: <evidence, single line — newlines folded to spaces>
      location: <location>        (only if present)
      severity: <severity>        (only if present)

Idempotent by ``(source_spec basename, normalized summary)`` — case-folded,
whitespace-collapsed — against the entries of BOTH the ledger and the archive
(``--archive`` defaults to the ledger's sibling ``deferred-work-resolved.md``);
an item already recorded in either file (or repeated within the spec) counts
in ``skipped_existing`` and is not written again. An item with a MISSING/BLANK
``summary`` has no identity of its own, so its ``evidence`` (plus ``location``
when present) joins the key instead — two summary-less items never collapse
into one. A missing ledger is created (H1 title + heading + entries) — but
never when the spec has nothing to harvest (``deferred_in_spec: 0`` ⇒ no-op,
no file created) and never when every item was already recorded.
``ledger_created`` is true ONLY when this run actually created the file: false
on every no-write path, ``--dry-run`` included (which computes the same counts
and writes nothing).
Prints::

    {"harvested": int, "skipped_existing": int, "ledger_created": bool,
     "heading": str, "deferred_in_spec": int, "dry_run": bool}

Exit codes: 0 ok (``plan`` on a missing ledger, an idempotent ``harvest``
re-run and a ``harvest`` that creates the ledger are all 0); 1 stale sha /
unknown id / missing ledger (``archive``), missing or unreadable spec, or a
missing ``story_plan.py`` sibling (``harvest``); 2 usage. An I/O failure on any
mode — a ledger/archive/spec that is unreadable or not valid UTF-8, or a
``--ledger``/``--archive`` that names a DIRECTORY — prints ``{"error": …}``
and exits 1 (never a traceback, never a partial write).
Dependency-free (stdlib only). Output is a single JSON object on stdout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile

# A ledger section heading: `## Deferred from: code review of story-3.3 (2026-03-18)`.
DEFER_HEADING_RE = re.compile(r"^#{1,4}\s+deferred\s+from:", re.IGNORECASE)
# Any ATX heading at level 1-4 — a section-end candidate. Level-aware: only a
# heading at the section's own level or shallower closes it; a DEEPER heading
# (`### context` under a `## Deferred from:`) is section-internal structure and
# the entries after it still belong to the section.
ANY_HEADING_RE = re.compile(r"^#{1,4}\s+\S")


def _heading_level(line):
    """Number of leading ``#`` on a line ``ANY_HEADING_RE`` matched."""
    return len(line) - len(line.lstrip("#"))
# A top-level bullet (column 0) — starts a new entry inside a deferral section.
TOP_BULLET_RE = re.compile(r"^[-*+]\s+\S")
# bmad-build's heading-less block: a column-0 bullet whose first line is
# `- source_spec: …` starts an entry even OUTSIDE any `## Deferred from:`
# section (reported under SYNTHETIC_HEADING). Other unsectioned bullets stay
# prose.
SOURCE_SPEC_BULLET_RE = re.compile(r"^[-*+]\s+source_spec:", re.IGNORECASE)
SYNTHETIC_HEADING = "## Deferred from: bmad-build (unsectioned)"
# `source_spec:` / `summary:` field lines inside an entry (first line may carry
# the bullet marker; continuation lines are indented). Value = group 1.
FIELD_LINE_RE = {
    name: re.compile(r"^\s*(?:[-*+]\s+)?%s:\s*(.*?)\s*$" % name, re.IGNORECASE)
    # `evidence` / `location` are read for the dedupe key only — they are the
    # fallback identity of a summary-less item (see `dedupe_key`).
    for name in ("source_spec", "summary", "evidence", "location")
}
# A YAML block-scalar indicator as the whole value (`>-`, `|-`, `>`, `|`, with
# an optional trailing comment): the value continues on the deeper-indented
# lines that follow, folded to one line.
BLOCK_INDICATOR_RE = re.compile(r"^[>|][-+]?\s*(?:#.*)?$")
# An indented, non-blank line — a continuation / nested bullet of the entry.
INDENTED_RE = re.compile(r"^\s+\S")
# Fenced code blocks (CommonMark-style, kept simple): a fence OPENS on a line
# whose content — at ANY indent, optionally right after a single bullet marker
# (`- ```py` is CommonMark-legal) — starts with 3+ backticks or tildes (an
# info string may follow); it CLOSES on a later line with the SAME fence char,
# at LEAST as many of them, any indent, and nothing else. One rule for every
# position (intro, section text, entry bullets, nested bullets): tracking the
# opener and the closer with the SAME indent tolerance is what prevents the
# state-inversion class of bug, where an untracked opener's closing line is
# read as an OPENER and the rest of the document is swallowed as fence
# content. While inside a fence NO line is a heading or a bullet — `## …` /
# `- …` lines in there are literal content, never section/entry boundaries.
# (Backtick branch: CommonMark forbids backticks in a backtick fence's info
# string, so requiring no later backtick keeps inline code spans — ```x``` —
# from reading as fence openers. Tilde info strings may contain anything.)
FENCE_OPEN_RE = re.compile(r"^\s*(?:[-*+]\s+)?(`{3,}(?!.*`)|~{3,})")


def _fence_open(line):
    """Return ``(char, length)`` if ``line`` opens a fence, else ``None``."""
    m = FENCE_OPEN_RE.match(line)
    return (m.group(1)[0], len(m.group(1))) if m else None


def _fence_closes(line, char, length):
    """True if ``line`` closes a fence opened with ``length`` × ``char``."""
    return bool(re.match(r"^\s*%s{%d,}\s*$" % (re.escape(char), length), line))

# Resolution markers (entry's OWN text only — the self-vouching rule). Word
# boundaries keep e.g. "disclosed" from reading as "closed".
RESOLUTION_RE = re.compile(
    r"(?:\bresolved\b|\bclosed\b|\baddressed\s+in\b|\bdone\s+in\b)", re.IGNORECASE
)
# A leading ✅ right after the bullet marker (optional checkbox/emphasis tolerated).
LEADING_CHECK_RE = re.compile(r"^[-*+]\s+(?:\[[ xX]\]\s+)?(?:\*\*|__)?\s*✅")
# Open-remainder signals — a partial resolution still carries open work.
REMAINDER_RE = re.compile(
    r"(?:\bremainder\b|\bstill\s+open\b|\bportion\b|\bowned\s+by\b|\bpartial(?:ly)?\b)",
    re.IGNORECASE,
)

ARCHIVE_TITLE = "# Deferred Work — Resolved"

# Placeholders `harvest` writes for a spec item with a blank/missing field.
NO_SUMMARY = "(no summary recorded)"
NO_EVIDENCE = "(no evidence recorded)"


class LedgerIOError(Exception):
    """A ledger / archive / spec path could not be read or written (missing
    permissions, a directory where a file is expected, non-UTF-8 bytes).
    Every mode turns this into ``{"error": …}`` + exit 1, never a traceback."""


def _read_ledger_bytes(path, label):
    """Read ``path`` as bytes. Raises ``LedgerIOError`` instead of an OSError."""
    if os.path.isdir(path):
        raise LedgerIOError(f"{label} path is a directory, not a markdown file: {path}")
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except (OSError, IsADirectoryError) as exc:
        raise LedgerIOError(f"cannot read {label}: {path}: {exc.strerror or exc}") from exc


def _decode_ledger(raw, path, label):
    """Decode ledger/archive bytes as UTF-8. Raises ``LedgerIOError``."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LedgerIOError(
            f"{label} is not valid UTF-8 ({exc.reason} at byte {exc.start}): {path}"
        ) from exc


def _read_ledger_text(path, label):
    """Read + decode a ledger/archive file. Raises ``LedgerIOError``."""
    return _decode_ledger(_read_ledger_bytes(path, label), path, label)


def classify_hint(entry_text: str) -> str:
    """Heuristic marker hint for ONE entry, from its own text only."""
    first_line = entry_text.split("\n", 1)[0]
    has_resolution = bool(RESOLUTION_RE.search(entry_text)) or bool(
        LEADING_CHECK_RE.match(first_line)
    )
    if not has_resolution:
        return "open"
    return "partial" if REMAINDER_RE.search(entry_text) else "resolved"


def _strip_wrapping(value: str) -> str:
    """Strip one layer of wrapping backticks / quotes around a field value."""
    v = value.strip()
    for q in ("`", '"', "'"):
        if len(v) >= 2 and v.startswith(q) and v.endswith(q):
            return v[1:-1].strip()
    return v


def _fold(value: str) -> str:
    """Fold any whitespace run (incl. newlines) to one space and strip."""
    return " ".join(value.split())


def extract_fields(entry_lines):
    """``{"source_spec", "summary", "evidence", "location"}`` (each str|None)
    from an entry's OWN lines: the first field line of each name before any
    fenced block (a `` `x` ``/quoted value is unwrapped; a ``>-``/``|-``
    block scalar is folded from the deeper-indented lines that follow)."""
    out = {name: None for name in FIELD_LINE_RE}
    n = len(entry_lines)
    for idx, line in enumerate(entry_lines):
        if _fence_open(line):
            break  # fields live above any fenced content; stop scanning
        for name, rx in FIELD_LINE_RE.items():
            if out[name] is not None:
                continue
            m = rx.match(line)
            if not m:
                continue
            value = m.group(1)
            if not value or BLOCK_INDICATOR_RE.match(value):
                indent = len(line) - len(line.lstrip())
                parts = []
                j = idx + 1
                while j < n and (not entry_lines[j].strip()
                                 or len(entry_lines[j]) - len(entry_lines[j].lstrip()) > indent):
                    if entry_lines[j].strip():
                        parts.append(entry_lines[j].strip())
                    j += 1
                value = " ".join(parts)
            value = _fold(_strip_wrapping(value))
            out[name] = value if value else None
    return out


def _collect_entry(lines, i):
    """Collect one entry starting at the column-0 bullet ``lines[i]``.
    Returns ``(entry_lines, next_i)``. Continuation rules: indented lines,
    nested bullets, lazy top-level prose right after entry content, and blank
    lines only when an indented continuation follows; fenced blocks (opened on
    the bullet line itself, on a nested bullet, or on a continuation line) are
    tracked so nothing inside them is a heading/bullet boundary."""
    n = len(lines)
    line = lines[i]
    entry_lines = [line]
    # The entry's own bullet may open a fence (`- ```py`): track it so
    # its closing line isn't mistaken for an opener.
    entry_fence = _fence_open(line)  # (char, length) of an open fence in the entry
    i += 1
    while i < n:
        nxt = lines[i]
        if entry_fence is not None:
            # Inside a fence every line (blank, `## …`, `- …`) is
            # entry content. With no closing fence this runs to EOF —
            # deliberate: "end of section" is itself heading-detected,
            # and inside a fence nothing is a heading, so the rest of
            # the document stays with this entry (lossless reading).
            entry_lines.append(nxt)
            if _fence_closes(nxt, *entry_fence):
                entry_fence = None
            i += 1
            continue
        if not nxt.strip():
            # Blank line(s): attach only if followed by an indented
            # continuation; otherwise they are the section separator.
            j = i
            while j < n and not lines[j].strip():
                j += 1
            if j < n and INDENTED_RE.match(lines[j]):
                entry_lines.extend(lines[i:j])
                i = j
                continue
            break
        if ANY_HEADING_RE.match(nxt) or TOP_BULLET_RE.match(nxt):
            # Break BEFORE the fence test: a column-0 `- ```py` is a
            # sibling entry (whose own first line opens ITS fence).
            break
        opened = _fence_open(nxt)
        if opened is not None:  # any indent — nested bullet fences too
            entry_fence = opened
            entry_lines.append(nxt)
            i += 1
            continue
        if INDENTED_RE.match(nxt):
            entry_lines.append(nxt)
            i += 1
            continue
        # Top-level prose directly after entry content (no blank line
        # between): markdown lazy continuation — part of the entry.
        entry_lines.append(nxt)
        i += 1
    return entry_lines, i


def parse_document(text: str):
    """Parse a ledger/archive into ``(segments, entries, next_section)``.

    ``segments`` is an ordered, lossless model of the document:
    ``{"kind": "text", "section": int|None, "lines": [...]}`` |
    ``{"kind": "heading", "section": int, "line": str}`` |
    ``{"kind": "entry", "section": int|None, "id": int, "lines": [...]}``.
    Text outside any ``## Deferred from:`` section has ``section: None`` and is
    always reproduced verbatim; a heading-less ``- source_spec:`` entry also
    has ``section: None`` (its ``heading`` is ``SYNTHETIC_HEADING``). Entry
    lines include attached blank lines (so a removal also removes its
    separator); the entry's ``text`` is rstripped.
    """
    lines = text.splitlines()
    segments = []
    entries = []
    section = None
    section_level = 0  # level of the current section's `## Deferred from:` heading
    cur_heading = None
    next_section = 0
    n = len(lines)

    def add_text(chunk):
        if segments and segments[-1]["kind"] == "text" and segments[-1]["section"] == section:
            segments[-1]["lines"].extend(chunk)
        else:
            segments.append({"kind": "text", "section": section, "lines": list(chunk)})

    def add_entry(entry_lines, heading):
        entry_text = "\n".join(entry_lines).rstrip()
        eid = len(entries)
        segments.append({"kind": "entry", "section": section, "id": eid, "lines": entry_lines})
        fields = extract_fields(entry_lines)
        entries.append(
            {
                "id": eid,
                "section": section,
                "heading": heading,
                "text": entry_text,
                "source_spec": fields["source_spec"],
                "summary": fields["summary"],
                # Dedupe-key fallback fields; NOT part of the `plan` JSON
                # (build_plan re-projects the documented entry keys).
                "evidence": fields["evidence"],
                "location": fields["location"],
                "marker_hint": classify_hint(entry_text),
            }
        )

    i = 0
    fence = None  # (char, length) of an open fence in title/intro/section text
    while i < n:
        line = lines[i]
        if fence is not None:
            # Inside a fenced code block: the line is verbatim text, never a
            # heading or a bullet.
            add_text([line])
            if _fence_closes(line, *fence):
                fence = None
            i += 1
            continue
        if DEFER_HEADING_RE.match(line):
            section = next_section
            next_section += 1
            cur_heading = line.strip()
            section_level = _heading_level(line)
            segments.append({"kind": "heading", "section": section, "line": line})
            i += 1
            continue
        if ANY_HEADING_RE.match(line):
            if section is not None and _heading_level(line) > section_level:
                # Deeper than the section heading: internal structure, not a
                # boundary — the section stays open and later bullets are
                # still entries. The heading travels as section text (so it
                # vanishes with an emptied section, like any section prose).
                add_text([line])
                i += 1
                continue
            # A heading at the section's level or shallower closes it.
            section = None
            cur_heading = None
            add_text([line])
            i += 1
            continue
        if section is not None and TOP_BULLET_RE.match(line):
            # Checked BEFORE the fence-open test: a column-0 bullet that opens
            # a fence (`- ```py`) starts a NEW entry whose first line opens the
            # entry's fence — it is not intro/section fence text.
            entry_lines, i = _collect_entry(lines, i)
            add_entry(entry_lines, cur_heading)
            continue
        if section is None and SOURCE_SPEC_BULLET_RE.match(line):
            # bmad-build's heading-less block: an entry outside any section,
            # reported under the synthetic heading.
            entry_lines, i = _collect_entry(lines, i)
            add_entry(entry_lines, SYNTHETIC_HEADING)
            continue
        opened = _fence_open(line)
        if opened is not None:
            fence = opened  # any non-entry line (bullet or indented) may open a fence
        add_text([line])
        i += 1
    return segments, entries, next_section


def render(segments, skip_entry_ids=frozenset(), skip_sections=frozenset()) -> str:
    """Reassemble a document, dropping the named entries and emptied sections."""
    out = []
    for seg in segments:
        if seg["kind"] == "entry":
            if seg.get("id") in skip_entry_ids:
                continue
            out.extend(seg["lines"])
        elif seg["kind"] == "heading":
            if seg["section"] in skip_sections:
                continue
            out.append(seg["line"])
        else:  # text — section-internal text vanishes with its emptied section
            if seg["section"] is not None and seg["section"] in skip_sections:
                continue
            out.extend(seg["lines"])
    body = "\n".join(out).rstrip()
    return body + "\n" if body else ""


def _last_line(segments):
    for seg in reversed(segments):
        seg_lines = [seg["line"]] if seg["kind"] == "heading" else seg["lines"]
        if seg_lines:
            return seg_lines[-1]
    return None


def _norm_entry_text(lines):
    """Entry text normalized for trailing whitespace — the dedupe comparison."""
    return "\n".join(ln.rstrip() for ln in lines).rstrip()


def _insert_entries(segments, next_section, moved):
    """Insert moved entries into the archive's segment model. Returns
    ``(headings_created, deduped)``: identical existing headings are reused,
    and an entry whose normalized text already sits under the target heading
    is NOT appended again (``deduped`` — the crash-recovery re-run case)."""
    created = 0
    deduped = 0
    for entry in moved:  # document order — stable regardless of --ids order
        lines = entry["text"].split("\n")
        target = None
        for seg in segments:
            if seg["kind"] == "heading" and seg["line"].strip() == entry["heading"]:
                target = seg["section"]
                break
        if target is None:
            last = _last_line(segments)
            if last is not None and last.strip():
                segments.append({"kind": "text", "section": None, "lines": [""]})
            segments.append({"kind": "heading", "section": next_section, "line": entry["heading"]})
            segments.append({"kind": "text", "section": next_section, "lines": [""]})
            segments.append({"kind": "entry", "section": next_section, "lines": lines})
            next_section += 1
            created += 1
            continue
        if _norm_entry_text(lines) in {
            _norm_entry_text(seg["lines"])
            for seg in segments
            if seg["kind"] == "entry" and seg["section"] == target
        }:
            deduped += 1  # already archived (e.g. crash before the ledger write)
            continue
        insert_at = None
        for idx in range(len(segments) - 1, -1, -1):  # after the section's last entry
            if segments[idx]["kind"] == "entry" and segments[idx]["section"] == target:
                insert_at = idx + 1
                break
        if insert_at is None:  # heading with no entries yet
            for idx, seg in enumerate(segments):
                if seg["kind"] == "heading" and seg["section"] == target:
                    insert_at = idx + 1
                    nxt = segments[insert_at] if insert_at < len(segments) else None
                    if (
                        nxt is not None
                        and nxt["kind"] == "text"
                        and nxt["section"] == target
                        and not any(ln.strip() for ln in nxt["lines"])
                    ):
                        insert_at += 1  # keep the blank line after the heading
                    break
        segments.insert(insert_at, {"kind": "entry", "section": target, "lines": lines})
    return created, deduped


def _atomic_write(path: str, content: str) -> None:
    """Atomic temp-file + ``os.replace`` write. Any OS failure (unwritable
    directory, a directory in place of the file) becomes a ``LedgerIOError``
    so the caller reports ``{"error": …}`` + exit 1 instead of a traceback."""
    try:
        _atomic_write_raw(path, content)
    except (OSError, IsADirectoryError) as exc:
        raise LedgerIOError(f"cannot write {path}: {exc.strerror or exc}") from exc


def _atomic_write_raw(path: str, content: str) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".deferred-ledger.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        try:
            # mkstemp creates 0600; carry an existing target's mode so the
            # replace doesn't silently drop group/other bits from a user file.
            os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        except OSError:
            pass  # fresh target (e.g. a new archive file): keep mkstemp's default
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def build_plan(ledger_path: str):
    """The ``plan`` JSON. An unreadable / non-UTF-8 ledger (or a ``--ledger``
    that names a directory) returns ``{"error": …}`` — exit 1 in ``main``."""
    try:
        return _build_plan(ledger_path)
    except LedgerIOError as exc:
        return {"error": str(exc)}


def _build_plan(ledger_path: str):
    if not os.path.isfile(ledger_path):
        if os.path.isdir(ledger_path):
            raise LedgerIOError(f"ledger path is a directory, not a markdown file: {ledger_path}")
        return {"ledger_present": False, "ledger_sha256": None, "entries": []}
    raw = _read_ledger_bytes(ledger_path, "ledger")
    sha = hashlib.sha256(raw).hexdigest()
    text = _decode_ledger(raw, ledger_path, "ledger")
    if not text.strip():
        return {"ledger_present": False, "ledger_sha256": sha, "entries": []}
    _segments, entries, _next = parse_document(text)
    return {
        "ledger_present": True,
        "ledger_sha256": sha,
        "entries": [
            {"id": e["id"], "heading": e["heading"], "text": e["text"],
             "source_spec": e["source_spec"], "summary": e["summary"],
             "marker_hint": e["marker_hint"]}
            for e in entries
        ],
    }


def do_archive(ledger_path: str, archive_path: str, ids, expect_sha: str):
    """Returns ``(result_dict, exit_code)``. No writes on any failure — an
    unreadable / non-UTF-8 / directory ledger or archive is ``{"error": …}``
    + exit 1, never a traceback."""
    try:
        return _do_archive(ledger_path, archive_path, ids, expect_sha)
    except LedgerIOError as exc:
        return {"error": str(exc)}, 1


def _do_archive(ledger_path: str, archive_path: str, ids, expect_sha: str):
    if not os.path.isfile(ledger_path):
        if os.path.isdir(ledger_path):
            raise LedgerIOError(f"ledger path is a directory, not a markdown file: {ledger_path}")
        return {"error": f"ledger not found: {ledger_path}"}, 1
    raw = _read_ledger_bytes(ledger_path, "ledger")
    actual_sha = hashlib.sha256(raw).hexdigest()
    if actual_sha != expect_sha.strip().lower():
        return (
            {
                "error": "stale --expect-sha: ledger changed since planning (re-run `plan`)",
                "expected_sha": expect_sha,
                "actual_sha": actual_sha,
            },
            1,
        )
    segments, entries, _next = parse_document(_decode_ledger(raw, ledger_path, "ledger"))
    known = {e["id"] for e in entries}
    wanted = sorted(set(ids))
    unknown = [i for i in wanted if i not in known]
    if unknown:
        return {"error": f"unknown entry id(s): {unknown}", "known_ids": sorted(known)}, 1
    move_set = set(wanted)
    moved = [e for e in entries if e["id"] in move_set]  # document order

    # Sections this move empties (a heading that had no entries to begin with
    # is left untouched — only emptied-by-the-move headings are dropped).
    # Heading-less entries (`section: None`) have no heading to drop.
    totals, removed = {}, {}
    for e in entries:
        totals[e["section"]] = totals.get(e["section"], 0) + 1
    for e in moved:
        removed[e["section"]] = removed.get(e["section"], 0) + 1
    emptied = {sec for sec, total in totals.items()
               if sec is not None and removed.get(sec, 0) == total}

    new_ledger = render(segments, skip_entry_ids=move_set, skip_sections=emptied)

    if os.path.isfile(archive_path):
        a_segments, _a_entries, a_next = parse_document(
            _read_ledger_text(archive_path, "archive")
        )
    elif os.path.isdir(archive_path):
        raise LedgerIOError(f"archive path is a directory, not a markdown file: {archive_path}")
    else:
        a_segments = [{"kind": "text", "section": None, "lines": [ARCHIVE_TITLE]}]
        a_next = 0
    created, deduped = _insert_entries(a_segments, a_next, moved)
    new_archive = render(a_segments)

    # Archive first: a crash between the two atomic writes can then only
    # duplicate an entry (it sits in both files), never lose one.
    _atomic_write(archive_path, new_archive)
    _atomic_write(ledger_path, new_ledger)
    return (
        {
            "moved": len(moved),
            "deduped": deduped,
            "headings_created": created,
            "headings_removed": len(emptied),
            "ledger_sha256_after": hashlib.sha256(new_ledger.encode("utf-8")).hexdigest(),
        },
        0,
    )


LEDGER_TITLE = "# Deferred Work"
HARVEST_HEADING_TMPL = "## Deferred from: build-auto review of {key} ({date})"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _load_story_plan(script_path=None):
    """Import the sibling ``story_plan.py`` (the spec frontmatter reader) via
    importlib. Returns the module or raises ``FileNotFoundError``."""
    import importlib.util

    if script_path is None:
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "story_plan.py")
    if not os.path.isfile(script_path):
        raise FileNotFoundError(script_path)
    spec = importlib.util.spec_from_file_location("_ab_story_plan", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dedupe_key(source_spec, summary, evidence=None, location=None):
    """The harvest idempotency key: ``(spec basename, normalized summary)``.

    A summary-less item (blank/missing ``summary``, i.e. the ``NO_SUMMARY``
    placeholder ``harvest`` renders) has no identity of its own, so its
    evidence — and location when present — is folded into the key instead:
    ``(basename, "", evidence, location)``. Without that, two DIFFERENT
    summary-less items collapse into one and the second is silently dropped
    as "already recorded". ``None`` when the entry has none of the fields
    (free-text bullets never collide with harvested items)."""
    if source_spec is None and summary is None and evidence is None and location is None:
        return None
    base = os.path.basename(_strip_wrapping(source_spec)) if source_spec else ""
    norm_summary = _fold(summary or "").casefold()
    if norm_summary and norm_summary != NO_SUMMARY.casefold():
        return (base.casefold(), norm_summary)
    return (
        base.casefold(),
        "",
        _fold(evidence or "").casefold(),
        _fold(location or "").casefold(),
    )


def _existing_keys(path, label="ledger"):
    """Dedupe keys of every entry in a ledger/archive file (missing ⇒ empty).
    Raises ``LedgerIOError`` on an unreadable / non-UTF-8 file."""
    keys = set()
    if not os.path.isfile(path):
        if os.path.isdir(path):
            raise LedgerIOError(f"{label} path is a directory, not a markdown file: {path}")
        return keys
    _segs, entries, _n = parse_document(_read_ledger_text(path, label))
    for e in entries:
        k = dedupe_key(e["source_spec"], e["summary"], e["evidence"], e["location"])
        if k is not None:
            keys.add(k)
    return keys


def render_harvest_entry(spec_basename, item):
    """The ledger entry lines for one spec ``deferred:`` item."""
    summary = _fold(str(item.get("summary") or "")) or NO_SUMMARY
    evidence = _fold(str(item.get("evidence") or "")) or NO_EVIDENCE
    lines = [
        f"- source_spec: `{spec_basename}`",
        f"  summary: {summary}",
        f"  evidence: {evidence}",
    ]
    for opt in ("location", "severity"):
        v = item.get(opt)
        if v not in (None, ""):
            lines.append(f"  {opt}: {_fold(str(v))}")
    return lines


def do_harvest(ledger_path, spec_path, story_key, archive_path=None, date=None,
               dry_run=False, story_plan_module=None):
    """Returns ``(result_dict, exit_code)``. Never writes on failure or dry-run.
    An unreadable / non-UTF-8 / directory ledger, archive or spec is
    ``{"error": …, "heading": …}`` + exit 1, never a traceback."""
    if archive_path is None:
        archive_path = os.path.join(os.path.dirname(os.path.abspath(ledger_path)),
                                    "deferred-work-resolved.md")
    if date is None:
        import datetime as _dt
        date = _dt.date.today().isoformat()
    heading = HARVEST_HEADING_TMPL.format(key=story_key, date=date)
    try:
        return _do_harvest(ledger_path, spec_path, archive_path, heading,
                           dry_run, story_plan_module)
    except LedgerIOError as exc:
        return {"error": str(exc), "heading": heading}, 1


def _do_harvest(ledger_path, spec_path, archive_path, heading, dry_run, story_plan_module):
    if os.path.isdir(ledger_path):
        raise LedgerIOError(f"ledger path is a directory, not a markdown file: {ledger_path}")
    try:
        sp = story_plan_module or _load_story_plan()
    except FileNotFoundError as exc:
        return {"error": f"story_plan.py not found next to this script: {exc}",
                "heading": heading}, 1
    spec = sp.read_spec(spec_path)
    if not spec.get("exists") or spec.get("error"):
        # Missing, unreadable or non-UTF-8 spec: story_plan.py already reports
        # the reason (it never raises) — pass it through as this mode's error.
        return {"error": spec.get("error") or f"spec file not found: {spec_path}",
                "heading": heading}, 1
    items = spec["frontmatter"].get("deferred") or []
    result = {
        "harvested": 0,
        "skipped_existing": 0,
        "ledger_created": False,
        "heading": heading,
        "deferred_in_spec": len(items),
        "dry_run": bool(dry_run),
    }
    if not items:
        return result, 0  # nothing to harvest: never create/touch the ledger

    spec_basename = os.path.basename(spec_path)
    seen = _existing_keys(ledger_path, "ledger") | _existing_keys(archive_path, "archive")
    new_entries = []
    for item in items:
        lines = render_harvest_entry(spec_basename, item)
        fields = extract_fields(lines)
        key = dedupe_key(fields["source_spec"], fields["summary"],
                         fields["evidence"], fields["location"])
        if key in seen:
            result["skipped_existing"] += 1
            continue
        seen.add(key)
        new_entries.append({"heading": heading, "text": "\n".join(lines)})
    result["harvested"] = len(new_entries)

    ledger_exists = os.path.isfile(ledger_path)
    text = _read_ledger_text(ledger_path, "ledger") if ledger_exists else ""
    if not new_entries:
        # Everything was already recorded: nothing is written, so no file was
        # created either (`ledger_created` stays false).
        return result, 0
    if text.strip():
        segments, _entries, next_section = parse_document(text)
    else:  # absent or blank: start from a titled document
        segments = [{"kind": "text", "section": None, "lines": [LEDGER_TITLE]}]
        next_section = 0
    _insert_entries(segments, next_section, new_entries)
    if not dry_run:
        _atomic_write(ledger_path, render(segments))
        # True ONLY when this run actually created the file: never on the
        # all-skipped early exit above, and never under --dry-run.
        result["ledger_created"] = not ledger_exists
    return result, 0


# --------------------------------------------------------------------------- #
# Self-test
# --------------------------------------------------------------------------- #
_LEDGER = """\
# Deferred Work

Intro prose that must survive archiving verbatim.

- intro bullet outside any `## Deferred from:` heading — NOT an entry

## Deferred from: code review of story-1-1 (2026-03-10)

- ✅ Tidy the legacy import shim [src/old.py:3]
- RESOLVED — bump the linter baseline [tooling/lint.cfg]
- Quarantine the flaky pre-existing test [tests/t.py:9]
  - nested: needs the CI quarantine label first
- Auth hardening: token portion resolved in story 1-4; remainder owned by story 2-1
- Improve the disclosed-config docs [docs/config.md]

## Deferred from: quick-dev of story-1-2 (2026-03-18)

- Addressed in story 1-5 — paginate the admin list [src/admin.py:77]
  follow-up note that travels with the entry
- Resolved in story 1-5 — that fix also closed the flaky pre-existing test [tests/t.py:9] above
- Done in story 1-6 — bump the dep,
lazy continuation line of the same entry
- Migration partially done in story 1-6; the data backfill is still open

## Notes

Free-form notes that must survive archiving untouched.
"""

_ARCHIVE_SEED = """\
# Deferred Work — Resolved

## Deferred from: code review of story-1-1 (2026-03-10)

- ✅ Previously archived entry [src/prev.py:1]
"""

_H1 = "## Deferred from: code review of story-1-1 (2026-03-10)"
_H2 = "## Deferred from: quick-dev of story-1-2 (2026-03-18)"

# F1 fixture: a column-0 fenced block inside an entry, whose body fakes a
# heading and a bullet, followed by a REAL sibling entry; plus a fenced block
# in the intro that fakes a `## Deferred from:` heading.
_FENCED_LEDGER = """\
# Deferred Work

Intro with a fenced example that must never become a section:

```md
## Deferred from: fake intro section (2026-01-01)
- not an entry, just fence content
```

## Deferred from: code review of story-2-1 (2026-04-02)

- Resolved in story 2-2 — repro snippet kept verbatim [src/repro.py:1]
```text
## fake heading inside the fence
- fake bullet inside the fence
```
  indented note after the fence
- Open follow-up: port the repro to the e2e suite [tests/e2e.py:4]

## Notes

Outside prose that must survive.
"""

_HF = "## Deferred from: code review of story-2-1 (2026-04-02)"

# D8 fixture: bmad-build's heading-less `- source_spec:` blocks (before any
# section AND after a non-deferral heading), a plain intro bullet that must
# stay prose, and a sectioned entry — all in one ledger.
_UNSECTIONED_LEDGER = """\
# Deferred Work

- plain intro bullet — prose, never an entry

- source_spec: `/abs/impl/spec-1-2-account.md`
  summary: Legacy session store ignores TTL
  evidence: `store.get()` at src/session.py:88 has no expiry check
- source_spec: none
  summary: >-
    Split remainder: the export
    endpoint still lacks paging
  evidence: clarify-and-route split

## Deferred from: code review of story-1-1 (2026-03-10)

- Free-text review bullet [src/x.py:1]

## Notes

- notes bullet — prose
- source_spec: `spec-1-3-billing.md`
  summary: RESOLVED in story 1-4 — invoice rounding
  evidence: fixed by the money helper
"""

_HARVEST_SPEC = """\
---
title: 'Story 2.6a: Digest delivery'
status: 'done'
followup_review_recommended: false
deferred:
  - summary: >-
      Legacy session store ignores TTL
    evidence: |-
      `store.get()` at src/session.py:88 has no expiry check;
      the "ttl" column is written but never read.
    location: >-
      src/session.py:88
    severity: medium
  - summary: >-
      Duplicate email check is case-sensitive
    evidence: |-
      users table has no lower(email) index.
  - summary: >-
      Duplicate   email check is CASE-sensitive
    evidence: |-
      repeated within the spec (whitespace/case variant)
---

body
"""

_HARVEST_SPEC_EMPTY = """\
---
title: 'Story 2.7: Nothing deferred'
status: 'done'
deferred: []
---

body
"""


def _run_self_test():
    import contextlib
    import io

    failures = []

    def check(name, cond):
        if not cond:
            failures.append(name)

    def run_main(argv):
        buf = io.StringIO()
        try:  # capture stderr too: argparse usage noise is expected output here
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
                code = main(argv)
        except SystemExit as exc:
            code = exc.code
        return code, buf.getvalue()

    def read(path):
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()

    with tempfile.TemporaryDirectory() as td:
        def fresh(name):
            p = os.path.join(td, name)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(_LEDGER)
            return p

        # ---- plan: ids, headings, hint classification --------------------- #
        la = fresh("ledger-a.md")
        plan = build_plan(la)
        check("plan: ledger present", plan["ledger_present"] is True)
        check("plan: 9 entries (intro bullet excluded)", len(plan["entries"]) == 9)
        check("plan: ids are document order", [e["id"] for e in plan["entries"]] == list(range(9)))
        check("plan: heading attached", plan["entries"][0]["heading"] == _H1)
        check("plan: second section heading", plan["entries"][5]["heading"] == _H2)
        hints = [e["marker_hint"] for e in plan["entries"]]
        check("hint: leading checkmark => resolved", hints[0] == "resolved")
        check("hint: RESOLVED word => resolved", hints[1] == "resolved")
        check("hint: unmarked => open", hints[2] == "open")
        check("hint: resolved-in + remainder/portion => partial", hints[3] == "partial")
        check("hint: 'disclosed' does not read as 'closed'", hints[4] == "open")
        check("hint: addressed-in => resolved", hints[5] == "resolved")
        check("hint: resolved/closed, no remainder => resolved", hints[6] == "resolved")
        check("hint: done-in + lazy continuation => resolved", hints[7] == "resolved")
        check("hint: partially + still-open => partial", hints[8] == "partial")
        # The trap: entry 6 says it "closed the flaky pre-existing test" — that
        # vouches only for ITSELF; entry 2 (the flaky test) must stay open.
        check("hint: other entry vouching never resolves this one", hints[2] == "open")
        check("plan: nested bullet kept in text", "nested: needs the CI" in plan["entries"][2]["text"])
        check("plan: lazy continuation kept in text", "lazy continuation" in plan["entries"][7]["text"])

        # ---- archive: absent archive file gets created with a title ------- #
        arch_a = os.path.join(td, "resolved-a.md")
        res, code = do_archive(la, arch_a, [0, 0], plan["ledger_sha256"])  # dupes dedupe
        check("create: exit 0", code == 0)
        check("create: moved 1 (duplicate ids deduped)", res["moved"] == 1)
        check("create: nothing already archived", res["deduped"] == 0)
        check("create: one heading created", res["headings_created"] == 1)
        check("create: no heading removed", res["headings_removed"] == 0)
        arch_text = read(arch_a)
        check("create: archive starts with H1 title", arch_text.startswith(ARCHIVE_TITLE + "\n"))
        check("create: heading appended", _H1 in arch_text)
        check("create: entry moved in", "Tidy the legacy import shim" in arch_text)
        check("create: entry gone from ledger", "Tidy the legacy" not in read(la))
        check("create: sha-after matches disk",
              res["ledger_sha256_after"] == hashlib.sha256(read(la).encode("utf-8")).hexdigest())

        # ---- archive preserves the ledger's file mode (mkstemp is 0600) --- #
        import stat as _stat
        lm = fresh("ledger-mode.md")
        wide = _stat.S_IRUSR | _stat.S_IWUSR | _stat.S_IRGRP | _stat.S_IWGRP | _stat.S_IROTH
        os.chmod(lm, wide)
        pm = build_plan(lm)
        res, code = do_archive(lm, os.path.join(td, "resolved-mode.md"), [0], pm["ledger_sha256"])
        check("mode: exit 0", code == 0)
        check("mode: ledger mode preserved", os.stat(lm).st_mode & 0o7777 == wide)

        # ---- archive: multi-heading move, reuse + creation, emptied heading #
        lb = fresh("ledger-b.md")
        arch_b = os.path.join(td, "resolved-b.md")
        with open(arch_b, "w", encoding="utf-8") as fh:
            fh.write(_ARCHIVE_SEED)
        sha_b = build_plan(lb)["ledger_sha256"]
        res, code = do_archive(lb, arch_b, [7, 0, 6, 1, 5, 8], sha_b)  # shuffled ids
        check("move: exit 0", code == 0)
        check("move: moved 6", res["moved"] == 6)
        check("move: reused story-1-1 heading, created quick-dev", res["headings_created"] == 1)
        check("move: emptied quick-dev heading removed", res["headings_removed"] == 1)
        led = read(lb)
        check("move: ledger title preserved", led.startswith("# Deferred Work\n"))
        check("move: intro prose preserved", "Intro prose that must survive" in led)
        check("move: intro bullet preserved", "intro bullet outside any" in led)
        check("move: kept heading stays", _H1 in led)
        check("move: emptied heading dropped", _H2 not in led)
        check("move: open entry kept (with nested line)",
              "Quarantine the flaky" in led and "nested: needs the CI" in led)
        check("move: partial entry kept", "Auth hardening" in led)
        check("move: other open entry kept", "disclosed-config" in led)
        check("move: moved entries gone",
              "Tidy the legacy" not in led and "bump the linter" not in led
              and "lazy continuation" not in led)
        check("move: trailing non-deferral section untouched",
              "## Notes" in led and "Free-form notes that must survive" in led)
        check("move: sha-after matches disk",
              res["ledger_sha256_after"] == hashlib.sha256(led.encode("utf-8")).hexdigest())
        arch = read(arch_b)
        check("reuse: identical heading not duplicated", arch.count(_H1) == 1)
        check("reuse: appended after existing entries",
              arch.index("Previously archived") < arch.index("Tidy the legacy"))
        check("create: new heading appears once", arch.count(_H2) == 1)
        check("order: document order despite shuffled --ids",
              arch.index("Addressed in story 1-5")
              < arch.index("Done in story 1-6")
              < arch.index("Migration partially"))
        check("move: continuation lines travel",
              "follow-up note that travels" in arch and "lazy continuation line" in arch)

        # ---- idempotency: re-planning shows the entries gone -------------- #
        replan = build_plan(lb)
        check("replan: 3 entries remain", len(replan["entries"]) == 3)
        check("replan: ids renumbered in document order",
              [e["id"] for e in replan["entries"]] == [0, 1, 2])
        check("replan: hints open/partial/open",
              [e["marker_hint"] for e in replan["entries"]] == ["open", "partial", "open"])

        # ---- F1: fenced code blocks never split or truncate entries ------- #
        lf1 = os.path.join(td, "ledger-fenced.md")
        with open(lf1, "w", encoding="utf-8") as fh:
            fh.write(_FENCED_LEDGER)
        pf = build_plan(lf1)
        check("fence: exactly the two real entries", len(pf["entries"]) == 2)
        check("fence: intro fence never becomes a section",
              all(e["heading"] == _HF for e in pf["entries"]))
        e0 = pf["entries"][0]["text"] if len(pf["entries"]) == 2 else ""
        check("fence: fake heading stays inside the entry",
              "## fake heading inside the fence" in e0)
        check("fence: fake bullet stays inside the entry",
              "- fake bullet inside the fence" in e0)
        check("fence: continuation after the closing fence kept",
              "indented note after the fence" in e0)
        check("fence: sibling entry visible after the fence",
              len(pf["entries"]) == 2
              and "Open follow-up: port the repro" in pf["entries"][1]["text"])
        check("fence: hints unaffected by fence content",
              [e["marker_hint"] for e in pf["entries"]] == ["resolved", "open"])
        arch_f1 = os.path.join(td, "resolved-fenced.md")
        res, code = do_archive(lf1, arch_f1, [0], pf["ledger_sha256"])
        check("fence archive: exit 0, moved 1", code == 0 and res["moved"] == 1)
        led = read(lf1)
        check("fence archive: heading kept (sibling remains)", _HF in led)
        check("fence archive: sibling untouched", "Open follow-up: port the repro" in led)
        check("fence archive: intro fence preserved verbatim",
              "## Deferred from: fake intro section (2026-01-01)" in led)
        check("fence archive: moved entry fully gone",
              "repro snippet" not in led and "fake heading inside" not in led)
        arch_f1_text = read(arch_f1)
        check("fence archive: entry moved whole (fence + tail)",
              "## fake heading inside the fence" in arch_f1_text
              and "- fake bullet inside the fence" in arch_f1_text
              and "indented note after the fence" in arch_f1_text)
        aplan = build_plan(arch_f1)
        check("fence archive: archive re-parses as one whole entry",
              len(aplan["entries"]) == 1
              and "fake bullet inside the fence" in aplan["entries"][0]["text"])

        # ---- F1: fence close rules + unclosed fence runs to EOF ----------- #
        _segs, ents, _ = parse_document(
            _HF + "\n\n- fence closed by a longer fence\n```\nbody\n`````\n- sibling after close\n"
        )
        check("fence: longer same-char fence closes", len(ents) == 2)
        lf2 = os.path.join(td, "ledger-unclosed.md")
        with open(lf2, "w", encoding="utf-8") as fh:
            fh.write(
                "# Deferred Work\n\n"
                + _HF + "\n\n"
                "- Entry with an unclosed fence\n"
                "````\n"
                "~~~\n"  # wrong fence char: not a close
                "```\n"  # too short for a 4-backtick fence: not a close
                "## swallowed heading\n"
                "- swallowed bullet\n"
            )
        pu = build_plan(lf2)
        check("unclosed fence: single entry runs to EOF",
              len(pu["entries"]) == 1
              and "## swallowed heading" in pu["entries"][0]["text"]
              and "- swallowed bullet" in pu["entries"][0]["text"])

        # ---- a fence opened on the entry's OWN bullet line (`- ```py`) ----- #
        # Without tracking it, the closing line would read as an OPENER and the
        # sibling entry + everything to EOF would be swallowed into entry 0.
        _segs, ents, _ = parse_document(
            _HF + "\n\n"
            "- ```py\n"
            "  print('repro')\n"
            "  ```\n"
            "- Sibling entry still visible\n"
        )
        check("bullet fence: sibling survives", len(ents) == 2)
        check("bullet fence: fence body stays in entry 0",
              "print('repro')" in ents[0]["text"]
              and "Sibling entry" in ents[1]["text"])
        # Same shape in the intro (outside any section): the closing line must
        # not flip fence state and hide the real section heading that follows.
        _segs, ents, _ = parse_document(
            "# Deferred Work\n\n- ```\n  intro fence\n  ```\n\n"
            + _HF + "\n\n- Real entry\n"
        )
        check("intro bullet fence: section still parses", len(ents) == 1
              and "Real entry" in ents[0]["text"])
        # The SAME inversion at 1-3 spaces of indent (regression): a bullet
        # fence indented 1 space inside an entry, closed at 3 spaces. The old
        # column-0-only bullet-fence rule left the opener untracked while the
        # closer matched the opener regex — everything to EOF (live sibling,
        # next section, its entry) was swallowed into entry 0.
        _segs, ents, _ = parse_document(
            _HF + "\n\n"
            "- Entry with an indented bullet fence:\n"
            " - ```py\n"
            "   print('repro')\n"
            "   ```\n"
            "- Live sibling entry one\n\n"
            "## Deferred from: quick-dev (2026-03-20)\n\n"
            "- Live entry two\n"
        )
        check("indented bullet fence: all three entries survive", len(ents) == 3)
        check("indented bullet fence: fence body stays in entry 0",
              "print('repro')" in ents[0]["text"]
              and "Live sibling entry one" in ents[1]["text"]
              and "Live entry two" in ents[2]["text"])
        # And in the intro: ' - ```md' at indent 1 must not invert state and
        # hide the real heading that follows.
        _segs, ents, _ = parse_document(
            "# Deferred Work\n\n - ```md\n   intro fence\n   ```\n\n"
            + _HF + "\n\n- Real entry\n"
        )
        check("indented intro bullet fence: section still parses",
              len(ents) == 1 and "Real entry" in ents[0]["text"])
        # A NESTED bullet fence (indent >= 2, closer at the nested content
        # indent) is tracked too: its fenced fake bullet/heading stay inside
        # the entry and the sibling survives.
        _segs, ents, _ = parse_document(
            _HF + "\n\n"
            "- Entry with a nested fence:\n"
            "  - ```\n"
            "    - fake bullet in nested fence\n"
            "    ## fake heading in nested fence\n"
            "    ```\n"
            "- Sibling entry\n"
        )
        check("nested bullet fence: sibling survives, fakes stay inside",
              len(ents) == 2
              and "fake bullet in nested fence" in ents[0]["text"]
              and "fake heading in nested fence" in ents[0]["text"]
              and "Sibling entry" in ents[1]["text"])
        # An inline code SPAN is not a fence (CommonMark: a backtick fence's
        # info string may not contain backticks) — neither on a bullet line
        # nor on a continuation line.
        _segs, ents, _ = parse_document(
            _HF + "\n\n"
            "- ```fix``` the rendering bug\n"
            "  note: see ```render()``` for context\n"
            "- Sibling entry\n"
        )
        check("inline code span: not a fence, sibling survives",
              len(ents) == 2 and "Sibling entry" in ents[1]["text"])

        # ---- a DEEPER heading inside a section is structure, not a boundary - #
        _segs, ents, _ = parse_document(
            _HF + "\n\n"
            "- Entry before the subheading\n\n"
            "### context subheading\n\n"
            "- Entry after the subheading\n\n"
            "## Notes\n\n"
            "- not an entry (same-level heading closed the section)\n"
        )
        check("subheading: entries on both sides counted", len(ents) == 2)
        check("subheading: both attach to the deferral heading",
              all(e["heading"] == _HF for e in ents))
        lsub = os.path.join(td, "ledger-subheading.md")
        with open(lsub, "w", encoding="utf-8") as fh:
            fh.write(
                "# Deferred Work\n\n" + _HF + "\n\n"
                "- ✅ Resolved entry before the subheading\n\n"
                "### context subheading\n\n"
                "- Open entry after the subheading\n"
            )
        psub = build_plan(lsub)
        res, code = do_archive(lsub, os.path.join(td, "resolved-sub.md"), [0],
                               psub["ledger_sha256"])
        led_sub = read(lsub)
        check("subheading archive: open entry and subheading survive",
              code == 0 and "### context subheading" in led_sub
              and "Open entry after" in led_sub
              and "Resolved entry" not in led_sub)

        # ---- F2: crash-recovery re-run dedupes the archive ----------------- #
        lf3 = fresh("ledger-f2.md")
        arch_f3 = os.path.join(td, "resolved-f2.md")
        sha_f3 = build_plan(lf3)["ledger_sha256"]
        pre_crash = read(lf3)
        res, code = do_archive(lf3, arch_f3, [1], sha_f3)
        check("crash: first run inserts (no dedupe)", code == 0 and res["deduped"] == 0)
        # Simulate a crash between the archive write and the ledger write:
        # the entry sits in BOTH files and the ledger sha still matches.
        with open(lf3, "w", encoding="utf-8") as fh:
            fh.write(pre_crash)
        res, code = do_archive(lf3, arch_f3, [1], sha_f3)
        check("crash rerun: exit 0", code == 0)
        check("crash rerun: still reported moved", res["moved"] == 1)
        check("crash rerun: reported deduped", res["deduped"] == 1)
        check("crash rerun: no new heading", res["headings_created"] == 0)
        arch_f3_text = read(arch_f3)
        check("crash rerun: exactly one archived copy",
              arch_f3_text.count("bump the linter baseline") == 1)
        check("crash rerun: ledger entry removed", "bump the linter" not in read(lf3))
        # Dedupe match is trailing-whitespace-normalized.
        with open(lf3, "w", encoding="utf-8") as fh:
            fh.write(pre_crash)
        with open(arch_f3, "w", encoding="utf-8") as fh:
            fh.write(arch_f3_text.replace("baseline [tooling/lint.cfg]",
                                          "baseline [tooling/lint.cfg]  "))
        res, code = do_archive(lf3, arch_f3, [1], sha_f3)
        check("crash rerun: trailing-whitespace tolerant",
              code == 0 and res["deduped"] == 1
              and read(arch_f3).count("bump the linter baseline") == 1)

        # ---- refusals: stale sha, unknown id — no writes ------------------ #
        lc = fresh("ledger-c.md")
        arch_c = os.path.join(td, "resolved-c.md")
        before = read(lc)
        res, code = do_archive(lc, arch_c, [0], "0" * 64)
        check("stale sha: exit 1", code == 1 and "stale" in res["error"])
        check("stale sha: ledger untouched", read(lc) == before)
        check("stale sha: archive not created", not os.path.exists(arch_c))
        sha_c = build_plan(lc)["ledger_sha256"]
        res, code = do_archive(lc, arch_c, [0, 42], sha_c)
        check("unknown id: exit 1", code == 1 and "unknown" in res["error"])
        check("unknown id: ledger untouched", read(lc) == before)
        check("unknown id: archive not created", not os.path.exists(arch_c))

        # ---- absent / empty ledger ---------------------------------------- #
        gone = os.path.join(td, "no-such-ledger.md")
        p = build_plan(gone)
        check("absent: not present, no entries, null sha",
              p == {"ledger_present": False, "ledger_sha256": None, "entries": []})
        res, code = do_archive(gone, arch_c, [0], "0" * 64)
        check("absent: archive refuses", code == 1)
        empty = os.path.join(td, "empty.md")
        with open(empty, "w", encoding="utf-8") as fh:
            fh.write("\n\n")
        pe = build_plan(empty)
        check("empty: not present, no entries",
              pe["ledger_present"] is False and pe["entries"] == [])


        # ---- D8: heading-less bmad-build blocks are entries ---------------- #
        lu = os.path.join(td, "ledger-unsectioned.md")
        with open(lu, "w", encoding="utf-8") as fh:
            fh.write(_UNSECTIONED_LEDGER)
        pu2 = build_plan(lu)
        check("unsectioned: 4 entries (2 before, 1 sectioned, 1 after Notes)",
              len(pu2["entries"]) == 4)
        heads = [e["heading"] for e in pu2["entries"]]
        check("unsectioned: synthetic heading on heading-less entries",
              heads[0] == SYNTHETIC_HEADING and heads[1] == SYNTHETIC_HEADING
              and heads[3] == SYNTHETIC_HEADING)
        check("unsectioned: sectioned entry keeps its real heading", heads[2] == _H1)
        check("unsectioned: plain intro/notes bullets are not entries",
              not any("plain intro bullet" in e["text"] or "notes bullet" in e["text"]
                      for e in pu2["entries"]))
        check("plan: source_spec unwrapped from backticks",
              pu2["entries"][0]["source_spec"] == "/abs/impl/spec-1-2-account.md")
        check("plan: summary parsed", pu2["entries"][0]["summary"] == "Legacy session store ignores TTL")
        check("plan: source_spec none literal", pu2["entries"][1]["source_spec"] == "none")
        check("plan: block-scalar summary folded",
              pu2["entries"][1]["summary"] == "Split remainder: the export endpoint still lacks paging")
        check("plan: free-text bullet has null fields",
              pu2["entries"][2]["source_spec"] is None and pu2["entries"][2]["summary"] is None)
        check("plan: hints on unsectioned entries",
              [e["marker_hint"] for e in pu2["entries"]] == ["open", "open", "open", "resolved"])
        arch_u = os.path.join(td, "resolved-unsectioned.md")
        res, code = do_archive(lu, arch_u, [3], pu2["ledger_sha256"])
        check("unsectioned archive: exit 0, moved 1, no heading removed",
              code == 0 and res["moved"] == 1 and res["headings_removed"] == 0
              and res["headings_created"] == 1)
        led_u = read(lu)
        check("unsectioned archive: entry gone, prose + siblings intact",
              "invoice rounding" not in led_u and "notes bullet — prose" in led_u
              and "plain intro bullet" in led_u and "ignores TTL" in led_u
              and "Free-text review bullet" in led_u and "## Notes" in led_u)
        arch_u_text = read(arch_u)
        check("unsectioned archive: literal synthetic heading in archive",
              SYNTHETIC_HEADING in arch_u_text and "invoice rounding" in arch_u_text)
        aplan_u = build_plan(arch_u)
        check("unsectioned archive: re-parses under the same heading",
              len(aplan_u["entries"]) == 1 and aplan_u["entries"][0]["heading"] == SYNTHETIC_HEADING
              and aplan_u["entries"][0]["source_spec"] == "spec-1-3-billing.md")
        # Moving BOTH remaining synthetic entries + the sectioned one: the real
        # heading is dropped, the synthetic ones have none to drop.
        pu3 = build_plan(lu)
        res, code = do_archive(lu, arch_u, [0, 1, 2], pu3["ledger_sha256"])
        check("unsectioned archive: only the real emptied heading counted",
              code == 0 and res["moved"] == 3 and res["headings_removed"] == 1)
        check("unsectioned archive: ledger keeps title/prose only",
              build_plan(lu)["entries"] == [] and "plain intro bullet" in read(lu))
        check("unsectioned archive: archive reuses synthetic heading once",
              read(arch_u).count(SYNTHETIC_HEADING) == 1)
        # A `- source_spec:` block appended AFTER a harvested/real heading is an
        # entry of that section (documented), not a synthetic one.
        _segs, ents, _ = parse_document(
            _HF + "\n\n- source_spec: `s.md`\n  summary: in section\n  evidence: e\n")
        check("source_spec inside a section: real heading",
              len(ents) == 1 and ents[0]["heading"] == _HF and ents[0]["summary"] == "in section")
        # A `- source_spec:` line inside an intro fence is fence text.
        _segs, ents, _ = parse_document(
            "# T\n\n```\n- source_spec: `x.md`\n  summary: fenced\n```\n")
        check("source_spec inside a fence: not an entry", ents == [])
        # extract_fields: fields below a fence are ignored; quoted value unwrapped.
        ef = extract_fields(["- ```", "  summary: fenced", "  ```"])
        check("extract_fields: nothing before the fence ⇒ nulls",
              ef == {"source_spec": None, "summary": None, "evidence": None, "location": None})
        ef = extract_fields(['- source_spec: "spec-9.md"', "  summary: |-", "    two", "    lines",
                             "  evidence: `x.py:1`", "  location: src/x.py:1"])
        check("extract_fields: quotes stripped, literal block folded, dedupe fields read",
              ef == {"source_spec": "spec-9.md", "summary": "two lines",
                     "evidence": "x.py:1", "location": "src/x.py:1"})

        # ---- harvest: lockstep with story_plan.py ------------------------- #
        sp_mod = None
        try:
            sp_mod = _load_story_plan()
        except FileNotFoundError:
            pass
        check("harvest lockstep: story_plan.py importable next to this script", sp_mod is not None)
        check("harvest lockstep: read_spec + parse_frontmatter exported",
              sp_mod is not None and callable(getattr(sp_mod, "read_spec", None))
              and callable(getattr(sp_mod, "parse_frontmatter", None)))
        spec_p = os.path.join(td, "spec-2-6a-digest-delivery.md")
        with open(spec_p, "w", encoding="utf-8") as fh:
            fh.write(_HARVEST_SPEC)
        if sp_mod is not None:
            sp_read = sp_mod.read_spec(spec_p)
            check("harvest lockstep: spec deferred items carry the four keys",
                  sp_read["frontmatter"]["deferred_count"] == 3
                  and set(sp_read["frontmatter"]["deferred"][0]) == {"summary", "evidence", "location", "severity"})
        hl = os.path.join(td, "harvest", "deferred-work.md")
        harch = os.path.join(td, "harvest", "deferred-work-resolved.md")
        heading = HARVEST_HEADING_TMPL.format(key="2-6a-digest-delivery", date="2026-08-16")
        # Empty `deferred: []` ⇒ no-op, ledger NOT created.
        spec_e = os.path.join(td, "spec-2-7-nothing.md")
        with open(spec_e, "w", encoding="utf-8") as fh:
            fh.write(_HARVEST_SPEC_EMPTY)
        res, code = do_harvest(hl, spec_e, "2-7-nothing", date="2026-08-16")
        check("harvest empty: exit 0, zero counts, ledger not created",
              code == 0 and res["harvested"] == 0 and res["deferred_in_spec"] == 0
              and res["ledger_created"] is False and not os.path.exists(hl))
        # Missing spec ⇒ exit 1.
        res, code = do_harvest(hl, os.path.join(td, "no-spec.md"), "2-6a-digest-delivery")
        check("harvest missing spec: exit 1 + error", code == 1 and "error" in res and not os.path.exists(hl))
        # Missing story_plan.py sibling ⇒ FileNotFoundError ⇒ harvest exit 1.
        try:
            _load_story_plan(os.path.join(td, "no-story-plan.py"))
            check("harvest: missing story_plan.py raises", False)
        except FileNotFoundError:
            pass
        # Dry run: counts computed, nothing written.
        res, code = do_harvest(hl, spec_p, "2-6a-digest-delivery", date="2026-08-16", dry_run=True)
        check("harvest dry-run: counts + no file, ledger_created false (nothing was created)",
              code == 0 and res["harvested"] == 2 and res["skipped_existing"] == 1
              and res["ledger_created"] is False and res["dry_run"] is True and not os.path.exists(hl))
        # Real run: ledger created with title + heading + 2 entries (spec-internal dupe skipped).
        res, code = do_harvest(hl, spec_p, "2-6a-digest-delivery", date="2026-08-16")
        check("harvest create: exit 0, harvested 2, skipped 1, ledger_created",
              code == 0 and res == {"harvested": 2, "skipped_existing": 1, "ledger_created": True,
                                    "heading": heading, "deferred_in_spec": 3, "dry_run": False})
        hl_text = read(hl)
        check("harvest create: title + heading + entries",
              hl_text.startswith(LEDGER_TITLE + "\n") and hl_text.count(heading) == 1
              and "- source_spec: `spec-2-6a-digest-delivery.md`" in hl_text)
        check("harvest create: evidence folded to one line, optional fields present",
              "  evidence: `store.get()` at src/session.py:88 has no expiry check; the \"ttl\" column is written but never read." in hl_text
              and "  location: src/session.py:88" in hl_text and "  severity: medium" in hl_text)
        check("harvest create: optional fields absent when missing",
              hl_text.count("  location:") == 1 and hl_text.count("  severity:") == 1)
        hp = build_plan(hl)
        check("harvest create: plan reads 2 entries under the harvest heading",
              len(hp["entries"]) == 2 and all(e["heading"] == heading for e in hp["entries"])
              and hp["entries"][1]["summary"] == "Duplicate email check is case-sensitive"
              and hp["entries"][0]["source_spec"] == "spec-2-6a-digest-delivery.md")
        # Idempotent re-run: nothing harvested, file byte-identical.
        res, code = do_harvest(hl, spec_p, "2-6a-digest-delivery", date="2026-08-16")
        check("harvest rerun: idempotent",
              code == 0 and res["harvested"] == 0 and res["skipped_existing"] == 3
              and res["ledger_created"] is False and read(hl) == hl_text)
        # A later date ⇒ nothing new to write, so no new heading either.
        res, code = do_harvest(hl, spec_p, "2-6a-digest-delivery", date="2026-08-17")
        check("harvest rerun (new date): still nothing written", read(hl) == hl_text and res["harvested"] == 0)
        # New spec item ⇒ appended under the SAME (reused) heading.
        with open(spec_p, "a", encoding="utf-8") as fh:
            pass
        spec_more = _HARVEST_SPEC.replace(
            "---\n\nbody", "  - summary: >-\n      Third finding\n    evidence: |-\n      e3\n---\n\nbody")
        with open(spec_p, "w", encoding="utf-8") as fh:
            fh.write(spec_more)
        res, code = do_harvest(hl, spec_p, "2-6a-digest-delivery", date="2026-08-16")
        check("harvest more: one new item, heading reused",
              code == 0 and res["harvested"] == 1 and res["skipped_existing"] == 3
              and read(hl).count(heading) == 1 and "summary: Third finding" in read(hl))
        check("harvest more: appended after the earlier entries",
              read(hl).index("Duplicate email") < read(hl).index("Third finding"))
        # New date + new item ⇒ a second heading is created at EOF.
        spec_more2 = spec_more.replace(
            "---\n\nbody", "  - summary: >-\n      Fourth finding\n    evidence: |-\n      e4\n---\n\nbody")
        with open(spec_p, "w", encoding="utf-8") as fh:
            fh.write(spec_more2)
        res, code = do_harvest(hl, spec_p, "2-6a-digest-delivery", date="2026-08-17")
        h2 = HARVEST_HEADING_TMPL.format(key="2-6a-digest-delivery", date="2026-08-17")
        t = read(hl)
        check("harvest new date: second heading created at EOF, one entry",
              res["harvested"] == 1 and t.count(h2) == 1 and t.index(heading) < t.index(h2)
              and t.rstrip().endswith("evidence: e4"))
        # An item already archived (moved to the sibling archive) is skipped.
        hp = build_plan(hl)
        fourth = [e["id"] for e in hp["entries"] if "Fourth" in e["text"]]
        res, code = do_archive(hl, harch, fourth, hp["ledger_sha256"])
        check("harvest archive-dedupe: item archived", code == 0 and "Fourth" not in read(hl))
        res, code = do_harvest(hl, spec_p, "2-6a-digest-delivery", date="2026-08-18")
        check("harvest archive-dedupe: archived item not re-harvested",
              res["harvested"] == 0 and res["skipped_existing"] == 5 and "Fourth" not in read(hl))
        # A bmad-build heading-less block (absolute path, backticks) already
        # in the ledger dedupes against the harvest by basename + summary.
        hl2 = os.path.join(td, "harvest2", "deferred-work.md")
        os.makedirs(os.path.dirname(hl2))
        with open(hl2, "w", encoding="utf-8") as fh:
            fh.write("# Deferred Work\n\n- source_spec: `/abs/impl/spec-2-6a-digest-delivery.md`\n"
                     "  summary:   legacy SESSION store ignores ttl\n  evidence: e\n")
        res, code = do_harvest(hl2, spec_p, "2-6a-digest-delivery", date="2026-08-16")
        check("harvest vs bmad-build block: basename + normalized summary dedupe",
              code == 0 and res["harvested"] == 3 and res["skipped_existing"] == 2)
        t2 = read(hl2)
        check("harvest vs bmad-build block: unsectioned block preserved, heading appended after",
              t2.startswith("# Deferred Work\n\n- source_spec: `/abs/impl/")
              and t2.index("legacy SESSION") < t2.index(heading))
        # A blank existing ledger gets the title; not counted as created.
        hl3 = os.path.join(td, "harvest3", "deferred-work.md")
        os.makedirs(os.path.dirname(hl3))
        with open(hl3, "w", encoding="utf-8") as fh:
            fh.write("\n")
        res, code = do_harvest(hl3, spec_p, "2-6a-digest-delivery", date="2026-08-16")
        check("harvest blank ledger: titled, not reported created",
              code == 0 and res["ledger_created"] is False and read(hl3).startswith(LEDGER_TITLE + "\n"))
        # Explicit --archive path is honoured for the dedupe.
        alt_arch = os.path.join(td, "alt-archive.md")
        with open(alt_arch, "w", encoding="utf-8") as fh:
            fh.write(ARCHIVE_TITLE + "\n\n" + heading + "\n\n- source_spec: `spec-2-6a-digest-delivery.md`\n"
                     "  summary: Third finding\n  evidence: e3\n")
        hl4 = os.path.join(td, "harvest4", "deferred-work.md")
        res, code = do_harvest(hl4, spec_p, "2-6a-digest-delivery", archive_path=alt_arch, date="2026-08-16")
        check("harvest --archive: explicit archive dedupes",
              code == 0 and res["harvested"] == 3 and res["skipped_existing"] == 2
              and "Third finding" not in read(hl4))
        # ---- ledger_created: true ONLY on a real creation ----------------- #
        # Every item already archived ⇒ nothing written ⇒ no file created.
        skip_spec = os.path.join(td, "spec-3-1-allskipped.md")
        with open(skip_spec, "w", encoding="utf-8") as fh:
            fh.write("---\nstatus: done\ndeferred:\n  - summary: >-\n      Only finding\n"
                     "    evidence: |-\n      e\n---\n\nbody\n")
        skip_arch = os.path.join(td, "allskipped-archive.md")
        with open(skip_arch, "w", encoding="utf-8") as fh:
            fh.write(ARCHIVE_TITLE + "\n\n" + SYNTHETIC_HEADING
                     + "\n\n- source_spec: `spec-3-1-allskipped.md`\n"
                       "  summary: Only finding\n  evidence: e\n")
        hl5 = os.path.join(td, "harvest5", "deferred-work.md")
        res, code = do_harvest(hl5, skip_spec, "3-1-allskipped", archive_path=skip_arch,
                               date="2026-08-16")
        check("harvest all-skipped on a missing ledger: ledger_created false, no file",
              code == 0 and res["harvested"] == 0 and res["skipped_existing"] == 1
              and res["ledger_created"] is False and not os.path.exists(hl5))

        # ---- summary-less items keep their own identity ------------------- #
        blank_spec = os.path.join(td, "spec-3-2-nosummary.md")
        with open(blank_spec, "w", encoding="utf-8") as fh:
            fh.write("---\nstatus: done\ndeferred:\n"
                     "  - evidence: |-\n      first evidence line\n    location: src/a.py:1\n"
                     "  - evidence: |-\n      second evidence line\n    location: src/b.py:2\n"
                     "  - evidence: |-\n      first evidence line\n    location: src/a.py:1\n"
                     "---\n\nbody\n")
        hl6 = os.path.join(td, "harvest6", "deferred-work.md")
        res, code = do_harvest(hl6, blank_spec, "3-2-nosummary", date="2026-08-16")
        check("harvest summary-less: distinct evidence ⇒ two entries, exact dupe skipped",
              code == 0 and res["harvested"] == 2 and res["skipped_existing"] == 1)
        t6 = read(hl6)
        check("harvest summary-less: both items written under the placeholder summary",
              t6.count("summary: " + NO_SUMMARY) == 2
              and "first evidence line" in t6 and "second evidence line" in t6)
        res, code = do_harvest(hl6, blank_spec, "3-2-nosummary", date="2026-08-16")
        check("harvest summary-less: re-run is idempotent against the ledger",
              code == 0 and res["harvested"] == 0 and res["skipped_existing"] == 3
              and read(hl6) == t6)
        check("dedupe_key: summary-less items differ by evidence/location",
              dedupe_key("s.md", None, "e1", "l") != dedupe_key("s.md", None, "e2", "l")
              and dedupe_key("s.md", None, "e1", "l1") != dedupe_key("s.md", None, "e1", "l2")
              and dedupe_key("s.md", NO_SUMMARY, "e1") == dedupe_key("s.md", "  ", " E1 "))

        # ---- unreadable / directory paths: JSON error + exit 1 ------------ #
        bad_ledger = os.path.join(td, "bad-ledger.md")
        with open(bad_ledger, "wb") as fh:
            fh.write(b"# Deferred Work\n\n- source_spec: caf\xe9\n")
        r = build_plan(bad_ledger)
        check("plan non-UTF-8 ledger: error dict, no traceback",
              "error" in r and "UTF-8" in r["error"])
        code, out = run_main(["plan", "--ledger", bad_ledger])
        check("cli plan non-UTF-8 ledger: exit 1 + JSON error",
              code == 1 and "error" in json.loads(out))
        a_dir = os.path.join(td, "a-directory")
        os.makedirs(a_dir)
        code, out = run_main(["plan", "--ledger", a_dir])
        check("cli plan --ledger is a directory: exit 1 + JSON error",
              code == 1 and "directory" in json.loads(out)["error"])
        res, code = do_harvest(a_dir, spec_p, "2-6a-digest-delivery", date="2026-08-16")
        check("harvest --ledger is a directory: exit 1 + error",
              code == 1 and "directory" in res["error"] and res["heading"])
        res, code = do_harvest(bad_ledger, spec_p, "2-6a-digest-delivery", date="2026-08-16")
        with open(bad_ledger, "rb") as fh:
            check("harvest non-UTF-8 ledger: exit 1 + error, file untouched",
                  code == 1 and "UTF-8" in res["error"] and fh.read().endswith(b"caf\xe9\n"))
        bad_arch = os.path.join(td, "bad-archive.md")
        with open(bad_arch, "wb") as fh:
            fh.write(b"# Deferred Work \xff\n")
        hl7 = os.path.join(td, "harvest7", "deferred-work.md")
        res, code = do_harvest(hl7, spec_p, "2-6a-digest-delivery", archive_path=bad_arch,
                               date="2026-08-16")
        check("harvest non-UTF-8 archive: exit 1 + error, no ledger created",
              code == 1 and "UTF-8" in res["error"] and not os.path.exists(hl7))
        bad_spec = os.path.join(td, "spec-3-3-bad.md")
        with open(bad_spec, "wb") as fh:
            fh.write(b"---\nstatus: done\n---\n\xff\n")
        hl8 = os.path.join(td, "harvest8", "deferred-work.md")
        res, code = do_harvest(hl8, bad_spec, "3-3-bad", date="2026-08-16")
        check("harvest non-UTF-8 spec: exit 1 + error, no ledger created",
              code == 1 and "UTF-8" in res["error"] and not os.path.exists(hl8))
        lz = fresh("ledger-z.md")
        pz = build_plan(lz)
        res, code = do_archive(a_dir, os.path.join(td, "arch-z.md"), [0], pz["ledger_sha256"])
        check("archive --ledger is a directory: exit 1 + error",
              code == 1 and "directory" in res["error"])
        res, code = do_archive(lz, bad_arch, [0], pz["ledger_sha256"])
        check("archive non-UTF-8 archive: exit 1 + error, ledger untouched",
              code == 1 and "UTF-8" in res["error"] and read(lz) == _LEDGER)
        res, code = do_archive(lz, a_dir, [0], pz["ledger_sha256"])
        check("archive --archive is a directory: exit 1 + error, ledger untouched",
              code == 1 and "directory" in res["error"] and read(lz) == _LEDGER)

        # dedupe_key: free-text bullets never collide.
        check("dedupe_key: null for free text", dedupe_key(None, None) is None)
        check("dedupe_key: basename + casefold + fold",
              dedupe_key("`/a/b/spec-1.md`", "  Foo   BAR ") == ("spec-1.md", "foo bar"))

        # ---- CLI surface ---------------------------------------------------#
        code, out = run_main(["plan", "--ledger", la])
        check("cli plan: exit 0 + valid JSON",
              code == 0 and json.loads(out)["ledger_present"] is True)
        code, _ = run_main([])
        check("cli: no sub-command => usage exit 2", code == 2)
        code, _ = run_main(["plan"])
        check("cli: plan without --ledger => exit 2", code == 2)
        code, _ = run_main(
            ["archive", "--ledger", lc, "--archive", arch_c, "--ids", "a,b", "--expect-sha", sha_c]
        )
        check("cli: malformed --ids => exit 2", code == 2)
        code, out = run_main(
            ["archive", "--ledger", lc, "--archive", arch_c, "--ids", "0", "--expect-sha", "0" * 64]
        )
        check("cli: stale sha => exit 1 + JSON error",
              code == 1 and "error" in json.loads(out))

        code, out = run_main(["harvest", "--ledger", os.path.join(td, "cli", "deferred-work.md"),
                              "--spec", spec_p, "--story-key", "2-6a-digest-delivery",
                              "--date", "2026-08-16"])
        check("cli harvest: exit 0 + JSON counts",
              code == 0 and json.loads(out)["harvested"] == 4)
        code, out = run_main(["harvest", "--ledger", os.path.join(td, "cli", "deferred-work.md"),
                              "--spec", spec_p, "--story-key", "2-6a-digest-delivery",
                              "--date", "2026-08-16", "--dry-run"])
        check("cli harvest --dry-run: idempotent counts",
              code == 0 and json.loads(out)["harvested"] == 0 and json.loads(out)["dry_run"] is True)
        code, _ = run_main(["harvest", "--ledger", hl, "--story-key", "k"])
        check("cli harvest: missing --spec => exit 2", code == 2)
        code, _ = run_main(["harvest", "--ledger", hl, "--spec", spec_p, "--story-key", "k",
                            "--date", "16-08-2026"])
        check("cli harvest: malformed --date => exit 2", code == 2)
        code, out = run_main(["harvest", "--ledger", hl, "--spec", os.path.join(td, "nope.md"),
                              "--story-key", "k"])
        check("cli harvest: missing spec => exit 1 + JSON error",
              code == 1 and "error" in json.loads(out))

    if failures:
        print("SELF-TEST FAILED:", ", ".join(failures), file=sys.stderr)
        return 1
    print("SELF-TEST PASSED (all assertions)")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="auto-bmad deferred-work ledger mechanics (plan / archive / harvest)"
    )
    parser.add_argument("--self-test", action="store_true", help="run built-in fixtures and exit")
    sub = parser.add_subparsers(dest="cmd")
    p_plan = sub.add_parser("plan", help="read-only: parse the ledger into entries + marker hints")
    p_plan.add_argument("--ledger", required=True, help="path to the active deferred-work.md")
    p_arch = sub.add_parser("archive", help="atomically move chosen entries ledger -> archive")
    p_arch.add_argument("--ledger", required=True, help="path to the active deferred-work.md")
    p_arch.add_argument("--archive", required=True, help="path to deferred-work-resolved.md")
    p_arch.add_argument("--ids", required=True, help="comma-separated entry ids from `plan`")
    p_arch.add_argument("--expect-sha", required=True, help="`ledger_sha256` from `plan`")
    p_harv = sub.add_parser("harvest", help="append a spec's frontmatter `deferred:` items to the ledger")
    p_harv.add_argument("--ledger", required=True, help="path to the active deferred-work.md")
    p_harv.add_argument("--spec", required=True, help="path to the story's bmad-build-auto spec")
    p_harv.add_argument("--story-key", required=True, help="sprint-status story key (heading only)")
    p_harv.add_argument("--archive", default=None,
                        help="archive to dedupe against (default: sibling deferred-work-resolved.md)")
    p_harv.add_argument("--date", default=None, help="heading date YYYY-MM-DD (default: today)")
    p_harv.add_argument("--dry-run", action="store_true", help="compute counts, write nothing")
    args = parser.parse_args(argv)

    if args.self_test:
        return _run_self_test()
    if args.cmd == "plan":
        result = build_plan(args.ledger)
        print(json.dumps(result, indent=2))
        return 1 if "error" in result else 0
    if args.cmd == "archive":
        try:
            ids = [int(token.strip()) for token in args.ids.split(",") if token.strip()]
            if not ids:
                raise ValueError
        except ValueError:
            parser.error("--ids must be a non-empty comma-separated list of integers")
        result, code = do_archive(args.ledger, args.archive, ids, args.expect_sha)
        print(json.dumps(result, indent=2))
        return code
    if args.cmd == "harvest":
        if args.date is not None and not _DATE_RE.match(args.date):
            parser.error("--date must be YYYY-MM-DD")
        if not args.story_key.strip():
            parser.error("--story-key must be non-empty")
        result, code = do_harvest(args.ledger, args.spec, args.story_key.strip(),
                                  archive_path=args.archive, date=args.date,
                                  dry_run=args.dry_run)
        print(json.dumps(result, indent=2))
        return code
    parser.error("a sub-command is required: plan | archive | harvest (or --self-test)")


if __name__ == "__main__":
    raise SystemExit(main())
