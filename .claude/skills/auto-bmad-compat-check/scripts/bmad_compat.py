#!/usr/bin/env python3
"""bmad_compat.py — assess BMAD version changes against auto-bmad's surface.

auto-bmad's build lane delegates into TWO separately versioned npm packages:
`bmad-method` (the core BMM line — `bmad-build-auto` is the story primitive,
`bmad-sprint-planning` owns sprint-status.yaml, `bmad-retrospective` closes an
epic) and `bmad-method-test-architecture-enterprise` (the TEA module — the
`bmad-testarch-*` skills run in the TEA-gated phases). They ship identically
(`latest`/`next` dist-tags, `vX.Y.Z` git tags, a `package/src/**` payload), so
one diff engine checks both; `--report` emits a combined result with a worst-of
headline verdict.

The hard, error-prone part of "is the new release compatible?" is mechanical:
work out which versions exist (stable vs prerelease), download the *published*
packages, diff them, and decide which changed files actually touch the skills
auto-bmad delegates to or the contracts it parses. This script does exactly that
and emits structured JSON. The *judgement* — does a flagged change really break
us, is a new skill worth adopting — is left to the caller (the SKILL.md reading
this output), because that needs reading the real diff, not a heuristic.

Three modes, and only one of them touches the network:

  --report     fetch npm metadata + tarballs and diff each line *incrementally* —
               last-checked stable -> current stable, and last-checked prerelease
               -> current prerelease — so only what is genuinely new since the
               last check is surfaced. classify, emit JSON.  (network)
  --surface    print the surface auto-bmad's docs name (all skills / delegated
               skills / contract owners) and stop.  (hermetic)
  --self-test  exercise every pure function against fixtures.  (hermetic — no
               network, so it is safe in CI and matches the repo's other scripts)

Why diff the *published tarballs* rather than git? Because that is what users
actually `npm install`. Only `src/**` (+ `package.json`, `removals.txt`, and
`tools/**` when a package ships it — bmad-method 6.11.x does) is read; docs and
tests are ignored even when packaged, so a docs-only release correctly shows
up here as "nothing shipped" — which is the truth for a runtime-compatibility
question.

Surface model (what the classifier keys off):

  * CONTRACT_OWNERS — skills that own a durable contract auto-bmad parses,
    writes next to, or hard-depends on (tier `critical`, or `low` for a
    heading/marker/argument-form auto-bmad merely reads or names). Each entry
    carries the parser(s)/asset(s) to cross-check when it changes.
  * CONTRACT_FILES — non-skill payload files that are contracts too
    (`src/scripts/config_utils.py` & co. — the customization/config machinery
    build-auto and auto-bmad's own scripts mirror).
  * surface = every `bmad-*` skill name auto-bmad's SKILL.md + references name
    (derived live via --refs); the *delegated* subset = names appearing in
    `references/delegation.md`, any `bmad-testarch-*` skill, and every owner.
    A named-but-not-delegated skill (e.g. `bmad-checkpoint-preview`, which the
    report only recommends) is `low` when it changes, never `high`.
  * shims — a skill whose SKILL.md frontmatter carries `metadata.lifecycle: shim`
    (BMAD's v6 forwarders; the folder name is NOT the signal — some shims live
    under `plan/`). Shims are never required by auto-bmad and never move the
    verdict; a *surface* skill that turns into a shim is `critical`, because a
    delegated skill just became a deprecated forwarder.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import tarfile
import urllib.request
from difflib import unified_diff
from urllib.parse import urlparse

NPM_REGISTRY = "https://registry.npmjs.org"
# Tarball URLs are read out of the registry JSON, so pin them to https on the
# npm host before fetching — never follow a `file://` or off-host URL even if
# the metadata is tampered with.
ALLOWED_HOST_SUFFIX = ".npmjs.org"

# The BMAD npm packages auto-bmad's pipeline delegates into. They ship the SAME
# way — `latest`/`next` dist-tags, `vX.Y.Z` git tags, a `package/src/**` payload —
# so one diff engine serves both. `bmad-method` is the core BMM line;
# `bmad-method-test-architecture-enterprise` is the separately versioned TEA
# (test-architecture) module that ships the `bmad-testarch-*` skills auto-bmad
# runs in its TEA-gated phases. Each entry pins the npm name (the dict key), a
# short report label, and the GitHub slug Step 3 cross-checks + the README
# blockquote windows baselines by. Order matters only cosmetically (report order).
PACKAGES = {
    "bmad-method": {
        "label": "BMAD-METHOD",
        "repo": "bmad-code-org/BMAD-METHOD",
    },
    "bmad-method-test-architecture-enterprise": {
        "label": "TEA (test-architecture)",
        "repo": "bmad-code-org/bmad-method-test-architecture-enterprise",
    },
}

# Skills that don't just run in the pipeline but *own a durable contract*
# auto-bmad reads, writes next to, or hard-depends on. `tier` is the relevance a
# change to that skill gets: `critical` = a format/protocol auto-bmad parses or
# a prose contract its prompts encode; `low` = a single heading/marker/argument
# form auto-bmad only reads or names (skim for that one thing, nothing else).
# `parsers` = the auto-bmad files to cross-check when the diff moves the contract.
CONTRACT_OWNERS = {
    "bmad-build-auto": {
        "tier": "critical",
        "contract": (
            "the story primitive — spec-template.md frontmatter keys (title/type/created/status/"
            "review_loop_iteration/followup_review_recommended/context/warnings/deferred) + the "
            "status vocabulary (draft | ready-for-dev | in-progress | in-review | done | blocked); "
            "customize.toml `[[workflow.review_layers]]` schema (id/name/instruction/when) + the "
            "runtime placeholders {diff_output} (<= 6.11.0) / {diff_file} + {claims_file} "
            "(>= 6.11.1) / {verbatim_intent} / {skill-root} and the "
            "`implementation_handoff` {spec_file}; workflow.md HALT protocol (`## Auto Run Result` "
            "with `Status:` / `Blocking condition:` lines, the no-spec "
            "`bmad-build-auto-result-<slug-or-timestamp>.md` fallback, `no subagents` halt); "
            "step-01 route (existing-spec EARLY EXIT by status, `-2`/`-3` slug suffixing, "
            "`blocked spec supplied`, `done` ⇒ fresh review pass with review_loop_iteration reset, "
            "`unclear intent`, dirty-tree/continuity halts); step-02 `Halt after planning.` ⇒ HALT "
            "`ready-for-dev`; step-04 blocking strings (`intent gap`, `patch verification failed`, "
            "`review repair loop exceeded 5 iterations (non-convergence)`, `finalization left "
            "repository dirty`), the RULES line `same model capability as the current session` (why "
            "the security layer's model line is only a preference), the `followup_review_recommended` "
            "rule (any high patch, or 3×medium + 1×low ≥ 5), the `deferred:` item shape "
            "(summary/evidence/location/severity), the `## Review Triage Log` entry format, and the "
            "Finalize commit rule (commit reviewed-diff files + spec, verify clean, never push, HALT "
            "`done`)"
        ),
        "parsers": ["scripts/story_plan.py (--spec / --find-spec)", "scripts/state_plan.py",
                    "scripts/deferred_ledger.py (harvest)", "scripts/build_auto_custom.py",
                    "assets/bmad-custom/bmad-build-auto.toml", "references/delegation.md",
                    "references/pipeline.md"],
    },
    "bmad-sprint-planning": {
        "tier": "critical",
        "contract": (
            "sprint-status.yaml grammar + vocabulary (STORY_KEY_RE `^(\\d+)-(\\d+)([a-z]?)-.+`, "
            "epic-N / epic-N-retrospective keys, story statuses backlog|ready-for-dev|in-progress|"
            "review|done, epic backlog|in-progress|done, retro optional|done, `last_updated` "
            "DATE_FORMAT `%m-%d-%Y %H:%M`), the epics heading grammar EPIC_RE/STORY_RE mirrored by "
            "`story_plan.py --planning-dir`, and the `sprint_plan.py status` JSON keys "
            "(recommendation{skill,story_key,reason}, open_action_items, risks, warnings, all_done, "
            "stories/epics/retrospectives counts)"
        ),
        "parsers": ["scripts/story_plan.py", "references/pipeline.md (Phase 0 picker)",
                    "references/epic-pipeline.md"],
    },
    "bmad-retrospective": {
        "tier": "critical",
        "contract": (
            "`-H <epic>` headless invocation; the retro document's frontmatter `verdict` "
            "(accepted | accepted-with-open-items | rejected — the gate auto-bmad reads with "
            "`story_plan.py --retro-verdict`); `sprint_status.py update` — action_items shape "
            "(id/action/owner/status open|in-progress|done/ref) and the retro key flip to `done`"
        ),
        "parsers": ["scripts/story_plan.py (--retro-verdict)", "references/delegation.md (retrospective)",
                    "references/pipeline.md (Phase 8.5)"],
    },
    "bmad-project-context": {
        "tier": "low",
        "contract": ("the `<!-- bmad:context -->` … `<!-- /bmad:context -->` AGENTS.md marker pair "
                     "preflight probes for (warn-only) — auto-bmad never invokes the skill, it only "
                     "recommends `/bmad-project-context refresh` at epic end"),
        "parsers": ["scripts/preflight.py (agents_md probe)"],
    },
    "bmad-code-review": {
        "tier": "low",
        "contract": ("only the `## Deferred from: code review (<date>)` deferred-work.md heading + "
                     "one-bullet-per-finding shape that deferred_ledger.py parses as a ledger section"),
        "parsers": ["scripts/deferred_ledger.py"],
    },
    "bmad-build": {
        "tier": "low",
        "contract": ("only the heading-less deferred-work.md entry block it appends "
                     "(`- source_spec:` / `summary:` / `evidence:`) that deferred_ledger.py parses"),
        "parsers": ["scripts/deferred_ledger.py"],
    },
    "bmad-checkpoint-preview": {
        "tier": "low",
        "contract": ("invocation argument forms (PR / branch / commit / spec file) — the report's "
                     "`Human review: /bmad-checkpoint-preview <pr_url | branch>` next-step line"),
        "parsers": ["references/pipeline.md (Phase 9)", "references/state-and-resume.md (report)"],
    },
}

# Non-skill payload files that are contracts too: the customization/config
# machinery `bmad-build-auto` renders through and auto-bmad's own scripts mirror.
# Keyed by exact package path (leading `package/` stripped).
CONTRACT_FILES = {
    "src/scripts/config_utils.py": {
        "tier": "critical",
        "contract": ("central-config layer order (`_bmad/config.toml` → `config.user.toml` → "
                     "`custom/config.toml` → `custom/config.user.toml`, tables deep-merged) and the "
                     "arrays-of-tables keyed merge by `code`/`id` (matching id REPLACES, new ids "
                     "append) that makes auto-bmad's `[[workflow.review_layers]]` region work"),
        "parsers": ["scripts/preflight.py (central_config)", "scripts/build_auto_custom.py"],
    },
    "src/scripts/resolve_customization.py": {
        "tier": "high",
        "contract": ("`<skill>/customize.toml` → `_bmad/custom/<skill>.toml` → "
                     "`_bmad/custom/<skill>.user.toml` resolution — where the managed region lands"),
        "parsers": ["scripts/build_auto_custom.py"],
    },
    "src/scripts/render_skill.py": {
        "tier": "high",
        "contract": ("`uv run render_skill.py` — how bmad-build-auto renders its snapshot; the reason "
                     "for the `uv` + Python 3.11 prerequisites preflight probes"),
        "parsers": ["scripts/preflight.py (uv / python probes)"],
    },
    "src/scripts/resolve_config.py": {
        "tier": "high",
        "contract": "central TOML resolver every skill calls — the layer set preflight.py mirrors",
        "parsers": ["scripts/preflight.py (central_config)"],
    },
}

# TEA skills auto-bmad delegates to (test-design/atdd/automate/trace/nfr/test-review in
# the TEA-gated phases; framework/ci in the one-time TEA setup ask).
TEA_SKILLS = (
    "bmad-testarch-test-design", "bmad-testarch-atdd", "bmad-testarch-automate",
    "bmad-testarch-trace", "bmad-testarch-nfr", "bmad-testarch-test-review",
    "bmad-testarch-framework", "bmad-testarch-ci",
)

# Fallback surface if the caller can't supply one from the repo. Kept small and
# obviously-current; the real run derives the surface from SKILL.md + references/
# so this never silently goes stale on its own.
FALLBACK_SURFACE = sorted(set(CONTRACT_OWNERS) | set(TEA_SKILLS))

# Tokens the surface regex picks up that are not real skills: the family prefix
# (`bmad-testarch-*`), the shipped asset dir (`assets/bmad-custom/`), build-auto's
# no-spec result file (`bmad-build-auto-result-*.md`), and package/dir names.
SURFACE_NOISE = {"bmad-output", "bmad-method", "bmad-testarch", "bmad-custom",
                 "bmad-build-auto-result"}

SKILL_SEG_RE = re.compile(r"^(?:bmad|gds)-[a-z0-9]+(?:-[a-z0-9]+)*$")
# A skill id must start at a word edge: `auto-bmad-security` (an auto-bmad review
# layer id) must not yield a phantom `bmad-security` skill.
SURFACE_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_-])bmad-[a-z0-9]+(?:-[a-z0-9]+)*")
SEMVER_RE = re.compile(r"\b(\d+)\.(\d+)\.(\d+)(?:-next\.(\d+))?\b")
TEA_FAMILY_PREFIX = "bmad-testarch-"
DELEGATION_DOC_BASENAME = "delegation.md"

RELEVANCE_ORDER = {"critical": 0, "high": 1, "low": 2, "shim": 3, "info": 4}


# --------------------------------------------------------------------------- #
# Pure helpers (all covered by --self-test)                                    #
# --------------------------------------------------------------------------- #

def semver_key(version: str):
    """Sort key honouring that a `-next` prerelease sits *below* its own final
    release but *above* the previous patch: 6.8.0 < 6.8.1-next.0 < 6.8.1."""
    m = SEMVER_RE.search(version)
    if not m:
        return (0, 0, 0, 0, 0)
    major, minor, patch, pre = m.groups()
    is_final = 0 if pre is not None else 1  # final outranks its prerelease
    return (int(major), int(minor), int(patch), is_final, int(pre or 0))


def derive_surface(refs_text: str) -> list:
    """Extract the set of BMAD skills auto-bmad's docs name by scanning them.
    Over-inclusion is safe (a flagged skill just gets read); omission is not, so
    we err toward catching everything that looks like a skill id at a word edge
    and only strip known non-skill tokens."""
    found = set(SURFACE_TOKEN_RE.findall(refs_text))
    return sorted(t for t in found if t not in SURFACE_NOISE)


def derive_delegated(surface, delegation_text: str) -> list:
    """The subset of the surface auto-bmad actually *runs*: skills named in
    references/delegation.md (the file that owns every delegate prompt) plus the
    `bmad-testarch-*` family (TEA skills are always reached by delegation, incl.
    the one-time framework/ci setup ask that lives outside delegation.md).
    Contract owners are classified by their own tier regardless of this set;
    anything else in the surface is a mention."""
    named = set(derive_surface(delegation_text)) if delegation_text else set()
    return sorted(s for s in surface if s in named or s.startswith(TEA_FAMILY_PREFIX))


def skill_name_of(path: str):
    """Return the skill-directory segment of a package path, or None.
    e.g. src/bmm-skills/ship/bmad-build-auto/SKILL.md -> bmad-build-auto."""
    for seg in path.split("/"):
        if SKILL_SEG_RE.match(seg):
            return seg
    return None


def parse_frontmatter(skill_md: str):
    """The raw YAML frontmatter block of a SKILL.md (between the leading `---`
    fences), or '' when there is none."""
    m = re.match(r"\s*^---\s*\n(.*?)\n---\s*(?:\n|$)", skill_md, re.DOTALL | re.MULTILINE)
    return m.group(1) if m else ""


def parse_lifecycle(skill_md: str):
    """`metadata.lifecycle` from a SKILL.md frontmatter (`shim` marks BMAD's v6
    forwarders), or None. Dependency-free: walks the indented block under a
    top-level `metadata:` line."""
    fm = parse_frontmatter(skill_md)
    in_meta = False
    for line in fm.splitlines():
        if re.match(r"^metadata:\s*$", line):
            in_meta = True
            continue
        if in_meta:
            if not line.strip() or line[0] in " \t":
                m = re.match(r"^\s+lifecycle:\s*['\"]?([A-Za-z0-9_-]+)['\"]?\s*$", line)
                if m:
                    return m.group(1)
                continue
            in_meta = False
    return None


def is_shim(skill_md: str) -> bool:
    return parse_lifecycle(skill_md) == "shim"


def classify_path(path: str, surface, delegated=None, shims=(), became_shim=()) -> dict:
    """Decide how much a changed file matters to auto-bmad.

    critical — a contract owner (skill or file) auto-bmad parses/depends on changed,
               or a surface skill turned into a v6 shim (deprecated forwarder)
    high     — a delegated skill (or a high-tier contract file) changed
    low      — a skill auto-bmad only mentions, a low-tier contract owner, or an
               off-pipeline BMAD skill (maybe a new capability worth a look)
    shim     — a v6 shim (`metadata.lifecycle: shim`) — never required, no verdict impact
    info     — a non-skill file (package.json, installer under tools/, removals.txt)

    `delegated=None` means "treat every surface skill as delegated" (the legacy
    behaviour, used when no delegation.md was supplied)."""
    surface = set(surface)
    delegated = surface if delegated is None else set(delegated)
    shims = set(shims)
    became_shim = set(became_shim)
    skill = skill_name_of(path)

    if skill is None:
        if path in CONTRACT_FILES:
            spec = CONTRACT_FILES[path]
            return {"path": path, "skill": None, "relevance": spec["tier"],
                    "owns_contract": spec["contract"], "parsers": spec["parsers"],
                    "reason": "non-skill payload file that IS a contract auto-bmad mirrors — read the diff"}
        if path.startswith("tools/"):
            return {"path": path, "skill": None, "relevance": "info", "area": "installer",
                    "reason": "installer/tooling file — read only for install/update-guidance changes"}
        if path == "removals.txt":
            return {"path": path, "skill": None, "relevance": "info", "area": "removals",
                    "reason": "installer removal list (skill dirs deleted on install/update)"}
        return {"path": path, "skill": None, "relevance": "info", "reason": "non-skill file"}

    if skill in became_shim and skill in surface:
        return {"path": path, "skill": skill, "relevance": "critical", "lifecycle": "shim",
                "reason": ("skill auto-bmad names/delegates to just became a v6 shim (deprecated "
                           "forwarder) — migrate to its canonical replacement")}
    if skill in shims:
        entry = {"path": path, "skill": skill, "relevance": "shim", "lifecycle": "shim",
                 "reason": "v6 shim (metadata.lifecycle: shim) — never required by auto-bmad"}
        if skill in surface:
            entry["relevance"] = "critical"
            entry["reason"] = ("auto-bmad's docs name a v6 shim — a shim is never required and must "
                               "not be spelled in shipped files; move to the canonical skill")
        return entry
    if skill in CONTRACT_OWNERS:
        spec = CONTRACT_OWNERS[skill]
        reason = ("skill that OWNS a contract auto-bmad parses/depends on — read the diff for "
                  "format/protocol changes" if spec["tier"] == "critical" else
                  "not delegated; auto-bmad only reads/names ONE thing it owns — skim for that contract only")
        return {"path": path, "skill": skill, "relevance": spec["tier"],
                "owns_contract": spec["contract"], "parsers": spec["parsers"], "reason": reason}
    if skill in delegated:
        return {"path": path, "skill": skill, "relevance": "high",
                "reason": "delegated skill — runs in the auto-bmad pipeline; skim for changed "
                          "invocation flags/modes or removed capabilities"}
    if skill in surface:
        return {"path": path, "skill": skill, "relevance": "low",
                "reason": "skill auto-bmad names but never runs (mention only) — no parser to break"}
    return {"path": path, "skill": skill, "relevance": "low",
            "reason": "BMAD skill not in auto-bmad's pipeline — possible new capability"}


def diff_sets(files_a: dict, files_b: dict) -> dict:
    """Compare two {path: bytes} maps into changed / added / removed path lists."""
    a, b = set(files_a), set(files_b)
    changed = sorted(p for p in (a & b) if files_a[p] != files_b[p])
    return {"changed": changed, "added": sorted(b - a), "removed": sorted(a - b)}


def _skill_dirs(files: dict) -> dict:
    """Map skill-name -> its SKILL.md path for every skill present in a tree."""
    out = {}
    for path in files:
        if path.endswith("/SKILL.md"):
            name = skill_name_of(path)
            if name:
                out[name] = path
    return out


def shim_skills(files: dict) -> set:
    """Skill names whose SKILL.md frontmatter says `metadata.lifecycle: shim`."""
    out = set()
    for name, path in _skill_dirs(files).items():
        if is_shim(files[path].decode("utf-8", "replace")):
            out.add(name)
    return out


def parse_description(skill_md: str):
    """Pull the `description:` value out of a SKILL.md frontmatter block."""
    m = re.search(r"^description:\s*(.+?)\s*$", skill_md, re.MULTILINE)
    if not m:
        return None
    return m.group(1).strip().strip("'\"")


def find_new_skills(files_a: dict, files_b: dict, since: str) -> list:
    """Skills present in the newer tree but not the older one (shims tagged)."""
    a, b = _skill_dirs(files_a), _skill_dirs(files_b)
    out = []
    for name in sorted(set(b) - set(a)):
        content = files_b[b[name]].decode("utf-8", "replace")
        out.append({"name": name, "path": b[name], "since": since,
                    "description": parse_description(content),
                    "lifecycle": parse_lifecycle(content)})
    return out


def _compat_blockquote(text: str) -> str:
    """Isolate the `> … Compatibility: …` blockquote so version parsing can't
    collide with the BMAD-METHOD repo URL that also appears in the page's badges
    and links. Falls back to the whole text when no such blockquote is found."""
    lines = text.splitlines()
    idx = next((i for i, ln in enumerate(lines)
                if ln.lstrip().startswith(">") and "Compatibility" in ln), None)
    if idx is None:
        return text
    start = idx
    while start > 0 and lines[start - 1].lstrip().startswith(">"):
        start -= 1
    end = idx
    while end + 1 < len(lines) and lines[end + 1].lstrip().startswith(">"):
        end += 1
    return "\n".join(lines[start:end + 1])


def _highest_pair(text: str):
    """(highest plain semver, highest -next) found in a span — None where absent."""
    finals, pres = [], []
    for m in SEMVER_RE.finditer(text):
        v = m.group(0)
        (pres if "-next." in v else finals).append(v)
    stable = max(finals, key=semver_key) if finals else None
    prerelease = max(pres, key=semver_key) if pres else None
    return stable, prerelease


def parse_baseline_from_readme(text: str, package=None, packages=None):
    """Read the last-verified versions out of the README compat blockquote.

    With `package` set, scope to *that* package's clause: within the compat
    blockquote, the window runs from the package's GitHub repo slug up to the next
    package's slug (or end of blockquote). Per-package scoping is a *correctness*
    requirement, not a nicety — the two lines need not share a prerelease (TEA's
    `next` can sort below its own stable, leaving its clause with no `-next` token),
    so a global 'highest -next' would hand one package's prerelease to the other.
    Authoring rule the windowing assumes: each clause's versions sit *after* its
    repo link. A clause may name a floor AND a tested-up-to version ("floor
    **6.11.0**, tested up to **6.11.0**") — the highest plain semver wins, so the
    floor never masks the tested version. Returns (stable, prerelease|None);
    (None, None) when the package's clause isn't present yet. With `package=None`,
    the legacy global parse over the blockquote (highest plain semver + highest -next)."""
    packages = packages or PACKAGES
    region = _compat_blockquote(text)
    if package is None:
        return _highest_pair(region)
    repo = packages[package]["repo"]
    start = region.find(repo)
    if start == -1:
        return None, None
    later = [p for p in (region.find(m["repo"]) for k, m in packages.items() if k != package)
             if p != -1 and p > start]
    end = min(later) if later else len(region)
    return _highest_pair(region[start:end])


def prerelease_anchor(stable, prev_prerelease, prerelease):
    """Pick the 'from' version for the prerelease diff, or None to skip it.

    We only want what's *genuinely new* in the prerelease line since the last
    check — never re-surfacing anything already covered by the stable diff or the
    prerelease we last signed off on. So anchor at the highest version we've
    already accounted for: the current stable, or the last-checked prerelease when
    it still sits above stable (semver_key ranks a final above its own -next, so a
    prerelease that has since *graduated* to stable drops below the stable floor
    and is correctly covered by the stable diff, not re-reported here). Skip
    entirely when the live prerelease isn't above that floor — it graduated, or
    hasn't moved since the last check."""
    if not prerelease:
        return None
    floor = stable
    if prev_prerelease and semver_key(prev_prerelease) > semver_key(floor):
        floor = prev_prerelease
    return floor if semver_key(prerelease) > semver_key(floor) else None


def stable_anchor(baseline, prev_prerelease, stable):
    """Pick the 'from' version for the stable diff, or None to skip it.

    Symmetric to prerelease_anchor: anchor at the highest version we've already
    checked that sits *below* the current stable — the last-checked stable, or the
    last-checked prerelease once it has *graduated* into this stable (then we diff
    only the prerelease→final sliver, never re-showing changes already reviewed as
    prereleases). A prerelease aimed at a *future* line (>= this stable) is not a
    precursor to it, so it's ignored. Skip when stable hasn't moved past what we've
    seen."""
    floor = baseline
    if (prev_prerelease
            and semver_key(prev_prerelease) < semver_key(stable)
            and semver_key(prev_prerelease) > semver_key(floor)):
        floor = prev_prerelease
    return floor if semver_key(stable) > semver_key(floor) else None


def unified(path: str, a: bytes, b: bytes, max_lines: int) -> str:
    """A bounded unified diff for one file, or a binary-change note."""
    try:
        a_lines = a.decode("utf-8").splitlines(keepends=True)
        b_lines = b.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return "(binary file changed)"
    lines = list(unified_diff(a_lines, b_lines, fromfile="a/" + path, tofile="b/" + path))
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"... (+{len(lines) - max_lines} more diff lines truncated)\n"]
    return "".join(lines)


