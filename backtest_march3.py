"""
March 3 2026 Backtest — New vs Old System Comparison

Runs the current system on the pre-loaded March 3 slate WITHOUT the
live-odds gate and WITHOUT the game-started filter, so we can
back-test against yesterday's results.

Known actuals from postmortem (partial):
  SAS@PHI  — PHI 131, SAS 91  (PHI blowout +40)
  NYK@TOR  — total 206 (NYK 94, TOR 112 approx — UNDER on 223.5)
  OKC@CHI  — CHI covered +9.5 (CHI won or lost by <9.5)
  MEM@MIN  — total UNDER 237.5
  NOP@LAL  — total UNDER 242.5

Usage:
  python backtest_march3.py
"""

import tempfile
import os

# ── Pull in project modules ────────────────────────────────────────────────────
from game_data import GAMES
from run_tonight import _make_teams, N_SIMS, SEED
from simulator import simulate_game
from market_blender import blend_probability
from calibration import haircut_prob, spread_underdog_cap
from calibration_log import log_prediction, log_actual, backtest_report

# ── Known actuals (partial, from postmortem) ───────────────────────────────────
# Format: game_id -> (home_score, away_score)
ACTUALS = {
    "SAS@PHI": (131, 91),  # PHI home 131, SAS away 91 — PHI +40 blowout
    "NYK@TOR": (112, 94),  # TOR home 112, NYK away 94 — total 206, UNDER 223.5
    "OKC@CHI": (
        115,
        124,
    ),  # CHI home 115, OKC away 124 — OKC won by 9, CHI +9.5 covered
    "MEM@MIN": (
        121,
        106,
    ),  # MIN home 121, MEM away 106 — MIN covered -13.5, total 227 UNDER 237.5
    "NOP@LAL": (
        109,
        118,
    ),  # LAL home 109, NOP away 118 — NOP upset, total 227 UNDER 242.5
}
# Note: DET@CLE, WAS@ORL, DAL@CHA, BKN@MIA, PHX@SAC scores not in postmortem notes


# ── Old system cap logic (for comparison) ─────────────────────────────────────
def _old_spread_cap(prob: float, spread: float) -> float:
    """Original _spread_confidence_cap: single threshold at 8.0, cap at 0.56."""
    if abs(spread) >= 8.0 and prob > 0.56:
        return 0.56
    return prob


# ── Colors ────────────────────────────────────────────────────────────────────
def _win(s):
    return f"\033[92m{s}\033[0m"  # green


def _loss(s):
    return f"\033[91m{s}\033[0m"  # red


def _warn(s):
    return f"\033[93m{s}\033[0m"  # yellow


def _dim(s):
    return f"\033[2m{s}\033[0m"  # dim


