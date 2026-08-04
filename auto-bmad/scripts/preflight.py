#!/usr/bin/env python3
"""Phase 0 preflight for auto-bmad — ONE call replacing ~8 hand-rolled shell probes.

The orchestrator's Phase 0 (SKILL.md Step 1) needs a batch of environment facts
before any commit: git repo / clean tree / branch / base branch / git mode
(``remote`` vs ``local``), whether a ``project-context.md`` already exists, CI
workflow presence, required-skill availability, and (first-run only) test-framework
config detection. Each was a separate shell probe — and bare globs are fatal under
zsh/fish (``nomatch`` ⇒ exit 1; see CLAUDE.md → "Shell globs") — so this script
folds them all into one deterministic call printing ONE JSON object on stdout.
All filesystem walking is ``os.walk``/``pathlib`` (no shell, no globs).

Encoded rules (the normative definitions live in the reference docs):

* **git** (git-and-pr.md → "Mode detection (Phase 0)"):
  - ``is_repo``: ``git rev-parse --is-inside-work-tree`` succeeds.
  - ``tree_clean``: ``git status --porcelain`` output is empty;
    ``dirty_files_count`` = its non-empty line count. If the status probe FAILS
    (rc != 0 — e.g. timeout), both are ``null`` and ``status_error`` carries a
    stderr snippet — the gate fails CLOSED (hard stop), never reads as clean.
  - ``base_branch``: remote HEAD via ``git symbolic-ref refs/remotes/origin/HEAD``
    (``refs/remotes/origin/`` prefix stripped), else the current branch.
  - ``mode``: ``remote`` iff ``gh --version`` works AND ``gh auth status`` exits 0
    AND ``git remote -v`` shows a github.com remote — else ``local``.
* **project_context** (pipeline.md Phase 0 → project-context probe): finds EITHER
  upstream artifact shape and reports which as ``kind``. ``kernel`` =
  ``bmad-project-context``'s ``kernel.md`` + bundle (primary
  ``<project-knowledge>/``); ``legacy`` = ``bmad-generate-project-context``'s
  ``project-context.md`` (primary ``<output-folder>/``). Kernel wins wherever both
  exist, primaries before the fallback walk of ``--project-root`` (pruning
  ``node_modules``/``.venv``/``.git`` in-place); among same-kind hits the first in
  walk order wins. A bare ``kernel.md`` never counts — see ``_KERNEL_MARKERS``.
* **ci.workflows_present**: any ``*.yml``/``*.yaml`` under ``.github/workflows``,
  or a ``.gitlab-ci.yml`` at the project root.
* **skills**: each ``--require-skills`` name is present iff a directory of that
  name exists under ANY of ``--skills-dirs`` (the orchestrator passes the
  host-appropriate dirs); any miss → hard stop.
* **framework** (state-and-resume.md → First-run step 3; only with
  ``--detect-framework-ci``, else ``null``): project-root configs among
  ``playwright.config.*``, ``cypress.config.*``, ``jest.config.*``,
  ``vitest.config.*`` (final extension must be js/cjs/mjs/ts/cts/mts/json —
  multi-dot names like ``jest.config.e2e.js`` count, ``*.bak``/``*.orig`` don't),
  ``pytest.ini``, ``pyproject.toml`` containing ``[tool.pytest``, ``setup.cfg``
  containing ``[tool:pytest]``; ``ci_present`` mirrors ``ci.workflows_present``.
* **hard_stop** (true, with reasons) when: not a git repo; working tree state
  unknown (``git status`` failed — fail closed); dirty tree AND
  (no ``--expected-branch`` given OR ``current_branch != expected-branch``)
  — dirty ON the expected story branch is the fine resume case; detached/unknown
  HEAD even on a clean tree (a null branch poisons ``base_branch`` downstream);
  or any required skill is missing.

Structure mirrors ``cli_delegate.py``: pure classification functions over
injected probe results (``classify(...)`` takes a ``run`` callable) + a real
``subprocess`` runner, so ``--self-test`` exercises every rule with fake runners
and one real temp-git-repo end-to-end case.

Usage:
    preflight.py --project-root DIR --output-folder DIR [--project-knowledge DIR]
                 [--expected-branch NAME]
                 [--require-skills CSV --skills-dirs CSV] [--detect-framework-ci]
    preflight.py --self-test

Exit codes: 0 = ran, no hard stop; 1 = ran, hard_stop true; 2 = usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable, Sequence

_PROBE_TIMEOUT = 20  # seconds — keep short so a wedged probe can't hang preflight

# A runner takes an argv and returns (returncode, stdout, stderr).
Runner = Callable[[Sequence[str]], tuple[int, str, str]]

_WALK_EXCLUDES = {"node_modules", ".venv", ".git"}

# A `bmad-project-context` bundle is `kernel.md` plus one of these siblings:
# `.memlog.md` (init'd on every run of that skill) or `index.md` (the bundle index
# it writes before validating). Requiring the pair keeps an unrelated `kernel.md`
# from reading as project context.
_KERNEL_MARKERS = {".memlog.md", "index.md"}

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


def real_runner(argv: Sequence[str], cwd: str | None = None) -> tuple[int, str, str]:
    """Run ``argv`` via subprocess; FileNotFoundError/timeout degrade to rc=127."""
    try:
        p = subprocess.run(
            list(argv), capture_output=True, text=True, cwd=cwd, timeout=_PROBE_TIMEOUT
        )
        return p.returncode, p.stdout, p.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        return 127, "", str(e)


# --- pure classification (all probe results injected via `run`) ---

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


def _is_kernel_bundle(filenames: Iterable[str]) -> bool:
    """True iff these sibling filenames form a ``bmad-project-context`` bundle:
    ``kernel.md`` PLUS a corroborating marker (see ``_KERNEL_MARKERS``). A bare
    ``kernel.md`` is far too common a filename to trust on its own."""
    names = set(filenames)
    return "kernel.md" in names and bool(names & _KERNEL_MARKERS)


def _dir_names(d: Path) -> list[str]:
    """Filenames directly under ``d``; empty when it isn't a readable directory."""
    try:
        return [p.name for p in d.iterdir()]
    except (OSError, ValueError):
        return []


