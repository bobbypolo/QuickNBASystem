# Session Handoff — 2026-03-04

## Session Type: Post-Mortem Analysis + Accuracy Upgrade Implementation

## Completed This Session

### 1. Six-Phase Accuracy Upgrade (carried from 2026-03-03 session)

Implemented all 6 phases of the simulator accuracy upgrade plan, porting features from `F:\NBA system\nba-production-system`:

| Phase | Feature                                   | Files Created/Modified                                                      |
| ----- | ----------------------------------------- | --------------------------------------------------------------------------- |
| 1     | Pace Engine + Quarter-by-Quarter Scaffold | `pace_engine.py` (new), `simulator.py` (rewrite)                            |
| 2     | Discrete Outcome Scoring Model            | `outcome_model.py` (new)                                                    |
| 3     | Market Blending (Logit-Space)             | `market_blender.py` (new), `run_tonight.py` (rewrite), `main.py` (modified) |
| 4     | Gaussian Copula Correlation Matrix        | `correlations.py` (new), `parlay.py` (modified)                             |
| 5     | Fatigue & Schedule Context                | `fatigue.py` (new), `game_data.py` (modified)                               |
| 6     | Correlated Quarter Noise                  | `simulator.py` (integrated)                                                 |

- 7 new test files, 54 total tests passing
- Performance: 10 games in 0.02s (target was <10s)
- All existing interfaces preserved (SimResult, ParlayLeg, ParlayResult)

### 2. March 3 Parlay Post-Mortem

Analyzed the 7-leg "highest probability" parlay against actual game results:

**Result: 5/7 legs hit, ticket lost.**

| Leg                 | Model Prob | Result               | Miss  |
| ------------------- | ---------- | -------------------- | ----- |
| DET@CLE OVER 221.5  | ~65%       | WIN (222)            | +0.5  |
| WAS@ORL OVER 221.5  | ~65%       | WIN (235)            | +13.5 |
| NYK@TOR OVER 221.5  | 76.6%      | **LOSS** (206)       | -15.5 |
| PHI +7.5 vs SAS     | 75.0%      | **LOSS** (SAS by 40) | -32.5 |
| CHI +9.5 vs OKC     | 74.8%      | WIN (OKC by 8)       | +1.5  |
| NOP@LAL UNDER 242.5 | 78.0%      | WIN (211)            | +31.5 |
| MEM@MIN UNDER 237.5 | 65.9%      | WIN (227)            | +10.5 |

**Night context**: Favorites covered 7/10 spreads. UNDER went 9-1. Massively defense-tilted.

### 3. Root Cause Analysis & Lessons Captured

Five root causes documented in `lessons.md`:

1. **PHI injury data fatally incomplete** — `game_data.py` had 1.5pt adj but PHI was missing Embiid (season), George (suspension), AND Oubre. True impact ~20+ pts.
2. **NYK@TOR OVER missed cold-shooting tail** — Season-level pace/ORTG can't model long cold stretches or halfcourt drag.
3. **Median-diff bug** (simulator.py:202) — Pace engine gets single median, not per-sim diffs. Suppresses blowout tails, inflates underdog cover rates.
4. **Overconfident probabilities** — Model says 75% when reality is ~60%. Expected 5.37/7 hits; all-7 hit chance was only 15.63%.
5. **No mechanism for league-wide defensive trends** — 9-1 UNDER night was invisible to model.

### 4. Production System Comparison

Documented structural differences that would have prevented this parlay:

- Totals market classified `implemented_but_unproven` (4/7 legs blocked)
- Confidence gate: >65% prob AND >3.5% edge after market blending
- Kelly sizing: 7-leg capped at 0.25% bankroll with 0.7^6 decay
- Lineup-level EPV catches depleted rosters (vs. team-level ORTG)
- Per-sim game-state tracking models blowout tails correctly
- Production would have recommended 2-4 single ML/spread bets → probable 3/4 winning night

## Files Changed This Session

| File                                | Action    | Purpose                                        |
| ----------------------------------- | --------- | ---------------------------------------------- |
| `.claude/docs/knowledge/lessons.md` | MODIFIED  | Added postmortem lesson + linter import lesson |
| `.claude/docs/HANDOFF.md`           | REWRITTEN | This file                                      |
| `memory/MEMORY.md`                  | CREATED   | Persistent cross-session memory                |

## Known Bugs

1. **Median-diff bug** (simulator.py:202): `np.median(home_scores - away_scores)` feeds one number to pace engine for all 10k sims. Should be per-sim tracking. Inflates underdog cover rates.
2. **Correlation diagonal** (correlations.py:21): Same-type legs across different games use diagonal 1.0, inflating MG parlay joint hit rates.

## Blockers / Open Questions

- PLAN.md still contains the sync-check / Ralph delegation fix plan from a prior session. This is unrelated to the simulator work and remains unimplemented.

## Next Session Should

### Priority 1: Fix Critical Bugs

1. Fix median-diff bug in simulator.py:202 — replace `np.median()` with per-sim score tracking for pace engine and garbage time decisions
2. Fix correlation diagonal issue in correlations.py — same bet type across different games should NOT use 1.0 correlation

### Priority 2: Implement Postmortem Recommendations

3. Add hard gate preventing started-game betting without live-state simulation
4. Replace manual injury adjustments with automated injury feed (API or scraper) + confirmed starters check; fail closed when data is uncertain
5. Add uncertainty haircuts — use lower-bound probabilities (e.g., p - 1\*stderr) for leg selection instead of point estimates
6. Cap "high probability" parlay recommendations at 3-4 legs; label 5+ legs as lottery
7. Add nightly calibration/backtest report (Brier score, log loss by market type, by edge bucket, by leg count)

### Priority 3: Model Improvements

8. Add recency-weighted team ratings (60% last-10-games, 40% season) alongside static season averages
9. Add spread-magnitude calibration curve as post-processing layer (historical cover rates by spread size)
10. Implement confidence ceiling: `abs(spread) >= 12 → cap cover prob at 0.52`
11. Strengthen garbage time model — current threshold (margin >= 25, 0.90x) is too gentle; need graduated scale starting at margin >= 15
