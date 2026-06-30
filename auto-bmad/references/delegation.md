# Delegation prompts

**This file is the single source of truth for what each BMAD step runs** — its exact `/bmad-*` command, prompt body, and the placeholders below.

- One entry per step, named by its heading.
- `pipeline.md` references each by heading name and never repeats the command.
- Git/PR steps are not delegated and have no entry here — the orchestrator runs them. See `git-and-pr.md`.

To dispatch a step, the orchestrator:
- Fills the placeholders below.
- Sends the result as the Agent prompt to the profile `phase_profiles` assigns to the step's phase — the phase→profile-key mapping is in `pipeline.md`, the config in `state-and-resume.md`.

Prompt-authoring rules:
- Keep each prompt **minimal** — the command plus the inputs the skill needs.
- End each prompt with the shared autonomy directive below — the short version is enough, because the delegate profiles already carry the full form.

**Shared autonomy directive (append to every prompt):**
> Run fully autonomously — answer any interactive BMAD menu/checkpoint with the sensible default
> and never wait for human input. The sensible default is ALWAYS the option that completes the
> step and persists its deliverable — never one that skips it, discards findings, or writes
> nothing. If something genuinely needs a human (missing secret/credential, external service, 
> manual action, or an ambiguity that changes the outcome), STOP and report it as `needs-human`. 
> Return the structured result: Outcome, Files changed, Status, Open questions, Deferred work, 
> Blockers, Retro notes (short and terse — say `none` unless something is genuinely worth the 
> epic retrospective; one line per item, no recap of routine work).

