# Brainstorm: Complete Solutions for 7 Workflow Issues

**Date**: 2026-03-01
**Problem**: The workflow review identified 7 distinct issues — prompt bloat, QA redundancy, traceability ceremony, verification triple-redundancy, over-engineered research, shell=True contradiction, and three-source-of-truth drift for QA logic. This brainstorm proposes complete solutions for each.

---

## Issue 1: Enormous Prompt Payload / Context Tax

**Current state**: CLAUDE.md (~8.9K tokens) + MCP tools (~36K tokens) + agent/skill bodies loaded per-invocation. Ralph worker gets ~2K+ tokens of instructions before writing a line of code. Total pre-loaded: ~52K tokens (~26% of 200K window).

**Prior work**: Brainstorm `2026-03-01-context-window-optimization.md` already covers CLAUDE.md separation and MCP restructuring. PLAN.md has 3 phases covering this. What's missing is the _agent/skill_ payload reduction.

### Ideas

#### 1A. Tiered instruction loading for ralph-worker.md

Currently ralph-worker.md is 226 lines — all loaded at dispatch. Most of it is Production Standards (15 rules, repeated verbatim from CLAUDE.md) and the qa_receipt JSON schema (20+ lines of example JSON).

**Proposal**: Split ralph-worker.md into two sections:

- **Core instructions** (~80 lines): Startup, build rules, fix loop, return format
- **Reference appendix** (loaded via `Read` on first use): Production standards, qa_receipt schema, manual verification fallback

The worker reads PLAN.md anyway at startup. Add one more `Read` call for the reference appendix. This cuts the dispatch prompt by ~60%.

**Implementation**: Add a `## Reference (load on demand)` section to a separate file `.claude/agents/ralph-worker-reference.md`. Worker's startup step says "Read `.claude/agents/ralph-worker-reference.md` for production standards and QA receipt schema."

