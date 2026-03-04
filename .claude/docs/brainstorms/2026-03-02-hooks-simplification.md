# Brainstorm: Hooks Infrastructure Simplification

**Date**: 2026-03-02
**Problem**: The workflow hooks infrastructure has grown to 4,152 lines of hook code + 10,743 lines of tests, but the core value (format on save, block dangerous commands, verify before stop) could be delivered in ~500 lines — the rest supports QA pipeline features that fire infrequently.

## Current State (by the numbers)

| Component           | Lines      | Purpose                                                                                                                  |
| ------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------ |
| `_lib.py`           | 2,081      | Monolith: state, scanning, plan validation, test quality, R-markers, coverage, call-graph                                |
| `qa_runner.py`      | 1,281      | 12-step QA pipeline orchestrator                                                                                         |
| 6 hook scripts      | 602        | `pre_bash_guard`, `post_format`, `post_bash_capture`, `post_write_prod_scan`, `stop_verify_gate`, `post_compact_restore` |
| `test_quality.py`   | 112        | CLI wrapper around qa_runner                                                                                             |
| `plan_validator.py` | 76         | CLI wrapper around \_lib                                                                                                 |
| **Hook code total** | **4,152**  |                                                                                                                          |
| 14 test files       | 10,743     | 2.6x the code they test                                                                                                  |
| **Grand total**     | **14,895** |                                                                                                                          |

### What \_lib.py actually contains (functional breakdown)

| Category                                                   | Lines | Used by                             |
| ---------------------------------------------------------- | ----- | ----------------------------------- |
| Core hook utilities (state, stdin, config, audit, markers) | ~365  | All 6 hooks                         |
| Production violation scanning (patterns + file scan)       | ~195  | `post_write_prod_scan`, `qa_runner` |
| Test quality analysis (scan, negative tests, API coverage) | ~340  | `qa_runner`, `test_quality`         |
| R-marker validation                                        | ~130  | `qa_runner`                         |
| Plan quality validation (5 checks, helpers)                | ~250  | `plan_validator`                    |
| Plan sync utilities (hash, R-marker drift)                 | ~85   | `qa_runner`                         |
| Story file coverage gate                                   | ~105  | `qa_runner`                         |
| Diff-line coverage gate                                    | ~65   | `qa_runner`                         |
| Call-graph wiring check (AST-based)                        | ~150  | `qa_runner`                         |
| Legacy migration (dead code)                               | ~50   | Nobody (migration complete)         |
| Constants, regexes, type defs                              | ~346  | Various                             |

**Key insight**: Only ~365 lines of `_lib.py` are used by the always-on hooks. The remaining ~1,716 lines exist solely to support `qa_runner.py` and `plan_validator.py` — which only run when you explicitly invoke `/verify` or Ralph.

## Ideas

### 1. Two-Tier Split: Hot Path vs QA Engine

Split the infrastructure into two layers:

- **Hot path** (`_lib.py` → stays small): State management, stdin parsing, config loading, audit logging, formatter execution, marker I/O. Used by all 6 always-on hooks. Target: ~400 lines.
- **QA engine** (new `_qa_lib.py`): Test quality scanning, R-marker validation, plan quality validation, plan sync, coverage checks, call-graph wiring, story file coverage. Used only by `qa_runner.py`, `test_quality.py`, and `plan_validator.py`. Target: ~1,200 lines.

Production violation scanning stays in `_lib.py` since `post_write_prod_scan.py` (always-on) uses it.

- **Pros**: Clean separation of hot-path vs cold-path. No behavior change. Every hook still works identically. Reduced import time for hot-path hooks (no AST import, no regex compilation for plan validation).
- **Cons**: Two files to maintain instead of one. Some shared constants (CODE_EXTENSIONS) need to be importable from both.

### 2. Delete Dead Code + Unnecessary State Tracking

Remove code that serves no current purpose:

