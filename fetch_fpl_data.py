"""
fetch_fpl_data.py
------------------
Pulls the full live Fantasy Premier League dataset from the official,
free FPL API (no key needed) and saves a clean version to disk.

This is step 1 of the data pipeline: run this locally (or later on a
schedule via GitHub Actions / cron) to refresh player data.

Usage:
    pip install requests
    python fetch_fpl_data.py

Output:
    fpl_players.json  -- one row per player with the fields we care about
    fpl_teams.json    -- the 20 Premier League clubs
"""

import json
import os
import requests

BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
FIXTURES_URL = "https://fantasy.premierleague.com/api/fixtures/"

# element_type in the API maps to position like this:
POSITIONS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}

# 2025/26 Premier League final table (1st = strongest baseline).
# Teams not in this dict were promoted into the league this season and
# don't have a top-flight finish to go on, so they default to a weak
# baseline (see LAST_SEASON_DEFAULT below) until they've built up form.
LAST_SEASON_POSITION = {
    "Arsenal": 1, "Man City": 2, "Man Utd": 3, "Aston Villa": 4,
    "Liverpool": 5, "Bournemouth": 6, "Sunderland": 7, "Chelsea": 8,
    "Brentford": 9, "Everton": 10, "Fulham": 11, "Brighton": 12,
    "Newcastle": 13, "Crystal Palace": 14, "Leeds": 15, "Spurs": 16,
    "Nott'm Forest": 17,
    # West Ham (18th), Burnley (19th) and Wolves (20th) were relegated
    # and are no longer in this season's team list.
}
LAST_SEASON_DEFAULT_POSITION = 19  # used for newly-promoted teams


def fetch_bootstrap_data():
    """Fetch the main FPL dataset (players, teams, gameweeks)."""
    response = requests.get(BOOTSTRAP_URL, timeout=15)
    response.raise_for_status()
    return response.json()


def fetch_fixtures():
    """Fetch every fixture for the season (past and future)."""
    response = requests.get(FIXTURES_URL, timeout=15)
    response.raise_for_status()
    return response.json()


def clean_players(data, last_season_snapshot):
    """Extract just the fields our site needs, in a simple flat format."""
    team_lookup = {team["id"]: team["name"] for team in data["teams"]}

    players = []
    for p in data["elements"]:
        last_season = last_season_snapshot.get(str(p["id"]), {})
        players.append({
            "id": p["id"],
            "name": p["web_name"],
            "full_name": f'{p["first_name"]} {p["second_name"]}',
            "team": team_lookup.get(p["team"], "Unknown"),
            "position": POSITIONS.get(p["element_type"], "UNK"),
            "price": p["now_cost"] / 10,  # API stores price x10 (e.g. 95 = £9.5m)
            "total_points": p["total_points"],
            "points_per_game": float(p["points_per_game"]),
            "form": float(p["form"]),
            "selected_by_percent": float(p["selected_by_percent"]),
            "expected_goals": float(p["expected_goals"]),
            "expected_assists": float(p["expected_assists"]),
            "expected_goal_involvements": float(p["expected_goal_involvements"]),
            "defensive_contribution": p.get("defensive_contribution", 0),
            "tackles": p.get("tackles", 0),
            "clearances_blocks_interceptions": p.get("clearances_blocks_interceptions", 0),
            "recoveries": p.get("recoveries", 0),
            "ep_next": float(p["ep_next"]) if p["ep_next"] else 0.0,  # predicted pts next GW (FPL's own estimate)
            "minutes": p["minutes"],
            "starts": p.get("starts", 0),
            "last_season_tackles": last_season.get("tackles", 0),
            "last_season_clearances_blocks_interceptions": last_season.get("clearances_blocks_interceptions", 0),
            "last_season_recoveries": last_season.get("recoveries", 0),
            "last_season_starts": last_season.get("starts", 0),
            "status": p["status"],       # "a" = available, "i" = injured, "d" = doubtful, "s" = suspended
            "news": p["news"],           # injury/team news text, blank if none
            "transfers_in_event": p["transfers_in_event"],
            "transfers_out_event": p["transfers_out_event"],
            "transfers_in": p["transfers_in"],
            "transfers_out": p["transfers_out"],
            "cost_change_event": p["cost_change_event"],  # today's price movement so far
        })
    return players


def clean_teams(data, strengths):
    return [
        {
            "id": t["id"],
            "name": t["name"],
            "short_name": t["short_name"],
            "strength_score": strengths.get(t["id"], 50.0),  # our own 0-100 model
        }
        for t in data["teams"]
    ]


def clean_fixtures(fixtures_raw):
    """Keep only the fields the fixture ticker needs."""
    return [
        {
            "event": f["event"],          # gameweek number, null if not yet scheduled
            "team_h": f["team_h"],        # home team id
            "team_a": f["team_a"],        # away team id
            "kickoff_time": f["kickoff_time"],
            "finished": f["finished"],
        }
        for f in fixtures_raw
        if f["event"] is not None
    ]


