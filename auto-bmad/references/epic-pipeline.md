# Epic pipeline (`/auto-bmad epic`)

Epic mode drives a **whole epic** — every actionable story — in one run, then **one PR**.

**Why epic mode exists** — to collapse N branches / PRs / CI-waits / merges into **one**, and to run the per-story build lane unattended from the first plan to the epic-end retrospective.

**The deliberate trade** — warned and confirmed up front — is that epic mode runs **unattended between E0 and E_final**:
- There are **no per-story human checkpoints**: no spec-approval halt, no Phase 7 review halt (`hitl_halt: "auto-continued (epic — no halt)"`), no external-change re-review.
- Review stays automatic: build-auto's own review layers inside every build run, plus the Phase 7 follow-up pass on the secondary model when its gate holds. A story that still recommends a follow-up review after its last pass — or `skip code-review` — sets `review_unverified` on the epic anchor, and the epic **ships a draft**.
- A per-story `blocked`/`needs-human` **stops the whole epic** (report + resume command).

**The only human touchpoints left** are the **E0 safety asks** (config-drift review, adopt, base-readiness, the previous epic's retro verdict gate, the unattended-run confirm) and the **E_final merge prompt**. The config-drift review fires only when an update shipped new config, pauses **once** before E1, and self-clears — it never recurs mid-epic.

**This file is the epic analog of `pipeline.md`.** It does **not** restate per-story phase internals:
- Each E-step names the per-story phase it reuses; read `pipeline.md` for that phase's mechanics (its cross-phase rules — clean-tree gate, `commits[]` capture around every build-auto invocation, timing brackets, outcome vocabulary — apply unchanged inside the loop).
- The orchestrator obeys the same **core principle**: it delegates every BMAD step, never reads or edits story code, never edits a spec, and reads spec/BMAD-doc facts only through the script readers (`story_plan.py`, `state_plan.py`, `deferred_ledger.py`, `sprint_plan.py status`).
- It owns git + finalize bookkeeping directly (`git-and-pr.md` → "Ownership" and "Epic mode", now at epic scope).
- The delegated prompts are the **exact** `delegation.md` entries — the per-story ones reused verbatim in the loop, plus the epic-scoped TEA / reconcile / retrospective entries.

**Placeholders:** the `delegation.md` glossary (it defines the epic ones too — `<state-dir>`, `<anchor>`, `<base>`, `<sprint_plan_script>`).

---

## E-steps at a glance

| E-step | Reuses (per-story) | Runs | Owner | Anchor marker |
|--------|--------------------|------|-------|---------------|
| **E0** Preflight, enumerate & adopt | Phase 0 | once | orchestrator (TEA triage deferred into E5a) | `0` |
| **E1** Epic branch + anchor | Phase 1 | once | orchestrator (git) | `1` |
| **E2** Epic-start | Phase 2 | once (conditional) | delegated | `2` |
| **E5** Story loop (sequential) | Phases 3–7 per story | per story | delegated steps; orchestrator commits/state | `5` |
| **E8a** Epic-end gates | Phase 8.1 | once (conditional) | delegated; gate ask **suppressed** | `81` |
| **E8b** Epic-end closing | Phase 8.2–8.5 | once | delegated + orchestrator (pre-retro batch flip) | `82` |
| **E_final** Finalize | Phase 9 | once | orchestrator (git) | `9` |

Rules that hold across E-steps:
- **Sequential loop** — never overlap stories; a story's Phase 3 plan starts only after the previous story landed (E5h).
- **Markers** — each E-step records its integer marker in the **epic anchor's** `completed_phases` (`state_update.py phase-done --phase <marker> --state-file <anchor>`) in a folded write. E8a/E8b sub-steps resume by the anchor's `phase8_steps` markers (`trace_gate`/`nfr`/`test_review` for E8a; `reconcile`/`archive`/`retro` for E8b).
- **Commits** — per `git-and-pr.md` → "Commits" (each E-step commits its artifacts + state together, never state-only); the clean-tree gate's `pipeline state` commit is the one exception and may also sweep a pending anchor write.
- **Timing** — bracket every delegated step and every `AskUserQuestion` with `state_update.py timing-start/-pause` on the **epic anchor**; the loop body additionally brackets the per-story file exactly as `pipeline.md` does.
- **Clean-tree gate, epic delta** (`git-and-pr.md` → "Clean-tree gate"): both files get the build-auto step's `timing-start` — the per-story file AND the anchor (E5a start → E5b; `plan spec` → E5d; `mark review`/Phase 6 → E5f), so no anchor write is ever pending at an invocation. On any non-folded path write BOTH before gate (b), never after it.
- **Exception — E0:** the anchor does not exist until E1's `init`, so E0 writes no state — every E0 decision rides into E1's `init --json` payload.
- **Halts** — a per-story `blocked`/`needs-human` runs **Blocked handling** (`pipeline.md` header) and stops the whole epic. Epic deltas: the anchor is NOT touched (no `blockers` append — a story's blockers reach the anchor only when it lands, E5h); hand back to SKILL Step 3, which appends the epic report section tagged `(halted — needs-human)` as its fallback (`report-section --epic`, **no commit** — the human commits alongside their fix); the recovery text's step 3 command becomes `/auto-bmad epic --epic {e}` (a bare `/auto-bmad --story {key}` on an epic-owned story hard-stops per the SKILL.md epic-ownership guard). No push, no PR.

---

## E0 — Preflight, enumerate & adopt  *(orchestrator)*
Runs during the SKILL procedure before any commit. **Phase 0 verbatim, in the `pipeline.md` Phase 0 order** — every step's inputs come only from earlier steps. Same probe discipline: one full `preflight.py` call; never a bare glob.

Precondition: the `--central-config-only` call + the runtime-config locate — `SKILL.md` → On activation / Step 0.

0. **Overrides:** as Phase 0 step 0, with `overrides.md` → "Epic mode" for what composes and what is rejected (reject with its precise message). Epic delta: `dry_run`'s read-only window is the E0 steps below (drift / adopt / gate facts print as notes) and the stop is before E1.
1. **Host/tier:** as Phase 0 step 1.
2. **Epic-anchor resume pre-read** (no `uv`, no git): `python3 {skill-root}/scripts/state_plan.py --state-dir <state-dir> --scope epic`.
   - An in-flight anchor (`status != done`) whose `epic_num` is `{e}` (or, with no `--epic N`, the first in-flight anchor) ⇒ **resume target** — carry its `branch` (⇒ `--expected-branch` for step 3), `active_story`, and read the anchor for `stories_landed`, `epic_slug`, `completed_phases`.
   - Otherwise a fresh epic run; `{e}` = `--epic N` if given, else resolved at step 5.
3. **ONE full `preflight.py` call:** as Phase 0 step 3 — same flags, same required-skills CSV (the same set as a per-story run, because this run always reaches the epic end), same `hard_stop`/`warnings` handling, keep `skills.sprint_plan_script` + the `git` block. Epic delta: `--expected-branch <anchor branch>` on a resume.
4. **Config-drift heal + review, then review-layers freshness:** as Phase 0 step 4. Epic deltas: the pause happens once **before E1's `init`** and **cannot recur mid-epic** (after **Apply & continue** restamps `profiles_source_version`, no later E5 story re-checks); the writes are swept into E1's commit (or, on a resume, the next clean-tree gate / the E_final report commit).
5. **Sprint status read + `{e}` resolution:** the upstream picker call (unconditional here) + its contract (`ok: false` / `all_done` / null-key hard-stops, the `risks`/`warnings`/`illegal`/`unrecognized` echo) — `pipeline.md` Phase 0 step 5. Epic deltas:
   - `{e}` still unknown (no `--epic N`, no in-flight anchor) ⇒ `{e}` = the epic number of `recommendation.story_key`.
   - Keep `open_action_items`: the entries with `epic == e-1` build **`{carry_over_block}`** once (`delegation.md` → `build-plan`); it is passed to **every** story's plan run in epic mode. Empty ⇒ no block.
6. **Enumerate the epic:** `python3 {skill-root}/scripts/story_plan.py --epic {e} --sprint-status <impl>/sprint-status.yaml --planning-dir <planning>` — the field list is Phase 0 step 5's; epic mode additionally keeps `epic_stories[]` (ordered; each `key`, `status`, `title`, `is_first_in_epic`, `is_last_in_epic`, `stories_after_in_epic`).
   - Epic delta: `hard_stop` (unparseable/unknown/empty epic, **epic already `done`**) ⇒ surface `hard_stop_reason`, stop — here it really stops, unlike the per-story informational verdict.
7. **Adopt — reconcile each story** (the epic form of the `state-and-resume.md` status-mismatch guard). Decide per enumerated story, in order:
   - **On a resume, first skip every story in the anchor's `stories_landed`** — landed by THIS run; `stories_landed` (not the sprint status) is the authority for "done this run". Also skip every story recorded in the anchor's `stories_skipped` (E0 verdicts persist — never re-ask).
   - **`done`** ⇒ **skip** — listed under **Skipped** with reason `already done`; never re-entered, never flipped, not in the rollup.
   - **`review`/`in-progress` WITH a per-story `<state-dir>/{key}.yaml`** (`state_plan.py --state-dir <state-dir> --story-key {key}` ⇒ `exists: true`, `status != done`, `branch`) — the epic branch is the only place per-story work may land, so first check WHERE that state's work is (git only — never a code read):
     - its `branch` is the epic branch (the anchor's `branch` on a resume; on a fresh run any `{git.epic_branch_prefix}{e}-*` branch), OR that branch is already merged into `<base>` (`git merge-base --is-ancestor <branch> <base>` succeeds) ⇒ **resume that story in E5** from its first incomplete phase (its per-story file owns intra-story resume).
     - otherwise (a per-story run's own `{git.branch_prefix}{e}-{s}-*` branch — unmerged, or missing — its commits and spec are NOT on the epic branch, so E5 cannot resume it here) ⇒ **ASK**: **Skip** (finish it per-story with `/auto-bmad --story {key}` — or merge that branch into `<base>` — then re-run the epic; listed under **Skipped** with reason `in-flight on <branch> — not on the epic branch`) / **Stop**. Never auto-resume it.
   - **`review`/`in-progress` WITHOUT a state file** (work done outside auto-bmad) ⇒ probe `python3 {skill-root}/scripts/story_plan.py --find-spec --impl-dir <impl> --story-key {key} --sprint-status <impl>/sprint-status.yaml` first (`ambiguous: true` ⇒ hard-stop listing `candidates`), then decide — two distinguishable options, never "adopt as-is":
     - `in-progress` and a spec found at `ready-for-dev`/`in-progress`/`in-review` ⇒ **ASK**: **Adopt — enter at Phase 5** (this story's E5 body starts at Phase 5 with that spec) / **Skip**.
     - `review` and a `done` spec found ⇒ **ASK**: **Adopt — run a follow-up review pass on it in E5** (E5 body starts at Phase 7) / **Skip**.
     - Any other combination (`found: false`, a `draft`/`blocked` spec, or a spec status the two rows above do not name) ⇒ **auto-skip** with an E0 note — `story {key} is {status} outside auto-bmad and has no build-auto spec — skipped` — no ask.
     - Adopted stories run their (partial) E5 body, join `stories_landed`, and are eligible for the E8b batch flip like any other landed story. Skipped stories are excluded from this run entirely (never flipped, not in the rollup, listed under **Skipped** with the E0 note as reason).
   - **`ready-for-dev`/`backlog`** ⇒ fresh loop body (Phase 3 adopts an already-planned spec when `--find-spec` finds one at `ready-for-dev`, or re-plans a `draft` one — `pipeline.md` Phase 3 resume matrix).
   - Every story left after this step is the run's work list; no story ⇒ hard-stop `epic {e} has no story for auto-bmad to run` (list the skip reasons).
8. **Base-readiness guard (git only — never a code read):** epic mode branches off `<base>` and assumes `done` stories are in `<base>`. A `done` story with a `{git.branch_prefix}{e}-{s}-*` branch **not merged into `<base>`** (`git branch --list "{git.branch_prefix}{e}-{s}-*"` then `git merge-base --is-ancestor <branch> <base>`) ⇒ **ASK**: proceed off base (that story's work won't be in this epic's PR) / stop and merge it first, then re-run. Skip on a resume (step 2 found the anchor): the epic branch was already cut off `<base>` at the first E0, so the ask was answered then and merging now cannot change the base.
9. **Epic slug** (deterministic, no grep): kebab-case of `epic_title` from step 6; fallback the first story-key's slug stem, else `epic-{e}`. Stored in E1 as `epic_slug` so resume reuses it, never re-derives a different one.
10. **Retro verdict gate:** `pipeline.md` Phase 0 step 7 (skip when `e == 1`, on a resume, or `skip retro-gate`; not bracketed — the anchor does not exist yet).
11. **Unattended-run confirm** (once, fresh runs only — skip on a resume with an in-flight anchor; suppressed by `dry_run`; not bracketed — the anchor does not exist yet): `AskUserQuestion` — "Epic {e} (`{epic_title}`, {n} stories: <work list>) will run **unattended** from E1 to E_final: no spec-approval halt, no per-story review halt, no epic-end trace-gate ask; one epic branch, one PR (draft if any caveat); a `blocked`/`needs-human` story stops the whole epic. Proceed?" — **Proceed** / **Stop**. Stop ⇒ hard-stop, nothing written.
12. **TEA triage is per story** — NOT run here (the epic spans many risk levels); E5a delegates `tea-triage` per story.
13. Record E0's decisions for E1's `init --json`: `epic_story_count`, `epic_slug`, the adopt verdicts (`stories_skipped`; the per-story adopt entry phase / spec ride into that story's E5a `init`), the composed `overrides`, `git_mode`, `base_branch`. `{carry_over_block}` is session memory (re-derived at step 5 on every E0). No commit, no state write.

## E1 — Epic branch + anchor  *(orchestrator, git)*
- Ensure we are NOT on `<base>`; create the **one** epic branch `{git.epic_branch_prefix}{e}-{slug}` (default `epic/{e}-{slug}`) off `<base>` — `git switch -c <branch> <base>` (`git-and-pr.md` → "Branching"); on resume (the anchor exists) check it out and skip the `init` below.
- Write the epic anchor: `python3 {skill-root}/scripts/state_update.py init --state-file <anchor> --json -` (refuses if it exists, so resume never re-inits — `started_at` + timing span all sessions).
  - Payload: E0's decisions plus `story_key: epic-{e}`, `epic_num: {e}`, `branch`, `epic_slug`, `active_story: null`, `stories_landed: []`, `stories_skipped: ["{key} — <reason>", …]` (preserved extras; `stories_landed`/`stories_skipped` are read-modify-write lists — `_append` does not apply to them).
- Commit: `chore(epic-{e}): start auto-bmad epic pipeline` (also carries a Phase 0 auto-applied `_bmad/custom/bmad-build-auto.toml` / healed `config.yaml`). Marker `1`.

## E2 — Epic-start setup  *(conditional; reuses Phase 2)*
Runs **once** at the start of the epic — one sub-step: **only if `tea.enabled`** (and not `skip tea`) delegate **`testarch-test-design (epic level)`** to `tea_epic` for epic `{e}`. Commit `test(epic-{e}): epic-level test design`. Gate false ⇒ no-op, marker `2` still recorded.

> **Resume note:** if the epic was partially completed **outside** epic mode (no anchor existed before this run), E2 still records its marker once run, so a later resume cannot re-run epic test design.

## E5 — Story loop (sequential)  *(per story)*
For each `{key}` in `epic_stories` order that is **not in `stories_landed` and not in `stories_skipped`**: set `active_story: {key}` on the anchor, then run the per-story phases exactly as `pipeline.md` (delegation, state writes, commit subjects, clean-tree gate, `commits[]` capture) with the epic deltas below. `{branch}` in every prompt is the epic branch.

a. **Per-story state + triage.**
   - Delegate **`tea-triage`** to `tea_triage` (only if `tea.enabled` and not `skip tea`); classify per `tea-policy.md` (incl. the `trace-advisory` rule — `stories_after_in_epic` / `epic_story_count` from the E0 enumerate).
   - `python3 {skill-root}/scripts/state_update.py init --state-file <state-dir>/{key}.yaml --json -` with the Phase 1 payload (`story_suffix`, `branch` = the epic branch, `tea_*`, `epic_story_count`, `stories_after_in_epic`, `is_first/last_in_epic`, `git_mode`, `base_branch`, `overrides` = the composed epic overrides). For an **E0-adopted** story also `spec_path` = the spec E0 found and `overrides.start_phase: 5` or `7` per the adopt choice (an orchestrator-set entry marker — the user-facing `start_phase` override stays rejected in epic mode) — the body then starts at that phase (`--allow-regress` is never needed: the entry only moves forward from `in-progress`/`review`).
   - Commit `chore(story-{e}-{s}): start auto-bmad pipeline` — this is the clean-tree gate before Phase 3 (fold Phase 3's `timing-start` on BOTH the per-story file and the anchor, plus the anchor's `active_story` write, into it).
   - *(A story E0 marked "resume" reuses its existing per-story state — no `init` — and enters at its first incomplete phase; `set branch` = the epic branch on its per-story file (swept by the next clean-tree gate) so its record names where its work lands from now on.)*
b. **Phase 3 Plan** (`build-plan` → `build`): `{carry_over_block}` = epic {e-1}'s open action items for **every** story; **no spec-approval halt** (`spec_approved: true` on the folded write). Sprint entry → `ready-for-dev`; commit `docs(story-{e}-{s}): plan spec`.
c. **Phase 4 Pre-dev TEA** (only if `atdd ∈ tea_selected`) → `testarch-atdd`; commit `test(story-{e}-{s}): ATDD acceptance scaffolds (red)`.
d. **Phase 5 Build** (`build-run` → `build`): sprint entry → `in-progress` (lifts `epic-{e}`), then `review`; commit `chore(story-{e}-{s}): mark review`. `blocked` ⇒ **stops the whole epic** (`needs-human`, see the halt rule above).
e. **Phase 6 Post-dev TEA** (only if `automate ∈ tea_selected`) → `testarch-automate`; commit `test(story-{e}-{s}): expand automated coverage`.
f. **Phase 7 Follow-up review** (`followup-review` → `followup_review`): same gate as per story (`skip code-review` ⇒ no pass + `review_unverified: true`); one pass when it holds (an E0-adopted `review` story enters under `pipeline.md` Phase 7's "Entry at Phase 7 without a Phase 5 result" rule — that is what the adopt choice means); `review_unverified` per Phase 7 step 2. Then `hitl_halt: "auto-continued (epic — no halt)"` — **no `AskUserQuestion`, no external-change check** (no human pause produced changes to review).
g. **Phase 7 tail** — trace advisory (if `trace-advisory ∈ tea_selected`; `story_trace`) + deferred harvest (`deferred_ledger.py harvest --ledger <impl>/deferred-work.md --spec <spec_path> --story-key {key}`) + the tail commit rule; `phase-done --phase 7` on the per-story file. **Leave the sprint entry at `review`** — not `done` (the batch flip is E8b / E_final).
h. **Land the story on the anchor in ONE write** — a single `state_update.py set --state-file <anchor>` patch that, at once: sets `stories_landed` = previous list + `[{key}]` (read-modify-write); sets `active_story` = the next work-list key (or `null` after the last); sets `review_unverified: true` if this story's is true (never back to false); `_append`s the story's `blockers` / `open_questions` / `deferred_work` entries (each prefixed `[{key}] `) to the anchor's lists — only **live** blockers reach the anchor: a phase that blocked and later completed on resume has already removed its own entries (`state-and-resume.md` → "Blockers clear on resume"). Never two writes — a crash between them could double-land or double-append a re-entered story. Marker `5` once the work list is empty.

## E8a — Epic-end gates  *(conditional; reuses Phase 8.1)*
**Only if `tea.enabled`** (and not `skip tea`): delegate **`testarch-trace (epic gate)`** via `tea_epic` (blocking), then **`testarch-nfr (epic gate)`** + **`testarch-test-review (epic gate)`** via `tea_epic_audit` (advisory) — verdicts from the delegates' structured results only, never a TEA artifact read. Record `gate_decision` + `phase8_steps.trace_gate/nfr/test_review` on the anchor.
- **The trace `FAIL` ask is SUPPRESSED** — epic mode never halts here. Remediation runs mechanically: `testarch-automate` at epic scope, commit `test(epic-{e}): close trace coverage gaps (gate iter {i})`, re-trace — up to `tea.gate_max_iterations`.
- Verdicts as `pipeline.md` Phase 8 step 1. Epic deltas: `FAIL`/`WAIVED` ⇒ a finding in the epic report + PR `Needs attention`, and **both drive the draft predicate** — `WAIVED` via clause 3 (`gate_decision`); a terminal `FAIL` (cap reached, still `FAIL`) keeps `gate_decision: FAIL` + `trace_gate: failed` and appends an anchor `blockers[]` entry `epic {e} trace gate FAILED — {n} requirements lack test coverage` (clause 1; removed when a re-run gate returns non-`FAIL`, per "Blockers clear on resume"). No `AskUserQuestion`.
- Marker `81` (also when the gate is `tea`-disabled — a no-op).

## E8b — Epic-end closing  *(reuses Phase 8.2–8.5)*
In order (anchor `phase8_steps` markers `reconcile` → `archive` → `retro`):
1. **Reconcile** (`deferred_reconcile`): as `pipeline.md` Phase 8 step 2 — marker `reconcile`.
2. **Archive** (orchestrator-direct): as `pipeline.md` Phase 8 step 3 — marker `archive`, recording `deferred_work_archived` on the anchor.
3. **Pre-retro batch flip** (skip when `skip retrospective`): `python3 {skill-root}/scripts/state_plan.py --state-dir <state-dir> --scope epic --story-key epic-{e} --finalize` (no `--ci-status`). `flip_bmad_status: true` ⇒ flip **every story in `stories_landed`** — one `python3 {skill-root}/scripts/story_plan.py --mark-status {key} --to done --sprint-status <impl>/sprint-status.yaml` per story (skip a pre-existing `done`; E0-skipped stories are not landed and are never flipped); the last flip lifts `epic-{e}` to `done` when the epic is complete. Anchor `batch_flip_done: true`, `bmad_status_flipped_at: 82`; the flips + the anchor write fold into this step's commit. Caveated ⇒ flip **none** — **ALL** landed stories stay at `review`, not just the offending one (one PR is either mergeable or not), and the retro then judges the epic unfinished. A later CI failure never regresses the entries; the caveat lives in the PR draft state + report. E_final step 4 is the second, idempotent chance.
4. **Retrospective** (`retrospective`; skip on `skip retrospective`): as `pipeline.md` Phase 8 step 5. Epic deltas: `retro.doc` / `retro.verdict` / `retro.open_action_items` are written to the **anchor**, and the verdict gates the NEXT epic's E0 (step 10). Marker `retro: done`.
Commit once: `docs(epic-{e}): gate, deferred-work reconcile + archive, retrospective` (carries the flips + anchor writes; E8a remediation commits are already separate). Marker `82`.

## E_final — Finalize  *(orchestrator, git)*
1. Ensure committed: per `pipeline.md` Phase 9 step 1 (own-writes exclusion: `pipeline.md` Phase 7 step 3). At epic scope the tolerated writes are the anchor's (a pending E5/E8 folded write, or a Phase 0 auto-applied heal / layers regen on a resume that entered at E8b/E_final).
2. **Epic report (before push):** `python3 {skill-root}/scripts/state_update.py report-section --epic --report-file <output_folder>/auto-bmad/reports/epic-{e}.md --state-file <anchor> --json -` with the `EPIC_REPORT_PAYLOAD_KEYS`: `disposition_tag`, `pipeline_status`, `continues`, `epic_summary`, `story_rollup` (one line per landed story: `build status / review passes / deferred / trace`, from each per-story state), `stories_skipped` (one line per story with its reason), `epic_gate`, `tea`, `retro` (verdict, open action items listed, doc), `overrides`, `open_questions`, `deferred_work` + `deferred_archived_note`, `needs_human`, `next`, `head_sha`. `next` = `Human review: /bmad-checkpoint-preview <pr_url | branch>` + `Project context: run /bmad-project-context refresh (recommended after an epic).` Commit `docs(epic-{e}): pipeline report`.
3. **Mode `remote`:** push the epic branch, open **one** PR (title `feat(epic-{e}): <epic summary>`; body per `git-and-pr.md` → "Epic mode (`/auto-bmad epic`)", which owns the required epic PR-body sections; `--draft` per the pre-CI predicate), CI wait (`ci_wait.py`), draft conversion — per `git-and-pr.md`. Capture `pr_url`, `ci_run_url`, `ci_status`. **Mode `local`:** leave the branch, no push/PR.
4. **Draft predicate + batch flip:** `state_plan.py --state-dir <state-dir> --scope epic --story-key epic-{e} --finalize [--ci-status <live>] [--no-pr-draft]`. `flip_bmad_status: true` and NOT `batch_flip_done` ⇒ batch-flip now (same per-story `--mark-status … --to done` loop as E8b.3, same skip-a-pre-existing-`done` / never-an-E0-skipped-story rules; `batch_flip_done: true`, `bmad_status_flipped_at: 9`; the flips + the anchor write fold into step 5's finalize commit); caveated ⇒ flip **none** — ALL landed stories stay at `review` (or `done` if E8b already flipped — never regressed).
5. Anchor `status: done`, `pr_url`, `ci_run_url`, `ci_status`, `branch`, `active_story: null` in ONE `set`; also `set status: done` + `pr_url` on every landed story's per-story `<state-dir>/{key}.yaml` (a completed run — the `state-and-resume.md` `done` rule then applies to them, so a bare `/auto-bmad` never resumes a story this epic already shipped). Commit `chore(epic-{e}): finalize (mark done + BMAD status)`; push. Marker `9`.
6. **Merge prompt** — per `git-and-pr.md` → "Merging the PR"; add the retro `rejected` line when it applies. Outcome written to the **anchor**, without a commit.
7. Hand back to SKILL Step 3. Chat-only lines: final status (clean = landed stories flipped `done` — at E8b or E_final — vs caveated = ALL landed stories left at `review` + the draft reasons), PR, CI, merge, next-step lines as in `next`.

## Resume
- **Find the target:** `state_plan.py --state-dir <state-dir> --scope epic` — an `epic-{e}.yaml` with `status != done` is the resume target (`branch` ⇒ `--expected-branch`).
- **Enter at the first unresolved E-step** in the anchor's `completed_phases`; E8a/E8b at their first `null` `phase8_steps` marker; the batch flip is idempotent (`batch_flip_done`).
- **Intra-story granularity for `active_story`:** the anchor owns *which story / which E-step*; the per-story `<state-dir>/{key}.yaml` owns *which phase within the story* (`pipeline.md` resume rules: Phase 3 by the resume matrix, Phase 5/7 re-invoke build-auto with `<spec_path>`, a follow-up pass is atomic — re-run it). No halt is ever re-opened in epic mode.
- **Skip `stories_landed` and `stories_skipped`** — a resume never re-enters a story this run already landed or skipped, even though it sits at `review` with a complete per-story state file.
- **A bare `/auto-bmad` (no `epic`) whose target story is owned by an in-flight epic anchor hard-stops**, redirecting to `/auto-bmad epic --epic {e}` (SKILL.md) — finishing one story alone would split the epic's single PR.

## Overrides in epic mode
Composition and rejections are normative in `overrides.md` → "Epic mode". Composing: `dry_run`, `skip tea`, `skip merge-prompt`, `git_mode local` (and `skip pr`), `no_pr_draft`, `skip config-pause`, `skip retro-gate`, `skip code-review` (skips **every** story's follow-up pass and sets `review_unverified` on the anchor — draft epic PR), `skip retrospective` (also skips the E8b pre-retro flip; E_final flips instead), `skip trace-advisory`. Rejected: the phase window (`start_phase`/`stop_before`/`stop_after`), phase-number skips, `approve spec`, `skip branch`. Every composed override rides in the anchor's `overrides` and in each per-story `init` payload.