- `migrate_legacy_markers()` (~50 lines) — migration is complete, legacy files deleted
- `PROD_VIOLATIONS_PATH` constant — references a file that no longer exists
- `_LEGACY_RALPH_STATE_PATH` — already removed in polish sprint (verify)
- Error history rotation in `post_bash_capture.py` — keep only `last_error.json`, drop `error_history.jsonl` and the 50-line rotation logic
- `read_prod_violations()` legacy string format handling — only dict format exists now

- **Pros**: Pure deletion — zero risk to behavior. Reduces `_lib.py` by ~80 lines. Removes dead test code too.
- **Cons**: Minimal impact on its own. More of a hygiene pass.

### 3. Simplify Production Violation Tracking (Stateless Scan)

Replace the stateful per-file violation registry (`set_file_violations`, `remove_file_violations`, `read_prod_violations`) with a stateless approach:

- `post_write_prod_scan.py` scans the file, prints warnings/blocks, but does NOT write to `.workflow-state.json`
- `stop_verify_gate.py` checks only `needs_verify` (not `prod_violations`)
- If you want a prod scan at stop time, run `/verify` which does a full scan

This eliminates: `set_file_violations()`, `remove_file_violations()`, `read_prod_violations()`, `clear_prod_violations()`, and the `prod_violations` key in `.workflow-state.json`.

- **Pros**: Removes ~65 lines of state I/O. Simplifies the stop gate (one marker instead of two). Eliminates an entire state key and its edge cases (dict vs string format, partial cleanup).
- **Cons**: Security violations that were previously tracked across the session would only be caught at write-time. But since security violations already exit 2 (blocking the write), they must be fixed immediately anyway — tracking them in state is redundant.

### 4. Slim the QA Pipeline to Essential Steps

Reduce the 12-step QA pipeline to the 6 steps that provide 95% of the value:

1. **Lint** (ruff/eslint)
2. **Type check** (pyright/tsc)
3. **Unit tests** (pytest)
4. **Security scan** (violation patterns)
5. **Plan conformance** (R-markers match prd.json)
6. **Production scan** (code hygiene)

Drop steps that are rarely actionable or duplicate other steps:

- ~~Integration tests~~ — merged into unit test step (just run all tests)
- ~~Regression tests~~ — merged into unit test step
- ~~Clean diff~~ — duplicates production scan
- ~~Coverage analysis~~ — rarely used, `coverage.json` often missing
- ~~Mock audit~~ — niche, rarely triggers
- ~~Acceptance tests~~ — duplicate of plan conformance

This would shrink `qa_runner.py` from 1,281 lines to ~600-700 lines.

- **Pros**: Faster QA runs. Less code to maintain. Steps 7-12 almost never produce actionable results in practice. Removes `check_diff_line_coverage()` and `check_call_graph_wiring()` from `_lib.py` (~215 lines).
- **Cons**: Loses the "12-step" branding. Mock audit and coverage could catch real issues in edge cases. If a project needs those steps later, they'd need to be re-added.

### 5. Right-Size the Test Suite

The test suite is 2.6x the code it tests. Approach:

- Merge `test_lib_quality.py` (2,489 lines) into focused test files that match the module split (e.g., `test_qa_lib.py` for QA engine functions, `test_lib.py` for core utilities)
- Delete tests for removed features (legacy migration, error history rotation, prod violation string format)
- Consolidate parametrized tests where multiple test functions test the same function with different inputs
- Target: 1:1 ratio (test lines ≈ code lines) for core hooks, 1.5:1 for QA engine

- **Pros**: Faster test runs. Easier to maintain. Tests organized by module rather than by the monolith they used to test.
- **Cons**: Significant rework. Risk of losing coverage if consolidation is too aggressive. Must run coverage to verify.

### 6. Extract Plan Validation to Standalone Module

Move `validate_plan_quality()` and all its helpers (~250 lines, 6 private functions, 5 compiled regexes) out of `_lib.py` into `plan_validator.py` directly. Currently `plan_validator.py` is a 76-line wrapper that imports one function from `_lib.py` — make it self-contained.

- **Pros**: `_lib.py` shrinks by ~250 lines. `plan_validator.py` becomes a complete, self-contained tool. No import chain needed.
- **Cons**: If QA runner also uses plan validation, it would need to import from `plan_validator.py` instead of `_lib.py`. Minor import restructuring.

