# Architecture — Claude Workflow (ADE)

## Overview

A portable workflow framework for Claude Code that enforces structured development via 4 role-based agents, 11 slash-command skills, Python hook-based quality gates, and a V-Model orchestrator (Ralph v4) that drives autonomous Plan-Build-Verify loops with persistent worktree-isolated sub-agents. All workflow state is unified in `.workflow-state.json`.

## System Diagram

```
User
  │
  ├── /health, /refresh, /audit        → Skills (read-only diagnostics)
  │     └── /audit Section 9 → silent-failure-hunter (error handling resilience)
  ├── /plan                     → Architect Agent → PLAN.md + prd.json v2 (smart sizing)
  ├── /build-system {slug}              → Unified pipeline (Plan→Build→Audit→Handoff)
  ├── /ralph                            → Ralph Orchestrator v4 (autonomous)
  │     ├── STEP 1: Validate prd.json v2, init sprint state
  │     ├── STEP 1.5: Feature branch (ralph/[name])
  │     ├── STEP 2-3: Find next story, display details
  │     ├── STEP 5: Dispatch ralph-worker (worktree-isolated)
  │     │     └── ralph-worker: Build + QA fix loop (persists until pass)
  │     ├── STEP 6: Auto-merge or auto-retry (up to 4 attempts)
  │     │     ├── merge --abort on conflict (clean recovery)
  │     │     └── Circuit breaker: 3 consecutive skips → stop
  │     └── STEP 8: Sprint summary + PR creation (only user prompt)
  │           └── /code-review (optional post-PR review via plugin)
  └── /verify, /learn, /handoff         → Skills (verification, knowledge, session handoff)

Hooks (always active):
  PreToolUse:Bash  → pre_bash_guard.py        (block dangerous commands)
  PostToolUse:Bash → post_bash_capture.py      (capture errors, detect tests)
  PostToolUse:Edit → post_format.py            (format code, set needs_verify in .workflow-state.json)
  PostToolUse:Edit → post_write_prod_scan.py   (scan for production violations)
  Stop             → stop_verify_gate.py       (block stop if unverified — reads .workflow-state.json)
  SessionStart     → post_compact_restore.py   (session reminder from .workflow-state.json)

Quality utilities:
  qa_runner.py      → Automated 12-step QA pipeline CLI (supports --phase-type for adaptive QA)
  test_quality.py   → Test quality analyzer (assertion, mock, strategy checks)
  plan_validator.py → Plan quality validator (verbs, R-markers, test file coverage)
```

## Components

### Agents (`.claude/agents/`)

| Agent             | Purpose         | Key Behavior                                                               |
| ----------------- | --------------- | -------------------------------------------------------------------------- |
| `architect.md`    | Planning        | Produces PLAN.md, no code                                                  |
| `builder.md`      | Implementation  | Follows plan, TDD, selective staging                                       |
| `/verify` skill   | Verification    | 12-step pipeline via qa_runner.py incl. acceptance tests + prod-grade scan |
| `librarian.md`    | Documentation   | Updates knowledge, decisions, handoffs                                     |
| `ralph-worker.md` | Story execution | Worktree-isolated worker: Build + QA with fix loop, persists until pass    |

### Skills (`.claude/skills/`)

| Skill          | Purpose                                                          |
| -------------- | ---------------------------------------------------------------- |
| `ralph`        | V-Model orchestrator v4 — autonomous Plan-Build-Verify per story |
| `plan`         | Create PLAN.md + auto-generate prd.json v2                       |
| `audit`        | 9-section end-to-end workflow integrity audit (incl. error handling resilience via `silent-failure-hunter`) |
| `verify`       | Run phase verification commands                                  |
| `health`       | Environment readiness check                                      |
| `refresh`      | Re-sync context mid-session                                      |
| `build-system` | Unified plan-build-audit-handoff pipeline                        |
| `brainstorm`   | Structured idea generation with build strategy                   |
| `learn`        | Capture lessons learned                                          |
| `decision`     | Record architecture decisions (ADRs)                             |
| `handoff`      | Session handoff with state detection                             |
| `code-review`  | Post-PR review via plugin (5 parallel agents, confidence-scored) |

### Hooks (`.claude/hooks/`)

