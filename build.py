#!/usr/bin/env python3
"""Baut docs/index.html + docs/data.json für das Fantasy-Football-Dashboard.

Nutzung: python3 build.py
Holt alle Daten ausschließlich über öffentliche APIs (Sleeper, FantasyCalc)
ohne Login. Schlägt ein Endpoint fehl, wird das offen geloggt und mit
Fallback/leeren Werten weitergearbeitet statt Daten zu erfinden. Vor dem
Schreiben von docs/data.json läuft eine Plausibilitätsprüfung; schlägt sie
fehl, wird NICHTS geschrieben und die zuletzt veröffentlichte, funktionierende
Version bleibt live (siehe _plausibility_check).
"""

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import subprocess

from fantasy import config, model, history, espn_odds, league_rules
from fantasy import sleeper_api as sleeper
from fantasy import fantasycalc_api
from fantasy import tradefinder


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
        and (players_db.get(pid) or {}).get("active")
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


def _plausibility_check(data):
    """Grobe Sanity-Checks auf dem fertigen data.json-Modell. Schlägt einer
    fehl, wird der Lauf verworfen (data.json/history.json NICHT geschrieben)
    und die zuletzt veröffentlichte Version bleibt live, statt eine kaputte
    oder leere Seite zu deployen."""
    errors = []

    total_rosters = data["league"]["total_rosters"]
    if total_rosters != 14:
        errors.append(f"Erwartet 14 Teams in der Liga, aber {total_rosters} gemeldet.")
    if len(data["teams"]) != total_rosters:
        errors.append(f"{len(data['teams'])} Teams aufgebaut, aber {total_rosters} erwartet.")

    empty_rosters = [t["team_name"] for t in data["teams"] if not t.get("players")]
    if empty_rosters:
        errors.append(f"Leere Kader gefunden: {', '.join(empty_rosters)}.")

    if not data["players"]:
        errors.append("Spieler-Datenbank (data['players']) ist leer.")

    if not data["my_roster"]["slots"]:
        errors.append("Eigene Start-Slots sind leer.")

    trade_values = [p["trade_value"] for p in data["players"].values() if p.get("trade_value") is not None]
    if trade_values:
        lo, hi = min(trade_values), max(trade_values)
        if lo < 0 or hi > 20000:
            errors.append(f"Trade-Werte außerhalb des plausiblen Bereichs (min={lo}, max={hi}).")

    if data["league"]["week"] < 1 or data["league"]["week"] > 18:
        errors.append(f"Unplausible aktuelle Woche: {data['league']['week']}.")

    return errors


