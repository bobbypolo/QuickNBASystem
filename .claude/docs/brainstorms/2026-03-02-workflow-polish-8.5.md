# Brainstorm: Workflow Polish — From 7.5 to 8.5+

**Date**: 2026-03-02
**Problem**: The workflow architecture and enforcement mechanisms are 9/10, but documentation drift, empty knowledge base, residual artifacts, and one traceability gap are dragging the overall score to 7.5. How do we close that gap systematically?

## Current Defect Inventory

Before brainstorming solutions, here is the exact inventory of every issue holding the score back, grouped by category:

### A. Documentation Drift (6 stale references)

| #   | File              | Line(s)     | Issue                                                                             | Correct State                                                                                             |
| --- | ----------------- | ----------- | --------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| A1  | `WORKFLOW.md`     | 95          | "auto-stashes dirty tree if needed"                                               | STEP 4 now requires clean tree and STOPs if dirty                                                         |
| A2  | `WORKFLOW.md`     | 250         | "STEP 4: Checkpoint (auto-stash dirty tree, record HEAD hash)"                    | Should be "Checkpoint (clean-tree check, record HEAD hash)"                                               |
| A3  | `WORKFLOW.md`     | 291         | "Recover stashed changes: `git stash pop` (if Ralph auto-stashed)"                | Remove entire line — Ralph no longer stashes                                                              |
| A4  | `ralph-worker.md` | 59          | Lists `.needs_verify`, `.prod_violations` as separate files to not stage          | These are fields in `.workflow-state.json`, not separate files                                            |
| A5  | `ralph-worker.md` | 63          | "Follow Production-Grade Code Standards from CLAUDE.md (all 15 rules)"            | Rules are in `.claude/rules/production-standards.md`, not CLAUDE.md. "15 rules" is not an accurate count. |
| A6  | `ralph/SKILL.md`  | 3, 7, 9, 13 | Says "v3" in 4 places (frontmatter description, title, body text, display string) | Everything else (ARCHITECTURE.md, WORKFLOW.md, PROJECT_BRIEF.md) says v4                                  |

### B. Empty Knowledge Base

| #   | File         | Issue                                                                                      |
| --- | ------------ | ------------------------------------------------------------------------------------------ |
| B1  | `lessons.md` | Placeholder only — zero entries despite 13 brainstorms documenting problems and solutions  |
| B2  | `decisions/` | Zero ADRs despite 20+ decisions documented in ARCHITECTURE.md's Key Design Decisions table |

### C. Residual Artifacts

| #   | Artifact                                                        | Issue                                                                                                                                                                             |
| --- | --------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| C1  | `.claude/ralph-sprint-state.json`                               | Legacy file from pre-unified-state era. Contains data from completed sprint. Superseded by `.workflow-state.json`. `_lib.py` still has `_LEGACY_RALPH_STATE_PATH` pointing to it. |
| C2  | `.claude/docs/brainstorms/2026-03-02-research-cleanup-plan.md`  | Untracked. The research cleanup work is complete and merged. This plan was superseded by the main PLAN.md.                                                                        |
| C3  | `.claude/docs/brainstorms/2026-03-02-research-cleanup-prd.json` | Untracked companion to C2. Also stale.                                                                                                                                            |
| C4  | `_lib.py` line 56                                               | `stash_created: False` in `DEFAULT_WORKFLOW_STATE` — residual from removed auto-stash feature                                                                                     |
| C5  | `.claude/.workflow-state.json` line 9                           | `stash_created: false` — same residual in the live state file                                                                                                                     |
| C6  | `.claude/templates/config.yaml` lines 39-43                     | Trading-system-specific fields (`max_position_size`, `max_daily_loss`, `paper_trading`) in a generic ADE template                                                                 |

### D. Traceability Gap

| #   | Issue                                                                                                                                                                                                                                                                       |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1  | Old PLAN.md R-P1-06 required `~/.claude.json` to have 3 MCP servers (github, context7, exa). Actual state has 2 (github, context7 — exa was moved to research project). STORY-001 was marked `passed: true` despite this. Decision was likely intentional but undocumented. |

### E. Git Hygiene

