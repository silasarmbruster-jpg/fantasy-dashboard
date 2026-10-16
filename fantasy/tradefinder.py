"""Trade Finder v5: kompletter Neuaufbau um zwei Reiter herum.

- "Spieler-Suche" (Modus A: eigenen Spieler abgeben / Modus B: Zielspieler
  holen) - der Nutzer wählt Spieler, diese Datei liefert für JEDEN
  handelbaren Spieler (meiner wie jeder gegnerische) einen Index aus
  Paketen, gruppiert nach Format (Spielerzahl je Seite).
- "Trade-Ideen" - die Seite sucht selbst, ohne Spielerwahl, nach
  Gelegenheiten in 7 Kategorien (Spitze verbessern, Breite aufbauen,
  Bye-Weeks, Buy Low, Partner-Notlage, Sell High, Playoff-Vorbereitung).

Architektur (Performance): pro Partner-Team werden die wertvollsten Spieler
beider Seiten (POOL_CAP) zu Paketen bis GIVE_MAX_SIDE (ich) bzw. GET_MAX_SIDE (ich bekomme) Spielern je Seite
kombiniert. Die Wert-Fairness-Prüfung (billig, reine Arithmetik) läuft VOR
der teuren Lineup-Prüfung (Beam-Search-Prinzip: nur wertmäßig passende
Teilpakete werden überhaupt mit dem Lineup-Optimizer geprüft). Für einzelne,
frei gewählte Spieler, die es nicht in den allgemeinen Pool schaffen, gibt es
eine gezielte, günstige Nachsuche (anchored auf genau diesen Spieler).

Alle Zahlen kommen aus echten Daten (Sleeper, FantasyCalc, ESPN - siehe
build.py). Fehlende Daten (z.B. kein strukturierter Rückkehrtermin bei
Verletzungen) werden nie erfunden, sondern offen als "unbekannt" markiert.
"""

import itertools
import time
from collections import Counter

from .roster_strength import weakness_matrix
from .startsit import _best_lineup, HARD_OUT_STATUSES

TRADE_POSITIONS = ("QB", "RB", "WR", "TE")  # K/DEF sind nie Teil eines Trades
SKILL_POSITIONS = ("RB", "WR", "TE")

NEAR_PLAYOFF_WINDOW = 2  # Wochen vor Playoff-Start, die für Bye-Absicherung zählen
MIN_BENCH_DEPTH = 1

GIVE_MAX_SIDE = 4  # "keine feste Obergrenze" heißt praktisch: bis 4 Spieler auf meiner Seite
GET_MAX_SIDE = 3  # ... und bis 3 auf der Empfangsseite, siehe Formate in Teil 2 (nie 4) und PR-Beschreibung
POOL_CAP = 9  # je Team nur die wertvollsten N Spieler für den allgemeinen Paar-Abgleich
TOPUP_COMPANION_CAP = 6  # Begleitspieler-Pool für die gezielte Nachsuche eines einzelnen Spielers

DEFAULT_FORMATS = [(1, 1), (2, 1), (3, 1), (1, 2), (2, 2), (3, 2)]
EXTRA_FORMATS = [(4, 1), (4, 2), (1, 3), (2, 3), (3, 3), (4, 3)]

POWER = 1.5  # Potenz-Summe: Summe der Werte^1.5, damit zwei Mittelklasse-Spieler keinen Star aufwiegen
REPLACEMENT_VALUE = 50  # fehlender Marktwert (null) wird als niedriges Ersatzniveau behandelt, nicht als 0
GAIN_CAP = 0.10  # was ich bekomme, darf NIE mehr als 10% mehr Wert haben als das, was ich gebe - wird nie gelockert
TOLERANCE_OPTIONS = [0.05, 0.10, 0.15, 0.20]
DEFAULT_TOLERANCE = 0.10
TOLERANCE_MAX = 0.20  # Lockerung ausschließlich zu meinen Lasten (ich überzahle), nie zugunsten eines Partner-Verlusts
SUPERSTAR_CAP = 1.3
TOP30_RANK = 30

MIN_PACKAGES_PER_PLAYER = 2
MIN_FORMATS_PER_PLAYER = 3
MAX_PACKAGES_PER_FORMAT = 3  # Standardformate: pro Spieler/Format vorgehalten, Frontend zeigt 3-5 + "Mehr anzeigen"
EXTRA_FORMAT_CAP = 2  # "Mehr Formate"-Formate: seltener angesehen, kleinerer Vorrat je Spieler
TARGET_MIN_TRADE_VALUE = 150  # Zielspieler-Index nur für Spieler mit nennenswertem Marktwert (Datei-Größe)
IDEA_LIMIT = 10

PERFORMANCE_BUDGET_SECONDS = 45.0

INJURY_VALUE_DISCOUNT = {
    "Out": 0.2, "Doubtful": 0.6, "Questionable": 0.9,
    "IR": 0.05, "PUP": 0.05, "Sus": 0.1, "NA": 0.05, "COV": 0.5,
}
SEASON_ENDING_STATUSES = {"IR", "PUP", "NA", "Sus", "COV"}  # werden nie als Buy-Low-Kauf vorgeschlagen
SHORT_TERM_INJURY_STATUSES = {"Questionable", "Doubtful"}
INJURY_RISK_LABEL = {"Questionable": "niedrig", "Doubtful": "mittel", "Out": "hoch"}

STATUS_LABELS_DE = {
    "Questionable": "fraglich", "Doubtful": "unwahrscheinlich im Einsatz", "Out": "out",
    "IR": "verletzt (IR)", "PUP": "PUP", "Sus": "gesperrt", "NA": "nicht verfügbar", "COV": "Covid-Liste",
}


# ---------------------------------------------------------------------------
# Grundbausteine
# ---------------------------------------------------------------------------

def _tradeable_pool(team, players, pool_cap=None):
    """Nur QB/RB/WR/TE mit bekanntem Marktwert ODER fehlendem (= niedriges
    Ersatzniveau, siehe REPLACEMENT_VALUE), keine Reserve/IR-Spieler, nie
    K/DEF - hartes Invariant."""
    reserve = set(team.get("reserve") or [])
    pool = [
        players[pid] for pid in team["players"]
        if pid in players and pid not in reserve
        and players[pid]["position"] in TRADE_POSITIONS
    ]
    pool.sort(key=lambda p: p.get("trade_value") or 0, reverse=True)
    return pool[:pool_cap] if pool_cap else pool


def _player_value(p):
    return p.get("trade_value") or REPLACEMENT_VALUE


def _week_player_effective(p, week, current_week):
    """Effektive Punktzahl eines Spielers für eine bestimmte Woche - echte
    Projection für die aktuelle Woche, für andere Wochen der beste
    verfügbare Schätzwert (Saison-Schnitt mit Usage-Trend- und
    Verletzungs-Abschlag, da keine spielerspezifische Wochen-Projection für
    künftige Wochen in den Daten existiert). Bye Week: komplett raus."""
    if p.get("bye_week") == week:
        return None
    if week == current_week:
        if p.get("injury_status") in HARD_OUT_STATUSES:
            return None
        return p.get("projection_week") or 0.0
    season_avg = p.get("season_avg") or 0.0
    avg_last3 = p.get("avg_last3")
    trend = 1.0
    if avg_last3 is not None and season_avg:
        trend = max(0.75, min(1.25, avg_last3 / season_avg))
    injury = INJURY_VALUE_DISCOUNT.get(p.get("injury_status"), 1.0)
    return round(season_avg * trend * injury, 2)


