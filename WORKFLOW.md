# Claude Workflow (ADE) — User Guide

> For machine-enforced rules and standards, see `CLAUDE.md`

## Overview

A portable, opinionated workflow framework for Claude Code that provides structured planning, autonomous V-Model orchestration (Ralph v4), quality enforcement via Python hooks, and end-to-end traceability from requirements to verified production-grade code.

## Commands

| Action         | Command                                                                                 |
| -------------- | --------------------------------------------------------------------------------------- |
| Tests          | `python -m pytest .claude/hooks/tests/ -v`                                              |
| Lint           | `ruff check .`                                                                          |
| Format         | `ruff format .`                                                                         |
| QA Runner      | `python .claude/hooks/qa_runner.py --help`                                              |
| Test Quality   | `python .claude/hooks/test_quality.py --dir .claude/hooks/tests --prd .claude/prd.json` |
| Plan Validator | `python .claude/hooks/plan_validator.py --plan .claude/docs/PLAN.md`                    |

---

## How This Workflow Works

### The Big Picture

This workflow turns Claude Code into a structured development system. Instead of ad-hoc coding, every feature goes through a disciplined pipeline:

```
You describe what you want
    -> Architect creates a phased plan (PLAN.md)
    -> Plan is decomposed into testable stories (prd.json)
    -> Ralph autonomously builds each story with TDD
    -> Every story is verified by a 12-step QA pipeline
    -> Passing work is merged to a feature branch
    -> You review and create a PR
```

### The Three Modes of Working

**1. Ralph Mode (Autonomous)** — For feature implementation. You describe what you want, Ralph builds it story by story with no intervention needed until PR creation. This is the primary workflow.

**2. Manual Mode (Role-Based)** — For fine-grained control. You invoke agents directly (`Act as Builder`, `Act as QA`) and run verification manually. Useful for debugging or one-off tasks.

---

## Step-by-Step: Building a Feature with Ralph

### Step 1: Start Your Session

```
/health          # Verify environment (git, Python, gh CLI)
/refresh         # Load current project context
```

Check `.claude/docs/HANDOFF.md` if resuming from a prior session.

### Step 2: Plan the Feature

Tell Claude what you want to build:

```
Act as Architect. Plan [describe your feature]
```

Or use the slash command:

```
/plan
```

**What happens:**

1. The Architect agent reads your codebase, identifies affected files, and produces `.claude/docs/PLAN.md`
2. PLAN.md contains phased implementation with:
   - Discovery findings (existing code, patterns, constraints)
   - Per-phase changes, interface contracts, data flow, testing strategy
   - Requirements tagged with `R-PN-NN` IDs (e.g., `R-P1-01`, `R-P2-03`)
   - Blast radius assessment and risk mitigations
3. Step 7 of `/plan` auto-generates `.claude/prd.json` — structured stories with acceptance criteria, test types, and gate commands

**Review the plan before proceeding.** This is your chance to adjust scope, add requirements, or change the approach.

### Step 3: Run Ralph

```
/ralph
```

**What happens (fully autonomous):**

1. **Initialize**: Validates prd.json schema, shows story count and progress
2. **Feature branch**: Creates `ralph/[plan-name]` branch (or resumes existing one)
3. **For each story** (no user interaction):
   - Displays story details and acceptance criteria
   - Creates a safety checkpoint (requires clean working tree, stops if dirty)
   - Verifies PLAN.md covers all story criteria (stops if gaps found)
   - Dispatches a `ralph-worker` sub-agent in an isolated git worktree
   - Worker implements with TDD: writes failing tests first, then code to pass them
   - Worker runs full 12-step QA pipeline and fixes any failures
   - **On pass**: Merges worktree branch to feature branch, records progress
   - **On fail**: Auto-retries (up to 4 attempts per story with failure context)
   - **On exhaustion**: Auto-skips after 4 failed attempts
   - **Circuit breaker**: Stops if 3 consecutive stories are exhausted
4. **Session end** (only user interaction): Shows sprint summary, offers PR creation

### Step 4: Review and Ship

After Ralph completes:

```
/audit           # Validate end-to-end integrity (optional but recommended)
/handoff         # Save session state for next time
```

Ralph will prompt you to create a PR via `gh pr create` with an auto-generated summary.

---

## Step-by-Step: Manual Mode (Without Ralph)

For one-off tasks, debugging, or when you want direct control:

### Step 1: Plan

```
Act as Architect. Plan [your task]
```

### Step 2: Build (One Phase at a Time)

```
Act as Builder. Implement Phase 1
```

The Builder agent:

- Reads PLAN.md and finds the current phase
- Runs a plan sanity check (files exist, signatures match, tests specified)
- Implements with TDD: test first, then code
- Tags tests with `# Tests R-PN-NN` markers
- Runs verification commands
- Escalates if stuck (2 compile errors, 3 test failures)

