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
profiles_source_version: "0.10.3"  # abm version whose assets/agents/profiles.yaml seeded the
                                  # profiles + phase_profiles blocks below. Stamped at first-run
                                  # write and re-stamped by the Phase 0 config-drift heal (and by
                                  # `/auto-bmad reprovision`) when they re-seed. Read every run by
                                  # scripts/config_plan.py and compared to the installed
                                  # module_version: a newer module triggers an ADDITIVE re-seed of
                                  # any asset keys this config is MISSING — never overwriting the
                                  # user's retunes.
delegation:                # spawn mechanism — host/mode auto-detected each run
  host: auto               # auto (detect each run) | claude-code | codex | other
  mode: auto               # auto (derive from host) | custom-subagents | general-subagents | inline
  target_tools:            # tools to provision agents for; detected from installed skill dirs and
    - claude-code          # confirmed at first run (.claude/skills=>claude-code, .agents/skills=>
    - codex                # codex). Listing more than one = run in either tool with no reconfig.
tea:
  enabled: true            # set at first run after checking TEA skills exist
  framework_ci: prompt     # prompt | done | skip  (resolved at first run)
  gate_max_iterations: 2   # Phase 8 trace-gate remediation cap (automate + re-trace) before only waive/stop are offered
  story_trace_advisory:    # per-story, non-blocking trace pass — shifts coverage-gap visibility left on LONG epics
    enabled: true          # self-activating: dormant on short epics (see min_epic_stories), fires only on long high-risk stories
    min_epic_stories: 6    # only runs in epics with >= this many stories; short epics rely on the epic-end gate alone
git:
  mode: auto               # auto -> detect; or force "remote" / "local"
  branch_prefix: "story/"
  base_branch: main        # auto-detected; written after first detection
  offer_merge: true        # Phase 9: ask the user whether to merge a clean-completion PR
  ci_wait_minutes: 30      # max wait for in-progress CI before deciding (used only when offer_merge is on)
code_review:
  max_iterations: 3
  alternate_models: true   # odd iters use code_review_review, even iters code_review_review_secondary
# profiles + phase_profiles complete the file but are NOT reproduced here (with values) on
# purpose — their single source is assets/agents/profiles.yaml, which render-agents.py reads and
# first run copies in verbatim. Edit that file (or this per-project copy) then `/auto-bmad
# reprovision`; `/auto-bmad reset-defaults` discards edits and re-seeds from the asset (see
# "reset-defaults" below). Shape only — see the asset for the actual model/effort defaults:
profiles: {…}              # ab-xhigh | ab-high | ab-alt-xhigh | ab-alt-high, each:
                           #   {claude: {model, effort}, codex: {model, reasoning_effort}}
phase_profiles: {…}        # create_story, dev_story, code_review_review,
                           #   code_review_review_secondary, code_review_fix, tea_triage,
                           #   tea_per_story, tea_epic, retrospective, project_context
                           # (git/PR work is run by the orchestrator directly — no delegate profile)
