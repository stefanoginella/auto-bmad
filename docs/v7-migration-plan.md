# auto-bmad → BMAD 6.11+/v7 migration plan (DRAFT)

Status: **decided 2026-08-15** (decisions in §8). Written 2026-08-15 from a live read of
`bmad-method@6.11.1-next.14` (npm `next`; `latest` = 6.11.0), TEA `1.23.0` (npm `latest`;
`next` = 1.22.7-next.0 is byte-identical content), `bmad-loop` v0.10.0 (comparison only), and
GitHub statements about v7. No backward compatibility is kept.

auto-bmad stays a **standalone alternative to bmad-loop** — it does not adopt or wrap it.

---

## 1. Goal

Make auto-bmad ride the **current official BMAD implementation lane** and be **v7-ready**:

- Floor: **BMAD-METHOD ≥ 6.11.0** (stable) and **TEA ≥ 1.23.0**. Nothing older.
- Use only skills that survive the v7 cut. Never invoke anything under `v6-shims/`.
- **Zero overlap with default BMAD behaviour**: if a shipped BMAD skill does X, auto-bmad
  delegates X — it never re-implements X. auto-bmad keeps only the stages BMAD does not do
  (git/PR, sprint-status write-back, deferred-work ledger, TEA gating, retro gate, report, HITL).

## 2. Upstream facts this plan rests on (verified 2026-08-15)

