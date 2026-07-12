# Per-story pipeline

The orchestrator runs these phases **in order** for a single story. Each phase runs this sequence:
1. Check its condition.
2. Delegate the named **`delegation.md` entry** (the hyphenated name in **bold backticks** below, e.g. **`create-story`**) to the profile `phase_profiles` assigns to the phase.
   - Each phase also names its `phase_profiles` **key** — the underscored form, e.g. `→ create_story`.
   - Resolve key → profile → model+effort via config.
   - The mapping lives only in config — **never** hardcode a profile name here.
   - `delegation.md` owns the exact `/bmad-*` command + prompt.
   - Spawn it for the current host/tier per `delegation-runtime.md`.
3. Read the result.
   - `blocked`/`needs-human` → stop and report.
   - Otherwise → update the state file via `state_update.py` (`phase-done --phase N` with the folded `set` patch; retro notes via `retro-append`; timing via the brackets below — see `state-and-resume.md`).
4. **Commit the state update in the same single commit as the phase's artifacts.**

**Which phases enter `completed_phases`:**
- A phase whose own gates made it a no-op → still enters `completed_phases` (recorded as skipped).
- A phase excluded by an override window → does **not** enter (`overrides.md`).
- **Never** make a standalone state-only commit (see `git-and-pr.md` → "Commits").

**Commit messages:** Each phase below gives its `Commit:` **subject only**. Every commit also carries a **required body** (and a footer when relevant), built from that phase's own facts, per `git-and-pr.md` → "Message body & footer".

**Timing:** Record timing — never with hand-rolled `date` arithmetic. The script owns the clock math (`state-and-resume.md` → timing fields).
- Bracket each phase with `python3 {skill-root}/scripts/state_update.py timing-start --state-file <state>` just before delegating.
- Close the bracket with `… timing-pause …` when it returns — just before the state write + commit.
- **Don't count time spent waiting on the user.** If the phase opens an `AskUserQuestion` (e.g. the Phase 7 decision asks or the HITL halt), invert the bracket — `timing-pause` before the prompt, `timing-start` after — so the wait lands on human/idle, not active.
- A `dropped_anchor: true` from `timing-start` means a prior session crashed mid-bracket; the dangling interval is discarded conservatively — expected on resume, not an error.

**Exception — Phase 0:** the state file does not exist until Phase 1's `init`, and every `state_update.py` subcommand except `init` refuses a missing file.
- Phase 0 is never bracketed and never writes state — its triage time goes untracked (accepted).
- Every Phase-0 "record …" decision is **carried into Phase 1's `init --json` payload**, not written during Phase 0.

