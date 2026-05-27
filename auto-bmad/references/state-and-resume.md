# Config, state, resume & first-run

Everything auto-bmad persists lives under `{project-root}/_bmad-output/auto-bmad/`:

```
_bmad-output/auto-bmad/
  config.yaml                 # project config (created on first run)
  state/{key}.yaml            # one resumable state file per story
  retro-notes/epic-{e}.md     # accumulated notes feeding the epic retrospective
  reports/{key}.md            # per-story report log (appended each run; see below)
```

## config.yaml
```yaml
version: 1
delegation:                # spawn mechanism — host/mode auto-detected each run
  host: auto               # auto (detect each run) | claude-code | codex | other
  mode: auto               # auto (derive from host) | custom-subagents | general-subagents | inline
  target_tools:            # tools to provision agents for; detected from installed skill dirs and
    - claude-code          # confirmed at first run (.claude/skills=>claude-code, .agents/skills=>
    - codex                # codex). Listing more than one = run in either tool with no reconfig.
tea:
  enabled: true            # set at first run after checking TEA skills exist
  framework_ci: prompt     # prompt | done | skip  (resolved at first run)
git:
  mode: auto               # auto -> detect; or force "remote" / "local"
  branch_prefix: "story/"
  base_branch: main        # auto-detected; written after first detection
code_review:
  max_iterations: 3
  alternate_models: true   # odd iters use code_review_review, even iters code_review_review_secondary
# profiles + phase_profiles complete the file but are NOT reproduced here (with values) on
# purpose — their single source is assets/agents/profiles.yaml, which render-agents.py reads and
# first run copies in verbatim. Edit that file (or this per-project copy) then `/auto-bmad
# reprovision`. Shape only — see the asset for the actual model/effort defaults:
profiles: {…}              # ab-max | ab-xhigh | ab-high | ab-fast, each:
                           #   {claude: {model, effort}, codex: {model, reasoning_effort}}
phase_profiles: {…}        # create_story, dev_story, code_review_review,
                           #   code_review_review_secondary, code_review_fix, tea_per_story,
                           #   tea_epic, retrospective, project_context
                           # (git/PR work is run by the orchestrator directly — no delegate profile)
