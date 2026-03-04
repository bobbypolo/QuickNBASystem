# 001 - Exa MCP Server Separation from Global Config

**Date**: 2026-03-02
**Status**: Accepted
**Deciders**: Project owner during research/build ADE separation sprint

## Context

The Claude Workflow project originally ran as a single ADE (Autonomous Development Environment) that handled both coding workflows and research workflows. All MCP servers -- including research-focused ones like Exa, arXiv, OpenAlex, Crossref, Playwright, Firecrawl, and Browserbase -- were configured globally in `~/.claude.json`, meaning they loaded for every project regardless of whether research was needed.

During the context bloat reduction initiative (2026-03-02), analysis showed that the 9 global MCP servers contributed approximately 1,600 tokens of deferred tool names to the ToolSearch description in every session. Six of these servers (arXiv, Crossref, OpenAlex, Playwright, Firecrawl, Browserbase) were used exclusively by the research pipeline, and Exa was used primarily for research with only marginal utility for coding tasks.

Simultaneously, the research pipeline was extracted into a separate repository (`F:\Claude-Research-Workflow`) as a standalone ADE, removing all research commands, phases, and documentation from the Build ADE.

A prior plan (R-P1-06 in the research-cleanup prd.json) had required `~/.claude.json` to contain 3 MCP servers: github, context7, and exa. The story was marked as passed, but the actual implementation moved exa to the research project's `.mcp.json` instead of keeping it global. This created a traceability gap -- the decision was correct but undocumented.

## Options Considered

### Option 1: Keep Exa Global

Keep exa in `~/.claude.json` alongside github and context7, as the original plan specified.

**Pros:**

- Exa web search is occasionally useful during coding (looking up library docs, API references)
- No change needed to existing configuration

**Cons:**

- Adds ~100 tokens of tool names to every session that does not need web search
- Exa's primary use case (research discovery) no longer exists in the Build ADE
- Claude Code's built-in WebSearch tool covers most ad-hoc web lookup needs

### Option 2: Move Exa to Research Project Only

Move exa to `F:\Claude-Research-Workflow\.mcp.json` where it is actually needed. Keep only github and context7 as global servers.

**Pros:**

- Reduces global MCP overhead for all non-research projects
- Exa loads only when working in the research project (where it is heavily used)
- Cleaner separation: global servers are coding essentials only
- Consistent with the principle of moving research tools to the research ADE

**Cons:**

- If a coding project occasionally needs web search, exa is not available
- Mitigated by Claude Code's built-in WebSearch and WebFetch tools

## Decision

We decided on **Option 2** because the research/build ADE separation established a clear boundary: research tools belong in the research project. Exa's primary value is in research discovery workflows (finding sources, extracting content, code context search), which now live exclusively in the Research ADE. The Build ADE's occasional web lookup needs are adequately served by Claude Code's built-in WebSearch and WebFetch tools.

## Consequences

### Positive

- Global MCP server count reduced from 9 to 2 (github, context7), saving ~900 tokens per session across all projects
- Clean separation of concerns: coding tools are global, research tools are per-project
- Closes the R-P1-06 traceability gap -- the exa removal decision is now formally documented

### Negative

- Coding projects cannot use exa for web search without adding it to their `.mcp.json`
- If a future coding project needs heavy web search, exa must be added per-project

### Neutral

- The `.mcp.json.example` template documents how to add exa (and other servers) per-project if needed
- Trello was added to the Build ADE's `.mcp.json` (disabled by default) as an example of per-project server configuration

## Follow-up Actions

- [x] Move exa from `~/.claude.json` to research project `.mcp.json`
- [x] Update CLAUDE.md to document global vs per-project server split
- [x] Create this ADR to close R-P1-06 traceability gap
