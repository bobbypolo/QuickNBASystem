# Brainstorm: Orchestrator Context Refresh -- True Infinite Context for Ralph

**Date**: 2026-03-03
**Problem**: The Ralph orchestrator runs as one monolithic conversation from `/ralph` start through all stories to PR creation. Its context grows monotonically with each story cycle (dispatch prompt, worker result parsing, 5-question diff review, merge output, regression output), adding ~5-10K tokens per story. A 6-story sprint hits 60-80K tokens before Claude Code's automatic context compaction, which is lossy and unpredictable -- the orchestrator loses track of what it was doing.

**Cross-references**:

- `2026-03-02-ralph-perfection-infinite-context.md` -- Idea 8 describes the infinite context mechanism at a high level but does not solve the orchestrator's own context growth
- `2026-03-02-context-bloat-reduction.md` -- Reduces pre-loaded context (~6,350 token savings) but does not address runtime accumulation
- `2026-03-01-context-window-optimization.md` -- System-level context budget analysis

## Current Architecture (The Problem in Detail)

### What Happens During a Ralph Sprint

```
STEP 1:  Read prd.json, validate schema, init state        (~3K tokens added)
STEP 1.5: Feature branch setup                              (~500 tokens added)
--- Per story (repeats N times) ---
STEP 2:  Re-read state, find next story                    (~1K tokens added)
STEP 3:  Display story details                              (~500 tokens added)
STEP 4:  Git checkpoint                                     (~300 tokens added)
STEP 5A: Plan check                                         (~500 tokens added)
STEP 5:  Dispatch worker (prompt construction + result)     (~3-5K tokens added)
STEP 6:  Receipt validation + diff review + merge + regress (~3-5K tokens added)
STEP 6A: Progress file append                               (~300 tokens added)
STEP 7:  State update (trivial)                             (~100 tokens added)
--- End per story ---
STEP 8:  Sprint summary + PR creation                       (~1K tokens added)
```

**Per-story cost**: ~6-8K tokens of orchestrator-side work per story cycle.

**6-story sprint**: ~48K tokens of accumulated orchestrator context, PLUS the ~16K pre-loaded system prompt, PLUS SKILL.md (~5K tokens), PLUS initial reads (prd.json, PLAN.md). That is ~75-85K tokens before compaction.

### What Happens at Compaction

Claude Code's automatic compaction fires around 80-100K tokens. It summarizes the conversation, losing:

1. **SKILL.md instructions** -- the detailed step-by-step protocol that governs orchestrator behavior
2. **prd.json structure** -- which stories passed, which are next, gate commands, acceptance criteria
3. **Sprint state nuance** -- what attempt number, what the prior failure summary was, what the diff review found
4. **Loop position** -- which STEP the orchestrator was in when compaction fired

The result: Ralph either hallucinates its next action, repeats a story it already completed, or loses the structured protocol and improvises.

### Why Workers Do Not Have This Problem

Workers are dispatched via `isolation: worktree` with `maxTurns: 150`. Each worker:

- Starts with a fresh 200K context window
- Receives all needed context inline in the dispatch prompt
- Works, commits, and returns a structured `RALPH_WORKER_RESULT`
- Terminates -- its context is discarded

Workers have infinite context by construction. The orchestrator is the bottleneck.

### What STEP 7 Does Today (Almost Nothing)

```markdown
## STEP 7: Inter-Story Cleanup

1. Update sprint state file `.claude/.workflow-state.json` with latest values
2. Worktree cleanup handled automatically by Claude Code
3. Continue to **STEP 2** for next story
```

This is the natural refresh point between stories, but it performs zero context management.

### What Exists But Is Not Used

**`/refresh` skill** (`refresh/SKILL.md`): Re-reads PROJECT_BRIEF.md, PLAN.md, HANDOFF.md, last 3 lessons, git status, prd.json plan-hash sync. Outputs a structured "Context Refresh" summary. This is exactly what the orchestrator needs between stories, but Ralph never calls it -- it is manual-only.

**`post_compact_restore.py` SessionStart hook**: Fires on every session start (including after compaction). Currently prints:

- Workflow rules reminder (4 lines)
- Unverified code warning (conditional)
- State summary: `ralph_active`, story ID, attempt, skips
- Mandatory re-read instruction: "Re-read .workflow-state.json before continuing any loop"

This hook knows Ralph is active but does not re-establish orchestrator context. It prints a reminder but does not re-read prd.json, PLAN.md, or SKILL.md.