| Area | Fact | Consequence for auto-bmad |
|---|---|---|
| Implementation lane | Phase 4 = `bmad-sprint-planning → bmad-build → bmad-code-review`. `bmad-build-auto` = the unattended, single-iteration variant with a HALT/`status` contract (`draft/ready-for-dev/in-progress/in-review/done/blocked` + `blocking condition`). | Replace `create-story` + `dev-story` (v6-shims, removed at v7) with **`bmad-build-auto`**. |
| Rendered skills | `bmad-build(-auto)` are rendered by `uv run _bmad/scripts/render_skill.py`; **hard HALT without `uv` + Python 3.11**. | `uv` becomes an auto-bmad prerequisite; preflight checks it. |
| Subagents | `bmad-build(-auto)` spawn their **own** subagents (implementer, 3–4 review layers, epic-context compile); `build-auto` HALTs `blocked/no subagents` otherwise. Subagents must be synchronous, never backgrounded. | Requires **nested subagents**: Claude Code ≥ 2.1.219 nests 3 deep by default (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`); Codex V1 default `agents.max_depth = 1` → must be raised (`[agents] max_depth = 2`+) or `multi_agent_v2` enabled; opencode: no documented limit (verify live). |
| Story artifact | `bmad-build` writes `<impl>/spec-{slug}.md` (slug led by `{e}-{s}`), status in **YAML frontmatter** (`in-review`, not `review`); `build-auto` adds `deferred: []`, `warnings: []`, `followup_review_recommended`, `baseline_revision`, `## Review Triage Log`, `## Auto Run Result`. Also caches `<impl>/epic-{N}-context.md`. | Story-file `Status:` parsing dies. Read spec frontmatter instead. |
| sprint-status.yaml | Format unchanged; still canonical ("remains the default indefinitely" per bmad-loop; v7 ticket-tree proposal was closed unmerged). `bmad-build` syncs `in-progress`/`review` (never `done`); **`build-auto` never touches it**; `bmad-code-review` flips `done`/`in-progress`. Key grammar allows split suffix `2-6a-…`. `sprint_plan.py status` (uv+ruamel) recommends the next story. No upstream script flips one story key. | Orchestrator stays sole sprint-status writer around `build-auto` (`--mark-status`, add `last_updated` + `[a-z]?` grammar). |
| Review | `bmad-code-review` = "optional extra check after Build's built-in review"; 4 layers as **subagents**, human HALTs (checkpoint, patch choice), applies patches, flips status. Core `bmad-review` = lens engine (adversarial, edge-case-hunter, verification-gap, structure, prose), **no triage/severity/persistence, no security lens, no model diversity**. `build-auto` review layers + `implementation_handoff` are **customizable** via `_bmad/custom/bmad-build-auto.toml` (`[[workflow.review_layers]]` — "an override may run anything, e.g. an external reviewer via bash"). Re-invoking `build-auto` on a `done` spec = a fresh independent review pass. | Delete the fan-out replica. Add auto-bmad's extras through the upstream extension point (see §5). |
| Project context | `bmad-project-context` (modes `setup/adopt/refresh/record/audit`) writes an **`AGENTS.md` managed block**; "conversational always; the user approves every write". `project-context.md` is legacy input only. `bmad-generate-project-context` = shim. | Probe `AGENTS.md` `<!-- bmad:context -->`; warn only, never delegate. |
| Retro | `bmad-retrospective -H <epic>` is "the stable orchestrator-facing interface"; verdict `accepted / accepted-with-open-items / rejected` in the retro doc frontmatter; `action_items` carry `id`/`ref`; runs `bmad-review` on the epic diff; needs uv + ruamel. | Keep delegating; add the **verdict gate** (epic mode halts on `rejected`); consume `action_items`. |
| Deferred work | `bmad-build` appends `- source_spec/summary/evidence` blocks; `build-auto` puts them in spec frontmatter `deferred:`; `code-review` appends `## Deferred from:` bullets. **No upstream reconcile/archive/reader.** | Ledger management stays auto-bmad's; parser must read both shapes and **harvest `deferred:` frontmatter** into the ledger. |
| Config | Central 4-layer TOML (`resolve_config.py`, Python 3.11 `tomllib`); `_bmad/bmm/config.yaml` still written ("this release is the migration, not the cutover"). | Read the TOML layers directly with `tomllib`. |
| Removed/renamed | `bmad-sprint-status` → shim; `bmad-check-implementation-readiness` → folded into sprint-planning; `bmad-review-*` lenses → core shims; `bmad-generate-project-context`/`document-project` → shims. | Never name any of these. |
| TEA 1.23.0 | Same 9 skills, no build/review integration, no sprint-status writes. `uv` required for `resolve_customization.py` (graceful fallback). `framework` (1.23.0) installs a Claude Code write-time hook (`.claude/settings.json`, `.claude/hooks/tea-enforce.cjs`, `.tea/`). `test-design` (1.22.3) halts on a stale in-progress checkpoint. Trace artifacts are fixed-path (`gate-decision.json`, `e2e-trace-summary.json`, `traceability-matrix.md`) — the story advisory overwrites the epic gate's. | Prompt fixes only (Create mode/replace checkpoint; `gate_type: epic`; `allow_gate: false` for the advisory; `review_files` not `suite`). |
| v7 | No date, milestone, or 7.x prerelease. Confirmed for v7: shims removed; `uv run` standard; TOML cutover likely; ticket-tree/spec-tree direction real but uncommitted (PR #2672 closed unmerged). `bmad-code-review` stays. | Keep the story source behind one adapter (`story_plan.py`) so a v7 ticket tree is a one-module swap. |

## 3. Design principles (unchanged, restated for the new lane)

1. **Delegate, never do.** The orchestrator runs no BMAD skill and reads no code.
2. **No overlap.** BMAD's own steps (spec, implement, in-loop review+triage+patch, retro,
   project context, sprint-status generation/status view) are delegated as-is. auto-bmad adds
   only what BMAD lacks.
3. **Orchestrator-owned direct actions** stay: git preflight/branch/commits/push/PR/CI-wait/merge
   prompt; sprint-status + spec status write-back around `build-auto`; report/state; ledger
   archive; HITL halts.
4. **Delegation tiers shrink to two** — `custom-subagents` (default) and `inline` (last
   resort); the `general-subagents` tier is **dropped**. `cli_phases` stays.
   Nested-subagent capability becomes a **preflight probe** (host + config), not an assumption.

## 4. Target per-story pipeline (old → new)

| Old phase | New phase | Delegate / owner | Notes |
|---|---|---|---|
| 0 Preflight & triage | 0 Preflight & triage | orchestrator + `tea_triage` | + `uv` check, Python ≥ 3.11, nested-subagent capability, `_bmad/config.toml`, `AGENTS.md` block probe, skills present (`bmad-build-auto`, `bmad-sprint-planning`, `bmad-retrospective`, `bmad-project-context`, TEA). Story pick via **`sprint_plan.py status`**. |
| 1 Branch | 1 Branch | orchestrator | unchanged. |
| 2 Epic-start (context bootstrap + epic test-design) | 2 Epic-start (epic test-design only) | `tea_epic` | test-design prompt: Create mode, epic `{e}`, replace any stale checkpoint. |
| 3 create-story | **3 Plan** — `bmad-build-auto <key> … Halt after planning.` | `build` (new profile key) | Yields `spec-{key}-…md` at `ready-for-dev`. Orchestrator flips sprint entry → `in-progress` (build-auto never does). Opt-in per-story **spec-approval halt**. Commit `docs(story): plan spec`. |
| 4 ATDD | 4 ATDD | `tea_per_story` | Input = the spec file (has ACs). Runs between plan-halt and resume. |
| 5 dev-story | **5 Build** — `bmad-build-auto <spec path>` (resumes at implement → review → finalize) | `build` | build-auto commits its own diff + spec (no push). Read `## Auto Run Result` + frontmatter (`status`, `blocking condition`, `followup_review_recommended`, `deferred`, `warnings`, `review_loop_iteration`). `blocked` ⇒ `needs-human`. Orchestrator flips sprint entry → `review`. |
| 6 automate | 6 automate | `tea_per_story` | on the spec. |
| 7 Code-review loop (fan-out replica) | **7 Follow-up review** | see §5 | Replica deleted. |
| 7 tail trace advisory | 7 tail | `tea_per_story` | pass `allow_gate: false`. |
| 8 Epic end | 8 Epic end | `tea_epic`, `tea_epic_audit`, `deferred_reconcile`, `retrospective` | + `gate_type: epic`; retro **verdict gate**; `action_items` consumption; ledger harvest+reconcile+archive; report line recommending `/bmad-project-context refresh`. |
| 9 Finalize | 9 Finalize | orchestrator | Report, push, PR, CI wait, `done` flip (sprint entry; the spec is already `done` by build-auto), merge prompt. No UAT delegate; next-step line → `/bmad-checkpoint-preview`. |

Epic mode (`epic-pipeline.md`) keeps its E-steps; the inner loop is the new Phases 3–7.

## 5. Review strategy — DECIDED: A (extend upstream, delete the replica)

Upstream now reviews inside `build-auto` (Blind Hunter, Edge-Case Hunter, Verification-Gap,
Intent-Alignment; the parent triages, patches, loops ≤ 5). auto-bmad's replica (3×R lenses +
triage + `### Review Findings` + `review_findings.py`/`review_loop.py`) is overlap → **deleted**.

