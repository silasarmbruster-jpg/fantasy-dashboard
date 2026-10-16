"""Liest die tatsächlichen Liga-Regeln aus den Sleeper-Settings, statt sie
fest zu codieren: Roster-Slots, erlaubte FLEX-Positionen (SUPER_FLEX schaltet
einen zweiten startbaren QB frei), Liga-Typ (Redraft/Keeper/Dynasty) und die
daraus passenden FantasyCalc-Parameter."""

FLEX_BASE = {"RB", "WR", "TE"}


def parse(league):
    settings = league.get("settings", {}) or {}
    roster_positions = league.get("roster_positions", []) or []
    scoring = league.get("scoring_settings", {}) or {}

    starter_slots = [p for p in roster_positions if p not in ("BN", "IR", "TAXI")]
    super_flex = "SUPER_FLEX" in roster_positions
    flex_positions = FLEX_BASE | ({"QB"} if super_flex else set())

    starter_counts = {}
    for slot in starter_slots:
        starter_counts[slot] = starter_counts.get(slot, 0) + 1

    league_type = settings.get("type", 0)  # 0=Redraft, 1=Keeper, 2=Dynasty
    is_dynasty = league_type == 2
    is_keeper_or_dynasty = league_type in (1, 2)

    rec_points = scoring.get("rec", 0) or 0
    if rec_points >= 0.9:
        ppr = 1
    elif rec_points >= 0.4:
        ppr = 0.5
    else:
        ppr = 0

    return {
        "starter_slots": starter_slots,
        "starter_counts": starter_counts,
        "flex_positions": flex_positions,
        "super_flex": super_flex,
        "num_qb_starters": starter_counts.get("QB", 0) + (1 if super_flex else 0),
        "reserve_slots": settings.get("reserve_slots", 0),
        "trade_deadline": settings.get("trade_deadline"),
        "playoff_week_start": settings.get("playoff_week_start"),
        "playoff_teams": settings.get("playoff_teams"),
        "num_teams": settings.get("num_teams"),
        "league_type": league_type,
        "is_dynasty": is_dynasty,
        "is_keeper_or_dynasty": is_keeper_or_dynasty,
        "num_qbs_fantasycalc": 2 if super_flex else 1,
        "ppr": ppr,
        "total_roster_slots": len(roster_positions) + (settings.get("reserve_slots") or 0),
    }
