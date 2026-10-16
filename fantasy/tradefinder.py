"""Trade Finder: ermittelt für jedes andere Team Überschuss/Bedarf je
Position und leitet daraus faire 1-für-1-Tauschvorschläge (max. 10 %
Wertdifferenz nach FantasyCalc) ab, die beide Teams an ihrer Schwachstelle
verstärken. Eigene Schlüsselspieler werden nie angeboten."""

from .roster_strength import weakness_matrix

MAX_VALUE_DIFF_PCT = 0.10
MY_KEY_PLAYER_COUNT = 5
NEED_THRESHOLD = 1.5  # Mindest-Schwäche, damit eine Position als "Bedarf" zählt
TRADE_POSITIONS = ("QB", "RB", "WR", "TE")


def _bench_surplus(team, players, position):
    """Tatsächliche Bankspieler (nicht Starter, nicht verletzte Reserve/IR)
    dieser Position, nach Trade-Wert sortiert - das ist der handelbare
    Überschuss."""
    excluded_ids = set(team.get("starters") or []) | set(team.get("reserve") or [])
    bench = [
        players[pid] for pid in team["players"]
        if pid in players and players[pid]["position"] == position
        and pid not in excluded_ids and players[pid].get("trade_value")
    ]
    bench.sort(key=lambda p: p["trade_value"], reverse=True)
    return bench


def _top_needs(weakness_for_team):
    return sorted(
        [pos for pos in TRADE_POSITIONS if weakness_for_team.get(pos, 0) >= NEED_THRESHOLD],
        key=lambda pos: weakness_for_team.get(pos, 0),
        reverse=True,
    )


def compute(data):
    players = data["players"]
    teams = data["teams"]
    my_roster_id = data["me"]["roster_id"]
    my_team = next(t for t in teams if t["roster_id"] == my_roster_id)

    weakness = weakness_matrix(teams, players)
    my_needs = _top_needs(weakness.get(my_roster_id, {}))

    my_players_by_value = sorted(
        (players[pid] for pid in my_team["players"] if pid in players and players[pid].get("trade_value")),
        key=lambda p: p["trade_value"],
        reverse=True,
    )
    key_player_ids = {p["id"] for p in my_players_by_value[:MY_KEY_PLAYER_COUNT]}

    my_surplus_by_pos = {pos: _bench_surplus(my_team, players, pos) for pos in TRADE_POSITIONS}
    my_offer_pool = [
        p for pos in TRADE_POSITIONS for p in my_surplus_by_pos[pos]
        if p["id"] not in key_player_ids
    ]

    team_entries = []
    for team in teams:
        if team["roster_id"] == my_roster_id:
            continue
        their_needs = _top_needs(weakness.get(team["roster_id"], {}))
        their_surplus_by_pos = {pos: _bench_surplus(team, players, pos) for pos in TRADE_POSITIONS}
        their_surplus_positions = [pos for pos in TRADE_POSITIONS if their_surplus_by_pos[pos]]

        # Ich biete aus meinem Überschuss an Positionen, die DIE anderen brauchen.
        my_offers_for_them = [p for p in my_offer_pool if p["position"] in their_needs]
        # Sie bieten aus ihrem Überschuss an Positionen, die ICH brauche.
        their_offers_for_me = [
            p for pos in my_needs for p in their_surplus_by_pos.get(pos, [])
        ]

        best = None
        best_combined = -1
        for give in my_offers_for_them:
            for get in their_offers_for_me:
                v1, v2 = give["trade_value"], get["trade_value"]
                if not v1 or not v2:
                    continue
                diff_pct = abs(v1 - v2) / max(v1, v2)
                if diff_pct > MAX_VALUE_DIFF_PCT:
                    continue
                combined = v1 + v2
                if combined > best_combined:
                    best_combined = combined
                    best = (give, get)

        proposal = None
        if best:
            give, get = best
            proposal = {
                "give_player_id": give["id"],
                "get_player_id": get["id"],
                "give_value": give["trade_value"],
                "get_value": get["trade_value"],
            }

        team_entries.append({
            "roster_id": team["roster_id"],
            "team_name": team["team_name"],
            "needs": their_needs,
            "surplus": their_surplus_positions,
            "proposal": proposal,
        })

    return {
        "my_needs": my_needs,
        "key_player_ids": sorted(key_player_ids),
        "teams": team_entries,
    }