def find_project_context(
    project_root: Path,
    output_folder: Path,
    project_knowledge: Path | None = None,
) -> dict:
    """Locate an existing project-context artifact in EITHER shape and report which.

    ``kind`` is ``kernel`` for ``bmad-project-context``'s kernel+bundle system and
    ``legacy`` for a ``bmad-generate-project-context`` ``project-context.md``. The
    kernel outranks legacy wherever both exist — upstream demotes the legacy file to
    a mining source once a project migrates, so a bundle anywhere means the project
    HAS migrated and Phase 2/8 must not be handed the old vocabulary. Primaries
    first (``<project-knowledge>`` then ``<output-folder>``), else walk
    ``project_root`` (pruning node_modules/.venv/.git in-place). The walk runs to
    completion rather than stopping at the first hit, so a bundle in a
    later-sorting directory still beats an earlier ``project-context.md``; among
    same-kind hits the first in walk order wins."""
    if project_knowledge is not None and _is_kernel_bundle(_dir_names(project_knowledge)):
        return {"found": True, "path": str(project_knowledge / "kernel.md"), "kind": "kernel"}
    primary = output_folder / "project-context.md"
    if primary.is_file():
        return {"found": True, "path": str(primary), "kind": "legacy"}
    legacy: Path | None = None
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = sorted(d for d in dirnames if d not in _WALK_EXCLUDES)
        here = Path(dirpath)
        if _is_kernel_bundle(filenames):
            return {"found": True, "path": str(here / "kernel.md"), "kind": "kernel"}
        if legacy is None and "project-context.md" in filenames:
            legacy = here / "project-context.md"
    if legacy is not None:
        return {"found": True, "path": str(legacy), "kind": "legacy"}
    return {"found": False, "path": None, "kind": None}


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
    """A skill is present iff a directory of that name exists under ANY skills dir."""
    checked = [s for s in required if s]
    missing = [
        name for name in checked
        if not any((d / name).is_dir() for d in skills_dirs)
    ]
    return {"checked": checked, "missing": missing}


def detect_framework(project_root: Path, ci_present: bool) -> dict:
    """Test-framework configs at the project root (first-run flow step 3)."""
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


def classify_hard_stop(git: dict, skills: dict, expected_branch: str | None) -> tuple[bool, list[str]]:
    """Hard-stop rules: not a repo; tree state unknown (fail closed); dirty off the
    expected branch; detached/unknown HEAD; missing skills."""
    reasons: list[str] = []
    if not git["is_repo"]:
        reasons.append("not a git repo (run `git init` first — the local-branch flow needs a repo)")
    else:
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
    for name in skills["missing"]:
        reasons.append(f"required skill missing: {name}")
    return bool(reasons), reasons


