# Brainstorm: Context Bloat Reduction + Ralph Perfection — Full Picture

**Date**: 2026-03-02
**Problem**: Each Claude Code conversation in this project loads ~21,000 tokens before the user types anything. Reduce this to ~16,700 tokens (20% reduction) while preserving all workflow functionality. Additionally, address known Ralph bugs, skill-level token waste, and runtime efficiency to make Ralph production-perfect for all projects.

**Cross-references**: Incorporates findings from `2026-03-02-ralph-perfection-infinite-context.md` (bugs, parallel execution, SKILL.md optimization, anti-gaming completion, infinite context architecture).

## Current Token Budget (Measured)

| Component                                                | Tokens      | Controllable?                         |
| -------------------------------------------------------- | ----------- | ------------------------------------- |
| Claude Code system prompt + built-in instructions        | ~2,000      | No                                    |
| 18 built-in tool schemas (Read, Write, Edit, Bash, etc.) | ~9,900      | No                                    |
| 185 deferred MCP tool names in ToolSearch description    | ~1,600      | **Yes** — move servers to per-project |
| Project CLAUDE.md (121 lines)                            | ~1,400      | **Yes** — trim sections               |
| Global + User CLAUDE.md + MEMORY.md                      | ~400        | Minimal                               |
| Skill descriptions (11 skills, frontmatter only)         | ~300        | Minimal                               |
| Git status + branch info                                 | ~200        | No                                    |
| Hook output (SessionStart only)                          | ~170        | Minimal                               |
| **Subtotal: System prompt**                              | **~15,970** |                                       |
| First-turn eager reads (5 files from Quick Start)        | ~6,950      | **Yes** — reduce file count           |
| **Total first turn**                                     | **~22,920** |                                       |

**Target: ~16,700 tokens (reduce ~6,200)**

## Ideas

### 1. Trim Quick Start from 5 files to 2

Current CLAUDE.md Quick Start instructs Claude to read 5 files on first turn:

- `PROJECT_BRIEF.md` (~500 tokens)
- `.claude/docs/PLAN.md` (~variable, typically 1,000-2,500 tokens)
- `.claude/docs/ARCHITECTURE.md` (~1,700 tokens)
- `.claude/docs/HANDOFF.md` (~500 tokens)
- `WORKFLOW.md` (~2,700 tokens)

**Change**: Read only PLAN.md + HANDOFF.md on first turn. These two files give Claude the current work context and session continuity. ARCHITECTURE.md, PROJECT_BRIEF.md, and WORKFLOW.md are reference docs that can be read on-demand when needed (the `/refresh` skill already loads them).

**New Quick Start**:

```markdown
## Quick Start

- **Current Work**: Read `.claude/docs/PLAN.md`
- **Last Session**: Read `.claude/docs/HANDOFF.md`
- **Reference** (read on demand): `PROJECT_BRIEF.md`, `.claude/docs/ARCHITECTURE.md`, `WORKFLOW.md`
```

- **Pros**: Saves ~4,900 tokens on first turn. PLAN.md and HANDOFF.md contain everything needed to resume work. Architecture and project brief rarely change and are only needed for planning sessions.
- **Cons**: Claude won't know project brief or architecture details until it reads them. Architect agent already reads these files explicitly — so no impact on planning. Builder/QA agents don't need them to function.

**Estimated savings: ~4,900 tokens (first turn)**

### 2. Move 6 MCP servers from global to per-project

Current state: 9 servers in `~/.claude.json` (global), loaded for ALL projects. This adds ~1,600 tokens of deferred tool names to the ToolSearch description.

**Proposed split**:

| Server      | Tools | Keep Global?     | Rationale                |
| ----------- | ----- | ---------------- | ------------------------ |
| github      | ~40   | **Yes**          | Used across all projects |
| context7    | 2     | **Yes**          | General docs lookup      |
| exa         | 3     | **Yes**          | General web search       |
| arxiv       | 4     | No → per-project | Research only            |
| crossref    | 3     | No → per-project | Research only            |
| openalex    | ~35   | No → per-project | Research only            |
| playwright  | ~30   | No → per-project | Browser testing only     |
| firecrawl   | 12    | No → per-project | Overlaps with playwright |
| browserbase | 8     | No → per-project | Overlaps with playwright |

**Implementation**: Remove 6 servers from `~/.claude.json`. For projects that need them, add to `.mcp.json` (per-project config).

