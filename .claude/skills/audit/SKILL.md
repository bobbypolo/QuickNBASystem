---
name: audit
description: Run end-to-end workflow integrity audit — validates PLAN.md, prd.json, tests, verification logs, architecture, hooks, git hygiene, test quality, and error handling resilience.
context: fork
---

# /audit — End-to-End Workflow Integrity Audit

Run all 9 audit sections in order. For each check, record PASS, FAIL, or SKIP with evidence. Missing files are SKIP (not FAIL) with reason.

## Section 1: PLAN.md Completeness

Read `.claude/docs/PLAN.md`. If not found: **SKIP** `"PLAN.md not found"`.

- [ ] Goal section filled (not placeholder brackets)
- [ ] At least 1 phase defined
- [ ] Every phase has: Changes table, Interface Contracts, Data Flow, Testing Strategy, Done When, Verification Command
- [ ] All Done When items use R-PN-NN format (regex: `R-P\d+-\d{2}`)
- [ ] Risks & Mitigations section filled (not placeholder)
- [ ] Dependencies section present

## Section 2: prd.json <-> PLAN.md Alignment

Read `.claude/prd.json`. If not found: **SKIP** `"prd.json not found"`.

- [ ] `version` field equals `"2.0"`
- [ ] Forward check: every prd.json acceptanceCriteria `id` exists in PLAN.md Done When
- [ ] Backward check: every PLAN.md R-PN-NN ID appears in at least one prd.json story's criteria
- [ ] Story count vs phase count comparison (flag mismatches)
- [ ] `gateCmds` entries match PLAN.md Verification Commands (semantic comparison)
- [ ] `planRef` points to an existing file
- [ ] `plan_hash` check: if prd.json has a `plan_hash` field, compute normalized hash via `compute_plan_hash()` from `_qa_lib.py` (hashes only R-marker lines, sorted) and compare against stored hash. **FAIL** if mismatch (R-marker criteria changed but prd.json not regenerated). **SKIP** if `plan_hash` field absent (legacy prd.json without hash). **PASS** if hashes match.

## Section 3: Test Coverage Traceability

For each R-PN-NN ID found in prd.json:

- [ ] Grep test files for `# Tests R-PN-NN` marker — flag untraceable criteria (no linked test)
- [ ] If prd.json specifies `testFile`: verify the file path exists (Glob)
- [ ] Flag orphan tests: test files with `# Tests R-PN-NN` markers that don't match any prd.json criterion
- [ ] Summary: X/Y criteria traceable, Z orphan tests

If no test files exist: **SKIP** `"No test files found"`.

## Section 4: Verification Log Integrity

Read `.claude/docs/verification-log.jsonl` (JSONL format — one JSON object per line). If the file is missing and no phases are completed: **SKIP** `"No verification log (no phases completed)"`. If missing but stories are marked `passed: true`: **FAIL** `"Stories passed but no verification log"`.

**Namespace isolation**: Use `read_verification_log(path, plan_hash=current_hash)` from `_qa_lib.py` to scope the audit to the current planning cycle. Read the current plan hash from `prd.json["plan_hash"]`. If `plan_hash` is absent from prd.json (legacy format), fall back to `read_verification_log(path)` (no filter) with a **WARNING** `"prd.json has no plan_hash — reading all verification entries (no namespace isolation)"`.

Legacy entries (entries without a `plan_hash` field) are excluded from the filtered view. If any legacy entries exist, emit an informational **WARNING** `"[N] legacy entries without plan_hash found — these belong to prior planning cycles and are excluded from this audit"`. This is NOT a failure.

Parse each line with `json.loads()`. If a line fails to parse, emit a **WARNING** `"Corrupt JSONL line [N]: skipping"` and continue processing remaining lines. Do not treat corrupt lines as FAIL — only warn.

- [ ] Every story with `passed: true` in prd.json has at least one JSONL entry with matching `story_id` and `overall_result: "PASS"` (within current plan_hash namespace)
- [ ] No unresolved FAIL entries: for each `story_id`, the most recent entry should be `"PASS"` (a FAIL followed by a later PASS is resolved)
- [ ] Each entry contains required fields: `story_id`, `timestamp`, `overall_result`
- [ ] If entry has `qa_steps` array: verify each step has `step`, `name`, `result` fields
- [ ] If entry has `spot_check` object: verify it contains gate command results

## Section 5: Architecture Conformance

Read `.claude/docs/ARCHITECTURE.md`. If not found: **SKIP** `"ARCHITECTURE.md not found"`.

- [ ] Content is populated (not just placeholder brackets)
- [ ] No `[AUTO-DETECTED]` tags remaining unchecked
- [ ] Components listed match actual file structure (spot-check top-level dirs)

## Section 6: Hook Chain Health

Check all 6 hook files exist in `.claude/hooks/`:

- [ ] `pre_bash_guard.py` exists
- [ ] `post_format.py` exists
- [ ] `post_bash_capture.py` exists
- [ ] `stop_verify_gate.py` exists
- [ ] `post_compact_restore.py` exists
- [ ] `post_write_prod_scan.py` exists
- [ ] `_lib.py` exists and importable (`python -c "import sys; sys.path.insert(0,'.claude/hooks'); import _lib; print('OK')"`)

Check supporting utilities exist:

- [ ] `qa_runner.py` exists and runnable (`python .claude/hooks/qa_runner.py --help`)
- [ ] `test_quality.py` exists and runnable (`python .claude/hooks/test_quality.py --help`)

Check runtime state via `.claude/.workflow-state.json`:

- [ ] `needs_verify` field: non-null (needs verification) or null (clean)
- [ ] `stop_block_count` field: value > 0 (blocked) or 0 (clean)
- [ ] `prod_violations` field: non-null (violations pending) or null (clean)
- [ ] `.claude/workflow.json` valid JSON (if present)

## Section 7: Git Hygiene & Production-Grade Code

If not in a git repository: **SKIP** `"Not a git repository"`.

- [ ] No secrets in uncommitted changes: grep staged/unstaged for `.env` patterns, API keys, tokens
- [ ] No debug prints in committed source files: `grep -rn "print(\|console\.log\|debugger\|binding\.pry" --include="*.py" --include="*.js" --include="*.ts" src/ lib/` (adjust paths)
- [ ] Conventional commit format in recent commits: `git log --oneline -10` all match `feat:|fix:|docs:|chore:|refactor:|test:|ci:`
- [ ] No merge conflict markers in tracked files: `grep -rn "<<<<<<\|======\|>>>>>>" --include="*.py" --include="*.js" --include="*.ts" --include="*.md"`
- [ ] Work is on a feature branch (not main/master): `git rev-parse --abbrev-ref HEAD`
- [ ] No TODO/HACK/FIXME/XXX in committed source files: `grep -rn "TODO\|HACK\|FIXME\|XXX" --include="*.py" --include="*.js" --include="*.ts" src/ lib/`
- [ ] No bare except/catch blocks in committed source files
- [ ] No hardcoded URLs, ports, or credentials in source files
- [ ] No unused imports in committed source files (ruff/eslint if available)
- [ ] No `git add -A` or `git add .` in recent git reflog: `git reflog --format='%gs' -20`
- [ ] `.gitignore` includes: `.claude/worktrees/`, `.claude/.workflow-state.json`, `.claude/docs/verification-log.md`

## Section 8: Test Quality Scan (Mock Abuse & Assertion Quality)

Run the automated test quality analyzer for programmatic detection:

```bash
python .claude/hooks/test_quality.py --dir .claude/hooks/tests --prd .claude/prd.json
```

Parse the JSON output and report findings. If `test_quality.py` is not available, fall back to manual analysis below.

For each test file containing `# Tests R-PN-NN` markers:

If no test files with R-PN-NN markers exist: **SKIP** `"No traceable test files found"`.

### Self-mock detection

- Does the test import `mock`/`patch`/`MagicMock`?
- Is the mock target the same module/function the test claims to test?
- **YES → FAIL** `"Self-mocking: test mocks what it is supposed to test"`

### Assertion-free test detection

- Does the test contain `assert`/`assertEqual`/`expect`/`assert_called` statements?
- **ZERO assertions → FAIL** `"Assertion-free: test proves nothing"`

### Strategy mismatch detection

- Read prd.json `testType` for this criterion's R-PN-NN ID
- Read PLAN.md Testing Strategy Real/Mock column for this test
- **If Strategy says "Real" but test uses mock/patch → FAIL** `"Strategy mismatch: plan says Real, test uses Mock"`

### Heavy mock detection

- Count `mock`/`patch` decorators + context managers in test
- Count real (non-mocked) dependencies
- **If >80% dependencies mocked → WARNING** `"Heavily mocked: [X]% dependencies are mocked"`

### Mock-only assertion detection

- If test ONLY asserts `mock.called` / `mock.call_count` / `mock.assert_called_with`
- AND does NOT assert any return value or state change
- **→ WARNING** `"Mock-only assertions: verifies call happened but not correctness"`

## Section 9: Error Handling Resilience

Analyze error handling quality in changed source files using the `silent-failure-hunter` agent from the `pr-review-toolkit` plugin.

**SKIP conditions**:

- `"No source files changed"` — if `git diff main...HEAD --name-only --diff-filter=d` returns no source files (`.py`, `.js`, `.ts`)
- `"pr-review-toolkit plugin not available"` — if the `silent-failure-hunter` agent cannot be invoked

**Procedure**:

1. Get changed source files: `git diff main...HEAD --name-only --diff-filter=d` filtered to `*.py`, `*.js`, `*.ts`
2. If no source files in the diff: **SKIP** `"No source files changed"`
3. Invoke `silent-failure-hunter` agent against the changed files. If agent is not available: **SKIP** `"pr-review-toolkit plugin not available"`
4. Collect findings by severity: CRITICAL, HIGH, MEDIUM

The `silent-failure-hunter` agent analyzes:

- Catch specificity (bare except/catch blocks)
- Fallback masking (errors swallowed without logging)
- Error propagation (exceptions re-raised with context)
- Logging quality (structured error messages)

**PASS/FAIL criteria**:

- **PASS** if no CRITICAL findings
- **FAIL** if any CRITICAL findings detected

HIGH and MEDIUM findings are reported as warnings but do not cause FAIL.

- [ ] Changed source files identified via `git diff main...HEAD --name-only --diff-filter=d`
- [ ] `silent-failure-hunter` agent invoked against changed files
- [ ] No CRITICAL error handling findings (PASS) or CRITICAL findings present (FAIL)
- [ ] HIGH/MEDIUM findings listed as warnings

## Output Format

```
## Audit Report — [date]

### Summary: [X]/9 sections PASS — Overall: [PASS/FAIL]

### Section 1: PLAN.md Completeness — [PASS/FAIL/SKIP]
[Per-check results with evidence]

### Section 2: prd.json Alignment — [PASS/FAIL/SKIP]
[Per-check results]

... [Sections 3-9] ...

### Critical Issues (must fix)
- [List of FAIL items across all sections]

### Warnings (should fix)
- [List of WARNING items]

### Clean Items
- [List of PASS items confirming workflow integrity]
```