| #   | Issue                                                                                                                                                |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| E1  | `.claude/rules/production-standards.md` is untracked (`??` in git status) despite being actively referenced by CLAUDE.md, ralph-worker.md, and hooks |
| E2  | `CLAUDE.md` has unstaged modifications (` M` in git status)                                                                                          |
| E3  | `.mcp.json.example` has staged modifications (`M ` in git status)                                                                                    |
| E4  | `HANDOFF.md` is stale — describes a brainstorm session from before the plan was executed, all 3 stories are now done                                 |

---

## Ideas

### 1. Single "Documentation Sync" Pass

Fix all 6 stale references (A1-A6) in one focused editing session. No new code, no architecture changes — just updating text in 3 files to match the actual system state.

**Scope**: WORKFLOW.md (3 edits), ralph-worker.md (2 edits), ralph/SKILL.md (4 edits of "v3" → "v4")

- **Pros**: Lowest risk of all ideas. Every edit is a 1-line text fix. Can be verified with grep. Immediately eliminates the most visible inconsistency category.
- **Cons**: Does not address deeper issues (empty knowledge base, artifacts). Pure housekeeping — no system improvement.

### 2. ADR Backfill — Top 5 Decisions

Extract the 5 most impactful, hardest-to-reverse decisions from ARCHITECTURE.md's 20-entry table and create proper ADRs with full context/options/consequences. Candidates:

1. **001 — Worktree Isolation for Sub-Agents**: The foundational architectural choice that prevents failed work from touching the feature branch.
2. **002 — Unified State File (.workflow-state.json)**: Replaced file-based markers with single JSON. Drives all hooks and Ralph.
3. **003 — Hook Fail-Closed Design**: Exit 2 on error blocks the operation. Safety over convenience.
4. **004 — Research/Build ADE Separation**: Split one repo into two specialized workflows.
5. **005 — Ralph Worker Self-Containment**: Workers don't read builder.md. All rules inlined. Prevents instruction conflicts.

- **Pros**: Fills the empty `decisions/` directory with high-value content. Each ADR documents _why_ — the table only shows _what_. Future contributors (or future sessions) can understand trade-offs. The `/decision` skill exists and is unused.
- **Cons**: Historical context may be incomplete — decisions were made across multiple sessions. Options-considered sections may need reconstruction from brainstorm files. Time investment ~15-20 min per ADR.

### 3. Lessons Extraction from Brainstorms

Mine the 13 existing brainstorm files for lessons that should have been captured with `/learn`. The brainstorms contain extensive post-mortem analysis. Top candidates:

1. **Auto-stash consumed by worker** (from anti-gaming-enforcement brainstorm): Worker popped the orchestrator's stash, destroying safety checkpoint. Led to clean-tree requirement.
2. **Gaming vector: self-mock bypass** (from anti-gaming-enforcement brainstorm): Name-matching regex can be bypassed by naming tests differently from mocked functions.
3. **Context bloat from eager file reads** (from context-bloat-reduction brainstorm): 5-file Quick Start loaded ~6,950 tokens. Trimmed to 2 files + on-demand.
4. **Hook double-firing with frontmatter hooks** (from workflow-v4-autonomous-excellence brainstorm): Worker frontmatter hooks stack with settings.json hooks, causing double execution.
5. **Refactoring vs feature confusion** (from MEMORY.md): When instructions say to REMOVE bloat, don't treat the trimmed state as a defect to fix.

- **Pros**: Zero research needed — all material exists in brainstorm files. Formalizes institutional knowledge. Makes `lessons.md` useful for future sessions. Demonstrates that the `/learn` mechanism works.
- **Cons**: Extracting and formatting takes time. Lessons need to be concise to be useful (not copy-paste from brainstorms).

### 4. Artifact Cleanup Pass

Delete or fix every residual artifact (C1-C6, E1-E4):

- Delete `ralph-sprint-state.json` and remove `_LEGACY_RALPH_STATE_PATH` from `_lib.py`
- Delete or commit the untracked research-cleanup brainstorm files
- Remove `stash_created` from `DEFAULT_WORKFLOW_STATE` in `_lib.py` and from `.workflow-state.json`
- Generalize `config.yaml` template (replace trading fields with generic `# domain_specific:` placeholder)
- `git add` and commit `production-standards.md`
- Commit or discard pending CLAUDE.md and `.mcp.json.example` changes
- Regenerate `HANDOFF.md` via `/handoff`