def preflight(
    project_root: Path,
    output_folder: Path,
    expected_branch: str | None = None,
    require_skills: Sequence[str] = (),
    skills_dirs: Sequence[Path] = (),
    detect_framework_ci: bool = False,
    project_knowledge: Path | None = None,
    run: Runner | None = None,
) -> dict:
    """Assemble the full preflight JSON object (pure given ``run`` + a filesystem)."""
    if run is None:
        run = lambda argv: real_runner(argv, cwd=str(project_root))  # noqa: E731
    git = classify_git(run)
    ci = detect_ci(project_root)
    skills = check_skills(require_skills, skills_dirs)
    hard_stop, reasons = classify_hard_stop(git, skills, expected_branch)
    return {
        "git": git,
        "project_context": find_project_context(project_root, output_folder, project_knowledge),
        "ci": ci,
        "skills": skills,
        "framework": detect_framework(project_root, ci["workflows_present"]) if detect_framework_ci else None,
        "hard_stop": hard_stop,
        "hard_stop_reasons": reasons,
    }


# --- self-test ---

def _fake_runner(table: dict) -> Runner:
    """Map an argv (joined) to (rc, stdout, stderr); unknown commands fail rc=127."""
    def run(argv: Sequence[str]) -> tuple[int, str, str]:
        return table.get(" ".join(argv), (127, "", "unknown command"))
    return run

_GIT_OK = {
    "git rev-parse --is-inside-work-tree": (0, "true\n", ""),
    "git branch --show-current": (0, "story/1-2-auth\n", ""),
    "git status --porcelain": (0, "", ""),
    "git symbolic-ref refs/remotes/origin/HEAD": (0, "refs/remotes/origin/main\n", ""),
    "git remote -v": (0, "origin\tgit@github.com:me/repo.git (fetch)\n", ""),
    "gh --version": (0, "gh version 2.0\n", ""),
    "gh auth status": (0, "Logged in\n", ""),
}


