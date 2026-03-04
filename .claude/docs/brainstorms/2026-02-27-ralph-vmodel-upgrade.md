# Brainstorm: Ralph Orchestration, V-Model Traceability, and prd.json Schema — Upgrade to 8+/10

**Date**: 2026-02-27
**Problem**: Ralph bypasses the V-Model workflow it was designed to orchestrate. It skips plan creation, never invokes QA verification, and runs gate commands as dumb exit-code checks. The prd.json schema is a flat template with no structural links to PLAN.md requirements. V-Model traceability exists in design but is not enforced anywhere.

---

## Current State (Baseline)

| Component            | Score | Core Deficiency                                                       |
| -------------------- | ----- | --------------------------------------------------------------------- |
| Ralph orchestration  | 5/10  | Runs stories without requiring plans, tests, or QA verification       |
| V-Model traceability | 4/10  | Designed in brainstorm, not enforced in any agent or hook             |
| prd.json schema      | 4/10  | Flat string arrays, no structured criteria, no requirement ID linkage |

### 10 Gaps Being Addressed

| #   | Gap                                    | Severity | Component     |
| --- | -------------------------------------- | -------- | ------------- |
| 1   | Ralph bypasses plan creation           | CRITICAL | Ralph         |
| 2   | Ralph never calls /verify              | CRITICAL | Ralph         |
| 3   | prd.json lacks structured criteria     | MODERATE | prd.json      |
| 4   | No TDD enforcement in Ralph            | MODERATE | Ralph         |
| 5   | No traceability enforcement            | MODERATE | V-Model       |
| 6   | Plan mode doesn't trigger feature_plan | LOW      | Documentation |
| 7   | No gateCmds validation                 | LOW      | Ralph         |
| 8   | No test coverage verification          | LOW      | Ralph + QA    |
| 9   | Checkpoint/rollback mismatch           | LOW      | Ralph         |
| 10  | Verification log not used in retries   | LOW      | Ralph + QA    |

---

## Ideas

### 1. Ralph Phase Gate Architecture — "Plan-Build-Verify" Inner Loop

**Description**: Restructure Ralph's Step 5 (Implement) into three mandatory sub-phases that mirror the V-Model left side:

```
STEP 5A: PLAN — If no PLAN.md covers this story, run Architect workflow
STEP 5B: BUILD — Act as Builder with TDD (tests first, then implementation)
STEP 5C: VERIFY — Run /verify (full 14-step QA checklist), not just gate exit codes
```

Each sub-phase has its own gate. Ralph cannot proceed from 5A to 5B without a plan. Cannot proceed from 5B to 5C without passing gate commands. Cannot mark a story as passed without /verify producing an overall PASS.

**Implementation details**:

Step 5A (Plan):

- Read PLAN.md. Check if any phase's scope covers this story's acceptance criteria.
- If no coverage: Run Architect workflow — Discovery, Interface Contracts, Testing Strategy, Pre-Flight.
- Write or update PLAN.md for this story's scope.
- If plan already covers this story: Skip to 5B.
- Gate: PLAN.md exists with Done When criteria that map to this story's acceptance criteria IDs.

Step 5B (Build):

- Act as Builder with Plan Sanity Check (5 checks).
- TDD mandatory: For each acceptance criterion, write a failing test FIRST, then implement.
- Tests must include `# Tests R-PN-NN` docstring markers for traceability.
- Gate: All gateCmds pass (unit, integration, lint).

Step 5C (Verify):

- Run full /verify (14-step QA checklist).
- Gate: Overall result is PASS. Verification report persisted to verification-log.md.

- **Pros**: Closes GAP 1 (plan creation), GAP 2 (QA verification), GAP 4 (TDD), GAP 5 (traceability). Ralph becomes a true V-Model orchestrator instead of a build-and-check loop. Every story gets the full Architect → Builder → QA pipeline. No story can pass without plan, tests, and verification.
- **Cons**: Adds significant overhead per story. A story that takes 5 minutes today may take 20 minutes with planning + verification. For trivial stories (rename a variable), the full Architect workflow is overkill. Risk of process fatigue — if every story requires 3 sub-phases, users may abandon Ralph for ad-hoc work.

### 2. Smart Plan Detection — "Plan If Needed" Heuristic

