"""Statische Konfiguration für das Fantasy-Dashboard."""

SLEEPER_USERNAME = "Club3"

# Liga ist fest auf die vom Nutzer bestätigte 14-Team-PPR-Liga gepinnt.
# Es gab zwei 14-Team-Ligen für Club3; der Nutzer hat sich für diese entschieden.
LEAGUE_ID = "1382641066959720448"

RELEVANT_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}

# Wie viele zusätzliche (nicht verrosterte) Free Agents pro Position maximal
# in data.json aufgenommen werden, um die Datei klein zu halten.
MAX_FREE_AGENTS_PER_POSITION = {
    "QB": 40,
    "RB": 90,
    "WR": 110,
    "TE": 50,
    "K": 40,
    "DEF": 32,
}

# Wie viele vergangene Wochen für Charts/Durchschnitte maximal mitgenommen werden.
MAX_HISTORY_WEEKS = 8
