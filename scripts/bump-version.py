#!/usr/bin/env python3
"""Bump auto-bmad's version: promote the changelog, sync every version string,
commit, and tag — the single "easy bump" for this repo.

auto-bmad is a BMAD module, not an npm package, so there is no `npm version` to
lean on. The version is duplicated in four tracked places that must stay in
lockstep, and "publishing" is just pushing a `vX.Y.Z` git tag (the BMAD
installer keys its upgrade detection off stable tags; the Claude plugin
marketplace reads the manifest `version`):

  1. .claude-plugin/marketplace.json                  "version": "X.Y.Z"
  2. auto-bmad/assets/module.yaml                      module_version: X.Y.Z
  3. README.md                                         shields badge  version-X.Y.Z-blue
  4. auto-bmad/references/state-and-resume.md          profiles_source_version: "X.Y.Z"
     (the schema example for config.yaml — first-run stamps this field with the
     installed module's version so a future update can detect a stale-defaults
     snapshot; the schema example must reflect the current release so docs and
     freshly-seeded configs agree)

Usage:
  python3 scripts/bump-version.py <patch|minor|major|X.Y.Z> [--dry-run]
  python3 scripts/bump-version.py --self-test

What a real (non --dry-run) run does, in order:
  1. Reads the current version from marketplace.json (the source of truth) and
     refuses to proceed if the other three files disagree (drift guard).
  2. Promotes CHANGELOG.md's `## [Unreleased]` to `## [X.Y.Z] - <date>`, opens a
     fresh empty `[Unreleased]`, and fixes the compare links. Aborts if
     `[Unreleased]` is empty — you can't release nothing. (Notes are written by
     hand; this only relabels them. See CLAUDE.md -> "Releasing".)
  3. Rewrites the version in all four files above.
  4. Requires a clean working tree, then commits `chore(release): vX.Y.Z` and
     creates the annotated tag `vX.Y.Z`. Push with: git push --follow-tags
     (annotated so --follow-tags actually pushes it).

Zero dependencies on purpose (matches the repo's other helper scripts).
"""

from __future__ import annotations

import datetime
import os
import re
import subprocess
import sys

REPO_FALLBACK = "https://github.com/stefanoginella/auto-bmad"

# Each entry: (repo-relative path, regex with exactly 3 groups: pre / version /
# post). The version group is rewritten; pre and post are preserved verbatim so
# file formatting is untouched. Every pattern must match exactly once.
VERSION_FILES = [
    (".claude-plugin/marketplace.json", r'("version"\s*:\s*")(\d+\.\d+\.\d+)(")'),
    ("auto-bmad/assets/module.yaml", r"(?m)^(module_version:\s*)(\d+\.\d+\.\d+)(\s*)$"),
    ("README.md", r"(badge/version-)(\d+\.\d+\.\d+)(-blue)"),
    # Schema example in the config.yaml block — stays in lockstep so docs match
    # what first-run actually writes into a fresh project's config (see step 4 of
    # the First-run flow in state-and-resume.md).
    ("auto-bmad/references/state-and-resume.md", r'(profiles_source_version:\s*")(\d+\.\d+\.\d+)(")'),
]

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


class ReleaseError(Exception):
    """A precondition for the bump was not met (clean abort, no side effects)."""


# --- pure helpers (exercised by --self-test) --------------------------------

