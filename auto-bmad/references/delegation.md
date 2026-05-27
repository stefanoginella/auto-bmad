# Delegation prompts

One template per BMAD step. The orchestrator fills the placeholders and sends the result as the
Agent prompt to the profile that `phase_profiles` assigns to the step's phase (see `pipeline.md`
for the phase→key mapping and `state-and-resume.md` for the config). Keep prompts **minimal** —
the exact `/bmad-*` command + the inputs the skill needs. Every prompt ends with the shared
autonomy directive (the delegate profiles already carry it, so the short form below is enough).

**Shared autonomy directive (append to every prompt):**
> Run fully autonomously — answer any interactive BMAD menu/checkpoint with the sensible default
> and never wait for human input. If something genuinely needs a human (missing secret/credential,
> external service, manual action, or an ambiguity that changes the outcome), STOP and report it
> as `needs-human`. Return the structured result: Outcome, Files changed, Status, Open questions,
> Deferred work, Blockers, Retro notes.

**Placeholders.** `<...>` = a filesystem path the orchestrator resolves; `{...}` = a non-path
value it fills in (identity/config scalar, or an injected block). Specifically: `{e}`/`{s}`
(epic/story number), `{key}`, `{slug}`, `{decisions}` (the human-chosen fix directions from
Phase 7); `<project_root>` (absolute cwd), `<story_file>` (absolute, `<impl>/{key}.md`),
`<impl>`/`<planning>` dirs.

---

### create-story
```
Run `/bmad-create-story {e}-{s}` in <project_root>.
Create the comprehensive story context file for story {e}-{s}.
```

### dev-story
```
Run `/bmad-dev-story <story_file>` in <project_root>.
Implement the story to completion: all tasks/subtasks done, tests written and passing, story
moved to `review`. Do not commit or branch — the orchestrator handles git.
```

### code-review
```
Run `/bmad-code-review` in <project_root>, reviewing the changes on the current branch for
story <story_file> (review the branch diff against the base branch).
Persist findings to the story file's `### Review Findings` section (the skill writes
`[Review][Patch]`, `[Review][Decision]`, and `[Review][Defer]` items there). Report the verdict
(Approve / Changes Requested / Blocked), the Critical/High/Med/Low counts, AND the count of
open `[Review][Decision]` items (they need a human call — see `pipeline.md` Phase 7).
```

### code-review fix
```
Run `/bmad-dev-story <story_file>` in <project_root>, focused ONLY on the open code-review
findings under the story's `### Review Findings` section: resolve every unchecked `[Review][Patch]`
item, plus each `[Review][Decision]` item for which a human-chosen fix direction is listed below.
Implement each in the stated direction and check it off. NEVER invent a direction for a
`[Review][Decision]` item with no chosen direction — leave it unchecked. Make tests pass.
Do not commit.

Resolved decisions (implement exactly these): {decisions}
```
(The orchestrator fills `{decisions}` from the Phase 7 AskUserQuestion answers, or omits the line
when there are none.)

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

### testarch-trace (epic gate)
```
Run `/bmad-testarch-trace` in <project_root> for epic {e}. Build the traceability matrix and
produce the quality-gate decision. Report the gate verdict (PASS/CONCERNS/FAIL/WAIVED) + rationale.
```

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
Run `/bmad-generate-project-context` in <project_root>. Update project-context.md to reflect the
current stack, patterns, and conventions after epic {e}. Use sensible defaults for any prompt.
```

### retrospective
```
Run `/bmad-retrospective` in <project_root> for epic {e}.
You are the sole facilitator AND participant — answer all party-mode questions yourself using
the accumulated notes at _bmad-output/auto-bmad/retro-notes/epic-{e}.md plus the story files and
sprint-status. Produce the full retrospective document and mark the epic retrospective `done`.
```

### git ops (preflight / branch / commits / finalize / PR) — **not delegated**
Git/PR work is run by the **orchestrator itself**, never by a delegate — so there is no
delegation prompt for it. See `git-and-pr.md` for the exact commands.
