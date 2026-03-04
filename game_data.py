"""
    print(f"  NBA TONIGHT - MARCH 3, 2026  |  {len(slate)} GAMES")
Pre-loaded team stats, injury adjustments, and Vegas lines.
Stats source: NBAstuffer.com / Basketball-Reference 2025-26 season.
Injury source: ESPN, Yahoo Sports, Athlon Sports (as of March 3, 2026).
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import os
import time
import requests
from dotenv import load_dotenv


@dataclass
class GameEntry:
    """One game's full data: teams, lines, context."""

    game_id: str
    tip_off_et: str
    away_name: str
    away_abbr: str
    away_pace: float
    away_ortg: float
    away_drtg: float
    away_injury_adj: float  # pts to subtract from away ortg
    away_injury_notes: str
    home_name: str
    home_abbr: str
    home_pace: float
    home_ortg: float
    home_drtg: float
    home_injury_adj: float  # pts to subtract from home ortg
    home_injury_notes: str
    vegas_home_spread: float  # e.g. -7.5 means home favored by 7.5
    vegas_total: float  # o/u line
    vegas_home_ml: Optional[int] = None
    vegas_away_ml: Optional[int] = None
    notes: str = ""
    # Schedule context (Phase 5 — fatigue)
    home_is_b2b: bool = False
    home_is_3in4: bool = False
    home_rest_days: float = 1.0
    home_travel_miles: float = 0.0
    away_is_b2b: bool = False
    away_is_3in4: bool = False
    away_rest_days: float = 1.0
    away_travel_miles: float = 0.0
    # Injury stacking (Phase 5)
    home_n_key_out: int = 0  # count of key players confirmed out for home team
    away_n_key_out: int = 0  # count of key players confirmed out for away team
    # Last-10-game ratings (Phase 6 — auto-populated by update_with_live_ratings)
    home_last10_ortg: Optional[float] = None
    home_last10_drtg: Optional[float] = None
    home_last10_pace: Optional[float] = None
    away_last10_ortg: Optional[float] = None
    away_last10_drtg: Optional[float] = None
    away_last10_pace: Optional[float] = None


