# CLAUDE.md — working in the auto-bmad repo

This repo is a **BMAD standalone module** (one skill + a Claude `marketplace.json`). The skill
(`auto-bmad`) is an orchestrator that runs the full BMAD story workflow one story at a time — or, with
`/auto-bmad epic`, a whole epic in one run (`references/epic-pipeline.md`) — on **Claude Code, Codex,
or opencode**. This file is guidance for working **on the module**, not for using it.

## Core principle (do not violate)
The orchestrator **delegates BMAD work and reports** — it must never implement story work or run
`/bmad-*` skills directly. Every BMAD step (create-story, dev-story, code-review, TEA, retro,
project-context bootstrap/refresh) runs in a delegated `ab-*` sub-agent — code-review as a **fan-out**
of delegates the orchestrator drives (see the owns-directly list). **Preserve this separation
when editing.**

The orchestrator owns a small set of actions **directly** (never delegated) — all git/finalize
bookkeeping it already holds full pipeline context for. Don't "fix" these into delegated steps:
- **Git/PR work** — preflight, branching, per-phase commits, push, PR, and the Phase 9 merge prompt.
- **Phase 0 project-context probe** — an existence check that only decides whether Phase 2's
  bootstrap sub-step runs (the bootstrap itself is delegated like every other skill call).
- **Phase 5 sprint-status write-back** — after the feat commit, script the BMAD-status flip to
  `review` (sprint-status entry + story file) with `story_plan.py --mark-status`, rather than
  trusting the dev-story delegate's LLM-only step-9 sync (the drift root cause). Same helper and
  rationale as the Phase 9 `done` flip.
- **Phase 9 finalize writes** — BMAD-status flip to `done` + the pre-push pipeline-report commit.
- **Phase 8 deferred-work archive** — at epic-end, after the project-context refresh **and the
  delegated deferred-work reconcile** (a `deferred_reconcile` delegate that marks any ledger item
  whose deferred work actually landed but went unmarked — that judgment reads code, so it is
  delegated, not direct), move fully-resolved entries out of the active `<impl>/deferred-work.md`
  ledger into the sibling `deferred-work-resolved.md` archive. No `/bmad-*` skill prunes the ledger,
  and the orchestrator already writes this file directly at Phase 7 — so the archive itself is
  connective bookkeeping, not a delegate.
- **Phase 7 code-review fan-out** — `/bmad-code-review` fans out to three review subagents internally,
  which a delegate can't (no nested subagents). So the orchestrator hoists the fan-out: it builds the
  diff (git) and spawns the review lenses (three per configured reviewer model, 3–9 in total) + the
  triage as delegates. **The lenses and triage are
  all delegated; the orchestrator only routes the diff and findings by path and never reads
  either.** Because auto-bmad here mirrors the upstream skill's
  *internal* structure (lens roster, the inline Acceptance Auditor prompt, the triage rubric), an
  upstream `bmad-code-review` change can drift silently — keep the replica in lockstep.
  **Three deliberate auto-bmad-local additions ride on top of the replica** (fenced with
  `auto-bmad-local` markers so a compat-check sees them as intentional, not drift): (1) a
  single-instance `code-review-security` delegate per iteration (gated by
  `code_review.security_review`, off the `3×R` lens total — it gates via finding severity); (2) a
  triage **security-severity map + Low keep/drop test** — both in `delegation.md` (security entry +
  triage edits) and `pipeline.md` (Phase 7 step 1); and (3) a triage **recommended resolution per
  `[Review][Decision]`** (a `fix`/`defer`/`dismiss` channel + direction) that **epic mode** applies
  autonomously instead of asking the user — `delegation.md` (triage REPORT/PERSIST) + `epic-pipeline.md`
  (E5f / E_review). Per-story mode is unchanged (the recommendation is advisory; the human still picks).
- **Phase 7 external-change handling** — at the end-of-loop human halt, the orchestrator detects any
  external-review changes with a **git-only check** (never a code read), commits them, and re-opens
  the halt. The **re-review of those changes is delegated** like every other review (the same
  fan-out, full reviewer roster) and its findings gate the re-halt — not an inline read. **The
  orchestrator never inspects code at any tier — keep it that way.**

