# Module Validation Report — `abm` (Auto-BMAD Orchestrator)

- **Date:** 2026-08-16
- **Validator:** bmad-module-builder (Validate Module)
- **Module type:** standalone single-skill (`auto-bmad`)
- **Status:** ✅ PASS — ready for use (0 findings)

## Structural validation (script)

`python3 .claude/skills/bmad-module-builder/scripts/validate-module.py .`

**PASS** — standalone module, 1 skill (`auto-bmad`), 3 CSV entries. All required
standalone files present (`module-setup.md`, `module.yaml`, `module-help.csv`,
`merge-config.py`, `merge-help-csv.py`). 0 findings (critical/high/medium/low all 0).

## Quality assessment (LLM review)

| Dimension | Result |
| --- | --- |
| Completeness | ✅ All SKILL.md capabilities registered: `AB` = run pipeline, `AE` = run epic, `AC` = configure (bundles `setup\|configure\|install\|reprovision\|reset-defaults\|config-check`). No unregistered capability found. |
| Accuracy | ✅ Each row's `action`/`args` match SKILL.md's On-activation gate and Procedure. |
| Description quality | ✅ All three verb-first, specific, one sentence, no filler. |
| Menu codes | ✅ `AB`/`AE`/`AC` intuitive, shared `A` (auto-bmad) prefix. |
| Ordering & relationships | ✅ Empty before/after + `required: false` correct for a standalone orchestrator with no fixed sequence. |
| Cross-file consistency | ✅ `module.yaml`, `module_greeting`, `post-install-notes`, `SKILL.md`, `module-setup.md`, and CSV descriptions all agree. |
| Agent roster | n/a — `module.yaml` has no `agents:` block (no persona agents; every pipeline step runs in a generic delegated subagent). |
| Version lockstep (repo invariant, CLAUDE.md → "Releasing") | ✅ `marketplace.json`, `module.yaml` (`module_version`), README badge, and `state-and-resume.md`'s `profiles_source_version` all agree at `0.27.0`. |

## Changes made this session

None — module validated cleanly with no fixes required.

## Overall assessment

Module passes cleanly with zero structural or quality findings, and all four
version markers remain in lockstep at `0.27.0`. Ready for use.
