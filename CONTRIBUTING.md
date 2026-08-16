# Contributing to auto-bmad

Thanks for helping improve `auto-bmad`! This guide covers local development, testing, and the
conventions we follow. By participating you agree to our [Code of Conduct](./CODE_OF_CONDUCT.md).

## Repository layout

```
.claude-plugin/marketplace.json        # Claude distribution; lists the single ./auto-bmad skill
auto-bmad/                             # the BMAD standalone module (one skill)
  SKILL.md                             # orchestrator entry point
  references/                          # phase + epic playbooks, delegation, TEA policy, git, state
  assets/                              # module identity, setup, defaults
    profiles.yaml                      # source of truth: per-profile, per-tool model + effort
                                       # (no persona text; no rendered agent files)
    config-defaults.yaml               # constant-default setup-block keys the Phase 0 drift
                                       # heal appends to an existing config.yaml
    bmad-custom/bmad-build-auto.toml   # template for auto-bmad's two review layers (security,
                                       # cross-model); build_auto_custom.py bakes it into the
                                       # project's _bmad/custom/bmad-build-auto.toml
    module.yaml, module-help.csv, module-setup.md   # module identity + self-registration flow
  scripts/                             # dependency-free helpers, each with --self-test
    story_plan.py                      # story-source adapter: --resolve / --epic readers,
                                       # --mark-status flip, --find-spec / --spec, --retro-verdict
    state_plan.py                      # auto-bmad state-file reader (resume detection);
                                       # --finalize evaluates the Phase 9 draft predicate
    state_update.py                    # deterministic state/report writer
    config_plan.py                     # detects/heals profiles<->config drift (Phase 0 self-heal)
    preflight.py                       # one-call Phase 0 preflight (central TOML, uv/Python 3.11,
                                       # nesting, git, skills, CI, AGENTS.md — hard-stops)
    build_auto_custom.py               # syncs the managed review-layers region into
                                       # _bmad/custom/bmad-build-auto.toml (setup / reprovision)
    ci_wait.py                         # Phase 9 CI wait; classifies the ci_status verdict
    deferred_ledger.py                 # deferred-work ledger: harvest / plan / sha-guarded archive
    cli_delegate.py                    # resolves opt-in per-phase external-CLI delegation
                                       # (claude -p / codex exec / opencode run) + the cross-model
                                       # layer's command + preflight validation
    merge-config.py, merge-help-csv.py # vendored BMAD-template merge scripts (installer environment)
CHANGELOG.md                           # hand-maintained; source for release notes
scripts/bump-version.py                # release helper (repo tooling; does NOT ship in the skill)
skills/reports/                        # tracked module-validation snapshots (repo tooling)
docs/                                  # migration plan + upstream capability backlog (repo docs)
.claude/skills/auto-bmad-compat-check/ # tracked maintainer skill: checks new BMAD/TEA releases for
                                       # impact on auto-bmad (repo tooling; does NOT ship)
```

The published repo contains the module + marketplace + docs, plus the repo tooling above
(`scripts/bump-version.py`, `skills/reports/`, and the one tracked maintainer skill under
`.claude/skills/` — a deliberate `.gitignore` exception). A full BMAD install plus local host
config (`_bmad/`, `_bmad-output/`, `.agents/`, `.claude/`, `.codex/`, `.opencode/`) may exist
locally as a test sandbox; it is gitignored — never commit it. Nothing is generated per tool any
more (no rendered agent files).

## Local development & testing

1. **Run the deterministic self-tests** (no Claude Code needed):
   ```bash
   python3 auto-bmad/scripts/story_plan.py --self-test
   python3 auto-bmad/scripts/state_plan.py --self-test
   python3 auto-bmad/scripts/state_update.py --self-test
   python3 auto-bmad/scripts/preflight.py --self-test
   python3 auto-bmad/scripts/config_plan.py --self-test
   python3 auto-bmad/scripts/cli_delegate.py --self-test
   python3 auto-bmad/scripts/build_auto_custom.py --self-test
   python3 auto-bmad/scripts/ci_wait.py --self-test
   python3 auto-bmad/scripts/deferred_ledger.py --self-test
   python3 scripts/bump-version.py --self-test
   # maintainer-only compat-check skill (repo tooling, not shipped in the module):
   python3 .claude/skills/auto-bmad-compat-check/scripts/bmad_compat.py --self-test
   # story_plan.py also runs standalone (one mode per call; output is JSON), e.g.:
   python3 auto-bmad/scripts/story_plan.py --epic 1 --sprint-status path/to/sprint-status.yaml
   python3 auto-bmad/scripts/story_plan.py --resolve 1-3 --sprint-status path/to/sprint-status.yaml
   ```

