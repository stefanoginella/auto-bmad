# Upstream capability backlog

Upstream BMAD/TEA capabilities auto-bmad has **seen and deliberately deferred** —
"nice, not needed (yet)". This is a maintainer backlog, not a changelog: nothing
under **Open** has shipped. Each entry records *why* we passed and a concrete
**revisit trigger** so the decision is re-examined when the ground actually shifts.

The `/auto-bmad-compat-check` skill consults this file in **Step 4** on every run:
for each entry, if that run's diff touches the entry's *Revisit when* trigger, the
reviewer re-surfaces it in the report instead of letting it quietly age out. Add an
entry whenever a compat check concludes "real capability, but no fit today"; move
one under **Closed** once it ships (with a CHANGELOG note) or is judged a permanent
non-fit — the closed record keeps the history without re-surfacing.

## Open

### `tea-test-review` CLI as a headless review runner

- **What it is:** a `tea-test-review` binary — a headless runner for the
  `bmad-testarch-test-review` skill. TEA 1.20.0 was the first release to ship the `bin`
  (per TEA's own `cli/examples/pr-test-review.yml` note); TEA 1.22.1 is where the
  CHANGELOG records the CLI in full — per-vendor agent adapters (`claude`, `codex`),
  pinned review models, changed-test scoping from a PR diff, waivers with expiry,
  minimum-evidence floors, strict report validation, and CI exit codes.
- **Why nice:** it is the same "drive a skill headlessly and parse a structured verdict"
  shape as auto-bmad's `delegation.cli_phases` external-CLI route, with real gate
  semantics already built.
- **Why deferred:** it is built to be a *required PR gate in CI*, not a pipeline step —
  it brings its own filesystem isolation, its own agent/model resolution, and its own
  waiver vocabulary, all of which duplicate or fight the delegation tiers
  (`delegation-runtime.md`). Phase 8's in-tool delegate already gets the same skill at
  the profile's tuned model. Adopting it would mean auto-bmad shelling to a TEA-owned
  runner that re-implements the routing auto-bmad exists to own.
- **Revisit when:** auto-bmad grows a CI-gate mode (running as a PR check rather than an
  interactive pipeline), **or** TEA ships an equivalent headless runner for the
  *blocking* `bmad-testarch-trace` gate — at which point a structured trace verdict from
  a CLI would beat parsing a delegate's prose return.
- **First noted:** 2026-08-04 compat check (TEA `1.21.3`, PRs from the 1.20.0 line).
- **Re-checked:** TEA `1.23.0` (auto-bmad 0.27.0 migration) — still no headless CLI for
  the *blocking* `bmad-testarch-trace` gate (the runner covers `test-review` only), and
  auto-bmad still has no CI-gate mode. Deferral stands; the trace gate stays a delegated
  in-tool run.

### `bmad-spec` stories mode — `stories.yaml` folder+id dispatch of `bmad-build-auto`

- **What it is:** `bmad-spec` (BMAD 6.11) can break a `SPEC.md` into a sibling
  `stories.yaml` (schema in `bmad-spec/assets/stories-schema.md`: ordered entries with
  `id` / `title` / `description` plus caller-only `spec_checkpoint` / `done_checkpoint`
  / `invoke_dev_with`). `bmad-build-auto` step-01 accepts a **folder+id dispatch** — a
  spec folder + a story id instead of a spec path — reads that one entry, plans
  `{spec_folder}/stories/{id}-{slug}.md` from `SPEC.md` and its companions, and never
  advances to another id.
- **Why nice:** it is the story source `bmad-spec` writes for "whichever tool dispatches
  the stories"; its checkpoint fields map onto auto-bmad's spec-approval halt and
  per-story stop.
- **Why deferred:** auto-bmad's story source is `sprint-status.yaml` + the epics
  documents (`story_plan.py --resolve/--epic`, `sprint_plan.py status`), and 0.27.0
  dispatches build-auto by intent (`Story {e}.{s} … Halt after planning.`) then by spec
  path. `stories.yaml` has no status field and no sprint-status write-back, so adopting
  it means a second story-source adapter, not a prompt change. The v7 spec/ticket tree
  is still uncommitted upstream — nothing in the `6.11.1-next.14` tree; per the
  migration plan's GitHub read on 2026-08-15 (`docs/v7-migration-plan.md`), PR #2672
  closed unmerged.
- **Revisit when:** the v7 spec/ticket tree becomes the primary story source (a
  `bmad-sprint-planning` or `bmad-build-auto` change that reads `stories.yaml` as the
  default), **or** a `bmad-build-auto` step-01 change to the folder+id contract — the
  single-adapter design (`story_plan.py`) is meant to make that a one-module swap.
- **First noted:** 2026-08-15 v7 migration read (BMAD `6.11.1-next.14`).

### TEA live-verification evidence (`live-verification-results.json`)

- **What it is:** TEA 1.22.1 taught `bmad-testarch-trace` to read
  `{test_artifacts}/live-verification-results.json` (`workflow.yaml`
  `live_results_input`) as a `live` coverage level — a producer-agnostic JSON contract
  (`docs/reference/live-verification-results.md`) for requirements verified by *running*
  the system rather than by a test file. Only a `pass` recorded against the commit under
  trace counts; live-only evidence caps the gate at CONCERNS.
- **Why nice:** a story whose ACs are verified live (a smoke run, a driven app) would
  stop scoring as uncovered in the Phase 7 advisory / Phase 8 epic gate — trace stays a
  consumer, so someone has to produce the file.
- **Why deferred:** auto-bmad never opens a TEA artifact and never runs the system;
  producing the file would be a new delegate (or a build-auto layer) with its own
  `source_sha` discipline, and the 0.27.0 gates already carry the CONCERNS advisory
  path. Additive to a file auto-bmad neither reads nor writes, so **not** a
  compatibility risk.
- **Revisit when:** a delegated skill (build-auto, atdd/automate) starts emitting the
  file, **or** the trace `live_results_input` / schema changes, **or** users report P0s
  failing the epic gate purely for lack of a test file.
- **First noted:** 2026-08-15 v7 migration read (TEA `1.23.0`; feature from `1.22.1`).

### TEA write-time enforcement hook (Claude Code only; expected, not managed)

- **What it is:** TEA 1.23.0's `bmad-testarch-framework` scaffolds a write-time hook
  into the target project — `.claude/hooks/tea-enforce.cjs`, its `.claude/settings.json`
  registration, and `.tea/enforce-config.json` (globs for the detected stack + the
  hook's sha256). It blocks the mechanically decidable `Absolute` criteria (`.only`,
  fixed sleeps, …) at write time on Claude Code.
- **Why nice:** it catches at the write what `test-review` only scores afterwards —
  including writes made by auto-bmad's delegated TEA runs.
- **Why deferred:** it is Claude Code-only (settings-hook mechanism), installed by a
  skill auto-bmad merely delegates (`framework_ci`), and fails open. auto-bmad's job is
  to **expect** those files (`tea-policy.md`: commit-worthy, not stray changes) — not to
  install, verify, or refresh them.
- **Revisit when:** TEA ships the hook for Codex/opencode, **or** makes it a hard
  prerequisite of `atdd`/`automate`, **or** the file set/paths change (the tea-policy
  note must follow).
- **First noted:** 2026-08-15 v7 migration read (TEA `1.23.0`).

### TEA `test_dir` passthrough

- **What it is:** every TEA workflow resolves `test_dir` (default
  `{project-root}/tests`, `workflow.yaml` `variables`) — `trace` discovers tests under
  it, `atdd`/`automate` write there. A project whose tests are co-located with the
  source gets incomplete discovery unless the variable is retuned per skill
  (`_bmad/custom/<skill>.toml` / `.user.toml`).
- **Why nice:** a single `tea.test_dir` in auto-bmad's runtime config, passed to every
  TEA delegate prompt, would fix discovery for co-located layouts without per-skill TOML
  edits.
- **Why deferred (decision, 0.27.0):** no `tea.test_dir` key. It duplicates TEA's own
  customization layer for one variable, and auto-bmad's prompts already override only
  what the *pipeline* needs (`gate_type`, `allow_gate`, `review_files`, `headless`); the
  per-skill TOML is the supported knob.
- **Revisit when:** TEA moves `test_dir` to `_bmad/tea/config.yaml` (module-level, one
  place), **or** users hit incomplete trace discovery on co-located layouts often enough
  that a README note is not enough.
- **First noted:** 2026-08-16 v7 migration decision (TEA `1.23.0`).

## Closed

Shipped entries stay here as history (the compat-check no longer re-surfaces them).

### `bmad-build-auto` native unattended dev loop — **shipped in 0.27.0**

- **What it was:** `bmad-method` 6.9.1-next.1 (PR #2500) added a single skill that runs
  *"one iteration of an unattended development loop"* on the quick-dev / spec lane —
  clarify+route → plan (spec) → implement → multi-layer review, HALTing with a `status`
  verdict, meant to be looped externally. Renamed `bmad-build-auto` when
  `bmad-quick-dev` became BMAD's official Phase 4 implementation method `bmad-build`
  (PRs #2637, #2651); the v6 story lane was deprecated in place under `v6-shims/` (PR
  #2641) with removal riding the v7 cut.
- **Why it was deferred:** through 6.10.x it overlapped auto-bmad's whole orchestration
  role at lower fidelity (no TEA gate, no git/PR, no retro, no epic mode, no independent
  review pass), so adopting it would have replaced Phases 2–7 wholesale rather than
  slotting into one.
- **How it closed:** BMAD 6.11 made `bmad-build-auto` the official unattended lane with
  a customizable review step (`_bmad/custom/bmad-build-auto.toml`
  `[[workflow.review_layers]]`) and a re-invoke-on-`done` review pass — exactly the
  hooks auto-bmad needed. 0.27.0 makes it the story primitive (plan → build → follow-up
  review) and keeps only what BMAD does not do around it (`docs/v7-migration-plan.md`).
- **First noted:** 2026-06-23 (BMAD `6.9.1-next.1`). **Re-confirmed:** 2026-07-30
  (`6.10.1-next.34`). **Closed:** 2026-08-16 (`6.11.1-next.14`).

### Consume upstream `action_items` (sprint-status.yaml) — **shipped in 0.27.0**

- **What it was:** `bmad-retrospective` (since `bmad-method` 6.8.1-next.x, PR #2465)
  appends a structured top-level `action_items:` section to `sprint-status.yaml` (`epic`
  / `action` / `owner` / `status`, later a stable `id` + `ref` per item — PR #2612 —
  *"so an orchestrator can dedupe items across re-runs"*); `bmad-sprint-planning`
  carries them over.
- **Why it was deferred:** the previous plan step mined the same items from the retro
  prose, and the structured feed landed only on 6.10.1+ while 6.10.0 was still
  supported.
- **How it closed:** the 6.11 floor makes the field reliably present, and
  `sprint_plan.py status` returns `open_action_items` directly. 0.27.0 feeds the
  previous epic's open items into every plan run's carry-over block, the report, and the
  PR body (`## Open action items (epic {e})`).
- **First noted:** 2026-06-18 (BMAD `6.8.1-next.14`). **Re-confirmed:** 2026-06-21,
  2026-08-04. **Closed:** 2026-08-16.

### BMAD v7 standardizes Python on `uv run` (watch) — **shipped in 0.27.0**

- **What it was:** `bmad-method` 6.9.0 (PR #2495) flagged an upcoming v7 breaking change
  — every skill running a Python script would invoke `uv run` instead of `python3`; 6.x
  only warned.
- **Trigger fired:** 2026-08-04 (`6.10.1-next.49`) — `bmad-retrospective`,
  `bmad-sprint-planning` and `bmad-project-context` mechanics moved to `uv run`. On 6.11
  `bmad-build`/`bmad-build-auto` render through `uv run render_skill.py` and HALT
  without `uv` + Python 3.11.
- **How it closed:** 0.27.0 makes `uv` + Python 3.11 hard prerequisites — `preflight.py`
  probes `uv` on PATH and `uv python find '>=3.11'`, and README/CLAUDE.md document them.
  auto-bmad's own scripts stay stdlib-only `python3` (≥ 3.11 for `tomllib`) and must not
  gain a `uv` dependency.
- **First noted:** 2026-06-22 (BMAD `6.9.0`). **Closed:** 2026-08-16.

### Gate the epic on the retrospective's machine-readable `verdict` — **shipped in 0.27.0**

- **What it was:** `bmad-method` 6.10.1-next.x (PR #2612) rewrote `bmad-retrospective`
  as an evidence engine whose document opens with frontmatter `verdict: accepted |
  accepted-with-open-items | rejected` — *"an epic gate or orchestrator keys off
  `verdict` to decide whether to hold the next epic"*; sprint-status alone cannot tell a
  rejected epic from an accepted one.
- **Why it was deferred:** the field existed only on 6.10.1+ while 6.10.0 was still
  supported, and it needed new state/report fields plus an epic-mode block-vs-warn
  decision.
- **How it closed:** 0.27.0 delegates `bmad-retrospective -H {e}` at epic end, reads the
  verdict through `story_plan.py --retro-verdict`, records
  `retro.{doc,verdict,open_action_items}` in state, surfaces a `rejected` verdict in the
  report / PR body / merge prompt, and asks before the next epic starts (Phase 0 / E0
  retro verdict gate).
- **First noted:** 2026-08-04 (BMAD `6.10.1-next.49`). **Closed:** 2026-08-16.
