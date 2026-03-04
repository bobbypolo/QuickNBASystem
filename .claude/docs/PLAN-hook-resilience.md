# PLAN: Hook Resilience & Orchestrator Infinite Context

## Goal

Fix 4 systemic bugs discovered during Ralph sprint operation AND redesign the orchestrator for true infinite context. Part A (Phases 1-4) fixes immediate bugs: worktree state contamination, hook stdin blocking, Windows write failures, and weak session restore. Part B (Phases 5-7) restructures Ralph into a story-per-agent architecture giving both the orchestrator and workers infinite context, plus parallel story dispatch for 2-3x throughput on parallelizable sprints. All changes are backward-compatible and additive. Further speed optimizations (graduated QA, incremental regression) are deferred to post-plan measurement — see Future Work.

## Execution Strategy

**Builder agent dispatch**: Each phase is implemented by a dedicated Builder sub-agent dispatched via `Agent tool` with `subagent_type: "Builder"`. The orchestrating conversation stays lean — it dispatches builders, collects results, runs verification, and moves to the next phase. This maximizes context for each builder (fresh 200K window per phase) and prevents the orchestrator from hitting compaction during a multi-phase implementation session.

```
Orchestrator (this conversation):
  For each phase:
    1. Dispatch Builder agent with phase instructions + file context
    2. Receive result (pass/fail, summary)
    3. Run full test suite to verify
    4. If pass: move to next phase
    5. If fail: re-dispatch with failure context
```

**Conflict avoidance**: A parallel Ralph sprint is running on branch `ralph/hooks-infrastructure-simplification` modifying: `qa_runner.py`, `test_lib_quality.py`, `test_qa_lib.py`, `test_qa_runner.py`, `settings.json`. None of these overlap with files in this plan.

## Source Brainstorms

- `.claude/docs/brainstorms/2026-03-03-worktree-hook-isolation.md`
- `.claude/docs/brainstorms/2026-03-03-hook-fail-open-safety.md`
- `.claude/docs/brainstorms/2026-03-03-state-file-race-safety.md`
- `.claude/docs/brainstorms/2026-03-03-orchestrator-context-refresh.md`
- `.claude/docs/brainstorms/2026-03-03-orchestrator-infinite-context-and-speed.md` (NEW — story-per-agent pattern, parallel dispatch, speed optimizations)

## System Context

### Files Read

| File                                                | Key Observations                                                                                                                                                                                                                                                  |
| --------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `.claude/hooks/_lib.py` (2,081 lines)               | Core state I/O: `read/write/update_workflow_state`, `write_marker`, `clear_marker`, `parse_hook_stdin`. `DEFAULT_WORKFLOW_STATE` at line 45. `write_marker` has no worktree guard. `parse_hook_stdin` has `fail_open` param. `write_workflow_state` has no retry. |
| `.claude/hooks/post_format.py` (98 lines)           | PostToolUse:Edit\|Write. Calls `write_marker(f"Modified: {file_path}")` without checking if path is in worktree. Uses `fail_open=False`.                                                                                                                          |
| `.claude/hooks/post_bash_capture.py` (80 lines)     | PostToolUse:Bash. Calls `clear_marker()` on test pass. Uses `fail_open=False`.                                                                                                                                                                                    |
| `.claude/hooks/pre_bash_guard.py` (98 lines)        | PreToolUse:Bash. Uses `fail_open=False`.                                                                                                                                                                                                                          |
| `.claude/hooks/post_write_prod_scan.py` (156 lines) | PostToolUse:Edit\|Write. Uses `fail_open=True`. Stateless (no state writes).                                                                                                                                                                                      |
| `.claude/hooks/stop_verify_gate.py` (87 lines)      | Stop hook. Uses `fail_open=True`. Reads `needs_verify` — blocks if worktree path leaked in.                                                                                                                                                                       |
| `.claude/hooks/post_compact_restore.py` (49 lines)  | SessionStart. Reads state, prints summary. No prd.json context restore for Ralph.                                                                                                                                                                                 |
| `.claude/skills/ralph/SKILL.md` (348 lines)         | Monolithic orchestrator. STEP 7 is a no-op for context. No `current_step` tracking. Accumulates ~6-8K tokens/story. Hits compaction at ~6 stories.                                                                                                                |
| `.claude/agents/ralph-worker.md` (153 lines)        | Self-contained worker. `isolation: worktree`, `maxTurns: 150`. Gets fresh context per dispatch. Contains self-imposed rule "Sub-agents cannot spawn sub-agents" (not a platform limitation).                                                                      |
| `.claude/settings.json` (59 lines)                  | All hooks hardcode `cd /c/Users/rober/Documents/'Claude Workflow'`.                                                                                                                                                                                               |