```

**`assets/agents/profiles.yaml` is the single source of truth for both blocks** — see the
`config.yaml` comment above; first run copies it here verbatim, shape only, so asset and doc can't
drift. `delegation.host`/`mode` are re-detected each run and `target_tools` only controls which
agent files were provisioned (see `delegation-runtime.md`). Codex model names ship as real
defaults; retune `profiles` (in the asset) if your install differs.

## First-run flow (only when config.yaml is absent)
The single interactive episode in normal operation. Always confirm `target_tools`, then offer
**quick vs full** setup. Use AskUserQuestion.

0. **Seed delegation & profiles (non-interactive):** set `delegation.host`/`mode` to `auto`
   (re-detected each run — see `delegation-runtime.md`). Copy the `profiles` and `phase_profiles`
   defaults from `{skill-root}/assets/agents/profiles.yaml` — these are file-editable, never
   interviewed (point the user to `config.yaml` + `/auto-bmad reprovision` to retune). Detect the
   live host; if it needs `custom-subagents` but its agent files are missing, run `reprovision`
   (`scripts/render-agents.py`) before the pipeline starts.
1. **Confirm `target_tools` (always):** detect from the installed skill dirs on disk and confirm
   with the user — same procedure as setup, see `assets/module-setup.md` → "Provision Delegate
   Agents" (Step 1) for the exact detection rules. If `module-setup.md` already ran *this session*
   (fresh registration), reuse the `abm` value it just confirmed instead of re-asking. If the
   confirmed set differs from what agents were rendered for, run `reprovision` for it.
2. **Choose setup depth:** ask **Quick** (recommended — `target_tools` + TEA only; sensible
   defaults for everything else) or **Full** (also set git + code-review prefs). Quick → skip
   step 4.
3. **TEA (both depths):** detect the TEA skills (`bmad-testarch-*`) and ask `tea.enabled` —
   default "yes" if present, "no" if absent (don't offer yes when absent). If enabled, resolve
   `framework_ci`: detect a test-framework config (`playwright.config.*`, `cypress.config.*`,
   `pytest`/`jest`/`vitest`) and a CI workflow (`.github/workflows/*`, `.gitlab-ci.yml`, …) —
   probe with `find`/`test -f`, never a bare `ls playwright.config.*` / `ls .github/workflows/*`
   (unmatched it aborts under zsh/fish, same trap as the resume-scan above). Both
   present → `framework_ci: done` silently; missing → **ask** to run one-time
   `/bmad-testarch-framework` + `/bmad-testarch-ci` now (delegate to `ab-high`) or `skip`. Heavy,
   infra-choosing setup — never auto-run without asking.
4. **Full only — extra prefs** (each prefilled with the default shown; the user changes only what
   they want): `git.mode` (auto | remote | local; default auto), `git.branch_prefix` (default
   `story/`), `code_review.max_iterations` (default 3), `code_review.alternate_models` (default
   true). `git.base_branch` is auto-detected, never asked.
5. Write `config.yaml` with the seeded delegation/profiles, the confirmed `target_tools`, the
   answers, and detected `git`/`base_branch` values (Quick fills the step-4 fields with the
   defaults above). Above the copied `profiles:` block, write a short pointer comment naming both
   retune paths — *edit here, then `/auto-bmad reprovision`* and *discard edits with `/auto-bmad
   reset-defaults`* (see "reset-defaults" below). Also stamp `profiles_source_version` with the current `module_version` from
   `{skill-root}/assets/module.yaml` (advisory; never auto-overwrites the user's blocks — see the
   `config.yaml` comment above).
   **Then stop — do not start the pipeline this session.** This first-run write
   (plus any module registration done earlier this session) is the one-time setup; report what was
   configured, then tell the user how to begin the first story:
   - **`custom-subagents` tier (Claude Code / Codex):** the user must fully quit and relaunch the
     tool before `/auto-bmad` — see `delegation-runtime.md` → "Newly-rendered agents need a
     process restart". A `/clear` or "new chat" reuses the same process and will fail with
     *"Agent type 'ab-…' not found"*.
   - **Other tiers:** no project agents to load, so a fresh session/context is enough.

   Either way, running the pipeline on the context that just did setup wastes the window. (On
   later runs `config.yaml` already exists, so this flow is skipped.)

## reset-defaults — restore shipped profile defaults
`/auto-bmad reset-defaults [scope]` discards retunes in `config.yaml` and re-seeds the
**asset-sourced** blocks from `{skill-root}/assets/agents/profiles.yaml`. It is the inverse of the
Phase 0 additive heal (which only *appends* missing keys and never reverts an edited value), and the
one-shot fix for a `manual_review` item the heal won't auto-write (a sub-key missing from a profile
that already exists). **Config-only:** report what changed, then stop — never start a pipeline.

**Scope** (the optional arg; bare = both asset blocks):
- *(omitted)* — both `profiles` and `phase_profiles`.
- `profiles` — every profile block (a user-added profile absent from the asset is left intact).
- `<profile-name>` (e.g. `ab-high`) — that one profile.
- `phase_profiles` — the phase→profile mapping only.

**Boundary (state it to the user):** reset-defaults touches **only** `profiles`, `phase_profiles`,
and the `profiles_source_version` stamp — **never** `delegation`/`tea`/`git`/`code_review`, which
are setup answers, not shipped defaults. Redoing those is `setup`/`configure`.

**Flow:**
1. Require `config.yaml` to exist. Absent → "Nothing to reset — run `/auto-bmad setup` first." and stop.
2. Plan (read-only):
   ```
   python3 {skill-root}/scripts/config_plan.py --reset <scope> --config <output_folder>/auto-bmad/config.yaml
   ```
   (the shipped `assets/agents/profiles.yaml` + `assets/module.yaml` resolve relative to the script).
   Empty `would_change` → "Already at shipped defaults for `<scope>`." and stop.
3. **Confirm** with `AskUserQuestion`, showing the `current → default` diff (truncate long persona
   strings). Options: **Reset** (discards the listed retunes) / **Cancel**. This is the sole
   interactive moment; Cancel → stop, write nothing.
4. On confirm, write by re-running with `--write` (backs the prior config up to `config.yaml.bak`,
   then overwrites). Report the backup path and any `version_restamp`: a **full** reset restamps
   `profiles_source_version` to the module version; a **scoped** reset leaves it — a partial reset
   can't claim the whole asset-sourced surface matches that version.
5. **Re-render delegates iff the plan's `render_needed` is true** — a profile's model/effort/persona
   changed, so the `ab-*` agent files are now stale. Hand this to the **same reprovision path** the
   rest of the skill uses: resolve host/tier per `delegation-runtime.md` and read
   `delegation.target_tools` from the config you just wrote, then run the `reprovision` action
   (`scripts/render-agents.py` for those tools) exactly as `module-setup.md` describes — don't
   re-derive it here. It is a no-op off `custom-subagents` (there are no `ab-*` files under
   `general-subagents`/`inline`), and a `phase_profiles`-only reset never sets `render_needed`. When
   agents were actually rendered, surface the **process-restart caveat** (`delegation-runtime.md` →
   "Newly-rendered agents need a process restart") — the new agents aren't invokable until a full
   quit & relaunch.
6. Report scope, what was reset, the backup path, restamp, and whether a relaunch is needed. Stop.

## state/{key}.yaml
The state file is a **machine-readable contract**, not a prose log. Every field listed below is
**always emitted** with an explicit value (use `null` / `false` / `[]` / `{}` for not-yet-set or
not-applicable — never omit a field), so parsers and human readers can rely on a stable shape.
Prose (multi-line YAML comment narratives about what a phase did, review-iteration findings,
etc.) belongs in `reports/{key}.md` — keep it out of state.

```yaml
story_key: 1-2-user-auth
epic_num: 1
story_num: 2
branch: story/1-2-user-auth
status: in-progress         # in-progress | done
updated_at: "2026-05-28T14:04:41Z"  # ISO-8601 UTC; set by the orchestrator after every phase write
started_at: "2026-05-28T13:55:02Z"  # ISO-8601 UTC; stamped ONCE at the Phase 1 write, never rewritten (survives resume)
completed_at: null          # ISO-8601 UTC; set when status flips to done (Phase 9 finalize); null while in-progress
active_seconds: 0           # accumulated wall-clock spent EXECUTING phases (delegate runtime + the orchestrator's own
                            #   commit/state work), summed across every session so it keeps growing on resume. Each phase:
                            #   read `date +%s` before delegating and again after its commit, add the delta here.
                            #   elapsed = completed_at-started_at; human/idle wait = elapsed - active_seconds.
is_first_in_epic: false
is_last_in_epic: false
needs_project_context_bootstrap: false  # set at Phase 0; flipped to false by Phase 2's bootstrap sub-step
git_mode: remote
base_branch: main
tea_risk: high                   # low|med|high from Phase 0 triage; gates per-story TEA + the long-epic trace advisory
tea_selected: [atdd, automate]   # from triage; [] if trivial or TEA off; may also include trace-advisory (long-epic high-risk)
tea_rationale: "touches auth -> High risk"
epic_story_count: 12             # stories under epic {e} (from sprint-status); gates the long-epic trace advisory
completed_phases: [0, 1, 3, 5]   # phase numbers from pipeline.md; Phase 2 lands here if EITHER sub-step ran
code_review_iterations: 1
convergence_unverified: false  # true if the review cap was hit while Critical/High were still being found+fixed and the user chose to ship anyway (Phase 7) -> Phase 9 opens the PR as a draft
story_trace: null              # Phase 7 tail trace advisory result, or null if not selected / not yet run:
                               #   {verdict: PASS|CONCERNS|FAIL, uncovered: [..], ran: true}. Advisory only — never blocks/drafts; non-null = done (resume marker)
commits: [a1b2c3d, e4f5g6h]
gate_decision: null          # PASS|CONCERNS|FAIL|WAIVED (last story only)
gate_iterations: 0           # Phase 8 trace-gate remediation passes run (automate+re-trace); capped by tea.gate_max_iterations; resume continues mid-loop
pr_url: null
ci_run_url: null             # link to the CI run the PR/push triggered, if the repo has workflows
ci_status: unknown           # passed|failed|timeout|none|unknown — set only when Phase 9 waited (offer_merge on); else 'unknown'
pr_merged: false             # true only if the user chose a merge style in Phase 9's merge prompt and `gh pr merge` succeeded
merge_method: null           # squash|merge|rebase|null — null if not merged or prompt was skipped
merge_commit: null           # full SHA of the merge commit on the base branch, or null
branch_deleted: false        # true if --delete-branch was used in the successful merge
open_questions: []
deferred_work: []
blockers: []                 # each: short human-action description
overrides: {}                # this run's normalized invocation overrides (see overrides.md); {} if none
constraints: []              # caller-supplied constraints carried in via invocation (e.g. exact-string requirements); [] if none
```

Update it after every phase. Treat it as the source of truth for resume. The merge-related fields
(`pr_merged`, `merge_method`, `merge_commit`, `branch_deleted`, `ci_status`) carry their
`false`/`null`/`unknown` defaults from the first write; Phase 9 mutates them only when it actually
waits for CI / runs `gh pr merge`.

The **timing** fields are orchestrator-owned (use the host's `date`): `started_at` is stamped once
at the Phase 1 write and never touched again; `completed_at` is set only when the run flips `status`
to `done`; `active_seconds` accumulates each phase's execution window, so it grows across resumes.
Derive for the report: **elapsed** = `completed_at − started_at` (total, includes overnight resume
gaps), **AI-run time** ≈ `active_seconds`, **human/idle wait** ≈ `elapsed − active_seconds`.
The split is best-effort, not exact — it's host wall-clock, not token-compute time. Time spent
waiting on the user does **not** count as active: when a phase opens an `AskUserQuestion` (e.g. the
Phase 7 decision asks or cap prompt), the orchestrator brackets the prompt and excludes that
interval from `active_seconds`, so it lands on wait. Between-phase prompts and resume gaps land on
wait too; a story halted overnight shows a large wait dominated by the gap, not by work.

## Target selection & resume logic
No-arg `/auto-bmad` chooses the target story with this precedence:
1. **Incomplete auto-bmad pipeline first.** If any `state/*.yaml` has `status != done`, that
   story is the target — finish in-flight work before starting anything new. (At most one should
   exist; if several, take the most-recently-updated and mention the others in the report.)
   State files are named `{key}.yaml` — e.g. `1-2-user-auth.yaml`. There is **no `story-`
   prefix**: the `story-{e}-{s}` form appears only in commit/PR scopes (`docs(story-1-2): …`),
   never in a filename. **Don't hand-roll shell for this** — call the deterministic reader:
   ```
   python3 {skill-root}/scripts/state_plan.py --state-dir {output_folder}/auto-bmad/state
   ```
   Parse its JSON: `resume: true` ⇒ resume `target` (the most-recently-updated in-flight story),
   and `extra_in_flight` lists any others to mention; `resume: false` (empty dir, absent dir, or
   all `done`) ⇒ fall through to `story_plan.py`. The script enumerates `{state-dir}/*.yaml` and
   reads each `status:` itself — dependency-free, exit 0 even on a first-run absent/empty dir, so
   there's no raw-glob `nomatch` footgun and no chance of probing a phantom `story-*` name. (See
   `CLAUDE.md` → "Shell globs" for why the hand-rolled loop was the problem.)
2. **Else `story_plan.py`** picks the next actionable story. Its own precedence is
   `in-progress → review → ready-for-dev → backlog → retrospective`, so it resumes BMAD-level
   unfinished work before pulling a fresh `backlog` item — it does NOT jump straight to backlog.

An explicit `--story <arg>` overrides both and targets that story directly.

**Why a finished story doesn't re-stick (clean completions).** A `dev-story` run leaves the
BMAD-level status at `review`, and BMAD only flips `review → done` on human merge. Without
intervention that traps the pipeline: `story_plan.py` (precedence above) keeps returning the
just-finished `review` story, but its auto-bmad `state/{key}.yaml` is already `done`, so the run
reports "already complete" and stops — it never advances. To avoid this, **Phase 9 flips the
BMAD-level status (story file `Status:` + the `sprint-status.yaml` entry) to `done` on a clean
completion** (non-draft PR — see `pipeline.md` Phase 9), decoupling `done` from the human's
merge so `story_plan.py` moves on to the next story. A **caveated** completion (draft PR / blocker
/ waived gate / CI red or timed-out) deliberately stays at `review`: it still needs a human, so it keeps re-surfacing —
and a re-run, finding the auto-bmad state already `done`, reports it complete (per the rule below)
rather than redoing the work.

Once the target `story_key` is known (e.g. from an explicit `--story` arg), check its state with
the same reader — an exact `{key}` lookup, never a glob:
```
python3 {skill-root}/scripts/state_plan.py --state-dir {output_folder}/auto-bmad/state --story-key {key}
```
`resume: true` (file exists, `status != done`) ⇒ resume; `exists: false` ⇒ start fresh; a `done`
status ⇒ already complete (see below). The script tests the exact `{key}.yaml` path, so there's
no glob to misname (`story-*`) or to abort under zsh/fish.
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
The cross-story scratchpad the epic retrospective reads — **signal only, not a log.** After each
phase, append the agent's **Retro notes** under one per-story heading (create `## Story {key}` on
the first real note for that story; reuse it for later phases):
```
## Story {key}
- <one terse line: a deviation / non-obvious decision / surprise / risk / deferred item>
```
Keep it small so it stays usable across a multi-story epic:
- **Skip empty notes.** Most phases run clean and have nothing retrospective-worthy — when a
  delegate returns `Retro notes: none` (or only routine "did the work" text), append **nothing**
  (don't even write the heading). Only genuine signal lands here.
- **One terse line per item** — never a paragraph, and never a recap of what the story file
  already records.

This file is created lazily on the first real note for an epic and handed to `/bmad-retrospective`
at epic end as primary input — it carries the cross-step context (autonomy choices, why things
were done a certain way) that the story file alone doesn't capture.

## reports/{key}.md
The per-story report is a **log**, not a single overwritten document. It carries only the
**story-level** outputs that aren't recorded elsewhere — overrides, TEA outcomes, open
questions, deferred work, blockers, next-story preview. PR URL, CI link/status, draft reason,
merge method, and the BMAD-status-flip outcome are **chat-only** at end of run — already
retrievable from git/GitHub/sprint-status, so the file is written **once** pre-push and never
re-touched after the PR/CI/merge resolve.

- On a clean path the file is written + committed in **Phase 9 before push**
  (`docs(story-{e}-{s}): pipeline report`) so it ships in the PR diff. See
  `pipeline.md` Phase 9 + `git-and-pr.md` → "Ownership".
- On a hard-stop before Phase 9 (or any path that didn't reach the pre-push write), `SKILL.md`
  Step 3 writes the file as a fallback — same content, no commit (the working tree is already
  in needs-human state; the human will commit it alongside their fix).
- Each run (first completion OR resume) **appends** a new `## Report — <ISO timestamp>` section,
  preserving everything already in the file. A resume must never clobber an earlier run's
  report, since prior sections may hold context (decisions, partial outcomes) we'd otherwise lose.
- The file is created on the first report for the story.
- The **only** time it's overwritten is a deliberate full re-run of an already-`done` story, and
  only after explicit user confirmation ("overwrite the existing report log for {key}?"). If the
  user declines, append instead.

### Section template (use literally, in this order)
Every `## Report — <ISO timestamp>` section uses the same headings in the same order so a PR
reviewer always finds each field in a predictable place. Omit a heading only when its content is
empty AND the heading's own line says "(none)" — never drop the heading silently.

```markdown
## Report — <ISO timestamp UTC>

**Story:** `{key}` (epic {e}, story {s}) — {first-in-epic? / last-in-epic? / mid-epic}.
**Branch:** `<branch>` (HEAD `<short-sha>`).
**Pipeline status:** <one-line summary, e.g. ✅ clean completion / halted at Phase 5 (needs-human) / draft (CI red)>.

**Timing:** started <ISO>; completed <ISO, or "in progress"> — elapsed <Hh Mm> (≈<Hh Mm> AI-run, ≈<Hh Mm> human/idle wait)<; resumed N× if >1 session>.

**Phases run:** <comma-joined Phase N list, with profile in parens for delegated phases>.
**Skipped:** <comma-joined Phase N list with reason in parens>.

**Overrides:** <one line; "none" if no invocation overrides applied>.

**TEA:** <which skills ran and their one-line outcome; "disabled" if tea.enabled=false; epic-gate decision if last story; for the per-story trace advisory, its verdict + any uncovered ACs (advisory, non-blocking)>.

**Code review:** <iterations run; per-iteration verdict + severity counts on one line each; "skipped" if no review>.

**Open questions:** <numbered list, one per line; "(none)" if empty>.

**Deferred work:** <numbered list, one per line; cross-link to `<impl>/deferred-work.md` if items landed there; "(none)" if empty>.

**Planning drift:** <epic-end only — planning assumptions the retrospective proved wrong + the recommended re-sync (document-project → generate-project-context → bmad-prd update; correct-course if structural); non-blocking, never auto-run; "(none)" if clean or not epic-end>.

**⚠️ Needs human:** <numbered list of blockers / manual actions; "(none)" if clean>.

**Next:** <one line — the story `story_plan.py` would pick next; preview only>.
```
