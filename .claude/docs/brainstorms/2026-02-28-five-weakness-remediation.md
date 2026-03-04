# Brainstorm: Five Weakness Remediation — Closing the Quality Gaps

**Date**: 2026-02-28
**Problem**: The ADE workflow has five identified weaknesses that prevent it from being truly bulletproof: (1) production violations are warn-only, (2) 5 of 9 hooks lack tests, (3) QA Steps 10-14 are manual, (4) violation regex patterns are too narrow, (5) no PLAN.md-to-prd.json drift detection. Each needs a concrete fix applied through the V-Model SDLC.

---

## Weakness 1: Production Violations Are Warn-Only

### The Problem

`post_write_prod_scan.py` always exits 0. This means Claude can write code with TODO comments, bare excepts, debug prints, or hardcoded secrets and the hook merely prints a warning. The warning is easily ignored. This directly contradicts QA Step 16's "ANY violation = FAIL, no exceptions" policy.

The result: violations get committed, QA Step 16 catches them reactively, and Ralph auto-retries — wasting attempts on something the hook should have prevented.

### Ideas

#### 1A. Make post_write_prod_scan.py exit 2 on violations (blocking)

Change the hook to exit 2 when violations are found, preventing the Edit/Write from completing.

- **Pros**: Zero tolerance enforced at write-time. No violations can enter the codebase. Aligns perfectly with QA Step 16's "no exceptions" mandate. Simple change — swap `sys.exit(0)` to `sys.exit(2)` in the violations branch.
- **Cons**: Blocks ALL writes with violations, including intermediate work where a developer might legitimately write a function with a TODO while working through a multi-step implementation. Could make the builder agent thrash if it writes scaffolding code. Would require Claude to fix violations before the file is even saved, which could break the write-test-fix cycle.

#### 1B. Two-tier system: warn on write, block on stop (via .prod_violations marker)

Keep post_write_prod_scan.py as warn-only (exit 0), but make `stop_verify_gate.py` ALSO check `.prod_violations` marker and block if outstanding violations exist. Add a `clear_prod_violations()` function to `_lib.py` that `post_bash_capture.py` calls when tests pass (same as `.needs_verify`).

- **Pros**: Preserves the write-test-fix development flow. Builder can write code, run tests, fix violations, and only then the markers clear. Existing escape hatch (3 attempts) still works for emergencies. No breaking change to the current hook chain — only additive. Stop gate becomes the single enforcement point for both markers.
- **Cons**: Violations CAN exist temporarily in the codebase during a work session. If the session crashes before stop gate fires, violations persist uncaught. Adds complexity to the stop gate (now checking two markers). Relies on `post_bash_capture.py` to clear the marker, which only fires when tests match configured patterns.

#### 1C. Configurable severity levels per violation pattern

Add a `severity` field to each `PROD_VIOLATION_PATTERNS` entry: `"block"` (exit 2), `"warn"` (exit 0), `"info"` (log only). Configure via `workflow.json` overrides.

```python
PROD_VIOLATION_PATTERNS = [
    (r"\b(TODO|HACK|FIXME|XXX)\b", "todo-comment", "...", "warn"),
    (r"^\s*except\s*:", "bare-except", "...", "block"),
    (r"""(?:password|...)...""", "hardcoded-secret", "...", "block"),
    ...
]
```

- **Pros**: Granular control. Security-critical violations (secrets, injection) block immediately while cleanup items (TODO, debug prints) warn. Matches real-world workflow where some violations are "fix before commit" and others are "fix before merge." Configurable via workflow.json so different projects can set different thresholds.
- **Cons**: Most complex to implement. Adds a 4th element to every pattern tuple (breaking change to \_lib.py). qa_runner.py and test_quality.py would need updates. More test surface. Risk of misconfiguration if user sets everything to "info."

#### 1D. Post-write prod scan blocks, but only for security-critical violations