### Observed Bugs

The stop hook blocked the main orchestrator 6+ times in one session with:

```
Blocked: unverified code: Modified: C:\...\worktrees\agent-ad35199d\.claude\hooks\_lib.py
```

A dead worktree's edit bled into the main state. Had to manually clear `.workflow-state.json` each time.

### Key Discovery: 2-Level Agent Nesting

The Agent tool is available to ALL agent types including sub-agents. The line in `ralph-worker.md` ("Sub-agents cannot spawn sub-agents") is a self-imposed rule in the prompt text, NOT a platform limitation. This means a sub-agent CAN dispatch another sub-agent, enabling 3-level nesting:

```
User conversation → ralph-story-agent (fresh context) → ralph-worker (worktree isolation)
```

This unlocks the story-per-agent pattern — the same infinite context formula workers already use, applied to the orchestrator.

---

# PART A: Hook Resilience (Bug Fixes)

## Phase 1: Worktree Hook Isolation

**Priority**: CRITICAL — actively causing bugs during every Ralph sprint.

### Done When

- R-P1-01: `is_worktree_path(path)` returns True for paths containing `.claude/worktrees/` (Unix or Windows separators)
- R-P1-02: `write_marker()` silently skips writes when `source_path` is a worktree path
- R-P1-03: `stop_verify_gate.py` auto-clears stale worktree markers from state before blocking
- R-P1-04: All existing tests pass without modification

### Changes

| File                                             | Action                                                                                                                          | Test File                                        |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ |
| `.claude/hooks/_lib.py`                          | ADD `is_worktree_path()` function (~12 lines). MODIFY `write_marker()` to accept optional `source_path` param, skip if worktree | `.claude/hooks/tests/test_worktree_isolation.py` |
| `.claude/hooks/post_format.py`                   | MODIFY `set_verify_marker()` to pass `file_path` as `source_path` to `write_marker()`. ADD `is_worktree_path` to imports        | `.claude/hooks/tests/test_worktree_isolation.py` |
| `.claude/hooks/stop_verify_gate.py`              | ADD worktree marker sanitize check before blocking logic. ADD `is_worktree_path` to imports                                     | `.claude/hooks/tests/test_worktree_isolation.py` |
| `.claude/hooks/tests/test_worktree_isolation.py` | CREATE new test file with ~9 tests                                                                                              | —                                                |

### Interface Contracts

```python
# _lib.py — NEW
def is_worktree_path(path: str) -> bool:
    """Check if path is inside .claude/worktrees/. Handles Unix and Windows separators."""
    # Called By: write_marker(), stop_verify_gate.py
    # Returns: True if path contains worktree segment

# _lib.py — MODIFIED signature
def write_marker(content: str, source_path: str | None = None) -> None:
    """Write needs_verify. Skips if source_path is a worktree path."""
    # Called By: post_format.py set_verify_marker()
    # Calls: is_worktree_path(), update_workflow_state()
```

### Testing Strategy

| Test                                       | Type        | R-marker |
| ------------------------------------------ | ----------- | -------- |
| `test_unix_worktree_path_detected`         | unit        | R-P1-01  |
| `test_windows_worktree_path_detected`      | unit        | R-P1-01  |
| `test_main_project_path_not_detected`      | unit        | R-P1-01  |
| `test_empty_path_returns_false`            | unit        | R-P1-01  |
| `test_marker_content_string_detected`      | unit        | R-P1-01  |
| `test_write_marker_skips_worktree_source`  | unit        | R-P1-02  |
| `test_write_marker_writes_for_main_source` | unit        | R-P1-02  |
| `test_stop_gate_sanitizes_worktree_marker` | integration | R-P1-03  |
| `test_stop_gate_blocks_real_marker`        | integration | R-P1-03  |

