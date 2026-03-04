# Brainstorm: Ralph Loop Perfection + Infinite Context for All Projects

**Date**: 2026-03-02
**Problem**: Make the Claude Workflow / Ralph loop completely perfect, solid, and ready to serve as the standard infinite-context orchestration layer for all large-scale work projects — including parallel sub-agent execution for maximum efficiency.

## Current State Assessment

### What's Working Well

- Ralph v3 loop: 2/2 stories passed in last sprint, full QA verification, PR created
- Worktree isolation: failed work never touches feature branch
- 12-step QA pipeline: automated, produces structured JSON receipts
- Sprint state persistence: `.workflow-state.json` survives context compaction
- Feature branch workflow: `ralph/{plan-name}`, `--no-ff` merge, selective staging
- Cumulative regression gate: catches cross-story breakage
- Circuit breaker: 3 consecutive skips stops sprint
- Plan-PRD sync check: R-marker drift detection prevents stale stories
- Diff review gate (STEP 6): 5 structured questions catch scope creep

### Known Bugs

1. **criteria_verified semantic issue** in qa_runner.py: `criteria_verified` always includes all criteria IDs regardless of Step 11 result. Should only include actually-verified criteria.
2. **qa_receipt.overall=FAIL override**: STORY-002 worker returned `passed: true` but `qa_receipt.overall: "FAIL"` due to pre-existing issues. Ralph had to override with judgment — the strict validation says reject but causes are all pre-existing.
3. **Stash consumed by worker**: Git stashes are shared across worktrees. Auto-stash before STORY-001 was popped by the worker in the worktree. Untracked files lost from main working directory.

### Document Overlap (from prior analysis)

- CLAUDE.md <-> WORKFLOW.md: ~35% overlap (hook tables, QA steps, production standards)
- WORKFLOW.md <-> architect.md: planning sections duplicated
- ARCHITECTURE.md <-> CLAUDE.md: file organization, data flow
- code-quality.md <-> CLAUDE.md: production standards

### Anti-Gaming Gaps (from audit)

- 90 weak assertion tests across 10 files (isinstance, len>0, truthiness)
- Current PLAN.md is Anti-Gaming Enforcement v2 — partially implemented (STORY-003 merged)
- Diff review Q1/Q2 rely on LLM judgment, not deterministic parsing

---

## Ideas

### 1. Fix Known Bugs (P0 — Must Fix Before Next Sprint)

**Description**: Fix the three known bugs before running any more Ralph sprints.

**a. criteria_verified semantic fix**: In `qa_runner.py`, Step 11 (`_step_acceptance_tests`) should only add criteria IDs to `criteria_verified` when they actually pass. Currently the field is populated from prd.json regardless. Fix: only populate `criteria_verified` with IDs whose tests are found and pass.

**b. qa_receipt strict vs pragmatic validation**: Add a "pre-existing exception" path in Ralph STEP 6. If `qa_receipt.overall` is FAIL but ALL failing steps are flagged as `pre_existing: true` (i.e., failures exist in unchanged files from before this story), allow the PASS with a documented override. This is a policy decision — codify it rather than ad-hoc overriding.

**c. Stash isolation**: Replace `git stash push` with a copy-based approach. Before dispatching workers, copy dirty files to a temp directory instead of stashing. Workers in worktrees can't accidentally consume the backup. Alternatively, stash with `--include-untracked` and immediately `git stash pop` before worker dispatch (since worker gets its own worktree, the main tree doesn't need to be clean).

- **Pros**: Eliminates known failure modes. Makes next sprint reliable. Low risk — targeted fixes.
- **Cons**: Small scope, not flashy. The stash fix needs careful testing with worktree lifecycle.

---

### 2. Document Consolidation (Context Efficiency)

**Description**: Reduce context bloat by deduplicating overlapping documents. Three targeted consolidations:

**a. CLAUDE.md as machine-only instructions (~3K tokens → ~2K tokens)**: Remove all content that duplicates WORKFLOW.md (user tutorial content) or ARCHITECTURE.md (file organization). Keep only: Quick Start pointers, Role Commands, Hooks table (condensed), Production Standards (3 judgment rules + hook ref), Data Classification, Non-Negotiables, Precedence Rules, Git Workflow. Target: under 200 lines.

**b. WORKFLOW.md dedup pass**: Already reduced from 372→311 lines. Further opportunities: remove QA Pipeline table (duplicates qa_runner.py help output and ARCHITECTURE.md), remove Ralph detailed behavior section (duplicates SKILL.md, already cross-referenced).

**c. code-quality.md consolidation**: Rules in `.claude/rules/code-quality.md` overlap with CLAUDE.md Production Standards. Merge into one authoritative source. code-quality.md is path-triggered (only loads when code files are touched), so it should contain only the delta beyond CLAUDE.md.

**Estimated savings**: ~1,500-2,000 tokens from always-loaded context.

- **Pros**: Less context waste. Fewer conflicting instructions. Easier maintenance.
- **Cons**: Risk of accidentally removing something Claude needs. Two-file maintenance.

---

### 3. Parallel Sub-Agent Execution in Ralph

**Description**: When a plan identifies independent stories (no shared files, no data flow dependencies), dispatch multiple ralph-workers simultaneously instead of sequentially.

**How it works today vs proposed**:

```
CURRENT (sequential):
  STORY-001 → worker → merge → STORY-002 → worker → merge → STORY-003

PROPOSED (parallel where safe):
  STORY-001 → worker ─┐
  STORY-002 → worker ─┤→ collect results → merge in order → regression
  STORY-003 → worker ─┘
  STORY-004 (depends on 1-3) → sequential from here
```

**Implementation approach**:

1. **Dependency analysis in /plan**: Add `dependsOn` field to prd.json stories. `/plan` Step 7 analyzes which stories are independent (no shared files in Changes Tables) and sets dependencies.

2. **Parallel dispatch in STEP 5**: When multiple stories have no unresolved dependencies, dispatch all their workers simultaneously using multiple `Agent` tool calls in a single message. Each worker gets its own worktree (already supported by `isolation: worktree`).

3. **Parallel result collection in STEP 6**: Wait for all dispatched workers to return. Process results in story order (maintain deterministic merge order).

4. **Sequential merge**: Even though workers run in parallel, merge results one at a time to the feature branch (prevents merge conflicts). Run cumulative regression after each merge.

**Claude Code support**: The official sub-agents docs confirm: "spawn multiple subagents to work simultaneously" and "each subagent runs in its own context window." Multiple `Agent()` calls in one message triggers parallel execution. Worktree isolation means workers can't conflict on files.

**prd.json schema extension**:

```json
{
  "id": "STORY-003",
  "dependsOn": ["STORY-001"],
  "parallelGroup": 2,
  ...
}
```

Stories in the same `parallelGroup` with all dependencies met can run simultaneously.

- **Pros**: 2-3x faster for sprints with independent stories. No new infrastructure — uses existing worktree isolation. Deterministic merge order preserves safety. Workers can't conflict (separate worktrees, separate files).
- **Cons**: Dependency analysis must be accurate — wrong deps = merge conflicts. Parallel workers consume more API tokens simultaneously. Ralph's context receives multiple results at once (larger payloads). Requires careful handling if one parallel worker fails (others already running).

---

### 4. Agent Teams Integration (Experimental Alternative)

**Description**: Claude Code now has an experimental "Agent Teams" feature where multiple Claude Code instances work in parallel with shared task lists and inter-agent messaging. This could replace or supplement the Ralph parallel dispatch from Idea 3.

**Key differences from sub-agents**:

- Agent Teams: each teammate is a full Claude Code session with its own context window. Teammates can message each other and share a task list.
- Sub-agents: worker reports back to parent only. No inter-agent communication.

