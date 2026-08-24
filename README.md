# auto-bmad — hands-off BMAD stories, human-in-the-loop where it counts

[![license: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](./LICENSE) [![Version](https://img.shields.io/badge/version-0.30.2-blue.svg)](https://github.com/stefanoginella/auto-bmad) [![BMAD-METHOD](https://img.shields.io/badge/BMAD--METHOD-module-8A2BE2.svg)](https://github.com/bmad-code-org/BMAD-METHOD) [![Tested with BMAD 6.11.x](https://img.shields.io/badge/tested%20with%20BMAD-6.11.x-8A2BE2.svg)](https://github.com/bmad-code-org/BMAD-METHOD) [![Tested with TEA 1.23.x](https://img.shields.io/badge/tested%20with%20TEA-1.23.x-8A2BE2.svg)](https://github.com/bmad-code-org/bmad-method-test-architecture-enterprise) [![Works best with: Claude Code | Codex | opencode](https://img.shields.io/badge/works%20best%20with-Claude%20Code%20%7C%20Codex%20%7C%20opencode-00A3A3.svg)](#install) [![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](./CONTRIBUTING.md)

A **BMAD module** that runs the **[BMAD](https://github.com/bmad-code-org/BMAD-METHOD) build lane end-to-end — one story at a time, or an [entire epic in one run](#run-a-whole-epic)**, on **Claude Code, Codex, or opencode**, with **[human-in-the-loop checkpoints](#human-in-the-loop-stops)** at the decisions that matter.

`auto-bmad` wraps BMAD's own unattended story primitive, **`bmad-build-auto`** (plan → build → review), in a resumable pipeline: it picks the next story from your story source — `sprint-status.yaml`, or a `bmad-spec` spec folder's `stories.yaml` (see [Two story sources](#two-story-sources)) — or takes one as an argument, runs `bmad-build-auto` to **plan** the story into a spec, then to **build** it (implement → review → finalize, with build-auto's own review layers *plus* auto-bmad's security and cross-model layers), then runs a **follow-up review pass on a second model**, adds the optional TEA (Test Architect) skills by risk, keeps the sprint status in sync, and finishes with a branch, a PR, and a report of open questions, deferred work, and anything that needs your attention — then stops so **you** decide when to start the next story. Or run a **whole epic at once** with [`/auto-bmad epic`](#run-a-whole-epic) — the same lane looped over the epic's stories, no per-story halts, one branch, one PR, one epic-end retrospective.

The orchestrator **only delegates and reports** — it never reads or edits story code, and never edits the spec. Every step runs in **your host's native subagents with per-phase models** (Claude Code, Codex, opencode): the heavy plan/build steps on your strongest model, the follow-up review on a *different* model, triage and the retrospective on a faster one. Nothing is rendered into your repo — the models live in a `profiles` block in auto-bmad's config, and the same project runs unchanged under any of the three tools (the host is re-detected every run). Where a host has no subagents at all, the pipeline runs inline — same phases, same stops.

> **Prerequisites**
> - **BMAD ≥ 6.11.0** installed in the project (`_bmad/config.toml` present) with the **`bmm`** module — that is where `bmad-build-auto`, `bmad-sprint-planning` and `bmad-retrospective` come from — plus **`tea`** for the test-architecture phases (optional). The installer below can add these in the same run.
> - **`uv`** on PATH (BMAD's build lane renders through `uv run`) and a **`python3` ≥ 3.11 on PATH** (auto-bmad reads BMAD's TOML config with the standard library; `uv python install 3.11` if you need one).
> - **Nested subagents** enabled for your host — auto-bmad's delegate must be able to spawn `bmad-build-auto`'s own subagents. **Claude Code:** the default (depth 3) is fine; only an explicit `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1` breaks it. **Codex:** add `[agents]` `max_depth = 2` to `~/.codex/config.toml` (or the project's `.codex/config.toml`), or run `codex features enable multi_agent_v2`. **opencode:** set `"subagent_depth": 2` in `opencode.json` and grant the Task tool to the subagent (`"agent": {"general": {"permission": {"task": "allow"}}}`). Preflight checks this and prints the exact fix.
> - **`gh`** (GitHub CLI, authenticated) for the push/PR/CI/merge steps — without it, or without a GitHub remote, auto-bmad runs in **local mode** (branch + commits, no PR).
> - Recommended: an `AGENTS.md` with BMAD's `<!-- bmad:context -->` block (`/bmad-project-context setup`) so build-auto's implementers inherit your repo conventions — preflight only warns when it is missing.

> **Compatibility:** tested against the **[BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) 6.11 line** — floor **6.11.0**, tested up to **6.11.0** (and prerelease **6.11.1-next.27**) — and the separately versioned **[TEA test-architecture module](https://github.com/bmad-code-org/bmad-method-test-architecture-enterprise) v1 line** (the `testarch` skills) — floor **1.23.0**, tested up to **1.23.2** (and prerelease **1.23.3-next.0**) — auto-bmad couples to those skills' contracts rather than pinned versions.

> ⚠️ **It can't save you from bad inputs.** auto-bmad automates the *workflow*, not judgment — vague epics, thin acceptance criteria, or a shaky architecture produce vague, untrustworthy code, just faster. The review passes and human-in-the-loop stops below are guardrails, not guarantees; the real leverage is clear stories and sound design *before* you press go.

## Install

auto-bmad is a BMAD module, so the official way to install it — for **any** supported tool, Claude Code included — is the **BMAD installer**. Requires **Node.js 20.12+** and Git.

From your project directory, run the installer and add this repo as a custom source:

```bash
npx bmad-method install
```

When the interactive flow asks **"Do you want to install custom or community modules (Git URL or local path)?"**, choose **Yes** and enter:

```text
https://github.com/stefanoginella/auto-bmad
```

The installer reads this repo's `marketplace.json`, offers the `auto-bmad` module, and copies it into your tool's skills dir (`.claude/skills/` for Claude Code, `.agents/skills/` for Codex and opencode). In the same run, also select the official modules auto-bmad orchestrates if they aren't already installed — at least **bmm**, plus **tea** for the test-architecture phases.

Non-interactive equivalent:

```bash
npx bmad-method install \
  --directory . \
  --modules bmm,tea \
  --custom-source https://github.com/stefanoginella/auto-bmad \
  --tools claude-code \
  --yes
```

Use `--tools codex` for Codex or `--tools opencode` for opencode (`npx bmad-method install --list-tools` lists every target).

Both the interactive and `--custom-source` forms install auto-bmad's latest **`main`** commit; to pin a specific release instead, append a release tag to the URL (`…/auto-bmad@vX.Y.Z`) — see [Updating](#updating).

Then run **`/auto-bmad setup`** once in your tool. It registers auto-bmad in BMAD's help catalog, runs the short first-run interview, writes auto-bmad's runtime config (`<output_folder>/auto-bmad/config.yaml`, default `_bmad-output/auto-bmad/config.yaml`), and writes auto-bmad's review layers into `_bmad/custom/bmad-build-auto.toml` (a marker-fenced region at the end of that file; everything else in it is left alone). No agent files are generated. If you skip `setup`, the first normal `/auto-bmad` run does the same and then stops so the first story runs in a fresh session.

<details>
<summary>Claude Code–only alternative (plugin marketplace)</summary>

If you exclusively use Claude Code, you can instead add this repo as a Claude plugin marketplace (you'll still need the `bmm`/`tea` BMAD skills installed separately via the installer above):

```text
/plugin marketplace add stefanoginella/auto-bmad
/plugin install auto-bmad@auto-bmad
```
</details>

## Updating

auto-bmad installs as a **custom-source** BMAD module. The reliable way to update it is to re-run the installer in `update` mode and re-supply this repo as the source (requires Node.js 20.12+):

```bash
npx bmad-method install \
  --action update \
  --custom-source https://github.com/stefanoginella/auto-bmad \
  --yes
```

This re-clones the repo into BMAD's module cache (`~/.bmad/cache/custom-modules/`), rewrites the install manifest with auto-bmad's source, and redeploys the skill.

**Choosing a version.** The bare `--custom-source` URL tracks auto-bmad's **`main` HEAD** — the latest commit. To pin an exact release instead, append a release tag: `--custom-source https://github.com/stefanoginella/auto-bmad@vX.Y.Z` (tags are listed on the [releases page](https://github.com/stefanoginella/auto-bmad/releases)). For a custom-source URL the `@<ref>` suffix is the version selector — BMAD's `--channel`/`--all-next` flags govern *registered* modules, not custom-source URLs.

> 💡 **About `quick-update`** (the installer's default for an existing install). On BMAD 6.11 a quick update refreshes auto-bmad too, *as long as its clone is still in `~/.bmad/cache/custom-modules/`* — it re-fetches the same ref you installed (latest `main`, or your pinned tag). If that cache is gone (cleared, or auto-bmad was installed another way), the installer prints `Skipping … no source available` and leaves auto-bmad as is. To change the pinned version, or whenever auto-bmad is skipped, use the `--custom-source` command above (interactively: choose **Modify BMAD Installation** and re-enter the custom source).

After an update, nothing needs re-rendering: the next `/auto-bmad` run re-checks the review-layers region in `_bmad/custom/bmad-build-auto.toml` and re-syncs it if it is stale, and offers to append any new config keys the update shipped (append-only — your values are kept; see `config-check` below). To re-sync the review layers by hand, run `/auto-bmad reprovision`.

If you installed via the Claude plugin marketplace (the alternative above) rather than the BMAD installer, update through Claude Code instead:

```text
/plugin marketplace update auto-bmad
/plugin install auto-bmad@auto-bmad
```

## Usage

Run from the root of a BMAD-enabled project:

```text
/auto-bmad                       # implement the next story from sprint-status.yaml
/auto-bmad --story 1-3           # implement a specific story (epic 1, story 3)
/auto-bmad --story 1-3-user-auth
/auto-bmad --spec _bmad-output/specs/spec-rate-limits            # next story of a bmad-spec spec folder
/auto-bmad --spec _bmad-output/specs/spec-rate-limits --story 2  # a specific story of that folder
/auto-bmad epic                  # implement an ENTIRE epic in one run (see "Run a whole epic")
/auto-bmad epic --epic 2         # implement a specific epic
/auto-bmad epic --spec _bmad-output/specs/spec-rate-limits       # the whole spec folder as one epic
/auto-bmad stop before the review     # steer a single run in plain language (see "Steer a single run")
/auto-bmad --story 1-3 approve the spec first   # pause after planning so you can approve/edit the spec
/auto-bmad setup                 # (re)configure: register, first-run interview, sync review layers
/auto-bmad reprovision           # re-sync the review layers in _bmad/custom/bmad-build-auto.toml
/auto-bmad reset-defaults        # discard profile retunes, restore shipped defaults
/auto-bmad config-check          # preview (read-only) what an update would add + your customisations
```

> 💡 **Run it in an auto-approve / "YOLO" mode.** auto-bmad is built to run autonomously between the [human-in-the-loop stops](#human-in-the-loop-stops) below, so it works best when the host tool isn't prompting for permission on every tool call — Claude Code's `--dangerously-skip-permissions`, opencode's `--auto`, or Codex's `--dangerously-bypass-approvals-and-sandbox`. Because that hands the agent broad access, run it inside a sandbox: see [aicontainer](https://github.com/stefanoginella/aicontainer) for a containerized environment that lets you skip permission prompts safely — and because Codex's normal sandbox (bubblewrap) can't initialize inside a nested container, that bypass flag is also what lets Codex run *within* aicontainer.

- **No-argument `/auto-bmad` resumes unfinished work first** — an interrupted pipeline if one exists, otherwise the story BMAD's own `sprint_plan.py status` recommends (`in-progress → review → ready-for-dev → backlog`); it doesn't jump straight to a fresh backlog item. Pass `--story` to target one explicitly. The pipeline is **resumable** (re-run to continue from the last completed phase), and a **clean run marks the story `done`** in `sprint-status.yaml` so the next run advances instead of re-picking it.
- **The story spec is `bmad-build-auto`'s** — auto-bmad never edits it. It sits under your BMM implementation-artifacts folder (`spec-<epic>-<story>-<slug>.md`); the report and PR link to it. If build-auto stops with `blocked`, the report tells you which spec status to set to resume, and re-running `/auto-bmad --story <key>` picks up from there.
- A per-story **report log** is saved to `<output_folder>/auto-bmad/reports/<story>.md` — each run appends a timestamped section (never overwritten on resume), and a clean run **commits it before push so it ships in the PR diff**. It holds the story-level outputs: this run's instructions, TEA outcomes, the build-auto result, follow-up review passes, timing (total elapsed plus an AI-run vs human-wait split), open questions, deferred work, blockers, the epic-end retrospective verdict, and the one-line pipeline **disposition** (clean / caveated / halted + reason). PR/CI links, merge method, and the final status flip are printed to chat only.
- **Everything auto-bmad does per phase, and every point where it stops for you, is in the two tables below** — the phase playbook and the human-in-the-loop stops.

### Two story sources

auto-bmad runs the same lane from either source, and picks between them for you:

- **Sprint** — PRD → epics → `/bmad-sprint-planning` → `sprint-status.yaml`. The default; a bare `/auto-bmad` uses it whenever that file exists.
- **Spec** — `/bmad-spec` → "break this into stories" → a spec folder holding `SPEC.md` + `stories.yaml` (ordered stories with `id` / `title` / `description`, plus optional `spec_checkpoint`, `done_checkpoint` and `invoke_dev_with` notes). Target it with `--spec <folder>`; with no `--spec` and no `sprint-status.yaml`, auto-bmad looks for spec folders and **asks** which to use — never silently.

What differs in the spec route: there is **no sprint-status write-back** (each story's status lives in its own `stories/<id>-*.md` file, written by `bmad-build-auto`), the entry's **checkpoints are honoured** — `spec_checkpoint` pauses for spec approval, `done_checkpoint` stops after that story, epic runs included — and the epic-end retrospective lands in `<spec-folder>/RETROSPECTIVE.md`. Branches, commits and reports are keyed on the spec folder (`story/<spec>-<id>-<slug>`, `story-<spec>-<id>`). Everything else — delegation, profiles, TEA, PR/CI/merge, resume — is identical. Mechanics: `references/stories-mode.md`.

## What it does per story

| Phase | Step | Skill | When |
|-------|------|-------|------|
| 0 | Preflight (BMAD config, `uv`/Python, nested subagents, git, required skills), config heal, story pick, per-story TEA risk triage | `sprint_plan.py status` (BMAD's picker; the spec route picks from `stories.yaml` order instead); triage is a small delegate | always |
| 1 | Create `story/X-Y-slug` branch | — | always |
| 2 | Epic-level test design | `bmad-testarch-test-design` | first story of epic, TEA on |
| 3 | **Plan** — build-auto plans the story into a spec and halts (`Halt after planning.` ⇒ spec at `ready-for-dev`); sprint entry → `ready-for-dev`; then the optional **spec-approval halt** | `bmad-build-auto` | always |
| 4 | ATDD acceptance scaffolds (red) | `bmad-testarch-atdd` | TEA on + high-risk story |
| 5 | **Build** — build-auto implements → reviews (its own review layers + auto-bmad's **security** and **cross-model** layers) → finalizes and **commits its own diff**; sprint entry → `in-progress` → `review` | `bmad-build-auto <spec>` | always |
| 6 | Expand automated coverage | `bmad-testarch-automate` | TEA on + medium/high-risk story |
| 7 | **Follow-up review** — a fresh build-auto review pass on the finished spec at a **different model** (the `followup_review` profile; may be routed to another tool's CLI); then the **review halt** (another pass / continue / stop; external changes you make while paused are re-reviewed once); then a non-blocking per-story trace advisory (long epics) and the deferred-work harvest into `deferred-work.md` | `bmad-build-auto <spec>`; `bmad-testarch-trace` (advisory) | pass: when the spec says `followup_review_recommended` (default) or `code_review.followup: always`; halt: whenever a pass ran or the review is unverified |
| 8 | Epic end — trace **gate** (asks if it fails), NFR + test-quality audits, deferred-work reconcile + archive, pre-retro status flip, headless **retrospective** with a recorded verdict | `bmad-testarch-trace`/`nfr`/`test-review`, `bmad-retrospective -H` | last story of epic |
| 9 | Report, push, open PR, wait for CI, mark story `done` (clean run), **ask whether to merge** (clean run, opt-in), final report | — | always |

Each orchestrator phase ends with a conventional commit (build-auto's own commits land in between), so progress survives interruptions and is easy to review. A story that ends caveated (review unverified, waived gate, blocker, red CI) ships a **draft** PR and stays at `review` until you act.

## Run a whole epic

`/auto-bmad epic` (or `/auto-bmad epic --epic N`, or `/auto-bmad epic --spec <folder>` for a spec folder) drives an **entire epic** — every actionable story — in one run, then **one PR**. It runs the same per-story lane (plan → build → follow-up review, with TEA) for each story in order, on one `epic/N-slug` branch, with one CI wait and one merge prompt at the end.

- **It warns and asks you to confirm up front** — an epic runs **fully unattended between preflight and the merge prompt**: no spec-approval halt, no per-story review halt, no epic-end trace-gate ask (remediation runs mechanically up to the cap). The only stops left are the **preflight safety asks** (config update, adopting a half-done epic, a base-branch readiness check, the previous epic's retro verdict) and the final **merge prompt**.
- **Review stays automatic:** every build run carries build-auto's review layers plus auto-bmad's security/cross-model layers, and the follow-up pass on the second model runs whenever its gate holds. A story whose spec still recommends another review after its last pass — or a run you told to skip that pass — makes the epic **ship a draft**.
- **A per-story `blocked`/needs-human stops the whole epic** with the resume command (`/auto-bmad epic --epic N`).
- **It completes a half-done epic:** stories already `done` are skipped (assumed merged into your base branch — it asks if a `done` story's branch isn't); stories worked outside auto-bmad are adopted at the matching phase (build or follow-up review) after a quick question, or skipped.
- **One report, one status flip:** a single `reports/epic-N.md` rolls up every story; on a clean run all the epic's stories flip to `done` together (before the retrospective, so it judges a finished epic). If anything is caveated (an unverified review, a waived gate, a blocker, red CI), the whole epic stays at `review` — a single PR is either mergeable or not.
- **The retrospective's verdict is recorded** in the report, the PR body and the merge prompt; a `rejected` verdict gates the *next* epic's start (it asks before proceeding).

Delegation, profiles, TEA and resume all work as in per-story mode. Full mechanics: `references/epic-pipeline.md`.

## Human-in-the-loop stops

auto-bmad runs autonomously between the points below — delegated subagents answer BMAD's interactive prompts with sensible defaults. It pauses for **you** only here:

| Stop | When | What you decide / do |
|------|------|----------------------|
| **First-run setup** | First `/auto-bmad` in a project (or `/auto-bmad setup`) | One-time questions: **Quick** (TEA on/off — plus a one-time framework/CI scaffolding offer if TEA's on and none is set up) or **Full** (also git mode/prefix, the follow-up review policy, which extra review layers to write, spec approval). Writes `config.yaml` + the review layers, then stops — **start a new session and re-run `/auto-bmad`** so the first story runs on fresh context. |
| **Config update** | Preflight, only when an auto-bmad update shipped new config keys/profiles | Apply the new defaults & continue (append-only — your values are kept), or stop to edit `config.yaml` first. Epic mode asks once, up front. |
| **Spec approval** *(opt-in)* | After Phase 3, when `build.spec_approval: true`, you ask for it in the invocation, or the story's `stories.yaml` entry sets `spec_checkpoint` (that one fires in epic runs too) — otherwise never in epic mode | Approve & continue, or stop to edit the spec; the next `/auto-bmad --story <key>` re-opens the halt (your spec edits are committed as `spec edits (human)`). |
| **Follow-up review done** | Phase 7 — after the follow-up review pass (or when the review is unverified because no pass ran) | Choose: run another review pass (a fresh build-auto review on the second model), continue, or stop. While paused you're encouraged to run an external review (a human, another model/AI); on continue auto-bmad **re-reviews any changes you made** (one more build-auto pass) and, if they were meaningful, asks once more. When the spec still recommends another review, a **Continue — ship as ready** option overrides the draft. If you stop, re-running `/auto-bmad --story <key>` re-opens the halt. |
| **Epic trace gate failed** | Phase 8 — `bmad-testarch-trace` returns `FAIL` (requirements/ACs lack test coverage) | Choose: remediate & re-gate (auto-expand coverage, then re-run trace; capped by `tea.gate_max_iterations`, default 2), waive and continue (PR opened as a **draft** with the gaps noted), or stop. `CONCERNS` is advisory and doesn't pause. Epic mode remediates without asking. |
| **Previous epic rejected** | Starting the first story of an epic (or an epic run) when the previous epic's retrospective verdict is `rejected` | Proceed anyway, or stop and resolve the previous epic first. |
| **Merge the PR?** | Phase 9 — clean completion only (no blocker, review verified, gates passed, CI green — auto-bmad waits for in-progress CI, cap `git.ci_wait_minutes`, default 30), with `git.offer_merge: true` (default). A run that instead ends as a **draft** PR (CI red or timed-out, unverified review, waived gate) or with a recorded blocker gets **no merge prompt** and stays at `review` for you to finish. | Choose: **Merge commit (default — preserves the per-phase and build-auto commits for AI archaeology)** / **Rebase and merge** / **Squash and merge** / **Don't merge**. If you pick a merge style, a follow-up asks whether to **delete the branch**. auto-bmad runs the chosen `gh pr merge`; on failure (branch protection, required reviews, etc.) it surfaces the error and leaves the PR open. Opt out with `git.offer_merge: false`. |
| **Re-running a completed story** | You target an already-`done` story with `--story` | Confirm before the story is re-run (and its report log overwritten); otherwise it won't redo the story. |
| **Story worked outside auto-bmad** | The story sits at `review`/`in-progress` but has **no auto-bmad state** (hand-driven story, a bare `/bmad-build-auto` run, or a lost state dir) | Choose: **enter at the matching phase** (recommended — `in-progress` ⇒ build, `review` ⇒ follow-up review, using the spec build-auto left), run the full pipeline anyway (a deliberate redo), or stop. |
| **Blocker / needs-human** | Any phase | Hard-stop: build-auto reports `blocked` (missing secret/credential, required external service or manual step, unclear intent, no subagents), a merge/rebase conflict, a dirty tree on the wrong branch, not a BMAD project, a missing prerequisite or required skill, or an ambiguous/not-found `--story`. It reports exactly what's needed (for a build-auto block: the blocking condition verbatim and how to resume) and never pushes past it. |

Want an extra stop? Add a plain-language instruction to the invocation (below) — e.g. `stop before the review` — or set `build.spec_approval: true` to approve every spec.

## Steer a single run

Add plain-language instructions to the invocation. There is **no fixed vocabulary** — auto-bmad reads what you wrote, echoes how it understood it and which phases will run, then executes. Instructions apply to that run only; they are never written to `config.yaml`.

```text
/auto-bmad stop before the review
/auto-bmad --story 1-3 approve the spec first
/auto-bmad skip TEA this time
/auto-bmad dry run                # preflight read-only, print the plan, change nothing
```

Two things to know before you ask for them:

- **Skipping the follow-up review** removes the second-model quality gate, so the PR ships as a **draft** and the story stays at `review` (build-auto's own review layers still ran during the build).
- **Skipping git commits isn't possible** — build-auto commits its own work. To keep a run off GitHub, ask for a local run, or set `git.mode: local`.

## Split a story across tools

The cleanest way to mix tools is **`delegation.cli_phases`** (see [Configuration](#configuration)): it routes chosen phases to another tool's CLI (`claude -p` / `codex exec` / `opencode run`) — at that phase's model + effort — so a **single, autonomous `/auto-bmad` run** mixes tools with no hand-off. Set it once and every run honours it — e.g. `cli_phases: { followup_review: codex }` to build in your host tool but run the follow-up review pass on Codex (Codex reviews *and* triages/patches, since it is running build-auto). The orchestrator builds the command and parses the result; the routed tool just needs the BMAD skills installed for it (`bmm`, plus `tea` when you route a TEA phase) and, when it isn't the host, to be authenticated — the preflight hard-stops if not. Routing both `build` and `followup_review` also means the host itself needs no nested subagents.

You can also hand a story off **by hand**, mid-pipeline — handy when you'd rather drive each tool interactively, or haven't set the other tool up as a headless CLI. The running tool is auto-detected every run and the pipeline is resumable, so stopping at a phase boundary in one tool and resuming in another just works — e.g. **build in Claude Code, review in Codex**:

```text
# In Claude Code — runs phases 0–6 (plan → build), committing each phase
/auto-bmad stop before the review

# In Codex, same project directory — resumes at phase 7 (follow-up review) through the PR
/auto-bmad
```

Swap the tools for the reverse. A plain no-arg `/auto-bmad` resumes the interrupted pipeline at the next unfinished phase. The same pattern works at any phase boundary — e.g. stop after the build, then resume.

**Prerequisites for the manual hand-off:** install the `auto-bmad` and `bmm` skills in **both** tools, and enable nested subagents in both (see Prerequisites). The per-phase commits and the shared `<output_folder>/auto-bmad/state/` file are what let the other tool pick up where the first left off.

## Configuration

`<output_folder>/auto-bmad/config.yaml` (created on first run) controls:

- **Code review** —
  - `code_review.followup`: `recommended` (default — a follow-up pass only when the finished spec says `followup_review_recommended: true`) | `always` (every story) | `never`.
  - `code_review.security_layer` (default `true`) — write auto-bmad's **security review layer** into `_bmad/custom/bmad-build-auto.toml`, so build-auto's own review step runs it alongside its shipped layers.
  - `code_review.cross_model_layer`: `codex` | `claude` | `opencode` | `""` — a **cross-model review layer** that shells out to that tool's CLI (at the `cross_model_layer` profile's model + effort) during build-auto's review. Detected at first run as the first of `codex`, `claude`, `opencode` on PATH that isn't your host; `""` disables it.
  - ⚠️ **Both layers are project-wide:** they live in BMAD's team customization file, so they also run for a manual `/bmad-build-auto` in this project. Change either setting, then run `/auto-bmad reprovision` to re-sync (removing a layer = disable it and re-sync).
- **Build** — `build.spec_approval` (default `false`): pause after every plan for your OK on the spec (or ask for it in a single invocation).
- **TEA** — `tea.enabled`, plus the epic trace-gate remediation cap (`tea.gate_max_iterations`) and the non-blocking long-epic per-story trace advisory (`tea.story_trace_advisory`: toggle + epic-length & distance-to-gate thresholds).
- **Git** — mode (`auto` = detect PR vs local-only, or forced), branch prefixes, `offer_merge`, `ci_wait_minutes`.
- **Profiles = models.** `profiles` holds, per profile, the model per tool (`claude.model`, `codex.model` + `codex.reasoning_effort`, `opencode.model` + `opencode.variant`); `phase_profiles` maps each phase (`build`, `followup_review`, `security_layer`, `cross_model_layer`, `tea_triage`, `tea_per_story`, `tea_epic`, `tea_epic_audit`, `retrospective`, `deferred_reconcile`) to a profile. Shipped profiles, three tiers: `light` (mechanical/advisory steps — Sonnet / `gpt-5.6-luna`), `standard` (the default, incl. plan/build — Opus / `gpt-5.6-terra`), `critical` (the follow-up review only — Fable / `gpt-5.6-sol`, a *different*, stronger model than `build`); add your own (any name, same fields) and point `phase_profiles` at it. What the knobs buy in-tool: **Claude Code** honours the model per phase (effort inherits your session), **Codex** honours model + reasoning effort per phase, **opencode** subagents inherit your default model (`opencode.model`/`variant` are used only by the `cli_phases` route and the cross-model layer). After editing the profiles the two layers use, run `/auto-bmad reprovision`; `/auto-bmad reset-defaults` restores the shipped profiles (your git/TEA/review answers are never touched).
- **`delegation.mode`** — `auto` (default: subagents where the host has them, else inline) | `subagents` | `inline`.
- **`delegation.cli_phases`** — opt-in per-phase external-CLI routing (a phase→tool map, empty by default): delegates chosen phases to `claude -p` / `codex exec` / `opencode run` instead of an in-tool subagent, for cross-tool (and, via opencode, cross-vendor) diversity — e.g. `{ followup_review: codex }`; model + effort still come from that phase's profile.

`/auto-bmad config-check` shows what an update would add and everything you've changed vs the shipped defaults, and offers to apply the update (append-only). See `references/state-and-resume.md` for the full schema, `references/config-commands.md` for the config commands, and `references/delegation-runtime.md` (plus `references/cli-route.md`) for the delegation mechanics.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) and our [Code of Conduct](./CODE_OF_CONDUCT.md).

## License

[MIT](./LICENSE) © 2026 Stefano Ginella
