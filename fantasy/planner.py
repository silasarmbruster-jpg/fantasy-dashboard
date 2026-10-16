"""Planer: Bye-Week-Kalender und Restprogramm (Fantasy-Gegner je Woche)
für den Rest der Saison, bezogen auf den eigenen Kader."""


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


def compute(data, future_matchups_by_week):
    players = data["players"]
    my_roster_id = data["me"]["roster_id"]
    roster_by_id = {t["roster_id"]: t for t in data["teams"]}

    my_player_ids = (
        [s["player_id"] for s in data["my_roster"]["slots"]]
        + data["my_roster"]["bench"]
        + data["my_roster"]["reserve"]
    )

    return {
        "bye_calendar": _bye_calendar(my_player_ids, players),
        "remaining_schedule": _my_future_opponents(my_roster_id, roster_by_id, future_matchups_by_week),
    }