**For Ralph**: Agent Teams would allow workers to share discoveries (e.g., "Module A found a pattern useful for Module B"). But Ralph's current model — isolated workers that report structured results — is simpler and more deterministic.

**Assessment**: Agent Teams are experimental with known limitations (no session resumption, task status can lag, split panes need tmux). Ralph's sub-agent model is production-ready and sufficient. The structured receipt validation + diff review gate provides stronger quality control than team coordination.

- **Pros**: Full parallel sessions. Inter-agent communication. Shared task board.
- **Cons**: Experimental with documented bugs. Higher token cost. Coordination overhead. Less deterministic than structured receipt flow. No worktree isolation by default. Overkill for Ralph's needs — workers don't need to communicate.

---

### 5. Complete Anti-Gaming Enforcement Plan

**Description**: The current PLAN.md (Anti-Gaming Enforcement v2) has 3 phases. Phase 1 (Context + Assertion Hardening) and Phase 3 (Diff Review Gate) are done. Phase 2 (Diff-Line Coverage + Call-Graph Wiring) remains. Complete it to close the anti-gaming gaps.

**What's left from Phase 2**:

- `check_diff_line_coverage()` in `_lib.py` — parse coverage.json, compute coverage on changed lines only
- `check_call_graph_wiring()` in `_lib.py` — AST-based orphan function detection
- Enhanced `_step_coverage()` (Step 8) — run diff-line coverage after existing coverage command
- Enhanced `_step_plan_conformance()` (Step 10) — add call-graph wiring sub-check
- Tests for all new functions

**Additionally**: Fix the 90 weak assertion tests flagged by the audit. These are pre-existing but should be hardened.

- **Pros**: Closes the biggest anti-gaming gaps. Catches unwired code and uncovered changes. Makes QA pipeline genuinely hard to game.
- **Cons**: The 90 weak assertion fixes are tedious. Phase 2 is code-heavy (new \_lib.py functions + qa_runner.py changes). Could be its own Ralph sprint.

---

### 6. Ralph SKILL.md Optimization (Context Efficiency)

**Description**: ralph/SKILL.md is ~17K bytes (~5K tokens), loaded every time `/ralph` runs. Compress without losing functionality.

**Specific reductions**:

- Display template blocks (ASCII-bordered sections): remove exact formatting — LLM can produce readable output without templates (~800 bytes saved)
- Error Recovery table: compress to inline references (~400 bytes saved)
- STEP 6 receipt validation sub-steps: condense from ~40 lines to ~15 lines with a checklist format (~600 bytes saved)
- Inline JSON examples: reference qa_runner.py output format instead of repeating (~500 bytes saved)
- Sprint state JSON example: reference workflow-state.json schema instead of inlining (~300 bytes saved)

**Estimated savings**: 2,500-3,000 bytes (~700-850 tokens).

- **Pros**: Meaningful token savings on the most-used skill. Less instruction noise for the LLM.
- **Cons**: Risk of under-specifying behavior. The verbose format was intentional for deterministic execution. Must test compressed version produces identical behavior.

---

### 7. \_lib.py Modularization (Maintenance Efficiency)

**Description**: `_lib.py` is 1,851 lines. When workers or hooks need to modify it, the entire file must be read. Split into focused modules:

```
_lib.py (facade, ~50 lines, re-exports all symbols)
├── _lib_core.py      (~200 lines: paths, state, stdin, audit log)
├── _lib_violations.py (~300 lines: PROD_VIOLATION_PATTERNS, scan_file_violations)
├── _lib_quality.py    (~300 lines: scan_test_quality, assertion analysis)
├── _lib_traceability.py (~300 lines: R-markers, plan parsing, coverage)
└── _lib_plan.py       (~200 lines: check_plan_prd_sync, parse_plan_changes)
```

- **Pros**: Workers read only the module they need. Cleaner separation of concerns. Easier testing.
- **Cons**: Migration complexity. All hooks import from `_lib` — need backward-compatible re-exports. Risk of circular imports. More files to maintain.

