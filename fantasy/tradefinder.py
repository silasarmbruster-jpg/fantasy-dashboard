"""Trade Finder: durchsucht alle 1-zu-1 bis 3-zu-2-Kombinationen (beide
Richtungen: Konsolidierung und Aufteilung) zwischen meinem Team und jedem
der 13 anderen Teams, filtert nach Wert-Fairness und Positionsbedarf vor
und bewertet die überlebenden Kandidaten mit der echten Lineup-Auswirkung
(Start/Sit-Optimizer). Keine Vorab-Beschränkung auf "realistische" Trades -
das ist ein Frontend-Filter, Standard aus."""

import itertools

from .roster_strength import weakness_matrix
from .startsit import _best_lineup, _effective_projection, HARD_OUT_STATUSES

TRADE_POSITIONS = ("QB", "RB", "WR", "TE")
MY_KEY_PLAYER_COUNT = 5
POOL_CAP = 14  # je Team, nach Wert begrenzt, hält die Kombinatorik handhabbar
MAX_SIDE_SIZE = 3
VALUE_FAIRNESS_CAP = 0.25  # grobe Vorfilterung; echte Toleranz ist ein Frontend-Filter
NEED_FIT_SHORTLIST = 15  # pro Team: wie viele wertfaire Kandidaten die teure Lineup-Berechnung durchlaufen
MAX_PROPOSALS_PER_TEAM = 6
MAX_TOTAL_PROPOSALS = 150

# (give_size, get_size)-Paare laut Vorgabe - bewusst ohne 3-zu-3.
COMBO_SIZE_PAIRS = [
    (1, 1), (1, 2), (1, 3),
    (2, 1), (2, 2), (2, 3),
    (3, 1), (3, 2),
]


def _tradeable_pool(team, players, exclude_ids=None):
    exclude_ids = exclude_ids or set()
    reserve = set(team.get("reserve") or [])
    pool = [
        players[pid] for pid in team["players"]
        if pid in players and pid not in reserve and pid not in exclude_ids
        and players[pid].get("trade_value")
    ]
    pool.sort(key=lambda p: p["trade_value"], reverse=True)
    return pool[:POOL_CAP]


def _combos(pool):
    """{size: [tuple(player,...), ...]} für size 1..MAX_SIDE_SIZE."""
    out = {}
    for size in range(1, MAX_SIDE_SIZE + 1):
        out[size] = list(itertools.combinations(pool, size))
    return out


def _need_fit(combo, weakness_for_team):
    return round(sum(weakness_for_team.get(p["position"], 0) for p in combo), 2)


def _lineup_points(player_ids, players, roster_positions, current_week):
    pool = []
    for pid in player_ids:
        p = players.get(pid)
        if not p:
            continue
        if p.get("bye_week") == current_week or p.get("injury_status") in HARD_OUT_STATUSES:
            continue
        p = dict(p)
        p["_eff"] = _effective_projection(p)
        pool.append(p)
    lineup = _best_lineup(pool, roster_positions)
    return round(sum(p["_eff"] for p in lineup if p), 2)


def _age_stance(give_combo, get_combo):
    def avg_age(combo):
        ages = [p["age"] for p in combo if p.get("age")]
        return sum(ages) / len(ages) if ages else None

    give_age, get_age = avg_age(give_combo), avg_age(get_combo)
    if give_age is None or get_age is None:
        return "unklar"
    return "Langfristig" if get_age < give_age - 1 else "Win-Now" if get_age > give_age + 1 else "neutral"


def _acceptance_label(their_need_fit, diff_pct):
    if their_need_fit >= 3 and diff_pct <= 0.10:
        return "hoch"
    if their_need_fit <= 0.5 or diff_pct > 0.20:
        return "niedrig"
    return "mittel"


def _reasons(give_combo, get_combo, their_need_fit, my_need_fit, diff_pct):
    reasons = []
    get_names = ", ".join(p["name"] for p in get_combo)
    give_names = ", ".join(p["name"] for p in give_combo)
    if my_need_fit > 0:
        positions = sorted({p["position"] for p in get_combo})
        reasons.append(f"Verstärkt deinen Bedarf auf {', '.join(positions)}")
    if their_need_fit > 0:
        positions = sorted({p["position"] for p in give_combo})
        reasons.append(f"Trifft den Bedarf des anderen Teams auf {', '.join(positions)}")
    reasons.append(f"Wertdifferenz {round(diff_pct * 100, 1)}%")
    return reasons