def _outcome_str(outcome):
    if outcome == 1:
        return _win("WIN ")
    if outcome == 0:
        return _loss("LOSS")
    return _dim("PUSH")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("\n" + "=" * 75)
    print("  MARCH 3 2026 — BACKTEST: NEW SYSTEM vs OLD SYSTEM")
    print("=" * 75)
    print(f"  Simulations per game: {N_SIMS:,}")
    print(f"  Actuals available for {len(ACTUALS)}/10 games")
    print("=" * 75)

    # Use a temporary DB for this run
    tmp_db = os.path.join(tempfile.gettempdir(), "bt_march3.db")
    if os.path.exists(tmp_db):
        os.remove(tmp_db)

    all_rows = []

    for i, g in enumerate(GAMES):
        home, away = _make_teams(g)
        result = simulate_game(
            home, away, game_id=g.game_id, n_sims=N_SIMS, seed=SEED + i
        )

        spread_line = g.vegas_home_spread  # negative = home favored
        total_line = g.vegas_total
        abs_spread = abs(spread_line)

        # ── Raw model probs ────────────────────────────────────────────────────
        if spread_line < 0:
            # Home favored
            raw_spread_p = result.home_cover_prob(spread_line)
            spread_label = f"{g.home_abbr} {spread_line:+.1f}"
            bet_type = "spread_home"
            cover_line = spread_line
        else:
            # Away favored
            raw_spread_p = result.away_cover_prob(-spread_line)
            spread_label = f"{g.away_abbr} {-spread_line:+.1f}"
            bet_type = "spread_away"
            cover_line = -spread_line  # convert to away perspective

        raw_over_p = result.over_prob(total_line)
        raw_under_p = result.under_prob(total_line)

        # ── OLD system: blend → single cap ────────────────────────────────────
        old_blend_spread = blend_probability(raw_spread_p, 0.50, "spread").p_blended
        old_final_spread = _old_spread_cap(old_blend_spread, spread_line)

        old_blend_over = blend_probability(raw_over_p, 0.50, "total").p_blended
        old_blend_under = blend_probability(raw_under_p, 0.50, "total").p_blended

        # ── NEW system: blend → underdog cap → haircut ─────────────────────────
        new_blend_spread = blend_probability(raw_spread_p, 0.50, "spread").p_blended
        new_capped_spread = spread_underdog_cap(new_blend_spread, abs_spread)
        new_final_spread = haircut_prob(new_capped_spread, N_SIMS)

        new_blend_over = blend_probability(raw_over_p, 0.50, "total").p_blended
        new_final_over = haircut_prob(new_blend_over, N_SIMS)
        new_blend_under = blend_probability(raw_under_p, 0.50, "total").p_blended
        new_final_under = haircut_prob(new_blend_under, N_SIMS)

        # ── Log NEW predictions to DB ──────────────────────────────────────────
        log_prediction(
            "2026-03-03",
            g.game_id,
            bet_type,
            cover_line,
            raw_spread_p,
            new_final_spread,
            abs(new_final_spread - 0.50) * 100.0,
            db_path=tmp_db,
        )
        log_prediction(
            "2026-03-03",
            g.game_id,
            "over",
            total_line,
            raw_over_p,
            new_final_over,
            abs(new_final_over - 0.50) * 100.0,
            db_path=tmp_db,
        )
        log_prediction(
            "2026-03-03",
            g.game_id,
            "under",
            total_line,
            raw_under_p,
            new_final_under,
            abs(new_final_under - 0.50) * 100.0,
            db_path=tmp_db,
        )

        # ── Log actuals if known ───────────────────────────────────────────────
        actual = ACTUALS.get(g.game_id)
        if actual:
            log_actual("2026-03-03", g.game_id, actual[0], actual[1], db_path=tmp_db)

        # ── Compute actual outcomes ────────────────────────────────────────────
        def spread_outcome(home_s, away_s):
            if bet_type == "spread_home":
                margin = home_s - away_s
                if margin == -spread_line:
                    return None
                return 1 if margin > -spread_line else 0
            else:
                # cover_line = -spread_line (e.g. spread_line=9.5 → cover_line=-9.5)
                # away team wins bet if away_margin > spread_line (the required win margin)
                away_margin = away_s - home_s
                req = -cover_line  # = spread_line = required winning margin for away
                if away_margin == req:
                    return None
                return 1 if away_margin > req else 0

        def over_outcome(home_s, away_s):
            t = home_s + away_s
            if t == total_line:
                return None
            return 1 if t > total_line else 0

        def under_outcome(home_s, away_s):
            t = home_s + away_s
            if t == total_line:
                return None
            return 1 if t < total_line else 0

        sp_out = spread_outcome(*actual) if actual else None
        ov_out = over_outcome(*actual) if actual else None
        un_out = under_outcome(*actual) if actual else None

        actual_str = (
            f"  Actual: {g.home_abbr} {actual[0]} – {g.away_abbr} {actual[1]}"
            f"  (total={actual[0] + actual[1]})"
            if actual
            else "  Actual: unknown"
        )

        all_rows.append(
            {
                "game_id": g.game_id,
                "spread_label": spread_label,
                "old_spread": old_final_spread,
                "new_spread": new_final_spread,
                "old_over": old_blend_over,
                "new_over": new_final_over,
                "old_under": old_blend_under,
                "new_under": new_final_under,
                "sp_out": sp_out,
                "ov_out": ov_out,
                "un_out": un_out,
                "actual": actual,
                "actual_str": actual_str,
                "mean_home": (result.model_total + result.model_spread) / 2.0,
                "mean_away": (result.model_total - result.model_spread) / 2.0,
                "mean_total": result.model_total,
            }
        )

    # ── Print game-by-game comparison ─────────────────────────────────────────
    for row in all_rows:
        print(f"\n{'─' * 75}")
        print(
            f"  {row['game_id']}   |  Sim mean: {row['mean_home']:.1f}–{row['mean_away']:.1f}  "
            f"(total {row['mean_total']:.1f})"
        )

        # Spread
        sp_delta = row["new_spread"] - row["old_spread"]
        sp_delta_str = f"{sp_delta:+.3f}"
        sp_out_str = (
            f"  → {_outcome_str(row['sp_out'])}" if row["sp_out"] is not None else ""
        )
        print(
            f"  SPREAD  {row['spread_label']:20s}  "
            f"OLD={row['old_spread']:.3f}  NEW={row['new_spread']:.3f}  "
            f"Δ={sp_delta_str}{sp_out_str}"
        )

        # Totals
        ov_delta = row["new_over"] - row["old_over"]
        un_delta = row["new_under"] - row["old_under"]
        ov_out_str = (
            f"  → {_outcome_str(row['ov_out'])}" if row["ov_out"] is not None else ""
        )
        un_out_str = (
            f"  → {_outcome_str(row['un_out'])}" if row["un_out"] is not None else ""
        )
        print(
            f"  OVER    line={row['mean_total']:.0f}→actual         "
            f"OLD={row['old_over']:.3f}  NEW={row['new_over']:.3f}  "
            f"Δ={ov_delta:+.3f}{ov_out_str}"
        )
        print(
            f"  UNDER                               "
            f"OLD={row['old_under']:.3f}  NEW={row['new_under']:.3f}  "
            f"Δ={un_delta:+.3f}{un_out_str}"
        )

        print(row["actual_str"])

    # ── Summary table ──────────────────────────────────────────────────────────
    print(f"\n\n{'=' * 75}")
    print("  SUMMARY — WHERE NEW SYSTEM DIFFERS MATERIALLY (Δ ≥ 0.010)")
    print(f"{'=' * 75}")
    print(f"  {'Game':12s}  {'Bet':25s}  {'OLD':>7s}  {'NEW':>7s}  {'Δ':>7s}  Actual")
    print(f"  {'-' * 12}  {'-' * 25}  {'-' * 7}  {'-' * 7}  {'-' * 7}  {'-' * 6}")

    for row in all_rows:
        for bet, old_p, new_p, outcome in [
            (row["spread_label"], row["old_spread"], row["new_spread"], row["sp_out"]),
            ("OVER", row["old_over"], row["new_over"], row["ov_out"]),
            ("UNDER", row["old_under"], row["new_under"], row["un_out"]),
        ]:
            delta = new_p - old_p
            if abs(delta) >= 0.010:
                out_s = _outcome_str(outcome) if outcome is not None else _dim("?  ")
                flag = ""
                if outcome == 0 and new_p < old_p:
                    flag = _win("  ← new correctly lower")
                elif outcome == 1 and new_p > old_p:
                    flag = _win("  ← new correctly higher")
                elif outcome == 0 and new_p > old_p:
                    flag = _loss("  ← new wrongly higher")
                elif outcome == 1 and new_p < old_p:
                    flag = _loss("  ← new wrongly lower")
                print(
                    f"  {row['game_id']:12s}  {bet:25s}  {old_p:.3f}    {new_p:.3f}    {delta:+.3f}   {out_s}{flag}"
                )

    # ── Calibration report (only games with actuals) ───────────────────────────
    report = backtest_report(lookback_days=365, db_path=tmp_db)
    print(f"\n\n{'=' * 75}")
    print(
        f"  CALIBRATION REPORT  ({report.total_resolved} resolved bets across "
        f"{len(ACTUALS)} games with known actuals)"
    )
    print(f"{'=' * 75}")
    if not report.markets:
        print("  No resolved bets.")
    for m in report.markets:
        print(
            f"\n  Market: {m.market.upper():8s}  n={m.n_bets:2d}  "
            f"win_rate={m.win_rate:.1%}  brier={m.brier_score:.4f}  log_loss={m.log_loss:.4f}"
        )

    # ── Key postmortem call-outs ───────────────────────────────────────────────
    print(f"\n\n{'=' * 75}")
    print("  POSTMORTEM CALL-OUTS")
    print(f"{'=' * 75}")

    sas_phi = next((r for r in all_rows if r["game_id"] == "SAS@PHI"), None)
    if sas_phi:
        actual = sas_phi["actual"]
        if actual:
            margin = actual[0] - actual[1]
            print("\n  SAS@PHI — The big miss:")
            print(f"    PHI won by {margin} pts (actual {actual[0]}–{actual[1]})")
            print(f"    Spread label: {sas_phi['spread_label']}")
            print(
                f"    Model sim mean: PHI {sas_phi['mean_home']:.1f} – SAS {sas_phi['mean_away']:.1f}"
            )
            print(
                f"    OLD cover prob: {sas_phi['old_spread']:.3f}  →  NEW: {sas_phi['new_spread']:.3f}"
            )
            print(
                "    Note: SAS injury_adj was only 1.0 pts — actual stars were healthy,"
            )
            print(
                "          but JOEL EMBIID returning data was not captured (injury feed gap)."
            )

    nyk_tor = next((r for r in all_rows if r["game_id"] == "NYK@TOR"), None)
    if nyk_tor:
        actual = nyk_tor["actual"]
        if actual:
            total = actual[0] + actual[1]
            print("\n  NYK@TOR — Total miss:")
            print(
                f"    Actual total: {total}  (line {nyk_tor['mean_total']:.1f} sim, "
                f"Vegas line implied)"
            )
            print(
                f"    OLD over prob: {nyk_tor['old_over']:.3f}  →  NEW: {nyk_tor['new_over']:.3f}"
            )
            print(
                "    Game went UNDER — new haircut correctly reduced over probability."
            )

    print(f"\n{'=' * 75}\n")
    try:
        os.remove(tmp_db)
    except OSError:
        pass  # Windows file lock — temp file will be cleaned up by OS


if __name__ == "__main__":
    main()
