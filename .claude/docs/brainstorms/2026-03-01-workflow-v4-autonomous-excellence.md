# Brainstorm: Workflow v4 — Autonomous Research-to-Delivery Pipeline

**Date**: 2026-03-01
**Problem**: Redesign the Claude Workflow (ADE) so Claude can autonomously conduct PhD-grade research on complex topics (meme coin trading systems, NBA simulation systems), brainstorm a detailed implementation path, build a bulletproof V-Model plan, implement everything in one conversation with minimal failure rate, audit the work against the plan, and complete handoff with changelogs — using parallel sub-agents or Ralph supervised loops as Claude decides during brainstorm.

## Current State Assessment

### What Works

- Research pipeline completed MemeSystem end-to-end: 116 sources, 42 deep extractions, 12 HIGH confidence claims, all 3 gates passed
- Ralph v3 completed a 4-story sprint (Quality Enforcement Upgrade): 127 tests, 8/8 audit PASS
- Hook system catches real violations (production scan, verify gate, bash guard)
- Traceability chain (R-PN-NN) from plan to test to verification log
- Plan skill with 6 automated pre-flight checks prevents bad plans

### What Breaks

- **Context compaction mid-sprint**: Ralph loses attempt counter, sprint state desyncs (30-50% failure on multi-story sprints)
- **Conflicting thresholds**: builder.md escalates at 2 compile errors; Ralph retries up to 4 times; ralph-worker ignores escalation entirely — no explicit precedence
- **QA Step 10 false positives**: blast radius check fails when builder legitimately touches utility files not listed in plan
- **Research sub-agent spawning undefined**: Phase 2 says "SPAWN AGENT" but doesn't specify the actual invocation mechanism
- **145+ decision points**: 1,868 lines of procedural instructions across agent files, skills, and CLAUDE.md
- **No integration between research and planning**: research output (final_deliverable.md) is not automatically consumed by /plan

### MCP Tools Available (confirmed)

| Tool                      | Purpose            | Key Functions                                                                                                          |
| ------------------------- | ------------------ | ---------------------------------------------------------------------------------------------------------------------- |
| **openalex**              | Academic papers    | search_works, get_work_references, get_work_citations, get_citation_network, find_seminal_papers, find_review_articles |
| **arxiv**                 | Preprints          | search_papers, read_paper                                                                                              |
| **crossref**              | DOI verification   | getWorkByDOI, searchByTitle, searchByAuthor                                                                            |
| **exa**                   | Web search         | web_search_exa, get_code_context_exa, company_research_exa                                                             |
| **firecrawl**             | Web extraction     | firecrawl_scrape, firecrawl_crawl, firecrawl_extract, firecrawl_search, firecrawl_map                                  |
| **context7**              | Library docs       | resolve-library-id, query-docs                                                                                         |
| **browserbase/stagehand** | Browser automation | stagehand_navigate, stagehand_extract, stagehand_act, stagehand_observe                                                |
| **playwright**            | Browser testing    | navigate, click, fill, screenshot, evaluate, expect_response                                                           |
| **github**                | Code/repo ops      | search_code, search_repositories, get_file_contents, create_pull_request                                               |

## Ideas

### 1. Unified Pipeline: Research → Brainstorm → Plan → Build → Audit → Handoff

**Description**: Create a single orchestrated pipeline that flows research output directly into planning, and planning output directly into building. Instead of separate `/research` then `/plan` then `/ralph` invocations, create a `/build-system {slug}` meta-command that chains them with automatic handoffs between phases.

**Pipeline flow:**

```
/build-system {slug}
  │
  ├─ PHASE A: Research (8-phase pipeline)
  │   └─ Output: research/{slug}/synthesis/final_deliverable.md
  │
  ├─ PHASE B: Brainstorm (auto-invoked)
  │   └─ Input: final_deliverable.md + risk_mitigations.md + claims.md
  │   └─ Output: .claude/docs/brainstorms/{date}-{slug}-path-forward.md
  │   └─ Includes: architecture options, tradeoff analysis, recommended approach
  │   └─ User approval gate here
  │
  ├─ PHASE C: Plan (architect, fed by research + brainstorm)
  │   └─ Input: brainstorm recommendation + final_deliverable.md
  │   └─ Output: PLAN.md + prd.json (auto-generated)
  │   └─ Research claims mapped to plan requirements (R-PN-NN ← claim.id)
  │   └─ User approval gate here
  │
  ├─ PHASE D: Build (Ralph loop or parallel agents)
  │   └─ Input: prd.json stories
  │   └─ Output: implemented, tested, verified code
  │   └─ Mode chosen during brainstorm (parallel vs sequential)
  │
  ├─ PHASE E: Audit (automatic)
  │   └─ Input: implemented code + PLAN.md + prd.json
  │   └─ Output: audit report (8 sections)
  │
  └─ PHASE F: Handoff (automatic)
      └─ Output: HANDOFF.md + changelogs + updated docs
```