- **Pros**: Saves ~900 tokens of deferred tool names from ToolSearch for projects that don't use research/browser servers. Also reduces MCP server startup time (6 fewer processes to spawn). The `.mcp.json.example` template already exists for per-project setup.
- **Cons**: Must run `claude mcp add --scope project` for each project that needs research/browser tools. Deployment scripts (`new-ade.ps1`, `update-ade.ps1`) should copy `.mcp.json.example`. Slight setup friction.

**Estimated savings: ~900 tokens (system prompt)**

### 3. Remove redundant CLAUDE.md sections

Three sections in CLAUDE.md duplicate information available elsewhere:

**a) "Verification flow" code block (lines 31-41, ~130 tokens)**
Duplicates the hooks table immediately above it. The hooks table already explains the verify→test→clear flow. The code block just restates it as a diagram.

**b) "What is committed vs ignored" table (lines 94-103, ~120 tokens)**
Duplicates ARCHITECTURE.md File Organization section. Claude only needs this when committing — and selective staging rules in "Git Workflow" already cover the policy.

**c) Hooks table detail (lines 22-29, ~250 tokens)**
The hooks table describes each hook in detail, but Claude doesn't need to know hook internals — it just needs to know hooks exist and run automatically. A one-liner reference suffices since hook behavior is enforced by the hooks themselves, not by Claude's knowledge of them.

**Change**: Replace all three with:

```markdown
## Hooks

Hooks in `.claude/settings.json` auto-enforce formatting, security scanning, test verification, and stop gates.
See `.claude/docs/ARCHITECTURE.md` for hook details. Configuration: `.claude/workflow.json`.
```

- **Pros**: Saves ~400 tokens from always-loaded CLAUDE.md. Reduces maintenance burden (single source of truth in ARCHITECTURE.md). Claude doesn't need to know hook implementation details — hooks enforce themselves via stdout/stderr.
- **Cons**: If Claude needs hook details for debugging, it must read ARCHITECTURE.md. But it already does this when working on hooks.

**Estimated savings: ~400 tokens (system prompt)**

### 4. Relocate Data Classification table to rules file

The P0-P4 Data Classification table (lines 55-65, ~130 tokens) is in always-loaded CLAUDE.md but is only relevant when writing code. Move it to a path-triggered rules file.

**Change**: Create `.claude/rules/data-classification.md`:

```markdown
---
paths:
  - "**/*.py"
  - "**/*.ts"
  - "**/*.js"
  - "**/*.go"
  - "**/*.rs"
---

# Data Classification

- P0 (Public): Normal handling
- P1 (Internal): Normal handling
- P2 (Competitive IP): Use `<TARGET>`, `<API_KEY>` placeholders. Generate `os.getenv()`.
- P3 (Resilience): Same as P2
- P4 (Unauthorized): **REFUSED**
```

Remove the table from CLAUDE.md, add a one-line reference: "See `.claude/rules/data-classification.md` for sensitivity handling."

- **Pros**: Saves ~100 tokens from always-loaded context. Only loads when code files are touched (which is when it matters). Consistent with existing `code-quality.md` pattern.
- **Cons**: If user asks about data classification in a non-code context, Claude won't know the rules until it reads the file. Marginal risk since P2/P3 only applies to code.

**Estimated savings: ~100 tokens (system prompt)**

### 5. Clean stale MEMORY.md entries

Current MEMORY.md (29 lines) has entries referencing features/decisions from prior iterations. Some are now stale:

- "templates/PLAN.md was intentionally deleted" — context that's no longer needed (was deleted months ago)
- "Local Specialist / air gap / /private were intentionally removed" — context that's no longer needed
- "`qa.md` agent deleted" — historical context, no longer relevant
- "Ralph spot-check step removed" — historical context

**Change**: Remove 4 stale entries, keep architecture decisions and patterns that are still active.

- **Pros**: Cleaner memory, ~50 tokens saved. Reduces noise in auto-loaded context.
- **Cons**: Negligible. These are historical notes with no current value.

**Estimated savings: ~50 tokens (system prompt)**

### 6. Ralph SKILL.md Optimization (~700-850 tokens when invoked)

ralph/SKILL.md is ~17K bytes (~5K tokens), loaded every time `/ralph` runs. It's the most-used skill and the heaviest.

