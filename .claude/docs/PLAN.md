# Plan: NBA Quick System — Post-Mortem Remediation

## Goal

Systematically address all 11 accuracy and reliability issues identified in the March 3, 2026 parlay post-mortem. Fixes are sequenced by dependency and risk: quick-win hardening first, then core engine fixes, then data quality infrastructure. All changes must be test-verified and wired through `run_tonight.py` end-to-end before the story is considered done.

## Implementation Sequence

| Phase | Story                           | Items Addressed                                                            | Dependencies |
| ----- | ------------------------------- | -------------------------------------------------------------------------- | ------------ |
| 1     | Simulation Accuracy Micro-Fixes | #2 correlation diagonal, #10 confidence ceiling, #11 garbage time tiers    | None         |
| 2     | Operational Safety Rails        | #3 started-game gate, #6 parlay leg cap                                    | None         |
| 3     | Per-Sim Game-State Tracking     | #1 median-diff bug (vectorize)                                             | Phase 1      |
| 4     | Probability Calibration Layer   | #5 uncertainty haircuts, #9 spread calibration curve                       | Phase 1      |
| 5     | Non-Linear Injury Stacking      | Partial #4 — stacking multiplier (no API needed)                           | Phase 2      |
| 6     | Automated Injury & Stats Feed   | #4 full (ESPN scraper + nba_api last-10-game), #8 recency-weighted ratings | Phase 5      |
| 7     | Nightly Calibration & Backtest  | #7 Brier/log-loss report, SQLite predictions log                           | Phase 4      |

Phases 1 and 2 are independent and can run in parallel. Phase 3 depends on Phase 1 (uses the same vectorized intensity function). Phase 4 depends on Phase 1 (uses run_tonight.py cover prob path). All Phase 3+ stories depend on prior phases completing cleanly.

---

## Phase 1: Simulation Accuracy Micro-Fixes

**Phase Type**: `module`

Three small but high-impact accuracy fixes in the simulation pipeline: fix the correlation diagonal bug that inflates MG parlay probabilities, graduate the garbage-time intensity model from a single threshold to four tiers, and add a spread-magnitude confidence ceiling that prevents the model from recommending large-underdog spreads with inflated cover probabilities.

### Changes

| Action | File                    | Description                                                                                                                                                                                                                                                                                                                                                                     |
| ------ | ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| MODIFY | `correlations.py`       | Add `CROSS_GAME_SAME_TYPE_RHO = 0.15` constant. Add `same_game: bool = False` param to `get_correlation()`. When `same_game=False` and `type1 == type2`, return `CROSS_GAME_SAME_TYPE_RHO` instead of diagonal 1.0. Add `game_ids: list[str] \| None = None` param to `correlated_parlay_prob()`. Build same_game matrix from game_ids (legs sharing game_id → same_game=True). |
| MODIFY | `outcome_model.py`      | Replace `GARBAGE_TIME_MARGIN = 25` / `GARBAGE_MULTIPLIER = 0.90` with `GARBAGE_TIERS: list[tuple[float, float]]` covering 4 thresholds. Extend garbage-time logic to Q3 when margin ≥ 30.                                                                                                                                                                                       |
| MODIFY | `run_tonight.py`        | Add `_spread_confidence_cap(raw_prob: float, abs_spread: float) -> float` helper. Apply cap in `print_game_result()` before using cover probability for recommendation qualification.                                                                                                                                                                                           |
| MODIFY | `test_correlations.py`  | Add tests for cross-game same-type returning 0.15, same-game same-type returning 1.0, correlated_parlay_prob joint not inflated.                                                                                                                                                                                                                                                |
| MODIFY | `test_outcome_model.py` | Add tests for each garbage time tier and Q3 application.                                                                                                                                                                                                                                                                                                                        |

### Interface Contracts

**`get_correlation(type1, type2, same_team=False, same_game=False) -> float`**

- If `same_game=False` and `type1 == type2`: return `CROSS_GAME_SAME_TYPE_RHO` (0.15)
- If `same_game=True` and `type1 == type2`: return 1.0 (diagonal, for SGP use)
- Otherwise: existing matrix lookup + same_team boost

**`correlated_parlay_prob(..., game_ids: list[str] | None = None) -> float`**

- `game_ids[i]` identifies the game for leg i
- When building NxN matrix: `same_game = (game_ids[i] == game_ids[j])` when game_ids provided
- When game_ids is None (backward compat): all off-diagonal pairs use same_game=False

**`GARBAGE_TIERS: list[tuple[float, float]]`**

```python
GARBAGE_TIERS = [
    (30.0, 0.72),   # 30+ margin → bench mob (both Q3 and Q4)
    (25.0, 0.80),   # 25-29 → mostly garbage time (Q4 only)
    (20.0, 0.88),   # 20-24 → deep bench entering (Q4 only)
    (15.0, 0.95),   # 15-19 → starters slowing (Q4 only)
]
```

