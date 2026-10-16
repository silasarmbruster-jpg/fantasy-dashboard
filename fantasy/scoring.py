"""Berechnet Fantasy-Punkte aus Rohstatistiken nach den individuellen
Scoring-Settings der Liga (statt pauschaler PPR-Presets zu übernehmen)."""


def score(stat_dict, scoring_settings):
    """stat_dict: Rohstatistik-Kategorien eines Spielers einer Woche (z.B. {"rec": 5, "rec_yd": 60}).
    scoring_settings: league["scoring_settings"] aus der Sleeper-API.
    """
    if not stat_dict:
        return 0.0
    total = 0.0
    for key, weight in scoring_settings.items():
        value = stat_dict.get(key)
        if value:
            total += value * weight
    return round(total, 2)