def _run_self_test() -> int:
    import tempfile

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
    # status failure with empty stderr still surfaces the exit code.
    t = dict(_GIT_OK); t["git status --porcelain"] = (128, "", "")
    assert classify_git(_fake_runner(t))["status_error"] == "exit 128"
    # status success leaves status_error null.
    assert g["status_error"] is None and g3["status_error"] is None

    # Clean DETACHED head: branch null, tree still clean (hard-stop rule covers it).
    t = dict(_GIT_OK)
    t["git branch --show-current"] = (0, "", "")
    t["git symbolic-ref refs/remotes/origin/HEAD"] = (1, "", "no ref")
    g6 = classify_git(_fake_runner(t))
    assert g6["current_branch"] is None and g6["base_branch"] is None and g6["tree_clean"], g6

    # --- hard-stop rules ---
    skills_ok = {"checked": [], "missing": []}
    hs, r = classify_hard_stop(g4, skills_ok, None)
    assert hs and any("not a git repo" in x for x in r), r
    # Dirty + no expected branch -> stop.
    hs, r = classify_hard_stop(g3, skills_ok, None)
    assert hs and any("dirty" in x for x in r), r
    # Dirty + WRONG branch -> stop.
    hs, _ = classify_hard_stop(g3, skills_ok, "story/9-9-other")
    assert hs
    # Dirty ON the expected branch -> fine (resume case).
    hs, r = classify_hard_stop(g3, skills_ok, "story/1-2-auth")
    assert not hs and r == [], r
    # Clean tree, no expected branch -> fine.
    hs, _ = classify_hard_stop(g, skills_ok, None)
    assert not hs
    # Missing skill -> stop, even with clean git.
    hs, r = classify_hard_stop(g, {"checked": ["bmad-dev-story"], "missing": ["bmad-dev-story"]}, None)
    assert hs and any("bmad-dev-story" in x for x in r), r
    # status failure -> stop with the fail-closed reason, even on the expected branch.
    hs, r = classify_hard_stop(g5, skills_ok, None)
    assert hs and any("could not evaluate working tree" in x and "timed out" in x for x in r), r
    hs, _ = classify_hard_stop(g5, skills_ok, "story/1-2-auth")
    assert hs
    # CLEAN detached head -> stop (null base_branch would break branching/PR later).
    hs, r = classify_hard_stop(g6, skills_ok, None)
    assert hs and any("detached/unknown branch" in x for x in r), r

    # --- filesystem rules in a sandbox ---
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        out = root / "_bmad-output"
        out.mkdir()

        # project_context: nothing anywhere.
        assert find_project_context(root, out) == {"found": False, "path": None, "kind": None}
        # Excluded dirs are pruned — a hit inside node_modules does NOT count.
        nm = root / "node_modules" / "pkg"; nm.mkdir(parents=True)
        (nm / "project-context.md").write_text("x")
        (root / ".venv").mkdir(); (root / ".venv" / "project-context.md").write_text("x")
        assert find_project_context(root, out)["found"] is False
        # A BARE kernel.md is not a bundle — too common a filename to trust.
        bare = root / "kernel-docs"; bare.mkdir(); (bare / "kernel.md").write_text("x")
        assert find_project_context(root, out)["found"] is False
        # Fallback walk finds a nested legit legacy copy.
        sub = root / "docs"; sub.mkdir(); (sub / "project-context.md").write_text("x")
        pc = find_project_context(root, out)
        assert pc["found"] and pc["path"] == str(sub / "project-context.md"), pc
        assert pc["kind"] == "legacy", pc
        # kernel.md + a bundle marker DOES count, and outranks a legacy hit.
        (bare / "index.md").write_text("x")
        pc = find_project_context(root, out)
        assert pc["kind"] == "kernel" and pc["path"] == str(bare / "kernel.md"), pc
        # `.memlog.md` is the other accepted marker.
        (bare / "index.md").unlink(); (bare / ".memlog.md").write_text("x")
        assert find_project_context(root, out)["kind"] == "kernel"
        # Primary output_folder location wins over the fallback walk.
        (out / "project-context.md").write_text("x")
        pc = find_project_context(root, out)
        assert pc["path"] == str(out / "project-context.md") and pc["kind"] == "legacy", pc
        # ...but an explicit project_knowledge bundle outranks even that: upstream
        # demotes project-context.md to a mining source once a project migrates.
        pk = root / "knowledge"; pk.mkdir()
        (pk / "kernel.md").write_text("x"); (pk / ".memlog.md").write_text("x")
        pc = find_project_context(root, out, pk)
        assert pc["kind"] == "kernel" and pc["path"] == str(pk / "kernel.md"), pc
        # A project_knowledge dir that isn't a bundle (or doesn't exist) falls through.
        assert find_project_context(root, out, root / "nope")["kind"] == "legacy"

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

        # skills: present iff a dir of that name exists under ANY skills dir.
        d1 = root / ".claude" / "skills"; d2 = root / ".agents" / "skills"
        (d1 / "bmad-create-story").mkdir(parents=True)
        (d2 / "bmad-dev-story").mkdir(parents=True)
        (d1 / "bmad-fake-file").parent.mkdir(parents=True, exist_ok=True)
        (d1 / "bmad-fake-file").write_text("not a dir")  # a FILE is not a skill
        s = check_skills(["bmad-create-story", "bmad-dev-story", "bmad-tea", "bmad-fake-file"], [d1, d2])
        assert s["checked"] == ["bmad-create-story", "bmad-dev-story", "bmad-tea", "bmad-fake-file"], s
        assert s["missing"] == ["bmad-tea", "bmad-fake-file"], s
        assert check_skills([], [d1]) == {"checked": [], "missing": []}

        # framework: prefix configs + pytest markers, root-level only.
        fr = detect_framework(root, ci_present=True)
        assert fr == {"configs": [], "ci_present": True}, fr
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

        # --- full assembly with a fake runner ---
        res = preflight(
            root, out,
            require_skills=["bmad-create-story", "bmad-tea"],
            skills_dirs=[d1, d2],
            detect_framework_ci=True,
            run=_fake_runner(_GIT_OK),
        )
        assert res["git"]["mode"] == "remote" and res["ci"]["workflows_present"] is True, res
        assert res["project_context"]["found"] is True
        assert res["framework"]["ci_present"] is True and "playwright.config.ts" in res["framework"]["configs"]
        assert res["hard_stop"] is True  # bmad-tea missing
        assert res["hard_stop_reasons"] == ["required skill missing: bmad-tea"], res
        # framework omitted entirely (null) without the flag.
        res2 = preflight(root, out, require_skills=["bmad-create-story"], skills_dirs=[d1], run=_fake_runner(_GIT_OK))
        assert res2["framework"] is None and res2["hard_stop"] is False, res2
        json.dumps(res)  # must be JSON-serializable

    # --- real end-to-end: temp git repo via the real subprocess runner ---
    with tempfile.TemporaryDirectory() as td:
        root = Path(td).resolve()
        out = root / "_bmad-output"; out.mkdir()
        rc, _, err = real_runner(["git", "init", "-b", "main"], cwd=str(root))
        assert rc == 0, err
        for k, v in (("user.email", "t@t.t"), ("user.name", "t")):
            real_runner(["git", "config", k, v], cwd=str(root))
        (root / "a.txt").write_text("x")
        run = lambda argv: real_runner(argv, cwd=str(root))  # noqa: E731
        # Dirty (untracked a.txt), no remote -> hard stop, mode local, base=current=main.
        res = preflight(root, out, run=run)
        assert res["git"]["is_repo"] and res["git"]["current_branch"] == "main", res
        assert res["git"]["base_branch"] == "main" and res["git"]["github_remote"] is False, res
        assert res["git"]["mode"] == "local", res
        assert not res["git"]["tree_clean"] and res["git"]["dirty_files_count"] == 1, res
        assert res["hard_stop"] and any("dirty" in x for x in res["hard_stop_reasons"]), res
        # Same dirt, but it IS the expected branch -> resume case, no stop.
        res = preflight(root, out, expected_branch="main", run=run)
        assert res["hard_stop"] is False, res
        # Commit -> clean -> no stop.
        real_runner(["git", "add", "."], cwd=str(root))
        rc, _, err = real_runner(["git", "commit", "-m", "init", "--no-gpg-sign"], cwd=str(root))
        assert rc == 0, err
        res = preflight(root, out, run=run)
        assert res["git"]["tree_clean"] and res["hard_stop"] is False, res
        json.dumps(res)

    print("SELF-TEST PASSED (all assertions)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-call Phase 0 preflight: git, project-context, CI, skills, framework."
    )
    parser.add_argument("--self-test", action="store_true", help="Run internal tests and exit.")
    parser.add_argument("--project-root", help="Project root (cwd for git probes; walk root).")
    parser.add_argument("--output-folder", help="BMAD output_folder (primary project-context.md location).")
    parser.add_argument("--project-knowledge", help="BMAD project_knowledge dir (primary kernel.md + bundle location); optional.")
    parser.add_argument("--expected-branch", help="The story branch a dirty tree is allowed on (resume case).")
    parser.add_argument("--require-skills", default="", help="CSV of required skill dir names; any miss is a hard stop.")
    parser.add_argument("--skills-dirs", default="", help="CSV of skills dirs to search (host-appropriate, orchestrator-supplied).")
    parser.add_argument("--detect-framework-ci", action="store_true", help="Also detect test-framework configs (first-run step 3); else framework is null.")
    args = parser.parse_args()

    if args.self_test:
        return _run_self_test()

    def usage_error(msg: str) -> int:
        print(json.dumps({"status": "error", "message": msg}))
        return 2

    missing = [n for n in ("project_root", "output_folder") if not getattr(args, n)]
    if missing:
        return usage_error(f"missing required: {missing}")
    project_root = Path(args.project_root)
    if not project_root.is_dir():
        return usage_error(f"project root not a directory: {project_root}")
    require_skills = [s.strip() for s in args.require_skills.split(",") if s.strip()]
    skills_dirs = [Path(s.strip()) for s in args.skills_dirs.split(",") if s.strip()]
    if require_skills and not skills_dirs:
        return usage_error("--require-skills given without --skills-dirs")

    result = preflight(
        project_root,
        Path(args.output_folder),
        expected_branch=args.expected_branch,
        require_skills=require_skills,
        skills_dirs=skills_dirs,
        detect_framework_ci=args.detect_framework_ci,
        project_knowledge=Path(args.project_knowledge) if args.project_knowledge else None,
    )
    print(json.dumps(result, indent=2))
    return 1 if result["hard_stop"] else 0


if __name__ == "__main__":
    sys.exit(main())