In `quarter_intensity()`: iterate tiers from highest to lowest margin, apply first match. Q3 triggers only for margin >= 30.

**`_spread_confidence_cap(raw_prob: float, abs_spread: float) -> float`**

```python
# Based on historical NBA cover rates 2015-2024
if abs_spread >= 13.0: return min(raw_prob, 0.50)
if abs_spread >= 10.0: return min(raw_prob, 0.52)
if abs_spread >= 8.0:  return min(raw_prob, 0.56)
return raw_prob  # no cap for spread < 8
```

### Testing Strategy

| What                                                                         | Type | File                               |
| ---------------------------------------------------------------------------- | ---- | ---------------------------------- |
| `get_correlation("team_win","team_win", same_game=False)` returns 0.15       | unit | `test_correlations.py`             |
| `get_correlation("team_win","team_win", same_game=True)` returns 1.0         | unit | `test_correlations.py`             |
| `correlated_parlay_prob([0.6,0.6], ["team_win","team_win"])` in [0.30, 0.42] | unit | `test_correlations.py`             |
| `quarter_intensity(4, 32.0)` returns `1.08 * 0.72 ≈ 0.778`                   | unit | `test_outcome_model.py`            |
| `quarter_intensity(3, 32.0)` returns `1.02 * 0.72 ≈ 0.734`                   | unit | `test_outcome_model.py`            |
| `quarter_intensity(4, 16.0)` returns `1.08 * 0.95 ≈ 1.026`                   | unit | `test_outcome_model.py`            |
| `_spread_confidence_cap(0.70, 13.5)` returns 0.50                            | unit | `test_calibration_guards.py` (new) |
| All existing `test_correlations.py` and `test_outcome_model.py` tests pass   | unit | both                               |

### Done When

- R-P1-01: `get_correlation("team_win", "team_win", same_game=False)` returns exactly `0.15`
- R-P1-02: `get_correlation("team_win", "team_win", same_game=True)` returns exactly `1.0`
- R-P1-03: `correlated_parlay_prob([0.6, 0.6], ["team_win", "team_win"], seed=42)` returns a value in `[0.30, 0.42]` (not inflated to 0.60)
- R-P1-04: `quarter_intensity(4, 31.0)` returns a value between `0.77` and `0.79` (1.08 \* 0.72)
- R-P1-05: `quarter_intensity(3, 31.0)` returns a value between `0.72` and `0.75` (1.02 \* 0.72), confirming Q3 blowout trigger
- R-P1-06: `quarter_intensity(4, 16.0)` returns a value between `1.02` and `1.04` (1.08 \* 0.95 tier)
- R-P1-07: `_spread_confidence_cap(0.75, 13.5)` returns `0.50` (hard cap at spread >= 13)
- R-P1-08: `_spread_confidence_cap(0.75, 10.5)` returns `0.52` (cap for abs_spread in [10.0, 13.0))
- R-P1-09: `_spread_confidence_cap(0.58, 6.0)` returns `0.58` (no cap below 8)
- R-P1-10: All existing `test_correlations.py` tests pass (9 tests)
- R-P1-11: All existing `test_outcome_model.py` tests pass (8 tests)
- R-P1-12: `correlations.py` does NOT contain any code path where `get_correlation()` can return 1.0 when `same_game=False` and `i != j`

### Verification Command

```bash
python -m pytest test_correlations.py test_outcome_model.py test_calibration_guards.py -v --tb=short && ruff check correlations.py outcome_model.py run_tonight.py
```

---

## Phase 2: Operational Safety Rails

**Phase Type**: `module`

Two operational guardrails that prevent common misuse: a hard gate that blocks recommending already-started games (the system currently has no way to simulate remaining time), and a parlay leg cap that prevents the auto-builder from producing lottery-grade tickets labeled as "high probability" recommendations.

### Changes

| Action | File                   | Description                                                                                                                                                                                                                                                      |
| ------ | ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| MODIFY | `run_tonight.py`       | Add `STARTED_GAME_LOOKBACK_MINUTES = 5`. In `main()`, after building `games_to_run`, filter out games where `tipoff_et < now_et - timedelta(minutes=STARTED_GAME_LOOKBACK_MINUTES)`. Print `⛔ SKIPPED (game in progress): {game_id}` for each filtered game.    |
| MODIFY | `run_tonight.py`       | Add `MAX_RECOMMENDED_PARLAY_LEGS = 4` and `MAX_LOTTO_PARLAY_LEGS = 7` constants. In parlay section, auto-parlay capped at `MAX_RECOMMENDED_PARLAY_LEGS`. Add `_classify_parlay(n_legs)` that labels parlays as STANDARD (2-4), HIGH_RISK (5-6), or LOTTERY (7+). |
| MODIFY | `parlay.py`            | Add `is_lottery_grade: bool` field to `ParlayResult` dataclass (True when len(legs) > 4). `print_parlay_result()` prints `⚠️  LOTTERY GRADE` banner when `is_lottery_grade=True`.                                                                                |
| CREATE | `test_safety_rails.py` | Tests for started-game filter and parlay leg classification.                                                                                                                                                                                                     |

