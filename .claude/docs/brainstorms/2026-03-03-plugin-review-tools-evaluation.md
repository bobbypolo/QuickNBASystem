# Brainstorm: Plugin Review Tools — Keep, Merge, or Discard?

**Date**: 2026-03-03
**Problem**: Two Anthropic official plugins (`code-review` and `pr-review-toolkit`) exist in the Claude Code plugin marketplace but are not integrated into our ADE workflow. Should they be adopted, merged into existing tools, or discarded?

## Context: What We Have vs What the Plugins Offer

### Our Existing Review Coverage

| Workflow Stage       | Tool                  | What It Does                                                                                                                    |
| -------------------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Pre-merge (in Ralph) | STEP 6 Diff Review    | 5 structured yes/no questions: plan conformance, scope creep, test presence, debug artifacts, interface contracts               |
| Pre-merge (in Ralph) | QA Receipt Validation | 12-step automated pipeline: lint, type check, tests, security, coverage, mock audit, plan conformance, production scan          |
| Pre-merge (in Ralph) | Cumulative Regression | Full test suite after merge to catch cross-story regressions                                                                    |
| Post-build           | `/audit`              | 8-section integrity audit: plan, prd alignment, traceability, verification logs, architecture, hooks, git hygiene, test quality |
| Post-build           | `/verify`             | Phase-level verification with 12-step QA + criteria checking                                                                    |
| On-demand            | `/simplify`           | Code review for reuse, quality, efficiency                                                                                      |

### Plugin 1: `code-review` (Boris Cherny @ Anthropic)

- **Command**: `/code-review`
- **Status**: On blocklist (added 2026-02-11 as test)
- **What it does**: Automated PR review. 5 parallel agents (2x CLAUDE.md compliance, 1x bug scan, 1x git history, 1x code comments). Confidence scoring 0-100, threshold 80. Posts review comment on GitHub PR.
- **Key feature**: Posts findings as GitHub PR comment (visible to team)

### Plugin 2: `pr-review-toolkit` (Daisy @ Anthropic)

- **Command**: `/pr-review-toolkit:review-pr`
- **Status**: Installed, not on blocklist
- **What it does**: 6 specialized agents (comment-analyzer, pr-test-analyzer, silent-failure-hunter, type-design-analyzer, code-reviewer, code-simplifier). Runs sequentially or in parallel.
- **Key feature**: Deep specialized analysis per aspect; local report (not posted to GitHub)

## Ideas

### 1. Discard Both — Our Pipeline Is Sufficient

Keep our existing tools as-is. The 12-step QA pipeline + diff review + audit already covers what these plugins do, and they're tuned to our specific workflow with R-marker traceability, plan conformance, and verification receipts.

- **Pros**:
  - Zero integration work
  - No context window cost from plugin prompts
  - Our tools are tuned for our V-Model traceability chain (R-markers, plan conformance, verification logs)
  - No dependency on third-party plugin updates
  - `/simplify` already covers the code-simplifier use case
  - Our test quality scanner (mock audit, assertion checks) is more rigorous than pr-test-analyzer for our specific patterns
- **Cons**:
  - We lose the GitHub PR comment capability (code-review posts directly to PR)
  - We lose deep error-handling analysis (silent-failure-hunter is specialized)
  - We lose type design scoring (type-design-analyzer)
  - No independent "fresh eyes" review — our tools are all self-review

### 2. Adopt `code-review` Only — GitHub PR Comment Gate

Add `/code-review` as a post-Ralph, pre-merge step. Its unique value is posting confidence-scored findings as GitHub PR comments, which our workflow doesn't do.

- **Pros**:
  - Only plugin that posts to GitHub (visible review trail)
  - Confidence-based scoring (80+ threshold) reduces noise
  - Git blame/history analysis catches context our pipeline misses
  - Lightweight — single command, no agent sprawl
  - Complements our internal QA (different perspective)