### Verification Command

```bash
python -m pytest .claude/hooks/tests/test_worktree_isolation.py -v --tb=short && python -m pytest .claude/hooks/tests/ -v --tb=short -q
```

---

## Phase 2: Hook Fail-Open Safety

**Priority**: HIGH — prevents agent freeze on malformed stdin.

### Done When

- R-P2-01: `parse_hook_stdin()` has no `fail_open` parameter — always returns `{}` on parse failure
- R-P2-02: Parse failures produce an audit log entry via `audit_log("parse_hook_stdin", "parse_error", ...)`
- R-P2-03: All 5 callers updated to call `parse_hook_stdin()` with no arguments
- R-P2-04: Tests that previously asserted `exit 2` on malformed stdin now assert `exit 0`

### Changes

| File                                    | Action                                                                                                     | Test File                                          |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| `.claude/hooks/_lib.py`                 | MODIFY `parse_hook_stdin()`: remove `fail_open` param, always return `{}` on failure, add `audit_log` call | `.claude/hooks/tests/test_workflow_state.py`       |
| `.claude/hooks/pre_bash_guard.py`       | MODIFY: `parse_hook_stdin(fail_open=False)` → `parse_hook_stdin()`                                         | `.claude/hooks/tests/test_pre_bash_guard.py`       |
| `.claude/hooks/post_bash_capture.py`    | MODIFY: `parse_hook_stdin(fail_open=False)` → `parse_hook_stdin()`                                         | `.claude/hooks/tests/test_post_bash_capture.py`    |
| `.claude/hooks/post_format.py`          | MODIFY: `parse_hook_stdin(fail_open=False)` → `parse_hook_stdin()`                                         | `.claude/hooks/tests/test_post_format.py`          |
| `.claude/hooks/post_write_prod_scan.py` | MODIFY: `parse_hook_stdin(fail_open=True)` → `parse_hook_stdin()`                                          | `.claude/hooks/tests/test_post_write_prod_scan.py` |
| `.claude/hooks/stop_verify_gate.py`     | MODIFY: `parse_hook_stdin(fail_open=True)` → `parse_hook_stdin()`                                          | `.claude/hooks/tests/test_stop_verify_gate.py`     |

### Interface Contracts

```python
# _lib.py — MODIFIED signature
def parse_hook_stdin() -> dict:
    """Parse JSON from stdin. Returns {} on TTY, empty, or malformed input.
    Parse errors are logged to audit trail but never block."""
    # Called By: all 5 hook scripts
    # Calls: audit_log() on parse failure
```

### Testing Strategy

| Test                                                          | Type        | R-marker |
| ------------------------------------------------------------- | ----------- | -------- |
| `test_parse_hook_stdin_returns_empty_on_malformed`            | unit        | R-P2-01  |
| `test_parse_hook_stdin_logs_audit_on_failure`                 | unit        | R-P2-02  |
| `test_pre_bash_guard_malformed_stdin_allows`                  | integration | R-P2-03  |
| `test_post_bash_capture_malformed_stdin_allows`               | integration | R-P2-03  |
| `test_post_format_malformed_stdin_allows`                     | integration | R-P2-03  |
| Update existing `test_malformed_json_exits_2` → assert exit 0 | update      | R-P2-04  |

### Verification Command

```bash
python -m pytest .claude/hooks/tests/test_pre_bash_guard.py .claude/hooks/tests/test_post_bash_capture.py .claude/hooks/tests/test_post_format.py .claude/hooks/tests/test_post_write_prod_scan.py .claude/hooks/tests/test_stop_verify_gate.py -v --tb=short && python -m pytest .claude/hooks/tests/ -v --tb=short -q
```

---

## Phase 3: State File Write Resilience

**Priority**: MEDIUM — prevents silent state loss on Windows.

### Done When

- R-P3-01: `write_workflow_state()` retries `os.replace()` up to 3 times with 10ms/20ms backoff on `PermissionError`
- R-P3-02: Exhausted retries produce an audit log entry
- R-P3-03: Non-retryable errors (`OSError`, `TypeError`, `ValueError`) break immediately with audit log
- R-P3-04: Failed writes clean up the `.json.tmp` temp file (no stale temp files left on disk)
- R-P3-05: All existing tests pass without modification

