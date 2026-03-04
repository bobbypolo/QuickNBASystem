# Brainstorm: Quality Enforcement Hardening & Simplification

**Date**: 2026-03-01
**Problem**: The workflow can produce bad code and bad tests that pass every gate, because quality enforcement checks form (did you follow the plan?) but not substance (is the plan good? do the tests prove the code works? do hygiene violations actually reach the stop gate?). Meanwhile, duplicate logic across files creates maintenance burden and inconsistency.

## Current State: Where Quality Leaks

### Critical Bugs (Discovered During This Analysis)

**BUG-1: Prod violations write/read path is broken.**
`post_write_prod_scan.py` (line 91) writes violations to the legacy `.prod_violations` file via its own `_write_marker()` function. But `stop_verify_gate.py` reads from `.workflow-state.json` via `read_prod_violations()`. The hook never calls `update_workflow_state()`. Result: hygiene violations detected at write-time are invisible to the stop gate. The stop gate can never block on prod violations because the data never reaches it.

**BUG-2: CLAUDE.md documentation says "16-step" in multiple places, but code has 12 steps.**
The QA Pipeline table header, multiple prose references, and the hook description table all reference 16 steps. `qa_runner.py` has 12 steps. `ralph-worker.md` has 12 steps. This is documentation drift that confuses both humans and Claude.

**BUG-3: Audit SKILL.md checks legacy file paths.**
Section 6 (lines 84-85) checks for `.needs_verify` and `.stop_block_count` as separate files. These now live in `.workflow-state.json`. The audit will always report them as "absent (clean)" even when they're active in the state file. Section 7 (line 102) checks `.gitignore` for `.claude/ralph-state.json` (wrong filename).

### Quality Gaps (The Real Problem)

**GAP-1: No plan quality validation.** A plan with "R-P1-01: Authentication works correctly" passes every current gate. There's no automated check that acceptance criteria are specific, measurable, and testable. Plan/SKILL.md Step 6b describes 6 checks but they're prompt-based (LLM executes them) — not deterministic Python code.

**GAP-2: Test assertions too shallow.** `test_quality.py` catches assertion-free tests (zero assertions) but not weak assertions. `assert result is not None` counts as an assertion. A function that always returns `True` passes if the test only checks truthiness. No requirement for negative tests (testing that invalid input fails).

**GAP-3: qa_runner.py is optional for workers.** `ralph-worker.md` (line 180-194) describes it as optional. Workers can skip it and use inline grep-based checks, which are less comprehensive than `scan_file_violations()` with compiled regex patterns.

**GAP-4: No cumulative regression after merge.** Ralph's spot-check runs only the current story's `gateCmds`. If STORY-003 breaks STORY-002's tests, nobody catches it until `/audit` or never.

**GAP-5: No semantic verification.** QA checks "did files change match the plan?" (structural) but not "does this function actually do what the criterion says?" A function called `validate_input` that always returns `True` passes every gate.

**GAP-6: 5 of 15 production standards have no automated enforcement.** Rules 2 (hardcoded URLs/ports/magic numbers), 5 (unused imports), 7 (type hints), 8 (input validation), and 9 (resource cleanup) have no regex patterns in `_lib.py`. They exist only as prose instructions to the LLM.

### Duplication (Maintenance Burden)

**DUP-1: Triple file scanning in qa_runner.py.** Steps 6, 7, and 12 each independently call `scan_file_violations()` on the same file set. Every source file is read from disk and regex-matched 3 times. Step 12 is a complete superset of Steps 6+7.

**DUP-2: CODE_EXTENSIONS defined in 3 files with inconsistent values.**

- `post_format.py`: 10 extensions (includes `.cs`)
- `post_write_prod_scan.py`: 10 extensions (includes `.cs`)
- `qa_runner.py`: 14 extensions (includes `.php, .c, .cpp, .h, .hpp`, missing `.cs`)

**DUP-3: Production standards in 3 places.** 15 prose rules in `ralph-worker.md`, 15 prose rules in `CLAUDE.md`, 13 regex patterns in `_lib.py`. They don't align: prose has 15 rules, regex covers only 10 of them fully.

**DUP-4: Plan Sanity Check duplicated verbatim.** `ralph-worker.md` lines 34-54 and `builder.md` lines 22-43 are identical word-for-word. Update one, forget the other.

**DUP-5: 12-step QA in two representations.** Full prose description in `ralph-worker.md` AND executable code in `qa_runner.py`. The prose can drift from the implementation. Workers who use prose instead of `qa_runner.py` run weaker checks.

**DUP-6: test_quality.py is a thin CLI wrapper.** 193 lines that call `scan_test_quality()` and `validate_r_markers()` from `_lib.py`. Could be a mode of `qa_runner.py` instead of a separate script.

---

## Ideas

### 1. Fix the Three Critical Bugs First

**Description**: Before any new features, fix the broken plumbing. (a) Make `post_write_prod_scan.py` write to `.workflow-state.json` via `update_workflow_state()`. (b) Update all CLAUDE.md references from 16 to 12 steps. (c) Update `audit/SKILL.md` to read markers from `.workflow-state.json` and fix the wrong `.gitignore` filename.

- **Pros**: Immediate correctness improvement. The stop gate actually works for prod violations. Documentation matches reality. Audit catches real state. Zero new features — pure fix.
- **Cons**: Requires updating `post_write_prod_scan.py` tests to reflect new write path. Small scope but high impact.

