# Epic pipeline (`/auto-bmad epic`)

Epic mode drives a **whole epic** — every actionable story — in one run, then **one PR**.

**Why epic mode exists** — to recover wall-clock on an epic that is unsustainable story-by-story:
- It trims the per-story heavy code-review loop to a **thin single review + fix** (Tier A).
- It batches the heavy adversarial review into **one epic integration review** (Tier B).
- It collapses N branches / PRs / CI-waits / merges into **one**.

**The deliberate trade** — warned and confirmed up front — is that epic mode runs **unattended through the review**:
- There are **no per-story human checkpoints**.
- There is **no review halt at all** — not even at epic end.
- Every `[Review][Decision]` finding is **auto-resolved with the triage's recommended resolution**.
- An unconverged review **ships a draft** — and a Critical/High auto-decision also forces the draft.
- Both the auto-resolutions and the draft are surfaced in the final report.

**The only human touchpoints left** are the **E0 preflight safety asks** (config-drift review, adopt, base-readiness) and the **E_final merge prompt**. The config-drift review fires only when an update shipped new config, pauses **once** before E1, and self-clears — it never recurs mid-epic.

**This file is the epic analog of `pipeline.md`.** It does **not** restate per-story phase internals:
- Each E-step names the per-story phase it reuses; read `pipeline.md` for that phase's mechanics.
- The orchestrator obeys the same **core principle**: it delegates every BMAD step and **reads no code**.
- It owns git + finalize bookkeeping directly (`git-and-pr.md` → "Ownership", now at epic scope).
- The delegated prompts are the **exact** `delegation.md` entries — the per-story ones reused verbatim in the loop, plus the epic code-review variants.

**Placeholders** are the `delegation.md` glossary (`{e}`/`{s}`, `{key}`, `{slug}`, `<impl>`, `<story_file>`, `<project_root>`, …):
- `{state}` = `<output_folder>/auto-bmad/state`.
- The **epic anchor** is `{state}/epic/epic-{e}.yaml` (`state-and-resume.md` → "state/epic/epic-{e}.yaml").
- `{base}` = `git.base_branch`.

---

## E-steps at a glance

| E-step | Reuses (per-story) | Runs | Owner |
|--------|--------------------|------|-------|
| **E0** Preflight, enumerate & adopt | Phase 0 | once | orchestrator (+ delegated TEA triage is deferred into E5) |
| **E1** Epic branch + anchor | Phase 1 | once | orchestrator (git) |
| **E2** Epic-start | Phase 2 | once (conditional) | delegated |
| **E5** Story loop (sequential) + **Tier A** | Phases 3–7 per story | per story | delegated steps; orchestrator commits/state |
| **E8a** Epic-end gates | Phase 8 (gates) | once (conditional) | delegated; gate ask **suppressed** |
| **E_review** Epic integration review (**Tier B**) | Phase 7 at epic scope | once (conditional) | delegated fan-out; **no halt** — decisions auto-resolved; unconverged ⇒ draft |
| **E8b** Epic-end closing | Phase 8 (closing) | once (conditional) | delegated |
| **E_final** Finalize | Phase 9 | once | orchestrator (git) |

The loop is **sequential** — create-story for the next story is **not** overlapped with the current story's dev (dev-story is the irreducible core; nothing else is safely overlappable).

Each E-step records its marker in the **epic anchor's** `completed_phases` (the E-steps as integers: E0→0, E1→1, E2→2, E5→5, E8a→81, E_review→7, E8b→82, E_final→9) in a folded `state_update.py` write.

Each E-step commits in the same single commit as its artifacts (`git-and-pr.md` → "Commits") — never a state-only commit.

Bracket every delegated step and every `AskUserQuestion` with `state_update.py timing-start/-pause` on the **epic anchor** (the per-story loop body also brackets the per-story state file).

**Exception — E0:** the epic anchor does not exist until E1's `init`, so E0 writes no state — every E0 decision rides into E1's `init --json` payload.

---

## E0 — Preflight, enumerate & adopt  *(orchestrator)*
Runs during the SKILL procedure before any commit. Same probe discipline as Phase 0: one `preflight.py` call; never a bare glob.