### Changes

| File                    | Action                                                                                                        | Test File                                    |
| ----------------------- | ------------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| `.claude/hooks/_lib.py` | MODIFY `write_workflow_state()`: add retry loop with backoff on `PermissionError`, add `audit_log` on failure | `.claude/hooks/tests/test_workflow_state.py` |

### Interface Contracts

```python
# _lib.py — MODIFIED implementation (signature unchanged)
def write_workflow_state(state: dict) -> None:
    """Atomically write state. Retries up to 3x on PermissionError (Windows antivirus/indexer)."""
    # Called By: update_workflow_state(), clear_marker(), write_marker()
    # Calls: audit_log() on failure
```

### Testing Strategy

| Test                                          | Type | R-marker |
| --------------------------------------------- | ---- | -------- |
| `test_retry_on_permission_error`              | unit | R-P3-01  |
| `test_exhausted_retries_logs_audit`           | unit | R-P3-02  |
| `test_non_retryable_error_breaks_immediately` | unit | R-P3-03  |
| `test_failed_write_cleans_up_temp_file`       | unit | R-P3-04  |

### Verification Command

```bash
python -m pytest .claude/hooks/tests/test_workflow_state.py -v --tb=short && python -m pytest .claude/hooks/tests/ -v --tb=short -q
```

---

## Phase 4: SessionStart State Restore

**Priority**: MEDIUM — safety net for context compaction recovery.

**Note**: Simplified from original "Orchestrator Context Refresh" scope. The STEP 7 refresh and step tracking are unnecessary once the story-per-agent pattern (Phase 6) makes the outer loop thin enough to never hit compaction. This phase adds only the SessionStart hook enhancement — a cheap safety net that remains valuable regardless of orchestrator architecture.

### Done When

- R-P4-01: `post_compact_restore.py` detects active Ralph (`ralph_active=True` AND `current_story_id` is non-null) and prints full context restore (remaining stories, current story details, resume instructions)
- R-P4-02: `post_compact_restore.py` handles missing/corrupt prd.json gracefully (try/except, falls back to existing behavior)
- R-P4-03: `post_compact_restore.py` prints current story description and acceptance criteria when ralph_active=True
- R-P4-04: `post_compact_restore.py` skips context restore block when `current_story_id` is null (sprint not in progress — avoids confusing output on fresh sessions with stale Ralph state)
- R-P4-05: All existing tests pass without modification

### Changes

| File                                    | Action                                                                                                                                       | Test File                                          |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| `.claude/hooks/post_compact_restore.py` | ADD Ralph context restore block (~40 lines): read prd.json, display remaining stories, current story details, step-aware resume instructions | `.claude/hooks/tests/test_post_compact_restore.py` |

### Interface Contracts

```python
# post_compact_restore.py — NEW behavior when ralph_active=True
# Guard: only prints restore block when current_story_id is non-null
#   (null means sprint not in progress — skip to avoid stale output on fresh sessions)
# Reads: .claude/prd.json (stories array, acceptanceCriteria, gateCmds)
# Reads: .workflow-state.json (ralph.current_story_id, etc.)
# Prints: RALPH CONTEXT RESTORE block with:
#   - Story, Attempt, Skips, Branch
#   - Remaining stories (count + IDs)
#   - Current story description + acceptance criteria
#   - Resume instruction: "Re-read ralph/SKILL.md, continue from STEP 2"
```

### Testing Strategy

| Test                                        | Type        | R-marker |
| ------------------------------------------- | ----------- | -------- |
| `test_compact_restore_ralph_context`        | integration | R-P4-01  |
| `test_compact_restore_missing_prd`          | integration | R-P4-02  |
| `test_compact_restore_corrupt_prd`          | integration | R-P4-02  |
| `test_compact_restore_no_ralph`             | integration | R-P4-01  |
| `test_compact_restore_prints_story_details` | integration | R-P4-03  |
| `test_compact_restore_null_story_id_skips`  | integration | R-P4-04  |

### Verification Command

```bash
python -m pytest .claude/hooks/tests/test_post_compact_restore.py -v --tb=short && python -m pytest .claude/hooks/tests/ -v --tb=short -q
```

---

# PART B: Orchestrator Infinite Context & Speed