---

### 8. Infinite Context Architecture (Ralph as Standard for All Projects)

**Description**: Formalize Ralph as the standard workflow for ALL non-trivial work across any project using the ADE. Document when to use Ralph vs Manual Mode, and how Ralph's infinite context property works.

**Infinite context mechanism**:

```
Ralph orchestrator (Session context)
  ├── STEP 2: Re-read state from disk (survives compaction)
  ├── STEP 5: Dispatch worker in worktree (worker has fresh 200K context)
  ├── STEP 6: Only result summary returns (not full worker context)
  ├── STEP 7: Cleanup, loop
  └── If orchestrator compacts: state file + progress.md preserve everything
```

Each worker gets a fresh context window. Only structured results return to the orchestrator. The orchestrator's context grows linearly with story count (just summaries), not with implementation complexity. For a 20-story sprint, the orchestrator uses ~40K tokens of summaries + state, leaving ~160K for orchestration logic.

**When to use Ralph vs Manual**:
| Scenario | Mode | Why |
|---|---|---|
| Feature with 3+ acceptance criteria | Ralph | Structured stories, TDD, verification |
| Bug fix (single file, clear cause) | Manual | Ralph overhead not worth it |
| Exploration / research | Manual (/brainstorm) | No acceptance criteria to verify |
| Refactoring (many files, clear pattern) | Ralph | Verification crucial for refactoring |
| Documentation-only changes | Manual | No code to test |
| Plan creation itself | Manual (/plan) | /plan is the prerequisite to Ralph |

**For deployment to other projects**: The ADE deployment scripts (`new-ade.ps1`, `update-ade.ps1`) already copy all Ralph infrastructure. Any project using the ADE gets Ralph for free.

- **Pros**: Clear guidance on when to use what. Formalizes infinite context as an architectural property. Makes Ralph the default, not an option.
- **Cons**: Cultural shift — users must plan before building. Ralph requires prd.json, which requires /plan. Quick fixes feel heavy.

---

### 9. Pre-Existing Failure Policy (Codify the Override)

**Description**: During STORY-002, Ralph had to override strict qa_receipt validation because failures were pre-existing (weak assertions in unchanged files, blast radius WARN). This should be a codified policy, not an ad-hoc decision.

**Proposed policy**: Add to STEP 6 receipt validation:

```
1e. Pre-Existing Exception:
  If qa_receipt.overall is FAIL:
    - For each failing step, check if ALL violations are in files NOT in result.files_changed
    - If ALL failures are pre-existing (untouched files): override to PASS with documented evidence
    - Log: "Pre-existing override: Step [N] failures are in unchanged files [list]"
    - If ANY failure is in a changed file: treat as genuine FAIL
```

This also applies to Precedence Rule 3 (blast radius WARN not FAIL) — codify it in the receipt validation logic rather than relying on Ralph's judgment.

- **Pros**: Eliminates ad-hoc overrides. Deterministic policy. Won't block stories for pre-existing tech debt.
- **Cons**: Could mask real issues if the pre-existing check is too lenient. Must be very precise about "unchanged files" — a file that was formatted but not logically changed should still count as unchanged.

---

### 10. Stash-Free Dirty Tree Handling

**Description**: Replace git stash with a simpler approach that doesn't interact with worktree lifecycle.

**Option A: Commit-based checkpoint**: Instead of stashing, create a temporary commit: `git commit -am "ralph-checkpoint-[story-id]"`. After sprint, `git reset --soft HEAD~1` to undo. Workers in worktrees branch from this commit and never see uncommitted changes.

**Option B: Just don't allow dirty trees**: Require clean working tree before `/ralph`. If dirty, ask user to commit or stash manually. Simpler, no magic.

**Option C: Copy-based backup**: Copy modified files to `.claude/temp/pre-ralph-backup/`. Restore after sprint. Workers never see these files (worktrees get clean copy).

