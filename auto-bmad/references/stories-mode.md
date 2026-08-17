# Stories mode — the spec-folder story source

What it is: the complete delta for `story_source: stories` — a **spec folder** written by `bmad-spec` (`SPEC.md` + `stories.yaml` + `stories/{id}-*.md`) replaces `sprint-status.yaml` + the epics documents as the story source. Everything not listed here is identical to sprint mode.
When it is loaded: ONLY when this run resolved `story_source: stories` (an explicit `--spec <folder>`, an auto-detect confirm, or a resume whose state says so). A sprint-mode run never reads it.

## 1. What it is (upstream facts — do not re-derive)

- A **spec folder** (`{output_folder}/specs/spec-{slug}/` by default) holds `SPEC.md`, its companions, `.memlog.md`, and — once the user ran `bmad-spec` "break this into stories" — `stories.yaml`.
- `stories.yaml` is a top-level list, **execution order = list order** (never filename sort). Per entry: `id` (quoted string, unique, prefix-free), `title`, `description`, plus the caller-only `spec_checkpoint`, `done_checkpoint`, `invoke_dev_with`. **There is no `status` field, ever.**
- `bmad-build-auto` accepts a **folder+id dispatch**: a spec folder + a story id, no spec path. It reads that one entry's `title`+`description`, matches `{spec_folder}/stories/{id}-*.md` and routes by **that file's frontmatter `status`** (none ⇒ first dispatch, plans `stories/{id}-{slug}.md`; `draft` ⇒ plan; `ready-for-dev`/`in-progress` ⇒ implement; `in-review` ⇒ review; `done` ⇒ fresh review pass; `blocked` ⇒ HALT `story already blocked`; >1 match ⇒ HALT `ambiguous story file match`). One entry per invocation — it never advances to another id.
- **The story file's `status` is the only status, and build-auto owns it.** auto-bmad never writes it (it never edits the spec) — so stories mode has **no status write-back anywhere**.
- Every HALT lands at the id-keyed story file (`{id}-unresolved.md` when the entry could not be resolved, `{id}-ambiguous.md` on an ambiguous match). Under folder+id a `bmad-build-auto-result-*.md` is **never** written.
- `bmad-retrospective` has a stories mode: **a named folder is stories mode**; it reads `stories.yaml` order + each story file's status and writes `{spec_folder}/RETROSPECTIVE.md` (fixed name), with **no** `sprint_status.py` call and no sprint file. Headless requires the explicit folder.

**The orchestrator never opens `SPEC.md`, `stories.yaml` or a story file itself** — every read goes through `story_plan.py` (`--discover-specs`, `--resolve`, `--stories`, `--find-spec`, `--spec`, `--retro-verdict`).

## 2. Route selection (Phase 0 step 2 / E0 step 2 — before anything else)

Resolve the source in this order; **never choose silently**:

