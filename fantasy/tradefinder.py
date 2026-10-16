"""Trade Finder: durchsucht 1-zu-1 bis 3-zu-2-Kombinationen (beide Richtungen)
zwischen meinem Team und jedem anderen Team, aber zeigt nur Vorschläge, die
für BEIDE Seiten tatsächlich Sinn ergeben. Jeder Vorschlag muss:
  - die Liga-Regeln respektieren (echte roster_positions/FLEX-Regeln aus den
    Settings, nie K/DEF, keine sinnlose Positions-Verdopplung),
    das Roster beider Seiten danach noch vollständig und tief genug lassen,
  - ein klares Zweck-Label bekommen (sonst wird er verworfen).
Kein Vorab-Filter auf "realistische" Trades mehr als Pflicht - Fairness-
Toleranz und Realismus sind Frontend-Filter, Fairness-Vorfilter unten nur
zur Begrenzung der Kombinatorik."""

import itertools

from .roster_strength import weakness_matrix
from .startsit import _best_lineup, HARD_OUT_STATUSES

TRADE_POSITIONS = ("QB", "RB", "WR", "TE")  # K/DEF sind nie Teil eines Trades
SKILL_POSITIONS = ("RB", "WR", "TE")

MIN_LINEUP_GAIN = 1.5  # Punkte/Woche Mindest-Marginalgewinn für ein reines "Upgrade"-Label
MIN_BENCH_DEPTH = 1  # mindestens so viele Bankspieler je Skill-Position nach dem Trade
NEAR_PLAYOFF_WINDOW = 2  # Wochen vor Playoff-Start, die für Bye-Absicherung priorisiert zählen

MY_KEY_PLAYER_COUNT = 5
POOL_CAP = 14
MAX_SIDE_SIZE = 3
VALUE_FAIRNESS_CAP = 0.25
NEED_FIT_SHORTLIST = 20
MAX_PROPOSALS_PER_TEAM = 6
MAX_TOTAL_PROPOSALS = 150

# FantasyCalc preist Verletzungen nicht ein - eigener Abschlag weiter unten
# in _season_value(). COMBO_SIZE_PAIRS bewusst ohne 3-zu-3.
COMBO_SIZE_PAIRS = [
    (1, 1), (1, 2), (1, 3),
    (2, 1), (2, 2), (2, 3),
    (3, 1), (3, 2),
]

INJURY_VALUE_DISCOUNT = {
    "Out": 0.2, "Doubtful": 0.6, "Questionable": 0.9,
    "IR": 0.05, "PUP": 0.05, "Sus": 0.1, "NA": 0.05, "COV": 0.5,
}


def _tradeable_pool(team, players, exclude_ids=None):
    """Nur QB/RB/WR/TE mit bekanntem Marktwert, keine Reserve/IR-Spieler,
    nie K/DEF - das ist ein hartes Invariant, keine Heuristik."""
    exclude_ids = exclude_ids or set()
    reserve = set(team.get("reserve") or [])
    pool = [
        players[pid] for pid in team["players"]
        if pid in players and pid not in reserve and pid not in exclude_ids
        and players[pid]["position"] in TRADE_POSITIONS
        and players[pid].get("trade_value")
    ]
    pool.sort(key=lambda p: p["trade_value"], reverse=True)
    return pool[:POOL_CAP]


def _combos(pool):
    out = {}
    for size in range(1, MAX_SIDE_SIZE + 1):
        out[size] = list(itertools.combinations(pool, size))
    return out


def _need_fit(combo, weakness_for_team):
    return round(sum(weakness_for_team.get(p["position"], 0) for p in combo), 2)


def _lineup_points(player_ids, players, roster_positions, flex_positions, current_week):
    pool = []
    for pid in player_ids:
        p = players.get(pid)
        if not p:
            continue
        if p.get("bye_week") == current_week or p.get("injury_status") in HARD_OUT_STATUSES:
            continue
        p = dict(p)
        p["_eff"] = p.get("projection_week") or 0.0
        pool.append(p)
    lineup = _best_lineup(pool, roster_positions, flex_positions)
    return round(sum(p["_eff"] for p in lineup if p), 2)