- **Pros**: ~146 lines removed from dispatch prompt. Worker keeps full access to all rules. No behavior change. The `Read` call is cheap (~1 turn).
- **Cons**: One extra file to maintain. Worker might skip the read in early turns (unlikely — it's in Startup instructions).

#### 1B. Deduplicate Production Standards across files

The 15 Production Standards appear verbatim in 3 places: CLAUDE.md, ralph-worker.md, and qa.md. CLAUDE.md is the canonical source (tests parse it). The other two are copies.

**Proposal**: Remove the verbatim list from ralph-worker.md and qa.md. Replace with: "Follow Production-Grade Code Standards from CLAUDE.md (15 rules, all non-negotiable). CLAUDE.md is always loaded in context." Since CLAUDE.md is auto-loaded, the rules are always available. No need to repeat them.

- **Pros**: ~30 lines removed from ralph-worker.md, ~15 from qa.md. Single source of truth. No drift risk.
- **Cons**: Worker in worktree might not have CLAUDE.md in context if something goes wrong with context inheritance. (Low risk — Claude Code auto-loads project CLAUDE.md for all agents.)

#### 1C. Compress Ralph orchestrator SKILL.md

Ralph SKILL.md is 465 lines. The JSON schema examples (sprint state, prd.json, verification-log entry, PR body) account for ~120 lines. Error recovery table is ~15 lines.

**Proposal**: Move JSON schema examples to `.claude/docs/knowledge/conventions.md` (which already exists). Orchestrator says "see conventions.md for schema format". Inline only the field names, not full JSON blocks.

- **Pros**: ~120 lines removed from SKILL.md. Conventions.md is the right home for schemas.
- **Cons**: Orchestrator needs one `Read` call. Small risk of schema drift if conventions.md is outdated.

### Recommendation for Issue 1

**Combine 1A + 1B + existing PLAN.md phases (CLAUDE.md separation + MCP restructuring).**

Skip 1C for now — the orchestrator SKILL.md loads only when `/ralph` is invoked (lazy), so the 465 lines are a one-time cost per session, not a per-conversation tax. Focus on the always-loaded overhead first (CLAUDE.md, MCP) and the per-worker overhead (ralph-worker.md repetition).

**Expected total savings**: ~8K (CLAUDE.md) + ~23K (MCP) + ~1.5K (worker dedup) = ~32.5K tokens, dropping pre-loaded from ~52K to ~19.5K.

---

## Issue 2: 12-Step QA Pipeline Redundancy

**Current state**: Steps 6 (security scan), 7 (clean diff), and 12 (production scan) all call `scan_file_violations()` on the same files. They filter by violation category (security IDs, cleanup IDs, all). Steps 10 (plan conformance) and 11 (acceptance) both call `validate_r_markers()`. Steps 3, 4, 5 often run the same pytest command with different labels.

### Ideas

#### 2A. Merge steps 6+7+12 into a single "Code Scan" step

Replace three steps with one that runs `scan_file_violations()` once and reports three sub-sections: Security, Hygiene, Production.

**Implementation**:

- New step: `_step_code_scan()` that reads from violation cache and categorizes by violation_id sets
- Output: Single step result with structured evidence containing three sub-categories
- Failure logic: FAIL if any security or production violation; WARN-in-evidence if hygiene-only

This reduces the step count from 12 to 10, or keeps it at 12 with two freed slots for future checks.

- **Pros**: Eliminates duplicate filtering logic (~80 lines in qa_runner.py). Clearer output — one step, three sub-sections. Violation cache still works, just consumed once instead of three times.
- **Cons**: Changes the QA step numbering (downstream references in docs, tests, ralph-worker.md). Loss of granularity in reporting — but sub-sections preserve this.

#### 2B. Merge steps 10+11 into a single "Plan & Acceptance" step

Both steps validate R-markers. Step 10 adds blast radius checking. Step 11 adds per-criterion pass/fail reporting.

**Implementation**:

- New step: `_step_plan_acceptance()` combining blast radius + R-marker validation + criterion pass/fail
- Single call to `validate_r_markers()`, single scan of changed files vs plan

- **Pros**: Eliminates duplicate `validate_r_markers()` call. Coherent single step — "does the code match the plan?"
- **Cons**: Same renumbering issue as 2A.

#### 2C. Keep 12 steps but deduplicate internal logic

Don't change the step numbers or names. Instead, refactor the internals:

- Steps 6 and 7 become thin filters over violation cache (they already are, mostly)
- Step 12 becomes "everything not caught by 6+7" (deduplicate the loop)
- Step 11 reuses step 10's marker results instead of calling `validate_r_markers()` again

**Implementation**: Add a `_pipeline_context` dict passed through all steps that caches intermediate results. Steps 10 and 11 share marker validation results via this context.

- **Pros**: No renumbering. No downstream changes. Internal efficiency gain. Less code duplication.
- **Cons**: Doesn't address the conceptual redundancy — 12 step numbers still suggest 12 distinct concerns when there are really ~8-9.

#### 2D. Collapse test steps 3+4+5 into configurable "Test Suite" step

Steps 3 (unit), 4 (integration), 5 (regression) often run the same `pytest` command. The distinction is which gate command is configured.

**Implementation**: Single `_step_tests()` that runs all configured gate commands (unit, integration, regression) and reports results per command as sub-items. One step, multiple commands.

- **Pros**: Eliminates artificial separation between test types when they're all pytest. Clearer output.
- **Cons**: Loses the ability to skip integration tests independently via adaptive QA. Would need sub-step skip logic.

### Recommendation for Issue 2

**2C (keep 12 steps, deduplicate internals) + partial 2D (share test infrastructure).**

Rationale: Renumbering steps (2A/2B) creates a cascade of changes across ralph-worker.md, qa.md, verify/SKILL.md, test files, and documentation. The maintenance cost of renumbering exceeds the clarity gain. Instead:

1. Add a `pipeline_context: dict` parameter threaded through `_run_step()` calls
2. Steps 10 and 11 share `validate_r_markers()` results via context
3. Steps 6, 7, 12 already share the violation cache — keep this, just ensure step 12 doesn't re-scan what 6+7 already reported (add a `_reported_violations` set to context)
4. Keep steps 3/4/5 separate — adaptive QA phase-type skipping depends on this separation

**Net code reduction**: ~40-60 lines in qa_runner.py. Zero downstream documentation changes.

---

## Issue 3: R-PN-NN Traceability Ceremony Overhead

**Current state**: Every requirement needs an ID in PLAN.md Done When, a matching prd.json criterion, a `# Tests R-PN-NN` marker in test files, a verification-log entry, and audit validation. 5 touchpoints per requirement.

### Ideas

#### 3A. Auto-generate R-markers from prd.json (eliminate manual markers in tests)

Instead of requiring developers to manually add `# Tests R-P1-01` markers to test files, auto-detect which tests cover which criteria by:

1. Parsing test function names against criterion descriptions
2. Using the `testFile` field in prd.json to map criteria → test files
3. Running the test and checking which criteria's behaviors are exercised

**Implementation**: Enhance `validate_r_markers()` to use `testFile` from prd.json as the primary mapping. If `testFile` is specified and the test passes, the criterion is considered covered. Fall back to `# Tests R-PN-NN` markers only when `testFile` is null.

- **Pros**: Eliminates the most tedious manual step. prd.json already has a `testFile` field — this just uses it. Worker doesn't need to manually write markers.
- **Cons**: Less precise — a test file might exist but not actually test the specific criterion. The marker forces explicit intent.

#### 3B. Generate prd.json entirely from PLAN.md (eliminate manual prd.json editing)

The `/plan` skill already auto-generates prd.json in Step 7. The issue is that after generation, prd.json can drift from PLAN.md. Plan-PRD sync check catches this but adds ceremony.

**Proposal**: Make prd.json strictly derived — never manually edited. Add a `plan_hash` field (already exists). Before every Ralph run, regenerate prd.json from PLAN.md if hash doesn't match. Eliminate manual prd.json editing entirely.

- **Pros**: prd.json is always in sync. No drift detection needed — it's always fresh.
- **Cons**: Requires a reliable PLAN.md → prd.json parser. Currently this is done by the LLM (Step 7 of /plan), not by deterministic code. Making it deterministic would require a PLAN.md parser.

#### 3C. Simplify to 3 touchpoints: PLAN.md → test file → verification log

Eliminate prd.json as an intermediate artifact. Ralph reads criteria directly from PLAN.md's Done When sections. Test files link to criteria via markers. Verification log records results.

**Implementation**:

- Ralph parses PLAN.md for Done When criteria per phase (regex: `R-P\d+-\d{2}`)
- Gate commands move to PLAN.md (already partially there as Verification Command)
- prd.json becomes optional — only needed for story metadata (phase_type, passed status)
- Reduce prd.json to: `{ stories: [{ id, phase, phase_type, passed, verificationRef }] }` — criteria and gate commands come from PLAN.md

- **Pros**: Single source of truth for requirements (PLAN.md). No sync checks needed. Simpler workflow.
- **Cons**: PLAN.md becomes load-bearing (parsing errors break Ralph). prd.json currently has useful structured fields (testType, testFile) that PLAN.md's free-text format doesn't naturally encode.

#### 3D. Keep ceremony but automate it end-to-end

Accept that 5 touchpoints is the right level of rigor, but automate every transition:

1. `/plan` already generates PLAN.md → prd.json (Step 7) ✓
2. Builder/worker writes test with marker → **automate**: have worker use a template that auto-includes the marker based on which criterion it's implementing
3. QA validates markers → already automated by qa_runner.py ✓
4. Verification log → already automated ✓
5. Audit validates chain → already automated ✓

The only manual step is #2 (writing test markers). Automate it with a convention: if the worker creates a test file matching the `testFile` pattern from prd.json, markers are auto-inferred.

- **Pros**: No ceremony reduction, but all ceremony is automated. Full traceability preserved. No architectural changes.
- **Cons**: Doesn't reduce complexity — just makes it invisible. Still 5 touchpoints, still documentation overhead.

### Recommendation for Issue 3

**3A (auto-detect from testFile) + 3D (automate marker insertion).**

Rationale: The traceability chain is actually valuable — it catches real bugs (test exists but doesn't test what it claims). The problem isn't the chain, it's the manual labor. Solution:

1. Enhance `validate_r_markers()` to accept `testFile` from prd.json as primary evidence (already has the field, just needs to use it)
2. Keep `# Tests R-PN-NN` markers as optional supplementary evidence (don't require them if testFile mapping is clear)
3. Worker template includes auto-marker insertion: when implementing criterion R-P1-01, the test function docstring auto-includes `# Tests R-P1-01`

This preserves traceability while eliminating ~80% of the manual ceremony. The marker becomes confirmation, not requirement.

---

## Issue 4: Ralph's Triple-Redundant Verification

**Current state**: Worker runs 12-step QA → Ralph validates qa_receipt (4 checks) → Ralph runs spot-check (gate commands) → Ralph runs cumulative regression. Same tests run 2-3 times.

### Ideas

#### 4A. Trust the receipt, keep only cumulative regression

Remove the spot-check entirely. The qa_receipt validation (Step 6, sub-steps a-d) already verifies the worker's QA was complete and passed. The spot-check re-runs the same gate commands the worker already ran.

Keep cumulative regression as the ONLY post-merge check — this is the one thing the worker CANNOT verify (it doesn't have the merged feature branch state).

**Implementation**:

- Remove spot-check block from Ralph SKILL.md Step 6 (PASSED section, item 5)
- Keep qa_receipt validation (items 1a-1d) — this is cheap (JSON parsing, no subprocess)
- Keep cumulative regression (item 6) — this is the only unique check
- Merge step numbering adjusts accordingly

- **Pros**: Eliminates one full round of gate commands per story (~30-60 seconds saved). Cumulative regression is strictly more valuable (tests ALL prior stories, not just current). No loss of safety — receipt validation catches lying workers, regression catches integration issues.
- **Cons**: If the worker fabricated a qa_receipt (malformed or hand-constructed), the spot-check was the safety net. But: receipt validation sub-steps (a-d) already catch fabrication by checking step count, overall result, and criteria coverage.

#### 4B. Make spot-check probabilistic

Instead of always running spot-check, run it randomly (e.g., 50% of stories) or only on the first story and last story.

- **Pros**: Half the overhead. Still catches systematic issues.
- **Cons**: Adds randomness to a deterministic pipeline. Harder to reason about. Not worth the complexity.

#### 4C. Replace spot-check with a checksum/hash verification

Instead of re-running gate commands, have the worker include test output hashes in the qa_receipt. Ralph verifies the hashes match the merged code state.

- **Pros**: Verification without re-running tests.
- **Cons**: Complex to implement. Hash of what? Test output isn't deterministic (timestamps, ordering). Over-engineered.

#### 4D. Merge spot-check INTO cumulative regression

Don't run spot-check separately — just run the regression suite, which inherently includes the current story's tests. If the current story's tests are in the regression suite, spot-check is redundant.

**Implementation**: Ensure `commands.regression` in workflow.json runs ALL tests including the current story's. Then remove the separate spot-check.

- **Pros**: One test run instead of two. Same coverage. Simpler Step 6.
- **Cons**: If regression command doesn't include story-specific tests (e.g., different test directories), this loses coverage. Need to verify regression scope.

### Recommendation for Issue 4

**4A (trust receipt, keep only regression) with 4D's insight (ensure regression covers story tests).**

Specific implementation:

1. Remove spot-check from Ralph SKILL.md Step 6
2. Keep qa_receipt validation (cheap JSON checks)
3. Keep cumulative regression — verify that `commands.regression` in workflow.json runs ALL project tests (including current story's)
4. If regression is not configured, fall back to running story gate commands as regression (current spot-check behavior, but framed as "regression fallback" not "spot-check")

**Result**: One post-merge test run instead of two. Receipt validation catches worker dishonesty. Regression catches integration issues. No loss of safety.

---

## Issue 5: Over-Engineered Research Pipeline

**Current state**: 8 phases, ~2,043 lines across 13 files, confidence trees, authority levels, claims registries, gap analysis. Used primarily to produce a markdown document with implementation recommendations.

### Ideas

#### 5A. Collapse to 3 phases: Survey → Synthesize → Specify

Most research sessions don't need all 8 phases. The core value is: find sources (Survey), understand them (Synthesize), produce actionable output (Specify).

**Proposed 3-phase pipeline**:

1. **Survey** (merges current phases 0-2): Define scope, find sources, extract claims
2. **Synthesize** (merges current phases 3-5): Deep-read key sources, analyze contradictions, compile findings
3. **Specify** (merges current phases 6-7): Generate implementation spec, validate quality

**Implementation**: Three phase files instead of eight. Each is longer but self-contained. The dispatcher stays thin.

- **Pros**: 5 fewer files. Simpler mental model. Fewer phase transitions (each transition burns context on status updates). Still covers all activities — just grouped logically.
- **Cons**: Longer individual phase files. Harder to resume mid-phase if interrupted. Loss of granular progress tracking.

#### 5B. Make phases opt-in via presets

Keep all 8 phases but make them selectable via presets that skip phases:

- `--quick`: phases 0, 2, 5 only (plan, survey, compile)
- `--standard`: phases 0, 1, 2, 3, 5, 6 (skip failure analysis and validate)
- `--thorough`: all 8 phases

This already partially exists (`--quick` and `--thorough` presets in the dispatcher).

**Implementation**: Extend the dispatcher's decision tree to support `--standard` as default, reducing the typical run from 8 to 6 phases.

- **Pros**: Preserves full capability for thorough research. Reduces typical runs. No file changes — just dispatcher logic.
- **Cons**: Doesn't reduce the file count or maintenance burden. Users must know which preset to use.

#### 5C. Extract research into a separate installable package

Research is optional per-project. Most ADE instances (web apps, APIs, CLI tools) never use `/research`. The 13 files (~2,043 lines) are dead weight.

**Implementation**:

- Move `.claude/commands/research*.md` and `.claude/commands/research-phases/` to a separate repo or optional directory
- `new-ade.ps1` gets a `--with-research` flag
- Research files are not copied unless requested
- `update-ade.ps1` only updates research files if they exist

- **Pros**: Non-research projects drop ~2K lines. Cleaner `.claude/commands/`. Research can evolve independently.
- **Cons**: Two repos to maintain. Versioning complexity. Research users need extra setup.

#### 5D. Simplify the confidence/authority model

The confidence tree (HIGH/LOW/CONTESTED) and authority levels (FOUNDATIONAL/CORROBORATING/SUPPLEMENTARY) are well-designed but rarely change the outcome. In practice, most research produces "HIGH confidence" or "not enough sources" — the nuanced middle ground (CONTESTED with mixed authority levels) almost never occurs.

**Proposal**: Replace the 3-tier authority model with binary: **Primary** (peer-reviewed, vendor docs) vs **Secondary** (everything else). Replace confidence tree with: HIGH if 2+ primary sources agree, LOW otherwise.

- **Pros**: Simpler to explain, simpler to implement, covers 95% of cases.
- **Cons**: Loses nuance for edge cases. The current model is well-documented and already implemented.

### Recommendation for Issue 5

**5B (opt-in presets with better defaults) + 5C (extract to optional package) + 5D (simplify confidence model).**

Rationale:

1. Make `--standard` (6 phases) the default, `--thorough` (8 phases) opt-in. This handles 90% of research needs.
2. Make research files optional in deployment — `new-ade.ps1 --with-research` copies the files, without it they're omitted.
3. Simplify confidence to binary (HIGH/LOW) with primary/secondary sources. Keep the detailed rubric in research-reference.md for users who want it, but the dispatcher and phase files use the simpler model.

**Net reduction**: Most projects: -2,043 lines (research not installed). Research projects: same files, simpler defaults, fewer mandatory phases.

---

## Issue 6: shell=True Contradiction in qa_runner.py

**Current state**: `_run_command()` at line 321 uses `subprocess.run(cmd, shell=True, ...)`. Production standard #11 bans `subprocess` with `shell=True` and dynamic arguments. The hook file exclusion in `post_write_prod_scan.py` (`_is_hook_file()`) exists to exempt hooks from scanning themselves.

### Ideas

#### 6A. Convert to shell=False with shlex.split()

Replace `shell=True` with `shell=False` and parse commands using `shlex.split()`.

**Implementation**:

```python
import shlex
def _run_command(cmd: str, timeout: int = 120) -> tuple[int, str, str]:
    try:
        args = shlex.split(cmd)
        result = subprocess.run(args, shell=False, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"
    except (OSError, ValueError) as exc:
        return -1, "", str(exc)
```

- **Pros**: Eliminates the contradiction. Follows the project's own rules. Safer against injection.
- **Cons**: `shlex.split()` doesn't handle complex shell syntax (pipes, redirects, `&&`, `||`, subshells). Gate commands like `python -m pytest tests/ -v && ruff check .` would break. Many gate commands in prd.json use shell features.

#### 6B. Use shell=True but with a controlled allowlist

Keep `shell=True` but only for commands that match a known-safe pattern. Reject commands containing dangerous shell metacharacters beyond what's needed for pipes/redirects.

- **Pros**: Pragmatic. Allows shell features. Blocks injection.
- **Cons**: Allowlist maintenance. Complex regex. Half-measure.

#### 6C. Accept the pragmatic inconsistency and document it

The production standard exists to prevent SQL/shell injection from untrusted user input. qa_runner.py's commands come from prd.json, which is generated by the AI from PLAN.md — not from untrusted external input. The threat model is different.

**Implementation**: Add a comment in `_run_command()` documenting why `shell=True` is acceptable here:

```python
# shell=True is used here intentionally: gate commands from prd.json may contain
# shell syntax (pipes, &&, redirects). These commands are generated by the workflow
# (not from untrusted user input), so the injection risk is minimal.
# This is an acknowledged exception to Production Standard #11.
```

Also add `qa_runner.py` to the violation scanner's exempt list (it's already exempt via `_is_hook_file()`).

- **Pros**: Honest. No broken functionality. Documents the design decision.
- **Cons**: Still technically inconsistent. A purist would object.

#### 6D. Split command execution into shell and non-shell paths

Add a `use_shell` parameter to `_run_command()`. Simple commands (single executable + args) use `shell=False`. Complex commands (pipes, `&&`, redirects) use `shell=True`.

**Implementation**:

```python
def _run_command(cmd: str, timeout: int = 120) -> tuple[int, str, str]:
    needs_shell = any(c in cmd for c in ('|', '&&', '||', '>', '<', ';', '`', '$'))
    if needs_shell:
        result = subprocess.run(cmd, shell=True, ...)
    else:
        result = subprocess.run(shlex.split(cmd), shell=False, ...)
```

- **Pros**: Uses `shell=False` when possible. Documented, deterministic decision.
- **Cons**: Edge cases in the detection heuristic. `$VAR` in commands would trigger shell mode unnecessarily. More code for marginal safety gain.

### Recommendation for Issue 6

**6C (document the exception) + 6D (split paths for best-effort).**

Rationale: The threat model genuinely doesn't apply — prd.json commands aren't untrusted input. But we should still minimize `shell=True` usage:

1. Add the documentation comment to `_run_command()`
2. Implement the simple shell-detection heuristic from 6D
3. Commands without shell metacharacters run with `shell=False`
4. Commands with pipes/redirects/chaining use `shell=True` (documented)

This satisfies both the practical need (shell features work) and the principle (minimize shell=True usage).

---

## Issue 7: Manual Mode and Ralph Mode Share Logic, Express It Differently

**Current state**:

- QA pipeline defined in: `qa.md` (checklist, 78 lines), `qa_runner.py` (executable, 1171 lines), `ralph-worker.md` (inline, ~40 lines summarizing all 12 steps)
- Production standards defined in: `CLAUDE.md` (canonical), `ralph-worker.md` (copy), `qa.md` (partial copy via step 12)
- Builder escalation in: `builder.md` (thresholds), `ralph-worker.md` (override: "DO NOT apply")

Three sources of truth means three places to update when the QA pipeline changes.

### Ideas

#### 7A. Make qa_runner.py the single source of truth, all agents reference it

qa_runner.py IS the executable pipeline. qa.md and ralph-worker.md should reference it, not redefine it.

**Implementation**:

- `qa.md` becomes: "Run qa_runner.py with these arguments. Parse the JSON output. Report results." (~20 lines instead of 78)
- `ralph-worker.md` becomes: "Run qa_runner.py. If FAIL, fix and re-run. Repeat until PASS." (~10 lines for QA section instead of ~40)
- Production standards: reference CLAUDE.md only, never copy
- Step definitions live ONLY in qa_runner.py's `STEP_NAMES` dict and step functions

- **Pros**: True single source of truth. Change qa_runner.py, everything updates. No drift possible. Major line reduction in agent files.
- **Cons**: Agents become dependent on qa_runner.py being available and working. If qa_runner.py breaks, both Manual and Ralph modes break. (But it's already tested with ~84K lines of tests.)

#### 7B. Extract a shared "QA contract" document

Create `.claude/docs/knowledge/qa-contract.md` that defines what each step checks, what constitutes PASS/FAIL, and what the step names are. All three consumers (qa.md, ralph-worker.md, qa_runner.py) reference this document.

- **Pros**: Clean separation: contract (what) vs implementation (how). Agents know what to check, qa_runner.py knows how.
- **Cons**: Now there are FOUR files instead of three. The contract document is yet another thing to maintain.

#### 7C. Inline qa.md into verify/SKILL.md and delete qa.md

The QA agent is only invoked via `/verify`. Its instructions are in verify/SKILL.md (149 lines, references qa_runner.py) AND qa.md (78 lines, defines steps). Merge them.

**Implementation**:

- Delete qa.md
- verify/SKILL.md already tells QA to run qa_runner.py — just ensure it has all necessary context
- The `agent: qa` frontmatter in verify/SKILL.md already invokes the QA agent persona

- **Pros**: One file for verification instead of two. No orphan agent file.
- **Cons**: qa.md is referenced in CLAUDE.md's Role Commands table (`Act as QA → qa.md`). Would need to update the reference to verify/SKILL.md. But `Act as QA` is rarely used in Ralph mode anyway.

#### 7D. Create a builder-qa shared module with mode-specific overrides

Extract common behavior (TDD rules, test-first, selective staging, production standards) into a shared document. Builder.md and ralph-worker.md import from it and add mode-specific overrides (escalation thresholds for builder, persistence for worker).

**Implementation**: `.claude/agents/shared-build-rules.md` with:

- TDD rules
- Selective staging
- Production standards reference (→ CLAUDE.md)
- QA pipeline reference (→ qa_runner.py)

Builder.md adds: escalation thresholds, "one phase only" rule
Ralph-worker.md adds: "no escalation", persistence, qa_receipt requirement

- **Pros**: Common rules defined once. Mode-specific behavior clearly separated.
- **Cons**: Another file. Agents now have dependencies on a shared module — more coupling.

### Recommendation for Issue 7

**7A (qa_runner.py as single source) + 7C (merge qa.md into verify/SKILL.md).**

Specific implementation:

1. **qa.md** → deleted. Its 12-step checklist is redundant with qa_runner.py.
2. **verify/SKILL.md** → already references qa_runner.py. Add one line: "For step details, see `STEP_NAMES` in qa_runner.py." Remove any step re-definitions.
3. **ralph-worker.md QA section** → reduce to: "Run qa_runner.py. Parse output. If FAIL, fix and re-run. Return qa_receipt = qa_runner.py JSON output." (~10 lines)
4. **Production standards in ralph-worker.md** → replace with: "Follow Production-Grade Code Standards defined in CLAUDE.md."
5. **CLAUDE.md Role Commands** → update: `Act as QA → /verify` (skill) instead of `qa.md` (agent file)

**Net reduction**: ~80 lines removed (qa.md), ~50 lines reduced (ralph-worker.md), ~15 lines reduced (verify/SKILL.md duplication). Single source of truth: qa_runner.py for pipeline logic, CLAUDE.md for production standards.

---

## Sources

- Project files read: CLAUDE.md, WORKFLOW.md, PROJECT_BRIEF.md, ARCHITECTURE.md, PLAN.md
- Agent files: architect.md, builder.md, qa.md, ralph-worker.md, librarian.md
- Skill files: ralph/SKILL.md, verify/SKILL.md, all 11 skills (line counts)
- Hook files: all 6 hooks + \_lib.py + qa_runner.py + test_quality.py
- Documentation: knowledge/lessons.md, knowledge/planning-anti-patterns.md, knowledge/conventions.md
- Prior brainstorm: 2026-03-01-context-window-optimization.md
- Research pipeline: research.md, 8 phase files, research-status.md, research-validate.md, cite.md

---

## Build Strategy

### Module Dependencies

```
Issue 6 (shell=True fix)          ← standalone, no deps
    │
Issue 7 (single source of truth) ← standalone, no deps
    │
Issue 2 (QA dedup)               ← depends on Issue 7 (qa.md removal changes step references)
    │
Issue 3 (traceability)           ← depends on Issue 2 (validate_r_markers sharing)
    │
Issue 1 (prompt tax)             ← depends on Issue 7 (ralph-worker.md reduction)
                                 ← depends on existing PLAN.md phases (CLAUDE.md separation)
    │
Issue 4 (triple verification)    ← depends on Issue 2 (QA pipeline clarity)
    │
Issue 5 (research pipeline)      ← standalone, no deps on other issues
```

### Build Order

**Phase 1 — Foundation (parallel-safe, no deps between them)**:

1. Issue 6: Document shell=True exception + add shell detection heuristic in `_run_command()`
2. Issue 7: Delete qa.md, update verify/SKILL.md, slim ralph-worker.md QA section
3. Issue 5: Extract research to optional package, simplify confidence model

**Phase 2 — Core improvements (sequential, depends on Phase 1)**: 4. Issue 2: Add `pipeline_context` dict to qa_runner.py for shared intermediate results 5. Issue 3: Enhance `validate_r_markers()` to use `testFile` field from prd.json 6. Issue 1: Execute existing PLAN.md (CLAUDE.md separation), then slim ralph-worker.md

**Phase 3 — Verification optimization (depends on Phase 2)**: 7. Issue 4: Remove spot-check from Ralph SKILL.md, verify regression coverage

### Testing Pyramid

- **Unit tests** (70%): qa_runner.py pipeline_context, validate_r_markers with testFile, \_run_command shell detection
- **Integration tests** (20%): Full qa_runner.py pipeline with new context sharing, Ralph end-to-end with receipt-only validation
- **E2E tests** (10%): Manual — run /ralph on a real feature to verify the full pipeline works with changes

**Existing test coverage**: 15 test modules with ~400K+ bytes of tests. Most changes are internal refactors, so existing tests should catch regressions. New tests needed only for: pipeline_context sharing (Issue 2), testFile-based marker validation (Issue 3), and shell detection heuristic (Issue 6).

### Risk Mitigation Mapping

- Risk: Deleting qa.md breaks `Act as QA` manual mode → Mitigation: Update CLAUDE.md Role Commands table to point to /verify. Test manual invocation. (HIGH confidence)
- Risk: shell detection heuristic has false positives → Mitigation: Err on the side of shell=True (safe fallback). Comprehensive test cases for edge patterns. (HIGH confidence)
- Risk: pipeline_context introduces bugs in step ordering → Mitigation: Existing test suite for qa_runner.py (84K+ lines). Add targeted tests for context sharing. (HIGH confidence)
- Risk: testFile-based validation misses uncovered criteria → Mitigation: Keep R-PN-NN markers as optional supplementary evidence. Warn (not fail) if testFile exists but marker is absent. (MEDIUM confidence)
- Risk: Removing spot-check allows bad merges → Mitigation: Cumulative regression catches integration issues. Receipt validation catches fabrication. Monitor first 5 Ralph runs post-change. (MEDIUM confidence)
- Risk: Research extraction breaks /build-system pipeline → Mitigation: /build-system checks for research availability before invoking. Graceful skip if not installed. (HIGH confidence)

### Recommended Build Mode

**Manual Mode** for Issues 6, 7, 5 (documentation + file reorganization). **Ralph Mode** for Issues 2, 3, 4 (code changes to qa_runner.py and \_lib.py with testable acceptance criteria). **Hybrid**: Manual for Phase 1 (foundation), Ralph for Phases 2-3 (code changes with existing test coverage).

Justification: Issues 6/7/5 are primarily file moves, deletions, and documentation updates — no TDD loop needed. Issues 2/3/4 are internal refactors to well-tested Python code — exactly what Ralph excels at (clear criteria, existing tests, contained blast radius).
