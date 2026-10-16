"""Playoff-Wahrscheinlichkeiten per Monte-Carlo-Simulation (10.000 Läufe).

Nutzt echte wöchentliche Team-Punktzahlen aus den bisher gespielten Wochen,
um je Team einen Mittelwert und eine Streuung zu schätzen, und die bekannten
künftigen Matchup-Paarungen aus dem Sleeper-Spielplan der Liga. Für jeden
Durchlauf wird je Restwoche und Team eine Zufallspunktzahl aus einer
Normalverteilung gezogen, daraus Sieger/Verlierer und am Ende die Platzierung
bestimmt (bei gleicher Bilanz entscheiden die erzielten Punkte - Liga-
Tiebreak). Kein spielerbasiertes Projektionsmodell für künftige Wochen, keine
Berücksichtigung von Verletzungen, Bye Weeks einzelner Spieler oder
Kaderwechseln - eine grobe statistische Näherung, kein echtes Vorhersagemodell.
"""

import random

TRIALS = 10000
KEY_GAME_TRIALS = 3000  # weniger Durchläufe für die Sensitivitätsanalyse je Restwoche (Performance)
FALLBACK_SIGMA = 22.0
MIN_GAMES_FOR_OWN_STATS = 3
SEED = 42
TOP_KEY_GAMES = 3


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


def _run_trials(rng, team_stats, pairings_by_week, weeks, base_wins, base_fpts,
                 playoff_teams, trials, league_mean, forced=None):
    """Führt `trials` Durchläufe aus und gibt (playoff_count, win_total_sum,
    rank_sum) je roster_id zurück. `forced`: optionales {(week, roster_id):
    bool} - erzwingt für diese Seite des Matchups in dieser Woche einen Sieg
    (True) oder eine Niederlage (False), Rest bleibt zufällig. Für die
    Sensitivitätsanalyse "wichtigste Spiele"."""
    playoff_count = {rid: 0 for rid in base_wins}
    win_total_sum = {rid: 0 for rid in base_wins}
    rank_sum = {rid: 0 for rid in base_wins}

    for _ in range(trials):
        wins = dict(base_wins)
        fpts = dict(base_fpts)
        for wk in weeks:
            for a, b in pairings_by_week[wk]:
                ma, sa = team_stats.get(a, (league_mean, FALLBACK_SIGMA))
                mb, sb = team_stats.get(b, (league_mean, FALLBACK_SIGMA))
                score_a = max(0.0, rng.gauss(ma, sa))
                score_b = max(0.0, rng.gauss(mb, sb))

                force_a = forced.get((wk, a)) if forced else None
                force_b = forced.get((wk, b)) if forced else None
                if force_a is True or force_b is False:
                    score_a, score_b = max(score_a, score_b) + 0.1, min(score_a, score_b)
                elif force_a is False or force_b is True:
                    score_a, score_b = min(score_a, score_b), max(score_a, score_b) + 0.1

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
        for i, rid in enumerate(ranking, start=1):
            rank_sum[rid] += i
        for rid in ranking[:playoff_teams]:
            playoff_count[rid] += 1
        for rid, w in wins.items():
            win_total_sum[rid] += w

    return playoff_count, win_total_sum, rank_sum


def _key_games(my_roster_id, team_stats, pairings_by_week, weeks, base_wins, base_fpts,
               playoff_teams, league_mean, baseline_my_prob, team_names):
    """Für jede meiner restlichen Wochen: wie stark ändert sich MEINE
    Playoff-Chance, wenn ich dieses eine Spiel sicher gewinne vs. sicher
    verliere (Rest bleibt zufällig)? Größte Schwankung = wichtigstes Spiel."""
    my_weeks = [wk for wk in weeks if any(my_roster_id in pair for pair in pairings_by_week[wk])]
    results = []
    for wk in my_weeks:
        opponent_rid = next((b if a == my_roster_id else a for a, b in pairings_by_week[wk] if my_roster_id in (a, b)), None)
        if opponent_rid is None:
            continue
        rng = random.Random(SEED + wk)
        win_count, _, _ = _run_trials(
            rng, team_stats, pairings_by_week, weeks, base_wins, base_fpts, playoff_teams,
            KEY_GAME_TRIALS, league_mean, forced={(wk, my_roster_id): True},
        )
        rng = random.Random(SEED + wk)
        lose_count, _, _ = _run_trials(
            rng, team_stats, pairings_by_week, weeks, base_wins, base_fpts, playoff_teams,
            KEY_GAME_TRIALS, league_mean, forced={(wk, my_roster_id): False},
        )
        win_prob = win_count[my_roster_id] / KEY_GAME_TRIALS * 100
        lose_prob = lose_count[my_roster_id] / KEY_GAME_TRIALS * 100
        swing = round(win_prob - lose_prob, 1)
        results.append({
            "week": wk,
            "opponent_roster_id": opponent_rid,
            "opponent_team_name": team_names.get(opponent_rid, f"Team {opponent_rid}"),
            "playoff_probability_if_win": round(win_prob, 1),
            "playoff_probability_if_loss": round(lose_prob, 1),
            "swing": swing,
        })
    results.sort(key=lambda r: r["swing"], reverse=True)
    return results[:TOP_KEY_GAMES]


