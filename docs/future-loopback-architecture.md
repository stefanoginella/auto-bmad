# Future Architecture: Loopback Review Patterns

> These patterns were identified during analysis of BMAD 6.2.1's "quick-dev-new-preview"
> workflow (step-04-review.md). They represent architectural directions for future auto-bmad
> evolution. None are implemented yet — each requires its own planning and design phase.
>
> Reference: https://github.com/bmad-code-org/BMAD-METHOD/releases/tag/v6.2.1
> Key PRs: #2105 (intent cascade), #2055 (triage rewrite), #2069 (subagent separation)

---

## 1. Loopback Architecture

### Current State

auto-bmad's Phase 3 is linear:

```
3.1 parallel reviews → 3.2 acceptance audit → 3.3 triage → 3.4 dev fix → 3.5 resolve spec
```

When step 3.5 resolves a `bad_spec` finding, it amends the story spec and documents whether
the existing implementation is still consistent. If the implementation diverges from the
amended spec, this is noted as a follow-up action item — but the code is **not re-derived**.
The pipeline moves on to Phase 4 (traceability) with potentially misaligned code.

### Proposed Pattern

Replace the linear flow with a causal-layer loopback:

```
3.1 reviews → 3.2 audit → 3.3 triage ─┐
                                        ├── patch    → auto-fix in place (current behavior)
                                        ├── bad_spec → revert code → amend spec → re-derive (step 2.2) → re-audit
                                        ├── intent_gap → escalate to human → re-derive after resolution
                                        ├── defer    → append to deferred-work.md (already implemented)
                                        └── reject   → drop
```

For `bad_spec` findings:
1. Extract KEEP instructions — what works well and must survive re-derivation
2. Revert implementation code to pre-implementation state (COMMIT_BASELINE)
3. Amend the spec to correct the specification error
4. Log the amendment in the Spec Change Log with known-bad state and KEEP notes
5. Re-run step 2.2 (implementation) against the corrected spec
6. Re-run steps 3.1-3.3 (review + triage) to verify the fix

For `intent_gap` findings:
1. Do NOT attempt automatic resolution
2. Present the gap to the human with context from upstream artifacts
3. After human resolves the intent, re-run from step 2.2

The key insight from BMAD quick-dev: **diagnose where the failure entered the system, go
back to that layer, and regenerate from there** — rather than patching at the symptom layer.

### Why Deferred

This changes the pipeline from single-pass to potentially cyclic. It requires:

- **Selective code revert**: Currently `COMMIT_BASELINE` tracks the pre-pipeline SHA. A
  loopback needs a more granular checkpoint — the SHA after spec preparation (end of Phase 1)
  but before implementation (start of Phase 2). This is the revert target.
- **Re-entrant steps**: Steps 2.2 and 3.x must be re-runnable without corrupting state.
  The current `--from-step` resume mechanism is close but assumes forward-only progress.
- **Cycle detection**: Without a limiter, bad_spec→amend→re-derive→bad_spec could loop
  forever if the spec and implementation are fundamentally incompatible.
- **Cost model**: Each loopback re-runs implementation + review — potentially 8+ AI calls.
  Need criteria for when loopback is worth the cost vs. documenting the inconsistency.

### Dependencies

- Iteration Limiter (pattern 3) — required safety valve
- Frozen-After-Approval Spec Sections (pattern 2) — makes the `intent_gap` vs `bad_spec`
  classification reliable enough to drive automated loopback decisions

---

## 2. Frozen-After-Approval Spec Sections

### Current State

The distinction between `intent_gap` (captured intent is incomplete — needs human input) and
`bad_spec` (spec derivation was wrong — can be auto-resolved from upstream artifacts) relies
on the triage analyst's judgment call during step 3.3. This works for most cases but
introduces ambiguity when:

- A story section captures upstream intent correctly, but the intent itself was incomplete
- A finding touches both frozen intent and derived spec details
- Multiple reviewers disagree on the classification

The current KEEP instructions (implemented in steps 3.4 and 3.5) mitigate regression risk
but don't address the classification ambiguity itself.

### Proposed Pattern

Mark intent sections of the story as immutable after human approval using markers:

```markdown
<!-- frozen-after-approval -->
## User Story
As a [user], I want [goal] so that [benefit]

## Acceptance Criteria
- Given X, when Y, then Z
<!-- /frozen-after-approval -->

## Tasks
(derived — mutable by pipeline)
```

Classification becomes mechanical:
- Finding affects a `frozen-after-approval` section → **intent_gap** (escalate to human)
- Finding affects a non-frozen section → **bad_spec** (auto-resolve from upstream)

This removes judgment from the triage step for the most consequential classification decision
in the pipeline.

### Integration with BMAD Story Format

The BMAD story template would need modification to support these markers. Options:

1. **Inline markers** (shown above) — minimal format change, parseable by AI
2. **Frontmatter flags** — e.g., `frozen_sections: ["User Story", "Acceptance Criteria"]`
3. **Convention-based** — define which section headings are always frozen (simpler but less flexible)

Option 3 is the lightest touch: define in auto-bmad that `## User Story` and
`## Acceptance Criteria` sections are always frozen, and `## Tasks`, `## Technical Notes`,
etc. are always mutable. This requires no story format changes — just a convention documented
in the triage prompt.

### Why Deferred

- Requires consensus on which sections are frozen vs. mutable
- The convention-based approach (option 3) could be prototyped quickly, but the full marker
  approach needs BMAD story template changes
- Most valuable when combined with Loopback Architecture, where the classification directly
  determines whether to loop back (bad_spec) or escalate (intent_gap)
- Without loopback, the classification only affects documentation granularity — not pipeline behavior

### Dependencies

- Most valuable with Loopback Architecture (pattern 1)
- Could be implemented independently as a triage quality improvement

---

## 3. Iteration Limiter

### Current State

The pipeline is single-pass. Steps 3.4 (dev fix) and 3.5 (spec resolve) each run exactly
once. There are no loops to limit.

### Proposed Pattern

If Loopback Architecture is adopted, cap the spec amendment + re-derivation cycle:

```
MAX_SPEC_ITERATIONS=2  # configurable, default 2

spec_iteration=0
while findings contain bad_spec && spec_iteration < MAX_SPEC_ITERATIONS; do
    spec_iteration++
    amend spec → re-derive → re-review
done
if spec_iteration >= MAX_SPEC_ITERATIONS; then
    log_warn "Spec iteration limit reached — escalating to human"
    # present remaining findings for manual resolution
fi
```

BMAD quick-dev uses `specLoopIteration` with a limit of 5. For auto-bmad, a lower default
(2) is appropriate because:
- Each iteration is expensive (full implementation + 6 parallel reviews)
- If 2 rounds don't converge, the spec likely has a fundamental issue requiring human judgment
- The limit is configurable via a variable, so users can adjust

### State Tracking

The iteration counter should be:
- Stored in the pipeline log header (alongside COMMIT_BASELINE) for resume support
- Reported in the pipeline report's summary table
- Logged per-iteration with what changed

### Why Deferred

Without Loopback Architecture, there are no loops to limit. Designing the limiter in
isolation would be speculative. Implement this as part of the loopback epic.

### Dependencies

- Loopback Architecture (pattern 1) must be implemented first
- This is the safety valve that makes loopback viable for unattended execution
