"""Planer: Bye-Week-Kalender, Restprogramm (Fantasy-Gegner je Woche) und eine
grobe Matchup-Vorhersage für die nächsten Wochen, bezogen auf den eigenen
Kader."""

from .startsit import _best_lineup, HARD_OUT_STATUSES
from .util import win_probability

FORECAST_WEEKS = 4
NEAR_PLAYOFFS_WINDOW = 2  # Wochen vor Playoff-Start, die als "knapp davor" gelten


def _my_future_opponents(my_roster_id, roster_by_id, future_matchups_by_week):
    opponents = []
    for wk in sorted(future_matchups_by_week.keys()):
        entries = future_matchups_by_week[wk]
        my_entry = next((m for m in entries if m["roster_id"] == my_roster_id), None)
        if my_entry is None:
            continue
        opp_entry = next(
            (m for m in entries if m["matchup_id"] == my_entry["matchup_id"] and m["roster_id"] != my_roster_id),
            None,
        )
        opp_team = roster_by_id.get(opp_entry["roster_id"]) if opp_entry else None
        opponents.append({
            "week": wk,
            "opponent_team_name": opp_team["team_name"] if opp_team else None,
            "opponent_roster_id": opp_team["roster_id"] if opp_team else None,
        })
    return opponents


def _bye_calendar(my_player_ids, players, season_weeks=18):
    calendar = {wk: [] for wk in range(1, season_weeks + 1)}
    for pid in my_player_ids:
        p = players.get(pid)
        if not p or not p.get("bye_week"):
            continue
        calendar[p["bye_week"]].append(pid)
    return {str(wk): ids for wk, ids in calendar.items() if ids}


def _byes_near_playoffs(bye_calendar, playoff_week_start):
    if not playoff_week_start:
        return []
    window_start = playoff_week_start - NEAR_PLAYOFFS_WINDOW
    out = []
    for wk_str, ids in bye_calendar.items():
        wk = int(wk_str)
        if window_start <= wk < playoff_week_start and ids:
            out.append(wk)
    return sorted(out)


def _lineup_points_for_week(player_ids, players, roster_positions, week):
    """Grobe Projektion für eine künftige Woche auf Basis des Saison-
    Durchschnitts (keine wochenspezifischen Projections für die Zukunft
    verfügbar) und des AKTUELLEN Kaders (künftige Waiver/Trade-Aktivität
    wird nicht berücksichtigt)."""
    pool = []
    for pid in player_ids:
        p = players.get(pid)
        if not p:
            continue
        if p.get("bye_week") == week or p.get("injury_status") in HARD_OUT_STATUSES:
            continue
        p = dict(p)
        p["_eff"] = p.get("season_avg") or 0.0
        pool.append(p)
    lineup = _best_lineup(pool, roster_positions)
    return round(sum(p["_eff"] for p in lineup if p), 2)


def _matchup_forecast(my_roster_id, roster_by_id, players, roster_positions, remaining_schedule):
    forecast = []
    my_team = roster_by_id.get(my_roster_id)
    if not my_team:
        return forecast
    for opp in remaining_schedule[:FORECAST_WEEKS]:
        wk = opp["week"]
        opp_team = roster_by_id.get(opp["opponent_roster_id"]) if opp["opponent_roster_id"] else None
        my_pts = _lineup_points_for_week(my_team["players"], players, roster_positions, wk)
        opp_pts = _lineup_points_for_week(opp_team["players"], players, roster_positions, wk) if opp_team else None
        forecast.append({
            "week": wk,
            "opponent_team_name": opp["opponent_team_name"],
            "my_projected_points": my_pts,
            "opponent_projected_points": opp_pts,
            "win_probability_me": win_probability(my_pts - opp_pts) if opp_pts is not None else None,
        })
    return forecast


def compute(data, future_matchups_by_week):
    players = data["players"]
    my_roster_id = data["me"]["roster_id"]
    roster_by_id = {t["roster_id"]: t for t in data["teams"]}
    roster_positions = data["league"]["roster_positions"]

    my_player_ids = (
        [s["player_id"] for s in data["my_roster"]["slots"]]
        + data["my_roster"]["bench"]
        + data["my_roster"]["reserve"]
    )

    bye_calendar = _bye_calendar(my_player_ids, players)
    remaining_schedule = _my_future_opponents(my_roster_id, roster_by_id, future_matchups_by_week)

    return {
        "bye_calendar": bye_calendar,
        "byes_near_playoffs": _byes_near_playoffs(bye_calendar, data["league"].get("playoff_week_start")),
        "remaining_schedule": remaining_schedule,
        "matchup_forecast": _matchup_forecast(my_roster_id, roster_by_id, players, roster_positions, remaining_schedule),
        "forecast_note": (
            "Vorhersage basiert auf Saison-Durchschnittspunkten des aktuellen "
            "Kaders, nicht auf wochenspezifischen Projections (die gibt es bei "
            "Sleeper nur für die laufende Woche) - künftige Waiver-/Trade-"
            "Aktivität und Formschwankungen sind nicht berücksichtigt."
        ),
    }
