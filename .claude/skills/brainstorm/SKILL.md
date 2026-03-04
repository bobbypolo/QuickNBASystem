---
name: brainstorm
description: Brainstorm ideas for a problem using project context.
---

**Step 1 — Build knowledge.** Read all available project context:

- `PROJECT_BRIEF.md`
- `.claude/docs/ARCHITECTURE.md`
- `.claude/docs/PLAN.md`
- `.claude/docs/knowledge/lessons.md`
- `.claude/docs/decisions/` (all ADRs)
- `.claude/docs/HANDOFF.md` (if exists)
- Any additional docs the user points to, or discover them via Glob (`docs/**`, `*.md`)

If the project docs leave gaps relevant to the problem, conduct online research (WebSearch, Context7) to fill them.

**Step 2 — Brainstorm.** Using everything gathered, generate a list of distinct ideas that address the user's problem. Each idea should be grounded in the project reality, not generic. Aim for breadth — include obvious approaches and non-obvious ones.

**Step 3 — Evaluate.** For each idea, write honest pros and cons. Reference specific project constraints, architecture decisions, or research findings when they apply.

**Step 4 — Recommend.** Identify the best single idea or combination of ideas. Explain why, referencing the pros/cons. If it's close between options, say so and explain what would tip the decision.

**Step 5 — Save.** Write the output to `.claude/docs/brainstorms/YYYY-MM-DD-topic.md` using this format:

```
# Brainstorm: [Topic]
**Date**: [YYYY-MM-DD]
**Problem**: [One-sentence restatement]

## Ideas

### 1. [Idea name]
[Description]
- **Pros**: ...
- **Cons**: ...

### 2. [Idea name]
...

## Recommendation
[Best idea or combination, with reasoning]

## Sources
[Project docs read, research conducted, links found]
```

**Step 6 — Build Strategy.** After saving the brainstorm, generate a Build Strategy section and append it to the brainstorm output file.

Append the following 5 sections to the brainstorm output file:

```
## Build Strategy

### Module Dependencies
[Identify the key modules/components required and their dependency relationships.
Draw a dependency graph showing which modules depend on which.]

### Build Order
[Recommend a build order based on the dependency graph.
Specify which modules can be built in parallel vs. sequentially.
Flag any critical-path items that block downstream work.]

### Testing Pyramid
[Define the testing strategy across three levels:
- **Unit tests**: Pure logic, data transformations, utility functions
- **Integration tests**: Module interactions, API contracts, data flow
- **E2E tests**: Full user workflows, system-level behavior
Estimate the ratio (e.g., 70/20/10) based on the solution architecture.]

### Risk Mitigation Mapping
[Map each identified risk to a specific mitigation strategy:
- Risk: [description] -> Mitigation: [strategy]
Reference the Evaluation section (pros/cons) from Step 3.]

### Recommended Build Mode
[Recommend the appropriate build mode for this solution:
- **Ralph Mode**: For well-defined features with clear acceptance criteria
- **Manual Mode**: For exploratory work, debugging, or tightly-coupled changes
- **Hybrid**: Ralph for foundation phases, Manual for integration/E2E phases
Justify the recommendation based on solution complexity and risk profile.]
```