def compare_trees(label, older_v, newer_v, older, newer, surface, delegated, max_lines) -> dict:
    """Diff two extracted trees and classify every changed path (pure — the
    network layer only feeds it trees)."""
    sets = diff_sets(older, newer)
    shims_old, shims_new = shim_skills(older), shim_skills(newer)
    shims = shims_old | shims_new
    # "became" = existed before as a real skill and is a shim now (a brand-new
    # shim is just a new_skills entry tagged lifecycle: shim).
    became_shim = (shims_new - shims_old) & set(_skill_dirs(older))
    impact = []

    def classify(path):
        return classify_path(path, surface, delegated, shims, became_shim)

    for path in sets["changed"]:
        entry = classify(path)
        entry["change"] = "modified"
        if entry["relevance"] in ("critical", "high", "low") or entry.get("area"):
            entry["diff"] = unified(path, older[path], newer[path], max_lines)
        impact.append(entry)
    for path in sets["added"]:
        entry = classify(path)
        entry["change"] = "added"
        impact.append(entry)
    for path in sets["removed"]:
        entry = classify(path)
        entry["change"] = "removed"
        impact.append(entry)
    impact.sort(key=lambda e: (RELEVANCE_ORDER[e["relevance"]], e["path"]))
    surface_shims = sorted(set(surface) & shims_new)
    return {
        "label": label,
        "from": older_v,
        "to": newer_v,
        "files_changed": len(sets["changed"]),
        "files_added": len(sets["added"]),
        "files_removed": len(sets["removed"]),
        "impact": impact,
        "new_skills": find_new_skills(older, newer, f"{label} ({newer_v})"),
        "became_shim": sorted(became_shim),
        # Surface tokens that name a v6 shim in the newer tree — a shipped-file
        # violation (shims are never required) worth fixing in the references.
        "surface_shims": surface_shims,
    }