**Specific reductions** (from ralph-perfection brainstorm):

- Display template blocks (ASCII-bordered sections): remove exact formatting — LLM can produce readable output without templates (~800 bytes saved)
- Error Recovery table: compress to inline references (~400 bytes saved)
- STEP 6 receipt validation sub-steps: condense from ~40 lines to ~15 lines checklist (~600 bytes saved)
- Inline JSON examples: reference qa_runner.py output format instead of repeating (~500 bytes saved)
- Sprint state JSON example: reference workflow-state.json schema instead of inlining (~300 bytes saved)

- **Pros**: Saves ~700-850 tokens per Ralph invocation. Less instruction noise for the LLM. Same behavior with terser instructions.
- **Cons**: Risk of under-specifying behavior. Verbose format was intentional for deterministic execution. Must verify compressed version produces identical behavior.

**Estimated savings: ~700-850 tokens (per /ralph invocation, not system prompt)**

### 7. Fix 3 Known Ralph Bugs (P0 — from ralph-perfection brainstorm)

Three bugs identified in the last Ralph sprint must be fixed before running more sprints:

**a. criteria_verified semantic bug**: `qa_runner.py` Step 11 always includes all criteria IDs in `criteria_verified` regardless of whether tests actually pass. Should only include IDs whose tests are found AND pass.

**b. qa_receipt pre-existing override**: STORY-002 worker returned `passed: true` but `qa_receipt.overall: "FAIL"` due to pre-existing issues in unchanged files. Ralph had to ad-hoc override. Need a codified policy: if ALL failing steps are in files NOT in `result.files_changed`, override to PASS with documented evidence.

**c. Stash consumed by worker**: Git stashes are shared across worktrees. Auto-stash before dispatch was popped by the worker in the worktree. Fix: require clean working tree before `/ralph` (simplest, safest).

- **Pros**: Eliminates known failure modes. Makes next sprint reliable. Targeted fixes.
- **Cons**: Must complete before any more Ralph sprints. The stash fix changes UX (user must commit/stash manually before `/ralph`).

**Estimated savings: 0 tokens, but required for Ralph reliability**

### 8. Ralph QA complexity tiers (speed optimization, not token optimization)

Currently every Ralph story runs the same 12-step QA pipeline regardless of complexity. A simple file deletion or config change gets the same QA as a complex algorithm implementation.

**Change**: Add a `complexity` field to prd.json stories: `"simple"`, `"medium"`, `"complex"`. Simple stories skip Steps 2 (type check), 4 (integration tests), 8 (coverage), 10-sub4 (call-graph wiring). Medium runs all except call-graph. Complex runs all.

prd.json v2 schema addition:

```json
{
  "complexity": "simple|medium|complex",
  ...
}
```

qa_runner.py change: `--complexity` flag maps to step skip list.

- **Pros**: Simple stories finish 30-50% faster. Reduces token consumption per story (fewer QA steps = fewer tool calls). Already supported via `--skip-steps` in qa_runner.py — just needs a mapping layer.
- **Cons**: Complexity assessment happens during planning — the Architect must classify correctly. Wrong classification (marking complex as simple) could miss issues. Adds a decision point to the planning process.

**Estimated savings: 0 tokens from context, but 15-40% faster per simple story**

### 9. Parallel Sub-Agent Execution in Ralph (biggest efficiency multiplier)

When a plan identifies independent stories (no shared files, no data flow dependencies), dispatch multiple ralph-workers simultaneously instead of sequentially.

```
CURRENT (sequential):
  STORY-001 → worker → merge → STORY-002 → worker → merge → STORY-003

PROPOSED (parallel where safe):
  STORY-001 → worker ─┐
  STORY-002 → worker ─┤→ collect results → merge in order → regression
  STORY-003 → worker ─┘
  STORY-004 (depends on 1-3) → sequential from here
```

**Implementation**: Add `dependsOn` and `parallelGroup` fields to prd.json. `/plan` Step 7 analyzes which stories are independent (no shared files in Changes Tables). Ralph STEP 5 dispatches all independent workers simultaneously using multiple `Agent` tool calls. STEP 6 collects results and merges sequentially (prevents conflicts).

**Claude Code support confirmed**: Multiple `Agent()` calls in one message triggers parallel execution. Worktree isolation means workers can't conflict on files.