# ── Tonight's Slate ───────────────────────────────────────────────────────────
GAMES: List[GameEntry] = [
    # ─── 7:00 PM ET ──────────────────────────────────────────────────────────
    GameEntry(
        game_id="DAL@CHA",
        tip_off_et="7:00 PM ET",
        away_name="Dallas Mavericks",
        away_abbr="DAL",
        away_pace=101.7,
        away_ortg=111.0,
        away_drtg=114.7,
        away_injury_adj=7.5,  # Kyrie OUT, Cooper Flagg doubtful, Klay questionable, Lively OUT
        away_injury_notes="OUT: Kyrie Irving, Dereck Lively II, Naji Marshall, Marvin Bagley. DOUBTFUL: Cooper Flagg (midfoot), Klay Thompson (hip)",
        home_name="Charlotte Hornets",
        home_abbr="CHA",
        home_pace=97.4,
        home_ortg=118.6,
        home_drtg=115.5,
        home_injury_adj=2.0,  # Coby White OUT
        home_injury_notes="OUT: Coby White (calf - load management)",
        vegas_home_spread=-12.5,
        vegas_total=231.5,
        vegas_home_ml=-650,
        vegas_away_ml=475,
        notes="Dallas massively shorthanded. Flagg doubtful with midfoot sprain.",
    ),
    GameEntry(
        game_id="DET@CLE",
        tip_off_et="7:00 PM ET",
        away_name="Detroit Pistons",
        away_abbr="DET",
        away_pace=99.9,
        away_ortg=116.9,
        away_drtg=109.0,
        away_injury_adj=0.0,
        away_injury_notes="Full roster available",
        home_name="Cleveland Cavaliers",
        home_abbr="CLE",
        home_pace=100.3,
        home_ortg=118.2,
        home_drtg=114.0,
        home_injury_adj=6.5,  # Donovan Mitchell OUT
        home_injury_notes="OUT: Donovan Mitchell (groin). DTD: Dean Wade (right ankle sprain)",
        vegas_home_spread=2.5,  # Detroit road favorite (positive = home is the dog)
        vegas_total=227.5,
        notes="Detroit (45-14) is road favorite due to Mitchell OUT. Unusual situation.",
    ),
    GameEntry(
        game_id="WAS@ORL",
        tip_off_et="7:00 PM ET",
        away_name="Washington Wizards",
        away_abbr="WAS",
        away_pace=101.1,
        away_ortg=110.7,
        away_drtg=121.3,
        away_injury_adj=4.0,  # Multiple role players OUT
        away_injury_notes="OUT: Anthony Gill (illness), Jamir Watkins (ankle), Tristan Vukcevic (thigh), Kyshawn George (elbow)",
        home_name="Orlando Magic",
        home_abbr="ORL",
        home_pace=99.4,
        home_ortg=114.3,
        home_drtg=114.1,
        home_injury_adj=0.5,  # Anthony Black doubtful
        home_injury_notes="DOUBTFUL: Anthony Black (quadriceps)",
        vegas_home_spread=-15.5,
        vegas_total=228.5,
        vegas_home_ml=-1275,
        vegas_away_ml=724,
        notes="Washington missing 4 players. Lowest-variance game on slate.",
    ),
    # ─── 7:30 PM ET ──────────────────────────────────────────────────────────
    GameEntry(
        game_id="BKN@MIA",
        tip_off_et="7:30 PM ET",
        away_name="Brooklyn Nets",
        away_abbr="BKN",
        away_pace=96.5,
        away_ortg=110.3,
        away_drtg=119.0,
        away_injury_adj=0.0,
        away_injury_notes="No confirmed key injuries",
        home_name="Miami Heat",
        home_abbr="MIA",
        home_pace=103.9,
        home_ortg=115.2,
        home_drtg=112.4,
        home_injury_adj=2.0,  # Jovic OUT, Powell/Mitchell questionable
        home_injury_notes="OUT: Nikola Jovic (back). PROB: Andrew Wiggins (bilateral knee). DTD: Davion Mitchell (shoulder), Norman Powell (groin)",
        vegas_home_spread=-13.5,
        vegas_total=226.5,
        vegas_home_ml=-750,
        vegas_away_ml=525,
        notes="Brooklyn on 8-game losing streak. Miami large home favorite.",
    ),
    GameEntry(
        game_id="NYK@TOR",
        tip_off_et="7:30 PM ET",
        away_name="New York Knicks",
        away_abbr="NYK",
        away_pace=97.7,
        away_ortg=119.4,
        away_drtg=113.2,
        away_injury_adj=0.0,
        away_injury_notes="Full roster available",
        home_name="Toronto Raptors",
        home_abbr="TOR",
        home_pace=98.5,
        home_ortg=114.9,
        home_drtg=112.9,
        home_injury_adj=0.0,
        home_injury_notes="No confirmed key injuries",
        vegas_home_spread=2.5,  # Knicks -2.5 road favorite (positive = home is dog)
        vegas_total=223.5,
        vegas_home_ml=133,
        vegas_away_ml=-144,
        notes="Closest game on slate. Low total reflects both teams' defensive competence.",
    ),
    # ─── 8:00 PM ET ──────────────────────────────────────────────────────────
    GameEntry(
        game_id="SAS@PHI",
        tip_off_et="8:00 PM ET (NBC/Peacock)",
        away_name="San Antonio Spurs",
        away_abbr="SAS",
        away_pace=100.1,
        away_ortg=117.7,
        away_drtg=111.5,
        away_injury_adj=1.0,  # Mason Plumlee (reconditioning)
        away_injury_notes="OUT: Mason Plumlee (reconditioning), Jones Garcia (ankle surgery - season done)",
        home_name="Philadelphia 76ers",
        home_abbr="PHI",
        home_pace=99.0,
        home_ortg=116.0,
        home_drtg=115.5,
        home_injury_adj=1.5,  # Oubre OUT
        home_injury_notes="OUT: Kelly Oubre Jr. (illness)",
        vegas_home_spread=8.5,  # Spurs -8.5 road favorite (positive = home dog)
        vegas_total=232.5,
        notes="Spurs (43-17) are 4th-best record. National TV game.",
    ),
    GameEntry(
        game_id="OKC@CHI",
        tip_off_et="8:00 PM ET",
        away_name="Oklahoma City Thunder",
        away_abbr="OKC",
        away_pace=99.5,
        away_ortg=118.8,
        away_drtg=107.5,
        away_injury_adj=5.0,  # SGA OUT (load management) — biggest adjustment of the night
        away_injury_notes="OUT: Shai Gilgeous-Alexander (abdomen - load management), Jalen Mitchell (abdomen/ankle - 18th straight), Carlson (lower back - 3rd straight)",
        home_name="Chicago Bulls",
        home_abbr="CHI",
        home_pace=101.6,
        home_ortg=113.6,
        home_drtg=117.7,
        home_injury_adj=0.0,
        home_injury_notes="No confirmed key absences",
        vegas_home_spread=9.5,  # OKC -9.5 road favorite (positive = home dog)
        vegas_total=230.5,
        vegas_home_ml=320,
        vegas_away_ml=-410,
        notes="CRITICAL: SGA OUT for load management. Biggest single-player adjustment tonight. OKC ortg reduced 5pts.",
    ),
    GameEntry(
        game_id="MEM@MIN",
        tip_off_et="8:00 PM ET",
        away_name="Memphis Grizzlies",
        away_abbr="MEM",
        away_pace=101.3,
        away_ortg=113.9,
        away_drtg=115.8,
        away_injury_adj=8.0,  # Ja Morant OUT + 4 others
        away_injury_notes="OUT: Ja Morant, Zach Edey, Brandon Clarke, Kentavious Caldwell-Pope, Taj Gibson. QUESTIONABLE: Ty Jerome (thigh bruise)",
        home_name="Minnesota Timberwolves",
        home_abbr="MIN",
        home_pace=100.8,
        home_ortg=117.6,
        home_drtg=113.1,
        home_injury_adj=0.0,
        home_injury_notes="Full roster available",
        vegas_home_spread=-13.5,
        vegas_total=237.5,
        vegas_home_ml=-900,
        vegas_away_ml=600,
        notes="Memphis missing 5+ starters including Ja Morant. Highest total on 8pm slate.",
    ),
    # ─── 10:30 PM ET ─────────────────────────────────────────────────────────
    GameEntry(
        game_id="NOP@LAL",
        tip_off_et="10:30 PM ET",
        away_name="New Orleans Pelicans",
        away_abbr="NOP",
        away_pace=100.1,
        away_ortg=114.0,
        away_drtg=119.2,
        away_injury_adj=1.5,  # Zion questionable (expected to play - use small adj)
        away_injury_notes="QUESTIONABLE: Zion Williamson (sprained ankle - expected to play per reports)",
        home_name="Los Angeles Lakers",
        home_abbr="LAL",
        home_pace=98.4,
        home_ortg=117.8,
        home_drtg=117.3,
        home_injury_adj=0.0,
        home_injury_notes="Full roster available",
        vegas_home_spread=-8.5,
        vegas_total=242.5,
        vegas_home_ml=-345,
        vegas_away_ml=280,
        notes="Highest o/u on the slate (242.5). Both teams play at a fast, high-scoring pace.",
    ),
    # ─── 11:00 PM ET ─────────────────────────────────────────────────────────
    GameEntry(
        game_id="PHX@SAC",
        tip_off_et="11:00 PM ET (NBC/Peacock)",
        away_name="Phoenix Suns",
        away_abbr="PHX",
        away_pace=97.3,
        away_ortg=114.7,
        away_drtg=113.9,
        away_injury_adj=1.0,  # Brooks OUT, but Booker RETURNING
        away_injury_notes="OUT: Dillon Brooks (left hand fracture), Jordan Goodwin (left calf). RETURNING: Devin Booker (hip - back tonight after 4 games missed)",
        home_name="Sacramento Kings",
        home_abbr="SAC",
        home_pace=99.5,
        home_ortg=110.3,
        home_drtg=121.2,
        home_injury_adj=5.0,  # Sabonis, LaVine, Hunter all season-done
        home_injury_notes="SEASON DONE: Domantas Sabonis (knee), Zach LaVine (hand surgery), De'Andre Hunter (retinal repair). Worst record in NBA (14-48).",
        vegas_home_spread=10.0,  # Phoenix -10 (positive = home dog)
        vegas_total=223.5,
        notes="National TV nightcap. Sacramento worst team in league. Booker returns for Phoenix.",
    ),
]