What auto-bmad adds, through the upstream extension point only:

1. **Extra review layers** merged into the project's `_bmad/custom/bmad-build-auto.toml`
   (`[[workflow.review_layers]]`, merged by `id`; written at setup/`reprovision`, asked once):
   - `security` — auto-bmad's security prompt (no upstream equivalent).
   - `cross-model` — an external reviewer via bash (`codex exec` / `claude -p` /
     `opencode run`). Configured like every other phase: `phase_profiles.cross_model_layer →
     <profile>` and that profile's `codex:` / `claude:` / `opencode:` block gives model + effort;
     `code_review.cross_model_layer: codex|claude|opencode|""` picks the tool (default `codex`
     when on PATH and different from the host). Argv built by `cli_delegate.py`.
   build-auto's own triage + patch loop then handles these findings — no auto-bmad triage.
   Caveat (accepted): the TOML is project-wide, so the layers also run for a manual
   `/bmad-build-auto`; setup says so.
2. **Follow-up review pass** (Phase 7): when `followup_review_recommended` is true (or
   `code_review.followup: always`), re-invoke `/bmad-build-auto <done spec>` — upstream's
   sanctioned "fresh independent review pass" — at the **secondary reviewer profile**
   (different model). It may also be routed to Codex wholesale via `cli_phases`
   (`followup_review: codex` ⇒ `codex exec`, so Codex reviews **and** triages/patches).
3. **HITL halt** (per-story mode; epic mode auto-continues): after Phase 7 — options
   *another review pass* (re-invoke build-auto on the spec) / *continue* / *stop*. External
   changes made during the halt are committed (git-only) and re-reviewed by the same mechanism.

Config collapses to `code_review.followup: recommended|always|never`,
`code_review.security_layer: bool`, `code_review.cross_model_layer: codex|claude|opencode|""`.

## 6. Overlap audit — remove from auto-bmad

