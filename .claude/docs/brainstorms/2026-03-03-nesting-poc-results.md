# Nesting PoC Results (Phase 5)

**Date**: 2026-03-03
**Result**: FAIL — 2-level agent nesting is not supported

## Test Setup

Dispatched a parent agent (`general-purpose`) with instructions to dispatch a child agent (`general-purpose`, `isolation: worktree`).

## Findings

1. The Agent tool is available to the **top-level conversation** only
2. Sub-agents dispatched via the Agent tool do **not** have the Agent tool in their toolset
3. Sub-agents searched both immediate and deferred tools — no agent dispatch capability found
4. The `EnterWorktree` tool exists in sub-agents but only changes working directory, doesn't spawn a separate agent

## Implication

The story-per-agent pattern (Phases 6-7) requires 3-level nesting:

```
User conversation → ralph-story-agent → ralph-worker
```

Since level-2 agents cannot dispatch level-3 agents, this architecture is **not feasible**.

## Decision

Fall back to **Phase 4B** (Appendix A): strengthen session restore with step tracking and STEP 7 context refresh protocol. This provides the best achievable mitigation within a single monolithic conversation.

Phases 6 and 7 are cancelled.
