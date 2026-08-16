# CLI route — the opt-in per-phase external-CLI delegation path

What it is: the full contract for `delegation.cli_phases` — the `cli_delegate.py` resolver, the per-tool argv/validation matrix, the prompt recipe, the launch/wait/wedge model, result parsing and failure detection, plus the cross-model review layer's baked shell shapes.
When it is loaded: ONLY when `delegation.cli_phases` is non-empty (a phase is routed), or when resolving `code_review.cross_model_layer` needs the layer shapes. An empty map ⇒ every phase uses its tier and this file is never read.

## Per-phase external-CLI routing (opt-in — sits *above* the tiers)

A phase can be delegated to an **external CLI** — `claude -p`, `codex exec` or `opencode run` — via the `delegation.cli_phases` map:
- Keys = the ten `phase_profiles` keys; value = a tool name (`claude` | `codex` | `opencode`).
- Absent/empty ⇒ **every phase uses its normal tier**.
- Schema: `state-and-resume.md`. Examples: `assets/config-defaults.yaml`.

**Before spawning any phase, check `cli_phases` first**; if the phase key is present, take the CLI path. It is **still delegation** — you build the command, deliver the prompt, capture the child's structured-result block, then do your own git/finalize bookkeeping. You never read or write story code yourself.

Routing `build` or `followup_review` = build-auto runs *inside* `codex exec` / `claude -p` / `opencode run`: the external CLI plans/implements, and its own review layers review **and** triage/patch. The orchestrator's after-step reads are unchanged (`story_plan.py --spec <spec_path>`).

**Resolve the invocation with the helper — do not hand-build the command** — the per-tool flag matrix lives in the script, tested:

```bash
python3 {skill-root}/scripts/cli_delegate.py --phase <phase> \
  --config <output_folder>/auto-bmad/config.yaml --project-root <project_root> \
  --story-key <story_key> --host <resolved-host: claude-code|codex|opencode> --mkdir [--label <label>]
```

Pass the **resolved** host detected this run, not the literal config `auto` (any other value ⇒ the auth probe always runs). Use a distinct `--label` per repeated delegate of the same phase and story (e.g. `pass-2` for a second follow-up review pass, `rereview` for the external-change re-review) so `capture_log` / `exit_file` / `-o` paths don't collide.

It prints one JSON object. `routed:false` ⇒ use the normal tier. Otherwise it gives:
- `tool`, `profile`, `model`, `effort` — from the phase's profile's matching tool block (`claude.model`+`effort`, `codex.model`+`reasoning_effort`, `opencode.model`+`variant`).
  - **For opencode both `model` and the variant are optional — blank ⇒ inherit the user's opencode defaults**, never a hard-stop.
- `argv` (prompt-less), `prompt_via` (`stdin` for claude/codex, `arg` for opencode), `cwd`, the OS-temp `capture_log`, `exit_file`, `prompt_file`, `launch_cmd`, and `result_source` / `result_format` / `result_field` / `error_field`.

Per-tool argv:
- claude: `claude -p --model M --effort E --output-format json --dangerously-skip-permissions` (prompt on stdin).
- codex: `codex exec -m M -c model_reasoning_effort=E --dangerously-bypass-approvals-and-sandbox -C ROOT -o LASTMSG --ephemeral` (prompt on stdin).
- opencode: `opencode run [-m M] [--variant V] --format json --dir ROOT --auto <prompt>` (prompt = final positional arg; `--auto` auto-approves permissions).

It also runs the **preflight `validation`**, checking three things:
- **binary** on PATH.
- **that tool's BMAD skills present** — looked up in the tool's own skills dirs, because the CLI path consumes nothing provisioned by auto-bmad. Project paths are relative to the project root:
  - claude: `.claude/skills`.
  - codex: `.agents/skills`, `.codex/skills`, `~/.codex/skills`.
  - opencode: `.opencode/skills`, `~/.config/opencode/skills`, the `command`/`commands` siblings of both (some BMAD opencode installs expose the skills as slash-command files `bmad-*.md` there), plus the cross-tool `.claude/skills` and `.agents/skills` in the project.
- **auth** for the **non-host** tool only (lenient for opencode — see notes below).

**`ok:false` ⇒ hard-stop** with its `errors` (exit 1 = validation failed; exit 2 = resolution error, e.g. a phase whose `phase_profiles` value is blank — "no phase_profiles mapping"); never silently degrade to an in-tool subagent. Echo the routed phases + resolved tool/model/effort in the Phase 0 preflight and final report, next to `delegation.mode`.

**Prompt recipe** — a CLI invocation has no host-provided delegate context, so the prompt is assembled exactly as in-tool (`delegation.md`): role line + the entry's body (absolute paths) + the shared tail. That is the complete prompt; add no second operating block, so a CLI-routed delegate runs under exactly the same rules as an in-tool one.

**Launch it via the helper's `launch_cmd` — never hand-roll the spawn.** The plan emits a ready `launch_cmd` (a `bash -c` body) alongside `prompt_file` and `exit_file`. To spawn:
- Write the assembled prompt (above) to `prompt_file`.
- Run the delegate as a **background** task — `bash -c "$launch_cmd"`.

The emitted `launch_cmd` itself does the following:
- `cd`s into `cwd`.
- Delivers the prompt — stdin for claude/codex; final positional arg for opencode (`opencode run` does NOT read stdin).
- Redirects stdout+stderr to `capture_log`.
- Writes the child's `$?` to `exit_file` as a **completion sentinel**.