Split violations into "security" (hardcoded-secret, sql-injection, shell-injection, bare-except) and "hygiene" (todo-comment, debug-print, debugger-stmt, debug-import). Hook exits 2 only for security violations.

- **Pros**: The most dangerous violations are caught at write-time. Hygiene violations still warn. No configuration complexity. Security violations should never exist even temporarily.
- **Cons**: Still allows debug prints and TODOs to be committed (caught by QA Step 16 later). The line between "security" and "hygiene" is somewhat arbitrary — is bare-except security or hygiene?

### Recommendation for Weakness 1

**Idea 1B (two-tier: warn on write, block on stop)** combined with **1D (block security-critical at write-time)**.

Here's why: The write-test-fix cycle is fundamental to how Builder works. Blocking ALL writes would break TDD (you write a function with a print statement for debugging, then remove it). But security violations (hardcoded secrets, SQL injection) should NEVER exist even temporarily in a file.

**Implementation plan:**

1. Add severity field to `PROD_VIOLATION_PATTERNS` in `_lib.py`: `"block"` for security (hardcoded-secret, sql-injection, shell-injection), `"warn"` for everything else
2. `post_write_prod_scan.py`: exit 2 for any `"block"` severity violation, exit 0 (warn) for `"warn"` severity
3. `_lib.py`: add `PROD_VIOLATIONS_PATH`, `read_prod_violations()`, `clear_prod_violations()` functions
4. `post_bash_capture.py`: on successful test run, clear BOTH `.needs_verify` AND `.prod_violations`
5. `stop_verify_gate.py`: check BOTH markers — block if either exists
6. `qa_runner.py` Step 16: use severity in evidence output for clearer reporting

---

## Weakness 2: 5 of 9 Hooks Have Zero Tests

### The Problem

The workflow's own hooks — which are the enforcement backbone — have critical test gaps:

| Hook                      | Tests | Risk                                                                                       |
| ------------------------- | ----- | ------------------------------------------------------------------------------------------ |
| `pre_bash_guard.py`       | 0     | Safety gate untested — regression could silently disable command blocking                  |
| `stop_verify_gate.py`     | 0     | Escape hatch logic untested — counter bugs could lock users in or let them out early       |
| `post_bash_capture.py`    | 0     | Error logging and marker clearing untested — broken marker clearing breaks the whole chain |
| `post_format.py`          | 0     | Formatter invocation untested — broken formatting is invisible                             |
| `post_compact_restore.py` | 0     | Reminder output untested — lowest risk, but still a gap                                    |

This is the "cobbler's children have no shoes" problem. A system designed to enforce test quality doesn't test its own enforcement mechanisms.

### Ideas

#### 2A. Write comprehensive test suites for all 5 untested hooks

Create 5 new test files:

- `test_pre_bash_guard.py` (~40 tests): every DENY_PATTERN, bypass attempts, sudo prefix, false positives, exit codes
- `test_stop_verify_gate.py` (~25 tests): marker detection, counter increment/reset, escape hatch threshold, fail_open behavior
- `test_post_bash_capture.py` (~30 tests): error JSON structure, test pattern detection, marker clearing, history trimming
- `test_post_format.py` (~25 tests): ruff invocation, prettier invocation, extension filtering, marker creation, timeout handling
- `test_post_compact_restore.py` (~10 tests): output formatting, marker status detection

- **Pros**: Comprehensive. Every hook gets the same treatment as `post_write_prod_scan.py` (which has 26 tests). Catches regressions. Enables confident refactoring. Estimated ~130 new tests bringing total from 127 to ~257.
- **Cons**: Significant effort (~4 Ralph stories). Some hooks are hard to test in isolation (e.g., `post_format.py` needs ruff/prettier installed). Subprocess mocking needed for formatter tests.

#### 2B. Write tests only for safety-critical hooks (pre_bash_guard, stop_verify_gate)

Focus on the two hooks where bugs have the highest blast radius: the command guard and the stop gate. Defer the other three.