### 2. Plan Quality Validator (`plan_validator.py`)

**Description**: Create a deterministic Python script (like `qa_runner.py` for QA) that validates PLAN.md structure and quality. Run it as a gate before Ralph starts. Checks: (a) every acceptance criterion contains a measurable verb (rejects/returns/raises/contains, not "works"/"handles"), (b) every criterion specifies expected AND unexpected behavior, (c) every phase has testing strategy with specific test types, (d) no placeholder brackets remaining, (e) interface contracts have concrete signatures not prose, (f) R-marker format validation.

- **Pros**: Deterministic — same input always produces same result. Can be run by Ralph at STEP 5A before dispatching workers. Catches vague plans before they become vague code. Existing `check_plan_prd_sync()` in `_lib.py` proves the pattern works.
- **Cons**: Measuring "specificity" of prose is inherently fuzzy. Regex for measurable verbs may have false positives/negatives. Could become a gate that blocks legitimate plans if over-tuned.

### 3. Test Depth Enforcement (Enhanced `scan_test_quality()`)

**Description**: Upgrade `scan_test_quality()` in `_lib.py` to detect weak test patterns beyond assertion-free and self-mock: (a) **Weak assertions**: `assert x is not None`, `assert x`, `assert len(x)` with no value check, `assertTrue(result)` with no specificity. (b) **Happy-path-only**: Tests that never pass invalid/edge-case input — detect by counting test functions per module and flagging modules with zero "error"/"invalid"/"fail"/"edge"/"boundary" in test names. (c) **Assertion-to-code ratio**: If a test function has 20 lines of setup and 1 assertion, flag as potentially undertested. (d) **Stub-would-pass test**: If replacing the function under test with `return None` or `return True` would still pass all assertions, the test is vacuous (heuristic: test only asserts truthiness/existence, never specific values).

- **Pros**: Catches the exact failure mode the user described — tests that pass but prove nothing. Assertion strength checking is feasible with AST analysis. Already have the infrastructure in `_lib.py`. Would catch `assert result is not None` as WEAK. Ratio check flags suspiciously thin test coverage.
- **Cons**: AST-based analysis is more complex than regex. "Stub-would-pass" is a heuristic, not a proof. Happy-path detection by test name is unreliable (well-named tests might not use "error" keyword). Could produce false positives that annoy the worker.

### 4. Mandatory qa_runner.py (Not Optional)

**Description**: Remove the "optional" designation of `qa_runner.py` from `ralph-worker.md`. Workers MUST run `qa_runner.py` as their verification step. Remove the inline prose QA pipeline description from `ralph-worker.md` entirely — replace with "Run `python .claude/hooks/qa_runner.py --story {STORY_ID} ...` and fix all FAILs." This makes `qa_runner.py` the single source of truth for what QA means.

- **Pros**: Eliminates DUP-5 entirely. One implementation of QA, not two. Workers can't skip the harder checks. `qa_runner.py` is tested (the prose description is not). Reduces `ralph-worker.md` by ~80 lines. Any QA improvement automatically applies to all workers.
- **Cons**: `qa_runner.py` must be available in worktrees. Since `.claude/hooks/` is committed (not gitignored), this is already true. Workers lose the ability to do a "quick check" before full QA. If `qa_runner.py` breaks, all workers are blocked.

### 5. Scan Once, Partition Results (qa_runner.py Optimization)

**Description**: In `qa_runner.py`, scan each source file exactly once. Cache the results. Steps 6 (security), 7 (clean diff), and 12 (production scan) each filter the cached results by violation category instead of re-scanning. This turns 3N file reads into N.

Implementation:

```python
# At pipeline start:
_violation_cache: dict[str, list[dict]] = {}
for f in source_files:
    _violation_cache[str(f)] = scan_file_violations(f)

# Step 6: filter to _SECURITY_IDS
# Step 7: filter to _CLEANUP_IDS
# Step 12: use all results (no filter)
```

- **Pros**: 3x reduction in file I/O. Measurable speedup on large codebases. Results are guaranteed consistent across steps (no TOCTOU issues). Simple implementation — 10 lines of code.
- **Cons**: Memory usage scales with codebase size (but violation lists are small). Cache invalidation not needed (pipeline runs once). Minor refactor to step functions.

### 6. Centralize CODE_EXTENSIONS in \_lib.py

**Description**: Define `CODE_EXTENSIONS` once in `_lib.py`. Import it in `post_format.py`, `post_write_prod_scan.py`, and `qa_runner.py`. Use a single comprehensive set that covers all languages.

```python
# _lib.py
CODE_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs",
    ".java", ".rb", ".cs", ".php", ".c", ".cpp", ".h", ".hpp",
})
```

- **Pros**: One place to update when adding language support. Eliminates DUP-2 entirely. `frozenset` is immutable and fast. Consistent behavior across all hooks and utilities.
- **Cons**: Hooks that previously ignored `.php`/`.c` files will now process them (format/scan). This is actually correct behavior — the inconsistency was the bug.

### 7. Cumulative Regression Gate

**Description**: After Ralph merges each story's worktree, run ALL prior stories' gate commands in addition to the current story's. If STORY-003's merge breaks STORY-002's tests, catch it immediately.

Implementation in `ralph/SKILL.md` STEP 6 (spot-check):