def _season_value(player, weeks):
    """Grobe Wertschätzung für mein Team über eine Wochen-Liste: Saison-
    Durchschnitt mal Usage-Trend (letzte 3 vs. Saison) mal Verletzungs-
    Abschlag (FantasyCalc preist Verletzungen nicht ein), Bye Weeks werden
    übersprungen. Getrennt von FantasyCalc (= Marktpreis) nutzbar, um
    Käufe mit hohem Eigenwert bei niedrigem Marktpreis zu finden."""
    bye = player.get("bye_week")
    active_weeks = [w for w in weeks if w != bye]
    if not active_weeks:
        return 0.0
    season_avg = player.get("season_avg") or 0.0
    avg_last3 = player.get("avg_last3")
    trend = 1.0
    if avg_last3 is not None and season_avg:
        trend = max(0.75, min(1.25, avg_last3 / season_avg))
    injury = INJURY_VALUE_DISCOUNT.get(player.get("injury_status"), 1.0)
    return round(season_avg * trend * injury * len(active_weeks), 1)


def _lineup_legality(player_ids, players, rules):
    """Prüft, ob ein Roster nach dem Trade noch alle Pflicht-Slots und eine
    Mindesttiefe je Skill-Position stellen kann. Grobe Heuristik (zählt
    Spieler je Position, keine wochengenaue Simulation) - reicht aber, um
    offensichtlich kaputte Trades (leerer Slot, keine Tiefe mehr) zu
    verwerfen."""
    by_pos = {"QB": [], "RB": [], "WR": [], "TE": [], "K": [], "DEF": []}
    for pid in player_ids:
        p = players.get(pid)
        if p and p["position"] in by_pos:
            by_pos[p["position"]].append(p)
    counts = {pos: len(lst) for pos, lst in by_pos.items()}
    starter_counts = rules["starter_counts"]
    flex_positions = rules["flex_positions"]
    n_flex = starter_counts.get("FLEX", 0)

    for pos, need in starter_counts.items():
        if pos in ("FLEX", "BN", "IR", "TAXI"):
            continue
        if counts.get(pos, 0) < need:
            return False, f"zu wenige {pos}-Spieler für die Pflicht-Slots"

    remaining_flex_eligible = sum(
        max(0, counts.get(pos, 0) - starter_counts.get(pos, 0)) for pos in flex_positions
    )
    if remaining_flex_eligible < n_flex:
        return False, "nicht genug FLEX-fähige Spieler übrig"

    for pos in SKILL_POSITIONS:
        required_depth = starter_counts.get(pos, 0) + MIN_BENCH_DEPTH
        if counts.get(pos, 0) < required_depth:
            return False, f"zu dünne Tiefe auf {pos}"

    return True, None


def _redundant_position_violation(keep_ids, give_combo, get_combo, players, rules):
    """Harte Regel: nie einen zweiten QB (bzw. zweiten TE über die nötige
    Tiefe hinaus), wenn ich schon einen gesunden Starter habe - außer der
    bestehende Starter ist Out/IR (dann ist der Ersatz der Zweck selbst)."""
    give_ids = {p["id"] for p in give_combo}
    get_pos_count = {pos: 0 for pos in ("QB", "TE")}
    give_pos_count = {pos: 0 for pos in ("QB", "TE")}
    for p in get_combo:
        if p["position"] in get_pos_count:
            get_pos_count[p["position"]] += 1
    for p in give_combo:
        if p["position"] in give_pos_count:
            give_pos_count[p["position"]] += 1

    if not rules["super_flex"] and rules["num_qb_starters"] <= 1:
        net_qb = get_pos_count["QB"] - give_pos_count["QB"]
        if net_qb > 0:
            remaining_qbs = [
                players[pid] for pid in keep_ids
                if pid not in give_ids and pid in players and players[pid]["position"] == "QB"
            ]
            healthy_starter = any(p.get("injury_status") not in HARD_OUT_STATUSES for p in remaining_qbs)
            if healthy_starter:
                return True

    net_te = get_pos_count["TE"] - give_pos_count["TE"]
    if net_te > 0:
        remaining_tes = [
            players[pid] for pid in keep_ids
            if pid not in give_ids and pid in players and players[pid]["position"] == "TE"
        ]
        # Schon 1 gesunder TE als Starter + 1 als Tiefe vorhanden -> ein
        # weiterer ist Verdopplung, außer beide verbleibenden sind out.
        healthy_tes = [p for p in remaining_tes if p.get("injury_status") not in HARD_OUT_STATUSES]
        if len(healthy_tes) >= 2:
            return True

    return False