def _week_lineup_analysis(player_ids, players, roster_positions, flex_positions, week, current_week):
    pool = []
    for pid in player_ids:
        p = players.get(pid)
        if not p:
            continue
        eff = _week_player_effective(p, week, current_week)
        if eff is None:
            continue
        p2 = dict(p)
        p2["_eff"] = eff
        pool.append(p2)
    lineup = _best_lineup(pool, roster_positions, flex_positions)
    starter_ids = {p["id"] for p in lineup if p}
    points = round(sum(p["_eff"] for p in lineup if p), 2)
    by_pos = {}
    for pid in player_ids:
        p = players.get(pid)
        if p:
            by_pos.setdefault(p["position"], []).append(p)
    return starter_ids, by_pos, points


def _week_lineup_points(player_ids, players, roster_positions, flex_positions, week, current_week):
    _s, _b, points = _week_lineup_analysis(player_ids, players, roster_positions, flex_positions, week, current_week)
    return points


def _value_breakdown(before_ids, after_ids, players, roster_positions, flex_positions,
                      current_week, deadline_weeks, playoff_weeks):
    """Wochen-für-Woche-Aufschlüsselung aus EINER Funktion - "diese Woche",
    "Bis Deadline" und "Playoffs" können rechnerisch nie widersprüchlich
    sein, weil sie reine Summen derselben Wochenwerte sind."""
    all_weeks = sorted(set(deadline_weeks) | set(playoff_weeks))
    weekly = []
    for w in all_weeks:
        before = _week_lineup_points(before_ids, players, roster_positions, flex_positions, w, current_week)
        after = _week_lineup_points(after_ids, players, roster_positions, flex_positions, w, current_week)
        weekly.append({"week": w, "before": before, "after": after, "delta": round(after - before, 2)})
    by_week = {e["week"]: e for e in weekly}
    until_deadline_total = round(sum(by_week[w]["delta"] for w in deadline_weeks if w in by_week), 2)
    playoffs_total = round(sum(by_week[w]["delta"] for w in playoff_weeks if w in by_week), 2)
    this_week_delta = by_week[current_week]["delta"] if current_week in by_week else (weekly[0]["delta"] if weekly else 0.0)
    return {
        "weeks": weekly,
        "until_deadline_total": until_deadline_total,
        "playoffs_total": playoffs_total,
        "this_week_delta": this_week_delta,
        "short_term_negative_long_term_positive": this_week_delta < 0 and (until_deadline_total > 0 or playoffs_total > 0),
    }


def _bench_snapshot(ids, players, starter_ids):
    bench_ids = [pid for pid in ids if pid not in starter_ids]
    bench_value = sum((players.get(pid) or {}).get("season_avg") or 0 for pid in bench_ids)
    bye1314 = sum(1 for pid in bench_ids if (players.get(pid) or {}).get("bye_week") in (13, 14))
    return {"bench_value": round(bench_value, 1), "bench_bye_13_14_count": bye1314, "bench_count": len(bench_ids)}


# ---------------------------------------------------------------------------
# Kombinationen vorberechnen (billig: nur Werte/Positionen, keine Lineups)
# ---------------------------------------------------------------------------

def _combo_record(combo_players, current_starter_ids=None):
    ids = tuple(sorted(p["id"] for p in combo_players))
    raw_values = [_player_value(p) for p in combo_players]
    ranks = [p["trade_rank"] for p in combo_players if p.get("trade_rank")]
    rec = {
        "ids": ids,
        "size": len(combo_players),
        "power_sum": sum(v ** POWER for v in raw_values),
        "raw_sum": sum(raw_values),
        "max_value": max(raw_values),
        "min_rank": min(ranks) if ranks else None,
        "pos_counts": Counter(p["position"] for p in combo_players),
    }
    if current_starter_ids is not None:
        rec["all_bench"] = not any(p["id"] in current_starter_ids for p in combo_players)
    return rec


def _precompute_combos(pool, max_size, current_starter_ids=None):
    records = []
    for size in range(1, max_size + 1):
        if size > len(pool):
            break
        for combo in itertools.combinations(pool, size):
            records.append(_combo_record(combo, current_starter_ids))
    return records


def _combos_anchored(anchor, companions, max_size):
    """Gezielte Nachsuche: Kombinationen, die IMMER `anchor` enthalten, aus
    `anchor` + 0..(max_size-1) Begleitspielern aus `companions`. Linear im
    Aufwand statt kombinatorisch, weil der Anker feststeht."""
    records = []
    for n_companions in range(0, max_size):
        if n_companions > len(companions):
            break
        for extra in itertools.combinations(companions, n_companions):
            combo = [anchor] + list(extra)
            records.append(_combo_record(combo))
    return records


# ---------------------------------------------------------------------------
# Wert-Regeln (Teil 4) - billige Vorprüfung vor jeder teuren Lineup-Prüfung
# ---------------------------------------------------------------------------

def _value_check(give_rec, get_rec, max_qb, max_te, tolerance=TOLERANCE_MAX):
    denom = max(give_rec["power_sum"], get_rec["power_sum"], 1)
    diff_pct = (get_rec["power_sum"] - give_rec["power_sum"]) / denom
    if diff_pct > GAIN_CAP + 1e-9:
        return None
    if diff_pct < -tolerance - 1e-9:
        return None
    if get_rec["max_value"] > give_rec["max_value"] * SUPERSTAR_CAP + 1e-9:
        return None
    if give_rec.get("all_bench") and get_rec["min_rank"] is not None and get_rec["min_rank"] <= TOP30_RANK:
        return None
    if get_rec["pos_counts"].get("QB", 0) > max_qb:
        return None
    if get_rec["pos_counts"].get("TE", 0) > max_te:
        return None
    return round(diff_pct * 100, 1)


# ---------------------------------------------------------------------------
# Sinn-Regeln (Teil 5) - teure Prüfung, nur für Kandidaten, die die
# Wert-Vorprüfung schon bestanden haben
# ---------------------------------------------------------------------------

def _lineup_legality(player_ids, players, rules):
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

    remaining_flex_eligible = sum(max(0, counts.get(pos, 0) - starter_counts.get(pos, 0)) for pos in flex_positions)
    if remaining_flex_eligible < n_flex:
        return False, "nicht genug FLEX-fähige Spieler übrig"

    for pos in SKILL_POSITIONS:
        required_depth = starter_counts.get(pos, 0) + MIN_BENCH_DEPTH
        if counts.get(pos, 0) < required_depth:
            return False, f"zu dünne Tiefe auf {pos}"

    return True, None


def _must_drop_info(ids, total_roster_slots, players, waiver_by_position):
    overflow = len(ids) - total_roster_slots
    if overflow <= 0:
        return False, [], True
    droppable = sorted(ids, key=lambda pid: (players.get(pid) or {}).get("trade_value") or 0)
    drop_ids = droppable[:overflow]
    can_fill = all(bool(waiver_by_position.get((players.get(pid) or {}).get("position"))) for pid in drop_ids)
    return True, drop_ids, can_fill