---

## Option A: Enhanced STEP 7 -- Context Refresh Protocol Between Stories

### Concept

Add explicit context management to STEP 7. After each story completes (pass or skip), before looping to STEP 2, the orchestrator re-reads its essential files and prints a structured context summary. The goal is to keep the orchestrator's "working set" fresh, so when compaction eventually happens, the essential context is recent and survives summarization better.

### What Gets Re-Read

| File                           | Why                                            | Tokens     |
| ------------------------------ | ---------------------------------------------- | ---------- |
| `.claude/.workflow-state.json` | Sprint progress, attempt counter, skips        | ~200       |
| `.claude/prd.json`             | Which stories remain, their criteria and gates | ~500-2000  |
| `.claude/docs/PLAN.md`         | Current phase requirements for diff review     | ~1000-2500 |
| `.claude/docs/progress.md`     | What previous stories accomplished             | ~200-500   |

Total re-read cost: ~2-4K tokens per inter-story refresh.

### What Gets Discarded (Implicitly)

The orchestrator does not explicitly discard context -- Claude Code has no API for that. But by re-reading essential files, the most recent context contains fresh copies of the critical information. When compaction fires, the summarizer has recent authoritative versions to work with rather than stale references from 40K tokens ago.

### Proposed STEP 7 Change

````markdown
## STEP 7: Inter-Story Cleanup + Context Refresh

1. Update sprint state file `.claude/.workflow-state.json` with latest values
2. Worktree cleanup handled automatically by Claude Code
3. **Context Refresh Protocol**:
   a. Re-read `.claude/.workflow-state.json` -- extract sprint progress summary
   b. Re-read `.claude/prd.json` -- identify remaining stories (count and IDs only)
   c. Re-read `.claude/docs/PLAN.md` -- extract current phase header (not full plan)
   d. Display structured refresh:
   ```
   CONTEXT REFRESH: [stories_passed]/[total] complete, [stories_skipped] skipped
   Next: [next_story_id] — [next_story_description]
   Remaining: [list of remaining story IDs]
   Branch: [feature_branch]
   ```
4. Continue to **STEP 2** for next story
````

### Analysis

**Implementation complexity**: Low. Changes to one file: `ralph/SKILL.md` STEP 7 section. No code changes. No new hooks. ~15 lines of instruction added.

**Infinite context effectiveness**: Partial. This helps the orchestrator survive compaction better by ensuring critical context is recent in the conversation. But it does not prevent compaction or guarantee lossless recovery. If compaction fires mid-story (during STEP 5 or 6), the refresh at STEP 7 has not happened yet. The fundamental problem -- one monolithic conversation -- remains.

**What could go wrong**:

- The re-reads add ~2-4K tokens per story, slightly accelerating the approach toward compaction. Counterproductive if the context budget is already tight.
- Claude Code's compaction algorithm may or may not prioritize recent context. If it does not, the re-reads are wasted tokens.
- Does not help if compaction fires mid-story (STEP 5-6), which is the most critical and context-heavy phase.

**Interactions with existing system**:

- Compatible with all existing hooks. No conflicts.
- Compatible with the `post_compact_restore.py` hook -- they serve complementary purposes (refresh prevents loss, restore recovers after loss).

**Files changed**: `ralph/SKILL.md` only.

---

## Option B: Self-Dispatching Orchestrator -- Ralph as a Sub-Agent Loop

### Concept

Split Ralph into two layers:

1. **Outer shell** (the original conversation): Manages the sprint loop, state file, and PR creation. Minimal context -- just the loop logic and state transitions.
2. **Inner orchestrator** (sub-agent): Dispatched for batches of 2-3 stories. Gets a fresh context window. Reads prd.json, PLAN.md, dispatches workers, validates receipts, merges, runs regression. Returns structured results. Terminates.

The outer shell never accumulates story-level context. Each inner orchestrator gets a fresh 200K window and handles a small batch before terminating.

### Architecture

