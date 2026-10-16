"""Sell High / Buy Low: Spieler, deren Punkteausbeute deutlich über bzw.
unter ihrem Usage-Niveau (Touches/Targets pro Spiel) liegt. Reine
Volumen-vs-Produktions-Analyse aus den bereits vorhandenen Season-Daten,
keine externen Advanced-Metrics oder erfundenen Werte."""

MIN_GAMES = 2
SELL_HIGH_RATIO = 1.25
BUY_LOW_USAGE_RATIO = 1.1
BUY_LOW_EFFICIENCY_RATIO = 0.8


def _opportunity(p):
    if p["position"] == "RB":
        return p.get("touches_pg") or 0
    if p["position"] in ("WR", "TE"):
        return p.get("targets_pg") or 0
    return 0


def compute(data):
    players = data["players"]
    my_roster_id = data["me"]["roster_id"]
    pool = [p for p in players.values() if p["position"] in ("RB", "WR", "TE") and p["games_played"] >= MIN_GAMES]

    by_pos = {}
    for p in pool:
        opp = _opportunity(p)
        if opp <= 0:
            continue
        ppo = p["season_avg"] / opp
        by_pos.setdefault(p["position"], []).append((p, opp, ppo))

    league_avg_ppo = {}
    league_avg_opp = {}
    for pos, entries in by_pos.items():
        league_avg_ppo[pos] = sum(e[2] for e in entries) / len(entries)
        league_avg_opp[pos] = sum(e[1] for e in entries) / len(entries)

    def _is_mine(p):
        return bool(p["fantasy_team"] and p["fantasy_team"]["roster_id"] == my_roster_id)

    sell_high, buy_low = [], []
    for pos, entries in by_pos.items():
        avg_ppo, avg_opp = league_avg_ppo[pos], league_avg_opp[pos]
        if not avg_ppo or not avg_opp:
            continue
        for p, opp, ppo in entries:
            ppo_ratio = ppo / avg_ppo
            opp_ratio = opp / avg_opp
            entry = {
                "player_id": p["id"],
                "ppo_ratio": round(ppo_ratio, 2),
                "opportunity_pg": round(opp, 1),
                "is_mine": _is_mine(p),
            }
            if ppo_ratio >= SELL_HIGH_RATIO:
                sell_high.append(entry)
            if opp_ratio >= BUY_LOW_USAGE_RATIO and ppo_ratio <= BUY_LOW_EFFICIENCY_RATIO:
                buy_low.append(dict(entry, opp_ratio=round(opp_ratio, 2)))

    sell_high.sort(key=lambda e: (0 if e["is_mine"] else 1, -e["ppo_ratio"]))
    buy_low.sort(key=lambda e: (0 if e["is_mine"] else 1, -e["opp_ratio"]))

    return {"sell_high": sell_high[:15], "buy_low": buy_low[:15]}
