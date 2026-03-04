# Brainstorm: Workflow Quality Enforcement Upgrade (5/10 → 7+/10)

**Date**: 2026-02-28
**Problem**: The workflow has excellent documentation (9/10) but weak runtime enforcement (2-3/10) for QA pipeline, production standards, and test quality — most quality gates rely on agent honor system rather than automated verification.

## Current State Summary

| Dimension                  | Current Score | Root Cause                                                        |
| -------------------------- | ------------- | ----------------------------------------------------------------- |
| QA pipeline enforcement    | 3/10          | 16 steps live in qa.md as agent instructions, no automated runner |
| Production standards       | 2/10          | 10 rules documented, zero hooks enforce them                      |
| Test quality validation    | 2/10          | Markers tracked, assertions/mocks not validated                   |
| Worker result verification | 3/10          | Ralph trusts worker's `passed: true` without spot-check           |
| Verification auditability  | 3/10          | Text logs, not machine-readable, not parseable                    |
| Plan validation            | 8/10          | Step 6b has 6 automated checks — already strong                   |
| Safety hooks               | 8/10          | pre_bash_guard, stop_verify_gate work well                        |

**Architecture constraints** (must maintain):

- Hooks are independent Python scripts reading stdin JSON, exiting 0 (pass) or 2 (block)
- State persists via files (`.needs_verify`, `.stop_block_count`) — survives context compaction
- Shared utilities in `_lib.py` — new hooks import from here
- `settings.json` wires hooks to events (SessionStart, PreToolUse, PostToolUse, Stop)
- Hooks must fail-closed, be Python 3.10+ compatible, work on Windows/MINGW64
- No hook-to-hook communication except via filesystem
- workflow.json configures test patterns and formatter timeout

---

## Ideas

### 1. Automated QA Runner Script (`qa_runner.py`)

Create a standalone Python script that programmatically executes as many of the 16 QA steps as possible, producing structured JSON results. Not a hook — a utility invoked by ralph-worker and `/verify`.

**How it works:**

- Reads `workflow.json` for configured commands (test, lint, format)
- Reads `prd.json` for current story's `gateCmds` and `acceptanceCriteria`
- Executes steps sequentially:
  - Step 1 (Lint): Run configured lint command, capture exit code + output
  - Step 2 (Type check): Run mypy/tsc if configured
  - Step 3 (Unit tests): Run unit gate command
  - Step 4 (Integration): Run integration gate command if exists
  - Step 5 (Regression): Run full test suite, compare to baseline
  - Step 6 (Security scan): Grep for hardcoded secrets, SQL injection patterns
  - Step 7 (Clean diff): Grep staged files for debug prints, TODOs
  - Step 8 (Coverage): Run coverage command if configured
  - Step 9 (Mock audit): Parse test files for self-mocking patterns
  - Steps 10-14: Cannot be fully automated (require semantic judgment) — mark as "manual_review_required"
  - Step 15 (Acceptance traceability): Grep for R-PN-NN markers, verify linked tests pass
  - Step 16 (Production scan): Grep for all 10 production violations
- Outputs structured JSON: `{step: int, name: str, result: "PASS"|"FAIL"|"SKIP"|"MANUAL", evidence: str, duration_ms: int}`
- Returns overall PASS only if all non-MANUAL steps pass

**Pros:**

- Replaces honor system with verifiable execution for ~10 of 16 steps
- Structured output enables auditing and metrics
- Reusable by ralph-worker, `/verify`, and `/audit`
- Steps 10-14 honestly marked as manual (no fake automation)
- Can be extended incrementally (add automation for steps as tooling improves)

**Cons:**

- Requires `workflow.json` to be properly configured (currently empty)
- Steps 10-14 remain manual (blast radius, logic review, architecture conformance, builder deviation)
- Running all automated steps takes time (~30-60s depending on project size)
- Different projects need different commands — one-size-fits-all is hard
- Test suite must exist for steps 3-5 to work

---

### 2. Production Code Scan Hook (`post_write_prod_scan.py`)

A PostToolUse:Edit|Write hook that scans every written/edited code file against the 10 production-grade standards and warns immediately.

**How it works:**