- **Pros**: 2-3x faster for sprints with independent stories. No new infrastructure — uses existing worktree isolation. Deterministic merge order preserves safety.
- **Cons**: Dependency analysis must be accurate. Parallel workers consume more API tokens simultaneously. Requires careful handling if one parallel worker fails while others are running.

**Estimated savings: 0 tokens, but 2-3x sprint speed for independent stories**

### 10. Split \_lib.py monolith (maintainability, not token optimization)

`_lib.py` at 2,102 lines is the largest single file. It contains: violation patterns, scan functions, audit logging, hook stdin parsing, test quality analysis, verification log utilities, plan validation helpers.

**Change** (from ralph-perfection brainstorm):

```
_lib.py (facade, ~50 lines, re-exports all symbols)
├── _lib_core.py      (~200 lines: paths, state, stdin, audit log)
├── _lib_violations.py (~300 lines: PROD_VIOLATION_PATTERNS, scan_file_violations)
├── _lib_quality.py    (~300 lines: scan_test_quality, assertion analysis)
├── _lib_traceability.py (~300 lines: R-markers, plan parsing, coverage)
└── _lib_plan.py       (~200 lines: check_plan_prd_sync, parse_plan_changes)
```

- **Pros**: Workers read only the module they need. Cleaner separation of concerns. Easier testing.
- **Cons**: Zero token savings (hook code is never loaded into context). Significant refactoring effort. All 659+ tests must keep passing. Import paths change across all hooks. Risk of circular imports.

**Estimated savings: 0 tokens (hook code is never in context)**

### 11. Complete Anti-Gaming Phase 2 (from current PLAN.md)

The current PLAN.md (Anti-Gaming Enforcement v2) has Phase 2 remaining: diff-line coverage gate and call-graph wiring check. This closes the biggest anti-gaming gaps identified in the March 2026 audit.

**What's left**:

- `check_diff_line_coverage()` in `_lib.py` — parse coverage.json, compute coverage on changed lines only
- `check_call_graph_wiring()` in `_lib.py` — AST-based orphan function detection
- Enhanced `_step_coverage()` (Step 8) and `_step_plan_conformance()` (Step 10)
- Fix 90 weak assertion tests flagged by audit

- **Pros**: Closes biggest anti-gaming gaps. Catches unwired code and uncovered changes.
- **Cons**: Code-heavy. The 90 weak assertion fixes are tedious. Could be its own Ralph sprint.

**Estimated savings: 0 tokens, but significantly harder to game the QA pipeline**

### 12. Rotate exposed GitHub PAT (SECURITY — not optimization)

During this research, found a hardcoded GitHub PAT in `~/.claude.json` line 608:

```
"Authorization": "Bearer ghp_..."
```

**Change**: Rotate this token immediately. Replace with `gh auth` integration or environment variable reference.

- **Pros**: Eliminates credential exposure risk. The global config file could be accidentally shared or committed.
- **Cons**: None. This is mandatory.

**Estimated savings: 0 tokens, but critical security fix**

## Recommendation

### Full Roadmap (3 Phases)

All 12 ideas organized into three implementation phases. Phase 1 handles the immediate wins (context reduction + security). Phase 2 fixes Ralph bugs and completes anti-gaming. Phase 3 adds the big efficiency features (parallel execution, QA tiers).

### Phase 1: Context Bloat Reduction + Security (this session, Manual Mode)

Implement Ideas 1-5 + 12. All documentation/config changes, no code.

| Priority | Idea                                   | Savings       | Effort |
| -------- | -------------------------------------- | ------------- | ------ |
| **P0**   | 12. Rotate GitHub PAT                  | Security      | 5 min  |
| **P1**   | 1. Quick Start trim (5→2 files)        | ~4,900 tokens | 5 min  |
| **P2**   | 3. Remove redundant CLAUDE.md sections | ~400 tokens   | 10 min |
| **P3**   | 4. Data Classification → rules file    | ~100 tokens   | 5 min  |
| **P4**   | 2. MCP servers → per-project           | ~900 tokens   | 15 min |
| **P5**   | 5. Clean MEMORY.md                     | ~50 tokens    | 5 min  |

**Expected first-turn result**:

| Metric                 | Before      | After       | Change            |
| ---------------------- | ----------- | ----------- | ----------------- |
| System prompt tokens   | ~15,970     | ~14,520     | -1,450            |
| First-turn eager reads | ~6,950      | ~2,050      | -4,900            |
| **Total first turn**   | **~22,920** | **~16,570** | **-6,350 (-28%)** |

