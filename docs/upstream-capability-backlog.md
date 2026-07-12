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

### `bmad-dev-auto` native unattended dev loop (parallel approach, not a building block)

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