### Interface Contracts

**`is_game_started(g: GameEntry, now_et: datetime) -> bool`**

- Returns True if `tipoff_et < now_et - timedelta(minutes=5)`
- Returns False if game hasn't started or is within the 5-min window

**`_classify_parlay(n_legs: int) -> str`**

- 2-4 legs → `"STANDARD"`
- 5-6 legs → `"HIGH_RISK"`
- 7+ legs → `"LOTTERY"`

**`ParlayResult` additions**

- `is_lottery_grade: bool` — set by `evaluate_mg_parlay()` when `len(legs) > 4`

### Testing Strategy

| What                                                           | Type | File                   |
| -------------------------------------------------------------- | ---- | ---------------------- |
| `is_game_started()` returns True for game 10 min in the past   | unit | `test_safety_rails.py` |
| `is_game_started()` returns False for game starting in 30 min  | unit | `test_safety_rails.py` |
| `_classify_parlay(3)` returns "STANDARD"                       | unit | `test_safety_rails.py` |
| `_classify_parlay(7)` returns "LOTTERY"                        | unit | `test_safety_rails.py` |
| `evaluate_mg_parlay` with 5 legs sets `is_lottery_grade=True`  | unit | `test_safety_rails.py` |
| `evaluate_mg_parlay` with 3 legs sets `is_lottery_grade=False` | unit | `test_safety_rails.py` |

### Done When

- R-P2-01: `is_game_started(g, now_et)` returns `True` when `tipoff_et` is 10 minutes before `now_et`
- R-P2-02: `is_game_started(g, now_et)` returns `False` when `tipoff_et` is 30 minutes after `now_et`
- R-P2-03: `_classify_parlay(4)` returns `"STANDARD"`, `_classify_parlay(5)` returns `"HIGH_RISK"`, `_classify_parlay(7)` returns `"LOTTERY"`
- R-P2-04: `evaluate_mg_parlay(results, legs)` with `len(legs) == 5` produces a `ParlayResult` where `is_lottery_grade == True`
- R-P2-05: `evaluate_mg_parlay(results, legs)` with `len(legs) == 3` produces a `ParlayResult` where `is_lottery_grade == False`
- R-P2-06: `run_tonight.py main()` loop does NOT include started games in the simulation run (verified by checking that `is_game_started()` is called before `simulate_game()` for each game)

### Verification Command

```bash
python -m pytest test_safety_rails.py test_push_parlay.py -v --tb=short && ruff check run_tonight.py parlay.py
```

---

## Phase 3: Per-Sim Game-State Tracking

**Phase Type**: `module`

The median-diff bug. `simulator.py:202` collapses all 10,000 per-sim score differences into one scalar that is fed to the pace engine and garbage-time logic. This means simulations where one team leads by 30 never individually trigger garbage-time slowdowns — the median might be 8, so all sims use the 8-point pace/intensity. Fix: vectorize `predict_period_possessions` and `quarter_intensity` to accept `np.ndarray` inputs, and update `simulator.py` to pass per-sim arrays instead of the median scalar.

### Changes

| Action | File                    | Description                                                                                                                                                                                                                                                                                                                                   |
| ------ | ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| MODIFY | `pace_engine.py`        | Add `predict_period_possessions_vec(home_pace, away_pace, period, score_diff_arr: np.ndarray) -> np.ndarray`. Uses `np.where` chains for blowout/comfortable/close score-state bands. Scalar version `predict_period_possessions()` unchanged (backward compat).                                                                              |
| MODIFY | `outcome_model.py`      | Add `quarter_intensity_vec(period: int, score_diff_arr: np.ndarray) -> np.ndarray`. Vectorizes the existing `quarter_intensity()` using `np.where`. Scalar version unchanged. Update `sample_quarter_scores()` to accept `possessions: float \| np.ndarray` and `intensity: float \| np.ndarray` — numpy ops handle both cases transparently. |
| MODIFY | `simulator.py`          | In `simulate_game()`, replace lines computing `median_diff` → `possessions` → `intensity` with: `per_sim_diffs = home_scores - away_scores` → `predict_period_possessions_vec(...)` → `quarter_intensity_vec(...)`. Remove `np.median()` call entirely. OT loop keeps scalar path (tied sims have 0 effective margin).                        |
| MODIFY | `test_pace_engine.py`   | Add tests for `predict_period_possessions_vec()`: vector input produces correct shape, blowout sims get fewer possessions than close-game sims.                                                                                                                                                                                               |
| MODIFY | `test_outcome_model.py` | Add tests for `quarter_intensity_vec()`: array input → array output, blowout elements lower than close elements in Q4.                                                                                                                                                                                                                        |
| MODIFY | `test_quarter_sim.py`   | Add blowout-tail regression test: strong favorite should show std(margin) > 12 with n_sims=50_000 (was being suppressed by median-diff bug).                                                                                                                                                                                                  |

