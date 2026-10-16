"""Baut aus den rohen Sleeper-/FantasyCalc-Antworten das normalisierte
data.json-Modell, das das Frontend konsumiert."""

import math
from datetime import datetime, timezone

from . import config, waiver
from .scoring import score as score_stats

TEAM_LOGO = "https://sleepercdn.com/images/team_logos/nfl/{team}.png"
PLAYER_PHOTO = "https://sleepercdn.com/content/nfl/players/thumb/{pid}.jpg"
AVATAR = "https://sleepercdn.com/avatars/thumbs/{avatar}"


def _team_name_for(user):
    meta = user.get("metadata") or {}
    name = meta.get("team_name")
    if name and name.strip():
        return name.strip()
    return user.get("display_name") or "Unbekanntes Team"


def _win_probability(diff, sigma=18.0):
    """Heuristische Siegwahrscheinlichkeit aus der Projection-Differenz
    (Normalverteilung um 0 mit sigma als angenommene wöchentliche Streuung).
    Kein echtes Vorhersagemodell, nur eine grobe Orientierung."""
    z = diff / (sigma * math.sqrt(2))
    prob = 0.5 * (1 + math.erf(z))
    return round(max(0.01, min(0.99, prob)) * 100, 1)


def _compute_byes(schedule, season_weeks=18):
    """team_abbr -> bye week, abgeleitet daraus, in welcher Woche ein Team
    in keinem Spiel vorkommt."""
    teams_seen_per_week = {w: set() for w in range(1, season_weeks + 1)}
    all_teams = set()
    for game in schedule:
        wk = game.get("week")
        if wk is None or wk < 1 or wk > season_weeks:
            continue
        home, away = game.get("home"), game.get("away")
        if home:
            teams_seen_per_week[wk].add(home)
            all_teams.add(home)
        if away:
            teams_seen_per_week[wk].add(away)
            all_teams.add(away)

    bye_weeks = {}
    for wk in range(1, season_weeks + 1):
        missing = all_teams - teams_seen_per_week[wk]
        for team in missing:
            bye_weeks.setdefault(team, wk)
    return bye_weeks


def _remaining_schedule(schedule, current_week, season_weeks=18):
    """team_abbr -> [{week, opponent, home}] für alle Wochen >= current_week."""
    rest = {}
    for game in schedule:
        wk = game.get("week")
        if wk is None or wk < current_week or wk > season_weeks:
            continue
        home, away = game.get("home"), game.get("away")
        if home:
            rest.setdefault(home, []).append({"week": wk, "opponent": away, "home": True})
        if away:
            rest.setdefault(away, []).append({"week": wk, "opponent": home, "home": False})
    for team in rest:
        rest[team].sort(key=lambda g: g["week"])
    return rest