def _qb_te_must_start(get_ids, starter_ids, players):
    for pid in get_ids:
        p = players.get(pid)
        if p and p["position"] in ("QB", "TE") and pid not in starter_ids:
            return False
    return True


def _named_purpose(p, starter_ids, my_starters_by_pos, bye_calendar_weeks):
    if p["id"] in starter_ids:
        return None
    starters_here = my_starters_by_pos.get(p["position"], [])
    if any(s.get("injury_status") in HARD_OUT_STATUSES for s in starters_here):
        return "Verletzungs-Ersatz"
    for s in starters_here:
        s_bye = s.get("bye_week")
        if s_bye and s_bye in bye_calendar_weeks and p.get("bye_week") != s_bye:
            return "Bye-Absicherung vor Playoffs"
    return "Flex-Tiefe"


def _package_label(give_size, get_size):
    if give_size > get_size:
        return "Spitze verbessern"
    if give_size < get_size:
        return "Breite aufbauen"
    return "Gleichwertiger Tausch"


# ---------------------------------------------------------------------------
# Annahme-Wahrscheinlichkeit (vorzeichenrichtig aus Partnersicht)
# ---------------------------------------------------------------------------

def _acceptance_label(give_value, get_value, their_lineup_delta, their_need_fit, partner_type, boost=False):
    """give_value = was ICH abgebe (= Partner empfängt), get_value = was ich
    bekomme (= Partner abgibt). partner_loss_pct > 0 heißt: Partner gibt
    mehr ab, als er bekommt. `boost`: z.B. bei Bye-Woche-Ausnutzung darf die
    Annahme höher ausfallen, wenn der Partner kurzfristig einen Ersatz
    braucht - die Wert-Obergrenze (max. 10% Verlust, siehe GAIN_CAP) gilt
    trotzdem immer."""
    denom = max(give_value, get_value, 1)
    partner_loss_pct = (get_value - give_value) / denom
    if partner_loss_pct > 0.15:
        return "niedrig"
    if partner_loss_pct > 0.05:
        return "mittel" if not boost else "hoch"
    if their_need_fit >= 2 or their_lineup_delta > 0 or partner_type == "buyer" or boost:
        return "hoch"
    if partner_type == "seller" and their_lineup_delta <= 0 and their_need_fit <= 0:
        return "mittel"
    return "hoch"


def _partner_type(their_rank, num_teams, playoff_teams, scouting):
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


def _need_fit(combo_ids, players, weakness_for_team):
    return round(sum(weakness_for_team.get((players.get(pid) or {}).get("position"), 0) for pid in combo_ids), 2)


def _partner_accept_reasons(their_need_fit, their_lineup_delta, partner_type, acceptance, boost_reason=None):
    reasons = []
    if boost_reason:
        reasons.append(boost_reason)
    if their_lineup_delta > 0:
        reasons.append(f"Verbessert sein eigenes Lineup um {their_lineup_delta} Pkt./Woche")
    if their_need_fit > 0:
        reasons.append("Trifft einen Bedarf seines Teams")
    if partner_type == "buyer":
        reasons.append("Team im Playoff-Rennen - eher bereit, für sofortige Verbesserung zu handeln")
    elif partner_type == "seller":
        reasons.append("Team ohne Playoff-Chance - eher bereit, etablierte Spieler für Perspektive abzugeben")
    if acceptance == "niedrig":
        reasons.append("Partner gibt wertmäßig deutlich mehr ab, als er bekommt - Annahme unwahrscheinlich")
    return reasons or ["Kein eindeutiger Grund erkennbar - Annahme unsicher"]


def _league_rules_note(rules, is_dynasty, num_teams):
    league_type_label = "Dynasty" if is_dynasty else "Keeper" if rules.get("is_keeper_or_dynasty") else "Redraft"
    qb_label = "SUPER_FLEX" if rules.get("super_flex") else f"{rules.get('num_qb_starters', 1)} Start-QB"
    return (
        f"Liga-Regeln berücksichtigt: {league_type_label}, {qb_label}, {num_teams} Teams. "
        "Paketwerte werden als Potenz-Summe (Wert^1.5) verglichen, damit mehrere Mittelklasse-Spieler "
        "keinen Star aufwiegen. K/DEF sind nie Teil eines Trades, Roster-Pflicht-Slots und Mindesttiefe "
        "bleiben erhalten - sonst wird das Paket verworfen."
    )


def _injury_note(p):
    status = p.get("injury_status")
    if not status:
        return None
    label = STATUS_LABELS_DE.get(status, status)
    body = f" ({p['injury_body_part']})" if p.get("injury_body_part") else ""
    if p.get("practice_description"):
        practice = f" · Training: {p['practice_description']}"
    else:
        practice = " · Trainingsstatus unbekannt"
    return_note = " · Rückkehrtermin unbekannt (keine strukturierte Angabe in den Daten)"
    return f"{label}{body}{practice}{return_note}"


# ---------------------------------------------------------------------------
# Lineup-Lücken durch Bye/Verletzung (Datengrundlage für Bye-Weeks,
# Notlage-des-Partners und Playoff-Vorbereitung) - rein aus echten Feldern
# (bye_week, injury_status) und der aktuellen Roster-Zusammensetzung,
# nichts wird für künftige Wochen vorhergesagt oder erfunden.
# ---------------------------------------------------------------------------

def _team_lineup_gaps(roster_ids, starter_ids, players, current_week, weeks_ahead=4):
    weeks = list(range(current_week, current_week + weeks_ahead))
    by_pos_roster = {}
    for pid in roster_ids:
        p = players.get(pid)
        if p:
            by_pos_roster.setdefault(p["position"], []).append(p)
    gaps = []
    for w in weeks:
        for pid in starter_ids:
            p = players.get(pid)
            if not p:
                continue
            is_bye = p.get("bye_week") == w
            is_injured = w == current_week and p.get("injury_status") in HARD_OUT_STATUSES
            if not (is_bye or is_injured):
                continue
            same_pos = by_pos_roster.get(p["position"], [])
            replacement = next(
                (r for r in same_pos if r["id"] != pid and r.get("bye_week") != w
                 and not (w == current_week and r.get("injury_status") in HARD_OUT_STATUSES)),
                None,
            )
            if replacement is None:
                gaps.append({
                    "week": w, "position": p["position"], "player_id": pid, "player_name": p.get("name"),
                    "cause": "bye" if is_bye else "injury",
                    "magnitude": round(p.get("season_avg") or 0, 1),
                })
    return gaps


def _playoff_prep_flags(starter_ids, players, team_schedules, defense_ranks, playoff_weeks):
    flags = []
    for pid in starter_ids:
        p = players.get(pid)
        if not p or p["position"] not in SKILL_POSITIONS + ("QB",):
            continue
        if p.get("bye_week") in (13, 14):
            flags.append({
                "player_id": pid, "position": p["position"], "reason": "bye",
                "detail": f"Bye in Woche {p['bye_week']} (während der Playoffs)",
            })
            continue
        team = p.get("team")
        schedule = team_schedules.get(team) or []
        hard_weeks = []
        for g in schedule:
            wk = g.get("week")
            if wk not in playoff_weeks:
                continue
            opp = g.get("opponent")
            rank = (defense_ranks.get(p["position"]) or {}).get(opp)
            rank_of = len(defense_ranks.get(p["position"]) or {}) or 32
            if rank is not None and rank <= max(10, round(rank_of / 3)):
                hard_weeks.append((wk, opp, rank, rank_of))
        if len(hard_weeks) >= 2:
            detail = "; ".join(f"Woche {wk} gegen {opp} (Rang {rank}/{of} gegen {p['position']})" for wk, opp, rank, of in hard_weeks)
            flags.append({"player_id": pid, "position": p["position"], "reason": "matchups", "detail": detail, "hard_weeks": hard_weeks})
    return flags