- **Pros**: Addresses the "messy desk" perception that drags the score down. Removes every artifact that could confuse future sessions. Brings git status to clean. Removes dead code (`_LEGACY_RALPH_STATE_PATH`, `stash_created`).
- **Cons**: Deleting `ralph-sprint-state.json` means removing the `_LEGACY_RALPH_STATE_PATH` reference in `_lib.py` — need to verify no other code reads it. The `stash_created` removal touches DEFAULT_WORKFLOW_STATE which all state reads use (low risk but needs test verification). Tests must pass after changes.

### 5. Exa Decision Documentation

Close the D1 traceability gap by documenting the exa removal as a deliberate decision. Two options:

**5a**: Create ADR-006 explaining that exa was moved from global to research-project-only because it's unused by the Build ADE. Reference the research separation decision.

**5b**: Add a note to the completed prd.json story clarifying that R-P1-06 was superseded by the research separation decision (exa moved to F:\Claude-Research-Workflow\.mcp.json).

- **Pros**: Closes the one genuine traceability gap. If done as ADR, adds to the decisions/ directory. Prevents future audits from flagging this as a failure.
- **Cons**: Small scope — could be a single-line note rather than a full ADR. Risk of over-documenting a minor deviation.

### 6. Automated Documentation Drift Detection (/audit enhancement)

Add a new section to the `/audit` skill that checks for known drift patterns:

- Version string consistency (grep for "v3" and "v4" across all files, flag conflicts)
- Cross-reference resolution (for each "See X for details" reference, verify X exists)
- Stale file references (check that named files in agent instructions actually exist)
- HANDOFF.md freshness (warn if HANDOFF.md is older than the latest prd.json story completion)

- **Pros**: Prevents documentation drift from recurring. Makes the problem self-diagnosing. Aligns with the system's philosophy of automated enforcement.
- **Cons**: Most complex idea. Requires new code in `/audit` SKILL.md or a new utility. Regex-based version checking is brittle. Some drift is inherently hard to detect automatically.
- **Assessment**: High value but high effort. Better suited for a future plan than this cleanup.

### 7. Battle-Test Protocol

Create a structured test protocol document (`.claude/docs/knowledge/battle-test-protocol.md`) that defines specific scenarios to run on a real project:

- Full `/ralph` run through 3+ stories
- Deliberate failure injection (make a test fail, verify fix loop works)
- Context compaction recovery (long session, verify state survives)
- Merge conflict scenario (two stories touching same file)
- Circuit breaker trigger (3 consecutive failures)
- `/audit` after completed sprint

- **Pros**: Provides concrete next steps for moving from "well-designed on paper" to "battle-tested". Creates a reusable validation checklist. Could be run on the NBA trading system project.
- **Cons**: A protocol document is not the same as actually running it. Value only materializes when someone executes it. Could be scope creep relative to the "get to 8.5" goal.

### 8. Consolidated "Polish Sprint" — All Non-Code Fixes in One Pass

Combine Ideas 1, 3, 4, and 5b into a single Manual Mode session:

1. Fix all 6 stale references (Idea 1) — 10 min
2. Extract 5 lessons from brainstorms (Idea 3) — 15 min
3. Clean all artifacts (Idea 4) — 10 min
4. Add exa note to close traceability gap (Idea 5b) — 2 min
5. Commit everything clean — 5 min
6. Regenerate HANDOFF.md — 2 min

Total: ~45 min of focused work, entirely text edits and deletions. No new code. Low risk.

Defer Ideas 2 (ADR backfill), 6 (automated drift detection), and 7 (battle-test protocol) to a future session.

- **Pros**: Addresses every issue in the defect inventory except ADR backfill and automated detection. Achievable in one session. All changes are low-risk. Gets git status to clean. Brings the score to 8.5 by closing documentation + artifact + traceability gaps.
- **Cons**: Skips ADR backfill (decisions/ stays mostly empty). Skips automated drift detection (drift could recur). Prioritizes breadth over depth.