def _purpose_labels(give_combo, get_combo, my_weakness, their_weakness, lineup_delta,
                     my_starters_by_pos, my_roster_by_pos, bye_calendar_weeks, sell_high_ids,
                     buy_low_ids, their_need_fit):
    """Jeder Vorschlag braucht mindestens eines dieser Labels, sonst wird er
    verworfen - das erzwingt, dass jeder Trade einen erkennbaren Zweck hat."""
    labels = []
    give_ids = {p["id"] for p in give_combo}
    get_ids = {p["id"] for p in get_combo}

    if lineup_delta >= MIN_LINEUP_GAIN:
        upgraded_positions = sorted({p["position"] for p in get_combo})
        labels.append(f"Upgrade {'/'.join(upgraded_positions)}")

    for p in get_combo:
        starters_here = my_starters_by_pos.get(p["position"], [])
        if any(s.get("injury_status") in HARD_OUT_STATUSES for s in starters_here):
            labels.append("Loch füllen (Verletzungs-Ersatz)")
            break

    # Bye-Absicherung ist nur dann ein eigener Zweck, wenn ein Starter-Bye
    # in die Nähe der Playoffs fällt UND ich für diese Woche noch keinen
    # anderen gesunden Backup an der Position auf dem Kader habe - sonst
    # würde das Label bei praktisch jedem Trade feuern (fast jeder Spieler
    # hat eine andere Bye-Woche als der Starter) und wäre bedeutungslos.
    for p in get_combo:
        for s in my_starters_by_pos.get(p["position"], []):
            s_bye = s.get("bye_week")
            if not s_bye or s_bye not in bye_calendar_weeks or p.get("bye_week") == s_bye:
                continue
            has_other_backup = any(
                b["id"] not in give_ids and b["id"] != s["id"] and b.get("bye_week") != s_bye
                and b.get("injury_status") not in HARD_OUT_STATUSES
                for b in my_roster_by_pos.get(p["position"], [])
            )
            if not has_other_backup:
                labels.append("Bye-Absicherung vor Playoffs")
                break
        if "Bye-Absicherung vor Playoffs" in labels:
            break

    if len(give_combo) > len(get_combo) and lineup_delta > 0:
        labels.append("Konsolidierung")
    if len(give_combo) < len(get_combo) and lineup_delta > 0:
        labels.append("Tiefe aufbauen")

    if give_ids & sell_high_ids:
        labels.append("Sell High")
    if get_ids & buy_low_ids:
        labels.append("Buy Low")

    if their_need_fit >= 3:
        labels.append("Gegner-Schwäche nutzen")

    # Dedupe, Reihenfolge erhalten
    seen = set()
    out = []
    for l in labels:
        if l not in seen:
            seen.add(l)
            out.append(l)
    return out


def _acceptance_label(their_need_fit, diff_pct, partner_type):
    base_high = their_need_fit >= 3 and diff_pct <= 0.10
    base_low = their_need_fit <= 0.5 or diff_pct > 0.20
    if partner_type == "buyer" and not base_low:
        return "hoch"
    if partner_type == "seller" and diff_pct > 0.15:
        return "niedrig"
    if base_high:
        return "hoch"
    if base_low:
        return "niedrig"
    return "mittel"


def _partner_type(their_rank, num_teams, playoff_teams, scouting):
    """Record/Playoff-Rennen als Basis, aber ein Team mit sehr wenig
    Waiver-/Trade-Aktivität diese Saison gilt als 'passiv' unabhängig vom
    Tabellenplatz - die reine Rang-Heuristik würde sonst auch inaktive
    Manager als Käufer/Verkäufer einstufen."""
    trades = (scouting or {}).get("trades") or 0
    waiver_moves = (scouting or {}).get("waiver_moves") or 0
    activity = trades * 3 + waiver_moves
    if activity <= 1:
        return "passive"
    if playoff_teams and their_rank <= playoff_teams:
        return "buyer"
    if num_teams and their_rank >= num_teams - 2:
        return "seller"
    return "passive"


