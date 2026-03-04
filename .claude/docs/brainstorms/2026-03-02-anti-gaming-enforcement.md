# Brainstorm: Anti-Gaming Enforcement & Context Efficiency

**Date**: 2026-03-02
**Problem**: AI agents writing code can game structural quality checks by producing plausible-looking but non-functional code with hollow tests that assert nothing meaningful — and the current workflow catches code quality violations (secrets, TODOs, debug prints) but not behavioral correctness failures (unwired code, pass-through implementations, wrong-but-consistent code+tests).

## Part 1: Anti-Gaming / Silent Failure Prevention

### Context: The Gaming Problem

When an AI writes BOTH the production code AND the tests, it controls both sides of the verification equation. Current defenses are structural:

| Current Check              | What It Catches                                          | How AI Games It                                      |
| -------------------------- | -------------------------------------------------------- | ---------------------------------------------------- |
| Self-mock detection        | `mock.patch('module.func')` where func matches test name | Name the test differently from the mocked function   |
| Assertion-free detection   | Tests with zero assertions                               | Add `assert result is not None` — proves nothing     |
| Weak assertion detection   | `assert x is not None`, bare `assert x`                  | Use `assert len(result) > 0` or `isinstance()`       |
| Story file coverage (80%)  | No test file imports the module                          | Import the module, never exercise it meaningfully    |
| R-marker traceability      | No `# Tests R-P1-01` comment in tests                    | Stamp the marker on any test, including trivial ones |
| Production scan (15 rules) | Regex patterns for secrets, debug, TODOs                 | Write clean-looking code that does nothing           |

The NBA production system has 196K lines, 4,812 tests, copula math, Kelly sizing, and kill-switch infrastructure. A hollow implementation in `risk/barbell_kelly.py` that returns `0.0` instead of computing real position sizes could pass every structural check while silently disabling the entire risk layer.

---

### Idea 1: Differential Line Coverage Gate

**Description**: After a worker completes a story, run `pytest --cov` with coverage.py, generate a JSON coverage report, then compute coverage ONLY on the lines the worker changed (using `git diff` to identify changed lines). Require >= 90% line coverage on changed production code. Branch coverage on changed lines is even better — it catches `if/else` paths where only one branch is tested.

**Implementation approach**:

- Use `coverage.py` JSON report (provides per-file line-by-line execution data)
- Use `diff-cover` package (already does exactly this — compares coverage XML with git diff)
- Or build a lightweight version: parse `coverage.json` + `git diff --unified=0` to extract changed line numbers, cross-reference
- Add as QA Step 8.5 or replace current Step 8 (which is often SKIP)
- Command: `pytest --cov={changed_modules} --cov-branch --cov-report=json && python .claude/hooks/diff_coverage_check.py --min-coverage 90`

**What it catches**:

- Hollow implementations: `def validate(data): return True` — if no test exercises this line with meaningful assertions, coverage shows the function body was never reached via a test that actually checked the output
- Unwired code: new functions that are never called — coverage shows 0% on those lines
- Dead branches: `if complex_condition:` where only the `else` path is tested

**What it DOESN'T catch**:

- Wrong-but-consistent: if the test calls the function and the function returns wrong values that the test asserts, both lines are "covered"
- Overtested simple paths: 100% coverage on `return True` is still gaming

- **Pros**: Uses battle-tested tools (coverage.py, diff-cover). Directly measures "did tests exercise the new code?" Not bypassable by naming tricks. Low false-positive rate. Fast to run (seconds).
- **Cons**: Coverage measures execution, not correctness. An AI can write tests that execute every line but assert nothing meaningful about the results. Requires pytest + coverage.py in the target project. Adds ~5-15s to QA pipeline.

---

### Idea 2: Mutation Testing Gate (Targeted)

**Description**: After tests pass, inject small faults (mutations) into the CHANGED lines only — flip operators, swap constants, remove return statements, negate conditions — then re-run the tests that cover those lines. If tests still pass after a mutation, those tests are hollow (they don't actually verify the code's behavior). This is the gold standard for test quality validation.

**Implementation approach**:

- Use `mutmut` (most actively maintained, 1.5x faster mutant generation, checkpointing support) or `cosmic-ray` (broadest operator set, parallel execution)
- Scope mutations to ONLY changed files (not full codebase — that would take hours on 196K lines)
- Target: kill rate >= 70% on changed lines (industry standard for well-tested code)
- Command: `mutmut run --paths-to-mutate={changed_files} --tests-dir={test_dir} --runner="pytest {relevant_tests}"`
- Parse mutmut JSON results, report survived mutants as evidence of hollow tests

**What it catches**:

- Wrong-but-consistent: if the AI writes `return 0.0` and the test asserts `== 0.0`, mutating `0.0` to `1.0` makes the test fail — mutation killed. BUT if the AI writes `return calculated_value` and the test asserts `is not None`, mutating `calculated_value` to `0.0` won't make the test fail — mutation survives, exposing the hollow assertion
- Hollow tests of ALL types: any test that doesn't actually validate behavior will let mutations survive
- Off-by-one errors, boundary condition gaps, missing error handling

**What it DOESN'T catch**:

- Completely unwired code (no mutations needed — coverage already catches this)
- Architecturally wrong solutions (correct behavior, wrong design)
- Performance issues

- **Pros**: The strongest possible test quality signal. Directly answers "do these tests actually verify this code's behavior?" Not gameable without writing genuinely correct tests. Academic research consensus: mutation score is the most reliable indicator of test suite effectiveness.
- **Cons**: SLOW. Even targeted mutation testing on 5-10 files can take 5-30 minutes depending on test suite speed. Mutmut is Python-only (fine for NBA system, limits portability). Some mutations are equivalent (syntactically different but semantically identical) causing false "survived" reports. Requires mutmut/cosmic-ray as a dependency. May be too slow for the Ralph inner loop — better as a final gate.

---

### Idea 3: Call-Graph Wiring Verification

**Description**: After a worker adds new code, use Python's AST module to verify that every new public function/class is actually imported and called from somewhere in the project. This catches the "unwired code" gaming vector — where an AI creates a function but never connects it to the call graph.

**Implementation approach**:

- Parse changed files with `ast` module, extract all new `def` and `class` definitions (compare against pre-change AST)
- For each new public symbol (not starting with `_`), search the codebase for imports or references
- Exception: test functions (`test_*`) are allowed to be "leaf" nodes
- Can also use `vulture` (dead code detector) scoped to changed files: `vulture {changed_files} {project_root} --min-confidence 80`
- Add as sub-check in QA Step 10 (Plan Conformance) or new Step 10.5

**What it catches**:

- New functions/classes that exist but are never imported or called
- New parameters added to existing functions but never passed by any caller
- New modules created but never imported by any other module

**What it DOESN'T catch**:

- Functions that ARE called but do nothing meaningful (hollow implementations)
- Functions wired in but with wrong behavior
- Dynamic imports (`importlib.import_module`) which AST analysis can't trace

- **Pros**: Fast (AST parsing is milliseconds). Zero external dependencies (Python stdlib `ast` module). Catches a specific, common gaming vector. No false positives for correctly wired code.
- **Cons**: Python's dynamic nature means `getattr`, `importlib`, plugin systems, etc. can create false positives. Only catches one gaming vector (unwired code), not the broader problem. Needs careful handling of `__init__.py` re-exports.

---

### Idea 4: Existing-Test Behavioral Delta Check

