"""Client für die öffentliche FantasyCalc-API (Trade-Werte)."""

import json
import urllib.error
import urllib.request

from .sleeper_api import USER_AGENT, SleeperError

_URL = (
    "https://api.fantasycalc.com/values/current"
    "?isDynasty=false&numQbs=1&numTeams=14&ppr=1"
)


def get_trade_values():
    """Gibt {sleeper_player_id: {value, overallRank, positionRank, trend30Day}} zurück.

    Bei Fehlern wird ein leeres Dict zurückgegeben statt Daten zu erfinden;
    der Aufrufer markiert Trade-Werte dann als nicht verfügbar.
    """
    try:
        req = urllib.request.Request(_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = json.loads(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, SleeperError) as exc:
        print(f"[warn] FantasyCalc nicht erreichbar, Trade-Werte fehlen: {exc}")
        return {}

    out = {}
    for entry in raw:
        player = entry.get("player") or {}
        sleeper_id = player.get("sleeperId")
        if not sleeper_id:
            continue
        out[str(sleeper_id)] = {
            "value": entry.get("value"),
            "overallRank": entry.get("overallRank"),
            "positionRank": entry.get("positionRank"),
            "trend30Day": entry.get("trend30Day"),
        }
    return out