**Git/PR work is orchestrator-owned, not delegated** — see `git-and-pr.md` → "Ownership" for the full list.
- The git-only phases below (0 preflight, 1 branch, 9 finalize) carry no `phase_profiles` key.
- Only their non-git parts (e.g. Phase 0's TEA triage) are delegated.

Placeholders (`{e}`/`{s}`, `{key}`, `{slug}`, `<impl>`, `<story_file>`, …) are defined once in `delegation.md` — the canonical glossary.

---

## Phase 0 — Preflight & triage  *(git preflight: orchestrator; TEA triage: `tea_triage`)*
Runs during Step 1 of the SKILL procedure (before any commit).
- **Probe discipline:**
  - All orchestrator-run Phase 0 probes go through **one `scripts/preflight.py` call** — git preflight, project-context probe, CI presence, required-skills check, and (first-run) framework detection come back as a single JSON object.
  - Read its fields — never re-derive them in shell.
  - Any probe that stays hand-rolled (here or in later phases) uses `find`/`test`/Python, **never a bare glob** — because unmatched globs abort under zsh/fish (`nomatch` ⇒ exit 1).
  - Probe by real on-disk names (state `{key}.yaml`, story `{key}.md` — no `story-{e}-{s}` prefix).
  - State-file enumeration stays in `scripts/state_plan.py` — the deterministic reader; call it, don't re-derive.
- Verify required skills exist for the selected path (the preflight JSON's `skills.missing`, via `--require-skills` + `--skills-dirs`). Missing → hard-stop.
- Git preflight (**orchestrator runs this directly**). The normative rules live in `git-and-pr.md` → "Mode detection (Phase 0)"; `preflight.py` implements them.
  - Read the preflight JSON's `git` block — `is_repo`, `tree_clean`/`dirty_files_count`, `current_branch`, `base_branch`, `mode` (`remote`|`local`) — plus the top-level `hard_stop`/`hard_stop_reasons`.
  - Not a repo, or dirty tree off the expected story branch → hard-stop.
  - On a resume, pass `--expected-branch` so in-flight dirt on the story branch is allowed.
- **Config drift heal + review (orchestrator; all hosts):** reconcile the runtime `config.yaml` against the shipped assets — both the `profiles`/`phase_profiles` blocks AND the constant-default **setup-block** keys (`delegation`/`tea`/`git`/`code_review`):
  ```
  python3 {skill-root}/scripts/config_plan.py --check --config <output_folder>/auto-bmad/config.yaml
  ```
  (the shipped `assets/agents/profiles.yaml`, `assets/config-defaults.yaml`, and `assets/module.yaml` resolve relative to the script).
  - **`status: fresh`** (exit 0) → nothing to do; continue.
  - **`status: drift`** (exit 1) splits by the **pause predicate** — did an update ship **new config the heal will ADD**: any of `missing_profiles`, `missing_phase_profiles`, or `missing_setup` is non-empty.
    - **Reviewable drift** (predicate true — a new profile, phase mapping, or setting) → **pre-run pause** (below), UNLESS `skip config-pause` is in effect for this run (`overrides.md`). *Epic mode handles this once at E0 — `epic-pipeline.md`; the per-story rule here is for a single-story run.*
    - **No reviewable drift** (predicate false — only an older `profiles_source_version` and/or `manual_review` items) → **auto-apply** (`--apply`) to restamp; surface any `manual_review` in the report; continue. No pause.
    - **Why `manual_review` is NOT in the predicate:** the heal never auto-writes it, so it would never self-clear — pausing on it would re-fire on **every** run (a nag). It rides in the report + the drift report instead, and the user fixes it via `reset-defaults`.
  - **Pre-run pause** — the ONE deliberate exception to "Phase 0 doesn't halt", and only on reviewable drift:
    - Open an `AskUserQuestion` showing the **drift report** (rendering below), read straight from the `--check` JSON — **never read code**.
    - Options: **Apply defaults & continue** / **Stop — let me edit `config.yaml` first**.
      - **Apply & continue** → re-run with `--apply`; print one line — `Applied — config.yaml now matches v<module_version>; continuing.` — and proceed.
      - **Stop** → print the config path + the exact re-invoke command, note that the heal is **append-only so your edits survive** (set a value / add a profile block by hand and the heal will not overwrite it), then **stop**. Phase 0 writes no state (the Phase 0 exception), so this is a clean pre-run stop — not a resumable halt; the user edits and re-invokes.
        - **Caveat for *profile* (model/effort) edits on `custom-subagents` hosts:** a *setting* edit takes effect on the next run, but a *profile* edit re-renders the agent file, which isn't invokable until a full tool restart (`delegation-runtime.md` → "Newly-rendered agents need a process restart"). Say so, so the user restarts before re-invoking — otherwise the run silently uses the old model.
  - **The additive heal** (`--apply`, on whichever path reaches it) appends only the MISSING keys — never overwriting a user value — and restamps `profiles_source_version`. Run it **before** the provisioning-freshness check below, so a re-seeded profile *value* is then caught there as a stale agent file.
  - `manual_review` items (a sub-key missing from a profile that already exists) are auto-written by neither path — **surfaced at preflight** (in the pause's drift report, or the live echo below); the one-shot fix is `reset-defaults`.
  - **Surfacing is preflight-only** — the report's section template has no config-heal heading (and its report `--json` rejects unknown keys), so the heal's effect is shown **at preflight**, not persisted as a report field: the **paused** path already showed the full drift report in the `AskUserQuestion`; the **auto-apply** paths get the non-blocking **live echo** below.
  - **Non-blocking live echo** — on the **auto-apply** paths only (version/`manual_review`-only drift, or `skip config-pause` bypass), where the user did NOT see the pause: when `--apply`'s `added_setup` is non-empty, show a brief, non-blocking block in the preflight echo, then continue.
    - The heal is behaviour-neutral, so there is nothing to approve; **never** open an `AskUserQuestion` on these paths.
    - Read the lists straight from the `--apply` JSON — don't recompute or read code. Render:
      - a **lead line** — `config.yaml updated to match v<module_version>`;
      - *Added N new setting(s) (defaults; behaviour unchanged)* — one `path = value` per `added_setup` entry;
      - *Kept your M customisation(s)* — one `path = value  (default <default>)` per `kept_setup` entry (omit this list entirely when `kept_setup` is empty);
      - a **closer line** — `→ continuing pipeline…`.
    - If `added_setup` is empty, show nothing. (`reseeded_*` reseeds and `manual_review` are in the `--apply` JSON for the orchestrator; they are not persisted to the report.)
- **Drift report rendering** (shared by the pre-run pause above and the `config-check` command — `state-and-resume.md`). Read straight from the `config_plan.py --check` JSON; render the two sides, omitting any sub-list that's empty and any side with nothing:
  - **New since v<config> (would be added):**
    - *New profiles* — one `name — <summary>` per `missing_profiles` (summary from `missing_profile_summaries`).
    - *New phase mappings* — one `phase → profile` per `missing_phase_profiles`.
    - *New settings* — one `path = value` per `added_setup`.
    - *Profile sub-keys you could set* — one `profile.key` per `manual_review` (not auto-written).
  - **Your customisations (preserved by the append-only heal):**
    - *Profile retunes* — one `profile.key = value  (default <default>)` per `customized_profiles` (model/effort tiers; persona strings are excluded).
    - *Custom profiles* — one `name` per `custom_profiles`.
    - *Remapped phases* — one `phase = profile  (default <default>)` per `customized_phase_profiles`.
    - *Settings* — one `path = value  (default <default>)` per `kept_setup`.
  - Every value here is short (model/effort tiers, setting scalars, profile/phase names) — render inline; persona strings are excluded from `customized_profiles`, so there is nothing long to truncate.
- **Provisioning freshness (custom-subagents hosts):** run `render-agents.py --check`. See `delegation-runtime.md` → "Resolving host & mode".
  - Delegate agents missing or stale (module updated / profiles edited) → auto-reprovision and note it in the preflight echo + final report.
  - Not a human stop.
- **Project-context probe (orchestrator):** read the preflight JSON's `project_context.found` (pass `<output_folder>` from `_bmad/bmm/config.yaml` as `--output-folder`; discovery internals live in `preflight.py`).
  - `found: false` → record `needs_project_context_bootstrap: true`; Phase 2 will bootstrap it before create-story.
  - `found: true` → record the flag `false` (Phase 8 still refreshes it on the last story of the epic).
  - Like every Phase-0 decision, this rides in Phase 1's `init --json` (no state file exists yet).
- **Triage (only if `tea.enabled`; delegated to `tea_triage`):**
  - Classify the story `low | med | high` and choose the per-story TEA set using `tea-policy.md`.
  - Record `tea_risk` (`low|med|high`) and `tea_selected` (e.g. `[atdd, automate]`, or `[]` for trivial).
  - Record `epic_story_count` and `stories_after_in_epic` (both from the sprint-status read that set `is_first/last_in_epic`).
  - When `tea-policy.md` §3's conditions all hold, add `trace-advisory` to `tea_selected` — Phase 7's tail runs it. The conditions: high risk, **not within the epic's last `skip_last_stories`** (i.e. `stories_after_in_epic >= skip_last_stories`, default 3), and a long-enough epic.
- No commit (nothing changed yet).
- **No state writes** (no state file exists yet — see the Phase 0 exception in the header): carry the decisions (`needs_project_context_bootstrap`, `tea_risk`, `tea_selected`, `epic_story_count`, `stories_after_in_epic`, any invocation `overrides`) forward into Phase 1's `init --json` payload.

## Phase 1 — Branch  *(orchestrator)*
- Ensure we are NOT on the base branch. Create/checkout `{branch_prefix}{e}-{s}-{slug}` (default `story/{e}-{s}-{slug}`). If the branch already exists (resume), check it out.
- Write the initial state file with `python3 {skill-root}/scripts/state_update.py init --state-file <state> --json -`.
  - It refuses (exit 1) if the file already exists — so a **resume** can never re-init, and `started_at`/`active_seconds` span all sessions.
  - The `init` payload is where every Phase-0 decision lands (the fields listed at the end of Phase 0).
  - Commit it: `chore(story-{e}-{s}): start auto-bmad pipeline`.

## Phase 2 — Epic-start setup  *(conditional; two independently-gated sub-steps)*
Two sub-steps that each carry their own gate; either, both, or neither may run. Execute them in the order below.
- **Phase 2 enters `completed_phases` only after BOTH gates have resolved** — each sub-step ran, or its gate was false.
- Never enter `completed_phases` in sub-step 1's folded state write — so a crash between the sub-steps re-enters Phase 2 on resume.
- On that resume, sub-step 1 won't double-run — its flag already flipped `false`.
- If both gates were false, Phase 2 is a no-op, recorded as skipped.

1. **Project-context bootstrap** *(only if `needs_project_context_bootstrap` from Phase 0)* → `project_context`
   - Delegate the **`generate-project-context`** entry with its Phase 2 `{bootstrap_intent}` fill — write `project-context.md` from scratch rather than refresh an existing file (`delegation.md`).
   - Commit: `docs(project-context): bootstrap`.
   - Flip `needs_project_context_bootstrap` to `false` in state so re-invocations don't double-run.
   - Gate is independent of `is_first_in_epic` / `tea.enabled`.
2. **Epic test design** *(only if `is_first_in_epic` AND `tea.enabled`)* → `tea_epic`
   - Delegate the **`testarch-test-design`** entry (epic level) for epic `{e}`.
   - Commit: `test(epic-{e}): epic-level test design`.

## Phase 3 — Create story  → `create_story`
- Delegate the **`create-story`** entry for story {e}-{s}. The skill self-validates against its checklist and auto-fixes; do NOT add a separate validate pass.
- The delegation is fed this epic's retro-notes + the deferred-work ledger; for the **first story of an epic** (no epic-{e} notes yet) it is instead fed the prior epic's retrospective forward sections (see `delegation.md` → `create-story`).
- Capture any open questions the skill saved → retro notes + report.
- Commit: `docs(story-{e}-{s}): create story context file`.

## Phase 4 — Pre-dev TEA  *(only if `tea.enabled` AND `atdd ∈ tea_selected`)*  → `tea_per_story`
- Delegate the **`testarch-atdd`** entry with `<story_file>`.
- Commit: `test(story-{e}-{s}): ATDD acceptance scaffolds (red)`.

## Phase 5 — Dev story  → `dev_story`
- Delegate the **`dev-story`** entry with `<story_file>`. Fully autonomous; it runs tests and moves the story to `review`.
- Capture deviations / deferred work / decisions → retro notes (these feed the commit body); if the agent reports a **breaking change**, capture it → the `feat` commit's `BREAKING CHANGE:` footer (see `git-and-pr.md` → Commits).
- Commit: `feat(story-{e}-{s}): <one-line summary from the agent>`. (If the dev agent reports it cannot complete — missing secret, external service, manual step — that is `needs-human`: stop and report.)
- **Scripted sprint-status write-back (REQUIRED — do not rely on the LLM alone).** `bmad-dev-story` step 9 *asks* the agent to sync `sprint-status.yaml` → `review`, but that LLM-only write-back is the root cause of the recurring Epic 12/13 drift (story file at `Status: review` while `sprint-status.yaml` stays `ready-for-dev`). After the feat commit, the **orchestrator** MUST flip both BMAD sources with the same atomic helper Phase 9 uses for `done`:
  ```
  python3 {skill-root}/scripts/story_plan.py --mark-status {key} --to review \
    --sprint-status <impl>/sprint-status.yaml --story-file <impl>/{key}.md
  ```
  Fold the resulting sprint-status / story-file touches into the feat commit when still unstaged, or amend only under the amend rules in `git-and-pr.md`. Never skip this call because the delegate "said" it already updated the file — verify with the script (idempotent when already at `review`).

## Phase 6 — Post-dev TEA  *(only if `tea.enabled` AND `automate ∈ tea_selected`)*  → `tea_per_story`
- Delegate the **`testarch-automate`** entry with `<story_file>`.
- Commit: `test(story-{e}-{s}): expand automated coverage`.

## Phase 7 — Code-review loop

Runs 1–`code_review.max_iterations` review passes (default 2), then ends at a human-in-the-loop halt (step 4) — unless step 4's skip gate fires.

**How many passes:**
- Always **≥ 2 passes**, with two exceptions: the first pass is *perfectly clean* (0 non-deferred findings AND every lens ran), or `max_iterations: 1` caps it at one.
- A `max_iterations: 1` cap is explicit consent to a single-pass review; that lone pass is judged by the **same convergence rules as any final iteration** (step 3).
- The step-4 halt can **extend** the loop, one iteration at a time.

**Authority & state:**
- Convergence is defined in step 3. Every continue/exit/halt decision is the `review_loop.py gate` decision table in step 3 — **call the script and obey it; never re-derive the rules.**
- Track `code_review_iterations` and `code_review_loop_done` in state. Resume continues mid-loop, or re-opens the halt once the loop is done.

For iteration `i` (1-based):
1. **Reviewer roster — every iteration runs the same parallel roster.** Build it from `phase_profiles`:
   - `code_review_review` (primary) — always.
   - `code_review_review_secondary` and `code_review_review_tertiary` — each only when it maps to a non-blank profile (a blank/absent value disables that slot).
   - With `R` = roster size (1–3), each iteration fans out the three lenses once **per roster profile** — 3, 6, or 9 lens delegates — and `3×R` feeds the gate's `--lenses-total`.
   - The single triage delegate always runs at the **primary** profile.

   **Dedicated security review (auto-bmad-local; only if `code_review.security_review`, default `true` — absent ⇒ `true`).** It is `delegation.md` → `code-review-security`.
   - Each iteration also fans out **one** `code-review-security` delegate — **single-instance** (NOT per roster profile) at the `code_review_security` profile (blank ⇒ the primary `code_review_review` profile).
   - It is **off** the `3×R` `--lenses-total` — because its findings reach convergence through the findings-severity channel (a security Critical/High lands in `open_crit_high`), so it needs no gate-math change.

   **Run the code-review fan-out (3×R lens delegates + one triage, not one skill call).** A delegate can't spawn `/bmad-code-review`'s three internal review subagents (no nested subagents), so the orchestrator hoists the fan-out (`delegation.md` → `code-review (fan-out)`). It passes the diff and findings **by path, never by content**, so it inspects no code.
   a. **Build the diff (orchestrator, tool call).** Run `python3 {skill-root}/scripts/review_loop.py prep-diff --project-root <project_root> --base {git.base_branch}`.
      - It writes the branch diff (exclude pathspecs baked into the script) to `diff_file` inside a throwaway `review_tmp` (outside the work tree, never committed).
      - It reserves the per-reviewer lens-output paths (`lens_paths.{primary|secondary|tertiary}.{blind|edge|auditor}` — use only the roster's slots).
      - Hand the returned paths to the lenses and triage below.
      - `diff_empty` true → there is nothing to review: delete `review_tmp` and treat it as a 0-finding pass through step 3. For the gate's `--findings-json`, run `review_findings.py --story-file <story_file> --expect-min 0`; gate with `--lenses-failed 0 --lenses-total {3×R}` — with no failed lenses it is a genuine clean pass, table row 2.
   b. **Fan out the 3×R lenses** — for EACH roster profile, the **`code-review-blind`**, **`code-review-edge`**, and **`code-review-auditor`** entries at that profile.
      - Each lens writes to its own slot's temp file (the primary's lenses → the `primary` paths, and so on).
      - Spawn them **all in parallel** on every host (across reviewers too): Claude Code via parallel Agent calls; Codex by naming all the agents in one request (it spawns concurrently and consolidates); opencode via concurrent task delegations — `delegation-runtime.md`.
      - **CLI-routed lenses (`cli_phases`) run in parallel too** — background OS processes, not in-tool subagents (`delegation-runtime.md`).
      - Collect each lens's reported path + count; note any empty/failed layer — the failed-lens count spans ALL reviewers.
      - **Plus, if `code_review.security_review` (default true): spawn the single `code-review-security` delegate in the same parallel batch**, writing to `<security_path>` (from prep-diff). Track its run separately from the lens count:
        - A successful pass that finds **0** issues is a clean security pass (NOT a failure).
        - Only a genuine delegate failure (errored / no parseable output) is a security-pass failure — it does **not** add to `--lenses-failed`, but feeds the convergence-unverified clause in step 3.
   c. **Capture the persistence baseline, then triage + persist.**
      - First run `python3 {skill-root}/scripts/review_findings.py --story-file <story_file>` and note its `total` as `{B}` — the section's bullet count BEFORE this pass (0 on a fresh story; on iteration ≥ 2 it holds the earlier passes' bullets). The reconciliation gate below subtracts it, so a prior pass's bullets can never vacuously satisfy this pass's persistence claim.
      - Then delegate the **`code-review-triage`** entry (always the primary profile), handed ALL the roster's lens paths (3×R files, grouped by reviewer) + (if security_review on) `<security_path>` via `{security_file_hint}` + `<diff_file>` + `<story_file>` + the failed-layer list. The triage delegate:
        - dedupes (across reviewers and the security pass — parallel models overlap heavily);
        - maps security severities;
        - applies the Low keep/drop test;
        - classifies, and writes the `### Review Findings` section (`[Review][Patch]` / `[Review][Decision]` / `[Review][Defer]`) plus the deferral ledger;
        - returns the verdict + counts.
      - It is the **only** code-review delegate that writes findings.

   **Verify persistence (reconciliation gate) — before trusting the result.** The triage delegate is the one that persists; never take its chat counts on faith — because a mis-bound write leaves the section empty while chat claims findings.
   - After it returns, run `python3 {skill-root}/scripts/review_findings.py --story-file <story_file> --expect-min {N} --baseline {B} --deferred-work-file <impl>/deferred-work.md --story-key {key}`.
     - `{N}` is the reviewer's reported `Findings persisted:` count (fall back to its total raised-findings count if that line is missing).
     - `{B}` is step 1c's pre-triage baseline.
     - The gate passes only if the section gained ≥ `{N}` bullets THIS pass.
   - The same gate confirms the `### Review Findings` section persisted AND that every `[Review][Defer]` finding reached the durable ledger (`deferred_work_logged >=` the story's defer count).
   - `reconciled: true` (exit 0) → proceed.
     - Use **the file's** counts AND severities (`open_patch` / `open_decision` / `open_nondeferred` / `open_crit_high` / `open_severity`), not the chat report, to drive step 2 (step 3 re-captures once the decisions are recorded).
     - Treat any `open_severity.untagged` finding as Critical/High (conservative).
     - Once the gate passes, delete `<review_tmp>` (`rm -rf`) — the lens outputs are spent.
   - `reconciled: false` (exit 1 — section absent, fewer bullets than claimed, or defer findings not logged to the ledger) → the findings did NOT persist.
     - **Re-run the `code-review-triage` entry once more this iteration**, with the spec binding and deferral-ledger reinforced — the lens findings are still on disk, so do NOT re-run the lenses (this retry does not consume a loop iteration).
     - If it still won't persist, **stop and report `needs-human`** ("code-review did not persist findings to `<story_file>`") rather than running the fix loop against an empty section.
     - On a `needs-human` exit keep `<review_tmp>` and surface its path for debugging.
2. **Resolve `[Review][Decision]` items first — ASK the user.** The reviewer flagged these as needing a human — never auto-guess them.
   - If this pass wrote any open `[Review][Decision]` items, batch them into `AskUserQuestion` **before** the fix: at most 4 findings per call (the tool's limit) — loop with more calls if there are >4.
   - Present each finding's title, detail, and the reviewer's suggested options; the user picks the fix direction (or **defer** / **dismiss**).
   - Record each resolution in state (`open_questions`/`deferred_work`) + the report.
   - Fix-direction choices flow into the fix in step 3.
   - **defer and dismiss the orchestrator records in `<story_file>` itself — a direct write** (the fix delegate never touches unresolved Decision items):
     - For each user **defer**, re-tag the bullet `[Review][Decision]` → `[Review][Defer]` and log it to `deferred_work`.
     - For each **dismiss**, check the bullet off as won't-fix.
   - For each item the user **defers**, also append it (with their one-line reason) to the durable cross-story ledger `<impl>/deferred-work.md` under this story's `## Deferred from: code review of {key} (<date>)` heading — the same file the `code-review-triage` delegate logs its own `[Review][Defer]` findings to (a direct orchestrator write).
3. **Fix, then classify the pass.**

   **Capture the gate input first.** Re-run `review_findings.py` (same flags as step 1's gate) now that step 2's resolutions are recorded in `<story_file>`.
   - This post-decision, PRE-fix JSON drives the counts below and the loop gate — so a user-deferred Critical/High no longer counts as open.
   - If step 2 didn't run (no open Decision items), step 1's reconciliation JSON is identical; reuse it.
   - There is no mid-iteration state capsule — a crash anywhere inside an iteration resumes by re-running the whole iteration from step 1 (`state-and-resume.md` → resume; one redundant review pass is the cost of a rare crash).

   **Read the verdict and counts.**
   - Read the verdict (Approve / Changes Requested / Blocked) from the triage report.
   - The Critical/High/Med/Low counts come from **the file** (this capture's `open_severity` / `open_crit_high`), never the chat counts.

   **Fix.**
   - Fixable work present — `[Review][Patch]` items, or `[Review][Decision]` items the user just resolved to fix → delegate the fix via the **`code-review fix`** entry (profile `code_review_fix`), focused on those items, implementing each resolved decision in its chosen direction and checking it off, then commit `fix(story-{e}-{s}): address code review (iter {i})`.
   - **No fixable findings** → instead commit the checkpoint `chore(story-{e}-{s}): code review passed (iter {i})`.

   **Post-fix verification — after EVERY fix delegate, before the commit.** Re-run `review_findings.py` (same flags as step 1's gate) and pipe its JSON to `python3 {skill-root}/scripts/review_loop.py post-fix --findings-json -` (add `--retry-used` on the second attempt). Obey its `action`:
   - `proceed` → carry on.
   - `retry-fix` → re-delegate the **`code-review fix`** entry once on the still-open items (this does not consume a loop iteration), then re-verify with `--retry-used`.
   - `needs-human` → stop and report ("fix pass left open findings in `<story_file>`").

   **Classify the pass by its non-deferred findings.** A pass's **non-deferred findings** are every finding it raised that was NOT routed to `[Review][Defer]` — the `[Review][Patch]` items plus the `[Review][Decision]` items the user chose to fix.
   - Use **the file's** counts and severities from the gate-time capture above, not the chat report.
   - A *deferred* Critical/High is a logged human decision and does not block convergence.

   The pass **converged** iff BOTH hold:
   - None of its non-deferred findings were Critical or High — file-derived: `open_crit_high == 0` AND `open_severity.untagged == 0` at gate time.
   - It found-and-fixed **either ≤ 3 non-deferred findings, or only Low-severity ones** (`open_severity.medium == 0`; no count cap on a Low-only pass).

   **Drive the loop — tool call, not prose.** Pipe the gate-time `review_findings.py` JSON to the gate. Use the **post-decision, PRE-fix** capture from the top of this step, never the post-fix re-run.
   ```
   python3 {skill-root}/scripts/review_loop.py gate --findings-json - --iteration {i} \
     --max-iterations {cap} --lenses-failed {failed-layer count from step 1b} --lenses-total {3×R}
   ```
   - Add `--convergence-unverified true` in either case:
     - state already holds the sticky flag; or
     - THIS iteration's `code-review-security` delegate failed to run — a genuine failure, never a clean 0-finding pass.
   - The security trigger is a **per-iteration** signal: a transient earlier security failure that recovered by the exit pass does NOT force a draft; only a failed security pass on the exit-deciding iteration does.
   - `{cap}` is `code_review.max_iterations` — except on a **user-extended iteration** (granted at the step-4 halt, recognizable as `i >` the config cap), where `{cap} = {i}`. Each extension grants exactly one more, always-final, iteration, judged by the final-iteration rows 6/7/9.

   **OBEY the gate's `action` and `convergence_unverified`:**
   - `continue` → run iteration `i+1` (same roster).
   - `exit-clean`/`exit-unconverged` → exit the loop, persist `convergence_unverified` to state (`true` ⇒ Phase 9 ships a **draft** — `git-and-pr.md` draft predicate), and enter step 4 (whose skip gate reads that same flag).
   - `needs-human` → stop and report `needs-human` ("code review incomplete — 0/M lenses produced findings"), keeping `<review_tmp>` for debugging.

   Carry the gate's `reason` (it includes any "incomplete review (only N/M lenses ran)" caveat) into the report and the step-4 halt summary.

   **The normative contract is `review_loop.py`** — its docstring carries the decision table and its `--self-test` pins every row; the copy below is a courtesy reference only (`M` = `--lenses-total`). On any discrepancy the script's JSON wins — obey it, never re-derive from this table:

   | # | i | lenses-failed | findings | cap (i==max)? | action | convergence_unverified |
   |---|---|---|---|---|---|---|
   | 1 | any | M (all) | — | — | needs-human ("0/M lenses produced findings") | input value (unchanged) |
   | 2 | 1 | 0 | clean | — | exit-clean (only first-pass early exit) | false (or input true) |
   | 3 | 1 | 0 | not clean | no | continue (second opinion mandatory — a Low-only first pass included) | false/input |
   | 4 | 1 | 1..M-1 | any (even 0 findings — untrustworthy) | no | continue | false/input |
   | 5 | 1 | any<M | any | yes (max==1) | → rows 6/7/9 (the capped first pass follows the final-iteration rules — converged + all lenses exits clean) | per row |
   | 6 | ≥2 | 0 | converged | — | exit-clean | false/input |
   | 7 | ≥2 | 1..M-1 | converged | — | exit-unconverged (reason notes "incomplete review N/M lenses") | true |
   | 8 | ≥2 | <M | not converged | no | continue | false/input |
   | 9 | ≥2 | <M | not converged | yes | exit-unconverged | true |

   On any exit, set `code_review_loop_done: true`, then go to step 4.
4. **HITL halt — ASK the user on every loop exit, except a clean convergence.**

   **Skip gate (evaluate first, at step entry).** Read the **loop-exit** `convergence_unverified` value — read it *before* any re-review machinery below runs, since that machinery also writes this flag.
   - `convergence_unverified == true` (capped-unconverged or incomplete-lens) → the gate **never** skips; always halt (go to "The halt" below).
   - `convergence_unverified == false` (the loop converged cleanly — a perfectly-clean first pass, a converged `max_iterations: 1` single pass, or an `i ≥ 2` converged exit) → **skip the halt** (do **not** open `AskUserQuestion`):
     - `log` one line: "review converged cleanly — Phase 7 HITL halt skipped".
     - Record `hitl_halt: skipped (clean convergence)` in state + the report's Code-review line.
     - Proceed as the **Continue** path **with no external-change check** — there was no human pause since the last review pass (an extension commits any pause changes before re-entering; otherwise there was no pause), so there is nothing to detect — straight to the Phase 7 tail.
   - There is **no config knob** for this: a clean convergence always auto-continues (a stale `code_review.skip_hitl_on_clean_convergence` key in a config is ignored).

   **The halt (the loop did not converge cleanly — converged-but-caveated, or capped).** The loop always ends here.
   - **Summarize:** iterations run; each pass's verdict + `Critical N / High N / Medium N / Low N` counts; the total non-deferred findings found-and-fixed; whether the loop converged or hit the cap unconverged (`convergence_unverified`).
   - **Recommend an external review while the pipeline is paused** — a human, another model/AI, or a separate tool, reviewing the branch's changes — because even a converged exit's final fix pass is itself unverified.
   - Then ask (`AskUserQuestion`) with these options:

   **Option — "Run another review iteration"** *(recommended when the last pass was unconverged)*. Extend the loop past the cap by exactly one full iteration, same roster.
   - First run the same git-only new-changes check as **Continue** and commit anything found (`fix(story-{e}-{s}): external review changes`) — the extended pass reviews those commits as part of the branch diff, so no single-shot re-review runs here (and none is consumed).
   - Set `code_review_loop_done: false`; reset `hitl_halt: null`.
   - **Clear `convergence_unverified` to `false` in state** — the loop exit set it, but this pass IS its re-verification, so it must not feed back in as the gate's sticky input.
   - Re-enter the loop at iteration `i+1`, gating with `--max-iterations {i+1}` (step 3's extended `{cap}`; the extended pass is always final).
   - Outcome: a converged full-lens extension exits clean (the skip gate then auto-continues; Phase 9 ships a normal PR); an unconverged or lens-incomplete one re-opens this halt (the user may extend again — one iteration per ask — or continue).
   - Note every extension in the report's Code-review line (`+N user-extended iteration(s)`).

   **Option — "Continue"** *(recommended otherwise)*. Resume the pipeline.
   - **First check (git only — the orchestrator never reads the code) for new changes since the halt:** new commits and/or a dirty working tree from the external review.
   - **Nothing changed → just continue.**
   - **Changes present → commit them** (`fix(story-{e}-{s}): external review changes`), then run the **single-shot re-review** (at most one per run):
     1. **Re-review (delegated, not an inline read).** Run the **code-review fan-out** (`delegation.md` → `code-review (fan-out)`) exactly like a loop pass, the same full reviewer roster: build the diff, the 3×R lenses **and** (if `code_review.security_review`) the single `code-review-security` delegate — external-review changes are exactly where a human-pushed fix can introduce a vuln — then `code-review-triage` at the primary profile (fill `{security_file_hint}` only when the security pass ran). Apply the **same reconciliation gate** as step 1 (`review_findings.py`; one `code-review-triage` re-run on non-persist, else `needs-human`). Increment `external_review_iterations`.
     2. **Gate on the FILE, not the chat.** Pipe this re-review's `review_findings.py` JSON (never the chat report) to `python3 {skill-root}/scripts/review_loop.py converged --findings-json -` and read **`meaningful`** (= NOT converged; the same convergence rule as the loop gate — the threshold lives only in the script, never re-derive it here).
        - `meaningful: false` → commit the checkpoint `chore(story-{e}-{s}): re-review external changes` and continue, no re-halt.
        - **Exception:** a genuine `code-review-security` failure on this pass (not a clean 0-finding pass) → treat the changes as **meaningful** (re-ask) regardless of the verdict. `converged` is findings-only and has no unverified input, and a security re-review that did not run is not trustworthy as clean.
     3. **Meaningful → re-ask ONCE.** Commit the persisted findings `chore(story-{e}-{s}): re-review external changes`, then **ask again** (`AskUserQuestion`), summarizing the new findings (verdict + `Critical N / High N / Medium N / Low N` + the non-deferred count). There is no inline fix loop here, but the loop itself can be re-entered. Four options:
        - **"Run another review iteration"** *(recommended for fixing in-pipeline)* — the same extension as the top-level option: re-enter the loop one (final) iteration. Its fix step addresses the open findings this re-review just persisted (the loop reads open items from `<story_file>`); clearing convergence still takes a subsequent converged pass, so expect one further extension if this pass fixes anything.
        - **"Continue (ship as draft)"** — proceed with the findings unaddressed: they stay open in `<story_file>`, surface in the report + PR `Needs attention` checklist, and set `convergence_unverified: true` so Phase 9 ships a **draft**. Any changes made during this second pause are committed (git-only) but NOT re-reviewed.
        - **"Continue (ship as ready)"** — identical to **Continue (ship as draft)** (findings stay open, surface in the report + PR checklist, `convergence_unverified: true`) **but** additionally set `no_pr_draft: true` in this run's `overrides` (state + report), so Phase 9 opens the PR **non-draft** anyway (`--no-pr-draft` flips only `draft`; the run stays caveated and the story stays at `review` — `git-and-pr.md`).
        - **"Stop now"** *(recommended for fixing outside the pipeline)* — as the **Stop the pipeline now** option below; report the open findings as `needs-human`. To get fixes re-reviewed, address the findings and re-run `/auto-bmad`: the resume re-opens this halt and its change check runs the single-shot re-review on what changed.

   **Option — "Stop the pipeline now"**. Skip the remaining phases, go straight to the report (Step 3); commits stay on the branch, nothing is pushed and no PR is opened. If the loop exited unconverged, report its last pass's findings as `needs-human`.

   **After the halt resolves:**
   - Record the choice, the external-change re-review outcome (if it ran — verdict + counts and the user's continue/stop decision), and any extra commits in state + the report.
   - **Bracket every prompt here** (the original ask and the re-ask) with `state_update.py timing-pause`/`timing-start`, so the external-review waits land on human/idle, not `active_seconds` (see top of this file).
   - Phase 7 enters `completed_phases` only after this halt resolves — or after the skip gate above fires (a skipped halt counts as resolved) — **and** the tail below, when selected.

### Phase 7 tail — per-story trace advisory  *(conditional; non-blocking)*  → `tea_per_story`
- Runs **once on the Continue path, after the review loop and its HITL halt resolve** — a halt skipped by the step-4 skip gate also reaches this path.
- Only if `trace-advisory ∈ tea_selected` (set in Phase 0 per `tea-policy.md` → §3).
- Resume-safe: skip if `story_trace` is already non-null in state.
- Phase 7 lands in `completed_phases` only after this step (when selected) finishes — so a resume that re-enters a converged Phase 7 with `story_trace == null` runs just this step.
- Delegate the **`testarch-trace (story advisory)`** entry with `<story_file>` (story scope).
- It mirrors the epic-end trace's *output* but never its *control flow*: **no `AskUserQuestion`, no remediation loop, no draft-PR forcing, no halt.** Whatever the verdict, the pipeline continues — this is visibility, not a gate.
- Record `story_trace: {verdict, uncovered: [...], ran: true}` in state. Surface any uncovered ACs in the report's **TEA** line, the PR-body checklist (so the human sees the gap at review time), and the epic retro notes (so the epic-end trace gate + retrospective inherit the signal). A non-PASS verdict does **not** set `convergence_unverified` and does **not** add a `blockers[]` entry.
- Commit `test(story-{e}-{s}): trace coverage advisory` (the trace matrix artifact if the skill wrote one, plus the state update).

## Phase 8 — Epic end  *(only if `is_last_in_epic`)*
Run the five sub-steps below in order.

**Per-sub-step marker.** Each sub-step records its `phase8_steps.<key>` marker (`trace_gate`, `nfr`, `test_review`, `project_context`, `reconcile`, `archive`, `retro`) in its folded state write:
- `done` when it ran (trace_gate also records `waived`/`failed`).
- `done` too when its gate was false (e.g. TEA off) — so a skip reads as resolved.

**Resume + completion.**
- On resume, enter Phase 8 at the **first null marker** instead of re-running completed delegations.
- Phase 8 joins `completed_phases` only once all seven markers are resolved.

**Commits.**
- Commit the epic-end docs once at the end: `docs(epic-{e}): gate, project context, deferred-work reconcile + archive, retrospective`.
- Trace-gate remediation, if any, commits separately as it runs (step 1).
1. **TEA gates (only if `tea.enabled`; epic-level skills are always on here).** Delegate, in order:
   - the **`testarch-trace`** entry via `tea_epic` — the blocking gate, full depth;
   - then the **`testarch-nfr`** and **`testarch-test-review`** entries via `tea_epic_audit` — advisory audits, one effort tier below the blocking gate.

   Capture each verdict; record the gate decision in state (`gate_decision`) + report. Handle the **trace** verdict before running nfr/test-review:
   - `PASS` → continue.
   - `WAIVED` (emitted by the skill itself) → continue; it ships as a **draft** PR in Phase 9 (already a documented human waiver — see `git-and-pr.md`).
   - `CONCERNS` → advisory; continue silently, but record it and surface it in the report + PR body. It does **not** halt or force a draft.
   - `FAIL` → **ASK the user** (AskUserQuestion; mirrors the Phase 7 HITL halt — this is not a silent hard-stop). Summarize the uncovered requirements/ACs the trace flagged, then offer the three options below.

   **Option — "Remediate & re-gate"** *(recommended; offered only while `gate_iterations < tea.gate_max_iterations`, default 2)*.
   - Delegate the **`testarch-automate`** entry at **epic scope** via `tea_epic` to close the flagged coverage gaps.
   - Increment `gate_iterations`.
   - Commit `test(epic-{e}): close trace coverage gaps (gate iter {i})` (`{i}` = the just-incremented value; first remediation ⇒ 1).
   - Re-run the **`testarch-trace`** entry and re-apply this same handling to the new verdict.
   - If the gaps are scope/spec drift rather than missing tests, the right heavier step is `/bmad-correct-course` — tell the user; do **not** auto-run it, as it changes story scope.

   **Option — "Waive & continue".**
   - Set `gate_decision: WAIVED`.
   - Record the user's rationale + the uncovered items in `deferred_work`/`open_questions`.
   - Continue. Phase 9 opens the PR as a **draft** with the waiver + gaps in the body.

   **Option — "Stop now".**
   - Skip the remaining phases, go straight to the report (Step 3); commits stay on the branch, nothing is pushed and no PR is opened.
   - Keep `gate_decision: FAIL`.
   - Add a `blockers[]` entry (e.g. `epic {e} trace gate FAILED — {n} requirements lack test coverage`), and report the gaps as `needs-human`.

   **FAIL-handling rules:**
   - Once `gate_iterations` reaches the cap and trace is still `FAIL`, drop the Remediate option and re-ask with only Waive / Stop.
   - Run nfr + test-review on every path except **Stop**.
2. **Project context:** delegate the **`generate-project-context`** entry via the `project_context` profile.
   - The Phase 8 refresh is fed the epic's accumulated retro notes (+ durable items from the deferred-work ledger).
   - The notes are the source — NOT the retro doc, which doesn't exist until step 4.
   - See `delegation.md` → `generate-project-context`.
3. **Reconcile missed completions** *(delegated — `deferred_reconcile`; runs BEFORE the archive).*
   - **Why:** the archive (step 4) judges each ledger entry on its OWN text only. A deferred item whose work actually landed during the epic but whose entry was never updated stays open forever, and create-story keeps re-folding finished work. This pass closes that gap.
   - Run `python3 {skill-root}/scripts/deferred_ledger.py plan --ledger <impl>/deferred-work.md`.
   - **Skip this step** (mark `reconcile: done`) if the ledger is absent/empty, or if **every** entry's `marker_hint` is already `resolved` — there is nothing unmarked to reconcile.
   - Otherwise delegate the **`deferred-reconcile`** entry (profile `deferred_reconcile`). It:
     - reads the ledger;
     - verifies each not-yet-fully-resolved entry (`open` or `partial`) against its referenced files / the current code;
     - writes a recognized resolution marker into the entry — only on unambiguous evidence that ALL of an item's deferred work is done (keep-on-doubt; the same asymmetry as step 4).
   - The orchestrator never reads the code or the ledger here — it routes the delegate and records its result.
   - Capture the count marked + each item's one-line evidence into the report's **Deferred work** field (folded into `deferred_archived_note` alongside step 4's archive line).
   - The delegate's ledger edits are committed with this phase's `docs(epic-{e})` commit.
   - See `delegation.md` → `deferred-reconcile`.
4. **Archive resolved deferred work** *(orchestrator-direct — connective bookkeeping, never delegated):* trim the active ledger `<impl>/deferred-work.md` so create-story stops re-folding finished work into future stories — including any entry step 3 just marked. The mechanics are scripted — you own only the keep-vs-move judgment:
   1. Run `python3 {skill-root}/scripts/deferred_ledger.py plan --ledger <impl>/deferred-work.md` (re-run it — step 3's marking changed the ledger, so its earlier sha is stale). It returns every entry (`id`, `heading`, `text`), the `ledger_sha256`, and a `marker_hint` (`resolved`/`partial`/`open`) — the hint is a heuristic aid that focuses your read; it never decides.
   2. Judge each entry on its own `text`.
      - **Move only a bullet that clearly states ALL of its deferred work is done** — keyed on a resolution *marker's meaning*, not a fixed string. The phrasing varies run to run: a leading `✅`, `RESOLVED`, "resolved in story …", "closed", "addressed in …".
      - **Keep — never move — any entry with an open remainder** (a *partial* resolution: "X portion done; Y owned by story Z" still carries open work). The entry must vouch for **itself** — do not move it just because some *other* entry says the remainder landed.
      - **Keep — never move — any unmarked entry** (a still-open deferral).
      - **When uncertain, keep it in the active ledger.** The asymmetry is the safety rule: a wrongly-kept resolved item is merely wasteful (create-story folds a done item once), but a wrongly-moved open item silently drops real follow-up work.
   3. Run `python3 {skill-root}/scripts/deferred_ledger.py archive --ledger <impl>/deferred-work.md --archive <impl>/deferred-work-resolved.md --ids <move ids> --expect-sha <ledger_sha256>`. A stale `--expect-sha` or unknown id exits 1 with no writes — re-run `plan` and re-judge.
   - No-op if the ledger is absent or holds no resolved entry (skip `archive` when the move set is empty).
   - Record the count moved (the result's `moved`) in state (`deferred_work_archived`) and the report's **Deferred work** field.
   - The move lands in this phase's `docs(epic-{e})` commit.
5. **Retrospective:** delegate the **`retrospective`** entry via the `retrospective` profile, handing it the accumulated `_bmad-output/auto-bmad/retro-notes/epic-{e}.md` as primary input. It runs autonomously and writes the retro doc + flips the retrospective status to `done`.

   **Planning-drift advisory.** Triggered when the delegate's `Planning drift` line is non-empty — the epic proved a planning assumption wrong (PRD / architecture / epic scope that no longer matches what was built).
   - Record it in state (`planning_drift`) and surface it in the report's **Planning drift** field.
   - It is **non-blocking** and **never auto-acted**.
   - Recommend the upstream re-sync, but do **not** run it — it changes planning scope and is the user's call:
     - refresh the codebase docs (`/bmad-document-project` only if `docs/` is stale, then `/bmad-generate-project-context`);
     - then `/bmad-prd` (update intent) to reconcile the PRD in place;
     - for **structural** drift, `/bmad-correct-course` instead.
   - `none` ⇒ omit.

## Phase 9 — Finalize  *(orchestrator)*
- Ensure everything is committed (no dirty tree).
- **UAT checklist (delegated — `uat`).** Before writing the report, delegate the **`uat`** entry (`delegation.md` → `uat`) via the `uat` profile, passing `<story_file>`.
  - It is **read-only** — makes no working-tree change, so it never trips the dirty-tree guard above.
  - It returns a manual user-acceptance checklist (or the single "No manual UAT applicable at this state — <reason>" line).
  - Capture its `Outcome` and pass it as the report's `uat` **list key** below — route it by value, the same as every other prose snippet; never read it as code.
  - Suppress only on the `skip uat` override (the report's **UAT** section then renders `(none)`).
  - Bracket the delegation with `state_update.py timing-start`/`timing-pause`.
- **Write the report file (before push, so it ships in the PR).** Emit it with:
  ```
  python3 {skill-root}/scripts/state_update.py report-section --report-file \
    _bmad-output/auto-bmad/reports/{key}.md --state-file <state> --json -
  ```
  - The script appends a new `## Report — <ISO timestamp>` section — creating the file if absent, never touching earlier sections — and derives the Story/Branch/Timing lines from state.
  - You supply the prose snippets in the JSON: `disposition_tag`, `pipeline_status`, `continues`, `phases_run`, `skipped`, `overrides`, `tea`, `code_review`, `next`, `head_sha`.
  - You also supply the **list keys** in the JSON: `uat` (the checklist from the `uat` delegate above), `open_questions`, `deferred_work`, `deferred_archived_note` (Phase 8's reconcile + archive line), `planning_drift`, and `needs_human`.
  - Use these exact names — the script REJECTS an unknown key. (A misspelled one would otherwise render its section `(none)` and silently drop content; the key↔heading map is pinned next to the Section template in `state-and-resume.md`.)
  - Tag the section with its disposition: `(final)` on a clean completion, `(final — caveated)` if the run finalized but stays at `review`.
  - Keep the section a session delta: on a resume, `phases_run` lists only the resumed phases and `continues` names the section it picks up from (full vocabulary in `state-and-resume.md` → "reports/{key}.md").
  - The file holds only the **story-level** outputs that aren't recorded elsewhere (fields: `state-and-resume.md` → "Section template").
  - The finalization **artifacts** — PR URL, CI run link, merge method + branch-deleted state, and the BMAD-status-flip outcome — are deliberately **chat-only** (Step 3 prints them; rationale in `state-and-resume.md` → "reports/{key}.md").
  - The one-line **disposition** DOES belong in the file's `Pipeline status` line — clean / caveated / halted at Phase N, and a draft's summary reason (CI red / waived gate / blocker). It is **not** chat-only.
  - Commit it: `docs(story-{e}-{s}): pipeline report`.
- **git mode `remote`:** push the branch, open the PR, evaluate CI, and convert to draft if warranted — all per `git-and-pr.md` ("PR" + "CI link & wait" + draft predicate clauses 1–4).
  - Capture `pr_url`, `ci_run_url`, and `ci_status`.
  - PR body = conventional summary + link to the story file + a checklist of open questions / deferred work / human-action items.
- **git mode `local`** (or the user chose "stop without a PR" in Phase 7): skip the push/PR.
  - Leave the branch in place (with the report commit on it) and note it in the chat report.
  - The CI wait and merge prompt below don't apply.
- Mark the auto-bmad state file `done` — one `state_update.py set` patch with `status: done` (the script auto-stamps `completed_at`), recording `pr_url`, `ci_run_url`, `ci_status`, final `branch`, any `blockers`.
  - **Don't commit this on its own** — it folds into the single finalize commit below (alongside the BMAD-status flip).
  - So the post-push bookkeeping is **one** commit, never a `mark done` + `record PR metadata` + `record CI status` chain.
- **Advance the BMAD-level status on a clean completion only.** Don't re-derive the verdict by hand — evaluate the draft predicate deterministically:
  ```
  python3 {skill-root}/scripts/state_plan.py --state-dir {output_folder}/auto-bmad/state \
    --story-key {key} --finalize [--ci-status passed|failed|timeout|none] [--no-pr-draft]
  ```
  - Pass the live post-wait `ci_status` when Phase 9 waited.
  - Pass `--no-pr-draft` when that override is active — it changes only `draft`, never `clean_completion`.
  - A **clean completion** = `clean_completion: true` (no draft-predicate clause fired — `git-and-pr.md` → "PR").
  - A **caveated completion** = any predicate clause fires (`reasons` names them).

  When `flip_bmad_status` is true, flip the story to `done` in the two BMAD-level sources so the next run advances past it — one idempotent call, value-only edits that preserve the rest of both files:
  ```
  python3 {skill-root}/scripts/story_plan.py --mark-done {key} \
    --sprint-status <impl>/sprint-status.yaml --story-file <impl>/{key}.md
  ```
  - the **story file `Status:`** field → `done`;
  - the **`<impl>/sprint-status.yaml`** entry for `{key}` → `done`.

  On a caveated completion (`flip_bmad_status: false`), **leave both BMAD-level sources at `review`** so the story keeps re-surfacing until a human acts (see `state-and-resume.md`).

  **Commit the state→`done` write and these two BMAD-status flips together** as the single `chore(story-{e}-{s}): finalize (mark done + BMAD status)` commit, then push it so it lands on the branch/PR.
  - On a **caveated** completion (no BMAD flip), the lone state→`done` write is still that one finalize commit.
  - The later merge-prompt outcome (`pr_merged` / `merge_method` / `branch_deleted`) is written to state but gets **no commit of its own** — the run is already `done` (resume skips it) and the chat report owns merge details (`git-and-pr.md` → "Merging the PR").
- **Merge prompt** — ask the user how to merge and execute their choice per `git-and-pr.md` → "Merging the PR". Records `pr_merged` / `merge_method` / `branch_deleted` in state. Offered only when ALL hold:
  - a clean completion;
  - `git.offer_merge: true`;
  - mode `remote`;
  - a PR was opened;
  - no `skip merge-prompt` override.
- Hand control back to the SKILL's Step 3, which **prints the final chat report** (the committed file portion plus PR / CI / merge / final-status details).