def next_version(current: str, part: str) -> str:
    """patch/minor/major bump of `current`, or an explicit X.Y.Z passthrough."""
    if SEMVER.match(part):
        return part
    if not SEMVER.match(current):
        raise ReleaseError(f"current version is not X.Y.Z: {current!r}")
    major, minor, patch = (int(n) for n in current.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ReleaseError(f"bump must be patch|minor|major|X.Y.Z, got {part!r}")


def find_version(text: str, pattern: str) -> str | None:
    m = re.search(pattern, text)
    return m.group(2) if m else None


def replace_version(text: str, pattern: str, new: str) -> tuple[str, int]:
    """Rewrite the version group to `new`, preserving the surrounding text."""
    return re.subn(pattern, lambda m: m.group(1) + new + m.group(3), text)


def _strip_blanks(lines: list[str]) -> list[str]:
    a = list(lines)
    while a and a[0].strip() == "":
        a.pop(0)
    while a and a[-1].strip() == "":
        a.pop()
    return a


def promote_changelog(text: str, version: str, date: str, repo: str) -> str:
    """Relabel `## [Unreleased]` as `## [version] - date`, reopen an empty
    Unreleased, and rebuild the compare links. Idempotent; raises if Unreleased
    has no content. Does not invent content — notes are hand-written.
    """
    lines = text.split("\n")
    if any(l.startswith(f"## [{version}]") for l in lines):
        return text  # already promoted

    link_start = next(
        (i for i, l in enumerate(lines) if re.match(r"^\[Unreleased\]:\s", l)), -1
    )
    body = lines if link_start == -1 else lines[:link_start]
    links = [] if link_start == -1 else _strip_blanks(lines[link_start:])

    u = next((i for i, l in enumerate(body) if re.match(r"^## \[Unreleased\]", l)), -1)
    if u == -1:
        raise ReleaseError('CHANGELOG.md has no "## [Unreleased]" heading.')

    nxt = next((i for i in range(u + 1, len(body)) if re.match(r"^## \[", body[i])), -1)
    content = _strip_blanks(body[u + 1 : len(body) if nxt == -1 else nxt])
    if not content:
        raise ReleaseError(
            "CHANGELOG.md [Unreleased] is empty — add notes before releasing."
        )

    prev = None
    if nxt != -1:
        m = re.match(r"^## \[(\d+\.\d+\.\d+)\]", body[nxt])
        prev = m.group(1) if m else None

    preamble = _strip_blanks(body[:u])
    released = _strip_blanks([] if nxt == -1 else body[nxt:])
    out = preamble + ["", "## [Unreleased]", "", f"## [{version}] - {date}", ""] + content
    if released:
        out += [""] + released

    ver_link = (
        f"[{version}]: {repo}/compare/v{prev}...v{version}"
        if prev
        else f"[{version}]: {repo}/releases/tag/v{version}"
    )
    if links:
        new_links = list(links)
        ui = next(i for i, l in enumerate(new_links) if re.match(r"^\[Unreleased\]:", l))
        new_links[ui] = f"[Unreleased]: {repo}/compare/v{version}...HEAD"
        new_links.insert(ui + 1, ver_link)
    else:
        new_links = [f"[Unreleased]: {repo}/compare/v{version}...HEAD", ver_link]

    return "\n".join(_strip_blanks(out)) + "\n\n" + "\n".join(new_links) + "\n"


# --- git + filesystem -------------------------------------------------------

def repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(root: str, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def read(root: str, rel: str) -> str:
    with open(os.path.join(root, rel), encoding="utf-8") as f:
        return f.read()


def write(root: str, rel: str, text: str) -> None:
    with open(os.path.join(root, rel), "w", encoding="utf-8") as f:
        f.write(text)


def repo_url(marketplace_text: str) -> str:
    m = re.search(r'"repository"\s*:\s*"([^"]+)"', marketplace_text)
    return (m.group(1) if m else REPO_FALLBACK).rstrip("/").removesuffix(".git")


def run(part: str, dry_run: bool) -> int:
    root = repo_root()
    manifest = read(root, VERSION_FILES[0][0])
    current = find_version(manifest, VERSION_FILES[0][1])
    if not current:
        raise ReleaseError(f"could not read version from {VERSION_FILES[0][0]}")

    # Drift guard: every version string must already agree before we bump.
    drift = []
    for rel, pat in VERSION_FILES[1:]:
        found = find_version(read(root, rel), pat)
        if found != current:
            drift.append(f"  {rel}: {found} (expected {current})")
    if drift:
        raise ReleaseError(
            "version strings disagree; fix the drift before bumping:\n"
            f"  {VERSION_FILES[0][0]}: {current}\n" + "\n".join(drift)
        )

    new = next_version(current, part)
    if new == current:
        raise ReleaseError(f"already at {current}; nothing to bump")

    date = datetime.date.today().isoformat()
    promoted = promote_changelog(
        read(root, "CHANGELOG.md"), new, date, repo_url(manifest)
    )

    if not dry_run:
        if git(root, "status", "--porcelain"):
            raise ReleaseError("working tree is not clean; commit or stash first")
        if git(root, "tag", "-l", f"v{new}"):
            raise ReleaseError(f"tag v{new} already exists")
        branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
        if branch != "main":
            print(f"warning: releasing from '{branch}', not 'main'", file=sys.stderr)

    print(f"auto-bmad {current} -> {new}  ({date})")
    edits = []
    for rel, pat in VERSION_FILES:
        text = read(root, rel)
        updated, n = replace_version(text, pat, new)
        if n != 1:
            raise ReleaseError(f"expected exactly one version match in {rel}, found {n}")
        edits.append((rel, updated))
        print(f"  {rel}")
    edits.append(("CHANGELOG.md", promoted))
    print("  CHANGELOG.md")

    if dry_run:
        section = []
        for line in promoted.split("\n"):
            if line.startswith(f"## [{new}]"):
                section.append(line)
            elif section and line.startswith("## ["):
                break
            elif section:
                section.append(line)
        print("\n--- CHANGELOG.md [%s] preview ---" % new)
        print("\n".join(section).strip())
        print("--- dry run: no files written, no commit, no tag ---")
        return 0

    for rel, text in edits:
        write(root, rel, text)
    git(root, "add", *[rel for rel, _ in edits])
    git(root, "commit", "-m", f"chore(release): v{new}")
    # Annotated (not lightweight): `git push --follow-tags` only pushes annotated
    # tags, so a lightweight tag would silently never reach the remote and the
    # release workflow would never fire.
    git(root, "tag", "-a", f"v{new}", "-m", f"auto-bmad v{new}")
    print(f"\ncommitted and tagged v{new} (annotated). Push with:\n  git push --follow-tags")
    return 0


# --- self-test --------------------------------------------------------------

def self_test() -> int:
    assert next_version("0.1.1", "patch") == "0.1.2"
    assert next_version("0.1.1", "minor") == "0.2.0"
    assert next_version("0.1.9", "major") == "1.0.0"
    assert next_version("0.1.1", "2.3.4") == "2.3.4"
    for bad in ("nope", "1.2", "v1.2.3"):
        try:
            next_version("0.1.1", bad)
            assert False, f"expected failure for {bad!r}"
        except ReleaseError:
            pass

    samples = [
        ('  "version": "0.1.1",\n', VERSION_FILES[0][1], '  "version": "0.2.0",\n'),
        ("module_version: 0.1.1\n", VERSION_FILES[1][1], "module_version: 0.2.0\n"),
        ("badge/version-0.1.1-blue.svg", VERSION_FILES[2][1], "badge/version-0.2.0-blue.svg"),
        (
            'profiles_source_version: "0.1.1"  # abm version that seeded',
            VERSION_FILES[3][1],
            'profiles_source_version: "0.2.0"  # abm version that seeded',
        ),
    ]
    for text, pat, want in samples:
        assert find_version(text, pat) == "0.1.1", f"find failed: {text!r}"
        got, n = replace_version(text, pat, "0.2.0")
        assert n == 1 and got == want, f"replace failed: {got!r} (n={n})"

    cl = (
        "# Changelog\n\n"
        "## [Unreleased]\n\n"
        "### Added\n\n- A new thing.\n\n"
        "## [0.1.1] - 2026-05-26\n\n### Added\n\n- First.\n\n"
        "[Unreleased]: https://x/compare/v0.1.1...HEAD\n"
        "[0.1.1]: https://x/releases/tag/v0.1.1\n"
    )
    out = promote_changelog(cl, "0.1.2", "2026-05-27", "https://x")
    assert "## [0.1.2] - 2026-05-27" in out
    assert "- A new thing." in out
    assert "[0.1.2]: https://x/compare/v0.1.1...v0.1.2" in out
    assert "[Unreleased]: https://x/compare/v0.1.2...HEAD" in out
    # The reopened Unreleased must be empty (nothing between it and 0.1.2).
    body = out.split("## [0.1.2]")[0]
    assert body.split("## [Unreleased]")[1].strip() == ""
    assert promote_changelog(out, "0.1.2", "2026-05-27", "https://x") == out  # idempotent

    empty = "# Changelog\n\n## [Unreleased]\n\n## [0.1.1] - 2026-05-26\n\n- x.\n"
    try:
        promote_changelog(empty, "0.1.2", "2026-05-27", "https://x")
        assert False, "expected empty-Unreleased to fail"
    except ReleaseError:
        pass

    print("bump-version self-test: OK")
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    args = [a for a in argv if a != "--dry-run"]
    dry_run = "--dry-run" in argv
    if len(args) != 1:
        print((__doc__ or "").strip().split("\n\n")[0])
        print("\nusage: bump-version.py <patch|minor|major|X.Y.Z> [--dry-run]")
        print("       bump-version.py --self-test")
        return 2
    try:
        return run(args[0], dry_run)
    except ReleaseError as e:
        print(f"bump-version: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
