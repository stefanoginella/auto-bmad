# Git & PR conventions

- All git work is performed by the **orchestrator directly** — never delegated (see "Ownership" below).
- Nothing ever lands on the base branch.
- Every phase is its own commit — so the pipeline is resumable and reviewable.
- **`bmad-build-auto` authors every code commit** (the Phase 5 build run and every Phase 7 review pass commit their own diff on the current branch and never push). The orchestrator commits everything else — spec/plan artifacts, TEA artifacts, sprint-status flips, state, reports — and **never** makes a `feat` commit of story code.

## Ownership

This file is the single source for everything the orchestrator owns directly (does not delegate) — other docs link here by name instead of restating the list.

Orchestrator-owned, never delegated:

- git preflight, branching, every per-phase commit, push, PR open.
- the **clean-tree gate** before every build-auto invocation and the `head_before` capture around it (see "Commits" → "Clean-tree gate" / "`commits[]`") — git-only.
- the **Phase 0 probes** — `preflight.py` (git state/mode, `uv`, Python 3.11, nested-subagent capability, `_bmad/config.toml`, `AGENTS.md`), the config-drift heal, the review-layers TOML sync (`build_auto_custom.py`) — see `pipeline.md` Phase 0.
- the **sprint-status write-back around build-auto** — `story_plan.py --mark-status` at Phase 3 end (`ready-for-dev`), Phase 5 start (`in-progress`, incl. the epic lift) and end (`review`), the Phase 8 pre-retro `done` flip, the Phase 9 `done` flip. The orchestrator never edits the spec.
- the **retro verdict gate** ask (Phase 0 / E0) — see `pipeline.md` Phase 0.
- the Phase 9 **pre-push report write + commit** (`docs(story-{e}-{s}): pipeline report`) — the story-level report file is written and committed *before* push, so it ships in the PR diff.
- the **CI wait** + draft conversion — when `git.offer_merge` is on.
- the Phase 9 **BMAD-level status flip** on a clean completion (`sprint-status.yaml` → `done`, unless the Phase 8 pre-retro flip already did it).
- the Phase 9 **merge prompt + `gh pr merge` execution** — opt-in via `git.offer_merge` (default on), only on a clean completion.
- the Phase 8 **deferred-work archive** (+ the Phase 7 tail **harvest**) — `deferred_ledger.py`; the keep-vs-move judgment and the reconcile stay delegated.
- the Phase 7 **HITL-halt handling**:
  - detect external-review changes — a git-only check, never a code read; auto-bmad's own writes are excluded (`pipeline.md` Phase 7 step 3, own-writes exclusion): changed := `git status --porcelain -- . ':(exclude)<output_folder>/auto-bmad' ':(exclude)<project_root>/_bmad/custom/bmad-build-auto.toml'` non-empty OR HEAD moved — `git rev-parse HEAD` ≠ the HEAD when the halt opened this session; on a halt re-opened after `stopped`, HEAD moved := `git log --format=%h --since=<state updated_at, read BEFORE the re-open reset write> HEAD -- . ':(exclude)<output_folder>/auto-bmad' ':(exclude)<project_root>/_bmad/custom/bmad-build-auto.toml'` non-empty.
  - commit them (`fix(story-{e}-{s}): external review changes`).
  - re-open the halt ONCE after the re-review.
  - the **re-review of those changes is delegated**, NOT orchestrator-owned — one more `followup-review` build-auto pass at `followup_review` (see `pipeline.md` Phase 7 step 3).
- **epic mode** (`/auto-bmad epic`) owns the same git set at **epic scope**:
  - one `epic/{e}-{slug}` branch, the E0 base-readiness guard (git-only), the per-story commits on that branch, the batch BMAD-status flip (E8b pre-retro / E_final), and the epic-anchor finalize.
  - epic mode has **no review halt** — every story's follow-up pass auto-continues (`hitl_halt: auto-continued (epic — no halt)`), and an unverified review ships a draft (no `AskUserQuestion`).
  - details: "Epic mode" below + `epic-pipeline.md`.