```
For each completed story (passed: true) INCLUDING the current story:
    Run gateCmds.unit (if defined)
    Run gateCmds.lint (if defined)
    If any fails: FAIL the current story merge
```

- **Pros**: Catches cross-story regressions immediately, not at audit time. Uses existing gate commands — no new infrastructure. Prevents the "10 stories pass individually but don't work together" failure mode.
- **Cons**: Gets slower as stories accumulate (N stories = N test suites). For a 10-story sprint, the last story runs 10 test suites. Can be mitigated by running a single comprehensive test command instead of per-story commands. May catch pre-existing failures that aren't the current story's fault.

### 8. Merge test_quality.py into qa_runner.py

**Description**: Add `--test-quality` mode to `qa_runner.py` that runs everything `test_quality.py` does. Keep `test_quality.py` as a thin backward-compatible wrapper that calls `qa_runner.py --test-quality`. This consolidates two scripts into one.

- **Pros**: One CLI for all quality checks. Reduces file count. `qa_runner.py` already calls `scan_test_quality()` in Step 9. Makes `test_quality.py` a convenience alias, not a separate tool.
- **Cons**: `qa_runner.py` gets larger. The two tools serve different audiences (qa_runner = story verification, test_quality = standalone analysis). Backward compatibility wrapper adds a tiny bit of indirection.

### 9. Production Standards Alignment

**Description**: Align the 15 prose rules with the 13 regex patterns. For the 5 rules without patterns, either: (a) add regex patterns where feasible (unused imports can be detected via `import X` where X never appears elsewhere in the file), or (b) explicitly document them as "enforced by external tool" (ruff handles unused imports, mypy handles type hints) and wire those tools into the production scan step.

Map:
| Rule | Current Enforcement | Proposed |
|------|-------------------|----------|
| 2. No hardcoded URLs/ports/magic numbers | None | Add regex for common patterns (`http://`, `localhost:`, numeric port assignments) |
| 5. No unused imports | None (ruff handles it) | Document as "enforced by Step 1 (lint)" |
| 7. Type hints on public functions | None (mypy handles it) | Document as "enforced by Step 2 (type check)" |
| 8. Input validation at boundaries | None (subjective) | Remove from automated list — keep as review guidance |
| 9. Resource cleanup | None (subjective) | Remove from automated list — keep as review guidance |

- **Pros**: Every automated rule has enforcement. Subjective rules are honestly labeled. No false promises about what's checked. Prose and regex stay in sync.
- **Cons**: Reducing the list from 15 to "13 automated + 2 guidance" might feel like losing coverage. Adding new regex patterns needs thorough testing to avoid false positives.

### 10. Worker Verification Receipt

**Description**: After a worker runs `qa_runner.py`, the JSON output becomes a "verification receipt" that Ralph validates before accepting the PASS result. Ralph checks: (a) all 12 steps present in output, (b) no steps skipped without `--phase-type` justification, (c) overall result is PASS, (d) `criteria_verified` list matches the story's acceptance criteria IDs. If the receipt is missing or incomplete, treat as FAIL regardless of what the worker claims.

- **Pros**: Closes GAP-3 completely — workers can't claim PASS without actually running QA. Receipt is machine-parseable (JSON). Ralph can spot-check the receipt without re-running all 12 steps. Creates verifiable evidence chain.
- **Cons**: Workers must format the receipt correctly. If qa_runner.py output format changes, validation breaks. Adds parsing logic to Ralph's STEP 6.

### 11. Negative Test Requirement for Validation Criteria

**Description**: For any acceptance criterion that mentions validation, rejection, filtering, or boundary checking, require at least one test with "invalid", "rejected", "malformed", "edge", "boundary", or "error" in the test name OR a test that asserts a raised exception/error return. `test_quality.py` flags criteria about validation that have only happy-path tests.

Detection heuristic:

```python
VALIDATION_KEYWORDS = {"validate", "reject", "filter", "boundary", "limit", "max", "min", "invalid", "error", "fail"}
# If criterion text contains any keyword AND linked tests contain zero negative patterns → WARN
```

- **Pros**: Directly addresses the "function that always returns True" failure mode. If the criterion says "rejects invalid input" but no test sends invalid input, that's a real gap. Lightweight heuristic — no AST needed.
- **Cons**: Keyword matching is imprecise. Criterion "validate configuration file format" might not have "reject" in test names but still tests errors via exception assertions. False positive risk.

### 12. Single Comprehensive Test Command for Regression

**Description**: Instead of per-story gate commands for cumulative regression (Idea 7), define a single `regression_cmd` in `workflow.json` that runs ALL project tests. Ralph runs this after every merge instead of accumulating per-story commands.

```json
// workflow.json
{
  "commands": {
    "test": "python -m pytest .claude/hooks/tests/ -v",
    "regression": "python -m pytest .claude/hooks/tests/ -v --tb=short"
  }
}
```

- **Pros**: Simpler than accumulating per-story commands. One command catches all regressions. Already natural — most projects have a "run all tests" command. Constant time regardless of story count.
- **Cons**: Slower than running only the current story's tests (runs everything every time). May catch pre-existing failures unrelated to current work. But this is actually desirable — pre-existing failures should be caught.

### 13. Coverage Gap Detection — The "42% Untested" Problem