- **Pros**: Faster to implement (2 stories instead of 5). Covers the highest-risk gaps. 80/20 rule — these two hooks protect against the most dangerous scenarios.
- **Cons**: Leaves post_bash_capture untested — and marker clearing is the linchpin of the entire hook chain. A bug in `is_test_command()` matching would mean markers never clear, effectively locking users in. Also leaves post_format untested — formatter failures are silent.

#### 2C. Integration test approach — test the hook chain end-to-end

Instead of unit-testing each hook, write integration tests that simulate the full lifecycle:

1. Simulate Edit → verify post_format creates marker → verify post_write_prod_scan warns
2. Simulate Bash with test command → verify post_bash_capture clears marker
3. Simulate Stop → verify stop_verify_gate blocks → verify escape hatch works

- **Pros**: Tests the actual flow users experience. Catches integration bugs that unit tests miss (e.g., marker path mismatch between post_format and post_bash_capture). Fewer tests needed to cover the same scenarios.
- **Cons**: Harder to write — needs stdin/stdout simulation for hook JSON protocol. Harder to debug failures (which hook broke?). Doesn't test individual DENY_PATTERNS or edge cases well. Slower to run.

#### 2D. Hybrid: Unit tests for safety-critical + integration tests for the chain

Write unit tests for pre_bash_guard.py and stop_verify_gate.py (highest risk), plus one integration test file that tests the marker lifecycle chain (post_format → post_bash_capture → stop_verify_gate). Defer post_compact_restore.py tests (lowest risk).

- **Pros**: Best coverage-to-effort ratio. Safety-critical hooks get thorough unit testing. The marker chain gets integration testing. Total ~80 new tests across 3 files.
- **Cons**: post_format.py formatter invocation still not directly tested. Slightly less total coverage than 2A.

### Recommendation for Weakness 2

**Idea 2A (comprehensive test suites for all 5 hooks)**.

Rationale: This is the workflow's own infrastructure. Cutting corners here is exactly the kind of technical debt the system is designed to prevent. The hooks are the foundation — if they break, everything above them (QA pipeline, Ralph, audit) gives false confidence. The existing test infrastructure (conftest.py, tmp_path fixtures, R-marker conventions) makes adding new test files straightforward.

**Implementation plan (4 stories):**

**Story A**: `test_pre_bash_guard.py` + `test_stop_verify_gate.py`

- Test every DENY_PATTERN in pre_bash_guard (positive + negative cases)
- Test bypass attempts (unicode tricks, encoding, extra whitespace)
- Test stop gate: marker present → block, marker absent → allow
- Test escape hatch: count 0→1→2→force-allow, counter reset on clear
- Test fail_open=True: malformed stdin → allow stop (never lock user in)

**Story B**: `test_post_bash_capture.py`

- Test error JSON structure (all fields present, truncation limits)
- Test is_test_command() integration (configured patterns, defaults, env var prefix)
- Test marker clearing on test pass (both .needs_verify and .stop_block_count)
- Test history trimming (>50 entries trimmed)
- Test exit code handling (0 = no capture, non-zero = capture)

**Story C**: `test_post_format.py`

