"""Dünner Client für die öffentliche Sleeper-API (keine Authentifizierung nötig)."""

import time
import urllib.error
import urllib.request
import json

_BASE_V1 = "https://api.sleeper.app/v1"
_BASE_ROOT = "https://api.sleeper.app"

USER_AGENT = "fantasy-dashboard-build/1.0 (+https://github.com)"


class SleeperError(RuntimeError):
    pass


def _get(url, retries=3, timeout=30):
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                return json.loads(data)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last_err = exc
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise SleeperError(f"Sleeper-API nicht erreichbar: {url} ({last_err})")


def get_user(username):
    return _get(f"{_BASE_V1}/user/{username}")


def get_user_leagues(user_id, season, sport="nfl"):
    return _get(f"{_BASE_V1}/user/{user_id}/leagues/{sport}/{season}")


def get_league(league_id):
    return _get(f"{_BASE_V1}/league/{league_id}")


def get_rosters(league_id):
    return _get(f"{_BASE_V1}/league/{league_id}/rosters")


def get_league_users(league_id):
    return _get(f"{_BASE_V1}/league/{league_id}/users")


def get_matchups(league_id, week):
    return _get(f"{_BASE_V1}/league/{league_id}/matchups/{week}")


def get_transactions(league_id, round_):
    return _get(f"{_BASE_V1}/league/{league_id}/transactions/{round_}")


def get_state(sport="nfl"):
    return _get(f"{_BASE_V1}/state/{sport}")


def get_all_players(sport="nfl"):
    """~15MB; nur einmal pro Build-Lauf aufrufen."""
    return _get(f"{_BASE_V1}/players/{sport}")


def get_trending(kind="add", sport="nfl", lookback_hours=24, limit=50):
    assert kind in ("add", "drop")
    return _get(
        f"{_BASE_V1}/players/{sport}/trending/{kind}"
        f"?lookback_hours={lookback_hours}&limit={limit}"
    )


def get_schedule(season, season_type="regular", sport="nfl"):
    return _get(f"{_BASE_ROOT}/schedule/{sport}/{season_type}/{season}")


def get_weekly_stats(season, week, season_type="regular", sport="nfl"):
    """Leichtgewichtige, nach player_id geschlüsselte Rohstatistik einer Woche."""
    return _get(f"{_BASE_V1}/stats/{sport}/{season_type}/{season}/{week}")


def get_weekly_projections(season, week, season_type="regular", sport="nfl"):
    """Leichtgewichtige, nach player_id geschlüsselte Projektionen einer Woche."""
    return _get(f"{_BASE_V1}/projections/{sport}/{season_type}/{season}/{week}")