### 7. Radical Simplification: Self-Contained Hooks

Make each hook completely self-contained — no shared `_lib.py` at all. Each hook file contains only the code it needs:

- `pre_bash_guard.py`: Deny patterns + check logic (~100 lines, already nearly self-contained)
- `post_format.py`: Formatter execution + marker write (~120 lines)
- `post_bash_capture.py`: Error capture + marker clear (~80 lines)
- `post_write_prod_scan.py`: Violation patterns + scan (~180 lines)
- `stop_verify_gate.py`: State read + gate logic (~100 lines)
- `post_compact_restore.py`: State read + reminder (~60 lines)

Shared functions (state I/O, config loading) would be duplicated in each file that needs them — but since only 3-4 hooks need state I/O, the duplication is ~50 lines per hook.

`qa_runner.py` would keep its own `_qa_lib.py` for QA-specific utilities.

- **Pros**: Zero coupling between hooks. Each hook can be understood, tested, and modified in isolation. A bug in one hook can never affect another. Dramatically simpler mental model.
- **Cons**: ~150 lines of duplication across hooks (state I/O, config loading). Changes to state format require updating multiple files. Violates DRY.

### 8. Hybrid: Split \_lib + Delete Dead Code + Simplify Violations

Combine Ideas 1 + 2 + 3 + 6 — the changes that are complementary and low-risk:

- Split `_lib.py` into `_lib.py` (core, ~350 lines) + `_qa_lib.py` (QA engine, ~1,200 lines)
- Delete all dead code (legacy migration, error history, prod violations string format)
- Simplify prod violation tracking to stateless scan-and-warn
- Extract plan validation into `plan_validator.py`
- Keep the 12-step QA pipeline structure but remove the two heaviest steps (call-graph wiring, diff-line coverage) that depend on AST parsing and git operations

Net result: `_lib.py` drops from 2,081 to ~350 lines. `_qa_lib.py` holds ~950 lines. Total hook code drops from 4,152 to ~3,600. Dead code and unnecessary state complexity eliminated.

- **Pros**: Addresses the biggest pain points (monolith, dead code, over-engineering) without breaking anything. Each change is independently safe and testable. Preserves the QA pipeline for Ralph users.
- **Cons**: More changes to coordinate than any single idea. Still has a large QA engine (but that's intentional — it's where the value is for Ralph sprints).

## Recommendation

**Idea 8 (Hybrid)** is the best approach. Here's why:

1. **It addresses the root cause**: The monolith (`_lib.py`) is the #1 problem. Splitting it into hot-path vs QA-engine makes the always-on hooks lean and the QA pipeline self-contained.

2. **It's safe**: Every change is independently reversible. Dead code deletion is zero-risk. The stateless prod scan simplification removes complexity without changing visible behavior (security violations already block at write-time). The plan validation extraction is a pure code-move.

3. **It preserves the QA pipeline**: Ideas 4 (slim to 6 steps) and 7 (self-contained hooks) are more aggressive and risk losing capabilities that Ralph sprints depend on. The hybrid keeps 10 of 12 QA steps (dropping only the AST-heavy call-graph and the rarely-used diff-coverage), which is the right tradeoff.

4. **The test suite naturally shrinks**: Deleting dead code means deleting dead tests. Splitting `_lib.py` means splitting `test_lib_quality.py`. The test:code ratio improves without a dedicated "test reduction" effort.

**What tips it over Idea 1 alone**: Ideas 2, 3, and 6 are essentially free — they remove dead code, unnecessary state, and misplaced code. Doing them alongside the split is more efficient than doing them separately.

**What I'd defer**: Idea 4 (slim to 6 steps) is tempting but risky — it changes the QA pipeline's public interface, which Ralph's SKILL.md references. Idea 5 (right-size tests) will happen naturally as a consequence of the split and dead code removal. Idea 7 (self-contained hooks) is intellectually clean but the DRY violation isn't worth it.

## Expected Outcome