```
Outer Shell (persistent conversation, minimal context)
  ├── STEP 1: Validate prd.json, init state, feature branch
  ├── Loop:
  │   ├── Read state from .workflow-state.json
  │   ├── Identify next batch (2-3 unpassed stories)
  │   ├── Dispatch "ralph-batch" sub-agent with batch assignment
  │   │     └── ralph-batch agent (fresh context):
  │   │           ├── Read prd.json, PLAN.md, progress.md
  │   │           ├── For each story in batch:
  │   │           │   ├── Dispatch ralph-worker (worktree isolation)
  │   │           │   ├── Validate receipt, diff review, merge, regression
  │   │           │   └── Update state file
  │   │           └── Return RALPH_BATCH_RESULT
  │   ├── Parse batch result (pass/fail/skip per story)
  │   ├── Update outer state
  │   └── If stories remain and no circuit breaker: continue loop
  └── STEP 8: Sprint summary + PR creation
```

### New Agent File: `ralph-batch.md`

Would need a new agent file defining the batch orchestrator behavior. This agent would contain the current STEP 2-7 logic from `ralph/SKILL.md`, adapted for batch execution. It would:

- Accept a list of story IDs to process
- Read all necessary files (prd.json, PLAN.md, progress.md, state file)
- Process stories sequentially within the batch
- Dispatch workers via Task tool (sub-agents can dispatch sub-agents if Claude Code supports 2-level nesting)
- Return a structured result per story

### Critical Question: Can Sub-Agents Dispatch Sub-Agents?

Ralph-batch needs to dispatch ralph-workers. This requires 2-level sub-agent nesting:

- Outer shell dispatches ralph-batch (level 1)
- ralph-batch dispatches ralph-worker (level 2)

Claude Code documentation on sub-agents says each agent "runs in its own context window" and can use tools. But it is unclear whether a sub-agent can use the Task tool to dispatch further sub-agents. If not, this architecture is impossible.

**Workaround if nesting is not supported**: ralph-batch does the worker's job itself (no worker dispatch). This loses worktree isolation -- the batch agent would need to do implementation directly. This defeats the purpose of the worker isolation pattern.

**Alternative workaround**: ralph-batch returns a "need worker dispatch" signal, and the outer shell dispatches the worker on its behalf. This adds round-trip overhead but preserves the isolation model. However, this means the outer shell still handles worker results, which adds context to the outer conversation.

### Analysis

**Implementation complexity**: High. Requires:

- New agent file: `.claude/agents/ralph-batch.md`
- Major refactoring of `ralph/SKILL.md` (outer shell becomes thin loop)
- New result format: `RALPH_BATCH_RESULT`
- State file changes to support batch tracking
- Handling of the sub-agent nesting question

**Infinite context effectiveness**: Excellent if it works. Each batch gets a fresh 200K context window. The outer shell stays thin (only accumulates batch result summaries, ~500 tokens each). A 20-story sprint would use 7 batch dispatches, adding ~3,500 tokens to the outer shell -- well within budget.

**What could go wrong**:

- Sub-agent nesting may not be supported. This is the deal-breaker question.
- The batch agent itself could hit context limits if stories are complex and retries are needed. A batch of 3 stories with 4 retries each = 12 worker dispatches within one batch context.
- Error recovery is more complex: if the batch agent crashes mid-batch, the outer shell must detect partial progress and resume.
- The batch agent cannot access `.claude/` gitignored files if it runs in a worktree. But the batch agent should NOT run in a worktree (it merges to the feature branch). It should run with `isolation: none` or a new isolation mode.

**Interactions with existing system**:

- `post_compact_restore.py` fires for the outer shell's session. It would correctly detect Ralph is active and print state.
- Workers still get worktree isolation -- unchanged.
- State file management becomes more complex (batch agent and outer shell both write to it).

**Files changed**:

- New: `.claude/agents/ralph-batch.md`
- Modified: `.claude/skills/ralph/SKILL.md` (major rewrite)
- Modified: `.claude/.workflow-state.json` schema (batch tracking fields)
- Possibly: `.claude/hooks/_lib.py` (new state fields)

---

## Option C: Enhanced SessionStart Hook -- Full Context Restore After Compaction

### Concept

Make `post_compact_restore.py` detect that Ralph is active and automatically re-establish full orchestrator context by reading essential files and printing their contents into the conversation. The hook output becomes the orchestrator's "cold start" protocol after compaction.

### Current Hook (47 lines)

Prints:

1. Workflow rules reminder (4 lines of text)
2. Unverified code warning (conditional)
3. State summary: `ralph_active={bool}, story={id}, attempt={n}, skips={n}`
4. Mandatory re-read instruction

### Proposed Enhancement

When `ralph_active` is True, the hook reads and prints additional context:

```python
if ralph_active:
    # Read and print essential Ralph context
    prd_path = _CLAUDE_DIR / "prd.json"
    plan_path = _CLAUDE_DIR / "docs" / "PLAN.md"
    progress_path = _CLAUDE_DIR / "docs" / "progress.md"
    skill_path = _CLAUDE_DIR / "skills" / "ralph" / "SKILL.md"

    # Sprint state (full details)
    print(f"RALPH CONTEXT RESTORE:")
    print(f"  Story: {ralph_story} (attempt {ralph_attempt}/{ralph.get('max_attempts', 4)})")
    print(f"  Skips: {ralph_skips} consecutive")
    print(f"  Passed: {ralph.get('stories_passed', 0)}")
    print(f"  Branch: {ralph.get('feature_branch', 'unknown')}")
    print(f"  Prior failure: {ralph.get('prior_failure_summary', 'none')}")

    # Remaining stories summary
    if prd_path.exists():
        prd = json.loads(prd_path.read_text())
        remaining = [s["id"] for s in prd.get("stories", []) if not s.get("passed")]
        print(f"  Remaining stories: {', '.join(remaining)}")

    # Current story details
    current = next((s for s in prd.get("stories", []) if s["id"] == ralph_story), None)
    if current:
        print(f"  Current story: {current['description']}")
        for ac in current.get("acceptanceCriteria", []):
            print(f"    - {ac['id']}: {ac['criterion']}")

    print("MANDATORY: You are the Ralph orchestrator. Re-read ralph/SKILL.md for your protocol.")
    print("MANDATORY: Continue from your current STEP based on the state above.")
```

### Analysis

**Implementation complexity**: Medium. Changes to one file: `post_compact_restore.py`. Requires reading prd.json in the hook (adding JSON parsing, which `_lib.py` already supports). ~40 lines of new code.

**Infinite context effectiveness**: Reactive only. This does not prevent compaction or reduce context growth. It only helps recovery AFTER compaction has already happened. The quality of recovery depends on:

1. Whether the hook output is detailed enough for the orchestrator to resume correctly
2. Whether the orchestrator can correctly determine which STEP it was in when compaction fired
3. Whether the orchestrator re-reads SKILL.md as instructed (the hook cannot force this -- it can only print a reminder)

**The fundamental problem**: The hook prints into the conversation, but the orchestrator's understanding of its own protocol (SKILL.md) has been compacted away. Printing "re-read SKILL.md" works only if the post-compaction context still remembers what SKILL.md is and how to follow it. In practice, after heavy compaction, the LLM may have lost the detailed step-by-step protocol and may not fully reconstruct it from a re-read.

**What could go wrong**:

- The hook fires on EVERY session start, not just after compaction. The `SessionStart` event does not distinguish between "new session" and "resumed after compaction." If Ralph is active (state file says so) but this is a brand new session (user ran `/ralph` in a new terminal), the hook would print restore context that is confusing because the orchestrator has not started yet in this session.
- The hook cannot know which STEP the orchestrator was in. The state file tracks `current_story_id` and `current_attempt` but not `current_step`. Adding step tracking to the state file would help but requires changes to the SKILL.md protocol (write step number to state at each transition).
- Hook output is limited. Printing the entire SKILL.md (~348 lines) into hook output would be excessive. But without it, the orchestrator may not remember its protocol.

**Interactions with existing system**:

- Directly extends `post_compact_restore.py` -- clean integration.
- Uses `_lib.py`'s `read_workflow_state()` -- already compatible.
- Does not conflict with other hooks.

**Files changed**:

- Modified: `.claude/hooks/post_compact_restore.py` (~40 lines added)
- Possibly: `.claude/skills/ralph/SKILL.md` (add step tracking to state writes)
- Possibly: `.claude/hooks/_lib.py` (add `current_step` to DEFAULT_WORKFLOW_STATE ralph section)

---

## Option D: Hybrid -- Enhanced STEP 7 + Enhanced SessionStart Hook

### Concept

Combine Option A and Option C to create a two-layer defense:

1. **Proactive** (Option A at STEP 7): Between every story, re-read essential files and print a structured refresh. This keeps critical context fresh and recent, improving compaction survival.

2. **Reactive** (Option C at SessionStart): After compaction fires, the hook detects Ralph is active and prints a full context restore with sprint state, remaining stories, current story details, and re-read instructions.

### Why Both Layers Are Needed