def get_game(game_id: str) -> Optional[GameEntry]:
    """Look up a game by ID."""
    for g in GAMES:
        if g.game_id == game_id:
            return g
    return None


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def update_with_live_odds(min_coverage: float = 0.90) -> Dict[str, Any]:
    """Fetch live odds and return coverage status for spread/total updates."""
    load_dotenv()
    api_key = os.getenv("THE_ODDS_API_KEY")
    if not api_key:
        print("THE_ODDS_API_KEY not found. Using pre-loaded odds.")
        return {
            "success": False,
            "reason": "missing_api_key",
            "matched_games": 0,
            "updated_spreads": 0,
            "updated_totals": 0,
            "updated_moneylines": 0,
            "coverage": 0.0,
            "stale_game_ids": [g.game_id for g in GAMES],
        }

    url = (
        "https://api.the-odds-api.com/v4/sports/basketball_nba/odds/"
        f"?apiKey={api_key}&regions=us&markets=h2h,spreads,totals"
        "&bookmakers=draftkings,fanduel,betmgm"
    )
    data = None
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            break
        except Exception as e:
            if attempt == 2:
                print(
                    f"Failed to fetch live odds: {e}. Falling back to pre-loaded odds."
                )
                return {
                    "success": False,
                    "reason": "fetch_failed",
                    "error": str(e),
                    "matched_games": 0,
                    "updated_spreads": 0,
                    "updated_totals": 0,
                    "updated_moneylines": 0,
                    "coverage": 0.0,
                    "stale_game_ids": [g.game_id for g in GAMES],
                }
            wait_seconds = 2**attempt
            print(
                f"Live odds fetch failed (attempt {attempt + 1}/3): {e}. "
                f"Retrying in {wait_seconds}s..."
            )
            time.sleep(wait_seconds)

    preferred_books = ["draftkings", "fanduel", "betmgm"]
    book_priority = {book: idx for idx, book in enumerate(preferred_books)}

    matched_games = 0
    updated_spreads = 0
    updated_totals = 0
    updated_moneylines = 0
    updated_spread_games = set()
    updated_total_games = set()

    for odds_game in data:
        home_full = odds_game.get("home_team")
        away_full = odds_game.get("away_team")

        target_game = next(
            (g for g in GAMES if g.home_name == home_full and g.away_name == away_full),
            None,
        )
        if not target_game:
            continue
        matched_games += 1

        bookmakers = odds_game.get("bookmakers", [])
        if not bookmakers:
            continue

        try:
            sorted_books = sorted(
                bookmakers, key=lambda b: book_priority.get(b.get("key", ""), 999)
            )
            spread_market = None
            totals_market = None
            h2h_market = None

            for book in sorted_books:
                for market in book.get("markets", []):
                    market_key = market.get("key")
                    outcomes = market.get("outcomes", [])
                    if market_key == "spreads" and not spread_market and outcomes:
                        spread_market = market
                    elif market_key == "totals" and not totals_market and outcomes:
                        totals_market = market
                    elif market_key == "h2h" and not h2h_market and outcomes:
                        h2h_market = market

            if spread_market:
                for outcome in spread_market.get("outcomes", []):
                    if outcome.get("name") == target_game.home_name:
                        point = _to_float(outcome.get("point"))
                        if point is not None:
                            target_game.vegas_home_spread = point
                            updated_spreads += 1
                            updated_spread_games.add(target_game.game_id)
                        break

            if totals_market:
                for outcome in totals_market.get("outcomes", []):
                    if outcome.get("name") == "Over":
                        point = _to_float(outcome.get("point"))
                        if point is not None:
                            target_game.vegas_total = point
                            updated_totals += 1
                            updated_total_games.add(target_game.game_id)
                        break

            if h2h_market:
                for outcome in h2h_market.get("outcomes", []):
                    name = outcome.get("name")
                    price = _to_int(outcome.get("price"))
                    if price is None:
                        continue
                    if name == target_game.home_name:
                        target_game.vegas_home_ml = price
                        updated_moneylines += 1
                    elif name == target_game.away_name:
                        target_game.vegas_away_ml = price
                        updated_moneylines += 1
        except Exception as e:
            print(f"Skipping malformed odds payload for {target_game.game_id}: {e}")
            continue

    required_updates = updated_spread_games & updated_total_games
    stale_game_ids = [g.game_id for g in GAMES if g.game_id not in required_updates]
    coverage = len(required_updates) / len(GAMES) if GAMES else 0.0
    success = coverage >= min_coverage

    if success:
        print(
            f"Live odds integrated: {len(required_updates)}/{len(GAMES)} games "
            "updated for spread+total."
        )
    else:
        print(
            "Live odds coverage incomplete: "
            f"{len(required_updates)}/{len(GAMES)} games updated for spread+total "
            f"(coverage={coverage:.1%})."
        )

    return {
        "success": success,
        "reason": "ok" if success else "partial_coverage",
        "matched_games": matched_games,
        "updated_spreads": updated_spreads,
        "updated_totals": updated_totals,
        "updated_moneylines": updated_moneylines,
        "coverage": coverage,
        "stale_game_ids": stale_game_ids,
    }


def print_slate_summary(games: Optional[List[GameEntry]] = None) -> None:
    """Print a quick summary of tonight's slate."""
    slate = games if games is not None else GAMES
    print("\n" + "=" * 65)
    print(f"  NBA TONIGHT - MARCH 3, 2026  |  {len(slate)} GAMES")
    print("=" * 65)
    for g in slate:
        spread_str = (
            f"{g.home_abbr} {g.vegas_home_spread:+.1f}"
            if g.vegas_home_spread < 0
            else f"{g.away_abbr} {-g.vegas_home_spread:+.1f}"
        )
        print(
            f"  {g.tip_off_et:18s} {g.away_abbr} @ {g.home_abbr:5s}  | Spread: {spread_str:12s} | O/U: {g.vegas_total}"
        )
    print("=" * 65 + "\n")
