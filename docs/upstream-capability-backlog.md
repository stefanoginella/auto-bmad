# Upstream capability backlog

Upstream BMAD/TEA capabilities auto-bmad has **seen and deliberately deferred** —
"nice, not needed (yet)". This is a maintainer backlog, not a changelog: nothing
here has shipped. Each entry records *why* we passed and a concrete **revisit
trigger** so the decision is re-examined when the ground actually shifts.

The `/auto-bmad-compat-check` skill consults this file in **Step 4** on every run:
for each entry, if that run's diff touches the entry's *Revisit when* trigger, the
reviewer re-surfaces it in the report instead of letting it quietly age out. Add an
entry whenever a compat check concludes "real capability, but no fit today"; remove
one once it ships (with a CHANGELOG note) or is judged a permanent non-fit.

## Open

### `bmad-build-auto` native unattended dev loop (parallel approach, not a building block)

- **What it is:** `bmad-method` 6.9.1-next.1 (PR #2500) adds `bmad-dev-auto` — a
  single skill that runs *"one iteration of an unattended development loop"*:
  clarify+route → plan (spec) → implement → 2-lens review (Blind + Edge Case
  Hunter), fully autonomous, no human interaction. It's built on the **quick-dev /
  spec lane** (`spec-template.md`, `<intent-contract>`, structured
  `deferred-work.md`), HALTs with a `status` verdict, and is meant to be looped
  externally.
- **Why nice:** it's BMAD's own native autonomous loop — conceptually the same
  problem auto-bmad solves, now with first-party support.
- **Why deferred:** it overlaps auto-bmad's *entire* orchestration role at lower
  fidelity, not a single phase. It rides the thin quick-dev/spec lane (no
  create-story/dev-story, no TEA gate, no code-review fan-out + security lens, no
  retro, no git branch/PR, no epic mode, no per-phase model+effort tuning) — so it
  doesn't slot into a phase; adopting it would *replace* Phases 2–7 with one
  delegate and discard auto-bmad's differentiators. Off auto-bmad's delegated
  surface (`low`), so **not** a compatibility risk.
- **Revisit when:** `bmad-dev-auto` graduates to stable **and** gains story-workflow
  / TEA / git-PR integration (i.e. becomes a richer loop that genuinely overlaps the
  full BMM story pipeline auto-bmad drives), **or** if auto-bmad ever adds a
  lightweight/freeform non-story lane — at which point delegating to it could be a
  real fit instead of a wholesale replacement.
- **First noted:** 2026-06-23 compat check (BMAD `6.9.1-next.1`, PR #2500).
- **Re-confirmed:** 2026-07-30 compat check (BMAD `6.10.1-next.34`) — the trigger
  fired *partially*, and the lane around it moved a lot. `bmad-quick-dev` was
  promoted to BMAD's **official Phase 4 implementation method** and renamed
  **`bmad-build`** (PRs #2637, #2651); `bmad-dev-auto` renamed to
  **`bmad-build-auto`**. `bmad-create-story` / `bmad-dev-story` are now **deprecated
  in place** (PR #2641): moved under `src/bmm-skills/v6-shims/`, description swapped
  to *"Only use this when explicitly invoked by name"*, and dropped from
  `module-help.csv` — but **retained in full** (templates/checklists byte-identical),
  with removal explicitly riding the **v7 cut, never a 6.x minor**. auto-bmad
  invokes both by name, which is exactly the path the shim preserves, so the story
  lane is safe for all of 6.x. The deferral **stands**: `bmad-build-auto` is still
  prerelease-only and still has no TEA gate, git/PR, retro, epic mode, or
  code-review fan-out — adopting it would still replace Phases 2–7 wholesale. What
  changed is the clock, not the fit.
- **Also watch:** `bmad-build-auto` now **hard-requires `uv`** (its SKILL.md HALTs
  when `uv` is unavailable). No skill auto-bmad delegates has converted — see the
  `uv run` entry below, whose trigger has **not** fired.
- **Revisit sooner if:** BMAD announces a v7 timeline, or any `bmad-build*` gains
  TEA / git-PR / epic integration — the first would put a removal date on the lane
  auto-bmad rides, the second would make delegation a real fit.

### Consume upstream `action_items` (sprint-status.yaml)

- **What it is:** `bmad-retrospective` (since `bmad-method` 6.8.1-next.x, PR #2465)
  appends a structured top-level `action_items:` section to `sprint-status.yaml` —
  a list of `epic` / `action` / `owner` / `status` (`open → in-progress → done`)
  entries it updates across epics; `bmad-sprint-status` surfaces the open ones.
- **Why nice:** it's a machine-readable mirror of the retro document's prose
  "Action Items" section that auto-bmad's create-story feed already reads at the
  first story of an epic (`auto-bmad/references/delegation.md`, the retro
  forward-feed). In **epic mode** it could deterministically seed epic N+1 prep
  from epic N's retro instead of relying on the delegate to extract it from prose.
- **Why deferred:** create-story already mines these items from the retro prose, so
  reading the structured field is only a marginal robustness gain — no new
  capability. Purely additive to a file auto-bmad parses (`story_plan.py` stops at
  the `development_status` block boundary), so it is **not** a compatibility risk.
- **Revisit when:** any further `bmad-retrospective` or `bmad-sprint-*` change to
  the `action_items` shape, **or** if we rework the epic-transition forward-feed /
  epic-mode prep (`delegation.md` retro feed, `epic-pipeline.md`) for other reasons
  — at which point consuming the structured field becomes nearly free.
- **Re-confirmed:** 2026-08-04 compat check (BMAD `6.10.1-next.49`, PR #2612) — the
  trigger fired: the evidence-based retrospective rework gives each item a stable
  `id` (`epic-<N>-retro-item-<n>-<slug>`) and a `ref` back to the retro document,
  explicitly *"so an orchestrator can dedupe items across re-runs and dispatch each
  one to its full, sourced finding"*. That is a materially better feed than prose
  mining — but it lands only on 6.10.1+, while auto-bmad still supports 6.10.0,
  so consuming it means carrying both paths. Deferral stands until the 6.10.1 line
  is the floor. Track alongside the retro `verdict` entry below, which lands with it.
- **First noted:** 2026-06-18 compat check (BMAD `6.8.1-next.14`).
- **Re-confirmed:** 2026-06-21 compat check (BMAD `6.8.1-next.17`, PR #2465) — the
  revisit trigger fired (the `action_items` write/transition rules were hardened and
  three skills now coordinate on the field: `bmad-retrospective` writes,
  `bmad-sprint-planning` carries over, `bmad-sprint-status` surfaces). The field
  *shape* (`epic`/`action`/`owner`/`status`) is unchanged, so the deferral stands.

### BMAD v7 standardizes Python on `uv run` (watch, not a capability)

- **What it is:** `bmad-method` 6.9.0 (PR #2495) flags an **upcoming v7 breaking
  change** — every skill that runs a Python script will invoke `uv run` instead of
  calling `python3` directly. In 6.9.0 it's warning-only: the installer checks for
  `uv` and points you to setup if it's missing, but a missing `uv` never blocks.
- **Why it matters to us:** auto-bmad delegates by *invoking* BMAD skills, so the
  environment those skills shell out from is BMAD's concern, not a contract we
  parse — no impact today. But if v7 makes `uv` a hard prerequisite for the
  delegated skills (create-story/dev-story/code-review/…), users provisioning
  auto-bmad would need `uv` present, which the README "Install/Updating" guidance
  may need to mention. auto-bmad's *own* scripts stay stdlib-only `python3` and are
  unaffected either way (and must not gain a `uv` dependency — see CLAUDE.md).
- **Why no action now:** 6.x only warns; nothing auto-bmad runs or delegates
  changes behavior. Acting now would document a requirement that doesn't yet exist.
- **Revisit when:** BMAD v7 ships (or a `next` prerelease flips a delegated skill
  from `python3` to a required `uv run`), **or** any installer/`tools/` change that
  makes `uv` a hard install gate — at which point weigh a README "Install/Updating"
  note. Cross-check CLAUDE.md "Known platform facts" (BMAD install/update channels).
- **First noted:** 2026-06-22 compat check (BMAD `6.9.0`, PR #2495).
- **TRIGGER FIRED:** 2026-08-04 compat check (BMAD `6.10.1-next.49`) — the prerelease
  line now has delegated skills whose *mechanics* run through `uv run`:
  `bmad-retrospective` (rewritten with `sprint_status.py` / `git_evidence.py`, PR
  #2612), `bmad-sprint-planning` (PR #2659), and the new `bmad-project-context`
  (PR #2674). `bmad-create-story`, `bmad-dev-story`, and `bmad-code-review` are still
  `uv`-free, so the core story lane is unaffected — but the epic-end closing phase
  is not. The `generate-project-context` delegate entry now states the dependency and
  its failure mode; **still open** is the README "Install/Updating" note, which should
  land when 6.10.1 goes stable rather than while it is prerelease-only.

### Gate the epic on the retrospective's machine-readable `verdict`

- **What it is:** `bmad-method` 6.10.1-next.x (PR #2612) rewrote `bmad-retrospective`
  as an evidence engine that opens its document with YAML frontmatter carrying
  `verdict: accepted | accepted-with-open-items | rejected`. Its `retro-document.md`
  states the intent outright — *"an epic gate or orchestrator keys off `verdict` to
  decide whether to hold the next epic"* — and warns that sprint-status alone
  **cannot** tell a rejected epic from an accepted one, because the retro key reads
  `done` either way (`done` means *the retrospective ran*, not *the epic passed*).
- **Why nice:** epic mode currently closes an epic on Phase 8 completion and only
  surfaces a prose `Planning drift` line. A rejected verdict is exactly the signal
  that should halt the run before the next epic, and it costs one frontmatter read.
- **Why deferred:** it exists only on 6.10.1+, and auto-bmad still supports 6.10.0
  where the field is absent — so shipping it means a new halt that silently never
  fires on half the supported range, plus new state/report fields
  (`state-and-resume.md`, `state_update.py`) and an epic-mode decision about whether
  a `rejected` epic blocks or warns. That is a pipeline-behavior change, not a
  prompt fix, so it wants its own change rather than riding a compat pass.
- **Revisit when:** BMAD 6.10.1 ships **stable** (making the field reliably present),
  **or** we touch Phase 8 / `E8b` closing for other reasons. Land it together with
  the structured `action_items` entry above — same rework, same release floor.
- **First noted:** 2026-08-04 compat check (BMAD `6.10.1-next.49`, PR #2612).

### `tea-test-review` CLI as a headless review runner

- **What it is:** TEA 1.20.0 ships a `tea-test-review` binary — a headless runner for
  the `bmad-testarch-test-review` skill with per-vendor agent adapters (`claude`,
  `codex`), pinned review models, changed-test scoping from a PR diff, waivers with
  expiry, minimum-evidence floors, strict report validation, and CI exit codes.
- **Why nice:** it is the same "drive a skill headlessly and parse a structured
  verdict" shape as auto-bmad's `delegation.cli_phases` external-CLI route, with
  real gate semantics already built.
- **Why deferred:** it is built to be a *required PR gate in CI*, not a pipeline step
  — it brings its own filesystem isolation, its own agent/model resolution, and its
  own waiver vocabulary, all of which duplicate or fight the delegation tiers
  (`delegation-runtime.md`). Phase 8's in-tool delegate already gets the same skill at
  the profile's tuned model. Adopting it would mean auto-bmad shelling to a TEA-owned
  runner that re-implements the routing auto-bmad exists to own.
- **Revisit when:** auto-bmad grows a CI-gate mode (running as a PR check rather than
  an interactive pipeline), **or** TEA ships an equivalent headless runner for the
  *blocking* `bmad-testarch-trace` gate — at which point a structured trace verdict
  from a CLI would beat parsing a delegate's prose return.
- **First noted:** 2026-08-04 compat check (TEA `1.21.3`, PRs from the 1.20.0 line).
