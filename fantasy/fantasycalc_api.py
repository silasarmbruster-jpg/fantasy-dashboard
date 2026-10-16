"""Client für die öffentliche FantasyCalc-API (Trade-Werte)."""

import json
import urllib.error
import urllib.request

from .sleeper_api import USER_AGENT, SleeperError

_BASE_URL = "https://api.fantasycalc.com/values/current"


def get_trade_values(is_dynasty=False, num_qbs=1, num_teams=14, ppr=1):
    """Gibt {sleeper_player_id: {value, overallRank, positionRank, trend30Day}} zurück.

    Parameter werden aus den echten Liga-Settings abgeleitet (Liga-Typ,
    SUPER_FLEX, Teamanzahl, PPR-Wert) statt fest codiert zu sein.
    Bei Fehlern wird ein leeres Dict zurückgegeben statt Daten zu erfinden;
    der Aufrufer markiert Trade-Werte dann als nicht verfügbar.
    """
    url = (
        f"{_BASE_URL}?isDynasty={'true' if is_dynasty else 'false'}"
        f"&numQbs={num_qbs}&numTeams={num_teams}&ppr={ppr}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
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
