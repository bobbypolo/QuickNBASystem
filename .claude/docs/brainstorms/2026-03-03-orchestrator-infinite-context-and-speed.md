# Brainstorm: Orchestrator Infinite Context + Speed

**Date**: 2026-03-03
**Problem**: The Ralph orchestrator runs as one monolithic conversation, accumulating ~6-8K tokens per story. A 6-story sprint hits 75-85K tokens before context compaction, which is lossy -- Ralph hallucates, repeats stories, or improvises. Workers already have infinite context by construction (fresh window per dispatch). The orchestrator should use the same pattern.

**Cross-references**:

- `2026-03-03-orchestrator-context-refresh.md` -- Option A-D analysis; Option D (hybrid mitigation) was recommended but is acknowledged as a mitigation, not the real solution
- `2026-03-02-ralph-perfection-infinite-context.md` -- Idea 8 (infinite context architecture), Idea 3 (parallel sub-agent execution)
- `2026-03-02-context-bloat-reduction.md` -- Pre-loaded context reduction (~6,350 token savings)
- `2026-03-01-context-window-optimization.md` -- System-level context budget analysis
- `2026-03-02-hooks-simplification.md` -- \_lib.py modularization (ongoing, Phases 1-2 complete)
- PLAN-hook-resilience.md -- Phase 4 is the Option D implementation, potentially superseded here

**Key Insight**: The previous brainstorm identified Option B (self-dispatching orchestrator) as the theoretically correct solution but flagged 2-level sub-agent nesting as "unknown." That turns out to be wrong -- the Agent tool is available to all agent types including `ralph-worker`, meaning sub-agents CAN dispatch sub-agents. The constraint in `ralph-worker.md` ("Sub-agents cannot spawn sub-agents") is a self-imposed rule in the prompt text, not a platform limitation. This unlocks Option B.

---

## 1. Story-Per-Agent Pattern (TRUE Infinite Context for Orchestrator)

### Core Architecture

Split `/ralph` into two layers:

```
User conversation (/ralph skill -- the OUTER LOOP)
  |
  |-- STEP 1: Initialize (validate prd.json, init state, feature branch)
  |-- Loop:
  |     |-- Read state from .workflow-state.json
  |     |-- Find next unpassed story
  |     |-- Dispatch ralph-story-agent for that story (Agent tool, fresh context)
  |     |     |
  |     |     |-- Reads prd.json, PLAN.md, state, progress.md
  |     |     |-- STEP 4: Create safety checkpoint
  |     |     |-- STEP 5A: Plan check
  |     |     |-- STEP 5: Dispatch ralph-worker (Agent tool, isolation: worktree)
  |     |     |-- STEP 6: Handle result (validate receipt, diff review, merge, regression)
  |     |     |-- STEP 6A: Progress file
  |     |     |-- Update state file
  |     |     |-- Return RALPH_STORY_RESULT
  |     |
  |     |-- Parse story result (~500 tokens)
  |     |-- Check circuit breaker
  |     |-- Continue or stop
  |
  |-- STEP 8: Sprint summary + PR creation
```

**Why this works**: The outer loop NEVER accumulates story-level context. Each `ralph-story-agent` gets a fresh 200K context window. The outer loop only sees the structured `RALPH_STORY_RESULT` (pass/fail, summary, files changed, verification ref) -- roughly 300-500 tokens per story. A 20-story sprint adds ~10K tokens to the outer loop. The outer loop will NEVER hit compaction.

**Nesting depth**:

```
Level 0: User conversation (outer loop)
Level 1: ralph-story-agent (per-story orchestrator, fresh context)
Level 2: ralph-worker (implementation + verification, isolation: worktree)
```

### Defining the Story Agent

**Option A: New agent file (`.claude/agents/ralph-story.md`)**

Create a new agent definition file containing the per-story orchestration logic -- essentially STEPs 4 through 6A from the current SKILL.md, adapted for single-story execution. The outer loop dispatches it via:

```
Agent tool:
  subagent_type: "ralph-story"
  prompt: [story assignment with full context]
```

The agent file would specify:

- `isolation: none` -- the story agent merges to the feature branch, so it must NOT be in a worktree
- `maxTurns: 200` -- enough for worker dispatch + retries + merge + regression
- `memory: user` -- persist lessons across stories
- `permissionMode: acceptEdits` -- needs git operations
- `model: inherit`

**Option B: Inline prompt (no new agent file)**

Define the story agent entirely via the dispatch prompt, with no `.md` file. The outer loop constructs a comprehensive prompt that includes all the protocol instructions inline. This is how ralph-worker already works -- the worker's behavior is 50% defined by `ralph-worker.md` and 50% by the dispatch prompt.

**Recommendation: Option A (new agent file).** The per-story orchestration logic is substantial (~150 lines of protocol for checkpoint, plan check, worker dispatch, receipt validation, diff review, merge, regression, state update). Inlining all of that in the dispatch prompt would consume ~3-4K tokens per dispatch. An agent file means the protocol loads once from disk and the dispatch prompt only needs the story-specific context (~500-800 tokens).

### Story Agent Definition: `ralph-story.md`

