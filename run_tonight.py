"""
NBA Monte Carlo - Tonight's Full Slate Runner
=============================================
Run: python run_tonight.py

Simulates all 10 games, outputs:
  - Win probability, true spread, true total
  - Blended probabilities (model + market consensus)
  - Edge vs Vegas lines (threshold: 2.5pt spread / 2pt total)
  - Top recommended bets
  - Sample SGP and multi-game parlay analysis
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List
from zoneinfo import ZoneInfo

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from calibration import haircut_prob, spread_underdog_cap
from fatigue import ScheduleContext, compute_fatigue
from game_data import GAMES, GameEntry, print_slate_summary, update_with_live_odds  # noqa: F401
from market_blender import blend_probability
from parlay import ParlayLeg, evaluate_mg_parlay, evaluate_sgp, print_parlay_result
from simulator import (
    SimResult,
    TeamInput,
    american_to_implied_prob,
    devig_pair,
    format_american,
    simulate_game,
)


# ── Calibration log helper ────────────────────────────────────────────────────
def _try_log_prediction(*args, **kwargs) -> None:
    """Call log_prediction() wrapped in try/except so logging never aborts a live run."""
    try:
        from calibration_log import log_prediction

        log_prediction(*args, **kwargs)
    except Exception:
        pass


# ── Config ────────────────────────────────────────────────────────────────────
N_SIMS = 10_000
SEED = 42
SPREAD_EDGE_THRESHOLD = 2.5  # minimum point edge to flag as a recommended bet
TOTAL_EDGE_THRESHOLD = 2.0  # minimum point edge on totals
MIN_WIN_PROB_BET = 0.52  # don't recommend ML bets below this threshold
MIN_COVER_PROB_BET = 0.535  # require beat-vig-ish hit rate for spread/total plays
DEFAULT_LIVE_ODDS_COVERAGE = 0.90
NBA_TZ = ZoneInfo("America/New_York")
STARTED_GAME_LOOKBACK_MINUTES = (
    5  # games tipped off more than N minutes ago are excluded
)
MAX_RECOMMENDED_PARLAY_LEGS = 4  # auto-parlay capped at this many legs
MAX_LOTTO_PARLAY_LEGS = 7  # 7+ legs labeled LOTTERY


# ── Safety Rail helpers ───────────────────────────────────────────────────────
def is_game_started(g: GameEntry, now_et: datetime) -> bool:
    """Return True if the game tipped off more than STARTED_GAME_LOOKBACK_MINUTES ago."""
    tipoff_et = _parse_tipoff_datetime_et(g, now_et)
    return tipoff_et < now_et - timedelta(minutes=STARTED_GAME_LOOKBACK_MINUTES)


def _classify_parlay(n_legs: int) -> str:
    """Classify a parlay by leg count."""
    if n_legs >= MAX_LOTTO_PARLAY_LEGS:
        return "LOTTERY"
    if n_legs >= 5:
        return "HIGH_RISK"
    return "STANDARD"


# ── Injury stacking ───────────────────────────────────────────────────────────
def injury_stacking_multiplier(n_out: int) -> float:
    """Non-linear penalty: missing 4 players > 4x missing 1.

    n=0 or 1 → 1.0x, n=2 → 1.15x, n=3 → 1.30x, n=4 → 1.45x, n=5 → 1.60x
    """
    if n_out <= 1:
        return 1.0
    return 1.0 + 0.15 * (n_out - 1)


# ── Build TeamInput from GameEntry ────────────────────────────────────────────
def _make_teams(g: GameEntry):
    # Compute fatigue multipliers from schedule context
    home_ctx = ScheduleContext(
        is_b2b=g.home_is_b2b,
        is_3in4=g.home_is_3in4,
        rest_days=g.home_rest_days,
        opponent_rest_days=g.away_rest_days,
        travel_miles=g.home_travel_miles,
    )
    away_ctx = ScheduleContext(
        is_b2b=g.away_is_b2b,
        is_3in4=g.away_is_3in4,
        rest_days=g.away_rest_days,
        opponent_rest_days=g.home_rest_days,
        travel_miles=g.away_travel_miles,
    )
    home_fatigue = compute_fatigue(home_ctx)
    away_fatigue = compute_fatigue(away_ctx)

    # Recency-weighted ratings (Phase 6): blend last-10 with season average
    _rw = 0.60
    home_ortg = (
        _rw * g.home_last10_ortg + (1 - _rw) * g.home_ortg
        if g.home_last10_ortg is not None
        else g.home_ortg
    )
    home_drtg = (
        _rw * g.home_last10_drtg + (1 - _rw) * g.home_drtg
        if g.home_last10_drtg is not None
        else g.home_drtg
    )
    home_pace = (
        _rw * g.home_last10_pace + (1 - _rw) * g.home_pace
        if g.home_last10_pace is not None
        else g.home_pace
    )
    away_ortg = (
        _rw * g.away_last10_ortg + (1 - _rw) * g.away_ortg
        if g.away_last10_ortg is not None
        else g.away_ortg
    )
    away_drtg = (
        _rw * g.away_last10_drtg + (1 - _rw) * g.away_drtg
        if g.away_last10_drtg is not None
        else g.away_drtg
    )
    away_pace = (
        _rw * g.away_last10_pace + (1 - _rw) * g.away_pace
        if g.away_last10_pace is not None
        else g.away_pace
    )

    home = TeamInput(
        name=g.home_name,
        abbr=g.home_abbr,
        pace=home_pace,
        ortg=home_ortg,
        drtg=home_drtg,
        injury_adj=g.home_injury_adj * injury_stacking_multiplier(g.home_n_key_out),
        pace_mult=home_fatigue.pace_mult,
        ortg_mult=home_fatigue.ortg_mult,
        drtg_mult=home_fatigue.drtg_mult,
    )
    away = TeamInput(
        name=g.away_name,
        abbr=g.away_abbr,
        pace=away_pace,
        ortg=away_ortg,
        drtg=away_drtg,
        injury_adj=g.away_injury_adj * injury_stacking_multiplier(g.away_n_key_out),
        pace_mult=away_fatigue.pace_mult,
        ortg_mult=away_fatigue.ortg_mult,
        drtg_mult=away_fatigue.drtg_mult,
    )
    return home, away


def _parse_tipoff_datetime_et(g: GameEntry, now_et: datetime) -> datetime:
    """Parse tip-off text like '8:00 PM ET' or '8:00 PM ET (NBC/Peacock)'."""
    raw = g.tip_off_et.split("(")[0].replace("ET", "").strip()
    parsed_time = datetime.strptime(raw, "%I:%M %p")
    return now_et.replace(
        hour=parsed_time.hour,
        minute=parsed_time.minute,
        second=0,
        microsecond=0,
    )


def games_starting_within_minutes(
    games: List[GameEntry], minutes: int
) -> List[GameEntry]:
    """Return games with tip-off in the next N minutes (ET)."""
    now_et = datetime.now(NBA_TZ)
    selected = []
    for g in games:
        tipoff_et = _parse_tipoff_datetime_et(g, now_et)
        delta_minutes = (tipoff_et - now_et).total_seconds() / 60.0
        if 0 < delta_minutes <= minutes:
            selected.append(g)
    return selected


# ── Print Game Result ─────────────────────────────────────────────────────────
def print_game_result(g: GameEntry, result: SimResult, recommendations: list) -> None:
    print(f"\n{'═' * 65}")
    print(f"  {g.away_abbr} @ {g.home_abbr}   [{g.tip_off_et}]")
    print(f"{'═' * 65}")

    # Injury notes
    if g.away_injury_adj > 0:
        print(f"  ⚠️  {g.away_abbr} injuries: {g.away_injury_notes[:70]}")
    if g.home_injury_adj > 0:
        print(f"  ⚠️  {g.home_abbr} injuries: {g.home_injury_notes[:70]}")

    print()

    # Win probability (raw model)
    h_wp = result.home_win_prob
    a_wp = result.away_win_prob
    h_ml = result.home_ml_american()
    a_ml = result.away_ml_american()

    # Market blending for win probability
    blended_h_wp = h_wp
    if g.vegas_home_ml is not None and g.vegas_away_ml is not None:
        h_implied = american_to_implied_prob(g.vegas_home_ml)
        a_implied = american_to_implied_prob(g.vegas_away_ml)
        fair_h, _ = devig_pair(h_implied, a_implied)
        blend_res = blend_probability(h_wp, fair_h, "moneyline")
        blended_h_wp = blend_res.p_blended
        print(
            f"  WIN PROB: {g.home_abbr} {h_wp:.1%} ({format_american(h_ml)})  |  {g.away_abbr} {a_wp:.1%} ({format_american(a_ml)})"
        )
        print(
            f"  BLENDED: {g.home_abbr} {blended_h_wp:.1%}  |  {g.away_abbr} {1.0 - blended_h_wp:.1%}  (market: {fair_h:.1%})"
        )
    else:
        print(
            f"  WIN PROB: {g.home_abbr} {h_wp:.1%} ({format_american(h_ml)})  |  {g.away_abbr} {a_wp:.1%} ({format_american(a_ml)})"
        )

    # Spread analysis
    model_s = result.model_spread
    vegas_s = g.vegas_home_spread
    cover_threshold = -vegas_s
    spread_diff = model_s - cover_threshold

    if model_s > 0:
        model_spread_str = f"{g.home_abbr} -{model_s:.1f}"
    else:
        model_spread_str = f"{g.away_abbr} -{abs(model_s):.1f}"

    if vegas_s < 0:
        vegas_spread_str = f"{g.home_abbr} {vegas_s:.1f}"
    else:
        vegas_spread_str = f"{g.away_abbr} -{vegas_s:.1f}"

    # Blend cover probabilities (Vegas spread implies ~50/50)
    raw_h_cover = result.home_cover_prob(vegas_s)
    blended_h_cover = blend_probability(raw_h_cover, 0.50, "spread").p_blended

    spread_flag = ""
    if abs(spread_diff) >= SPREAD_EDGE_THRESHOLD:
        if spread_diff > 0:
            p_cover = haircut_prob(
                spread_underdog_cap(blended_h_cover, abs(vegas_s)), N_SIMS
            )
            if p_cover >= MIN_COVER_PROB_BET:
                spread_flag = f"  ✅ EDGE: BET {g.home_abbr} {vegas_s:+.1f} ({abs(spread_diff):.1f}pt edge, p={p_cover:.1%})"
                recommendations.append(
                    {
                        "type": "SPREAD",
                        "game": g.game_id,
                        "bet": f"{g.home_abbr} {vegas_s:+.1f}",
                        "edge": abs(spread_diff),
                        "result": result,
                        "leg": ParlayLeg(
                            g.game_id,
                            "home_spread",
                            vegas_s,
                            f"{g.home_abbr} {vegas_s:+.1f}",
                        ),
                    }
                )
        else:
            away_line = -vegas_s
            away_str = f"{g.away_abbr} {away_line:+.1f}"
            raw_a_cover = result.away_cover_prob(away_line)
            p_cover = haircut_prob(
                spread_underdog_cap(
                    blend_probability(raw_a_cover, 0.50, "spread").p_blended,
                    abs(away_line),
                ),
                N_SIMS,
            )
            if p_cover >= MIN_COVER_PROB_BET:
                spread_flag = f"  ✅ EDGE: BET {away_str} ({abs(spread_diff):.1f}pt edge, p={p_cover:.1%})"
                recommendations.append(
                    {
                        "type": "SPREAD",
                        "game": g.game_id,
                        "bet": away_str,
                        "edge": abs(spread_diff),
                        "result": result,
                        "leg": ParlayLeg(
                            g.game_id,
                            "away_spread",
                            away_line,
                            away_str,
                        ),
                    }
                )

    print(
        f"  SPREAD:   Model {model_spread_str:15s} | Vegas {vegas_spread_str:15s}{spread_flag}"
    )

    # Total analysis
    model_t = result.model_total
    vegas_t = g.vegas_total
    total_diff = model_t - vegas_t

    # Blend O/U probabilities
    raw_over_p = result.over_prob(vegas_t)
    blended_over_p = blend_probability(raw_over_p, 0.50, "total").p_blended
    blended_under_p = 1.0 - blended_over_p

    total_flag = ""
    if abs(total_diff) >= TOTAL_EDGE_THRESHOLD:
        ou = "OVER" if total_diff > 0 else "UNDER"
        p_total = blended_over_p if ou == "OVER" else blended_under_p
        if p_total >= MIN_COVER_PROB_BET:
            total_flag = f"  ✅ EDGE: BET {ou} {vegas_t} ({abs(total_diff):.1f}pt edge, p={p_total:.1%})"
            recommendations.append(
                {
                    "type": "TOTAL",
                    "game": g.game_id,
                    "bet": f"{ou} {vegas_t}",
                    "edge": abs(total_diff),
                    "result": result,
                    "leg": ParlayLeg(
                        g.game_id,
                        "over" if ou == "OVER" else "under",
                        vegas_t,
                        f"{ou} {vegas_t}",
                    ),
                }
            )

    print(
        f"  TOTAL:    Model {model_t:.1f}          | Vegas {vegas_t:<15.1f}{total_flag}"
    )

    # Cover probabilities at the Vegas line (blended)
    a_cover_p = blend_probability(
        result.away_cover_prob(-vegas_s), 0.50, "spread"
    ).p_blended
    push_p = max(0.0, 1.0 - blended_over_p - blended_under_p)
    print(
        f"  COVER P:  {g.home_abbr} {vegas_s:+.1f} = {blended_h_cover:.1%}  |  {g.away_abbr} {-vegas_s:+.1f} = {a_cover_p:.1%}  |  O/U {vegas_t}: O {blended_over_p:.1%} / U {blended_under_p:.1%} / Push {push_p:.1%}"
    )

    if g.notes:
        print(f"  📝 {g.notes}")


# ── Main Runner ───────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--next-hour",
        action="store_true",
        help="Only simulate games starting in the next 60 minutes (ET).",
    )
    parser.add_argument(
        "--live-coverage",
        type=float,
        default=float(os.getenv("MIN_LIVE_ODDS_COVERAGE", DEFAULT_LIVE_ODDS_COVERAGE)),
        help="Minimum required spread+total live-odds coverage (0.0-1.0).",
    )
    args = parser.parse_args()

    require_live_odds = os.getenv("REQUIRE_LIVE_ODDS", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }

    print("Fetching live odds...")
    live_status = update_with_live_odds(min_coverage=args.live_coverage)
    if require_live_odds and not live_status.get("success", False):
        stale = ", ".join(live_status.get("stale_game_ids", [])[:8])
        print("Live odds requirement not met. Aborting simulation run.")
        print(
            f"Coverage: {live_status.get('coverage', 0.0):.1%} "
            f"(required >= {args.live_coverage:.1%})"
        )
        if stale:
            print(f"Stale/missing odds games: {stale}")
        raise SystemExit(1)

    games_to_run = list(GAMES)
    if args.next_hour:
        games_to_run = games_starting_within_minutes(games_to_run, 60)
        if not games_to_run:
            print("No games starting in the next 60 minutes ET. Exiting.")
            return

    # Filter out games already in progress
    now_et = datetime.now(NBA_TZ)
    filtered_games = []
    for g in games_to_run:
        if is_game_started(g, now_et):
            print(f"⛔ SKIPPED (game in progress): {g.game_id}")
        else:
            filtered_games.append(g)
    games_to_run = filtered_games

    print_slate_summary(games_to_run)
    print(f"Running {N_SIMS:,} Monte Carlo simulations per game...\n")

    results: Dict[str, SimResult] = {}
    recommendations: list = []

    # Simulate selected games
    for i, g in enumerate(games_to_run):
        home, away = _make_teams(g)
        result = simulate_game(
            home, away, game_id=g.game_id, n_sims=N_SIMS, seed=SEED + i
        )
        results[g.game_id] = result
        print_game_result(g, result, recommendations)

    # ── Recommendations Summary ───────────────────────────────────────────────
    print(f"\n\n{'═' * 65}")
    print("  RECOMMENDED BETS  (Edge ≥ threshold)")
    print(f"{'═' * 65}")

    if not recommendations:
        print("  No strong edges found tonight. Consider passing.")
    else:
        recs_sorted = sorted(recommendations, key=lambda x: x["edge"], reverse=True)
        for r in recs_sorted:
            result: SimResult = r["result"]
            leg: ParlayLeg = r["leg"]
            # Get actual cover probability (blended)
            if r["type"] == "SPREAD":
                if leg.bet_type == "home_spread":
                    raw_p = result.home_cover_prob(leg.line)
                else:
                    raw_p = result.away_cover_prob(leg.line)
                p = blend_probability(raw_p, 0.50, "spread").p_blended
            else:
                if leg.bet_type == "over":
                    raw_p = result.over_prob(leg.line)
                else:
                    raw_p = result.under_prob(leg.line)
                p = blend_probability(raw_p, 0.50, "total").p_blended

            print(
                f"  [{r['type']:6s}] {r['game']:8s}  {r['bet']:25s}  edge={r['edge']:.1f}pt  p={p:.1%}"
            )
            # Log for backtest calibration (fails silently if unavailable)
            bt = (
                "spread_home"
                if leg.bet_type == "home_spread"
                else ("spread_away" if leg.bet_type == "away_spread" else leg.bet_type)
            )
            _try_log_prediction(
                datetime.now().strftime("%Y-%m-%d"),
                r["game"],
                bt,
                leg.line,
                raw_p,
                p,
                r["edge"],
                rank=recs_sorted.index(r) + 1,
            )

    # ── Parlay Analysis ───────────────────────────────────────────────────────
    print(f"\n\n{'═' * 65}")
    print("  PARLAY ANALYSIS")
    print(f"{'═' * 65}")

    # Auto-build best MG parlay from top recommendations (max 3 legs, spread only)
    spread_recs = [r for r in recommendations if r["type"] == "SPREAD"]
    total_recs = [r for r in recommendations if r["type"] == "TOTAL"]
    top_spread = sorted(spread_recs, key=lambda x: x["edge"], reverse=True)[:3]

    # Multi-game parlay: top spread picks
    if len(top_spread) >= 2:
        mg_legs = [r["leg"] for r in top_spread]
        mg_result = evaluate_mg_parlay(results, mg_legs)
        print("\n  Auto-built MG Parlay (top spread edges):")
        print_parlay_result(mg_result)

    # SGP examples for highest-confidence games (blowouts)
    # WAS@ORL SGP: Magic ML + Under
    if "WAS@ORL" in results:
        g_orl = next((g for g in games_to_run if g.game_id == "WAS@ORL"), None)
        if g_orl is None:
            g_orl = next(g for g in GAMES if g.game_id == "WAS@ORL")
        sgp_legs_orl = [
            ParlayLeg("WAS@ORL", "home_ml", 0.0, "Orlando ML"),
            ParlayLeg(
                "WAS@ORL", "under", g_orl.vegas_total, f"Under {g_orl.vegas_total}"
            ),
        ]
        sgp_orl = evaluate_sgp(results, sgp_legs_orl)
        print(f"\n  SGP Example — WAS @ ORL (Magic ML + Under {g_orl.vegas_total}):")
        print_parlay_result(sgp_orl)

    # MEM@MIN SGP: Wolves -13.5 + Over
    if "MEM@MIN" in results:
        g_min = next((g for g in games_to_run if g.game_id == "MEM@MIN"), None)
        if g_min is None:
            g_min = next(g for g in GAMES if g.game_id == "MEM@MIN")
        sgp_legs_min = [
            ParlayLeg(
                "MEM@MIN",
                "home_spread",
                g_min.vegas_home_spread,
                f"MIN {g_min.vegas_home_spread:+.1f}",
            ),
            ParlayLeg(
                "MEM@MIN", "over", g_min.vegas_total, f"Over {g_min.vegas_total}"
            ),
        ]
        sgp_min = evaluate_sgp(results, sgp_legs_min)
        print(
            f"\n  SGP Example — MEM @ MIN (Wolves {g_min.vegas_home_spread:+.1f} + Over {g_min.vegas_total}):"
        )
        print_parlay_result(sgp_min)

    # If we have spread + total recs in same game, show SGP
    game_ids_with_both = set(r["game"] for r in spread_recs) & set(
        r["game"] for r in total_recs
    )
    for gid in list(game_ids_with_both)[:1]:
        s_leg = next(r["leg"] for r in spread_recs if r["game"] == gid)
        t_leg = next(r["leg"] for r in total_recs if r["game"] == gid)
        sgp_auto = evaluate_sgp(results, [s_leg, t_leg])
        print(f"\n  SGP Example — {gid} (auto: spread + total edge):")
        print_parlay_result(sgp_auto)

    print(f"\n{'═' * 65}")
    print("  ✅ All simulations complete. Good luck tonight.")
    print(f"{'═' * 65}\n")


if __name__ == "__main__":
    main()