### Phase 2: Ralph Bug Fixes + Anti-Gaming Completion (next session, Ralph Mode)

Implement Ideas 7 + 11. Code changes with TDD and QA verification.

| Priority | Idea                             | Impact                    | Effort    |
| -------- | -------------------------------- | ------------------------- | --------- |
| **P0**   | 7. Fix 3 known Ralph bugs        | Required for reliability  | 2-3 hours |
| **P1**   | 11. Complete Anti-Gaming Phase 2 | Closes gaming gaps        | 4-6 hours |
| **P2**   | 6. Ralph SKILL.md optimization   | ~700-850 tokens per ralph | 1-2 hours |

**Prerequisite**: Phase 1 must be complete so context is optimized before running Ralph.

### Phase 3: Ralph Perfection (future session, Ralph Mode)

Implement Ideas 8-10. Major features requiring careful planning.

| Priority     | Idea                           | Impact                       | Effort     |
| ------------ | ------------------------------ | ---------------------------- | ---------- |
| **P1**       | 9. Parallel sub-agent dispatch | 2-3x sprint speed            | 6-10 hours |
| **P2**       | 8. Ralph QA complexity tiers   | 30-50% faster simple stories | 2-4 hours  |
| **Deferred** | 10. \_lib.py modularization    | Maintainability only         | 4-8 hours  |

**Note**: Parallel dispatch (Idea 9) is the single biggest productivity multiplier. It should be the primary feature of Phase 3. Use sub-agents (not Agent Teams — see ralph-perfection brainstorm for detailed comparison).

### Why This Order

1. **Context reduction first**: Cheaper sessions for everything that follows. Reduces cost of Phase 2 and 3.
2. **Bug fixes before features**: Running more sprints on known bugs compounds problems. Fix criteria_verified, pre-existing override, and stash issues before the next Ralph run.
3. **Anti-gaming before parallel**: Parallel execution amplifies both good and bad patterns. Ensure QA pipeline is hard to game before running 3 workers simultaneously.
4. **Parallel dispatch last**: It's the biggest feature and uses all prior improvements. It's also the proof-of-concept for Ralph as the infinite-context orchestration layer for all projects.

## Sources