# ---------------------------------------------------------------------------
# Teure Kandidaten-Prüfung (nur für Wert-Vorprüfung-Überlebende)
# ---------------------------------------------------------------------------

def _evaluate_candidate(give_ids, get_ids, ctx, diff_pct_value):
    players = ctx["players"]
    give_combo = [players[i] for i in give_ids]
    get_combo = [players[i] for i in get_ids]

    my_after_ids = [pid for pid in ctx["my_current_ids"] if pid not in give_ids] + list(get_ids)
    their_after_ids = [pid for pid in ctx["their_keep_ids"] if pid not in get_ids] + list(give_ids)

    my_starters_after, my_by_pos_after, my_after_points = _week_lineup_analysis(
        my_after_ids, players, ctx["roster_positions"], ctx["flex_positions"], ctx["current_week"], ctx["current_week"],
    )
    if not _qb_te_must_start(get_ids, my_starters_after, players):
        return None

    legal, _ = _lineup_legality(my_after_ids, players, ctx["rules"])
    must_drop_mine, drop_ids_mine, can_fill_mine = _must_drop_info(
        my_after_ids, ctx["total_roster_slots"], players, ctx["waiver_by_position"],
    )
    if not legal and not must_drop_mine:
        return None

    their_starters_after, their_by_pos_after, their_after_points = _week_lineup_analysis(
        their_after_ids, players, ctx["roster_positions"], ctx["flex_positions"], ctx["current_week"], ctx["current_week"],
    )
    their_legal, _ = _lineup_legality(their_after_ids, players, ctx["rules"])
    must_drop_theirs, drop_ids_theirs, can_fill_theirs = _must_drop_info(
        their_after_ids, ctx["total_roster_slots"], players, ctx["waiver_by_position"],
    )
    if not their_legal and not must_drop_theirs:
        return None

    my_delta = round(my_after_points - ctx["my_baseline_points"], 2)
    their_delta = round(their_after_points - ctx["their_baseline_points"], 2)

    their_need_fit = _need_fit(give_ids, players, ctx["their_weakness"])
    # Der Partner muss etwas davon haben: Lineup-Gewinn oder Bedarf auf der
    # Position - sonst ist das Paket für ihn unrealistisch, egal wie fair
    # der Marktwert aussieht.
    if not (their_delta > 0 or their_need_fit > 0):
        return None

    give_value = sum(_player_value(p) for p in give_combo)
    get_value = sum(_player_value(p) for p in get_combo)
    my_need_fit = _need_fit(get_ids, players, ctx["my_weakness"])
    partner_type = ctx["partner_type"]
    acceptance = _acceptance_label(give_value, get_value, their_delta, their_need_fit, partner_type)

    purpose_notes = []
    for p in get_combo:
        note = _named_purpose(p, my_starters_after, ctx["my_starters_by_pos"], ctx["bye_calendar_weeks"])
        if note:
            purpose_notes.append(f"{p.get('name')}: {note}")

    has_injured = any(p.get("injury_status") in HARD_OUT_STATUSES for p in give_combo + get_combo)
    injured_detail = [
        {"player_id": p["id"], "name": p.get("name"), "status": p.get("injury_status"), "note": _injury_note(p)}
        for p in give_combo + get_combo if p.get("injury_status") in HARD_OUT_STATUSES
    ]

    bench_before = _bench_snapshot(ctx["my_current_ids"], players, ctx["my_starter_ids"])
    bench_after = _bench_snapshot(my_after_ids, players, my_starters_after)

    is_rival = False
    pr = ctx["playoff_results"].get(ctx["roster_id"])
    if pr is not None and ctx["playoff_teams"]:
        prob = pr.get("playoff_probability", 0)
        is_rival = 15 <= prob <= 95 and abs((pr.get("projected_rank") or 99) - ctx["playoff_teams"]) <= 2.5

    return {
        "roster_id": ctx["roster_id"], "team_name": ctx["team_name"],
        "give_player_ids": sorted(give_ids), "get_player_ids": sorted(get_ids),
        "give_value": round(give_value), "get_value": round(get_value),
        "value_diff_pct": diff_pct_value,
        "lineup_points_before": ctx["my_baseline_points"], "lineup_points_after": my_after_points, "lineup_delta": my_delta,
        "their_lineup_points_before": ctx["their_baseline_points"], "their_lineup_points_after": their_after_points,
        "their_lineup_delta": their_delta,
        "is_win_win": my_delta > 0 and their_delta > 0,
        "bench_before": bench_before, "bench_after": bench_after,
        "acceptance": acceptance, "partner_type": partner_type,
        "label": _package_label(len(give_ids), len(get_ids)),
        "format": f"{len(give_ids)}-{len(get_ids)}",
        "purpose_notes": purpose_notes,
        "roster_legal_for_me": legal, "must_drop_players": must_drop_mine,
        "my_drop_candidate_ids": drop_ids_mine, "can_fill_via_waiver_mine": can_fill_mine,
        "their_roster_legal": their_legal, "their_must_drop_players": must_drop_theirs,
        "their_drop_candidate_ids": drop_ids_theirs, "can_fill_via_waiver_theirs": can_fill_theirs,
        "has_injured_player": has_injured, "injured_players_detail": injured_detail,
        "my_need_fit": my_need_fit, "their_need_fit": their_need_fit,
        "their_record": ctx["their_record"], "their_waiver_moves": ctx["their_waiver_moves"], "their_trades": ctx["their_trades"],
        "is_current_week_opponent": ctx["roster_id"] == ctx["current_opponent_roster_id"],
        "is_playoff_rival": is_rival,
        "partner_accept_reasons": _partner_accept_reasons(their_need_fit, their_delta, partner_type, acceptance),
    }


def _score(c):
    rival_penalty = 0.5 * max(c["their_lineup_delta"], 0) if c["is_playoff_rival"] else 0
    return c["lineup_delta"] - rival_penalty


def _combo_key(c):
    return (c["roster_id"], tuple(c["give_player_ids"]), tuple(c["get_player_ids"]))


def _with_breakdown(c, ctx_common):
    if "value_breakdown" in c:
        return c
    players = ctx_common["players"]
    give_ids = set(c["give_player_ids"])
    get_ids = set(c["get_player_ids"])
    my_after_ids = [pid for pid in ctx_common["my_current_ids"] if pid not in give_ids] + list(get_ids)
    breakdown = _value_breakdown(
        ctx_common["my_current_ids"], my_after_ids, players, ctx_common["roster_positions"], ctx_common["flex_positions"],
        ctx_common["current_week"], ctx_common["deadline_weeks"], ctx_common["playoff_weeks"],
    )
    c["value_breakdown"] = breakdown
    c["value_delta_until_deadline"] = breakdown["until_deadline_total"]
    c["value_delta_playoffs"] = breakdown["playoffs_total"]
    return c


