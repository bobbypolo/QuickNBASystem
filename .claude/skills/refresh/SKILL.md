---
name: refresh
description: Re-sync context with current project state mid-session.
---

Perform a context refresh by reading and summarizing:

1. `PROJECT_BRIEF.md` — project overview
2. `.claude/docs/PLAN.md` — find current phase (first incomplete)
3. `.claude/docs/HANDOFF.md` — prior session state (if exists)
4. `.claude/docs/knowledge/lessons.md` — last 3 lessons
5. `git status` — uncommitted work

6. `.claude/prd.json` — check `plan_hash` field for plan-prd sync status:
   - If `plan_hash` field exists: compute normalized hash via `compute_plan_hash()` from `_qa_lib.py` (R-marker lines only) and compare
   - Match → sync status is `CLEAN`
   - Mismatch → sync status is `DRIFT DETECTED — run /plan to resync`
   - If `plan_hash` field absent (legacy prd.json): sync status is `UNKNOWN (legacy prd.json, no hash)`

Output a structured summary:

## Context Refresh

**Project**: [name from PROJECT_BRIEF.md]
**Current Phase**: [N] - [name] ([status])
**Plan-PRD Sync**: [CLEAN | DRIFT DETECTED — run /plan to resync | UNKNOWN (legacy prd.json)]
**Prior Session**: [summary from HANDOFF.md or "New session"]
**Uncommitted Changes**: [list or "Working tree clean"]
**Recent Lessons**:

- [lesson 1]
- [lesson 2]
- [lesson 3]

**Recommended Next Action**: [what to do now based on plan status]
