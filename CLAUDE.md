# Claude Workflow (ADE) — Machine Instructions

## Quick Start

- **Current Work**: Read `.claude/docs/PLAN.md`
- **Last Session**: Read `.claude/docs/HANDOFF.md`
- **Reference** (read on demand): `PROJECT_BRIEF.md`, `.claude/docs/ARCHITECTURE.md`, `WORKFLOW.md`

## Role Commands

| Command            | Agent        | Behavior                                                                                                                                       |
| ------------------ | ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `Act as Architect` | architect.md | Planning mode. Reads codebase, produces PLAN.md with phased implementation. Never writes code.                                                 |
| `Act as Builder`   | builder.md   | Implementation mode. Follows PLAN.md exactly, one phase at a time. TDD mandatory. Escalates at thresholds (2 compile errors, 3 test failures). |
| `Act as QA`        | /verify      | Runs 12-step QA pipeline via verify/SKILL.md + qa_runner.py. Reports issues, does not fix them.                                                |
| `Act as Librarian` | librarian.md | Documentation mode. Updates knowledge base, decisions, handoffs.                                                                               |

## Hooks (Always Active)

6 Python hooks enforce quality gates automatically. See `.claude/docs/ARCHITECTURE.md` → Hooks section for full details.
Edit/write → auto-format + prod scan → run tests → verify gate on stop. Configuration in `.claude/workflow.json`.

See `.claude/rules/production-standards.md` for code standards, data classification, and precedence rules (auto-loaded when code files are touched).

## Non-Negotiables

1. **No secrets in code** — Use environment variables via `.env`
2. **No unverified changes** — Tests must pass before commit
3. **No scope creep** — If it's not in `.claude/docs/PLAN.md`, don't build it
4. **Conventional commits** — `feat:`, `fix:`, `docs:`, `chore:`
5. **Safety first** — Destructive commands require confirmation

## Git Workflow

- **Feature branches**: Ralph creates `ralph/[plan-name]` branch before any story work
- **All commits to feature branch**: Story commits NEVER go directly to main or master
- **Worktree isolation**: Each sub-agent works in its own git worktree — failed work never touches the feature branch. Successful work is merged via `git merge --no-ff`
- **Merge conflict recovery**: `git merge --abort` on conflict, treated as FAIL with auto-retry
- **Selective staging**: Sub-agents use explicit file paths in `git add` (NEVER `git add -A` or `git add .`). Only source code, test files, and documentation are staged. `.claude/` state files are never staged
- **PR creation**: At session end, Ralph offers `gh pr create` with auto-generated summary

See `.claude/docs/ARCHITECTURE.md` → File Organization for the commit/ignore table.

## When Stuck

If blocked for 3+ attempts on the same issue:

1. Run `/learn` to document what was tried
2. Ask for guidance with specific context
3. Do NOT compound errors with more attempts

## MCP Servers

**Global** (always on): `github`, `context7`. **Project** (disabled by default): `trello` — enable in `.claude/settings.local.json` by removing from `disabledMcpjsonServers`.

## Environment

Hooks are configured per-project in `.claude/settings.json`.
Required environment variables are documented in `PROJECT_BRIEF.md`.