### Interface Contracts

**`predict_period_possessions_vec(home_pace, away_pace, period, score_diff_arr: np.ndarray) -> np.ndarray`**

- Input: `score_diff_arr` shape `(n_sims,)`
- Output: shape `(n_sims,)` — per-sim possession estimates
- Uses `np.where` for each score-state band (same logic as scalar version)
- Vectorized `score_state_factor_vec(score_diff_arr)` → returns `(home_factors, away_factors)` as arrays

**`quarter_intensity_vec(period: int, score_diff_arr: np.ndarray) -> np.ndarray`**

- Input: `score_diff_arr` shape `(n_sims,)`
- Output: shape `(n_sims,)` — per-sim intensity multipliers
- Applies graduated GARBAGE_TIERS from Phase 1 per-element using `np.where` chains
- Q3 blowout trigger applies to elements where `abs_diff >= 30`
- Foul game boost (Q4 close game) applies to elements where `abs_diff < FOUL_GAME_MARGIN`

**`sample_quarter_scores(team_ppp, possessions, intensity, n_sims, rng, noise=None)`**

- `possessions` and `intensity` now accept `float` OR `np.ndarray` — no signature change needed
- `np.sqrt(var_pts * effective_poss)` handles both scalar and array `effective_poss` via numpy broadcasting
- When both are arrays of shape `(n_sims,)`, output is still shape `(n_sims,)` ✓

### Testing Strategy

| What                                                                                                 | Type       | File                    |
| ---------------------------------------------------------------------------------------------------- | ---------- | ----------------------- |
| `predict_period_possessions_vec(100,100,4, np.array([-30,0,30]))` returns shape (3,) where [0] > [2] | unit       | `test_pace_engine.py`   |
| `quarter_intensity_vec(4, np.array([-31,0,31]))` shape (3,) with blowout elements < close element    | unit       | `test_outcome_model.py` |
| `simulate_game()` with ortg 130 vs ortg 100 produces `std(margin) > 12.0` at n_sims=50_000           | regression | `test_quarter_sim.py`   |
| All existing scalar tests for `predict_period_possessions` still pass (8 tests)                      | unit       | `test_pace_engine.py`   |
| All existing scalar tests for `quarter_intensity` still pass                                         | unit       | `test_outcome_model.py` |
| `simulator.py` does NOT contain `np.median(home_scores - away_scores)`                               | manual     | n/a                     |

### Done When

- R-P3-01: `predict_period_possessions_vec(100.0, 100.0, 4, np.array([-30.0, 0.0, 30.0]))` returns array of shape `(3,)` where element index 0 (large trailing) has MORE possessions than element index 2 (large leading)
- R-P3-02: `quarter_intensity_vec(4, np.array([-31.0, 0.0, 31.0]))` returns array of shape `(3,)` where elements 0 and 2 are less than element 1 (blowout paths are slower than close game)
- R-P3-03: `quarter_intensity_vec(3, np.array([-31.0, 0.0, 31.0]))` returns array where blowout elements apply the 30+ tier (Q3 blowout applies)
- R-P3-04: `simulate_game(home, away, n_sims=50_000)` with home `ortg=130, drtg=100` and away `ortg=100, drtg=130` produces `np.std(result.margin) > 12.0` (blowout tail now present)
- R-P3-05: `simulate_game()` with equal teams (both `ortg=115, drtg=115`) still produces `90 < np.mean(home_scores) < 130` (distribution sanity)
- R-P3-06: `simulate_game()` with equal teams produces zero ties after OT resolution at `n_sims=100_000`
- R-P3-07: All 8 existing `test_pace_engine.py` scalar tests pass
- R-P3-08: All existing `test_outcome_model.py` scalar tests pass

### Verification Command

```bash
python -m pytest test_pace_engine.py test_outcome_model.py test_quarter_sim.py test_correlated_quarters.py -v --tb=short && ruff check simulator.py pace_engine.py outcome_model.py
```

---

## Phase 4: Probability Calibration Layer

**Phase Type**: `module`

Two calibration improvements that prevent overconfident recommendations: a spread-magnitude calibration curve (lookup table of historical underdog cover rates by spread bucket) implemented as a standalone module, and uncertainty haircuts that use the binomial standard error of the model's cover probability to select legs using a lower-confidence bound rather than the point estimate.

### Changes