def _player_record(pid, pinfo, scoring_settings, weekly_stats_by_week, weekly_proj,
                    current_week, bye_weeks, trade_values, trending_add, trending_drop,
                    rest_of_season):
    fantasy_positions = pinfo.get("fantasy_positions") or []
    primary_position = pinfo.get("position")
    # Spieler mit Doppel-Listung (z.B. WR/DB) sollen mit ihrer fantasy-relevanten
    # Position geführt werden, nicht mit ihrer primären NFL-Positionsbezeichnung.
    position = next(
        (fp for fp in fantasy_positions if fp in config.RELEVANT_POSITIONS),
        primary_position if primary_position in config.RELEVANT_POSITIONS else (fantasy_positions[0] if fantasy_positions else primary_position),
    )
    team = pinfo.get("team")
    is_def = position == "DEF"

    weekly_points = {}
    played_weeks = []
    targets_total = touches_total = redzone_total = air_yards_total = 0.0
    snap_pct_samples = []
    for wk in sorted(weekly_stats_by_week.keys()):
        if wk > current_week:
            continue
        raw = weekly_stats_by_week[wk].get(pid)
        pts = score_stats(raw, scoring_settings) if raw else 0.0
        weekly_points[str(wk)] = pts
        if raw:
            played_weeks.append(wk)
            targets_total += raw.get("rec_tgt") or 0
            touches_total += (raw.get("rush_att") or 0) + (raw.get("rec") or 0)
            redzone_total += (raw.get("rec_rz_tgt") or 0) + (raw.get("rush_rz_att") or 0)
            air_yards_total += raw.get("rec_air_yd") or 0
            tm_snp = raw.get("tm_off_snp")
            off_snp = raw.get("off_snp")
            if tm_snp:
                snap_pct_samples.append((off_snp or 0) / tm_snp)

    season_total = round(sum(weekly_points.values()), 2)
    played_count = len(played_weeks)
    season_avg = round(season_total / played_count, 2) if played_count else 0.0
    snap_pct = round(sum(snap_pct_samples) / len(snap_pct_samples) * 100, 1) if snap_pct_samples else None

    last3 = sorted(played_weeks)[-3:]
    avg_last3 = (
        round(sum(weekly_points[str(w)] for w in last3) / len(last3), 2) if last3 else 0.0
    )

    proj_raw = weekly_proj.get(pid)
    projection_week = score_stats(proj_raw, scoring_settings) if proj_raw else 0.0

    tv = trade_values.get(pid) or {}

    if is_def:
        name = pinfo.get("first_name", "") + " " + pinfo.get("last_name", "")
        name = name.strip() or (team or pid)
        photo = TEAM_LOGO.format(team=team.lower()) if team else None
    else:
        name = pinfo.get("full_name") or f"{pinfo.get('first_name','')} {pinfo.get('last_name','')}".strip()
        photo = PLAYER_PHOTO.format(pid=pid)

    return {
        "id": pid,
        "name": name or pid,
        "position": position,
        "team": team,
        "age": pinfo.get("age"),
        "years_exp": pinfo.get("years_exp"),
        "status": pinfo.get("status"),
        "injury_status": pinfo.get("injury_status"),
        "injury_body_part": pinfo.get("injury_body_part"),
        "injury_notes": pinfo.get("injury_notes"),
        "bye_week": bye_weeks.get(team) if team else None,
        "photo": photo,
        "weekly_points": weekly_points,
        "season_total": season_total,
        "season_avg": season_avg,
        "avg_last3": avg_last3,
        "games_played": played_count,
        "targets": round(targets_total) if targets_total else 0,
        "targets_pg": round(targets_total / played_count, 1) if played_count else 0.0,
        "touches": round(touches_total) if touches_total else 0,
        "touches_pg": round(touches_total / played_count, 1) if played_count else 0.0,
        "snap_pct": snap_pct,
        "redzone_touches": round(redzone_total) if redzone_total else 0,
        "redzone_pg": round(redzone_total / played_count, 1) if played_count else 0.0,
        "air_yards": round(air_yards_total) if air_yards_total else 0,
        "air_yards_pg": round(air_yards_total / played_count, 1) if played_count else 0.0,
        "projection_week": round(projection_week, 2),
        "trade_value": tv.get("value"),
        "trade_rank": tv.get("overallRank"),
        "trade_pos_rank": tv.get("positionRank"),
        "trade_trend_30d": tv.get("trend30Day"),
        "trending_add": trending_add.get(pid),
        "trending_drop": trending_drop.get(pid),
        "rest_of_season": rest_of_season.get(team, []) if team else [],
        "fantasy_team": None,  # wird nach dem Aufbau der Teams gefüllt
    }