2. **Install it live** to try the skill end-to-end — add this repo as a local marketplace
   (Claude Code) or as a BMAD module source, then run `/auto-bmad` in a BMAD project:
   ```text
   /plugin marketplace add /absolute/path/to/this/repo
   /plugin install auto-bmad@auto-bmad
   ```
   Re-run `/plugin marketplace update auto-bmad` after edits to pick up changes, and
   `/auto-bmad reprovision` to re-sync the review-layers TOML after retuning `profiles` or
   `code_review` in the runtime config.

3. **Validate the module structure and manifest:**
   ```bash
   python3 -m json.tool .claude-plugin/marketplace.json >/dev/null
   # BMAD module validator (run from the repo root, which holds the one skill):
   python3 .claude/skills/bmad-module-builder/scripts/validate-module.py .
   ```

## Making changes

- **Pipeline behavior** lives in `auto-bmad/references/pipeline.md`. Keep the orchestrator a pure
  delegator — it must never implement story work, read or edit story code, or edit a build-auto
  spec. A small set of git / preflight / status write-back / finalize bookkeeping actions are the
  documented exceptions it owns directly — see `CLAUDE.md` → "Core principle" for the list.
- **Review extras are review layers, not orchestrator steps.** auto-bmad's security and cross-model
  reviews are two `[[workflow.review_layers]]` tables that `bmad-build-auto` runs inside its own
  review step. Their template is `auto-bmad/assets/bmad-custom/bmad-build-auto.toml`; the tested
  `scripts/build_auto_custom.py` bakes it into the project's `_bmad/custom/bmad-build-auto.toml`
  managed region. Keep the template in lockstep with upstream `bmad-build-auto/customize.toml`'s
  layer schema (an upstream change to that schema is a compat break); never re-implement review
  in the orchestrator.
- **Epic-mode behavior** (`/auto-bmad epic`) lives in `auto-bmad/references/epic-pipeline.md`. It
  reuses the per-story phases as the epic's inner loop, so a per-story phase change usually flows
  into epic mode for free; the same delegate-only rule applies.
- **Per-skill delegation prompts** live in `auto-bmad/references/delegation.md`. Every prompt is
  self-contained (role line first, autonomy directive last). New BMAD skills get a prompt template
  here, never inline ad-hoc text.
- **Delegate profiles** live in `auto-bmad/assets/profiles.yaml` — the single source of truth for
  each profile's per-tool model + effort (`claude.model`/`effort`, `codex.model`/`reasoning_effort`,
  `opencode.model`/`variant`) and the `phase_profiles` mapping. There are no persona strings and no
  rendered agent files: a delegate is a generic host subagent spawned at the profile's model. Add a
  profile only when an existing one doesn't fit; the security / cross-model layer models are baked
  into the review-layers TOML from these profiles (`/auto-bmad reprovision` re-syncs it).
- **TEA selection rules** live in `auto-bmad/references/tea-policy.md`.
- **External-CLI routing** (the opt-in `delegation.cli_phases` path) and the cross-model layer's
  command are documented in `references/delegation-runtime.md`; their per-tool flag matrix +
  preflight validation live in the tested `scripts/cli_delegate.py`, never in orchestrator prose —
  keep them there.
- **Every user-facing change needs a `CHANGELOG.md` note** under `## [Unreleased]` (correct
  Keep-a-Changelog heading) in the same PR. Never bump the version files by hand — `scripts/bump-version.py`
  keeps the four version strings in sync at release time.

## Commit & PR conventions

- Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`,
  `test:`, `chore:`, `refactor:` (this is also what the orchestrator generates).
- Keep PRs focused; describe the change and how you tested it.
- Run the self-tests, manifest validation, and the module validator before opening a PR.

## Reporting bugs & ideas

Open a GitHub issue with steps to reproduce (and a minimal `sprint-status.yaml` excerpt where
relevant). Report security vulnerabilities **privately** via
[GitHub Security Advisories](https://github.com/stefanoginella/auto-bmad/security/advisories/new).
For conduct concerns, see the [Code of Conduct](./CODE_OF_CONDUCT.md).