| Hook                      | Event                  | Purpose                                                                                                                       |
| ------------------------- | ---------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `pre_bash_guard.py`       | PreToolUse:Bash        | Block destructive commands (rm -rf, force push, etc.)                                                                         |
| `post_format.py`          | PostToolUse:Edit/Write | Auto-format, set `needs_verify` in `.workflow-state.json`                                                                     |
| `post_bash_capture.py`    | PostToolUse:Bash       | Log errors, clear `needs_verify` in `.workflow-state.json` on successful test run                                             |
| `post_write_prod_scan.py` | PostToolUse:Edit/Write | Two-tier enforcement: security violations BLOCK (exit 2), hygiene violations WARN (exit 0). Records in `.workflow-state.json` |
| `stop_verify_gate.py`     | Stop                   | Block stop if `needs_verify` or `prod_violations` set in `.workflow-state.json`. Force-stop clears all (escape after 3)       |
| `post_compact_restore.py` | SessionStart           | Remind about workflow rules, read current state from `.workflow-state.json`                                                   |
| `_lib.py`                 | Shared                 | Common utilities (audit_log, parse_hook_stdin, quality scanning, verification log)                                            |

### Quality Utilities (`.claude/hooks/`)

| Utility             | Type       | Purpose                                                                                                                                                                                         |
| ------------------- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `qa_runner.py`      | CLI script | Automated 12-step QA pipeline. All steps automated. Supports `--phase-type` for adaptive QA and `--plan` for conformance checks.                                                                |
| `test_quality.py`   | CLI script | Analyzes test files for assertion presence, self-mock patterns, mock-only assertions, R-markers.                                                                                                |
| `plan_validator.py` | CLI script | Validates PLAN.md quality: measurable verbs in Done When, R-PN-NN format IDs, Testing Strategy completeness, no placeholder verification commands, Test File column coverage in Changes tables. |

### Verification Logs (`.claude/docs/`)

| File                     | Format | Purpose                                                             |
| ------------------------ | ------ | ------------------------------------------------------------------- |
| `verification-log.jsonl` | JSONL  | Structured verification log. One JSON object per line. Append-only. |
| `verification-log.md`    | MD     | Human-readable verification summaries. Append-only. Gitignored.     |

## Data Flow

### Feature Development (Ralph)

1. User runs `/plan` → Architect produces `PLAN.md` with R-PN-NN requirements
2. `/plan` Step 7 auto-generates `prd.json` v2 from PLAN.md
3. User runs `/ralph` → validates prd.json, creates `ralph/[name]` feature branch
4. Per story: dispatches `ralph-worker` sub-agent (worktree-isolated, persists until pass)
5. On PASS: merges worktree branch via `git merge --no-ff` (abort on conflict → auto-retry)
6. On FAIL: auto-retry up to 4 attempts, then auto-skip. Circuit breaker at 3 consecutive skips
7. Verification results appended to `verification-log.jsonl` (structured) and `verification-log.md` (human-readable)
8. Progress appended to `.claude/docs/progress.md`, sprint state persisted to `.claude/.workflow-state.json` (ralph section)
9. At end: sprint summary + `gh pr create` (only user interaction point)
10. Post-PR: optional `/code-review` via plugin (user prompted, posts review comment on PR)

### Traceability Chain

```
PLAN.md R-PN-NN requirements
    ↓ (extracted by /plan Step 7)
prd.json v2 acceptanceCriteria[].id
    ↓ (enforced by Builder TDD)
Test files: # Tests R-PN-NN markers
    ↓ (validated by QA Step 11 / qa_runner.py)
verification-log.jsonl: structured JSONL entries per story
    ↓ (audited by /audit Section 4)
Full traceability: requirement → story → test → verification
```

### Hook Chain

```
Edit/Write code → post_format.py sets needs_verify in .workflow-state.json
    ↓           → post_write_prod_scan.py scans for violations
    ↓               ├── severity=block → exit 2 (BLOCK), records in .workflow-state.json
    ↓               └── severity=warn  → exit 0 (WARN),  records in .workflow-state.json
    ↓
Run tests → post_bash_capture.py detects test command
    ↓
Tests pass → needs_verify cleared + prod_violations cleared in .workflow-state.json
    ↓
Stop session → stop_verify_gate.py reads .workflow-state.json → allowed if all clear
    ↓  (blocked) → 3 consecutive attempts → force-stop (clears all flags)
```

## Key Design Decisions

> For detailed decision records, see `docs/decisions/`

