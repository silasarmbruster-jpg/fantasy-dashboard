#!/usr/bin/env python3
"""Baut docs/index.html + docs/data.json für das Fantasy-Football-Dashboard.

Nutzung: python3 build.py
Holt alle Daten ausschließlich über öffentliche APIs (Sleeper, FantasyCalc)
ohne Login. Schlägt ein Endpoint fehl, wird das offen geloggt und mit
Fallback/leeren Werten weitergearbeitet statt Daten zu erfinden.
"""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from fantasy import config, model
from fantasy import sleeper_api as sleeper
from fantasy import fantasycalc_api


def log(msg):
    print(f"[build] {msg}", flush=True)


def fetch_all_relevant_player_ids(rosters, players_db, trending_add_list, trending_drop_list):
    rostered = set()
    for r in rosters:
        rostered |= set(r.get("players") or [])

    trending_ids_raw = {e["player_id"] for e in trending_add_list} | {e["player_id"] for e in trending_drop_list}
    trending_ids = {
        pid for pid in trending_ids_raw
        if (players_db.get(pid) or {}).get("position") in config.RELEVANT_POSITIONS
    }

    # Alle 32 Team-Defenses immer aufnehmen (kleine, feste Menge).
    def_ids = {pid for pid, p in players_db.items() if p.get("position") == "DEF"}

    # Zusätzliche Free Agents je Position, begrenzt und nach Sleeper search_rank sortiert,
    # damit data.json klein bleibt.
    candidates_by_pos = {}
    for pid, p in players_db.items():
        if pid in rostered or pid in def_ids:
            continue
        pos = p.get("position")
        if pos not in config.RELEVANT_POSITIONS:
            continue
        if not p.get("active"):
            continue
        if not p.get("team"):
            continue
        candidates_by_pos.setdefault(pos, []).append((p.get("search_rank") or 9999, pid))

    free_agents = set()
    for pos, cands in candidates_by_pos.items():
        limit = config.MAX_FREE_AGENTS_PER_POSITION.get(pos, 50)
        cands.sort()
        free_agents |= {pid for _, pid in cands[:limit]}

    return rostered | def_ids | free_agents | trending_ids


def main():
    log(f"Suche Liga {config.LEAGUE_ID} für Nutzer {config.SLEEPER_USERNAME} ...")
    state = sleeper.get_state()
    season = state["season"]
    current_week = state.get("display_week") or state.get("week") or 1
    log(f"Saison {season}, aktuelle Woche {current_week}")

    league = sleeper.get_league(config.LEAGUE_ID)
    rosters = sleeper.get_rosters(config.LEAGUE_ID)
    users = sleeper.get_league_users(config.LEAGUE_ID)
    matchups = sleeper.get_matchups(config.LEAGUE_ID, current_week)

    log("Lade Spieler-Datenbank (einmalig, ~15MB) ...")
    players_db = sleeper.get_all_players()

    log("Lade NFL-Spielplan für Bye Weeks / Restprogramm ...")
    try:
        schedule = sleeper.get_schedule(season)
    except Exception as exc:  # noqa: BLE001
        log(f"WARNUNG: Spielplan nicht verfügbar ({exc}); Bye Weeks bleiben leer.")
        schedule = []

    log("Lade Trending Adds/Drops ...")
    try:
        trending_add_list = sleeper.get_trending("add", limit=75)
        trending_drop_list = sleeper.get_trending("drop", limit=75)
    except Exception as exc:  # noqa: BLE001
        log(f"WARNUNG: Trending-Endpoint nicht verfügbar ({exc}).")
        trending_add_list, trending_drop_list = [], []

    relevant_ids = fetch_all_relevant_player_ids(rosters, players_db, trending_add_list, trending_drop_list)
    log(f"{len(relevant_ids)} relevante Spieler ausgewählt (von {len(players_db)} gesamt).")

    log(f"Lade Wochenstatistiken 1..{current_week} ...")
    weekly_stats_by_week = {}
    for wk in range(1, current_week + 1):
        try:
            weekly_stats_by_week[wk] = sleeper.get_weekly_stats(season, wk)
        except Exception as exc:  # noqa: BLE001
            log(f"WARNUNG: Stats für Woche {wk} nicht verfügbar ({exc}).")
            weekly_stats_by_week[wk] = {}

    log(f"Lade Projections für Woche {current_week} ...")
    try:
        weekly_proj = sleeper.get_weekly_projections(season, current_week)
    except Exception as exc:  # noqa: BLE001
        log(f"WARNUNG: Projections nicht verfügbar ({exc}).")
        weekly_proj = {}

    log("Lade FantasyCalc Trade-Werte ...")
    trade_values = fantasycalc_api.get_trade_values()
    if not trade_values:
        log("WARNUNG: Keine FantasyCalc-Werte erhalten, Trade-Werte bleiben leer.")

    log("Baue data.json-Modell ...")
    data = model.build(
        state=state,
        league=league,
        rosters=rosters,
        users=users,
        matchups=matchups,
        players_db=players_db,
        schedule=schedule,
        weekly_stats_by_week=weekly_stats_by_week,
        weekly_proj=weekly_proj,
        trade_values=trade_values,
        trending_add_list=trending_add_list,
        trending_drop_list=trending_drop_list,
        relevant_player_ids=relevant_ids,
        my_username=config.SLEEPER_USERNAME,
    )

    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)

    site = ROOT / "site"
    for item in site.iterdir():
        if item.is_file():
            shutil.copy2(item, docs / item.name)

    data_path = docs / "data.json"
    data_path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    size_kb = data_path.stat().st_size / 1024
    log(f"data.json geschrieben ({size_kb:.1f} KB) -> {data_path}")
    log(f"Mein Team: {data['me']['team_name']} (Rang {data['me']['rank']}/{data['league']['total_rosters']})")
    log("Fertig.")


if __name__ == "__main__":
    main()