def surface_unmatched(surface, shipped_by_package: dict) -> list:
    """Surface tokens that match no skill dir in ANY package's newest tree —
    junk the surface regex picked up, or a skill upstream dropped/renamed (both
    worth a look; a token that only lives in the *other* package is fine and
    is not listed)."""
    shipped = set()
    for names in shipped_by_package.values():
        shipped |= set(names)
    return sorted(set(surface) - shipped)


def summarize(comparisons) -> dict:
    hits = {"critical": [], "high": [], "low": []}
    new_skills, new_shims = [], []
    surface_shims = set()
    for c in comparisons:
        for e in c["impact"]:
            if e["relevance"] in hits:
                hits[e["relevance"]].append(e["path"])
        for s in c["new_skills"]:
            (new_shims if s.get("lifecycle") == "shim" else new_skills).append(s["name"])
        surface_shims |= set(c.get("surface_shims", []))
    if hits["critical"] or hits["high"]:
        verdict = "needs-attention"
    elif hits["low"] or new_skills:
        verdict = "review-opportunities"
    elif not comparisons:
        # Nothing new on either line since the last check.
        verdict = "up-to-date"
    else:
        verdict = "compatible"
    return {
        "verdict": verdict,
        "delegated_skill_changes": hits["critical"] + hits["high"],
        "contract_owner_changes": hits["critical"],
        "other_skill_changes": hits["low"],
        "new_skills": sorted(set(new_skills)),
        "new_shims": sorted(set(new_shims)),
        "surface_shims": sorted(surface_shims),
    }


