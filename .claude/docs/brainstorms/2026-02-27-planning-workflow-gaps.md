# Brainstorm: Planning Workflow Gaps — V-Model SDLC, Testing Strategy, First-Time-Right Plans

**Date**: 2026-02-27
**Problem**: Plans produced by the Architect agent consistently have gaps requiring multiple revision passes. Mock testing hides real defects. No V-Model traceability from requirements through acceptance testing.

---

## Executive Summary

Three parallel analyses identified **22 gaps** across the workflow. The findings converge on 7 root causes and 5 cross-cutting problems. Below is the unified synthesis.

---

## Root Causes (Why Plans Fail on First Attempt)

### RC-1: The Architect Never Reads Existing Code

The Architect agent reads `CLAUDE.md`, `PROJECT_BRIEF.md`, and `ARCHITECTURE.md` but **never opens the source files it plans to change**. It plans modifications to code it has never seen — wrong assumptions about signatures, patterns, and dependencies are guaranteed.

### RC-2: No Interface Contract Specification

The plan's "Changes" table says "Add X functionality" but never specifies function signatures, input/output types, error types, or caller/callee relationships. When Phase 2 depends on Phase 1, there is no contract between them.

### RC-3: No Testing Strategy Per Phase

Plans say "tests pass" without specifying WHAT to test, WHETHER to mock or use real dependencies, what edge cases to cover, or what test files to create. The Builder makes ad-hoc testing decisions.

### RC-4: No Data Flow Analysis

Plans do not trace how data flows from input to output. They treat each phase as isolated. Missing error paths, format mismatches, and cascading failures are not anticipated.

### RC-5: No Pre-Flight Validation

The workflow goes Architect → Builder with no validation step. Plan defects propagate fully through implementation before being caught.

### RC-6: Feature Plan Skill Is Dangerously Sparse

The feature_plan SKILL.md is **16 lines** (vs ralph at 218 lines). The most consequential workflow step has the least procedural guidance. The Architect has discretion to skip any analysis.

### RC-7: ARCHITECTURE.md Is Empty

Contains only placeholder brackets. When the Architect reads it as instructed, it gets zero information about the system.

---

## V-Model Gap Analysis

### Level 1: Requirements ↔ Acceptance Testing — WEAKEST LEVEL

| Gap    | Description                                                                               | Fix                                                                      |
| ------ | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| GAP-1A | No requirement identifiers. "Done When" items cannot be referenced from tests or prd.json | Add requirement IDs (e.g., R-P1-01) to every Done When criterion         |
| GAP-1B | PLAN.md and prd.json are disconnected artifacts with no structural link                   | prd.json `acceptanceCriteria` must reference PLAN.md requirement IDs     |
| GAP-1C | No acceptance test plan authored at requirements time                                     | Testing Strategy section authored during planning, not deferred to build |
| GAP-1D | QA verification reports are ephemeral (conversation only, never persisted)                | Persist verification reports to `.claude/docs/verification/`             |

### Level 2: System Design ↔ System Testing — MISSING ENTIRELY

| Gap    | Description                                                                    | Fix                                                                    |
| ------ | ------------------------------------------------------------------------------ | ---------------------------------------------------------------------- |
| GAP-2A | ARCHITECTURE.md is a static placeholder never validated against running system | Architect must populate from Discovery; flag drift if outdated         |
| GAP-2B | No workflow step checks for architecture drift                                 | QA agent should compare implementation against ARCHITECTURE.md         |
| GAP-2C | No system-level test step in QA agent                                          | Add system test verification step: "Does the feature work end-to-end?" |

### Level 3: Architecture ↔ Integration Testing — PERMISSIVE

| Gap    | Description                                                                               | Fix                                                                       |
| ------ | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| GAP-3A | QA says "Integration tests — if they exist, run them" making integration testing optional | Change to "Integration tests — REQUIRED if plan touches multiple modules" |
| GAP-3B | Ralph gateCmd is a single command, cannot distinguish test layers                         | Enhanced gateCmd schema with unit/integration/e2e layers                  |
| GAP-3C | No integration boundary analysis in plans                                                 | Interface Contracts table with Called By / Calls columns                  |