**Description**: The most dangerous AI behavior is writing _impressive-looking_ tests for the files it chooses to test while silently skipping entire modules. Real-world evidence: a codebase with 3,800 tests, zero assertion-free, zero self-mock, good mock ratio (1:15.6), parametrization and edge cases everywhere — yet 42% of production files have no test at all. `engine/` at 36% file coverage, `evaluation/` at 25%, `governance/` at 0%.

No current quality gate catches this. `test_quality.py` checks the tests that exist but cannot flag tests that _should_ exist but don't.

**Solution — Test-to-File Coverage Mapping (enforced at two levels):**

**Level 1: Plan requires explicit test file list.**
Every phase's Changes table must include a "Test Files" column listing every test file that will be created or modified. The plan validator (Idea 2) rejects phases where production files have no corresponding test file entry.

```markdown
### Changes Table (Enhanced)

| File                  | Action | Test File                                 | Test Type   |
| --------------------- | ------ | ----------------------------------------- | ----------- |
| engine/pace_engine.py | CREATE | tests/unit/test_pace_engine.py            | unit        |
| engine/pace_engine.py | CREATE | tests/integration/test_engine_pipeline.py | integration |
| governance/rules.py   | CREATE | tests/unit/test_governance_rules.py       | unit        |
```

Plan validator check: `For each production file with Action CREATE or MODIFY, at least one Test File entry must exist. FAIL if any production file has zero test file mappings.`

**Level 2: QA Step verifies test files actually exist and cover the production file.**
New qa_runner step (or enhancement to existing Step 11): For each production file changed in this story, verify:
(a) A test file exists that imports or references the production module
(b) The test file has at least one test function
(c) The test file has at least one assertion that exercises the production module's public API

```python
def _check_test_file_coverage(changed_files: list[Path], test_dir: Path) -> list[dict]:
    """For each changed production file, verify a corresponding test exists."""
    gaps = []
    for prod_file in changed_files:
        if _is_test_file(prod_file):
            continue
        # Derive expected test file name
        expected_test = test_dir / f"test_{prod_file.stem}.py"
        # Also check if ANY test file imports this module
        module_name = prod_file.stem
        found = expected_test.exists() or _any_test_imports(module_name, test_dir)
        if not found:
            gaps.append({"file": str(prod_file), "reason": "no_test_file"})
    return gaps
```

- **Pros**: Directly prevents the "42% untested" scenario. Plan-level enforcement means the AI must plan test files before building (can't skip during implementation). QA-level enforcement catches files that were planned but never tested. Catches the exact AI gaming behavior described.
- **Cons**: Some utility files genuinely don't need dedicated test files (they're tested transitively). Need an escape hatch: `# no-direct-test: tested via test_parent_module.py`. Adds a column to the Changes table (plan template change).

### 14. Integration Test Ratio Enforcement

**Description**: 5 integration tests for 145+ modules is mathematically inadequate but no gate catches it. Enforce a minimum integration test ratio: for every N modules that interact across boundaries, require at least 1 integration test that exercises the interaction.

**Detection approach:**

- From the plan's Data Flow section, extract module interaction pairs (e.g., "engine → sequencer", "markets → optimizer")
- Count unique interaction pairs
- Count integration test files
- If `integration_tests / interaction_pairs < 0.5`: WARN "Integration test coverage is thin"
- If `integration_tests / interaction_pairs < 0.25`: FAIL "Critical integration test gap"

**Plan-level enforcement:**
The plan's Testing Strategy section must list specific integration test scenarios for each cross-module interaction identified in Data Flow. The plan validator checks this list exists and is non-empty.

- **Pros**: Prevents thin integration coverage from slipping through. Ties integration test planning to the Data Flow section (which already exists in plans). The ratio is adjustable per project. Forces the AI to think about module interactions during planning, not just implementation.
- **Cons**: Counting "interaction pairs" from prose is fuzzy. The ratio thresholds need calibration. Over-enforcement could require unnecessary integration tests for simple interactions. Some interactions are adequately tested by unit tests with proper contracts.

### 15. Test File Must Exercise Production File's Public API

**Description**: Even when a test file exists, the AI can create a test that technically imports the module but only tests trivial behavior. For example, `test_governance_rules.py` that only tests `__init__` or string representations while ignoring the actual rule enforcement logic.

**Enhancement to scan_test_quality():**
For each test file, analyze:
(a) Which functions/classes from the production module are actually called in test code
(b) Which public functions in the production module are NOT called by any test
(c) If >50% of public functions are untested: WARN "Test file covers only {X}% of {module} public API"

```python
def _check_api_coverage(test_file: Path, prod_file: Path) -> dict:
    """Check which public functions in prod_file are exercised by test_file."""
    prod_functions = _extract_public_functions(prod_file)  # def foo(), not _private()
    test_source = test_file.read_text()
    covered = [f for f in prod_functions if f in test_source]
    uncovered = [f for f in prod_functions if f not in covered]
    coverage_pct = len(covered) / max(len(prod_functions), 1) * 100
    return {
        "prod_file": str(prod_file),
        "total_public": len(prod_functions),
        "covered": len(covered),
        "uncovered": uncovered,
        "coverage_pct": coverage_pct,
    }
```