- Option A alone helps compaction produce better summaries (recent context is prioritized) but cannot guarantee lossless recovery.
- Option C alone only fires after compaction has already lost context. The quality of the summary that the orchestrator resumes from depends on how much context survived.
- Together: Option A maximizes what survives compaction (proactive). Option C provides the safety net for what did not survive (reactive).

### Additional Enhancement: Step Tracking in State File

Add `current_step` to the ralph state in `.workflow-state.json`. The orchestrator writes its current step number at each major transition:

```python
# At STEP 2:
update_workflow_state(ralph={"current_step": "STEP_2_FIND_NEXT"})

# At STEP 5:
update_workflow_state(ralph={"current_step": "STEP_5_DISPATCH"})

# At STEP 6:
update_workflow_state(ralph={"current_step": "STEP_6_HANDLE_RESULT"})
```

This allows the SessionStart hook to print the exact step to resume from:

```
RALPH CONTEXT RESTORE: Resume from STEP_6_HANDLE_RESULT
  Waiting for worker result for STORY-003 (attempt 2/4)
```

### Additional Enhancement: Context Budget Awareness

Add a note in STEP 7 that the orchestrator should assess its own context usage. While Claude Code does not expose a "tokens used" counter, the orchestrator can use a rough heuristic:

```markdown
## STEP 7 sub-step: Context Budget Check

Count the number of completed story cycles since the last context refresh or session start.
If 4+ stories have been processed in this session without compaction:

- Print: "CONTEXT NOTE: [N] stories processed. Context may be aging."
- The next compaction will trigger SessionStart hook for full restore.
```

This is informational, not actionable, but it primes the LLM to expect compaction and handle it gracefully.

### Proposed STEP 7 (Full Hybrid Version)

````markdown
## STEP 7: Inter-Story Cleanup + Context Refresh

1. Update sprint state file `.claude/.workflow-state.json`:
   - Set `current_step` to `"STEP_7_CLEANUP"`
   - Update `consecutive_skips`, `stories_passed`, `stories_skipped`
2. Worktree cleanup handled automatically by Claude Code
3. **Context Refresh Protocol**:
   a. Re-read `.claude/.workflow-state.json` — extract full ralph section
   b. Re-read `.claude/prd.json` — count remaining stories, extract next story ID and description
   c. Display structured refresh:
   ```
   CONTEXT REFRESH: [stories_passed]/[total] complete, [stories_skipped] skipped
   Next: [next_story_id] — [next_story_description]
   Remaining: [comma-separated remaining story IDs]
   Branch: [feature_branch] | Skips: [consecutive_skips]
   ```
4. Continue to **STEP 2** for next story
````

### Proposed SessionStart Hook Enhancement

```python
if ralph_active:
    print("RALPH CONTEXT RESTORE:")
    print(f"  Step: {ralph.get('current_step', 'unknown')}")
    print(f"  Story: {ralph_story} (attempt {ralph_attempt}/{ralph.get('max_attempts', 4)})")
    print(f"  Consecutive skips: {ralph_skips}")
    print(f"  Stories passed: {ralph.get('stories_passed', 0)}")
    print(f"  Branch: {ralph.get('feature_branch', 'unknown')}")
    if ralph.get('prior_failure_summary'):
        print(f"  Prior failure: {ralph.get('prior_failure_summary')}")

    # Read remaining stories from prd.json
    prd_path = PROJECT_ROOT / ".claude" / "prd.json"
    if prd_path.exists():
        try:
            prd = json.loads(prd_path.read_text(encoding="utf-8"))
            remaining = [s for s in prd.get("stories", []) if not s.get("passed")]
            print(f"  Remaining: {len(remaining)} stories — {', '.join(s['id'] for s in remaining)}")
            # Print current story details if identifiable
            current = next((s for s in remaining if s["id"] == ralph_story), None)
            if current:
                print(f"  Current story: {current.get('description', 'no description')}")
                for ac in current.get("acceptanceCriteria", []):
                    print(f"    AC {ac['id']}: {ac['criterion']}")
                gc = current.get("gateCmds", {})
                if gc:
                    print(f"    Gates: {', '.join(f'{k}={v}' for k, v in gc.items() if v)}")
        except (json.JSONDecodeError, KeyError, TypeError):
            print("  WARNING: Could not parse prd.json for context restore")

    print("MANDATORY: Re-read .claude/skills/ralph/SKILL.md for orchestrator protocol.")
    step = ralph.get('current_step', '')
    if 'STEP_5' in step or 'STEP_6' in step:
        print(f"MANDATORY: Resume from {step}. Check if worker result is pending.")
    elif 'STEP_7' in step or 'STEP_2' in step:
        print(f"MANDATORY: Resume from STEP 2 — find next unpassed story.")
    else:
        print(f"MANDATORY: Resume from STEP 2 — determine current position from state.")
```