## Phase 5: Proof-of-Concept — 2-Level Agent Nesting

**Priority**: HIGH — gates all of Part B. Must validate before writing Phase 6-7 code.

### Context

The story-per-agent pattern requires 3-level nesting: `user conversation → ralph-story-agent → ralph-worker`. The Agent tool documentation says all tools (including Agent) are available to sub-agents, but this has not been tested in practice. This phase validates the assumption with a minimal test.

### Done When

- R-P5-01: A test script successfully dispatches a "parent" agent that dispatches a "child" agent with `isolation: worktree`
- R-P5-02: The child agent makes a file change, commits, and returns a structured result
- R-P5-03: The parent agent receives and parses the child's result, then returns its own structured result to the test
- R-P5-04: The test conversation (outermost layer) receives the parent's result containing the child's summary
- R-P5-05: Results documented in `.claude/docs/brainstorms/2026-03-03-nesting-poc-results.md`

### How to Test

This is a manual interactive test, not automated code. The orchestrator (this conversation) runs it directly:

1. Dispatch an Agent with `subagent_type: "general-purpose"` and a prompt instructing it to:
   - Create a temporary test file
   - Dispatch another Agent with `subagent_type: "general-purpose"` and `isolation: "worktree"` that:
     - Writes "hello from grandchild" to a file
     - Returns the text `CHILD_RESULT: {"message": "success"}`
   - Parse the child's result
   - Return `PARENT_RESULT: {"child_message": "success", "nesting_works": true}`
2. Parse the parent's result in this conversation
3. Document: did nesting work? Any errors? Latency?

### Verification

- If nesting works: proceed to Phase 6
- If nesting fails: fall back to Phase 4B (see Appendix A). Document the failure and update this plan.

---

## Phase 6: Story-Per-Agent Pattern

**Priority**: HIGH — the core infinite context solution.

**Depends on**: Phase 5 (nesting must be validated first)

### Architecture

Split Ralph into two layers:

```
User conversation (/ralph skill — LEAN OUTER LOOP, ~100 lines)
  |
  |-- STEP 1: Validate prd.json, init state
  |-- STEP 1.5: Feature branch setup
  |-- Loop:
  |     |-- STEP 2: Read state, find next story
  |     |-- STEP 3: Dispatch ralph-story-agent (Agent tool, fresh 200K context)
  |     |     |-- Reads prd.json, PLAN.md, progress.md
  |     |     |-- Checkpoint, plan check
  |     |     |-- Dispatch ralph-worker (worktree isolation)
  |     |     |-- Validate receipt, diff review, merge, regression
  |     |     |-- Retry loop (up to max_attempts internally)
  |     |     |-- Return RALPH_STORY_RESULT
  |     |-- STEP 4: Handle result (~500 tokens added to outer loop)
  |     |-- Circuit breaker check
  |-- STEP 5: Sprint summary + PR creation
```

**Why this works**: The outer loop NEVER accumulates story-level context. Each story agent gets a fresh 200K window. The outer loop only sees structured `RALPH_STORY_RESULT` summaries (~500 tokens/story). A 20-story sprint adds ~10K tokens to the outer loop — well within budget.

### Done When

- R-P6-01: `.claude/agents/ralph-story.md` exists with frontmatter (`maxTurns: 200`, `memory: user`, `model: inherit`, `permissionMode: acceptEdits`) and contains STEPs 4-6A logic from current SKILL.md
- R-P6-02: `ralph-story.md` dispatches `ralph-worker` via Agent tool and handles the `RALPH_WORKER_RESULT`
- R-P6-03: `ralph-story.md` returns structured `RALPH_STORY_RESULT` format with: `story_id`, `passed`, `skipped`, `attempts`, `summary`, `files_changed`, `verification_ref`, `failure_summary`
- R-P6-04: `ralph-story.md` handles retries internally (up to `max_attempts` worker dispatches within one story agent invocation)
- R-P6-05: `.claude/skills/ralph/SKILL.md` rewritten as lean outer loop (~100 lines): init, branch, find-next, dispatch-story-agent, handle-result, circuit-breaker, PR
- R-P6-06: SKILL.md outer loop dispatches `ralph-story` agent via `Agent tool` with `subagent_type: "ralph-story"`
- R-P6-07: `.claude/agents/ralph-worker.md` line "Sub-agents cannot spawn sub-agents" removed
- R-P6-08: Existing worker behavior is completely unchanged (only the nesting restriction line removed)

