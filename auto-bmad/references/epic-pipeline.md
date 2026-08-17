# Epic pipeline (`/auto-bmad epic`)

Epic mode drives a **whole epic** — every actionable story — in one run, then **one PR**: N branches / PRs / CI-waits / merges collapse into one.

Epic mode runs **unattended between E0 and E_final** (warned + confirmed at E0.11):
- There are **no per-story human checkpoints**: no spec-approval halt, no Phase 7 review halt (`hitl_halt: "auto-continued (epic — no halt)"`), no external-change re-review. *Stories mode carve-out: an entry's `spec_checkpoint` / `done_checkpoint` still pauses the epic (and a `spec_checkpoint` halt is re-opened on resume) — `stories-mode.md` §7.*
- Review stays automatic: build-auto's own review layers inside every build run, plus the Phase 7 follow-up pass on the secondary model when its gate holds. A story that still recommends a follow-up review after its last pass — or a run whose instructions skip the follow-up review — sets `review_unverified` on the epic anchor, and the epic **ships a draft**.
- A per-story `blocked`/`needs-human` **stops the whole epic** (report + resume command).

**The only human touchpoints left** are the **E0 safety asks** (config-drift review, adopt, base-readiness, the previous epic's retro verdict gate, the unattended-run confirm) and the **E_final merge prompt** — *plus, in stories mode, any entry carrying `spec_checkpoint` / `done_checkpoint` (`stories-mode.md` §7; E0.11's confirm lists them up front).*

Each E-step names the per-story phase it reuses; that phase's mechanics and cross-phase rules (clean-tree gate, `commits[]` capture, timing brackets, outcome vocabulary) apply unchanged inside the loop — as do the core principle (`SKILL.md` → The one rule), the ownership list (`git-and-pr.md` → "Ownership") and the `delegation.md` prompts (the per-story entries verbatim, plus the epic-scoped TEA / reconcile / retrospective ones). Placeholders (incl. `<state-dir>`, `<anchor>`, `<base>`, `<sprint_plan_script>`): the `delegation.md` glossary.

