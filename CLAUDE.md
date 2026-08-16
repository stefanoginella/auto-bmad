# CLAUDE.md — working in the auto-bmad repo

This repo is a **BMAD standalone module** (one skill + a Claude `marketplace.json`). The skill
(`auto-bmad`) is an orchestrator that runs the **BMAD build lane** (`bmad-build-auto` plan → build →
follow-up review, plus risk-gated TEA and epic-boundary work) one story at a time — or, with
`/auto-bmad epic`, a whole epic in one run (`references/epic-pipeline.md`) — on **Claude Code, Codex,
or opencode**. This file is guidance for working **on the module**, not for using it.

## Core principle (do not violate)
The orchestrator **delegates BMAD work and reports** — it never runs `/bmad-*` skills itself (the
only exception is the `inline` tier), **never reads or edits story code, and never edits the spec**
(spec metadata comes only from `story_plan.py --spec` / `--find-spec`). Every BMAD step — the
`bmad-build-auto` plan run, build run and follow-up review pass, TEA, the retrospective, the
deferred-work reconcile — runs in a delegated generic subagent at the phase profile's model.
**Preserve this separation when editing.**

The orchestrator owns a small set of actions **directly** (never delegated) — git/finalize
bookkeeping it already holds full pipeline context for. `git-and-pr.md` → "Ownership" is the
single normative list; in short:
- **Git/PR work** — preflight, branching, per-phase commits, push, PR, CI wait, the Phase 9 merge
  prompt, and the clean-tree gate before every build-auto invocation (build-auto HALTs on a dirty
  tree and **authors every code commit itself**; the orchestrator never makes a `feat` commit).
- **Phase 0 probes** — `preflight.py` (git state/mode, `uv`, Python 3.11, nested-subagent
  capability, `_bmad/config.toml`, `AGENTS.md` block, required skills), the config-drift heal
  (`config_plan.py`), and the review-layers TOML sync (`build_auto_custom.py`).
- **Sprint-status write-back around build-auto** — `story_plan.py --mark-status`: Phase 3 end →
  `ready-for-dev`, Phase 5 start → `in-progress` (+ the epic lift), Phase 5 end → `review`, the
  Phase 8 pre-retro `done` flip, the Phase 9 `done` flip. Scripted, never trusted to a delegate.
- **Phase 7 halt handling** — external-review changes are detected with a **git-only check**
  (never a code read), committed, and the halt re-opened once; the **re-review is delegated** (one
  more build-auto follow-up pass), never an inline read.
- **Phase 8 deferred-work archive** (+ the Phase 7 tail **harvest** of the spec's `deferred:` list
  into `<impl>/deferred-work.md`) — `deferred_ledger.py` mechanics; the keep-vs-move judgment and
  the `deferred-reconcile` delegate stay LLM/delegated.
- **Phase 9 finalize writes** — the pre-push pipeline-report commit + the status flip.
- **The retro verdict gate ask** (Phase 0 / E0) when the previous epic's newest retro doc says
  `rejected`.

auto-bmad's review extras are **two `[[workflow.review_layers]]` tables** (`auto-bmad-security`,
`auto-bmad-cross-model`) that `build_auto_custom.py` writes into a marker-fenced managed region of
the project's `_bmad/custom/bmad-build-auto.toml` — build-auto runs them inside its own review step;
the orchestrator never fans out reviewers itself. Keep `assets/bmad-custom/bmad-build-auto.toml` in
lockstep with upstream `bmad-build-auto/customize.toml`'s layer schema (compat-check "critical").

The mechanics live in the reference docs — **don't restate them here**: `git-and-pr.md`
(ownership, branching, push, PR, merge prompt), `pipeline.md` (Phase 0 probes, status write-back,
Phase 7 halt + tail, Phase 8 archive, Phase 9), `delegation.md` (the per-step prompts).