def build(*, state, league, rosters, users, matchups, players_db, schedule,
          weekly_stats_by_week, weekly_proj, trade_values, trending_add_list,
          trending_drop_list, relevant_player_ids, my_username):
    season = state["season"]
    current_week = state.get("display_week") or state.get("week") or 1
    scoring_settings = league.get("scoring_settings", {})

    bye_weeks = _compute_byes(schedule)
    rest_of_season = _remaining_schedule(schedule, current_week)

    trending_add = {e["player_id"]: e["count"] for e in trending_add_list}
    trending_drop = {e["player_id"]: e["count"] for e in trending_drop_list}

    users_by_id = {u["user_id"]: u for u in users}

    # --- Spieler-Datensätze ---
    players = {}
    for pid in relevant_player_ids:
        pinfo = players_db.get(pid)
        if not pinfo:
            continue
        players[pid] = _player_record(
            pid, pinfo, scoring_settings, weekly_stats_by_week, weekly_proj,
            current_week, bye_weeks, trade_values, trending_add, trending_drop,
            rest_of_season,
        )

    # --- Teams / Standings ---
    teams = []
    roster_by_id = {}
    for roster in rosters:
        owner = users_by_id.get(roster.get("owner_id"), {})
        settings = roster.get("settings", {})
        meta = roster.get("metadata") or {}
        roster_players = roster.get("players") or []

        roster_value = 0
        has_any_value = False
        for pid in roster_players:
            tv = trade_values.get(pid)
            if tv and tv.get("value") is not None:
                roster_value += tv["value"]
                has_any_value = True

        team = {
            "roster_id": roster["roster_id"],
            "owner_id": roster.get("owner_id"),
            "user_id": roster.get("owner_id"),
            "display_name": owner.get("display_name"),
            "team_name": _team_name_for(owner) if owner else f"Team {roster['roster_id']}",
            "avatar_url": AVATAR.format(avatar=owner["avatar"]) if owner.get("avatar") else None,
            "wins": settings.get("wins", 0),
            "losses": settings.get("losses", 0),
            "ties": settings.get("ties", 0),
            "fpts": round(settings.get("fpts", 0) + settings.get("fpts_decimal", 0) / 100, 2),
            "fpts_against": round(
                settings.get("fpts_against", 0) + settings.get("fpts_against_decimal", 0) / 100, 2
            ),
            "streak": meta.get("record"),
            "roster_value": roster_value if has_any_value else None,
            "players": roster_players,
            "starters": roster.get("starters") or [],
            "reserve": roster.get("reserve") or [],
        }
        teams.append(team)
        roster_by_id[team["roster_id"]] = team

    # Rang nach Siegen, dann Punkten
    ranked = sorted(teams, key=lambda t: (-t["wins"], -t["fpts"]))
    for i, t in enumerate(ranked, start=1):
        t["rank"] = i

    # Spieler ihrem Fantasy-Team zuordnen
    for team in teams:
        for pid in team["players"]:
            if pid in players:
                players[pid]["fantasy_team"] = {
                    "roster_id": team["roster_id"],
                    "team_name": team["team_name"],
                }

    # --- Ich ---
    me_user = next(
        (u for u in users if (u.get("display_name") or "").lower() == my_username.lower()),
        None,
    )
    me_roster = None
    if me_user:
        me_roster = next((t for t in teams if t["owner_id"] == me_user["user_id"]), None)
    if me_roster is None:
        raise RuntimeError(f"Konnte Roster von '{my_username}' in Liga nicht finden.")

    roster_positions = [p for p in league.get("roster_positions", []) if p not in ("BN", "IR", "TAXI")]

    my_roster_obj = next(r for r in rosters if r["roster_id"] == me_roster["roster_id"])
    starters = my_roster_obj.get("starters") or []
    all_players_mine = my_roster_obj.get("players") or []
    bench = [p for p in all_players_mine if p not in starters and p not in (my_roster_obj.get("reserve") or [])]
    reserve = my_roster_obj.get("reserve") or []

    slots = []
    for slot_label, pid in zip(roster_positions, starters):
        slots.append({"slot": slot_label, "player_id": pid})

    # --- Matchup dieser Woche ---
    matchup_block = None
    my_entry = next((m for m in matchups if m["roster_id"] == me_roster["roster_id"]), None)
    if my_entry is not None:
        opp_entry = next(
            (m for m in matchups if m["matchup_id"] == my_entry["matchup_id"] and m["roster_id"] != me_roster["roster_id"]),
            None,
        )

        def _side(entry):
            if entry is None:
                return None
            team = roster_by_id.get(entry["roster_id"])
            side_starters = []
            ent_starters = entry.get("starters") or []
            points_map = entry.get("players_points") or {}
            for slot_label, pid in zip(roster_positions, ent_starters):
                side_starters.append({
                    "slot": slot_label,
                    "player_id": pid,
                    "actual_points": points_map.get(pid, 0.0),
                })
            proj_total = sum(players[p]["projection_week"] for p in ent_starters if p in players)
            return {
                "roster_id": entry["roster_id"],
                "team_name": team["team_name"] if team else None,
                "points": entry.get("points", 0.0),
                "projected_points": round(proj_total, 2),
                "starters": side_starters,
            }

        me_side = _side(my_entry)
        opp_side = _side(opp_entry) if opp_entry else None

        win_prob = None
        if opp_side is not None:
            diff = me_side["projected_points"] - opp_side["projected_points"]
            win_prob = _win_probability(diff)

        matchup_block = {
            "week": current_week,
            "me": me_side,
            "opponent": opp_side,
            "win_probability_me": win_prob,
        }

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "league": {
            "league_id": league["league_id"],
            "name": league["name"],
            "season": season,
            "week": current_week,
            "total_rosters": league["settings"]["num_teams"],
            "playoff_week_start": league["settings"].get("playoff_week_start"),
            "trade_deadline": league["settings"].get("trade_deadline"),
            "roster_positions": roster_positions,
        },
        "me": {
            **me_roster,
            "rank": me_roster["rank"],
        },
        "teams": sorted(teams, key=lambda t: t["rank"]),
        "matchup": matchup_block,
        "my_roster": {
            "slots": slots,
            "bench": bench,
            "reserve": reserve,
        },
        "players": players,
    }
    data["waiver"] = waiver.compute(data)
    return data