1. **Preflight (reuse Phase 0 verbatim):** run `preflight.py` for git state/mode, project-context, CI presence, required skills, and the config-drift heal (`config_plan.py`) + provisioning freshness.
   - Obey its `git` block + `hard_stop`.
   - The required-skills list is the same as a per-story run: core + TEA if enabled + epic-end skills — because this run always reaches the epic end.
   - **The config-drift review pause fires here — once.** Run Phase 0's config-drift step exactly (`pipeline.md`): on **reviewable drift** (the pause predicate — a new profile / phase mapping / setting the heal will add) open the same pre-run pause **before E1's `init`**, consistent with E0's other front-loaded asks (adopt / base-readiness). After **Apply & continue** restamps `profiles_source_version`, every later E5 story's Phase 0 check reads `fresh`, so the pause **cannot recur mid-epic** — the run stays unattended. `skip config-pause` bypasses it; version-only drift auto-applies without pausing (as per story).
2. **Enumerate the epic:** `python3 {skill-root}/scripts/story_plan.py --epic {e} --sprint-status <impl>/sprint-status.yaml --impl-dir <impl>`.
   - Parse `epic_stories` (ordered).
   - `hard_stop` true (unknown/empty epic, or epic already `done`) ⇒ surface and stop.
   - (SKILL.md owns how `{e}` is resolved — `--epic N`, else the epic of the next actionable story.)
