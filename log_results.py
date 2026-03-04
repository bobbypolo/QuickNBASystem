"""
CLI script for ingesting nightly game actuals into the predictions database.

Usage:
    python log_results.py --date 2026-03-03 --scores "CHA 117 DAL 90, CLE 113 DET 109"
"""

import argparse
import re
import sys

from calibration_log import log_actual
from game_data import GAMES


def _find_game_id(team1: str, team2: str) -> str | None:
    """Find game_id for a pair of teams from tonight's GAMES slate."""
    t1, t2 = team1.upper(), team2.upper()
    for g in GAMES:
        if {g.home_abbr.upper(), g.away_abbr.upper()} == {t1, t2}:
            return g.game_id
    # Fall back to constructing game_id as "away@home"
    # Try both orderings
    for g in GAMES:
        if g.home_abbr.upper() == t1 and g.away_abbr.upper() == t2:
            return g.game_id
        if g.home_abbr.upper() == t2 and g.away_abbr.upper() == t1:
            return g.game_id
    return None


def parse_score_string(score_str: str) -> list[tuple[str, int, str, int]]:
    """Parse score strings like 'CHA 117 DAL 90' into (team1, score1, team2, score2) tuples."""
    results = []
    # Each score entry: ABBR NNN ABBR NNN
    pattern = r"([A-Z]{2,4})\s+(\d+)\s+([A-Z]{2,4})\s+(\d+)"
    for m in re.finditer(pattern, score_str.upper()):
        team1, score1, team2, score2 = (
            m.group(1),
            int(m.group(2)),
            m.group(3),
            int(m.group(4)),
        )
        results.append((team1, score1, team2, score2))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Log nightly NBA game results")
    parser.add_argument("--date", required=True, help="Game date (YYYY-MM-DD)")
    parser.add_argument(
        "--scores",
        required=True,
        help='Comma-separated scores: "CHA 117 DAL 90, CLE 113 DET 109"',
    )
    parser.add_argument(
        "--db", default=None, help="Override database path (for testing)"
    )
    args = parser.parse_args()

    entries = parse_score_string(args.scores)
    if not entries:
        print("ERROR: No valid score strings parsed. Format: 'ABBR NNN ABBR NNN'")
        return 1

    logged = 0
    for team1, score1, team2, score2 in entries:
        game_id = _find_game_id(team1, team2)
        if game_id is None:
            print(f"WARN: No game found for {team1} vs {team2} — skipping")
            continue

        # Determine home/away from game_id "AWAY@HOME"
        parts = game_id.split("@")
        if len(parts) != 2:
            print(f"WARN: Unexpected game_id format {game_id} — skipping")
            continue
        away_abbr, home_abbr = parts[0].upper(), parts[1].upper()

        if home_abbr == team1:
            home_score, away_score = score1, score2
        elif home_abbr == team2:
            home_score, away_score = score2, score1
        else:
            print(f"WARN: Could not determine home/away for {game_id} — skipping")
            continue

        kwargs = {}
        if args.db:
            kwargs["db_path"] = args.db
        log_actual(args.date, game_id, home_score, away_score, **kwargs)
        print(f"Logged: {game_id} — {home_abbr} {home_score}, {away_abbr} {away_score}")
        logged += 1

    print(f"Done: {logged}/{len(entries)} results logged for {args.date}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