### Changes

| File                                    | Action                                                                                                                 | Test File                      |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- | ------------------------------ |
| `.claude/agents/ralph-story.md`         | CREATE new agent definition (~225 lines): STEPs 4-6A from current SKILL.md, worker dispatch, retry loop, result format | — (instruction file, no tests) |
| `.claude/skills/ralph/SKILL.md`         | MAJOR REWRITE: lean outer loop (~100 lines, down from 348). Steps: init, branch, find-next, dispatch, handle, PR       | — (instruction file, no tests) |
| `.claude/agents/ralph-worker.md`        | MINOR EDIT: remove line 26 ("Sub-agents cannot spawn sub-agents")                                                      | — (instruction file, no tests) |
| `.claude/hooks/post_compact_restore.py` | MINOR EDIT: update state summary to reference story-per-agent architecture                                             | existing tests cover           |

### Interface Contracts

```
# ralph-story.md — DISPATCH PROMPT from outer loop
## Story Assignment
Story ID: [story.id]
Phase: [story.phase]
Description: [story.description]
Feature Branch: [feature_branch]
Attempt: [current_attempt] of [max_attempts]
Prior Failure: [prior_failure_summary or "First attempt"]

### Acceptance Criteria
[List each ac.id: ac.criterion (ac.testType)]

### Gate Commands
unit: [gateCmds.unit]
integration: [gateCmds.integration]

# ralph-story.md — RETURN FORMAT
RALPH_STORY_RESULT:
{
  "story_id": "STORY-NNN",
  "passed": true/false,
  "skipped": true/false,
  "attempts": N,
  "summary": "What happened",
  "files_changed": ["list"],
  "verification_ref": "verification-log.jsonl",
  "failure_summary": "If failed, why"
}
```

### Key Design Decisions

1. **Retries inside story agent** (not outer loop): The story agent has 200K context budget — plenty for 4 worker retries at ~5K each. Keeps outer loop maximally thin.
2. **Story agent does NOT use worktree isolation**: It merges to the feature branch, so it must run in the same repo. Only workers use worktree isolation.
3. **Story agent reads files from disk**: prd.json, PLAN.md, progress.md are read by the story agent at startup. The dispatch prompt only needs story ID, branch name, attempt info.
4. **Outer loop error handling**: The outer loop wraps every Agent tool dispatch in error handling. ANY non-parseable story agent response — crash, timeout, malformed result, or Agent tool error — is treated as FAIL with `passed: false` and the raw error message as `failure_summary`. The outer loop rolls back to the git checkpoint and counts it as a failed attempt. This ensures no story agent failure mode can break the sprint loop.

### Verification

This phase produces instruction files (`.md`), not code. Verification is a manual integration test:

```
1. Run /ralph on a prd.json with 3+ unpassed stories
2. Observe: outer loop dispatches ralph-story-agent per story
3. Observe: story agent dispatches ralph-worker in worktree
4. Observe: outer loop context stays under 20K tokens for entire sprint
5. Observe: all stories process correctly (pass/fail/skip handled)
```

---

## Phase 7: Parallel Story Dispatch

**Priority**: MEDIUM — speed multiplier (2-3x for parallelizable sprints).

**Depends on**: Phase 6 (story-per-agent must be working first)

### Architecture

When multiple stories in the same phase have non-overlapping file changes, dispatch story agents simultaneously:

```
Outer loop detects 3 independent stories in Phase 2:
  STORY-003: Changes files A, B
  STORY-004: Changes files C, D
  STORY-005: Changes files E, F

  1. Record pre-batch checkpoint (git rev-parse HEAD)
  2. Dispatch 3 ralph-story-agents simultaneously (skip merge — return worktree branches)
  3. Collect all RALPH_STORY_RESULTs
  4. Merge results sequentially in outer loop (in story order)
     - If merge conflict: git merge --abort → go to step 6
  5. Run cumulative regression ONCE after all merges
     - If regression fails: go to step 6
  6. Rollback: git reset --hard [checkpoint], re-dispatch entire batch sequentially
```