**Story source:** the E-steps below are written for sprint mode. `/auto-bmad epic --spec <folder>` runs a `bmad-spec` spec folder as the epic — the folder IS the epic — under the deltas in `stories-mode.md` (§8 for the E-steps). The `epic-{e}` / `story-{e}-{s}` commit scopes below are `{epic_label}` / `{story_label}`; stories mode substitutes `spec-{spec_slug}` / `story-{spec_slug}-{id}` (`stories-mode.md` §3).

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
- **Commits** — `git-and-pr.md` → "Commits"; the clean-tree gate's `pipeline state` commit may also sweep a pending anchor write.
- **Timing** — bracket every delegated step and every `AskUserQuestion` with `state_update.py timing-start/-pause` on the **epic anchor**; the loop body additionally brackets the per-story file exactly as `pipeline.md` does.
- **Clean-tree gate** (`git-and-pr.md`) — epic delta: the build-auto step's `timing-start` is written on BOTH the per-story file AND the anchor (folded forward, or before gate (b) — never after it), so no anchor write is ever pending at an invocation.
- **Exception — E0:** the anchor does not exist until E1's `init`, so E0 writes no state — every E0 decision rides into E1's `init --json` payload.
- **Halts** — a per-story `blocked`/`needs-human` runs **Blocked handling** (`pipeline.md`) and stops the whole epic. Epic deltas:
  - the anchor is NOT touched (no `blockers` append — a story's blockers reach the anchor only when it lands, E5h);
  - hand back to SKILL Step 3, which appends the epic report section tagged `(halted — needs-human)` as its fallback (`report-section --epic`, **no commit** — the human commits alongside their fix);
  - the recovery text's step 3 command becomes `/auto-bmad epic --epic {e}`;
  - no push, no PR.

---

## E0 — Preflight, enumerate & adopt  *(orchestrator)*
Runs during the SKILL procedure before any commit: **Phase 0 verbatim, in the `pipeline.md` Phase 0 order** (same precondition, same probes) — only the deltas below.

0. **Run instructions:** Phase 0 step 0 (`SKILL.md` → "Run instructions"). Epic delta: a **dry run**'s read-only window is the E0 steps below (drift / adopt / gate facts print as notes) and the stop is before E1. An instruction that only makes sense per story — entering at a phase, approving each spec, staying on the current branch — does not map onto the E-steps: say so and stop rather than guessing.
1. **Host/tier:** Phase 0 step 1.
2. **Epic-anchor resume pre-read** (no `uv`, no git): `python3 {skill-root}/scripts/state_plan.py --state-dir <state-dir> --scope epic`.
   - An in-flight anchor (`status != done`) whose `epic_num` is `{e}` (or, with no `--epic N`, the first in-flight anchor) ⇒ **resume target** — carry its `branch` (⇒ `--expected-branch` for step 3), `active_story`, and read the anchor for `stories_landed`, `stories_skipped`, `epic_slug`, `completed_phases`.
   - Otherwise a fresh epic run; `{e}` = `--epic N` if given, else resolved at step 5.
3. **ONE full `preflight.py` call:** Phase 0 step 3 — the required-skills CSV is unchanged (an epic run always reaches the epic end). Epic delta: `--expected-branch <anchor branch>` on a resume. *(Stories mode: the CSV stays unchanged here too — add `--story-source stories --spec-folder <folder>` and preflight downgrades `bmad-sprint-planning` / `sprint_plan.py` to a warning, `stories-mode.md` §2.)*
4. **Config-drift heal + review, then review-layers freshness:** Phase 0 step 4. Epic deltas: the pause happens once **before E1's `init`** and **cannot recur mid-epic** (after **Apply & continue** restamps `profiles_source_version`, no later E5 story re-checks); the writes are swept into E1's commit (or, on a resume, the next clean-tree gate / the E_final report commit).
5. **Sprint status read + `{e}` resolution** *(stories mode: no picker and no `{e}` — the folder is the epic; the carry-over block is always empty, `stories-mode.md` §8)*: the upstream picker call and its contract — `pipeline.md` Phase 0 step 5 (unconditional here). Epic deltas:
   - `{e}` still unknown (no `--epic N`, no in-flight anchor) ⇒ `{e}` = the epic number of `recommendation.story_key`.
   - Keep `open_action_items`: the entries with `epic == e-1` build **`{carry_over_block}`** once (`delegation.md` → `build-plan`); it is passed to **every** story's plan run in epic mode. Empty ⇒ no block.
6. **Enumerate the epic** *(stories mode: `story_plan.py --stories --spec-folder <folder>`, `stories-mode.md` §8)*: `python3 {skill-root}/scripts/story_plan.py --epic {e} --sprint-status <impl>/sprint-status.yaml --planning-dir <planning>` — the field list is Phase 0 step 5's; epic mode additionally keeps `epic_stories[]` (ordered; each `key`, `status`, `title`, `is_first_in_epic`, `is_last_in_epic`, `stories_after_in_epic`).
   - Epic delta: `hard_stop` (unparseable/unknown/empty epic, **epic already `done`**) ⇒ surface `hard_stop_reason`, stop — here it really stops, unlike the per-story informational verdict.
7. **Adopt — reconcile each story** (the epic form of the `state-and-resume.md` status-mismatch guard; stories mode keys the same matrix on the story file's own status — `stories-mode.md` §8). Decide per enumerated story, in order:
   - **On a resume, first skip every story in the anchor's `stories_landed`** — landed by THIS run; `stories_landed` (not the sprint status) is the authority for "done this run". Also skip every story in `stories_skipped` (E0 verdicts persist — never re-ask).
   - **`done`** ⇒ **skip** — listed under **Skipped** with reason `already done`; never re-entered, never flipped, not in the rollup.
   - **`review`/`in-progress` WITH a per-story `<state-dir>/{key}.yaml`** (`state_plan.py --state-dir <state-dir> --story-key {key}` ⇒ `exists: true`, `status != done`, `branch`) — the epic branch is the only place per-story work may land, so first check WHERE that state's work is (git only — never a code read):
     - its `branch` is the epic branch (the anchor's `branch` on a resume; on a fresh run any `{git.epic_branch_prefix}{e}-*` branch), OR that branch is already merged into `<base>` (`git merge-base --is-ancestor <branch> <base>` succeeds) ⇒ **resume that story in E5** from its first incomplete phase (its per-story file owns intra-story resume).
     - otherwise (a per-story run's own `{git.branch_prefix}{e}-{s}-*` branch, unmerged or missing — its commits and spec are not on the epic branch) ⇒ **ASK**: **Skip** (finish it per-story with `/auto-bmad --story {key}` — or merge that branch into `<base>` — then re-run the epic; listed under **Skipped** with reason `in-flight on <branch> — not on the epic branch`) / **Stop**. Never auto-resume it.
   - **`review`/`in-progress` WITHOUT a state file** (work done outside auto-bmad) ⇒ probe `python3 {skill-root}/scripts/story_plan.py --find-spec --impl-dir <impl> --story-key {key} --sprint-status <impl>/sprint-status.yaml` first (`ambiguous: true` ⇒ hard-stop listing `candidates`), then decide — two distinguishable options, never "adopt as-is":
     - `in-progress` and a spec found at `ready-for-dev`/`in-progress`/`in-review` ⇒ **ASK**: **Adopt — enter at Phase 5** (this story's E5 body starts at Phase 5 with that spec) / **Skip**.
     - `review` and a `done` spec found ⇒ **ASK**: **Adopt — run a follow-up review pass on it in E5** (E5 body starts at Phase 7) / **Skip**.
     - Any other combination (`found: false`, a `draft`/`blocked` spec, or a spec status the two rows above do not name) ⇒ **auto-skip** with an E0 note — `story {key} is {status} outside auto-bmad and has no build-auto spec — skipped` — no ask.
     - Adopted stories run their (partial) E5 body, join `stories_landed`, and are eligible for the E8b batch flip like any other landed story. Skipped stories are excluded from this run entirely (never flipped, not in the rollup, listed under **Skipped** with the E0 note as reason).
   - **`ready-for-dev`/`backlog`** ⇒ fresh loop body (Phase 3's resume matrix adopts an already-planned spec or re-plans a `draft` one).
   - Every story left after this step is the run's work list; no story ⇒ hard-stop `epic {e} has no story for auto-bmad to run` (list the skip reasons).
8. **Base-readiness guard** — epic mode branches off `<base>` and assumes `done` stories are in `<base>`. A `done` story with a `{git.branch_prefix}{e}-{s}-*` branch **not merged into `<base>`** (git-only detection: `git-and-pr.md` → "Epic mode") ⇒ **ASK**: proceed off base (that story's work won't be in this epic's PR) / stop and merge it first, then re-run. Skip on a resume (step 2 found the anchor): the epic branch was already cut off `<base>` at the first E0, so the ask was answered then and merging now cannot change the base.
9. **Epic slug:** derive per `git-and-pr.md` → "Branching" (stored in E1 as `epic_slug`; resume reuses it).
10. **Retro verdict gate:** `pipeline.md` Phase 0 step 7 (skip when `e == 1` or on a resume; not bracketed — the anchor does not exist yet). *Stories mode: the gate reads this same folder's `RETROSPECTIVE.md`; absent ⇒ skip, and the `e == 1` skip has no analogue (`stories-mode.md` §8).*
11. **Unattended-run confirm** *(stories mode: name the spec folder and list every story whose `spec_checkpoint` / `done_checkpoint` will pause the run — `stories-mode.md` §7)* (once, fresh runs only — skip on a resume with an in-flight anchor; suppressed on a dry run; not bracketed — the anchor does not exist yet): `AskUserQuestion` — "Epic {e} (`{epic_title}`, {n} stories: <work list>) will run **unattended** from E1 to E_final: no spec-approval halt, no per-story review halt, no epic-end trace-gate ask; one epic branch, one PR (draft if any caveat); a `blocked`/`needs-human` story stops the whole epic. Proceed?" — **Proceed** / **Stop**. Stop ⇒ hard-stop, nothing written.
12. **TEA triage is per story** — NOT run here (the epic spans many risk levels); E5a delegates `tea-triage` per story.
13. Record E0's decisions for E1's `init --json`: `epic_story_count`, `epic_slug`, the adopt verdicts (`stories_skipped`; the per-story adopt entry phase / spec ride into that story's E5a `init`), this run's `overrides`, `git_mode`, `base_branch`. `{carry_over_block}` is session memory (re-derived at step 5 on every E0). No commit, no state write.

## E1 — Epic branch + anchor  *(orchestrator, git)*
- Ensure we are NOT on `<base>`; create the **one** epic branch `{git.epic_branch_prefix}{e}-{slug}` (default `epic/{e}-{slug}`) off `<base>` — `git-and-pr.md` → "Branching"; on resume (the anchor exists) check it out and skip the `init` below.
- Write the epic anchor: `python3 {skill-root}/scripts/state_update.py init --state-file <anchor> --json -` (refuses if it exists, so resume never re-inits — `started_at` + timing span all sessions).
  - Payload: E0's decisions + the anchor extras (`state-and-resume.md` → "state/epic/epic-{e}.yaml").
- Commit: `chore(epic-{e}): start auto-bmad epic pipeline` (also carries a Phase 0 auto-applied `_bmad/custom/bmad-build-auto.toml` / healed `config.yaml`). Marker `1`.

## E2 — Epic-start setup  *(conditional; reuses Phase 2)*
Runs **once** at the start of the epic — one sub-step: **only if `tea.enabled`** delegate **`testarch-test-design (epic level)`** to `tea_epic` for epic `{e}`. Commit `test(epic-{e}): epic-level test design`. Gate false ⇒ no-op, marker `2` still recorded (so a later resume never re-runs epic test design).

## E5 — Story loop (sequential)  *(per story)*
For each `{key}` in `epic_stories` order that is **not in `stories_landed` and not in `stories_skipped`**: set `active_story: {key}` on the anchor, then run the per-story phases exactly as `pipeline.md` (delegation, state writes, commit subjects, clean-tree gate, `commits[]` capture) with the epic deltas below. `{branch}` in every prompt is the epic branch.

a. **Per-story state + triage.**
   - Delegate **`tea-triage`** to `tea_triage` (only if `tea.enabled`); classify per `tea-policy.md` (incl. the `trace-advisory` rule — `stories_after_in_epic` / `epic_story_count` from the E0 enumerate).
   - `python3 {skill-root}/scripts/state_update.py init --state-file <state-dir>/{key}.yaml --json -` with the Phase 1 payload; epic values: `branch` = the epic branch, `overrides` = this run's instructions, and `epic_story_count` / `stories_after_in_epic` / `is_first/last_in_epic` from the E0 enumerate. For an **E0-adopted** story also `spec_path` = the spec E0 found and `overrides.start_phase: 5` or `7` per the adopt choice (an orchestrator-set entry marker, not a user instruction) — the body then starts at that phase (`--allow-regress` is never needed: the entry only moves forward from `in-progress`/`review`).
   - Commit `chore(story-{e}-{s}): start auto-bmad pipeline` — this is the clean-tree gate before Phase 3 (fold Phase 3's `timing-start` on BOTH files, plus the anchor's `active_story` write, into it).
   - *(A story E0 marked "resume" reuses its existing per-story state — no `init` — and enters at its first incomplete phase; `set branch` = the epic branch on its per-story file (swept by the next clean-tree gate) so its record names where its work lands from now on.)*
b. **Phase 3 Plan** (**`build-plan`** → `build`): `{carry_over_block}` = epic {e-1}'s open action items for **every** story; **no spec-approval halt** (`spec_approved: true` on the folded write).
   - *Stories mode: an entry with `spec_checkpoint: true` DOES run the Phase 3 approval halt here — the ask, its resumable stop and the resume that re-opens it are `stories-mode.md` §7.*
c. **Phase 4 Pre-dev TEA** (only if `atdd ∈ tea_selected`) → **`testarch-atdd`**.
d. **Phase 5 Build** (**`build-run`** → `build`): `blocked` ⇒ **stops the whole epic** (`needs-human`, see the halt rule above).
e. **Phase 6 Post-dev TEA** (only if `automate ∈ tea_selected`) → **`testarch-automate`**.
f. **Phase 7 Follow-up review** (**`followup-review`** → `followup_review`): the same gate as per story; one pass when it holds (an E0-adopted `review` story enters under `pipeline.md` Phase 7's "Entry at Phase 7 without a Phase 5 result" rule — that is what the adopt choice means). Then `hitl_halt: "auto-continued (epic — no halt)"` — **no `AskUserQuestion`, no external-change check** (no human pause produced changes to review).
g. **Phase 7 tail** — trace advisory + deferred harvest + the tail commit rule as per story; `phase-done --phase 7` on the per-story file. Epic delta: **leave the sprint entry at `review`** — not `done` (the batch flip is E8b / E_final). *Stories mode: nothing to leave — there is no sprint entry (`stories-mode.md` §8).*
h. **Land the story on the anchor in ONE write** — a single `state_update.py set --state-file <anchor>` patch that, at once:
   - sets `stories_landed` = previous list + `[{key}]` (read-modify-write);
   - sets `active_story` = the next work-list key (or `null` after the last);
   - sets `review_unverified: true` if this story's is true (never back to false);
   - `_append`s the story's `blockers` / `open_questions` / `deferred_work` entries (each prefixed `[{key}] `) to the anchor's lists — only **live** blockers reach the anchor (`state-and-resume.md` → "Blockers clear on resume").

   Never two writes — a crash between them could double-land or double-append a re-entered story. Marker `5` once the work list is empty.

   *Stories mode: an entry with `done_checkpoint: true` pauses right here, after this write — the ask and its resumable stop are `stories-mode.md` §7.*

## E8a — Epic-end gates  *(conditional; reuses Phase 8.1)*
**Only if `tea.enabled`**: run `pipeline.md` Phase 8 step 1's gates at epic scope; record `gate_decision` + `phase8_steps.trace_gate/nfr/test_review` on the anchor.
- **The trace `FAIL` ask is SUPPRESSED** — epic mode never halts here, on any verdict. Remediation runs mechanically: `testarch-automate` at epic scope, commit `test(epic-{e}): close trace coverage gaps (gate iter {i})`, re-trace — up to `tea.gate_max_iterations`.
- Verdict deltas: `FAIL`/`WAIVED` ⇒ a finding in the epic report + PR `Needs attention`, and both make the epic PR a draft (`git-and-pr.md` → "Draft predicate"); a terminal `FAIL` (cap reached, still `FAIL`) keeps `gate_decision: FAIL` + `trace_gate: failed` and appends an anchor `blockers[]` entry `epic {e} trace gate FAILED — {n} requirements lack test coverage` (removed when a re-run gate returns non-`FAIL`).
- Marker `81` (also when the gate is `tea`-disabled — a no-op).

## E8b — Epic-end closing  *(reuses Phase 8.2–8.5)*
In order (anchor `phase8_steps` markers `reconcile` → `archive` → `retro`):
1. **Reconcile** (`deferred_reconcile`): `pipeline.md` Phase 8 step 2 — marker `reconcile`.
2. **Archive** (orchestrator-direct): `pipeline.md` Phase 8 step 3 — marker `archive`, recording `deferred_work_archived` on the anchor.
3. **Pre-retro batch flip** *(stories mode: no flip at all — record `batch_flip_done: true` vacuously and leave `bmad_status_flipped_at: null`, `stories-mode.md` §8)* (skip it when this run skips the retrospective — E_final flips instead): `python3 {skill-root}/scripts/state_plan.py --state-dir <state-dir> --scope epic --story-key epic-{e} --finalize` (no `--ci-status`). `flip_bmad_status: true` ⇒ flip **every story in `stories_landed`** — one `python3 {skill-root}/scripts/story_plan.py --mark-status {key} --to done --sprint-status <impl>/sprint-status.yaml` per story (skip a pre-existing `done`; E0-skipped stories are not landed and are never flipped); the last flip lifts `epic-{e}` to `done` when the epic is complete. Anchor `batch_flip_done: true`, `bmad_status_flipped_at: 82`; the flips + the anchor write fold into this step's commit. Caveated ⇒ flip **none** — **ALL** landed stories stay at `review`, not just the offending one; the retro then judges the epic unfinished. A later CI failure never regresses the entries; the caveat lives in the PR draft state + report. E_final step 4 is the second, idempotent chance.
4. **Retrospective** (`retrospective`; when this run skips it, still record the marker `retro: done`): `pipeline.md` Phase 8 step 5 (stories mode: on the spec folder — `stories-mode.md` §6). Epic deltas: `retro.doc` / `retro.verdict` / `retro.open_action_items` are written to the **anchor**, and the verdict gates the NEXT epic's E0 (step 10). Marker `retro: done`.
Commit once: `docs(epic-{e}): gate, deferred-work reconcile + archive, retrospective` (carries the flips + anchor writes; E8a remediation commits are already separate). Marker `82`.

## E_final — Finalize  *(orchestrator, git)*
1. **Ensure committed:** `pipeline.md` Phase 9 step 1. At epic scope the tolerated own-writes are the anchor's (a pending E5/E8 folded write, or a Phase 0 auto-applied heal / layers regen on a resume that entered at E8b/E_final).
2. **Epic report (before push):** `python3 {skill-root}/scripts/state_update.py report-section --epic --report-file <output_folder>/auto-bmad/reports/epic-{e}.md --state-file <anchor> --json -` — payload keys: `state-and-resume.md` → "reports/{key}.md" (epic — `EPIC_REPORT_PAYLOAD_KEYS`). `next` = `Human review: /bmad-checkpoint-preview <pr_url | branch>` + `Project context: run /bmad-project-context refresh (recommended after an epic).` Commit `docs(epic-{e}): pipeline report`.
3. **Mode `remote`:** push the epic branch, open **one** PR (title `feat(epic-{e}): <epic summary>`; body per `git-and-pr.md` → "Epic mode"), CI wait, draft conversion — all per `git-and-pr.md`. Capture `pr_url`, `ci_run_url`, `ci_status`. **Mode `local`:** leave the branch, no push/PR.
4. **Draft predicate + batch flip** *(stories mode: add `--story-source stories`; the flip never runs — `stories-mode.md` §8)*: `state_plan.py --state-dir <state-dir> --scope epic --story-key epic-{e} --finalize [--ci-status <live>] [--no-pr-draft]`. `flip_bmad_status: true` and NOT `batch_flip_done` ⇒ batch-flip now (same loop and rules as E8b step 3; `batch_flip_done: true`, `bmad_status_flipped_at: 9`; the flips + the anchor write fold into step 5's finalize commit); caveated ⇒ flip **none** — ALL landed stories stay at `review` (or `done` if E8b already flipped — never regressed).
5. Anchor `status: done`, `pr_url`, `ci_run_url`, `ci_status`, `branch`, `active_story: null` in ONE `set`; also `set status: done` + `pr_url` on every landed story's per-story `<state-dir>/{key}.yaml` (a completed run — the `state-and-resume.md` `done` rule then applies to them, so a bare `/auto-bmad` never resumes a story this epic already shipped). Commit `chore(epic-{e}): finalize (mark done + BMAD status)`; push. Marker `9`.
6. **Merge prompt** — `git-and-pr.md` → "Merging the PR"; add the retro `rejected` line when it applies. Outcome written to the **anchor**, without a commit.
7. Hand back to SKILL Step 3, which owns the chat-only lines. Epic delta for the final-status line: clean = every landed story flipped `done` (at E8b or E_final); caveated = ALL landed stories left at `review` + the draft reasons.

## Resume
- **Find the target:** `state_plan.py --state-dir <state-dir> --scope epic` — an `epic-{e}.yaml` with `status != done` is the resume target (`branch` ⇒ `--expected-branch`).
- **Enter at the first unresolved E-step** in the anchor's `completed_phases`; E8a/E8b at their first `null` `phase8_steps` marker; the batch flip is idempotent (`batch_flip_done`).
- **Intra-story granularity for `active_story`:** the anchor owns *which story / which E-step*; the per-story `<state-dir>/{key}.yaml` owns *which phase within the story* (`state-and-resume.md`). No halt is ever re-opened in epic mode — *except a stories-mode `spec_checkpoint` halt, which the resume re-opens for that story (`stories-mode.md` §7).*
- **Skip `stories_landed` and `stories_skipped`** — a resume never re-enters a story this run already landed or skipped, even though it sits at `review` with a complete per-story state file.
- Bare-`/auto-bmad` redirect (epic-ownership guard): `state-and-resume.md` → "Target selection"; stories mode matches the anchor on its `spec_folder` (`stories-mode.md` §8).

## Run instructions in epic mode
Interpretation and echo: `SKILL.md` → "Run instructions"; the epic delta is E0 step 0.
Whatever applies rides in the anchor's `overrides` and in each per-story `init` payload.
