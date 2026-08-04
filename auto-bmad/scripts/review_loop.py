#!/usr/bin/env python3
"""Deterministic Phase 7 code-review loop driver for the orchestrator.

Phase 7's control flow — build the review diff, gate each pass's findings into
continue/exit/halt, and verify each fix pass actually closed its items — is a
decision table, not judgment. This script encodes it so the orchestrator calls
a tool and OBEYS the answer instead of re-deriving the rules from prose every
iteration. The table below is the normative contract; the ``--self-test`` pins
every row.

Four modes, each emitting ONE JSON object on stdout:

* ``prep-diff`` (live, git): create a throwaway temp dir OUTSIDE the work tree
  (``tempfile.mkdtemp``), write the branch diff ``git diff --no-ext-diff
  --no-color <base>...HEAD`` — run inside ``--project-root``, output pinned to
  a plain unified diff (immune to user ``diff.external``/``color.diff``
  config), with the review exclude pathspecs baked in (``_bmad``,
  ``_bmad-output`` and, in root-matching glob magic, ``**/__pycache__/**``,
  ``**/*.pyc``, ``**/.DS_Store``) — to ``<tmp>/diff.patch``, and reserve the
  lens-output paths for all three reviewer slots
  (``lens_paths.{primary|secondary|tertiary}.{blind|edge|auditor}`` — reserved
  PATHS only, the files are NOT created; the lens delegates write them; the
  orchestrator uses only the slots whose reviewer is configured in
  ``phase_profiles``). The orchestrator routes the returned paths to the
  fan-out delegates and never reads the diff itself ("no code inspection at
  any tier"). Output: ``{review_tmp, diff_file, lens_paths, diff_empty, base,
  head_sha}``. ``diff_empty: true`` means there is nothing to review — the
  orchestrator treats it as a perfectly clean 0-finding pass with 0 failed
  lenses (gate row 2).

* ``gate`` (pure decision, no I/O beyond reading the findings): decide what
  the loop does after a review pass. ``--findings-json`` is the VERBATIM JSON
  of ``review_findings.py`` at gate time (``-`` = stdin); the keys consumed
  are ``open_nondeferred``, ``open_crit_high``, ``open_severity.medium`` and
  ``open_severity.untagged``. Derived: ``clean`` = ``open_nondeferred == 0``;
  ``converged`` = ``open_crit_high == 0 AND open_severity.untagged == 0 AND
  (open_nondeferred <= 3 OR open_severity.medium == 0)`` — a small pass
  (≤ 3 non-deferred, none Critical/High), OR a pass whose open non-deferred
  findings are ALL Low severity, any count (an untagged finding is treated as
  Critical/High — conservative). A review pass fans out the three lenses once
  per configured reviewer (primary + optional secondary/tertiary), so
  ``--lenses-total`` is 3, 6 or 9 and ``--lenses-failed`` counts genuinely
  failed lenses across ALL reviewers: an errored / ``needs-human`` delegate,
  or an artifact that is absent, unreadable, or neither a finding list nor
  the canonical clean marker (a blank file is not the marker). A well-formed
  zero-finding artifact is a completed lens, not a failure. It is a count of
  DISTINCT lenses — a lens failing two ways is one. Decision table (``i`` =
  1-based ``--iteration``; cap = ``i`` reaching ``--max-iterations``; ``M`` =
  ``--lenses-total``):

  | # | i   | lenses-failed | findings            | cap? | action           | convergence_unverified |
  |---|-----|---------------|---------------------|------|------------------|------------------------|
  | 1 | any | M (all)       | —                   | —    | needs-human      | input (unchanged)       |
  | 2 | 1   | 0             | clean               | —    | exit-clean       | false (or input true)   |
  | 3 | 1   | 0             | not clean           | no   | continue         | false/input             |
  | 4 | 1   | 1..M-1        | any (untrustworthy) | no   | continue         | false/input             |
  | 5 | 1   | any < M       | any                 | yes  | → rows 6/7/9     | per row                 |
  | 6 | ≥2  | 0             | converged           | —    | exit-clean       | false/input             |
  | 7 | ≥2  | 1..M-1        | converged           | —    | exit-unconverged | true                    |
  | 8 | ≥2  | < M           | not converged       | no   | continue         | false/input             |
  | 9 | ≥2  | < M           | not converged       | yes  | exit-unconverged | true                    |

  Semantics:
  - Row 2 is the ONLY first-pass early exit: "perfectly clean" = 0 non-deferred
    findings AND every lens ran. Any other first pass pulls the mandatory
    second opinion (rows 3–4) — a Low-only first pass included (the Low-only
    convergence arm applies to final iterations only) — unless the cap blocks
    it (``max_iterations: 1``, row 5): the cap is explicit consent to a
    single-pass review, so the lone pass is judged by the final-iteration
    rules 6/7/9 — a converged pass with all lenses exits clean; only an
    unconverged or lens-incomplete one exits as an unverified draft.
  - Row 7: a converged pass with a genuinely failed lens is the same flavor of
    unverified-ness as a cap exit — its ``reason`` carries the "incomplete
    review (only N/M lenses ran)" caveat for the report and halt summary.
  - On an exit-* action the OUTPUT ``convergence_unverified`` alone decides
    the Phase 7 step-4 HITL halt: false → skip the halt (a clean convergence
    always auto-continues, no config knob), true → halt. ``needs-human`` is a
    hard stop (there is no halt to skip).
  - ``--convergence-unverified true`` is a pre-existing STICKY flag (e.g. set
    by an earlier event): the output value is ``input OR what this decision
    sets`` — the gate can NEVER clear it, and a sticky true forces the halt
    even on rows 2/6.
  - The decision IS the result: exit 0 whatever the action (2 only on
    usage/bad JSON). Defensive: an iteration OVERSHOOTING ``--max-iterations``
    still counts as capped (the loop exits; it can never spin past the cap).
  - The step-4 halt may grant a ONE-iteration user extension: the orchestrator
    re-enters with ``--iteration i+1 --max-iterations i+1`` and a cleared
    sticky flag (the exit's ``true`` is what the extension re-verifies), so
    the extended pass is always judged as a final iteration (rows 6/7/9).
    Nothing changes in this script — the extension is pure inputs.

* ``converged`` (pure): the convergence rule ALONE, for the Phase 7
  external-change re-review at the HITL halt: the external changes are
  ``meaningful`` (re-open the halt) iff the re-review's findings are NOT
  converged — the same rule, same verbatim ``review_findings.py`` input as the
  gate, so the threshold lives only here, never in orchestrator prose. Output:
  ``{converged, meaningful, open_nondeferred, open_crit_high, untagged, reason}``.

* ``post-fix`` (pure): verify a fix delegate's work from a POST-FIX re-run of
  ``review_findings.py``. Expectation: ``open_patch == 0 AND open_decision ==
  0`` (the fix resolves every patch plus every human-resolved decision;
  deferred/dismissed items are checked off or re-tagged, so they no longer
  count as open). Met → ``proceed``. Unmet → ``retry-fix`` (one re-delegation
  of the `code-review fix` entry; it does not consume a loop iteration) or,
  when ``--retry-used`` is present, ``needs-human``. This guarantees the next
  gate's open counts are attributable to the next review pass, not a half-done
  fix. Output: ``{action, open_patch, open_decision, reason}``.

Usage:
    review_loop.py prep-diff --project-root DIR --base BRANCH
    review_loop.py gate --findings-json -|FILE --iteration I --max-iterations M \\
        --lenses-failed 0..T --lenses-total 3|6|9 [--convergence-unverified true|false]
    review_loop.py post-fix --findings-json -|FILE [--retry-used]
    review_loop.py converged --findings-json -|FILE
    review_loop.py --self-test

Exit codes: 0 = success (gate/post-fix: the decision is the result, whatever
it says); 2 = usage error, unreadable/invalid findings JSON, or (prep-diff) a
failed git command. Dependency-free (stdlib only).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

# The exclude pathspecs baked into the review diff. Passed as single argv
# tokens straight to git (never through a shell), so there is no glob hazard.
# The wildcard ones use ``:(exclude,glob)`` magic: under glob (wildmatch
# pathname) semantics a leading ``**/`` matches in ALL directories INCLUDING
# the repo root, whereas default fnmatch never matches root-level files
# (verified live: a committed root ``.DS_Store``/``*.pyc`` leaked without it).
# ``__pycache__`` needs the trailing ``/**`` because glob ``*`` stops at
# slashes — ``**/__pycache__`` alone matches the directory NAME, never the
# files inside it.
EXCLUDE_PATHSPECS = (
    ":(exclude)_bmad",
    ":(exclude)_bmad-output",
    ":(exclude,glob)**/__pycache__/**",
    ":(exclude,glob)**/*.pyc",
    ":(exclude,glob)**/.DS_Store",
)
DIFF_FILENAME = "diff.patch"
# Reserved lens-output files inside review_tmp (paths only, never created
# here — the lens delegates write them): blind/auditor emit markdown lists,
# edge emits a JSON array (delegation.md → code-review (fan-out)). One set of
# three per reviewer slot — the orchestrator uses only the slots whose
# reviewer is configured (a blank phase_profiles value disables the slot).
REVIEWER_SLOTS = ("primary", "secondary", "tertiary")
LENSES = (("blind", "md"), ("edge", "json"), ("auditor", "md"))

CONVERGENCE_MAX_FINDINGS = 3
VALID_LENS_TOTALS = (3, 6, 9)  # 3 lenses x 1..3 configured reviewers


# --------------------------------------------------------------------------- #
# prep-diff
# --------------------------------------------------------------------------- #
def build_diff_argv(base: str) -> list:
    """Pure argv builder for the review diff. Three-dot = exactly what this
    branch changed since it diverged from base. ``--no-ext-diff --no-color``
    pin the output to a plain unified diff: a user ``diff.external`` (e.g.
    difftastic) would otherwise silently replace it with external-tool output
    (exit 0!), and ``color.diff=always`` would embed ANSI escapes."""
    return ["git", "diff", "--no-ext-diff", "--no-color", f"{base}...HEAD", "--", *EXCLUDE_PATHSPECS]


def build_head_argv() -> list:
    return ["git", "rev-parse", "HEAD"]


def _default_runner(argv, cwd):
    """Run argv in cwd; return (returncode, stdout_bytes, stderr_text).

    stdout stays BYTES so a diff with non-UTF-8 hunks is written verbatim.
    """
    proc = subprocess.run(argv, cwd=cwd, capture_output=True)
    return proc.returncode, proc.stdout, proc.stderr.decode("utf-8", "replace")


def prep_diff(project_root: str, base: str, runner=_default_runner, mkdtemp=tempfile.mkdtemp) -> dict:
    """Build the review diff in a fresh temp dir OUTSIDE the work tree.

    Returns the success dict (the prep-diff JSON contract) or
    ``{"status": "error", "message": ...}`` when git fails. The temp dir is
    only created AFTER both git commands succeed, so a failure leaks nothing.
    """
    try:
        rc, head_out, err = runner(build_head_argv(), project_root)
        if rc != 0:
            return {"status": "error",
                    "message": f"git rev-parse HEAD failed in {project_root!r} (exit {rc}): {err.strip()[:300]}"}
        rc, diff_out, err = runner(build_diff_argv(base), project_root)
        if rc != 0:
            return {"status": "error",
                    "message": f"git diff {base}...HEAD failed in {project_root!r} (exit {rc}): {err.strip()[:300]}"}
    except OSError as exc:
        return {"status": "error", "message": f"could not run git in {project_root!r}: {exc}"}

    review_tmp = mkdtemp(prefix="auto-bmad-review-")
    diff_file = os.path.join(review_tmp, DIFF_FILENAME)
    with open(diff_file, "wb") as fh:
        fh.write(diff_out)

    result = {
        "review_tmp": review_tmp,
        "diff_file": diff_file,
        "lens_paths": {
            slot: {lens: os.path.join(review_tmp, f"{lens}-{slot}.{ext}")
                   for lens, ext in LENSES}
            for slot in REVIEWER_SLOTS
        },
        # The dedicated per-story security review (auto-bmad-local) is single-instance — one
        # delegate per iteration, NOT per reviewer — so it gets ONE reserved path, outside the
        # 3xR lens_paths grid. Its findings flow into triage on the severity channel (they gate
        # convergence via open_crit_high), so it is NOT counted in --lenses-total. Reserved only;
        # the security delegate writes it.
        "security_path": os.path.join(review_tmp, "security.md"),
        # The verification-gap review (upstream bmad-review-verification-gap, run single-instance —
        # auto-bmad's roster treatment, like security) also gets ONE reserved path outside the lens
        # grid. It reports verification gaps with NO severity; triage assigns severity, so its
        # findings gate convergence through the same channel and it too is NOT in --lenses-total.
        # Reserved only; the verification-gap delegate writes it.
        "verification_path": os.path.join(review_tmp, "verification.md"),
    }
    result["diff_empty"] = not diff_out.strip()
    result["base"] = base
    result["head_sha"] = head_out.decode("utf-8", "replace").strip()
    return result


# --------------------------------------------------------------------------- #
# gate
# --------------------------------------------------------------------------- #
def _findings_int(findings, *path):
    node = findings
    for key in path:
        try:
            node = node[key]
        except (KeyError, TypeError) as exc:
            raise ValueError(
                f"findings JSON is missing review_findings.py key {'.'.join(path)!r}"
            ) from exc
    try:
        return int(node)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"findings key {'.'.join(path)!r} is not an integer: {node!r}") from exc


def _is_converged(nondef: int, crit_high: int, untagged: int, medium: int) -> bool:
    """THE convergence rule — the only place it is encoded (the gate and the
    ``converged`` mode both call this; the docs say to call, never re-derive).
    Converged = nothing Critical/High/untagged AND (a small pass — ≤ 3
    non-deferred — OR a Low-only pass: 0 Medium, any count of Lows)."""
    return crit_high == 0 and untagged == 0 and (
        nondef <= CONVERGENCE_MAX_FINDINGS or medium == 0)


def _convergence_desc(nondef: int) -> str:
    """Which convergence arm a converged pass satisfied, for the reason string."""
    if nondef > CONVERGENCE_MAX_FINDINGS:
        return f"all {nondef} non-deferred findings Low severity, 0 Critical/High, 0 untagged"
    return f"{nondef} non-deferred ≤ {CONVERGENCE_MAX_FINDINGS}, 0 Critical/High, 0 untagged"


def _nonconvergence_why(nondef: int, crit_high: int, untagged: int, medium: int) -> str:
    parts = []
    if crit_high:
        parts.append(f"{crit_high} Critical/High")
    if untagged:
        parts.append(f"{untagged} untagged (treated as Critical/High)")
    if nondef > CONVERGENCE_MAX_FINDINGS and medium:
        parts.append(f"{nondef} non-deferred findings > {CONVERGENCE_MAX_FINDINGS} "
                     f"and not Low-only ({medium} Medium)")
    return ", ".join(parts) or "not converged"


def decide_gate(
    findings: dict,
    iteration: int,
    max_iterations: int,
    lenses_failed: int,
    lenses_total: int,
    convergence_unverified: bool = False,
) -> dict:
    """Encode the Phase 7 decision table. Pure; raises ValueError on bad findings."""
    nondef = _findings_int(findings, "open_nondeferred")
    crit_high = _findings_int(findings, "open_crit_high")
    untagged = _findings_int(findings, "open_severity", "untagged")
    medium = _findings_int(findings, "open_severity", "medium")

    clean = nondef == 0
    converged = _is_converged(nondef, crit_high, untagged, medium)
    lenses_ran = lenses_total - lenses_failed
    cap = iteration >= max_iterations  # >= is defensive: an overshoot still caps
    unverified = bool(convergence_unverified)  # sticky: never cleared below
    lens_caveat = f"; incomplete review (only {lenses_ran}/{lenses_total} lenses ran)" if lenses_failed else ""

    if lenses_failed >= lenses_total:  # row 1
        action = "needs-human"
        reason = (f"code review incomplete — 0/{lenses_total} lenses completed successfully; "
                  "the review did not actually happen, never count it as clean")
    elif iteration == 1 and clean and lenses_failed == 0:  # row 2
        action = "exit-clean"
        reason = ("first pass perfectly clean (0 non-deferred findings, all "
                  f"{lenses_total} lenses ran) — the only first-pass early exit; second opinion skipped")
    elif iteration == 1 and not cap:  # rows 3–4
        action = "continue"
        if lenses_failed:  # row 4 — even a 0-finding pass is untrustworthy
            reason = (f"only {lenses_ran}/{lenses_total} lenses ran — a first pass this incomplete "
                      "is not trustworthy as clean; the second opinion is mandatory")
        else:  # row 3
            reason = f"first pass found {nondef} non-deferred finding(s) — the second opinion is mandatory"
    else:
        # Rows 6–9 — final-iteration rules. Row 5 (a capped first pass,
        # max_iterations == 1) lands here too: the cap is explicit consent to a
        # single-pass review, so the lone pass is judged by the same convergence
        # rules as any other final iteration — the second opinion is mandatory
        # only when an iteration remains to run it in.
        if converged and lenses_failed == 0:  # row 6
            action = "exit-clean"
            reason = (f"pass converged ({_convergence_desc(nondef)}, "
                      f"all {lenses_total} lenses ran)")
            if iteration == 1:
                reason += " — single pass accepted as final (max_iterations == 1)"
        elif converged:  # row 7
            action = "exit-unconverged"
            unverified = True
            reason = (f"pass converged, but incomplete review (only {lenses_ran}/{lenses_total} "
                      "lenses ran) — a converged result with a missing lens is unverified")
        elif not cap:  # row 8
            action = "continue"
            reason = (f"not converged ({_nonconvergence_why(nondef, crit_high, untagged, medium)})"
                      f"{lens_caveat} — continue to iteration {iteration + 1}")
        else:  # row 9
            action = "exit-unconverged"
            unverified = True
            reason = (f"max_iterations ({max_iterations}) reached without convergence "
                      f"({_nonconvergence_why(nondef, crit_high, untagged, medium)}){lens_caveat}")

    return {
        "action": action,
        "convergence_unverified": unverified,
        "clean": clean,
        "converged": converged,
        "reason": reason,
    }


# --------------------------------------------------------------------------- #
# converged
# --------------------------------------------------------------------------- #
def decide_converged(findings: dict) -> dict:
    """The convergence rule ALONE, for the Phase 7 external-change re-review:
    the changes are 'meaningful' (re-open the halt) iff the re-review's
    findings are NOT converged. Same verbatim review_findings.py input as the
    gate; pure. Keeps CONVERGENCE_MAX_FINDINGS out of orchestrator prose."""
    nondef = _findings_int(findings, "open_nondeferred")
    crit_high = _findings_int(findings, "open_crit_high")
    untagged = _findings_int(findings, "open_severity", "untagged")
    medium = _findings_int(findings, "open_severity", "medium")
    converged = _is_converged(nondef, crit_high, untagged, medium)
    return {
        "converged": converged,
        "meaningful": not converged,
        "open_nondeferred": nondef,
        "open_crit_high": crit_high,
        "untagged": untagged,
        "medium": medium,
        "reason": (f"converged ({_convergence_desc(nondef)})" if converged
                   else _nonconvergence_why(nondef, crit_high, untagged, medium)),
    }


# --------------------------------------------------------------------------- #
# post-fix
# --------------------------------------------------------------------------- #
def decide_post_fix(findings: dict, retry_used: bool) -> dict:
    """Verify a fix pass from a post-fix re-run of review_findings.py. Pure."""
    open_patch = _findings_int(findings, "open_patch")
    open_decision = _findings_int(findings, "open_decision")
    met = open_patch == 0 and open_decision == 0
    if met:
        action = "proceed"
        reason = "fix pass verified — no open [Review][Patch] or [Review][Decision] items remain"
    elif not retry_used:
        action = "retry-fix"
        reason = (f"{open_patch} open patch + {open_decision} open decision item(s) remain — "
                  "re-delegate the `code-review fix` entry once on the still-open items "
                  "(the retry does not consume a loop iteration), then re-verify with --retry-used")
    else:
        action = "needs-human"
        reason = (f"{open_patch} open patch + {open_decision} open decision item(s) still remain "
                  "after the one fix retry — the fix delegate is not closing its items")
    return {
        "action": action,
        "open_patch": open_patch,
        "open_decision": open_decision,
        "reason": reason,
    }


# --------------------------------------------------------------------------- #
# CLI plumbing
# --------------------------------------------------------------------------- #
def _parse_bool(value: str) -> bool:
    v = value.strip().lower()
    if v == "true":
        return True
    if v == "false":
        return False
    raise argparse.ArgumentTypeError(f"expected 'true' or 'false', got {value!r}")


def _load_findings(spec: str) -> dict:
    """Read the review_findings.py JSON from a file path or stdin ('-')."""
    if spec == "-":
        raw = sys.stdin.read()
    else:
        with open(spec, "r", encoding="utf-8") as fh:
            raw = fh.read()
    data = json.loads(raw)  # ValueError on bad JSON
    if not isinstance(data, dict):
        raise ValueError("findings JSON must be a single object (review_findings.py output)")
    return data


# --------------------------------------------------------------------------- #
# Self-test
# --------------------------------------------------------------------------- #
def _f(nondef=0, crit_high=0, untagged=0, low=0):
    """A minimal review_findings.py-shaped fixture (only the keys gate reads).
    Findings not explicitly Critical/High/untagged/Low default to Medium."""
    return {
        "open_nondeferred": nondef,
        "open_crit_high": crit_high,
        "open_severity": {"critical": 0, "high": crit_high,
                          "medium": max(0, nondef - crit_high - untagged - low), "low": low,
                          "untagged": untagged},
    }


_GATE_KEYS = {"action", "convergence_unverified", "clean", "converged", "reason"}
_PREP_KEYS = {"review_tmp", "diff_file", "lens_paths", "security_path", "verification_path",
              "diff_empty", "base", "head_sha"}
_POST_FIX_KEYS = {"action", "open_patch", "open_decision", "reason"}


def _run_self_test():
    import contextlib
    import io
    import itertools
    import shutil

    failures = []

    def check(name, cond):
        if not cond:
            failures.append(name)

    # ---------------- prep-diff: pure argv builders ----------------
    argv = build_diff_argv("main")
    check("argv: git diff three-dot, plain-format pins",
          argv[:5] == ["git", "diff", "--no-ext-diff", "--no-color", "main...HEAD"])
    check("argv: pathspec separator", argv[5] == "--")
    check("argv: all five excludes, in order", tuple(argv[6:]) == EXCLUDE_PATHSPECS)
    check("argv: _bmad excluded", ":(exclude)_bmad" in argv)
    check("argv: _bmad-output excluded", ":(exclude)_bmad-output" in argv)
    check("argv: pycache excluded (glob, root-matching)", ":(exclude,glob)**/__pycache__/**" in argv)
    check("argv: pyc excluded (glob, root-matching)", ":(exclude,glob)**/*.pyc" in argv)
    check("argv: DS_Store excluded (glob, root-matching)", ":(exclude,glob)**/.DS_Store" in argv)
    check("argv: never two-dot", "main..HEAD" not in " ".join(argv).replace("main...HEAD", ""))
    check("argv: head rev-parse", build_head_argv() == ["git", "rev-parse", "HEAD"])

    # ---------------- prep-diff: injectable runner (no repo needed) ----------------
    calls = []

    def fake_runner(diff_bytes):
        def run(argv, cwd):
            calls.append((argv, cwd))
            if argv[:2] == ["git", "rev-parse"]:
                return 0, b"abc123def\n", ""
            return 0, diff_bytes, ""
        return run

    res = prep_diff("/proj", "develop", runner=fake_runner(b"diff --git a/x b/x\n+new\n"))
    check("prep: exact key set", set(res) == _PREP_KEYS)
    check("prep: base echoed", res["base"] == "develop")
    check("prep: head sha trimmed", res["head_sha"] == "abc123def")
    check("prep: non-empty diff flagged", res["diff_empty"] is False)
    check("prep: cwd is project root", all(cwd == "/proj" for _, cwd in calls))
    check("prep: tmp under OS tempdir, not the work tree",
          res["review_tmp"].startswith(tempfile.gettempdir()) and not res["review_tmp"].startswith("/proj"))
    check("prep: diff file inside review_tmp",
          res["diff_file"] == os.path.join(res["review_tmp"], DIFF_FILENAME))
    with open(res["diff_file"], "rb") as fh:
        check("prep: diff bytes written verbatim", fh.read() == b"diff --git a/x b/x\n+new\n")
    check("prep: a lens-path set per reviewer slot", set(res["lens_paths"]) == set(REVIEWER_SLOTS))
    for slot in REVIEWER_SLOTS:
        check(f"prep: {slot} slot has all three lenses",
              set(res["lens_paths"][slot]) == {lens for lens, _ in LENSES})
        for lens, ext in LENSES:
            path = res["lens_paths"][slot][lens]
            check(f"prep: {lens}-{slot} path reserved inside review_tmp",
                  path == os.path.join(res["review_tmp"], f"{lens}-{slot}.{ext}"))
            check(f"prep: {lens}-{slot} NOT created", not os.path.exists(path))
    check("prep: all 9 lens paths distinct",
          len({p for s in res["lens_paths"].values() for p in s.values()}) == 9)
    # The single-instance security review path: one reserved file, outside the lens grid, not created.
    check("prep: security_path reserved inside review_tmp",
          res["security_path"] == os.path.join(res["review_tmp"], "security.md"))
    check("prep: security_path NOT created", not os.path.exists(res["security_path"]))
    check("prep: security_path distinct from every lens path",
          res["security_path"] not in {p for s in res["lens_paths"].values() for p in s.values()})
    # The single-instance verification-gap review path: same shape as security — reserved,
    # outside the lens grid, not created, and distinct from every other reserved path.
    check("prep: verification_path reserved inside review_tmp",
          res["verification_path"] == os.path.join(res["review_tmp"], "verification.md"))
    check("prep: verification_path NOT created", not os.path.exists(res["verification_path"]))
    check("prep: verification_path distinct from every lens + security path",
          res["verification_path"] not in (
              {p for s in res["lens_paths"].values() for p in s.values()} | {res["security_path"]}))
    shutil.rmtree(res["review_tmp"])

    # Empty diff: file still written (empty), diff_empty true.
    res_e = prep_diff("/proj", "develop", runner=fake_runner(b""))
    check("prep: empty diff flagged", res_e["diff_empty"] is True)
    check("prep: empty diff file written", os.path.getsize(res_e["diff_file"]) == 0)
    shutil.rmtree(res_e["review_tmp"])

    # Git failure: error dict, and no temp dir was created (nothing to leak).
    made = []

    def spy_mkdtemp(prefix):
        made.append(prefix)
        return tempfile.mkdtemp(prefix=prefix)

    def fail_runner(argv, cwd):
        if argv[:2] == ["git", "rev-parse"]:
            return 0, b"abc\n", ""
        return 128, b"", "fatal: bad revision 'nope...HEAD'"

    bad = prep_diff("/proj", "nope", runner=fail_runner, mkdtemp=spy_mkdtemp)
    check("prep: git diff failure => error", bad.get("status") == "error" and "git diff" in bad["message"])
    check("prep: no temp dir on failure", made == [])
    bad2 = prep_diff("/proj", "main",
                     runner=lambda a, c: (128, b"", "fatal: not a git repository"), mkdtemp=spy_mkdtemp)
    check("prep: rev-parse failure => error", bad2.get("status") == "error" and "rev-parse" in bad2["message"])
    check("prep: OSError => error",
          prep_diff("/no/such/dir-xyz", "main").get("status") == "error")

    # ---------------- prep-diff: real temp git repo (git is available) ----------------
    if shutil.which("git"):
        repo = tempfile.mkdtemp(prefix="review_loop_repo_")

        def git(*args):
            subprocess.run(
                ["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@example.com",
                 "-c", "commit.gpgsign=false", *args],
                check=True, capture_output=True)

        def put(rel, text):
            path = os.path.join(repo, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)

        git("init", "-q")
        put("a.txt", "base\n")
        git("add", "-A")
        git("commit", "-q", "-m", "base")
        git("branch", "-M", "main")
        git("checkout", "-q", "-b", "feature")
        put("src/b.txt", "needle-line\n")
        put("_bmad/inside.txt", "excluded-bmad-needle\n")
        put("pkg/__pycache__/mod.pyc", "excluded-pyc-needle\n")
        put("pkg/__pycache__/mod.cache", "excluded-pycache-other-needle\n")
        # Root-level junk: under default fnmatch a leading **/ never matched
        # the repo root — these two leaked into the diff before glob magic.
        put(".DS_Store", "excluded-root-dsstore-needle\n")
        put("root.pyc", "excluded-root-pyc-needle\n")
        git("add", "-A", "-f")
        git("commit", "-q", "-m", "feature work")
        # Hostile user diff config: an external diff tool (difftastic-style)
        # and forced color would corrupt the patch unless prep-diff pins the
        # output format with --no-ext-diff --no-color.
        git("config", "diff.external", "echo EXTERNAL-DIFF")
        git("config", "color.diff", "always")

        live = prep_diff(repo, "main")
        check("live: succeeds", live.get("status") != "error")
        if live.get("status") != "error":
            check("live: exact key set", set(live) == _PREP_KEYS)
            check("live: diff not empty", live["diff_empty"] is False)
            with open(live["diff_file"], "r", encoding="utf-8") as fh:
                patch = fh.read()
            check("live: real change in diff", "needle-line" in patch and "src/b.txt" in patch)
            check("live: plain unified diff despite diff.external", patch.startswith("diff --git"))
            check("live: no external-tool output", "EXTERNAL-DIFF" not in patch)
            check("live: no ANSI escapes despite color.diff=always", "\x1b" not in patch)
            check("live: _bmad excluded", "excluded-bmad-needle" not in patch and "_bmad" not in patch)
            check("live: pycache/pyc excluded", "excluded-pyc-needle" not in patch and ".pyc" not in patch)
            check("live: non-pyc files inside __pycache__ excluded",
                  "excluded-pycache-other-needle" not in patch and "__pycache__" not in patch)
            check("live: ROOT-level .DS_Store excluded",
                  "excluded-root-dsstore-needle" not in patch and ".DS_Store" not in patch)
            check("live: ROOT-level .pyc excluded", "excluded-root-pyc-needle" not in patch)
            head = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                                  capture_output=True, text=True, check=True).stdout.strip()
            check("live: head_sha matches rev-parse", live["head_sha"] == head)
            check("live: tmp outside the work tree", not live["review_tmp"].startswith(repo))
            check("live: lens paths not created",
                  not any(os.path.exists(p) for s in live["lens_paths"].values() for p in s.values()))
            check("live: security_path reserved, not created",
                  live["security_path"] == os.path.join(live["review_tmp"], "security.md")
                  and not os.path.exists(live["security_path"]))
            check("live: verification_path reserved, not created",
                  live["verification_path"] == os.path.join(live["review_tmp"], "verification.md")
                  and not os.path.exists(live["verification_path"]))
            shutil.rmtree(live["review_tmp"])

        empty = prep_diff(repo, "feature")  # feature...HEAD == nothing
        check("live: same-ref diff is empty", empty.get("status") != "error" and empty["diff_empty"] is True)
        if empty.get("status") != "error":
            shutil.rmtree(empty["review_tmp"])

        broken = prep_diff(repo, "no-such-branch")
        check("live: bad base => error", broken.get("status") == "error")
        # repo is reused by the prep-diff CLI round-trips below, then removed.

    # ---------------- gate: one case per decision-table row ----------------
    # (decide_gate args: findings, iteration, max_iterations, lenses_failed,
    #  lenses_total[, convergence_unverified])
    # row 1 — ALL lenses failed: hard stop, sticky flag passes through unchanged.
    o = decide_gate(_f(0), 1, 2, 3, 3)
    check("row1: needs-human", o["action"] == "needs-human")
    check("row1: reason names 0/3 lenses", "0/3 lenses completed successfully" in o["reason"])
    check("row1: unverified unchanged (false in)", o["convergence_unverified"] is False)
    o = decide_gate(_f(5, 2, 0), 2, 2, 3, 3, convergence_unverified=True)
    check("row1: unverified unchanged (true in)",
          o["action"] == "needs-human" and o["convergence_unverified"] is True)
    o = decide_gate(_f(0), 1, 2, 9, 9)  # three-reviewer roster, all nine failed
    check("row1: all 9 lenses failed => needs-human",
          o["action"] == "needs-human" and "0/9 lenses" in o["reason"])

    # row 2 — perfectly clean first pass: the only first-pass early exit.
    o = decide_gate(_f(0), 1, 2, 0, 3)
    check("row2: successful zero-finding lenses exit clean", o["action"] == "exit-clean")
    check("row2: unverified false", o["convergence_unverified"] is False)
    check("row2: clean+converged flags", o["clean"] is True and o["converged"] is True)
    o = decide_gate(_f(0), 1, 1, 0, 3)  # max_iterations == 1, perfectly clean
    check("row2: clean single pass at max==1 still exits clean (non-draft)",
          o["action"] == "exit-clean" and o["convergence_unverified"] is False)
    # invariant: empty diff == row 2 (an all-zero findings JSON + 0 failed lenses).
    o = decide_gate(_f(0, 0, 0), 1, 2, 0, 6)
    check("row2: empty-diff zeros land here (two-reviewer roster)",
          o["action"] == "exit-clean" and "all 6 lenses ran" in o["reason"])
    # invariant: a sticky input true survives even a perfectly clean pass.
    o = decide_gate(_f(0), 1, 2, 0, 3, convergence_unverified=True)
    check("row2: sticky true survives", o["convergence_unverified"] is True)

    # row 3 — first pass with findings: mandatory second opinion.
    o = decide_gate(_f(2), 1, 2, 0, 3)
    check("row3: continue", o["action"] == "continue")
    check("row3: unverified false", o["convergence_unverified"] is False)
    o = decide_gate(_f(1), 1, 2, 0, 3)
    check("row3: even a would-converge first pass continues", o["action"] == "continue" and o["converged"] is True)
    o = decide_gate(_f(5, low=5), 1, 2, 0, 6)
    check("row3: a Low-only first pass still pulls the second opinion",
          o["action"] == "continue" and o["converged"] is True)

    # row 4 — first pass with some (not all) lenses failed: untrustworthy even at 0 findings.
    o = decide_gate(_f(0), 1, 2, 1, 3)
    check("row4: 0-finding pass with a failed lens continues", o["action"] == "continue")
    check("row4: reason notes 2/3 lenses", "2/3" in o["reason"])
    o = decide_gate(_f(2), 1, 3, 2, 3)
    check("row4: two failed lenses also continue", o["action"] == "continue")
    check("row4: unverified false", o["convergence_unverified"] is False)
    o = decide_gate(_f(0), 1, 2, 5, 9)
    check("row4: 5 of 9 lenses failed continues, reason notes 4/9",
          o["action"] == "continue" and "4/9" in o["reason"])

    # row 5 — a capped first pass (max_iterations == 1) follows the
    # final-iteration rules 6/7/9: the cap is consent to a single-pass review.
    o = decide_gate(_f(1), 1, 1, 0, 3)  # converged, all lenses → row 6
    check("row5: converged single pass exits clean", o["action"] == "exit-clean")
    check("row5: unverified false (ships non-draft)", o["convergence_unverified"] is False)
    check("row5: reason notes single-pass acceptance", "max_iterations == 1" in o["reason"])
    o = decide_gate(_f(3), 1, 1, 0, 3)  # boundary: exactly 3 still converges
    check("row5: boundary 3 findings still converge at max==1", o["action"] == "exit-clean")
    o = decide_gate(_f(0), 1, 1, 1, 3)  # clean but a lens failed → row 7
    check("row5: missing lens at max==1 is unverified (row 7)",
          o["action"] == "exit-unconverged" and o["convergence_unverified"] is True)
    o = decide_gate(_f(4), 1, 1, 0, 3)  # not converged → row 9
    check("row5: unconverged single pass still drafts (row 9)",
          o["action"] == "exit-unconverged" and o["convergence_unverified"] is True)
    o = decide_gate(_f(1, 1, 0), 1, 1, 0, 3)  # Critical/High blocks convergence
    check("row5: Critical/High single pass still drafts", o["action"] == "exit-unconverged")
    o = decide_gate(_f(7, low=7), 1, 1, 0, 3)  # Low-only lone pass at max==1
    check("row5: Low-only single pass at max==1 exits clean", o["action"] == "exit-clean")

    # row 6 — i>=2, converged with all lenses: clean exit.
    o = decide_gate(_f(2), 2, 2, 0, 3)
    check("row6: exit-clean", o["action"] == "exit-clean")
    check("row6: unverified false", o["convergence_unverified"] is False)
    o = decide_gate(_f(3), 2, 2, 0, 3)  # boundary: exactly 3 non-deferred converges
    check("row6: boundary 3 findings converge", o["action"] == "exit-clean")
    o = decide_gate(_f(2), 2, 2, 0, 3, convergence_unverified=True)
    check("row6: sticky true survives a converged exit", o["convergence_unverified"] is True)
    # Low-only arm: a final pass whose findings are ALL Low converges, no count cap.
    o = decide_gate(_f(7, low=7), 2, 2, 0, 6)
    check("row6: Low-only pass converges with no count cap",
          o["action"] == "exit-clean" and o["converged"] is True)
    check("row6: Low-only reason names the arm",
          "all 7 non-deferred findings Low severity" in o["reason"])
    o = decide_gate(_f(4, low=3), 2, 2, 0, 3)  # 4 findings, one Medium => neither arm
    check("row6 boundary: 4 findings with one Medium do NOT converge",
          o["action"] == "exit-unconverged" and "not Low-only (1 Medium)" in o["reason"])
    o = decide_gate(_f(7, crit_high=1, low=6), 2, 3, 0, 3)
    check("row6 boundary: a Critical/High blocks the Low-only arm", o["converged"] is False)
    o = decide_gate(_f(7, untagged=1, low=6), 2, 3, 0, 3)
    check("row6 boundary: an untagged finding blocks the Low-only arm", o["converged"] is False)

    # row 7 — i>=2, converged but a lens missing: unverified exit.
    o = decide_gate(_f(1), 2, 3, 1, 3)
    check("row7: exit-unconverged", o["action"] == "exit-unconverged")
    check("row7: unverified true", o["convergence_unverified"] is True)
    check("row7: reason notes incomplete review 2/3 lenses",
          "incomplete review" in o["reason"] and "2/3" in o["reason"])
    o = decide_gate(_f(0), 2, 2, 2, 3)
    check("row7: clean-with-2-missing-lenses also unverified",
          o["action"] == "exit-unconverged" and "1/3" in o["reason"])
    o = decide_gate(_f(2, low=2), 2, 2, 3, 9)
    check("row7: converged 3-reviewer pass with 3 failed lenses is unverified",
          o["action"] == "exit-unconverged" and "6/9" in o["reason"])

    # row 8 — i>=2, not converged, below the cap: continue.
    o = decide_gate(_f(5), 2, 3, 0, 3)
    check("row8: >3 findings continue", o["action"] == "continue")
    o = decide_gate(_f(2, 1, 0), 2, 3, 0, 3)
    check("row8: Critical/High blocks convergence", o["action"] == "continue" and o["converged"] is False)
    o = decide_gate(_f(1, 0, 1), 2, 3, 1, 3)
    check("row8: untagged blocks convergence (treated as Crit/High)",
          o["action"] == "continue" and o["converged"] is False)
    check("row8: unverified false", o["convergence_unverified"] is False)
    o = decide_gate(_f(5, low=4), 2, 3, 0, 6)
    check("row8: one Medium among Lows still blocks the Low-only arm",
          o["action"] == "continue" and "not Low-only (1 Medium)" in o["reason"])

    # row 9 — i>=2, not converged, at the cap: unconverged draft exit.
    o = decide_gate(_f(4), 2, 2, 0, 3)
    check("row9: exit-unconverged", o["action"] == "exit-unconverged")
    check("row9: unverified true", o["convergence_unverified"] is True)
    o = decide_gate(_f(1, 1, 0), 2, 2, 2, 3)
    check("row9: crit/high at cap with missing lenses", o["action"] == "exit-unconverged")
    # Defensive: an overshoot (i > max) still caps — never continues past the cap.
    o = decide_gate(_f(5), 3, 2, 0, 3)
    check("row9: overshoot still exits", o["action"] == "exit-unconverged")

    # ---------------- gate: invariant sweep ----------------
    findings_variants = [(0, 0, 0, 0), (2, 0, 0, 0), (2, 1, 0, 0), (2, 0, 1, 0),
                         (5, 0, 0, 0), (5, 0, 0, 5), (5, 1, 0, 4), (7, 0, 0, 6)]
    bools = (False, True)
    for (i, m), total, fv, sticky in itertools.product(
            [(i, m) for i in (1, 2, 3) for m in (1, 2, 3) if i <= m],
            VALID_LENS_TOTALS, findings_variants, bools):
        for lf in {0, 1, total - 1, total}:
            out = decide_gate(_f(*fv), i, m, lf, total, sticky)
            tag = f"sweep i={i} m={m} lf={lf}/{total} f={fv} sticky={sticky}"
            check(f"{tag}: exact key set", set(out) == _GATE_KEYS)
            if out["action"] == "exit-unconverged":
                check(f"{tag}: exit-unconverged => unverified", out["convergence_unverified"] is True)
            if sticky:
                check(f"{tag}: sticky flag never cleared", out["convergence_unverified"] is True)
            if out["action"] == "continue":
                check(f"{tag}: continue only below the cap", i < m)
            if lf >= total:
                check(f"{tag}: all lenses failed is always needs-human", out["action"] == "needs-human")
            json.dumps(out)  # every decision must be JSON-serializable

    # Bad findings JSON shapes raise ValueError (=> exit 2 in main). The fourth
    # shape pins that open_severity.medium is now a consumed (required) key.
    for bad_findings in ({}, {"open_nondeferred": 1}, {"open_nondeferred": 1, "open_crit_high": 0},
                         {"open_nondeferred": 1, "open_crit_high": 0, "open_severity": {"untagged": 0}},
                         {"open_nondeferred": "x", "open_crit_high": 0,
                          "open_severity": {"untagged": 0, "medium": 0}}):
        try:
            decide_gate(bad_findings, 1, 2, 0, 3)
            check(f"gate: bad findings {bad_findings!r} must raise", False)
        except ValueError:
            pass

    # ---------------- post-fix ----------------
    pf = decide_post_fix({"open_patch": 0, "open_decision": 0}, retry_used=False)
    check("post-fix: expectation met => proceed", pf["action"] == "proceed")
    check("post-fix: exact key set", set(pf) == _POST_FIX_KEYS)
    check("post-fix: counts echoed", pf["open_patch"] == 0 and pf["open_decision"] == 0)
    pf = decide_post_fix({"open_patch": 0, "open_decision": 0}, retry_used=True)
    check("post-fix: met after retry still proceeds", pf["action"] == "proceed")
    pf = decide_post_fix({"open_patch": 2, "open_decision": 0}, retry_used=False)
    check("post-fix: open patch => retry-fix", pf["action"] == "retry-fix" and pf["open_patch"] == 2)
    pf = decide_post_fix({"open_patch": 0, "open_decision": 1}, retry_used=False)
    check("post-fix: open decision alone => retry-fix", pf["action"] == "retry-fix")
    pf = decide_post_fix({"open_patch": 1, "open_decision": 1}, retry_used=True)
    check("post-fix: unmet after retry => needs-human", pf["action"] == "needs-human")
    try:
        decide_post_fix({"open_patch": 1}, retry_used=False)
        check("post-fix: missing key must raise", False)
    except ValueError:
        pass

    # ---------------- converged (external-change re-review) ----------------
    cv = decide_converged(_f(CONVERGENCE_MAX_FINDINGS))
    check("converged: at the cap converges, not meaningful",
          cv["converged"] is True and cv["meaningful"] is False)
    cv = decide_converged(_f(CONVERGENCE_MAX_FINDINGS + 1))
    check("converged: over the cap is meaningful",
          cv["converged"] is False and cv["meaningful"] is True)
    cv = decide_converged(_f(1, crit_high=1))
    check("converged: any Crit/High is meaningful", cv["meaningful"] is True)
    cv = decide_converged(_f(1, untagged=1))
    check("converged: untagged treated as Crit/High", cv["meaningful"] is True
          and "untagged" in cv["reason"])
    cv = decide_converged(_f(10, low=10))
    check("converged: Low-only any-count converges, not meaningful",
          cv["converged"] is True and cv["meaningful"] is False and cv["medium"] == 0)
    cv = decide_converged(_f(10, low=9))
    check("converged: one Medium among Lows is meaningful",
          cv["meaningful"] is True and cv["medium"] == 1)
    check("converged: same rule as the gate",
          decide_converged(_f(2))["converged"]
          == decide_gate(_f(2), 2, 3, 0, 3, False)["converged"])
    check("converged: same Low-only rule as the gate",
          decide_converged(_f(7, low=7))["converged"]
          == decide_gate(_f(7, low=7), 2, 3, 0, 3, False)["converged"])
    try:
        decide_converged({"open_nondeferred": 1})
        check("converged: missing key must raise", False)
    except ValueError:
        pass

    # ---------------- main(): CLI round-trips (stdout JSON + exit codes) ----------------
    def run_main(argv, stdin_text=None):
        out, err = io.StringIO(), io.StringIO()
        old_stdin = sys.stdin
        if stdin_text is not None:
            sys.stdin = io.StringIO(stdin_text)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    rc = main(argv)
                except SystemExit as exc:  # argparse usage errors
                    rc = exc.code
        finally:
            sys.stdin = old_stdin
        return rc, out.getvalue()

    gate_args = ["gate", "--iteration", "1", "--max-iterations", "2",
                 "--lenses-failed", "0", "--lenses-total", "3"]
    rc, out = run_main(gate_args + ["--findings-json", "-"], stdin_text=json.dumps(_f(0)))
    check("cli: gate via stdin exits 0", rc == 0)
    check("cli: gate stdin decision", json.loads(out)["action"] == "exit-clean")

    ftmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    ftmp.write(json.dumps(_f(4)))
    ftmp.close()
    rc, out = run_main(["gate", "--findings-json", ftmp.name, "--iteration", "2",
                        "--max-iterations", "2", "--lenses-failed", "0", "--lenses-total", "6",
                        "--convergence-unverified", "false"])
    parsed = json.loads(out)
    check("cli: gate via file exits 0 (decision IS the result)", rc == 0)
    check("cli: gate file decision row 9", parsed["action"] == "exit-unconverged" and parsed["convergence_unverified"] is True)
    os.unlink(ftmp.name)

    rc, out = run_main(gate_args + ["--findings-json", "-"], stdin_text="not json{")
    check("cli: bad JSON exits 2", rc == 2)
    check("cli: bad JSON reports error", json.loads(out).get("status") == "error")
    rc, _ = run_main(["gate", "--findings-json", "/no/such/findings.json"] + gate_args[1:])
    check("cli: missing args usage exit 2 or file error 2", rc == 2)
    rc, _ = run_main(["gate", "--findings-json", "-", "--iteration", "0",
                      "--max-iterations", "2", "--lenses-failed", "0", "--lenses-total", "3"])
    check("cli: iteration < 1 is usage error", rc == 2)
    rc, _ = run_main(["gate", "--findings-json", "-", "--iteration", "1",
                      "--max-iterations", "2", "--lenses-failed", "4", "--lenses-total", "3"])
    check("cli: lenses-failed > lenses-total is usage error", rc == 2)
    rc, _ = run_main(["gate", "--findings-json", "-", "--iteration", "1",
                      "--max-iterations", "2", "--lenses-failed", "0", "--lenses-total", "4"])
    check("cli: lenses-total not in 3|6|9 is usage error", rc == 2)
    rc, _ = run_main(["gate", "--findings-json", "-", "--iteration", "1",
                      "--max-iterations", "2", "--lenses-failed", "0", "--lenses-total", "3",
                      "--convergence-unverified", "yes"])
    check("cli: non-true/false bool is usage error", rc == 2)
    rc, _ = run_main(gate_args + ["--findings-json", "-",
                                  "--skip-hitl-on-clean-convergence", "true"])
    check("cli: removed --skip-hitl-on-clean-convergence flag is usage error", rc == 2)

    rc, out = run_main(["post-fix", "--findings-json", "-"],
                       stdin_text=json.dumps({"open_patch": 1, "open_decision": 0}))
    check("cli: post-fix exits 0", rc == 0)
    check("cli: post-fix retry-fix", json.loads(out)["action"] == "retry-fix")
    rc, out = run_main(["converged", "--findings-json", "-"],
                       stdin_text=json.dumps(_f(4)))
    check("cli: converged exits 0, meaningful", rc == 0 and json.loads(out)["meaningful"] is True)
    rc, out = run_main(["post-fix", "--findings-json", "-", "--retry-used"],
                       stdin_text=json.dumps({"open_patch": 1, "open_decision": 0}))
    check("cli: post-fix --retry-used => needs-human", json.loads(out)["action"] == "needs-human" and rc == 0)
    # prep-diff round-trips: success (live repo) exits 0 with the full
    # contract; a failed prep (error dict) maps to exit 2.
    if shutil.which("git"):
        rc, out = run_main(["prep-diff", "--project-root", repo, "--base", "main"])
        parsed = json.loads(out)
        check("cli: prep-diff exits 0", rc == 0)
        check("cli: prep-diff exact key set", set(parsed) == _PREP_KEYS)
        check("cli: prep-diff diff not empty", parsed["diff_empty"] is False)
        shutil.rmtree(parsed["review_tmp"])
        rc, out = run_main(["prep-diff", "--project-root", repo, "--base", "no-such-branch"])
        check("cli: prep-diff bad base exits 2", rc == 2)
        check("cli: prep-diff bad base reports error", json.loads(out).get("status") == "error")
        shutil.rmtree(repo)
    rc, out = run_main(["prep-diff", "--project-root", "/no/such/dir-xyz", "--base", "main"])
    check("cli: prep-diff bad project root exits 2", rc == 2)
    check("cli: prep-diff bad project root reports error", json.loads(out).get("status") == "error")
    rc, _ = run_main(["prep-diff", "--base", "main"])
    check("cli: prep-diff missing --project-root is usage error", rc == 2)

    rc, _ = run_main([])
    check("cli: no mode is usage error", rc == 2)

    if failures:
        print("SELF-TEST FAILED:", ", ".join(failures), file=sys.stderr)
        return 1
    print("SELF-TEST PASSED (all assertions)")
    return 0


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main(argv=None):
    parser = argparse.ArgumentParser(description="auto-bmad Phase 7 code-review loop driver")
    parser.add_argument("--self-test", action="store_true", help="run built-in fixtures and exit")
    sub = parser.add_subparsers(dest="mode")

    p_diff = sub.add_parser("prep-diff", help="build the review diff in a temp dir outside the work tree")
    p_diff.add_argument("--project-root", required=True, help="the git work tree to diff")
    p_diff.add_argument("--base", required=True, help="git.base_branch — diffed as <base>...HEAD")

    p_gate = sub.add_parser("gate", help="decide continue/exit/halt from a pass's reconciled findings")
    p_gate.add_argument("--findings-json", required=True,
                        help="review_findings.py JSON: a file path, or '-' for stdin")
    p_gate.add_argument("--iteration", type=int, required=True, help="1-based review iteration i")
    p_gate.add_argument("--max-iterations", type=int, required=True, help="code_review.max_iterations")
    p_gate.add_argument("--lenses-failed", type=int, required=True,
                        help="how many DISTINCT lenses genuinely failed (delegate error/needs-human, "
                             "or an artifact that is absent, unreadable, or neither a finding list nor "
                             "the canonical clean marker), across ALL reviewers (0..total); a "
                             "well-formed zero-finding artifact is not failed")
    p_gate.add_argument("--lenses-total", type=int, required=True,
                        help="total lenses this pass fanned out: 3 per configured reviewer (3|6|9)")
    p_gate.add_argument("--convergence-unverified", type=_parse_bool, default=False,
                        metavar="true|false",
                        help="pre-existing sticky flag from state; the gate can set but never clear it")

    p_fix = sub.add_parser("post-fix", help="verify a fix delegate's work from a post-fix findings re-run")
    p_fix.add_argument("--findings-json", required=True,
                       help="POST-FIX review_findings.py JSON: a file path, or '-' for stdin")
    p_fix.add_argument("--retry-used", action="store_true",
                       help="the one fix retry already ran — an unmet expectation is now needs-human")

    p_conv = sub.add_parser("converged", help="the convergence rule alone — external-change "
                                              "re-review ('meaningful' = NOT converged)")
    p_conv.add_argument("--findings-json", required=True,
                        help="review_findings.py JSON of the re-review: a file path, or '-' for stdin")

    args = parser.parse_args(argv)

    if args.self_test:
        return _run_self_test()
    if not args.mode:
        parser.error("a mode is required: prep-diff | gate | post-fix | converged (or use --self-test)")

    if args.mode == "prep-diff":
        result = prep_diff(args.project_root, args.base)
        print(json.dumps(result, indent=2))
        return 2 if result.get("status") == "error" else 0

    if args.mode == "gate":
        if args.iteration < 1:
            parser.error("--iteration must be >= 1")
        if args.max_iterations < 1:
            parser.error("--max-iterations must be >= 1")
        if args.lenses_total not in VALID_LENS_TOTALS:
            parser.error(f"--lenses-total must be one of {VALID_LENS_TOTALS} (3 per configured reviewer)")
        if not 0 <= args.lenses_failed <= args.lenses_total:
            parser.error(f"--lenses-failed must be 0..{args.lenses_total} (--lenses-total)")
        try:
            findings = _load_findings(args.findings_json)
            result = decide_gate(
                findings, args.iteration, args.max_iterations,
                args.lenses_failed, args.lenses_total,
                args.convergence_unverified,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}))
            return 2
        print(json.dumps(result, indent=2))
        return 0

    # post-fix / converged (same findings-JSON plumbing)
    try:
        findings = _load_findings(args.findings_json)
        result = (decide_converged(findings) if args.mode == "converged"
                  else decide_post_fix(findings, args.retry_used))
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
