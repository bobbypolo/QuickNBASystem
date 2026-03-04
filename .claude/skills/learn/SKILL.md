---
name: learn
description: Capture a solved issue as a durable lesson.
agent: librarian
context: fork
---

Summarize what failed, root cause, fix, and "how to detect early next time".
Append to `.claude/docs/knowledge/lessons.md` with a date header and tags.

## Lesson Template

Use this structured format when writing the lesson:

```markdown
### [Title]

- **Date**: YYYY-MM-DD
- **Category**: bug | architecture | tooling | process | performance
- **Scope**: [file or area affected]
- **Root Cause**: [what actually caused it]
- **What Happened**: [1-2 sentences]
- **Resolution**: [what fixed it]
- **Prevention**: [how to avoid next time]
```

## Process

1. Ask user what happened (if not already clear from context)
2. Identify root cause — dig past symptoms to the underlying issue
3. Write the lesson using the template above
4. Append to `.claude/docs/knowledge/lessons.md`
5. If the lesson reveals a pattern, check if an existing lesson covers it — update rather than duplicate
