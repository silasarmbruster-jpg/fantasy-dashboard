"""Kleine geteilte Hilfsfunktionen ohne Abhängigkeiten auf andere Module,
um zirkuläre Importe zwischen model.py und planner.py zu vermeiden."""

import math


def win_probability(diff, sigma=18.0):
    """Heuristische Siegwahrscheinlichkeit aus einer Punkte-Differenz
    (Normalverteilung um 0 mit sigma als angenommene wöchentliche Streuung).
    Kein echtes Vorhersagemodell, nur eine grobe Orientierung."""
    z = diff / (sigma * math.sqrt(2))
    prob = 0.5 * (1 + math.erf(z))
    return round(max(0.01, min(0.99, prob)) * 100, 1)