- Fires after every Edit/Write on code files (same trigger as post_format.py)
- Extracts the file path from stdin JSON
- Reads the file and runs regex scans for each of 10 standards:
  1. `grep -nE "TODO|HACK|FIXME|XXX"` (exclude test files)
  2. `grep -nE "password\s*=\s*['\"]|api_key\s*=\s*['\"]|secret\s*=\s*['\"]"`
  3. `grep -nE "except:|catch\s*\(?\s*\)?"` (bare except detection)
  4. `grep -nE "print\(|console\.log|debugger|binding\.pry"`
  5. `grep -nE "f['\"].*SELECT|f['\"].*INSERT|f['\"].*UPDATE|f['\"].*DELETE"` (SQL concatenation)
- Outputs warnings to stdout (visible to agent)
- Does NOT block (exit 0) — warns only, to avoid disrupting flow
- Creates a `.claude/.prod_violations` marker file with violation details
- Ralph-worker's QA Step 16 can read this marker for instant results

**Pros:**

- Catches violations at write-time, not after entire QA pipeline
- Non-blocking (warning) means it doesn't disrupt development flow
- Marker file enables downstream verification (Step 16 reads it)
- Lightweight — regex scans are fast
- Integrates naturally into existing PostToolUse:Edit|Write chain

**Cons:**

- Regex-based detection has false positives (e.g., `password` in a comment)
- Cannot detect semantic violations (missing error handling, missing type hints, resource leaks)
- Standards 3, 7, 8, 9 require semantic analysis beyond regex
- Warning fatigue if too many false positives
- Only catches violations in files touched by Edit/Write, not files created via Bash

---

### 3. Test Quality Validator (`test_quality.py`)

A utility script (not a hook) that analyzes test files for assertion quality, self-mocking, and coverage gaps.

**How it works:**

- Accepts a list of test file paths
- For each test file, parses and checks:
  - **Assertion presence**: Does every `def test_*` / `it(` block contain at least one assert/expect/assertEqual?
  - **Self-mock detection**: Does the test mock a function from the same module it imports and tests?
  - **Mock-only tests**: Does the test ONLY assert `mock.called` / `mock.assert_called_with` without checking actual behavior?
  - **R-PN-NN marker presence**: Does the test have a requirement traceability marker?
  - **Marker validity**: Does the R-PN-NN ID exist in prd.json?
- Outputs structured JSON per test file:
  ```json
  {
    "file": "tests/test_auth.py",
    "tests_found": 5,
    "assertions": { "total": 12, "per_test_min": 1, "per_test_max": 4 },
    "self_mocks": [],
    "mock_only_tests": [],
    "markers": ["R-P1-01", "R-P1-02"],
    "orphan_markers": [],
    "assertion_free_tests": [],
    "quality_score": "PASS"
  }
  ```
- Used by qa_runner.py for Step 9 (mock audit) and Step 15 (acceptance traceability)

**Pros:**

- Directly addresses the "tests that prove nothing" gap
- Structured output enables metrics and trend tracking
- Catches the most common test antipatterns (assertion-free, self-mock, mock-only)
- Validates R-PN-NN markers against prd.json (catches stale/wrong markers)
- Can be run standalone or as part of qa_runner.py

**Cons:**

- AST parsing is language-specific — needs separate logic for Python vs JS/TS
- Cannot detect semantic test quality (testing the right thing, meaningful assertions)
- Self-mock detection has edge cases (legitimate use of mocking within same module)
- Doesn't detect integration test gaps (only analyzes existing tests)
- Initial implementation complexity is moderate

---

### 4. Ralph Spot-Check Verification

After ralph-worker returns `passed: true`, have Ralph independently run the story's `gateCmds` on the merged result before recording success.

**How it works:**

- After STEP 6 merge succeeds, BEFORE updating prd.json:
  1. Read story's `gateCmds` from prd.json
  2. Run `gateCmds.lint` → verify exit 0
  3. Run `gateCmds.unit` → verify exit 0
  4. Run `gateCmds.integration` → verify exit 0 (if exists)
  5. Run production scan (qa_runner.py --step 16 only) on changed files