---

## Recommendation

**Idea 8 (Consolidated Polish Sprint)** is the clear winner. Here's why:

1. **It closes every defect in categories A, C, D, and E.** Documentation drift (A1-A6), residual artifacts (C1-C6), the traceability gap (D1), and git hygiene (E1-E4) are all resolved in one pass.

2. **It populates the knowledge base (B1) with real lessons.** Five extracted lessons from brainstorms is enough to make `lessons.md` genuinely useful, not just decorative.

3. **The ADR gap (B2) can wait.** An empty `decisions/` directory is less damaging than stale references in active agent instructions. The 20-entry decisions table in ARCHITECTURE.md already documents the decisions — ADRs add depth but not urgency. Recommend as the natural follow-on work.

4. **Risk is minimal.** Every change is either a text edit, a file deletion, or a field removal from a JSON default. No new code, no new functions, no architecture changes. Tests only need to pass (not be written).

5. **It's achievable in one session.** The scope is bounded and every edit is identified down to the line number.

**What gets us to 8.5:**

- Documentation coherence: 7/10 → 9/10 (all stale refs fixed, HANDOFF regenerated)
- Artifact cleanliness: 6/10 → 9/10 (all residual artifacts removed, git status clean)
- Knowledge base: 3/10 → 6/10 (5 lessons populated, ADRs still empty but noted as follow-on)
- Traceability: 9/10 → 10/10 (exa gap documented)

**What gets us to 9.0+ (future work):**

- ADR backfill for top 5 decisions (Idea 2)
- Automated drift detection in /audit (Idea 6)
- Battle-test on a real project (Idea 7)

## Sources

- All 13 brainstorm files in `.claude/docs/brainstorms/`
- `.claude/docs/ARCHITECTURE.md` — Key Design Decisions table (20 entries)
- `.claude/docs/PLAN.md` — Completed Context Bloat Reduction plan (3 stories, all passed)
- `.claude/docs/HANDOFF.md` — Stale session handoff from brainstorm session
- `.claude/agents/ralph-worker.md` — Lines 59, 63 (stale references)
- `.claude/skills/ralph/SKILL.md` — Lines 3, 7, 9, 13 (v3 label)
- `WORKFLOW.md` — Lines 95, 250, 291 (auto-stash references)
- `.claude/hooks/_lib.py` — Lines 46, 56 (`_LEGACY_RALPH_STATE_PATH`, `stash_created`)
- `.claude/.workflow-state.json` — Line 9 (`stash_created`)
- `.claude/ralph-sprint-state.json` — Legacy sprint state (superseded)
- `.claude/rules/production-standards.md` — Untracked but actively used
- `.claude/templates/config.yaml` — Trading-specific fields
- `.claude/docs/brainstorms/2026-03-02-research-cleanup-plan.md` — Untracked stale plan
- `.claude/docs/brainstorms/2026-03-02-research-cleanup-prd.json` — Untracked stale prd

---

## Build Strategy

### Module Dependencies

```
Documentation Fixes (A1-A6)  ──→  independent, no dependencies
Lesson Extraction (B1)       ──→  reads brainstorm files (exist, no dependency)
Artifact Cleanup (C1-C6)     ──→  C4 modifies _lib.py DEFAULT_WORKFLOW_STATE
                                   C1 removes _LEGACY_RALPH_STATE_PATH from _lib.py
                                   ──→ requires test run after (existing tests)
Git Hygiene (E1-E4)          ──→  E1 (commit production-standards.md) is independent
                                   E4 (regenerate HANDOFF.md) should be LAST
Traceability Fix (D1)        ──→  independent (prd.json note or ADR)
```

