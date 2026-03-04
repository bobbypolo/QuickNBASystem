---
name: decision
description: Record an architecture decision (ADR).
agent: librarian
context: fork
disable-model-invocation: true
---

Create an Architecture Decision Record:

## Process

1. List existing ADRs in `.claude/docs/decisions/` to determine the next number
2. Gather from user (ask if not provided):
   - Decision title (what are we deciding?)
   - Context (why do we need to decide this?)
   - Options considered (at least 2)
   - The chosen option and reasoning
3. Create the ADR file using `.claude/docs/decisions/000-template.md` as the format
4. Update `.claude/docs/decisions/README.md` index table

## File Naming

- Format: `NNN-kebab-case-title.md`
- Example: `001-use-postgresql-for-persistence.md`

## After Creation

- If this decision affects `.claude/docs/ARCHITECTURE.md`, note that it needs updating
- Inform user of the file created and any follow-up actions needed