### Analysis

**Implementation complexity**: Medium. Changes to two files (SKILL.md + post_compact_restore.py), plus a minor state schema addition. No architectural changes. ~50 lines of new hook code, ~15 lines of SKILL.md changes, ~5 lines of state schema change.

**Infinite context effectiveness**: Good but not perfect. This is the best achievable outcome within the constraint of a single conversation. The proactive refresh keeps context fresh (improving compaction quality), and the reactive restore provides a safety net. Together, they handle the two failure modes:

1. **Gradual degradation** (context ages, references become stale): Handled by STEP 7 refresh.
2. **Sudden loss** (compaction fires): Handled by SessionStart restore.

The remaining gap: neither mechanism can guarantee the orchestrator correctly follows SKILL.md after compaction. The LLM must re-read SKILL.md and correctly identify its position in the protocol. This is probabilistic, not deterministic.

**What could go wrong**:

- The re-reads at STEP 7 add ~1-2K tokens per story (less than the full Option A proposal because we only read state and prd.json summary, not full PLAN.md). This slightly accelerates context growth but the tradeoff is worth it.
- The SessionStart hook printing current story details adds ~200-500 tokens to hook output. This is within reasonable bounds.
- Step tracking in the state file requires discipline -- every major transition in SKILL.md must include a state write. If a step is missed, the restore may resume from the wrong position.

**Files changed**:

- Modified: `.claude/skills/ralph/SKILL.md` (STEP 7 enhancement, step tracking in STEPs 2-7)
- Modified: `.claude/hooks/post_compact_restore.py` (~50 lines added)
- Modified: `.claude/hooks/_lib.py` (add `current_step` to DEFAULT_WORKFLOW_STATE ralph dict)

---

## Option E: Considered and Rejected -- `/refresh` Integration

One obvious idea is to have Ralph call `/refresh` at STEP 7. This was considered and rejected because:

1. **Skills cannot be invoked from within skills.** Ralph is a skill (`/ralph`). It cannot invoke `/refresh` as a sub-command. Skills are invoked by the user or by Claude's tool routing, not by other skills programmatically.

2. **Even if it could**, `/refresh` reads files that are not useful to Ralph (PROJECT_BRIEF.md, HANDOFF.md, lessons.md) and does not read files that ARE useful (prd.json story details, sprint state). The overlap is partial at best.

3. **The right approach is to inline the relevant refresh logic** into STEP 7, reading exactly the files Ralph needs -- not a generic context refresh.

---

## Comparison Matrix

| Criterion                             | A: Enhanced STEP 7         | B: Self-Dispatching    | C: Enhanced Hook     | D: Hybrid (A+C)       |
| ------------------------------------- | -------------------------- | ---------------------- | -------------------- | --------------------- |
| Implementation complexity             | Low                        | High                   | Medium               | Medium                |
| True infinite context                 | No (mitigates, not solves) | Yes (if nesting works) | No (reactive only)   | No (best mitigation)  |
| Files changed                         | 1                          | 3-4 + new agent        | 1-2                  | 2-3                   |
| Risk of breaking existing behavior    | Very low                   | High                   | Low                  | Low                   |
| Handles compaction mid-story          | No                         | N/A (no compaction)    | Yes (after the fact) | Partially             |
| Adds context overhead                 | ~1-2K/story                | ~500/batch (outer)     | ~200-500 on restore  | ~1-2K/story + restore |
| Sub-agent nesting dependency          | No                         | Yes (deal-breaker?)    | No                   | No                    |
| Works with parallel dispatch (future) | Yes                        | Complicates it         | Yes                  | Yes                   |

---

## Recommendation: Option D (Hybrid) with Path to Option B

### Immediate Implementation: Option D

Option D (Hybrid: Enhanced STEP 7 + Enhanced SessionStart Hook) is the right choice for these reasons:

1. **It is the highest-value, lowest-risk option.** Two targeted changes to existing files, no new agents, no architectural changes, no dependency on unverified Claude Code features (sub-agent nesting).