def _age_stance(give_combo, get_combo, is_dynasty):
    def avg_age(combo):
        ages = [p["age"] for p in combo if p.get("age")]
        return sum(ages) / len(ages) if ages else None

    give_age, get_age = avg_age(give_combo), avg_age(get_combo)
    if give_age is None or get_age is None:
        return None
    if get_age > give_age + 1:
        return "Win-Now"
    if get_age < give_age - 1:
        return "Langfristig" if is_dynasty else None
    return "neutral"


def _reasons(give_combo, get_combo, their_need_fit, my_need_fit, diff_pct):
    reasons = []
    if my_need_fit > 0:
        positions = sorted({p["position"] for p in get_combo})
        reasons.append(f"Verstärkt deinen Bedarf auf {', '.join(positions)}")
    if their_need_fit > 0:
        positions = sorted({p["position"] for p in give_combo})
        reasons.append(f"Trifft den Bedarf des anderen Teams auf {', '.join(positions)}")
    reasons.append(f"Wertdifferenz {round(diff_pct * 100, 1)}%")
    return reasons


def _partner_accept_reasons(give_combo, get_combo, their_need_fit, their_lineup_delta, partner_type, diff_pct):
    """Separate, partner-fokussierte Begründung: warum der ANDERE Manager
    diesem Trade zustimmen könnte - nicht zu verwechseln mit den eigenen
    Gründen in _reasons()."""
    reasons = []
    if their_lineup_delta > 0:
        reasons.append(f"Verbessert sein eigenes Lineup um {their_lineup_delta} Pkt./Woche")
    if their_need_fit > 0:
        positions = sorted({p["position"] for p in give_combo})
        reasons.append(f"Füllt seinen Bedarf auf {', '.join(positions)}")
    if partner_type == "buyer":
        reasons.append("Team im Playoff-Rennen - eher bereit, für sofortige Verbesserung zu handeln")
    elif partner_type == "seller":
        reasons.append("Team ohne Playoff-Chance - eher bereit, etablierte Spieler für Perspektive abzugeben")
    if diff_pct <= 0.10:
        reasons.append("Wertmäßig sehr ausgeglichen")
    return reasons or ["Kein eindeutiger Grund erkennbar - Annahme unsicher"]


def _roster_overflow(player_ids, total_roster_slots):
    return len(player_ids) > total_roster_slots


def _league_rules_note(rules, is_dynasty, num_teams):
    league_type_label = "Dynasty" if is_dynasty else "Keeper" if rules.get("is_keeper_or_dynasty") else "Redraft"
    qb_label = "SUPER_FLEX" if rules.get("super_flex") else f"{rules.get('num_qb_starters', 1)} Start-QB"
    return (
        f"Liga-Regeln berücksichtigt: {league_type_label}, {qb_label}, {num_teams} Teams. "
        "K/DEF sind nie Teil eines Trades. Jeder Vorschlag braucht ein Zweck-Label, respektiert "
        "Roster-Pflicht-Slots und Mindesttiefe je Skill-Position - ohne das wird er verworfen."
    )