## Delegation: two tiers (the heart of the module)
BMAD abstracts neither sub-agent delegation nor per-agent model/effort, so we supply those through
each host's **native** subagent mechanism — **no rendered agent files**, nothing provisioned per
tool, nothing to go stale:
- **Tier 1 `subagents`** (Claude Code, Codex, opencode) — a generic subagent spawned with the phase
  profile's model: Claude Code Agent tool `model:` (per-call model; **effort inherits the
  session**), Codex per-call `model` + `reasoning_effort` (the only host honoring per-phase effort
  in-tool), opencode default subagent (**inherits** the user's model and reasoning). Spawned in the
  foreground, one step at a time.
- **Tier 2 `inline`** — no subagent mechanism; run the step in-context (documented last resort).

Orthogonal to the tiers, an **opt-in per-phase external-CLI route** (`delegation.cli_phases`) sends
a phase to `claude -p` / `codex exec` / `opencode run` for cross-tool/cross-vendor diversity. It
reads the *same* `profiles` blocks (claude→`--effort`, codex→`model_reasoning_effort`,
opencode→`--variant`; opencode's model + variant are optional ⇒ inherit), is still delegation (the
orchestrator builds the command + parses the result, never reads code), hard-stops on a failed
preflight (binary/skills/auth), and needs no in-tool nesting when both `build` and
`followup_review` are routed. The per-tool flag matrix + validation live in
`scripts/cli_delegate.py` (tested), not orchestrator prose. Default empty ⇒ all in-tool.

**Nesting requirement.** build-auto spawns its own subagents, so the `subagents` tier needs
orchestrator (depth 0) → delegate (depth 1) → build-auto's subagents (depth 2). Preflight verifies
it per host (knobs in "Known platform facts") and prints a verbatim fix on `hard_stop`.

`assets/profiles.yaml` is the **single source of truth** — per-profile, per-tool **model + effort
only** (`claude.model`/`effort`, `codex.model`/`reasoning_effort`, `opencode.model`/`variant`; no
persona text — every `delegation.md` prompt carries its own role line); `phase_profiles` maps the
ten phase keys to a profile. Host/mode are `auto` and re-detected every run. Full detail:
`delegation-runtime.md` (host detection, nesting, the tiers, the `cli_phases` route) and
`state-and-resume.md` (config/profiles schema, first-run).

## Layout & where behavior lives
- `.claude-plugin/marketplace.json` — Claude distribution (lists the single `./auto-bmad` skill).
- `auto-bmad/SKILL.md` — orchestrator entry point (On-activation gate + procedure). Keep it thin.
- `auto-bmad/references/` — where the real detail lives; each file owns one area:
  - `pipeline.md` — per-phase (per-story) playbook.
  - `epic-pipeline.md` — the `/auto-bmad epic` E-step flow (the per-story phases are the inner
    loop; no per-story halts).
  - `delegation.md` — exact per-step prompts (tool-agnostic, self-contained).
  - `delegation-runtime.md` — host detection, nesting, the two spawn tiers, the CLI route.
  - `tea-policy.md` — TEA risk rubric / selection.
  - `git-and-pr.md` — ownership list, branching, commits, push, PR, merge prompt.
  - `state-and-resume.md` — config/state schema, first-run, profiles, removed-keys note.
  - `overrides.md` — invocation-override vocabulary.
- `auto-bmad/assets/profiles.yaml` — the single per-profile source (model/effort blocks + the
  `phase_profiles` map). Custom profiles (any name) are first-class: `config_plan.py`'s heal passes
  them through, a whole-block reset prunes them.
- `auto-bmad/assets/config-defaults.yaml` — the source of truth for the **constant-default
  setup-block** keys (`delegation`/`tea`/`git`/`code_review`/`build`) that the Phase 0 drift heal
  appends to an existing `config.yaml`. Deliberately **omits** environment-detected/interviewed
  fields (`git.base_branch`, `host`/`mode`, `tea.enabled`/`framework_ci`, `git.mode`,
  `code_review.cross_model_layer`) so the append-only heal can never write a wrong static value.
  Lockstep: each default must equal the orchestrator fallback **and** the `state-and-resume.md`
  schema (config_plan.py's `--self-test` enforces the include/exclude sets).
- `auto-bmad/assets/bmad-custom/bmad-build-auto.toml` — the review-layers region template
  (`@@…@@` placeholders filled by `build_auto_custom.py`). Mirror upstream's layer schema.
- `auto-bmad/assets/module.yaml` + `module-help.csv` + `module-setup.md` — module identity, help
  rows, and the self-registration/provisioning flow (help catalog + review-layers sync).
- `auto-bmad/scripts/` — dependency-free helpers, each with a `--self-test` and a self-documenting
  docstring (read the script for exact behavior):
  - `story_plan.py` — the single story-source adapter: `--resolve` (explicit `--story` arg →
    key/title, ambiguity hard-stop), `--epic N` (enumerate keys/statuses/first-last), `--mark-status`
    (byte-preserving BMAD-status flip + `last_updated` stamp + epic lift, `[a-z]?` split-key
    grammar), `--find-spec` / `--spec` (build-auto spec discovery + frontmatter/`## Auto Run
    Result` reader), `--retro-verdict` (retro-doc frontmatter).
  - `state_plan.py` — `state/{key}.yaml` reader (resume detection, `--scope epic`); `--finalize`
    evaluates the Phase 9 draft predicate / clean-completion verdict.
  - `state_update.py` — deterministic per-story state/report writer (init / patch / phase-done,
    timing brackets, literal report sections). Lockstep-self-tested against the schema block.
  - `config_plan.py` — detects and additively heals drift between the shipped defaults
    (`profiles.yaml`; `config-defaults.yaml`) and a project's runtime `config.yaml`. Append-only
    (`--apply`); `--reset` re-seeds the profiles blocks (whole-block scope prunes stale profiles /
    keys) but never the setup blocks.
  - `preflight.py` — one-call Phase 0 preflight (`--central-config-only` for the gate): central
    TOML read (`tomllib`), `uv` + Python 3.11, nesting, git state/mode, `AGENTS.md`, CI, required
    skills + `sprint_plan.py` location, framework detection — one JSON with hard-stop reasons.
  - `deferred_ledger.py` — `harvest` (Phase 7 tail: spec `deferred:` → ledger, idempotent), `plan`
    / `archive` (Phase 8, sha-guarded atomic move); keep-vs-move judgment stays with the LLM.
  - `cli_delegate.py` — resolves the opt-in CLI route for a phase (argv + model/effort +
    `launch_cmd`, live `validate()`, `--once`/`--wait` watchers) and `--layer-argv` builds the ONE
    shell line of the cross-model review layer that `build_auto_custom.py` bakes into the TOML.
  - `ci_wait.py` — Phase 9 CI wait: polls `gh pr checks`, classifies `ci_status`, resolves
    `ci_run_url` by head SHA.
  - `build_auto_custom.py` — syncs the managed review-layers region of
    `_bmad/custom/bmad-build-auto.toml` from the runtime config (`--check`/`--apply`; models baked
    from `profiles`; whole-file `tomllib` validation; duplicate-id guard). Setup, `reprovision`,
    Phase 0 freshness.
  - `merge-help-csv.py` — the live self-registration merge into `_bmad/_config/bmad-help.csv`
    (anti-zombie; stdlib only, no PyYAML). Called with `--target`; never
    `--legacy-dir` (it would delete the per-module file setup just wrote).
  - `merge-config.py` — **retained only to satisfy the standalone-module validator**
    (`validate-module.py` requires the file); auto-bmad **does not invoke it** — it never writes
    the installer-owned central BMAD config. Don't reintroduce a call to it.
  - **Both of the above are VENDORED**, not ours: verbatim copies from
    `bmad-code-org/bmad-builder` (`skills/bmad-module-builder/assets/standalone-module-template/`),
    MIT © BMad Code, LLC. Each carries a provenance header with origin, sync SHA, and local-delta
    list — **record every local edit there**, or the next re-sync silently reverts it. Prefer fixing
    upstream and re-syncing. The upstream lives in `bmad-builder`, a *separate* repo from
    `BMAD-METHOD`.
- **Repo-root tooling, NOT shipped in the skill:** `CHANGELOG.md` (hand-maintained),
  `scripts/bump-version.py` (release helper — see "Releasing"), `skills/reports/` (tracked
  module-validation snapshots), `docs/` (the v7 migration plan + the upstream capability backlog).

## Testing
```bash
# Deterministic cores:
python3 auto-bmad/scripts/story_plan.py --self-test
python3 auto-bmad/scripts/state_plan.py --self-test
python3 auto-bmad/scripts/state_update.py --self-test
python3 auto-bmad/scripts/preflight.py --self-test
python3 auto-bmad/scripts/config_plan.py --self-test
python3 auto-bmad/scripts/cli_delegate.py --self-test
python3 auto-bmad/scripts/ci_wait.py --self-test
python3 auto-bmad/scripts/deferred_ledger.py --self-test
python3 auto-bmad/scripts/build_auto_custom.py --self-test
# Maintainer-only skill (tracked under .claude/ via gitignore exception; NOT shipped to users):
python3 .claude/skills/auto-bmad-compat-check/scripts/bmad_compat.py --self-test
# Marketplace manifest is valid JSON:
python3 -m json.tool .claude-plugin/marketplace.json >/dev/null
# Module structure passes the BMAD validator (run from the repo root, which holds the one skill):
python3 .claude/skills/bmad-module-builder/scripts/validate-module.py .
# Live: add this repo as a local marketplace (Claude) or BMAD module source, install, run
# /auto-bmad in a BMAD project. `/auto-bmad reprovision` re-syncs the review-layers TOML.
# Release helper:
python3 scripts/bump-version.py --self-test
```

## Releasing
The version lives in **four** tracked files that must stay in lockstep —
`.claude-plugin/marketplace.json` (`version`), `auto-bmad/assets/module.yaml` (`module_version`),
the README shields badge, and `auto-bmad/references/state-and-resume.md`
(`profiles_source_version`, the config.yaml schema example). "Publishing" is just **pushing a
`vX.Y.Z` git tag** (the BMAD
installer keys upgrade detection off stable tags; the Claude plugin marketplace reads the manifest
`version`).

Cut a release from a clean `main`:
1. Ensure this release's notes are under `## [Unreleased]` in `CHANGELOG.md`, grouped under
   Keep-a-Changelog headings. Write them by hand as changes land — never auto-generate from commits.
2. `python3 scripts/bump-version.py <patch|minor|major>` (or an explicit `X.Y.Z`; `--dry-run` to
   preview). It refuses an empty `[Unreleased]`, guards against version drift across the four files,
   promotes the changelog (date + compare links), rewrites all four versions, then commits
   `chore(release): vX.Y.Z` and tags it.
3. `git push --follow-tags`.

`.github/workflows/release.yml` then fires on the `v*` tag and creates the GitHub Release from that
tag's CHANGELOG section (idempotent; it verifies the tag agrees with all four version files and the
changelog first). That's the only CI — no build/publish step (`/auto-bmad reprovision` is a runtime
concern, not a release artifact).