# ---------------------------------------------------------------------------
# Hauptfunktion
# ---------------------------------------------------------------------------

def compute(data, rules, bye_weeks_by_team):
    start_time = time.monotonic()
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
    trade_deadline = data["league"].get("trade_deadline") or current_week
    total_roster_slots = rules.get("total_roster_slots") or (len(roster_positions) + (rules.get("reserve_slots") or 0))
    current_opponent_roster_id = ((data.get("matchup") or {}).get("opponent") or {}).get("roster_id")
    playoff_results = {r["roster_id"]: r for r in ((data.get("playoffs") or {}).get("results") or [])}
    waiver_by_position_all = (data.get("waiver") or {}).get("by_position") or {}
    team_schedules = data.get("team_schedules") or {}
    defense_ranks = data.get("defense_position_ranks") or {}
    max_qb = max(1, rules.get("num_qb_starters") or 1)
    max_te = max(1, rules.get("starter_counts", {}).get("TE", 1) or 1)

    weakness = weakness_matrix(teams, players)
    my_weakness = weakness.get(my_roster_id, {})
    scouting_by_roster = {p["roster_id"]: p for p in (data.get("league_feed") or {}).get("scouting_profiles", [])}

    my_current_ids = [s["player_id"] for s in data["my_roster"]["slots"]] + data["my_roster"]["bench"]
    my_starter_ids, my_starters_by_pos_full, my_baseline_points = _week_lineup_analysis(
        my_current_ids, players, roster_positions, flex_positions, current_week, current_week,
    )
    my_starters_by_pos = {}
    for s in data["my_roster"]["slots"]:
        p = players.get(s["player_id"])
        if p:
            my_starters_by_pos.setdefault(p["position"], []).append(p)

    bye_calendar_weeks = set()
    if playoff_week_start:
        window_start = playoff_week_start - NEAR_PLAYOFF_WINDOW
        bye_calendar_weeks = set(range(window_start, playoff_week_start))
    deadline_weeks = list(range(current_week, trade_deadline + 1))
    playoff_weeks = list(range(playoff_week_start, min((playoff_week_start or 14) + 4, 19))) if playoff_week_start else []

    my_full_pool = _tradeable_pool(my_team, players)
    my_full_ids = [p["id"] for p in my_full_pool]
    my_pool_capped = my_full_pool[:POOL_CAP]
    my_combos_capped = _precompute_combos(my_pool_capped, GIVE_MAX_SIDE, my_starter_ids)

    ctx_common = {
        "players": players, "roster_positions": roster_positions, "flex_positions": flex_positions,
        "current_week": current_week, "deadline_weeks": deadline_weeks, "playoff_weeks": playoff_weeks,
        "my_current_ids": my_current_ids,
    }

    all_candidates = []
    team_data = {}
    pool_cap_current = POOL_CAP
    perf = {"value_checks": 0, "expensive_evals": 0}

    teams_to_process = [t for t in teams if t["roster_id"] != my_roster_id]
    for idx, team in enumerate(teams_to_process):
        elapsed = time.monotonic() - start_time
        remaining_teams = len(teams_to_process) - idx
        if elapsed > PERFORMANCE_BUDGET_SECONDS * 0.6 and remaining_teams > 3 and pool_cap_current > 6:
            pool_cap_current = max(6, pool_cap_current - 2)

        their_full_pool = _tradeable_pool(team, players)
        their_full_ids = [p["id"] for p in their_full_pool]
        if not their_full_ids:
            continue
        their_pool_capped = their_full_pool[:pool_cap_current]
        their_combos_capped = _precompute_combos(their_pool_capped, GET_MAX_SIDE)

        their_weakness = weakness.get(team["roster_id"], {})
        their_rank = team.get("rank") or (num_teams or 14)
        scouting = scouting_by_roster.get(team["roster_id"])
        partner_type = _partner_type(their_rank, num_teams, playoff_teams, scouting)
        their_keep_ids = team["players"]
        _ts0, _tbp0, their_baseline_points = _week_lineup_analysis(
            their_keep_ids, players, roster_positions, flex_positions, current_week, current_week,
        )

        ctx = dict(ctx_common)
        ctx.update({
            "rules": rules, "bye_calendar_weeks": bye_calendar_weeks,
            "their_keep_ids": their_keep_ids, "my_baseline_points": my_baseline_points,
            "their_baseline_points": their_baseline_points, "total_roster_slots": total_roster_slots,
            "waiver_by_position": waiver_by_position_all, "my_weakness": my_weakness, "their_weakness": their_weakness,
            "my_starter_ids": my_starter_ids, "my_starters_by_pos": my_starters_by_pos,
            "roster_id": team["roster_id"], "team_name": team["team_name"], "partner_type": partner_type,
            "their_record": f"{team.get('wins', 0)}-{team.get('losses', 0)}",
            "their_waiver_moves": scouting["waiver_moves"] if scouting else None,
            "their_trades": scouting["trades"] if scouting else None,
            "current_opponent_roster_id": current_opponent_roster_id,
            "playoff_results": playoff_results, "playoff_teams": playoff_teams,
        })
        team_data[team["roster_id"]] = {
            "ctx": ctx, "their_full_pool": their_full_pool, "their_full_ids": their_full_ids,
            "their_pool_capped": their_pool_capped, "their_combos_capped": their_combos_capped,
        }

        for give_rec in my_combos_capped:
            for get_rec in their_combos_capped:
                perf["value_checks"] += 1
                diff_pct = _value_check(give_rec, get_rec, max_qb, max_te, tolerance=TOLERANCE_MAX)
                if diff_pct is None:
                    continue
                perf["expensive_evals"] += 1
                cand = _evaluate_candidate(set(give_rec["ids"]), set(get_rec["ids"]), ctx, diff_pct)
                if cand:
                    all_candidates.append(cand)

    search_seconds = round(time.monotonic() - start_time, 2)
    performance_note = None
    if search_seconds > PERFORMANCE_BUDGET_SECONDS:
        performance_note = (
            f"Die Paket-Suche hat {search_seconds}s gedauert und wurde für die letzten Teams auf die "
            f"{pool_cap_current} wertvollsten Spieler je Team begrenzt. Alle Wert- und Sinn-Regeln blieben "
            "dabei unverändert in Kraft."
        )

    # ---- Indizes je Spieler x Format -----------------------------------------
    block_index = {}
    target_index = {}
    by_roster_id = {}
    for c in all_candidates:
        by_roster_id.setdefault(c["roster_id"], []).append(c)
        for pid in c["give_player_ids"]:
            block_index.setdefault(pid, {}).setdefault(c["format"], []).append(c)
        for pid in c["get_player_ids"]:
            target_index.setdefault(pid, {}).setdefault(c["format"], []).append(c)

    owner_of_map = {}
    team_by_id = {t["roster_id"]: t for t in teams}
    for t in teams:
        if t["roster_id"] == my_roster_id:
            continue
        for pid in t["players"]:
            owner_of_map[pid] = t["roster_id"]

    def _dedupe_sorted(lst):
        seen = set()
        out = []
        for c in sorted(lst, key=_score, reverse=True):
            key = _combo_key(c)
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
        return out

    def _coverage(by_format):
        total = sum(len(v) for v in by_format.values())
        return total, len(by_format)

    def _explain_no_package(any_value_fair):
        """Wenn auch die Nachsuche nichts findet, kurz erklären warum, statt
        kommentarlos leer zu bleiben (Teil 4: 'nur wenn auch das nichts
        ergibt, kurz erklären, warum')."""
        if not any_value_fair:
            return (
                f"Kein Angebot erreicht die Wert-Toleranz (max. {TOLERANCE_MAX*100:.0f}% zu meinen Lasten, "
                f"max. {GAIN_CAP*100:.0f}% zu meinen Gunsten) oder verletzt die Superstar-Regel "
                f"(höchstens das {SUPERSTAR_CAP}-Fache meines wertvollsten Gegenstücks)."
            )
        return (
            "Wertfaire Pakete existieren, verletzen aber Roster-Regeln (Pflicht-Slot, Start-QB/TE, "
            "Roster-Limit) oder bringen dem Partner keinen Lineup-Gewinn bzw. Bedarf."
        )

    def _topup_give(pid, companions_pool, by_format):
        """Gezielte Nachsuche: `pid` fest auf meiner Seite, Begleitspieler aus
        `companions_pool` (mein Kader ohne pid), gegen die schon
        vorberechneten Partner-Kombinationen jedes Teams - linear im
        Aufwand, weil der Anker feststeht und die Gegenseite bereits fertig
        vorliegt."""
        anchor = players[pid]
        companions = [p for p in companions_pool if p["id"] != pid][:TOPUP_COMPANION_CAP]
        give_recs = _combos_anchored(anchor, companions, GIVE_MAX_SIDE)
        any_value_fair = False
        for rid, td in team_data.items():
            for give_rec in give_recs:
                for get_rec in td["their_combos_capped"]:
                    diff_pct = _value_check(give_rec, get_rec, max_qb, max_te, tolerance=TOLERANCE_MAX)
                    if diff_pct is None:
                        continue
                    any_value_fair = True
                    cand = _evaluate_candidate(set(give_rec["ids"]), set(get_rec["ids"]), td["ctx"], diff_pct)
                    if cand:
                        by_format.setdefault(cand["format"], []).append(cand)
        if not by_format:
            return _explain_no_package(any_value_fair)
        return None

    def _topup_target(pid, by_format):
        """Gezielte Nachsuche: `pid` (ein gegnerischer Spieler) fest auf der
        Gegenseite, Begleitspieler aus demselben Team, gegen meine schon
        vorberechneten Kombinationen."""
        rid = owner_of_map.get(pid)
        if rid is None or rid not in team_data:
            return "Dieser Spieler gehört keinem handelbaren Gegner-Team an."
        td = team_data[rid]
        anchor = players.get(pid)
        if not anchor:
            return "Spielerdaten unvollständig."
        companions = [p for p in td["their_full_pool"] if p["id"] != pid][:TOPUP_COMPANION_CAP]
        get_recs = _combos_anchored(anchor, companions, GET_MAX_SIDE)
        any_value_fair = False
        for give_rec in my_combos_capped:
            for get_rec in get_recs:
                diff_pct = _value_check(give_rec, get_rec, max_qb, max_te, tolerance=TOLERANCE_MAX)
                if diff_pct is None:
                    continue
                any_value_fair = True
                cand = _evaluate_candidate(set(give_rec["ids"]), set(get_rec["ids"]), td["ctx"], diff_pct)
                if cand:
                    by_format.setdefault(cand["format"], []).append(cand)
        if not by_format:
            return _explain_no_package(any_value_fair)
        return None

    default_format_keys = {f"{g}-{s}" for g, s in DEFAULT_FORMATS}

    def _finalize_player_index(by_format):
        """Begrenzt je Format auf die besten paar Pakete (Standardformate
        etwas großzügiger als die selteneren Zusatzformate) und hält die
        volle Woche-für-Woche-Aufschlüsselung nur für das insgesamt beste
        Paket vor - alle anderen bekommen nur die Summenwerte (bis
        Deadline/Playoffs/diese Woche), um die Datei nicht mit redundanten
        Wochenlisten aufzublähen."""
        trimmed = {
            fmt: [
                _with_breakdown(c, ctx_common)
                for c in _dedupe_sorted(lst)[:(MAX_PACKAGES_PER_FORMAT if fmt in default_format_keys else EXTRA_FORMAT_CAP)]
            ]
            for fmt, lst in by_format.items() if lst
        }
        all_items = [c for lst in trimmed.values() for c in lst]
        if not all_items:
            return trimmed
        best_key = _combo_key(max(all_items, key=_score))
        for c in all_items:
            if _combo_key(c) != best_key:
                c["value_breakdown"] = {k: v for k, v in c["value_breakdown"].items() if k != "weeks"}
        return trimmed

    block_candidates = {}
    for pid in my_full_ids:
        by_format = {fmt: list(lst) for fmt, lst in block_index.get(pid, {}).items()}
        total, n_formats = _coverage(by_format)
        empty_reason = None
        if total < MIN_PACKAGES_PER_PLAYER or n_formats < MIN_FORMATS_PER_PLAYER:
            empty_reason = _topup_give(pid, my_full_pool, by_format)
        block_candidates[pid] = {"by_format": _finalize_player_index(by_format), "empty_reason": empty_reason}

    opponent_tradeable_ids = [
        pid for pid, rid in owner_of_map.items() if rid in team_data
        and players.get(pid, {}).get("position") in TRADE_POSITIONS
        and (players.get(pid, {}).get("trade_value") or 0) >= TARGET_MIN_TRADE_VALUE
    ]
    target_candidates = {}
    for pid in opponent_tradeable_ids:
        by_format = {fmt: list(lst) for fmt, lst in target_index.get(pid, {}).items()}
        total, n_formats = _coverage(by_format)
        empty_reason = None
        if total < MIN_PACKAGES_PER_PLAYER or n_formats < MIN_FORMATS_PER_PLAYER:
            empty_reason = _topup_target(pid, by_format)
        target_candidates[pid] = {"by_format": _finalize_player_index(by_format), "empty_reason": empty_reason}

    # ---- Trade-Ideen ----------------------------------------------------------
    def _best_overall(predicate, idea_label, anlass_fn, limit=IDEA_LIMIT):
        cands = [c for c in all_candidates if predicate(c)]
        out = []
        seen = set()
        for c in sorted(cands, key=_score, reverse=True):
            key = _combo_key(c)
            if key in seen:
                continue
            seen.add(key)
            item = _with_breakdown(dict(c), ctx_common)
            item["idea_label"] = idea_label
            item["anlass"] = anlass_fn(item)
            out.append(item)
            if len(out) >= limit:
                break
        return out

    def _idea_result(items, reason_if_none):
        """Mindestens 3 Ideen je Kategorie, sonst eine kurze Erklärung, warum
        nicht (Teil 3/8) - auch wenn ein paar, aber weniger als 3 gefunden
        wurden, statt nur beim kompletten Leerlauf."""
        if not items:
            return {"items": items, "empty_reason": reason_if_none}
        if len(items) < 3:
            return {
                "items": items,
                "empty_reason": (
                    f"Nur {len(items)} von mindestens 3 gewünschten Ideen gefunden - "
                    f"die Datenlage (Kader, Verletzungen, Bye-Wochen) gibt aktuell nicht mehr her."
                ),
            }
        return {"items": items, "empty_reason": None}

    ideas = {}

    def _spitze_anlass(c):
        return (
            f"{len(c['give_player_ids'])} Spieler für {len(c['get_player_ids'])}: "
            f"+{c['lineup_delta']} Pkt./Woche Lineup-Gewinn, Tiefe sinkt von {c['bench_before']['bench_value']} "
            f"auf {c['bench_after']['bench_value']} Bank-Punkte/Woche"
        )

    spitze = _best_overall(
        lambda c: c["label"] == "Spitze verbessern" and c["lineup_delta"] > 0,
        "Spitze verbessern", _spitze_anlass,
    )
    ideas["spitze_verbessern"] = _idea_result(spitze, "Keine Konsolidierungs-Pakete mit Lineup-Gewinn gefunden.")

    def _breite_anlass(c):
        bench_gain = round(c["bench_after"]["bench_value"] - c["bench_before"]["bench_value"], 1)
        return (
            f"{len(c['give_player_ids'])} Spieler für {len(c['get_player_ids'])}: "
            f"Bank-Tiefe {'+' if bench_gain >= 0 else ''}{bench_gain} Pkt./Woche, "
            f"Lineup {'+' if c['lineup_delta'] >= 0 else ''}{c['lineup_delta']} Pkt./Woche"
        )

    breite = _best_overall(
        lambda c: c["label"] == "Breite aufbauen" and (c["lineup_delta"] > 0 or c["bench_after"]["bench_value"] > c["bench_before"]["bench_value"]),
        "Breite aufbauen", _breite_anlass,
    )
    ideas["breite_aufbauen"] = _idea_result(breite, "Keine Aufteilungs-Pakete mit Tiefe- oder Lineup-Gewinn gefunden.")

    sell_buy = data.get("sell_buy") or {"sell_high": [], "buy_low": []}
    sell_high_ids = {e["player_id"] for e in sell_buy.get("sell_high", []) if e.get("is_mine")}
    sell_high_items = []
    for pid in sell_high_ids:
        matches = [c for c in block_index.get(pid, {}).values() for c in c]
        if not matches:
            continue
        best = sorted(matches, key=_score, reverse=True)[0]
        entry = next((e for e in sell_buy["sell_high"] if e["player_id"] == pid), None)
        best = _with_breakdown(dict(best), ctx_common)
        best["idea_label"] = "Sell High"
        best["anlass"] = f"{players[pid]['name']}: {entry['ppo_ratio']}x Punkte pro Opportunity ggü. Positions-Schnitt ({entry['opportunity_pg']}/Spiel) - Touchdown-Glück-Risiko"
        sell_high_items.append(best)
    sell_high_items = sorted(sell_high_items, key=_score, reverse=True)[:IDEA_LIMIT]
    ideas["sell_high"] = _idea_result(sell_high_items, "Keine eigenen Sell-High-Kandidaten mit passendem Gegenangebot gefunden.")

    buy_low_items = []
    for pid, p in players.items():
        if p["position"] not in TRADE_POSITIONS:
            continue
        if p.get("fantasy_team") and p["fantasy_team"]["roster_id"] == my_roster_id:
            continue
        status = p.get("injury_status")
        if status not in SHORT_TERM_INJURY_STATUSES:
            continue
        if not p.get("trade_value") or (p.get("season_avg") or 0) < 5:
            continue
        matches = [c for lst in target_index.get(pid, {}).values() for c in lst]
        if not matches:
            continue
        best = sorted(matches, key=_score, reverse=True)[0]
        best = _with_breakdown(dict(best), ctx_common)
        best["idea_label"] = "Buy Low"
        best["risk_level"] = INJURY_RISK_LABEL.get(status, "mittel")
        best["anlass"] = f"{p['name']}: {_injury_note(p)}"
        buy_low_items.append(best)
    buy_low_items = sorted(buy_low_items, key=_score, reverse=True)[:IDEA_LIMIT]
    ideas["buy_low"] = _idea_result(buy_low_items, "Keine angeschlagenen Spieler mit kurzfristigem Status und hohem Restwert gefunden.")

    # Lücken je Team (Bye + Verletzung) für Notlage/Bye-Weeks
    team_gaps = {}
    for t in teams:
        s_ids = my_starter_ids if t["roster_id"] == my_roster_id else None
        if s_ids is None:
            s_ids, _bp, _pts = _week_lineup_analysis(t["players"], players, roster_positions, flex_positions, current_week, current_week)
        team_gaps[t["roster_id"]] = _team_lineup_gaps(t["players"], s_ids, players, current_week)

    def _surplus_at_position(pos):
        return [p["id"] for p in my_full_pool if p["position"] == pos and p["id"] not in my_starter_ids]

    bye_items = []
    for pid, p in players.items():
        if p["position"] not in TRADE_POSITIONS:
            continue
        fteam = p.get("fantasy_team")
        if fteam and fteam.get("roster_id") == my_roster_id:
            continue
        if p.get("bye_week") not in (current_week, current_week + 1):
            continue
        if (p.get("season_avg") or 0) < 6 or not p.get("trade_value"):
            continue
        matches = [c for lst in target_index.get(pid, {}).values() for c in lst]
        if not matches:
            continue
        best = sorted(matches, key=_score, reverse=True)[0]
        owner_rid = owner_of_map.get(pid)
        owner_gaps = [g for g in team_gaps.get(owner_rid, []) if g["position"] == p["position"]]
        boost = bool(owner_gaps)
        best = dict(best)
        best["acceptance"] = _acceptance_label(best["give_value"], best["get_value"], best["their_lineup_delta"], best["their_need_fit"], best["partner_type"], boost=boost)
        best = _with_breakdown(best, ctx_common)
        best["idea_label"] = "Bye-Weeks ausnutzen (Kaufen)"
        best["anlass"] = f"{p['name']}: Bye in Woche {p['bye_week']}, Saison-Schnitt {p.get('season_avg')} Pkt."
        bye_items.append(best)

    for g in team_gaps.get(my_roster_id, []):
        if g["cause"] != "bye":
            continue
        surplus = _surplus_at_position(g["position"])
        for sid in surplus:
            matches = [c for lst in block_index.get(sid, {}).values() for c in lst]
            if not matches:
                continue
            best = sorted(matches, key=_score, reverse=True)[0]
            best = _with_breakdown(dict(best), ctx_common)
            best["idea_label"] = "Bye-Weeks ausnutzen (Anbieten)"
            best["anlass"] = f"Dein {g['position']}-Loch in Woche {g['week']} ({g['player_name']} Bye) durch Überschuss abgedeckt"
            bye_items.append(best)
            break
    for rid, gaps in team_gaps.items():
        if rid == my_roster_id:
            continue
        for g in gaps:
            if g["cause"] != "bye":
                continue
            surplus = _surplus_at_position(g["position"])
            for sid in surplus:
                matches = [c for c in block_index.get(sid, {}).get("1-1", []) + block_index.get(sid, {}).get("1-2", []) if c["roster_id"] == rid]
                if not matches:
                    continue
                best = _with_breakdown(dict(sorted(matches, key=_score, reverse=True)[0]), ctx_common)
                best["idea_label"] = "Bye-Weeks ausnutzen (Anbieten)"
                best["anlass"] = f"{best['team_name']} hat Bye-Lücke auf {g['position']} in Woche {g['week']} ({g['player_name']})"
                bye_items.append(best)
                break
    bye_items = sorted(_dedupe_sorted(bye_items), key=_score, reverse=True)[:IDEA_LIMIT]
    ideas["bye_weeks"] = _idea_result(bye_items, "Keine Bye-Wochen-Gelegenheit in den nächsten Wochen gefunden.")

    partner_notlage_items = []
    for rid, gaps in team_gaps.items():
        if rid == my_roster_id:
            continue
        for g in gaps:
            surplus = _surplus_at_position(g["position"])
            for sid in surplus:
                matches = [c for c in block_index.get(sid, {}).get("1-1", []) + block_index.get(sid, {}).get("1-2", []) if c["roster_id"] == rid]
                if not matches:
                    continue
                best = _with_breakdown(dict(sorted(matches, key=_score, reverse=True)[0]), ctx_common)
                best["idea_label"] = "Notlage des Partners nutzen"
                cause_label = "Bye" if g["cause"] == "bye" else "Verletzt"
                best["anlass"] = f"{best['team_name']}: {g['player_name']} ({cause_label}, Woche {g['week']}) - Bedarf {g['position']}, keine Bank-Alternative berechnet"
                partner_notlage_items.append(best)
                break
    partner_notlage_items = sorted(_dedupe_sorted(partner_notlage_items), key=_score, reverse=True)[:IDEA_LIMIT]
    ideas["partner_notlage"] = _idea_result(partner_notlage_items, "Keine nachgewiesene Lineup-Lücke bei anderen Teams gefunden.")

    playoff_flags = _playoff_prep_flags(my_starter_ids, players, team_schedules, defense_ranks, playoff_weeks) if playoff_weeks else []
    playoff_items = []
    for flag in playoff_flags:
        pos = flag["position"]
        candidates_pos = [
            c for lst in target_index.values() for c in lst.get("1-1", []) + lst.get("2-1", [])
            if any(players.get(gid, {}).get("position") == pos for gid in c["get_player_ids"])
        ]
        if not candidates_pos:
            continue
        best = _with_breakdown(dict(sorted(candidates_pos, key=_score, reverse=True)[0]), ctx_common)
        best["idea_label"] = "Playoff-Vorbereitung"
        best["anlass"] = f"{players[flag['player_id']]['name']}: {flag['detail']}"
        playoff_items.append(best)
    playoff_items = sorted(_dedupe_sorted(playoff_items), key=_score, reverse=True)[:IDEA_LIMIT]
    playoff_empty_reason = (
        "Keine Playoff-Wochen in den Liga-Einstellungen gefunden." if not playoff_weeks else
        "Keine Starter mit Bye in Woche 13/14 oder zwei+ schweren Playoff-Matchups gefunden."
    )
    ideas["playoff_vorbereitung"] = _idea_result(playoff_items, playoff_empty_reason)

    team_pools = {
        str(t["roster_id"]): [
            {"player_id": p["id"], "trade_value": p.get("trade_value"), "position": p["position"], "name": p.get("name")}
            for p in _tradeable_pool(t, players)
        ]
        for t in teams
    }

    return {
        "data_as_of": data.get("generated_at"),
        "my_needs": sorted([p for p in TRADE_POSITIONS if my_weakness.get(p, 0) >= 1.5], key=lambda p: my_weakness.get(p, 0), reverse=True),
        "league_rules_note": _league_rules_note(rules, is_dynasty, num_teams),
        "formats": {"default": [f"{g}-{s}" for g, s in DEFAULT_FORMATS], "extra": [f"{g}-{s}" for g, s in EXTRA_FORMATS]},
        "value_rules": {
            "power": POWER, "gain_cap_pct": GAIN_CAP * 100, "tolerance_options_pct": [t * 100 for t in TOLERANCE_OPTIONS],
            "default_tolerance_pct": DEFAULT_TOLERANCE * 100, "superstar_cap": SUPERSTAR_CAP, "top30_rank": TOP30_RANK,
        },
        "block_candidates": {str(pid): v for pid, v in block_candidates.items()},
        "target_candidates": {str(pid): v for pid, v in target_candidates.items()},
        "ideas": ideas,
        "team_pools": team_pools,
        "performance_note": performance_note,
        "build_seconds": round(time.monotonic() - start_time, 2),
        "value_checks": perf["value_checks"],
        "expensive_evals": perf["expensive_evals"],
    }


