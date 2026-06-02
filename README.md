# auto-bmad

[![license: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](./LICENSE) [![Version](https://img.shields.io/badge/version-0.10.3-blue.svg)](https://github.com/stefanoginella/auto-bmad) [![BMAD-METHOD](https://img.shields.io/badge/BMAD--METHOD-module-8A2BE2.svg)](https://github.com/bmad-code-org/BMAD-METHOD) [![Tested with BMAD 6.8.x](https://img.shields.io/badge/tested%20with%20BMAD-6.8.x-8A2BE2.svg)](https://github.com/bmad-code-org/BMAD-METHOD) [![Works best with: Claude Code | Codex](https://img.shields.io/badge/works%20best%20with-Claude%20Code%20%7C%20Codex-00A3A3.svg)](#install) [![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](./CONTRIBUTING.md)

A **BMAD module** that runs the **full [BMAD](https://github.com/bmad-code-org/BMAD-METHOD) story implementation workflow end-to-end — one story at a time**, on **Claude Code or Codex**.

`auto-bmad` chains the core BMM skills (`create-story` → `dev-story` → `code-review`) and the optional TEA (Test Architect) skills into a single resumable pipeline. It detects the next story from `sprint-status.yaml` (or takes one as an argument), runs every step in an isolated git branch with conventional-commit checkpoints, opens a PR, and finishes with a report of the PR link, open questions, deferred work, and anything that needs your attention — then stops so **you** decide when to start the next story.

The orchestrator **only delegates and reports.** Every BMAD step runs inside a sub-agent, with the model and thinking effort matched to the stakes of the step (e.g. Opus/max for high-stakes implementation, a faster model for low-stakes mechanics). On **Claude Code and Codex** those delegates are real, tuned subagents (`.claude/agents` / `.codex/agents`, generated from a configurable profiles block); on a tool with generic subagents it falls back to those (untuned), and on one with none it runs steps inline — same pipeline either way.

> Requires the BMAD skills it orchestrates (`bmm`, plus `tea` for the test phases) and a `_bmad/` config in your project — the installer below can add these in the same run. auto-bmad drives those skills; it does not replace them.

> **Compatibility:** tested against the **[BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) v6 skill line**, currently up to **6.8.0** (and the **6.8.1-next.0** prerelease).

> ⚠️ **It can't save you from bad inputs.** auto-bmad automates the *workflow*, not judgment — the quality of what comes out is capped by what goes in. Vague epics, thin acceptance criteria, or a shaky architecture produce vague, untrustworthy code, just faster and more confidently. The automated code-review loop and the human-in-the-loop stops below are guardrails, not guarantees; the real leverage is clear stories and a sound design *before* you press go. Garbage in, garbage out.

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

This re-clones the repo into BMAD's module cache and rewrites the install manifest with auto-bmad's source, so the update applies and future `bmad update` runs resolve it cleanly. To track development versions ahead of a tagged release, add the prerelease installer channel: `npx bmad-method@next install --action update --custom-source https://github.com/stefanoginella/auto-bmad --yes`.

> ⚠️ **Don't update auto-bmad with `--action quick-update`** (which is also the interactive default for an existing install). quick-update only re-pulls modules whose source is already cached under `~/.bmad/cache/`, and it skips custom-source re-cloning entirely — so unless auto-bmad's repo is already cached from a prior `--custom-source` run, it is **silently skipped** and you keep seeing `[warn] … could not locate module.yaml for 'abm'` on the next `bmad update`. Always re-supply `--custom-source` as above (interactively: choose **"Modify BMAD Installation"** and re-enter the custom source — don't accept the quick-update default).

> 💡 **Delegate agents re-render themselves after an update.** auto-bmad generates its tuned subagents from `profiles`/templates, so a module update (or a `profiles` edit) would otherwise leave the generated `.claude/agents` / `.codex/agents` stale. The next `/auto-bmad` run **detects this at preflight and reprovisions automatically**, noting it in the report — so you normally don't need to do anything. To refresh them yourself (e.g. right after editing `profiles`), run `/auto-bmad reprovision`. Nothing else needs reconfiguring — the running tool is auto-detected every run.

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
/auto-bmad stop before code-review        # steer a single run (see Overrides)
/auto-bmad --story 1-3 skip git commits
/auto-bmad reprovision                    # re-render delegate agents after editing profiles
/auto-bmad reset-defaults                 # discard profile retunes, restore shipped defaults
```

> 💡 **Run it in an auto-approve / "YOLO" mode.** auto-bmad is built to run autonomously between the [human-in-the-loop stops](#human-in-the-loop-stops) below, so it works best when the host tool isn't prompting for permission on every tool call — Claude Code's `--dangerously-skip-permissions` (aka YOLO mode), or Codex's full-auto/auto-approve mode. Because that hands the agent broad access, run it inside a sandbox: see [aicontainer](https://github.com/stefanoginella/aicontainer) for a containerized environment that lets you skip permission prompts safely.

- **First run in a project** asks a few one-time setup questions — confirms which AIs to provision delegate agents for (`target_tools`, re-detected from your installed skill dirs), then **Quick** (default: TEA on/off only, sensible defaults for the rest) or **Full** (also git mode/prefix + code-review iteration cap) — writes `_bmad-output/auto-bmad/config.yaml`, then **stops and asks you to start a fresh session** so the first story runs clean (configuration pollutes the context window).
- **No-argument `/auto-bmad` resumes unfinished work first.** It picks up an interrupted auto-bmad pipeline if one exists, otherwise the next actionable story by status (`in-progress → review → ready-for-dev → backlog`) — it doesn't jump straight to a fresh backlog item. Pass a story id to target one explicitly.
- **A clean run marks the story `done`** (story file + `sprint-status.yaml`) at the end, so the next `/auto-bmad` advances to the next story instead of re-picking the one just finished. On a clean completion auto-bmad **waits for in-progress CI** (cap `git.ci_wait_minutes`, default 30) and then **asks** whether to merge — **Merge commit (default)** / Rebase / Squash / Don't merge, plus a delete-branch sub-question. Merge commit is the default because auto-bmad's per-phase commits (initial dev, review fixes, the report commit) are the richest signal an AI later running `git log`/`blame`/`bisect` on the story can use to reconstruct what happened — squashing collapses that. It never merges silently; "Don't merge" leaves the PR open for you, same as before. The merge prompt is opt-out: set `git.offer_merge: false` or pass `skip merge-prompt` for a single run. A run that ends as a **draft** PR (unresolved review / waived gate / CI red or timed-out) or with a recorded blocker stays at `review` for you to finish — no merge prompt offered.
- The pipeline is **resumable** — re-run `/auto-bmad` to continue from the last completed phase after an interruption.
- **Code review starts on Opus** and alternates Opus/Sonnet across iterations. If Critical/High findings remain after the iteration cap (default 3), it **asks you** whether to run another pass, accept the findings and continue (the eventual PR is opened as a draft), or stop.
- A per-story **report log** is saved to `_bmad-output/auto-bmad/reports/<story>.md` — each run appends a timestamped section (never overwritten on resume). On a clean run the file is **committed before push so it ships in the PR diff**; it holds the story-level outputs (overrides, TEA outcomes, timing — total elapsed plus an AI-run vs human-wait split, open questions, deferred work, planning drift (epic-end), blockers, next-story preview). PR / CI / merge / final-status details are printed to chat only (they're already retrievable from GitHub and the BMAD status files, so the file never needs touching after the PR/CI/merge resolve).
- It **stops and tells you** whenever something genuinely needs a human (missing planning docs, merge conflicts, missing credentials, etc.).

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
| 7 | Code review (Opus-first, alternating models, ≤3 iters; asks if unresolved) | `bmad-code-review` | always |
| 7 | Per-story trace advisory (after review; non-blocking — surfaces uncovered ACs early) | `bmad-testarch-trace` | TEA on + risk-warranted, *not* last story of epic, long epic (≥6 stories) |
| 8 | Gates (asks if trace fails), project context, retrospective | `bmad-testarch-trace`/`nfr`/`test-review`, `bmad-generate-project-context`, `bmad-retrospective` | last story of epic |
| 9 | Push, open PR, wait for CI, mark story `done` (clean run), **ask whether to merge** (clean run, opt-in), final report | — | always |

Each phase ends with a conventional commit, so progress survives interruptions and is easy to review.

## Human-in-the-loop stops

auto-bmad runs autonomously between the points below — delegated sub-agents answer BMAD's interactive prompts with sensible defaults. It pauses for **you** only here:

| Stop | When | What you decide / do |
|------|------|----------------------|
| **First-run setup** | First `/auto-bmad` in a project | One-time questions: confirm `target_tools`, choose **Quick** (TEA on/off + framework/CI scaffolding) or **Full** (also git + code-review prefs). Writes `config.yaml`, then stops — **start a new session and re-run `/auto-bmad`** so the first story runs on fresh context. |
| **Module setup** | `/auto-bmad setup` (or module not yet registered) | Confirm or adjust which AIs to provision delegate agents for (defaults to the ones your BMAD install targets). |
| **Code review didn't converge** | Phase 7 — iteration cap reached with unresolved Critical/High findings | Choose: run another review + fix pass, accept and continue (the PR is opened as a **draft**), or stop. |
| **Epic trace gate failed** | Phase 8 — `bmad-testarch-trace` returns `FAIL` (requirements/ACs lack test coverage) | Choose: remediate & re-gate (auto-expand coverage, then re-run trace; capped, default 2), waive and continue (PR opened as a **draft** with the gaps noted), or stop. `CONCERNS` is advisory and doesn't pause. |
| **Merge the PR?** | Phase 9 — clean completion only (no blocker, code review converged, gates passed, CI green), with `git.offer_merge: true` (default) | Choose: **Merge commit (default — preserves the per-phase auto-bmad commits for AI archaeology)** / **Rebase and merge** / **Squash and merge** / **Don't merge**. If you pick a merge style, a follow-up asks whether to **delete the branch**. auto-bmad runs the chosen `gh pr merge`; on failure (branch protection, required reviews, etc.) it surfaces the error and leaves the PR open. Opt out with `git.offer_merge: false` or `skip merge-prompt`. |
| **Re-running a completed story** | You target an already-`done` story | Confirm before its report log is overwritten; otherwise it won't redo the story. |
| **Blocker / needs-human** | Any phase | Hard-stop: a missing secret/credential, a required external service or manual step, a merge/rebase conflict, a dirty tree on the wrong branch, not a BMAD project, a missing required skill, or an ambiguous/not-found `--story`. It reports exactly what's needed and never pushes past it. |

Use overrides (below) if you want to add your own stops — e.g. `stop before code-review`.

## Overrides

Steer a single run by adding instructions to the invocation (natural language or flags) — e.g. `stop before code-review`, `start at phase 5`, `skip git commits`, `skip TEA`, `skip merge-prompt`, `max 5 review iterations`, `git mode local`, `dry run`. The orchestrator echoes how it interpreted them and which phases will run before executing. See `references/overrides.md`.

## Split a story across Claude Code and Codex

The running tool is auto-detected every run and the pipeline is resumable, so you can hand a single story off between tools mid-pipeline — e.g. **implement in Claude Code, review in Codex** (or the reverse). There's no built-in per-phase tool switching; it's a manual workaround built from overrides: run part of the pipeline in one tool, stop at a phase boundary, then resume in the other.

**Prerequisites:** install the `auto-bmad` skill in **both** tools and provision delegates for both — `delegation.target_tools` must list `claude-code` *and* `codex` (confirm at `/auto-bmad setup`). Keep git commits **on** (the default): the per-phase checkpoint commits and the shared `_bmad-output/auto-bmad/state/` file are exactly what let the other tool pick up where the first left off.

Implement in Claude Code, review in Codex:

```text
# In Claude Code — runs phases 0–6 (create-story → dev-story), committing each phase
/auto-bmad stop before code-review

# In Codex, same project directory — resumes at phase 7 (code-review) through the PR
/auto-bmad
```

Implement in Codex, review in Claude Code — same idea, tools swapped:

```text
# In Codex
/auto-bmad stop before code-review

# In Claude Code
/auto-bmad                 # or, explicitly: /auto-bmad start at phase 7
```

A plain no-arg `/auto-bmad` resumes the interrupted pipeline at the next unfinished phase; `start at phase 7` is the explicit equivalent (it first validates the story is implemented). The same pattern works at any phase boundary — e.g. `stop after phase 5`, then resume — so you can route any slice of the pipeline to whichever tool you prefer for it.

## Configuration

`_bmad-output/auto-bmad/config.yaml` (created on first run) controls TEA on/off (including the non-blocking long-epic per-story trace advisory, `tea.story_trace_advisory` — toggle + `min_epic_stories` threshold), git mode (PR vs local-only), branch prefix, code-review iteration cap + model alternation, the per-phase profile mapping (`phase_profiles`), and the per-tool model + effort for each delegate (`profiles`). It also records `delegation.target_tools` — the tools agents are provisioned for. Setup **defaults this to whichever AIs your BMAD install already targets** (detected from where the skill is installed — `.claude/skills` for Claude Code, `.agents/skills` for Codex) and lets you confirm or adjust. **Provision more than one and the same project works in either** — the running tool is auto-detected each run, so you never reconfigure when you switch. After editing `profiles` (e.g. to set your Codex model names), run `/auto-bmad reprovision`; to undo your edits and restore the shipped defaults, run `/auto-bmad reset-defaults` (scope it to one profile, all profiles, or the phase mapping — your git/TEA/delegation settings are never touched). See `references/state-and-resume.md` for the full schema.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) and our [Code of Conduct](./CODE_OF_CONDUCT.md).

## License

[MIT](./LICENSE) © 2026 Stefano Ginella