3. **Adopt — reconcile each story** (`state-and-resume.md` → "Adopting a partially-started epic"; the plan's full rules).
   - **First, on a resume, skip every story already in the epic anchor's `stories_landed`** — it was completed by THIS run, so it must NOT be re-entered, even though it sits at `review` with a complete per-story state file. `stories_landed` (not the `review` status) is the authority for "done this run"; the status-based rules below are for stories finished *outside* this run.
   - Then, for each remaining enumerated story, decide using its `status` + whether a per-story `{state}/{key}.yaml` exists:
     - **`done`** → **skip** — no re-dev, no re-review; assumed already in `{base}`; NOT in the batch-flip set.
     - **`review`/`in-progress` WITH a state file** (and NOT in `stories_landed`) → resume that story per-story in E5 (the existing `state_plan.py --story-key {key}` path; continue from its first incomplete phase).
     - **`review`/`in-progress` WITHOUT a state file** (bare BMAD / external) → apply the existing **status-mismatch guard** (`state-and-resume.md`): **ASK** — adopt as-is (leave at `review`, surface in the rollup) / run the thin Tier-A review on it in E5 / skip. Never blind-re-dev a human's work.
     - **`ready-for-dev`/`backlog`** → run the E5 loop body fresh.
4. **Base-readiness guard (git only — never a code read).** Epic mode branches off `{base}` and assumes `done` stories are in `{base}`.
   - Detect: a `done` story with a `{branch_prefix}{e}-{s}-*` branch **not merged into `{base}`** (`git branch --list "{branch_prefix}{e}-{s}-*"` then `git merge-base --is-ancestor <branch> {base}`).
   - On detect, **ASK**:
     - proceed off base — that story's work won't be in this epic's PR; only the remaining stories will; **or**
     - stop and merge it first, then re-run.
5. **Resolve the epic slug** (git only, deterministic — no LLM read).
   - Search the planning epics doc for epic `{e}`'s title (e.g. `find <planning_artifacts> -name 'epics*.md'` / `-name 'epic-{e}*.md'`, then read the `Epic {e}` heading); kebab-case it.
   - Fallback when absent: the first story-key's slug stem, else bare `epic-{e}`.
   - Carry it into E1 as `epic_slug` — stored so resume reuses it, never re-derives a different one.
6. **TEA triage is per story** — it is NOT run here, because the epic spans many risk levels; E5a delegates the `tea_triage` per story.
   - Record E0's decisions (`needs_project_context_bootstrap`, `epic_story_count`, the adopt verdicts, `epic_slug`, any `overrides`) for E1's `init --json`.
   - No commit, no state write — the anchor doesn't exist yet.

## E1 — Epic branch + anchor  *(orchestrator, git)*
- Ensure we are NOT on `{base}`.
- Create/checkout the **one** epic branch `{git.epic_branch_prefix}{e}-{slug}` (default `epic/{e}-{slug}`) off `{base}`.
- If it already exists (resume), check it out.
- Write the epic anchor: `python3 {skill-root}/scripts/state_update.py init --state-file {state}/epic/epic-{e}.yaml --json -` (refuses if it exists, so resume never re-inits — `started_at` + timing span all sessions).
  - The payload carries E0's decisions plus `story_key: epic-{e}`, `epic_num: {e}`, `branch`, `epic_slug`, `active_story: null`, `stories_landed: []`, `auto_decisions: []`, `uat_items: []`.
- Commit: `chore(epic-{e}): start auto-bmad epic pipeline`.

## E2 — Epic-start setup  *(conditional; reuses Phase 2)*
Runs **once** at the start of the epic — the epic's first story IS the epic start.

Two independently-gated sub-steps, exactly as Phase 2 — record each, mark E2 done once both resolve:
1. **Project-context bootstrap** *(only if `needs_project_context_bootstrap`)* → delegate **`generate-project-context`** (bootstrap fill). Commit `docs(project-context): bootstrap`.
2. **Epic test design** *(only if `tea.enabled`)* → delegate **`testarch-test-design`** (epic level) for epic `{e}`. Commit `test(epic-{e}): epic-level test design`.

> **Resume note:** if the epic was partially completed **outside** epic mode (no anchor existed before
> this run), E2 still records its `completed_phases` marker once run, so a later resume cannot re-run
> epic test design.

## E5 — Story loop (sequential) + Tier A  *(per story)*
For each story `{key}` in `epic_stories` order that is **not in the anchor's `stories_landed`** (already done by THIS run — see E0) and not E0-skipped:
- Set `active_story: {key}` on the epic anchor.
- **Capture `tier_a_base_sha = git rev-parse HEAD`** — the epic-branch tip *before* this story's first commit.
- Run the per-story phases (delegated exactly as `pipeline.md`), with the epic deltas below.

a. **Per-story state + triage.**
   - Delegate `tea_triage` (only if `tea.enabled`) to pick this story's TEA set.
   - Then `state_update.py init` the **per-story** `{state}/{key}.yaml` carrying the triage + `is_first/last_in_epic` + `tier_a_base_sha` — `tier_a_base_sha` recorded here so a resume reuses it, never re-derives it from a moved HEAD.
   - Commit `chore(story-{e}-{s}): start auto-bmad pipeline`.
   - *(Resume of an adopted in-flight story reuses its existing per-story state instead of init.)*
b. **Create-story** (Phase 3) → **`create-story`**. Commit `docs(story-{e}-{s}): create story context file`.
c. **Pre-dev TEA** (Phase 4, only if `atdd ∈ tea_selected`) → **`testarch-atdd`**. Commit `test(story-{e}-{s}): ATDD acceptance scaffolds (red)`.
d. **Dev-story** (Phase 5) → **`dev-story`** — the hard gate (runs tests, moves the story to `review`).
   - A `needs-human` (missing secret/service/manual step) **stops the whole epic** → report.
   - Commit `feat(story-{e}-{s}): <summary>` (+ `BREAKING CHANGE:` footer if reported).
e. **Post-dev TEA** (Phase 6, only if `automate ∈ tea_selected`) → **`testarch-automate`**. Commit `test(story-{e}-{s}): expand automated coverage`.
f. **Tier A — thin single review + fix (NO loop, NO convergence gate, NO halt).** This REPLACES the per-story Phase 7 loop.
   - **Build the story-scoped diff:** `review_loop.py prep-diff --project-root <project_root> --base <tier_a_base_sha>` — the epic-branch tip captured at this story's entry, so the diff is **only this story's commits**.
     - NOT `--base {base}`: in epic mode every story commits onto the one epic branch, so `--base {base}` would make story N's review the cumulative 1..N diff — fattening every story and breaking "thin".
     - The whole-epic diff is Tier B's job.
   - **Fan out only the `tier_a_lenses`** at the **primary** profile (`code_review_review`):
     - the **`code-review-auditor`** (the per-story AC check);
     - **+ `code-review-security`** if `security` is in `tier_a_lenses` and `code_review.security_review`.
     - **+ `code-review-verification-gap`** if `verification` is in `tier_a_lenses` and `code_review.verification_gap` — **NOT in the default `[auditor, security]` set** (Tier A stays thin; add `verification` explicitly to opt this story-scoped lens in).
     - NOT blind/edge — because their payoff is the whole-epic diff in Tier B.
   - **Delegate `code-review-triage`** (primary profile; `{R}=1`, only the auditor file in the lens list, `{security_file_hint}` if security ran, `{verification_file_hint}` if the verification-gap lens ran).
     - It persists the `### Review Findings` section to **`<story_file>`** verbatim, as in a per-story run.
     - Apply the **same reconciliation gate** (`review_findings.py … --story-file <story_file>`; one triage re-run on non-persist, else `needs-human`).
   - **Auto-resolve `[Review][Decision]` items with the triage's recommendation** — no halt to ask. Each open Decision carries a `Recommended resolutions:` channel from the triage (`delegation.md` → `code-review-triage`, auto-bmad-local). Apply it as if a human picked it — a direct findings-file write the orchestrator already owns, never a code read:
     - `fix:` → carry the direction into this story's fix pass via `{decisions}`.
     - `defer:` → re-tag `[Review][Decision]` → `[Review][Defer]` + log to `<impl>/deferred-work.md` under `## Deferred from: code review of {key}`.
     - `dismiss:` → check the bullet off as won't-fix.
     - **No recommendation for an item ⇒ default to `defer`** — never leave it open.
     - Record each on the **epic anchor**: `auto_decisions += "<title> [<sev>] → <channel>: <direction> (Tier A, {key})"` — for the E_final **Auto-decided** report section.
     - **Any Critical/High auto-decision sets epic `convergence_unverified: true`** — because a best-guess on a high-severity item must reach a human before merge; the epic PR then ships a draft and the item lands in **⚠️ Needs human**.
     - Tier-A decisions are resolved with **per-story context only** — noted in the report.
   - **Delegate one `code-review fix` pass** (`code_review_fix`) on the `[Review][Patch]` items **plus any `fix:`-channel resolved decisions** (via `{decisions}`).
     - Then **post-fix verify** (`review_loop.py post-fix`; one `retry-fix` allowed; `needs-human` stops the epic).
     - Commit `fix(story-{e}-{s}): address code review (thin)`.
     - If nothing fixable, commit `chore(story-{e}-{s}): code review passed (thin)` instead.
   - **Aggregate up to the epic anchor:**
     - If this story's post-fix non-deferred findings include any Critical/High (`open_crit_high > 0` or `open_severity.untagged > 0` from the gate-time capture), set epic `convergence_unverified: true`.
     - Record any blocker on the epic `blockers`.
     - No per-story draft decision — stories get no PR.
     - Record a thin marker `tier_a_review` in the per-story state — NOT `code_review_iterations`, which is Tier-B-only.
g. **Leave the story at `review`** — not `done`.
   - Optionally run the per-story trace advisory (Phase 7 tail) if `trace-advisory ∈ tea_selected` — non-blocking, reuses as-is.
   - Then, unless `skip uat`, delegate the **`uat`** entry (`delegation.md` → `uat`; `uat` profile; `<story_file>`) — read-only, returns this story's manual UAT one-liners (or the single not-applicable line).
h. **Land the story on the anchor in ONE write.** A single `state_update.py set` on the epic anchor that, in one patch:
   - extends `stories_landed += [{key}]`;
   - extends `uat_items += [<this story's UAT items, each prefixed `[{key}] `>]`;
   - advances `active_story`.
   - **Never two writes** — `stories_landed` / `uat_items` are anchor preserved-extras, so read-modify-write the full list for each in one patch (`_append` doesn't apply to them).
   - One write so a crash between them can't double-append a re-entered story's items — a re-entry isn't in `stories_landed` yet (E0 adopt).
   - Hand any retro notes to `state_update.py retro-append` (`retro-notes/epic-{e}.md`).

## E8a — Epic-end gates  *(conditional; reuses Phase 8 gates; runs BEFORE E_review)*
Only the **gates** run here — so their verdicts feed E_review and the epic report; the closing steps are E8b.

**Only if `tea.enabled`** (epic-level skills always on at the epic end):
- Delegate **`testarch-trace`** via `tea_epic` (the blocking gate, full depth), then **`testarch-nfr`** and **`testarch-test-review`** via `tea_epic_audit` (advisory).
- Capture each verdict; record `gate_decision`.
- **The trace `FAIL` interactive ask is SUPPRESSED in epic mode** — epic mode never halts for review.
- Run the gate to a verdict. Remediation may still run mechanically up to `tea.gate_max_iterations`: delegate **`testarch-automate`** at epic scope, commit `test(epic-{e}): close trace coverage gaps (gate iter {i})`, re-trace.
- Record the terminal verdict whatever it is:
  - `PASS`/`CONCERNS` → continue.
  - `FAIL`/`WAIVED` → a **finding surfaced in the epic report** — and it drives the draft predicate at E_final.
- Do **not** open `AskUserQuestion` here.

## E_review — Epic integration review (Tier B)  *(conditional; no halt — decisions auto-resolved)*
The heavy adversarial pass over the **whole epic diff**, run **once** after all stories land and the gates resolve.
- Gated by `code_review.epic_review` (default true; false ⇒ skip Tier B, rely on Tier A + E8a).
- This **relocates Phase 7 steps 1–4 to epic scope** — reuse them, do not fork, **except step 2 (decisions are auto-resolved, never asked) and step 4 (no halt — see below)**.
- Track `code_review_iterations` + `code_review_loop_done` on the epic anchor:
  - resume continues mid-loop; **or**
  - once the loop is done, proceeds to E8b — there is no halt to re-open.

1. **Roster — the per-story Phase 7 shape, at epic scope.**
   - Build the epic diff with `review_loop.py prep-diff --project-root <project_root> --base {base}` — everything the epic branch changed.
   - Fan out, per roster profile (`code_review_review` + the optional secondary/tertiary), the **`code-review-blind`**, **`code-review-edge`**, and **`code-review-auditor (epic)`** lenses (`3×R` total — identical roster shape to per-story Phase 7).
   - **`code-review-security` stays single-instance, off the `3×R` total, severity-gated** — exactly as per story.
   - **`code-review-verification-gap` stays single-instance too, off the `3×R` total** (gated by `code_review.verification_gap`) — exactly as per story.
   - All in parallel.
2. **Persist to the epic findings file.** Delegate **`code-review-triage (epic)`** (primary profile), handed all the lens files + (if security ran) `<security_path>` + (if the verification-gap lens ran) `<verification_path>` + the epic diff + the story-file list.
   - It writes the `### Review Findings` section to **`<impl>/epic-{e}-review-findings.md`**.
   - It copies `[Review][Defer]` items to `<impl>/deferred-work.md` under `## Deferred from: epic review of epic-{e}`.
   - Apply the **same reconciliation gate** as Phase 7 step 1 against that file (`review_findings.py --story-file <impl>/epic-{e}-review-findings.md … --story-key epic-{e}`; one triage re-run on non-persist, else `needs-human`).
3. **Loop + classify** as Phase 7 steps 2–3, against the epic findings file, with ONE epic substitution at step 2.

   **The step-2 substitution — auto-resolve open `[Review][Decision]` items with the triage's recommendation instead of asking** (same mechanism as Tier A, E5f):
   - `fix:` → `{decisions}`.
   - `defer:` → re-tag + ledger.
   - `dismiss:` → check off.
   - missing ⇒ default `defer`.
   - Record each on the epic anchor's `auto_decisions` (`(E_review, epic-{e})` context).
   - Set `convergence_unverified: true` for any Critical/High auto-decision.
   - **No `AskUserQuestion`** — epic mode never asks about review findings.

   **Then fix + drive the loop:**
   - Delegate **`code-review fix (epic)`** (`code_review_fix`) on the `[Review][Patch]` items **+ the `fix:`-channel resolved decisions**.
   - Commit `fix(epic-{e}): address code review (iter {i})`.
   - Drive the loop with:
     ```
     review_loop.py gate --findings-json - --iteration {i} --max-iterations {code_review.max_iterations} --lenses-failed {failed} --lenses-total {3×R}
     ```

   **Pass `--convergence-unverified true` whenever the epic anchor already holds the sticky flag** — any one of:
   - a Tier-A story aggregated a Crit/High (E5f); **or**
   - a Crit/High decision was just auto-resolved this pass (above); **or**
   - this iteration's security **or** verification-gap pass failed.

   The gate's `convergence_unverified` is **sticky** — it preserves a `true` even on a clean exit and never clears it (`review_loop.py`). So passing the flag here is what keeps the caveat from being overwritten when you persist the gate's output to state. Obey its `action`.
4. **No halt — auto-continue (epic mode runs unattended).** Unlike per-story Phase 7 step 4, E_review does **not** open `AskUserQuestion` on loop exit — because there is no human to pause for, and no external-change re-review (no human pause produced changes to review).

   **Pick the PR shape by the loop-exit `convergence_unverified`:**
   - **clean convergence** (`convergence_unverified=false`) → the epic ships a **normal** PR.
   - **capped-unconverged, lens-incomplete, or caveated** exit (`convergence_unverified=true`) → the epic ships a **draft** PR, with the open findings in the report + PR `Needs attention` checklist.
     - This flag is persisted by the loop gate, which preserves the sticky caveat carried in from a Tier-A aggregate or a Crit/High auto-decision (per step 3).

   **Then, either way:**
   - Record `hitl_halt: "auto-continued (epic — no halt)"` — the loop exit already set `code_review_loop_done: true`.
   - Proceed straight to E8b.
   - On resume, `code_review_loop_done: true` means "go to E8b", never "re-open a halt".
   - `convergence_unverified` drives the epic PR draft predicate (E_final).

**Large-diff strategy.**
- **Default — one high-context pass.** `prep-diff` writes the full epic diff.
- **Chunk when `diff_file` exceeds `code_review.epic_diff_chunk_threshold_lines`** — a deterministic `wc -l` check on the path, not a code read (`0` ⇒ never chunk). To chunk:
  - Run `prep-diff --base <story-base>` per landed story — each in its own temp dir.
  - Fan the roster per chunk, in parallel.
  - Then run **one JOINT `code-review-triage (epic)`** over ALL chunk outputs → the single epic findings file (dedup across chunk boundaries).
  - Gate `--lenses-total = 3×R` over the **logical** roster — a lens "failed" only if it failed for every chunk — so chunk count never violates the `{3,6,9}` validator.
- **The residual purely-cross-chunk discovery gap is accepted** — backstopped by the E8a trace gate + the human halt.

## E8b — Epic-end closing  *(conditional; reuses Phase 8 closing; runs AFTER E_review)*
So they capture the integration review's findings + fix commits (mirrors per-story Phase 7 → Phase 8 ordering). In order:
1. **Project context** → delegate **`generate-project-context`** (refresh) via `project_context`, fed the epic's accumulated `retro-notes/epic-{e}.md` + the deferred-work ledger.
2. **Reconcile missed completions** *(delegated — `deferred_reconcile`; runs BEFORE the archive)*: delegate the **`deferred-reconcile`** entry to mark any `open`/`partial` ledger item whose deferred work actually landed during the epic but went unmarked, so step 3 can archive it (same mechanics + skip condition as Phase 8 step 3). Record the marked count + evidence in the report.
3. **Archive resolved deferred work** *(orchestrator-direct — connective bookkeeping)*: trim `<impl>/deferred-work.md` via `deferred_ledger.py plan` → judge keep-vs-move → `deferred_ledger.py archive` into `<impl>/deferred-work-resolved.md` (same mechanics as Phase 8 step 4). Record `deferred_work_archived`.
4. **Retrospective** → delegate **`retrospective`** via `retrospective` for epic `{e}`, fed `retro-notes/epic-{e}.md`. Record any `planning_drift` (non-blocking; surface in the report).
Commit once: `docs(epic-{e}): gate, project context, deferred-work reconcile + archive, retrospective`. (Trace-gate remediation, if any in E8a, already committed separately.)

## E_final — Finalize  *(orchestrator, git)*
- Ensure everything is committed (no dirty tree).
- **UAT consolidation (delegated — `uat (epic)`).** Before writing the report:
  - **If the anchor's `uat_items` is non-empty,** delegate the **`uat (epic)`** entry (`delegation.md` → `uat (epic)`; `uat` profile).
    - Fill `{uat_items}` with the accumulated `[{key}] <item>` one-liners.
    - It composes ONE single-session checklist for the whole assembled epic (dedup + order across stories).
    - It is read-only — route its `Outcome` into the report's `uat` list key below; never read it as code.
  - **Skip the delegate if `uat_items` is empty** (no story produced a testable item) **or `skip uat`** — the **UAT** section then renders `(none)`.
  - Bracket with `state_update.py timing-start`/`timing-pause` on the epic anchor.
- **Write the epic report (before push):** `state_update.py report-section --epic --report-file <output_folder>/auto-bmad/reports/epic-{e}.md --state-file {state}/epic/epic-{e}.yaml --json -` (the epic-rollup template; `EPIC_REPORT_PAYLOAD_KEYS`). Pass `uat` = the consolidated single-session checklist (above) and `auto_decided` = the epic anchor's accumulated `auto_decisions` (Tier-A + E_review auto-resolutions) so the **Auto-decided (epic mode)** section lists every decision the run made without a human. Commit `docs(epic-{e}): pipeline report`.
- **git mode `remote`:** push the epic branch, open **one** PR, wait for CI (`ci_wait.py`), convert to draft if warranted — all per `git-and-pr.md` → "Epic mode". Capture `pr_url`, `ci_run_url`, `ci_status`. **git mode `local`** (or "stop" was chosen): leave the branch, no push/PR.
- **Draft predicate + batch flip.**
  - Evaluate the epic draft predicate deterministically (reads the aggregated anchor):
    ```
    state_plan.py --state-dir {state} --scope epic --story-key epic-{e} --finalize [--ci-status …] [--no-pr-draft]
    ```
  - **Clean completion** (`flip_bmad_status: true`) → batch-flip **every story in `stories_landed`** to `done`, one per story:
    ```
    story_plan.py --mark-done {key} --sprint-status <impl>/sprint-status.yaml --story-file <impl>/{key}.md
    ```
    - Skip a pre-existing `done` story.
    - **Never** flip an un-verified adopted `review` story.
  - **Caveated completion** → flip **none** — the whole epic stays at `review` until a human acts (`git-and-pr.md` → the caveated-epic mirror).
  - Mark the epic anchor `status: done`.
  - Commit the anchor→done write + the flips together: `chore(epic-{e}): finalize (mark done + BMAD status)`; push.
- **Merge prompt** (clean completion, `git.offer_merge`, mode `remote`, PR opened, no `skip merge-prompt`): ask + execute per `git-and-pr.md` → "Merging the PR".

## Resume
- **Find the target.** Epic resume reads the epic anchor via `state_plan.py --state-dir {state} --scope epic` — an `epic-{e}.yaml` with `status != done` is the resume target.
- **Enter at the first unresolved E-step** in the anchor's `completed_phases`.
- **Resolve intra-story granularity for the `active_story`.** Read its per-story `{state}/{key}.yaml` (`--story-key {key}`).
  - The anchor owns *which story / which E-step*.
  - The per-story file owns *which phase within the story*.
- **Skip stories already in `stories_landed`** (E0 adopt) — a resume never re-enters a story this run already landed, even though it sits at `review` with a complete state file.
- **E_review resume:**
  - mid-loop → resume the loop (`code_review_iterations`); **or**
  - once `code_review_loop_done` → simply proceed to E8b.
  - There is no halt to re-open — epic mode auto-continues; Phase 7's re-open-the-halt resume path does not apply.
- **A bare `/auto-bmad` (no `epic`) whose resolved target story is owned by an in-flight epic anchor hard-stops, redirecting to `/auto-bmad epic --epic {e}`** (SKILL.md) — because finishing one story alone would split the epic's single PR.