```markdown
---
name: ralph-story
description: Per-story orchestrator. Handles one complete story cycle including worker dispatch, validation, merge, and regression.
maxTurns: 200
memory: user
model: inherit
permissionMode: acceptEdits
---

# Ralph Story Agent -- Single Story Orchestrator

You handle one story from the Ralph sprint. You receive a story assignment
and execute the full cycle: checkpoint, plan check, worker dispatch,
receipt validation, diff review, merge, regression, and state update.

## Startup

1. Read `.claude/docs/PLAN.md` for the implementation plan
2. Read `.claude/prd.json` for story details and acceptance criteria
3. Review the story assignment in your dispatch prompt

## Critical Rules

- You dispatch `ralph-worker` sub-agents for implementation (isolation: worktree)
- You merge worker results to the feature branch
- You run cumulative regression after merge
- You update `.claude/.workflow-state.json` and `.claude/prd.json` on completion
- You return a structured RALPH_STORY_RESULT as your final output

## STEP 4: Create Safety Checkpoint

[... current SKILL.md STEP 4 content ...]

## STEP 5A: Plan Check

[... current SKILL.md STEP 5A content ...]

## STEP 5: Dispatch Worker

[... current SKILL.md STEP 5 content ...]

## STEP 6: Handle Result

[... current SKILL.md STEP 6 content, including receipt validation,
diff review, merge, regression, prd.json update, verification log ...]

## Return Format

RALPH_STORY_RESULT:
{
"story_id": "STORY-NNN",
"passed": true/false,
"skipped": true/false,
"attempts": N,
"summary": "What happened",
"files_changed": ["list"],
"verification_ref": "verification-log.jsonl",
"failure_summary": "If failed/skipped, why"
}
```

### Lean Outer Loop (New SKILL.md)

The current 348-line SKILL.md becomes ~80-100 lines. Most of the protocol moves into `ralph-story.md`. What remains in the outer loop:

```
STEP 1: Initialize
  - Validate prd.json (schema, version, plan-PRD sync)
  - Init sprint state
  - Display story count and progress

STEP 1.5: Feature Branch Setup
  - Create or checkout ralph/{plan-name}
  - Record in sprint state

STEP 2: Find Next Story
  - Re-read sprint state from .workflow-state.json
  - Re-read prd.json (find first unpassed story)
  - Display STATE SYNC
  - If all passed: go to STEP 8

STEP 3: Dispatch Story Agent
  - Construct dispatch prompt with:
    - Story ID, phase, description, acceptance criteria, gate commands
    - Feature branch name
    - Current attempt number and max_attempts
    - Prior failure summary (if retry)
    - Sprint progress context
  - Launch ralph-story agent via Agent tool
  - Receive RALPH_STORY_RESULT

STEP 4: Handle Story Result
  - Parse RALPH_STORY_RESULT
  - If passed: reset consecutive_skips, increment stories_passed
  - If failed with attempts remaining: increment attempt, store failure, go to STEP 3
  - If exhausted: increment skips, go to STEP 5
  - Circuit breaker: if consecutive_skips >= 3, go to STEP 6
  - Otherwise: go to STEP 2

STEP 5: Record Skip
  - Append skip to progress.md
  - Continue to STEP 2

STEP 6: End of Session
  [... current STEP 8 content: PR creation ...]
```

**Comparison**:

| Aspect             | Current SKILL.md                      | Proposed SKILL.md    |
| ------------------ | ------------------------------------- | -------------------- |
| Lines              | ~348                                  | ~80-100              |
| Tokens             | ~5,000                                | ~1,200-1,500         |
| Steps              | 10 (STEP 1 through 8, plus 5A and 6A) | 6 (STEP 1 through 6) |
| Receipt validation | In outer loop (~60 lines)             | In story agent       |
| Diff review        | In outer loop (~40 lines)             | In story agent       |
| Merge logic        | In outer loop (~20 lines)             | In story agent       |
| Regression         | In outer loop (~15 lines)             | In story agent       |
| Worker dispatch    | In outer loop (~30 lines)             | In story agent       |

### State Management Between Layers

The state file `.claude/.workflow-state.json` is the coordination point:

```
Outer loop WRITES:
  - consecutive_skips (incremented on skip)
  - stories_passed (incremented on pass)
  - stories_skipped (incremented on skip)
  - feature_branch (set at STEP 1.5)
  - current_story_id (set before dispatch)
  - current_attempt (set before dispatch)
  - prior_failure_summary (set before retry)

Story agent WRITES:
  - current_step (set at each major transition within the story)
  - Updates prd.json (sets passed: true, verificationRef)
  - Appends to verification-log.jsonl
  - Appends to verification-log.md
  - Appends to progress.md

Story agent READS:
  - All sprint state fields
  - prd.json (story details, acceptance criteria, gate commands)
  - PLAN.md (for plan check and diff review)
  - progress.md (for worker dispatch context)
```

**Concurrency safety**: There is no concurrency issue in the sequential pattern -- only one story agent runs at a time, and the outer loop waits for it to complete before continuing. The state file is single-writer at any point.

### Error Handling

**Story agent crashes (no result returned)**:

The outer loop treats a missing or unparseable `RALPH_STORY_RESULT` as a FAIL:

```
If no RALPH_STORY_RESULT found in agent output:
  - Treat as FAIL with summary: "Story agent returned no structured result"
  - Check if story agent made commits (git log since checkpoint)
  - If commits exist: git reset to checkpoint (agent crashed mid-merge)
  - Proceed to retry logic
```

**Story agent exceeds maxTurns**:

The Agent tool returns the agent's last output. The outer loop checks for `RALPH_STORY_RESULT` in the output. If absent, treat as FAIL.