def compute_team_strength(teams_raw, fixtures_raw):
    """
    Our own team strength score (0-100, higher = stronger), blending:
      - last season's final position (fixed baseline)
      - this season's live table position (weight ramps up as games are played)
      - recent form: points-per-game across the last 5 finished matches (same ramp-up)

    Before the season starts this is 100% last season's table. By around
    Gameweek 10 it's almost entirely this season's table + form.
    """
    # Build a lookup of each team's finished fixtures, in chronological order,
    # so we can work out current-season points-per-game and last-5-game form.
    finished = [f for f in fixtures_raw if f["finished"]]
    finished.sort(key=lambda f: f["event"] or 0)

    results_by_team = {t["id"]: [] for t in teams_raw}
    for f in finished:
        h, a = f["team_h"], f["team_a"]
        hs, aws = f["team_h_score"], f["team_a_score"]
        if hs is None or aws is None:
            continue
        h_pts = 3 if hs > aws else (1 if hs == aws else 0)
        a_pts = 3 if aws > hs else (1 if hs == aws else 0)
        if h in results_by_team:
            results_by_team[h].append(h_pts)
        if a in results_by_team:
            results_by_team[a].append(a_pts)

    strengths = {}
    for t in teams_raw:
        team_id = t["id"]
        results = results_by_team[team_id]
        games_played = len(results)

        # --- last season baseline (1st = 100, 20th = 0) ---
        last_pos = LAST_SEASON_POSITION.get(t["name"], LAST_SEASON_DEFAULT_POSITION)
        last_season_score = (21 - last_pos) / 19 * 100

        # --- this season so far (points-per-game, out of 3, scaled to 100) ---
        current_score = (sum(results) / games_played / 3 * 100) if games_played > 0 else None

        # --- recent form: last 5 games only ---
        recent = results[-5:]
        form_score = (sum(recent) / len(recent) / 3 * 100) if recent else None

        # Ramp live data in gradually: 0% weight before a ball is kicked,
        # full weight by 10 games played.
        live_weight = min(games_played / 10, 1.0)
        if games_played > 0:
            live_component = 0.6 * current_score + 0.4 * form_score
            strength = (1 - live_weight) * last_season_score + live_weight * live_component
        else:
            strength = last_season_score

        strengths[team_id] = round(strength, 1)

    return strengths


LAST_SEASON_SNAPSHOT_FILE = "fpl_last_season_snapshot.json"


def capture_last_season_snapshot_if_needed(data):
    """
    Before Gameweek 1 starts, the FPL API still shows LAST season's final
    numbers in each player's normal stats fields (minutes, starts, tackles,
    etc) since this season has no data yet. We grab a one-time snapshot of
    that here, before it gets overwritten once the new season's matches
    begin. If the snapshot file already exists, we leave it alone — it's
    frozen in place as our permanent "last season" reference.
    """
    if os.path.exists(LAST_SEASON_SNAPSHOT_FILE):
        with open(LAST_SEASON_SNAPSHOT_FILE) as f:
            return json.load(f)

    any_games_played_this_season = any(t["played"] > 0 for t in data["teams"])
    if any_games_played_this_season:
        # Season's already underway and we never captured a snapshot in time —
        # nothing we can do about that now, just skip it.
        print("Note: season has already started and no last-season snapshot exists yet, skipping.")
        return {}

    snapshot = {}
    for p in data["elements"]:
        snapshot[str(p["id"])] = {
            "tackles": p.get("tackles", 0),
            "clearances_blocks_interceptions": p.get("clearances_blocks_interceptions", 0),
            "recoveries": p.get("recoveries", 0),
            "starts": p.get("starts", 0),
        }

    with open(LAST_SEASON_SNAPSHOT_FILE, "w") as f:
        json.dump(snapshot, f, indent=2)
    print(f"Captured last-season snapshot for {len(snapshot)} players (one-time, won't be overwritten).")
    return snapshot


def clean_meta(data):
    """A few site-wide numbers we need for calculations, like the total
    number of FPL managers (used to scale price-change predictions)."""
    current_event = next((e for e in data["events"] if e["is_current"]), None)
    next_event = next((e for e in data["events"] if e["is_next"]), None)
    return {
        "total_players": data["total_players"],  # total registered FPL managers
        "current_event": current_event["id"] if current_event else None,
        "next_event": next_event["id"] if next_event else None,
    }


def main():
    print("Fetching live data from the FPL API...")
    data = fetch_bootstrap_data()
    fixtures_raw = fetch_fixtures()

    last_season_snapshot = capture_last_season_snapshot_if_needed(data)
    strengths = compute_team_strength(data["teams"], fixtures_raw)

    players = clean_players(data, last_season_snapshot)
    teams = clean_teams(data, strengths)
    fixtures = clean_fixtures(fixtures_raw)
    meta = clean_meta(data)

    with open("fpl_players.json", "w") as f:
        json.dump(players, f, indent=2)

    with open("fpl_teams.json", "w") as f:
        json.dump(teams, f, indent=2)

    with open("fpl_fixtures.json", "w") as f:
        json.dump(fixtures, f, indent=2)

    with open("fpl_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    print(f"Saved {len(players)} players to fpl_players.json")
    print(f"Saved {len(teams)} teams to fpl_teams.json")
    print(f"Saved {len(fixtures)} fixtures to fpl_fixtures.json")
    print(f"Saved meta info to fpl_meta.json")


if __name__ == "__main__":
    main()
