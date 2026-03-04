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

# Production-Grade Code Standards

Enforced by hooks (`post_write_prod_scan.py`, `_lib.py` PROD_VIOLATION_PATTERNS), QA Step 12, and `/audit` Section 7. **NO EXCEPTIONS** — every violation must be fixed before a phase can pass.

1. **Security**: No hardcoded secrets, no injection vectors (SQL, shell, HTML), no unsafe subprocess calls -- **Automated (regex)**
2. **Code hygiene**: No debug prints, unused imports/variables, bare excepts, or TODO/FIXME markers; all public APIs have type hints -- **Automated (lint/type-check)**
3. **Robustness**: Proper error handling at system boundaries, input validation at system boundaries (never trust external data), resource cleanup (close files, connections, cursors) via context managers/try-finally -- **Review guidance**

Hook enforcement covers 12 specific regex patterns (see `_lib.py` PROD_VIOLATION_PATTERNS). Rules 1-2 are fully automated; rule 3 requires review judgment.

# Data Classification

| Level  | Category                                 | Handling                              |
| ------ | ---------------------------------------- | ------------------------------------- |
| **P0** | Public (UI, CRUD, boilerplate)           | Normal                                |
| **P1** | Internal (business logic)                | Normal                                |
| **P2** | Competitive IP (algorithms, scrapers)    | Placeholders in chat, execute locally |
| **P3** | Resilience (security, traffic analysis)  | Placeholders in chat, execute locally |
| **P4** | Unauthorized (destructive, out-of-scope) | **REFUSED**                           |

For P2/P3: use `<TARGET>`, `<API_KEY>` placeholders in chat. Generate code with `os.getenv()`. User runs sensitive code locally.

# Precedence Rules

When rules conflict, apply these precedence rules in order:

1. **Production safety wins over all other rules.** If a production-grade code standard (e.g., no hardcoded secrets) conflicts with speed, convenience, or any other consideration, production safety always takes priority.
2. **Ralph workers ignore builder escalation thresholds.** Builder.md defines escalation at 2 compile errors or 3 test failures — these apply only in Manual Mode. Ralph workers persist until all acceptance criteria pass or they exhaust their turns.
3. **Blast radius check is WARN, not FAIL.** QA Step 10 (blast radius) flags files changed outside the plan's assessment as a warning. It does not block phase completion. All other QA steps that report FAIL do block.
4. **Mock policy: no self-mocking the function under test.** A test must never mock the function or class it claims to verify. This applies across all modes (Ralph, Manual, /verify). Self-mocking tests are always a FAIL regardless of other considerations.
5. **Workflow state file is canonical.** The file `.claude/.workflow-state.json` is the single source of truth for all workflow state (sprint progress, verification flags, violation tracking). Re-read it at every step of the Ralph loop. Do not rely on in-memory state — context compaction may have cleared it.