| Action | File                  | Description                                                                                                                                                                                                                                            |
| ------ | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| CREATE | `calibration.py`      | `SPREAD_COVER_CAPS` lookup table (empirical NBA cover rates 2015-2024). `spread_underdog_cap(raw_prob, abs_spread) -> float`. `haircut_prob(raw_prob, n_sims, k=1.5) -> float`.                                                                        |
| MODIFY | `run_tonight.py`      | Import `calibration.py`. In `print_game_result()`, replace `_spread_confidence_cap()` helper (added in Phase 1) with `calibration.spread_underdog_cap()`. Apply `haircut_prob()` before recommendation qualification (use `n_sims = N_SIMS = 10_000`). |
| CREATE | `test_calibration.py` | Unit tests for both functions, edge cases (spread=0, spread=20), haircut math.                                                                                                                                                                         |

### Interface Contracts

**`SPREAD_COVER_CAPS: list[tuple[float, float]]`**

```python
# (spread_threshold, historical_cover_cap)
# Source: public NBA ATS data 2015-2024, ~15,000 games
SPREAD_COVER_CAPS = [
    (7.5,  1.00),   # small spreads: no cap
    (10.0, 0.54),   # -7.5 to -10: modest cap
    (13.0, 0.52),   # -10 to -13: significant cap
    (float("inf"), 0.50),  # -13+: near fair value for underdog
]
```

**`spread_underdog_cap(raw_prob: float, abs_spread: float) -> float`**

- Iterates SPREAD_COVER_CAPS, returns `min(raw_prob, cap)` for first matching bucket
- Only applied to the underdog's cover probability (not the favorite's)

**`haircut_prob(raw_prob: float, n_sims: int, k: float = 1.5) -> float`**

- Computes binomial standard error: `stderr = sqrt(raw_prob * (1 - raw_prob) / n_sims)`
- Returns `max(0.0, raw_prob - k * stderr)`
- With n_sims=10_000 and p=0.60: `stderr ≈ 0.0049`, haircut `≈ 0.593`
- With n_sims=10_000 and p=0.75: `stderr ≈ 0.0043`, haircut `≈ 0.743`
- Effect is small but consistent — nudges borderline picks below MIN_COVER_PROB_BET threshold

### Testing Strategy

| What                                                                | Type | File                  |
| ------------------------------------------------------------------- | ---- | --------------------- |
| `spread_underdog_cap(0.70, 13.5)` returns 0.50                      | unit | `test_calibration.py` |
| `spread_underdog_cap(0.55, 5.0)` returns 0.55 (no cap)              | unit | `test_calibration.py` |
| `haircut_prob(0.60, 10_000, k=1.5)` returns value in [0.585, 0.595] | unit | `test_calibration.py` |
| `haircut_prob(0.535, 10_000)` returns value just below 0.535        | unit | `test_calibration.py` |
| `haircut_prob(0.0, 10_000)` returns 0.0 (no negative prob)          | unit | `test_calibration.py` |

### Done When

- R-P4-01: `spread_underdog_cap(0.70, 13.5)` returns exactly `0.50`
- R-P4-02: `spread_underdog_cap(0.70, 10.5)` returns exactly `0.52`
- R-P4-03: `spread_underdog_cap(0.58, 5.0)` returns `0.58` (no cap for small spreads)
- R-P4-04: `haircut_prob(0.60, 10_000, k=1.5)` returns a value between `0.585` and `0.595`
- R-P4-05: `haircut_prob(0.0, 10_000)` returns `0.0` (floor enforced)
- R-P4-06: `run_tonight.py` imports and calls both `spread_underdog_cap()` and `haircut_prob()` in the cover-probability recommendation path (grep verification)
- R-P4-07: All existing `test_market_blender.py` tests still pass (8 tests) — confirms no regression on blending logic

### Verification Command

```bash
python -m pytest test_calibration.py test_market_blender.py -v --tb=short && ruff check calibration.py run_tonight.py
```

---

## Phase 5: Non-Linear Injury Stacking

**Phase Type**: `module`

The PHI blowout (40-point SAS win) was partially caused by PHI's injury adjustment being manually entered as 1.5 (Oubre only) when Embiid and George were also unavailable. Even with correct data entry, the current model applies a flat per-player ortg subtraction. Missing 4 players is NOT 4x missing 1 player — depth depletion creates a multiplicative effect. This phase adds a stacking multiplier and a `n_key_players_out` field to GameEntry.

### Changes

| Action | File                      | Description                                                                                                                                                                                    |
| ------ | ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| MODIFY | `game_data.py`            | Add `home_n_key_out: int = 0` and `away_n_key_out: int = 0` fields to `GameEntry` dataclass. Update existing GAMES slate entries with correct `n_key_out` counts.                              |
| MODIFY | `run_tonight.py`          | Add `injury_stacking_multiplier(n_out: int) -> float` function. In `_make_teams()`, apply stacking: `effective_injury_adj = g.home_injury_adj * injury_stacking_multiplier(g.home_n_key_out)`. |
| CREATE | `test_injury_stacking.py` | Tests for stacking multiplier, GameEntry field presence, \_make_teams integration.                                                                                                             |