- **Pros**: Eliminates stash-worktree interaction bug entirely. Any option is simpler than current stash approach.
- **Cons**: Option A risks leaving a temp commit if Ralph crashes. Option B is less convenient. Option C adds file management complexity.

---

## Recommendation

**Phase 1: Critical Fixes (do immediately, before next sprint)**

1. **Fix criteria_verified bug** (Idea 1a) — targeted fix in qa_runner.py
2. **Codify pre-existing override policy** (Idea 9) — add to STEP 6 in SKILL.md
3. **Replace stash with clean-tree requirement** (Idea 10, Option B) — simplest and safest

**Phase 2: Ralph Perfection (next Ralph sprint)**

4. **Parallel sub-agent execution** (Idea 3) — the biggest efficiency gain. Add `dependsOn` to prd.json, parallel dispatch in STEP 5, sequential merge in STEP 6
5. **Complete Anti-Gaming Phase 2** (Idea 5) — diff-line coverage + call-graph wiring

**Phase 3: Context Optimization (subsequent sprint)**

6. **Document consolidation** (Idea 2) — CLAUDE.md trim, WORKFLOW.md dedup, code-quality merge
7. **Ralph SKILL.md optimization** (Idea 6) — compress from ~5K to ~4K tokens
8. **\_lib.py modularization** (Idea 7) — split into focused modules

**Defer:**

- **Agent Teams** (Idea 4) — experimental, not needed. Sub-agent parallel dispatch (Idea 3) is simpler and production-ready
- **Infinite Context Architecture docs** (Idea 8) — update docs AFTER implementing parallel dispatch. The architecture section should reflect the actual capability

### Why This Order

1. **Bugs first**: Running more sprints on known bugs compounds problems
2. **Parallel dispatch next**: It's the single biggest productivity multiplier (2-3x faster sprints). It uses existing infrastructure (worktrees, sub-agents) and doesn't require the experimental Agent Teams feature
3. **Context optimization last**: Important but lower urgency — the current context budget works, it just wastes some tokens

### On Parallel Agents: Sub-Agents vs Agent Teams

**Use sub-agents (Idea 3), not Agent Teams (Idea 4).** Here's why:

- Ralph workers are **fire-and-forget** — they don't need to communicate with each other
- Sub-agents with worktree isolation already provide **safe parallel execution**
- The structured receipt validation + diff review gate provides **stronger quality control** than team coordination
- Sub-agents are **production-ready**; Agent Teams are **experimental with known bugs**
- Ralph's sequential merge pattern prevents **merge conflicts** regardless of parallel execution

Agent Teams would be valuable if workers needed to share discoveries mid-sprint. For Ralph's use case (independent stories, structured results), sub-agents are the right tool.

## Sources

### Project Docs Read

- `PROJECT_BRIEF.md`, `ARCHITECTURE.md`, `PLAN.md`, `HANDOFF.md`
- `knowledge/lessons.md`, `decisions/` (template + README)
- `ralph/SKILL.md` (full orchestrator spec)
- `ralph-worker.md` (worker agent spec)
- `workflow.json` (test commands, qa_runner config)
- `WORKFLOW.md` (user guide)
- `_lib.py` (header + constants)
- `qa_runner.py` (header + imports)
- All 11 brainstorm files
- `.claude/prd.json` (current stories, both passed)
- `.claude/.workflow-state.json` (current state)
- `verification-log.md`, `progress.md` (sprint history)

### External Research