def compute(data, rules, bye_weeks_by_team):
    players = data["players"]
    teams = data["teams"]
    my_roster_id = data["me"]["roster_id"]
    my_team = next(t for t in teams if t["roster_id"] == my_roster_id)
    roster_positions = data["league"]["roster_positions"]
    flex_positions = rules.get("flex_positions") or {"RB", "WR", "TE"}
    current_week = data["league"]["week"]
    playoff_week_start = data["league"].get("playoff_week_start")
    num_teams = data["league"].get("total_rosters")
    playoff_teams = data["league"].get("playoff_teams")
    is_dynasty = rules.get("is_dynasty", False)
    trade_deadline = data["league"].get("trade_deadline")
    total_roster_slots = rules.get("total_roster_slots") or (len(roster_positions) + (rules.get("reserve_slots") or 0))

    weakness = weakness_matrix(teams, players)
    my_weakness = weakness.get(my_roster_id, {})

    sell_buy = data.get("sell_buy") or {"sell_high": [], "buy_low": []}
    sell_high_ids = {e["player_id"] for e in sell_buy.get("sell_high", []) if e.get("is_mine")}
    buy_low_ids = {e["player_id"] for e in sell_buy.get("buy_low", [])}

    scouting_by_roster = {p["roster_id"]: p for p in (data.get("league_feed") or {}).get("scouting_profiles", [])}

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
    my_baseline_points = _lineup_points(my_current_ids, players, roster_positions, flex_positions, current_week)

    my_starters_by_pos = {}
    for s in data["my_roster"]["slots"]:
        p = players.get(s["player_id"])
        if p:
            my_starters_by_pos.setdefault(p["position"], []).append(p)

    my_roster_by_pos = {}
    for pid in my_current_ids:
        p = players.get(pid)
        if p:
            my_roster_by_pos.setdefault(p["position"], []).append(p)

    bye_calendar_weeks = set()
    if playoff_week_start:
        window_start = playoff_week_start - NEAR_PLAYOFF_WINDOW
        bye_calendar_weeks = set(range(window_start, playoff_week_start))

    remaining_weeks_list = sorted({g["week"] for g in data["planner"]["remaining_schedule"]})
    remaining_weeks = min(len(remaining_weeks_list), 12) or 1
    deadline_weeks = [w for w in range(current_week, (trade_deadline or current_week) + 1)]
    playoff_weeks = [w for w in range(playoff_week_start, min((playoff_week_start or 14) + 4, 19))] if playoff_week_start else []

    all_candidates = []

    for team in teams:
        if team["roster_id"] == my_roster_id:
            continue
        their_weakness = weakness.get(team["roster_id"], {})
        their_pool = _tradeable_pool(team, players)
        if not their_pool:
            continue
        their_combos = _combos(their_pool)
        their_rank = team.get("rank") or (num_teams or 14)
        scouting = scouting_by_roster.get(team["roster_id"])
        partner_type = _partner_type(their_rank, num_teams, playoff_teams, scouting)
        their_keep_ids = team["players"]
        their_baseline_points = _lineup_points(their_keep_ids, players, roster_positions, flex_positions, current_week)

        team_candidates = []
        for give_size, get_size in COMBO_SIZE_PAIRS:
            for give_combo in my_combos.get(give_size, []):
                v1 = sum(p["trade_value"] for p in give_combo)
                for get_combo in their_combos.get(get_size, []):
                    v2 = sum(p["trade_value"] for p in get_combo)
                    diff_pct = abs(v1 - v2) / max(v1, v2)
                    if diff_pct > VALUE_FAIRNESS_CAP:
                        continue
                    if _redundant_position_violation(my_current_ids, give_combo, get_combo, players, rules):
                        continue
                    if _redundant_position_violation(their_keep_ids, get_combo, give_combo, players, rules):
                        continue
                    my_need_fit = _need_fit(get_combo, my_weakness)
                    their_need_fit = _need_fit(give_combo, their_weakness)
                    priority = my_need_fit * 2 + their_need_fit + (v1 + v2) / 5000
                    team_candidates.append((priority, diff_pct, my_need_fit, their_need_fit, give_combo, get_combo, v1, v2, partner_type, their_rank))

        team_candidates.sort(key=lambda c: c[0], reverse=True)
        shortlist = team_candidates[:NEED_FIT_SHORTLIST]

        for priority, diff_pct, my_need_fit, their_need_fit, give_combo, get_combo, v1, v2, partner_type, their_rank in shortlist:
            give_ids = {p["id"] for p in give_combo}
            get_ids = {p["id"] for p in get_combo}

            my_hypothetical_ids = [pid for pid in my_current_ids if pid not in give_ids] + list(get_ids)
            legal, _reason = _lineup_legality(my_hypothetical_ids, players, rules)

            their_hypothetical_ids = [pid for pid in their_keep_ids if pid not in get_ids] + list(give_ids)
            their_legal, _their_reason = _lineup_legality(their_hypothetical_ids, players, rules)

            if _roster_overflow(my_hypothetical_ids, total_roster_slots) or _roster_overflow(their_hypothetical_ids, total_roster_slots):
                must_drop = True
            else:
                must_drop = False

            after_points = _lineup_points(my_hypothetical_ids, players, roster_positions, flex_positions, current_week)
            lineup_delta = round(after_points - my_baseline_points, 2)
            their_after_points = _lineup_points(their_hypothetical_ids, players, roster_positions, flex_positions, current_week)
            their_lineup_delta = round(their_after_points - their_baseline_points, 2)
            is_win_win = lineup_delta > 0 and their_lineup_delta > 0

            labels = _purpose_labels(
                give_combo, get_combo, my_weakness, their_weakness, lineup_delta,
                my_starters_by_pos, my_roster_by_pos, bye_calendar_weeks, sell_high_ids, buy_low_ids, their_need_fit,
            )
            if not labels:
                continue
            if not legal and lineup_delta < MIN_LINEUP_GAIN * 3:
                # Positionsloch ohne klar hohen Gesamtgewinn -> verwerfen
                continue
            if not their_legal:
                continue

            has_injured = any(p.get("injury_status") in HARD_OUT_STATUSES for p in give_combo + get_combo)
            includes_key_player = bool(give_ids & key_player_ids)

            my_value_deadline = sum(_season_value(p, deadline_weeks) for p in get_combo) - sum(_season_value(p, deadline_weeks) for p in give_combo)
            my_value_playoffs = sum(_season_value(p, playoff_weeks) for p in get_combo) - sum(_season_value(p, playoff_weeks) for p in give_combo)

            stance = _age_stance(give_combo, get_combo, is_dynasty)

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
                "their_lineup_points_before": their_baseline_points,
                "their_lineup_points_after": their_after_points,
                "their_lineup_delta": their_lineup_delta,
                "is_win_win": is_win_win,
                "my_value_delta_until_deadline": round(my_value_deadline, 1),
                "my_value_delta_playoffs": round(my_value_playoffs, 1),
                "season_delta_estimate": round(
                    (sum(p["season_avg"] for p in get_combo) - sum(p["season_avg"] for p in give_combo)) * remaining_weeks,
                    1,
                ),
                "remaining_weeks_estimate": remaining_weeks,
                "acceptance": _acceptance_label(their_need_fit, diff_pct, partner_type),
                "partner_type": partner_type,
                "stance": stance,
                "purpose_labels": labels,
                "roster_legal_for_me": legal,
                "must_drop_players": must_drop,
                "includes_key_player": includes_key_player,
                "has_injured_player": has_injured,
                "my_need_fit": my_need_fit,
                "their_need_fit": their_need_fit,
                "their_record": f"{team.get('wins',0)}-{team.get('losses',0)}",
                "their_waiver_moves": scouting["waiver_moves"] if scouting else None,
                "their_trades": scouting["trades"] if scouting else None,
                "reasons": _reasons(give_combo, get_combo, their_need_fit, my_need_fit, diff_pct),
                "partner_accept_reasons": _partner_accept_reasons(give_combo, get_combo, their_need_fit, their_lineup_delta, partner_type, diff_pct),
            })

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
        "league_rules_note": _league_rules_note(rules, is_dynasty, num_teams),
    }


