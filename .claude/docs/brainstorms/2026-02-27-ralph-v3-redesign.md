# Brainstorm: Ralph v3 Redesign — External Loop + Native Sub-Agents

**Date**: 2026-02-27
**Problem**: Ralph v2 runs inside a single Claude session, creating a context ceiling that prevents infinite story loops and unattended overnight operation. Online Ralph implementations use external bash scripts spawning fresh `claude -p` processes per story — achieving unlimited context and autonomous operation. We need to adopt this pattern while preserving our strengths (16-step QA, R-PN-NN traceability, prd.json v2, production-grade enforcement).

## Current State (Ralph v2)

| Aspect             | Implementation                                 | Limitation                            |
| ------------------ | ---------------------------------------------- | ------------------------------------- |
| Loop driver        | In-session `/ralph` skill                      | Context ceiling, can't run unattended |
| Context per story  | Task tool sub-agent (isolated)                 | Orchestrator still accumulates        |
| Worktree isolation | Manual bash commands in prompt                 | Native `isolation: worktree` exists   |
| Exit detection     | String match on sub-agent result               | Fragile, no structured output         |
| Error recovery     | 3-attempt retry, escalation stop               | No circuit breaker, no cooldown       |
| Rate limiting      | None                                           | Can exhaust API limits silently       |
| Turn limits        | None per story                                 | Runaway sub-agent possible            |
| Memory             | ralph-state.json (ephemeral)                   | No persistent cross-story learning    |
| QA pipeline        | 16-step, acceptance tests, prod-grade scan     | This is a strength to preserve        |
| Traceability       | R-PN-NN end-to-end chain                       | This is a strength to preserve        |
| Git workflow       | Feature branch, selective staging, PR creation | This is a strength to preserve        |

## Ideas

### 1. External Orchestrator Script (ralph-runner)

**Description**: Move the story loop from a Claude skill to an external PowerShell/bash script that calls `claude -p` per story. The script reads prd.json, finds the next incomplete story, constructs a prompt, spawns a fresh Claude process, parses the structured JSON result, and loops. prd.json is the shared state file between invocations.

```
ralph-runner.ps1 / ralph-runner.sh
  │
  ├── Read prd.json → find first story where passed: false
  ├── Construct prompt with story details + builder/QA instructions
  ├── claude -p "[prompt]" --output-format json --json-schema "[schema]" \
  │     --allowedTools "Read,Edit,Write,Bash,Glob,Grep" \
  │     --dangerously-skip-permissions
  ├── Parse JSON result: {passed, story_id, summary, files_changed, escalation}
  ├── If passed: update prd.json, append to progress.md, git commit
  ├── If failed: increment failure counter, check circuit breaker
  ├── Sleep 5s → loop
  └── Exit when all stories passed or circuit breaker opens
```

**What goes into the prompt per story**:

- Story definition from prd.json (criteria, gate commands)
- "Read PLAN.md for context"
- "Read .claude/agents/builder.md and .claude/agents/qa.md for rules"
- "Read .claude/docs/progress.md for what prior stories did"
- All 10 production-grade code standards
- TDD mandate with R-PN-NN markers
- 16-step QA pipeline instructions
- Selective staging rules
- "Return structured JSON result"

**What the external script handles** (not Claude):

- Story selection (next incomplete from prd.json)
- prd.json updates (set passed: true, verificationRef)
- Circuit breaker logic
- Rate limit tracking
- Git commit after success
- Progress logging
- Feature branch setup
- PR creation at end

- **Pros**: Infinite context — each story gets a fresh 200K context window. Can run unattended overnight. Circuit breaker in script is deterministic (not prompt-dependent). Structured JSON exit via `--json-schema` eliminates fragile string matching. Rate limit handling is trivial in script. Cross-platform (PowerShell for Windows, bash for Linux/Mac). Matches proven industry pattern (snarktank/ralph, frankbria). External script can be tested independently of Claude.
- **Cons**: Loses interactive Retry/Skip/Stop flow — script decides automatically. Each story re-reads PLAN.md, builder.md, qa.md from scratch (redundant I/O but context is fresh). `--dangerously-skip-permissions` required for unattended — security tradeoff. No session continuity — if a story needs context from a prior story's implementation, it must discover it from git history or progress.md. More complex deployment — script + skill instead of just skill. PowerShell/bash is a second language to maintain alongside Python hooks.

### 2. Native Sub-Agent Definition (ralph-worker.md)

