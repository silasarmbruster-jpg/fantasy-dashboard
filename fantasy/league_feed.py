"""Aufbereitung für den Liga-Tab: Power-Ranking nach Roster-Wert und eine
lesbare Transaktions-Historie aus den rohen Sleeper-Transaktionen."""

MAX_TRANSACTIONS = 25


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
