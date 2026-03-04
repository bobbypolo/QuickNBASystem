---
paths:
  - "**/*.py"
  - "**/*.ts"
  - "**/*.tsx"
  - "**/*.js"
  - "**/*.jsx"
  - "**/*.go"
  - "**/*.rs"
---

# Code Quality Rules (auto-loaded when code files are touched)

- Check `.claude/workflow.json` for configured test/lint commands. Run them.
- If `needs_verify` is set in `.claude/.workflow-state.json`, you MUST run tests before committing or finishing.
- After modifying code: run tests → fix failures → then move on. Never leave failing tests.
- Before committing: verify no debug prints, console.logs, commented-out code, or TODO hacks.
- If no test command is configured in workflow.json, run `/verify` to manually clear the gate.