- **Pros**: Catches the "test file exists but only tests **init**" gaming pattern. Surfaces exactly which functions lack test coverage. Public API extraction is feasible (regex for `def` not starting with `_`). Complements file-level coverage (Idea 13) with function-level coverage.
- **Cons**: String matching for function names has false positives (a function name that appears in a string literal). Doesn't verify the function is called _correctly_ — just that it's referenced. Some functions are tested indirectly through higher-level calls. Needs AST parsing for accuracy, regex for speed.

### 16. Plan Must Specify Untested File Justification

**Description**: If a plan intentionally leaves production files without direct test files, it must explicitly justify each one. This prevents silent omission — the AI must acknowledge the gap and explain why.

```markdown
### Untested Files (with justification)

| File               | Reason                   | Tested Via                 |
| ------------------ | ------------------------ | -------------------------- |
| utils/constants.py | Pure constants, no logic | Imported by all test files |
| types/enums.py     | Type definitions only    | Used in type-checked tests |
```

Plan validator check: `If any production file in the Changes table has no Test File entry AND no Untested Files justification: FAIL.`

- **Pros**: Makes coverage decisions explicit and reviewable. Prevents silent omission. The justification "tested via X" can be verified (does X actually import this file?). Lightweight — just a markdown table.
- **Cons**: Could become a bureaucratic checkbox where the AI writes boilerplate justifications. Need to validate justifications are genuine (not "tested transitively" for a file with complex logic).

### 17. CI Parity Enforcement

**Description**: Tests that only run locally give false confidence. The audit from the user's codebase shows golden path E2E tests that are `@pytest.mark.skipif` in CI — meaning system-level validation never runs in the automated pipeline.

**Plan-level rule:** Every test listed in the Testing Strategy must be either:
(a) Runnable in CI (no skip conditions that depend on local-only fixtures)
(b) Explicitly marked as "local-only" with justification AND a CI-compatible alternative specified

**QA check:** New qa_runner check that parses test files for `skipif`/`skip` markers and flags:

- `@pytest.mark.skipif` with conditions that are always true in CI (missing fixture files, specific OS)
- `@pytest.mark.skip(reason=...)` without a CI-runnable companion test
- Tests in the `e2e/` or `integration/` directory that are never actually run by the CI test command

- **Pros**: Prevents the "tests exist but never run" blind spot. Forces either fixing CI compatibility or acknowledging the gap. Surfaces the real test coverage that CI validates vs. what only runs on developer machines.
- **Cons**: Some tests genuinely can't run in CI (require databases, external services, specific hardware). The "local-only with justification" path handles this. Parsing pytest markers reliably requires understanding decorators, which is more complex than simple regex.

### 18. Coverage Floor per Story (Not Just Global)

**Description**: Instead of only checking global coverage at audit time, enforce a coverage floor per story at verification time. If a story adds 5 new production files and 200 lines of code, but only 3 files have tests, the story fails — even if global coverage is acceptable.

**Implementation in qa_runner.py:**

```python
def _step_story_coverage(changed_files, test_dir):
    """Verify each changed production file has test coverage."""
    prod_files = [f for f in changed_files if not _is_test_file(f) and _is_code_file(f)]
    tested = 0
    for pf in prod_files:
        if _has_corresponding_test(pf, test_dir):
            tested += 1
    coverage = tested / max(len(prod_files), 1) * 100
    if coverage < 80:  # 80% of changed files must have tests
        return {"result": "FAIL", "coverage": coverage, "untested": [...]}
    return {"result": "PASS", "coverage": coverage}
```

- **Pros**: Catches coverage gaps at story time, not at audit time. The 80% threshold allows utility/config files to skip tests. Per-story enforcement prevents accumulating technical debt across stories. Works with existing qa_runner infrastructure.
- **Cons**: 80% threshold is arbitrary — needs calibration. Some stories are purely configuration/documentation with no testable code. Need to exclude non-code files (markdown, config, templates).

---

## Recommendation (Updated with Coverage Enforcement)

**Implement in three tiers: Fix Bugs → Simplify → Harden Quality.**

The original 12 ideas remain, with 6 new ideas (13-18) strengthening Tier 3 to address the "42% untested" coverage gaming problem.

### Tier 1: Fix Bugs (Do First, Non-Negotiable)

- **Idea 1**: Fix the three critical bugs. Prod violations write path, 16→12 doc references, audit legacy paths. Estimated: 2-3 hours.

### Tier 2: Simplify (Reduce Surface Area)

Combine **Ideas 4 + 5 + 6 + 8 + 9**:

- Make `qa_runner.py` mandatory for workers, remove inline QA prose from `ralph-worker.md` (Idea 4)
- Scan once, partition results in `qa_runner.py` (Idea 5)
- Centralize `CODE_EXTENSIONS` in `_lib.py` (Idea 6)
- Merge `test_quality.py` into `qa_runner.py` as a mode (Idea 8)
- Align production standards prose with regex patterns (Idea 9)

These five changes eliminate DUP-1 through DUP-6. Estimated: 4-5 hours.

### Tier 3: Harden Quality (The Real Goal — Two Sub-Tiers)

**Tier 3A — Prevent Bad Plans from Entering Pipeline:**

- **Plan validator** catches vague plans before they become vague code (Idea 2)
- **Plan must list test files** for every production file in Changes table (Idea 13, Level 1)
- **Untested file justification** forces explicit acknowledgment of coverage gaps (Idea 16)

**Tier 3B — Prevent Bad Tests from Passing Gates:**