**Placeholders (canonical glossary — `pipeline.md` references this list, not its own copy).**
`<...>` = a filesystem path the orchestrator resolves; `{...}` = a non-path value it fills in (identity/config scalar, or an injected block).
- `{e}` / `{s}` — epic / story number.
- `{key}` — full story key (e.g. `1-2-user-auth`).
- `{slug}` — the title part of the key.
- `{decisions}` — the chosen fix directions from Phase 7: human-picked (per-story), or in **epic mode** the triage's recommended `fix:` directions applied autonomously (`epic-pipeline.md`).
- `<project_root>` — absolute cwd.
- `<impl>` — the `implementation_artifacts` dir; `<planning>` — the planning dir.
- `<story_file>` — absolute path `<impl>/{key}.md` (from `story_plan.py`).
- `<review_tmp>` — the throwaway dir `review_loop.py prep-diff` creates **outside the work tree** for the code-review fan-out, holding `<diff_file>` (the branch diff), one set of three lens-output paths per reviewer slot (`lens_paths.{primary|secondary|tertiary}.{blind|edge|auditor}`), and the single `security_path` (the dedicated security review's output). In the lens prompts below, `<blind_out>` / `<edge_out>` / `<auditor_out>` mean *the running reviewer slot's* reserved paths, and `<security_out>` is the `security_path`. Never under `<impl>` or the repo — it must not be committable. Deleted (`rm -rf`) once the iteration's reconciliation gate passes; on a `needs-human` exit it is kept and its path surfaced for debugging.

---

### create-story
```
Run `/bmad-create-story {e}-{s}` in <project_root>.
Create the comprehensive story context file for story {e}-{s}.
{retro_notes_hint}
{deferred_work_hint}
```
The orchestrator fills `{retro_notes_hint}` from on-disk state. First matching branch wins:
- If `_bmad-output/auto-bmad/retro-notes/epic-{e}.md` exists and is non-empty — earlier stories in this epic have landed signal — inject: `BEFORE drafting the story context, ALSO read _bmad-output/auto-bmad/retro-notes/epic-{e}.md and treat each '## Story <key>' section's bullets as constraints surfaced by earlier stories in the same epic — epic-wide gotchas, schema inheritance, conventions ratified, things later stories MUST or MUST NOT do. Reflect any that apply to this story directly in the Story Context (constraints, persistent_facts, or test notes), not as a generic "see retro-notes" reference.`
- Else if this is the **first story of epic {e}** AND a prior epic `{e-1}` closed with a retrospective document, inject the string below.
  - Locate the retro with `find <impl> -name 'epic-{e-1}-retro-*.md'` — BMAD writes the retro there.
  - NEVER iterate a raw glob — unmatched globs abort under zsh/fish.
  - Use the newest match if several; omit this branch if none.
  - Inject: `BEFORE drafting the story context, ALSO read the prior epic's retrospective document and focus on its FORWARD-looking sections (e.g. "Next Epic Preparation", "Preparation Checklist Before Epic {e}", "Conventions Ratified for All Epic {e}+ Stories", Action Items). These are the epic-transition prep + conventions the just-closed epic flagged for THIS epic. Fold the items that apply to this story into the Story Context (constraints, persistent_facts, or test notes) — especially any "before the first story of epic {e}" prep, and any "the gate/check will fail-loud on the new table → that is expected, register/extend it" heads-ups — not as a generic "see the retro" reference. (Durable conventions also reach you via project-context.md as persistent_facts; this feed adds the transient, epic-specific prep that project-context.md does not carry.)`
- Otherwise omit the line entirely — first story of epic 1, or no signal yet.

Phase notes in the retro file use a `[Phase X — short-name]` prefix (e.g. `[Phase 5 — dev-story]`, `[Phase 7 — code review]`).
- Preserve the prefix when appending — it lets later stories filter by phase if they need to.

The orchestrator also fills `{deferred_work_hint}` from on-disk state.
- No BMAD or TEA skill reads the ledger `<impl>/deferred-work.md` back — so create-story only sees it if we inject it here.
- If `<impl>/deferred-work.md` exists and is non-empty, inject: `ALSO read <impl>/deferred-work.md before drafting the story context. It is a project-wide ledger of work earlier stories consciously deferred — most entries are out of scope for this story. Identify ONLY the deferrals whose subject overlaps this story's area, files, or acceptance criteria, and fold those into the Story Context (constraints, persistent_facts, or test notes) so the dev agent either addresses them or knowingly works around them. Do NOT copy the whole ledger, and do NOT reopen or re-defer items unrelated to this story.`
- Otherwise omit the line entirely — the ledger doesn't exist yet, or is empty.

### dev-story
```
Run `/bmad-dev-story <story_file>` in <project_root>.
Implement the story to completion: all tasks/subtasks done, tests written and passing, story
moved to `review`. Do not commit or branch — the orchestrator handles git.
When done, report a short summary of what you built plus any deviations, key decisions, and
deferred work — and any breaking change you introduce (a changed/removed public interface, config
key, schema, CLI flag, or required migration step). The orchestrator records these in the commit
body (and a `BREAKING CHANGE:` footer).
```

### code-review  (fan-out — 3×R lens delegates + one triage, not one skill call)
Code-review is **not** delegated as a single `/bmad-code-review` call.
- That skill internally fans out to three review subagents.
- A delegate cannot do that — a sub-agent can't spawn sub-agents.

So the **orchestrator hoists the fan-out** (`pipeline.md` Phase 7 step 1). It:
- Builds the diff.
- Runs the three lens entries below **once per roster reviewer** — `code_review_review` (primary, always), plus `code_review_review_secondary` / `code_review_review_tertiary` when each maps to a non-blank profile. Each lens runs at its reviewer's profile and writes to that reviewer slot's reserved paths.
- Runs one `code-review-triage` at the **primary** profile over all the lens files.
- Gates persistence.

It passes the diff and each lens's findings **by path, never by content** — so it never reads either, and "no code inspection at any tier" holds.

<!-- auto-bmad-local: NOT from upstream bmad-code-review (which has no security lens); do not
     reconcile away on a compat-check. -->
**Plus a dedicated security review (auto-bmad-local).** When `code_review.security_review` is true (default), each iteration ALSO fans out one `code-review-security` delegate.
- It is **single-instance** — one per iteration at the `code_review_security` profile, NOT per reviewer — and writes to `<security_out>`.
- A blank `code_review_security` profile falls back to the `code_review_review` (primary) profile.
- Its findings feed the SAME `code-review-triage` and gate convergence through the findings-severity channel — a security Critical/High lands in `open_crit_high`.
- It is therefore **not** counted in the gate's `3×R` `--lenses-total`.
- Handling its run/failure is `pipeline.md` Phase 7 step 1: a successful 0-finding pass is clean; only a genuine delegate failure forces a draft.

**Keep that invariant real for the three lenses.** When you append the shared autonomy directive to a lens prompt, bind its structured result so finding content stays out of chat:
- The lens's `Outcome` is just its output-file path + finding count.
- Its `Deferred work` / `Retro notes` are `none`.
- Only `code-review-triage` reads the findings.
- Triage's own report carries counts + verdict — metadata, not code — which the orchestrator needs for the loop.

**Diff construction (orchestrator — tool call, by path, no ingestion).**
- `review_loop.py prep-diff --project-root <project_root> --base {git.base_branch}` builds `<review_tmp>`, `<diff_file>` and the three lens-output paths (three-dot diff; the `:(exclude)` pathspecs live in the script — `pipeline.md` Phase 7 step 1a).
- Non-code files beyond those excludes are **not** a path rule — `code-review-triage` dismisses them (see its prompt).
- If `diff_empty`, there is nothing to review.

**Epic mode (Tier B)** reuses this exact fan-out over the **whole-epic** diff (`prep-diff --base {base}`). Flow: `epic-pipeline.md` E_review.
- Swap the auditor/triage/fix entries for their `(epic)` variants below.
- Persist to `<impl>/epic-{e}-review-findings.md`.
- Security stays single-instance off-total exactly as here.
- The roster shape is identical (`3×R` = blind/edge/auditor per reviewer).

#### code-review-blind  (Blind Hunter — diff + code read, blind to spec/intent)
<!-- Access model mirrors bmad-code-review #2507: the Blind Hunter is blind to INTENT (no
     spec/context), NOT to the codebase — it may read surrounding code to judge correctness. -->