1. **Resume wins.** `state_plan.py` returned an in-flight target (per-story) or anchor (epic) ⇒ take `story_source` / `spec_folder` / `story_id` from that state file. No detection, no ask. (Story keys `spec-{spec_slug}-{id}` can never match the sprint key grammar, so the two sources never collide.)
2. **Explicit `--spec <folder>`** ⇒ stories mode, that folder. Forms: `/auto-bmad --spec <folder>`, `/auto-bmad --spec <folder> --story <id>`, `/auto-bmad epic --spec <folder>`. `--spec` and `--epic N` in one invocation ⇒ hard-stop `` `--spec` selects a spec folder; `--epic` selects a sprint epic — pick one ``.
3. **No `--spec`, and `<impl>/sprint-status.yaml` exists** (`test -f`) ⇒ **sprint mode**, unchanged.
4. **No `--spec` and no `sprint-status.yaml`** ⇒ auto-detect:
   ```
   python3 {skill-root}/scripts/story_plan.py --discover-specs --roots <output_folder>/specs <planning> <impl>
   ```
   - **0 candidates** ⇒ the "no story source" stop: `no sprint-status.yaml and no stories.yaml found — run /bmad-sprint-planning to generate the sprint status, or /bmad-spec "break this into stories" to produce a stories.yaml in a spec folder`. Stop.
   - **1 candidate** ⇒ `AskUserQuestion`: "Use spec folder `<spec_folder>` (`<epic_title>`, `<story_count>` stories, `<done_count>` done)?" — **Use it** / **Stop**.
   - **2–4 candidates** ⇒ `AskUserQuestion` with one option per candidate (same label shape) + **Stop**.
   - **> 4 candidates** ⇒ print the full list (path, title, `n` stories, `m` done) and stop with `re-run with /auto-bmad --spec <folder>`.
   - A **dry run** never asks: print the candidates as a note and stop before Phase 1 (Phase 0 step 0's rule).
5. Record the verdict in Phase 1's `init --json`: `story_source: stories`, `spec_folder` (absolute), `story_id`; `epic_num`/`story_num`/`story_suffix` are `null`.
   - A hard-stop **before** that `init` still writes its report section (`SKILL.md` Step 3's pre-init fallback) — add the identity to the call: `state_update.py report-section --allow-missing-state --story-source stories --story-id <id> [--spec-folder <spec_folder>]`. The three flags are honoured **only** together with `--allow-missing-state` (a usage error otherwise) and make the header read `(spec {spec_slug}, story {id})` instead of an empty sprint identity.

**Story pick when no `--story` was given** (Phase 0 step 5 — there is no `sprint_plan.py status` picker in stories mode):
```
python3 {skill-root}/scripts/story_plan.py --stories --spec-folder <spec_folder>
```
- `hard_stop` ⇒ surface `hard_stop_reason` verbatim and stop (missing/unparseable `stories.yaml`, missing `SPEC.md`, invalid ids).
- `all_done: true` (`next_story_key` null) ⇒ the not-silent stop `all stories in <spec_folder> are done — nothing for auto-bmad to run` + `(retrospective is still optional: run /bmad-retrospective <spec_folder>)` when `retrospective_status` is null.
- Else target = `next_story_key` (first entry in list order whose status ≠ `done`); its entry's `status: blocked` ⇒ **needs-human** stop (build-auto halted this story; the recovery text below applies).
- Then `state_plan.py --state-dir … --story-key {key}` exactly as in sprint mode.

**`--story <arg>` in stories mode** ⇒ `story_plan.py --resolve <arg> --spec-folder <spec_folder>`: exact `id` > exact story key > case-insensitive substring of `title`/slug; ambiguous ⇒ hard-stop listing `candidates`. The sprint `E-S` / `E.S` / `E-Sx` grammar does not apply.

**Echo every `warnings` entry** returned by `--discover-specs`, `--stories` and `--resolve` — in the Phase 0 console echo and again in the report's Needs human list, the same treatment `preflight.py` warnings get. They flag `stories.yaml` shapes build-auto's own parser may read differently (an unquoted value containing `: `, a second YAML document, an unreadable candidate directory), so dropping them hides a failure that lands later inside build-auto.

**Preflight** (Phase 0 step 3) gains `--story-source stories --spec-folder <spec_folder>`:
- `bmad-sprint-planning` **may stay in the `--require-skills` CSV** — `--story-source stories` downgrades its absence, and a missing `sprint_plan.py`, to a **warning** instead of a hard-stop. Nothing in stories mode calls it.
- `skills.build_auto_folder_id` other than `true` (`false`, or `null` when step-01 was not found) ⇒ **hard-stop** (surface it verbatim): the installed `bmad-build-auto` has no folder+id dispatch — update BMAD to ≥ 6.11.0.
- `bmad-retrospective` stays required.

## 3. Identity & naming

`spec_slug` = the spec folder's basename minus a leading `spec-`. `story_label` / `epic_label` come from `story_plan.py` — never hand-built.

| thing | sprint mode | stories mode |
|---|---|---|
| story key | `{e}-{s}-{slug}` | `spec-{spec_slug}-{id}` |
| `{story_label}` (commit scope) | `story-{e}-{s}` | `story-{spec_slug}-{id}` |
| `{epic_label}` (commit scope) | `epic-{e}` | `spec-{spec_slug}` |
| state file | `state/{key}.yaml` | `state/spec-{spec_slug}-{id}.yaml` |
| report file | `reports/{key}.md` | `reports/spec-{spec_slug}-{id}.md` |
| epic anchor | `state/epic/epic-{e}.yaml` | `state/epic/spec-{spec_slug}.yaml` |
| epic report | `reports/epic-{e}.md` | `reports/spec-{spec_slug}.md` |
| story branch | `{git.branch_prefix}{e}-{s}-{slug}` | `{git.branch_prefix}{spec_slug}-{id}-{slug}` (`{slug}` = kebab-case of `title`) |
| epic branch | `{git.epic_branch_prefix}{e}-{slug}` | `{git.epic_branch_prefix}{spec_slug}` |
| story PR title | `feat(story-{e}-{s}): {title}` | `feat(story-{spec_slug}-{id}): {title}` |
| epic PR title | `feat(epic-{e}): <epic summary>` | `feat(spec-{spec_slug}): {epic_title}` |
| base-readiness pattern | `git branch --list "{git.branch_prefix}{e}-{s}-*"` | `git branch --list "{git.branch_prefix}{spec_slug}-{id}-*"` |
| epic test-design doc | `test-design-epic-{e}.md` | `test-design-spec-{spec_slug}.md` |
| `<epic_start>` grep (per-story mode) | `^chore(story-{e}-` | `^chore(story-{spec_slug}-` |
| `<spec_path>` | `<impl>/spec-{e}-{s}-<slug>.md` | `{spec_folder}/stories/{id}-<slug>.md` |

`epic_title` = `SPEC.md`'s frontmatter `title` → its first `#` heading → `spec_slug` (from `story_plan.py`; never a grep).

## 4. Status vocabulary

The story file's frontmatter status maps onto the pipeline's existing vocabulary — `story_plan.py` does the mapping; use `current_status` / `status`, and `story_file_status` only where this file says so.

| story file (`stories/{id}-*.md`) | pipeline status | notes |
|---|---|---|
| *(no file)* | `backlog` | not started — fresh loop body |
| `draft` | `backlog` + `draft_spec: true` | planning was interrupted; Phase 3 re-dispatches (folder+id resumes it). `draft_spec` is **informational only** — the story pick treats the entry as `backlog`; nothing branches on it |
| `ready-for-dev` | `ready-for-dev` | plan done — Phase 3 adopts, no plan delegate |
| `in-progress` | `in-progress` | build interrupted |
| `in-review` | `review` | build done, review pending |
| `done` | `done` | complete |
| `blocked` | `blocked` | needs-human (recovery text below) |
| *(unreadable, no frontmatter, unrecognized status, or an ambiguous `{id}-*.md` match)* | `null` | **hard-stop, needs-human** — `--stories` still enumerates but sets `hard_stop` and never points `next_story_key` at it; `--resolve` on that id exits 1. Surface `hard_stop_reason` **and** `warnings` verbatim; the human fixes `stories/{id}-*.md` by hand (build-auto would HALT `unrecognized status in existing story file` / `ambiguous story file match`) |

`epic_status`: all `done` ⇒ `done`; any story not `backlog` ⇒ `in-progress`; else `backlog`. `retrospective_status`: `done` when `{spec_folder}/RETROSPECTIVE.md` exists, else null.

## 5. Dispatch — folder+id, every time

**Never pass a spec path to build-auto in stories mode** — not for the plan run, not for the build run, not for a follow-up review pass. Folder+id routes by the on-disk story file's status, which is exactly the resume behaviour the pipeline wants. The **`build-plan`**, **`build-run`** and **`followup-review`** entries of `delegation.md` each carry a *Stories mode variant* — use that fence verbatim. The invocation intent it hands build-auto is always:

```
Spec folder `{spec_folder}` (absolute path), story id "{story_id}" — folder+id dispatch: do not pass a spec
file path. Branch `{branch}` is the intended branch for this work (judge it against the epic). [Halt after planning.]
```
- `Halt after planning.` on the plan run only.
- **`{invoke_dev_with}` rides the plan run ONLY** — the entry's field **verbatim**, after a blank line, when non-empty. Only a first/`draft` dispatch carries extra prompt text into build-auto's planning step; on the build run that text becomes the implementation handoff (a disagreement with the story file HALTs `handoff conflicts with spec`) and on a follow-up review pass it becomes the reviewed intent. It is planning context, never scope.
- Every entry's Status ask becomes: return the absolute path of the id-keyed story file `{spec_folder}/stories/{id}-*.md`. There is no `bmad-build-auto-result-*.md` to report, and no `epic-{e}-context.md` is ever written.

## 6. Per-phase deltas

| Phase | Delta |
|---|---|
| **0** | Route selection + story pick per §2; preflight `--story-source stories --spec-folder`; **no** `sprint_plan.py status` call anywhere; the `build-plan` prompt's `{carry_over_block}` is always empty (no `open_action_items` source) — omit the block, and do not invent a report field for it; retro-verdict gate (step 7) = `story_plan.py --retro-verdict --spec-folder <spec_folder>` on this folder's `RETROSPECTIVE.md` (absent ⇒ skip; `rejected` ⇒ the same ask, worded "This spec folder's retrospective verdict is **rejected** (`<doc>`). Run more of its stories anyway?" — options **Proceed** / **Stop — resolve this spec's retrospective first**); step 5's epic facts come from `--stories` / `--resolve`, not `--epic`. |
| **1** | Branch + commit subjects use `{story_label}` (§3). |
| **2** | Epic-start test design runs on `is_first_in_epic` as usual; the delegate targets the spec folder, doc `test-design-spec-{spec_slug}.md`; commit `test({epic_label}): epic-level test design`. |
| **3** | Folder+id plan dispatch (§5). Spec locate after the halt: `story_plan.py --find-spec --spec-folder <spec_folder> --story-id {story_id}` — `ambiguous: true` ⇒ hard-stop listing `candidates` (mirrors build-auto's own `ambiguous story file match`); `found: false` means build-auto never HALTed (it always writes the id-keyed file) ⇒ Blocked handling with **no leftover result file** to commit. **No `--mark-status`** — the story file already carries `ready-for-dev`. Commit `docs({story_label}): plan spec` (the untracked story file + state; there is no `epic-{e}-context.md` under folder+id). Approval halt: run it when `build.spec_approval` is true **OR** the entry's `spec_checkpoint` is true **OR** this run's instructions ask for it (§7). |
| **4** | Unchanged (`<spec_path>` = the story file). |
| **5** | **No `in-progress` flip and no epic lift** — step 1 is only the clean-tree gate; when it needs a commit the subject is `chore({story_label}): pipeline state` (the `mark in-progress` subject does not exist here). Build via folder+id. **No `review` flip** — the `phase-done --phase 5` write folds into the next phase's commit, or, if a build-auto invocation comes first, into the clean-tree gate's `chore({story_label}): pipeline state` commit. Stragglers build-auto left uncommitted ride that commit with the same warning. |
| **6** | Unchanged. |
| **7** | Unchanged — the halt, the git-only external-change check, the re-review, the trace advisory and the deferred harvest (`<impl>/deferred-work.md`) all work as written; only the commit scopes change. |
| **8** | Steps 1–3 unchanged. **Step 4 (pre-retro flip) does not exist** — record the marker as done and leave `bmad_status_flipped_at: null`. Step 5 retrospective: delegate `/bmad-retrospective -H <spec_folder>` (a named folder is stories mode; it writes `{spec_folder}/RETROSPECTIVE.md` and makes no `sprint_status.py` call); read the verdict with `story_plan.py --retro-verdict --spec-folder <spec_folder>`; `retro.open_action_items: null` (no scripted source — the doc's action items are surfaced from the delegate's result only). Commit `docs({epic_label}): gate, deferred-work reconcile + archive, retrospective`. |
| **9** | `python3 {skill-root}/scripts/state_plan.py --state-dir … --story-key {key} --finalize --story-source stories [--ci-status …] [--no-pr-draft]` ⇒ `flip_bmad_status: false` with the reason `stories mode: no BMAD-status flip (build-auto owns the story-file status)`; `clean_completion` / `draft` are unchanged and still drive the draft PR, the merge prompt and the report's clean-vs-caveated line. **No flip**; `bmad_status_flipped_at` stays `null`. Finalize commit `chore({story_label}): finalize (mark done)`. |

**Recovery after a build-auto `blocked`** — the `pipeline.md` template with these stories-mode differences:
- the `Spec:` line is always the id-keyed story file `{spec_folder}/stories/{id}-*.md` (a pre-planning halt lands at `{id}-unresolved.md`, an ambiguous on-disk match at `{id}-ambiguous.md`); there is never a `bmad-build-auto-result-*.md`;
- **a halt that landed at `{id}-unresolved.md` or `{id}-ambiguous.md`: step 2 is not "edit its `status:`" but "fix `stories.yaml` (or the duplicate story files), then DELETE or RENAME that file"** — build-auto routes by whatever matches `stories/{id}-*.md`, so leaving `{id}-unresolved.md` at `draft` makes it plan into the placeholder, and leaving `{id}-ambiguous.md` next to the real story file keeps the `ambiguous story file match` HALT permanent;
- step 3's command is `Re-run /auto-bmad --spec <spec_folder> --story {story_id}` (epic mode: `/auto-bmad epic --spec <spec_folder>`), and the re-run **re-dispatches by folder+id, never by a spec path** — the story file's own `status` is what picks the step to resume at;
- the `missing previous-story continuity decision` special case cannot occur under folder+id — drop that line; the `no subagents` and `finalization left repository dirty` cases stand.

## 7. Checkpoints (`spec_checkpoint` / `done_checkpoint`)

Both are caller-only fields the orchestrator honours **in per-story AND epic mode** — they override epic mode's "no per-story human checkpoints" rule. Both values come from `story_plan.py --resolve` / `--stories`; build-auto never sees them.

- **`spec_checkpoint: true`** ⇒ the Phase 3 spec-approval halt runs for that story, in both modes, exactly as `pipeline.md` P3.6 defines it (`timing-pause` before the ask, `timing-start` after; Stop ⇒ `(halted — spec approval pending)`, resumable — the resume re-opens the halt). In epic mode the resume command is `/auto-bmad epic --spec <spec_folder>`.
- **`done_checkpoint: true`**:
  - *per-story mode* — the run stops after that story anyway; record it in the report ("`done_checkpoint` on story `{story_id}`") and do nothing else.
  - *epic mode* — after E5h has landed that story (the anchor write is complete, so the stop is clean): `timing-pause` on the anchor, then `AskUserQuestion` "`done_checkpoint` on story `{story_id}` (`{title}`) — continue the epic?" — **Continue the epic** / **Stop here**. Continue ⇒ `timing-start`, next story. Stop ⇒ a **resumable stop**: the anchor stays in-flight (`active_story` = the next work-list key), commits stay on the branch, no push, no PR, outcome `stopped`, report tagged `(halted — done_checkpoint on story {story_id})`; re-run `/auto-bmad epic --spec <spec_folder>` to continue.
- **E0.11's unattended confirm must list both** — after the work list, name the stories that will pause and why: "`spec_checkpoint` on story `{id}` (spec approval after planning)", "`done_checkpoint` on story `{id}` (stops after it lands)". An epic whose entries carry no checkpoint reads exactly as today.

## 8. Epic mode (E-step deltas)

`/auto-bmad epic --spec <folder>` — **the spec folder IS the epic**. On top of §§3–7:

| E-step | Delta |
|---|---|
| **E0.2** | Anchor pre-read: an in-flight anchor matches when its `spec_folder` equals the target folder (there is no `epic_num`); anchor key `spec-{spec_slug}`. |
| **E0.5** | No picker call and no `{e}` resolution — the folder is given (or auto-detected per §2). `{carry_over_block}` is always empty. |
| **E0.6** | Enumerate with `story_plan.py --stories --spec-folder <folder>`: `epic_stories[]` in list order (`key`, `story_id`, `status`, `story_file_status`, `title`, `is_first_in_epic`, `is_last_in_epic`, `stories_after_in_epic`, the checkpoint fields, `invoke_dev_with`). `hard_stop` ⇒ stop; `all_done: true` ⇒ hard-stop `every story in <folder> is done`. |
| **E0.7** | The adopt matrix keys on `story_file_status`: *(no file)* / `draft` / `ready-for-dev` ⇒ fresh loop body (Phase 3's resume matrix adopts or re-plans); `in-progress` and `in-review` ⇒ exactly the sprint rules (with a per-story state file ⇒ the git branch check, then resume in E5; without one ⇒ the ASK — `in-progress` adopt at Phase 5, `in-review` adopt at Phase 7 — or Skip); `done` ⇒ skip (`already done`); `blocked` ⇒ auto-skip with the E0 note `story {id} is blocked — resolve it with /auto-bmad --spec <folder> --story {id}`. No `--find-spec` probe is needed to distinguish the cases — the story file's own status is the answer. |
| **E0.8** | Base-readiness guard: same git-only check, pattern `{git.branch_prefix}{spec_slug}-{id}-*`. |
| **E0.9** | Epic slug = `spec_slug` (no title kebab-casing); epic branch `{git.epic_branch_prefix}{spec_slug}`. |
| **E0.10** | Retro gate reads **this** folder's `RETROSPECTIVE.md` (`--retro-verdict --spec-folder`); absent ⇒ skip. The sprint `e == 1` skip has no analogue. |
| **E0.11** | The unattended confirm names the spec folder and its title, and lists the checkpoint pauses (§7). |
| **E5g** | Nothing to leave at `review` — there is no sprint entry. |
| **E5h** | Unchanged, plus the `done_checkpoint` ask (§7) immediately after the anchor write. |
| **E8b.3 / E_final.4** | **No batch flip** — record `batch_flip_done: true` (vacuously) and leave `bmad_status_flipped_at: null`. The draft predicate / `clean_completion` still decide the draft PR and the merge prompt. |
| **E8b.4** | Retrospective per §6 Phase 8; verdict + doc land on the anchor and gate the next run against this folder (E0.10). |
| **E_final** | Report `reports/spec-{spec_slug}.md`; PR title `feat(spec-{spec_slug}): {epic_title}`; the PR body's `## Open action items` section is omitted (no source); finalize commit `chore({epic_label}): finalize (mark done)` — no "+ BMAD status", nothing is flipped; the final-status line reads clean vs caveated without a status flip. |

Every epic-scoped commit subject substitutes `{epic_label}` for `epic-{e}` (`chore(spec-{spec_slug}): start auto-bmad epic pipeline`, `docs(spec-{spec_slug}): pipeline report`, …).

## 9. TEA

- **`tea-triage` input** = the `stories.yaml` entry's `title` + `description` (two sentences by convention) plus `{spec_folder}/SPEC.md` for context — no epics document. Thinner input, so `tea-policy.md`'s "when in doubt, pick the higher tier" carries more weight.
- `is_first_in_epic` / `is_last_in_epic` / `epic_story_count` / `stories_after_in_epic` are **list-order** facts from `--resolve` / `--stories`; `tea-policy.md` §3's advisory gates read them unchanged.
- Epic-scoped TEA entries name the spec folder instead of "epic {e}"; the story-scoped ones take `<spec_path>` (the story file) unchanged.

## 10. Unchanged in stories mode

Delegation tiers and the foreground rule (`delegation-runtime.md`); the `cli_phases` external-CLI route (`cli-route.md`); every git rule in `git-and-pr.md` except the write-back line and the naming forms of §3 — branching off base, the clean-tree gate, one commit per phase, the sha-lag `commits[]` rule, the draft predicate (clauses 1–4), push/PR/CI wait/merge prompt; the deferred-work ledger at `<impl>/deferred-work.md` (harvest, reconcile, archive); the security + cross-model review layers inside build-auto; state/report mechanics, timing brackets, outcome vocabulary and Blocked handling.