- **Pros**: End-to-end automation. Research findings directly inform plan quality (no manual translation). Brainstorm step gives Claude agency to choose the best build strategy. User only approves at 2 gates (brainstorm and plan). Audit and handoff are automatic.
- **Cons**: Very long pipeline — could exceed a single session. Requires tight integration between research output format and plan input format. If research takes 2+ hours, plan + build may hit context limits. Recovery from mid-pipeline failure is complex.

### 2. Cognitive Load Reduction: Instruction Consolidation

**Description**: Reduce the 145+ decision points by consolidating overlapping instructions across files. Merge builder.md + qa.md into ralph-worker.md as the single source of truth for implementation. Eliminate the "read 4 files at startup" pattern. Establish explicit precedence rules for all conflicts.

**Specific consolidations:**

```
BEFORE (4 files, overlapping):
  builder.md (90 lines) — escalation thresholds, TDD rules, staging rules
  qa.md (81 lines) — 16 QA steps, fail-closed, evidence rules
  ralph-worker.md (114 lines) — "read builder.md and qa.md", overrides escalation
  CLAUDE.md (542 lines) — production standards (duplicated in worker)

AFTER (2 files, no overlap):
  ralph-worker.md (~180 lines) — EVERYTHING the worker needs inline:
    - TDD rules (from builder.md)
    - 16 QA steps (from qa.md, condensed)
    - Production standards (from CLAUDE.md, canonical copy)
    - Selective staging rules
    - Fix loop behavior
    - Structured result format

  builder.md (60 lines) — ONLY for manual mode (Act as Builder)
  qa.md (60 lines) — ONLY for manual mode (Act as QA)
```

**Precedence rules (add to CLAUDE.md):**

```
## Precedence Rules (when instructions conflict)
1. Production safety (QA Step 16) always wins over escalation thresholds
2. ralph-worker ignores builder escalation — persists until pass or maxTurns
3. Blast radius check: WARN (not FAIL) for utility files; FAIL only for core modules
4. Mock vs Real: if plan says "Real", ANY mock of the unit under test = FAIL
5. Sprint state file is canonical — re-read from disk at every STEP 2 loop
```

- **Pros**: Worker reads 1 file instead of 4. Zero ambiguity about which rule wins. Eliminates the "builder says stop, Ralph says continue" paradox. Reduces cognitive load from ~1,868 to ~1,200 lines. Manual mode (builder.md, qa.md) stays intact for non-Ralph work.
- **Cons**: ralph-worker.md grows larger (~180 lines). Three places to update if QA steps change (worker, manual qa.md, CLAUDE.md reference). Needs careful diff to ensure nothing is lost during consolidation.

### 3. State Persistence Revolution: Single State File + Mandatory Re-Read Hook

**Description**: Replace the 6 scattered marker files with a single `.claude/.workflow-state.json` file. Add a `post_compact_restore.py` enhancement that forces state re-read after context compaction. Make STEP 2 of Ralph emit a "STATE SYNC" marker that the hook validates.

**Single state file:**

```json
{
  "needs_verify": false,
  "prod_violations": [],
  "stop_block_count": 0,
  "ralph": {
    "active": true,
    "feature_branch": "ralph/meme-trading-system",
    "current_story_id": "STORY-003",
    "current_attempt": 2,
    "max_attempts": 4,
    "consecutive_skips": 0,
    "stories_passed": 2,
    "stories_skipped": 0,
    "stash_created": false,
    "prior_failure_summary": "Merge conflict on utils.py"
  },
  "research": {
    "active": false,
    "slug": "",
    "phase": ""
  },
  "last_updated": "2026-03-01T14:30:00Z"
}
```

**Mandatory re-read protocol:**

```
At EVERY STEP 2 iteration:
  1. Read .claude/.workflow-state.json from disk (not from memory)
  2. Display: "STATE SYNC: story=[id] attempt=[n] skips=[n]"
  3. If file missing: STOP with error (state corruption)
  4. If last_updated > 10 minutes ago: WARN (possible stale state)
```

**Hook enhancement (post_compact_restore.py):**

```python
# On SessionStart/Restore, emit reminder:
# "MANDATORY: Re-read .claude/.workflow-state.json before continuing any loop"
# Also emit current state summary so Claude has immediate context
```