## Conventions
- Conventional Commits (`feat:`/`fix:`/`docs:`/`test:`/`chore:`/`refactor:`).
- Never commit the local BMAD test install or any host config — `_bmad/`, `_bmad-output/`,
  `.agents/`, `.claude/`, `.codex/`, `.opencode/` are gitignored. The published repo is module +
  marketplace + docs only. **One deliberate exception** (a `.gitignore` negation): the tracked
  maintainer skill `.claude/skills/auto-bmad-compat-check/` — checks new releases (npm
  `latest`/`next`) of **both** packages auto-bmad delegates into — `bmad-method` (its "critical"
  contract owners are `bmad-build-auto` incl. the `customize.toml` review-layer schema,
  `bmad-sprint-planning`, `bmad-retrospective`) and the separately versioned
  `bmad-method-test-architecture-enterprise` (TEA, the `bmad-testarch-*` skills) — for impact on
  auto-bmad and offers to bump the README compat markers. It derives auto-bmad's skill surface from
  the `bmad-…` tokens in `SKILL.md` + `references/*.md`, so never spell a removed or shim skill name in a shipped
  file (the `state-and-resume.md` removed-keys note, self-test fixtures and `CHANGELOG.md` are the
  only sanctioned places). Repo tooling, not shipped inside the module; everything else under
  `.claude/` stays ignored.
