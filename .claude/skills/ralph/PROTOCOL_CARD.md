# Ralph Protocol Card (condensed state machine)

## Loop: STEP 2→3→4→5A→5→6→6A→7→loop | all passed→STEP 8

| Step    | current_step         | Action                          | Key Decision                    |
| ------- | -------------------- | ------------------------------- | ------------------------------- |
| STEP 2  | STEP_2_FIND_NEXT     | Find first unpassed story       | All passed? → STEP 8            |
| STEP 3  | (set story context)  | Display story, set attempt=1    | —                               |
| STEP 4  | STEP_4_CHECKPOINT    | git rev-parse HEAD, clean check | Dirty tree? → STOP              |
| STEP 5A | (plan check)         | Verify criteria IDs in PLAN.md  | Gap? → STOP for /plan           |
| STEP 5  | STEP_5_DISPATCH      | Launch ralph-worker in worktree | Worker returns RESULT JSON      |
| STEP 6  | STEP_6_HANDLE_RESULT | Parse result, gate checks       | PASS → merge; FAIL → retry/skip |
| STEP 6A | (progress)           | Append to progress.md           | —                               |
| STEP 7  | STEP_7_CLEANUP       | Context refresh, state sync     | → STEP 2                        |

## PASS Path (STEP 6)

1. Validate qa_receipt: exists, 12 steps, overall=PASS, criteria match
2. Pre-existing override: if all failures in unchanged files → override to PASS
3. Diff review: 5 questions (Q1-Q5) all YES required
4. Merge: `git merge --no-ff [worktree_branch]`
5. Regression gate: run commands.regression from workflow.json
6. Log to verification-log.jsonl, update prd.json passed=true
7. Reset consecutive_skips=0, increment stories_passed → STEP 6A → STEP 7

## FAIL Path (STEP 6)

- attempt < max_attempts(4): increment attempt, store failure summary → STEP 5 (retry)
- attempt >= max_attempts: skip story, increment consecutive_skips → STEP 6A → STEP 7

## Circuit Breaker

consecutive_skips >= 3 → STOP sprint → STEP 8

## State Files

- **Read/Write**: `.claude/.workflow-state.json` (ralph section: consecutive_skips, stories_passed, stories_skipped, current_story_id, current_attempt, current_step, prior_failure_summary)
- **Read + update passed**: `.claude/prd.json`
- **Append**: `.claude/docs/progress.md`, `.claude/docs/verification-log.md`, `verification-log.jsonl`
