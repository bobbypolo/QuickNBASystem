import json
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_simulate():
    payload = {
        "home_team": {
            "name": "Lakers",
            "abbr": "LAL",
            "pace": 100.5,
            "ortg": 112.3,
            "drtg": 110.1,
            "injury_adj": 0.0
        },
        "away_team": {
            "name": "Warriors",
            "abbr": "GSW",
            "pace": 102.1,
            "ortg": 114.5,
            "drtg": 113.2,
            "injury_adj": 0.0
        },
        "n_sims": 1000
    }
    
    response = client.post("/simulate/test_game", json=payload)
    print("Status Code:", response.status_code)
    try:
        print(json.dumps(response.json(), indent=2))
        assert response.status_code == 200
    except Exception as e:
        print(response.text)
        raise e

if __name__ == "__main__":
    test_simulate()
    print("FastAPI /simulate endpoint working.")