2. **It addresses both failure modes.** Proactive refresh at STEP 7 keeps context fresh. Reactive restore at SessionStart provides a safety net after compaction. Neither alone is sufficient; together they cover the gap.

3. **It is compatible with all planned future work.** Parallel sub-agent dispatch (from the ralph-perfection brainstorm) works with this approach -- STEP 7 fires after each story regardless of whether workers ran in parallel. The SessionStart hook is independent of dispatch strategy.

4. **The step tracking addition is independently valuable.** Even without the context refresh use case, knowing which STEP Ralph was in when a session ended or compacted is useful for debugging and manual recovery.

### Future Path: Option B

Option B (self-dispatching orchestrator) is the theoretically correct solution -- it gives true infinite context by construction, the same way workers already have it. But it depends on a critical unknown (sub-agent nesting support) and requires significant architectural work. The right approach is:

1. **Implement Option D now.** Ship it, run a multi-story sprint, observe whether compaction causes issues in practice.
2. **Test sub-agent nesting.** Run a simple experiment: can a sub-agent dispatch another sub-agent? If yes, Option B becomes viable.
3. **If Option D proves insufficient** (orchestrator still loses context after compaction despite the refresh + restore), invest in Option B with the confirmed nesting support.

In practice, Option D may be sufficient indefinitely. The orchestrator's per-story context cost is ~6-8K tokens. With the refresh keeping context fresh and the restore recovering after compaction, a 10-story sprint should be manageable. Only sprints with 15+ stories or complex multi-retry stories would push the limits.

---

## Concrete Implementation Plan (Option D)

### Phase 1: State Schema Extension

**File**: `.claude/hooks/_lib.py`

Add `current_step` to `DEFAULT_WORKFLOW_STATE["ralph"]`:

```python
DEFAULT_WORKFLOW_STATE: dict = {
    "needs_verify": None,
    "stop_block_count": 0,
    "ralph": {
        "consecutive_skips": 0,
        "stories_passed": 0,
        "stories_skipped": 0,
        "feature_branch": "",
        "current_story_id": "",
        "current_attempt": 0,
        "max_attempts": 4,
        "prior_failure_summary": "",
        "current_step": "",          # NEW: tracks orchestrator position
    },
}
```

**Risk**: None. Adding a new key with empty default is backward-compatible. Existing state files without this key will get the default via `_deep_merge_defaults()`.

### Phase 2: Enhanced STEP 7 in SKILL.md

**File**: `.claude/skills/ralph/SKILL.md`

Replace current STEP 7 with the hybrid version (see Option D section above). Additionally, add step tracking writes to STEPs 2, 4, 5, 6, and 7:

- STEP 2: `update_workflow_state(ralph={"current_step": "STEP_2_FIND_NEXT"})`
- STEP 4: `update_workflow_state(ralph={"current_step": "STEP_4_CHECKPOINT"})`
- STEP 5: `update_workflow_state(ralph={"current_step": "STEP_5_DISPATCH"})`
- STEP 6: `update_workflow_state(ralph={"current_step": "STEP_6_HANDLE_RESULT"})`
- STEP 7: `update_workflow_state(ralph={"current_step": "STEP_7_CLEANUP"})`

Note: These are instructions in the SKILL.md for the orchestrator to follow. They translate to the orchestrator calling `update_workflow_state` via inline Python or writing to the state file via bash.

**Risk**: Low. The step tracking is additive -- it writes to the state file at transitions that already update state. The refresh protocol at STEP 7 adds ~1-2K tokens per story cycle.

### Phase 3: Enhanced SessionStart Hook

**File**: `.claude/hooks/post_compact_restore.py`

Add the Ralph context restore block from Option D analysis. The hook already reads workflow state; the enhancement adds:

1. prd.json reading for remaining stories
2. Current story details (description, acceptance criteria, gate commands)
3. Step-aware resume instructions
4. SKILL.md re-read instruction

**Risk**: Low. The hook already fires on every session start. The added code is guarded by `if ralph_active` and wrapped in try/except. A failure in prd.json parsing falls back to the existing behavior.

### Phase 4: Validation

Run a multi-story Ralph sprint (4+ stories) and observe:

1. Does the STEP 7 refresh display correctly between stories?
2. Does the orchestrator maintain protocol adherence across stories?
3. If compaction fires, does the SessionStart hook print the restore context?
4. Does the orchestrator correctly resume from the restore context?

### Testing

