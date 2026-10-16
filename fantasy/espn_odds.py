"""Holt Vegas-Odds (Spread, Over/Under) für die aktuelle NFL-Woche von
ESPNs öffentlicher API (kein Login/Key nötig). Rein optional: schlägt ein
Call fehl, bricht der Build nicht ab - Vegas-Infos bleiben für die
betroffenen Spiele dann einfach leer, statt Daten zu erfinden."""

import json
import urllib.error
import urllib.request

from .sleeper_api import USER_AGENT

_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?seasontype=2&week={week}&year={year}"
_ODDS = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{event_id}/competitions/{event_id}/odds"


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def get_week_odds(season, week):
    """team_abbr -> {spread, over_under, favorite, details, opponent, home}."""
    try:
        board = _get(_SCOREBOARD.format(week=week, year=season))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
        print(f"[warn] ESPN-Scoreboard nicht erreichbar, Vegas-Odds fehlen: {exc}")
        return {}

    out = {}
    for ev in board.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        teams = {c.get("homeAway"): c["team"]["abbreviation"] for c in comp.get("competitors", []) if c.get("team")}
        event_id = ev.get("id")
        if not event_id or "home" not in teams or "away" not in teams:
            continue
        try:
            odds_resp = _get(_ODDS.format(event_id=event_id))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
            continue
        items = odds_resp.get("items") or []
        if not items:
            continue
        best = items[0]
        home_fav = (best.get("homeTeamOdds") or {}).get("favorite")
        for side, team in (("home", teams["home"]), ("away", teams["away"])):
            is_fav = home_fav if side == "home" else (None if home_fav is None else not home_fav)
            out[team] = {
                "spread": best.get("spread"),
                "over_under": best.get("overUnder"),
                "favorite": is_fav,
                "details": best.get("details"),
                "opponent": teams["away"] if side == "home" else teams["home"],
                "home": side == "home",
            }
    return out