**Description**: Define a proper `.claude/agents/ralph-worker.md` with YAML frontmatter using Claude Code's native sub-agent features instead of manually constructing Task tool prompts.

```yaml
---
name: ralph-worker
description: V-Model story implementation worker. TDD + 16-step QA pipeline.
isolation: worktree
maxTurns: 100
memory: project
model: inherit
permissionMode: acceptEdits
skills:
  - verify
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "python .claude/hooks/pre_bash_guard.py"
  PostToolUse:
    - matcher: "Edit|Write"
      hooks:
        - type: command
          command: "python .claude/hooks/post_format.py"
---
[System prompt with builder rules, QA steps, production-grade standards...]
```

Key frontmatter features:

- `isolation: worktree` — automatic worktree creation/cleanup (replaces our manual bash commands)
- `maxTurns: 100` — hard cap prevents runaway sub-agents (new safety)
- `memory: project` — persistent memory at `.claude/agent-memory/ralph-worker/` survives across sessions. Worker writes lessons, codebase patterns, recurring issues. Auto-injected into future invocations.
- `skills: [verify]` — preloads /verify skill content into worker context
- `hooks` — worker-scoped bash guard and format hooks (don't need parent session hooks)

- **Pros**: Native platform features replace manual workarounds. `maxTurns` prevents infinite loops per story. Persistent memory builds institutional knowledge across sessions. Worker-scoped hooks are cleaner than parent-session hooks. Worktree lifecycle managed by platform (no manual cleanup). `permissionMode: acceptEdits` enables unattended operation. Skills preloading means worker starts with /verify knowledge. Transcript persistence at `~/.claude/projects/.../subagents/` enables post-mortem debugging.
- **Cons**: Sub-agents cannot spawn other sub-agents (no nested delegation). If worker needs to invoke /audit or other skills beyond verify, those must be in the system prompt. Worker prompt becomes very large (builder.md + qa.md + standards + story details). `memory: project` writes to `.claude/agent-memory/` — need to add to .gitignore or commit it. Frontmatter fields depend on Claude Code version — breaking changes possible.

### 3. Dual-Mode Ralph (Interactive + Autonomous)

**Description**: Keep `/ralph` skill for interactive supervised sessions AND add `ralph-runner` script for autonomous overnight operation. Both modes share the same prd.json, progress.md, and ralph-worker sub-agent. The skill mode uses Task tool dispatch with ralph-worker. The script mode uses `claude -p` with the same worker prompt.

```
INTERACTIVE MODE (/ralph skill):
  User → /ralph → validates prd.json → per story:
    Task(ralph-worker) → result → ask user Continue/Stop → loop

AUTONOMOUS MODE (ralph-runner script):
  Script → reads prd.json → per story:
    claude -p "story prompt" → JSON result → update prd.json → loop
    Circuit breaker, rate limits, progress.md logging
```

Shared artifacts:

- `.claude/prd.json` — story definitions and status
- `.claude/docs/progress.md` — append-only learnings log
- `.claude/agents/ralph-worker.md` — sub-agent definition
- `.claude/docs/PLAN.md` — implementation context
- `.claude/docs/verification-log.md` — QA results

- **Pros**: No breaking change — `/ralph` still works for supervised use. Autonomous mode available when user wants overnight runs. Same worker definition, same quality gates. Users choose based on context: interactive for tricky work, autonomous for well-defined stories. Gradual migration path — start with interactive, move to autonomous as confidence grows.
- **Cons**: Two orchestration paths to maintain. Divergence risk — interactive mode may get features that autonomous doesn't and vice versa. Duplication in prompt construction. User confusion about when to use which mode.

### 4. Circuit Breaker System

**Description**: Add circuit breaker logic (external script for autonomous mode, hook-based for interactive mode) that detects stuck states and prevents infinite retries.

**Three-strike circuit breaker**:

```
State: CLOSED (normal) → OPEN (blocked) → HALF_OPEN (testing)

Triggers to OPEN:
- 3 consecutive stories with same error signature
- 5 consecutive stories with no progress (passed count unchanged)
- 3 consecutive stories where sub-agent hits maxTurns limit
- Rate limit error from Anthropic API

Recovery:
- OPEN: wait cooldown period (default 30 min)
- After cooldown: try ONE story (HALF_OPEN)
- If success: back to CLOSED
- If failure: back to OPEN with doubled cooldown

Error signature detection:
- Hash the last 200 chars of error output
- Compare against last N error hashes
- If 3+ identical hashes → identical error → circuit opens
```

**In external script** (autonomous mode):

```powershell
$errorHashes = @()
$consecutiveFailures = 0
$circuitState = "CLOSED"
$cooldownMinutes = 30

# After each story failure:
$hash = Get-Hash $result.summary
if ($errorHashes[-3..-1] -contains $hash) {
    $circuitState = "OPEN"
    Write-Host "Circuit OPEN: identical errors detected. Cooling down..."
    Start-Sleep ($cooldownMinutes * 60)
}
```

**In interactive mode** (ralph skill):

- After 3 identical failures: display warning, recommend stopping
- Not a hard block — user can override

- **Pros**: Prevents burning API credits on unsolvable problems. Identical error detection catches infinite loops. No-progress detection catches semantic loops (different errors, same outcome). Cooldown allows transient issues (rate limits, network) to resolve. State machine is deterministic and testable. External script implementation is straightforward.
- **Cons**: Error signature hashing is imprecise — similar but different errors may not match. Cooldown timer means autonomous mode sits idle. False positives possible (3 different but related failures misidentified as stuck). Adds complexity to the external script. In interactive mode, user probably notices stuck state themselves.

### 5. Structured Exit via --json-schema

**Description**: Replace string-matching completion detection with Claude Code's native `--json-schema` flag. The external script passes a JSON schema, Claude returns conforming output, script parses with `jq`.

**Schema definition**:

```json
{
  "type": "object",
  "properties": {
    "passed": { "type": "boolean" },
    "story_id": { "type": "string" },
    "summary": { "type": "string" },
    "files_changed": { "type": "array", "items": { "type": "string" } },
    "escalation": { "type": "boolean" },
    "escalation_reason": { "type": "string" },
    "verification_report": { "type": "string" },
    "worktree_branch": { "type": "string" }
  },
  "required": ["passed", "story_id", "summary"]
}
```

**Script usage**:

```bash
RESULT=$(claude -p "$PROMPT" \
  --output-format json \
  --json-schema "$SCHEMA" \
  --allowedTools "Read,Edit,Write,Bash,Glob,Grep")

PASSED=$(echo "$RESULT" | jq -r '.structured_output.passed')
STORY_ID=$(echo "$RESULT" | jq -r '.structured_output.story_id')
```

- **Pros**: Zero ambiguity in exit detection. Schema-validated output — malformed results caught automatically. `jq` parsing is trivial and reliable. Works with any prompt content (no fragile string markers). Schema can evolve with versioning. The `--json-schema` flag is officially supported by Claude Code.
- **Cons**: `--json-schema` is a relatively new feature — may have edge cases. Large schemas may constrain Claude's output. The `structured_output` field is separate from `result` — need to handle both. If Claude fails to conform to schema, the entire invocation may fail rather than returning partial results.

### 6. Progress File as Persistent Memory

**Description**: Replace ephemeral `ralph-state.json` with an append-only `progress.md` that persists across stories and sessions. Each story appends what was built, what failed, and what was learned. Subsequent stories read this for context.

**Format**:

```markdown
# Ralph Progress Log

## STORY-001: prd.json v2 Schema (PASSED, attempt 1)

- Files: .claude/prd.json, .claude/docs/knowledge/conventions.md
- Key decisions: Used structured objects over flat strings
- Learned: JSON schema validation catches issues early

## STORY-002: Feature Plan Upgrades (PASSED, attempt 2)

- Files: .claude/skills/feature_plan/SKILL.md
- Attempt 1 failed: Pre-Flight checks missed interface contract validation
- Fix: Added cross-phase consistency check
- Learned: Step ordering matters — 6b must pass before 7 runs

## STORY-003: QA Enhancement (FAILED → SKIPPED)

- Escalation: Builder couldn't resolve circular dependency in test imports
- Error: ImportError in test_acceptance.py due to conftest.py conflict
- Action needed: Manual restructuring of test directory
```

**How it's used**:

- External script: appends after each story completion
- Claude prompt: "Read .claude/docs/progress.md for context from prior stories"
- Native sub-agent with `memory: project`: worker writes to its own MEMORY.md AND script writes to progress.md (complementary — worker memory is agent-internal, progress.md is human-readable)

- **Pros**: Human-readable log of the entire sprint. Provides context to subsequent stories without session continuity. Captures lessons that inform retries (what failed and why). Survives script crashes — it's just a file. Can be reviewed by humans between autonomous runs. Complements native `memory: project` (different audiences — progress.md is for humans and scripts, MEMORY.md is for the agent).
- **Cons**: Grows unbounded during long sprints — need to cap or rotate. Claude reads the entire file each story — context cost increases over time. Append-only means no correction of inaccurate entries. Format is convention-based — script must parse markdown. Duplication with verification-log.md (which records QA results).

### 7. SubagentStop Hook for Quality Gate

**Description**: Use Claude Code's native `SubagentStop` hook event in `settings.json` to add a quality gate when the ralph-worker sub-agent finishes. The hook runs a Python script that validates the worker's output before allowing completion.

```json
{
  "hooks": {
    "SubagentStop": [
      {
        "matcher": "ralph-worker",
        "hooks": [
          {
            "type": "command",
            "command": "python .claude/hooks/ralph_worker_gate.py"
          }
        ]
      }
    ]
  }
}
```

**Gate script** (`ralph_worker_gate.py`):

```python
# Reads sub-agent result, validates:
# 1. Did sub-agent produce verification-log.md entry?
# 2. Does entry show all R-PN-NN criteria PASS?
# 3. No production-grade violations in changed files?
# Exit 0 = allow completion, Exit 2 = block and send feedback
```

- **Pros**: Quality gate is enforced by the platform, not by prompt compliance. Worker can't exit without verification. Hook has access to filesystem state (verification-log.md, changed files). Exit code 2 sends feedback to worker, forcing it to fix issues. Separates quality enforcement from quality instructions (belt AND suspenders).
- **Cons**: SubagentStop hook may not have access to the sub-agent's structured output — only to filesystem state. If worker committed but didn't write verification-log.md, the hook blocks but damage may be done. Hook adds latency per story. Complex interaction between hook and sub-agent retry logic. Hook failures could deadlock the workflow.

### 8. Keep /ralph Skill as Thin Dispatcher Only

**Description**: Radically simplify the `/ralph` skill from its current 293-line orchestrator to a thin entry point (~50 lines) that delegates ALL work — either to the ralph-worker sub-agent (interactive mode) or explains how to use the external script (autonomous mode).

```markdown
---
name: ralph
description: V-Model orchestrator entry point.
disable-model-invocation: true
---

# Ralph — V-Model Orchestrator

## Mode Selection

Ask the user: "Interactive mode (supervised, single session) or Autonomous mode (unattended, infinite loop)?"

### Interactive Mode

1. Validate prd.json v2
2. Create/checkout feature branch
3. For each incomplete story:
   - Dispatch ralph-worker sub-agent (native agent with worktree isolation)
   - Display result, ask Continue/Stop
4. Offer PR creation

### Autonomous Mode

Display:
"Run the external orchestrator:
powershell .claude/scripts/ralph-runner.ps1

# or

bash .claude/scripts/ralph-runner.sh

This spawns fresh Claude instances per story with circuit breaker,
rate limiting, and structured exit detection. See progress in
.claude/docs/progress.md"
```

- **Pros**: Skill stays maintainable (~50 lines vs 293). All complexity moves to the right place: worker agent for implementation, script for orchestration. Clear separation of concerns. Easy to update — skill, worker, and script evolve independently. Users understand the two modes immediately.
- **Cons**: Interactive mode loses some current features (detailed step display, inline error recovery). Users need to know about the external script — it's not discoverable from `/ralph` alone. The skill becomes documentation rather than orchestration — may feel hollow.

## Evaluation Matrix

| Idea                                    | Impact    | Complexity | Risk   | Preserves Strengths | Recommended           |
| --------------------------------------- | --------- | ---------- | ------ | ------------------- | --------------------- |
| 1. External orchestrator script         | Very High | Medium     | Medium | Yes (via prompt)    | **YES (core)**        |
| 2. Native sub-agent (ralph-worker.md)   | High      | Low        | Low    | Yes (native)        | **YES (core)**        |
| 3. Dual-mode (interactive + autonomous) | High      | Medium     | Low    | Yes                 | **YES (pragmatic)**   |
| 4. Circuit breaker                      | High      | Low        | Low    | N/A (new)           | **YES (safety)**      |
| 5. Structured exit (--json-schema)      | Medium    | Low        | Low    | N/A (new)           | **YES (reliability)** |
| 6. Progress file                        | Medium    | Low        | Low    | N/A (new)           | **YES (context)**     |
| 7. SubagentStop hook                    | Medium    | Medium     | Medium | Yes (enforcement)   | **MAYBE (v3.1)**      |
| 8. Thin skill dispatcher                | Low       | Low        | Low    | Yes                 | **YES (cleanup)**     |

## Recommendation

**Implement Ideas 1 + 2 + 3 + 4 + 5 + 6 + 8. Defer Idea 7 to v3.1.**

### Architecture: Ralph v3

```
┌─────────────────────────────────────────────────┐
│ AUTONOMOUS MODE (ralph-runner.ps1 / .sh)        │
│                                                 │
│ External script — runs outside Claude           │
│ ├── Reads prd.json, finds next incomplete story │
│ ├── Constructs prompt with story + instructions │
│ ├── claude -p --json-schema → structured result │
│ ├── Circuit breaker (3-strike, cooldown)        │
│ ├── Rate limit tracking                         │
│ ├── Updates prd.json (passed: true)             │
│ ├── Appends to progress.md                      │
│ ├── Git commit per story                        │
│ └── Loop until all passed or circuit opens      │
│                                                 │
│ Feature branch: ralph/[plan-name]               │
│ PR creation: gh pr create at end                │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│ INTERACTIVE MODE (/ralph skill)                 │
│                                                 │
│ In-session skill — user present                 │
│ ├── Validates prd.json v2                       │
│ ├── Creates/checks out feature branch           │
│ ├── Per story: dispatches ralph-worker agent    │
│ ├── Displays result, asks Continue/Stop         │
│ ├── User can Retry/Skip/Stop on failures        │
│ └── Offers PR creation at end                   │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│ SHARED: ralph-worker.md (native sub-agent)      │
│                                                 │
│ YAML frontmatter:                               │
│   isolation: worktree                           │
│   maxTurns: 100                                 │
│   memory: project                               │
│   permissionMode: acceptEdits                   │
│   skills: [verify]                              │
│                                                 │
│ System prompt:                                  │
│   Builder rules + TDD mandate                   │
│   16-step QA pipeline                           │
│   10 production-grade standards                 │
│   R-PN-NN traceability enforcement              │
│   Selective staging rules                       │
│   Structured JSON result                        │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│ SHARED STATE (filesystem)                       │
│                                                 │
│ .claude/prd.json          — story status        │
│ .claude/docs/PLAN.md      — implementation plan │
│ .claude/docs/progress.md  — append-only log     │
│ .claude/docs/verification-log.md — QA results   │
│ .claude/agent-memory/ralph-worker/ — agent mem  │
└─────────────────────────────────────────────────┘
```

### Why This Architecture

**The external script solves the fundamental problem**: infinite context per story, unattended overnight operation, deterministic circuit breaker. No amount of in-session optimization can match spawning a fresh 200K context window per story.

**The native sub-agent preserves our strengths**: worktree isolation, maxTurns safety, persistent memory, preloaded skills, scoped hooks — all via platform features instead of manual workarounds. The 16-step QA pipeline and R-PN-NN traceability live in the worker's system prompt.

**Dual mode is pragmatic**: interactive mode for complex/risky stories where human judgment matters, autonomous mode for well-defined work. Same worker, same quality gates, different orchestration.

**The thin skill dispatcher is honest**: `/ralph` becomes a routing decision, not a 293-line orchestrator. The real orchestration lives in the script (autonomous) or the worker agent (interactive).

### Implementation Priority

| Phase | Deliverable                      | Files                                                                             |
| ----- | -------------------------------- | --------------------------------------------------------------------------------- |
| 1     | ralph-worker.md native sub-agent | `.claude/agents/ralph-worker.md` (NEW)                                            |
| 2     | External orchestrator script     | `.claude/scripts/ralph-runner.ps1` (NEW), `.claude/scripts/ralph-runner.sh` (NEW) |
| 3     | Progress file convention         | `.claude/docs/progress.md` (NEW, gitignored)                                      |
| 4     | Simplified /ralph skill          | `.claude/skills/ralph/SKILL.md` (REWRITE — 293 → ~80 lines)                       |
| 5     | Circuit breaker in script        | Integrated into ralph-runner scripts                                              |
| 6     | Update docs                      | `CLAUDE.md`, `ARCHITECTURE.md`, `update-ade.ps1`                                  |

### What Changes vs Ralph v2

| Aspect               | Ralph v2 (current)           | Ralph v3 (proposed)                                      |
| -------------------- | ---------------------------- | -------------------------------------------------------- |
| Loop driver          | In-session skill (293 lines) | External script + thin skill (~80 lines)                 |
| Context per story    | Task tool sub-agent          | Native sub-agent OR fresh `claude -p` process            |
| Worktree isolation   | Manual bash in prompt        | `isolation: worktree` frontmatter                        |
| Turn limit           | None                         | `maxTurns: 100`                                          |
| Persistent memory    | None                         | `memory: project` → `.claude/agent-memory/ralph-worker/` |
| Exit detection       | String match on result       | `--json-schema` structured output                        |
| Circuit breaker      | 3-attempt retry only         | 3-strike + cooldown + error hashing                      |
| Rate limits          | None                         | Script-level tracking                                    |
| Unattended operation | Impossible                   | Primary mode                                             |
| Interactive option   | Only mode                    | Still available via `/ralph`                             |
| QA pipeline          | 16-step (preserved)          | 16-step (preserved, in worker prompt)                    |
| Traceability         | R-PN-NN (preserved)          | R-PN-NN (preserved, in worker prompt)                    |
| Progress tracking    | ralph-state.json (ephemeral) | progress.md (persistent) + agent memory                  |
| Skill preloading     | None                         | `skills: [verify]` in frontmatter                        |

### What We Preserve (Non-Negotiable)

1. 16-step QA pipeline with acceptance tests and production-grade scan
2. R-PN-NN traceability chain (PLAN → prd.json → tests → verification)
3. prd.json v2 structured schema with typed criteria
4. Feature branch workflow (ralph/[name], selective staging, PR creation)
5. Production-grade code standards (10 rules, zero tolerance)
6. /audit skill for end-to-end validation
7. Smart plan detection (STEP 5A)
8. Escalation thresholds (2 compile errors, 3 test failures)

### What's New (Additive)

1. Unattended overnight operation via external script
2. Infinite context via fresh processes per story
3. Circuit breaker with error hashing and cooldown
4. Native worktree isolation via frontmatter
5. Per-story turn limits (maxTurns: 100)
6. Persistent agent memory across sessions
7. Structured JSON exit detection
8. Progress file for cross-story context
9. Rate limit awareness in script
10. Skill preloading for worker context

### Risk Assessment

| Risk                                                | Mitigation                                                                                     |
| --------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `--dangerously-skip-permissions` in autonomous mode | pre_bash_guard.py hook still fires; only destructive commands blocked                          |
| Worker prompt too large (builder + qa + standards)  | Preload via `skills` field; keep prompt focused on story-specific instructions                 |
| progress.md grows unbounded                         | Cap at 50 entries, rotate older entries to progress-archive.md                                 |
| Platform feature changes break frontmatter          | Pin to documented fields; test on Claude Code updates                                          |
| Autonomous mode commits bad code                    | Same QA pipeline as interactive; circuit breaker catches loops; /audit for post-run validation |
| Script not cross-platform                           | PowerShell for Windows, bash for Linux/Mac — both maintained                                   |

## Sources

### Project Docs Read

- `.claude/skills/ralph/SKILL.md` (293 lines) — current v2 orchestrator
- `.claude/agents/builder.md`, `.claude/agents/qa.md` — agent definitions
- `.claude/docs/knowledge/conventions.md` — R-PN-NN traceability conventions
- `.claude/prd.json` — v2 schema with 6 stories (all passed)
- `.claude/docs/ARCHITECTURE.md` — system architecture
- `.claude/docs/brainstorms/2026-02-27-ralph-vmodel-upgrade.md` — v2 brainstorm (13 ideas)
- `PROJECT_BRIEF.md` — project context

### Online Research

- [snarktank/ralph](https://github.com/snarktank/ralph) — original external bash loop pattern
- [frankbria/ralph-claude-code](https://github.com/frankbria/ralph-claude-code) — dual-gate exit, circuit breaker, session continuity
- [Claude Code sub-agents docs](https://code.claude.com/docs/en/sub-agents) — native frontmatter fields (isolation, maxTurns, memory, hooks, skills, permissionMode)
- [Claude Code headless/Agent SDK docs](https://code.claude.com/docs/en/headless) — `claude -p`, `--json-schema`, `--output-format json`, `--allowedTools`
- [Claude Code hooks docs](https://code.claude.com/docs/en/hooks) — SubagentStart, SubagentStop, hook lifecycle
- [Ralph Wiggum bash loop guide](https://pasqualepillitteri.it/en/news/192/ralph-wiggum-claude-code-loop-bash-coding-agent) — concrete script implementation with `claude -p`
- [Claude Code best practices](https://www.anthropic.com/engineering/claude-code-best-practices) — Anthropic's official patterns
- [Awesome Claude — Ralph Wiggum](https://awesomeclaude.ai/ralph-wiggum) — technique overview