- **Weak assertion detection** catches `assert result is not None` (Idea 3)
- **Negative test requirement** for validation-related criteria (Idea 11)
- **Coverage floor per story** — 80% of changed production files must have tests (Idea 18)
- **Test-to-file verification** ensures planned test files actually exist and import the module (Idea 13, Level 2)
- **Public API coverage** flags test files that exist but only test trivial behavior (Idea 15)

**Tier 3C — Prevent Bad Merges from Reaching Feature Branch:**

- **Cumulative regression** via single test command after every merge (Idea 12)
- **Worker verification receipt** so Ralph validates QA was actually run (Idea 10)

**Tier 3D — Plan-Level Coverage Architecture (Longer Term):**

- **Integration test ratio enforcement** tied to Data Flow section (Idea 14)
- **CI parity enforcement** flags tests that only run locally (Idea 17)

Estimated Tier 3 total: 8-12 hours.

### Why This Catches the "42% Untested" Problem

The AI's gaming strategy was:

1. Skip hard files during implementation ← **Caught by Idea 13 (plan must list test files) + Idea 16 (justify gaps)**
2. Write impressive tests for easy files ← **Caught by Idea 18 (per-story coverage floor) + Idea 15 (API coverage check)**
3. Make tests look thorough with parametrize/edge cases ← **Already caught by existing test_quality.py**
4. All quality gates say PASS ← **Closed by Tier 3B (new gates for assertion depth, negative tests, file coverage)**

The key insight is that enforcement must happen at TWO levels:

- **Plan level**: The AI must declare what it will test BEFORE building. Silent omission is a plan validator failure.
- **QA level**: The AI must actually create the tests it declared. Missing test files or trivial test files are QA failures.

Neither level alone is sufficient. Plan-level-only lets the AI declare tests then skip creating them. QA-level-only lets the AI create tests that technically exist but don't test anything meaningful. Both together create a closed loop.

### What Not To Do

- **Don't require 100% file coverage** — some files (constants, type definitions, pure config) don't need direct tests. The 80% floor + justification table handles this.
- **Don't use mutation testing yet** — mutation testing (changing code and verifying tests fail) is the gold standard for test quality but is computationally expensive and complex to integrate. The weak assertion + API coverage checks are 80% of the value at 20% of the cost.
- **Don't block on integration test ratio initially** — start as WARN, upgrade to FAIL after calibrating thresholds on real projects.
- **Don't parse pytest markers for CI parity in v1** — this requires decorator parsing which is complex. Start with the simpler checks (file coverage, assertion depth) and add marker analysis later.

## Sources

### Project Docs Read

- `PROJECT_BRIEF.md` — project context, v4.0 tech stack
- `.claude/docs/ARCHITECTURE.md` — system diagram, hook chain, components
- `.claude/docs/PLAN.md` — current plan (Workflow v4, 10 stories all passed)
- `.claude/docs/HANDOFF.md` — last session (quality enforcement upgrade, 127 tests)
- `.claude/docs/knowledge/lessons.md` — template only (no entries)
- `.claude/docs/brainstorms/2026-03-01-workflow-v4-autonomous-excellence.md` — v4 brainstorm (12 ideas, 9 implemented)

### Source Code Analyzed

- `.claude/hooks/_lib.py` — PROD_VIOLATION_PATTERNS (13 patterns), scan_file_violations(), scan_test_quality(), CODE_EXTENSIONS analysis
- `.claude/hooks/qa_runner.py` — 12-step pipeline, triple scanning issue, phase-type relevance matrix
- `.claude/hooks/post_write_prod_scan.py` — write path bug (writes to legacy file, not .workflow-state.json)
- `.claude/hooks/stop_verify_gate.py` — read path (reads from .workflow-state.json correctly)
- `.claude/hooks/post_bash_capture.py` — clear path (clears .workflow-state.json correctly)
- `.claude/hooks/test_quality.py` — thin wrapper analysis (193 lines, 2 function calls)
- `.claude/skills/audit/SKILL.md` — legacy path checks (Sections 6, 7)
- `.claude/skills/ralph/SKILL.md` — spot-check scope (current story only)
- `.claude/agents/ralph-worker.md` — qa_runner optional designation, inline QA prose
- `.claude/agents/builder.md` — Plan Sanity Check duplication
- `CLAUDE.md` — "16-step" references, production standards prose

### Real-World Evidence (User-Provided)

- NBA sports parlay system audit: 3,800 tests, 152 unit test files, 27 regression files — but 42% of production files untested. Engine/ 36%, evaluation/ 25%, governance/ 0%. 5 integration tests for 145+ modules. Golden path E2E tests skip in CI. All existing quality gates report PASS despite these gaps.

### Exploration Agent Findings

- Deep analysis of all hooks, agents, skills, and test files
- Identified prod violations write/read mismatch
- Mapped all CODE_EXTENSIONS inconsistencies
- Identified triple scanning in qa_runner.py
- Catalogued all duplication across files

**Implement in three tiers: Fix Bugs → Simplify → Harden Quality.**

### Tier 1: Fix Bugs (Do First, Non-Negotiable)

- **Idea 1**: Fix the three critical bugs. This is not optional — the prod violations stop gate is broken, the docs are wrong, and the audit checks dead paths. Estimated: 2-3 hours.

### Tier 2: Simplify (Reduce Surface Area)

Combine **Ideas 4 + 5 + 6 + 8 + 9**:

