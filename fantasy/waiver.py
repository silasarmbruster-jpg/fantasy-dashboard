"""Berechnet Waiver-Wire-Empfehlungen: beste verfügbare Spieler je Position,
gewichtet nach Roster-Schwächen, mit Begründung und Drop-Kandidat."""

FLEX_ELIGIBLE = {"RB", "WR", "TE"}
STARTER_SLOTS_BY_POS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1}

MAX_SUGGESTIONS_PER_POSITION = 8


def _effective_strength(player_ids, position, players):
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


def _position_weakness(teams, players, my_roster_id):
    """position -> Schwäche (>0 heißt: unterdurchschnittlich, Waiver-Bedarf)."""
    strengths_by_pos = {pos: {} for pos in STARTER_SLOTS_BY_POS}
    for team in teams:
        for pos in STARTER_SLOTS_BY_POS:
            strengths_by_pos[pos][team["roster_id"]] = _effective_strength(team["players"], pos, players)

    weakness = {}
    for pos, by_team in strengths_by_pos.items():
        league_avg = sum(by_team.values()) / len(by_team) if by_team else 0.0
        mine = by_team.get(my_roster_id, 0.0)
        weakness[pos] = round(max(0.0, league_avg - mine), 2)
    return weakness


def _reasons(p, weakness_for_pos, pos_avg_season):
    reasons = []
    if p.get("trending_add") and p["trending_add"] > 20000:
        count_de = f"{p['trending_add']:,}".replace(",", ".")
        reasons.append(f"Stark steigende Waiver-Aktivität (+{count_de} Adds, 24h)")
    if p["season_avg"] and pos_avg_season and p["season_avg"] > pos_avg_season:
        reasons.append(f"Über Positions-Durchschnitt ({p['season_avg']} Pkt./Spiel)")
    if p["position"] in FLEX_ELIGIBLE and p.get("targets_pg", 0) and p["targets_pg"] >= 5:
        reasons.append(f"{p['targets_pg']} Targets/Spiel")
    if p.get("redzone_pg", 0) and p["redzone_pg"] >= 1:
        reasons.append(f"{p['redzone_pg']} Red-Zone-Chancen/Spiel")
    if p.get("snap_pct") and p["snap_pct"] >= 65:
        reasons.append(f"{p['snap_pct']}% Snap-Anteil")
    if weakness_for_pos > 2:
        reasons.append(f"Verstärkt deine Schwachstelle auf {p['position']}")
    if p.get("injury_status") is None and p.get("projection_week", 0) > 0:
        reasons.append(f"Projektion diese Woche: {p['projection_week']} Pkt.")
    if not reasons:
        reasons.append("Solide Tiefe für die Bank")
    return reasons[:3]


def _drop_candidate(position, bench_ids, players):
    compatible = FLEX_ELIGIBLE if position in FLEX_ELIGIBLE else {position}
    candidates = [
        players[pid] for pid in bench_ids
        if pid in players and players[pid]["position"] in compatible
    ]
    if not candidates:
        return None
    worst = min(candidates, key=lambda p: p["season_avg"])
    return worst["id"]


def compute(data):
    players = data["players"]
    teams = data["teams"]
    my_roster_id = data["me"]["roster_id"]
    bench_ids = data["my_roster"]["bench"]

    weakness = _position_weakness(teams, players, my_roster_id)

    pos_avgs = {}
    for pos in STARTER_SLOTS_BY_POS:
        vals = [p["season_avg"] for p in players.values() if p["position"] == pos and p["games_played"] > 0]
        pos_avgs[pos] = sum(vals) / len(vals) if vals else 0.0

    free_agents = [p for p in players.values() if p["fantasy_team"] is None]

    def _score(p, pos):
        s = (p["season_avg"] or 0) * 1.0
        s += (p.get("projection_week") or 0) * 0.5
        s += ((p.get("trending_add") or 0) / 50000) * 2.0
        s += weakness.get(pos, 0) * 1.5
        return s

    suggestions_by_pos = {}
    scored_entries = []
    for pos in STARTER_SLOTS_BY_POS:
        pos_players = [p for p in free_agents if p["position"] == pos]
        pos_players.sort(key=lambda p: _score(p, pos), reverse=True)
        top = pos_players[:MAX_SUGGESTIONS_PER_POSITION]
        entries = []
        for p in top:
            entry = {
                "player_id": p["id"],
                "reasons": _reasons(p, weakness.get(pos, 0), pos_avgs.get(pos, 0)),
                "drop_candidate_id": _drop_candidate(pos, bench_ids, players),
            }
            entries.append(entry)
            scored_entries.append((_score(p, pos), entry))
        suggestions_by_pos[pos] = entries

    # Übergreifendes Top-N (für Übersicht-Karte), unabhängig von Position gemischt
    scored_entries.sort(key=lambda t: t[0], reverse=True)
    top_overall = [entry for _, entry in scored_entries[:10]]

    return {
        "position_weakness": weakness,
        "by_position": suggestions_by_pos,
        "top_overall": top_overall,
    }