- **Unit test**: Verify `current_step` is included in DEFAULT_WORKFLOW_STATE and survives read/write cycle.
- **Unit test**: Verify `post_compact_restore.py` reads prd.json and prints story details when ralph_active is True.
- **Unit test**: Verify `post_compact_restore.py` handles missing/corrupt prd.json gracefully.
- **Integration test**: Full Ralph sprint simulation (mock workers) -- verify STEP 7 refresh output appears between stories.
- **Manual test**: Run actual Ralph sprint, observe context behavior across 4+ stories.

---

## Sources

- `.claude/skills/ralph/SKILL.md` -- full orchestrator protocol (348 lines)
- `.claude/skills/refresh/SKILL.md` -- manual context refresh skill (36 lines)
- `.claude/hooks/post_compact_restore.py` -- current SessionStart hook (49 lines)
- `.claude/hooks/_lib.py` -- state management, DEFAULT_WORKFLOW_STATE (lines 45-58)
- `.claude/agents/ralph-worker.md` -- worker agent spec (153 lines)
- `.claude/settings.json` -- hook wiring configuration
- `.claude/docs/ARCHITECTURE.md` -- system diagram, hook chain, design decisions
- Prior brainstorm: `2026-03-02-ralph-perfection-infinite-context.md` -- Idea 8 (infinite context architecture)
- Prior brainstorm: `2026-03-02-context-bloat-reduction.md` -- context budget analysis
- Prior brainstorm: `2026-03-01-context-window-optimization.md` -- system-level optimization
- Prior brainstorm: `2026-03-02-hooks-simplification.md` -- hooks infrastructure analysis

---

## Build Strategy

### Module Dependencies

```
Phase 1 (State Schema):
  _lib.py DEFAULT_WORKFLOW_STATE ← standalone, backward-compatible

Phase 2 (STEP 7 Enhancement):
  ralph/SKILL.md ← depends on Phase 1 (uses current_step field)

Phase 3 (SessionStart Enhancement):
  post_compact_restore.py ← depends on Phase 1 (reads current_step field)
                           ← reads prd.json (no new dependency, just JSON parsing)

Phase 4 (Validation):
  ← depends on Phases 1-3 being complete
```

### Build Order

1. Add `current_step` to DEFAULT_WORKFLOW_STATE in `_lib.py`
2. Update existing tests to include `current_step` in expected state dicts
3. Enhance STEP 7 in `ralph/SKILL.md` with context refresh protocol
4. Add step tracking instructions to STEPs 2, 4, 5, 6, 7 in `ralph/SKILL.md`
5. Enhance `post_compact_restore.py` with Ralph context restore
6. Add unit tests for new hook behavior
7. Run full test suite to verify no regressions
8. Manual validation with a multi-story Ralph sprint

### Testing Pyramid

- **Unit tests (80%)**: State schema changes, hook prd.json parsing, hook output with ralph_active=True, hook graceful degradation with missing prd.json
- **Integration tests (10%)**: Full hook invocation with simulated workflow state
- **Manual tests (10%)**: Multi-story Ralph sprint observing context behavior

### Risk Mitigation Mapping

| Risk                                                       | Mitigation                                                                                                             |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| State schema change breaks existing state files            | `_deep_merge_defaults()` adds missing keys automatically; backward-compatible                                          |
| STEP 7 refresh adds too many tokens                        | Refresh is summary-only (story IDs and counts, not full details); ~1-2K tokens                                         |
| SessionStart hook fails to parse prd.json                  | Try/except wraps all prd.json reading; falls back to existing behavior                                                 |
| Orchestrator ignores re-read instructions after compaction | Step-aware resume instructions are specific ("Resume from STEP_6_HANDLE_RESULT"); SKILL.md re-read is marked MANDATORY |
| Step tracking instructions not followed by orchestrator    | Step writes are simple one-liners added to existing state update points; failure is silent (empty string default)      |

### Recommended Build Mode

**Manual Mode** (builder agent, single session)

Rationale:

- This is a small, focused change across 3 files (~100 lines of changes total)
- The SKILL.md changes are instruction edits, not code
- The hook changes are ~50 lines of Python with straightforward logic
- The state schema change is a single line addition
- Ralph Mode (with its worker dispatch, QA pipeline, and merge workflow) would add overhead disproportionate to the scope
- This should be one of the first changes applied before the next Ralph sprint, so it cannot be built using Ralph itself