def validate_proposals(trade_finder_data, players):
    """Build-Gate: prüft die harten Regeln über ALLE tatsächlich erzeugten
    Pakete (block_candidates, target_candidates, ideas) - nicht nur
    Stichproben. Gibt eine Liste von Fehlertexten zurück (leer = alles ok)."""
    errors = []
    seen_combos = set()

    def check(c, source):
        for pid in c["give_player_ids"] + c["get_player_ids"]:
            pos = (players.get(pid) or {}).get("position")
            if pos in ("K", "DEF"):
                errors.append(f"[{source}] Paket enthält K/DEF ({pid}, {pos}): {c['team_name']}")
        get_qb = [pid for pid in c["get_player_ids"] if (players.get(pid) or {}).get("position") == "QB"]
        get_te = [pid for pid in c["get_player_ids"] if (players.get(pid) or {}).get("position") == "TE"]
        if len(get_qb) > 1:
            errors.append(f"[{source}] mehr als 1 QB erhalten: {c['give_player_ids']}->{c['get_player_ids']}")
        if len(get_te) > 1:
            errors.append(f"[{source}] mehr als 1 TE erhalten: {c['give_player_ids']}->{c['get_player_ids']}")
        diff = c.get("value_diff_pct")
        if diff is not None and diff > GAIN_CAP * 100 + 0.5:
            errors.append(f"[{source}] Wertgewinn {diff}% überschreitet die 10%-Obergrenze: {c['give_player_ids']}->{c['get_player_ids']}")
        key = (c["roster_id"], tuple(sorted(c["give_player_ids"])), tuple(sorted(c["get_player_ids"])), source)
        if key in seen_combos:
            errors.append(f"Doppeltes Paket: {key}")
        seen_combos.add(key)

    for pid, entry in trade_finder_data.get("block_candidates", {}).items():
        for fmt, lst in entry.get("by_format", {}).items():
            for c in lst:
                check(c, f"block_candidates[{pid}][{fmt}]")

    for pid, entry in trade_finder_data.get("target_candidates", {}).items():
        for fmt, lst in entry.get("by_format", {}).items():
            for c in lst:
                check(c, f"target_candidates[{pid}][{fmt}]")

    for idea_key, idea in trade_finder_data.get("ideas", {}).items():
        for c in idea.get("items", []):
            check(c, f"ideas[{idea_key}]")
            if not c.get("anlass"):
                errors.append(f"Trade-Idee ohne Anlass: ideas[{idea_key}] {c['give_player_ids']}->{c['get_player_ids']}")

    return errors