**Description**: Instead of always running the full Architect workflow (Idea 1's 5A), Ralph checks whether a plan already covers the current story's scope. Only triggers planning when coverage is missing.

**Detection logic**:

1. Read PLAN.md.
2. Extract all requirement IDs (R-PN-NN pattern).
3. Extract story's acceptance criteria IDs from prd.json.
4. If all story criteria IDs exist in PLAN.md Done When sections → Plan covers this story, skip planning.
5. If any story criteria ID is missing from PLAN.md → Run Architect workflow for uncovered scope only.
6. If PLAN.md doesn't exist → Full Architect workflow required.

**Fallback**: If prd.json acceptance criteria don't use R-PN-NN format (legacy/template entries), flag a warning and require manual confirmation before proceeding without a plan.

- **Pros**: Avoids redundant planning for stories already covered by an existing plan. Handles the common case where `/feature_plan` was run before `/ralph`. Lightweight detection — string matching on requirement IDs. Graceful degradation for legacy prd.json format.
- **Cons**: Partial coverage detection is imprecise — a plan might have the requirement ID but the scope may have changed since planning. The heuristic can be fooled by mismatched IDs (plan says R-P1-01 but story says R-P1-01 with different criterion text). Adds complexity to Ralph's decision tree.

### 3. Structured prd.json Schema v2 — Typed Criteria with Test Links

**Description**: Upgrade prd.json from flat string arrays to structured objects with requirement IDs, test types, and test file links. Add schema validation at Ralph initialization.

**Schema**:

```json
{
  "version": "2.0",
  "planRef": ".claude/docs/PLAN.md",
  "stories": [
    {
      "id": "STORY-001",
      "description": "Implement user authentication endpoint",
      "phase": 1,
      "acceptanceCriteria": [
        {
          "id": "R-P1-01",
          "criterion": "POST /auth/login returns 200 with JWT token for valid credentials",
          "testType": "integration",
          "testFile": "tests/integration/test_auth.py::test_login_success"
        },
        {
          "id": "R-P1-02",
          "criterion": "POST /auth/login returns 401 with error message for invalid credentials",
          "testType": "integration",
          "testFile": "tests/integration/test_auth.py::test_login_invalid"
        }
      ],
      "gateCmds": {
        "unit": "pytest tests/unit/ -v --tb=short",
        "integration": "pytest tests/integration/ -v --tb=short",
        "lint": "ruff check src/"
      },
      "passed": false,
      "verificationRef": null
    }
  ]
}
```

**Validation at Ralph Step 1 (Initialize)**:

1. Check `version` field exists and equals "2.0".
2. Every story has `gateCmds` (not just `gateCmd`). If only `gateCmd` exists, warn and require user to upgrade.
3. Every acceptance criterion has `id` matching `R-PN-NN` pattern.
4. Every acceptance criterion has `testType` from allowed set: `unit`, `integration`, `e2e`, `manual`.
5. `testFile` is optional but recommended — flag stories with zero `testFile` entries as "untraceable."
6. `phase` links to PLAN.md phase number.

**Backward compatibility**: Ralph reads old-format prd.json (flat string arrays) but prints a deprecation warning and suggests migration. Old format works but bypasses traceability checks.

- **Pros**: Closes GAP 3 (structured criteria), GAP 5 (traceability), GAP 7 (gateCmds validation). Every criterion becomes traceable from plan to test to verification. Schema validation catches malformed stories before implementation begins. `testFile` enables targeted test runs — only run tests that cover this story's criteria. `verificationRef` links to the persisted verification report for audit trails.
- **Cons**: More complex JSON to author manually. The `testFile` field requires knowing test file paths at story-writing time, which may not be known until after planning. Schema version migration adds one-time friction. Over-structured for simple projects.

### 4. Verification-Integrated Ralph — Replace Exit-Code Gates with QA Pipeline

**Description**: Replace Ralph's Step 6 (gate command exit codes) with a full QA verification pipeline that runs the 14-step checklist from the QA agent. The gate commands become just one input to the verification — not the entire gate.

**Modified Step 6**:

```
STEP 6: Run Verification Pipeline

6.1 Run gateCmds (unit → integration → lint) — capture results
6.2 Run traceability check:
    - For each acceptance criterion in this story:
      - Does a test file exist with "# Tests [criterion.id]" marker?
      - Did that test pass in step 6.1?
    - If any criterion has no linked test: FAIL with "Untraceable criterion"
6.3 Run QA verification steps (from qa.md):
    - Mock quality audit (step 9)
    - Blast radius check (step 10)
    - Clean diff check (step 7)
    - Logic review (step 12)
6.4 Persist verification report to verification-log.md
6.5 Overall gate: ALL of 6.1-6.4 must pass
```

- **Pros**: Closes GAP 2 (full QA), GAP 5 (traceability enforcement), GAP 8 (coverage via traceability check), GAP 10 (verification log persistence). Every story gets the same rigor as a `/verify` call. Traceability is enforced structurally — stories without traced tests cannot pass. Verification reports are persisted for audit.
- **Cons**: Significantly slower than exit-code checking. QA steps like "logic review" and "mock quality audit" require reading code — this adds cognitive load and time per story. For a 10-story sprint, this could add 30+ minutes of verification overhead. Some QA steps (blast radius, architecture conformance) require PLAN.md context that may not exist for every story.

### 5. Checkpoint-Aware Rollback with Git Stash Integration

**Description**: Fix Ralph's checkpoint/rollback mismatch (GAP 9) by using `git stash` for work-in-progress preservation and `git reset --hard <checkpoint>` for true rollbacks.

**Modified Step 4 (Checkpoint)**:

```
STEP 4: Create Safety Checkpoint

1. Verify working tree is clean: `git status --porcelain`
   - If dirty: Ask user to commit or stash before proceeding
2. Record checkpoint: `git rev-parse HEAD` (full hash, not short)
3. Display: "Checkpoint: [short hash] ([branch name])"
4. Store full hash for rollback
```

**Modified Step 7 (Rollback)**:

```
Rollback procedure:
1. Stash current work: `git stash push -m "ralph-[story.id]-attempt-[N]"`
2. Reset to checkpoint: `git reset --hard [checkpoint_hash]`
3. Display: "Rolled back to [short hash]. Work stashed as ralph-[story.id]-attempt-[N]"
4. Ask user: "Retry (stash preserved) / Skip / Stop?"
```

**Retry with prior context**:
When retrying after rollback, Ralph reads the verification-log.md entry from the failed attempt to understand what went wrong. This closes GAP 10.

- **Pros**: Closes GAP 9 (rollback mismatch), GAP 10 (verification log in retries). True rollback via `git reset --hard` undoes any intermediate commits. Stash preserves work for debugging. Prior failure context informs retry attempts. Clean-tree verification prevents dirty-state surprises.
- **Cons**: `git reset --hard` is destructive — if the checkpoint hash is wrong, work is lost. Stash names can collide if not careful. More complex than `git checkout .` — more failure modes. Requires understanding of git stash semantics.

### 6. V-Model Traceability Enforcement via Naming Convention

**Description**: Enforce traceability through naming conventions rather than metadata, making it self-documenting and grep-searchable.

**Convention**:

- PLAN.md Done When: `R-P1-01: POST /auth/login returns 200 with JWT`
- prd.json criterion ID: `"id": "R-P1-01"`
- Test function: `def test_r_p1_01_login_success():` or docstring `# Tests R-P1-01`
- Verification report: `R-P1-01: PASS (evidence: ...)`

**Enforcement**: Ralph Step 6 runs a grep check:

```bash
# For each acceptance criterion ID in the current story:
grep -r "R-P1-01" tests/ --include="*.py" | grep -v __pycache__
# Must return at least one match. Zero matches = FAIL.
```

This is a lightweight traceability gate — no complex tooling, just a naming convention enforced by grep.

- **Pros**: Zero tooling cost. Self-documenting — anyone can grep the codebase for a requirement ID and find plan, story, test, and verification report. Works with any test framework. Closes GAP 5 (traceability enforcement) with minimal complexity. Easy to audit — `grep -r "R-P1-01"` shows the full trace chain.
- **Cons**: Naming convention requires discipline — easy to typo an ID. Doesn't verify that the test actually tests what the criterion describes (a test named `test_r_p1_01` could test something completely different). Grep-based enforcement is fragile — refactoring test names breaks traceability. No structural guarantee — it's a pattern, not a contract.

### 7. Tiered Ralph Mode — Express vs Full V-Model

**Description**: Introduce two Ralph modes to balance rigor with velocity:

**Express Mode** (`/ralph --express`):

- Stories ≤ 2 acceptance criteria, single-file changes
- Skip Architect planning (use existing PLAN.md or none)
- Gate: gateCmds exit codes only
- No full QA verification
- For: config changes, bug fixes, cosmetic updates

**Full V-Model Mode** (`/ralph` or `/ralph --full`):

- All stories regardless of size
- Mandatory: Plan-Build-Verify inner loop (Idea 1)
- Gate: Full QA verification pipeline (Idea 4)
- Traceability enforcement (Idea 6)
- For: features, refactors, multi-file changes

**Auto-detection** (default behavior):
Ralph reads each story's `complexity` field or infers from criteria count:

- 1-2 criteria, no `gateCmds.integration` → Express eligible
- 3+ criteria, or has `gateCmds.integration` → Full V-Model required
- User can override with `--express` or `--full`

- **Pros**: Prevents process fatigue. Trivial changes don't need full V-Model treatment. Users retain control via flags. Auto-detection makes the default intelligent. Matches industry practice of risk-proportional governance (IEC 62304, ISO 26262).
- **Cons**: Two modes means two code paths to maintain. "Express" mode is exactly the bypass that created the current gaps — if users default to Express, they get today's 5/10 quality. Auto-detection can misjudge complexity (a "simple" 2-criteria story might touch 5 files). Complexity creep in Ralph — the skill goes from 227 lines to potentially 400+.

### 8. prd.json Auto-Generation from PLAN.md

**Description**: Instead of manually authoring prd.json, auto-generate it from PLAN.md after the Architect completes planning. Each phase in PLAN.md becomes a story in prd.json, with acceptance criteria pulled from Done When, and gate commands pulled from Verification Command.

**Generation logic** (added to feature_plan skill as Step 7):

```
For each phase in PLAN.md:
  story.id = "STORY-{phase_number:03d}"
  story.description = phase title
  story.phase = phase_number
  story.acceptanceCriteria = parse Done When items into structured objects:
    - Extract R-PN-NN ID
    - Extract criterion text
    - Infer testType from Testing Strategy table
    - testFile = from Testing Strategy "Test File" column
  story.gateCmds = parse Verification Command:
    - If single command: set as gateCmd
    - If multiple: parse into unit/integration/lint layers
  story.passed = false
Write to .claude/prd.json with version: "2.0"
```

- **Pros**: Eliminates the disconnect between PLAN.md and prd.json (GAP 1B from the original brainstorm). Single source of truth — change the plan, regenerate stories. Criteria IDs are guaranteed to match because they're extracted from the same source. Reduces manual work — user writes one plan, gets both artifacts. Closes GAP 3 (structured criteria), GAP 5 (traceability by construction), GAP 7 (gateCmds from verification commands).
- **Cons**: Requires PLAN.md to be in strict format (already enforced by feature_plan skill). One-to-one phase-to-story mapping may not always be correct — some phases may need multiple stories, or one story may span phases. Auto-generation logic must handle edge cases (phases with "N/A" Testing Strategy, verification commands with shell pipelines). If user manually edits prd.json after generation, the link to PLAN.md drifts.

---

## Evaluation Matrix

| Idea                              | Gaps Closed | Complexity | Process Overhead      | Robustness | Recommended                     |
| --------------------------------- | ----------- | ---------- | --------------------- | ---------- | ------------------------------- |
| 1. Plan-Build-Verify inner loop   | 1, 2, 4, 5  | Medium     | High                  | Very High  | YES (core)                      |
| 2. Smart plan detection           | 1 (refined) | Low        | Low                   | Medium     | YES (optimize #1)               |
| 3. Structured prd.json v2         | 3, 5, 7     | Medium     | Low                   | High       | YES (core)                      |
| 4. QA verification pipeline       | 2, 5, 8, 10 | Medium     | High                  | Very High  | YES (core)                      |
| 5. Checkpoint-aware rollback      | 9, 10       | Low        | None                  | High       | YES (surgical fix)              |
| 6. Naming convention traceability | 5           | Low        | Low                   | Medium     | YES (supplements #3)            |
| 7. Tiered Express/Full modes      | N/A         | High       | Reduces overhead      | Medium     | NO (creates bypass)             |
| 8. prd.json auto-generation       | 3, 5, 7     | Medium     | Negative (saves time) | High       | YES (replaces manual authoring) |

---

## Recommendation

**Implement Ideas 1 + 2 + 3 + 4 + 5 + 6 + 8 as a unified upgrade. Reject Idea 7.**

### Core Architecture: The V-Model Ralph

Ralph becomes a true V-Model orchestrator with three structural changes:

**Change 1: Plan-Build-Verify inner loop (Ideas 1 + 2)**

Ralph Step 5 becomes three mandatory sub-phases. Smart plan detection (Idea 2) prevents redundant planning when PLAN.md already covers the story. The workflow becomes:

```
Story picked → Plan check (5A) → Builder + TDD (5B) → QA verify (5C) → Gate pass → Commit
```

This is the single highest-impact change. It transforms Ralph from "build-and-check" to "plan-build-verify" — the V-Model's core loop.

**Change 2: Structured prd.json with auto-generation (Ideas 3 + 8)**

prd.json v2 schema with typed criteria, requirement IDs, and test links. Auto-generated from PLAN.md by the feature_plan skill (Step 7). This eliminates the PLAN.md ↔ prd.json disconnect by construction — not by convention.

Manual prd.json authoring remains possible but the auto-generation path is the recommended workflow:

```
/feature_plan → PLAN.md → auto-generates prd.json v2 → /ralph executes stories
```

**Change 3: Full QA verification as gate (Ideas 4 + 6)**

Ralph's gate becomes the full QA verification pipeline, not just exit codes. Traceability is enforced via naming convention (grep for R-PN-NN in test files). Verification reports are persisted for audit trails.

**Change 4: Checkpoint-aware rollback (Idea 5)**

Surgical fix: use `git stash` + `git reset --hard` for true rollbacks. Read verification-log.md on retry to avoid repeating the same failed approach.

### Why Reject Idea 7 (Tiered Express/Full)

The user explicitly wants "extremely strict acceptance criteria" and "following V-Model SDLC every step of the way." An Express mode that bypasses V-Model verification is the exact opposite of this requirement. The current 5/10 score exists because Ralph already has implicit "express mode" — it skips planning and QA. Adding a formal bypass would codify the problem rather than fix it.

For truly trivial changes, users can skip Ralph entirely and use the standard Builder workflow with `/verify`. Ralph is the high-rigor path — it should not have a low-rigor escape hatch.

### Projected Score After Implementation

| Component            | Before | After | Key Improvement                                           |
| -------------------- | ------ | ----- | --------------------------------------------------------- |
| Ralph orchestration  | 5/10   | 9/10  | Plan-Build-Verify loop, full QA gates                     |
| V-Model traceability | 4/10   | 8/10  | R-PN-NN enforcement, grep-searchable, verification-log.md |
| prd.json schema      | 4/10   | 9/10  | Structured v2 schema, auto-generated from PLAN.md         |

The V-Model traceability score is 8 rather than 9 because the naming convention enforcement (grep for R-PN-NN) is pattern-based, not structurally guaranteed. A test named `test_r_p1_01` could test something unrelated to R-P1-01. Achieving 9+ would require a custom hook that parses test assertions — high cost for marginal gain.

### Implementation Files

| File                                   | Change Type   | Purpose                                                                           |
| -------------------------------------- | ------------- | --------------------------------------------------------------------------------- |
| `.claude/skills/ralph/SKILL.md`        | MAJOR REWRITE | Plan-Build-Verify inner loop, QA verification pipeline, checkpoint-aware rollback |
| `.claude/prd.json`                     | REPLACE       | v2 schema template with structured criteria                                       |
| `.claude/skills/feature_plan/SKILL.md` | ADD Step 7    | Auto-generate prd.json from PLAN.md                                               |
| `CLAUDE.md`                            | MINOR EDIT    | Document that `/feature_plan` is the planning workflow (not built-in plan mode)   |

### Implementation Order

1. **prd.json v2 schema** (Idea 3) — foundation that everything else depends on
2. **feature_plan Step 7** (Idea 8) — auto-generation from PLAN.md
3. **Ralph rewrite** (Ideas 1 + 2 + 4 + 5 + 6) — the main deliverable
4. **CLAUDE.md documentation** (Idea 6 note) — document the workflow

---

## Addendum: Context Limits, Audit Workflow, and Remaining Category Upgrades

### GAP 11: Ralph Context Exhaustion (CRITICAL — Previously Unidentified)

Ralph runs with `disable-model-invocation: true` — it executes in the **main conversation context**. There is no fork, no refresh, no isolation between stories. Every story's file reads, code writes, test outputs, error messages, and retry attempts accumulate in the same context window.

**Impact**: For a 5-story sprint with the upgraded Plan-Build-Verify loop, each story generates roughly:

- Plan check: ~2-4 file reads
- Builder: ~5-15 file reads/writes + test output
- QA verification: ~14 checks with captured output
- Gate commands: unit + integration + lint output
- Total per story: ~25-40 tool calls with output

At 5 stories, that's 125-200 tool calls. Context will auto-compact, losing implementation details that later stories may depend on.

**Current mitigation**: `post_compact_restore.py` fires a rules reminder on compaction. But it doesn't restore Ralph state (current story, attempt count, checkpoint hash, progress).

### Idea 9: Ralph Context Isolation — Sub-Agent Per Story

**Description**: Each story runs in an isolated sub-agent via the Task tool with `subagent_type: "Builder"`. Ralph (the orchestrator) stays lean in the main context — it only tracks state and dispatches work. The sub-agent gets the story details, PLAN.md context, and does all the heavy lifting (plan check, build, verify). When it returns, Ralph receives only the result summary.

**Implementation**:

```
STEP 5: Execute Story (via Sub-Agent)

1. Write story context to `.claude/ralph-state.json`:
   - story object from prd.json
   - checkpoint hash
   - attempt count
   - prior failure notes (from verification-log.md)

2. Launch sub-agent (Task tool, subagent_type: "Builder"):
   Prompt: "Read .claude/ralph-state.json. Execute the story using
   Plan-Build-Verify workflow. Return: {passed: bool, summary: string,
   files_changed: list, verification_report: string}"

3. Receive result from sub-agent.
   - Sub-agent's full context (file reads, test outputs, etc.) is discarded.
   - Only the result summary enters Ralph's context.

4. Based on result, proceed to STEP 6 (Handle Result).
```

- **Pros**: Eliminates context exhaustion entirely. Each story gets a fresh context window. Ralph's main context stays tiny — just state tracking and dispatch. Sub-agents can be parallelized in future (independent stories). Matches the RACI model from the NBA brainstorm (orchestrator manages, builder executes).
- **Cons**: Sub-agents don't have conversation history — they can't reference "what we discussed earlier." Sub-agent results are compressed — Ralph loses granular debugging context. The Task tool's sub-agent has its own context limits (but fresh per story). More complex orchestration — Ralph needs to serialize state to a file for the sub-agent to read.

### Idea 10: Ralph Inter-Story Refresh — Lightweight Context Reset

**Description**: Between stories, Ralph runs a context-saving sequence: persist state to file, then run `/refresh` to compress old context. Less aggressive than sub-agents but prevents unbounded accumulation.

**Implementation**:

```
After STEP 7 (story complete or skipped), before STEP 2 (next story):

STEP 7.5: Inter-Story Context Management

1. Persist Ralph state to `.claude/ralph-state.json`:
   {
     "session_id": "[timestamp]",
     "stories_completed": ["STORY-001", ...],
     "stories_skipped": ["STORY-003", ...],
     "current_progress": "3/5",
     "checkpoint_hash": "[hash]",
     "last_story_summary": "[what happened]"
   }

2. Run `/refresh` to re-sync context.

3. Read `.claude/ralph-state.json` to restore Ralph state.

4. Continue to STEP 2.
```

- **Pros**: Simple to implement. `/refresh` already exists and works. State file preserves Ralph progress across compactions. Lower complexity than sub-agents. Works within current skill architecture.
- **Cons**: `/refresh` doesn't actually free context — it just adds a summary. Auto-compaction is the only real context recovery, and that's lossy. State file is a band-aid — if context compacts during a story (not between), the problem remains. Doesn't solve the fundamental issue that long stories exhaust context.

### Idea 11: End-to-End Audit Skill — `/audit`

**Description**: A new skill that validates the entire artifact chain end-to-end. Run at any time to get a comprehensive health report of the workflow's integrity.

**Audit checks**:

```
/audit — Full Workflow Integrity Audit

1. PLAN.md Completeness
   - [ ] Goal section filled (not placeholder)
   - [ ] At least one phase defined
   - [ ] Every phase has: Changes, Interface Contracts, Data Flow, Testing Strategy, Done When, Verification Command
   - [ ] All Done When criteria have R-PN-NN format IDs
   - [ ] Pre-Flight Checklist items all addressed
   - [ ] Risks & Mitigations section filled

2. prd.json ↔ PLAN.md Alignment
   - [ ] prd.json version is "2.0" (structured schema)
   - [ ] Every story's acceptance criteria IDs exist in PLAN.md Done When
   - [ ] Every PLAN.md requirement ID appears in at least one story's criteria
   - [ ] Story count matches phase count (or justified divergence)
   - [ ] gateCmds match PLAN.md verification commands

3. Test Coverage Traceability
   - [ ] For each R-PN-NN ID in prd.json: grep finds matching test marker in test files
   - [ ] Zero "untraceable" criteria (criteria with no linked test)
   - [ ] Test files referenced in prd.json testFile fields actually exist
   - [ ] No orphan tests (tests with R-PN-NN markers that don't match any criterion)

4. Verification Log Integrity
   - [ ] verification-log.md exists (if any phases completed)
   - [ ] Every completed phase has a verification entry
   - [ ] No FAIL entries without a subsequent PASS (unresolved failures)
   - [ ] Mock Quality and Blast Radius checks present in each entry

5. Architecture Conformance
   - [ ] ARCHITECTURE.md is populated (not placeholder)
   - [ ] No [AUTO-DETECTED] tags remaining unchecked
   - [ ] Components in ARCHITECTURE.md match actual file structure

6. Hook Chain Health
   - [ ] All 5 hooks exist and are syntactically valid Python
   - [ ] _lib.py importable without errors
   - [ ] .needs_verify marker status (present/absent)
   - [ ] .stop_block_count status (present/absent/value)
   - [ ] workflow.json exists and is valid JSON (if present)

7. Git Hygiene
   - [ ] No uncommitted changes containing secrets (.env patterns)
   - [ ] No debug prints in committed code
   - [ ] Conventional commit format in recent commits
   - [ ] No merge conflicts in tracked files

Output:
## Audit Report — [timestamp]

### Summary: [X/7 sections PASS] — Overall: PASS/FAIL

### Section Details
[Per-section pass/fail with evidence]

### Critical Issues (must fix)
- [List]

### Warnings (should fix)
- [List]

### Clean Items
- [List of things that passed]
```

- **Pros**: Single command gives complete workflow health. Catches drift between artifacts that individual agents miss. Can be run before starting a Ralph sprint to validate readiness. Can be run after a sprint to validate completeness. Provides the "end-to-end perfected audit" the user requested.
- **Cons**: Another skill to maintain. Some checks (grep for test markers) may be slow on large codebases. The audit is read-only — it reports problems but doesn't fix them. Risk of "audit fatigue" if it reports too many warnings for template/placeholder state.

### Idea 12: Feature Planning Score Upgrade (8/10 → 9/10)

**Current gap**: The Pre-Flight Checklist in `architect.md` is a manual checklist that the Architect self-verifies. There's no independent validation. The Architect can claim "all checks pass" without actually verifying.

**Fix**: Add a Pre-Flight Validation step to `feature_plan/SKILL.md` that programmatically checks what can be checked:

```
### 6. Pre-Flight Validation (Automated Checks)

After writing the plan, run these automated checks:

a. Files exist check:
   - For each file in Changes tables marked MODIFY:
     Glob for the file. If not found → FAIL.

b. Requirement ID format check:
   - For each Done When item: verify it starts with R-PN-NN pattern.
     If any don't → FAIL.

c. Interface Contracts completeness:
   - For each phase that has a Changes table entry with Action = "ADD function" or "MODIFY function":
     Verify Interface Contracts table has a matching row.
     If missing → FAIL.

d. Testing Strategy completeness:
   - For each phase: verify Testing Strategy section has at least one row.
     If missing → FAIL.

e. Verification command check:
   - For each phase: verify Verification Command is not placeholder syntax.
     If it contains "[", "]", "your_command_here", or "TBD" → FAIL.

f. Cross-phase consistency:
   - For each Interface Contract in Phase N that is consumed by Phase N+1:
     Verify the signature matches.
     If mismatch → FAIL.

If ANY check fails: fix the plan before declaring it complete.
Report all check results to the user.
```

- **Pros**: Moves Pre-Flight from honor system to automated validation. Catches the most common planning anti-patterns (AP-1 through AP-6) before the plan is finalized. Quick to run — all checks are Glob/Grep/Read operations.
- **Cons**: Some checks require interpretation (e.g., "is this Interface Contract complete?") that automated validation can't fully cover. False positives possible for legitimate "N/A" entries. Adds ~20 lines to an already-long skill file.

### Idea 13: QA Agent Enhancement — Acceptance Test Execution

**Current gap**: QA agent has 14 verification steps but Step 11 (System/E2E test) only runs "if the plan's Testing Strategy includes E2E tests." There's no explicit acceptance test step that validates each R-PN-NN criterion against actual system behavior.

**Fix**: Add Step 15 to QA agent:

```
15. **Acceptance test validation** — For each Done When criterion (R-PN-NN) in the current phase:
    - Find the test that carries the "# Tests R-PN-NN" marker
    - Verify that test PASSED in the most recent test run
    - If the criterion describes observable behavior (e.g., "GET /api returns 200"):
      Execute the verification directly (curl, script, etc.) and confirm
    - Every criterion must have: (a) a linked test, (b) a passing result
    - If any criterion has no linked test: FAIL with "Untraceable: R-PN-NN"
```

- **Pros**: Closes the V-Model's top level (Requirements ↔ Acceptance Testing). Every requirement is verified by name, not just by "tests pass." Catches the scenario where tests pass but don't actually cover the acceptance criteria.
- **Cons**: Adds execution time. Direct verification (curl, etc.) may not be possible for all criteria types. Requires test markers to exist — which depends on Builder discipline.

---

## Revised Evaluation Matrix (All 13 Ideas)

| Idea                              | Gaps Closed      | Complexity | Process Overhead | Robustness | Recommended               |
| --------------------------------- | ---------------- | ---------- | ---------------- | ---------- | ------------------------- |
| 1. Plan-Build-Verify inner loop   | 1, 2, 4, 5       | Medium     | High             | Very High  | YES (core)                |
| 2. Smart plan detection           | 1 (refined)      | Low        | Low              | Medium     | YES (optimize #1)         |
| 3. Structured prd.json v2         | 3, 5, 7          | Medium     | Low              | High       | YES (core)                |
| 4. QA verification pipeline       | 2, 5, 8, 10      | Medium     | High             | Very High  | YES (core)                |
| 5. Checkpoint-aware rollback      | 9, 10            | Low        | None             | High       | YES (surgical fix)        |
| 6. Naming convention traceability | 5                | Low        | Low              | Medium     | YES (supplements #3)      |
| 7. Tiered Express/Full modes      | N/A              | High       | Reduces overhead | Medium     | NO (creates bypass)       |
| 8. prd.json auto-generation       | 3, 5, 7          | Medium     | Negative         | High       | YES (replaces manual)     |
| 9. Sub-agent per story            | 11 (context)     | High       | None             | Very High  | YES (best context fix)    |
| 10. Inter-story refresh           | 11 (partial)     | Low        | Low              | Low        | FALLBACK (if #9 rejected) |
| 11. /audit skill                  | All (validation) | Medium     | None (on-demand) | Very High  | YES (end-to-end audit)    |
| 12. Automated Pre-Flight          | Feature plan 8→9 | Low        | Low              | High       | YES (quick win)           |
| 13. QA acceptance test step       | V-Model Level 1  | Low        | Medium           | High       | YES (closes V-Model top)  |

## Revised Recommendation

**Implement Ideas 1 + 2 + 3 + 4 + 5 + 6 + 8 + 9 + 11 + 12 + 13. Reject Ideas 7 and 10.**

### Revised Projected Scores

| Component            | Before | After    | Key Additions                                                |
| -------------------- | ------ | -------- | ------------------------------------------------------------ |
| Ralph orchestration  | 5/10   | **9/10** | Plan-Build-Verify, sub-agent isolation, checkpoint rollback  |
| V-Model traceability | 4/10   | **9/10** | R-PN-NN enforcement + QA acceptance test step closes Level 1 |
| prd.json schema      | 4/10   | **9/10** | Structured v2, auto-generated from PLAN.md                   |
| Feature planning     | 8/10   | **9/10** | Automated Pre-Flight validation                              |
| Individual agents    | 9/10   | **9/10** | QA gains acceptance test step (#13)                          |
| Hook enforcement     | 9/10   | **9/10** | No changes needed                                            |
| End-to-end audit     | N/A    | **9/10** | New /audit skill validates entire chain                      |
| Context management   | 3/10   | **8/10** | Sub-agent isolation prevents exhaustion                      |

### Implementation Files (Revised)

| File                                   | Change Type     | Purpose                                                    |
| -------------------------------------- | --------------- | ---------------------------------------------------------- |
| `.claude/skills/ralph/SKILL.md`        | MAJOR REWRITE   | Plan-Build-Verify, sub-agent dispatch, checkpoint rollback |
| `.claude/prd.json`                     | REPLACE         | v2 schema template                                         |
| `.claude/skills/feature_plan/SKILL.md` | ADD Steps 6b, 7 | Automated Pre-Flight + prd.json auto-generation            |
| `.claude/skills/audit/SKILL.md`        | NEW             | End-to-end workflow integrity audit                        |
| `.claude/agents/qa.md`                 | ADD Step 15     | Acceptance test validation                                 |
| `CLAUDE.md`                            | MINOR EDIT      | Document /audit, /feature_plan as planning workflow        |

### Implementation Order (Revised)

1. **prd.json v2 schema** (Idea 3) — foundation
2. **feature_plan upgrades** (Ideas 8 + 12) — auto-generation + automated Pre-Flight
3. **QA agent Step 15** (Idea 13) — acceptance test validation
4. **Ralph rewrite** (Ideas 1 + 2 + 4 + 5 + 6 + 9) — the main deliverable
5. **`/audit` skill** (Idea 11) — end-to-end validation
6. **CLAUDE.md documentation** — document the new workflow

---

## Sources

### Project Docs Read

- `.claude/skills/ralph/SKILL.md` (227 lines) — current Ralph loop, all 7 steps
- `.claude/skills/feature_plan/SKILL.md` (93 lines) — current planning skill
- `.claude/skills/verify/SKILL.md` (107 lines) — current verification skill
- `.claude/agents/architect.md` (116 lines) — Architect agent with Pre-Flight Checklist
- `.claude/agents/builder.md` (93 lines) — Builder agent with Plan Sanity Check
- `.claude/agents/qa.md` (58 lines) — QA agent with 14 verification steps
- `.claude/prd.json` (29 lines) — current story template
- `.claude/docs/brainstorms/2026-02-27-planning-workflow-gaps.md` (238 lines) — 22-gap V-Model analysis
- `.claude/docs/brainstorms/2026-02-11-nba-tdd-governance-gaps.md` (318 lines) — RTM and governance design
- `.claude/docs/knowledge/planning-anti-patterns.md` (57 lines) — 7 anti-patterns
- `.claude/hooks/_lib.py` (269 lines) — shared hook library
- `.claude/hooks/stop_verify_gate.py` (71 lines) — verification enforcement hook
- `.claude/hooks/post_bash_capture.py` (87 lines) — test detection and marker clearing
- `CLAUDE.md` — project-level workflow documentation
- `PROJECT_BRIEF.md` — project template (placeholder state)
- `.claude/docs/ARCHITECTURE.md` — architecture template (placeholder state)

### External Research

- [Perforce: Requirements Traceability Matrix](https://www.perforce.com/blog/alm/how-create-traceability-matrix) — RTM best practices and CI/CD integration
- [Teaching Agile: V-Model Verification & Validation](https://teachingagile.com/sdlc/models/v-model) — V-Model level-by-level testing correspondence
- [LDRA: Requirements Traceability](https://ldra.com/capabilities/requirements-traceability/) — automated traceability enforcement in safety-critical industries
- [Ketryx: IEC 62304 RTM in Jira](https://www.ketryx.com/blog/iec-62304-requirements-traceability-matrix-rtm-in-jira-a-guide-for-medical-device-companies) — regulated-industry RTM patterns applicable to rigorous SDLC
