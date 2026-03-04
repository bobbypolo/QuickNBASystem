---
name: build-system
description: End-to-end pipeline that chains Planning, Building, Audit, and Handoff into a single orchestrated flow with user approval gates.
argument-hint: "{slug}"
---

# /build-system -- Unified Pipeline Meta-Command

Orchestrates the full feature lifecycle from planning through verified implementation. Runs 4 phases with 2 user approval gates.

```
========================================
  BUILD-SYSTEM - Unified Pipeline
  Phases: A (Plan) -> [Gate 1] -> B (Build)
       -> C (Audit) -> D (Handoff) -> [Gate 2]
========================================
```

## Session Detection (Run First)

Before executing any phase, detect the current session state to determine the correct starting point. Check each indicator in order and skip to the appropriate phase.

### Detection Logic

```
1. Check .claude/.workflow-state.json for active ralph section:
   - If ralph.current_story_id is non-empty AND ralph.consecutive_skips < 3:
     -> Ralph sprint in progress. Display: "Resuming Ralph sprint at [story_id]"
     -> Skip to Phase B (resume /ralph)

2. Check .claude/docs/PLAN.md exists AND .claude/prd.json exists with version "2.0":
   - If both exist AND prd.json has stories with passed: false:
     -> Plan exists, build not started. Display: "Plan found with [N] remaining stories."
     -> Skip to Phase B (start /ralph)

3. Check .claude/docs/PLAN.md exists but prd.json missing or invalid:
   - If PLAN.md exists but prd.json is absent or version != "2.0":
     -> Plan exists but stories not generated. Display: "Plan found but prd.json needs regeneration."
     -> Skip to Phase A (re-run /plan to regenerate prd.json)

4. No plan exists:
   - Start from Phase A (plan)
```

Display the detection result before proceeding:

```
SESSION STATE:
  Plan:      [exists / missing]
  prd.json:  [valid / invalid / missing]
  Ralph:     [in progress at STORY-NNN / not started / complete]
  Starting:  Phase [X]
```

---

## Phase A: Plan

1. Display: `"Phase A: Creating implementation plan..."`
2. Invoke `/plan` with the feature description.
3. Wait for plan generation to complete (includes pre-flight validation in /plan Steps 6a-6b).
4. If plan pre-flight fails, see Error Handling below.
5. `/plan` auto-generates `prd.json` in Step 7.
6. Display: `"Phase A complete. Plan and stories ready for review."`

### User Approval Gate 1: Plan Review

**This gate is mandatory. Do NOT proceed without explicit user approval.**

```
========================================
  GATE 1: Plan Review
========================================
Plan: .claude/docs/PLAN.md
Stories: .claude/prd.json ([N] stories, [M] acceptance criteria)

Please review the plan before building begins.
Key files to check:
  - PLAN.md: Phased implementation, risk assessment
  - prd.json: Story decomposition, gate commands

Options:
  1. Approve and continue to Build (Phase B)
  2. Revise the plan (describe changes needed)
  3. Save and stop (review offline, resume later)
========================================
```

- **Option 1**: Proceed to Phase B.
- **Option 2**: Incorporate feedback, re-run `/plan` or manually adjust, then re-present Gate 1.
- **Option 3**: Run `/handoff` with note that plan is ready for build. STOP. User resumes with `/build-system {slug}` in a new session (Session Detection skips to Phase B).

---

## Phase B: Build

1. Display: `"Phase B: Starting autonomous build with Ralph..."`
2. Invoke `/ralph` to run the V-Model orchestrator.
   - Ralph validates prd.json, creates/resumes feature branch, and processes all stories autonomously.
   - No user interaction during Ralph execution (except at Ralph session end).
3. Wait for Ralph to complete all stories (or hit circuit breaker).
4. Display: `"Phase B complete. Ralph session finished."`

---

## Phase C: Audit

1. Display: `"Phase C: Running end-to-end audit..."`
2. Invoke `/audit` to run the 9-section integrity audit.
   - Validates PLAN.md completeness, prd.json schema, test coverage, verification logs, architecture conformance, hook wiring, git hygiene, production-grade code scan, and error handling resilience.
3. Review audit results:
   - If all sections pass: proceed to Phase F.
   - If any section fails: display failures and ask user whether to fix issues or proceed with noted deficiencies.
4. Display: `"Phase C complete. Audit results recorded."`

---

## Phase D: Handoff

1. Display: `"Phase D: Generating handoff and session summary..."`
2. Invoke `/handoff` to save session state.
3. Display sprint summary.

### User Approval Gate 2: PR Review

**This gate is mandatory. Do NOT create a PR without explicit user approval.**

```
========================================
  GATE 2: PR Review
========================================
Branch: [feature-branch-name]
Stories completed: [N]/[total] ([skipped] skipped)
Audit status: [PASS / FAIL with details]

Options:
  1. Create Pull Request (push branch + gh pr create)
  2. Review changes first (git diff, file inspection)
  3. Skip PR (keep changes on branch for manual review)
========================================
```

- **Option 1**: Push branch and create PR via `gh pr create` with auto-generated summary.
  - After PR creation, ask user: `"Run /code-review on this PR? (Yes / No)"`
    - If **Yes**: Invoke `/code-review` on the PR. Display result summary.
    - If **No**: Skip code-review. Display: `"Code review skipped."`
- **Option 2**: Allow user to inspect changes, then re-present Gate 2.
- **Option 3**: Display branch name and instructions for manual PR creation later.

```
========================================
  BUILD-SYSTEM COMPLETE
========================================
Pipeline: Plan -> Build -> Audit -> Handoff
Result: [summary of what was accomplished]
Branch: [branch-name]
PR: [URL if created, or "Not created" if skipped]

Next steps:
  - Review and merge the PR
  - Run /code-review if not already run on the PR
  - Run /health before next session
========================================
```

---

## Error Handling

### Plan Pre-Flight Failure

```
ERROR: Plan pre-flight validation failed.

Failures:
  [List each failed check from /plan Step 6b]
  - Check [a-f]: [specific failure message]

How to fix:
  - File not found: Verify file paths in the Changes table
  - Hollow criterion: Add R-PN-NN ID to each Done When item
  - Missing Interface Contract: Add contract row for changed components
  - No Testing Strategy: Add at least one test row per phase
  - Placeholder verification: Replace with actual runnable command
  - Signature mismatch: Align function signatures across phases

The plan must pass all 6 pre-flight checks before stories can be generated.
Fix the issues and re-run /plan, or run /build-system {slug} to restart from Phase A.
```

**Action**: Return to Phase A after fixes.