- If any spot-check fails: treat as FAIL, increment attempt counter, auto-retry
- Log spot-check results to verification-log.jsonl

**Pros:**

- Breaks the honor system — independent verification after worker claims success
- Catches worker bugs (skipped steps, partial verification, false positives)
- Gate commands are already defined in prd.json — no new configuration needed
- Spot-check runs on merged code (catches merge-induced failures)
- Lightweight — only runs gate commands, not full 16-step pipeline

**Cons:**

- Adds ~15-30s per story (running gate commands again)
- Only checks automated gates — manual steps still unverified
- If worker worktree cleanup happened, merged code may not be in right state
- Requires qa_runner.py (Idea 1) to exist for Step 16 spot-check
- Could cause false failures if test environment differs between worktree and feature branch

---

### 5. Machine-Readable Verification Log (`verification-log.jsonl`)

Replace the text-based verification-log.md with structured JSON Lines format that enables automated auditing and metrics.

**How it works:**

- Each verification produces a JSONL entry:
  ```json
  {
    "story_id": "STORY-001",
    "timestamp": "2026-02-28T10:30:45Z",
    "attempt": 1,
    "worker_id": "ralph-worker-abc123",
    "qa_steps": [
      {"step": 1, "name": "lint", "result": "PASS", "duration_ms": 2300, "evidence": "0 warnings"},
      {"step": 2, "name": "type_check", "result": "PASS", "duration_ms": 5100, "evidence": "Success: no issues found"},
      ...
    ],
    "spot_check": {"lint": "PASS", "unit": "PASS", "integration": "SKIP"},
    "overall_result": "PASS",
    "criteria_verified": ["R-P1-01", "R-P1-02"],
    "files_changed": ["src/auth.py", "tests/test_auth.py"],
    "production_violations": 0
  }
  ```
- `/audit` Section 4 parses JSONL for:
  - Pass rate across stories
  - Most commonly failing steps
  - Average verification duration
  - Criteria coverage gaps
- Ralph reads it to show sprint summary metrics

**Pros:**

- Enables automated auditing (no regex parsing of markdown)
- Supports metrics and trend analysis across sprints
- Each entry is self-contained and machine-parseable
- Compatible with existing audit framework (Section 4 just reads differently)
- Can be queried with `jq` for ad-hoc analysis

**Cons:**

- Breaking change from verification-log.md format (migration needed)
- Human-readability decreases (JSONL not as nice to browse as markdown)
- Requires qa_runner.py to produce structured output (dependency on Idea 1)
- Log rotation needed (could grow large over many sprints)

---

### 6. Enhanced `workflow.json` Configuration

Populate workflow.json with actual project-specific commands and add new configuration sections for the quality enforcement tools.

**How it works:**

- Extend schema to include:
  ```json
  {
    "commands": {
      "test": "pytest",
      "lint": "ruff check .",
      "format": "ruff format .",
      "type_check": "python -m mypy src/",
      "coverage": "pytest --cov=src --cov-report=term-missing"
    },
    "test_patterns": ["pytest", "python -m pytest"],
    "format_timeout_seconds": 30,
    "qa_runner": {
      "enabled": true,
      "skip_steps": [],
      "manual_steps": [10, 11, 12, 13, 14],
      "production_scan": {
        "exclude_patterns": ["**/test_*", "**/conftest.py"],
        "custom_violations": []
      },
      "test_quality": {
        "min_assertions_per_test": 1,
        "detect_self_mocks": true,
        "detect_mock_only": true
      }
    },
    "verification_log": {
      "format": "jsonl",
      "max_entries": 200,
      "path": ".claude/docs/verification-log.jsonl"
    }
  }
  ```
- All new tools read from workflow.json for configuration
- Existing hooks already use `load_workflow_config()` — just need new keys

**Pros:**

- Single source of truth for all quality configuration
- Projects can customize thresholds, commands, exclusions
- Existing hooks already load workflow.json — natural extension
- Makes the "currently empty" workflow.json actually useful
- New projects get sensible defaults via \_lib.py fallbacks

**Cons:**

- Schema complexity increases (more fields to document and validate)
- Risk of configuration drift (workflow.json disagrees with documentation)
- Need to validate new fields without breaking existing hooks
- Per-language defaults are hard (Python vs JS vs Go need different commands)

