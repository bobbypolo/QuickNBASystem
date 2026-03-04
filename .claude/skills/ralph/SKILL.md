---
name: ralph
description: Run autonomous V-Model orchestrator v4 — auto-retries failures (up to 4 attempts per story), auto-skips on exhaustion, circuit breaker stops after 3 consecutive exhausted stories. Only prompts user for PR creation at session end.
---

# Ralph - V-Model Autonomous Orchestrator v4

You are now operating in **Ralph Mode** — a V-Model orchestrator that executes stories from `.claude/prd.json` with Plan-Build-Verify inner loops, worktree-isolated sub-agents, feature branch workflow, and full QA verification gates. **v4 runs fully autonomously** — no user prompts between stories. The only user interaction is PR creation at session end.

## Core Rule

Delegation to `ralph-worker` via the **Agent tool** is mandatory. Ralph MUST NOT attempt to implement stories directly. Every story is dispatched to a ralph-worker sub-agent running in an isolated worktree. Ralph orchestrates; the worker builds and verifies.

## STEP 1: Initialize

Display: `"RALPH - V-Model Orchestrator v4 — Mode: Autonomous"`

Read `.claude/prd.json` and validate:

1. Check `version` field exists and equals `"2.0"`
   - If version missing or != "2.0": display deprecation warning:
     `"prd.json is v1 format (no version field). v1 is no longer supported. Run /plan to regenerate from PLAN.md."`
     Then **STOP**.
2. Validate schema on every story:
   - Required fields: `id`, `description`, `phase`, `acceptanceCriteria` (array), `gateCmds` (object), `passed` (boolean), `verificationRef`
   - Each `acceptanceCriteria` item: `id` (string matching `R-P\d+-\d{2}`), `criterion` (string), `testType` (string)
   - `gateCmds` must have at least one of: `unit`, `integration`, `lint`
3. If validation fails: display specific errors per story, then **STOP**
4. **Plan-PRD Sync Check**: Run `check_plan_prd_sync()` from `_lib.py` on `.claude/docs/PLAN.md` and `.claude/prd.json`:
   - If `added` is non-empty (markers in plan but not prd): display `"Drift detected — R-markers in PLAN.md but missing from prd.json: [added list]"`
   - If `removed` is non-empty (markers in prd but not plan): display `"Drift detected — R-markers in prd.json but missing from PLAN.md: [removed list]"`
   - If EITHER is non-empty: display `"PLAN.md and prd.json are out of sync. Run /plan to regenerate stories."` then **STOP**
   - If both empty (`in_sync: true`): display `"Plan-PRD sync: OK"` and continue
   - **4b. Plan Hash Check**: Compare `check_plan_prd_sync().plan_hash` (computed from current PLAN.md) against `prd.json["plan_hash"]` (stored hash). If they differ: display `"Plan-PRD hash mismatch: stored=[stored_hash[:12]]... computed=[computed_hash[:12]]... PLAN.md has changed since prd.json was generated. Run /plan to regenerate."` then **STOP**. If they match: display `"Plan hash: OK"` and continue.
5. Display story count and progress: `"Found [total] stories, [passed] completed, [remaining] remaining"`

Initialize sprint state in `.claude/.workflow-state.json` via `update_workflow_state(ralph={...})` from `_lib.py`. Ralph fields: `consecutive_skips`, `stories_passed`, `stories_skipped`, `feature_branch`, `current_story_id`, `current_attempt`, `max_attempts` (4), `prior_failure_summary`.

## STEP 1.5: Feature Branch Setup

Determine branch name:

- Default: `ralph/{plan-name}` derived from PLAN.md title (lowercase, hyphens for spaces)
  - Example: PLAN.md title "Ralph V-Model SDLC Upgrade" → `ralph/v-model-sdlc-upgrade`
- Or user-specified name

Check if branch exists:

- **Exists**: `git checkout [branch]` — resume previous sprint
  - Display: `"Resuming branch: [branch]"`
- **New**: `git checkout -b [branch]` — start fresh from current HEAD
  - Display: `"Created branch: [branch] (based on [current-branch])"`

Record branch name in sprint state: update `feature_branch` field in `.claude/.workflow-state.json`.

All story commits go to THIS branch. **NEVER commit directly to main or master.**

## STEP 2: Find Next Story

Update step tracking: `update_workflow_state(ralph={"current_step": "STEP_2_FIND_NEXT"})`