- **Pros**: Single file = single read = single source of truth. Atomic writes prevent partial state corruption. Hook forces re-read after compaction. STATE SYNC marker creates visible audit trail. 10-minute staleness warning catches forgotten re-reads.
- **Cons**: All hooks must be updated to read/write new file format. Migration from current 6 files needs careful handling. Single file corruption affects everything (vs isolated marker files).

### 4. Smart Story Sizing: Research-Informed Plan Decomposition

**Description**: Use research findings to estimate story complexity BEFORE creating prd.json. Stories that research identifies as high-risk or high-complexity get smaller scope. Stories that research identifies as well-understood get larger scope. This prevents the "4 attempts exhausted" failure mode by right-sizing stories.

**How it works:**

```
Research Phase 5 (compile) produces claims.md with confidence levels:
  - HIGH confidence claims → larger stories (more work per story, lower risk)
  - LOW confidence claims → smaller stories (less work per story, higher risk)
  - CONTESTED claims → separate spike stories (research-first, then implement)

Plan Step 5 reads claims.md and sizes stories:
  - Each story's scope calibrated by confidence of underlying research
  - HIGH claims: up to 3 acceptance criteria per story
  - LOW claims: max 1 acceptance criterion per story
  - CONTESTED: spike story with "resolve ambiguity" as sole criterion
```

**Example for meme coin trading system:**

```
Research claim: "Jito bundles provide MEV protection" (HIGH, 3 foundational sources)
  → Story: "Implement Jito bundle submission with retry logic" (3 criteria, confident)

Research claim: "Bonding curve detection is reliable" (LOW, 1 source)
  → Story: "Implement bonding curve detection" (1 criterion, needs more validation)
  → Story: "Add fallback for failed curve detection" (1 criterion, defensive)

Research claim: "ML-based rug detection outperforms heuristics" (CONTESTED)
  → Spike story: "Benchmark ML vs heuristic rug detection" (resolve first)
```