```

**`assets/agents/profiles.yaml` is the single source of truth for both blocks** — the default
model/effort (`profiles`) and the phase→profile binding (`phase_profiles`, whose keys the
pipeline/delegation playbooks name instead of raw profile names). First run copies it here
verbatim; this schema shows only the *shape* so the asset and the doc can never drift.
`delegation.host`/`mode` default to `auto` and are **re-detected each run**, so the same config
runs in Claude Code or Codex with no reconfiguration; `target_tools` only controls which agent
files were provisioned (see `delegation-runtime.md`). Codex model names ship as real defaults;
retune `profiles` (in the asset) if your install differs.

## First-run flow (only when config.yaml is absent)
The single interactive episode in normal operation. Always confirm `target_tools`, then offer
**quick vs full** setup. Use AskUserQuestion.

0. **Seed delegation & profiles (non-interactive):** set `delegation.host`/`mode` to `auto`
   (re-detected each run — see `delegation-runtime.md`). Copy the `profiles` and `phase_profiles`
   defaults from `{skill-root}/assets/agents/profiles.yaml` — these are file-editable, never
   interviewed (point the user to `config.yaml` + `/auto-bmad reprovision` to retune). Detect the
   live host; if it needs `custom-subagents` but its agent files are missing, run `reprovision`
   (`scripts/render-agents.py`) before the pipeline starts.
1. **Confirm `target_tools` (always):** if `module-setup.md` already ran *this session* (fresh
   registration), it already confirmed `target_tools` — reuse the `abm` value, don't re-ask.
   Otherwise (the common case — BMAD pre-registered the module, so setup was skipped, and the
   `abm` value is unconfirmed) **re-detect from the installed skill dirs on disk, not just the
   `abm` section**: `claude-code` if `.claude/skills/auto-bmad/` exists; `codex` if
   `.agents/skills/auto-bmad/` (BMAD installs Codex skills under `.agents/`) or
   `.codex/skills/auto-bmad/` / `~/.codex/skills/auto-bmad/` exists. Present that set (unioned with
   the `abm` value, preferring on-disk detection and noting any mismatch) as the default and **ask
   the user to confirm** — they may drop one or add a tool they'll install later. If the confirmed
   set differs from what agents were rendered for, run `reprovision` for it. (Mirrors
   `assets/module-setup.md` → "Provision Delegate Agents".)
2. **Choose setup depth:** ask **Quick** (recommended — `target_tools` + TEA only; sensible
   defaults for everything else) or **Full** (also set git + code-review prefs). Quick → skip
   step 4.
3. **TEA (both depths):** detect the TEA skills (`bmad-testarch-*`) and ask `tea.enabled` —
   default "yes" if present, "no" if absent (don't offer yes when absent). If enabled, resolve
   `framework_ci`: detect a test-framework config (`playwright.config.*`, `cypress.config.*`,
   `pytest`/`jest`/`vitest`) and a CI workflow (`.github/workflows/*`, `.gitlab-ci.yml`, …). Both
   present → `framework_ci: done` silently; missing → **ask** to run one-time
   `/bmad-testarch-framework` + `/bmad-testarch-ci` now (delegate to `ab-high`) or `skip`. Heavy,
   infra-choosing setup — never auto-run without asking.
4. **Full only — extra prefs** (each prefilled with the default shown; the user changes only what
   they want): `git.mode` (auto | remote | local; default auto), `git.branch_prefix` (default
   `story/`), `code_review.max_iterations` (default 3), `code_review.alternate_models` (default
   true). `git.base_branch` is auto-detected, never asked.
5. Write `config.yaml` with the seeded delegation/profiles, the confirmed `target_tools`, the
   answers, and detected `git`/`base_branch` values (Quick fills the step-4 fields with the
   defaults above). **Then stop — do not start the pipeline this session.** This first-run write
   (plus any module registration done earlier this session) is the one-time setup; report what was
   configured and tell the user to open a **new session with fresh context** and run `/auto-bmad`
   to begin the first story. Running the pipeline on the same context that just did setup wastes
   the window — a fresh session re-detects host/mode and starts the story clean. (On later runs
   `config.yaml` already exists, so this flow is skipped and the pipeline proceeds normally.)

## state/{key}.yaml
```yaml
story_key: 1-2-user-auth
epic_num: 1
story_num: 2
branch: story/1-2-user-auth
status: in-progress         # in-progress | done
is_first_in_epic: false
is_last_in_epic: false
git_mode: remote
tea_selected: [atdd, automate]   # from triage; [] if trivial or TEA off
tea_rationale: "touches auth -> High risk"
completed_phases: [0, 1, 3, 5]   # phase numbers from pipeline.md
code_review_iterations: 1
convergence_unverified: false  # true if the review cap was hit while Critical/High were still being found+fixed and the user chose to ship anyway (Phase 7) -> Phase 9 opens the PR as a draft
commits: [a1b2c3d, e4f5g6h]
gate_decision: null          # PASS|CONCERNS|FAIL|WAIVED (last story only)
pr_url: null
ci_run_url: null             # link to the CI run the PR/push triggered, if the repo has workflows
open_questions: []
deferred_work: []
blockers: []                 # each: short human-action description
overrides: {}                # this run's normalized invocation overrides (see overrides.md); {} if none
```
Update it after every phase. Treat it as the source of truth for resume.

## Target selection & resume logic
No-arg `/auto-bmad` chooses the target story with this precedence:
1. **Incomplete auto-bmad pipeline first.** If any `state/*.yaml` has `status != done`, that
   story is the target — finish in-flight work before starting anything new. (At most one should
   exist; if several, take the most-recently-modified and mention the others in the report.)
2. **Else `story_plan.py`** picks the next actionable story. Its own precedence is
   `in-progress → review → ready-for-dev → backlog → retrospective`, so it resumes BMAD-level
   unfinished work before pulling a fresh `backlog` item — it does NOT jump straight to backlog.

An explicit `--story <arg>` overrides both and targets that story directly.

Once the target `story_key` is known:
- If `state/{key}.yaml` exists and `status != done` → **resume**: skip phases already in
  `completed_phases`, and if Phase 7 is in progress, continue the review loop from
  `code_review_iterations`. Re-detect git mode/branch (cheap) rather than trusting stale values
  if the branch is missing.
- Else → start fresh (initialize the state file in Phase 1).
- A `done` state file for the requested story → tell the user it's already complete and show the
  recorded `pr_url`; do not redo it (unless they explicitly force a re-run).

Git commits are the secondary safety net: even if the state file is lost, the per-phase commits
on the story branch show how far the pipeline got.

## retro-notes/epic-{e}.md
After each phase, append the agent's **Retro notes** under a per-story heading:
```
## Story {key}
- <decision / surprise / deviation / deferred item / risk worth remembering>
```
This file is created lazily on the first note for an epic and handed to `/bmad-retrospective`
at epic end as primary input — it carries the cross-step context (autonomy choices, why things
were done a certain way) that the story file alone doesn't capture.

## reports/{key}.md
The per-story report is a **log**, not a single overwritten document:
- Each run (first completion OR resume) **appends** a new `## Report — <ISO timestamp>` section,
  preserving everything already in the file. A resume must never clobber an earlier run's
  report, since prior sections may hold context (decisions, partial outcomes) we'd otherwise lose.
- The file is created on the first report for the story.
- The **only** time it's overwritten is a deliberate full re-run of an already-`done` story, and
  only after explicit user confirmation ("overwrite the existing report log for {key}?"). If the
  user declines, append instead.