**Re-read sprint state** from `.claude/.workflow-state.json` (survives context compaction). Read the `ralph` section for sprint progress.

**Mandatory STATE SYNC display** (must appear every STEP 2 iteration):

```
STATE SYNC: story=[current_story_id] attempt=[current_attempt] skips=[consecutive_skips]
```

From the `stories` array in prd.json, find the **first story** where `"passed": false`.

- If ALL stories have `"passed": true`, display completion and proceed to **STEP 8**.
- If a story is found, continue to STEP 3.

## STEP 3: Display Story Details

Display story ID, phase, description, acceptance criteria (ID + criterion + testType), and gate commands (unit, integration, lint).

Update sprint state via `update_workflow_state(ralph={"current_story_id": "[story.id]", "current_attempt": 1, "max_attempts": 4, "prior_failure_summary": ""})` or equivalent.

## STEP 4: Create Safety Checkpoint

Update step tracking: `update_workflow_state(ralph={"current_step": "STEP_4_CHECKPOINT"})`

1. Verify working tree is clean: `git status --porcelain`
   - If dirty: display `"Working tree is dirty. Commit or stash changes before running /ralph."` then **STOP**.
2. Record full hash: `git rev-parse HEAD` (NOT `--short`)
3. Display: `"Checkpoint: [short-hash] ([branch-name]) — full: [full-hash]"`
4. Store full hash for rollback reference

## STEP 5A: Plan Check (Smart Plan Detection)

1. Read `.claude/docs/PLAN.md`
   - If PLAN.md doesn't exist: display `"No plan found. Run /plan first."` **STOP**
2. Extract all R-PN-NN IDs from Done When sections (regex: `R-P\d+-\d{2}`)
3. Extract this story's acceptanceCriteria IDs
4. Compare:
   - If ALL story criteria IDs found in PLAN.md → plan covers story, skip to STEP 5
   - If ANY story criteria ID missing from PLAN.md → plan gap detected:
     - Display: `"Plan gap: criteria [missing IDs] not covered by PLAN.md"`
     - Display: `"Run /plan to update PLAN.md, then resume /ralph"`
     - **STOP** Ralph session (user must update plan externally, then restart)
     - Ralph does NOT recursively invoke /plan — it pauses for user action
5. If legacy criteria (no R-PN-NN format): warn, require manual confirmation before proceeding

## STEP 5: Dispatch Worker

Update step tracking: `update_workflow_state(ralph={"current_step": "STEP_5_DISPATCH"})`

1. Read `.claude/docs/progress.md` if it exists — extract relevant progress context for this story.

2. Read sprint state from `.claude/.workflow-state.json` for current attempt and prior failure context.

3. Launch `ralph-worker` agent via Agent tool with `subagent_type: "ralph-worker"`:

   **Dispatch prompt** (embed all context inline — worker cannot read gitignored files):

   ```
   ## Story Assignment

   Story ID: [story.id]
   Phase: [story.phase]
   Description: [story.description]

   ### Acceptance Criteria
   [List each ac.id: ac.criterion (ac.testType)]

   ### Gate Commands
   unit: [gateCmds.unit]
   integration: [gateCmds.integration]
   lint: [gateCmds.lint]

   ### Checkpoint
   Base commit: [full_hash]

   ### Attempt
   Attempt [current_attempt] of [max_attempts]

   ### Prior Failure Context
   [If current_attempt > 1, include prior_failure_summary from sprint state]
   [If current_attempt == 1: "First attempt — no prior failures"]

   ### Sprint Progress
   [Embed relevant lines from progress.md if it exists, otherwise "First story in sprint"]

   ## Instructions
   Follow your ralph-worker.md agent instructions exactly.
   Follow your ralph-worker.md agent instructions exactly (self-contained build + verify rules).
   Persist until all acceptance criteria pass. Do NOT stop at builder escalation thresholds.
   Return your result in RALPH_WORKER_RESULT format.
   ```

4. Receive result from worker agent.
   - Worker worked in isolated worktree — only result summary enters Ralph's context
   - If worker made changes, worktree path + branch name are returned

## STEP 6: Handle Result

Update step tracking: `update_workflow_state(ralph={"current_step": "STEP_6_HANDLE_RESULT"})`

Parse worker result. Look for `RALPH_WORKER_RESULT:` in the agent output and extract the JSON.

### If PASSED:

