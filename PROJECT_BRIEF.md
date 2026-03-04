# Project Brief — Claude Workflow (ADE)

## What This Is

An Autonomous Development Environment (ADE) for Claude Code — a portable, opinionated workflow framework providing structured planning, V-Model orchestration, quality enforcement via hooks, and end-to-end traceability from requirements to verified code.

## Tech Stack

| Layer         | Technology                                   | Version |
| ------------- | -------------------------------------------- | ------- |
| Language      | Python (hooks), Markdown (skills/agents)     | 3.10+   |
| Runtime       | Claude Code CLI                              | Latest  |
| Orchestration | Ralph V-Model SDLC                           | v4.0    |
| QA Pipeline   | 12-step automated verification               | v4.0    |
| Testing       | pytest (hooks), manual verification (skills) | N/A     |
| Deployment    | PowerShell scripts (new-ade, update-ade)     | N/A     |

## External Dependencies

| Service         | Purpose                   | Documentation           |
| --------------- | ------------------------- | ----------------------- |
| GitHub (gh CLI) | PR creation, repo ops     | `gh --help`             |
| MCP Servers     | Search, context           | See `.mcp.json.example` |
| Ruff            | Python formatting/linting | `ruff --help`           |

## Key Constraints

- Must work on Windows (MINGW64/Git Bash) and macOS/Linux
- All workflow state under `.claude/` — no pollution of project root beyond CLAUDE.md, PROJECT_BRIEF.md, .gitignore
- Hooks must fail-closed (block on error, not silently pass)
- No secrets committed — `.env` in `.gitignore`

## Current Focus

> **Active Work**: Ralph v4 autonomous orchestrator — deployed with unified state, 12-step QA, /build-system, adaptive QA, smart sizing, two-session handoff
> **Target Milestone**: Production use of v4 features on real projects
> **Last Updated**: 2026-03-01

## Quick Commands

```bash
# Start a session
claude
/health

# Plan a feature
/plan

# Run Ralph orchestrator
/ralph

# Run audit
/audit

# Full pipeline (plan -> build -> audit -> handoff)
/build-system {slug}
```

## Environment Setup

```bash
# Required for GitHub PR creation
# (usually already configured via gh auth login)
```

## Team Contacts

- **Owner**: bobbypolo
- **Repository**: github.com/bobbypolo/ClaudeWorkflow