- Prior brainstorm: `2026-03-01-context-window-optimization.md` (CLAUDE.md trim + MCP restructure analysis)
- Prior brainstorm: `2026-03-02-ralph-perfection-infinite-context.md` (bugs, parallel execution, SKILL.md optimization, anti-gaming, infinite context)
- Prior plan: `2026-03-02-research-cleanup-plan.md` (research remnant removal)
- Current plan: `.claude/docs/PLAN.md` (Anti-Gaming Enforcement v2 — Phase 2 remaining)
- Measured file sizes via Read tool (CLAUDE.md, WORKFLOW.md, ARCHITECTURE.md, PROJECT_BRIEF.md, HANDOFF.md)
- `~/.claude.json` global MCP server configuration (lines 595-697)
- `.claude/settings.json` hook configuration
- `.claude/workflow.json` QA runner configuration
- `.claude/rules/code-quality.md` path-triggered rule example
- Claude Code system prompt (this session's loaded context)

## Build Strategy

### Module Dependencies

```
Phase 1 (Context + Security — all independent):
  GitHub PAT rotation ← standalone
  CLAUDE.md changes (Quick Start, hooks, committed/ignored, data classification) ← standalone
  .claude/rules/data-classification.md (new) ← content from CLAUDE.md
  MEMORY.md cleanup ← standalone
  ~/.claude.json MCP restructure ← standalone

Phase 2 (Ralph Bugs + Anti-Gaming — partially dependent):
  criteria_verified fix (qa_runner.py) ── standalone
  pre-existing override policy (SKILL.md) ── standalone
  clean-tree requirement (SKILL.md) ── standalone
  Ralph SKILL.md optimization ── standalone
  Anti-Gaming Phase 2 (_lib.py + qa_runner.py) ── depends on bug fixes being complete
    ├── check_diff_line_coverage() ── standalone within phase
    └── check_call_graph_wiring() ── standalone within phase

Phase 3 (Ralph Perfection — sequential dependencies):
  prd.json schema extension (dependsOn, parallelGroup, complexity) ← must be first
    ↓
  /plan Step 7 dependency analysis ← depends on schema
    ↓
  STEP 5 parallel dispatch ← depends on schema + /plan
    ↓
  STEP 6 parallel result collection ← depends on STEP 5
    ↓
  QA complexity tier mapping ← depends on schema (complexity field)
    ↓
  _lib.py modularization ← depends on anti-gaming being complete
```

### Build Order

**Phase 1** (Manual Mode, single session, ~45 min):

1. Rotate GitHub PAT (standalone, security-critical, do immediately)
2. CLAUDE.md changes (Ideas 1, 3, 4 — all modify the same file, do together)
3. Data Classification rules file (create new file, depends on CLAUDE.md changes)
4. MEMORY.md cleanup (standalone, can parallel with 2-3)
5. MCP server restructure (standalone, can parallel with 2-4)

**Phase 2** (Ralph Mode, 1-2 sessions):

1. Fix criteria_verified bug in qa_runner.py
2. Add pre-existing override policy to SKILL.md STEP 6
3. Replace stash with clean-tree requirement in SKILL.md STEP 4
4. Compress Ralph SKILL.md (display templates, error recovery, JSON examples)
5. Complete anti-gaming Phase 2 (diff coverage + call-graph wiring)

**Phase 3** (Ralph Mode with parallel dispatch as goal):

1. Extend prd.json schema with `dependsOn`, `parallelGroup`, `complexity`
2. Update /plan Step 7 to analyze dependencies and set groups
3. Implement parallel dispatch in Ralph STEP 5
4. Implement parallel result collection in Ralph STEP 6
5. Add QA complexity tier mapping (--complexity flag)
6. \_lib.py modularization (if Phase 2 anti-gaming is stable)

### Testing Pyramid

**Phase 1**: 0/0/100 manual validation (docs/config only)

**Phase 2**: 70/20/10 — Unit tests for criteria_verified fix, pre-existing override logic, SKILL.md compression behavior. Integration tests for full QA pipeline with pre-existing failures. E2E: run Ralph on a test story to verify end-to-end.

**Phase 3**: 70/20/10 — Unit tests for dependency analysis, parallel dispatch simulation (mock Agent calls), complexity tier mapping. Integration tests for parallel dispatch with 2-3 mock workers. E2E: full Ralph sprint on a 3-story plan with 2 parallel stories.

### Risk Mitigation Mapping

**Phase 1 Risks**:

- Risk: Critical machine instruction accidentally removed from CLAUDE.md → Mitigation: Section-by-section diff review. Non-Negotiables, Precedence Rules, Production Standards, and Git Workflow are NOT touched.
- Risk: MCP servers break after global→per-project move → Mitigation: Move one server at a time. Test with `claude mcp list`. Keep backup of `~/.claude.json`.
- Risk: Quick Start trim causes Claude to miss context → Mitigation: `/refresh` skill loads all files on demand. Architect agent explicitly reads reference docs.

**Phase 2 Risks**:

- Risk: criteria_verified fix breaks existing tests → Mitigation: Fix is additive — only changes when IDs are NOT added, not when they are.
- Risk: Pre-existing override too lenient → Mitigation: Strict file-change check — only override for genuinely untouched files.
- Risk: SKILL.md compression loses deterministic behavior → Mitigation: A/B test on same story with old vs new SKILL.md.

**Phase 3 Risks**:

- Risk: Parallel workers touch same file → Mitigation: Dependency analysis in /plan prevents it; sequential merge catches it.
- Risk: Parallel dispatch overwhelms API → Mitigation: Max 3 parallel workers rate limit.
- Risk: \_lib.py modularization breaks imports → Mitigation: Keep `_lib.py` as re-export facade; full test suite before/after.

### Recommended Build Mode

**Phase 1: Manual Mode** — Documentation and config restructuring. No code changes. Ralph/TDD unnecessary. ~45 minutes.

**Phase 2: Ralph Mode** — 5 stories with testable acceptance criteria. Fix bugs first, then use fixed Ralph for anti-gaming completion. ~1-2 sessions.

**Phase 3: Ralph Mode** — 5-6 stories with clear dependencies. Parallel dispatch stories must be built sequentially (need it working before you can use it). The \_lib.py modularization can run parallel once anti-gaming is stable. ~2-3 sessions.