- Test ruff invocation for .py files (mock subprocess)
- Test prettier invocation for .ts/.js files (mock subprocess)
- Test extension filtering (non-code files skipped)
- Test verification marker creation (code files get marker, non-code don't)
- Test timeout handling

**Story D**: `test_post_compact_restore.py` + `test_marker_io.py`

- Test post_compact_restore output formatting
- Test \_lib.py marker I/O: read_marker, write_marker, clear_marker
- Test stop counter: get, increment, clear
- Test edge cases: permission errors, missing directories, concurrent access

---

## Weakness 3: QA Steps 10-14 Are Manual (No Automation)

### The Problem

Steps 10-14 in the QA pipeline are marked `MANUAL` in qa_runner.py:

| Step | Name                     | What It Checks                              |
| ---- | ------------------------ | ------------------------------------------- |
| 10   | Blast radius check       | Were files changed that aren't in the plan? |
| 11   | System/E2E test          | Does the full feature path work?            |
| 12   | Logic review             | Edge cases, race conditions, off-by-one?    |
| 13   | Architecture conformance | Does implementation match ARCHITECTURE.md?  |
| 14   | Builder deviation review | Did Builder deviate from PLAN.md?           |

These steps return `{"result": "MANUAL", "evidence": "Requires semantic review"}` and rely entirely on the QA agent's diligence. A rubber-stamp QA pass skips all five.

### Ideas

#### 3A. Automate blast radius (Step 10) via git diff comparison

Parse PLAN.md's "Changes" table to extract expected file paths. Run `git diff --name-only {checkpoint}..HEAD` to get actual changed files. Report any files changed that weren't in the plan.

```python
def _step_blast_radius(changed_files, plan_path):
    expected = parse_plan_changes_table(plan_path)  # Extract from PLAN.md
    actual = set(str(f) for f in changed_files)
    unexpected = actual - expected
    if unexpected:
        return "FAIL", f"Unexpected files changed: {unexpected}"
    return "PASS", f"All {len(actual)} changed files are in plan"
```

- **Pros**: Catches accidental scope creep immediately. Simple to implement — PLAN.md already has a structured Changes table. No external dependencies. Deterministic (no AI judgment needed).
- **Cons**: Requires PLAN.md to have a parseable Changes table (it does — the Architect template mandates this). Might be too strict — Builder sometimes creates helper files not in the plan. Would need an "allowed extras" mechanism (e.g., `__init__.py`, config files).

#### 3B. Automate architecture conformance (Step 13) via import graph

Parse ARCHITECTURE.md for component boundaries and allowed dependencies. Scan changed files' import statements. Flag imports that cross documented boundaries.

- **Pros**: Catches architectural drift programmatically. Import graph analysis is well-understood (Python AST, JS/TS require different parser).
- **Cons**: Complex to implement — needs ARCHITECTURE.md to be machine-parseable (currently it's narrative prose). Different languages have different import systems. False positives on utility imports. Would need significant ARCHITECTURE.md restructuring.

#### 3C. Semi-automate via structured checklists in qa_runner output

Instead of returning just `"MANUAL"`, have qa_runner output specific questions the QA agent MUST answer:

```json
{
  "step": 10,
  "name": "Blast radius check",
  "result": "REVIEW",
  "checklist": [
    "Are all changed files listed in PLAN.md Changes table?",
    "Were any files modified that affect modules outside this story?",
    "Are there any new dependencies introduced?"
  ],
  "evidence": "QA must answer each question with PASS/FAIL + evidence"
}
```

- **Pros**: Forces QA to address specific questions (can't rubber-stamp). qa_runner provides the structure, QA provides the judgment. No complex parsing needed. Works for all 5 manual steps.
- **Cons**: Still relies on QA agent's honesty and thoroughness. Not truly automated — just more structured manual review. Adds output complexity to qa_runner.

#### 3D. Automate Step 10 (blast radius) + Step 14 (deviation) via diff analysis, leave 11-13 as structured manual

Step 10 (blast radius) and Step 14 (builder deviation) are the most automatable because they compare actual changes against documented expectations:

- **Step 10**: Compare `changed_files` against PLAN.md Changes table
- **Step 14**: Compare `changed_files` against story's `files` array in prd.json, check that test files have correct R-markers

Steps 11-13 require genuine semantic understanding (E2E test execution, logic review, architecture judgment) and are better left as structured checklists.

- **Pros**: Automates the two most objective checks. Leaves genuinely subjective steps as structured manual. Pragmatic 80/20 approach.
- **Cons**: Still leaves 3 steps manual. Step 13 (architecture) remains the biggest gap.

### Recommendation for Weakness 3

**Idea 3D (automate Steps 10 + 14, structured checklists for 11-13)**.

Rationale: Steps 10 and 14 are comparing actual output against documented expectations — this is fundamentally a diff operation, not a judgment call. Steps 11-13 genuinely require semantic understanding that regex can't provide. Structured checklists force the QA agent to be explicit about what it reviewed.

**Implementation plan:**

1. Add `parse_plan_changes()` to `_lib.py` — extracts expected file paths from PLAN.md's Changes table using regex on the markdown table format
2. Add `_step_blast_radius()` to `qa_runner.py` — compares changed_files against plan expectations, allows configurable "always-allowed" patterns (e.g., `__init__.py`, `*.pyc`)
3. Add `_step_deviation_check()` to `qa_runner.py` — checks that story's `files` array in prd.json matches actual changed files, validates R-markers exist for all testable criteria
4. Update Steps 11-13 to return `"REVIEW"` result with structured checklists instead of bare `"MANUAL"`
5. Update `/verify` skill to require QA agent to answer each checklist question with evidence

---

## Weakness 4: Violation Regex Patterns Are Too Narrow

### The Problem

The 8 patterns in `PROD_VIOLATION_PATTERNS` miss real-world violations:

| Pattern          | What It Catches     | What It Misses                                                                 |
| ---------------- | ------------------- | ------------------------------------------------------------------------------ |
| hardcoded-secret | `password = "..."`  | `oauth_token`, `credentials`, `jwt_secret`, `auth_header`, dict values, YAML   |
| sql-injection    | `SELECT ... + var`  | `subprocess.run(f"...", shell=True)`, multi-line SQL, ORM raw queries          |
| shell-injection  | `os.system(f"...")` | `subprocess.run()`, `subprocess.Popen()`, `os.popen()`, `commands.getoutput()` |
| bare-except      | `except:`           | `except Exception:` (catches SystemExit), over-broad catch blocks              |
| debug-print      | `print(`            | `logging.debug(` in production, `pp(`, `ic(`                                   |

A developer who knows the patterns can write code that bypasses all detection.

### Ideas

#### 4A. Expand existing patterns to cover common variants

Add new patterns and broaden existing ones:

```python
# Expanded hardcoded-secret (add common variable names)
r"""(?:password|passwd|api_key|apikey|secret|token|oauth|credential|jwt|auth_token|private_key|access_key)\s*=\s*(['"])(?!$)"""

# Expanded shell-injection (add subprocess, os.popen)
r"""(?:subprocess\.(?:run|call|Popen|check_output|check_call)|os\.(?:system|popen|exec[lv]?p?))\s*\(\s*(?:f['"]|['"].*\+|.*\.format\()"""

# Expanded SQL (catch f-strings in SQL context)
r"""(?:execute|executemany|raw|cursor\.)\s*\(\s*f['"]"""

# New: subprocess with shell=True and f-string/concat
r"""subprocess\.\w+\(.*shell\s*=\s*True.*(?:f['"]|['"].*\+)"""
```

- **Pros**: Catches the most common bypass vectors. Stays within the existing regex-per-line architecture. No new dependencies. Each new pattern gets tests.
- **Cons**: More patterns = more false positives. Regex complexity increases maintenance burden. Still fundamentally line-based — multi-line violations slip through. Will never catch ALL variants.

#### 4B. Add AST-based analysis for Python files

Use Python's `ast` module to parse files and check for:

- Any `subprocess` call with `shell=True` where the command argument contains f-string or format
- Any `except` clause that catches `Exception` (too broad)
- Any string literal assigned to variables matching secret-related names

```python
import ast

class SecurityVisitor(ast.NodeVisitor):
    def visit_Call(self, node):
        if is_subprocess_with_shell_true(node):
            self.report("shell-injection", node.lineno)
        self.generic_visit(node)
```

- **Pros**: Understands code structure, not just text. Catches multi-line violations. No false positives from comments or strings. Can detect complex patterns like `shell=True` with variable command.
- **Cons**: Python-only (JS/TS/Go/Rust need different parsers). Significant implementation effort. ast.parse fails on syntax errors. Adds ~200 lines to \_lib.py. Only works for Python — other languages still need regex.

#### 4C. Integrate external linters as optional QA steps

Instead of building our own detection, integrate existing tools:

- `bandit` for Python security (covers all OWASP patterns)
- `semgrep` for multi-language pattern matching
- `eslint-plugin-security` for JS/TS

Configure as optional commands in workflow.json:

```json
{
  "commands": {
    "security_scan": "bandit -r . -f json",
    "semgrep": "semgrep --config=auto --json"
  }
}
```

- **Pros**: Battle-tested tools with thousands of rules. Much broader coverage than hand-rolled regex. Active community maintaining rule sets. Zero maintenance burden for pattern updates.
- **Cons**: Adds external dependencies (bandit, semgrep must be installed). Slower execution. Output format varies (need parsers). Might flag patterns we don't care about. Not all projects want these dependencies.

#### 4D. Hybrid: expand regex patterns + optional external linter integration

Expand the most critical regex patterns (4A) for the built-in scan, AND add optional external linter support (4C) as a workflow.json configuration. The built-in scan is always active; external linters are bonus layers.

- **Pros**: Immediate improvement from expanded regex. Optional linters for projects that want deeper analysis. No mandatory new dependencies. Backward compatible.
- **Cons**: More work than either 4A or 4C alone. Two detection systems might produce duplicate findings.

### Recommendation for Weakness 4

**Idea 4D (hybrid: expand regex + optional external linters)**.

Rationale: The built-in regex patterns should catch the 90% case without any external dependencies — this is a portable workflow framework. But for projects that want deeper analysis, integrating bandit/semgrep as optional tools makes the system extensible.

**Implementation plan:**

1. Expand `PROD_VIOLATION_PATTERNS` in `_lib.py`:
   - Broaden `hardcoded-secret` to include `oauth`, `credential`, `jwt`, `private_key`, `access_key`
   - Add `subprocess-shell-injection`: catches `subprocess.run/call/Popen/check_output` with f-string or concat AND `shell=True`
   - Add `os-exec-injection`: catches `os.popen`, `os.exec*`, `commands.getoutput`
   - Add `raw-sql-fstring`: catches `execute(f"..."`, `cursor.execute(f"..."`
   - Add `broad-except`: catches `except Exception:` (distinct from bare-except, severity=warn)
   - Total: 8 patterns → 13 patterns
2. Add `external_scanners` section to `workflow.json`:
   ```json
   "external_scanners": {
     "bandit": { "cmd": "bandit -r {files} -f json", "enabled": false },
     "semgrep": { "cmd": "semgrep --config=auto {files} --json", "enabled": false }
   }
   ```
3. Add `_step_external_scan()` to `qa_runner.py` as Step 6b (runs after built-in security scan)
4. Write tests for all 5 new patterns (positive + negative cases)
5. Update CLAUDE.md Production-Grade Code Standards to document expanded patterns

---

## Weakness 5: No PLAN.md-to-prd.json Drift Detection

### The Problem

After `/plan` generates both PLAN.md and prd.json, the user can edit PLAN.md without regenerating prd.json. Ralph then runs against stale stories. Scenario:

1. `/plan` creates PLAN.md (4 phases, 12 R-PN-NN requirements) + prd.json (4 stories)
2. User reviews and edits PLAN.md: adds Phase 5, modifies Phase 3 testing strategy
3. User runs `/ralph` — Ralph reads prd.json (still 4 stories, old Phase 3 criteria)
4. Ralph completes all 4 stories, declares sprint done
5. Phase 5 requirements were never built

There's no mechanism to detect that PLAN.md and prd.json are out of sync.

### Ideas

#### 5A. Hash-based drift detection in Ralph STEP 1

When `/plan` generates prd.json, also write a hash of PLAN.md into prd.json:

```json
{
  "version": 2,
  "plan_hash": "sha256:a1b2c3...",
  "plan_path": ".claude/docs/PLAN.md",
  "stories": [...]
}
```

Ralph STEP 1 recomputes the hash and compares. If they differ, Ralph stops with: "PLAN.md has changed since prd.json was generated. Run /plan to regenerate stories."

- **Pros**: Deterministic detection. Zero false positives (hash only changes when content changes). Minimal implementation (one hash computation). Catches any edit to PLAN.md — additions, deletions, modifications.
- **Cons**: Overly sensitive — even whitespace changes or typo fixes in prose trigger a mismatch. User must re-run `/plan` for any PLAN.md edit, even trivial ones. Hash doesn't tell you WHAT changed.

#### 5B. R-marker count comparison

Instead of hashing the whole file, extract R-PN-NN markers from PLAN.md and compare against prd.json's acceptanceCriteria IDs. If PLAN.md has markers not in prd.json (or vice versa), drift is detected.

```python
def check_plan_prd_sync(plan_path, prd_path):
    plan_markers = extract_r_markers_from_plan(plan_path)
    prd_markers = extract_r_markers_from_prd(prd_path)
    added = plan_markers - prd_markers  # New in plan, missing in prd
    removed = prd_markers - plan_markers  # In prd, removed from plan
    return added, removed
```

- **Pros**: Only detects meaningful drift (requirement changes, not typos). Tells you exactly which requirements drifted. No re-run needed for prose edits. Reuses existing `_R_MARKER_RE` regex.
- **Cons**: Doesn't catch modifications to existing requirements (e.g., changing R-P1-01's description without changing its ID). Doesn't catch changes to testing strategy or file lists. Only catches additions/removals of R-markers.

#### 5C. Timestamp-based staleness warning

Record PLAN.md's modification time in prd.json. On Ralph startup, compare timestamps. If PLAN.md is newer than prd.json, warn (but don't block).

- **Pros**: Simple to implement. Catches any edit. Low friction (warning, not block).
- **Cons**: Timestamps are unreliable (git checkout doesn't preserve mtime). Warning can be ignored. Doesn't work in worktrees (file copied, not linked).

#### 5D. Hybrid: R-marker sync check + content hash for strict mode

Default behavior: R-marker count comparison (5B) — catches requirement additions/removals. Optional strict mode: content hash (5A) — catches any change.

Add to workflow.json:

```json
"plan_sync": {
  "mode": "markers",  // or "strict" for hash-based
  "action": "block"   // or "warn"
}
```

- **Pros**: Flexible — teams choose their tolerance. Default mode catches the most dangerous drift (missing requirements). Strict mode available for high-stakes projects.
- **Cons**: Two code paths to maintain. "markers" mode still misses requirement modifications.

### Recommendation for Weakness 5

**Idea 5D (hybrid: R-marker sync + optional hash)** with one addition from 5B: also compare the STORY COUNT. If PLAN.md has more phases than prd.json has stories, that's a guaranteed drift indicator.

**Implementation plan:**

1. Add `extract_plan_r_markers()` to `_lib.py` — parses PLAN.md for R-PN-NN markers using regex
2. Add `check_plan_prd_sync()` to `_lib.py` — compares plan markers vs prd markers, returns added/removed/matched
3. `/plan` Step 7: write `plan_hash` and `plan_marker_count` into prd.json metadata
4. Ralph STEP 1: call `check_plan_prd_sync()` — STOP if requirements added/removed, WARN if hash differs but markers match
5. `/refresh` skill: include sync check in output — show drift if present
6. `/audit` Section 2: add sync check (currently checks "prd.json ↔ PLAN.md alignment" but doesn't verify marker sync)

---

## V-Model SDLC Implementation Strategy

### How to Apply All Five Fixes via the V-Model

The V-Model requires: Requirements → Design → Implementation → Unit Test → Integration Test → System Test → Acceptance Test. Here's how each weakness maps:

### Phase Structure

**Phase 1: Foundation** (Weaknesses 1 + 5 — shared \_lib.py changes)

- Add severity field to PROD_VIOLATION_PATTERNS
- Add prod_violations marker I/O functions
- Add plan-prd sync checking functions
- Add plan R-marker extraction
- ~15 new \_lib.py functions/changes, ~40 tests

**Phase 2: Hook Hardening** (Weakness 2 — all 5 test suites)

- test_pre_bash_guard.py (~40 tests)
- test_stop_verify_gate.py (~25 tests)
- test_post_bash_capture.py (~30 tests)
- test_post_format.py (~25 tests)
- test_post_compact_restore.py + test_marker_io.py (~20 tests)
- Total: ~140 new tests

**Phase 3: Hook Upgrades** (Weaknesses 1 + 4 — modified hooks + expanded patterns)

- Upgrade post_write_prod_scan.py: block on security violations, warn on hygiene
- Upgrade stop_verify_gate.py: check both .needs_verify and .prod_violations
- Upgrade post_bash_capture.py: clear .prod_violations on test pass
- Expand PROD_VIOLATION_PATTERNS: 8 → 13 patterns
- Add external scanner support to workflow.json
- Update existing tests + add tests for new patterns

**Phase 4: QA Pipeline Automation** (Weakness 3 — qa_runner upgrades)

- Implement \_step_blast_radius() for Step 10
- Implement \_step_deviation_check() for Step 14
- Add structured checklists for Steps 11-13
- Add plan-prd sync check to Ralph STEP 1
- Update /verify, /audit, /refresh skills
- Update documentation (CLAUDE.md, ARCHITECTURE.md)

### Traceability Chain per Phase

Each phase produces:

```
PLAN.md R-PN-NN requirements
  → prd.json stories with acceptanceCriteria
    → Test files with # Tests R-PN-NN markers
      → qa_runner.py verification
        → verification-log.jsonl entries
          → /audit validation
```

### Expected Outcome

| Metric                      | Before          | After                             |
| --------------------------- | --------------- | --------------------------------- |
| Hook test coverage          | 28% (2/9 hooks) | 100% (9/9 hooks)                  |
| Total tests                 | 127             | ~400                              |
| Violation patterns          | 8               | 13+                               |
| Automated QA steps          | 9 of 16         | 11 of 16                          |
| Plan-prd sync               | None            | R-marker + hash                   |
| Production scan enforcement | Warn-only       | Block (security) + warn (hygiene) |
| Overall quality score       | 7.5/10          | ~9/10                             |

---

## Sources

### Project Docs Read

- `PROJECT_BRIEF.md` — Tech stack, constraints, current focus
- `.claude/docs/ARCHITECTURE.md` — System diagram, component inventory, design decisions
- `.claude/docs/PLAN.md` — Previous quality enforcement upgrade plan (the work that created the current system)
- `.claude/docs/HANDOFF.md` — Session state from the last sprint (127 tests, 4/4 stories)
- `.claude/docs/knowledge/lessons.md` — Empty (no lessons captured yet)
- `.claude/docs/decisions/` — Only template and README (no ADRs recorded yet)

### Hook Source Code Read (all files, complete)

- `.claude/hooks/_lib.py` (632 lines) — Full shared library
- `.claude/hooks/pre_bash_guard.py` (98 lines) — 30 DENY_PATTERNS
- `.claude/hooks/post_write_prod_scan.py` (153 lines) — Warn-only scan
- `.claude/hooks/stop_verify_gate.py` (70 lines) — 3-attempt escape hatch
- `.claude/hooks/post_bash_capture.py` (91 lines) — Error capture + marker clear
- `.claude/hooks/post_format.py` (111 lines) — Auto-format + marker set
- `.claude/hooks/qa_runner.py` (773 lines) — Full 16-step pipeline

### Configuration Files Read

- `.claude/settings.json` — Hook wiring (all 6 hooks confirmed)
- `.claude/workflow.json` — Commands, qa_runner config, test_quality config
