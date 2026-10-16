"""Playoff-Wahrscheinlichkeiten per Monte-Carlo-Simulation (10.000 Läufe).

Nutzt echte wöchentliche Team-Punktzahlen aus den bisher gespielten Wochen,
um je Team einen Mittelwert und eine Streuung zu schätzen, und die bekannten
künftigen Matchup-Paarungen aus dem Sleeper-Spielplan der Liga. Für jeden
Durchlauf wird je Restwoche und Team eine Zufallspunktzahl aus einer
Normalverteilung gezogen, daraus Sieger/Verlierer und am Ende die Platzierung
bestimmt. Kein spielerbasiertes Projektionsmodell für künftige Wochen, keine
Berücksichtigung von Verletzungen, Bye Weeks einzelner Spieler oder
Kaderwechseln - eine grobe statistische Näherung, kein echtes Vorhersagemodell.
"""

import random

TRIALS = 10000
FALLBACK_SIGMA = 22.0
MIN_GAMES_FOR_OWN_STATS = 3
SEED = 42


def _team_weekly_scores(roster_id, historical_matchups_by_week):
    scores = []
    for wk in sorted(historical_matchups_by_week.keys()):
        for entry in historical_matchups_by_week[wk]:
            if entry.get("roster_id") == roster_id:
                pts = entry.get("points")
                if pts:
                    scores.append(pts)
                break
    return scores


def _mean_sigma(scores, league_mean, league_sigma):
    if len(scores) < MIN_GAMES_FOR_OWN_STATS:
        mean = sum(scores) / len(scores) if scores else league_mean
        return mean, league_sigma
    mean = sum(scores) / len(scores)
    if len(scores) > 1:
        var = sum((s - mean) ** 2 for s in scores) / (len(scores) - 1)
        sigma = max(8.0, var ** 0.5)
    else:
        sigma = league_sigma
    return mean, sigma


def compute(teams, historical_matchups_by_week, sim_matchups_by_week, playoff_teams):
    """teams: Liste der Team-Dicts (roster_id, team_name, wins, losses, ties, fpts).
    historical_matchups_by_week: {woche: [matchup-Eintrag, ...]} für bereits
      abgeschlossene Wochen (für Mittelwert/Streuung je Team).
    sim_matchups_by_week: {woche: [matchup-Eintrag, ...]} für alle noch zu
      simulierenden Wochen der regulären Saison (inkl. laufender Woche,
      falls diese noch nicht final ist), bis exklusive Playoff-Start.
    playoff_teams: Anzahl Playoff-Plätze laut Liga-Einstellungen.
    """
    if not teams:
        return {"trials": 0, "results": [], "method_note": "Keine Teams vorhanden."}

    all_scores = [s for rid in [t["roster_id"] for t in teams] for s in _team_weekly_scores(rid, historical_matchups_by_week)]
    league_mean = sum(all_scores) / len(all_scores) if all_scores else 100.0

    team_stats = {}
    for t in teams:
        rid = t["roster_id"]
        scores = _team_weekly_scores(rid, historical_matchups_by_week)
        team_stats[rid] = _mean_sigma(scores, league_mean, FALLBACK_SIGMA)

    pairings_by_week = {}
    for wk, entries in sim_matchups_by_week.items():
        by_matchup = {}
        for e in entries:
            by_matchup.setdefault(e["matchup_id"], []).append(e["roster_id"])
        pairings_by_week[wk] = [tuple(v) for v in by_matchup.values() if len(v) == 2]

    base_wins = {t["roster_id"]: t["wins"] for t in teams}
    base_losses = {t["roster_id"]: t["losses"] for t in teams}
    base_fpts = {t["roster_id"]: t["fpts"] for t in teams}

    rng = random.Random(SEED)
    playoff_count = {t["roster_id"]: 0 for t in teams}
    win_total_sum = {t["roster_id"]: 0 for t in teams}

    weeks = sorted(pairings_by_week.keys())
    for _ in range(TRIALS):
        wins = dict(base_wins)
        fpts = dict(base_fpts)
        for wk in weeks:
            for a, b in pairings_by_week[wk]:
                ma, sa = team_stats.get(a, (league_mean, FALLBACK_SIGMA))
                mb, sb = team_stats.get(b, (league_mean, FALLBACK_SIGMA))
                score_a = max(0.0, rng.gauss(ma, sa))
                score_b = max(0.0, rng.gauss(mb, sb))
                fpts[a] = fpts.get(a, 0) + score_a
                fpts[b] = fpts.get(b, 0) + score_b
                if score_a > score_b:
                    wins[a] = wins.get(a, 0) + 1
                elif score_b > score_a:
                    wins[b] = wins.get(b, 0) + 1
                else:
                    wins[a] = wins.get(a, 0) + 0.5
                    wins[b] = wins.get(b, 0) + 0.5

        ranking = sorted(wins.keys(), key=lambda rid: (-wins[rid], -fpts.get(rid, 0)))
        for rid in ranking[:playoff_teams]:
            playoff_count[rid] += 1
        for rid, w in wins.items():
            win_total_sum[rid] += w

    team_names = {t["roster_id"]: t["team_name"] for t in teams}
    results = [
        {
            "roster_id": rid,
            "team_name": team_names.get(rid, f"Team {rid}"),
            "current_wins": base_wins[rid],
            "current_losses": base_losses[rid],
            "playoff_probability": round(playoff_count[rid] / TRIALS * 100, 1),
            "projected_final_wins": round(win_total_sum[rid] / TRIALS, 1),
        }
        for rid in playoff_count
    ]
    results.sort(key=lambda r: r["playoff_probability"], reverse=True)

    return {
        "trials": TRIALS,
        "playoff_teams": playoff_teams,
        "weeks_simulated": weeks,
        "results": results,
        "method_note": (
            "Monte-Carlo-Simulation mit 10.000 Durchläufen: je Team wird aus den "
            "bisherigen Wochenpunkten ein Mittelwert und eine Streuung geschätzt "
            "(bei weniger als 3 gespielten Wochen Liga-Durchschnitt als Fallback-"
            "Streuung) und daraus für jede verbleibende Woche eine Zufallspunktzahl "
            "gezogen. Kein spielerbasiertes Projektionsmodell für künftige Wochen, "
            "keine Berücksichtigung von Verletzungen, einzelnen Bye Weeks oder "
            "Kaderwechseln während der Saison - eine grobe statistische Näherung, "
            "kein echtes Vorhersagemodell."
        ),
    }