**Worker crashes inside story agent**:

The story agent handles this internally (worker result parsing, retry within the story agent's context). If the story agent exhausts all worker retries, it returns `RALPH_STORY_RESULT` with `passed: false, skipped: true`.

### Retry Logic Placement

**Current**: Retries are managed by the OUTER loop -- it re-dispatches the worker with `prior_failure_summary`.

**Proposed**: Two options.

**Option A: Retries inside the story agent.**
The story agent dispatches the worker, and if the worker fails, the story agent dispatches again (up to max_attempts). The outer loop dispatches the story agent ONCE per story. If the story agent returns `skipped: true`, the outer loop records the skip.

- Pros: The story agent has full context about what went wrong (it parsed the worker's failure). It can adjust the retry prompt based on specific failures.
- Cons: The story agent accumulates retry context (~3-5K per retry \* 4 retries = 12-20K). For a story with 4 retries, the story agent uses 12-20K tokens for retry context -- still well within the 200K window.

**Option B: Retries in the outer loop.**
The outer loop dispatches a fresh story agent for each attempt. Each story agent handles exactly one worker dispatch. If the worker fails, the story agent returns FAIL, and the outer loop dispatches a NEW story agent with the failure context.

- Pros: Each story agent is truly minimal (one worker dispatch). Even retries get fresh context.
- Cons: More round-trips. The outer loop accumulates retry results (~500 tokens each). For 4 retries across 6 stories, that is 12K tokens -- still acceptable but larger than Option A's outer loop footprint.

**Recommendation: Option A (retries inside the story agent).** The story agent has plenty of context budget (200K) and retry context is small (3-5K per retry). This keeps the outer loop maximally thin. The outer loop sees at most one `RALPH_STORY_RESULT` per story, regardless of how many retries happened internally.

### What the "Sub-agents cannot spawn sub-agents" Line Really Means

The line in `ralph-worker.md` says: "Sub-agents cannot spawn sub-agents." This was written as a behavioral instruction to the worker (telling it not to try), not as a platform constraint. The Agent tool specification makes all tools available to sub-agents. A sub-agent CAN use the Agent tool.

To implement story-per-agent, we need to:

1. Remove or update the line in `ralph-worker.md` (it does not apply to the story agent, but the worker should still not spawn sub-agents itself)
2. Ensure the story agent's agent definition does NOT include `isolation: worktree` (it merges to the feature branch)
3. Ensure the worker's agent definition KEEPS `isolation: worktree`

The story agent is the ONLY layer that dispatches workers. The worker remains a leaf node.

---

## 2. Parallel Story Dispatch (Speed Improvement)

### When Is Parallel Dispatch Safe?

Two stories can run in parallel if and only if:

1. **No file overlap**: The stories do not modify the same files (checked via PLAN.md Changes Tables)
2. **No data flow dependency**: One story's output is not another story's input (checked via `dependsOn` field in prd.json, or inferred from phase ordering)
3. **Same phase**: Stories in the same phase are designed to be independent (by convention in the ADE planning process)

The safest heuristic: **stories in the same phase with non-overlapping Changes Tables can run in parallel.**

### How Parallel Dispatch Works

```
Outer loop detects 3 independent stories in Phase 2:
  STORY-003: Changes files A, B
  STORY-004: Changes files C, D
  STORY-005: Changes files E, F

  1. Dispatch ralph-story-agent for STORY-003  ]
  2. Dispatch ralph-story-agent for STORY-004  ] -- simultaneous via multiple Agent tool calls
  3. Dispatch ralph-story-agent for STORY-005  ]

  4. Collect all RALPH_STORY_RESULTs (Agent tool returns when each completes)

  5. Process results IN ORDER (STORY-003, then 004, then 005):
     - For each PASSED result: merge is already done by the story agent
     - For each FAILED result: record failure, queue for retry

  6. Run cumulative regression ONCE after all merges
     (instead of per-story regression)
```

### The Merge Ordering Problem

With parallel dispatch, multiple story agents may try to merge their workers' worktree branches to the feature branch simultaneously. This is a critical issue:

**Problem**: Story agents run in parallel. Each one dispatches a worker, validates the result, and merges. If STORY-003 and STORY-004 both try to `git merge` at the same time, they will conflict or corrupt the branch.

**Solution A: Story agents do NOT merge. They return the worktree branch name, and the OUTER LOOP merges sequentially.**

```
Story agent protocol (parallel mode):
  - Dispatch worker
  - Validate receipt, run diff review
  - Do NOT merge
  - Return RALPH_STORY_RESULT with worktree_branch field

Outer loop (after all story agents complete):
  - For each PASSED result, in story order:
    - git merge --no-ff [worktree_branch]
    - If merge conflict: git merge --abort, treat as FAIL
  - Run cumulative regression once after all merges
```

This is the safe approach. The outer loop serializes merges, avoiding conflicts.

**Solution B: Story agents merge, but acquire a lock.**

Not feasible -- there is no cross-agent locking mechanism.

**Recommendation: Solution A.** In parallel mode, story agents validate but do NOT merge. The outer loop handles merge and regression. This adds some protocol to the outer loop (merge logic stays in the outer loop for parallel mode) but is the only safe approach.

### Hybrid Mode: Sequential Merge Within Parallel Dispatch

For the outer loop:

```
If story count in current phase == 1:
  Dispatch story agent (it handles merge internally)    -- sequential mode

If story count in current phase > 1 and files non-overlapping:
  Dispatch story agents in parallel (they skip merge)   -- parallel mode
  Merge results sequentially in outer loop
  Run regression once after all merges

If story count in current phase > 1 but files overlap:
  Dispatch sequentially (story agents handle merge)     -- sequential mode
```

### Regression Strategy for Parallel Results

**Current**: Regression runs after EVERY story merge (cumulative).

**Parallel optimization**: Regression runs ONCE after all parallel stories are merged. This is safe because:

- All parallel stories were validated independently (receipt, diff review)
- If regression fails, the last-merged story is the most likely cause
- Rollback: `git reset --hard [checkpoint-before-parallel-batch]` undoes all parallel merges

**Rollback protocol for parallel regression failure**:

```
If regression fails after parallel batch merge:
  1. git reset --hard [pre-batch-checkpoint]
  2. Re-dispatch stories SEQUENTIALLY (fall back to sequential mode)
  3. Run regression after each merge to identify the breaking story
```

### State Management for Parallel Dispatch

The outer loop must track which stories are in-flight:

```json
{
  "ralph": {
    "parallel_batch": ["STORY-003", "STORY-004", "STORY-005"],
    "parallel_checkpoint": "abc123...",
    "stories_in_flight": 3
  }
}
```

Story agents in parallel mode only update their own story's state (prd.json `passed` field, verification log). They do NOT update sprint-level counters (those are managed by the outer loop after collecting results).

### Speed Estimate

Current sequential sprint (6 stories, ~20 min each): ~120 minutes.

Parallel sprint (2 parallel batches of 3): ~40-50 minutes.

**2-3x speedup** for sprints where stories are parallelizable.

---

## 3. Lean Orchestrator Protocol

### What Stays in the Outer Loop

| Responsibility                                       | Lines (est.) | Notes                                    |
| ---------------------------------------------------- | ------------ | ---------------------------------------- |
| STEP 1: Initialize (prd.json validation, state init) | ~25          | Same as today                            |
| STEP 1.5: Feature branch setup                       | ~15          | Same as today                            |
| STEP 2: Find next story                              | ~15          | Simplified (just reads state + prd.json) |
| STEP 3: Dispatch story agent                         | ~20          | Construct prompt, launch Agent tool      |
| STEP 4: Handle result                                | ~15          | Parse result, update sprint counters     |
| STEP 5: Record skip (if needed)                      | ~5           | Append to progress.md                    |
| STEP 6: End of session / PR                          | ~20          | Same as today                            |
| Error recovery table                                 | ~10          | Simplified                               |
| **Total**                                            | **~100-125** | **Down from 348**                        |

### What Moves to the Story Agent

| Responsibility                    | Lines (est.) | Notes                                   |
| --------------------------------- | ------------ | --------------------------------------- |
| STEP 4: Safety checkpoint         | ~10          | git rev-parse, clean check              |
| STEP 5A: Plan check               | ~15          | R-marker comparison                     |
| STEP 5: Worker dispatch           | ~30          | Construct prompt, embed context         |
| STEP 6: Receipt validation        | ~50          | 4 sub-checks + pre-existing override    |
| STEP 6: Diff review (5 questions) | ~35          | Read diff, read plan, answer Q1-Q5      |
| STEP 6: Merge + conflict handling | ~15          | git merge --no-ff, --abort on conflict  |
| STEP 6: Regression                | ~15          | Read workflow.json, run command         |
| STEP 6: Update prd.json + logs    | ~15          | JSON update, JSONL append               |
| STEP 6A: Progress file            | ~10          | Append to progress.md                   |
| Retry logic (internal)            | ~20          | Re-dispatch worker with failure context |
| Return format                     | ~10          | RALPH_STORY_RESULT                      |
| **Total**                         | **~225**     | New content in ralph-story.md           |

### Protocol Simplification Opportunities

With the story agent handling the complex middle, the outer loop protocol becomes almost trivially simple:

1. **No receipt validation in outer loop** -- the story agent validates and returns pass/fail
2. **No diff review in outer loop** -- the story agent performs it
3. **No merge logic in outer loop** (sequential mode) -- the story agent merges
4. **No regression in outer loop** (sequential mode) -- the story agent runs it
5. **No worker dispatch prompt construction** -- the story agent constructs it

The outer loop is a state machine with 6 states and simple transitions. It is robust against context compaction because:

- Its protocol is ~100 lines (easily re-read from SKILL.md)
- Its accumulated context is ~500 tokens per story (just results)
- It re-reads state from disk at every STEP 2

---

## 4. Speed Optimizations (Beyond Parallelism)

### 4.1 Graduated QA

**Concept**: Simple stories (single file, small change, pure addition) get lighter QA. Complex stories (multi-file, refactoring, interface changes) get full 12-step.

**Implementation**:

Add `complexity` field to prd.json stories (set by `/plan`):

```json
{
  "id": "STORY-001",
  "complexity": "simple",   // or "standard" or "complex"
  ...
}
```

QA strategy per complexity:

| Complexity | QA Steps                                    | Skip                                                                                               | Rationale                                                     |
| ---------- | ------------------------------------------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| simple     | lint, unit_tests, regression, security_scan | type_check, integration, clean_diff, coverage, mock_audit, plan_conformance, acceptance, prod_scan | Single-file additions with clear tests need only basic checks |
| standard   | All 12 steps                                | none                                                                                               | Default                                                       |
| complex    | All 12 steps + extra regression             | none                                                                                               | Multi-file refactoring gets full treatment                    |

**Feasibility**: High. The `/plan` skill can assess complexity from the Changes Table (file count, MODIFY vs NEW, interface changes). The `qa_runner.py` already supports `--phase-type` for adaptive QA; adding `--complexity` would follow the same pattern.

**Quality impact**: Low risk. Simple stories have narrow blast radius by definition. The worker still runs unit tests and lint, which catch the vast majority of issues. Plan conformance is the main loss, but simple stories have trivial plan conformance (one file, one change).

**Implementation complexity**: Medium. Requires prd.json schema extension, `/plan` changes, `qa_runner.py` changes, and `ralph-worker.md` changes. ~100 lines of code across 4 files.

### 4.2 Incremental Regression

**Concept**: Run full cumulative regression only at phase boundaries (or every N stories). Run quick targeted tests per story.

**Current**: After every story merge, the outer loop runs the full regression suite (all hook tests, ~690 tests, takes ~30-60 seconds).

**Proposed**:

```
Per story: run only the story's gate commands (unit tests for changed files)
Every 3 stories OR at phase boundary: run full regression
At sprint end: run full regression
```

**Feasibility**: High. The infrastructure already separates gate commands (per-story) from regression (cumulative). The change is in when the cumulative regression runs.

**Quality impact**: Medium risk. A story could break a test in an unrelated file, and the breakage would not be caught until the next regression checkpoint. Mitigation: the phase boundary regression catches it before the next phase starts.

**Implementation complexity**: Low. Change the regression trigger condition in the story agent (or outer loop). ~10 lines of logic.

### 4.3 Optimized Diff Review

**Concept**: Skip plan-dependent questions (Q1: files in Changes Table, Q2: changes match plan, Q5: signatures match Interface Contracts) when the plan is stable and the story is straightforward.

**Current**: All 5 questions are asked for every story. Q1, Q2, and Q5 require reading PLAN.md and cross-referencing with the diff. This adds ~1-2K tokens of plan content to the story agent's context.

**Proposed**:

```
If story.complexity == "simple":
  Skip Q1, Q2, Q5 (plan-dependent)
  Only check Q3 (test files present) and Q4 (no debug artifacts)

If story.complexity == "standard" or "complex":
  All 5 questions
```

**Feasibility**: High. The diff review is instruction-based (in the story agent protocol), not code. Changing the instructions is trivial.

**Quality impact**: Low for simple stories. Q3 (test files) and Q4 (debug artifacts) are the highest-value checks. Q1/Q2/Q5 are most valuable for complex multi-file changes where scope creep is a risk.

**Implementation complexity**: Very low. ~5 lines of conditional in the story agent protocol.

### 4.4 Worker Context Optimization

**Concept**: Reduce the size of the dispatch prompt sent to workers. Currently the dispatch prompt embeds:

- Story details (~300 tokens)
- All acceptance criteria (~200 tokens)
- Gate commands (~50 tokens)
- Checkpoint hash (~50 tokens)
- Attempt number + prior failure context (~100-500 tokens)
- Sprint progress from progress.md (~200-500 tokens)
- Instructions (~200 tokens)

Total: ~1,100-1,800 tokens per dispatch.

**Optimization**: The worker reads PLAN.md anyway (it is in the worktree). The worker reads prd.json from disk. The dispatch prompt only needs to provide:

- Story ID (worker reads details from prd.json)
- Checkpoint hash
- Attempt number + prior failure context
- Sprint progress summary (2-3 lines, not full progress.md)

This reduces the dispatch prompt to ~300-500 tokens.

**Feasibility**: High. The worker already reads PLAN.md and prd.json in its startup phase. The dispatch prompt duplicates information the worker can get from disk.

**Quality impact**: None. Same information, different source (disk vs prompt).

**Implementation complexity**: Low. Change the dispatch prompt template in the story agent. ~10 lines of change.

### 4.5 Pre-Flight File Caching in Story Agent

**Concept**: The story agent reads PLAN.md once at startup and extracts only the relevant phase information. It does not re-read PLAN.md for each sub-step (plan check, diff review, etc.).

**Current pattern**: PLAN.md is read multiple times:

1. STEP 5A: Plan check reads it to extract R-markers
2. STEP 6 diff review reads it to extract Changes Table and Interface Contracts
3. Worker dispatch prompt references it

**Optimization**: Read PLAN.md once. Extract phase header, Changes Table, Interface Contracts, and R-markers. Reference the extracted data for all sub-steps.

**Feasibility**: High. This is a prompt engineering change in the story agent protocol.

**Quality impact**: None. Same information, read once instead of multiple times.

**Implementation complexity**: Very low. Add a "Startup: read PLAN.md and extract current phase info" instruction to the story agent.

### Summary of Speed Optimizations

| Optimization                | Speed Gain                          | Quality Risk | Complexity | Recommendation                         |
| --------------------------- | ----------------------------------- | ------------ | ---------- | -------------------------------------- |
| Graduated QA                | ~30% per simple story               | Low          | Medium     | Implement                              |
| Incremental regression      | ~20-40% (skip per-story regression) | Medium       | Low        | Implement with phase-boundary fallback |
| Optimized diff review       | ~10% (less plan reading)            | Low          | Very low   | Implement                              |
| Worker context optimization | ~5% (smaller prompts)               | None         | Low        | Implement                              |
| Pre-flight file caching     | ~5% (fewer file reads)              | None         | Very low   | Implement                              |

Combined estimated speedup: **40-60%** on top of the baseline, PLUS the parallelism speedup (2-3x). Total: **3-5x faster sprints**.

---

## 5. Combined Architecture Vision

### Full Target Architecture

```
User conversation
  |
  /ralph (Lean Outer Loop -- ~100 lines SKILL.md, ~1,200 tokens)
  |
  |-- STEP 1: Validate prd.json, init state
  |-- STEP 1.5: Feature branch
  |-- Loop:
  |     |-- STEP 2: Read state, find next story(ies)
  |     |     |-- Detect parallelizable batch (same phase, no file overlap)
  |     |
  |     |-- STEP 3a (Sequential): Dispatch one ralph-story-agent
  |     |     |
  |     |     ralph-story-agent (fresh 200K context)
  |     |       |-- Read PLAN.md, prd.json, extract phase info
  |     |       |-- Checkpoint, plan check
  |     |       |-- Dispatch ralph-worker (worktree isolation)
  |     |       |-- Validate receipt, diff review, merge, regression
  |     |       |-- Retry loop (up to max_attempts)
  |     |       |-- Update prd.json, logs
  |     |       |-- Return RALPH_STORY_RESULT
  |     |
  |     |-- STEP 3b (Parallel): Dispatch N ralph-story-agents simultaneously
  |     |     |
  |     |     ralph-story-agent x N (each fresh 200K context)
  |     |       |-- Same as 3a, but SKIP merge step
  |     |       |-- Return RALPH_STORY_RESULT with worktree_branch
  |     |     |
  |     |     Outer loop merges results sequentially
  |     |     Outer loop runs regression once
  |     |
  |     |-- STEP 4: Handle results, update sprint counters
  |     |-- Circuit breaker check
  |     |-- Continue or STEP 6
  |
  |-- STEP 6: Sprint summary + PR creation
```

### File Changes Needed

| File                                    | Action        | Description                                                                                              |
| --------------------------------------- | ------------- | -------------------------------------------------------------------------------------------------------- |
| `.claude/agents/ralph-story.md`         | NEW           | Per-story orchestrator agent definition (~225 lines)                                                     |
| `.claude/skills/ralph/SKILL.md`         | MAJOR REWRITE | Outer loop only (~100 lines, down from 348)                                                              |
| `.claude/agents/ralph-worker.md`        | MINOR EDIT    | Remove "Sub-agents cannot spawn sub-agents" line (line 27), since the story agent now dispatches workers |
| `.claude/prd.json` schema               | EXTEND        | Add optional `dependsOn`, `parallelGroup`, `complexity` fields                                           |
| `.claude/hooks/_lib.py`                 | MINOR EDIT    | Add `parallel_batch`, `parallel_checkpoint`, `stories_in_flight` to DEFAULT_WORKFLOW_STATE ralph section |
| `.claude/hooks/post_compact_restore.py` | MINOR EDIT    | Update state summary to include story agent info                                                         |
| `.claude/docs/ARCHITECTURE.md`          | UPDATE        | Document 3-level architecture, story agent, parallel dispatch                                            |

### New Agent Definitions

**ralph-story.md** (~225 lines):

- Frontmatter: name, description, maxTurns: 200, memory: user, model: inherit, permissionMode: acceptEdits
- Startup protocol (read PLAN.md, prd.json, extract phase info)
- STEP 4: Safety checkpoint
- STEP 5A: Plan check
- STEP 5: Worker dispatch (with context optimization)
- STEP 6: Full result handling (receipt validation, diff review, merge, regression)
- Retry loop (dispatch new workers up to max_attempts)
- STEP 6A: Progress + logs
- Return format: RALPH_STORY_RESULT

**ralph-worker.md** (minimal change):

- Remove line 27 ("Sub-agents cannot spawn sub-agents")
- No other changes -- worker behavior is unchanged

### Flow Diagram (Detailed)

```
/ralph invoked
  |
  v
STEP 1: Read prd.json
  |-- Version check (must be 2.0)
  |-- Schema validation (all stories)
  |-- Plan-PRD sync check
  |-- Init sprint state
  |
  v
STEP 1.5: Feature branch
  |-- Create or checkout ralph/{name}
  |
  v
STEP 2: Find next -------> All passed? ----> STEP 6 (PR)
  |
  | (story found)
  v
Detect parallelizable batch:
  |-- Read prd.json: group unpassed stories by phase
  |-- Check Changes Tables for file overlap
  |-- If single story or overlapping files: SEQUENTIAL mode
  |-- If multiple stories, no overlap: PARALLEL mode
  |
  |-- SEQUENTIAL ----------------------------------------|
  |     |                                                |
  |     v                                                |
  |   Dispatch ralph-story-agent(story)                  |
  |     |                                                |
  |     v                                                |
  |   Receive RALPH_STORY_RESULT                         |
  |     |                                                |
  |     |-- PASSED: stories_passed++, skips=0            |
  |     |-- FAILED (retries left): story agent retried   |
  |     |     internally; if still failed, treat as skip |
  |     |-- SKIPPED: stories_skipped++, skips++          |
  |     |                                                |
  |     v                                                |
  |   Circuit breaker (skips >= 3?) -----> STEP 6        |
  |     |                                                |
  |     v                                                |
  |   Loop to STEP 2 <----------------------------------|
  |
  |-- PARALLEL ------------------------------------------|
  |     |                                                |
  |     v                                                |
  |   Record pre-batch checkpoint                        |
  |   Dispatch N ralph-story-agents simultaneously       |
  |     (skip merge, return worktree branches)           |
  |     |                                                |
  |     v                                                |
  |   Collect all RALPH_STORY_RESULTs                    |
  |     |                                                |
  |     v                                                |
  |   For each PASSED result (in story order):           |
  |     git merge --no-ff [worktree_branch]              |
  |     If conflict: git merge --abort, mark as FAILED   |
  |     |                                                |
  |     v                                                |
  |   Run cumulative regression once                     |
  |     If fails: git reset --hard [checkpoint]          |
  |     Re-dispatch failed batch sequentially            |
  |     |                                                |
  |     v                                                |
  |   Update sprint counters for all results             |
  |   Circuit breaker check                              |
  |     |                                                |
  |     v                                                |
  |   Loop to STEP 2 <----------------------------------|
  |
  v
STEP 6: Sprint summary + PR
```

---

## 6. Compatibility with PLAN-hook-resilience.md

### Current Plan (4 Phases)

| Phase   | Title                                   | Status      | Still Needed?                                                                                                    |
| ------- | --------------------------------------- | ----------- | ---------------------------------------------------------------------------------------------------------------- |
| Phase 1 | Worktree Hook Isolation                 | In progress | YES -- fixes a real bug where worktree workers contaminate main state. Independent of orchestrator architecture. |
| Phase 2 | Hook Fail-Open Safety                   | Pending     | YES -- prevents agent freeze on malformed stdin. Independent of orchestrator architecture.                       |
| Phase 3 | State File Write Resilience             | Pending     | YES -- Windows os.replace() retry for atomic writes. Independent of orchestrator architecture.                   |
| Phase 4 | Orchestrator Context Refresh (Option D) | Pending     | PARTIALLY SUPERSEDED                                                                                             |

### Phase 4 Analysis

Phase 4 implements Option D (hybrid STEP 7 refresh + SessionStart hook enhancement). With the story-per-agent pattern:

**What becomes unnecessary**:

- STEP 7 context refresh -- the outer loop never accumulates enough context to need refreshing
- Step tracking in state file (`current_step`) -- the outer loop's steps are trivial; the story agent has its own fresh context

**What is still useful**:

- Enhanced SessionStart hook -- even with the lean outer loop, context compaction COULD theoretically fire (very long sprint, many parallel batches). The SessionStart hook providing state context is a cheap safety net.
- The prd.json reading in the SessionStart hook is useful regardless of orchestrator architecture.

**Recommendation**:

1. **Keep Phase 4 but SIMPLIFY it.** Instead of the full Option D, implement only the SessionStart hook enhancement (read prd.json, print remaining stories, print resume instructions). Skip the STEP 7 refresh and step tracking -- they are unnecessary with the story-per-agent pattern.

2. **Rename Phase 4** from "Orchestrator Context Refresh" to "SessionStart State Restore" to reflect the narrower scope.

3. **Add a Phase 5** (or a separate plan) for the story-per-agent pattern itself. This is a bigger change than the hook resilience work and should be its own plan.

### Suggested Plan Revision

```
Phase 1: Worktree Hook Isolation         -- UNCHANGED
Phase 2: Hook Fail-Open Safety           -- UNCHANGED
Phase 3: State File Write Resilience     -- UNCHANGED
Phase 4: SessionStart State Restore      -- SIMPLIFIED (drop STEP 7 refresh, drop step tracking)

Separate plan: Orchestrator Infinite Context
  Phase 1: Create ralph-story.md agent definition
  Phase 2: Rewrite ralph/SKILL.md as lean outer loop
  Phase 3: Proof-of-concept (run a 3-story sprint with story-per-agent)
  Phase 4: Add parallel dispatch support
  Phase 5: Add speed optimizations (graduated QA, incremental regression)
```

---

## 7. Recommendation

### Confidence Assessment

| Component               | Confidence  | Rationale                                                                                                                      |
| ----------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Story-per-agent pattern | HIGH        | Same pattern as workers, proven to work. Only question is 2-level nesting, which the platform supports.                        |
| Lean outer loop         | HIGH        | Pure simplification -- move complexity to story agent, keep outer loop thin.                                                   |
| Parallel dispatch       | MEDIUM-HIGH | Multi-agent dispatch is documented. Merge ordering solved by outer-loop serialization. Regression rollback is straightforward. |
| Graduated QA            | MEDIUM      | Requires defining "simple" vs "complex" -- the heuristic may not cover edge cases.                                             |
| Incremental regression  | MEDIUM      | Risk of missing cross-story breakage between regression checkpoints.                                                           |

### Implementation Path

**Phase A: Proof of Concept (do FIRST)**

Before committing to the full rewrite, validate the critical assumption: 2-level sub-agent nesting.

```
Test: Create a minimal "parent" agent that dispatches a "child" agent
  that dispatches a "grandchild" agent (isolation: worktree).
  The grandchild makes a change, commits, returns result.
  The child validates and merges.
  The parent receives the final result.
```

If this works, proceed. If it does not (Agent tool not available inside a sub-agent), fall back to Option D from the prior brainstorm.

Estimated effort: 30 minutes for manual test.

**Phase B: Story-Per-Agent Pattern (core value)**

1. Create `.claude/agents/ralph-story.md` -- port STEPs 4-6A from current SKILL.md
2. Rewrite `.claude/skills/ralph/SKILL.md` as lean outer loop
3. Update `.claude/agents/ralph-worker.md` -- remove self-imposed nesting restriction
4. Run a 3-4 story sprint using the new architecture
5. Validate: outer loop context stays under 20K tokens for entire sprint

Estimated effort: 2-3 hours (manual builder mode, not Ralph -- this IS the orchestrator code).

**Phase C: Parallel Dispatch (speed multiplier)**

1. Add `dependsOn` and `parallelGroup` to prd.json schema
2. Update `/plan` to detect independent stories and set parallel groups
3. Add parallel mode to outer loop (detect batch, dispatch simultaneously, merge sequentially)
4. Add regression rollback for parallel batch failures
5. Run a sprint with 2+ parallel stories

Estimated effort: 4-6 hours (can be a Ralph sprint once Phase B is proven).

**Phase D: Speed Optimizations (polish)**

1. Add `complexity` to prd.json schema
2. Implement graduated QA in qa_runner.py (--complexity flag)
3. Implement incremental regression (phase-boundary only)
4. Optimize worker dispatch prompt
5. Run timing comparison: before vs after

Estimated effort: One Ralph sprint (3-4 stories).

### What Can We Implement Now With High Confidence?

**Phase B (story-per-agent)** can be implemented immediately with high confidence. The pattern is identical to what workers already do. The only unknown (2-level nesting) can be validated in 30 minutes. The rewrite is mechanical -- moving protocol instructions from SKILL.md to ralph-story.md.

### What Needs a Proof-of-Concept First?

**2-level nesting (Phase A)**. This is a 30-minute test that gates everything. Do it before writing any code.

**Parallel dispatch (Phase C)**. Should be tested with a 2-story parallel batch before scaling up. The merge ordering is the tricky part.

### Migration Path

```
Current state:
  SKILL.md (348 lines) -> ralph-worker (isolation: worktree)

After Phase B:
  SKILL.md (100 lines) -> ralph-story (fresh context) -> ralph-worker (worktree)

After Phase C:
  SKILL.md (120 lines) -> ralph-story x N (parallel) -> ralph-worker x N (worktrees)
  + outer loop handles merge ordering for parallel mode

After Phase D:
  Same architecture + graduated QA + incremental regression
```

Each phase is independently valuable and backward-compatible. Phase B alone solves the infinite context problem. Phase C adds speed. Phase D polishes.

### Relationship to Existing Work

- **Phases 1-3 of PLAN-hook-resilience.md**: Proceed as planned. These fix real bugs independent of orchestrator architecture.
- **Phase 4 of PLAN-hook-resilience.md**: Simplify to SessionStart-only restore. The STEP 7 refresh and step tracking become unnecessary with story-per-agent.
- **Hooks simplification (ongoing)**: Continue. The \_lib.py split and dead code removal improve the codebase regardless of orchestrator architecture.

### Risk Summary

| Risk                                          | Likelihood                                      | Impact                         | Mitigation                                                 |
| --------------------------------------------- | ----------------------------------------------- | ------------------------------ | ---------------------------------------------------------- |
| 2-level nesting not supported                 | Low (platform docs suggest it works)            | Blocks everything              | Phase A proof-of-concept first                             |
| Story agent exceeds 200K context              | Very low (single story + 4 retries is ~50K max) | Story fails                    | maxTurns limit terminates agent; outer loop treats as FAIL |
| Parallel merge conflicts                      | Low (file overlap detection prevents it)        | One story fails merge          | git merge --abort, fallback to sequential                  |
| Outer loop still hits compaction              | Very low (100 lines SKILL + ~500 tokens/story)  | Outer loop confused            | SessionStart hook restores state                           |
| Story agent does not return structured result | Medium (agent may get confused)                 | Outer loop cannot parse result | Treat as FAIL, rollback to checkpoint                      |

---

## Sources

### Project Files Read

- `.claude/skills/ralph/SKILL.md` -- full orchestrator protocol (348 lines)
- `.claude/agents/ralph-worker.md` -- worker agent definition (153 lines)
- `.claude/hooks/post_compact_restore.py` -- SessionStart hook (49 lines)
- `.claude/hooks/_lib.py` -- state management, DEFAULT_WORKFLOW_STATE (referenced via PLAN.md)
- `.claude/settings.json` -- hook wiring configuration (59 lines)
- `.claude/prd.json` -- current sprint stories (234 lines, STORY-001 and STORY-002 passed)
- `.claude/skills/refresh/SKILL.md` -- manual context refresh skill (36 lines)
- `.claude/docs/PLAN.md` -- current hooks simplification plan (Phase 1-4)
- `.claude/docs/ARCHITECTURE.md` -- system architecture (216 lines)
- `.claude/docs/HANDOFF.md` -- last session state
- `PROJECT_BRIEF.md` -- project context

### Prior Brainstorms Referenced

- `2026-03-03-orchestrator-context-refresh.md` -- Options A-D analysis (full read, 668 lines)
- `2026-03-02-ralph-perfection-infinite-context.md` -- Ideas 1-10 (full read, 399 lines)
- `2026-03-02-hooks-simplification.md` -- \_lib.py analysis and build strategy (full read, 324 lines)
- `2026-03-01-context-window-optimization.md` -- context budget analysis (full read, 197 lines)