def compute(teams, historical_matchups_by_week, sim_matchups_by_week, playoff_teams, my_roster_id=None):
    """teams: Liste der Team-Dicts (roster_id, team_name, wins, losses, ties, fpts).
    historical_matchups_by_week: {woche: [matchup-Eintrag, ...]} für bereits
      abgeschlossene Wochen (für Mittelwert/Streuung je Team).
    sim_matchups_by_week: {woche: [matchup-Eintrag, ...]} für alle noch zu
      simulierenden Wochen der regulären Saison (inkl. laufender Woche,
      falls diese noch nicht final ist), bis exklusive Playoff-Start.
    playoff_teams: Anzahl Playoff-Plätze laut Liga-Einstellungen.
    my_roster_id: für die "wichtigste Spiele"-Sensitivitätsanalyse.
    """
    if not teams:
        return {"trials": 0, "results": [], "key_games": [], "method_note": "Keine Teams vorhanden."}

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
    team_names = {t["roster_id"]: t["team_name"] for t in teams}

    weeks = sorted(pairings_by_week.keys())
    rng = random.Random(SEED)
    playoff_count, win_total_sum, rank_sum = _run_trials(
        rng, team_stats, pairings_by_week, weeks, base_wins, base_fpts, playoff_teams, TRIALS, league_mean,
    )

    results = [
        {
            "roster_id": rid,
            "team_name": team_names.get(rid, f"Team {rid}"),
            "current_wins": base_wins[rid],
            "current_losses": base_losses[rid],
            "playoff_probability": round(playoff_count[rid] / TRIALS * 100, 1),
            "projected_final_wins": round(win_total_sum[rid] / TRIALS, 1),
            "projected_rank": round(rank_sum[rid] / TRIALS, 1),
        }
        for rid in playoff_count
    ]
    results.sort(key=lambda r: r["playoff_probability"], reverse=True)

    key_games = []
    if my_roster_id is not None and my_roster_id in base_wins:
        my_baseline = next((r["playoff_probability"] for r in results if r["roster_id"] == my_roster_id), 0)
        key_games = _key_games(
            my_roster_id, team_stats, pairings_by_week, weeks, base_wins, base_fpts,
            playoff_teams, league_mean, my_baseline, team_names,
        )

    return {
        "trials": TRIALS,
        "playoff_teams": playoff_teams,
        "weeks_simulated": weeks,
        "results": results,
        "key_games": key_games,
        "method_note": (
            "Monte-Carlo-Simulation mit 10.000 Durchläufen: je Team wird aus den "
            "bisherigen Wochenpunkten ein Mittelwert und eine Streuung geschätzt "
            "(bei weniger als 3 gespielten Wochen Liga-Durchschnitt als Fallback-"
            "Streuung) und daraus für jede verbleibende Woche eine Zufallspunktzahl "
            "gezogen. Bei gleicher Bilanz entscheiden die erzielten Punkte (Liga-"
            "Tiebreak). Kein spielerbasiertes Projektionsmodell für künftige Wochen, "
            "keine Berücksichtigung von Verletzungen, einzelnen Bye Weeks oder "
            "Kaderwechseln während der Saison - eine grobe statistische Näherung, "
            "kein echtes Vorhersagemodell. 'Wichtigste Spiele': Sensitivitätsanalyse "
            "mit 3.000 Durchläufen je Szenario (sicherer Sieg vs. sichere Niederlage "
            "in dieser einen Woche, Rest bleibt zufällig)."
        ),
    }