# Worst-of ordering, so the combined headline verdict is the most-attention-needing
# of the packages checked (a TEA break must not be masked by a clean BMAD line).
VERDICT_RANK = {"up-to-date": 0, "compatible": 1, "review-opportunities": 2,
                "needs-attention": 3}


# --------------------------------------------------------------------------- #
# Network (NOT exercised by --self-test)                                       #
# --------------------------------------------------------------------------- #

def _get(url: str, timeout: int = 30) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not (parsed.hostname or "").endswith(ALLOWED_HOST_SUFFIX):
        raise SystemExit(f"refusing to fetch non-npm URL: {url!r}")
    req = urllib.request.Request(url, headers={"User-Agent": "auto-bmad-compat-check"})
    # nosemgrep: dynamic-urllib-use-detected -- scheme+host pinned to https npm above
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return r.read()


def registry_url(package: str) -> str:
    return f"{NPM_REGISTRY}/{package}"


def fetch_registry(package: str) -> dict:
    return json.loads(_get(registry_url(package)).decode("utf-8"))


PAYLOAD_PREFIXES = ("package/src/", "package/tools/")
PAYLOAD_FILES = ("package/package.json", "package/removals.txt")


def extract_package_src(tar_bytes: bytes) -> dict:
    """Return {path: bytes} for the runtime payload — package/src/**, package/tools/**
    (the installer, when a package ships it), package.json and removals.txt — with
    the leading `package/` stripped. docs/, tests, web-bundles etc. are deliberately
    skipped: they aren't what compatibility hinges on."""
    out = {}
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tf:
        for m in tf.getmembers():
            if not m.isfile():
                continue
            if m.name in PAYLOAD_FILES or m.name.startswith(PAYLOAD_PREFIXES):
                if "/__pycache__/" in m.name or m.name.endswith((".pyc", ".pyo")):
                    continue
                fh = tf.extractfile(m)
                if fh is not None:
                    out[m.name[len("package/"):]] = fh.read()
    return out