def main():
    log(f"Suche Liga {config.LEAGUE_ID} für Nutzer {config.SLEEPER_USERNAME} ...")
    source_status = {}

    state = sleeper.get_state()
    season = state["season"]
    current_week = state.get("display_week") or state.get("week") or 1
    log(f"Saison {season}, aktuelle Woche {current_week}")

    league = sleeper.get_league(config.LEAGUE_ID)
    rosters = sleeper.get_rosters(config.LEAGUE_ID)
    users = sleeper.get_league_users(config.LEAGUE_ID)
    matchups = sleeper.get_matchups(config.LEAGUE_ID, current_week)
    playoff_week_start = league["settings"].get("playoff_week_start") or 15

    log("Lade Spieler-Datenbank (einmalig, ~15MB) ...")
    players_db = sleeper.get_all_players()

    log("Lade NFL-Spielplan für Bye Weeks / Restprogramm ...")
    try:
        schedule = sleeper.get_schedule(season)
        source_status["schedule"] = "ok"
    except Exception as exc:  # noqa: BLE001
        log(f"WARNUNG: Spielplan nicht verfügbar ({exc}); Bye Weeks bleiben leer.")
        schedule = []
        source_status["schedule"] = f"fehlgeschlagen: {exc}"

    log("Lade Trending Adds/Drops ...")
    try:
        trending_add_list = sleeper.get_trending("add", limit=75)
        trending_drop_list = sleeper.get_trending("drop", limit=75)
        source_status["trending"] = "ok"
    except Exception as exc:  # noqa: BLE001
        log(f"WARNUNG: Trending-Endpoint nicht verfügbar ({exc}).")
        trending_add_list, trending_drop_list = [], []
        source_status["trending"] = f"fehlgeschlagen: {exc}"

    relevant_ids = fetch_all_relevant_player_ids(rosters, players_db, trending_add_list, trending_drop_list)
    log(f"{len(relevant_ids)} relevante Spieler ausgewählt (von {len(players_db)} gesamt).")

    log(f"Lade Wochenstatistiken 1..{current_week} ...")
    weekly_stats_by_week = {}
    stats_failures = []
    for wk in range(1, current_week + 1):
        try:
            weekly_stats_by_week[wk] = sleeper.get_weekly_stats(season, wk)
        except Exception as exc:  # noqa: BLE001
            log(f"WARNUNG: Stats für Woche {wk} nicht verfügbar ({exc}).")
            weekly_stats_by_week[wk] = {}
            stats_failures.append(wk)
    source_status["weekly_stats"] = "ok" if not stats_failures else f"fehlgeschlagen für Wochen {stats_failures}"

    log(f"Lade Projections für Woche {current_week} ...")
    try:
        weekly_proj = sleeper.get_weekly_projections(season, current_week)
        source_status["projections"] = "ok"
    except Exception as exc:  # noqa: BLE001
        log(f"WARNUNG: Projections nicht verfügbar ({exc}).")
        weekly_proj = {}
        source_status["projections"] = f"fehlgeschlagen: {exc}"

    rules = league_rules.parse(league)
    log(
        f"Liga-Regeln gelesen: Typ={['Redraft','Keeper','Dynasty'][rules['league_type']] if rules['league_type'] in (0,1,2) else rules['league_type']}, "
        f"SUPER_FLEX={rules['super_flex']}, PPR={rules['ppr']}, Trade-Deadline=Woche {rules['trade_deadline']}."
    )

    log("Lade FantasyCalc Trade-Werte ...")
    trade_values = fantasycalc_api.get_trade_values(
        is_dynasty=rules["is_dynasty"], num_qbs=rules["num_qbs_fantasycalc"],
        num_teams=rules["num_teams"] or 14, ppr=rules["ppr"],
    )
    if not trade_values:
        log("WARNUNG: Keine FantasyCalc-Werte erhalten, Trade-Werte bleiben leer.")
        source_status["fantasycalc"] = "fehlgeschlagen: leere Antwort"
    else:
        source_status["fantasycalc"] = "ok"

    log("Lade zukünftige Matchups (für Restprogramm, Matchup-Vorhersage, Playoff-Simulation) ...")
    future_matchups_by_week = {}
    future_failures = []
    for wk in range(current_week + 1, 19):
        try:
            future_matchups_by_week[wk] = sleeper.get_matchups(config.LEAGUE_ID, wk)
        except Exception as exc:  # noqa: BLE001
            log(f"WARNUNG: Matchups für Woche {wk} nicht verfügbar ({exc}).")
            future_failures.append(wk)
    source_status["future_matchups"] = "ok" if not future_failures else f"fehlgeschlagen für Wochen {future_failures}"

    log(f"Lade historische Matchups 1..{current_week - 1} (für Playoff-Simulation) ...")
    historical_matchups_by_week = {}
    hist_failures = []
    for wk in range(1, current_week):
        try:
            historical_matchups_by_week[wk] = sleeper.get_matchups(config.LEAGUE_ID, wk)
        except Exception as exc:  # noqa: BLE001
            log(f"WARNUNG: Historische Matchups für Woche {wk} nicht verfügbar ({exc}).")
            hist_failures.append(wk)
    source_status["historical_matchups"] = "ok" if not hist_failures else f"fehlgeschlagen für Wochen {hist_failures}"

    # Für die Playoff-Simulation: laufende Woche (noch nicht final) + alle
    # künftigen Wochen der regulären Saison, bis exklusive Playoff-Start.
    sim_matchups_by_week = {current_week: matchups}
    for wk, entries in future_matchups_by_week.items():
        if wk < playoff_week_start:
            sim_matchups_by_week[wk] = entries

    log(f"Lade Transaktionen 1..{current_week} ...")
    transactions = []
    tx_failures = []
    for wk in range(1, current_week + 1):
        try:
            transactions.extend(sleeper.get_transactions(config.LEAGUE_ID, wk) or [])
        except Exception as exc:  # noqa: BLE001
            log(f"WARNUNG: Transaktionen für Woche {wk} nicht verfügbar ({exc}).")
            tx_failures.append(wk)
    source_status["transactions"] = "ok" if not tx_failures else f"fehlgeschlagen für Wochen {tx_failures}"

    log("Lade Vegas-Odds (ESPN, öffentlich) für die aktuelle Woche ...")
    vegas_odds = espn_odds.get_week_odds(season, current_week)
    if not vegas_odds:
        log("WARNUNG: Keine Vegas-Odds erhalten, Spread/Over-Under bleiben leer.")
        source_status["vegas_odds"] = "fehlgeschlagen: leere Antwort"
    else:
        source_status["vegas_odds"] = "ok"

    run_date = datetime.now(timezone.utc).isoformat()
    history_path = ROOT / "history.json"
    hist = history.build_updated(history_path, run_date, trade_values)
    trade_value_history = history.player_histories(hist, relevant_ids)

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
        future_matchups_by_week=future_matchups_by_week,
        transactions=transactions,
        vegas_odds=vegas_odds,
        trade_value_history=trade_value_history,
        historical_matchups_by_week=historical_matchups_by_week,
        sim_matchups_by_week=sim_matchups_by_week,
        source_status=source_status,
        league_rules=rules,
    )

    log("Prüfe Plausibilität des Build-Laufs ...")
    errors = _plausibility_check(data)
    if errors:
        log("FEHLER: Plausibilitätsprüfung fehlgeschlagen, Lauf wird verworfen:")
        for e in errors:
            log(f"  - {e}")
        log("docs/data.json und history.json werden NICHT verändert - die zuletzt veröffentlichte Version bleibt live.")
        sys.exit(1)
    log("Plausibilitätsprüfung bestanden.")

    log("Prüfe Trade-Finder-Invarianten (kein K/DEF, Wert-/Sinn-Regeln, keine Duplikate, jede Idee hat einen Anlass) ...")
    tf_errors = tradefinder.validate_proposals(data["trade_finder"], data["players"])
    if tf_errors:
        log("FEHLER: Trade-Finder-Invarianten verletzt, Lauf wird verworfen:")
        for e in tf_errors[:20]:
            log(f"  - {e}")
        log("docs/data.json und history.json werden NICHT verändert - die zuletzt veröffentlichte Version bleibt live.")
        sys.exit(1)
    tf = data["trade_finder"]
    n_packages = sum(len(lst) for e in tf["block_candidates"].values() for lst in e["by_format"].values())
    n_packages += sum(len(lst) for e in tf["target_candidates"].values() for lst in e["by_format"].values())
    n_ideas = sum(len(idea["items"]) for idea in tf["ideas"].values())
    log(
        f"Trade-Finder-Invarianten bestanden ({n_packages} Pakete über "
        f"{len(tf['block_candidates'])} Block-Spieler + {len(tf['target_candidates'])} Zielspieler geprüft, "
        f"{n_ideas} Trade-Ideen, Suche {tf['build_seconds']}s)."
    )

    log("Führe pytest-Testsuite aus ...")
    tests_dir = ROOT / "tests"
    if tests_dir.exists():
        result = subprocess.run([sys.executable, "-m", "pytest", str(tests_dir), "-q"], cwd=ROOT)
        if result.returncode != 0:
            log("FEHLER: pytest-Tests fehlgeschlagen, Lauf wird verworfen (siehe Ausgabe oben).")
            log("docs/data.json und history.json werden NICHT verändert - die zuletzt veröffentlichte Version bleibt live.")
            sys.exit(1)
        log("pytest-Tests bestanden.")
    else:
        log("WARNUNG: tests/-Verzeichnis nicht gefunden, pytest-Lauf übersprungen.")

    history.save(history_path, hist)
    log(f"history.json aktualisiert ({len(hist['runs'])} Läufe gespeichert).")

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
    failed_sources = [k for k, v in source_status.items() if v != "ok"]
    if failed_sources:
        log(f"Hinweis: Quellen mit Problemen in diesem Lauf: {', '.join(failed_sources)}.")
    log(f"Mein Team: {data['me']['team_name']} (Rang {data['me']['rank']}/{data['league']['total_rosters']})")
    log("Fertig.")


if __name__ == "__main__":
    main()