### Level 4: Module Design ↔ Unit Testing — TEST-LAST, NO DESIGN

| Gap    | Description                                                                           | Fix                                                        |
| ------ | ------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| GAP-4A | No module design step — Builder goes straight from plan to code                       | Plan's Interface Contracts section IS the module design    |
| GAP-4B | "Test after every code change" is test-LAST, not test-first                           | Testing Strategy specifies tests before code, enabling TDD |
| GAP-4C | `.needs_verify` marker clears when ANY test passes, not tests covering modified files | Hook should verify test coverage of changed files          |

### Level 5: Implementation — ADEQUATE BUT INCOMPLETE

| Gap    | Description                                                  | Fix                                                        |
| ------ | ------------------------------------------------------------ | ---------------------------------------------------------- |
| GAP-5A | No code review step — QA checks automated metrics, not logic | Add "logic review" step to QA agent                        |
| GAP-5B | No coding standards beyond formatting                        | Code-quality rules already exist; ensure they are enforced |

---

## Cross-Cutting: The Telephone Game (Information Loss Between Agents)

1. **Architect → Builder**: Builder told to "find first incomplete phase" but NOT to read Risks & Mitigations. Architect's risk warnings are silently dropped.
2. **Builder → QA**: No handoff mechanism. Implementation context (deviations, workarounds) exists only in conversation. QA reads PLAN.md cold.
3. **QA → Builder on FAIL**: Verification report lives in conversation only. If session compacts, failure details are lost.

---

## Cross-Cutting: Mock Testing — The Silent Killer

The workflow has **zero mention of mocking strategy** in any file. No agent, rule, or hook addresses when to use mocks vs real dependencies.

### Mock vs Real Decision Framework

| Scenario                         | Decision                                   | Reasoning                                                            |
| -------------------------------- | ------------------------------------------ | -------------------------------------------------------------------- |
| Pure functions (no side effects) | **ALWAYS REAL**                            | No external deps to mock. Mocking pure functions hides real behavior |
| Internal module interactions     | **ALWAYS REAL**                            | These are YOUR code — test real integration                          |
| Business logic / data transforms | **ALWAYS REAL**                            | This is what you're shipping. Mock = untested                        |
| Database operations              | **MOCK for unit, REAL for integration**    | Unit tests use in-memory fixtures; integration tests need real DB    |
| External API calls               | **MOCK for unit, REAL for contract tests** | Record real responses as fixtures. Verify contracts separately       |
| File system operations           | **MOCK for unit, REAL for integration**    | Use temp directories for integration                                 |
| Authentication/authorization     | **REAL with test credentials**             | Auth logic is too critical to mock                                   |
| Network/HTTP calls               | **MOCK for unit**                          | But verify with contract tests against recorded responses            |

### Red Flags (QA Should Catch These)

- Test mocks the function it's supposed to test (testing the mock, not the code)
- All dependencies mocked in every test (no integration coverage at all)
- Mock returns hardcoded success — never tests error paths
- Test asserts mock was called but doesn't assert return value correctness
- No integration tests exist for components that cross module boundaries

---

## Cross-Cutting: Requirements Traceability (Currently Broken)

**Current chain (broken)**:

```
PLAN.md bullets (no IDs) → Builder code (no trace markers) → QA report (ephemeral)
prd.json criteria (separate, unlinked) → Ralph gateCmd (exit code only)
```

**Target chain**:

```
PLAN.md R-P1-01 → prd.json criteria ref R-P1-01 → test docstring "# Tests R-P1-01"
→ QA report "R-P1-01: PASS (evidence: ...)" → persisted verification report
```

---

## Enhanced prd.json Schema

Current:

```json
{
  "id": "STORY-001",
  "description": "...",
  "acceptanceCriteria": ["..."],
  "gateCmd": "pytest tests/ -v",
  "passed": false
}
```

Proposed:

