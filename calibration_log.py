"""
Nightly Calibration & Backtest Log — SQLite predictions database.
Logs every recommendation and later ingests actuals for Brier/log-loss reporting.
"""

import math
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "predictions.db")


def _get_conn(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DB_PATH) -> None:
    """Create tables if they don't exist."""
    with _get_conn(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                game_id TEXT NOT NULL,
                bet_type TEXT NOT NULL,
                line REAL NOT NULL,
                model_prob REAL NOT NULL,
                blended_prob REAL NOT NULL,
                edge REAL NOT NULL,
                rank INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS actuals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                game_id TEXT NOT NULL,
                home_score INTEGER NOT NULL,
                away_score INTEGER NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)


def log_prediction(
    date_str: str,
    game_id: str,
    bet_type: str,
    line: float,
    model_prob: float,
    blended_prob: float,
    edge: float,
    rank: Optional[int] = None,
    db_path: str = DB_PATH,
) -> None:
    """Insert one prediction row."""
    init_db(db_path)
    with _get_conn(db_path) as conn:
        conn.execute(
            """INSERT INTO predictions
               (date, game_id, bet_type, line, model_prob, blended_prob, edge, rank)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (date_str, game_id, bet_type, line, model_prob, blended_prob, edge, rank),
        )


def log_actual(
    date_str: str,
    game_id: str,
    home_score: int,
    away_score: int,
    db_path: str = DB_PATH,
) -> None:
    """Insert actual game result."""
    init_db(db_path)
    with _get_conn(db_path) as conn:
        conn.execute(
            """INSERT INTO actuals (date, game_id, home_score, away_score)
               VALUES (?, ?, ?, ?)""",
            (date_str, game_id, home_score, away_score),
        )


def _resolve_outcome(
    bet_type: str, line: float, home_score: int, away_score: int
) -> Optional[int]:
    """Determine outcome (1=WIN, 0=LOSS, None=push/no result).

    Spread logic (margin = home_score - away_score):
      - spread_home: home covers if margin > -line
      - spread_away: away covers if (away_score - home_score) > -line
    Total logic:
      - over: WIN if total > line
      - under: WIN if total < line
    ML logic:
      - ml_home: WIN if home_score > away_score
      - ml_away: WIN if away_score > home_score
    """
    margin = home_score - away_score
    total = home_score + away_score

    if bet_type == "spread_home":
        if margin == -line:
            return None  # push
        return 1 if margin > -line else 0
    elif bet_type == "spread_away":
        away_margin = away_score - home_score
        if away_margin == -line:
            return None
        return 1 if away_margin > -line else 0
    elif bet_type == "over":
        if total == line:
            return None
        return 1 if total > line else 0
    elif bet_type == "under":
        if total == line:
            return None
        return 1 if total < line else 0
    elif bet_type == "ml_home":
        if margin == 0:
            return None
        return 1 if margin > 0 else 0
    elif bet_type == "ml_away":
        if margin == 0:
            return None
        return 1 if margin < 0 else 0
    return None


@dataclass
class MarketStats:
    """Brier score and log loss for one market type."""

    market: str
    n_bets: int
    win_rate: float
    brier_score: float
    log_loss: float
    edge_buckets: dict = field(default_factory=dict)  # bucket_label -> win_rate


@dataclass
class BacktestReport:
    """Full backtest report with per-market stats."""

    lookback_days: int
    total_bets: int
    total_resolved: int
    markets: list[MarketStats]


def backtest_report(lookback_days: int = 30, db_path: str = DB_PATH) -> BacktestReport:
    """Compute Brier score and log loss per market type.

    Joins predictions + actuals on (date, game_id), resolves outcomes,
    groups by market type (spread/total/ml) and edge bucket.
    """
    init_db(db_path)
    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()

    with _get_conn(db_path) as conn:
        rows = conn.execute(
            """SELECT p.date, p.game_id, p.bet_type, p.line,
                      p.model_prob, p.blended_prob, p.edge,
                      a.home_score, a.away_score
               FROM predictions p
               JOIN actuals a ON p.date = a.date AND p.game_id = a.game_id
               WHERE p.date >= ?""",
            (cutoff,),
        ).fetchall()

    if not rows:
        return BacktestReport(
            lookback_days=lookback_days,
            total_bets=0,
            total_resolved=0,
            markets=[],
        )

    # Group by market type (spread/total/ml)
    by_market: dict[str, list] = {}
    for row in rows:
        outcome = _resolve_outcome(
            row["bet_type"], row["line"], row["home_score"], row["away_score"]
        )
        if outcome is None:
            continue  # push — skip
        market = _market_family(row["bet_type"])
        if market not in by_market:
            by_market[market] = []
        by_market[market].append((row["blended_prob"], outcome, row["edge"]))

    market_stats: list[MarketStats] = []
    for market, entries in by_market.items():
        probs = [e[0] for e in entries]
        outcomes = [e[1] for e in entries]
        edges = [e[2] for e in entries]
        n = len(probs)
        win_rate = sum(outcomes) / n
        brier = sum((p - y) ** 2 for p, y in zip(probs, outcomes)) / n
        log_loss = (
            -sum(
                y * math.log(max(p, 1e-9)) + (1 - y) * math.log(max(1 - p, 1e-9))
                for p, y in zip(probs, outcomes)
            )
            / n
        )

        # Edge buckets
        buckets: dict[str, list] = {"[2,4)": [], "[4,6)": [], "[6,8)": [], "8+": []}
        for p, y, e in zip(probs, outcomes, edges):
            if e < 4:
                buckets["[2,4)"].append(y)
            elif e < 6:
                buckets["[4,6)"].append(y)
            elif e < 8:
                buckets["[6,8)"].append(y)
            else:
                buckets["8+"].append(y)
        edge_wr = {k: sum(v) / len(v) if v else None for k, v in buckets.items()}

        market_stats.append(
            MarketStats(
                market=market,
                n_bets=n,
                win_rate=win_rate,
                brier_score=brier,
                log_loss=log_loss,
                edge_buckets=edge_wr,
            )
        )

    total_resolved = sum(len(v) for v in by_market.values())
    return BacktestReport(
        lookback_days=lookback_days,
        total_bets=len(rows),
        total_resolved=total_resolved,
        markets=market_stats,
    )


def _market_family(bet_type: str) -> str:
    """Map bet_type to market family for grouping."""
    if "spread" in bet_type:
        return "spread"
    if bet_type in ("over", "under"):
        return "total"
    return "ml"