### Done When

- R-P7-01: SKILL.md outer loop detects parallelizable stories (same phase, non-overlapping Changes Tables from PLAN.md)
- R-P7-02: Parallel mode dispatches multiple `ralph-story` agents simultaneously via multiple Agent tool calls
- R-P7-03: Story agents in parallel mode skip merge step and return `worktree_branch` in result
- R-P7-04: Outer loop merges parallel results sequentially (in story order) after all agents complete
- R-P7-05: Outer loop runs cumulative regression once after parallel batch merge
- R-P7-06: Merge conflict during sequential merge triggers `git merge --abort`, rollback to checkpoint, and sequential re-dispatch of the entire batch
- R-P7-07: Regression failure after all merges complete triggers `git reset --hard [checkpoint]` and sequential re-dispatch of the entire batch
- R-P7-08: `DEFAULT_WORKFLOW_STATE["ralph"]` includes `parallel_batch`, `parallel_checkpoint` fields

### Changes

| File                            | Action                                                                                                               | Test File                                    |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| `.claude/skills/ralph/SKILL.md` | ADD parallel batch detection logic to STEP 2. ADD STEP 3b (parallel dispatch). ADD parallel merge + regression logic | — (instruction file, no tests)               |
| `.claude/agents/ralph-story.md` | ADD `parallel_mode` flag support: when true, skip merge, return worktree_branch in result                            | — (instruction file, no tests)               |
| `.claude/hooks/_lib.py`         | MODIFY `DEFAULT_WORKFLOW_STATE`: add `parallel_batch`, `parallel_checkpoint` to ralph dict                           | `.claude/hooks/tests/test_workflow_state.py` |

### Interface Contracts

```
# Parallel mode dispatch (outer loop sends to story agent):
## Mode: parallel
Skip merge after validation. Return worktree_branch for outer loop to merge.

# Parallel RALPH_STORY_RESULT (additional field):
{
  ...existing fields...,
  "worktree_branch": "agent-xxxxx-story-003"  // only in parallel mode
}
```

### Testing Strategy

| Test                                          | Type        | R-marker                |
| --------------------------------------------- | ----------- | ----------------------- |
| `test_parallel_state_fields_in_default_state` | unit        | R-P7-08                 |
| Manual: 3-story parallel sprint               | integration | R-P7-01 through R-P7-07 |

### Verification

Manual integration test with a 3+ story sprint where stories are in the same phase with non-overlapping files. Observe parallel dispatch, sequential merge, single regression run.

---

## Risk Assessment

| Risk                                                                          | Impact     | Mitigation                                                                                                                           |
| ----------------------------------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Phase 1 `write_marker` signature change breaks existing callers               | Low        | Optional param with `None` default — backward-compatible                                                                             |
| Phase 2 removing fail-closed on pre_bash_guard lets dangerous command through | Very Low   | Every hook already handles empty dict via early-exit guards. Audit log makes failures visible. Claude Code itself has safety checks. |
| Phase 3 retry adds latency to hooks                                           | Negligible | Retry only on failure path. 10-30ms worst case, within 100ms hook budget.                                                            |
| Phase 4 SessionStart hook reads prd.json on every start                       | Negligible | Guarded by `if ralph_active`. Falls back on parse error.                                                                             |
| Phase 5 nesting doesn't work                                                  | HIGH       | **Gating test before Phase 6.** Fallback: Phase 4B (Appendix A) — implement Option D (STEP 7 refresh + step tracking).               |
| Phase 6 SKILL.md rewrite breaks Ralph                                         | Medium     | Keep old SKILL.md as `SKILL.md.bak`. New version is a simplification — fewer things can go wrong. Manual test with 3-story sprint.   |
| Phase 6 story agent crash/timeout/malformed result                            | Medium     | Outer loop wraps Agent dispatch in error handling. ANY non-parseable response = FAIL, rollback to checkpoint, counts as attempt.     |
| Phase 7 merge conflict during sequential merge                                | Low        | `git merge --abort`, rollback to checkpoint, re-dispatch entire batch sequentially. Separate from regression failure path.           |
| Phase 7 regression failure after parallel merge                               | Low        | `git reset --hard [checkpoint]`, re-dispatch entire batch sequentially. File overlap detection prevents most conflicts proactively.  |
| Concurrent changes to `_lib.py` across Part A phases                          | Low        | Each phase touches different sections: worktree detection, stdin parsing, state writing. No overlap.                                 |