def _has_version(registry: dict, version: str) -> bool:
    """Whether npm still publishes this exact version (prereleases can be pulled)."""
    return version in registry.get("versions", {})


def _resolve_anchor(anchor, fallback, registry, kind):
    """Guard against anchoring a diff at an *ephemeral* prerelease npm has since
    unpublished. If `anchor` is such a version, degrade to `fallback` (always a
    durable stable) and return a note saying so; otherwise return it unchanged."""
    if anchor and anchor != fallback and not _has_version(registry, anchor):
        note = (f"last-checked prerelease {anchor} is no longer published on npm; "
                f"anchored the {kind} diff at {fallback} instead")
        return fallback, note
    return anchor, None


def _git_head(registry: dict, version) -> str | None:
    """The exact source commit a published version was built from, if npm recorded
    it. npm stamps `gitHead` into each published version's metadata, so this pins a
    tagless `-next` prerelease to a precise commit — letting the repo cross-check
    (Step 3) read the *exact* commit window that produced a diff, instead of the
    looser `v<stable>...main` (where `main` can sit ahead of the published build)."""
    if not version:
        return None
    return registry.get("versions", {}).get(version, {}).get("gitHead")


def _tarball_url(registry: dict, version: str) -> str:
    try:
        return registry["versions"][version]["dist"]["tarball"]
    except KeyError:
        raise SystemExit(f"version {version!r} not found on npm")


def _tree(registry: dict, version: str) -> dict:
    return extract_package_src(_get(_tarball_url(registry, version)))


def build_report(package, baseline, prev_prerelease, surface, delegated, max_lines) -> dict:
    registry = fetch_registry(package)
    tags = registry.get("dist-tags", {})
    stable = tags.get("latest")
    nxt = tags.get("next")
    # A `next` tag can lag behind a fresh stable; only treat it as a real
    # prerelease if it actually sorts above the current stable.
    prerelease = nxt if (nxt and semver_key(nxt) > semver_key(stable)) else None

    trees = {baseline: _tree(registry, baseline), stable: _tree(registry, stable)}

    comparisons = []

    def add(comp):
        # Pin each comparison to the exact source commits npm built its endpoints
        # from, so Step 3's repo cross-check reads the precise commit window.
        comp["from_git_head"] = _git_head(registry, comp["from"])
        comp["to_git_head"] = _git_head(registry, comp["to"])
        comparisons.append(comp)

    # Stable line: only what's new since the highest version we've already checked
    # below the current stable — the last-checked stable, or a prerelease that has
    # since graduated into it (then just the prerelease→final sliver).
    s_anchor = stable_anchor(baseline, prev_prerelease, stable)
    s_anchor, stable_anchor_note = _resolve_anchor(s_anchor, baseline, registry, "stable")
    if s_anchor:
        if s_anchor not in trees:
            trees[s_anchor] = _tree(registry, s_anchor)
        label = "prev_stable_to_stable" if s_anchor == baseline else "prev_prerelease_to_stable"
        add(compare_trees(label, s_anchor, stable,
                          trees[s_anchor], trees[stable], surface, delegated, max_lines))

    # Prerelease line: only what's new since the last-checked prerelease (or the
    # current stable, whichever is higher — see prerelease_anchor).
    pre_anchor = prerelease_anchor(stable, prev_prerelease, prerelease)
    pre_anchor, pre_anchor_note = _resolve_anchor(pre_anchor, stable, registry, "prerelease")
    if pre_anchor and prerelease:  # prerelease is non-None whenever pre_anchor is set
        if pre_anchor not in trees:
            trees[pre_anchor] = _tree(registry, pre_anchor)
        if prerelease not in trees:
            trees[prerelease] = _tree(registry, prerelease)
        label = ("stable_to_prerelease" if pre_anchor == stable
                 else "prev_prerelease_to_prerelease")
        add(compare_trees(label, pre_anchor, prerelease,
                          trees[pre_anchor], trees[prerelease], surface, delegated, max_lines))

    newest = trees[prerelease] if prerelease in trees else trees[stable]
    return {
        "package": package,
        "label": PACKAGES.get(package, {}).get("label", package),
        "repo": PACKAGES.get(package, {}).get("repo"),
        "shipped_skills": sorted(_skill_dirs(newest)),
        "shipped_shims": sorted(shim_skills(newest)),
        # Surface tokens that name a v6 shim this package ships NOW (checked even
        # when nothing changed): shims are never required, so a hit is a shipped-
        # file violation to fix in auto-bmad's references, not an upstream issue.
        "surface_shims": sorted(set(surface) & shim_skills(newest)),
        "baseline": baseline,
        "prev_prerelease": prev_prerelease,
        "stable": stable,
        "prerelease": prerelease,
        "prerelease_tag_raw": nxt,
        "stable_anchor_note": stable_anchor_note,
        "prerelease_anchor_note": pre_anchor_note,
        "surface_skills": surface,
        "delegated_skills": delegated,
        "comparisons": comparisons,
        "summary": summarize(comparisons),
    }


def build_combined_report(specs, surface, delegated, max_lines) -> dict:
    """Build one per-package report for each (package, baseline, prev_prerelease)
    spec and fold them into a combined result with a worst-of headline verdict.

    A package whose baseline can't be resolved (no README clause and no override)
    becomes an `error` entry rather than aborting the whole run — one missing clause
    must never sink the other package's check."""
    reports = []
    for package, baseline, prev_prerelease in specs:
        if not baseline:
            reports.append({
                "package": package,
                "label": PACKAGES.get(package, {}).get("label", package),
                "error": "could not determine baseline (no README compat clause and no override)",
            })
            continue
        reports.append(build_report(package, baseline, prev_prerelease, surface, delegated, max_lines))
    graded = [r["summary"]["verdict"] for r in reports if "summary" in r]
    if graded:
        verdict = max(graded, key=lambda v: VERDICT_RANK.get(v, 0))
    elif reports:
        verdict = "error"
    else:
        verdict = "up-to-date"
    shipped = {r["package"]: r.get("shipped_skills", []) for r in reports if "summary" in r}
    return {
        "verdict": verdict,
        "surface_skills": surface,
        "delegated_skills": delegated,
        # Only meaningful when every package resolved; a token unmatched across
        # ALL fetched packages is junk or an upstream rename/drop.
        "surface_unmatched": surface_unmatched(surface, shipped) if shipped else [],
        "surface_shims": sorted({n for r in reports for n in r.get("surface_shims", [])}),
        "contract_owners": {k: v["tier"] for k, v in CONTRACT_OWNERS.items()},
        "contract_files": {k: v["tier"] for k, v in CONTRACT_FILES.items()},
        "packages": reports,
    }


def load_surface(ref_paths):
    """Derive (surface, delegated) from the reference docs the caller passed.
    Falls back to FALLBACK_SURFACE (all treated as delegated) when nothing was
    readable — never to an empty surface."""
    surface, delegation_text = [], ""
    for path in ref_paths:
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        surface += derive_surface(text)
        if path.replace("\\", "/").rsplit("/", 1)[-1] == DELEGATION_DOC_BASENAME:
            delegation_text += "\n" + text
    surface = sorted(set(surface))
    if not surface:
        return list(FALLBACK_SURFACE), list(FALLBACK_SURFACE)
    delegated = derive_delegated(surface, delegation_text) if delegation_text else list(surface)
    return surface, delegated


