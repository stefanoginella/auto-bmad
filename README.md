# auto-bmad — hands-off BMAD stories, human-in-the-loop where it counts

[![license: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](./LICENSE) [![Version](https://img.shields.io/badge/version-0.25.2-blue.svg)](https://github.com/stefanoginella/auto-bmad) [![BMAD-METHOD](https://img.shields.io/badge/BMAD--METHOD-module-8A2BE2.svg)](https://github.com/bmad-code-org/BMAD-METHOD) [![Tested with BMAD 6.9.x](https://img.shields.io/badge/tested%20with%20BMAD-6.9.x-8A2BE2.svg)](https://github.com/bmad-code-org/BMAD-METHOD) [![Tested with TEA 1.19.x](https://img.shields.io/badge/tested%20with%20TEA-1.19.x-8A2BE2.svg)](https://github.com/bmad-code-org/bmad-method-test-architecture-enterprise) [![Works best with: Claude Code | Codex | opencode](https://img.shields.io/badge/works%20best%20with-Claude%20Code%20%7C%20Codex%20%7C%20opencode-00A3A3.svg)](#install) [![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](./CONTRIBUTING.md)

A **BMAD module** that runs the **full [BMAD](https://github.com/bmad-code-org/BMAD-METHOD) story implementation workflow end-to-end — one story at a time, or an [entire epic in one run](#run-a-whole-epic)**, on **Claude Code, Codex, or opencode**, with **[human-in-the-loop checkpoints](#human-in-the-loop-stops)** at the decisions that matter.

`auto-bmad` chains the core BMM skills (`create-story` → `dev-story` → `code-review`) and the optional TEA (Test Architect) skills into a single resumable pipeline. It detects the next story from `sprint-status.yaml` (or takes one as an argument), runs every step in an isolated git branch with conventional-commit checkpoints, opens a PR, and finishes with a report of the PR link, open questions, deferred work, and anything that needs your attention — then stops so **you** decide when to start the next story. Or run a **whole epic at once** with [`/auto-bmad epic`](#run-a-whole-epic) — the same pipeline looped over the epic's stories, trimmed for wall-clock and capped with one integration review + one PR.

The orchestrator **only delegates and reports** — every BMAD step runs inside a sub-agent, with model and thinking effort matched to the stakes (Opus/max for high-stakes implementation, a faster model for low-stakes mechanics). On **Claude Code, Codex, and opencode** those are real, isolated subagents (`.claude/agents` / `.codex/agents` / `.opencode/agent`, generated from a configurable profiles block); elsewhere it falls back to generic subagents (untuned) or runs inline — same pipeline either way. **opencode** is multi-provider — point any phase (or the second-opinion reviewer) at any provider/model you've configured (Anthropic, DeepSeek, Qwen, local, …); it's model-tuned per phase but, since its reasoning knob is provider-specific, not effort-tuned in the agent files.

> Requires the BMAD skills it orchestrates (`bmm`, plus `tea` for the test phases) and a `_bmad/` config in your project — the installer below can add these in the same run. auto-bmad drives those skills; it does not replace them.

> **Compatibility:** tested against the **[BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) v6 skill line** up to **6.9.0** (and prerelease **6.9.1-next.19**), and the separately versioned **[TEA test-architecture module](https://github.com/bmad-code-org/bmad-method-test-architecture-enterprise) v1 line** (the `testarch` skills) up to **1.19.0** — auto-bmad couples to those skills' contracts rather than pinned versions.

> ⚠️ **It can't save you from bad inputs.** auto-bmad automates the *workflow*, not judgment — vague epics, thin acceptance criteria, or a shaky architecture produce vague, untrustworthy code, just faster. The code-review loop and human-in-the-loop stops below are guardrails, not guarantees; the real leverage is clear stories and sound design *before* you press go.

## Install

auto-bmad is a BMAD module, so the official way to install it — for **any** supported tool, Claude Code included — is the **BMAD installer**. Requires **Node.js 20.12+** and Git.

From your project directory, run the installer and add this repo as a custom source:

```bash
npx bmad-method install
```

When the interactive flow asks **"Would you like to install from a custom source (Git URL or local path)?"**, choose **Yes** and enter:

```text
https://github.com/stefanoginella/auto-bmad
```

The installer reads this repo's `marketplace.json`, offers the `auto-bmad` module, and copies it into your tool's skills dir (`.claude/skills/` for Claude Code, `.agents/skills/` for Codex, …). In the same run, also select the official modules auto-bmad orchestrates if they aren't already installed — at least **bmm**, plus **tea** for the test-architecture phases.

Non-interactive equivalent:

```bash
npx bmad-method install \
  --directory . \
  --modules bmm,tea \
  --custom-source https://github.com/stefanoginella/auto-bmad \
  --tools claude-code \
  --yes
```

Use `--tools codex` for Codex (`npx bmad-method install --list-tools` lists every target). Re-run `npx bmad-method install` anytime to update.

Both the interactive and `--custom-source` forms install auto-bmad's latest **`main`** commit; to pin a specific release instead, append the tag to the URL (`…/auto-bmad@v0.20.1`) — see [Updating](#updating).

Then provision the delegate agents once with `/auto-bmad setup` — though auto-bmad also self-registers on the first normal `/auto-bmad` run if you skip it.

<details>
<summary>Claude Code–only alternative (plugin marketplace)</summary>

If you exclusively use Claude Code, you can instead add this repo as a Claude plugin marketplace (you'll still need the `bmm`/`tea` BMAD skills installed separately via the installer above):

```text
/plugin marketplace add stefanoginella/auto-bmad
/plugin install auto-bmad@auto-bmad
```
</details>

## Updating

auto-bmad installs as a **custom-source** BMAD module, so an update has to re-supply its Git source. Re-run the installer in `update` mode pointing at this repo (requires Node.js 20.12+):

```bash
npx bmad-method install \
  --action update \
  --custom-source https://github.com/stefanoginella/auto-bmad \
  --yes
```

This re-clones the repo into BMAD's module cache and rewrites the install manifest with auto-bmad's source, so the update applies and future `bmad update` runs resolve it cleanly.

**Choosing a version.** The bare `--custom-source` URL above tracks auto-bmad's **`main` HEAD** — the latest commit, so each update pulls the newest `main`. To pin an exact release instead, append the tag to the source: `--custom-source https://github.com/stefanoginella/auto-bmad@v0.20.1`. For a custom-source URL the `@<ref>` suffix is the only version selector — BMAD's `--channel`/`--all-next` flags govern *registered* modules, not custom-source URLs, so they won't move auto-bmad onto a release tag.

> ⚠️ **Don't update with `--action quick-update`** (the interactive default for an existing install). It skips custom-source re-cloning entirely, so auto-bmad is **silently skipped** and you keep seeing `[warn] … could not locate module.yaml for 'abm'` on the next `bmad update`. Always re-supply `--custom-source` as above (interactively: choose **"Modify BMAD Installation"** and re-enter the custom source — don't accept the quick-update default).

> 💡 **Delegate agents re-render themselves after an update.** A module update (or a `profiles` edit) would otherwise leave the generated `.claude/agents` / `.codex/agents` stale, so the next `/auto-bmad` run **detects this at preflight and reprovisions automatically**, noting it in the report. To refresh them yourself (e.g. right after editing `profiles`), run `/auto-bmad reprovision`. Nothing else needs reconfiguring — the running tool is auto-detected every run.

If you installed via the Claude plugin marketplace (the alternative above) rather than the BMAD installer, update through Claude Code instead:

```text
/plugin marketplace update auto-bmad
/plugin install auto-bmad@auto-bmad
```

## Usage

Run from the root of a BMAD-enabled project:

```text
/auto-bmad              # implement the next story from sprint-status.yaml
/auto-bmad 1-3          # implement a specific story (epic 1, story 3)
/auto-bmad 1-3-user-auth
/auto-bmad epic         # implement an ENTIRE epic in one run (see "Run a whole epic")
/auto-bmad epic --epic 2  # implement a specific epic
/auto-bmad stop before code-review        # steer a single run (see Overrides)
/auto-bmad --story 1-3 skip git commits
/auto-bmad reprovision                    # re-render delegate agents after editing profiles
/auto-bmad reset-defaults                 # discard profile retunes, restore shipped defaults
```

> 💡 **Run it in an auto-approve / "YOLO" mode.** auto-bmad is built to run autonomously between the [human-in-the-loop stops](#human-in-the-loop-stops) below, so it works best when the host tool isn't prompting for permission on every tool call — Claude Code's or opencode's `--dangerously-skip-permissions` (aka YOLO mode), or Codex's `--dangerously-bypass-approvals-and-sandbox`. Because that hands the agent broad access, run it inside a sandbox: see [aicontainer](https://github.com/stefanoginella/aicontainer) for a containerized environment that lets you skip permission prompts safely — and because Codex's normal sandbox (bubblewrap) can't initialize inside a nested container, that bypass flag is also what lets Codex run *within* aicontainer.

- **No-argument `/auto-bmad` resumes unfinished work first** — an interrupted pipeline if one exists, otherwise the next actionable story by status (`in-progress → review → ready-for-dev → backlog`); it doesn't jump straight to a fresh backlog item. Pass a story id to target one explicitly. The pipeline is **resumable** (re-run to continue from the last completed phase), and a **clean run marks the story `done`** (story file + `sprint-status.yaml`) so the next run advances instead of re-picking it.
- A per-story **report log** is saved to `_bmad-output/auto-bmad/reports/<story>.md` — each run appends a timestamped section (never overwritten on resume), and a clean run **commits it before push so it ships in the PR diff**. It holds the story-level outputs: overrides, TEA outcomes, timing (total elapsed plus an AI-run vs human-wait split), open questions, deferred work, epic-end planning drift, blockers, next-story preview, and the one-line pipeline **disposition** (clean / caveated / draft + reason). PR/CI links, merge method, and the final status-flip are printed to chat only — already retrievable from GitHub and the BMAD status files.
- **Everything auto-bmad does per phase, and every point where it stops for you, is in the two tables below** — the phase playbook and the human-in-the-loop stops.

## What it does per story

| Phase | Step | Skill | When |
|-------|------|-------|------|
| 0 | Preflight, triage, first-run config | — | always |
| 1 | Create `story/X-Y-slug` branch | — | always |
| 2 | Bootstrap `project-context.md` (greenfield/brownfield onboarding) | `bmad-generate-project-context` | no `project-context.md` exists yet |
| 2 | Epic-level test design | `bmad-testarch-test-design` | first story of epic, TEA on |
| 3 | Create + self-validate story | `bmad-create-story` | always |
| 4 | ATDD acceptance scaffolds | `bmad-testarch-atdd` | TEA on + risk-warranted |
| 5 | Implement story | `bmad-dev-story` | always |
| 6 | Expand automated coverage | `bmad-testarch-automate` | TEA on + risk-warranted |
| 7 | Code review — up to three review models in parallel on every pass (primary + optional secondary/tertiary), **plus a dedicated security review** each pass; triage dedups across all of them and **suppresses low-severity noise** (cosmetic/hypothetical/already-guarded findings dismissed, genuine ones kept or deferred). Runs ≥2 passes unless the first is perfectly clean, then exits once a pass found-and-fixed ≤3 non-deferred findings with no Critical/High remaining — or only Low-severity ones, any count; halts for your go-ahead — run one more review iteration, continue, or stop — unless the loop converged cleanly (then it auto-continues) | `bmad-review-adversarial-general`, `bmad-review-edge-case-hunter` (`bmad-code-review`'s adversarial layers, run as parallel sub-agents per review model + one triage); the security review runs as an inline auto-bmad pass (no extra skill) | always |
| 7 | Per-story trace advisory (after review; non-blocking — surfaces uncovered ACs early) | `bmad-testarch-trace` | TEA on + risk-warranted, *not* last story of epic, long epic (≥6 stories) |
| 8 | Gates (asks if trace fails), project context, archive resolved deferred work, retrospective | `bmad-testarch-trace`/`nfr`/`test-review`, `bmad-generate-project-context`, `bmad-retrospective` | last story of epic |
| 9 | Push, open PR, wait for CI, mark story `done` (clean run), **ask whether to merge** (clean run, opt-in), final report | — | always |

Each phase ends with a conventional commit, so progress survives interruptions and is easy to review.

## Run a whole epic

`/auto-bmad epic` (or `/auto-bmad epic --epic N`) drives an **entire epic** — every actionable story — in one run, then **one PR**. It exists for epics that are too slow story-by-story: it keeps the autonomous `create-story → dev-story` core (with tests) for each story but **trims the heavy per-story code-review loop to a single thin review + fix**, and **batches the heavy adversarial review into one epic-wide integration pass** at the end. The result is one `epic/N-slug` branch, per-story commits on it, one CI wait, and one merge prompt.

- **It warns and asks you to confirm up front** — an epic runs **fully unattended through the review**: no per-story checkpoints, and **no review stop at all** (not even at the end). Review findings that need a decision are **auto-resolved with the reviewer's recommended fix/defer/dismiss** (surfaced in the epic report's **Auto-decided** section), and a review that can't converge cleanly **ships a draft** PR with the findings flagged. The only stops left are the **E0 preflight safety asks** (adopting a half-done epic / a base-branch readiness check) and the final **merge prompt**.
- **A best-guess on a high-severity finding still gets your eyes:** any Critical/High the run auto-decided forces the PR to a **draft** (epic stays at `review`) and lands in the report's *Needs human* — so you review it before merge.
- **Per-story safety stays:** every story must pass its own tests (the hard gate) and gets a quick review whose findings flow into the final integration review, so later stories don't build on unreviewed code.
- **It completes a half-done epic:** stories already finished — by the normal per-story `/auto-bmad` flow or by hand — are skipped (assumed merged into your base branch); epic mode runs only what's left. If a finished story's work is on an un-merged branch, it asks before proceeding.
- **One report, one status flip:** a single `reports/epic-N.md` rolls up every story; on a clean run all the epic's stories flip to `done` together. If anything is caveated (an open Critical/High, a Critical/High the run auto-decided, a waived gate, red CI), the whole epic stays at `review` — a single PR is either mergeable or not.

Delegation, profiles, TEA, resume, and the overrides that still apply all work as in per-story mode; epic mode uses the highest-effort delegate profiles throughout, so expect it to be slower and pricier per run than a single story (it's doing the whole epic). Full mechanics: `references/epic-pipeline.md`.

## Human-in-the-loop stops

auto-bmad runs autonomously between the points below — delegated sub-agents answer BMAD's interactive prompts with sensible defaults. It pauses for **you** only here:

| Stop | When | What you decide / do |
|------|------|----------------------|
| **First-run setup** | First `/auto-bmad` in a project | One-time questions: confirm `target_tools`, choose **Quick** (TEA on/off — plus a one-time framework/CI scaffolding offer if TEA's on and none is set up) or **Full** (also git + code-review prefs). Writes `config.yaml`, then stops — **start a new session and re-run `/auto-bmad`** so the first story runs on fresh context. |
| **Module setup** | `/auto-bmad setup` (or module not yet provisioned) | Confirm or adjust which AIs to provision delegate agents for (defaults to the ones your BMAD install targets). |
| **Code-review loop done** | Phase 7 — end of the review loop, whenever it did **not** converge cleanly (a clean convergence auto-continues with no stop) | Choose: run another review iteration (extends the loop by one full pass), continue, or stop. While paused you're encouraged to run an external review (a human, another model/AI); on continue auto-bmad **re-reviews** any changes you added (whole-story, full reviewer roster) and, if they're meaningful, asks once more: run another review iteration (fixes them in-pipeline), continue (ships the PR as a **draft** with the findings open — or as **ready** if you choose to override the draft), or stop — stop, fix, and re-run `/auto-bmad` to get the fixes re-reviewed. If the loop hit the iteration cap still unconverged (a Critical/High remaining, or >3 non-deferred findings that aren't all Low), the PR opens as a **draft**. Want a stop on every story regardless? Add the `stop after phase 7` override to the invocation. |
| **Epic trace gate failed** | Phase 8 — `bmad-testarch-trace` returns `FAIL` (requirements/ACs lack test coverage) | Choose: remediate & re-gate (auto-expand coverage, then re-run trace; capped, default 2), waive and continue (PR opened as a **draft** with the gaps noted), or stop. `CONCERNS` is advisory and doesn't pause. |
| **Merge the PR?** | Phase 9 — clean completion only (no blocker, code review converged, gates passed, CI green — auto-bmad waits for in-progress CI, cap `git.ci_wait_minutes`, default 30), with `git.offer_merge: true` (default). A run that instead ends as a **draft** PR (CI red or timed-out, or the unconverged-review / waived-gate cases above) or with a recorded blocker gets **no merge prompt** and stays at `review` for you to finish. | Choose: **Merge commit (default — preserves the per-phase auto-bmad commits for AI archaeology)** / **Rebase and merge** / **Squash and merge** / **Don't merge**. If you pick a merge style, a follow-up asks whether to **delete the branch**. auto-bmad runs the chosen `gh pr merge`; on failure (branch protection, required reviews, etc.) it surfaces the error and leaves the PR open. Opt out with `git.offer_merge: false` or `skip merge-prompt`. |
| **Re-running a completed story** | You target an already-`done` story | Confirm before its report log is overwritten; otherwise it won't redo the story. |
| **Story worked outside auto-bmad** | The story sits at `review`/`in-progress` but has **no auto-bmad state** (hand-driven story, or a lost state dir) | Choose: **enter at the matching phase** (recommended — `in-progress` ⇒ implement, `review` ⇒ code review), run the full pipeline anyway (a deliberate redo), or stop. |
| **Blocker / needs-human** | Any phase | Hard-stop: missing planning docs, a missing secret/credential, a required external service or manual step, a merge/rebase conflict, a dirty tree on the wrong branch, not a BMAD project, a missing required skill, or an ambiguous/not-found `--story`. It reports exactly what's needed and never pushes past it. |

Use overrides (below) if you want to add your own stops — e.g. `stop before code-review`.

## Overrides

Steer a single run by adding instructions to the invocation (natural language or flags) — e.g. `stop before code-review`, `start at phase 5`, `skip git commits`, `skip TEA`, `skip merge-prompt`, `max 5 review iterations`, `git mode local`, `dry run`. The orchestrator echoes how it interpreted them and which phases will run before executing. See `references/overrides.md`.

## Split a story across tools

The cleanest way to mix tools is **`delegation.cli_phases`** (see [Configuration](#configuration)): it routes chosen phases to another tool's CLI (`claude -p` / `codex exec` / `opencode run`) — at that phase's model + effort — so a **single, autonomous `/auto-bmad` run** mixes tools with no hand-off. Set it once and every run honours it — e.g. `cli_phases: { code_review_review_secondary: opencode }` to implement in your host tool but run the second-opinion review on a different vendor's model for diversity. The orchestrator builds the command and parses the result; the routed tool just needs its `auto-bmad`/`bmm` skills installed and (when it isn't the host) to be authenticated — the preflight hard-stops if not.

You can also hand a story off **by hand**, mid-pipeline — handy when you'd rather drive each tool interactively, or haven't set the other tool up as a headless CLI. The running tool is auto-detected every run and the pipeline is resumable, so stopping at a phase boundary in one tool and resuming in another just works — e.g. **implement in Claude Code, review in Codex**:

```text
# In Claude Code — runs phases 0–6 (create-story → dev-story), committing each phase
/auto-bmad stop before code-review

# In Codex, same project directory — resumes at phase 7 (code-review) through the PR
/auto-bmad
```

Swap the tools for the reverse (implement in Codex, review in Claude Code). A plain no-arg `/auto-bmad` resumes the interrupted pipeline at the next unfinished phase; `start at phase 7` is the explicit equivalent (it first validates the story is implemented). The same pattern works at any phase boundary — e.g. `stop after phase 5`, then resume — so you can route any slice of the pipeline to whichever tool you prefer for it.

**Prerequisites for the manual hand-off:** install the `auto-bmad` skill in **both** tools and provision delegates for both — `delegation.target_tools` must list `claude-code` *and* `codex` (confirm at `/auto-bmad setup`). Keep git commits **on** (the default): the per-phase checkpoint commits and the shared `_bmad-output/auto-bmad/state/` file are exactly what let the other tool pick up where the first left off.

## Configuration

`_bmad-output/auto-bmad/config.yaml` (created on first run) controls:

- **TEA** on/off — including the non-blocking long-epic per-story trace advisory (`tea.story_trace_advisory`: toggle + epic-length & distance-to-gate thresholds).
- **Git** — mode (PR vs local-only) and branch prefix.
- **Code review** — iteration cap (`code_review.max_iterations`); the optional second/third parallel review models (`code_review_review_secondary` / `code_review_review_tertiary` in `phase_profiles`; blank disables); and the dedicated **security review** (`code_review.security_review`, default on — its model is `code_review_security` in `phase_profiles`, blank ⇒ the primary reviewer's profile).
- **Delegation** — the per-phase profile mapping (`phase_profiles`) and the per-tool model + effort for each delegate (`profiles`). You can also **add custom profiles** (e.g. an `ab-ultradeep` for one phase): same field set as the shipped ones, name starting with `ab-`, then point `phase_profiles` entries at it and run `/auto-bmad reprovision`.
- **`delegation.target_tools`** — the tools agents are provisioned for. Setup defaults this to whichever AIs your BMAD install already targets (detected from `.claude/skills` for Claude Code, `.agents/skills` for Codex, `.opencode/skills` for opencode) and lets you confirm or adjust. **Provision more than one and the same project runs in any of them** — the running tool is auto-detected each run, so you never reconfigure when you switch. opencode's `opencode.model` ships **blank** (delegates inherit your opencode default model); set it per profile for per-phase model tiering and cross-vendor review diversity.
- **`delegation.cli_phases`** — opt-in per-phase external-CLI routing (a phase→tool map, empty by default): delegates chosen phases to `claude -p` / `codex exec` / `opencode run` instead of an in-tool sub-agent, for cross-tool (and, via opencode, cross-vendor) diversity (e.g. `{ code_review_review_secondary: opencode }`); model + effort still come from that phase's `profiles` block.

After editing `profiles` (e.g. to set your Codex model names or opencode `provider/model`), run `/auto-bmad reprovision`; to undo your edits and restore the shipped defaults, run `/auto-bmad reset-defaults` (scope it to one profile, all profiles, or the phase mapping — your git/TEA/delegation settings are never touched; an all-profiles reset also removes custom profiles, after confirming). See `references/delegation-runtime.md` and `references/state-and-resume.md` for the full schema.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) and our [Code of Conduct](./CODE_OF_CONDUCT.md).

## License

[MIT](./LICENSE) © 2026 Stefano Ginella