---

### 7. Integrated Verification Marker Enhancement

Extend the `.needs_verify` marker system to track WHAT needs verification, not just THAT verification is needed.

**How it works:**

- Current marker: just a file with timestamp + path
- Enhanced marker: JSONL file tracking each change:
  ```json
  {"ts": "...", "file": "src/auth.py", "tool": "Edit", "lines_changed": 15}
  {"ts": "...", "file": "src/models.py", "tool": "Write", "lines_changed": 42}
  ```
- `post_bash_capture.py` enhanced: on test pass, only clears entries for files covered by the test command's scope
- `stop_verify_gate.py` enhanced: shows which files remain unverified
- New: `post_write_prod_scan.py` can add violation entries to the marker
- `/verify` reads the marker to know exactly what to verify

**Pros:**

- More granular verification tracking (file-level, not session-level)
- Stop gate gives actionable feedback ("src/auth.py unverified")
- Enables targeted re-verification (only re-test changed files)
- Foundation for coverage-aware verification

**Cons:**

- Significant refactor of marker system (\_lib.py changes)
- Parsing JSONL marker is more complex than checking file existence
- Risk of marker growing large in long sessions
- Harder to clear atomically (partial clear vs full clear)
- May be over-engineering for current needs

---

### 8. `_lib.py` Quality Utilities Extension

Add shared quality-checking functions to \_lib.py that any hook or script can import.

**How it works:**

- Add to \_lib.py:

  ```python
  # Production violation patterns
  PROD_VIOLATION_PATTERNS = [
      (r'\b(TODO|HACK|FIXME|XXX)\b', 'todo_marker', 'Remove TODO/HACK/FIXME/XXX comment'),
      (r'except\s*:', 'bare_except', 'Catch specific exception type'),
      (r'\bprint\s*\(', 'debug_print', 'Remove debug print statement'),
      (r'console\.(log|debug|warn|error)\s*\(', 'console_log', 'Remove console.log'),
      (r'(password|secret|api_key|token)\s*=\s*["\'][^"\']+["\']', 'hardcoded_secret', 'Use environment variable'),
      (r'f["\'].*\b(SELECT|INSERT|UPDATE|DELETE)\b', 'sql_injection', 'Use parameterized query'),
      (r'\bdebugger\b', 'debugger_stmt', 'Remove debugger statement'),
      (r'binding\.pry', 'binding_pry', 'Remove binding.pry'),
  ]

  def scan_file_violations(filepath: Path, exclude_test: bool = True) -> list[dict]:
      """Scan a file for production code violations."""

  def scan_test_quality(filepath: Path) -> dict:
      """Analyze test file for assertion quality."""

  def validate_r_markers(test_dir: Path, prd_path: Path) -> dict:
      """Validate R-PN-NN markers against prd.json."""
  ```

- Used by: post_write_prod_scan.py, qa_runner.py, test_quality.py, /audit

**Pros:**

- DRY — violation patterns defined once, used everywhere
- Consistent detection across hooks, scripts, and audit
- Easy to extend (add patterns to list)
- Existing hooks already import from \_lib.py

**Cons:**

- \_lib.py grows in complexity (currently ~180 lines, would grow to ~350+)
- Testing \_lib.py itself becomes more important (need tests for quality functions)
- Regex patterns need careful tuning to minimize false positives

---

## Evaluation Matrix

| Idea                         | Impact on Score                   | Implementation Effort         | Dependencies         | Risk   |
| ---------------------------- | --------------------------------- | ----------------------------- | -------------------- | ------ |
| 1. QA Runner                 | +2.0 (QA: 3→7, Auditability: 3→6) | High (new script, ~300 LOC)   | workflow.json config | Medium |
| 2. Prod Scan Hook            | +1.5 (Production: 2→6)            | Medium (new hook, ~100 LOC)   | \_lib.py patterns    | Low    |
| 3. Test Quality Validator    | +1.5 (Test quality: 2→6)          | Medium (new script, ~200 LOC) | AST parsing          | Medium |
| 4. Ralph Spot-Check          | +1.0 (Worker verification: 3→6)   | Low (SKILL.md change)         | qa_runner.py         | Low    |
| 5. Verification Log JSONL    | +1.0 (Auditability: 3→7)          | Low (format change)           | qa_runner.py output  | Low    |
| 6. Workflow.json Enhancement | +0.5 (enables all above)          | Low (config schema)           | None                 | Low    |
| 7. Enhanced Markers          | +0.5 (granular tracking)          | High (refactor \_lib.py)      | None                 | Medium |
| 8. \_lib.py Utilities        | +1.0 (DRY, consistency)           | Medium (shared code)          | None                 | Low    |