## Dependency Graph

```
PART A (Bug Fixes) — all standalone, execute sequentially:
  Phase 1 (Worktree Isolation)     ← standalone
  Phase 2 (Fail-Open Safety)       ← standalone
  Phase 3 (Write Resilience)       ← standalone
  Phase 4 (SessionStart Restore)   ← standalone

PART B (Orchestrator Redesign) — sequential with gating:
  Phase 5 (Nesting PoC)           ← standalone, GATES Phase 6-7
  Phase 6 (Story-Per-Agent)       ← depends on Phase 5 success
  Phase 7 (Parallel Dispatch)     ← depends on Phase 6 working

Part A and Part B are independent — they can execute in any order.
All Part A phases touch hooks code. Part B touches agent/skill definitions.
No file conflicts between Part A and Part B.

Recommended execution order:
  Phase 1 → 2 → 3 → 4 (fix bugs first)
  Phase 5 (validate nesting — 30 min)
  Phase 6 (core rewrite — largest phase)
  Phase 7 (parallel — only after Phase 6 is proven)
```

---

## Appendix A: Phase 4B Fallback (If Nesting Fails)

**Trigger**: Phase 5 proves that 2-level agent nesting does not work. Phases 6-7 are cancelled.

**Purpose**: Strengthen Phase 4 to the full Option D from the orchestrator-context-refresh brainstorm. Instead of true infinite context via story-per-agent, this provides the best achievable mitigation within a single monolithic conversation: proactive refresh between stories + reactive restore after compaction + step tracking for resume accuracy.

### Additional Changes (on top of Phase 4)

| File                                    | Action                                                                                                                                                                            |
| --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `.claude/hooks/_lib.py`                 | ADD `current_step` (default: `""`) to `DEFAULT_WORKFLOW_STATE["ralph"]`                                                                                                           |
| `.claude/skills/ralph/SKILL.md`         | ADD step tracking writes to STEPs 2, 4, 5, 6, 7 (e.g., `update_workflow_state(ralph={"current_step": "STEP_5_DISPATCH"})`)                                                        |
| `.claude/skills/ralph/SKILL.md`         | REWRITE STEP 7 with Context Refresh Protocol: re-read `.workflow-state.json` + `prd.json`, display structured refresh summary (stories passed/remaining, next story, branch)      |
| `.claude/hooks/post_compact_restore.py` | ENHANCE with step-aware resume: read `current_step` from state, print specific resume instructions (e.g., "Resume from STEP_6_HANDLE_RESULT — check if worker result is pending") |

### Additional R-markers

- R-P4B-01: `DEFAULT_WORKFLOW_STATE["ralph"]` includes `current_step` field (default: `""`)
- R-P4B-02: SKILL.md STEP 7 includes context refresh protocol (re-reads state + prd.json, prints structured summary)
- R-P4B-03: STEPs 2, 4, 5, 6, 7 each write `current_step` to state via `update_workflow_state`
- R-P4B-04: `post_compact_restore.py` prints step-aware resume instructions when `current_step` is non-empty
- R-P4B-05: Context refresh at STEP 7 adds less than 2K tokens per story cycle

### Reference

Full specification: `.claude/docs/brainstorms/2026-03-03-orchestrator-context-refresh.md`, Option D section (lines 322-460).

---

## Future Work (Post-Plan)

The following optimizations were identified in the brainstorms but intentionally deferred. They should be measured and implemented only after Phases 1-7 are complete and real-world performance data is available:

- **Graduated QA**: Skip full QA pipeline for early stories in a sprint, full QA only for final stories
- **Incremental regression**: Run only tests affected by changed files, not full suite
- **Optimized diff review**: Reduce 5-question review to 3 targeted checks
- **Worker context optimization**: Pre-cache file contents in dispatch prompt to reduce worker disk reads
- **Pre-flight file caching**: Story agent reads and inlines file contents before dispatching worker

Reference: `.claude/docs/brainstorms/2026-03-03-orchestrator-infinite-context-and-speed.md`, Section 4.
