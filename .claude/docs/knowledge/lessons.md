# Lessons Learned

> This file captures insights from issues encountered during development.
> Use `/learn` to add new entries after resolving unexpected problems.

---

## [2026-03-02] - Auto-Stash Consumed by Worker in Shared Worktree

**Tags**: #ralph #git #worktree #safety

**Issue**: Ralph orchestrator auto-stashed the dirty working tree before dispatching a worker. The worker, running in a shared git environment, popped the stash during its operations, destroying the orchestrator's safety checkpoint.

**Root Cause**: Git stashes are global to the repository, not scoped to a worktree. Any process with access to the repo can pop or drop stashes created by another process.

**Resolution**: Replaced auto-stash with a clean-tree requirement. Ralph STEP 4 now checks `git status --porcelain` and STOPs if the tree is dirty, requiring the user to commit or stash manually before running `/ralph`.

**Prevention**: Never use `git stash` as a safety mechanism in multi-agent or worktree-isolated workflows. Require clean working tree as a precondition instead.

---

## [2026-03-02] - Context Bloat from Eager File Reads at Session Start

**Tags**: #context-window #performance #architecture

**Issue**: The Quick Start section in CLAUDE.md instructed Claude to read 5 files on first turn (PROJECT_BRIEF.md, PLAN.md, ARCHITECTURE.md, HANDOFF.md, WORKFLOW.md), consuming approximately 6,950 tokens before any user work began. Combined with the system prompt (~15,970 tokens), the total first-turn context was ~22,920 tokens.

**Root Cause**: All reference docs were loaded eagerly regardless of whether the session needed them. Most sessions only need current work state (PLAN.md) and session continuity (HANDOFF.md).

**Resolution**: Trimmed Quick Start to read only PLAN.md and HANDOFF.md on first turn. Other files (PROJECT_BRIEF.md, ARCHITECTURE.md, WORKFLOW.md) marked as "read on demand". The `/refresh` skill loads all files when explicitly needed.

**Prevention**: Classify startup reads as "essential" vs "reference". Only auto-load files that contain current work state. Use on-demand loading for reference documentation.

---

## [2026-03-01] - Hook Double-Firing with Frontmatter Hooks

**Tags**: #hooks #configuration #ralph-worker

**Issue**: When ralph-worker.md included hook definitions in its YAML frontmatter, these hooks stacked with the hooks already defined in `.claude/settings.json`. This caused hooks like `post_write_prod_scan.py` to execute twice per write operation, doubling execution time and producing duplicate output.

**Root Cause**: Claude Code merges hooks from all sources (settings.json + agent frontmatter). There is no deduplication -- if the same hook appears in both places, it runs twice.

**Resolution**: Removed all hook definitions from ralph-worker.md frontmatter. Workers now inherit hooks exclusively from `settings.json`, which is the single source of truth for hook configuration.

**Prevention**: Never define hooks in agent frontmatter if they are already configured in settings.json. Use frontmatter only for agent-specific hooks that should NOT run for other agents.

---

## [2026-03-01] - Conflicting Escalation Thresholds Across Agent Files

**Tags**: #agents #precedence #ralph

**Issue**: builder.md defined escalation at 2 compile errors or 3 test failures. ralph-worker.md said "ignore escalation thresholds." CLAUDE.md had no explicit precedence rule. This created ambiguity -- agents could not determine which rule applied when instructions from multiple files conflicted.

**Root Cause**: Three files defined overlapping behavior (build rules, escalation policy, production standards) without a clear hierarchy. The system grew incrementally and each file was written independently.

**Resolution**: Added explicit Precedence Rules section to CLAUDE.md establishing a clear hierarchy: (1) production safety always wins, (2) ralph-worker ignores builder escalation, (3) blast radius is WARN not FAIL, (4) no self-mocking, (5) workflow state file is canonical. Made ralph-worker.md self-contained with all rules inlined.

**Prevention**: When multiple agent files govern the same behavior, define explicit precedence rules in the top-level configuration file (CLAUDE.md). Each agent file should be self-contained for its mode of operation.

---

## [2026-03-01] - Refactoring Intent Misread as Defect

**Tags**: #workflow #communication #intent

**Issue**: During a cleanup sprint, Claude treated intentionally removed content (trimmed WORKFLOW.md sections, deleted research commands) as defects to restore. It re-added removed sections because the "canonical" version it synced to was the pre-cleanup state.

**Root Cause**: The instructions said to "sync to canonical version" without clarifying that the cleanup itself was the canonical intent. Claude's pattern-matching defaulted to "divergence = defect" rather than "divergence = deliberate change."

**Resolution**: Added explicit guidance in MEMORY.md: "When prompt.md or user instructions identify bloat to REMOVE, do NOT treat the trimmed state as a defect to fix. Read the intent before syncing to a canonical version."

**Prevention**: When issuing cleanup or removal instructions, explicitly state that the removal IS the desired end state. Use phrases like "the trimmed version is correct" rather than relying on Claude to infer intent from context.

---

## [2026-03-04] - March 3 Parlay Post-Mortem: 5/7 Legs Hit, Ticket Lost

