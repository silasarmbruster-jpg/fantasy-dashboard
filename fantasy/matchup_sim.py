"""Siegwahrscheinlichkeit für das aktuelle Wochen-Matchup per Monte-Carlo-
Simulation (10.000 Durchläufe) statt eines einfachen Vergleichs der
Projection-Summen. Nutzt eine je Position empirisch aus den tatsächlichen
Wochenpunkten dieser Saison geschätzte Streuung, und übernimmt für Spieler,
die in dieser Woche schon echte Punkte erzielt haben, diese fix statt sie
erneut zu simulieren."""

import random

TRIALS = 10000
FALLBACK_SIGMA = 6.0
MIN_SAMPLES_FOR_OWN_SIGMA = 20
SEED = 11


def _position_stddev(players):
    """pos -> empirische Streuung der Wochenpunkte über alle relevanten
    Spieler dieser Saison. Fallback-Wert bei zu wenigen Datenpunkten."""
    samples_by_pos = {}
    for p in players.values():
        pos = p.get("position")
        for pts in (p.get("weekly_points") or {}).values():
            samples_by_pos.setdefault(pos, []).append(pts)

    stddev = {}
    for pos, samples in samples_by_pos.items():
        if len(samples) < MIN_SAMPLES_FOR_OWN_SIGMA:
            stddev[pos] = FALLBACK_SIGMA
            continue
        mean = sum(samples) / len(samples)
        var = sum((s - mean) ** 2 for s in samples) / (len(samples) - 1)
        stddev[pos] = max(2.5, var ** 0.5)
    return stddev


def _side_fixed_and_random(starters, players, position_stddev):
    """Trennt eine Seite in bereits feststehende Punkte (Spieler mit schon
    erzielten Punkten diese Woche) und noch zu simulierende Slots
    (mean, sigma) für alle anderen."""
    fixed_total = 0.0
    random_specs = []
    for s in starters:
        pid = s.get("player_id")
        p = players.get(pid)
        if not p:
            continue
        actual = s.get("actual_points") or 0.0
        if actual:
            # Spieler hat in dieser Woche schon echte Punkte erzielt - als
            # fix übernehmen statt erneut zu würfeln. Vereinfachung: ein
            # Spieler, der spielt aber tatsächlich 0 Punkte erzielt, wird
            # hierdurch wie "noch nicht gespielt" behandelt (keine
            # Live-Spielstatus-Daten verfügbar, um das zu unterscheiden).
            fixed_total += actual
        else:
            mean = p.get("projection_week") or 0.0
            sigma = position_stddev.get(p.get("position"), FALLBACK_SIGMA)
            random_specs.append((mean, sigma))
    return fixed_total, random_specs


def simulate_win_probability(me_starters, opp_starters, players, trials=TRIALS, seed=SEED):
    """me_starters/opp_starters: Liste von {player_id, actual_points} aus
    dem aktuellen Matchup (wie in data['matchup']['me']['starters'])."""
    position_stddev = _position_stddev(players)
    me_fixed, me_random = _side_fixed_and_random(me_starters, players, position_stddev)
    opp_fixed, opp_random = _side_fixed_and_random(opp_starters, players, position_stddev)

    rng = random.Random(seed)
    wins = 0.0
    for _ in range(trials):
        me_total = me_fixed + sum(max(0.0, rng.gauss(m, s)) for m, s in me_random)
        opp_total = opp_fixed + sum(max(0.0, rng.gauss(m, s)) for m, s in opp_random)
        if me_total > opp_total:
            wins += 1
        elif me_total == opp_total:
            wins += 0.5
    prob = wins / trials * 100
    return round(max(1.0, min(99.0, prob)), 1)
