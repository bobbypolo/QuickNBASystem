import os

import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('THE_ODDS_API_KEY')
if not api_key:
    print('No API key found!')
    exit(1)

url = f'https://api.the-odds-api.com/v4/sports/basketball_nba/odds/?apiKey={api_key}&regions=us&markets=h2h,spreads,totals&bookmakers=draftkings'
try:
    resp = requests.get(url, timeout=10)
    print(f'Status: {resp.status_code}')
    if resp.status_code == 200:
        data = resp.json()
        print(f'Retrieved {len(data)} games.')
        if len(data) > 0:
            print(f'Sample game: {data[0].get("home_team")} vs {data[0].get("away_team")}')
    else:
        print(f'Response: {resp.text}')
except Exception as e:
    print(f'Error: {e}')