Use the emitted `launch_cmd` (every token `shlex.quote`d, wrapped in `bash -c`) precisely, so the spawn does NOT ride the host's interactive shell: a hand-rolled `( … ) & pid=$!` wrapper breaks under fish, and zsh leaves an unquoted argv scalar unsplit (`SH_WORD_SPLIT` off) and execs it as one filename.

Capture the task's pid where the host exposes it and pass it to the waiter.

**Run the CLI delegate in the background — never foreground.** (This is the orchestrator's *host shell* call; it is unrelated to the foreground rule for in-tool subagents above.)
- Process exit is the completion signal.
- Total runtime is UNBOUNDED — no phase has a wall-clock cap.

Host shell tools cap foreground commands far below real delegate runtimes (Claude Code: 10-min max; a `build` run can take **hours**) — a delegate that runs for hours is healthy and must **never** be killed on a clock.

Wait for it **with the helper**:
- **Never** a hand-rolled poll loop.
- **Never** `grep` `capture_log` for a result pattern — a format mismatch makes such a loop spin forever after the process is long gone.

Pick the wait by host:
- **Host that re-invokes you when a background task exits** (e.g. Claude Code `run_in_background`): background the delegate, then classify once on wake — `cli_delegate.py --once --capture-log <capture_log> --exit-file <exit_file> [--pid <pid>]`.
  - Claude Code hands back a task id, not a unix pid, so `--pid` is usually unavailable here.
  - A post-exit wake with **no sentinel** then means the delegate crashed; treat it as `dead-no-sentinel`.
- **Host without exit-notification:** background the **blocking** wait beside the delegate — `cli_delegate.py --wait …`. It MUST itself be backgrounded, or it hits the same foreground cap.

Wedge model — so a long *quiet* step is never falsely killed:
- **With a `--pid` a live process is never idle-wedged** — `claude -p` emits nothing until its final envelope, so log-silence ≠ liveness. The only stops are:
  - the real exit.
  - a crash (`dead-no-sentinel`).
  - the **opt-in** `--max-wait` absolute cap (default 0 = unbounded).
- **Without** a pid, the `--idle-timeout` backstop applies — default 1800 s (30 min) of *no new `capture_log` output*, a SILENCE allowance, **NOT** a runtime cap.

Any non-`exited` verdict (`dead-no-sentinel` / `wedged-idle` / `max-wait`; exit 1) is a **failed delegation: hard-stop** (surface `capture_log`). `running` from `--once` = not done yet.

On `status:"exited"`, read `result_source`:
- claude → parse `result_field` (`.result`) from the JSON envelope; `error_field` (`.is_error`) true = failed delegation.
- codex → read the `-o` last-message file verbatim.
- opencode → pass `capture_log` (the `--format json` event stream) through `cli_delegate.py`'s `extract_opencode_result()`.

**Failure detection is uniform — never proceed on an empty result.** A missing/blank required field is a **failed delegation: hard-stop.** Per tool:
- claude → `.result` absent/blank OR `.is_error` true.
- codex → empty/absent `-o` file.
- opencode → `extract_opencode_result` returns no message.

`capture_log` is **debug-grade** and lives **outside the repo**.
- Surface its path **only when a delegation fails**.

**Per-tool sandbox/auth notes:**
- **codex** runs with `--dangerously-bypass-approvals-and-sandbox` — full access, no inner OS sandbox.
  - This is parity with claude's `--dangerously-skip-permissions` and opencode's `--auto`.
  - It is required: its bubblewrap sandbox can't create a namespace inside a nested container. Run auto-bmad in an outer sandbox (see README).
- **opencode** runs with `--auto` — headless auto-approve.
  - Its auth preflight is **lenient** — keyless/local/config providers ⇒ "0 credentials" never hard-stops, so it won't catch a missing cloud login.
  - An unauthenticated `opencode run` on a cloud/Zen model **blocks indefinitely** — make sure opencode is logged in before routing to it.

**The cross-model review layer is not a routed phase.** `cli_delegate.py --layer-argv --config … --project-root … [--tool codex|claude|opencode]` builds the ONE shell line for the `auto-bmad-cross-model` review layer (tool = `code_review.cross_model_layer`, profile = `phase_profiles.cross_model_layer`); `build_auto_custom.py` bakes it into `_bmad/custom/bmad-build-auto.toml` at setup/`reprovision`, and **build-auto's parent runs it during its own review step — the orchestrator never runs it.** Verified shapes (`ROOT` = absolute project root; `TIMEOUT` = `timeout -k 30 1200 ` / `gtimeout -k 30 1200 ` when on PATH at bake time, else empty; `<DIFF_FILE>` = the diff temp file build-auto substitutes; each closes stdin so no CLI blocks on a pipe):
- claude: `cd "ROOT" && TIMEOUT claude -p "PROMPT" --model M --effort E --output-format text --allowedTools "Read,Grep,Glob" </dev/null`
- codex: `cd "ROOT" && TIMEOUT codex exec -m M -c model_reasoning_effort=E -c approval_policy=never -s read-only -C "ROOT" --ephemeral -o "<DIFF_FILE>.review" "PROMPT" </dev/null >/dev/null 2>&1; cat "<DIFF_FILE>.review"`.
- opencode: `cd "ROOT" && TIMEOUT opencode run [-m M] [--variant V] --dir "ROOT" --auto "PROMPT" </dev/null`
