import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional

from simulator import TeamInput, simulate_game, SimResult
from parlay import ParlayLeg, evaluate_mg_parlay, evaluate_sgp
from player_sim import PlayerInput, simulate_player_props

app = FastAPI(title="NBA Monte Carlo System API")


# ── API Models ───────────────────────────────────────────────────────────────
class TeamReq(BaseModel):
    name: str
    abbr: str
    pace: float
    ortg: float
    drtg: float
    injury_adj: float = 0.0


class SimulateRequest(BaseModel):
    home_team: TeamReq
    away_team: TeamReq
    n_sims: int = 10000
    vegas_home_ml: Optional[int] = None
    vegas_away_ml: Optional[int] = None


class ParlayLegReq(BaseModel):
    game_id: str
    bet_type: str
    line: float
    description: str
    book_odds: Optional[int] = None


class ParlayRequest(BaseModel):
    legs: List[ParlayLegReq]
    # To evaluate a parlay, we need the simulated results of the involved games
    # In a full app, we would fetch games from DB and simulate them.
    # Here, we accept the parameters to simulate them on the fly.
    games: Dict[str, SimulateRequest]
    is_sgp: bool = False
    book_odds: Optional[int] = None


class PlayerReq(BaseModel):
    player_id: int
    name: str
    team_id: int
    usg_pct: float
    ts_pct: float
    pts_per_game: float


class PropsRequest(SimulateRequest):
    home_players: List[PlayerReq]
    away_players: List[PlayerReq]


# ── Endpoints ────────────────────────────────────────────────────────────────
@app.post("/simulate/{game_id}")
def simulate_endpoint(game_id: str, req: SimulateRequest):
    home = TeamInput(**req.home_team.model_dump())
    away = TeamInput(**req.away_team.model_dump())
    result = simulate_game(home, away, game_id, n_sims=req.n_sims)

    response = {
        "game_id": game_id,
        "home_win_prob": result.home_win_prob,
        "away_win_prob": result.away_win_prob,
        "model_spread": result.model_spread,
        "model_total": result.model_total,
        "home_ml_american": result.home_ml_american(),
        "away_ml_american": result.away_ml_american(),
    }

    # Add blended probabilities when Vegas lines provided
    if req.vegas_home_ml is not None and req.vegas_away_ml is not None:
        from simulator import american_to_implied_prob, devig_pair
        from market_blender import blend_probability

        h_implied = american_to_implied_prob(req.vegas_home_ml)
        a_implied = american_to_implied_prob(req.vegas_away_ml)
        fair_h, _ = devig_pair(h_implied, a_implied)
        blend_res = blend_probability(result.home_win_prob, fair_h, "moneyline")
        response["blended_home_win_prob"] = blend_res.p_blended
        response["blended_away_win_prob"] = 1.0 - blend_res.p_blended
        response["market_home_prob"] = fair_h

    return response


@app.post("/parlay/evaluate")
def parlay_evaluate_endpoint(req: ParlayRequest):
    if not req.legs:
        raise HTTPException(status_code=400, detail="No parlay legs provided.")

    sim_results: Dict[str, SimResult] = {}

    # Simulate all required games
    for gid, game_req in req.games.items():
        home = TeamInput(**game_req.home_team.model_dump())
        away = TeamInput(**game_req.away_team.model_dump())
        sim_results[gid] = simulate_game(home, away, gid, n_sims=game_req.n_sims)

    legs = [ParlayLeg(**leg.model_dump()) for leg in req.legs]

    if req.is_sgp:
        try:
            parlay_res = evaluate_sgp(sim_results, legs, req.book_odds)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    else:
        parlay_res = evaluate_mg_parlay(sim_results, legs, req.book_odds)

    return {
        "parlay_type": parlay_res.parlay_type,
        "true_joint_prob": parlay_res.true_joint_prob,
        "independence_prob": parlay_res.independence_prob,
        "true_american": parlay_res.true_american,
        "correlation_factor": parlay_res.correlation_factor,
        "edge": parlay_res.edge,
    }


@app.post("/props/{game_id}")
def props_endpoint(game_id: str, req: PropsRequest):
    home = TeamInput(**req.home_team.model_dump())
    away = TeamInput(**req.away_team.model_dump())
    sim_result = simulate_game(home, away, game_id, n_sims=req.n_sims)

    home_ps = [PlayerInput(**p.model_dump()) for p in req.home_players]
    away_ps = [PlayerInput(**p.model_dump()) for p in req.away_players]

    props_result = simulate_player_props(sim_result, home_ps, away_ps)

    # Summarize distributions (sending back 10k arrays per player is too large)
    summary = {}
    for pid, sims in props_result.items():
        # Add basic prop metrics
        # For example, what is the probability of player getting 10+ points?
        summary[pid] = {
            "mean_pts": float(np.mean(sims)),
            "median_pts": float(np.median(sims)),
            "prob_over_10_5": float(np.mean(sims > 10.5)),
            "prob_over_15_5": float(np.mean(sims > 15.5)),
            "prob_over_20_5": float(np.mean(sims > 20.5)),
        }

    return {"game_id": game_id, "player_props_summary": summary}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