def compute(data):
    players = data["players"]
    teams = data["teams"]
    my_roster_id = data["me"]["roster_id"]
    my_team = next(t for t in teams if t["roster_id"] == my_roster_id)
    roster_positions = data["league"]["roster_positions"]
    current_week = data["league"]["week"]

    weakness = weakness_matrix(teams, players)
    my_weakness = weakness.get(my_roster_id, {})

    my_players_by_value = sorted(
        (players[pid] for pid in my_team["players"] if pid in players and players[pid].get("trade_value")),
        key=lambda p: p["trade_value"], reverse=True,
    )
    key_player_ids = {p["id"] for p in my_players_by_value[:MY_KEY_PLAYER_COUNT]}

    my_pool = _tradeable_pool(my_team, players)
    my_combos = _combos(my_pool)

    my_current_ids = (
        [s["player_id"] for s in data["my_roster"]["slots"]] + data["my_roster"]["bench"]
    )
    my_baseline_points = _lineup_points(my_current_ids, players, roster_positions, current_week)
    remaining_weeks = min(len(data["planner"]["remaining_schedule"]), 12) or 1

    all_candidates = []  # (score_tuple, proposal_dict) vor der teuren Lineup-Berechnung

    for team in teams:
        if team["roster_id"] == my_roster_id:
            continue
        their_weakness = weakness.get(team["roster_id"], {})
        their_pool = _tradeable_pool(team, players)
        if not their_pool:
            continue
        their_combos = _combos(their_pool)

        team_candidates = []
        for give_size, get_size in COMBO_SIZE_PAIRS:
            for give_combo in my_combos.get(give_size, []):
                v1 = sum(p["trade_value"] for p in give_combo)
                for get_combo in their_combos.get(get_size, []):
                    v2 = sum(p["trade_value"] for p in get_combo)
                    diff_pct = abs(v1 - v2) / max(v1, v2)
                    if diff_pct > VALUE_FAIRNESS_CAP:
                        continue
                    my_need_fit = _need_fit(get_combo, my_weakness)
                    their_need_fit = _need_fit(give_combo, their_weakness)
                    priority = my_need_fit * 2 + their_need_fit + (v1 + v2) / 5000
                    team_candidates.append((priority, diff_pct, my_need_fit, their_need_fit, give_combo, get_combo, v1, v2))

        team_candidates.sort(key=lambda c: c[0], reverse=True)
        shortlist = team_candidates[:NEED_FIT_SHORTLIST]

        for priority, diff_pct, my_need_fit, their_need_fit, give_combo, get_combo, v1, v2 in shortlist:
            give_ids = {p["id"] for p in give_combo}
            hypothetical_ids = [pid for pid in my_current_ids if pid not in give_ids] + [p["id"] for p in get_combo]
            after_points = _lineup_points(hypothetical_ids, players, roster_positions, current_week)
            lineup_delta = round(after_points - my_baseline_points, 2)

            has_injured = any(p.get("injury_status") in HARD_OUT_STATUSES for p in give_combo + get_combo)
            includes_key_player = bool(give_ids & key_player_ids)

            all_candidates.append({
                "roster_id": team["roster_id"],
                "team_name": team["team_name"],
                "give_player_ids": [p["id"] for p in give_combo],
                "get_player_ids": [p["id"] for p in get_combo],
                "give_value": v1,
                "get_value": v2,
                "value_diff_pct": round(diff_pct * 100, 1),
                "lineup_points_before": my_baseline_points,
                "lineup_points_after": after_points,
                "lineup_delta": lineup_delta,
                "season_delta_estimate": round(
                    (sum(p["season_avg"] for p in get_combo) - sum(p["season_avg"] for p in give_combo)) * remaining_weeks,
                    1,
                ),
                "remaining_weeks_estimate": remaining_weeks,
                "acceptance": _acceptance_label(their_need_fit, diff_pct),
                "stance": _age_stance(give_combo, get_combo),
                "includes_key_player": includes_key_player,
                "has_injured_player": has_injured,
                "my_need_fit": my_need_fit,
                "their_need_fit": their_need_fit,
                "reasons": _reasons(give_combo, get_combo, their_need_fit, my_need_fit, diff_pct),
            })

    # Pro Team begrenzen (Vielfalt), dann global nach Lineup-Verbesserung sortieren.
    # Wichtig: getrennte Top-Listen mit und ohne Schlüsselspieler, sonst dominieren
    # wertvolle Konsolidierungs-Trades (die immer meinen besten Spieler enthalten)
    # die Auswahl komplett und der "Schlüsselspieler ausschließen"-Filter liefe leer.
    by_team = {}
    for c in all_candidates:
        by_team.setdefault(c["roster_id"], []).append(c)
    final = []
    for rid, cands in by_team.items():
        cands.sort(key=lambda c: c["lineup_delta"], reverse=True)
        top_overall = cands[:MAX_PROPOSALS_PER_TEAM]
        top_non_key = [c for c in cands if not c["includes_key_player"]][:MAX_PROPOSALS_PER_TEAM]
        seen = set()
        for c in top_overall + top_non_key:
            key = (tuple(sorted(c["give_player_ids"])), tuple(sorted(c["get_player_ids"])))
            if key in seen:
                continue
            seen.add(key)
            final.append(c)
    final.sort(key=lambda c: c["lineup_delta"], reverse=True)
    final = final[:MAX_TOTAL_PROPOSALS]

    team_summaries = []
    team_pools = {}
    for team in teams:
        tw = weakness.get(team["roster_id"], {})
        needs = sorted([p for p in TRADE_POSITIONS if tw.get(p, 0) >= 1.5], key=lambda p: tw.get(p, 0), reverse=True)
        team_pools[str(team["roster_id"])] = [
            {"player_id": p["id"], "trade_value": p["trade_value"], "position": p["position"]}
            for p in _tradeable_pool(team, players)
        ]
        if team["roster_id"] == my_roster_id:
            continue
        team_summaries.append({"roster_id": team["roster_id"], "team_name": team["team_name"], "needs": needs})

    return {
        "my_needs": sorted([p for p in TRADE_POSITIONS if my_weakness.get(p, 0) >= 1.5], key=lambda p: my_weakness.get(p, 0), reverse=True),
        "key_player_ids": sorted(key_player_ids),
        "team_summaries": team_summaries,
        "proposals": final,
        "lineup_points_baseline": my_baseline_points,
        "weakness_matrix": {str(rid): w for rid, w in weakness.items()},
        "team_pools": team_pools,
        "remaining_weeks_estimate": remaining_weeks,
    }