| Today | Why it is overlap now | Action |
|---|---|---|
| `create-story` / `dev-story` delegates + retro/deferred forward-feed prompt | v6-shims; `build-auto` compiles epic context + prior done specs itself | delete |
| Phase 7 fan-out replica (`code-review-blind/edge/auditor/verification-gap`, `code-review-triage`, `code-review fix`, `### Review Findings` contract, `review_findings.py`, most of `review_loop.py`) | build-auto reviews + triages + patches | delete (keep only what §5-A needs: security prompt, layer TOML writer, follow-up gate) |
| `story_plan.py` next-story picker | `sprint_plan.py status` recommends next | shrink to the status-flip helper + spec-frontmatter reader |
| `bmad-sprint-status` delegate mention | shim | replace with `sprint_plan.py status` |
| `generate-project-context` delegate (`--auto`, kernel/legacy fill) | `bmad-project-context` (AGENTS.md block, human-approved) | delete; preflight warn + report recommendation |
| Retro-notes file + `retro-append` | retro is evidence-based (git + sprint-status + review) | delete |
| CLAUDE.md "cannot spawn sub-agents" platform fact | stale (Claude nests 3 deep) | rewrite |

## 7. Keep — auto-bmad's differentiators (no upstream equivalent)

git branch per story / per-phase conventional commits / push / PR / CI wait / merge prompt ·
sprint-status **and** epic-lift write-back around `build-auto` · story/epic selection + epic mode
+ resume/state/report · per-phase **model + effort** profiles across 3 hosts · TEA risk rubric
and phase placement · security lens + cross-model review · deferred-work harvest → reconcile →
archive · retro verdict gate + action_items feed · HITL halts (opt-in spec approval, review,
trace FAIL, merge).

## 8. Decisions (2026-08-15)

1. **Primitive**: `bmad-build-auto` per story, two-step (`Halt after planning.` → TEA ATDD →
   resume). Prerequisites accepted: `uv` + Python 3.11, nested subagents (Codex
   `agents.max_depth`), central TOML.
2. **Review**: §5-A. Codex stays a reviewer via the `cross-model` layer and/or a Codex-routed
   follow-up pass.
3. **Project context**: no delegation. Preflight **warns** when `AGENTS.md` has no
   `<!-- bmad:context -->` block (points at `/bmad-project-context setup`); the epic-end report
   carries a *recommendation* line (`/bmad-project-context refresh`). `project_context`
   profile + Phases 2.1/8.2 removed.
4. **Story picker**: upstream `sprint_plan.py status` (uv). `story_plan.py` shrinks to the
   sprint-status flip helper (+ `[a-z]?` grammar, `last_updated`) and a spec-frontmatter reader.
5. **Config**: read the central TOML layers with `tomllib` (Python 3.11 stdlib); no YAML read.
6. **Spec-approval halt**: opt-in per-story HITL between plan and implement
   (`git`/`build` config key `spec_approval: false` default; override `approve spec`).
7. **UAT delegate**: **dropped**; report next-step line points at `/bmad-checkpoint-preview`.
8. **Version**: minor bump (`0.27.0`). README un-archived; the unreleased `### Deprecated`
   wind-down entry is deleted from `CHANGELOG.md`.
9. **Epic mode**: **kept, shrunk** — loop the per-story lane, no per-story halts, one branch +
   one PR, epic-end once, retro **verdict gate** (`rejected` ⇒ halt before the next epic).
   Tier-A/Tier-B review, `E_review` auto-resolution, epic triage/fix/UAT entries: deleted.
10. **Also removed**: the `general-subagents` delegation tier; retro-notes file +
    `retro-append` (retro is evidence-based upstream);
    `ab-verification` profile; `code_review.max_iterations` / `verification_gap` /
    `security_review`; overrides `max N review iterations`, `skip uat`; review-loop state
    fields; `review_findings.py`, `review_loop.py`.
11. **Kept as-is**: `custom-subagents` + `inline` tiers, `cli_phases`; `config_plan.py` heal;
    `render-agents.py`; `ci_wait.py`; `cli_delegate.py`; vendored `merge-*.py`; TEA rubric.

## 9. Component change list