- **Cons**:
  - Designed for open PRs — won't work on pre-PR review (Ralph reviews before PR)
  - Overlaps with Ralph's diff review Q1 (CLAUDE.md compliance) and Q4 (debug artifacts)
  - Generic — doesn't know about R-markers, plan conformance, or our specific patterns
  - Plugin is on blocklist — was added as test, might have had issues
  - Uses 4+ parallel agents = significant context/token cost

### 3. Adopt `pr-review-toolkit` Only — Deep Specialized Analysis

Use the toolkit's specialized agents for targeted pre-commit or pre-PR review.

- **Pros**:
  - 6 specialized agents cover areas we're thin on (error handling, type design, comment accuracy)
  - silent-failure-hunter fills a real gap — our QA catches structural issues but not error handling quality
  - Can run individual agents selectively (e.g., just `errors` after error handling changes)
  - Already installed and not blocklisted
- **Cons**:
  - 6 agents is heavy — running all costs significant tokens
  - Doesn't post to GitHub (local output only)
  - Overlaps with `/simplify` (code-simplifier), `/audit` Section 8 (test quality), and Ralph diff review
  - Agents are generic — no awareness of our V-Model, R-markers, or verification chain
  - No integration with our workflow state or verification logs

### 4. Cherry-Pick: Integrate 2 Agents Into Our Workflow

Extract only the high-value, non-overlapping capabilities and merge them into our existing tools:

- **silent-failure-hunter** → integrate into `/verify` or qa_runner.py as Step 13
- **code-review GitHub posting** → add as optional Ralph STEP 8.5 (post-PR creation review comment)

- **Pros**:
  - Targeted value — only adds what we genuinely lack
  - Maintains our unified workflow (no separate plugin ecosystem)
  - Error handling analysis fills a real blind spot in our 12-step pipeline
  - GitHub PR comments add visible review trail without manual effort
  - Minimal context cost (2 capabilities, not 6+4 agents)