| Metric                    | Before                                                    | After                                                   |
| ------------------------- | --------------------------------------------------------- | ------------------------------------------------------- |
| `_lib.py` lines           | 2,081                                                     | ~350                                                    |
| `_qa_lib.py` lines        | 0                                                         | ~950                                                    |
| `qa_runner.py` lines      | 1,281                                                     | ~1,100 (drop 2 AST-heavy steps)                         |
| `plan_validator.py` lines | 76                                                        | ~320 (self-contained)                                   |
| Other hooks               | 602                                                       | ~560 (remove error history, simplify prod scan)         |
| **Hook code total**       | **4,152**                                                 | **~3,280**                                              |
| Dead code                 | ~130 lines                                                | 0                                                       |
| State keys tracked        | 3 (`needs_verify`, `stop_block_count`, `prod_violations`) | 2 (`needs_verify`, `stop_block_count`)                  |
| Test files                | 14                                                        | 14-15 (split test_lib_quality → test_lib + test_qa_lib) |
| Test lines                | 10,743                                                    | ~8,500 (dead test deletion + split)                     |
| **Grand total**           | **14,895**                                                | **~11,780**                                             |

**~21% total reduction** with the monolith broken up, dead code removed, and state model simplified.

## Sources

- `.claude/hooks/_lib.py` (2,081 lines, full read)
- `.claude/hooks/qa_runner.py` (1,281 lines, full read)
- All 6 hook scripts (full read)
- `test_quality.py`, `plan_validator.py` (full read)
- `.claude/docs/ARCHITECTURE.md` (hook chain, design decisions)
- `.claude/docs/PLAN.md` (recent polish sprint scope)
- `.claude/docs/knowledge/lessons.md` (hook double-firing, escalation conflicts)
- `.claude/docs/HANDOFF.md` (current sprint status)
- `PROJECT_BRIEF.md` (tech stack, constraints)

---

## Build Strategy

### Module Dependencies

```
                    ┌─────────────────────┐
                    │   settings.json     │  (hook wiring config)
                    └─────────┬───────────┘
                              │ triggers
              ┌───────────────┼───────────────┐
              │               │               │
     ┌────────▼───┐  ┌───────▼────┐  ┌───────▼──────┐
     │ Always-On  │  │ QA Engine  │  │ Plan Validator│
     │ Hooks (6)  │  │ (explicit) │  │  (explicit)   │
     └─────┬──────┘  └─────┬──────┘  └───────┬──────┘
           │               │                  │
     ┌─────▼──────┐  ┌─────▼──────┐  ┌───────▼──────┐
     │  _lib.py   │  │ _qa_lib.py │  │plan_validator │
     │  (core)    │◄─┤ (QA utils) │  │   .py (self-  │
     │  ~350 LOC  │  │  ~950 LOC  │  │  contained)   │
     └────────────┘  └────────────┘  └──────────────┘

_lib.py (core):
  - state I/O (read/write/update workflow state)
  - stdin parsing
  - config loading
  - audit logging
  - marker I/O (needs_verify, stop_block_count)
  - test command detection
  - formatter execution
  - violation patterns + scan_file_violations()
  - CODE_EXTENSIONS constant

_qa_lib.py (QA engine):
  imports from _lib.py: CODE_EXTENSIONS, PROJECT_ROOT, load_workflow_config
  - scan_test_quality()
  - check_negative_tests()
  - check_public_api_coverage()
  - check_story_file_coverage()
  - validate_r_markers()
  - check_plan_prd_sync()
  - extract_plan_r_markers()
  - parse_plan_changes()
  - append/read_verification_log()

plan_validator.py (self-contained):
  imports from _lib.py: nothing (fully standalone)
  - validate_plan_quality() + all helpers
  - _split_plan_into_phases()
  - _extract_done_when_items()
  - _check_vague_criteria()
  - _check_r_id_format()
  - _check_testing_strategy()
  - _check_verification_placeholders()
  - _check_test_file_coverage()
```

### Build Order

**Phase 1: Dead Code + Stateless Violations** (independent, no module split yet)

