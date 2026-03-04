# Planning Anti-Patterns

> Read this before writing any plan. Each pattern below has caused real plan failures
> requiring multiple revision passes to fix.

## AP-1: Phantom File Syndrome

**Pattern**: Plan references files the Architect never opened during Discovery.
**Symptom**: Builder opens the file and discovers different structure, function names, or patterns than assumed.
**Fix**: Read every file in the Changes table during Discovery. Record findings in System Context.

## AP-2: Interface by Imagination

**Pattern**: Plan says "add function X" without specifying signature, types, errors, callers.
**Symptom**: Phase 2 expects a different interface than Phase 1 created. Integration failures.
**Fix**: Every new/modified function needs an Interface Contracts row. Cross-phase consistency checked in Pre-Flight.

## AP-3: Mock Everything

**Pattern**: Testing Strategy says "unit tests pass" without specifying Real vs Mock. Builder mocks all dependencies.
**Symptom**: Tests pass but feature is broken in production. Integration bugs survive testing.
**Fix**: Testing Strategy must specify Real vs Mock per test with justification. Use this decision table:

| Scenario                         | Unit Tests                    | Integration Tests           |
| -------------------------------- | ----------------------------- | --------------------------- |
| Pure functions (no side effects) | **REAL** — always             | N/A                         |
| Internal module interactions     | **REAL** — always             | **REAL** — always           |
| Business logic / data transforms | **REAL** — always             | **REAL** — always           |
| Database operations              | **MOCK** (in-memory fixtures) | **REAL** (test DB)          |
| External API calls               | **MOCK** (recorded responses) | **REAL** (contract tests)   |
| File system operations           | **MOCK** (temp paths)         | **REAL** (temp directories) |
| Authentication/authorization     | **REAL** (test credentials)   | **REAL** (test credentials) |
| Network/HTTP calls               | **MOCK** (responses)          | **REAL** (contract tests)   |

## AP-4: Happy Path Only

**Pattern**: Plan specifies success behavior but not: DB down, malformed input, dependency errors, timeouts, missing files, permission denied.
**Symptom**: Builder implements happy path only. Tests only test happy path. Production crashes on first error.
**Fix**: Data Flow section must include error paths. "What happens when X fails?" answered for every step.

## AP-5: Orphan Phase

**Pattern**: Phase 2 depends on Phase 1's output but no contract specified between them.
**Symptom**: Phase 1 outputs format A, Phase 2 expects format B. Phase 1 passes verification, Phase 2 fails.
**Fix**: Interface Contracts "Called By" and "Calls" columns link components across phases. Pre-Flight checks consistency.

## AP-6: Hollow Done Criteria

**Pattern**: Done When says "code works" or "tests pass" without specifying WHICH tests or WHAT "works" means.
**Symptom**: Builder and QA disagree on whether phase is done. QA can't verify a vague criterion.
**Fix**: Every criterion has a requirement ID and specific observable outcome. Bad: "API works." Good: "R-P1-03: GET /trades?min_vol=100 returns 200 with JSON array where all volume >= 100."

## AP-7: Architecture Amnesia

**Pattern**: ARCHITECTURE.md is empty/outdated. Architect plans without knowing what components exist.
**Symptom**: Plan builds something that already exists. Or breaks an integration it didn't know about.
**Fix**: If ARCHITECTURE.md is empty, populate from Discovery with [AUTO-DETECTED] tags. If it exists, validate against current code and flag drift.