### Step 3: Verify

```
/verify
```

The QA agent runs all 12 verification steps (see QA Pipeline section below).

### Step 4: Repeat

Continue with `Act as Builder. Implement Phase 2`, then `/verify`, etc.

### Step 5: Wrap Up

```
/handoff         # Save session state
```

---

## Slash Command Reference Matrix

### Core Workflow Commands

| Command         | Category    | When to Use                          | What It Does                                                                                                                                                                                   | Requires                             |
| --------------- | ----------- | ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| `/ralph`        | Build       | Feature implementation               | Autonomous Plan-Build-Verify loop through all stories. Auto-retries failures, auto-skips exhausted stories, circuit breaker at 3 consecutive skips. Only prompts for PR at end.                | prd.json v2 (generated by /plan)     |
| `/plan`         | Plan        | Before `/ralph` or manual building   | Architect creates phased PLAN.md with R-PN-NN requirements. Step 7 auto-generates prd.json v2 stories.                                                                                         | Description of desired feature       |
| `/verify`       | QA          | After manual build phases            | Dispatches QA agent to run 12-step verification pipeline against current phase's acceptance criteria.                                                                                          | Active phase in PLAN.md              |
| `/health`       | Diagnostics | Start of session                     | Checks git status, Python version, gh CLI auth, hook wiring, required files. Reports any issues.                                                                                               | Nothing                              |
| `/refresh`      | Context     | Mid-session when context feels stale | Re-reads PLAN.md, ARCHITECTURE.md, HANDOFF.md, prd.json to sync Claude's understanding.                                                                                                        | Nothing                              |
| `/handoff`      | Session     | End of session                       | Creates `.claude/docs/HANDOFF.md` with session state for continuity.                                                                                                                           | Nothing                              |
| `/build-system` | Pipeline    | End-to-end feature lifecycle         | Unified pipeline: Plan -> [Gate 1] -> Build (Ralph) -> Audit -> Handoff -> [Gate 2]. Supports session resume.                                                                                  | Existing plan or feature description |
| `/audit`        | QA          | After Ralph sprint or before PR      | 8-section end-to-end integrity audit: PLAN.md completeness, prd.json schema, test coverage, verification logs, architecture conformance, hook wiring, git hygiene, production-grade code scan. | Existing PLAN.md and implementation  |

### Knowledge Management Commands

| Command       | Category  | When to Use                         | What It Does                                                                                                                                                              | Requires                     |
| ------------- | --------- | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| `/learn`      | Knowledge | After solving an unexpected problem | Captures what happened, what was tried, and the solution as a durable lesson in `.claude/docs/knowledge/lessons.md`. Prevents repeating the same mistakes.                | Description of what happened |
| `/decision`   | Knowledge | When making an architectural choice | Records an Architecture Decision Record (ADR) in `.claude/docs/decisions/NNN-title.md` with context, options considered, decision, and consequences.                      | Decision to record           |
| `/brainstorm` | Ideation  | Exploring a problem before planning | Structured idea generation using project context. Produces brainstorm document in `.claude/docs/brainstorms/`. Good for exploring approaches before committing to a plan. | Problem description          |

### Command Priority Guide

**Every session**: `/health` -> (your work) -> `/handoff`

**Feature build (recommended)**: `/plan` -> `/ralph` -> `/audit` -> `/handoff`

**Full pipeline**: `/build-system {slug}` (chains plan -> build -> audit -> handoff)

**Manual build**: `/plan` -> `Act as Builder` -> `/verify` -> `/handoff`

**As needed**: `/learn` (after surprises), `/decision` (architectural choices), `/brainstorm` (exploration)

---

## Quality Enforcement Details

### Quality Utilities

Standalone scripts called by `/verify`, `/audit`, `/plan`, and Ralph:

| Utility             | What It Does                                                                                                                                                                                                  |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `qa_runner.py`      | Automated 12-step QA pipeline CLI. Runs lint, tests, security scan, mock audit + story coverage gate, R-marker validation, production scan. Supports `--phase-type` for adaptive QA. Outputs structured JSON. |
| `test_quality.py`   | Test quality analyzer CLI. Detects assertion-free, self-mock, mock-only tests. Validates R-PN-NN markers against prd.json. Structured JSON output.                                                            |
| `plan_validator.py` | Plan quality validator CLI. Checks measurable verbs in Done When criteria, R-PN-NN format IDs, Testing Strategy completeness, no placeholder verification commands, Test File column coverage.                |

### QA Pipeline (12 Steps)

Two execution paths exist for the QA pipeline:

- **Ralph workers** use the inline 12-step pipeline from `ralph-worker.md` (self-contained, no external reads)
- **Manual `/verify`** runs the full 12-step pipeline via `verify/SKILL.md` + `qa_runner.py`

In both cases, ALL 12 steps execute (adaptive QA via `--phase-type` may skip inapplicable steps):

| Step | Check                               | Failure Means                                                                                   |
| ---- | ----------------------------------- | ----------------------------------------------------------------------------------------------- |
| 1    | Lint (zero warnings)                | Code style violations                                                                           |
| 2    | Type check (mypy/tsc if configured) | Type errors                                                                                     |
| 3    | Unit tests (all pass)               | Logic errors                                                                                    |
| 4    | Integration tests (if applicable)   | Module interaction failures                                                                     |
| 5    | Regression check                    | Broke existing functionality                                                                    |
| 6    | Security scan                       | Hardcoded secrets, injection patterns                                                           |
| 7    | Clean diff                          | Debug prints, TODOs, commented-out code                                                         |
| 8    | Coverage report                     | Uncovered new code paths                                                                        |
| 9    | Mock audit + story coverage gate    | Self-mocking, no assertions, story file coverage < 80%, weak assertions, missing negative tests |
| 10   | Plan Conformance Check (automated)  | Blast radius, R-markers, or plan deviation issues                                               |
| 11   | Acceptance test validation          | R-PN-NN criteria not covered by passing tests                                                   |
| 12   | Production-grade code scan          | ANY violation = FAIL (see standards in CLAUDE.md)                                               |

---

## Ralph v4 — Detailed Behavior

### Autonomous Loop

Ralph v4 runs without user intervention between stories:

```
STEP 1:   Validate prd.json v2 schema, initialize sprint state file
STEP 1.5: Create/resume feature branch (ralph/[plan-name])
STEP 2:   Find next story (first with passed: false). Re-read sprint state from file.
STEP 3:   Display story details. Set attempt counter to 1.
STEP 4:   Checkpoint (clean-tree check, record HEAD hash)
STEP 5A:  Plan check (verify PLAN.md covers all story criteria)
STEP 5:   Dispatch ralph-worker in isolated worktree
STEP 6:   Handle result:
           - PASS -> merge (abort on conflict), update prd.json, record progress
           - FAIL -> auto-retry (up to 4 attempts) with failure context
           - EXHAUSTED -> auto-skip, increment circuit breaker counter
           - CIRCUIT BREAKER -> stop if 3 consecutive stories exhausted
STEP 6A:  Append to progress.md
STEP 7:   Update sprint state, loop to STEP 2
STEP 8:   Sprint summary + PR creation prompt (only user interaction)
```

### Ralph Worker (Sub-Agent)

Each story is built by a `ralph-worker` — a dedicated sub-agent that:

- Works in an **isolated git worktree** (failed work never touches your branch)
- Is **self-contained** — all TDD, QA, and production-grade rules are inlined in `ralph-worker.md` (does NOT read `builder.md`)
- **Ignores escalation thresholds** — persists until criteria pass or maxTurns (150)
- Runs TDD: failing test first (`# Tests R-PN-NN`), then implementation
- Runs full 12-step QA pipeline (with adaptive `--phase-type` support)
- **Fix loop**: If QA fails, fixes violations and re-verifies (does NOT just report)
- Uses `memory: user` — lessons persist at `~/.claude/agent-memory/ralph-worker/` across sessions
- Inherits all hooks from `settings.json` (no hooks in frontmatter — avoids double-firing)

### Sprint State Persistence

All workflow state is persisted to `.claude/.workflow-state.json` (survives context compaction). See `ralph/SKILL.md` for schema details and field descriptions.

### Traceability Chain

Every requirement is tracked end-to-end: PLAN.md requirement -> prd.json story -> test file R-marker -> verification log. See `.claude/docs/knowledge/conventions.md` for the full traceability diagram and naming conventions.

---

## Recovery

- **Rewind session**: `Esc Esc` or `/rewind`
- **Check errors**: Read `.claude/errors/last_error.json`
- **Git reset**: `git checkout .` to discard changes

## Repo Structure

For the complete directory tree and file descriptions, see `.claude/docs/ARCHITECTURE.md`. Key entry points: `CLAUDE.md` (machine rules), `WORKFLOW.md` (this file), `.claude/` (all workflow files).

## Deployment

### New Project

```powershell
.claude/scripts/new-ade.ps1 "C:\Path\To\NewProject"
```

### Update Existing Project

```powershell
.claude/scripts/update-ade.ps1 "C:\Path\To\ExistingProject"
```

Updates workflow infrastructure (agents, skills, hooks, rules, scripts, settings, templates) without touching project-specific docs (PLAN.md, HANDOFF.md, ARCHITECTURE.md, prd.json, lessons.md).
