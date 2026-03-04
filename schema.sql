-- Database Schemas for NBA Monte Carlo System

CREATE TABLE IF NOT EXISTS games (
    game_id VARCHAR(20) PRIMARY KEY,
    game_date DATE NOT NULL,
    home_team_id INT NOT NULL,
    away_team_id INT NOT NULL,
    home_team_abbr VARCHAR(5) NOT NULL,
    away_team_abbr VARCHAR(5) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE TABLE IF NOT EXISTS team_stats (
    team_id INT PRIMARY KEY,
    team_abbr VARCHAR(5) NOT NULL,
    team_name VARCHAR(100) NOT NULL,
    pace FLOAT NOT NULL,
    ortg FLOAT NOT NULL,
    drtg FLOAT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE TABLE IF NOT EXISTS player_stats (
    player_id INT PRIMARY KEY,
    team_id INT NOT NULL,
    player_name VARCHAR(100) NOT NULL,
    usg_pct FLOAT NOT NULL,
    ts_pct FLOAT NOT NULL,
    pts_per_game FLOAT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);