| Decision                | Choice                                         | Rationale                                                            |
| ----------------------- | ---------------------------------------------- | -------------------------------------------------------------------- |
| Worktree isolation      | Sub-agents work in git worktrees               | Failed work never touches feature branch                             |
| Selective staging       | Explicit file paths, never `git add -A`        | Prevents accidental inclusion of state files                         |
| Hook fail-closed        | Hooks exit 2 on error (block)                  | Safety over convenience                                              |
| R-PN-NN convention      | `R-P{phase}-{seq:02d}` format                  | Machine-parseable, human-readable traceability                       |
| prd.json v2             | Structured objects, not flat strings           | Enables typed criteria, test linking, gate commands                  |
| Feature branches        | `ralph/[name]`, never commit to main           | Clean main, PR-based review                                          |
| Autonomous loop (v4)    | No user prompts between stories                | Fully autonomous sprint, only PR prompt at end                       |
| Worker persistence      | ralph-worker persists until criteria pass      | No escalation thresholds — fix loop until pass or maxTurns           |
| `memory: user`          | Agent memory at `~/.claude/agent-memory/`      | `project` writes to worktree (destroyed on cleanup); `user` persists |
| Unified state file      | `.claude/.workflow-state.json`                 | Single file for all workflow state; survives context compaction      |
| Merge conflict recovery | `git merge --abort` → treat as FAIL            | Without abort, feature branch stays in conflicted state              |
| No hooks in worker      | Worker inherits settings.json hooks            | Frontmatter hooks stack (not replace), causing double-firing         |
| Progress inline         | Orchestrator embeds progress context in prompt | progress.md is gitignored → not present in worktree                  |
| Two-tier enforcement    | Security=BLOCK (exit 2), hygiene=WARN (exit 0) | Security violations must be fixed immediately; cleanup can wait      |
| Unified state tracking  | Single `.workflow-state.json` replaces markers | Atomic reads/writes, no orphan marker files, single source of truth  |
| Plan-PRD sync           | SHA-256 hash + R-marker drift detection        | Prevents running against stale stories if plan changes               |
| Adaptive QA             | `--phase-type` skips irrelevant QA steps       | Foundation phases skip integration tests; e2e phases run all         |
| /build-system pipeline  | Unified plan-build meta-command                | Chains full lifecycle with user approval gates                       |
| Cherry-pick plugins     | Plugin integration: code-review post-PR, silent-failure-hunter in audit | Don't integrate plugins into inner QA loop; use selectively where they add value |

## File Organization

```
/
├── CLAUDE.md              # Machine instructions (auto-loaded)
├── WORKFLOW.md            # User guide and reference (on-demand)
├── PROJECT_BRIEF.md       # Project context
├── .mcp.json.example      # Per-project MCP server template
├── .gitignore             # Includes runtime state exclusions
└── .claude/
    ├── agents/            # 4 role-based agents (incl. ralph-worker)
    ├── rules/             # Path-specific rules (code-quality.md)
    ├── skills/            # 11 slash commands (incl. build-system)
    ├── hooks/             # 6 Python hooks + _lib.py + qa_runner.py + test_quality.py
    ├── scripts/           # Deployment (new-ade.ps1, update-ade.ps1)
    ├── templates/         # config.yaml, qa_receipt_fallback.json
    ├── errors/            # Runtime error logs (gitignored)
    ├── docs/
    │   ├── PLAN.md        # Current implementation plan
    │   ├── ARCHITECTURE.md # This file
    │   ├── HANDOFF.md     # Session state
    │   ├── knowledge/     # lessons.md, conventions.md
    │   ├── decisions/     # ADRs (000-template.md, README.md)
    │   └── brainstorms/   # Brainstorm outputs
    ├── prd.json           # Ralph stories (v2 schema)
    ├── settings.json      # Hook wiring (4 event types)
    └── workflow.json      # Test commands/patterns config
```

### What is committed vs ignored

| Committed (workflow definitions)  | Ignored (runtime state)               |
| --------------------------------- | ------------------------------------- |
| `SKILL.md`, agent `.md` files     | `.claude/.workflow-state.json`        |
| `prd.json` (schema template)      | `.claude/worktrees/`                  |
| Hook `.py` files, `_lib.py`       | `.claude/docs/verification-log.md`    |
| `qa_runner.py`, `test_quality.py` | `.claude/docs/verification-log.jsonl` |
| `PLAN.md`, `ARCHITECTURE.md`      | `.claude/docs/progress.md`            |
|                                   | `.claude/errors/`                     |

## Deployment

- **Environment**: Local CLI (Windows/macOS/Linux)
- **Distribution**: `new-ade.ps1` (new projects), `update-ade.ps1` (existing projects)
- **Repository**: github.com/bobbypolo/ClaudeWorkflow

## Constraints & Limitations

- Hooks require Python 3.10+ in PATH
- Ralph worktree isolation requires git 2.15+
- MCP servers support global (`~/.claude.json`) and per-project (`.mcp.json`) configuration