# --------------------------------------------------------------------------- #
# Self-test                                                                    #
# --------------------------------------------------------------------------- #

_SHIM_MD = (b"---\nname: bmad-old-thing\ndescription: 'Deprecated: forwards to bmad-new-thing'\n"
            b"metadata:\n  lifecycle: shim\n---\n# gone\n")
_REAL_MD = b"---\nname: bmad-new-thing\ndescription: Does the thing.\n---\n# body\n"


def _self_test() -> int:
    failures = []

    def check(name, cond):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        if not cond:
            failures.append(name)

    # semver ordering — the subtle prerelease rule
    ordered = sorted(["6.11.1", "6.11.0", "6.11.1-next.0", "6.10.1"], key=semver_key)
    check("semver: 6.10.1 < 6.11.0 < 6.11.1-next.0 < 6.11.1",
          ordered == ["6.10.1", "6.11.0", "6.11.1-next.0", "6.11.1"])
    check("semver: prerelease ranks above previous patch",
          semver_key("6.11.1-next.0") > semver_key("6.11.0"))

    # surface derivation strips noise, keeps real skills, honours word edges
    surf = derive_surface(
        "run /bmad-build-auto and bmad-testarch-trace; _bmad-output/; the bmad-testarch-* family; "
        "layer id `auto-bmad-security` + `auto-bmad-cross-model`; assets/bmad-custom/x.toml; "
        "the bmad-build-auto-result-*.md fallback")
    check("surface: keeps real skills", "bmad-build-auto" in surf and "bmad-testarch-trace" in surf)
    check("surface: drops _bmad-output / family-prefix / asset-dir / result-file noise",
          not ({"bmad-output", "bmad-testarch", "bmad-custom", "bmad-build-auto-result"} & set(surf)))
    check("surface: an auto-bmad layer id is not a phantom skill",
          "bmad-security" not in surf and "bmad-cross-model" not in surf)
    check("surface: the fan-out lens names are gone from the fallback",
          not any(s.startswith("bmad-review-") for s in FALLBACK_SURFACE))

    # delegated subset — delegation.md names + TEA family + owners; mentions stay out
    surface = ["bmad-build-auto", "bmad-checkpoint-preview", "bmad-help", "bmad-retrospective",
               "bmad-testarch-ci", "bmad-testarch-trace"]
    deleg = derive_delegated(surface, "delegate /bmad-build-auto … then bmad-testarch-trace")
    check("delegated: delegation.md names + TEA family (owners classified by tier, not here)",
          set(deleg) == {"bmad-build-auto", "bmad-testarch-ci", "bmad-testarch-trace"})
    check("delegated: a mention-only skill is not delegated", "bmad-help" not in deleg)

    # skill-name extraction from realistic package paths (both packages)
    check("skill_name: bmm nested path",
          skill_name_of("src/bmm-skills/ship/bmad-build-auto/SKILL.md") == "bmad-build-auto")
    check("skill_name: v6-shims folder path",
          skill_name_of("src/bmm-skills/v6-shims/bmad-old-thing/SKILL.md") == "bmad-old-thing")
    check("skill_name: TEA path",
          skill_name_of("src/workflows/testarch/bmad-testarch-atdd/SKILL.md") == "bmad-testarch-atdd")
    check("skill_name: core-skills path",
          skill_name_of("src/core-skills/bmad-party-mode/SKILL.md") == "bmad-party-mode")
    check("skill_name: non-skill path", skill_name_of("package.json") is None)
    check("skill_name: scripts path is not a skill", skill_name_of("src/scripts/config_utils.py") is None)

    # lifecycle parse — the shim signal lives in frontmatter metadata, not the folder
    check("lifecycle: shim parsed", parse_lifecycle(_SHIM_MD.decode()) == "shim")
    check("lifecycle: absent -> None", parse_lifecycle(_REAL_MD.decode()) is None)
    check("lifecycle: quoted value", parse_lifecycle("---\nmetadata:\n  lifecycle: 'shim'\n---\n") == "shim")
    check("lifecycle: word 'lifecycle' in the body is not a signal",
          parse_lifecycle("---\nname: x\n---\n# lifecycle refresh\nmetadata:\n  lifecycle: shim\n") is None)
    check("lifecycle: metadata block without lifecycle -> None",
          parse_lifecycle("---\nmetadata:\n  author: me\nname: y\n---\n") is None)
    tree = {"src/bmm-skills/plan/bmad-old-thing/SKILL.md": _SHIM_MD,
            "src/bmm-skills/plan/bmad-new-thing/SKILL.md": _REAL_MD}
    check("shim_skills: found by frontmatter even outside a v6-shims folder",
          shim_skills(tree) == {"bmad-old-thing"})

    # classification tiers
    surface = ["bmad-build-auto", "bmad-testarch-atdd", "bmad-help", "bmad-checkpoint-preview",
               "bmad-code-review", "bmad-old-thing"]
    delegated = ["bmad-build-auto", "bmad-testarch-atdd", "bmad-checkpoint-preview", "bmad-code-review"]
    c1 = classify_path("src/bmm-skills/ship/bmad-build-auto/step-04-review.md", surface, delegated)
    check("classify: critical contract owner -> critical",
          c1["relevance"] == "critical" and "owns_contract" in c1 and c1["parsers"])
    c2 = classify_path("src/workflows/testarch/bmad-testarch-atdd/SKILL.md", surface, delegated)
    check("classify: delegated non-owner -> high", c2["relevance"] == "high")
    c3 = classify_path("src/core-skills/bmad-party-mode/SKILL.md", surface, delegated)
    check("classify: off-pipeline skill -> low", c3["relevance"] == "low")
    c4 = classify_path("package.json", surface, delegated)
    check("classify: non-skill -> info", c4["relevance"] == "info")
    c5 = classify_path("src/bmm-skills/ship/bmad-checkpoint-preview/SKILL.md", surface, delegated)
    check("classify: low-tier owner -> low with contract",
          c5["relevance"] == "low" and "owns_contract" in c5)
    c6 = classify_path("src/core-skills/bmad-help/SKILL.md", surface, delegated)
    check("classify: mention-only surface skill -> low, no contract",
          c6["relevance"] == "low" and "owns_contract" not in c6 and "mention" in c6["reason"])
    c7 = classify_path("src/core-skills/bmad-help/SKILL.md", surface, None)
    check("classify: delegated=None treats every surface skill as delegated", c7["relevance"] == "high")
    c8 = classify_path("src/bmm-skills/v6-shims/bmad-dead/SKILL.md", surface, delegated, shims={"bmad-dead"})
    check("classify: shim off-surface -> shim (no verdict impact)", c8["relevance"] == "shim")
    c9 = classify_path("src/bmm-skills/plan/bmad-old-thing/SKILL.md", surface, delegated, shims={"bmad-old-thing"})
    check("classify: shim named in the surface -> critical", c9["relevance"] == "critical")
    c10 = classify_path("src/bmm-skills/ship/bmad-build-auto/SKILL.md", surface, delegated,
                        shims={"bmad-build-auto"}, became_shim={"bmad-build-auto"})
    check("classify: surface skill that became a shim -> critical",
          c10["relevance"] == "critical" and "became" in c10["reason"])
    c11 = classify_path("src/scripts/config_utils.py", surface, delegated)
    check("classify: contract file -> its tier + parsers",
          c11["relevance"] == "critical" and "build_auto_custom" in " ".join(c11["parsers"]))
    c12 = classify_path("tools/installer/installer.js", surface, delegated)
    check("classify: installer file -> info/installer",
          c12["relevance"] == "info" and c12["area"] == "installer")
    c13 = classify_path("removals.txt", surface, delegated)
    check("classify: removals.txt -> info/removals", c13["relevance"] == "info" and c13["area"] == "removals")
    c14 = classify_path("src/bmm-skills/ship/bmad-code-review/steps/step-04-present.md", surface, delegated)
    check("classify: code-review is a LOW owner (ledger heading only)",
          c14["relevance"] == "low" and "Deferred from" in c14["owns_contract"])

    # CONTRACT_OWNERS integrity — the spec'd owner set, no removed/shim name, tiers valid
    check("owners: build lane owners present",
          {"bmad-build-auto", "bmad-sprint-planning", "bmad-retrospective", "bmad-project-context",
           "bmad-code-review", "bmad-checkpoint-preview"} <= set(CONTRACT_OWNERS))
    check("owners: no fan-out lens name",
          not any(k.startswith("bmad-review-") for k in CONTRACT_OWNERS))
    check("owners: tiers valid + parsers listed",
          all(v["tier"] in ("critical", "low") and v["parsers"] for v in CONTRACT_OWNERS.values()))
    check("owners: critical owners are exactly build-auto / sprint-planning / retrospective",
          {k for k, v in CONTRACT_OWNERS.items() if v["tier"] == "critical"}
          == {"bmad-build-auto", "bmad-sprint-planning", "bmad-retrospective"})
    check("owners: build-auto contract names the placeholders + halt lines",
          all(tok in CONTRACT_OWNERS["bmad-build-auto"]["contract"]
              for tok in ("{diff_output}", "{diff_file}", "{claims_file}", "{verbatim_intent}",
                          "{skill-root}", "Auto Run Result",
                          "Halt after planning.", "followup_review_recommended", "Review Triage Log")))
    check("fallback surface = owners ∪ TEA skills",
          set(FALLBACK_SURFACE) == set(CONTRACT_OWNERS) | set(TEA_SKILLS))
    check("contract files: tiers valid",
          all(v["tier"] in ("critical", "high") for v in CONTRACT_FILES.values()))

    # diff sets
    a = {"p.json": b"1", "src/a/SKILL.md": b"x", "src/gone/SKILL.md": b"z"}
    b = {"p.json": b"2", "src/a/SKILL.md": b"x", "src/new/SKILL.md": b"y"}
    ds = diff_sets(a, b)
    check("diff_sets: changed", ds["changed"] == ["p.json"])
    check("diff_sets: added", ds["added"] == ["src/new/SKILL.md"])
    check("diff_sets: removed", ds["removed"] == ["src/gone/SKILL.md"])

    # new-skill detection + description parse + shim tagging
    old = {"src/core-skills/bmad-a/SKILL.md": b"---\nname: bmad-a\n---\n"}
    new = dict(old)
    new["src/core-skills/bmad-b/SKILL.md"] = b"---\nname: bmad-b\ndescription: Does a new thing.\n---\n"
    new["src/bmm-skills/v6-shims/bmad-old-thing/SKILL.md"] = _SHIM_MD
    ns = find_new_skills(old, new, "prerelease")
    check("new_skills: detects added skills", [s["name"] for s in ns] == ["bmad-b", "bmad-old-thing"])
    check("new_skills: parses description", ns[0]["description"] == "Does a new thing.")
    check("new_skills: tags a new shim", ns[1]["lifecycle"] == "shim" and ns[0]["lifecycle"] is None)

    # compare_trees end-to-end (pure): shim churn never moves the verdict
    older = {"package.json": b"1",
             "src/bmm-skills/ship/bmad-build-auto/SKILL.md": b"v1",
             "src/bmm-skills/v6-shims/bmad-old-thing/SKILL.md": _SHIM_MD}
    newer = {"package.json": b"2",
             "src/bmm-skills/ship/bmad-build-auto/SKILL.md": b"v1",
             "src/bmm-skills/v6-shims/bmad-old-thing/SKILL.md": _SHIM_MD + b"\nmore\n",
             "src/bmm-skills/v6-shims/bmad-newer-shim/SKILL.md": _SHIM_MD}
    comp = compare_trees("stable_to_prerelease", "6.11.0", "6.11.1-next.1", older, newer,
                         ["bmad-build-auto"], ["bmad-build-auto"], 50)
    summ = summarize([comp])
    check("compare: shim-only churn -> compatible", summ["verdict"] == "compatible")
    check("compare: new shim listed apart from new skills",
          summ["new_shims"] == ["bmad-newer-shim"] and summ["new_skills"] == [])
    check("surface_unmatched: a token shipped by EITHER package is matched",
          surface_unmatched(["bmad-build-auto", "bmad-testarch-trace", "bmad-gone"],
                            {"bmad-method": ["bmad-build-auto"],
                             "tea": ["bmad-testarch-trace"]}) == ["bmad-gone"])
    newer2 = dict(newer)
    newer2["src/bmm-skills/ship/bmad-build-auto/SKILL.md"] = _SHIM_MD
    comp2 = compare_trees("x", "a", "b", older, newer2, ["bmad-build-auto"], ["bmad-build-auto"], 50)
    check("compare: surface skill turned shim -> critical + surface_shims",
          summarize([comp2])["verdict"] == "needs-attention"
          and comp2["became_shim"] == ["bmad-build-auto"] and comp2["surface_shims"] == ["bmad-build-auto"])
    newer3 = dict(newer)
    newer3["tools/installer/installer.js"] = b"new"
    older3 = dict(older)
    older3["tools/installer/installer.js"] = b"old"
    comp3 = compare_trees("x", "a", "b", older3, newer3, ["bmad-build-auto"], ["bmad-build-auto"], 50)
    inst = [e for e in comp3["impact"] if e["path"].startswith("tools/")]
    check("compare: installer change carries a diff but stays info",
          inst and inst[0]["relevance"] == "info" and "diff" in inst[0]
          and summarize([comp3])["verdict"] == "compatible")

    # README baseline parse — legacy global parse over the blockquote
    readme = "> **Compatibility:** tested ... up to **6.11.0** (and the **6.11.1-next.0** prerelease)."
    stable, pre = parse_baseline_from_readme(readme)
    check("readme: stable baseline", stable == "6.11.0")
    check("readme: prerelease baseline", pre == "6.11.1-next.0")

    # Per-package windowing — mirrors the real two-clause compat blockquote (the
    # 0.27 shape: a "6.11 line" mention + floor + tested-up-to + prerelease for
    # bmad-method; "floor and tested" for TEA), with a decoy badge line carrying the
    # BMAD-METHOD repo URL *outside* the blockquote (proves _compat_blockquote
    # isolation dodges the badge collision).
    two_pkg = (
        "[badge](https://github.com/bmad-code-org/BMAD-METHOD) [other](https://x)\n"
        "\n"
        "> **Compatibility:** tested against the "
        "**[BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) 6.11 line** — floor "
        "**6.11.0**, tested up to **6.11.0** (and prerelease **6.11.1-next.14**) — and the separately "
        "versioned **[TEA test-architecture module]"
        "(https://github.com/bmad-code-org/bmad-method-test-architecture-enterprise) v1 line** (the "
        "`testarch` skills) — floor and tested **1.23.0** — auto-bmad couples to those skills' "
        "contracts rather than pinned versions.\n"
    )
    bm_s, bm_p = parse_baseline_from_readme(two_pkg, "bmad-method")
    check("windowed: bmad-method stable (floor + tested, '6.11 line' ignored)", bm_s == "6.11.0")
    check("windowed: bmad-method prerelease", bm_p == "6.11.1-next.14")
    tea_s, tea_p = parse_baseline_from_readme(two_pkg, "bmad-method-test-architecture-enterprise")
    check("windowed: TEA stable scoped to its clause", tea_s == "1.23.0")
    check("windowed: TEA has no prerelease (next sorts below stable)", tea_p is None)
    later = two_pkg.replace("tested up to **6.11.0**", "tested up to **6.12.0**")
    check("windowed: tested-up-to above the floor wins",
          parse_baseline_from_readme(later, "bmad-method")[0] == "6.12.0")
    miss_s, miss_p = parse_baseline_from_readme(
        "> **Compatibility:** only **6.11.0** here.", "bmad-method-test-architecture-enterprise")
    check("windowed: absent clause -> (None, None)", miss_s is None and miss_p is None)

    # PACKAGES integrity — distinct, non-substring repo slugs (windowing depends on it)
    slugs = [m["repo"] for m in PACKAGES.values()]
    check("packages: repo slugs distinct", len(set(slugs)) == len(slugs))
    check("packages: no slug is a substring of another",
          not any(a != b and a in b for a in slugs for b in slugs))

    # Combined verdict — worst-of, so a TEA break isn't masked by a clean BMAD line
    check("verdict: worst-of needs-attention > compatible",
          max(["compatible", "needs-attention"], key=lambda v: VERDICT_RANK[v]) == "needs-attention")
    check("verdict: worst-of review-opportunities > up-to-date",
          max(["up-to-date", "review-opportunities"], key=lambda v: VERDICT_RANK[v])
          == "review-opportunities")

    # prerelease anchoring — only diff what's genuinely new since the last check
    check("anchor: no live prerelease -> skip",
          prerelease_anchor("6.11.0", "6.11.1-next.2", None) is None)
    check("anchor: unchanged since last check -> skip",
          prerelease_anchor("6.11.0", "6.11.1-next.2", "6.11.1-next.2") is None)
    check("anchor: new prerelease on same line -> anchor at last-checked prerelease",
          prerelease_anchor("6.11.0", "6.11.1-next.2", "6.11.1-next.3") == "6.11.1-next.2")
    check("anchor: prerelease graduated + new line -> anchor at stable (no double-report)",
          prerelease_anchor("6.11.1", "6.11.1-next.2", "6.11.2-next.1") == "6.11.1")
    check("anchor: no prior prerelease recorded -> anchor at stable",
          prerelease_anchor("6.11.0", None, "6.11.1-next.1") == "6.11.0")

    # stable anchoring — symmetric: don't re-show prerelease content when it graduates
    check("stable-anchor: no new stable -> skip",
          stable_anchor("6.11.0", "6.11.1-next.2", "6.11.0") is None)
    check("stable-anchor: prerelease graduated -> anchor at it (sliver only)",
          stable_anchor("6.11.0", "6.11.1-next.2", "6.11.1") == "6.11.1-next.2")
    check("stable-anchor: no prior prerelease -> anchor at prev stable",
          stable_anchor("6.11.0", None, "6.11.1") == "6.11.0")
    check("stable-anchor: future-line prerelease ignored for this stable",
          stable_anchor("6.11.0", "6.12.0-next.1", "6.11.1") == "6.11.0")
    check("stable-anchor: prerelease already below baseline ignored",
          stable_anchor("6.11.1", "6.11.1-next.2", "6.12.0") == "6.11.1")

    # version availability — drives the graceful degrade when a recorded
    # prerelease has since been unpublished (anchor falls back to stable)
    reg = {"versions": {"6.11.0": {}, "6.11.1-next.2": {}}}
    check("has_version: present", _has_version(reg, "6.11.0"))
    check("has_version: pulled prerelease", not _has_version(reg, "6.11.1-next.1"))

    # gitHead pinning — lets Step 3 read the exact commit window for a tagless prerelease
    reg2 = {"versions": {"6.11.0": {"gitHead": "abc123"}, "6.11.1-next.2": {}}}
    check("git_head: present", _git_head(reg2, "6.11.0") == "abc123")
    check("git_head: not recorded -> None", _git_head(reg2, "6.11.1-next.2") is None)
    check("git_head: unknown version -> None", _git_head(reg2, "9.9.9") is None)
    check("git_head: None version -> None", _git_head(reg2, None) is None)

    # payload extraction — src/ + tools/ + package.json + removals.txt, never pycache/docs
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, data in (("package/package.json", b"{}"),
                           ("package/src/bmm-skills/ship/bmad-build-auto/SKILL.md", b"x"),
                           ("package/src/scripts/__pycache__/x.cpython-311.pyc", b"\x00"),
                           ("package/tools/installer/installer.js", b"j"),
                           ("package/removals.txt", b"r"),
                           ("package/docs/guide.md", b"d"),
                           ("package/test/t.js", b"t")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    tree = extract_package_src(buf.getvalue())
    check("extract: keeps src/tools/package.json/removals.txt, drops docs/tests/pycache",
          set(tree) == {"package.json", "src/bmm-skills/ship/bmad-build-auto/SKILL.md",
                        "tools/installer/installer.js", "removals.txt"})

    # unified diff truncation
    big = unified("f", b"a\n" * 50, b"b\n" * 50, max_lines=10)
    check("unified: truncates", "truncated" in big)

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        return 1
    print("All self-tests passed.")
    return 0


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true", help="run hermetic checks and exit")
    ap.add_argument("--report", action="store_true",
                    help="fetch + diff + classify BOTH packages (bmad-method + TEA) (network)")
    ap.add_argument("--surface", action="store_true",
                    help="print the derived surface (all / delegated / owners) from --refs and exit (hermetic)")
    ap.add_argument("--baseline", help="bmad-method last-verified stable (e.g. 6.11.0); "
                                       "defaults to the README compat blockquote via --readme")
    ap.add_argument("--prev-prerelease", help="bmad-method last-checked prerelease (e.g. 6.11.1-next.14); "
                                              "defaults to the README compat blockquote via --readme")
    ap.add_argument("--tea-baseline", help="TEA last-verified stable (e.g. 1.23.0); "
                                           "defaults to the README compat blockquote via --readme")
    ap.add_argument("--tea-prev-prerelease", help="TEA last-checked prerelease (e.g. 1.24.0-next.1); "
                                                  "defaults to the README compat blockquote via --readme")
    ap.add_argument("--readme", help="path to README.md to read both packages' baselines from")
    ap.add_argument("--refs", nargs="*", default=[],
                    help="auto-bmad docs to derive the surface from (SKILL.md + references/*.md; the "
                         "file named delegation.md marks the delegated subset)")
    ap.add_argument("--max-diff-lines", type=int, default=160,
                    help="cap unified-diff length per file")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    if args.surface:
        surface, delegated = load_surface(args.refs)
        json.dump({"surface_skills": surface, "delegated_skills": delegated,
                   "mention_only": sorted(set(surface) - set(delegated) - set(CONTRACT_OWNERS)),
                   "contract_owners": {k: v["tier"] for k, v in CONTRACT_OWNERS.items()},
                   "contract_files": {k: v["tier"] for k, v in CONTRACT_FILES.items()},
                   "fallback_used": not args.refs or surface == list(FALLBACK_SURFACE)},
                  sys.stdout, indent=2)
        print()
        return 0

    if not args.report:
        ap.error("nothing to do: pass --report, --surface, or --self-test")

    # Per-package CLI overrides; everything else comes from the README blockquote.
    overrides = {
        "bmad-method": (args.baseline, args.prev_prerelease),
        "bmad-method-test-architecture-enterprise": (args.tea_baseline, args.tea_prev_prerelease),
    }
    readme_text = None
    if args.readme:
        with open(args.readme, encoding="utf-8") as fh:
            readme_text = fh.read()

    specs = []
    for package in PACKAGES:
        baseline, prev_prerelease = overrides.get(package, (None, None))
        if readme_text is not None and (not baseline or prev_prerelease is None):
            r_stable, r_pre = parse_baseline_from_readme(readme_text, package)
            baseline = baseline or r_stable
            if prev_prerelease is None:
                prev_prerelease = r_pre
        specs.append((package, baseline, prev_prerelease))

    if not any(b for _, b, _ in specs):
        ap.error("could not determine any baseline: pass --readme, --baseline, or --tea-baseline")

    surface, delegated = load_surface(args.refs)
    report = build_combined_report(specs, surface, delegated, args.max_diff_lines)
    json.dump(report, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