- Make `qa_runner.py` mandatory for workers, remove inline QA prose from `ralph-worker.md` (Idea 4)
- Scan once, partition results in `qa_runner.py` (Idea 5)
- Centralize `CODE_EXTENSIONS` in `_lib.py` (Idea 6)
- Merge `test_quality.py` into `qa_runner.py` as a mode (Idea 8)
- Align production standards prose with regex patterns (Idea 9)

These five changes together eliminate DUP-1 through DUP-6, reduce file count, and make the codebase smaller and more consistent. Estimated: 4-5 hours.

### Tier 3: Harden Quality (The Real Goal)

Combine **Ideas 2 + 3 + 7/12 + 10 + 11**:

- `plan_validator.py` catches vague plans before they enter the pipeline (Idea 2)
- Enhanced `scan_test_quality()` catches weak assertions and happy-path-only tests (Idea 3)
- Cumulative regression via single test command after every merge (Idea 12, simpler than Idea 7)
- Worker verification receipt so Ralph validates QA was actually run (Idea 10)
- Negative test requirement for validation-related criteria (Idea 11)

These five changes close GAP-1 through GAP-5 — the actual failure modes where bad code slips through. Estimated: 6-8 hours.

### Why This Order

Tier 1 first because the prod violations bug means the stop gate is partially broken right now. Tier 2 before Tier 3 because simplification makes the codebase easier to modify — adding quality gates to a duplicated codebase means adding them in multiple places. Tier 3 last because it builds on the simplified foundation.

### What Not To Do

- **Don't add GAP-5 (semantic verification)** — verifying that code "does what the criterion says" requires code understanding that's beyond regex/AST analysis. The combination of better plans (Idea 2), stronger tests (Ideas 3+11), and verified QA execution (Idea 10) addresses this indirectly.
- **Don't over-tune plan_validator.py** — start with 3-4 checks (measurable verbs, no placeholders, R-marker format, testing strategy present). Add more checks only when real false negatives are found.
- **Don't make test depth enforcement FAIL-only** — start with WARN for weak assertions and happy-path-only detection. Upgrade to FAIL after calibrating false positive rate.

## Sources

### Project Docs Read

- `PROJECT_BRIEF.md` — project context, v4.0 tech stack
- `.claude/docs/ARCHITECTURE.md` — system diagram, hook chain, components
- `.claude/docs/PLAN.md` — current plan (Workflow v4, 10 stories all passed)
- `.claude/docs/HANDOFF.md` — last session (quality enforcement upgrade, 127 tests)
- `.claude/docs/knowledge/lessons.md` — template only (no entries)
- `.claude/docs/brainstorms/2026-03-01-workflow-v4-autonomous-excellence.md` — v4 brainstorm (12 ideas, 9 implemented)

### Source Code Analyzed

- `.claude/hooks/_lib.py` — PROD_VIOLATION_PATTERNS (13 patterns), scan_file_violations(), scan_test_quality(), CODE_EXTENSIONS analysis
- `.claude/hooks/qa_runner.py` — 12-step pipeline, triple scanning issue, phase-type relevance matrix
- `.claude/hooks/post_write_prod_scan.py` — write path bug (writes to legacy file, not .workflow-state.json)
- `.claude/hooks/stop_verify_gate.py` — read path (reads from .workflow-state.json correctly)
- `.claude/hooks/post_bash_capture.py` — clear path (clears .workflow-state.json correctly)
- `.claude/hooks/test_quality.py` — thin wrapper analysis (193 lines, 2 function calls)
- `.claude/skills/audit/SKILL.md` — legacy path checks (Sections 6, 7)
- `.claude/skills/ralph/SKILL.md` — spot-check scope (current story only)
- `.claude/agents/ralph-worker.md` — qa_runner optional designation, inline QA prose
- `.claude/agents/builder.md` — Plan Sanity Check duplication
- `CLAUDE.md` — "16-step" references, production standards prose

### Exploration Agent Findings

- Deep analysis of all hooks, agents, skills, and test files
- Identified prod violations write/read mismatch
- Mapped all CODE_EXTENSIONS inconsistencies
- Identified triple scanning in qa_runner.py
- Catalogued all duplication across files

---

## Build Strategy

### Module Dependencies

```
_lib.py (foundation)
    ├── CODE_EXTENSIONS (new export, Idea 6)
    ├── scan_file_violations() (existing, scan-once cache support, Idea 5)
    ├── scan_test_quality() (enhanced: weak assertions + API coverage, Ideas 3, 15)
    ├── check_test_file_coverage() (new: file-level coverage mapping, Idea 13)
    ├── validate_plan_quality() (new: measurable verbs, test file column, Ideas 2, 13, 16)
    └── update_workflow_state() (existing, needs new caller from prod scan, Idea 1)
         │
         ├── post_write_prod_scan.py (fix: use update_workflow_state, Idea 1)
         ├── qa_runner.py (Idea 5: scan once; Idea 8: test-quality mode; Idea 18: story coverage)
         ├── plan_validator.py (new CLI: Idea 2 + Idea 13 Level 1 + Idea 16)
         ├── test_quality.py (demote to thin wrapper around qa_runner, Idea 8)
         └── stop_verify_gate.py (already correct, reads .workflow-state.json)
              │
              ├── ralph-worker.md (Idea 4: mandate qa_runner, remove inline QA)
              ├── ralph/SKILL.md (Idea 10: verification receipt; Idea 12: cumulative regression)
              ├── plan/SKILL.md (Idea 13: enhanced Changes table; Idea 16: untested file justification)
              ├── audit/SKILL.md (Idea 1: fix unified state paths)
              └── CLAUDE.md (Idea 1: 12-step refs; Idea 9: aligned standards)
```