1. Delete `migrate_legacy_markers()` and all references
2. Delete error history rotation from `post_bash_capture.py`
3. Remove `prod_violations` state tracking — make `post_write_prod_scan.py` stateless, simplify `stop_verify_gate.py`
4. Run full test suite, delete dead tests

**Phase 2: Extract Plan Validation** (independent of Phase 1)

1. Move `validate_plan_quality()` + all helpers into `plan_validator.py`
2. Remove plan validation code from `_lib.py`
3. Update `qa_runner.py` to import from `plan_validator` instead of `_lib`
4. Move/update `test_plan_validator.py` to test the self-contained module

**Phase 3: Split \_lib.py** (depends on Phase 1 + 2 being complete)

1. Create `_qa_lib.py` with QA-specific functions
2. Update `qa_runner.py` and `test_quality.py` imports
3. Remove moved code from `_lib.py`
4. Remove `check_call_graph_wiring()` and `check_diff_line_coverage()` (AST-heavy, rarely used)
5. Split `test_lib_quality.py` into `test_lib.py` + `test_qa_lib.py`

**Phase 4: Test Suite Cleanup** (depends on Phase 3)

1. Delete tests for removed functions
2. Consolidate remaining tests to match new module boundaries
3. Verify coverage with `pytest --cov`

**Phases 1 and 2 can run in parallel.** Phase 3 depends on both. Phase 4 depends on Phase 3.

### Testing Pyramid

- **Unit tests** (85%): All hook functions, state I/O, violation scanning, QA utilities, plan validation. These are pure functions with no external dependencies.
- **Integration tests** (10%): Hook stdin/stdout contracts (simulated Claude Code hook invocations), QA pipeline end-to-end (all steps), plan validator CLI.
- **E2E tests** (5%): Full `settings.json` hook chain (edit file → format → scan → run tests → stop gate clears). This is currently manual — could be automated.

Ratio: **85/10/5** — matches current reality where all tests are unit tests with simulated I/O.

### Risk Mitigation Mapping

| Risk                                                               | Mitigation                                                                                                                                                                                                                                                                     |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Split introduces import errors                                     | Phase 3 runs full test suite after every file move. Import failures caught immediately.                                                                                                                                                                                        |
| Removing `prod_violations` state breaks stop gate                  | Phase 1 Step 3: stop gate only checks `needs_verify`. Security violations still block at write-time (exit 2). The gate behavior for hygiene violations changes from "block stop" to "warn at write-time only" — acceptable because running tests clears `needs_verify` anyway. |
| Plan validation extraction breaks qa_runner                        | Phase 2 Step 3: qa_runner imports `validate_plan` from `plan_validator` module. Same function, different import path. Test coverage verifies.                                                                                                                                  |
| Test suite split loses coverage                                    | Phase 4 Step 3: run `pytest --cov` before and after. Coverage delta must be ≤ 1%.                                                                                                                                                                                              |
| `_qa_lib.py` imports from `_lib.py` create circular dependency     | Architecture explicitly prevents this: `_lib.py` never imports from `_qa_lib.py`. Dependency is one-directional.                                                                                                                                                               |
| Removing call-graph wiring and diff-coverage removes QA capability | These steps have never produced an actionable FAIL in any sprint. `check_call_graph_wiring` depends on AST parsing + `git show` subprocess — fragile and slow. Coverage is better measured by pytest-cov directly.                                                             |

### Recommended Build Mode

**Manual Mode** (builder agent, phase-by-phase)

Rationale:

- This is a **refactoring task** — no new features, no acceptance criteria to verify against
- Changes are tightly coupled across files (moving code from \_lib.py to new modules requires simultaneous import updates)
- Risk of breaking existing hooks is real — needs careful, sequential execution with tests after every change
- Ralph is designed for story-by-story feature development with independent worktrees; refactoring across shared modules doesn't fit the worktree isolation model
- Phase 1 and 2 are small enough for a single manual session each
- Phase 3 (the core split) benefits from a human reviewing each code move before proceeding

The builder agent should execute each phase, run the full test suite after every file change, and escalate immediately if any test fails.
