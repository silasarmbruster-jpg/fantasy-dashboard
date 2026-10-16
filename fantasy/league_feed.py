"""Aufbereitung für den Liga-Tab: Power-Ranking nach Roster-Wert, eine
lesbare Transaktions-Historie und Scouting-Profile je Manager (Waiver-/
Trade-Aktivität, Positionsbedarf und -überschuss)."""

MAX_TRANSACTIONS = 25
SCOUTING_POSITIONS = ("QB", "RB", "WR", "TE")
SURPLUS_RANK_THRESHOLD = 3  # Top-3-Rang der Liga an einer Position gilt als Überschuss


def power_ranking(teams):
    ranked = sorted(teams, key=lambda t: (t.get("roster_value") or 0), reverse=True)
    return [
        {
            "roster_id": t["roster_id"],
            "team_name": t["team_name"],
            "roster_value": t.get("roster_value"),
            "power_rank": i + 1,
        }
        for i, t in enumerate(ranked)
    ]


def normalize_transactions(transactions, roster_by_id):
    out = []
    for tx in transactions:
        if tx.get("status") != "complete":
            continue
        tx_type = tx.get("type")
        roster_ids = tx.get("roster_ids") or []
        adds = tx.get("adds") or {}
        drops = tx.get("drops") or {}
        created = tx.get("created")

        if tx_type == "trade" and len(roster_ids) > 1:
            sides = {}
            for pid, rid in adds.items():
                sides.setdefault(rid, {"gets": [], "sends": []})["gets"].append(pid)
            for pid, rid in drops.items():
                sides.setdefault(rid, {"gets": [], "sends": []})["sends"].append(pid)
            participants = []
            for rid in roster_ids:
                team = roster_by_id.get(rid)
                side = sides.get(rid, {"gets": [], "sends": []})
                participants.append({
                    "roster_id": rid,
                    "team_name": team["team_name"] if team else f"Team {rid}",
                    "gets": side["gets"],
                    "sends": side["sends"],
                })
            out.append({"type": "trade", "created": created, "participants": participants})
        else:
            rid = roster_ids[0] if roster_ids else None
            team = roster_by_id.get(rid)
            add_ids = [pid for pid, r in adds.items() if r == rid] or list(adds.keys())
            drop_ids = [pid for pid, r in drops.items() if r == rid] or list(drops.keys())
            if not add_ids and not drop_ids:
                continue
            out.append({
                "type": tx_type,
                "created": created,
                "team_name": team["team_name"] if team else (f"Team {rid}" if rid is not None else "Unbekannt"),
                "roster_id": rid,
                "adds": add_ids,
                "drops": drop_ids,
            })

    out.sort(key=lambda t: t.get("created") or 0, reverse=True)
    return out[:MAX_TRANSACTIONS]


def scouting_profiles(teams, raw_transactions, weakness_matrix, position_rank_matrix):
    """roster_id -> Scouting-Profil: Waiver-/Trade-Aktivität aus den rohen
    Transaktionen dieser Saison, Positionsbedarf (aus weakness_matrix) und
    Positions-Überschuss (Top-3-Liga-Rang laut position_rank_matrix)."""
    waiver_counts = {t["roster_id"]: 0 for t in teams}
    trade_counts = {t["roster_id"]: 0 for t in teams}

    for tx in raw_transactions:
        if tx.get("status") != "complete":
            continue
        tx_type = tx.get("type")
        roster_ids = set(tx.get("roster_ids") or [])
        if tx_type == "trade":
            for rid in roster_ids:
                if rid in trade_counts:
                    trade_counts[rid] += 1
        elif tx_type in ("waiver", "free_agent"):
            for rid in roster_ids:
                if rid in waiver_counts:
                    waiver_counts[rid] += 1

    rank_by_pos_team = {}
    for pos, ranked in position_rank_matrix.items():
        for entry in ranked:
            rank_by_pos_team.setdefault(entry["roster_id"], {})[pos] = entry["rank"]

    profiles = []
    for t in teams:
        rid = t["roster_id"]
        tw = weakness_matrix.get(rid, {})
        ranks = rank_by_pos_team.get(rid, {})
        needs = sorted(
            [p for p in SCOUTING_POSITIONS if tw.get(p, 0) >= 1.5],
            key=lambda p: tw.get(p, 0), reverse=True,
        )
        surplus = sorted(
            [p for p in SCOUTING_POSITIONS if ranks.get(p, 99) <= SURPLUS_RANK_THRESHOLD],
            key=lambda p: ranks.get(p, 99),
        )
        profiles.append({
            "roster_id": rid,
            "team_name": t["team_name"],
            "waiver_moves": waiver_counts.get(rid, 0),
            "trades": trade_counts.get(rid, 0),
            "needs": needs,
            "surplus": surplus,
        })
    profiles.sort(key=lambda p: p["team_name"])
    return profiles
