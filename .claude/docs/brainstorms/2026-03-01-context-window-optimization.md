# Brainstorm: Context Window Optimization

**Date**: 2026-03-01
**Problem**: The workflow consumes ~65K tokens (~33% of 200K context window) before the user types anything. Need to reduce pre-loaded context while preserving functionality.

## Corrected Analysis

Initial analysis suggested skills (SKILL.md files) were consuming ~19K tokens. **This was wrong.** Claude Code only loads frontmatter `description` fields into the tool list (~400 tokens for all 11 skills). The full SKILL.md body loads on-demand when invoked. Skills are already properly lazy-loaded.

**Actual context budget (corrected):**

| Component                             | Tokens        | Notes                                        |
| ------------------------------------- | ------------- | -------------------------------------------- |
| Project CLAUDE.md                     | ~8,882        | User manual embedded as machine instructions |
| MCP tool descriptions                 | ~36,081       | 128 tools from 9 servers, always loaded      |
| Skill descriptions (frontmatter only) | ~400          | Already lazy — NOT a problem                 |
| Global/user CLAUDE.md + memory        | ~636          | Minimal                                      |
| Settings, workflow.json, rules        | ~720          | Minimal                                      |
| Claude Code system prompt             | ~5,000 (est.) | Fixed overhead                               |
| **TOTAL**                             | **~51,700**   | **~26% of 200K**                             |

**Real optimization targets: CLAUDE.md (~8.9K) and MCP tools (~36K).**

## Ideas

### 1. Separate CLAUDE.md into machine instructions + user README

Move all user-facing documentation (tutorials, reference tables, step-by-step guides) into a `README.md` that the user reads. Keep only rules Claude must follow in CLAUDE.md.

**Current CLAUDE.md (562 lines) content classification:**

| Section                    | Lines   | Category            | Keep in CLAUDE.md?              |
| -------------------------- | ------- | ------------------- | ------------------------------- |
| Overview                   | 1-5     | User docs           | No → README                     |
| Quick Start                | 7-12    | Machine instruction | Yes (condensed)                 |
| Commands table             | 14-28   | User reference      | No → README                     |
| How This Workflow Works    | 30-54   | User tutorial       | No → README                     |
| Step-by-Step: Ralph        | 56-127  | User tutorial       | No → README (in ralph/SKILL.md) |
| Step-by-Step: Manual       | 129-172 | User tutorial       | No → README                     |
| Step-by-Step: Research     | 174-206 | User tutorial       | No → README                     |
| Slash Command Reference    | 208-254 | User reference      | No → README                     |
| Role Commands              | 256-268 | Machine instruction | Yes (condensed)                 |
| Hooks table                | 270-306 | Mixed               | Yes (condensed)                 |
| Quality Utilities          | 286-293 | User reference      | No → README                     |
| QA Pipeline 12 Steps       | 308-331 | Redundant           | No (in qa.md + ralph-worker.md) |
| Production Code Standards  | 332-351 | Machine instruction | Yes                             |
| Ralph v4 Detailed Behavior | 352-428 | Redundant           | No (in ralph/SKILL.md)          |
| Data Classification        | 430-442 | Machine instruction | Yes                             |
| Non-Negotiables            | 444-450 | Machine instruction | Yes                             |
| Precedence Rules           | 452-461 | Machine instruction | Yes                             |
| Git Workflow               | 462-482 | Machine instruction | Yes (condensed)                 |
| When Stuck                 | 484-491 | Machine instruction | Yes                             |
| Recovery                   | 493-498 | User reference      | No → README                     |
| Repo Structure             | 499-536 | User reference      | No → README                     |
| Deployment                 | 538-552 | User reference      | No → README                     |
| MCP Tools                  | 554-557 | Machine instruction | Yes (updated)                   |
| Environment                | 559-562 | Machine instruction | Yes                             |

**Estimated trimmed CLAUDE.md: ~130-150 lines (~3,500 chars → ~875 tokens)**

- **Pros**: Saves ~8,000 tokens per conversation. Cleaner separation of concerns. README is actually useful for humans (they can read it in a browser/editor). CLAUDE.md becomes focused and auditable.
- **Cons**: Two files to maintain instead of one. Must ensure nothing Claude needs is accidentally moved to README. Users must learn that CLAUDE.md ≠ documentation.

### 2. Per-project MCP configuration via .mcp.json

Claude Code supports project-scoped `.mcp.json` files (discovered via research). Currently all 9 MCP servers are globally configured, meaning every project loads all 128 tools (~36K tokens).

**Proposed split:**

| Server      | Tokens  | Scope         | Reason                            |
| ----------- | ------- | ------------- | --------------------------------- |
| github      | ~11,094 | Global (user) | Used across all projects          |
| context7    | ~1,300  | Global (user) | General docs lookup               |
| exa         | ~800    | Global (user) | General web search                |
| playwright  | ~8,514  | Per-project   | Only for browser testing projects |
| openalex    | ~7,998  | Per-project   | Only for research projects        |
| crossref    | ~800    | Per-project   | Only for research projects        |
| arxiv       | ~1,000  | Per-project   | Only for research projects        |
| firecrawl   | ~3,096  | Per-project   | Overlaps with playwright          |
| browserbase | ~2,322  | Per-project   | Overlaps with playwright          |
| trello      | ~1,200  | Per-project   | Only for Trello projects          |

For this ADE project specifically: keep github, context7, exa globally. Add research servers (openalex, arxiv, crossref) to project `.mcp.json`. Remove browser servers (playwright, browserbase, firecrawl) unless actively needed.