def validate_proposals(trade_finder_data, players):
    """Prüft die harten Invarianten über ALLE tatsächlich erzeugten
    Vorschläge (nicht nur Stichproben): nie K/DEF, jeder Vorschlag hat ein
    Zweck-Label, keine Duplikate. Wird von build.py als Build-Gate benutzt -
    Verstöße brechen den Build ab, genau wie die Plausibilitätsprüfung.
    Gibt eine Liste von Fehlertexten zurück (leer = alles ok)."""
    errors = []
    seen_combos = set()
    for p in trade_finder_data.get("proposals", []):
        for pid in p["give_player_ids"] + p["get_player_ids"]:
            pos = (players.get(pid) or {}).get("position")
            if pos in ("K", "DEF"):
                errors.append(f"Trade enthält K/DEF ({pid}, {pos}): {p['team_name']}")
        if not p.get("purpose_labels"):
            errors.append(f"Vorschlag ohne Zweck-Label: {p['team_name']} {p['give_player_ids']}->{p['get_player_ids']}")
        key = (p["roster_id"], tuple(sorted(p["give_player_ids"])), tuple(sorted(p["get_player_ids"])))
        if key in seen_combos:
            errors.append(f"Doppelter Vorschlag: {key}")
        seen_combos.add(key)
    return errors