These stay orchestrator-owned because it already holds the full pipeline context. The **only** exception is the `inline` delegation tier (host with no subagent mechanism — see `delegation-runtime.md`), where the orchestrator runs *every* step itself.

## Mode detection (Phase 0)

- Evaluated by `scripts/preflight.py`.
- The orchestrator reads its JSON (`git.is_repo`, `git.current_branch`, `git.base_branch`, `git.mode`, `git.tree_clean`/`git.dirty_files_count`) — never re-derives these in shell.
- Config `git.mode`: `auto` (default) ⇒ the detection below; `remote`/`local` force the mode. The `git_mode local` override forces `local` for the run.
- The rules below are the normative definition the script implements:

- **Is it a git repo?** `git rev-parse --is-inside-work-tree`.
  - Not a repo → hard-stop (suggest `git init`).
- **Base branch** — the runtime config's `git.base_branch` is authoritative once set (seeded at first run from preflight's value below; `state-and-resume.md`). Preflight's `git.base_branch` only **seeds** that key at first run and **warns** when the two disagree while `origin/HEAD` is present — every `<base_branch>`/`<base>` placeholder here, in `pipeline.md`, `epic-pipeline.md` and `delegation.md` means the **config** value. Preflight's detection:
  - the remote HEAD if present (`git symbolic-ref refs/remotes/origin/HEAD`);
  - else the current branch at start (commonly `main`/`master`) — a first-run seed only, never the run-time base (on a resume that would be the story/epic branch itself).
- **Git mode:**
  - **`remote`** if `gh` is installed (`gh --version`), authenticated (`gh auth status`), AND a GitHub remote exists (`git remote -v` shows a github.com origin).
  - **`local`** otherwise.