The mechanics of these live in the reference docs — **don't restate them here**: `git-and-pr.md`
(branching, push, PR, merge prompt), `pipeline.md` (Phase 0 probe, Phase 5 sprint-status write-back,
Phase 7 code-review fan-out, Phase 7 external-change handling, Phase 8 deferred-work archive, Phase 9
status flip + report commit), and
`delegation.md` (the code-review fan-out's delegate entries). The only other time the
orchestrator does delegated step work itself is the `inline` delegation tier (see
`delegation-runtime.md`), and even then it follows the same phase contract.

## Delegation is tiered (the heart of the module)
BMAD abstracts neither sub-agent delegation nor per-agent model/effort, so we supply those with
tool-native files and degrade gracefully:
- **Tier 1 `custom-subagents`** (Claude Code, Codex, opencode) — each step runs in an isolated
  delegate at the profile's tuned model + effort (Claude `.claude/agents/ab-*.md`; Codex
  `.codex/agents/ab-*.toml`; opencode `.opencode/agent/ab-*.md` — **model-only**: no effort knob,
  and a blank model ⇒ the delegate inherits the user's opencode default model).
- **Tier 2 `general-subagents`** — generic subagents, no effort knob (effort not honored).
- **Tier 3 `inline`** — no subagents; run the step in-context (documented last resort).

Orthogonal to the tiers, an **opt-in per-phase external-CLI route** (`delegation.cli_phases`) can send
a chosen phase to `claude -p` / `codex exec` / `opencode run` instead of an in-tool sub-agent — for
cross-tool (and, via opencode, cross-vendor) diversity. It reads the *same* `profiles` blocks
(claude→`--effort`, codex→`model_reasoning_effort`, opencode→`--variant`; opencode's model + variant
are both optional ⇒ inherit the user's opencode defaults),
is still delegation (the orchestrator builds the command + parses the result, never reads code),
hard-stops on a failed preflight (binary/skills/auth), and leaves the three tiers untouched. The
per-tool flag matrix + validation live in `scripts/cli_delegate.py` (tested), not orchestrator prose;
keep them there. Default empty ⇒ all in-tool.

`assets/agents/profiles.yaml` is the **single source of truth** (per-profile, per-tool model+effort
plus tool-neutral persona strings); `phase_profiles` maps each phase to a profile; and
`scripts/render-agents.py` generates the tool-native files from it. Host/mode are `auto` and
re-detected every run, so one provisioned project runs under any of those tools with no
reconfiguration; `target_tools` only controls which agent files get generated. Full detail:
`delegation-runtime.md`
(host detection + the tiers + the `cli_phases` route) and `state-and-resume.md` (config/profiles
schema, first-run).

## Layout & where behavior lives
- `.claude-plugin/marketplace.json` — Claude distribution (lists the single `./auto-bmad` skill).
- `auto-bmad/SKILL.md` — orchestrator entry point (On-activation gate + procedure). Keep it thin.
- `auto-bmad/references/` — where the real detail lives; each file owns one area:
  - `pipeline.md` — per-phase (per-story) playbook.
  - `epic-pipeline.md` — the `/auto-bmad epic` E-step flow (reuses the per-story phases as the epic's
    inner loop; Tier-A thin per-story review + Tier-B epic integration review).
  - `delegation.md` — exact per-skill prompts (tool-agnostic).
  - `delegation-runtime.md` — host detection + the three spawn tiers.
  - `tea-policy.md` — TEA risk rubric / selection.
  - `git-and-pr.md` — branching, commits, push, PR, merge prompt.
  - `state-and-resume.md` — config/state schema, first-run, profiles.
  - `overrides.md` — invocation-override vocabulary.
- `auto-bmad/assets/agents/profiles.yaml` — the single per-profile source (model/effort + persona
  strings). `claude/agent.md.tmpl`, `codex/agent.toml.tmpl` + `opencode/agent.md.tmpl` — one shared
  body template per tool the renderer fills in, so the `ab-*` personas can't drift between tools. The renderer renders **every**
  `ab-*` profile in its source — the shipped four plus any user-added custom profiles in the runtime
  config (non-`ab-` names are skipped with a warning; custom profiles are first-class in
  config_plan.py too: the heal ignores them, a whole-block reset prunes them).
- `auto-bmad/assets/config-defaults.yaml` — the source of truth for the **constant-default
  setup-block** keys (`delegation`/`tea`/`git`/`code_review`) that the Phase 0 drift heal appends to
  an existing `config.yaml` (those blocks are otherwise setup answers with no asset). Deliberately
  **omits** environment-detected/interviewed fields (`git.base_branch`, `delegation.target_tools`,
  `host`/`mode`, `tea.enabled`/`framework_ci`, `git.mode`) so the append-only heal can never write a
  wrong static value. Lockstep: each default must equal the orchestrator fallback **and** the
  `state-and-resume.md` schema (config_plan.py's `--self-test` enforces the include/exclude sets).
- `auto-bmad/assets/module.yaml` + `module-help.csv` + `module-setup.md` — module identity,
  capability registry, and the self-registration/provisioning flow.
- `auto-bmad/scripts/` — dependency-free helpers, each with a `--self-test` and a self-documenting
  docstring (read the script for exact behavior):
  - `story_plan.py` — sprint-status reader; `--mark-status KEY --to STATUS` scripts the BMAD-status
    flip (sprint entry + story-file `Status:`, byte-preserving, idempotent) — Phase 5 (→ `review`)
    and Phase 9 (→ `done`, also via the back-compat `--mark-done` alias).
  - `state_plan.py` — auto-bmad `state/{key}.yaml` reader (resume detection); `--finalize`
    evaluates the Phase 9 draft predicate / clean-completion verdict (`flip_bmad_status`).
  - `state_update.py` — deterministic per-story state/report/retro writer: full-schema state
    writes (init / JSON patch / phase-done), the timing-start/-pause clock brackets, literal
    report-section rendering, and skip-empty retro appends. Lockstep-self-tested against the
    `state-and-resume.md` schema block.
  - `render-agents.py` — agent generator from `profiles.yaml`.
  - `config_plan.py` — detects and additively heals drift between the shipped defaults
    (`profiles.yaml` for `profiles`/`phase_profiles`; `config-defaults.yaml` for the constant-default
    setup-block keys) and a project's runtime `config.yaml`. Append-only (`--apply`); `--reset`
    overwrites the profiles blocks back to shipped values (a whole-block scope also **prunes**
    profiles the asset no longer ships — the rename/drop remedy, surfaced as `removed_profiles`)
    but never the setup blocks.
  - `preflight.py` — one-call Phase 0 preflight: git state/mode, project-context, CI, required
    skills, framework detection — single JSON with hard-stop reasons.
  - `review_findings.py` — Phase 7 reconciliation reader for a story's `### Review Findings`.
  - `review_loop.py` — Phase 7 loop driver: `prep-diff` builds the review diff in a temp dir,
    `gate` encodes the loop's decision table, `post-fix` verifies each fix pass.
  - `ci_wait.py` — Phase 9 CI wait: polls `gh pr checks`, classifies the pinned `ci_status`
    verdict (passed/failed/timeout/none), and resolves `ci_run_url` by head SHA.
  - `deferred_ledger.py` — Phase 8 deferred-work archive mechanics: `plan` reads ledger entries +
    resolution hints, `archive` moves chosen entries atomically (sha-guarded); keep-vs-move
    judgment stays with the LLM.
  - `cli_delegate.py` — resolves the opt-in external-CLI delegation for a phase (`delegation.cli_phases`):
    builds the `claude -p` / `codex exec` argv + model/effort from the phase's profile, and preflight-
    validates binary/skills/auth. Pure `resolve()` + live `validate()`.
  - `merge-help-csv.py` — the live self-registration: merges abm's help rows into the shared
    `_bmad/module-help.csv` (anti-zombie; PyYAML via the installer's environment).
  - `merge-config.py` — **retained only to satisfy the standalone-module validator**
    (`validate-module.py` requires the file to exist); auto-bmad **does not invoke it**. abm never
    writes the installer-owned central BMAD config (see the TOML-layout fact below) — its real
    config is the runtime `{output_folder}/auto-bmad/config.yaml`. Don't reintroduce a call to it.
  - **Both of the above are VENDORED**, not ours: verbatim copies from
    `bmad-code-org/bmad-builder` (`skills/bmad-module-builder/assets/standalone-module-template/`),
    MIT © BMad Code, LLC. Each carries a provenance header with its origin, sync SHA, and local-delta
    list — **record every local edit there**, or the next re-sync silently reverts it. Prefer fixing
    a bug upstream and re-syncing over diverging. Note the upstream lives in `bmad-builder`, a
    *separate* repo from `BMAD-METHOD`.
- **Repo-root tooling, NOT shipped in the skill:** `CHANGELOG.md` (hand-maintained),
  `scripts/bump-version.py` (release helper — see "Releasing"), `skills/reports/` (tracked
  module-validation snapshots), `docs/` (placeholder).

## Testing
```bash
# Deterministic cores:
python3 auto-bmad/scripts/story_plan.py --self-test
python3 auto-bmad/scripts/state_plan.py --self-test
python3 auto-bmad/scripts/state_update.py --self-test
python3 auto-bmad/scripts/preflight.py --self-test
python3 auto-bmad/scripts/render-agents.py --self-test
python3 auto-bmad/scripts/config_plan.py --self-test
python3 auto-bmad/scripts/review_findings.py --self-test
python3 auto-bmad/scripts/review_loop.py --self-test
python3 auto-bmad/scripts/cli_delegate.py --self-test
python3 auto-bmad/scripts/ci_wait.py --self-test
python3 auto-bmad/scripts/deferred_ledger.py --self-test
# Maintainer-only skill (tracked under .claude/ via gitignore exception; NOT shipped to users):
python3 .claude/skills/auto-bmad-compat-check/scripts/bmad_compat.py --self-test
# Marketplace manifest is valid JSON:
python3 -m json.tool .claude-plugin/marketplace.json >/dev/null
# Module structure passes the BMAD validator (run from the repo root, which holds the one skill):
python3 .claude/skills/bmad-module-builder/scripts/validate-module.py .
# Live: add this repo as a local marketplace (Claude) or BMAD module source, install, run
# /auto-bmad in a BMAD project. `/auto-bmad reprovision` re-renders agents after editing profiles.
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
changelog first). That's the only CI — no build/publish step, and nothing re-renders agents on bump
(`/auto-bmad reprovision` is a runtime concern, not a release artifact).

## Conventions
- Conventional Commits (`feat:`/`fix:`/`docs:`/`test:`/`chore:`/`refactor:`).
- Never commit the local BMAD test install or generated agents — `_bmad/`, `_bmad-output/`,
  `.agents/`, `.claude/`, `.codex/` are gitignored. The published repo is module + marketplace +
  docs only. **One deliberate exception** (a `.gitignore` negation): the tracked maintainer skill
  `.claude/skills/auto-bmad-compat-check/` — checks new releases (npm `latest`/`next`) of **both**
  packages auto-bmad delegates into — `bmad-method` and the separately versioned
  `bmad-method-test-architecture-enterprise` (TEA, the `bmad-testarch-*` skills) — for impact on
  auto-bmad and offers to bump the README compat markers. It's repo tooling, not shipped
  inside the module (like `scripts/bump-version.py`); everything else under `.claude/` stays ignored.
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
- **Claude Code:** sub-agents take `model:` + `effort:` frontmatter (effort is settable ONLY
  there, not via the Agent tool — hence the templates); they CAN invoke skills but CANNOT spawn
  sub-agents. `.claude/agents/` is scanned into the invokable roster **only at process launch** —
  agents rendered mid-session (first-run setup, reprovision) aren't invokable until a full quit &
  relaunch (`/clear` reuses the same process and does not re-scan).
- **Codex:** subagents are TOML files in `.codex/agents/` (project) or `~/.codex/agents/`, with
  `model` + `model_reasoning_effort` (gpt-5.x effort: low|medium|high|xhigh — xhigh is the ceiling);
  invoked by naming the agent in natural language — Codex spawns/collects them, **in parallel**
  when several are named in one request (subagents GA 2026-03-16, on by default; `[agents]`
  `max_threads` defaults to 6, `max_depth` defaults to 1 ⇒ a subagent can't spawn subagents, so
  the Phase 7 fan-out hoist still stands). Model names are
  environment-specific (retunable per install), so they're config, not hardcoded — the shipped
  defaults are real.
- **opencode** (verified against v1.16.2): markdown subagents in `.opencode/agent/` (SINGULAR —
  `agent list` registers plural too, but docs/convention are singular); frontmatter `mode: subagent`
  + optional `model: provider/model`, **no `name:` needed** (filename is the agent name) and **no
  portable per-agent effort knob** (reasoning is provider-shaped — `reasoningEffort`/`thinking` —
  set per-agent-name in `opencode.json`, NOT in our agent files; that's why opencode is model-only).
  Parallel subagent fan-out works (user-confirmed) — in-tool lenses run concurrently here too.
  Multi-provider, so there's no shippable default ⇒ `opencode.model` ships BLANK (inherit). opencode
  injects **`OPENCODE_SESSION_ID`** into the shell env of commands it runs (host-detection signal).
  Headless: `opencode run` — prompt is a positional **arg** (NOT stdin), `-m provider/model`,
  `--variant high|max|minimal` (reasoning), `--dir` (cwd, no `cd` needed), `--format json` (a JSONL
  event stream — parsed defensively by `cli_delegate.extract_opencode_result`, hard-stop on empty),
  `--dangerously-skip-permissions`. Skills load from `.opencode/skills/` or `~/.config/opencode/skills/`.
- **BMAD** has no portable abstraction for delegation or model/effort; modules are skills copied
  into a tool's skills dir (`.claude/skills/`, `.codex/skills/`, `.opencode/skills/`). Hence the tiered design.
- **BMAD install channels (since 6.8.0, #2305) — and why they DON'T govern `abm`:** for
  *registered/official* modules the installer resolves each to a git ref by *channel* — `stable`
  (highest semver release **tag**, the default), `next` (default-branch **HEAD**, i.e. `main`), or
  `pinned` (exact ref); flags `--channel`, `--all-stable`/`--all-next`, `--next=<code>`,
  `--pin <code>=<tag>`. **An ad-hoc `--custom-source <url>` (how `abm` installs) bypasses all of that**
  — *confirmed by live isolated install*: a bare URL clones the **default branch (`main` HEAD)** and
  records `channel:"next"`, and `--channel stable`/`--all-next` are **ignored** for it (marker stays
  `next`/`main`). The **only** version selector for a custom-source URL is an `@<tag-or-branch>` suffix
  (`…/auto-bmad@v0.20.1` ⇒ `channel:"pinned"`; raw SHAs unsupported), parsed by
  `custom-module-manager.js parseSource`. So the README's bare install/update commands track `main`
  HEAD — pin with `@<tag>` for a release; the `bmad-method@next` *installer* can't change a
  custom-source ref either.
- **BMAD update of a custom-source module (`abm`):** `--action quick-update` only re-pulls modules
  cached under `~/.bmad/cache/` and **skips custom-source re-cloning entirely** (`installer.js
  quickUpdate` adds a custom module only if `findModuleSourceByCode` hits a cached repo). And
  `resolveInstalledModuleYaml` never searches the project tree, so a self-registered/
  marketplace-installed `abm` shows `source: unknown` in `_bmad/_config/manifest.yaml` and emits
  benign `could not locate module.yaml for 'abm'` warnings on every update. Fix: re-supply the
  source — `npx bmad-method install --action update --custom-source <repo-url> --yes` (re-clones,
  rewrites the manifest source). So the README "Updating" section must recommend `--action update
  --custom-source …`, **never** bare `quick-update`.
- **BMAD central config went TOML (6.8.x; verified against 6.8.1-next.9) — and `abm` must not touch
  it.** The installer now owns a **four-layer TOML** config resolved by `src/scripts/resolve_config.py`
  (highest-last): `_bmad/config.toml` (team) → `_bmad/config.user.toml` (user) → `_bmad/custom/config.toml`
  → `_bmad/custom/config.user.toml` (the `custom/` pair is **never** touched by the installer). Tables
  deep-merge; arrays-of-tables merge by `code`/`id`. The unified `_bmad/config.yaml` is **dead** — 0
  shipped skills read it (the BMAD module-builder scaffold still *writes* it for self-registered
  modules, so it's a tolerated-but-inert marker). The installer **still writes** per-module
  `_bmad/{code}/config.yaml` (legacy compat — that's why Step 0.2's `_bmad/bmm/config.yaml` read is
  safe; latent fragility if BMAD ever drops it). A `--custom-source` install of `abm` registers
  `[modules.abm]` in `config.toml` **and** a per-module `_bmad/abm/config.yaml` — leave both alone.
  **Net for auto-bmad:** self-register via `_bmad/module-help.csv` + the runtime config only; the
  On-activation gate keys off the runtime config's existence, never an `abm` section in any central
  config. (`resolve_config.py` needs Python **3.11+** for stdlib `tomllib`; don't make abm depend on it.)
- `/bmad-create-story` has no `validate` mode; it self-validates against its checklist.
- **Shell globs:** the orchestrator's probe commands run under whatever shell the host uses (zsh,
  fish, bash). An unmatched glob is fatal in zsh/fish (`nomatch` ⇒ exit 1), and the `for f in
  *.glob; do …` loop syntax isn't even portable to fish — so probes must not iterate raw globs.
  Use `find … -name '<pat>'` (external binary, empty output + exit 0 everywhere) or Python.