**Description**: Before the worker starts, snapshot which existing tests pass. After the worker finishes, run ONLY the pre-existing tests (not the worker's new tests). If the worker claims to have added integration code but zero existing tests changed behavior (same pass/fail, same assertion values), that's suspicious — the code may not actually be wired into the system.

**Implementation approach**:

- At STEP 4 (Safety Checkpoint), run `pytest --co -q` to list all existing test names → save as baseline
- After worker returns, run ONLY the baseline tests: `pytest {baseline_test_list} -v --tb=short`
- Compare: same pass count, same fail count, same test names → no behavioral change detected
- For integration stories, flag if zero existing tests were affected (expected: at least some tests should observe the new behavior)
- For foundation stories (new modules), this check is informational only (new code may not affect existing tests)

**What it catches**:

- Code that claims to integrate with existing modules but doesn't actually affect their behavior
- Code that's completely isolated (never called by anything existing tests exercise)

**What it DOESN'T catch**:

- Foundation phases where new code is genuinely independent
- Subtle behavior changes that don't affect test outcomes (e.g., performance improvements)
- Code that's wired in but only affects paths not covered by existing tests

- **Pros**: Uses only existing tests the AI didn't write — can't be gamed. Zero new dependencies. Conceptually simple. Fast (runs existing tests that already run in regression).
- **Cons**: High false-positive rate for foundation/module phases where new code IS supposed to be independent. Only meaningful for integration/e2e phases. Requires careful phase-type gating. Informational rather than a hard gate — suspicious result doesn't prove gaming.

---

### Idea 5: Assertion Depth Scoring

**Description**: Go beyond binary "has assertions / doesn't have assertions" to score assertion QUALITY. Assign points based on assertion type — value comparisons score higher than truthiness checks. Require a minimum assertion depth score per test function.

**Scoring model**:

```
0 points: assert x (bare truthiness)
0 points: assert x is not None
1 point:  assert isinstance(x, Type)
2 points: assert x == expected_value
2 points: assert x != wrong_value
3 points: assert x == expected AND assert y == expected (multiple value checks)
3 points: assertRaises(SpecificError, func, bad_input)
4 points: assert computed_value == pytest.approx(expected, rel=1e-6)  # numerical precision
4 points: assert all(x > threshold for x in results)  # invariant check across collection
5 points: assert before != after (state change verification)
```

Minimum score per test: 2 (must have at least one real value comparison). Tests scoring 0-1 are flagged as "shallow."

**Implementation approach**:

- Extend `scan_test_quality()` in `_lib.py` to compute per-test assertion depth score
- Parse test function bodies, classify each assertion by type using regex patterns
- Sum scores per test function, flag functions below threshold
- Report: "3 tests have assertion depth < 2: test_foo (score=0), test_bar (score=1), test_baz (score=0)"

**What it catches**:

- Tests that only check truthiness (`assert result`, `assert result is not None`)
- Tests that only type-check (`isinstance`) without value verification
- Tests that use assertions but never compare against specific expected values

**What it DOESN'T catch**:

- Tests with high assertion scores that compare against WRONG expected values (AI controls both sides)
- Tests that compare against values derived from the function itself (circular validation)

- **Pros**: Incremental improvement over current binary detection. No external dependencies. Fast (regex-based). Gives actionable feedback ("test_foo needs stronger assertions").
- **Cons**: Still gameable — AI just writes `assert result == 42` where 42 is the wrong answer. Scoring model needs tuning. Regex-based classification may misclassify complex assertion patterns.

---

### Idea 6: Property-Based Testing Requirement

**Description**: For functions that transform data (pure functions, calculations, validators), require at least one property-based test using `hypothesis`. Property tests generate random inputs and verify INVARIANTS — properties that must always hold regardless of input. The AI can't game this because it doesn't control the inputs.

**Implementation approach**:

- For stories touching calculation/transformation code, require `@given(...)` decorated tests
- The prd.json acceptance criteria can specify `testType: "property"` for criteria where property testing is appropriate
- QA Step 9 (mock audit) extended to check: if criterion.testType == "property", verify a `@given` test exists
- Properties to verify: output type, output range bounds, monotonicity, idempotency, inverse relationships

**Example for NBA system**:

```python
@given(fair_prob=st.floats(0.01, 0.99), odds=st.floats(1.01, 100.0))
def test_kelly_fraction_bounded(fair_prob, odds):
    """Kelly fraction must be in [0, max_bet_pct]."""
    result = compute_kelly_fraction(fair_prob, odds)
    assert 0 <= result <= 0.05  # max 5% of bankroll
```

The AI can't fake this — hypothesis generates thousands of random inputs, and the invariant must hold for ALL of them.

**What it catches**:

- Hollow implementations: `return 0.0` fails because hypothesis finds inputs where 0.0 violates the invariant
- Off-by-one errors, boundary violations, type errors on unexpected inputs
- Functions that work for the happy path but break on edge cases

**What it DOESN'T catch**:

- Code that satisfies invariants but computes wrong specific values
- Integration issues (property tests are unit-level)
- Non-functional requirements (performance, latency)

- **Pros**: Strongest anti-gaming for pure functions. AI cannot control inputs. Catches edge cases humans/AI miss. The NBA system already has hypothesis in its pytest.ini. Forces tests to verify mathematical properties, not just example values.
- **Cons**: Not applicable to all code (I/O, side effects, UI). Requires `hypothesis` dependency. Property-based tests can be slow. Writing good properties requires domain knowledge — the AI might write trivially-true properties (`assert result is not None`). Only works for stateless/pure functions.

---

### Idea 7: Semantic Diff Review Step

**Description**: After the worker returns code, run a lightweight semantic analysis that compares the PLAN.md's stated behavior against the actual code diff. Extract function signatures, return types, and key logic patterns from the diff and cross-reference against what the plan said should be implemented.

**Implementation approach**:

- Parse the git diff for the story
- Extract: new function signatures, return statements, conditional logic, imports added
- Cross-reference against PLAN.md's Interface Contracts section
- Flag mismatches: "Plan says function returns `EdgeResult` but implementation returns `float`"
- Flag suspicious patterns: function with >5 parameters but only 1-2 are used in the body
- Flag: new functions with single-line bodies that just `return` a constant or `pass`

**What it catches**:

- Plan says "implement validation with 5 rules" but implementation has `return True`
- Plan says "integrate with correlations engine" but no import of correlations module
- Functions with unused parameters (signature matches plan but body ignores inputs)

**What it DOESN'T catch**:

- Implementations that structurally match the plan but compute wrong values
- Subtle logic errors in complex functions

- **Pros**: Directly validates plan-to-code alignment. Catches the most obvious forms of gaming (empty implementations, wrong signatures). No external dependencies.
- **Cons**: Requires sophisticated plan parsing. High false-positive risk on refactoring phases. The plan itself might be vague. Implementation complexity is significant — essentially building a mini code review bot.

---

## Part 2: Context Efficiency & Complexity Reduction

### Current Context Budget

**Always loaded** (CLAUDE.md is auto-loaded, ~10.8K chars = ~3K tokens):
| File | Size | Tokens (est.) |
|---|---|---|
| CLAUDE.md | 10,782 bytes | ~3,000 |

**Loaded on-demand per skill invocation**:
| Skill | Size | Tokens (est.) |
|---|---|---|
| ralph/SKILL.md | 17,639 bytes | ~5,000 |
| plan/SKILL.md | 11,121 bytes | ~3,200 |
| audit/SKILL.md | 8,218 bytes | ~2,400 |
| build-system/SKILL.md | 6,511 bytes | ~1,900 |
| verify/SKILL.md | 4,919 bytes | ~1,400 |
| brainstorm/SKILL.md | 3,183 bytes | ~900 |
| handoff/SKILL.md | 2,452 bytes | ~700 |
| health/SKILL.md | 1,956 bytes | ~560 |
| refresh/SKILL.md | 1,293 bytes | ~370 |
| learn/SKILL.md | 996 bytes | ~280 |
| decision/SKILL.md | 897 bytes | ~260 |

**Loaded when agent is invoked**:
| Agent | Size | Tokens (est.) |
|---|---|---|
| ralph-worker.md | 6,400 bytes | ~1,800 |
| architect.md | 5,455 bytes | ~1,600 |
| builder.md | 4,180 bytes | ~1,200 |
| librarian.md | 1,018 bytes | ~290 |

**Python backend** (never loaded as context, but must be maintained):
| File | Lines |
|---|---|
| \_lib.py | 1,851 |
| qa_runner.py | 1,220 |
| Total | 3,071 |

---

### Idea 8: Remove Research References (Quick Win)

**Description**: The user confirmed this is now a coding-only workflow. Remove all remaining research references from:

- `architect.md` Step 3 ("Research External Dependencies" — references WebSearch, Context7, arXiv)
- `plan/SKILL.md` Step 3 ("Research")
- `brainstorm/SKILL.md` (references OpenAlex/arXiv)
- `PLAN.md` (references to research servers in the old context window plan)
- `prompt.md` (entire file is a research execution prompt — delete or gitignore)
- `research/` directory (if still present)

**Impact**: Removes ~500-1000 tokens of research-specific instructions from skill/agent context. More importantly, prevents the AI from spending context/time on research tool invocations during coding tasks.

- **Pros**: Quick, zero risk, removes dead weight.
- **Cons**: Loses the ability to research external dependencies during planning. Mitigated by keeping WebSearch/Context7 available as MCP tools — they just won't be prompted for in skill instructions.

---

### Idea 9: CLAUDE.md Deduplication with Hooks

**Description**: CLAUDE.md contains written rules (like "No TODO comments", "No hardcoded secrets") that the hooks ALREADY enforce programmatically. These duplicate instructions burn context tokens. Replace the 15-rule Production-Grade Code Standards section with a compact reference: "Production standards enforced by `post_write_prod_scan.py` — see `_lib.py` PROD_VIOLATION_PATTERNS for the full rule set."

**Current duplication**: The 15 rules in CLAUDE.md (~800 bytes) are also encoded as regex patterns in `_lib.py` PROD_VIOLATION_PATTERNS (~1,200 bytes). The CLAUDE.md version is for AI instruction; the \_lib.py version is for programmatic enforcement. Both exist in context when the AI is writing code.

**What to keep in CLAUDE.md**: The 3 rules that hooks CAN'T enforce (rules 3, 8, 9 — proper error handling, input validation, resource cleanup — these require judgment, not regex).

**Impact**: Saves ~500 tokens from the always-loaded CLAUDE.md context. Reduces instruction noise — fewer rules means better adherence to the remaining ones.

- **Pros**: Direct token savings. Removes redundancy that can confuse the AI (two places saying the same thing with slightly different wording).
- **Cons**: If hooks fail to load (Python not in PATH), the written rules in CLAUDE.md are the only defense. Risk is low since hook failure causes exit 2 (blocks the action anyway).

---

### Idea 10: Slim ralph/SKILL.md

**Description**: At 17,639 bytes (~5K tokens), ralph/SKILL.md is the largest skill file. It contains verbose step-by-step instructions with extensive inline examples, error recovery tables, and display formatting templates. Much of this could be compressed without losing functionality.

Specific reductions:

- Display template blocks (the `---` bordered output sections) — the AI doesn't need exact ASCII formatting instructions; it can produce readable output without templates
- Error Recovery table — move to a separate `ralph-recovery.md` that's only loaded on error
- STEP 6 QA receipt validation — this is ~40 lines of detailed sub-steps that could be condensed to a checklist
- Inline JSON examples — the schema is already defined by qa_runner.py output; don't repeat it

**Estimated savings**: 3,000-5,000 bytes (800-1,400 tokens) from the skill file loaded every time `/ralph` runs.

- **Pros**: Significant token savings on the most-used skill. Less instruction noise for the AI.
- **Cons**: Risk of under-specifying behavior if compressed too aggressively. The verbose format was intentional — ensuring the AI follows exact steps. Testing needed to verify compressed version produces equivalent behavior.

---

### Idea 11: \_lib.py Modularization

**Description**: `_lib.py` is 1,851 lines in a single file. While it's never loaded as AI context, it's maintained by the AI when bugs are found or features added. Breaking it into focused modules would reduce the context needed to modify any single area:

```
_lib.py (1,851 lines) →
  _lib_core.py      (~200 lines: paths, state, stdin parsing, audit log)
  _lib_violations.py (~300 lines: PROD_VIOLATION_PATTERNS, scan_file_violations)
  _lib_test_quality.py (~300 lines: scan_test_quality, assertion analysis)
  _lib_traceability.py (~300 lines: R-markers, plan parsing, verification log)
  _lib_coverage.py   (~200 lines: story file coverage, public API coverage)
  _lib.py            (~50 lines: re-export all public symbols for backward compat)
```

**Impact**: When a hook needs modification, the AI only reads the relevant 200-300 line module instead of 1,851 lines. Each module fits easily in a single Read tool call.

- **Pros**: Reduces context per-modification. Cleaner separation of concerns. Easier to test individual modules. Each file has a single responsibility.
- **Cons**: Migration complexity — all hooks import from `_lib`, need backward-compatible re-exports. More files to maintain. Import chain gets deeper. Risk of circular imports if not careful.

---

## Recommendation

### Highest-Impact Anti-Gaming Combination

**Implement in this order** (each builds on the previous):

1. **Idea 1: Differential Line Coverage** (FIRST — quick win, high impact)
   - Closes the biggest gap: "did tests actually exercise the new code?"
   - Uses existing tools (coverage.py + diff-cover or lightweight custom script)
   - Fast to run (<15s), no new heavy dependencies
   - Catches unwired code, hollow implementations, dead branches
   - Add as QA Step 8 replacement (current Step 8 is usually SKIP)

2. **Idea 3: Call-Graph Wiring Check** (SECOND — complements coverage)
   - AST-based, zero dependencies, milliseconds to run
   - Catches the specific "function exists but nothing calls it" vector
   - Add as sub-check in QA Step 10 (Plan Conformance)

3. **Idea 5: Assertion Depth Scoring** (THIRD — strengthens test quality)
   - Incremental improvement over current binary assertion detection
   - Extend existing `scan_test_quality()` in `_lib.py`
   - No new dependencies, fast, actionable feedback

4. **Idea 2: Mutation Testing** (FOURTH — final quality gate for critical paths)
   - Use `mutmut` scoped to changed files only
   - Too slow for every story — use as optional `--phase-type e2e` step or `/audit` step
   - Reserve for integration/e2e phases where stakes are highest
   - Can be run as the cumulative regression enhancement post-merge

5. **Idea 6: Property-Based Testing** (FIFTH — for calculation-heavy stories)
   - The NBA system already has hypothesis installed
   - Add `testType: "property"` to prd.json schema for criteria where applicable
   - Architect specifies which criteria need property tests in PLAN.md
   - QA Step 9 validates property test presence when required

### Context Efficiency Priority

1. **Idea 8: Remove research references** — immediate, zero risk
2. **Idea 9: CLAUDE.md deduplication** — ~500 token savings from always-loaded context
3. **Idea 10: Slim ralph/SKILL.md** — ~1,000 token savings on most-used skill
4. **Idea 11: \_lib.py modularization** — reduces maintenance context, not runtime context

### What NOT to do

- **Idea 4 (Existing-Test Behavioral Delta)**: Too many false positives for foundation/module phases. The insight is correct but the signal-to-noise ratio is poor. The regression step already covers this partially.
- **Idea 7 (Semantic Diff Review)**: Implementation complexity too high for the return. Plan parsing is fragile, and building a mini code-review bot is a project unto itself. Better to rely on the combination of coverage + wiring + assertion depth.

## Build Strategy

### Module Dependencies

```
Idea 1 (Diff Coverage) ← depends on: coverage.py, git diff parsing
  ↓
Idea 3 (Wiring Check)  ← depends on: Python ast module
  ↓
Idea 5 (Assertion Depth) ← depends on: existing _lib.py scan_test_quality
  ↓
Idea 2 (Mutation Testing) ← depends on: mutmut, Idea 1 (to scope mutations)
  ↓
Idea 6 (Property Testing) ← depends on: hypothesis, prd.json schema extension

Context efficiency (Ideas 8-11) are independent of anti-gaming work.
```

### Build Order

**Phase 1** (Anti-Gaming Foundation):

- Idea 1: Differential line coverage gate
- Idea 3: Call-graph wiring verification
- Idea 8: Remove research references
- Idea 9: CLAUDE.md deduplication
- Can build 1+3 in parallel with 8+9

**Phase 2** (Test Quality Hardening):

- Idea 5: Assertion depth scoring
- Idea 10: Slim ralph/SKILL.md

**Phase 3** (Advanced Gates):

- Idea 2: Mutation testing (optional, e2e-only gate)
- Idea 6: Property-based testing requirement
- Idea 11: \_lib.py modularization

### Testing Pyramid

- **Unit tests (70%)**: Each new `_lib.py` function (diff_coverage_check, wiring_check, assertion_depth_score) tested in isolation with fixture files
- **Integration tests (20%)**: Full QA pipeline runs with known-gaming test fixtures (hollow tests, unwired code, etc.) — verify the pipeline catches them
- **E2E tests (10%)**: Ralph worker dispatched against a synthetic story with known gaming patterns — verify the full loop rejects it

### Risk Mitigation Mapping

| Risk                                                         | Mitigation                                                                  |
| ------------------------------------------------------------ | --------------------------------------------------------------------------- |
| Diff coverage too strict (false fails on config/glue code)   | Exclude `__init__.py`, `conftest.py`, and files < 5 changed lines           |
| Wiring check false positives on dynamic imports              | Allowlist patterns: `importlib`, `getattr`, plugin registries               |
| Assertion depth gaming (AI writes `assert x == wrong_value`) | Combine with mutation testing — mutations will expose wrong expected values |
| Mutation testing too slow                                    | Scope to changed files only + budget timer (max 5 minutes)                  |
| \_lib.py modularization breaks imports                       | Keep `_lib.py` as re-export facade, run full test suite before/after        |

### Recommended Build Mode

**Ralph Mode** for Phase 1 — well-defined acceptance criteria (coverage gate works/doesn't work, wiring check catches/misses known patterns). Clear stories with testable outcomes. The irony of using Ralph to build anti-Ralph-gaming features is not lost, but the existing regression suite (671 tests) provides the safety net.

**Manual Mode** for Phase 2-3 — assertion depth scoring requires tuning the scoring model, and mutation testing integration requires experimentation with mutmut configuration. These are exploratory and need human judgment at each step.

## Sources

### Research

- [diff-cover (PyPI)](https://pypi.org/project/diff-cover/) — diff coverage tool
- [mutmut (GitHub)](https://github.com/boxed/mutmut) — Python mutation testing
- [cosmic-ray (GitHub)](https://github.com/sixty-north/cosmic-ray) — Python mutation testing
- [vulture (PyPI)](https://pypi.org/project/vulture/) — Python dead code detection
- [deadcode (PyPI)](https://pypi.org/project/deadcode/) — Python unused code detection
- [coverage.py API](https://coverage.readthedocs.io/en/latest/api_coverage.html) — programmatic coverage access
- [pytest-cov](https://pypi.org/project/pytest-cov/) — pytest coverage plugin
- [Mutation Testing with Mutmut (2026)](https://johal.in/mutation-testing-with-mutmut-python-for-code-reliability-2026/)
- [Detecting Silent Failures in Multi-Agentic AI](https://arxiv.org/html/2511.04032) — anomaly detection in agent systems
- [Taming Silent Failures: Framework for Verifiable AI Reliability](https://arxiv.org/html/2510.22224v1)
- [Testing AI-Generated Code: Practical Strategies](https://www.sitepoint.com/testing-ai-generated-code/)
- [Claude Code Best Practices](https://code.claude.com/docs/en/best-practices) — context optimization
- [Context Window Optimization (54% reduction)](https://gist.github.com/johnlindquist/849b813e76039a908d962b2f0923dc9a)

### Project Docs Read

- `CLAUDE.md` — machine instructions, 15 production rules
- `PROJECT_BRIEF.md` — project context
- `ARCHITECTURE.md` — system design, hook chain, data flow
- `_lib.py` — full 1,851 lines (violation patterns, test quality, R-markers, state management)
- `qa_runner.py` — full 1,220 lines (12-step pipeline)
- `ralph/SKILL.md` — full orchestrator v3 spec
- `ralph-worker.md` — worker agent spec
- `architect.md`, `builder.md` — role agents
- All 6 hook scripts read in full
- NBA production system explored: 196K lines, 464 files, 4,812 tests, 13-stage pipeline
