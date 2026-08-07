"""
fetch_my_team.py
------------------
Pulls a specific FPL manager's squad (by their team ID) from the official
API and saves it as fpl_my_team.json, ready for my_team.html to display.

Usage:
    python fetch_my_team.py 1234567
    (or just run it with no argument and it'll ask you for your team ID)

Finding your team ID: log into fantasy.premierleague.com, go to "Points",
and look at the URL — it's the number after /entry/, e.g.
fantasy.premierleague.com/entry/1234567/event/1 -> your ID is 1234567

Run fetch_fpl_data.py first if you haven't already today — this script
reuses fpl_players.json and fpl_meta.json to fill in player names/stats.
"""

import json
import sys
import requests

ENTRY_URL = "https://fantasy.premierleague.com/api/entry/{entry_id}/"
PICKS_URL = "https://fantasy.premierleague.com/api/entry/{entry_id}/event/{event_id}/picks/"

POSITIONS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def get_team_id():
    if len(sys.argv) > 1:
        return sys.argv[1]
    return input("Enter your FPL team ID (from the URL when you're logged in): ").strip()


def load_local_json(filename, friendly_name):
    try:
        with open(filename) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Couldn't find {filename}. Run fetch_fpl_data.py first, then try this again.")
        sys.exit(1)


def fetch_entry_summary(entry_id):
    response = requests.get(ENTRY_URL.format(entry_id=entry_id), timeout=15)
    response.raise_for_status()
    return response.json()


def fetch_picks(entry_id, event_id):
    response = requests.get(PICKS_URL.format(entry_id=entry_id, event_id=event_id), timeout=15)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def main():
    entry_id = get_team_id()

    meta = load_local_json("fpl_meta.json", "meta")
    players = load_local_json("fpl_players.json", "players")
    players_by_id = {p["id"]: p for p in players}

    print(f"Fetching team {entry_id}...")
    try:
        summary = fetch_entry_summary(entry_id)
    except requests.exceptions.HTTPError:
        print(f"Couldn't find a team with ID {entry_id}. Double check the number and try again.")
        sys.exit(1)

    # Try next gameweek's picks first (squads are saved before the season
    # even starts), falling back to the current gameweek if that's empty.
    event_to_try = meta.get("next_event") or meta.get("current_event") or 1
    picks_data = fetch_picks(entry_id, event_to_try)
    if picks_data is None and meta.get("current_event"):
        event_to_try = meta["current_event"]
        picks_data = fetch_picks(entry_id, event_to_try)

    if picks_data is None:
        print("This team doesn't have a squad saved yet for the upcoming gameweek.")
        sys.exit(1)

    squad = []
    for pick in picks_data["picks"]:
        player = players_by_id.get(pick["element"])
        if not player:
            continue
        squad.append({
            **player,
            "squad_position": pick["position"],   # 1-15, order within squad
            "is_captain": pick["is_captain"],
            "is_vice_captain": pick["is_vice_captain"],
            "multiplier": pick["multiplier"],       # 0 = benched, 1 = playing, 2 = captain
        })

    my_team = {
        "manager_name": f'{summary["player_first_name"]} {summary["player_last_name"]}',
        "team_name": summary["name"],
        "overall_rank": summary.get("summary_overall_rank"),
        "total_points": summary.get("summary_overall_points"),
        "bank": picks_data["entry_history"]["bank"] / 10,
        "team_value": picks_data["entry_history"]["value"] / 10,
        "event": event_to_try,
        "squad": squad,
    }

    with open("fpl_my_team.json", "w") as f:
        json.dump(my_team, f, indent=2)

    print(f"Saved {my_team['team_name']} ({my_team['manager_name']}) to fpl_my_team.json")
    print(f"{len(squad)} players loaded for Gameweek {event_to_try}")


if __name__ == "__main__":
    main()