### Interface Contracts

**`injury_stacking_multiplier(n_out: int) -> float`**

```python
def injury_stacking_multiplier(n_out: int) -> float:
    """Non-linear penalty: missing 4 players > 4x missing 1."""
    if n_out <= 1:
        return 1.0
    return 1.0 + 0.15 * (n_out - 1)
    # n=2 → 1.15x, n=3 → 1.30x, n=4 → 1.45x, n=5 → 1.60x
```

**`GameEntry` additions**

- `home_n_key_out: int = 0` — count of key players (rotation-level+) confirmed OUT
- `away_n_key_out: int = 0` — same for away team

Example: DAL on March 3 (Kyrie OUT, Lively OUT, Marshall OUT, Bagley OUT) → `away_n_key_out = 4`. Effective adj = `7.5 * 1.45 = 10.875` instead of `7.5`. The model spread shifts by an additional ~3.4 points toward Charlotte.

### Testing Strategy

| What                                                                                        | Type        | File                      |
| ------------------------------------------------------------------------------------------- | ----------- | ------------------------- |
| `injury_stacking_multiplier(0)` returns 1.0                                                 | unit        | `test_injury_stacking.py` |
| `injury_stacking_multiplier(1)` returns 1.0                                                 | unit        | `test_injury_stacking.py` |
| `injury_stacking_multiplier(4)` returns 1.45                                                | unit        | `test_injury_stacking.py` |
| `_make_teams()` with `n_key_out=4, injury_adj=7.5` produces team with effective adj >= 10.5 | integration | `test_injury_stacking.py` |
| `GameEntry` instantiates with default `home_n_key_out=0` (backward compat)                  | unit        | `test_injury_stacking.py` |

### Done When

