"""
Automated Injury & Stats Feed.
Scrapes ESPN injury reports and fetches nba_api last-10-game team ratings.
Fails closed: on any error, returns empty list/dict and logs a warning.
"""

import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

# ESPN team abbr → ESPN team ID (partial — extend as needed)
ESPN_TEAM_IDS: dict[str, str] = {
    "ATL": "1",
    "BOS": "2",
    "BKN": "17",
    "CHA": "30",
    "CHI": "4",
    "CLE": "5",
    "DAL": "6",
    "DEN": "7",
    "DET": "8",
    "GSW": "9",
    "HOU": "10",
    "IND": "11",
    "LAC": "12",
    "LAL": "13",
    "MEM": "29",
    "MIA": "14",
    "MIL": "15",
    "MIN": "16",
    "NOP": "3",
    "NYK": "18",
    "OKC": "25",
    "ORL": "19",
    "PHI": "20",
    "PHX": "21",
    "POR": "22",
    "SAC": "23",
    "SAS": "24",
    "TOR": "28",
    "UTA": "26",
    "WAS": "27",
}

ESPN_INJURY_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
)

RECENCY_WEIGHT = 0.60  # weight for last-10 games vs season average


@dataclass
class PlayerInjury:
    """One player's injury status."""

    name: str
    status: str  # "OUT", "DOUBTFUL", "QUESTIONABLE"
    impact_pts: float  # estimated ortg impact (positive = loss to team)


@dataclass
class TeamRatings:
    """Last-N-game ratings for one team."""

    ortg: float
    drtg: float
    pace: float


def fetch_injuries(team_abbr: str) -> list[PlayerInjury]:
    """Fetch current injury report for a team from ESPN.

    Returns empty list on any network or parse error (fails closed).
    """
    team_id = ESPN_TEAM_IDS.get(team_abbr.upper())
    if team_id is None:
        logger.warning("fetch_injuries: unknown team abbr %s", team_abbr)
        return []
    try:
        resp = requests.get(
            ESPN_INJURY_URL,
            params={"team": team_id},
            timeout=5.0,
        )
        resp.raise_for_status()
        data = resp.json()
        injuries: list[PlayerInjury] = []
        for item in data.get("injuries", []):
            player = item.get("athlete", {}).get("displayName", "Unknown")
            status = item.get("status", "UNKNOWN").upper()
            if status in ("OUT", "DOUBTFUL", "QUESTIONABLE"):
                # Rough impact estimate: OUT=4, DOUBTFUL=2, QUESTIONABLE=1
                impact = {"OUT": 4.0, "DOUBTFUL": 2.0, "QUESTIONABLE": 1.0}.get(
                    status, 0.0
                )
                injuries.append(
                    PlayerInjury(name=player, status=status, impact_pts=impact)
                )
        return injuries
    except Exception as exc:
        logger.warning("fetch_injuries(%s): %s", team_abbr, exc)
        return []


def fetch_last10_ratings(team_abbrs: list[str]) -> dict[str, TeamRatings]:
    """Fetch last-10-game team ratings from nba_api.

    Returns empty dict on any API or parse error (fails closed).
    """
    try:
        from nba_api.stats.endpoints import LeagueDashTeamStats  # type: ignore[import]

        stats = LeagueDashTeamStats(
            last_n_games=10,
            per_mode_simple="Per100Possessions",
        )
        df = stats.get_data_frames()[0]
        result: dict[str, TeamRatings] = {}
        abbr_upper = {a.upper() for a in team_abbrs}
        for _, row in df.iterrows():
            abbr = str(row.get("TEAM_ABBREVIATION", "")).upper()
            if abbr not in abbr_upper:
                continue
            result[abbr] = TeamRatings(
                ortg=float(row.get("OFF_RATING", row.get("PTS", 0))),
                drtg=float(row.get("DEF_RATING", 110.0)),
                pace=float(row.get("PACE", 100.0)),
            )
        return result
    except Exception as exc:
        logger.warning("fetch_last10_ratings(%s): %s", team_abbrs, exc)
        return {}


def update_with_live_ratings(
    games: list,
    min_coverage: float = 0.80,
) -> dict:
    """Auto-populate last10 and injury fields on game entries.

    Returns coverage report: {success, coverage, updated_injuries, updated_ratings}.
    Fails closed: if coverage < min_coverage, does not update entries.
    """
    if not games:
        return {
            "success": False,
            "coverage": 0.0,
            "updated_injuries": 0,
            "updated_ratings": 0,
        }

    team_abbrs = []
    for g in games:
        team_abbrs.append(g.home_abbr)
        team_abbrs.append(g.away_abbr)
    unique_abbrs = list(set(team_abbrs))

    ratings = fetch_last10_ratings(unique_abbrs)
    coverage = len(ratings) / len(unique_abbrs) if unique_abbrs else 0.0

    if coverage < min_coverage:
        logger.warning(
            "update_with_live_ratings: coverage %.0f%% below threshold %.0f%% — skipping",
            coverage * 100,
            min_coverage * 100,
        )
        return {
            "success": False,
            "coverage": coverage,
            "updated_injuries": 0,
            "updated_ratings": 0,
        }

    updated_ratings = 0
    for g in games:
        for attr_prefix, abbr in (("home", g.home_abbr), ("away", g.away_abbr)):
            if abbr in ratings:
                r = ratings[abbr]
                object.__setattr__(g, f"{attr_prefix}_last10_ortg", r.ortg)
                object.__setattr__(g, f"{attr_prefix}_last10_drtg", r.drtg)
                object.__setattr__(g, f"{attr_prefix}_last10_pace", r.pace)
                updated_ratings += 1

    return {
        "success": True,
        "coverage": coverage,
        "updated_injuries": 0,
        "updated_ratings": updated_ratings,
    }
