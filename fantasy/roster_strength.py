"""Geteilte Hilfsfunktionen, um die Stärke eines Teams je Position relativ
zur Liga einzuschätzen. Wird von waiver.py und tradefinder.py genutzt."""

FLEX_ELIGIBLE = {"RB", "WR", "TE"}
STARTER_SLOTS_BY_POS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1}


def effective_strength(player_ids, position, players):
    """Durchschnitt der N stärksten Spieler eines Teams an einer Position,
    wobei N die Anzahl der Start-Slots ist (Flex-Slots zählen anteilig für
    RB/WR/TE mit hinein, vereinfacht über eine zusätzliche "Pseudo-Slot")."""
    n_slots = STARTER_SLOTS_BY_POS.get(position, 1)
    if position in FLEX_ELIGIBLE:
        n_slots += 1  # zwei Flex-Slots auf drei Flex-fähige Positionen verteilt -> grobe Pauschale
    pool = sorted(
        (players[pid]["season_avg"] for pid in player_ids if pid in players and players[pid]["position"] == position),
        reverse=True,
    )
    top = pool[:n_slots]
    return sum(top) / len(top) if top else 0.0


def team_strengths(teams, players):
    """pos -> {roster_id: effective_strength}, für alle Teams der Liga."""
    strengths_by_pos = {pos: {} for pos in STARTER_SLOTS_BY_POS}
    for team in teams:
        for pos in STARTER_SLOTS_BY_POS:
            strengths_by_pos[pos][team["roster_id"]] = effective_strength(team["players"], pos, players)
    return strengths_by_pos


def position_rank_matrix(teams, players):
    """pos -> Liste von {roster_id, team_name, value, rank}, nach Stärke
    sortiert (Rang 1 = stärkstes Team der Liga an dieser Position)."""
    strengths_by_pos = team_strengths(teams, players)
    team_names = {t["roster_id"]: t["team_name"] for t in teams}
    out = {}
    for pos, by_team in strengths_by_pos.items():
        ranked = sorted(by_team.items(), key=lambda kv: kv[1], reverse=True)
        out[pos] = [
            {"roster_id": rid, "team_name": team_names.get(rid, f"Team {rid}"), "value": round(val, 2), "rank": i + 1}
            for i, (rid, val) in enumerate(ranked)
        ]
    return out


def weakness_matrix(teams, players):
    """roster_id -> {pos: Schwäche (>0 = unterdurchschnittlich)}."""
    strengths_by_pos = team_strengths(teams, players)
    matrix = {team["roster_id"]: {} for team in teams}
    for pos, by_team in strengths_by_pos.items():
        league_avg = sum(by_team.values()) / len(by_team) if by_team else 0.0
        for roster_id, value in by_team.items():
            matrix[roster_id][pos] = round(max(0.0, league_avg - value), 2)
    return matrix