- **Working tree must be clean at start** (`git status --porcelain` empty):
  - dirty AND on the base branch or an unrelated branch → hard-stop ("commit or stash first").
  - dirty on the correct story/epic branch during a resume (`--expected-branch` = the state's `branch`) → fine; the in-flight phase (or the clean-tree gate) will commit it.
  - tree state unknown (status probe failed) → hard-stop, never read as clean.
- **Detached/unknown HEAD** → hard-stop even on a clean tree (branching and the PR base need a branch).

## Branching (Phase 1)
- Branch name: `{git.branch_prefix}{e}-{s}-{slug}` (default prefix `story/`), e.g. `story/1-2-user-auth`.
  - `{s}` includes the split suffix when the key has one — `story/2-6a-digest-delivery`.
  - Slug = the story-key title part (already kebab-case).
- Create it explicitly off base — `git switch -c <branch> <base_branch>`.
  - NEVER a bare `git switch -c <branch>` — because preflight allows a clean tree on an unrelated branch, and a bare `-c` would branch off it, leaking foreign commits into the PR.
  - On resume → `git switch <branch>` if it already exists.
- Never `commit`/`push` to the base branch.

## Commits (between phases)
- Use Conventional Commits, **in full** — never subject-only (see "Message body"):
  - a `type(scope): subject` line;
  - **plus a body** (required on every commit).
- Scope is the story or epic: `story-{e}-{s}` (`{s}` incl. any split suffix, e.g. `story-2-6a`) or `epic-{e}`.
- **Who commits what:**
  - **build-auto** commits its own diff inside the Phase 5 build run and every Phase 7 review pass (implement → review → finalize; never pushes). The plan run (Phase 3) commits nothing — the orchestrator's `plan spec` commit carries the untracked spec.
  - the **orchestrator** commits bookkeeping only. It never commits story code as its own work — the sole cases where non-bookkeeping files ride in an orchestrator commit are (a) stragglers build-auto left uncommitted (swept into the `mark review` commit with a warning), (b) a human's edits (`external review changes`, `spec edits (human)`), and (c) a `blocked` build-auto run's leftovers (`… blocked (<blocking condition>)`).
- **Per-phase subjects** (normative strings; `pipeline.md` places them):
  - Phase 1: `chore(story-{e}-{s}): start auto-bmad pipeline` (may also carry a Phase 0 auto-applied `_bmad/custom/bmad-build-auto.toml` / healed `config.yaml`).
  - Phase 2: `test(epic-{e}): epic-level test design`.
  - Phase 3: `docs(story-{e}-{s}): plan spec` (the spec, any compiled `epic-{e}-context.md`, sprint-status, state); plan HALTed `blocked` ⇒ `chore(story-{e}-{s}): plan blocked (<blocking condition | reason>)`; a human's spec edits found dirty at the spec-approval resume ⇒ `docs(story-{e}-{s}): spec edits (human)`.
  - Phase 4: `test(story-{e}-{s}): ATDD acceptance scaffolds (red)` — MANDATORY before Phase 5 (build-auto needs a clean tree).
  - Phase 5: build-auto's own commits, then `chore(story-{e}-{s}): mark review` (sprint flip + state [+ stragglers]); `blocked` ⇒ `chore(story-{e}-{s}): build blocked (<blocking condition | reason>)`.
  - Phase 6: `test(story-{e}-{s}): expand automated coverage`.
  - Phase 7: build-auto's own commits per pass; a pass HALTed `blocked` ⇒ `chore(story-{e}-{s}): review blocked (<blocking condition | reason>)`; halt: `fix(story-{e}-{s}): external review changes`; tail: `test(story-{e}-{s}): trace coverage advisory` (also carries the harvest + state) — else `docs(story-{e}-{s}): harvest deferred work` when only the ledger changed — else the state write folds into the next commit.
  - Phase 8: `test(epic-{e}): close trace coverage gaps (gate iter {i})` (per remediation pass); `docs(epic-{e}): gate, deferred-work reconcile + archive, retrospective` (the one end-of-phase commit; carries the pre-retro flip).
  - Phase 9: `docs(story-{e}-{s}): pipeline report`; `chore(story-{e}-{s}): finalize (mark done + BMAD status)`.
  - Clean-tree gate (below): `chore(story-{e}-{s}): pipeline state`; `chore(story-{e}-{s}): mark in-progress`.
- **The state update folds into the phase's commit — never standalone.**
  - A phase mutates the project artifacts *and* the auto-bmad state file (`<output_folder>/auto-bmad/state/{key}.yaml`); stage **both together** and make a **single** commit.
  - A phase with a documented multi-commit flow folds the state write into each such commit (Phase 8's separate remediation commits, Phase 3/5/7's `blocked` commits — `plan blocked` / `build blocked` / `review blocked`).
    - The rule is *no state-only commits*, not one-commit-per-phase-number.
  - **Never** emit a standalone bookkeeping commit whose only change is the state file — no `chore(story-{e}-{s}): record Phase N in pipeline state`, no `chore(...): update state/timestamps`.
  - **The ONE sanctioned exception is the clean-tree gate below.**

### Clean-tree gate (before EVERY build-auto invocation)
- Applies to the Phase 3 plan run, the Phase 5 build run, and every Phase 7 follow-up / re-review pass.
- Why: build-auto's fresh-intent route HALTs on a dirty tree (its step-01 version-control check), and every build-auto run diffs tracked+untracked files since its `baseline_revision` and sweeps stragglers into its own commit at Finalize — auto-bmad bookkeeping must never sit uncommitted when build-auto starts: it would be swept into build-auto's own commit (or trip `finalization left repository dirty`). (Already-committed bookkeeping — the `mark review` flip, state, TEA artifacts — is visible to a done-spec follow-up pass by design, since it keeps the ORIGINAL `baseline_revision`; the review triage treats it as noise.)
- (a) **Fold forward first:** write the build-auto phase's `timing-start` (epic mode: on the per-story file AND the epic anchor; and, for Phase 5, the `in-progress` sprint flip) *before* the preceding phase's commit when that commit is made in the same session — Phase 1 init → Phase 3 (when Phase 2 does not run); Phase 2 → Phase 3; Phase 3 → Phase 5 (when neither Phase 4 nor the spec-approval halt runs); Phase 4 → Phase 5; Phase 5 `mark review` → Phase 7 (when Phase 6 does not run); Phase 6 → Phase 7.
- (b) **Otherwise**, if `git status --porcelain` is non-empty immediately before the invocation, stage everything and commit — the ONE sanctioned bookkeeping commit:
  - `chore(story-{e}-{s}): pipeline state` — state file only (Phase 1's `init` before Phase 3 is the usual case);
  - `chore(story-{e}-{s}): mark in-progress` — Phase 5: sprint flip + state.
- A `blocked` plan run's untracked result file is committed by the `plan blocked` commit, never left for the next gate to sweep under a `pipeline state` subject.

### `commits[]`
- **Orchestrator commits — sha-lag rule.** Recording a commit's own sha can't happen inside that same commit — so do **not** chase it with a second commit. Append the just-made commit's short sha to `commits[]` on the **next** folded-in state write (Phase 9's finalize write closes out the last one).
- **build-auto's own commits — ONE rule for every invocation** (plan run, build run, each follow-up / re-review pass): immediately before the invocation (after the clean-tree gate) capture `head_before = git rev-parse HEAD` (session memory); right after it returns record `commits[] += git log --format=%h <head_before>..HEAD` (empty for the plan run).
  - Never use the spec's `baseline_revision` for this — a done-spec re-review keeps the ORIGINAL `baseline_revision`, so `baseline_revision..HEAD` would re-append Phase 5's and the orchestrator's commits.
- `commits[]` feeds the report only — resume keys off `completed_phases`, which the folded write keeps current — so a one-phase lag in `commits[]` is harmless.

### Message body
- **Subject** — keep it imperative and ≤ ~72 chars; the strings above are fixed.
- **Body — required on every commit.**
  - One blank line after the subject, then 1–4 wrapped lines saying *what this phase changed and why*.
  - Draw it from the context the orchestrator **already holds** for the phase (the delegate's report, build-auto's summary/counts, deviations, deferred work) — never invent, never describe code it has not read.
  - **The body must add information the subject doesn't carry** — never just restate it.
  - By subject:
    - `chore` start: story title, epic, branch, and the delegation tier/profiles in use.
    - `docs` plan spec: the spec path, its `ready-for-dev` status, and build-auto's planning summary (task count / notable decisions as reported).
    - `test`: the scaffolds/coverage added (ATDD red, post-dev automation, epic test design, trace advisory, gate remediation).
    - `chore` mark review: build-auto's summary line, patched/deferred counts, `followup_review_recommended`, warnings (incl. any swept stragglers).
    - `chore` pipeline state / mark in-progress: which phase's bookkeeping it carries and why it could not fold forward.
    - `chore` … blocked: the blocking condition verbatim + the result-file path.
    - `fix` external review changes: the file count from `git status`, that a human made them during the review halt, and that a re-review pass follows.
    - `docs`: which artifact and its scope (spec edits (human), deferred-work harvest, epic gate/reconcile/archive/retro, pipeline report).
    - `chore` finalize: clean-vs-caveated outcome, the BMAD-status flip (and which phase did it), and PR URL / CI status / gate decision.
- **Emit the parts as separate `-m` args** so the blank-line separator is guaranteed: `git commit -m "<subject>" -m "<body>"`.
  - Each `-m` becomes its own blank-line-separated paragraph — i.e. exactly the subject / body shape.
  - Stage the phase artifacts **and** the state file first — the single-commit rule above.

## PR (Phase 9, mode `remote` only)
- Before anything: no dirty tree OTHER THAN auto-bmad's own writes — the Phase 7 own-writes exclusion set: `<output_folder>/auto-bmad/**` (state, reports, config.yaml) and `<project_root>/_bmad/custom/bmad-build-auto.toml` (a pending Phase 7/8 folded state write, or a Phase 0 auto-applied heal/layers regen on a resume that entered at Phase 8/9) — those fold into the report commit; any other dirty file ⇒ hard-stop `unexpected uncommitted changes before finalize: <files>`.
- Push: `git push -u origin <branch>`.
- Open PR: `gh pr create --base <base_branch> --head <branch> --title "<title>" --body "<body>"`.
- Add `--draft` if **any** clause of the **draft predicate** holds (clauses 1–4 below):
  - Evaluated deterministically by `scripts/state_plan.py --state-dir <state-dir> --story-key {key} --finalize` from the story's state file.
  - Run it **twice** in Phase 9:
    - pre-create WITHOUT `--ci-status` — clauses 1–3 decide the initial `--draft`;
    - again after the CI wait WITH the live `--ci-status` — the full verdict that also drives the status flip.
  - Phase 8's pre-retro flip runs the same pre-CI evaluation once more (last story of an epic — `pipeline.md` Phase 8 step 4).
  - The four clauses below remain the normative definition the script implements.

  **Draft predicate (clauses 1–4):**
  1. a blocker was recorded (`blockers` non-empty);
  2. `review_unverified` is `true` — any of (Phase 7):
     - the `skip code-review` override — or a phase-7 skip normalized to it — no follow-up pass ran, see `overrides.md`;
     - **or** the spec's `followup_review_recommended` is still `true` after Phase 7's last pass (incl. `code_review.followup: never`, where build-auto's own recommendation was never acted on);
     - (a post-halt re-review that still recommends a follow-up leaves it `true` — the human's "Continue — ship as ready" sets `no_pr_draft` instead of clearing it — see `pipeline.md` Phase 7 step 3);
  3. `gate_decision` is `WAIVED` (Phase 8: the epic trace gate did not pass and the user — or the trace skill — chose to ship despite the coverage gaps);
  4. **CI is red or timed out** when the CI wait below resolves — a required check failed, or the wait cap was hit with checks still running (see "CI wait" below).
     - This condition can only be evaluated *after* the push.
     - If it fires → the PR is **converted to draft after the fact** with `gh pr ready --undo <pr-number>` (the initial `gh pr create` is issued without `--draft` for clauses 1–3 only).

- **The negation of this same draft predicate is the "clean completion" test** that decides whether Phase 9 also flips the BMAD-level story status (`sprint-status.yaml`) to `done` (see `pipeline.md` Phase 9):
  - predicate false AND not already flipped (`bmad_status_flipped_at` null) ⇒ `python3 {skill-root}/scripts/story_plan.py --mark-status {key} --to done --sprint-status <impl>/sprint-status.yaml` (also lifts `epic-{e}` to `done` when every story is `done`), `bmad_status_flipped_at: 9`;
  - any clause true ⇒ leave as is (`review` — or `done` when the Phase 8 pre-retro flip already ran; a later CI failure never regresses the entry, the caveat lives in the PR draft state + report).
  - `state_plan.py --finalize` emits both verdicts coupled in one JSON — `draft` and `clean_completion`/`flip_bmad_status`.
  - It is the *predicate* that decides, NOT the PR's actual draft flag: the `no_pr_draft` override (`--no-pr-draft`) forces only `draft` false and never touches `clean_completion`.
  - Keep the two coupled if you edit it.
- Title: a conventional summary of the story, e.g. `feat(story-1-2): user authentication` (`{s}` incl. any split suffix).
- Body must include:
  - one-paragraph summary of what the story delivered;
  - a link to the spec (`<spec_path>` as a repo-relative path);
  - a build result line — build-auto `status`, follow-up review passes, deferred count;
  - TEA outcomes / epic gate decision (if applicable);
  - `## Open action items (epic {e})` — from `sprint_plan.py status`, only when the story is last in its epic;
  - a `## Needs attention` checklist of open questions, deferred work, human-action items, and the `⚠️ Retrospective verdict: rejected — <doc>` line when it applies (empty section omitted);
  - a footer line: `🤖 Generated by auto-bmad`.
- Capture the returned PR URL into state (`pr_url`) for the **chat** report (chat-only artifact).
- **CI link & wait:**
  - If the repo has CI workflows, the push/PR will have triggered a run.
    - Test existence with `find .github/workflows -name '*.yml' -o -name '*.yaml'` or `test -d` (preflight already reports `ci.workflows_present`).
    - Never a bare `ls .github/workflows/*` glob — unmatched it aborts under zsh/fish.
  - The URL capture and the wait are one `ci_wait.py` call (see "How to wait" below).
    - Store the returned `ci_run_url` in state.
    - When it is `null` → fall back to the branch's Actions tab (`<repo_url>/actions?query=branch:<branch>`).
  - Then evaluate `ci_status` and, when warranted, **wait for in-progress checks to finish**.

  - **When to wait:** only if the merge prompt is effectively enabled this run — `git.offer_merge: true` AND no `skip merge-prompt` override.
    - prompt off → do not wait; just link the run and leave `ci_status: unknown`.
    - clauses 1–3 already made the run caveated (the PR is already a draft, so the merge prompt can't fire) → skip the wait; link the run, leave `ci_status: unknown`.
  - **How to wait:** one deterministic call — `python3 {skill-root}/scripts/ci_wait.py --pr <pr-number> --cap-minutes <git.ci_wait_minutes> --resolve-run-url --branch <branch> --head-sha <sha>` — then read `ci_status` and `ci_run_url` from its single JSON object.
    - The script owns the poll cadence, cap, registration grace (zero checks just after the push is lag — held as pending, not `none`), and output discipline.
    - Exit 2 means it couldn't evaluate CI (gh missing/errored) — leave `ci_status: unknown`, never `failed`.
  - **Outcomes** — record in state as `ci_status`; this list is normative, and `ci_wait.py` pins these exact values:
    - `passed` — every required check is `success` (or `neutral`/`skipped`).
    - `failed` — any required check is `failure`/`cancelled`/`timed_out`/`action_required`.
    - `timeout` — cap reached with checks still running.
    - `none` — no CI workflows or no checks reported.
  - Effect on the draft predicate:
    - `failed` or `timeout` ⇒ draft-predicate clause 4 fires (draft conversion per clause 4; story stays at `review`).
    - `passed` or `none` ⇒ clause 4 does not fire — clauses 1–3 still decide.
  - **Inherent lag:** the verdict above is evaluated on the pre-finalize HEAD — the Phase 9 finalize commit pushed *after* it supersedes that SHA and may re-trigger CI.
    - That commit is bookkeeping-only (state/report/status files, no code), so the verdict remains meaningful for the story's code.
    - On a protected branch the pending-checks merge fallback below covers the gap.

## Merging the PR (Phase 9, only when clean) — orchestrator
- auto-bmad never merges automatically.
- The orchestrator **asks** the user whether to merge before reporting, then runs the chosen `gh` command on their behalf — only when ALL of:
  - the run is a **clean completion** (full draft predicate is false — clauses 1–4 above);
  - AND `git.offer_merge` is `true`;
  - AND the run has no `skip merge-prompt` override.

- **Prompt** (`AskUserQuestion`, 4 options, in this order — first is the default):
  - **Merge commit (recommended)** / Rebase and merge / Squash and merge / Don't merge.
  - Merge commit is the default because it preserves every per-phase commit — the richest signal for later `git log`/`blame`/`bisect`.
  - When the epic retrospective verdict is `rejected` (Phase 8 / E8b), the prompt text carries the line `⚠️ Retrospective verdict: rejected — <doc>` first.
  - If a merge style is chosen → **ask a second question**: Delete branch? Yes / No.
- **Execute** (only if the user picked a merge style):
  - `gh pr merge <pr-number> --merge` *(or `--rebase` / `--squash`)* `[--delete-branch]`.
  - On success → `git switch <base_branch>` then `git pull --ff-only`, so the local tree matches `origin/<base_branch>` post-merge.
  - **Pending-checks fallback** — the merge fails because required checks are pending/expected on the head SHA (the finalize push superseded the CI-validated commit — the "inherent lag" above):
    - retry **once** with `--auto` added — the user already chose to merge, and auto-merge completes it when the checks pass; tell them that's what happened ("merge queued; completes when checks pass").
    - if the `--auto` retry also fails (e.g. auto-merge disabled in the repo) → fall through to the failure handling below.
  - On failure (branch protection, required reviews, conflict, CI required check missing, etc.):
    - don't retry, don't error out.
    - capture the `gh` stderr verbatim into the report under "Needs attention" ("PR merge failed: …; merge manually at `<pr_url>`") and leave the PR open.
    - the pipeline still ends `done` (the BMAD-status flip already happened) — a failed user-elected merge doesn't invalidate the completion.
- **Record** in state: `pr_merged: true|false`, `merge_method: squash|merge|rebase|null`, `branch_deleted: true|false` — written without a commit (the finalize commit is already pushed).
  - Surface the outcome in the **chat** report — a chat-only finalization artifact, one line: "Merged via merge commit; branch deleted." / "PR left open at user's request." / "Merge attempted but failed (`<reason>`); merge manually."
  - A *failed* merge also lands in the file's "⚠️ Needs human" — it's a genuine follow-up, not just an artifact echo.

- When the prompt is **off** for this run (`git.offer_merge: false` or `skip merge-prompt` override) → Phase 9 ends after the finalize bookkeeping; PR stays open for the human.

## Epic mode (`/auto-bmad epic`)
Epic mode produces **one** of each artifact for a whole epic (`epic-pipeline.md`):
- one branch → one PR → one CI wait → one merge prompt.

The run-level machinery above reuses **unchanged** — it all operates on the single epic PR:
- the **draft predicate** (clauses 1–4);
- the **CI wait**;
- the **merge prompt**.

Only the per-story-shaped items get an `epic-{e}` variant (below).

- **Branch (E1):**
  - Name: `{git.epic_branch_prefix}{e}-{slug}` (default prefix `epic/`), e.g. `epic/1-account-system`.
  - Create it explicitly off base — `git switch -c <branch> <base_branch>`.
  - Slug is resolved in E0 and stored as the anchor's `epic_slug` so resume reuses it.
    - Source: kebab-case of `epic_title` from `story_plan.py --epic {e} --sprint-status <impl>/sprint-status.yaml --planning-dir <planning>`; fallback the first story-key slug stem; else `epic-{e}`. Never a grep of the planning docs.
  - Per-story commits (the orchestrator's `story-{e}-{s}` commits AND build-auto's own) land on THIS branch; never on base.
- **Base-readiness guard (E0):** a git-only check — never a code read.
  - Epic mode branches off `{base}` and assumes already-`done` stories are in `{base}`.
  - The check: a `done` story has a `{git.branch_prefix}{e}-{s}-*` branch NOT merged into `{base}`.
    - Detect with `git branch --list "{git.branch_prefix}{e}-{s}-*"` then `git merge-base --is-ancestor <branch> <base_branch>`.
  - If that check holds → **ASK** before branching (`epic-pipeline.md` E0):
    - proceed off base — that story's work won't be in this epic's PR;
    - or stop and merge it first.
  - The same git-only `merge-base --is-ancestor` check runs in `epic-pipeline.md` E0 step 7 on the `branch` of any in-flight per-story state: resume that story in E5 only when it is the epic branch or already merged into `<base>`; else ASK Skip / Stop.
- **Commit taxonomy:**
  - Per-story commits keep their `story-{e}-{s}` scopes and subjects — they land on the epic branch unchanged (incl. the clean-tree gate commits and build-auto's own commits, recorded per the `commits[]` rule).
  - Epic-scoped commit subjects:
    - `chore(epic-{e}): start auto-bmad epic pipeline` (E1);
    - `test(epic-{e}): epic-level test design` (E2);
    - `test(epic-{e}): close trace coverage gaps (gate iter {i})` (E8a remediation);
    - `docs(epic-{e}): gate, deferred-work reconcile + archive, retrospective` (E8b — carries the pre-retro batch flip);
    - `docs(epic-{e}): pipeline report` (E_final);
    - `chore(epic-{e}): finalize (mark done + BMAD status)` (E_final).
  - Body rules are unchanged.
- **PR title/body:**
  - Title: `feat(epic-{e}): <epic summary>`.
  - Body must include:
    - a one-paragraph epic summary;
    - a **per-story rollup** — one line per landed story (`build status / review passes / deferred / trace`), from the anchor's `stories_landed` + each per-story state; E0-skipped stories are listed under **Skipped**, not in the rollup;
    - links to each story's spec (repo-relative `spec_path`);
    - the epic gate decision (E8a) + the retrospective verdict (E8b);
    - `## Open action items (epic {e})` from `sprint_plan.py status`;
    - a `## Needs attention` checklist aggregating deferred items across all stories, the stories whose review is unverified, E8a gaps, blockers, and the retro `rejected` line when it applies;
    - the `🤖 Generated by auto-bmad` footer.
- **Draft predicate (E8b / E_final):** the SAME predicate, evaluated on the **epic anchor**.
  - Call: `python3 {skill-root}/scripts/state_plan.py --state-dir <state-dir> --scope epic --story-key epic-{e} --finalize [--ci-status …] [--no-pr-draft]`.
  - Its inputs must be **aggregated up** to the anchor during the run (E5h, in the landing `set` patch):
    - a story whose Phase 7 left `review_unverified: true` (or the `skip code-review` override) → anchor `review_unverified: true`;
    - any per-story blocker → anchor `blockers`;
    - E8a terminal `FAIL` → anchor `blockers` entry (`epic {e} trace gate FAILED — …`);
    - E8a `WAIVED` → anchor `gate_decision`;
    - the one CI wait → anchor `ci_status`.
- **Batch BMAD-status flip:** on a **clean completion** (`flip_bmad_status: true`), flip **every story in `stories_landed`** to `done`.
  - Two chances: E8b pre-retro (no `--ci-status`; anchor `batch_flip_done: true`, `bmad_status_flipped_at: 82`), else E_final after the CI wait (`bmad_status_flipped_at: 9`).
  - One `python3 {skill-root}/scripts/story_plan.py --mark-status {key} --to done --sprint-status <impl>/sprint-status.yaml` per story; the last one lifts `epic-{e}` to `done` when the epic is complete.
  - Skip a pre-existing `done`.
  - **Never** flip an E0-skipped story (not landed, not in the rollup).
  - The flips + the anchor write fold into the E8b `docs(epic-{e}): gate, …` commit or the `chore(epic-{e}): finalize` commit — whichever performs them.
- **The caveated-epic mirror (call out):** a **caveated** epic leaves **ALL** landed stories at `review`, not just the offending one — because the batch flip is gated by `flip_bmad_status`.
  - One story's `review_unverified` or blocker (or any other clause) parks the whole epic at `review` until a human acts.
  - This is intended — a single PR is either mergeable or not.

## Mode `local`
- No push, no PR, no merge prompt — there's nothing to merge.
- Leave the branch checked out.
- The final report tells the user the branch name and that no GitHub remote/`gh` was found — so they can push/PR manually if they wish.
- Epic mode is the same — one `epic/{e}-{slug}` branch, no PR.
