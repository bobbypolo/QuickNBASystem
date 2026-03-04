---
name: health
description: Verify environment is ready for development.
---

Run environment health checks by executing actual commands and reporting results:

## Checks to Run

1. **Git**: Run `git status` — report if repo is clean or dirty
2. **Python**: Run `python --version` — report if Python is available
3. **Node**: Run `node --version` — report if Node is available (skip if not a JS project)
4. **Hooks config**: Read `.claude/settings.json` — verify it exists and has all 4 event types (SessionStart, PreToolUse, PostToolUse, Stop)
5. **Test command**: Check `CLAUDE.md` or `PROJECT_BRIEF.md` for a configured test command
6. **Formatters**: Check if `ruff` and/or `prettier` are available (run `ruff --version`, `npx prettier --version`)
7. **Verify marker**: Check if `.claude/.needs_verify` exists — report status
8. **Project files**: Check if `PLAN.md`, `ARCHITECTURE.md`, `HANDOFF.md` exist in `.claude/docs/`
9. **Workflow config**: Check if `.claude/workflow.json` exists — report configured commands (test, lint, format)

## Output Format

## Environment Health Check

| #   | Check           | Status       | Notes                       |
| --- | --------------- | ------------ | --------------------------- |
| 1   | Git repository  | PASS/FAIL    | [clean/dirty + branch]      |
| 2   | Python          | PASS/FAIL    | [version or not found]      |
| 3   | Node            | PASS/SKIP    | [version or not found]      |
| 4   | Hooks config    | PASS/FAIL    | [event types found]         |
| 5   | Test command    | PASS/WARN    | [command or not configured] |
| 6   | Formatters      | PASS/WARN    | [which are available]       |
| 7   | Verify marker   | CLEAR/ACTIVE | [file contents if active]   |
| 8   | Project files   | PASS/WARN    | [which exist]               |
| 9   | Workflow config | PASS/WARN    | [configured commands]       |

### Ready to Develop: YES / NO

[If NO, list what needs to be fixed]
