---
name: handoff
description: Create end-of-session summary with session state for continuity.
disable-model-invocation: true
---

Generate `.claude/docs/HANDOFF.md` using the protocol below.

## Step 1: Gather Context

1. `git log --oneline -10` for recent commits
2. `git status` for uncommitted work
3. `.claude/docs/PLAN.md` for phase status (note if file exists or not)
4. Any blockers or open questions from the session

## Step 2: Detect Session Type

Check these conditions to determine what type of session just occurred:

**Build-in-progress session**: `.claude/docs/PLAN.md` exists AND/OR a Ralph sprint is in progress (`.claude/.workflow-state.json` has ralph section with incomplete stories).

**Standard session**: None of the above conditions match (e.g., debugging, one-off tasks, documentation updates).

Detection steps:

1. Check if `.claude/docs/PLAN.md` exists and has content.
2. Check if `.claude/.workflow-state.json` has ralph section with incomplete stories.
3. Classify the session type based on the conditions above.

## Step 3: Write Handoff Document

Write to `.claude/docs/HANDOFF.md` using the appropriate template based on session type:

---

### Template A: Build-In-Progress Session

Use when session type is "build-in-progress".

```markdown
# Session Handoff - [Date]

## Session Type: Build In Progress

## Completed This Session

- {commit summaries or "No commits"}

## In Progress

- {uncommitted work description or "None"}

## Current Phase Status

Phase {N}: {name} - {what's done and what remains}

## Ralph Sprint Status (if applicable)

- Stories passed: {count}
- Stories skipped: {count}
- Current story: {story ID}
- Feature branch: {branch name}

## Blockers / Open Questions

- {any issues needing resolution or "None"}

## Next Session Should

1. Run `/refresh` to reload context
2. {Continue with /ralph, or Act as Builder for next phase, etc.}
```

### Template B: Standard Session

Use when session type is "standard".

```markdown
# Session Handoff - [Date]

## Session Type: Standard

## Completed This Session

- {commit summaries or "No commits"}

## In Progress

- {uncommitted work description or "None"}

## Current Phase Status

Phase {N}: {name} - {what's done and what remains}
(or "No active plan" if PLAN.md does not exist)

## Blockers / Open Questions

- {any issues needing resolution or "None"}

## Next Session Should

1. {First priority action}
2. {Second priority action}
```
