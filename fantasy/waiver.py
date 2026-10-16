"""Waiver-Wire-Empfehlungen: Kategorien (Gesamt, Lineup-Upgrade, Trending,
je Position, Handcuffs/Breakouts, Streaming-Tipp), FAAB/Prioritäts-
Erkennung mit Gebotsvorschlag bzw. Prioritäts-Hinweis, und Ersatzvorschläge
für verletzte Spieler aus Bank oder Waiver."""

from .roster_strength import FLEX_ELIGIBLE, STARTER_SLOTS_BY_POS, weakness_matrix

MAX_SUGGESTIONS_PER_POSITION = 8
HARD_OUT_STATUSES = {"Out", "IR", "NA", "Sus", "PUP", "COV", "DNR"}
ALL_INJURY_STATUSES = HARD_OUT_STATUSES | {"Questionable", "Doubtful"}


def _position_weakness(teams, players, my_roster_id):
    return weakness_matrix(teams, players).get(my_roster_id, {})


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


def _score(p, pos, weakness):
    s = (p["season_avg"] or 0) * 1.0
    s += (p.get("projection_week") or 0) * 0.5
    s += ((p.get("trending_add") or 0) / 50000) * 2.0
    s += weakness.get(pos, 0) * 1.5
    return s


def _detect_waiver_system(league, my_roster_raw, raw_transactions):
    """Ermittelt FAAB vs. Prioritäts-Waiver empirisch aus der Transaktions-
    historie (verlässlicher als das rohe waiver_type-Feld, das auch bei
    reinen Prioritäts-Ligen oft einen Budget-Default stehen hat)."""
    uses_faab = any(
        tx.get("type") == "waiver" and (
            (tx.get("settings") or {}).get("waiver_bid") is not None or tx.get("waiver_budget")
        )
        for tx in (raw_transactions or [])
    )
    settings = (my_roster_raw or {}).get("settings", {})
    if uses_faab:
        budget_total = league["settings"].get("waiver_budget")
        used = settings.get("waiver_budget_used", 0)
        return {
            "type": "faab",
            "budget_total": budget_total,
            "budget_remaining": (budget_total - used) if budget_total is not None else None,
        }
    has_any_waiver_tx = any(tx.get("type") == "waiver" for tx in (raw_transactions or []))
    return {
        "type": "priority" if has_any_waiver_tx or settings.get("waiver_position") else "unbekannt",
        "priority": settings.get("waiver_position"),
        "total_teams": league["settings"].get("num_teams"),
    }


def _faab_bid(p, max_trending, waiver_system):
    budget = waiver_system.get("budget_remaining")
    if budget is None or budget <= 0:
        return None
    urgency = min(1.0, (p.get("trending_add") or 0) / max(1, max_trending))
    pct = round(4 + urgency * 28)  # 4%..32% des Restbudgets je nach Nachfrage
    amount = max(1, round(budget * pct / 100))
    return {"amount": amount, "pct_of_budget": pct}


def _handcuffs(players, my_roster_id):
    rb1_by_team = {
        p["team"]: p for p in players.values()
        if p["position"] == "RB" and p.get("depth_chart_order") == 1 and p["team"]
    }
    out = []
    for p in players.values():
        if p["position"] != "RB" or p["fantasy_team"] is not None or p.get("depth_chart_order") != 2:
            continue
        starter = rb1_by_team.get(p["team"])
        if not starter or not starter.get("trade_value"):
            continue
        out.append({
            "player_id": p["id"],
            "handcuff_for_player_id": starter["id"],
            "is_mine": bool(starter["fantasy_team"] and starter["fantasy_team"]["roster_id"] == my_roster_id),
        })
    out.sort(key=lambda e: (not e["is_mine"]))
    return out[:10]


def _breakouts(free_agents):
    candidates = [
        p for p in free_agents
        if (p.get("years_exp") is not None and p["years_exp"] <= 2)
        and p["position"] in FLEX_ELIGIBLE | {"QB"}
        and ((p.get("trending_add") or 0) > 5000 or (p["games_played"] >= 2 and p["avg_last3"] > p["season_avg"] * 1.2 > 0))
    ]
    candidates.sort(key=lambda p: (p.get("trending_add") or 0, p["avg_last3"]), reverse=True)
    return [c["id"] for c in candidates[:8]]


def _streaming_tips(free_agents):
    tips = {}
    for pos in ("DEF", "K", "TE"):
        pool = [p for p in free_agents if p["position"] == pos and p.get("projection_week")]
        if not pool:
            continue
        for p in pool:
            p["_stream_score"] = (p.get("projection_week") or 0) * (p.get("matchup_factor") or 1.0)
        best = max(pool, key=lambda p: p["_stream_score"])
        tips[pos] = {
            "player_id": best["id"],
            "opponent": best.get("matchup_opponent"),
            "matchup_factor": best.get("matchup_factor"),
        }
    return tips