- Markdown reference files are read by the orchestrator at runtime; keep them concise and
  unambiguous (they are instructions, not prose). Helper scripts stay dependency-free with a
  `--self-test`.
- Don't land a user-facing change without a `CHANGELOG.md` note under `## [Unreleased]` (right
  Keep-a-Changelog heading) in the same commit/PR. Never bump the version files by hand — use
  `scripts/bump-version.py` so all four stay in sync (see "Releasing").
- **Changelog entries are written to be skimmed.** A reader must grasp a release from the **bold
  lead lines alone**, in seconds. Enforce:
  - **One change = one bullet** under one heading. Never bundle (if you're writing "three
    reinforcing fixes", that's three bullets).
  - **Bold headline first, ≤ ~12 words, stating the user-visible effect** ("X no longer Y"), not the
    internal mechanism.
  - **At most ~2 sentences of detail** after the headline — the one fact a reader needs. No
    "Previously…/the gap was…/chicken-and-egg" debugging narrative; the *how* lives in the reference
    docs and the commit body.
  - **Hard cap: 2 wrapped lines per bullet (3 only for a major item)** — headline, detail, and
    trailing parenthetical all included. Over the cap? Cut detail, never the wrap width.
  - **No inline file-touch lists** — git history records touched files. If a pointer genuinely
    helps, one terse trailing parenthetical (`(pipeline.md, git-and-pr.md)`), never woven into
    sentences.
- **Past released `## [X.Y.Z]` sections are immutable** — apply this style to new entries only;
  never rewrite a shipped section (`release.yml` renders the GitHub Release from it).

## Known platform facts (verified)
- **Claude Code (2.1.232):** the Agent tool takes a **per-call `model`** and **no per-call effort**
  (effort inherits the session — per-phase effort on Claude is CLI-route/cross-model-layer only).
  Subagents nest to **depth 3 by default** (≥ 2.1.219): env `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`
  wins when set; non-integer or `< 1` values are **ignored** (⇒ default), `=1` disables nesting —
  so preflight hard-stops only on a parsed `1`. Since 2.1.198 subagents run **in the background by
  default** — build-auto needs synchronous spawns, so the orchestrator spawns every delegate in the
  foreground (`run_in_background: false`) and every delegate prompt mandates foreground spawns for
  build-auto's own subagents. `claude -p` flags used: `--model`, `--effort`
  (`low|medium|high|xhigh|max`), `--output-format json|text`, `--allowedTools`,
  `--dangerously-skip-permissions`.
- **Codex (0.147.0):** `spawn_agent` takes a per-call **`model` + `reasoning_effort`** (gpt-5.x:
  low|medium|high|xhigh — the only host with per-phase effort in-tool). Nesting: **V1 `[agents]
  max_depth` defaults to 1** (child depth > max_depth is rejected ⇒ a delegate can't spawn
  build-auto's subagents; `max_depth = 2` fixes it), **ignored under `features.multi_agent_v2`**
  (V2 has no depth guard). Config layering: project `<repo>/.codex/config.toml` overrides
  `~/.codex/config.toml` (`$CODEX_HOME`); `-c key=value` on `codex exec` overrides both (CLI route
  only). These keys are **source-verified (0.147.0), not in the public docs**. `codex exec` flags
  used: `-m`, `-c model_reasoning_effort=E`, `-c approval_policy=never`, `-s read-only`, `-C`, `-o`,
  `--ephemeral`, `--dangerously-bypass-approvals-and-sandbox` (`-a` is a top-level `codex` flag
  only). Model names are environment-specific — config, not hardcoded.
- **opencode (1.18.15):** the Task tool has **no per-call model/effort knob** (only `subagent_type`,
  plus resume/background flags ⇒ a delegate inherits the user's model; `opencode.model`/`variant` matter only on the CLI route and
  the cross-model layer). Nesting: top-level **`subagent_depth`** in `opencode.json` (default 1 —
  subagents can't spawn subagents; auto-bmad needs `2`), **and** a subagent gets `permission.task`
  denied unless its agent definition grants it (`agent.<name>.permission.task: allow`). Background
  subagents are opt-in (synchronous by default). `opencode run` flags used: prompt as the final
  positional **arg** (not stdin), `-m provider/model`, `--variant`, `--format json` (a JSONL event
  stream — parsed defensively by `cli_delegate.extract_opencode_result`), `--dir`, `--auto`
  (auto-approve permissions). Skills load from `.opencode/skills/`, `~/.config/opencode/skills/`
  **and** the `.claude`/`.agents` `skills/**/SKILL.md` roots. opencode injects
  `OPENCODE_SESSION_ID` into the shell env of commands it runs (host-detection signal).
- **BMAD (6.11.x)** has no portable abstraction for delegation or model/effort; modules are skills
  the installer copies into `.claude/skills/` (Claude Code) or `.agents/skills/` (Codex, opencode —
  the cross-tool standard; the installer warns about stale `.codex/skills/`/`.opencode/skills/`
  installs as legacy paths). The CLIs still *load* skills from more roots (see
  `delegation-runtime.md`), which is why preflight probes several dirs. Hence the tiered design.
- **BMAD `bmad-build` / `bmad-build-auto` render through `uv run --no-cache
  _bmad/scripts/render_skill.py`** (PEP 723 `requires-python >= 3.11`) and HALT when `uv` is
  unavailable — so `uv` + a Python ≥ 3.11 reachable by `uv` are hard prerequisites (preflight P3/P4;
  `uv python find '>=3.11' --no-python-downloads` is the side-effect-free probe). auto-bmad's own
  `python3` must also be ≥ 3.11 (`tomllib`).
- **BMAD central config is TOML — auto-bmad READS it, never writes it.** Four layers resolved
  highest-last: `_bmad/config.toml` → `config.user.toml` → `custom/config.toml` →
  `custom/config.user.toml` (tables deep-merge; arrays-of-tables merge by `code`/`id` — a repeated
  id **replaces**). `preflight.py --central-config-only` mirrors that merge with `tomllib` for
  `core.output_folder` + the BMM artifact paths — nothing else in auto-bmad reads the *central BMAD*
  TOML (`build_auto_custom.py` validates our own customization file, and preflight's nesting probe
  reads codex `config.toml`). The only BMAD *config* file auto-bmad writes is the **fenced managed
  region of `_bmad/custom/bmad-build-auto.toml`** (help-catalog rows and the `story_plan.py
  --mark-status` sprint-status flip aside; skill customization resolves `<skill>/customize.toml` →
  `_bmad/custom/<skill>.toml` → `<skill>.user.toml`, `[[workflow.review_layers]]` merged by `id`).
  The installer **still writes**
  per-module `_bmad/{code}/config.yaml` and other skills (e.g. `bmad-sprint-planning`) still load
  `_bmad/bmm/config.yaml` — preflight warns when it is missing (P11). A `--custom-source` install of
  `abm` registers `[modules.abm]` in `config.toml` + `_bmad/abm/config.yaml` — leave both alone.
- **Help catalog on 6.11:** `bmad-help` reads `_bmad/_config/bmad-help.csv`, which the installer
  **regenerates on every install/update** by merging every `_bmad/<module>/module-help.csv`
  (`installer.js mergeModuleHelpCatalogs`; `_config`/`custom`/`scripts`/`render` dirs skipped).
  So setup copies our rows to `_bmad/abm/module-help.csv` (survives re-installs) **and** merges them
  into the live catalog; the legacy shared `_bmad/module-help.csv` is read by nothing upstream.
- **v6 shims:** the installer classifies a skill as a shim by `metadata.lifecycle: shim` in its
  SKILL.md frontmatter (`shim-policy.js`); a fresh install ships **none** unless `--shims`
  (`--no-shims` forces them off). Never require or name a shim skill.
- **BMAD `--custom-source` install (how `abm` installs):** a bare URL clones the **default branch
  HEAD** and records `channel: next`; the version selector is an `@<tag-or-branch>` suffix
  (`…/auto-bmad@v0.20.1` ⇒ `channel: pinned`; raw SHAs unsupported) — `custom-module-manager.js
  parseSource`/`cloneRepo` (`cloneRepo` takes no channel argument). So the README's bare
  install/update commands track `main` HEAD — pin with `@<tag>` for a release. Cache:
  `~/.bmad/cache/custom-modules/`.
- **BMAD update of a custom-source module (`abm`, 6.11):** `--action quick-update` now **refreshes
  URL-backed cached custom repos** before re-deploying (`findModuleSourceByCode … _refreshRepoCacheOnce`
  → `cloneRepo(rawInput, pinOverride)`: `next` ⇒ latest default-branch commits, `pinned` ⇒ the
  pinned ref) — but only for modules found in that cache; a marketplace-installed / self-registered
  `abm` with no cache entry is skipped ("no source available"). Re-supplying the source —
  `npx bmad-method install --action update --custom-source <repo-url> --yes` — works in every case,
  so the README "Updating" section recommends it.
- **Sprint-status grammar** (`bmad-sprint-planning/scripts/sprint_plan.py`): story keys match
  `^(\d+)-(\d+)([a-z]?)-.+` (the `[a-z]?` is the split suffix, e.g. `2-6a-…`); epics headings
  `EPIC_RE`/`STORY_RE` (`Story (\d+)\.(\d+[a-z]?)`) — `story_plan.py` mirrors both exactly; the
  `last_updated` stamp format is `%m-%d-%Y %H:%M`. Statuses: `backlog|ready-for-dev|in-progress|review|done`.
- **`bmad-build-auto` contracts are prose, parse defensively:** the HALT protocol writes the spec
  frontmatter `status` + a `## Auto Run Result` block with `Status:` / `Blocking condition:` lines
  (a no-spec HALT writes a `bmad-build-auto-result-*.md` skeleton instead); `Halt after planning.`
  is the "standard phrasing" that stops after step 2 at `ready-for-dev` (build-auto accepts "any
  clear equivalent"); a dirty tree, `no subagents`, `intent gap`, `blocked spec supplied` etc. are
  `blocked` blocking conditions. build-auto commits its own diff and never pushes. `story_plan.py
  --spec` is the only reader.
- **Shell globs:** the orchestrator's probe commands run under whatever shell the host uses (zsh,
  fish, bash). An unmatched glob is fatal in zsh/fish (`nomatch` ⇒ exit 1), and the `for f in
  *.glob; do …` loop syntax isn't even portable to fish — so probes must not iterate raw globs.
  Use `find … -name '<pat>'` (external binary, empty output + exit 0 everywhere) or Python.