- R-P5-01: `injury_stacking_multiplier(0)` returns `1.0`
- R-P5-02: `injury_stacking_multiplier(4)` returns `1.45`
- R-P5-03: `_make_teams(g)` where `g.away_n_key_out = 4` and `g.away_injury_adj = 7.5` produces an `away` `TeamInput` where the effective ortg reduction exceeds `10.5` points (stacking applied)
- R-P5-04: `GameEntry` dataclass has `home_n_key_out: int = 0` and `away_n_key_out: int = 0` fields with defaults (existing code that doesn't pass these args still works)
- R-P5-05: All existing tests that instantiate `GameEntry` or call `_make_teams()` continue to pass

### Verification Command

```bash
python -m pytest test_injury_stacking.py test_fatigue.py -v --tb=short && ruff check game_data.py run_tonight.py
```

---

## Phase 6: Automated Injury & Stats Feed

**Phase Type**: `module`

Automates the two manual-entry failure modes: injury adjustment data and season-averages-only ratings. Uses `nba_api` (free, unofficial NBA.com wrapper) for last-10-game team stats and ESPN's public injury report endpoint for current injury status. Auto-populates `game_data.py` fields at runtime so the slate is always current without manual re-entry.

### Changes

| Action | File                  | Description                                                                                                                                                                                                                                                                                                                                                                                                  |
| ------ | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| CREATE | `injury_feed.py`      | `fetch_injuries(team_abbr: str) -> list[PlayerInjury]`. `fetch_last10_ratings(team_abbrs: list[str]) -> dict[str, TeamRatings]`. ESPN scraper + nba_api integration. `PlayerInjury(name, status, impact_pts)` dataclass. `TeamRatings(ortg, drtg, pace)` dataclass.                                                                                                                                          |
| MODIFY | `game_data.py`        | Add `update_with_live_ratings(games: list[GameEntry]) -> dict` function (mirrors pattern of `update_with_live_odds`). Calls `injury_feed.py` functions, updates `injury_adj`, `n_key_out`, and last-10 stats on each game entry. Add `home_last10_ortg`, `home_last10_drtg`, `home_last10_pace`, `away_last10_ortg`, `away_last10_drtg`, `away_last10_pace` optional fields to `GameEntry` (default `None`). |
| MODIFY | `run_tonight.py`      | In `_make_teams()`, use recency-weighted ratings when last10 fields are present: `effective_ortg = 0.60 * last10_ortg + 0.40 * season_ortg`. Fall back to season-only when last10 is None.                                                                                                                                                                                                                   |
| CREATE | `test_injury_feed.py` | Mock-based tests for scraper parsing, rating calculation, recency weighting formula.                                                                                                                                                                                                                                                                                                                         |

### Interface Contracts

**`fetch_injuries(team_abbr: str) -> list[PlayerInjury]`**

- Scrapes ESPN injury endpoint (rate-limited, max 1 req/sec)
- Returns list of confirmed OUT/DOUBTFUL players with impact estimate
- Fails closed: on any error, returns empty list and logs warning

**`fetch_last10_ratings(team_abbrs: list[str]) -> dict[str, TeamRatings]`**

- Uses `nba_api.stats.endpoints.LeagueDashTeamStats(last_n_games=10)`
- Returns dict keyed by 3-letter abbr: `{"LAL": TeamRatings(ortg=118.2, drtg=115.1, pace=99.3), ...}`
- Fails closed: on API error, returns empty dict

**`update_with_live_ratings(games, min_coverage=0.80) -> dict`**

- Mirrors `update_with_live_odds()` pattern: returns coverage report
- Fails closed when coverage < min_coverage (doesn't abort; just skips update and uses static values)
- Returns `{"success": bool, "coverage": float, "updated_injuries": int, "updated_ratings": int}`

**Recency weighting in `_make_teams()`**

```python
if g.home_last10_ortg is not None:
    effective_ortg = 0.60 * g.home_last10_ortg + 0.40 * g.home_ortg
else:
    effective_ortg = g.home_ortg  # season-only fallback
```

### Testing Strategy

| What                                                                                                                  | Type        | File                  |
| --------------------------------------------------------------------------------------------------------------------- | ----------- | --------------------- |
| `fetch_injuries()` returns empty list on network error (fails closed)                                                 | unit (mock) | `test_injury_feed.py` |
| `fetch_last10_ratings()` returns empty dict on API error (fails closed)                                               | unit (mock) | `test_injury_feed.py` |
| Recency weighting: `0.60 * 120.0 + 0.40 * 115.0 == 118.0`                                                             | unit        | `test_injury_feed.py` |
| `_make_teams()` with `home_last10_ortg=120.0, home_ortg=115.0` produces `TeamInput` with higher ortg than static-only | integration | `test_injury_feed.py` |
| `_make_teams()` with `home_last10_ortg=None` produces same result as before Phase 6                                   | regression  | `test_injury_feed.py` |

### Done When

- R-P6-01: `fetch_injuries("LAL")` returns an empty list (not an exception) when the ESPN endpoint returns a network error
- R-P6-02: `fetch_last10_ratings(["LAL", "NOP"])` returns an empty dict (not an exception) when the nba_api call fails
- R-P6-03: `_make_teams(g)` where `g.home_last10_ortg = 120.0` and `g.home_ortg = 115.0` produces a `home` `TeamInput` with an effective ortg contribution of `118.0` (recency-weighted: 0.60*120 + 0.40*115)
- R-P6-04: `_make_teams(g)` where `g.home_last10_ortg = None` produces identical result to a pre-Phase-6 `_make_teams()` call (backward compat)
- R-P6-05: `GameEntry` dataclass accepts all six last10 fields as optional `float | None` with default `None`
- R-P6-06: `update_with_live_ratings()` returns `{"success": False, "coverage": 0.0}` when both feeds fail, without raising an exception
- R-P6-07: `requirements.txt` includes `nba_api` as a new dependency

### Verification Command

```bash
python -m pytest test_injury_feed.py -v --tb=short && python -c "from injury_feed import fetch_injuries, fetch_last10_ratings; print('imports OK')" && ruff check injury_feed.py game_data.py run_tonight.py
```

---

## Phase 7: Nightly Calibration & Backtest Report

**Phase Type**: `module`

Builds the observability layer that lets us measure model accuracy over time. A SQLite predictions database logs every recommendation produced by `run_tonight.py`. The next day, `log_results.py` ingests actual game scores. A `backtest_report()` function computes Brier score and log loss per market type, by edge bucket, and by leg count — surfacing systematic biases before they compound over many nights.

### Changes

| Action | File                      | Description                                                                                                                                                                                                                                                                                                                                                  |
| ------ | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| CREATE | `calibration_log.py`      | SQLite schema for `predictions` and `actuals` tables. `log_prediction(date, game_id, bet_type, line, model_prob, blended_prob, edge, recommendation_rank)`. `log_actual(date, game_id, home_score, away_score)`. `backtest_report(lookback_days=30) -> BacktestReport`. `BacktestReport` dataclass with per-market Brier, log loss, win rate by edge bucket. |
| MODIFY | `run_tonight.py`          | In recommendations loop, call `calibration_log.log_prediction(...)` for each recommendation. Import behind `try/except` so logging failure never aborts a live run.                                                                                                                                                                                          |
| CREATE | `log_results.py`          | CLI script: `python log_results.py --date 2026-03-03 --scores "CHA 117 DAL 90, CLE 113 DET 109, ..."`. Parses score strings, calls `log_actual()` for each, prints coverage.                                                                                                                                                                                 |
| CREATE | `test_calibration_log.py` | Tests for schema creation, log/read round-trip, Brier score math, log loss math, edge bucket grouping.                                                                                                                                                                                                                                                       |

### Interface Contracts

**Database schema**

```sql
predictions(id, date, game_id, bet_type, line, model_prob,
            blended_prob, edge, rank, created_at)
actuals(id, date, game_id, home_score, away_score, created_at)
```

**`log_prediction(date, game_id, bet_type, line, model_prob, blended_prob, edge, rank=None)`**

- Inserts one row into predictions table
- `date`: ISO date string (YYYY-MM-DD)
- `bet_type`: "spread_home", "spread_away", "over", "under", "ml_home", "ml_away"

**`log_actual(date, game_id, home_score, away_score)`**

- Inserts one row into actuals table

**`backtest_report(lookback_days=30) -> BacktestReport`**

- Joins predictions + actuals on (date, game_id)
- Derives outcome (1/0) per bet_type from home_score/away_score vs line
- Computes Brier score: `mean((p_predicted - outcome)^2)`
- Computes log loss: `mean(-y*log(p) - (1-y)*log(1-p))`
- Groups by market type, by edge bucket ([2,4), [4,6), [6,8), 8+), and by total legs in same session

### Testing Strategy

| What                                                                     | Type        | File                      |
| ------------------------------------------------------------------------ | ----------- | ------------------------- |
| `log_prediction()` inserts row and `backtest_report()` reads it back     | unit        | `test_calibration_log.py` |
| Brier score of perfect predictions (p=1.0 → outcome=1) returns 0.0       | unit        | `test_calibration_log.py` |
| Log loss of 0.60 predicted, outcome=1 returns `-log(0.60) ≈ 0.511`       | unit        | `test_calibration_log.py` |
| `backtest_report()` groups correctly by market type (spread vs total)    | unit        | `test_calibration_log.py` |
| Logging failure (disk full) does NOT raise exception in `run_tonight.py` | unit (mock) | `test_calibration_log.py` |

### Done When

- R-P7-01: `log_prediction("2026-03-03", "SAS@PHI", "spread_away", 7.5, 0.75, 0.62, 6.5)` followed by `log_actual("2026-03-03", "SAS@PHI", 131, 91)` produces a `BacktestReport` entry where the bet is scored as a LOSS (PHI +7.5 did not cover 40-point SAS win)
- R-P7-02: Brier score of a prediction where `model_prob=1.0` and `outcome=1` is `0.0`
- R-P7-03: `backtest_report()` returns separate Brier/log-loss rows for `"spread"` and `"total"` market types
- R-P7-04: `run_tonight.py` calls `log_prediction()` for each recommendation without raising an exception when `calibration_log.py` is unavailable (import wrapped in try/except)
- R-P7-05: `log_results.py --date 2026-03-03 --scores "CHA 117 DAL 90"` inserts an actuals row for game_id="DAL@CHA" with `home_score=117, away_score=90`
- R-P7-06: `predictions.db` is created in the project root (not committed to git — add to `.gitignore`)

### Verification Command

```bash
python -m pytest test_calibration_log.py -v --tb=short && python log_results.py --help && ruff check calibration_log.py log_results.py run_tonight.py
```

---

## Risks & Mitigations

| Risk                                                  | Likelihood | Impact | Mitigation                                                                                                                                                         |
| ----------------------------------------------------- | ---------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Phase 3 vectorization degrades performance beyond 10s | Low        | Medium | Benchmark before/after: `time python -c "from simulator import simulate_game, TeamInput; ..."`. NumPy arrays still vectorized — overhead is array allocation only. |
| nba_api rate limiting causes Phase 6 to hang          | Medium     | Medium | Add 1s sleep between requests. Wrap in 10s timeout. Fail closed (return empty).                                                                                    |
| ESPN injury scraper breaks on HTML changes            | High       | Low    | Fail closed (return empty list). Manual entry remains the fallback. Log warning prominently.                                                                       |
| Phase 7 SQLite file permission issue on Windows       | Low        | Low    | Use `os.path.join(os.path.dirname(__file__), "predictions.db")` for path.                                                                                          |
| Phase 1 conference ceiling suppresses real edges      | Low        | Medium | Cap is per historical data. `_spread_confidence_cap()` only applies to underdog cover prob, not to ML or favorite ATS.                                             |

## Dependencies

### External Packages (Phase 6)

- `nba_api >= 1.4.0` — add to `requirements.txt`
- `requests` — already in requirements

### Internal Ordering

- Phase 3 must run after Phase 1 (uses graduated GARBAGE_TIERS in vectorized intensity)
- Phase 4 replaces the `_spread_confidence_cap()` helper added in Phase 1 with the `calibration.py` module — builder must remove the Phase 1 helper to avoid duplication
- Phase 6 `_make_teams()` recency weighting is additive to Phase 5 injury stacking — both apply simultaneously
- Phase 7 logging is purely additive to `run_tonight.py` — no changes to simulation logic