---

## Recommendation

**Implement Ideas 1 + 2 + 3 + 4 + 5 + 6 + 8 as a coordinated upgrade.** Skip Idea 7 (enhanced markers) — it's over-engineering for current needs and the effort/risk is high for marginal benefit.

### Implementation order (dependency-aware):

```
Phase 1: Foundation
├── Idea 6: Enhanced workflow.json (enables everything else)
└── Idea 8: _lib.py quality utilities (shared patterns, scan functions)

Phase 2: Detection
├── Idea 2: Production scan hook (uses _lib.py patterns)
└── Idea 3: Test quality validator (uses _lib.py scan functions)

Phase 3: Automated QA
└── Idea 1: QA runner script (uses workflow.json, _lib.py, test_quality.py)

Phase 4: Verification
├── Idea 5: Verification log JSONL (uses qa_runner.py output)
└── Idea 4: Ralph spot-check (uses qa_runner.py, reads JSONL log)
```

### Expected outcome:

| Dimension                  | Before   | After      | Key Enabler                                   |
| -------------------------- | -------- | ---------- | --------------------------------------------- |
| QA pipeline enforcement    | 3/10     | 7/10       | qa_runner.py automates ~10 of 16 steps        |
| Production standards       | 2/10     | 7/10       | post_write_prod_scan.py catches at write-time |
| Test quality validation    | 2/10     | 7/10       | test_quality.py validates assertions + mocks  |
| Worker result verification | 3/10     | 7/10       | Ralph spot-check after merge                  |
| Verification auditability  | 3/10     | 8/10       | JSONL structured logs                         |
| Plan validation            | 8/10     | 8/10       | Already strong (no change)                    |
| Safety hooks               | 8/10     | 8/10       | Already strong (no change)                    |
| **Overall**                | **5/10** | **7.4/10** | Coordinated 4-phase upgrade                   |

### Why skip Idea 7 (Enhanced Markers):

- The current binary marker (exists/doesn't) is sufficient for the stop gate
- File-level tracking adds complexity without proportional quality improvement
- The QA runner + verification log provide better granularity through different means
- Can always add later if file-level tracking proves necessary

### Why this combination works:

- Phase 1 builds the foundation (config + shared utilities) that everything else depends on
- Phase 2 gives immediate developer feedback (violations caught at write-time)
- Phase 3 automates the biggest gap (QA pipeline goes from honor system to verified execution)
- Phase 4 closes the trust gap (Ralph independently verifies worker claims)
- Each phase is independently valuable — can ship incrementally

## Sources

- `.claude/hooks/_lib.py` — shared hook library (current architecture)
- `.claude/hooks/pre_bash_guard.py` — reference implementation for blocking hooks
- `.claude/hooks/post_format.py` — reference implementation for PostToolUse hooks
- `.claude/hooks/post_bash_capture.py` — test detection and error capture patterns
- `.claude/hooks/stop_verify_gate.py` — marker-based verification gate
- `.claude/settings.json` — hook wiring configuration
- `.claude/workflow.json` — runtime configuration (currently empty)
- `.claude/agents/qa.md` — 16-step QA pipeline definition
- `.claude/agents/ralph-worker.md` — worker agent architecture
- `.claude/skills/ralph/SKILL.md` — Ralph v3 orchestrator loop
- `.claude/skills/verify/SKILL.md` — verification skill
- `.claude/skills/audit/SKILL.md` — audit skill (8 sections)
- `.claude/prd.json` — PRD v2 schema reference
- Previous audit conversation (2026-02-28) — identified all gaps and scores