**Tags**: #simulation #accuracy #parlay #calibration #postmortem

**Issue**: 7-leg "highest probability" parlay went 5/7 (DET@CLE O 221.5 WIN, WAS@ORL O 221.5 WIN, NYK@TOR O 221.5 LOSS, PHI +7.5 LOSS, CHI +9.5 WIN, NOP@LAL U 242.5 WIN, MEM@MIN U 237.5 WIN). Model's top-3 confidence picks included both losers. PHI +7.5 was a catastrophic 40-point blowout miss (model said 75%, SAS won by 40). NYK@TOR OVER was 15.5 pts wrong on a 76.6% confidence call. Model expected ~5.37 of 7 hits — got exactly 5, but the wrong 5.

**Root Causes**:

1. **PHI injury context was fatally incomplete.** `game_data.py` had `home_injury_adj=1.5` (Oubre only). In reality, PHI was also missing Embiid (season) and George (suspension). True impact was ~20+ pts ORTG degradation, not 1.5. Manual injury entry with no automated feed caused the miss.

2. **NYK@TOR OVER missed defensive game script.** Model used season-level pace/ORTG and predicted both teams scoring ~111. Toronto shot terribly from 3 in a long cold stretch; actual total was 206. Model has no cold-shooting / halfcourt drag tail modeling.

3. **Median-diff bug in simulator.py:202.** `median_diff = float(np.median(home_scores - away_scores))` feeds one number to the pace engine for ALL 10,000 sims. Per-sim paths where SAS leads by 30+ never trigger garbage time slowdown individually. Production system tracks per-sim score diffs (sequencer.py:399-400). This inflates underdog cover probabilities and suppresses blowout tails.

4. **Overconfident probabilities — model says 75% when reality is ~60%.** Model expected 5.37/7 hits (15.63% all-hit). Even with correct expectations, 7-leg parlay was 84.37% likely to lose. The model's overconfidence didn't change the outcome, but it made the bet look far more attractive than it was.

5. **Night was 9-1 UNDER, favorites covered 7/10.** Massively defense-tilted night that neither model predicted. Three OVER picks included; one (NYK@TOR) was badly wrong. Model has no mechanism to detect league-wide defensive trends on a given night.

**Production System Comparison**: The production system would NOT have built this parlay:

- Totals market is classified `implemented_but_unproven` — 4 of 7 legs would be blocked
- Confidence gate requires >65% model prob AND >3.5% edge over market after blending
- Kelly sizing caps 7-leg parlays at 0.25% bankroll with 0.7^6 decay
- Lineup-level EPV (not team ORTG) would have caught PHI's depleted roster properly
- Per-sim game-state tracking would model blowout tails correctly
- Production would likely have recommended 2-4 single-leg ML/spread bets → probable 3/4 winning night

**Resolution**: Six priority changes identified for the quick system:

1. Hard gate: no started-game betting without live-state simulation (score + clock + remaining possessions)
2. Replace manual injury adjustments with automated injury feed + confirmed starters; fail closed on uncertainty
3. Uncertainty haircuts: use lower-bound probabilities for leg selection, not point estimates
4. Cap "high probability" parlay recommendations at 3-4 legs; 5+ legs = lotto by definition
5. Fix MG parlay correlation treatment — same-type legs across games should not be near-perfectly correlated (correlations.py diagonal 1.0 issue)
6. Add nightly calibration/backtest report (Brier score, log loss by market type, by edge bucket, by leg count)

**Prevention**:

- Never recommend a spread pick when injury data is manually entered and incomplete. Require automated injury feed or flag as LOW CONFIDENCE.
- Never claim >60% on any OVER pick based solely on season averages. Require recency-weighted ratings and defensive matchup adjustment.
- Fix the median-diff bug (simulator.py:202) before next live run — this affects every prediction.
- Treat any 7-leg parlay as a lottery ticket regardless of per-leg probabilities. Math: even 70%^7 = 8.2%.

---

## [2026-03-04] - Linter Auto-Strips New Imports During Incremental Edits

**Tags**: #hooks #editing #imports #linter

**Issue**: During the 6-phase simulator upgrade, adding new imports (e.g., `from pace_engine import predict_period_possessions`) to a file before modifying the function body that uses them caused the project's auto-format hook to strip the imports as "unused." This happened repeatedly across simulator.py, parlay.py, run_tonight.py, and main.py.

**Root Cause**: The project has Ruff-based auto-format hooks that run on every file write. When imports are added but the function body still references old code, Ruff correctly identifies the imports as unused and removes them. This creates a chicken-and-egg problem with incremental editing.

**Resolution**: Two strategies that work:

1. **Full file rewrite** — Write the entire file at once so imports are used immediately (used for simulator.py, run_tonight.py)
2. **Inline imports** — Place imports inside the function body instead of at module level (used for main.py: `from market_blender import blend_probability` inside the endpoint function)

**Prevention**: When modifying files in projects with auto-format hooks, always add imports AND their usage in the same edit operation. Never add imports in a standalone edit step.

---

<!-- New lessons are added above this line -->