**This project's savings: ~20K-25K tokens** (remove browser + research servers from global, add only research to project).

- **Pros**: Massive token savings. Each project only loads what it needs. Clean separation. Uses native Claude Code feature (no hacks).
- **Cons**: Must run `claude mcp add --scope project` for each project. More setup friction for new projects. Deployment scripts need updating. Users must understand the split.

### 3. Use `disable-model-invocation: true` for admin-only skills

Skills with `disable-model-invocation: true` don't appear in Claude's context at all — zero token cost until manually invoked. Research phase sub-skills already have this implicitly (they're commands, not skills). But some skills could benefit:

**Candidates for `disable-model-invocation: true`:**

| Skill        | Current        | Rationale                            |
| ------------ | -------------- | ------------------------------------ |
| build-system | auto           | Rarely used, always manually invoked |
| audit        | auto           | Always manually invoked              |
| decision     | already has it | N/A                                  |
| handoff      | already has it | N/A                                  |
| ralph        | already has it | N/A                                  |

**Token savings: ~100-150 tokens** (just removing 2-3 short descriptions from the skill list).

- **Pros**: Slightly cleaner skill list. Zero cost.
- **Cons**: Negligible savings. Not worth the effort alone.

### 4. Optimize CLAUDE.md verbiage (within kept sections)

Even for sections that stay, the language can be tightened. Current CLAUDE.md uses narrative explanations where bullet points would suffice:

**Example — Current (Production Standards, 17 lines):**

```
1. No TODO, HACK, FIXME, XXX comments in committed code -- **Automated (regex)**
2. No hardcoded values that should be configuration (URLs, ports, credentials, magic numbers) -- **Automated (regex)**
...
```

**Optimized (same info, terser):**

```
Automated: no TODO/HACK/FIXME/XXX | no hardcoded URLs/ports/creds/magic numbers | no bare except | no unused imports | no debug prints | type hints on public API | no string concat for SQL/HTML/shell | no subprocess shell=True | no os.popen/exec | no f-strings in SQL execute | no except Exception without re-raise | no hardcoded oauth/jwt/credential values
Review: error handling at boundaries | input validation at boundaries | resource cleanup (context managers)
```

- **Pros**: Further compresses kept sections by ~30%.
- **Cons**: Less readable for humans auditing CLAUDE.md. But that's what README is for.

## Recommendation

**Combine Ideas 1 + 2 + 4** (skip 3 — negligible value):

1. **Create `WORKFLOW.md` (user documentation)** — move all tutorials, reference tables, step-by-step guides. This becomes the human-readable manual.
2. **Trim `CLAUDE.md` to ~130 lines** — machine instructions only: rules, standards, precedence, data classification, git workflow, quick-start pointers.
3. **Restructure MCP servers** — move research/browser servers to per-project `.mcp.json`. Keep only universal servers global.
4. **Tighten verbiage** — compress kept sections to minimum viable instructions.

**Expected savings:**

- CLAUDE.md: ~8,882 → ~875 tokens (saves ~8,000)
- MCP tools: ~36,081 → ~13,200 tokens (saves ~22,800, project-dependent)
- **Total: ~30,800 token savings → pre-loaded context drops from ~52K to ~21K**

This cuts pre-loaded overhead roughly in half, leaving ~90% of the context window for actual work.

## Sources

- Claude Code documentation on MCP scopes (https://code.claude.com/docs/en/mcp.md)
- Claude Code documentation on skills (https://code.claude.com/docs/en/skills.md)
- Measured file sizes from project codebase
- Previous brainstorm: `2026-02-05-lean-workflow-remediation.md`

## Build Strategy

### Module Dependencies

```
README.md (new) ← content extracted from CLAUDE.md
    ↑
CLAUDE.md (trimmed) ← standalone, no new dependencies
    ↑
.mcp.json (new) ← project-level MCP config
    ↑
Deployment scripts ← must know about .mcp.json for new-ade.ps1
    ↑
~/CLAUDE.md ← update MCP reference
```

### Build Order

1. **CLAUDE.md trim + README creation** (parallel-safe, no code changes)
2. **MCP restructure** (.mcp.json creation + global server cleanup)
3. **Deployment script update** (new-ade.ps1 copies .mcp.json template)
4. **Documentation updates** (ARCHITECTURE.md, HANDOFF.md, ~/CLAUDE.md)

Steps 1 and 2 are independent. Steps 3-4 depend on both.

### Testing Pyramid

- **Unit tests**: N/A (no code changes — only markdown and JSON config)
- **Integration tests**: N/A
- **Validation**: Manual verification that CLAUDE.md still contains all required machine instructions. Diff comparison to ensure nothing critical was dropped.
- **Ratio**: 0/0/100 (all manual validation for a docs-only change)

### Risk Mitigation Mapping

- Risk: Critical machine instruction accidentally moved to README → Mitigation: Systematic section-by-section classification (table in Idea 1). Review diff before committing.
- Risk: MCP servers break after restructure → Mitigation: Test `claude mcp list` and verify tool availability after changes. Keep backup of current config.
- Risk: Deployment scripts don't copy .mcp.json → Mitigation: Test new-ade.ps1 on a scratch directory after update.
- Risk: Trello credentials exposed in .mcp.json → Mitigation: Add .mcp.json to .gitignore, use env vars instead.

### Recommended Build Mode

**Manual Mode** — This is a documentation restructuring task with no code changes. Ralph/TDD is overkill. Direct editing with manual verification is appropriate. Each change is simple, reversible, and independently verifiable.