```json
{
  "id": "STORY-001",
  "description": "...",
  "acceptanceCriteria": [
    { "id": "R-P1-01", "criterion": "...", "testType": "integration" }
  ],
  "gateCmds": {
    "unit": "pytest tests/unit/ -v --tb=short",
    "integration": "pytest tests/integration/ -v --tb=short",
    "lint": "ruff check src/"
  },
  "passed": false
}
```

---

## Proposed Solutions (5 Implementation Phases)

### Phase 1: Architect Agent Overhaul — Mandatory Discovery

- Add mandatory Discovery step: read source files, trace data flows, identify integration boundaries
- Add Pre-Flight Checklist: 10 items verified before plan is declared complete
- **File**: `.claude/agents/architect.md`

### Phase 2: Plan Template Overhaul — Interface Contracts, Testing Strategy, Data Flow

- Add per-phase sections: Interface Contracts (7-column table), Data Flow (with error paths), Testing Strategy (Real vs Mock with justification), System Context
- Add requirement IDs to Done When criteria
- **File**: `.claude/docs/PLAN.md` (as template)

### Phase 3: Feature Plan Skill Overhaul — Procedural Checklist

- Replace 16-line sparse instructions with ~80-line procedural checklist
- Steps: Load Context → Discovery → Research → Clarifying Questions → Write Plan → Pre-Flight Validation
- No steps skippable
- **File**: `.claude/skills/feature_plan/SKILL.md`

### Phase 4: Builder Agent — Plan Sanity Check + Risk Awareness

- Add Plan Sanity Check before any code: files exist, signatures match, tests specified, verification runnable
- Builder must read Risks & Mitigations table (currently skipped)
- Builder stops and requests plan revision if checks fail
- **File**: `.claude/agents/builder.md`

### Phase 5: Anti-Patterns Document + QA Agent Enhancement

- Create planning anti-patterns doc (7 patterns: Phantom File, Interface by Imagination, Mock Everything, Happy Path Only, Orphan Phase, Hollow Done Criteria, Architecture Amnesia)
- Enhance QA agent: add mock quality detection, integration test enforcement, logic review step
- **Files**: `.claude/docs/knowledge/planning-anti-patterns.md` (NEW), `.claude/agents/qa.md`

---

## Open Questions (Need User Input)

1. **Lightweight path?** Should there be a "Quick Plan" mode for trivial changes (< 3 files) that skips Interface Contracts and Data Flow? _Recommendation: No. "N/A" is cheap to write, and misjudging complexity is how gaps get introduced._

2. **Hook enforcement?** Should the Pre-Flight Checklist be enforced by a Python hook (cannot skip) or by agent instructions (voluntary)? _Recommendation: Start with agent instructions. Add hook later if compliance is low._

3. **Ralph schema migration?** Should prd.json adopt the enhanced schema (layered gateCmds, requirement IDs in criteria) immediately, or should it be backward-compatible? _Recommendation: Adopt immediately — the current prd.json is a template with no real data._

4. **Verification report persistence?** Should QA reports be persisted to `.claude/docs/verification/` or is conversation-only acceptable? _Recommendation: Persist. Information that exists only in conversation is lost on compaction._

5. **ARCHITECTURE.md bootstrapping?** For brand-new projects with no code, should the Architect populate ARCHITECTURE.md from PROJECT_BRIEF.md or require the user to fill it? _Recommendation: Architect populates from whatever sources exist (brief, initial code, or declared intent)._

---

## Sources

- `.claude/agents/architect.md` — current Architect agent definition
- `.claude/agents/builder.md` — current Builder agent definition
- `.claude/agents/qa.md` — current QA agent definition
- `.claude/skills/feature_plan/SKILL.md` — current feature plan skill (16 lines)
- `.claude/skills/ralph/SKILL.md` — current Ralph supervised autonomy loop
- `.claude/skills/verify/SKILL.md` — current verification skill
- `.claude/prd.json` — current story schema (template)
- `.claude/docs/brainstorms/2026-02-11-nba-tdd-governance-gaps.md` — prior related analysis
- V-Model SDLC methodology (Requirements ↔ Acceptance, Design ↔ System, Architecture ↔ Integration, Module ↔ Unit)