- **Pros**: Stories sized by actual knowledge, not guesswork. Reduces exhaustion rate (smaller risky stories are easier to complete). Spike stories prevent building on contested ground. Research investment pays off in plan quality. Direct traceability: research claim → story → test.
- **Cons**: Requires research to be complete before planning (can't plan without claims.md). Adds complexity to /plan skill. Over-decomposition risk (too many tiny stories). Spike stories may not produce code (research output only).

### 5. Parallel Build Strategy: Agent Swarm for Independent Modules

**Description**: When the brainstorm identifies independent modules (no shared interfaces, no data flow dependencies), dispatch multiple ralph-workers in parallel instead of sequentially. Each worker gets its own worktree and builds a complete module. Merge all worktrees at the end.

**How Claude decides (during brainstorm):**

```
Analyze PLAN.md dependency graph:
  - Phase 1: Foundation (shared types, config) → SEQUENTIAL (everything depends on this)
  - Phase 2: Module A (token safety) → PARALLEL with Phase 3
  - Phase 3: Module B (signal detection) → PARALLEL with Phase 2
  - Phase 4: Integration (A + B) → SEQUENTIAL (depends on 2 + 3)
  - Phase 5: E2E tests → SEQUENTIAL (depends on 4)

Dispatch strategy:
  - Sequential phases: Ralph loop (one worker at a time)
  - Parallel phases: Agent swarm (multiple workers simultaneously)
```

**Implementation:**

```
For parallel phases:
  1. Create all worktrees upfront
  2. Dispatch ralph-worker agents simultaneously via Agent tool
  3. Each worker builds in isolation (no merge conflicts possible)
  4. Collect results
  5. Merge all worktrees to feature branch in dependency order
  6. Run integration tests on merged code
  7. If integration fails: identify conflicting module, retry that module only
```

- **Pros**: 2-3x faster for projects with independent modules. MemeSystem has at least 3 independent modules (token safety, signal detection, risk sizing). NBA sim has independent modules (game engine, player models, betting odds). Workers can't conflict (separate worktrees). Merge order enforced by dependency graph.
- **Cons**: Integration failures after parallel merge are harder to debug than sequential failures. Workers can't share discoveries (module A finds a pattern useful for module B). Requires accurate dependency graph in plan (bad graph = merge conflicts). More worktrees = more disk space. Agent tool doesn't support true parallel dispatch natively — would need multiple Agent calls in one message.

### 6. Research Pipeline Hardening: Explicit Agent Protocol + Firecrawl Integration

**Description**: Fix the three critical gaps in the research pipeline: (1) define exact Agent tool invocation for sub-agent spawning, (2) integrate Firecrawl for practitioner source extraction, (3) add deduplication algorithm, (4) add authority rubric for practitioner sources.

**Sub-agent spawning protocol (replace vague "SPAWN AGENT" in Phase 2):**

```markdown
## Agent Dispatch Protocol

For each discovery pass, use the Agent tool:

Agent(
subagent_type: "Explore",
description: "Academic discovery for {slug}",
prompt: "[full discovery instructions with output file path]"
)

- Agents write results to files (research/{slug}/discovery/\*.md)
- Main phase waits for each agent to return before proceeding
- If agent fails: retry once with simplified query set
- If retry fails: document gap in discovery file, continue
- Agents run sequentially by default (avoid API rate limits)
- For --thorough preset: run academic + practitioner in parallel
```

**Firecrawl integration (Phase 3 deep dive):**

```markdown
## Extraction Protocol

For each source requiring full-text extraction:

1. Academic (has DOI):
   - Try mcp**arxiv**read_paper first
   - Fallback: mcp**crossref**getWorkByDOI → get PDF URL → WebFetch

2. Practitioner (URL):
   - Primary: mcp**firecrawl**firecrawl_scrape (clean markdown output)
   - Fallback: WebFetch (raw HTML, lower quality)

3. Code repositories:
   - mcp**github**get_file_contents for specific files
   - mcp**exa**get_code_context_exa for code search
```

**Deduplication algorithm:**

```
For each pair of sources across all discovery files:
1. If DOI matches: keep peer-reviewed version, drop preprint
2. If no DOI: compare (title_similarity > 0.85 AND same_first_author AND year_within_1)
3. If match: keep FULLTEXT version over ABSTRACT_ONLY
4. Log: "Dedup: removed [title] (matched S[n] via [method])"
```

**Authority rubric for practitioner sources:**

```
Foundational (3+ signals required):
  - Official vendor/project documentation
  - Author maintains repo with 500+ stars on related project
  - Source cited by 3+ foundational academic papers
  - Published by recognized technical venue (ACM Queue, IEEE Software)
  - Multiple independent implementations reference this source

Corroborating (2+ signals):
  - Technical blog by domain practitioner with working code
  - Conference talk with published slides/recording
  - Peer-reviewed case study

Supplementary (default):
  - Everything else
```

- **Pros**: Every gap identified in the validation is closed. Firecrawl produces clean markdown (proven available in MCP config). Agent dispatch is explicit and testable. Dedup algorithm is deterministic. Authority rubric eliminates subjective judgment.
- **Cons**: Sequential agent dispatch is slower than hypothetical parallel. Firecrawl has API rate limits. Authority rubric may need calibration for different domains. Dedup by title similarity is imperfect (different titles, same research).

### 7. Brainstorm-Driven Build Strategy Selection

**Description**: After research and before planning, Claude conducts a structured brainstorm that explicitly decides HOW to build the system — including which modules are parallel-safe, which need sequential building, what the integration strategy is, and what the testing pyramid looks like. This brainstorm becomes a binding input to the plan.

**Brainstorm template (auto-generated from research):**

```markdown
# Build Strategy Brainstorm: {slug}

## Module Dependency Analysis

[From research: which components are independent?]
[Draw dependency graph]

## Build Order Recommendation

[Sequential phases, parallel phases, integration phases]
[Estimated stories per phase]

## Testing Pyramid

[Unit: which modules have clear interfaces → high unit test coverage]
[Integration: which modules interact → integration test focus]
[E2E: what user flows to validate → system test scenarios]

## Risk Mitigation from Research

[Map research risk_mitigations.md to specific build phases]
[HIGH confidence areas: build confidently, larger stories]
[LOW/CONTESTED areas: spike first, smaller stories, more tests]

## Recommended Build Mode

[Ralph sequential: for dependent phases]
[Parallel agents: for independent modules]
[Estimated total stories: N]
[Estimated phases: M]
```

- **Pros**: Claude explicitly reasons about HOW to build before building. Research risk findings directly influence build strategy. Dependency analysis prevents merge conflicts in parallel mode. Testing pyramid is research-informed. User sees the full strategy before committing.
- **Cons**: Adds another step before building starts. Brainstorm quality depends on research quality. Could delay build start by 30-60 minutes. Brainstorm might identify blockers that require more research.

### 8. Bulletproof Plan: Research-Backed Acceptance Criteria

**Description**: Every acceptance criterion in PLAN.md / prd.json is backed by a specific research claim. This creates a traceability chain from academic/practitioner evidence through the plan to the test to the verification. If a criterion has no research backing, it's flagged for manual justification.

**Traceability chain:**

```
Research claim (claims.md)
  → claim_id: "C-TSF-01"
  → confidence: HIGH
  → sources: [S3, S7, S12]
  → recommendation: "Use rugcheck.xyz API + on-chain honeypot detection"
      ↓
Plan requirement (PLAN.md)
  → R-P1-01: "Token safety filter rejects honeypot tokens"
  → backed_by: "C-TSF-01"
  → confidence: HIGH (from research)
      ↓
Story criterion (prd.json)
  → id: "R-P1-01"
  → criterion: "Token safety filter rejects honeypot tokens"
  → testType: "integration"
  → research_backing: "C-TSF-01 (HIGH)"
      ↓
Test (test_token_safety.py)
  → # Tests R-P1-01 (backed by C-TSF-01)
  → assert filter.check(honeypot_token) == REJECT
      ↓
Verification (verification-log.jsonl)
  → R-P1-01: PASS
  → research_confidence: HIGH
  → claim_id: C-TSF-01
```

- **Pros**: Every line of code can be traced to a research finding. Plan quality is objectively measurable (% criteria with research backing). LOW confidence criteria get extra test coverage. Audit can verify research → plan → test → verification chain. Eliminates "where did this requirement come from?" ambiguity.
- **Cons**: Requires research to be complete before planning (sequential dependency). Not all criteria have research backing (infrastructure, config, tooling). Adds metadata overhead to prd.json schema. Over-formal for simple features.

### 9. Adaptive QA: Reduce 16 Steps to Context-Appropriate Set

**Description**: Instead of always running all 16 QA steps, let the plan specify which steps are relevant per phase. Foundation phases (types, config) don't need E2E tests. Integration phases don't need blast radius checks (they touch everything). This reduces false positives and cognitive load without reducing quality.

**QA step relevance matrix:**

```
                          Foundation  Module  Integration  E2E
Step 1  Lint              ✓           ✓       ✓            ✓
Step 2  Type check        ✓           ✓       ✓            ✓
Step 3  Unit tests        ✓           ✓       ✓
Step 4  Integration tests             ✓       ✓            ✓
Step 5  Regression        ✓           ✓       ✓            ✓
Step 6  Security scan     ✓           ✓       ✓            ✓
Step 7  Clean diff        ✓           ✓       ✓            ✓
Step 8  Coverage                      ✓       ✓
Step 9  Mock audit                    ✓       ✓
Step 10 Blast radius      ✓           ✓
Step 11 System/E2E test                       ✓            ✓
Step 12 Logic review      ✓           ✓       ✓
Step 13 Arch conformance              ✓       ✓            ✓
Step 14 Builder deviation ✓           ✓       ✓            ✓
Step 15 Acceptance test   ✓           ✓       ✓            ✓
Step 16 Prod-grade scan   ✓           ✓       ✓            ✓
```

**Implementation**: Plan specifies `phase_type` per phase. QA reads phase_type and skips irrelevant steps (with justification logged). Steps 1-2, 5-7, 14-16 are ALWAYS required.

- **Pros**: Fewer false positives (no blast radius check on integration phase). Faster verification (skip 3-4 irrelevant steps). Explicit about what's checked and why. Still 100% coverage — steps are skipped only when logically inapplicable.
- **Cons**: Plan must correctly classify phase types. Wrong classification could skip important checks. Adds complexity to plan schema. "Always run everything" is simpler to reason about.

### 10. Session Architecture: Research in Session 1, Build in Session 2

**Description**: Accept the reality that PhD-grade research + full implementation exceeds a single session's effective context. Design the pipeline as TWO sessions with a clean handoff between them.

**Session 1: Research + Brainstorm + Plan**

```
/build-system {slug}
  → Phase A: Research (8 phases, 1-3 hours)
  → Phase B: Brainstorm (30 min)
  → Phase C: Plan (30 min, user approves)
  → Auto-handoff: saves PLAN.md, prd.json, research artifacts
  → Displays: "Plan ready. Start new session and run /ralph to build."
```

**Session 2: Build + Audit + Handoff**

```
/ralph (or /ralph with parallel strategy from brainstorm)
  → Phase D: Build all stories
  → Phase E: Auto-audit
  → Phase F: Auto-handoff with changelogs
```

**Why this works better than one session:**

- Research fills context with 100+ sources, claims, synthesis — leaving less room for build
- Fresh session for build = full 200K context for implementation
- Research artifacts persist on disk (not in context)
- Builder reads research synthesis (final_deliverable.md) as needed, not carrying full research state

- **Pros**: Each session has maximum context for its task. Natural approval gate between research and build. Recovery is clean (restart session 2 without redoing research). Matches how Ralph v3 already works (fresh context per story). Users can review research before committing to build.
- **Cons**: Two sessions means two invocations (user friction). Handoff between sessions must be bulletproof. Research insights might be lost in translation if handoff is incomplete. User might want to iterate (research → plan → revise research → re-plan) which crosses session boundaries.

### 11. External Orchestrator for Maximum Scale

**Description**: For truly large systems (20+ stories), move the Ralph loop to an external script (ralph-runner.ps1/sh) that spawns fresh `claude -p` processes per story. Each story gets a fresh 200K context window. The script handles circuit breaker, rate limits, and state persistence deterministically.

**This was already brainstormed in detail** (see 2026-02-27-ralph-v3-redesign.md). Key addition: integrate with the research pipeline so the external script can also orchestrate research phases.

```powershell
# ralph-runner.ps1 — extended for research-first workflow
param(
    [string]$Slug,
    [switch]$ResearchFirst,
    [switch]$BuildOnly
)

if ($ResearchFirst) {
    # Phase A: Research (single claude -p invocation, long-running)
    claude -p "Execute /research $Slug --thorough" --max-turns 200

    # Phase B: Brainstorm + Plan (single invocation)
    claude -p "Read research/$Slug/synthesis/final_deliverable.md. Brainstorm build strategy. Then run /plan" --max-turns 100

    # User review gate
    Read-Host "Review PLAN.md and prd.json. Press Enter to continue or Ctrl+C to abort"
}

# Phase D: Build (per-story loop with fresh context)
$stories = Get-Content .claude/prd.json | ConvertFrom-Json
foreach ($story in $stories.stories | Where-Object { -not $_.passed }) {
    $result = claude -p $storyPrompt --output-format json --json-schema $schema
    # ... circuit breaker, state update, progress logging
}
```

- **Pros**: Infinite context per story. Deterministic circuit breaker. Unattended overnight operation. Rate limit handling in script. Fresh process per story prevents compaction issues entirely. Can handle 50+ story sprints.
- **Cons**: Requires `--dangerously-skip-permissions`. Each story re-reads PLAN.md from scratch (no shared context). No interactive user oversight during build. More complex deployment (script + skill). Script is a second codebase to maintain.

### 12. Quality Gate Simplification: Merge QA Steps 10-14 into "Plan Conformance Check"

**Description**: Steps 10-14 (blast radius, system/E2E test, logic review, architecture conformance, builder deviation) are all variations of "does the implementation match the plan?" Merge them into a single automated "Plan Conformance Check" that runs deterministic comparisons.

**Merged check:**

```
Plan Conformance Check (replaces Steps 10-14):

1. Files changed vs plan:
   - git diff --name-only [checkpoint]..HEAD
   - Compare against Changes table files
   - WARN (not FAIL) for files not in plan
   - FAIL only if plan files were NOT changed (missing implementation)

2. Interface contracts:
   - For each Interface Contract in plan, grep codebase for function signature
   - FAIL if signature doesn't match plan

3. Architecture conformance:
   - If ARCHITECTURE.md has component diagram, verify imports match
   - WARN on drift, FAIL on contradiction

4. Builder deviation:
   - Read verification-log.md for Builder Notes
   - If deviations exist: require justification text (not just "it was necessary")
```

**New 12-step pipeline:**

```
Steps 1-9:   Same as current (automated)
Step 10:     Plan Conformance Check (automated, replaces 10-14)
Step 11:     Acceptance test validation (same as current Step 15)
Step 12:     Production-grade code scan (same as current Step 16)
```

- **Pros**: 16 → 12 steps. Eliminates blast radius false positives. Conformance check is more actionable (specific failures vs vague "flag"). Automated steps only — no REVIEW steps that require judgment. Faster verification cycle. Less cognitive load on worker.
- **Cons**: Loses granularity of separate E2E and logic review steps. System/E2E tests (current Step 11) might be dropped — need to preserve them somehow. "Logic review" is genuinely valuable and hard to automate. Reducing steps might reduce thoroughness.

## Evaluation Matrix

| Idea                           | Impact    | Effort | Risk   | Addresses Core Problem        |
| ------------------------------ | --------- | ------ | ------ | ----------------------------- |
| 1. Unified Pipeline            | Very High | High   | Medium | End-to-end automation         |
| 2. Cognitive Load Reduction    | High      | Medium | Low    | 145+ decision points          |
| 3. Single State File           | High      | Medium | Low    | Context compaction state loss |
| 4. Smart Story Sizing          | High      | Medium | Low    | 30-50% failure rate           |
| 5. Parallel Build Strategy     | Medium    | High   | Medium | Build speed                   |
| 6. Research Pipeline Hardening | High      | Medium | Low    | Research gaps                 |
| 7. Brainstorm-Driven Build     | High      | Low    | Low    | Build strategy clarity        |
| 8. Research-Backed Criteria    | Medium    | Medium | Low    | Traceability                  |
| 9. Adaptive QA                 | Medium    | Medium | Low    | QA false positives            |
| 10. Two-Session Architecture   | High      | Low    | Low    | Context ceiling               |
| 11. External Orchestrator      | Very High | High   | Medium | Infinite scale                |
| 12. QA Step Consolidation      | Medium    | Low    | Low    | Cognitive load                |

## Recommendation

**Implement a phased combination of Ideas 1 + 2 + 3 + 4 + 6 + 7 + 9 + 10 + 12.**

Defer Ideas 5 (parallel agents), 8 (research-backed criteria), and 11 (external orchestrator) to v4.1.

### Why This Combination

The core problem is: "Claude needs to go from research to working code in a predictable, auditable way." The combination solves this by:

1. **Two-Session Architecture (Idea 10)** accepts reality — PhD-grade research + full implementation is too much for one context. Session 1 does research + brainstorm + plan. Session 2 does build + audit + handoff. Clean separation, maximum context for each task.

2. **Unified Pipeline (Idea 1)** provides the end-to-end flow within each session. Session 1 runs Research → Brainstorm → Plan automatically. Session 2 runs Build → Audit → Handoff automatically.

3. **Brainstorm-Driven Build Strategy (Idea 7)** gives Claude agency to decide HOW to build based on research findings. This is the "every detail end to end" the user wants — Claude reasons about module dependencies, testing strategy, and risk before writing a single line of code.

4. **Smart Story Sizing (Idea 4)** uses research confidence to right-size stories. HIGH confidence = larger stories (lower risk). LOW confidence = smaller stories (higher risk, more defensive). This directly attacks the 30-50% failure rate.

5. **Cognitive Load Reduction (Idea 2)** consolidates ralph-worker.md into a single self-contained file with explicit precedence rules. Worker reads 1 file, not 4. No conflicting thresholds.

6. **Single State File (Idea 3)** replaces 6 marker files with one. Mandatory re-read at every loop iteration. Hook reminder after compaction. This directly attacks the state loss problem.

7. **Research Pipeline Hardening (Idea 6)** closes the three critical gaps: agent spawning protocol, Firecrawl integration, deduplication algorithm. Research quality directly determines plan quality.

8. **Adaptive QA (Idea 9)** + **QA Consolidation (Idea 12)** reduces 16 steps to ~12 context-appropriate steps. Fewer false positives, faster verification, lower cognitive load.

### What This Looks Like in Practice

**User wants to build a meme coin trading system:**

```
SESSION 1 (Research + Plan):

User: /build-system MemeSystem
  │
  ├─ [AUTO] Research: 8 phases, discovers 116 sources, 42 deep extractions
  │   └─ Firecrawl extracts practitioner blogs/docs
  │   └─ OpenAlex finds academic MEV/rug-pull papers
  │   └─ Claims: 12 HIGH, 1 LOW with gaps, 23 risk-mitigation pairs
  │
  ├─ [AUTO] Brainstorm: analyzes research, proposes:
  │   └─ 5 modules: token-safety, dex-execution, signal-detection, risk-sizing, infrastructure
  │   └─ Dependency: token-safety → dex-execution → signal-detection (sequential)
  │   └─ risk-sizing and infrastructure are independent (could be parallel)
  │   └─ Testing: heavy integration tests (DeFi interactions are stateful)
  │   └─ Risk: bonding curve detection is LOW confidence → spike story first
  │   └─ Recommendation: Ralph sequential for v1, parallel for v2
  │
  ├─ [USER APPROVAL] Reviews brainstorm, agrees with sequential approach
  │
  ├─ [AUTO] Plan: creates PLAN.md with 6 phases, 18 stories
  │   └─ Stories sized by research confidence
  │   └─ Each R-PN-NN linked to research claim
  │   └─ Pre-flight validation: 6/6 checks pass
  │   └─ prd.json auto-generated
  │
  ├─ [USER APPROVAL] Reviews plan, approves
  │
  └─ [AUTO] Handoff: saves state for Session 2
      └─ HANDOFF.md: "Research complete, plan approved, ready to build"

SESSION 2 (Build + Verify):

User: /ralph
  │
  ├─ [AUTO] Reads HANDOFF.md, loads plan, validates prd.json
  ├─ [AUTO] Story loop (18 stories):
  │   └─ Each worker: TDD → 12-step QA → fix loop → commit
  │   └─ State persisted to single .workflow-state.json
  │   └─ Mandatory re-read at every loop iteration
  │   └─ Smart retry: prior failure context passed to next attempt
  │
  ├─ [AUTO] Audit: 8 sections, verifies plan ↔ implementation match
  │
  └─ [AUTO] Handoff: changelogs, updated docs, PR creation
      └─ "18/18 stories complete, 0 skipped, audit 8/8 PASS"
```

### What We Defer (v4.1)

- **Parallel agents (Idea 5)**: Powerful but complex. Sequential Ralph is proven. Add parallelism after sequential is bulletproof.
- **Research-backed criteria (Idea 8)**: Good idea but adds prd.json schema complexity. Start with manual claim→criterion linking, formalize later.
- **External orchestrator (Idea 11)**: Maximum scale solution. But the in-session two-session approach handles 18-story sprints. External script is for 50+ stories.

### Implementation Order

| Phase | What                                         | Files                                           | Effort  |
| ----- | -------------------------------------------- | ----------------------------------------------- | ------- |
| 1     | Cognitive load reduction + precedence rules  | ralph-worker.md, CLAUDE.md                      | 2-3 hrs |
| 2     | Single state file + re-read protocol         | .workflow-state.json, all hooks, ralph SKILL.md | 3-4 hrs |
| 3     | Research pipeline hardening                  | Phase 2, 3 files, research.md                   | 2-3 hrs |
| 4     | QA consolidation (16 → 12 steps)             | qa.md, ralph-worker.md, qa_runner.py            | 3-4 hrs |
| 5     | Brainstorm-driven build strategy template    | brainstorm SKILL.md, plan SKILL.md              | 2-3 hrs |
| 6     | Unified pipeline (build-system meta-command) | New skill, integration glue                     | 3-4 hrs |
| 7     | Smart story sizing in /plan                  | plan SKILL.md Step 7                            | 1-2 hrs |
| 8     | Adaptive QA per phase type                   | plan schema, qa_runner.py                       | 2-3 hrs |
| 9     | Two-session handoff protocol                 | handoff SKILL.md, HANDOFF.md format             | 1-2 hrs |
| 10    | Update all docs                              | CLAUDE.md, ARCHITECTURE.md, PROJECT_BRIEF.md    | 2-3 hrs |

**Total estimated: ~22-30 hours of implementation across 10 phases.**

This is itself a Ralph-able plan. The workflow upgrades itself using the workflow.

## Sources

### Project Docs Read

- `PROJECT_BRIEF.md` — project context, tech stack
- `.claude/docs/ARCHITECTURE.md` — system diagram, components, data flow
- `.claude/docs/PLAN.md` — current plan (Quality Enforcement Upgrade, completed)
- `.claude/docs/HANDOFF.md` — last session state (4/4 stories, 127 tests, PR #1)
- `.claude/docs/knowledge/lessons.md` — empty (template only)
- `.claude/docs/brainstorms/2026-02-05-lean-workflow-remediation.md` — bloat audit, v5.2
- `.claude/docs/brainstorms/2026-02-27-ralph-v3-redesign.md` — external orchestrator analysis
- `.claude/docs/research-core.md` — confidence tree, gates, authority levels
- `.claude/skills/ralph/SKILL.md` — current Ralph v3 orchestrator (412 lines)
- `.claude/skills/plan/SKILL.md` — plan skill with 8 steps, 6 pre-flight checks
- `.claude/agents/ralph-worker.md` — worker agent (114 lines)
- `.claude/agents/builder.md` — builder agent (90 lines)
- `.claude/agents/qa.md` — QA agent (81 lines)
- `.claude/commands/research.md` — research dispatcher (124 lines)
- `.claude/commands/research-phases/phase-2-survey.md` — survey phase with agent spawning
- `research/MemeSystem/STATE.json` — completed research (116 sources, all gates passed)

### Validation Agents (run during this session)

- Research workflow validation agent: examined all 8 phase files, all support commands, MemeSystem output, identified 3 critical gaps + 4 medium issues
- Cognitive load assessment agent: analyzed all agent/skill files, identified 145+ decision points, conflicting thresholds, state persistence risks, estimated 30-50% failure rate on multi-story sprints

### User-Confirmed MCP Tools

- openalex, arxiv, crossref, exa, firecrawl, context7, browserbase/stagehand, playwright, github — all confirmed enabled and available