- `SKILL.md`: procedure rewrite (phases, hard-stops, prerequisites, ownership list).
- `references/pipeline.md`, `epic-pipeline.md`, `delegation.md`, `delegation-runtime.md`
  (two tiers only, nested-subagent probe, Codex `max_depth`), `state-and-resume.md` (state schema: spec path,
  build-auto result fields, retro verdict, drop review-loop fields), `git-and-pr.md`
  (build-auto's own commits), `tea-policy.md` (spec as story input), `overrides.md`.
- `assets/agents/profiles.yaml`: phase keys → `build`, `followup_review` (secondary reviewer),
  `cross_model_layer`, `security_layer`, `tea_*`, `retrospective`, `deferred_reconcile`;
  drop `ab-verification`; persona text rewritten for the build lane.
- `assets/config-defaults.yaml`, `module.yaml`, `module-help.csv`, `module-setup.md`.
- New asset: `assets/bmad-custom/bmad-build-auto.toml` (security + cross-model layers) and a
  small stdlib merger (by layer `id`) run at setup/`reprovision` (§5).
- Scripts: `preflight.py` (uv/python/nesting/TOML/AGENTS.md), `story_plan.py` (flip helper,
  `[a-z]?`, `last_updated`, spec-frontmatter reader), `state_plan.py`, `state_update.py`
  (schema), `deferred_ledger.py` (both entry shapes + frontmatter harvest), `review_loop.py` +
  `review_findings.py` (delete), `config_plan.py`,
  `render-agents.py`, `cli_delegate.py` (+ layer-instruction builder), `ci_wait.py` (unchanged);
  **deleted**: `review_findings.py`, `review_loop.py`.
- Maintainer: `.claude/skills/auto-bmad-compat-check` surface (build-auto layers/spec template
  become the "critical" replica), `docs/upstream-capability-backlog.md` (close the entries that
  now ship), README (install/prereqs/compat markers/un-archive), CHANGELOG, CLAUDE.md
  (platform facts, core principle wording).

## 10. Backlog reconciliation (`docs/upstream-capability-backlog.md`)

| Entry | Outcome |
|---|---|
| `bmad-build-auto` native loop | **Ships** — becomes the story primitive (§4). Close with a CHANGELOG note. |
| Consume `action_items` | **Ships** — read open items from `sprint_plan.py status` JSON → epic-end report + PR body; in epic mode, and at the first story of an epic in per-story mode, the previous epic's open items ride as *carry-over context* in the build-auto plan intent (orchestration glue, no overlap). Close. |
| `uv run` v7 watch | **Ships** — `uv` + Python 3.11 are prerequisites; preflight check + README Install/Updating note. Close. |
| Retro `verdict` gate | **Ships** — decision 9. Close. |
| `tea-test-review` CLI | **Stays open** — trigger not fired (TEA 1.23.0 has no trace/gate CLI; auto-bmad has no CI-gate mode). Add a 1.23.0 re-check line. |

New deferred entries to add: **`bmad-spec` stories mode** (`stories.yaml` dispatch — revisit if the
v7 spec/ticket tree becomes the primary story source); **TEA live-verification evidence**
(`live-verification-results.json`, counts toward trace capped at CONCERNS — revisit when a
cheap producer format is documented); **TEA write-time enforcement hook** (Claude Code only;
auto-bmad only *expects* it — revisit if it gains a headless/CI form).

## 11. Risks / v7 unknowns

- v7 may replace `sprint-status.yaml` + monolithic epics with a ticket/spec tree; the build lane
  would be re-pointed. Mitigation: one story-source adapter; no format assumptions elsewhere.
- Codex nested-subagent config is per-user/project; preflight must fail loudly, not silently
  `blocked`.
- `build-auto` HALT statuses/blocking strings are prose contracts — parse defensively.
- TEA 1.23.0 write-time hook alters delegate behaviour on test files (Claude Code only).

## 12. Delivery (proposed)

M1 decisions + CLAUDE.md/platform facts · M2 preflight + config + story adapter · M3 build-auto
two-step lane (Phases 3–5) + status write-back · M4 review layers TOML + follow-up pass + HITL halt ·
M5 TEA prompt fixes · M6 epic-end (ledger harvest, retro verdict/action_items) + shrunk epic mode · M7 report/state
schema, epic mode, overrides · M8 compat-check skill, backlog reconciliation (§10), README, CHANGELOG, release.