```
  ┌────────────────┐    ┌─────────────────┐    ┌────────────────┐
  │  Doc Fixes     │    │ Lesson Extract   │    │ Traceability   │
  │  (A1-A6)       │    │ (B1)             │    │ Fix (D1)       │
  └───────┬────────┘    └────────┬─────────┘    └───────┬────────┘
          │                      │                       │
          │ all independent      │                       │
          ▼                      ▼                       ▼
  ┌────────────────────────────────────────────────────────────────┐
  │  Artifact Cleanup (C1-C6) — modifies _lib.py, needs test run  │
  └──────────────────────────────┬─────────────────────────────────┘
                                 │
                                 ▼
  ┌────────────────────────────────────────────────────────────────┐
  │  Test Run — verify all existing tests pass after _lib.py edits │
  └──────────────────────────────┬─────────────────────────────────┘
                                 │
                                 ▼
  ┌────────────────────────────────────────────────────────────────┐
  │  Git Hygiene (E1-E3) — stage and commit all changes            │
  └──────────────────────────────┬─────────────────────────────────┘
                                 │
                                 ▼
  ┌────────────────────────────────────────────────────────────────┐
  │  Regenerate HANDOFF.md (E4) — must be last (reflects final     │
  │  state)                                                        │
  └────────────────────────────────────────────────────────────────┘
```

### Build Order

**Phase 1 — Parallel text edits** (no dependencies between them):

1. Fix WORKFLOW.md auto-stash references (A1, A2, A3)
2. Fix ralph-worker.md stale references (A4, A5)
3. Fix ralph/SKILL.md v3 → v4 (A6)
4. Extract 5 lessons to lessons.md (B1)
5. Add exa note to prd.json or create minimal ADR (D1)

**Phase 2 — Sequential code/config edits** (depend on each other): 6. Remove `stash_created` from `_lib.py` DEFAULT_WORKFLOW_STATE (C4) 7. Remove `_LEGACY_RALPH_STATE_PATH` and any migration code from `_lib.py` (C1) 8. Delete `.claude/ralph-sprint-state.json` (C1) 9. Remove `stash_created` from `.workflow-state.json` (C5) 10. Generalize `config.yaml` template (C6) 11. Delete untracked research-cleanup brainstorm files (C2, C3) 12. **Run full test suite** — verify all existing tests pass

**Phase 3 — Git cleanup and finalization**: 13. Stage and commit `production-standards.md` (E1) 14. Stage and commit all doc/config changes 15. Regenerate HANDOFF.md (E4)

### Testing Pyramid

- **Unit tests**: 100% — run full existing test suite after `_lib.py` edits (Phase 2 step 12). No new tests needed — all changes are to defaults and dead code removal.
- **Integration tests**: 0% — no new integration points. Existing hook chain is unchanged.
- **E2E tests**: 0% — no new workflows. Existing Ralph/verify/audit behavior unchanged.

**Ratio**: 100/0/0 — this is pure cleanup, the test suite is the only verification needed.

### Risk Mitigation Mapping

| Risk                                                 | Mitigation                                                                                                                                                                                                      |
| ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Removing `stash_created` breaks state reads          | `read_workflow_state()` uses deep-merge with defaults. Missing keys fall back to defaults. Removing from defaults means old state files with the key still work (extra keys are harmless). Run tests to verify. |
| Removing `_LEGACY_RALPH_STATE_PATH` breaks migration | Check all references in `_lib.py` first. If migration code actively reads the legacy file, verify it's a dead path (the unified state file exists and is populated).                                            |
| Lessons extraction from brainstorms is inaccurate    | Each lesson cites a specific brainstorm file. Reviewer can cross-reference. Keep lessons factual and grounded in what actually happened.                                                                        |
| Test failures after `_lib.py` edits                  | Changes are purely subtractive (removing dead defaults and dead paths). If tests reference `stash_created`, update those tests. Likely no tests depend on it since it's a removed feature.                      |
| Committing production-standards.md exposes rules     | The file contains no secrets — it's code standards, data classification policy, and precedence rules. Safe to commit.                                                                                           |

### Recommended Build Mode

**Manual Mode.** This is a cleanup/housekeeping sprint with no new features, no new code, and no acceptance criteria that require TDD. Every change is a text edit, file deletion, or field removal. Ralph is overkill — Manual Mode with a single `/verify` pass at the end is the right fit.

**Justification**:

- No new functions or interfaces to test
- Changes span 10+ files but each edit is trivial (1-3 lines)
- The only code change (`_lib.py`) is removing dead fields
- A single test run verifies the entire batch
- Risk profile is LOW across the board