- [Claude Code Sub-Agents Documentation](https://code.claude.com/docs/en/sub-agents) — parallel dispatch, worktree isolation, permission modes, persistent memory
- [Claude Code Agent Teams Documentation](https://code.claude.com/docs/en/agent-teams) — experimental, shared task list, inter-agent messaging, limitations
- [Claude Code multiple agent systems guide](https://www.eesel.ai/blog/claude-code-multiple-agent-systems-complete-2026-guide)
- [Claude Code parallel sub-agent best practices](https://claudefa.st/blog/guide/agents/sub-agent-best-practices)

---

## Build Strategy

### Module Dependencies

```
Phase 1 (Critical Fixes):
  criteria_verified fix (qa_runner.py) ── standalone
  pre-existing override policy (SKILL.md) ── standalone
  clean-tree requirement (SKILL.md) ── standalone
  (All three are independent, can be done in parallel)

Phase 2 (Ralph Perfection):
  prd.json schema extension (dependsOn field) ← must be first
    ↓
  /plan Step 7 dependency analysis ← depends on schema
    ↓
  STEP 5 parallel dispatch ← depends on schema + /plan
    ↓
  STEP 6 parallel result collection ← depends on STEP 5
    ↓
  Anti-gaming Phase 2 (_lib.py + qa_runner.py) ← independent of parallel work

Phase 3 (Context Optimization):
  Document consolidation ── independent
  SKILL.md optimization ── independent
  _lib.py modularization ── depends on anti-gaming being complete
```

### Build Order

**Phase 1** (3 independent fixes — Ralph sprint with parallel dispatch NOT yet available):

1. Fix criteria_verified in qa_runner.py
2. Add pre-existing override policy to SKILL.md STEP 6
3. Replace stash with clean-tree requirement in SKILL.md STEP 4

**Phase 2** (sequential — each depends on prior): 4. Extend prd.json schema with `dependsOn` and `parallelGroup` 5. Update /plan Step 7 to analyze dependencies and set groups 6. Implement parallel dispatch in Ralph STEP 5 7. Implement parallel result collection in Ralph STEP 6 8. Complete anti-gaming Phase 2 (diff coverage + call-graph wiring)

**Phase 3** (independent — can parallelize after Phase 2 delivers parallel dispatch): 9. CLAUDE.md trim + WORKFLOW.md dedup 10. Ralph SKILL.md compression 11. \_lib.py modularization

### Testing Pyramid

- **Unit tests (70%)**: criteria_verified fix, pre-existing override logic, dependency analysis, parallel dispatch simulation (mock Agent calls), diff coverage, call-graph wiring
- **Integration tests (20%)**: Full QA pipeline with pre-existing failures, parallel dispatch with 2-3 mock workers returning structured results, prd.json schema validation with dependsOn
- **E2E tests (10%)**: Full Ralph sprint on a 3-story plan with 2 parallel stories — verify stories execute in parallel, merge in order, regression passes

### Risk Mitigation Mapping

| Risk                                        | Mitigation                                                               |
| ------------------------------------------- | ------------------------------------------------------------------------ |
| Parallel workers touch same file            | Dependency analysis in /plan prevents it; sequential merge catches it    |
| Parallel dispatch overwhelms API            | Rate limiting at dispatch level; max 3 parallel workers                  |
| Pre-existing override too lenient           | Strict file-change check: only override for genuinely untouched files    |
| criteria_verified fix breaks existing tests | Fix is additive — only changes when IDs are NOT added, not when they are |
| \_lib.py modularization breaks imports      | Keep `_lib.py` as re-export facade; run full test suite before/after     |
| SKILL.md compression loses behavior         | A/B test: run same story with old vs new SKILL.md, compare results       |

### Recommended Build Mode

**Phase 1: Ralph Mode** — 3 clear stories with testable acceptance criteria. Can run as a quick sprint (all fixes are in existing files with existing tests). This is the right time to run Ralph because we fix the bugs FIRST, then use the fixed Ralph for subsequent phases.

**Phase 2: Ralph Mode** — 5 stories with clear dependencies. The parallel dispatch stories should themselves be built sequentially (ironic but necessary — you need parallel dispatch working before you can USE parallel dispatch). Anti-gaming is independent and can be a parallel story once Phase 2's dispatch is ready.

**Phase 3: Ralph Mode with parallel dispatch** — 3 independent stories that can finally USE the parallel dispatch feature built in Phase 2. This is the proof-of-concept for the parallel architecture.
