# Module Setup

Standalone module self-registration. This file is loaded when:
- The user passes `setup`, `configure`, `install`, or `reprovision` as an argument
- The module is not yet provisioned for this project — its runtime config `{output_folder}/auto-bmad/config.yaml` is absent (the single condition; nothing else marks a project as provisioned)

## Overview

Registers this standalone module into a project. Module identity (name, code, version) comes from `./assets/module.yaml` (sibling to this file). Setup registers the module's help entries, and — through the skill's first-run flow (or `reprovision`) — syncs auto-bmad's review layers into `bmad-build-auto`'s team customization:

- **Help catalog** — auto-bmad's own `{project-root}/_bmad/abm/module-help.csv` (the per-module file the BMAD installer merges on every install/update, so the rows survive a BMAD re-install) **plus** a merge into the live `{project-root}/_bmad/_config/bmad-help.csv` that `/bmad-help` reads (anti-zombie: existing `abm` rows are replaced before fresh ones are written, so stale values never persist). Never `_bmad/module-help.csv` — nothing upstream reads that legacy shared file any more.
- **Review layers** — the marker-fenced managed region of `{project-root}/_bmad/custom/bmad-build-auto.toml` (`auto-bmad-security` / `auto-bmad-cross-model`, per the runtime config's `code_review.security_layer` / `cross_model_layer`), written by `./scripts/build_auto_custom.py` (see "Sync review layers" below). **Project-wide caveat:** these layers also run for a manual `/bmad-build-auto` in this project.

auto-bmad has **no** install-time variables: **all** runtime settings live exclusively in auto-bmad's own config, `{output_folder}/auto-bmad/config.yaml`, written by the skill's **first-run flow** (`references/config-commands.md`) — **not** by this setup file. Nothing is rendered into the repo (no agent files): every pipeline step runs in a generic host subagent spawned with the phase profile's model.

**auto-bmad never writes the central BMAD config.** That file is installer-owned: `_bmad/config.toml` (+ `config.user.toml`, and the never-installer-touched `_bmad/custom/config.toml` / `config.user.toml`), resolved by BMAD's own `resolve_config.py`. auto-bmad neither reads nor writes an `abm` section in it — registering there would be inert (BMAD ignores it) and confusingly shadow the installer's own `[modules.abm]`. It READS the central config for `output_folder` and the BMM artifact paths ONLY through this call (the same one SKILL Step 0 and the On-activation gate make; obey its `hard_stop` — a missing/unparseable `_bmad/config.toml` or a `python3` older than 3.11 stops here):

```bash
python3 ./scripts/preflight.py --project-root "{project-root}" --central-config-only
```

`{project-root}` is a **literal token** in config values — never substitute it with an actual path. It signals to the consuming LLM that the value is relative to the project root, not the skill root. (Filesystem arguments to the scripts below MUST be resolved to real paths.)

## Check Existing Config

1. Read `./assets/module.yaml` for module metadata (the `code` field is the module identifier; there are no variable definitions)
2. Check whether auto-bmad is already set up here — its runtime config `{output_folder}/auto-bmad/config.yaml` exists (`{output_folder}` = `central_config.output_folder` from the preflight call above). If so, inform the user this is an update (reconfiguration). (Don't key this off an `abm` row in the help catalog — the BMAD `--custom-source` installer pre-merges that row, so it would false-positive on a fresh auto-bmad setup.)

If the user provides arguments (e.g. `accept all defaults`, `--headless`), pass them through to the first-run flow, which maps them to config keys, uses defaults for the rest, and skips interactive prompting. Still display the full confirmation summary at the end.

## Collect Configuration

Nothing is collected here.

### Core Config

**Don't collect or write core settings.** auto-bmad runs on top of an existing BMAD install (BMAD >= 6.11: `_bmad/config.toml` present), so `user_name`, `communication_language`, `document_output_language`, and `output_folder` are already set by the installer in the central BMAD config. auto-bmad reads `output_folder` (and the BMM artifact paths) from there through `preflight.py --central-config-only` and never re-writes them.

### Module Config

`./assets/module.yaml` defines **no** variables with a `prompt` field, so there is no module question to ask. Every auto-bmad setting (setup depth, TEA, git, the follow-up review pass, the extra review layers, spec approval, delegate model profiles) is interviewed and persisted by the first-run flow into `{output_folder}/auto-bmad/config.yaml` (not written here).

## Write Files

Register auto-bmad's help entries — two writes, in this order:

1. **Copy** `./assets/module-help.csv` to `{project-root}/_bmad/abm/module-help.csv` (create the `_bmad/abm/` directory if needed; overwrite — it is auto-bmad's own file). This is what the BMAD installer picks up when it regenerates `bmad-help.csv` on the next install/update.
2. **Merge** the same rows into the live catalog:

```bash
python3 ./scripts/merge-help-csv.py --target "{project-root}/_bmad/_config/bmad-help.csv" --source ./assets/module-help.csv --module-code {module-code}
```

It outputs JSON to stdout (anti-zombie: existing `abm` rows are replaced). If it exits non-zero, surface the error and stop. Run `./scripts/merge-help-csv.py --help` for full usage. Do **not** pass `--legacy-dir` — that option deletes `_bmad/abm/module-help.csv` (the file step 1 just wrote) and `_bmad/core/module-help.csv`.

**Do not write the central BMAD config — there is no config write here.** This is deliberate, not an omission:

- auto-bmad's runtime settings are persisted to `{output_folder}/auto-bmad/config.yaml` by the **first-run flow**, which runs right after this file returns (see `references/config-commands.md`). Don't pre-write it here.
- The central `_bmad/config.toml` (+ layers) is **installer-owned**; a unified `_bmad/config.yaml` is inert (BMAD's `resolve_config.py` never reads it) and shadows the installer's layout. **Skip it.**
- If auto-bmad was installed through BMAD's `--custom-source` installer, that installer has **already** registered `[modules.abm]` in `_bmad/config.toml` (and a per-module `_bmad/abm/config.yaml`). Leave those untouched — do not duplicate or rewrite them.

(`./scripts/merge-config.py` ships only to satisfy the standalone-module validator; auto-bmad does **not** invoke it. Don't reintroduce a call to it.)

## Create Output Directories

auto-bmad defines **no** path-type install variables and no `directories` array in `./assets/module.yaml`, so there is nothing to create here. `output_folder` already exists from the BMAD install, and the first-run flow plus the state writers create `{output_folder}/auto-bmad/` (config, state, reports) on demand. Skip this step.

## Sync review layers (auto-bmad)

auto-bmad's extra review layers (`auto-bmad-security` — gated by `code_review.security_layer`; `auto-bmad-cross-model` — gated by `code_review.cross_model_layer`, whose external-CLI command is built from the `cross_model_layer` profile) live in a marker-fenced managed region at the end of `{project-root}/_bmad/custom/bmad-build-auto.toml`, rendered from `./assets/bmad-custom/bmad-build-auto.toml` with the model strings baked from the runtime config's `profiles`. **They are project-wide: bmad-build-auto runs them for a manual `/bmad-build-auto` too** — say so when reporting.

- **First setup:** the sync happens inside the first-run flow, right after `config.yaml` is written (`references/config-commands.md` → First-run flow, step 4). Nothing to run here.
- **`reprovision`** (the runtime config already exists — otherwise stop with "run `/auto-bmad setup` first"): skip everything above and run only

  ```bash
  python3 ./scripts/build_auto_custom.py --project-root "{project-root}" --config "{output_folder}/auto-bmad/config.yaml" --apply
  ```

  Surface its JSON (`status` applied|noop, `layers`, `warnings`, `errors`); exit 2 = nothing was written — show `errors` and stop (a duplicate of one of our layer ids outside the managed region, or an invalid TOML file, needs the user's hand). Removing a layer = set `code_review.security_layer: false` / `cross_model_layer: ""` in config.yaml and re-run this. The orchestrator also re-checks freshness at Phase 0 (`--check` → auto `--apply`), so users rarely have to run this by hand.

## Confirm

Use the script JSON output to display what was registered — help entries added (`_bmad/abm/module-help.csv` + `_bmad/_config/bmad-help.csv`), the review layers synced (or "synced by the first-run flow next"), and fresh install vs update. Note that runtime settings are persisted to `{output_folder}/auto-bmad/config.yaml` by the first-run flow that follows.

If `./assets/module.yaml` contains `post-install-notes`, display them.

Then display the `module_greeting` from `./assets/module.yaml` to the user.

## Return to Skill

Setup is complete (help registered; review layers synced or about to be by the first-run flow). Resume the main skill's normal activation flow. If this was a `setup`/`configure`/`reprovision`-only invocation, stop here (already reported). If it was a run-intent invocation that triggered setup only because the module wasn't set up yet, continue into the Procedure — its first-run flow writes the runtime config `{output_folder}/auto-bmad/config.yaml`, syncs the review layers, then **stops for a fresh session** (`references/config-commands.md` → "First-run flow", step 4).
