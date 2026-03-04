import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from supabase import create_client, Client

from nba_api.stats.endpoints import leaguedashteamstats, leaguedashplayerstats, scoreboardv2
from nba_api.stats.library.http import STATS_HEADERS
from game_data import GAMES

# Load environment variables
load_dotenv()
NBA_TZ = ZoneInfo("America/New_York")


def nba_today_str() -> str:
    return datetime.now(NBA_TZ).strftime("%Y-%m-%d")

# Rate limiting for nba_api (to prevent timeouts/bans)
def rate_limit():
    time.sleep(0.600)

def fetch_with_retry(endpoint_class, max_retries=5, backoff_factor=1.5, **kwargs):
    """Robust retry logic for unstable nba_api endpoints."""
    base_timeout = int(kwargs.pop("timeout", 30))
    if "headers" not in kwargs:
        kwargs["headers"] = STATS_HEADERS

    for attempt in range(max_retries):
        try:
            rate_limit()
            call_kwargs = dict(kwargs)
            call_kwargs["timeout"] = min(90, base_timeout + attempt * 15)
            response = endpoint_class(**call_kwargs)
            df = response.get_data_frames()[0]
            if df is not None:
                return df
        except Exception as e:
            print(f"nba_api request failed (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                wait_time = backoff_factor ** attempt
                print(f"Retrying in {wait_time:.1f}s...")
                time.sleep(wait_time)
            
    print(f"Failed to fetch data after {max_retries} attempts.")
    import pandas as pd
    return pd.DataFrame()

def get_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    return create_client(url, key)

def ingest_teams(supabase: Client):
    print("Fetching team stats...")
    rate_limit()
    
    # Advanced stats for Pace, ORtg, DRtg
    adv_stats = fetch_with_retry(
        leaguedashteamstats.LeagueDashTeamStats,
        per_mode_detailed='PerGame',
        measure_type_detailed_defense='Advanced'
    )
    
    if adv_stats.empty:
        print("Empty team stats DataFrame returned. Skipping team ingest.")
        return
    
    records = []
    for _, row in adv_stats.iterrows():
        records.append({
            "team_id": int(row['TEAM_ID']),
            "team_name": row['TEAM_NAME'],
            "team_abbr": row.get('TEAM_ABBREVIATION', row['TEAM_NAME'][:3].upper()),
            "pace": float(row['PACE']),
            "ortg": float(row['OFF_RATING']),
            "drtg": float(row['DEF_RATING']),
            "updated_at": datetime.utcnow().isoformat()
        })
        
    print(f"Upserting {len(records)} team records to Supabase...")
    supabase.table("team_stats").upsert(records).execute()
    print("Done ingest_teams.")

def ingest_players(supabase: Client):
    print("Fetching player stats...")
    rate_limit()
    # Advanced stats for USG_PCT and TS_PCT
    adv_stats = fetch_with_retry(
        leaguedashplayerstats.LeagueDashPlayerStats,
        per_mode_detailed='PerGame',
        measure_type_detailed_defense='Advanced'
    )

    # Base stats for PTS (Points Per Game)
    base_stats = fetch_with_retry(
        leaguedashplayerstats.LeagueDashPlayerStats,
        per_mode_detailed='PerGame',
        measure_type_detailed_defense='Base'
    )
    
    if adv_stats.empty or base_stats.empty:
        print("Empty player stats DataFrame returned. Skipping player ingest.")
        return
    
    # Merge on PLAYER_ID
    merged = adv_stats.merge(
        base_stats[['PLAYER_ID', 'PTS']], 
        on='PLAYER_ID', 
        how='left'
    )
    
    records = []
    for _, row in merged.iterrows():
        # Handle players with missing/null team_id
        if not row.get('TEAM_ID') or str(row.get('TEAM_ID')) == '0':
            continue
            
        records.append({
            "player_id": int(row['PLAYER_ID']),
            "team_id": int(row['TEAM_ID']),
            "player_name": row['PLAYER_NAME'],
            "usg_pct": float(row.get('USG_PCT', 0.0)),
            "ts_pct": float(row.get('TS_PCT', 0.0)),
            "pts_per_game": float(row.get('PTS', 0.0)),
            "updated_at": datetime.utcnow().isoformat()
        })
        
    print(f"Upserting {len(records)} player records to Supabase...")
    # Because there are many players, chunk the upsert
    chunk_size = 100
    for i in range(0, len(records), chunk_size):
        supabase.table("player_stats").upsert(records[i:i+chunk_size]).execute()
    print("Done ingest_players.")

def ingest_games(supabase: Client):
    print("Fetching today's games...")
    game_date = nba_today_str()
    board = fetch_with_retry(scoreboardv2.ScoreboardV2, game_date=game_date)

    if board.empty:
        # Keep existing schedule only if it's for the target NBA date.
        try:
            existing = (
                supabase.table("games")
                .select("game_id", count="exact")
                .eq("game_date", game_date)
                .limit(1)
                .execute()
            )
            if existing.count and existing.count > 0:
                print(
                    "No fresh games from nba_api. "
                    f"Keeping existing {existing.count} game rows for {game_date}."
                )
                return
        except Exception:
            pass

        print("No games found from nba_api. Falling back to static game_data slate.")
        try:
            teams_resp = supabase.table("team_stats").select("team_id, team_abbr").execute()
            abbr_to_team_id = {t["team_abbr"]: t["team_id"] for t in teams_resp.data}
        except Exception:
            abbr_to_team_id = {}

        fallback_records = []
        for g in GAMES:
            home_id = int(abbr_to_team_id.get(g.home_abbr, 0))
            away_id = int(abbr_to_team_id.get(g.away_abbr, 0))
            if home_id == 0 or away_id == 0:
                continue
            fallback_records.append(
                {
                    "game_id": g.game_id,
                    "game_date": game_date,
                    "home_team_id": home_id,
                    "away_team_id": away_id,
                    "home_team_abbr": g.home_abbr,
                    "away_team_abbr": g.away_abbr,
                    "status": "Scheduled",
                    "created_at": datetime.utcnow().isoformat(),
                }
            )

        if fallback_records:
            print(f"Upserting {len(fallback_records)} fallback game records to Supabase...")
            supabase.table("games").upsert(fallback_records).execute()
            print("Done ingest_games (fallback mode).")
        else:
            print("Fallback game ingest skipped: could not map team IDs.")
        return

    # To get team abbreviations, we might need to fetch from our DB
    # or just use what we can get (some endpoints have them, some don't).
    # ScoreboardV2 usually doesn't have HOME_TEAM_ABBREVIATION directly in the main Team stand-ins,
    # but let's try mapping.
    # Actually, we can fetch team_stats from supabase to create an ID -> Abbr map.
    try:
        teams_resp = supabase.table("team_stats").select("team_id, team_abbr").execute()
        team_map = {t['team_id']: t['team_abbr'] for t in teams_resp.data}
    except Exception:
        team_map = {}

    records_by_game = {}
    for _, row in board.iterrows():
        game_id = str(row['GAME_ID'])
        home_id = int(row['HOME_TEAM_ID'])
        away_id = int(row['VISITOR_TEAM_ID'])
        game_date_str = str(row['GAME_DATE_EST'])[:10]  # yyyy-mm-dd

        records_by_game[game_id] = {
            "game_id": game_id,
            "game_date": game_date_str,
            "home_team_id": home_id,
            "away_team_id": away_id,
            "home_team_abbr": team_map.get(home_id, "UNK"),
            "away_team_abbr": team_map.get(away_id, "UNK"),
            "status": str(row['GAME_STATUS_TEXT']),
            "created_at": datetime.utcnow().isoformat()
        }

    records = list(records_by_game.values())
    if not records:
        print("No game records to upsert.")
        return

    print(f"Upserting {len(records)} game records to Supabase...")
    supabase.table("games").upsert(records).execute()
    print("Done ingest_games.")

if __name__ == "__main__":
    client = get_supabase()
    ingest_teams(client)
    ingest_players(client)
    ingest_games(client)
    print("Ingestion complete.")