def injury_replacements(data):
    """Nur für aktuelle STARTER (nicht Bank/Reserve - dort ist kein
    Lineup-Eingriff nötig): beste Alternative von der Bank, sonst vom
    Waiver, bevorzugt exakt gleiche Position vor Flex-Kompatibilität."""
    players = data["players"]
    starter_ids = [s["player_id"] for s in data["my_roster"]["slots"] if s["player_id"]]
    bench_ids = set(data["my_roster"]["bench"])
    free_agents = [p for p in players.values() if p["fantasy_team"] is None]

    def _pick(pool_ids, positions):
        opts = [
            players[i] for i in pool_ids
            if i in players and players[i]["position"] in positions
            and players[i].get("injury_status") not in HARD_OUT_STATUSES
        ]
        return max(opts, key=lambda x: x.get("projection_week") or 0) if opts else None

    out = []
    for pid in starter_ids:
        p = players.get(pid)
        if not p or p.get("injury_status") not in ALL_INJURY_STATUSES:
            continue
        exact_pos = {p["position"]}
        flex_pos = FLEX_ELIGIBLE if p["position"] in FLEX_ELIGIBLE else exact_pos

        best = _pick(bench_ids, exact_pos) or _pick(bench_ids, flex_pos)
        source = "bench"
        if not best:
            fa_ids = [fa["id"] for fa in free_agents]
            best = _pick(fa_ids, exact_pos) or _pick(fa_ids, flex_pos)
            source = "waiver"
        out.append({"player_id": pid, "replacement_id": best["id"] if best else None, "source": source if best else None})
    return out


def compute(data, league_raw=None, my_roster_raw=None, raw_transactions=None):
    players = data["players"]
    teams = data["teams"]
    my_roster_id = data["me"]["roster_id"]
    bench_ids = data["my_roster"]["bench"]
    league_raw = league_raw or {"settings": {}}

    weakness = _position_weakness(teams, players, my_roster_id)

    pos_avgs = {}
    for pos in STARTER_SLOTS_BY_POS:
        vals = [p["season_avg"] for p in players.values() if p["position"] == pos and p["games_played"] > 0]
        pos_avgs[pos] = sum(vals) / len(vals) if vals else 0.0

    free_agents = [p for p in players.values() if p["fantasy_team"] is None]
    waiver_system = _detect_waiver_system(league_raw, my_roster_raw, raw_transactions)
    max_trending = max([p.get("trending_add") or 0 for p in free_agents], default=0)

    def _entry(p, pos):
        entry = {
            "player_id": p["id"],
            "reasons": _reasons(p, weakness.get(pos, 0), pos_avgs.get(pos, 0)),
            "drop_candidate_id": _drop_candidate(pos, bench_ids, players),
        }
        if waiver_system["type"] == "faab":
            bid = _faab_bid(p, max_trending, waiver_system)
            if bid:
                entry["faab_bid"] = bid
        if p.get("trending_add") and max_trending and p["trending_add"] >= max_trending * 0.5:
            entry["high_competition"] = True
        return entry

    suggestions_by_pos = {}
    scored_entries = []
    for pos in STARTER_SLOTS_BY_POS:
        pos_players = [p for p in free_agents if p["position"] == pos]
        pos_players.sort(key=lambda p: _score(p, pos, weakness), reverse=True)
        top = pos_players[:MAX_SUGGESTIONS_PER_POSITION]
        entries = [_entry(p, pos) for p in top]
        suggestions_by_pos[pos] = entries
        for p, entry in zip(top, entries):
            scored_entries.append((_score(p, pos, weakness), entry))

    scored_entries.sort(key=lambda t: t[0], reverse=True)
    top_overall = [entry for _, entry in scored_entries[:10]]

    # Bester Lineup-Upgrade: Projection-Gewinn ggü. meinem schwächsten
    # Starter/Flex an einer kompatiblen Position, diese Woche sofort nutzbar.
    my_slots = data["my_roster"]["slots"]

    def _weakest_starter(position):
        compatible = FLEX_ELIGIBLE if position in FLEX_ELIGIBLE else {position}
        cands = [players[s["player_id"]] for s in my_slots if s["player_id"] in players and players[s["player_id"]]["position"] in compatible]
        return min(cands, key=lambda p: p.get("projection_week") or 0) if cands else None

    lineup_upgrades = []
    for p in free_agents:
        weakest = _weakest_starter(p["position"])
        if not weakest:
            continue
        delta = (p.get("projection_week") or 0) - (weakest.get("projection_week") or 0)
        if delta > 0.5:
            lineup_upgrades.append({
                "player_id": p["id"],
                "replaces_player_id": weakest["id"],
                "delta": round(delta, 2),
            })
    lineup_upgrades.sort(key=lambda e: e["delta"], reverse=True)

    trending_list = sorted(
        (p for p in free_agents if p.get("trending_add")),
        key=lambda p: p["trending_add"], reverse=True,
    )[:10]

    return {
        "waiver_system": waiver_system,
        "position_weakness": weakness,
        "by_position": suggestions_by_pos,
        "top_overall": top_overall,
        "lineup_upgrades": lineup_upgrades[:8],
        "trending": [p["id"] for p in trending_list],
        "handcuffs": _handcuffs(players, my_roster_id),
        "breakouts": _breakouts(free_agents),
        "streaming": _streaming_tips(free_agents),
        "injury_replacements": injury_replacements(data),
    }