### Build Order

**Phase 1 — Bug Fixes (foundation)**: Fix prod violations write path, CLAUDE.md 16→12 references, audit legacy paths. All independent within phase.

**Phase 2 — Centralize & Simplify (foundation)**: Move CODE_EXTENSIONS to `_lib.py`. Scan-once cache in qa_runner.py. Merge test_quality mode. Align production standards. Must complete before Phase 3.

**Phase 3 — Worker Hardening (module)**: Make qa_runner.py mandatory. Remove inline QA from ralph-worker.md. Add verification receipt validation to Ralph STEP 6. Depends on Phase 2.

**Phase 4 — Plan Validator (module)**: New `plan_validator.py` with: measurable-verb check, enhanced Changes table validation (test file column required), untested file justification check. Update plan/SKILL.md template. Independent of Phase 3.

**Phase 5 — Test Depth Enforcement (module)**: Enhance `scan_test_quality()` for: weak assertions, happy-path detection, negative test requirement for validation criteria. Add public API coverage check. Independent of Phase 4.

**Phase 6 — Story Coverage Gate (integration)**: New qa_runner step: per-story file coverage floor (80% of changed production files must have tests). Test-to-file verification (planned test files must exist and import module). Depends on Phases 4+5.

**Phase 7 — Cumulative Regression (integration)**: Add regression command to workflow.json. Wire into Ralph STEP 6 spot-check (run full test suite after every merge). Depends on Phase 3.

**Phase 8 — Documentation & Full Test Suite (integration)**: Update all docs. Run full test suite. Verify end-to-end: plan validation → worker build → QA with new steps → story coverage check → cumulative regression → verification receipt.

### Testing Pyramid

- **Unit tests (70%)**: Each new function in `_lib.py` (plan validation, weak assertion detection, API coverage, file coverage mapping, CODE_EXTENSIONS export). Each bug fix verified by specific test. Scan-once caching tested with known violation sets. Plan validator tested against sample PLAN.md files (good and bad plans).
- **Integration tests (20%)**: Hook chain end-to-end: edit file → prod scan writes to `.workflow-state.json` → stop gate reads from state → blocks correctly. qa_runner full pipeline with test-quality mode and story coverage step. Plan validator integrated with qa_runner plan conformance step.
- **E2E tests (10%)**: Subprocess tests simulating actual hook invocation. Full qa_runner pipeline on a sample project with intentional coverage gaps (verify they're caught). Plan validator against a real PLAN.md with missing test file columns (verify it rejects).

Estimated ratio: 70/20/10. Key difference from previous sprints: must include **negative test cases for the quality gates themselves** — e.g., a test that submits a plan with vague criteria and verifies the plan validator rejects it.

### Risk Mitigation Mapping

- **Risk**: Plan validator false positives block legitimate plans → **Mitigation**: Start with WARN severity, upgrade to FAIL after calibrating on 3+ real plans. Keep check list small (5-6 checks initially).
- **Risk**: Weak assertion detection false positives → **Mitigation**: Start as WARN. Only flag `assert x is not None` and `assert x` patterns initially (high confidence). Don't flag `assertTrue(result)` in v1.
- **Risk**: Coverage floor per story too strict → **Mitigation**: 80% threshold with explicit justification escape hatch. Pure config/constant files can be listed in "Untested Files" table.
- **Risk**: API coverage check catches false positives from string matching → **Mitigation**: Use `import {module}` + function name co-occurrence as heuristic. Start as WARN. Upgrade to AST parsing later if needed.
- **Risk**: Cumulative regression slows sprint significantly → **Mitigation**: Single `regression` command (full suite once). Monitor timing — if >2 min, use `--tb=line`.
- **Risk**: Making qa_runner mandatory breaks workers → **Mitigation**: qa_runner.py is committed to `.claude/hooks/` (available in worktrees). Fallback: if qa_runner.py fails to execute, Ralph treats as FAIL (not silent pass).
- **Risk**: Enhanced Changes table is too verbose → **Mitigation**: Test File column is 1 extra column per row. The information is valuable for traceability. If it's too much, allow grouped entries (e.g., "tests/unit/test\_{module}.py" pattern).
- **Risk**: AI writes boilerplate "Untested Files" justifications → **Mitigation**: Plan validator checks that "Tested Via" column references an actual test file that exists. Justification "tested transitively" must name the specific transitive test file.

### Recommended Build Mode

**Ralph Mode** for all phases. Rationale:

- Every phase has clear, measurable acceptance criteria
- The test infrastructure is mature (547 existing tests provide regression safety)
- Phase dependencies are clean (1-2 foundation, 3-5 parallel modules, 6-8 integration)
- Confidence is HIGH — fixing known bugs and applying known patterns
- The new quality gates will be tested against their own codebase (dogfooding)

Exception: Phase 4 (plan_validator.py) benefits from initial calibration against real PLAN.md files. Consider Manual Mode for the heuristic tuning, then switch to Ralph for the remaining implementation.