1. **Validate verification receipt (`qa_receipt`)**

   Before trusting the worker's PASS claim, validate the `qa_receipt` field from the worker result:

   a. **Receipt exists**: Check that `result.qa_receipt` is present and is a valid JSON object.
   - If missing or not an object: treat as **FAIL** with summary: `"No verification receipt: worker claimed PASS but did not provide qa_receipt. Re-dispatching with receipt requirement."`
   - Proceed to FAIL handling below.

   b. **All 12 steps present**: Check that `qa_receipt.steps` is an array containing exactly 12 entries, one for each QA step: `lint`, `type_check`, `unit_tests`, `integration_tests`, `regression`, `security_scan`, `clean_diff`, `coverage`, `mock_audit`, `plan_conformance`, `acceptance_tests`, `production_scan`.
   - If any step is missing: treat as **FAIL** with summary: `"Incomplete verification receipt: missing steps [list missing step names]. Worker must run all 12 QA steps."`

   c. **Overall is PASS**: Check that `qa_receipt.overall_result` equals `"PASS"`.
   - If overall_result is not "PASS": treat as **FAIL** with summary: `"Verification receipt shows overall_result=FAIL despite worker claiming PASS. Rejecting result."`

   d. **Criteria verified match story**: Check that `qa_receipt.criteria_verified` contains ALL of the story's `acceptanceCriteria[].id` values.
   - Extract story criteria IDs: `[ac.id for ac in story.acceptanceCriteria]`
   - Check each ID is present in `qa_receipt.criteria_verified`
   - If any criteria ID is missing: treat as **FAIL** with summary: `"Verification receipt missing criteria: [missing IDs]. Worker did not verify all acceptance criteria."`

   If ALL receipt checks (a-d) pass, continue to sub-step 1f.

   e. **Pre-existing override** (file-scoped FAIL exemption)

   If `qa_receipt.overall_result == "FAIL"`, check whether all failures are pre-existing (not caused by this worker's changes):
   1. For each failing step in `qa_receipt.steps`, check if its evidence contains **specific file paths** (eligible steps: `lint`, `security_scan`, `production_scan`, `clean_diff`).
   2. Steps WITHOUT per-file evidence (`unit_tests`, `integration_tests`, `regression`, `mock_audit`, `acceptance_tests`) are NOT eligible — these are the worker's responsibility.
   3. For each eligible failing step, extract file paths from evidence and compare against `result.files_changed`.
   4. If ALL failing steps are file-based AND every failing file is NOT in `result.files_changed`:
      - Override `qa_receipt.overall_result` to `"PASS"` with log entry: `"Pre-existing override: all failures in files not changed by worker: [file list]"`
      - Continue to sub-step 1f.
   5. If ANY non-eligible step fails, OR any failing file IS in `result.files_changed`:
      - Proceed to normal FAIL handling.

   f. **Diff Review** (agent-based gate)

   Before merging, read the worker's diff and the plan, then answer 5 structured yes/no questions. All 5 must be YES to proceed to merge.

   **Get the diff:**

   ```bash
   git diff [checkpoint]..[result.worktree_branch]
   ```

   - If the diff is **empty**: treat as **FAIL** with summary: `"Diff review failed: empty diff — no changes found between checkpoint and worktree branch."`
   - Proceed to FAIL handling below.

   **Read the plan:**

   Read `.claude/docs/PLAN.md` and extract the current phase's Changes Table, Interface Contracts, and requirements.
   - If PLAN.md is **unreadable** (missing, corrupt, or unparseable): display `"WARN: PLAN.md unreadable — skipping plan-dependent questions (Q1, Q2, Q5). Proceeding with Q3 and Q4 only."` Continue with the review (do NOT treat as FAIL).

   **Answer 5 structured questions** (yes/no):
   - **Q1: Does every changed file appear in the plan's Changes Table?** Review each file in the diff against the Changes Table for the current phase. Files not listed in the plan are scope creep.
   - **Q2: Do the changes match the plan's described modifications (not extra, not missing)?** Compare what the diff actually does against what the plan says should be modified. Extra functionality or missing requirements both count as NO.
   - **Q3: Are test files present for every non-trivial source file change?** For each changed source file (not config, not markdown), verify a corresponding test file exists in the diff or already exists in the repo. Trivial changes (imports only, formatting) are exempt.
   - **Q4: Does the diff contain any debug artifacts (print statements, commented-out code, TODO)?** Scan the diff's added lines for `print(`, `console.log`, `debugger`, `TODO`, `FIXME`, `HACK`, `XXX`, or large blocks of commented-out code.
   - **Q5: Do function signatures in the diff match the Interface Contracts in the plan?** For each new or modified function in the diff, verify its name, parameters, and return type match the plan's Interface Contracts section. If the plan has no Interface Contracts section, answer YES.

   **Evaluation:**
   - If ALL 5 answers are **YES**: continue to step 2 (merge).
   - If ANY answer is **NO**: treat as **FAIL** with summary: `"Diff review failed: Q[N] = NO — [specific reason describing what was wrong]."` Include all failing question numbers. Proceed to FAIL handling below.
   - If PLAN.md was unreadable: Q1, Q2, and Q5 are automatically answered YES (skipped). Only Q3 and Q4 are evaluated.

2. Get branch name from worker result: `result.worktree_branch`
3. Merge worktree branch into Ralph's feature branch:
   ```bash
   git merge --no-ff [result.worktree_branch] -m "feat([story.id]): [story.description]"
   ```
4. **If merge conflict**:

   ```bash
   git merge --abort
   ```

   Treat as **FAIL** with summary: `"Merge conflict when integrating worktree branch. Feature branch restored to clean state."`
   Proceed to FAIL handling below.

5. **Cumulative regression gate**

   After a successful merge, run the full regression suite to ensure the new story did not break any previously passing work:

   ```bash
   # Read regression command from workflow.json
   # commands.regression (e.g., "python -m pytest .claude/hooks/tests/ -v --tb=short")
   ```

   - Read `.claude/workflow.json` and extract `commands.regression`
   - If the `regression` key exists and is not empty: run the command, check exit 0
     - **If regression passes (exit 0)**: continue to step 6
     - **If regression fails (exit != 0)**: this is a serious issue -- the merge introduced regressions
       - Treat as **FAIL** with summary: `"Cumulative regression failed after merge: [command] exited with [exit_code]. Merged code breaks previously passing tests."`
       - Proceed to FAIL handling below
   - If the `regression` key is missing or empty: display `"WARN: No regression command configured in workflow.json. Skipping cumulative regression."` and continue to step 6

6. **Append to verification-log.jsonl:** One JSON line per story with `story_id`, `timestamp`, `attempt`, `overall_result`, `plan_hash` (from `prd.json["plan_hash"]`), `regression`, `qa_receipt_valid`, `criteria_verified`, `files_changed`, `production_violations`.

7. Update prd.json: set `passed: true`, `verificationRef: "verification-log.jsonl"` for this story
8. **Append worker's verification_report** to main repo's `.claude/docs/verification-log.md`:
   - Create the file if it doesn't exist
   - Append with header: `## [story.id] — PASS ([date])`
   - This preserves verification evidence that would otherwise be lost with the worktree
9. Proceed to STEP 6A (record progress)
10. Update sprint state: set `consecutive_skips` to 0, increment `stories_passed`
11. Display: `"PASSED: [story.id] — Files: [files_changed] — Progress: [stories_passed]/[total_count]"`
12. Auto-continue to STEP 7

### If FAILED:

1. Worktree changes are isolated — no cleanup needed on feature branch
2. Read sprint state for `current_attempt` and `max_attempts`
3. **If attempts remaining** (current_attempt < max_attempts):
   - Increment `current_attempt` in sprint state
   - Store worker's failure summary as `prior_failure_summary` in sprint state
   - **Append FAIL entry to verification-log.jsonl**: `{"story_id": "[story.id]", "timestamp": "[ISO8601]", "attempt": [current_attempt], "overall_result": "FAIL", "failure_summary": "[worker failure summary]", "plan_hash": "[prd.json plan_hash]", "criteria_verified": [], "files_changed": [result.files_changed], "production_violations": 0}`
   - Display: `"FAILED: [story.id] (attempt [current_attempt]/[max_attempts]) — [worker summary]. Auto-retrying..."`
   - Go back to **STEP 5** (new worktree, worker gets prior failure context)
4. **If exhausted** (current_attempt >= max_attempts):
   - Auto-skip this story, increment `stories_skipped` and `consecutive_skips` in sprint state
   - **Append SKIP entry to verification-log.jsonl**: `{"story_id": "[story.id]", "timestamp": "[ISO8601]", "attempt": [current_attempt], "overall_result": "SKIP", "failure_summary": "Exhausted [max_attempts] attempts: [last worker failure summary]", "plan_hash": "[prd.json plan_hash]", "criteria_verified": [], "files_changed": [], "production_violations": 0}`
   - Display: `"EXHAUSTED: [story.id] after [max_attempts] attempts — [worker summary]. Skipping."`
   - Proceed to STEP 6A (record skip in progress)
5. **Circuit breaker**: if `consecutive_skips` >= 3:
   - Display: `"CIRCUIT BREAKER: 3 consecutive stories exhausted. Stopping sprint."`
   - Go to **STEP 8**
6. Otherwise: continue to STEP 7

## STEP 6A: Progress File

Append to `.claude/docs/progress.md` (create if needed):

- **PASS**: `### [story.id] — PASS ([date])` with files, criteria count, summary
- **SKIP**: `### [story.id] — SKIPPED ([date])` with attempts exhausted, last failure

## STEP 7: Inter-Story Cleanup + Context Refresh

1. Update step tracking: `update_workflow_state(ralph={"current_step": "STEP_7_CLEANUP"})`
2. Update sprint state file `.claude/.workflow-state.json` with latest `consecutive_skips`, `stories_passed`, `stories_skipped` values
3. Worktree cleanup handled automatically by Claude Code
4. **Context Refresh Protocol**:
   a. Re-read `.claude/.workflow-state.json` -- extract full ralph section
   b. Re-read `.claude/prd.json` -- count remaining stories, extract next story ID and description
   c. Re-read `.claude/skills/ralph/PROTOCOL_CARD.md` -- refresh loop protocol near context tail
   d. Display structured refresh:
   ```
   CONTEXT REFRESH: [stories_passed]/[total] complete, [stories_skipped] skipped
   Next: [next_story_id] -- [next_story_description]
   Remaining: [comma-separated remaining story IDs]
   Branch: [feature_branch] | Skips: [consecutive_skips]
   ```
5. Continue to **STEP 2** for next story

## STEP 8: End of Session / All Stories Complete

Display: `"RALPH SESSION COMPLETE — Progress: [stories_passed]/[total] ([stories_skipped] skipped) — Branch: [feature_branch]"`

If any stories were skipped, list each with failure summary and attempt count.

If ANY stories passed (commits exist on feature branch):

- Ask user: `"Create Pull Request? (Yes / No)"`
- If **Yes**:
  - Push feature branch: `git push -u origin [branch]`
  - Create PR:

    ```bash
    gh pr create --title "[plan-name]" --body "$(cat <<'EOF'
    ## Summary
    [Auto-generated from completed stories]

    ### Stories Completed
    - [story.id]: [story.description] (R-PN-NN criteria)

    ### Stories Skipped
    - [story.id]: [reason] ([attempts] attempts exhausted)

    ### Verification Status
    [Per-story PASS/FAIL with verification references]

    ### Files Changed
    [Aggregated from all stories]

    See .claude/docs/PLAN.md for full context.

    Generated with [Claude Code](https://claude.com/claude-code)
    EOF
    )"
    ```

  - Display PR URL
  - Ask user: `"Run /code-review on this PR? (Yes / No)"`
    - If **Yes**: Invoke `/code-review` on the PR. Display result summary.
    - If **No**: Skip code-review. Display: `"Code review skipped."`

- If **No**:
  - Display: `"Changes on branch [branch]. Push when ready: git push -u origin [branch]"`

Run `/handoff` to save session state.

Clean up sprint state: reset the ralph section in `.claude/.workflow-state.json` to defaults (do not delete the whole file, as it also holds needs_verify and prod_violations state).

Display next steps: review PR, run `/audit`, run `/health` before next session.

## Error Recovery

- **prd.json version/parse error**: Run `/plan` to regenerate
- **Git dirty at checkpoint**: STOP — commit or stash first
- **Worker timeout**: Treat as FAIL, auto-retry with context
- **Merge conflict**: `git merge --abort` → FAIL, auto-retry
- **gh CLI not authenticated**: `gh auth login` or push manually
- **Plan gap (STEP 5A)**: User runs `/plan`, then restarts `/ralph`
- **Circuit breaker**: Review skipped stories, fix root causes, restart
- **Context compaction**: Sprint state in file, re-read at each STEP 2. Protocol Card re-read at STEP 7 + printed inline by SessionStart hook after compaction.
- **code-review plugin not available**: Display warning and skip code-review step