```
Run `/bmad-review-adversarial-general` in <project_root> with the diff at <diff_file> as the content to
review. Review that diff — do NOT open the spec or the story file; your value is being unanchored by the
spec (intent). You MAY read the surrounding code the diff touches to judge whether a change is actually
correct. Write the skill's findings (its markdown list) to <blind_out>. Report ONLY the path you wrote
and your finding count — NOT the findings text.
```

#### code-review-edge  (Edge Case Hunter — diff + project read)
```
Run `/bmad-review-edge-case-hunter` in <project_root> with the diff at <diff_file> as the content to
review (you may read project files the diff references). Write the skill's JSON-array output to
<edge_out>. Report ONLY the path you wrote and your finding count — NOT the findings text.
```

#### code-review-auditor  (Acceptance Auditor — diff + spec)
```
You are an Acceptance Auditor. Review the provided diff against the spec and any loaded context docs. Check for: violations
of acceptance criteria, deviations from spec intent, missing implementation of specified behavior,
contradictions between spec constraints and actual code. Output findings as a Markdown list. Each
finding: one-line title, which AC/constraint it violates, and evidence from the diff.

The diff is at <diff_file>; the spec/story file is <story_file> (load it, plus any docs its `context`
frontmatter lists). Write your findings to <auditor_out>. Report ONLY the path you wrote and your
finding count — NOT the findings text.
```
(The first paragraph mirrors the Acceptance Auditor prompt from the `bmad-code-review` skill's `step-02-review.md` — upstream's `{spec_file}`/`{diff_output}` placeholders are resolved by auto-bmad's `<story_file>`/`<diff_file>` in the paragraph below. Keep it in lockstep with upstream.)

#### code-review-auditor (epic)  (Acceptance Auditor — epic diff + epic planning; epic mode Tier B)
<!-- VARIANT OF code-review-auditor: the upstream-verbatim first paragraph stays the single source —
     do NOT re-paste it (keep the base in lockstep with bmad-code-review). Only the spec input + diff
     scope change, below. -->
Identical to **`code-review-auditor`** above, with these substitutions:
- the diff `<diff_file>` is the **whole epic {e}** (all its stories), not one story's;
- in place of the single `<story_file>` spec, load epic {e}'s **planning artifacts** (`{epic_planning_files}` — the epics doc / epic PRD section resolved in E0) **and** the per-story spec files (`{story_files}`); audit how the **assembled epic** meets the epic's intent + each story's ACs, focusing on **cross-story / integration** gaps a per-story audit cannot see;
- write to `<auditor_out>` (the epic roster's auditor slot). Report ONLY the path + finding count.

#### code-review-security  (Security Reviewer — diff + project read; auto-bmad-local, NOT upstream)
<!-- auto-bmad-local: no upstream bmad-code-review counterpart; methodology ported from Anthropic's
     open-source claude-code-security-review. Do not reconcile away on a compat-check. -->
```
You are a Security Reviewer. Review this diff for exploitable security vulnerabilities introduced or
exposed by the change. Examine: input validation (SQL/command/template/NoSQL injection, XXE, path
traversal, SSRF); authentication & authorization (bypass, privilege escalation, session/JWT flaws);
crypto & secrets (HARDCODED credentials/keys/tokens — always report these; weak algorithms; improper
key/cert handling); injection & code execution (deserialization RCE, eval, XSS); sensitive-data
exposure (logging, PII, debug leakage).

For each finding give: a one-line title; file:line; severity HIGH (directly exploitable) / MEDIUM
(exploitable under conditions) / LOW (defense-in-depth); a concrete exploit scenario; and a fix.

DO NOT REPORT (noise): denial-of-service / resource exhaustion; memory or CPU exhaustion; absence of
rate limiting; lack of input validation on non-security-critical fields with no proven problem; any
finding you are <70% confident is a real, reachable issue. "Exploitable only under conditions" is
MEDIUM — report it, do not drop it.

The diff is at <diff_file>; you may read project files the diff references for reachability. Write
findings as a Markdown list to <security_out>. Report ONLY the path you wrote and your finding count
(by severity) — NOT the findings text.
```
Bind the structured result like the three lenses, so finding content stays out of chat:
- The `Outcome` is the output path + per-severity count.
- `Deferred work` / `Retro notes` are `none`.
- Only `code-review-triage` reads `<security_out>`.

#### code-review-triage  (triage + persist — the only code-review delegate that writes findings)
```
Triage a code review of story {key}. The same three review lenses ran independently under each of
{R} reviewer model(s); their raw findings are in these files (any may be empty or absent — note
each such case as a failed/empty layer):
{lens_files}
{security_file_hint}
The diff under review is at <diff_file>; the spec/story file is <story_file>. Do NOT re-review — work
from those files; you MAY open the source at a finding's location to calibrate its severity (below), but
do not redo the lenses' search.

Severity calibration (mirrors `bmad-code-review` step-03, upstream #2523 — but auto-bmad keeps its
4-level Critical/High/Med/Low scale, NOT upstream's 3-level low/medium/high): before tagging a finding's
severity, read enough surrounding code at its location — call sites, guards, and validation that live
OUTSIDE the diff hunk — to judge real reachability. Rate by the real consequence at a real call site,
not the worst theoretical reading of the diff hunk alone.

TRIAGE:
1. Normalize all findings to a common shape (title, detail, file:line if present, source lens+reviewer).
2. Deduplicate: merge findings describing the same issue — prefer the one with a concrete file:line,
   fold in the others' detail, mark the merged source (e.g. blind@primary+edge@secondary). Expect
   heavy overlap ACROSS reviewers AND with the security review (independent models on the same diff):
   same-issue findings are duplicates to merge, never separate bullets. On merge, the merged severity
   is the MAXIMUM across the merged findings — a non-security lens can never lower a severity the
   security review assigned.
3. Classify each into exactly one bucket:
   - Decision — an ambiguous choice that needs a human call; the code can't be correctly patched
     without knowing intent.
   - Patch — a code issue whose correct fix is unambiguous.
   - Defer — real but pre-existing, not caused by this change; not actionable now.
   - Dismiss — noise / false positive / handled elsewhere. ALSO dismiss any finding whose only locus
     is an obvious non-code file (lockfile, generated, vendored, build artifact).
   Drop every Dismiss finding (keep the dismissed count for the report).
4. (auto-bmad-local — NOT upstream bmad-code-review) Security mapping + Low selectivity:
   - Severity map for security-review findings (<security_out>): HIGH -> Critical/High, MEDIUM -> Med,
     LOW -> Low. A MEDIUM means "exploitable under conditions" — that is NOT a reason to dismiss.
   - A security-sourced Critical/High may ONLY be Patch or Decision — NEVER Defer or Dismiss (a
     pre-existing exploitable flaw still ships if deferred; force a human call instead). Medium/Low
     security findings follow the normal rules.
   - Dismiss a security finding ONLY via its exclusion list (DoS, rate-limiting, resource/CPU
     exhaustion, validation of non-security-critical fields with no proven problem, <70% confidence).
     NEVER dismiss it merely for needing attacker-controlled conditions.
   - Low selectivity (Low severity ONLY — Critical/High/Med are ALWAYS kept): keep a Low only if it
     names a concrete DEFECT (a specific wrong behaviour, not a preference) AND a realistic trigger.
     Dismiss cosmetic/style/preference nits, hypotheticals with no realistic trigger, and
     defense-in-depth where the value is already guarded (count them as noise). Do NOT apply this
     "realistic trigger" test to security findings — use their exclusion list above. A genuine-but-
     minor Low goes to Defer; a noise Low is dismissed.
5. (auto-bmad-local — NOT upstream bmad-code-review) Recommended resolution for every Decision:
   for each finding you bucket as Decision, also pick the single resolution a domain expert would
   most likely choose, as one of three channels + a one-line direction:
   - `fix: <concrete fix direction to implement>` — when one resolution is clearly best;
   - `defer: <why it is follow-up, not now>` — when the right call is to log it for later;
   - `dismiss: <why it is a non-issue / won't-fix>` — when on reflection it needs no action.
   Always recommend an actual resolution — NEVER "ask a human" (that is not a resolution). This is a
   best-guess for autonomous (epic-mode) runs that proceed without a human; in a per-story run a human
   still chooses, so the recommendation is advisory there.

PERSIST (this is the deliverable the orchestrator gates on):
- In <story_file>, add/append a `### Review Findings` section with one bullet per surviving finding,
  Decision first, then Patch, then Defer:
    - [ ] [Review][Decision][<Critical|High|Med|Low>] <title> — <detail>
    - [ ] [Review][Patch][<Critical|High|Med|Low>] <title> [<file>:<line>]
    - [x] [Review][Defer][<Critical|High|Med|Low>] <title> [<file>:<line>] — deferred, pre-existing
  Tag EVERY bullet with its severity, directly after the type tag as shown. The orchestrator reads
  severity from THIS FILE (an untagged finding is treated as Critical/High), never from your chat
  counts — an untagged bullet can force an extra review iteration.
- (auto-bmad-local — NOT upstream bmad-code-review) End every `[Review][Decision]` bullet's
  `<detail>` with ` Recommended: <fix|defer|dismiss>: <one-line direction>` — the SAME as REPORT
  below, persisted for auditability. The orchestrator's findings parser ignores trailing text, so
  this never affects tagging.
- Copy every `[Review][Defer]` finding to <impl>/deferred-work.md (create it if absent) under a
  `## Deferred from: code review of {key} (<date>)` heading — one bullet each.

REPORT (chat — the orchestrator reads this, then independently gates the file): verdict (Approve /
Changes Requested / Blocked); Critical/High/Med/Low counts; the count of open `[Review][Decision]`
items (a human call — `pipeline.md` Phase 7); (auto-bmad-local — NOT upstream bmad-code-review)
`Recommended resolutions:` = one line per OPEN `[Review][Decision]` item, `<title> [<sev>] ->
<fix|defer|dismiss>: <one-line direction>` (the channel an autonomous epic-mode run applies without
asking — `epic-pipeline.md` E5f / E_review; `none` if no open Decision items); `Findings persisted:
<N>` = total `[Review][*]` bullets
you wrote to <story_file>; `Deferrals logged: <W>` = bullets you added under this story's
`## Deferred from:` heading in <impl>/deferred-work.md; `Failed layers: <list or none>`;
`Dismissed (noise): <D>` = Low/noise findings you dropped, with a one-line category each (cosmetic /
hypothetical / already-guarded) so the human can pull any back. Do NOT change
the story's Status field, sync sprint-status.yaml, or halt for input — the orchestrator owns those.
```
The orchestrator fills `{R}` with the roster size.

The orchestrator fills `{lens_files}` with one block per roster reviewer, from `prep-diff`'s `lens_paths`:
- Reviewer `primary`:
  - Blind Hunter (adversarial markdown list): `<lens_paths.primary.blind>`
  - Edge Case Hunter (JSON array — location / trigger_condition / guard_snippet / potential_consequence; deletion findings add `kind`/`confidence`): `<lens_paths.primary.edge>`
  - Acceptance Auditor (markdown list — title / AC-or-constraint / evidence): `<lens_paths.primary.auditor>`
- Repeat for `secondary` / `tertiary` when on the roster — list only active slots.

The orchestrator fills `{security_file_hint}` from `code_review.security_review`:
- When true, inject: `A dedicated security review also ran (auto-bmad-local); its findings (severity HIGH/MEDIUM/LOW per the prompt) are at <security_out> — may be empty or absent.`
- When off, `{security_file_hint}` is empty.

### code-review-triage (epic)
<!-- VARIANT OF code-review-triage: the TRIAGE 1–4 block (incl. the auto-bmad-local security map +
     Low keep/drop test) and the REPORT contract stay the single source — do NOT re-paste them (keep
     the base in lockstep with upstream). Only the framing + persistence target change, below. -->
Identical to **`code-review-triage`** above (same TRIAGE steps 1–4 including the auto-bmad-local security severity map + Low selectivity, same REPORT contract), with these substitutions:
- **Framing:** "Triage a code review of story {key}" becomes "Triage the INTEGRATION code review of epic {e} (all {epic_story_count} stories landed)"; the diff is the **whole epic** at `<diff_file>`; for acceptance context use the per-story spec files `{story_files}` (do NOT re-review them). The lenses are the epic roster's (blind / edge / **`code-review-auditor (epic)`**) per reviewer.
- **PERSIST target:** write the `### Review Findings` section to **`<impl>/epic-{e}-review-findings.md`** (create if absent), NOT a story file — same bullet format + mandatory severity tags.
- **Deferral ledger heading:** copy every `[Review][Defer]` to `<impl>/deferred-work.md` under `## Deferred from: epic review of epic-{e} (<date>)`.
- **REPORT** is unchanged except `Findings persisted` / `Deferrals logged` count against the epic findings file + the `epic-{e}` heading.

Fill the remaining placeholders exactly as the base entry:
- `{lens_files}` / `{security_file_hint}` are filled from the epic roster's `prep-diff` paths.
- `{R}` = the epic roster size.
- In the chunked large-diff path, the orchestrator hands ONE triage call the lens files from every chunk — `epic-pipeline.md` E_review.

### code-review fix
```
Run `/bmad-dev-story <story_file>` in <project_root>, focused ONLY on the open code-review
findings under the story's `### Review Findings` section: resolve every unresolved `[Review][Patch]`
item, plus each `[Review][Decision]` item for which a human-chosen fix direction is listed below.
Implement each in the stated direction and mark it resolved in place (tick its `[ ]` checkbox if it
has one). NEVER invent a direction for a `[Review][Decision]` item with no chosen direction — leave
it unresolved. Make tests pass. Do not commit.

Resolved decisions (implement exactly these): {decisions}
```
The orchestrator fills `{decisions}` with the chosen `fix`-direction resolutions:
- Per story: the Phase 7 `AskUserQuestion` answers.
- In **epic mode**: the triage's auto-bmad-local `Recommended resolutions:` `fix:` directions applied without asking (`epic-pipeline.md` E5f / E_review).
- Omit the line when there are none.

Only `fix`-channel resolutions go here — `defer`/`dismiss` resolutions are direct orchestrator writes to the findings file, never the fix delegate.

### code-review fix (epic)
<!-- VARIANT OF code-review fix: identical prompt; only the findings file + a one-line epic context
     differ. -->
Identical to **`code-review fix`** above, with these substitutions:
- the findings live in **`<impl>/epic-{e}-review-findings.md`** — pass it to `/bmad-dev-story` in place of `<story_file>`; resolve the open `[Review][Patch]` items (+ any human-resolved `[Review][Decision]`) under that file's `### Review Findings` section;
- add one context line: `These findings span epic {e}'s stories; implemented story files: {story_files}.`
- `{decisions}` is filled exactly as the base entry — in epic mode from the triage's auto-bmad-local `Recommended resolutions:` `fix:` directions applied without asking (`epic-pipeline.md` E_review), never an `AskUserQuestion`.

### testarch-test-design (epic level)
```
Run `/bmad-testarch-test-design` in <project_root>. Choose EPIC-LEVEL mode for epic {e}
(epic + its stories). Produce the epic test plan / risk matrix.
```

### testarch-atdd
```
Run `/bmad-testarch-atdd` in <project_root> for story file <story_file>.
Generate the red-phase acceptance test scaffolds + checklist for this story.
```

### testarch-automate
```
Run `/bmad-testarch-automate` in <project_root> for story file <story_file>.
Expand automated test coverage for the code implemented in this story.
```
(Phase 8 trace-gate remediation reuses this skill at **epic scope**: pass epic {e} instead of a single story file and target the specific coverage gaps the trace gate reported.)

### testarch-trace (epic gate)
```
Run `/bmad-testarch-trace` in <project_root> for epic {e}. Build the traceability matrix and
produce the quality-gate decision. Report the gate verdict (PASS/CONCERNS/FAIL/WAIVED) + rationale.
If the verdict is not PASS, also list the specific requirements / acceptance criteria left
uncovered, so the orchestrator can summarize them for the human and target remediation.
```

### testarch-trace (story advisory)
```
Run `/bmad-testarch-trace` in <project_root> for story file <story_file> — STORY SCOPE: trace
ONLY this story's acceptance criteria, not the whole epic. Build the story-level traceability
matrix (each AC -> its covering test(s)) and report the verdict (PASS/CONCERNS/FAIL) plus the
specific ACs left uncovered. This is an ADVISORY pass: its job is to surface coverage gaps early
so they are visible at review time — do NOT block, remediate, or open a gate; just report.
```
(The blocking quality gate stays at epic end — see `tea-policy.md` → "Long-epic trace advisory".)

### testarch-nfr (epic gate)
```
Run `/bmad-testarch-nfr` in <project_root> for epic {e}. Audit NFR evidence
(performance/security/reliability/maintainability) for the work completed in this epic.
```

### testarch-test-review (epic gate)
```
Run `/bmad-testarch-test-review` in <project_root> with suite scope (the tests added across
epic {e}). Report quality findings + score.
```

### generate-project-context
```
Run `/bmad-generate-project-context` in <project_root>. {bootstrap_intent}
Use sensible defaults for any prompt.
```
The orchestrator fills `{bootstrap_intent}` from the calling phase:
- Phase 2 bootstrap (no `project-context.md` exists yet): `Create project context for the first time`
- Phase 8 refresh (epic-end, file already exists): `Update project-context.md to reflect the current stack, patterns, and conventions after epic {e}. BEFORE rewriting, read the accumulated retro notes at _bmad-output/auto-bmad/retro-notes/epic-{e}.md (and scan <impl>/deferred-work.md for any DURABLE constraint).`

### deferred-reconcile
This is **not** a `/bmad-*` skill call — it is a reconciliation pass (an inline prompt, like the code-review lenses).
- It runs once at epic end, immediately **before** the orchestrator-direct archive.
- It catches deferred items whose work actually landed during the epic but whose ledger entry was never updated to say so — because the text-only archive would otherwise keep re-folding finished work forever.
```
Reconcile the deferred-work ledger <impl>/deferred-work.md against the CURRENT codebase, in
<project_root>, after epic {e}.

For EACH ledger entry that is NOT already marked fully resolved — i.e. an UNMARKED entry (still
open) OR a PARTIAL entry (it carries a resolution marker but also an open-remainder clause like
"remainder owned by story X") — verify against the entry's referenced files (the `[path:line]`
refs) and the current code whether ALL of that item's deferred work is now actually done.

Mark an entry resolved ONLY on unambiguous evidence that EVERYTHING it defers is complete. This
is the safety rule and it is asymmetric: a wrongly-KEPT item is merely re-folded once (harmless);
a wrongly-MARKED item is silently archived and its real follow-up work is dropped. So when there
is ANY doubt — the evidence is indirect, the item is vague, only part of it is clearly done —
LEAVE THE ENTRY EXACTLY AS IT IS.

For each entry you DO confirm fully resolved, edit only that bullet's text in place:
- Prepend the resolution marker `✅ ` and append `— resolved in <where>` (name the file/commit/story
  that landed it). Use exactly that vocabulary: a leading ✅ plus "resolved in".
- It must read as FULLY resolved: do NOT include any of the words "remainder", "still open",
  "portion", "owned by", or "partial" in the edited bullet (those keep it un-archivable). For a
  previously-PARTIAL entry now fully done, REWRITE its remainder clause out so nothing open remains.

Edit nothing else: preserve every `## Deferred from:` heading, every other entry, all nesting and
prose, byte-for-byte — a downstream script re-parses this file. Do NOT reword, reorder, or remove
still-open entries; do NOT touch already-fully-resolved entries; do NOT add new entries.

Return, in `Deferred work`, the count of entries you marked and ONE line per marked entry naming
the item and the one-line evidence (the file/commit that resolved it); `none` if you marked
nothing.
```
Run condition:
- Run this only when `deferred_ledger.py plan` shows at least one entry that is not already `resolved`.
- Skip it — and mark `phase8_steps.reconcile: done` — when the ledger is absent/empty or every entry is already `resolved`.

The orchestrator records the result in state and the report.
- The delegate's ledger edits land in the same epic-end `docs(epic-{e})` commit as the archive that follows.

Pin the marker vocabulary above to what `deferred_ledger.py` recognizes — `✅` / "resolved in" / "closed" / "addressed in" / "done in", and no remainder signal.
- A marker it can't read silently no-ops — safe, because the entry is simply kept.

### retrospective
```
Run `/bmad-retrospective` in <project_root> for epic {e}.
You are the sole facilitator AND participant — answer all party-mode questions yourself using
the accumulated notes at _bmad-output/auto-bmad/retro-notes/epic-{e}.md plus the story files and
sprint-status. Produce the full retrospective document and mark the epic retrospective `done`.
In the structured result, add a `Planning drift` line: if the retro surfaced planning assumptions
the epic proved wrong (PRD / architecture / epic scope that no longer matches what was actually
built), list each as one line — the artifact, what drifted, and whether it is detail-level or
structural — so the orchestrator can recommend a re-sync. Say `none` when the build matched the plan.
```

### uat  (manual User-Acceptance-Testing checklist — auto-bmad-local, NOT a /bmad-* skill)
<!-- auto-bmad-local: no upstream bmad-code-review / BMAD counterpart — a hand-off artifact unique to
     auto-bmad. Do not reconcile away on a compat-check. -->
This is **not** a `/bmad-*` skill call — it is a **read-only** acceptance pass (an inline prompt, like the code-review lenses).
- It runs once the implementation is settled — Phase 9 head per story; `epic-pipeline.md` E5 per story in epic mode.
- It returns a manual UAT checklist the orchestrator routes verbatim into the report's **UAT** section.
- Finding/content stays out of the orchestrator's read path exactly like the `tea` / `pipeline_status` strings.
```
Produce a manual User-Acceptance-Testing (UAT) checklist for story {key}, in <project_root>.

READ-ONLY: read the story spec / acceptance criteria at <story_file> (plus any docs its `context`
frontmatter lists), then inspect the IMPLEMENTED code to see what actually exists and is runnable at
THIS point. Do NOT modify, create, or delete any file — make NO change to the working tree; your
`Files changed` is `none`.

Build the checklist from what a human can EXERCISE BY HAND right now:
- One item per line, each a concrete `action → expected result` a person can perform and verify
  (e.g. "Register with a valid email → account created, you land on the dashboard"). Fold any
  precondition/setup the human needs INTO the line (test creds, a seeded record, the exact
  command / URL / endpoint to hit).
- Scope to the acceptance criteria the implementation ACTUALLY satisfies at this state, and to the
  interface that actually exists now — if the slice shipped is a backend endpoint with no UI yet,
  write API / curl-level checks, NOT "click the button". NEVER write aspirational or full-feature
  steps for behavior not yet built.
- Cover the happy path plus the acceptance-relevant error / edge cases that are manually observable.

If NOTHING is manually user-testable at this state — a pure internal refactor, infra-only change, or
work with no human-observable surface yet — return EXACTLY ONE item that says so plainly with the
one-line reason (e.g. "No manual UAT applicable at this state — internal refactor of the auth token
store; behavior unchanged and covered by automated tests"). NEVER invent steps to fill the section.

Return the checklist as your `Outcome`: the list of one-line items (or the single not-applicable
line). Keep each item self-contained and short. `Files changed: none`; `Deferred work` / `Retro
notes`: `none` unless genuinely worth the epic retrospective.
```

### uat (epic)  (single-session consolidation — epic mode E_final)
<!-- VARIANT OF uat: composes the per-story UAT one-liners the E5 loop accumulated into ONE
     session-ordered checklist against the assembled epic; auto-bmad-local, NOT upstream. -->
```
Compose a SINGLE-SESSION manual UAT checklist for epic {e}, in <project_root>, from the per-story UAT
items the loop accumulated (below) reconciled against the FINAL assembled epic.

READ-ONLY (same discipline as `uat`): you may inspect the implemented code for reachability; make NO
change to the working tree (`Files changed: none`).

Accumulated per-story UAT items (each tagged with its story key):
{uat_items}

Produce ONE checklist a human can run end-to-end in a single sitting against the assembled epic:
- DEDUPLICATE across stories (a later story often supersedes an earlier story's interim step) and DROP
  any item a later story made obsolete or that no longer matches the final state.
- ORDER the survivors into a coherent walk-through — setup / precondition items first, then the user
  journeys they unlock — merging per-story fragments into whole flows where they compose.
- Re-scope each item to the final assembled interface (a check that was API-only mid-epic may have a
  UI now — verify against what exists now).
- Same not-applicable rule: if NOTHING across the epic is manually user-testable, return EXACTLY ONE
  line saying so + the reason.

Return the consolidated checklist as your `Outcome` (one item per line). `Files changed: none`;
`Deferred work` / `Retro notes`: `none` unless genuinely retro-worthy.
```
The orchestrator fills `{uat_items}` from the epic anchor's accumulated `uat_items`, one `[{key}] <item>` per line.
- If it is empty — no story produced a testable item — skip this delegate and render the report's **UAT** section `(none)`.