- **Cons**:
  - Integration work required (extract logic, adapt to our patterns)
  - Maintenance burden — must track upstream plugin changes
  - Adding Step 13 to QA increases pipeline time
  - GitHub comment posting only useful after PR creation (chicken-and-egg with Ralph's pre-merge review)

### 5. Use `code-review` as Post-PR Gate Only

Don't integrate into Ralph's inner loop. Instead, run `/code-review` after PR creation as an independent quality signal — similar to how CI runs on PRs.

- **Pros**:
  - Clean separation: internal QA (pre-merge) vs external review (post-PR)
  - GitHub PR comment visible to anyone reviewing the PR
  - Doesn't slow down Ralph's autonomous loop
  - Easy to add — just run after `gh pr create` in Ralph STEP 8 or `/build-system` Phase D
  - Independent perspective catches things our self-review misses
- **Cons**:
  - Findings arrive after PR is already created (can't prevent bad PRs, only flag them)
  - If findings are serious, requires additional commits to fix
  - Token cost for running 4+ agents on already-reviewed code
  - May produce false positives that our QA already handled

## Recommendation

**Idea 5 (Use `code-review` as Post-PR Gate) combined with cherry-picking `silent-failure-hunter` for targeted use.**

Rationale:

1. **Our internal pipeline is strong for our use case** — the 12-step QA, diff review, and audit cover plan conformance, traceability, test quality, and structural integrity. These plugins can't replicate that. Discarding everything (Idea 1) is defensible.

2. **But we have two genuine gaps**:
   - **No GitHub PR comment trail** — our reviews are ephemeral (lost with context). `code-review` posts durable findings on the PR itself.
   - **No deep error handling analysis** — qa_runner checks for bare excepts (production scan), but `silent-failure-hunter` goes deeper: catch specificity, fallback masking, error propagation, logging quality.

3. **Post-PR is the right timing for `code-review`** because:
   - Ralph's internal QA already gates quality before merge
   - The PR comment serves as an independent audit trail, not a gate
   - Running before PR creation would slow down the autonomous loop
   - If it finds issues, we fix on the feature branch before merge to main

4. **`silent-failure-hunter` is useful ad-hoc, not as a pipeline step** — running it on every story would be overkill. Keep it available for manual invocation when error handling is the focus of a change.

5. **Discard the rest of `pr-review-toolkit`** — `code-simplifier` = `/simplify`, `code-reviewer` = overlap with audit, `comment-analyzer` = low value for our Python hook codebase, `type-design-analyzer` = irrelevant (we don't have complex type hierarchies), `pr-test-analyzer` = weaker than our test_quality.py.

**Concrete actions**:

- Remove `code-review` from blocklist
- Add optional `/code-review` step after PR creation in Ralph STEP 8 and `/build-system` Phase D
- Keep `pr-review-toolkit` installed for ad-hoc `/pr-review-toolkit:review-pr errors` use
- Do NOT integrate either into the inner QA loop

## Sources

- `.claude/docs/ARCHITECTURE.md` — System diagram, hook chain, skill inventory
- `.claude/skills/verify/SKILL.md` — 12-step QA pipeline
- `.claude/skills/audit/SKILL.md` — 8-section audit
- `.claude/skills/ralph/SKILL.md` — STEP 6 diff review, STEP 8 PR creation
- `.claude/skills/build-system/SKILL.md` — Phase D handoff and PR gate
- `~/.claude/plugins/marketplaces/claude-plugins-official/plugins/code-review/` — Plugin source
- `~/.claude/plugins/marketplaces/claude-plugins-official/plugins/pr-review-toolkit/` — Plugin source
- `~/.claude/plugins/blocklist.json` — Blocklist configuration
- `.claude/docs/knowledge/lessons.md` — Lessons learned
- `PROJECT_BRIEF.md` — Project constraints

## Build Strategy

### Module Dependencies

```
[code-review plugin] ─── depends on ──→ [gh CLI] ──→ [GitHub PR exists]
                     ─── depends on ──→ [CLAUDE.md] (reads for compliance)

[silent-failure-hunter] ─── depends on ──→ [git diff] (reads changed files)
                        ─── standalone (no workflow dependencies)

[Ralph STEP 8] ──→ [gh pr create] ──→ [/code-review] (post-PR)
[/build-system Phase D] ──→ [gh pr create] ──→ [/code-review] (post-PR)
```

### Build Order

1. **Remove blocklist entry** (blocklist.json edit — 5 min)
2. **Update Ralph STEP 8** — add optional code-review after PR creation (SKILL.md edit)
3. **Update /build-system Phase D** — add optional code-review after PR creation (SKILL.md edit)
4. **Test end-to-end** — create a test PR and run `/code-review` to verify it works

Steps 2-3 can be done in parallel. Step 4 depends on all prior steps.

### Testing Pyramid

- **Unit tests**: None needed — plugin commands are self-contained
- **Integration tests**: Verify `/code-review` runs successfully against a real PR (manual)
- **E2E tests**: Run full `/build-system` pipeline and verify code-review comment appears on PR (manual)
- Ratio: 0/30/70 — this is a workflow integration change, not code change

### Risk Mitigation Mapping

- Risk: `/code-review` posts noise to PR → Mitigation: 80+ confidence threshold already filters; we can raise it
- Risk: Token cost of running 4+ agents on every PR → Mitigation: Make it optional ("Ask user: Run code review?")
- Risk: Plugin updates break our workflow → Mitigation: Plugin is Anthropic-maintained; low risk. Pin version if needed
- Risk: False positives confuse PR reviewers → Mitigation: Add note that findings are advisory, internal QA already passed
- Risk: `/code-review` fails on private repo → Mitigation: Uses gh CLI which is already authenticated

### Recommended Build Mode

**Manual Mode** — This is a small SKILL.md edit + blocklist removal + testing. No acceptance criteria, no complex logic. Ralph would be overkill for 2 file edits.
