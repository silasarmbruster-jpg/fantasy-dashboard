"""Trade Finder v4: harte Sinn-Regeln gelten IMMER (werden nie gelockert),
alles andere ist nur Information oder ein optionaler Frontend-Filter.

Architektur:
  - Vorfilter + Beam-Search statt voller Kombinatorik: je Partner-Team werden
    kleine Pakete (bis 2 Spieler je Seite) vollständig durchprobiert, größere
    Pakete (bis zu PRACTICAL_MAX_SIDE je Seite - echte Unbegrenztheit ist
    kombinatorisch sinnlos, siehe PR-Beschreibung) werden per Beam-Search aus
    den besten kleinen Paketen heraus erweitert.
  - Jeder Kandidat durchläuft dieselben harten Sinn-Regeln (Teil A), egal wie
    groß das Paket ist oder wie "fair" der Marktwert aussieht.
  - "Diese Woche", "Bis Deadline" und "Playoffs" kommen aus derselben
    Wochen-für-Woche-Lineup-Funktion (_week_lineup_points) - keine zweite,
    abweichende Formel mehr.
  - Zusätzlich zur normalen Top-Liste wird JEDER handelbare Spieler (meiner
    und jeder gegnerische) in einen Index aufgenommen (block_player_candidates
    / target_offers), damit Trade-Block und Wunschspieler-Modus nie leer
    bleiben - mit gezielter Nachsuche für Spieler, die es nicht in die
    allgemeine Top-Liste geschafft haben.
"""

import itertools
import time

from .roster_strength import weakness_matrix
from .startsit import _best_lineup, HARD_OUT_STATUSES

TRADE_POSITIONS = ("QB", "RB", "WR", "TE")  # K/DEF sind nie Teil eines Trades
SKILL_POSITIONS = ("RB", "WR", "TE")

MIN_BENCH_DEPTH = 1
NEAR_PLAYOFF_WINDOW = 2  # Wochen vor Playoff-Start, die für Bye-Absicherung zählen
MAX_BENCH_COVER_PER_TRADE = 1  # höchstens 1 nicht-startender RB/WR mit benanntem Zweck je Trade

MY_KEY_PLAYER_COUNT = 5
PRACTICAL_MAX_SIDE = 6  # "unbegrenzt" im UI heißt: bis zu dieser Paketgröße je Seite
POOL_CAP = 11  # je Team nur die wertvollsten N Spieler fürs allgemeine Durchsuchen
BEAM_WIDTH = 12
TOPUP_OTHER_CAP = 7  # Kandidatenpool für die gezielte Nachsuche (Trade-Block/Ziel)

MAX_GIVE_PLAYER_APPEARANCES = 3  # ein eigener Spieler erscheint in höchstens 3 Top-Vorschlägen
MAX_PROPOSALS_PER_TEAM = 6
MAX_TOTAL_PROPOSALS = 120
MIN_PROPOSALS_PER_PLAYER = 5
TARGET_OFFER_TIER_COUNT = 3

PERFORMANCE_BUDGET_SECONDS = 45.0  # weicher Richtwert, kein Timeout - siehe _run_all_teams

INJURY_VALUE_DISCOUNT = {
    "Out": 0.2, "Doubtful": 0.6, "Questionable": 0.9,
    "IR": 0.05, "PUP": 0.05, "Sus": 0.1, "NA": 0.05, "COV": 0.5,
}

RELAXATION_LABELS = {
    1: "Strenge Prüfung",
    2: "Erweitert: Fairness bis 25%",
    3: "Erweitert: Fairness egal",
    4: "Erweitert: Partner nur nach Marktwert",
    5: "Erweitert: größere Pakete",
    6: "Wertgewinn statt Lineup-Gewinn",
}


# ---------------------------------------------------------------------------
# Grundbausteine: Pools, Wochen-Lineup, Bedarf
# ---------------------------------------------------------------------------

def _tradeable_pool(team, players, pool_cap=None, exclude_ids=None):
    """Nur QB/RB/WR/TE mit bekanntem Marktwert, keine Reserve/IR-Spieler, nie
    K/DEF - hartes Invariant (Regel A5), keine Heuristik."""
    exclude_ids = exclude_ids or set()
    reserve = set(team.get("reserve") or [])
    pool = [
        players[pid] for pid in team["players"]
        if pid in players and pid not in reserve and pid not in exclude_ids
        and players[pid]["position"] in TRADE_POSITIONS
        and players[pid].get("trade_value")
    ]
    pool.sort(key=lambda p: p["trade_value"], reverse=True)
    return pool[:pool_cap] if pool_cap else pool


def _need_fit(combo, weakness_for_team):
    return round(sum(weakness_for_team.get(p["position"], 0) for p in combo), 2)


def _week_player_effective(p, week, current_week):
    """Effektive Punktzahl eines Spielers für eine bestimmte Woche. Für die
    aktuelle Woche: echte Projection, Hard-Out komplett raus (wie Start/Sit).
    Für andere Wochen gibt es keine spielerspezifische Wochen-Projection in
    den Daten - bester verfügbarer Schätzwert ist der Saison-Schnitt mit
    Usage-Trend- und Verletzungs-Abschlag (gleiche Methodik wie der jeweils
    aktuelle Status, nicht erfunden). Bye Week: Spieler fällt für diese Woche
    komplett raus."""
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
    """Baut für EINE Woche das optimale Lineup aus einer Spielerliste und
    gibt (Starter-IDs, Spieler-nach-Position, Punktesumme) zurück. Einzige
    Quelle für 'diese Woche', 'Bis Deadline' und 'Playoffs' - Konsistenz wird
    dadurch erzwungen, nicht nur angestrebt."""
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
    _starters, _by_pos, points = _week_lineup_analysis(
        player_ids, players, roster_positions, flex_positions, week, current_week,
    )
    return points


def _value_breakdown(before_ids, after_ids, players, roster_positions, flex_positions,
                      current_week, deadline_weeks, playoff_weeks):
    """Wochen-für-Woche-Aufschlüsselung über alle relevanten Wochen (Deadline-
    Fenster + Playoff-Fenster), aus EINER Funktion. 'Diese Woche' ist einer
    der Deadline-Wochen-Einträge, 'Bis Deadline' und 'Playoffs' sind reine
    Summen derselben Werte - rechnerisch können sie nie widersprüchlich sein."""
    all_weeks = sorted(set(deadline_weeks) | set(playoff_weeks))
    weekly = []
    for w in all_weeks:
        before = _week_lineup_points(before_ids, players, roster_positions, flex_positions, w, current_week)
        after = _week_lineup_points(after_ids, players, roster_positions, flex_positions, w, current_week)
        weekly.append({"week": w, "before": before, "after": after, "delta": round(after - before, 2)})
    by_week = {e["week"]: e for e in weekly}
    until_deadline_total = round(sum(by_week[w]["delta"] for w in deadline_weeks if w in by_week), 2)
    playoffs_total = round(sum(by_week[w]["delta"] for w in playoff_weeks if w in by_week), 2)
    this_week_delta = by_week[current_week]["delta"] if current_week in by_week else (
        weekly[0]["delta"] if weekly else 0.0
    )
    short_term_negative_long_term_positive = this_week_delta < 0 and (until_deadline_total > 0 or playoffs_total > 0)
    return {
        "weeks": weekly,
        "until_deadline_total": until_deadline_total,
        "playoffs_total": playoffs_total,
        "this_week_delta": this_week_delta,
        "short_term_negative_long_term_positive": short_term_negative_long_term_positive,
    }


# ---------------------------------------------------------------------------
# Teil A: harte Sinn-Regeln (gelten auf jeder Stufe, werden nie gelockert)
# ---------------------------------------------------------------------------

def _lineup_legality(player_ids, players, rules):
    """A3: nach dem Trade darf kein Pflicht-Slot leer sein, Mindesttiefe je
    Skill-Position muss bleiben."""
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


def _qb_te_rule_violation(get_combo, post_trade_starter_ids, rules):
    """A1: ein Trade darf höchstens so viele QBs/TEs bringen, wie die Liga
    Start-Slots dafür hat (in dieser 1-QB-Liga also genau 1 QB, 1 TE) - UND
    jeder erhaltene QB/TE muss im optimalen Lineup nach dem Trade tatsächlich
    starten. Kein Ausnahme-Pfad, anders als bei RB/WR-Bankspielern."""
    max_qb = max(1, rules.get("num_qb_starters") or 1)
    max_te = max(1, rules.get("starter_counts", {}).get("TE", 1) or 1)
    get_qb = [p for p in get_combo if p["position"] == "QB"]
    get_te = [p for p in get_combo if p["position"] == "TE"]
    if len(get_qb) > max_qb:
        return True, f"mehr als {max_qb} QB im selben Trade erhalten"
    if len(get_te) > max_te:
        return True, f"mehr als {max_te} TE im selben Trade erhalten"
    for p in get_qb + get_te:
        if p["id"] not in post_trade_starter_ids:
            return True, f"{p['position']} {p.get('name')} würde nach dem Trade nicht starten"
    return False, None


def _bench_cover_violation(get_combo, post_trade_starter_ids, post_trade_by_pos, bye_calendar_weeks):
    """A2: jeder erhaltene Spieler muss starten ODER einen benannten Zweck
    haben (Bye-Absicherung Woche 13/14, Ersatz für verletzten Starter).
    Bench-Cover nur für RB/WR, höchstens 1 Spieler pro Trade."""
    bench_cover_used = 0
    for p in get_combo:
        if p["id"] in post_trade_starter_ids:
            continue
        if p["position"] not in ("RB", "WR"):
            return True, f"{p['position']} {p.get('name')} startet nicht und hat keinen benannten Zweck"

        starters_here = [s for s in post_trade_by_pos.get(p["position"], []) if s["id"] in post_trade_starter_ids]
        injury_purpose = any(s.get("injury_status") in HARD_OUT_STATUSES for s in starters_here)

        bye_purpose = False
        for s in starters_here:
            s_bye = s.get("bye_week")
            if not s_bye or s_bye not in bye_calendar_weeks or p.get("bye_week") == s_bye:
                continue
            other_backup = [
                b for b in post_trade_by_pos.get(p["position"], [])
                if b["id"] not in (s["id"], p["id"]) and b.get("bye_week") != s_bye
                and b.get("injury_status") not in HARD_OUT_STATUSES
            ]
            if not other_backup:
                bye_purpose = True
                break

        if not (injury_purpose or bye_purpose):
            return True, f"{p['position']} {p.get('name')} ist unbegründete Bank-Reserve"
        bench_cover_used += 1
        if bench_cover_used > MAX_BENCH_COVER_PER_TRADE:
            return True, "mehr als 1 unbegründeter Bank-Cover-Spieler im selben Trade"
    return False, None


def _must_drop_info(ids, total_roster_slots, players, waiver_by_position):
    """A4: Roster-Limit nach dem Trade. Bei Überlauf: wer müsste gedroppt
    werden (günstigste Spieler nach Marktwert zuerst), und lässt sich der
    frei werdende Slot mit einem Waiver-Pickup auf derselben Position
    füllen?"""
    overflow = len(ids) - total_roster_slots
    if overflow <= 0:
        return False, [], True
    droppable = sorted(ids, key=lambda pid: (players.get(pid) or {}).get("trade_value") or 0)
    drop_ids = droppable[:overflow]
    can_fill = all(
        bool(waiver_by_position.get((players.get(pid) or {}).get("position")))
        for pid in drop_ids
    )
    return True, drop_ids, can_fill


def _evaluate_state(give_ids, get_ids, ctx):
    """Prüft ALLE harten Sinn-Regeln (Teil A) für beide Seiten und liefert,
    falls der Trade zulässig ist, die vollständigen Metriken (aktuelle Woche)
    für Beam-Scoring und Anzeige. None = Trade verletzt eine harte Regel und
    wird nie angezeigt, egal auf welcher Lockerungsstufe."""
    players = ctx["players"]
    give_combo = [players[i] for i in give_ids]
    get_combo = [players[i] for i in get_ids]

    v1 = sum(p["trade_value"] for p in give_combo)
    v2 = sum(p["trade_value"] for p in get_combo)
    diff_pct = abs(v1 - v2) / max(v1, v2, 1)

    my_after_ids = [pid for pid in ctx["my_current_ids"] if pid not in give_ids] + list(get_ids)
    their_after_ids = [pid for pid in ctx["their_keep_ids"] if pid not in get_ids] + list(give_ids)

    my_starters, my_by_pos, my_after_points = _week_lineup_analysis(
        my_after_ids, players, ctx["roster_positions"], ctx["flex_positions"], ctx["current_week"], ctx["current_week"],
    )
    violated, _ = _qb_te_rule_violation(get_combo, my_starters, ctx["rules"])
    if violated:
        return None
    violated, _ = _bench_cover_violation(get_combo, my_starters, my_by_pos, ctx["bye_calendar_weeks"])
    if violated:
        return None

    their_starters, their_by_pos, their_after_points = _week_lineup_analysis(
        their_after_ids, players, ctx["roster_positions"], ctx["flex_positions"], ctx["current_week"], ctx["current_week"],
    )
    # A1/A2 ("muss starten oder benannten Zweck haben") gelten für das, was
    # ICH bekomme - das schützt mein Roster vor nutzlosen Spielern. Für den
    # Partner wäre dieselbe Regel unrealistisch: echte Trades enthalten fast
    # immer Füllspieler, die beim Partner nicht sofort starten. Für ihn
    # gelten weiterhin die strukturellen Regeln (kein leerer Slot, Roster-
    # Limit, siehe unten) sowie Lineup-Gewinn/Bedarf als Information.
    legal, _ = _lineup_legality(my_after_ids, players, ctx["rules"])
    must_drop_mine, drop_ids_mine, can_fill_mine = _must_drop_info(
        my_after_ids, ctx["total_roster_slots"], players, ctx["my_waiver_by_pos"],
    )
    if not legal and not must_drop_mine:
        return None

    their_legal, _ = _lineup_legality(their_after_ids, players, ctx["rules"])
    must_drop_theirs, drop_ids_theirs, can_fill_theirs = _must_drop_info(
        their_after_ids, ctx["total_roster_slots"], players, ctx["their_waiver_by_pos"],
    )
    if not their_legal and not must_drop_theirs:
        return None

    my_delta = round(my_after_points - ctx["my_baseline_points"], 2)
    their_delta = round(their_after_points - ctx["their_baseline_points"], 2)

    my_need_fit = _need_fit(get_combo, ctx["my_weakness"])
    their_need_fit = _need_fit(give_combo, ctx["their_weakness"])

    beam_score = my_delta * 2 + max(their_delta, 0) + my_need_fit * 1.5 + their_need_fit - diff_pct * 3

    return {
        "give_player_ids": sorted(give_ids),
        "get_player_ids": sorted(get_ids),
        "give_value": v1,
        "get_value": v2,
        "value_diff_pct": round(diff_pct * 100, 1),
        "value_diff_pct_signed": round((v1 - v2) / max(v1, v2, 1) * 100, 1),
        "lineup_points_before": ctx["my_baseline_points"],
        "lineup_points_after": my_after_points,
        "lineup_delta": my_delta,
        "their_lineup_points_before": ctx["their_baseline_points"],
        "their_lineup_points_after": their_after_points,
        "their_lineup_delta": their_delta,
        "is_win_win": my_delta > 0 and their_delta > 0,
        "roster_legal_for_me": legal,
        "must_drop_players": must_drop_mine,
        "my_drop_candidate_ids": drop_ids_mine,
        "can_fill_via_waiver_mine": can_fill_mine,
        "their_roster_legal": their_legal,
        "their_must_drop_players": must_drop_theirs,
        "their_drop_candidate_ids": drop_ids_theirs,
        "can_fill_via_waiver_theirs": can_fill_theirs,
        "my_need_fit": my_need_fit,
        "their_need_fit": their_need_fit,
        "_beam_score": beam_score,
    }


# ---------------------------------------------------------------------------
# Teil C.3: Annahme-Wahrscheinlichkeit (vorzeichenrichtig aus Partnersicht)
# ---------------------------------------------------------------------------

def _acceptance_label(give_value, get_value, their_lineup_delta, their_need_fit, partner_type):
    """give_value = Wert, den ICH abgebe (= der Partner EMPFÄNGT).
    get_value = Wert, den ich bekomme (= der Partner ABGIBT).
    partner_loss_pct > 0 heißt: der Partner gibt mehr Marktwert ab, als er
    bekommt - das darf NIE als 'hoch' erscheinen, egal was Need/Partnertyp
    sagen."""
    denom = max(give_value, get_value, 1)
    partner_loss_pct = (get_value - give_value) / denom

    if partner_loss_pct > 0.15:
        return "niedrig"
    if partner_loss_pct > 0.05:
        return "mittel"

    # Partner verliert höchstens 5% oder gewinnt sogar Marktwert (ich überzahle).
    if their_need_fit >= 2 or their_lineup_delta > 0 or partner_type == "buyer":
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


# ---------------------------------------------------------------------------
# Zweck-Labels (ohne mindestens eines wird ein Vorschlag nie angezeigt)
# ---------------------------------------------------------------------------

def _purpose_labels(give_combo, get_combo, their_weakness, lineup_delta,
                     my_starters_by_pos, my_roster_by_pos, bye_calendar_weeks, sell_high_ids,
                     buy_low_ids, their_need_fit, relaxation_level):
    labels = []
    give_ids = {p["id"] for p in give_combo}
    get_ids = {p["id"] for p in get_combo}

    if lineup_delta >= 1.5:
        upgraded_positions = sorted({p["position"] for p in get_combo})
        labels.append(f"Upgrade {'/'.join(upgraded_positions)}")

    for p in get_combo:
        starters_here = my_starters_by_pos.get(p["position"], [])
        if any(s.get("injury_status") in HARD_OUT_STATUSES for s in starters_here):
            labels.append("Loch füllen (Verletzungs-Ersatz)")
            break

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
    if relaxation_level >= 6:
        labels.append("Wertgewinn statt Lineup-Gewinn")

    seen = set()
    out = []
    for l in labels:
        if l not in seen:
            seen.add(l)
            out.append(l)
    return out


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


def _partner_accept_reasons(give_combo, their_need_fit, their_lineup_delta, partner_type, acceptance):
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
    if acceptance == "niedrig":
        reasons.append("Partner gibt wertmäßig deutlich mehr ab, als er bekommt - Annahme unwahrscheinlich")
    return reasons or ["Kein eindeutiger Grund erkennbar - Annahme unsicher"]


def _league_rules_note(rules, is_dynasty, num_teams):
    league_type_label = "Dynasty" if is_dynasty else "Keeper" if rules.get("is_keeper_or_dynasty") else "Redraft"
    qb_label = "SUPER_FLEX" if rules.get("super_flex") else f"{rules.get('num_qb_starters', 1)} Start-QB"
    return (
        f"Liga-Regeln berücksichtigt: {league_type_label}, {qb_label}, {num_teams} Teams. "
        "K/DEF sind nie Teil eines Trades. Jeder erhaltene QB/TE muss nach dem Trade "
        "tatsächlich starten, jeder andere erhaltene Spieler startet oder hat einen "
        "benannten Zweck (Bye-Absicherung, Verletzungs-Ersatz). Roster-Pflicht-Slots und "
        "Mindesttiefe je Skill-Position bleiben erhalten - sonst wird der Vorschlag verworfen."
    )


# ---------------------------------------------------------------------------
# Relaxation-Stufe: jeder Kandidat bekommt EINE objektive Stufe zugewiesen,
# statt sequenziell immer lockerer zu suchen. Das ist deterministisch,
# schneller (ein Suchlauf statt bis zu 6) und ergibt dasselbe Ergebnis: die
# Sinn-Regeln aus Teil A gelten für jede Stufe gleich (bereits in
# _evaluate_state durchgesetzt, nie hier gelockert).
# ---------------------------------------------------------------------------

def _relaxation_level(diff_pct_0to1, my_delta, their_delta, side_size):
    if my_delta <= 0:
        return 6
    if their_delta > 0:
        if diff_pct_0to1 <= 0.15:
            return 1
        if diff_pct_0to1 <= 0.25:
            return 2
        return 3
    if side_size >= 4:
        return 5
    return 4


# ---------------------------------------------------------------------------
# Beam-Search je Team-Paar
# ---------------------------------------------------------------------------

def _generate_team_pair_states(my_ids_pool, their_ids_pool, ctx, perf):
    """Kleine Pakete (bis 2 je Seite) vollständig, größere Pakete (bis
    PRACTICAL_MAX_SIDE) per Beam-Search aus den besten kleinen Paketen
    heraus erweitert. Gibt alle gültigen (Sinn-Regel-konformen) Zustände
    zurück, mit Rohmetriken (Marktwert, diese-Woche-Delta, Need-Fit)."""
    cache = {}

    def add_state(give_ids, get_ids):
        key = (tuple(sorted(give_ids)), tuple(sorted(get_ids)))
        if key in cache:
            return cache[key]
        perf["evals"] += 1
        m = _evaluate_state(set(give_ids), set(get_ids), ctx)
        cache[key] = m
        return m

    seeds = []
    for gsize, ssize in ((1, 1), (1, 2), (2, 1), (2, 2)):
        if gsize > len(my_ids_pool) or ssize > len(their_ids_pool):
            continue
        for g in itertools.combinations(my_ids_pool, gsize):
            for s in itertools.combinations(their_ids_pool, ssize):
                m = add_state(g, s)
                if m:
                    seeds.append(m)

    seeds.sort(key=lambda m: m["_beam_score"], reverse=True)
    beam = seeds[:BEAM_WIDTH]
    for _depth in range(PRACTICAL_MAX_SIDE - 2):
        next_beam = []
        for state in beam:
            give_ids = set(state["give_player_ids"])
            get_ids = set(state["get_player_ids"])
            if len(give_ids) < PRACTICAL_MAX_SIDE:
                for pid in my_ids_pool:
                    if pid in give_ids:
                        continue
                    m = add_state(give_ids | {pid}, get_ids)
                    if m:
                        next_beam.append(m)
            if len(get_ids) < PRACTICAL_MAX_SIDE:
                for pid in their_ids_pool:
                    if pid in get_ids:
                        continue
                    m = add_state(give_ids, get_ids | {pid})
                    if m:
                        next_beam.append(m)
        if not next_beam:
            break
        next_beam.sort(key=lambda m: m["_beam_score"], reverse=True)
        beam = next_beam[:BEAM_WIDTH]
        seeds.extend(beam)

    return [m for m in cache.values() if m]


def _topup_states_for_player(pid, side, my_ids_pool_full, their_ids_pool_full, ctx, perf, extra_cap=TOPUP_OTHER_CAP):
    """Gezielte Nachsuche für EINEN Spieler, der es nicht in den allgemeinen
    Pool (Top-POOL_CAP je Team) geschafft hat: fixiert `pid` auf der
    angegebenen Seite und probiert ihn solo sowie mit je einem der
    relevantesten anderen Spieler - linear im Aufwand, nicht kombinatorisch,
    weil pid fest steht."""
    results = []
    if side == "give":
        others = [pid2 for pid2 in my_ids_pool_full if pid2 != pid][:extra_cap]
        combos = [(pid,)] + [(pid, o) for o in others]
        their_candidates = their_ids_pool_full[:extra_cap]
        for g in combos:
            for s_size in (1, 2):
                for s in itertools.combinations(their_candidates, min(s_size, len(their_candidates))):
                    if not s:
                        continue
                    perf["evals"] += 1
                    m = _evaluate_state(set(g), set(s), ctx)
                    if m:
                        results.append(m)
    else:
        others = [pid2 for pid2 in their_ids_pool_full if pid2 != pid][:extra_cap]
        combos = [(pid,)] + [(pid, o) for o in others]
        my_candidates = my_ids_pool_full[:extra_cap]
        for s in combos:
            for g_size in (1, 2):
                for g in itertools.combinations(my_candidates, min(g_size, len(my_candidates))):
                    if not g:
                        continue
                    perf["evals"] += 1
                    m = _evaluate_state(set(g), set(s), ctx)
                    if m:
                        results.append(m)
    return results


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

    my_current_ids = [s["player_id"] for s in data["my_roster"]["slots"]] + data["my_roster"]["bench"]
    _starters0, _by_pos0, my_baseline_points = _week_lineup_analysis(
        my_current_ids, players, roster_positions, flex_positions, current_week, current_week,
    )

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

    deadline_weeks = list(range(current_week, trade_deadline + 1))
    playoff_weeks = list(range(playoff_week_start, min((playoff_week_start or 14) + 4, 19))) if playoff_week_start else []
    remaining_weeks_list = sorted({g["week"] for g in data["planner"]["remaining_schedule"]})
    remaining_weeks_estimate = min(len(remaining_weeks_list), 12) or 1

    my_full_pool = _tradeable_pool(my_team, players)
    my_full_ids = [p["id"] for p in my_full_pool]
    my_pool_ids = my_full_ids[:POOL_CAP]

    all_states = []
    team_waiver_cache = {}
    team_contexts = {}
    pool_cap_current = POOL_CAP
    perf = {"evals": 0}

    teams_to_process = [t for t in teams if t["roster_id"] != my_roster_id]
    for idx, team in enumerate(teams_to_process):
        elapsed = time.monotonic() - start_time
        remaining_teams = len(teams_to_process) - idx
        if elapsed > PERFORMANCE_BUDGET_SECONDS * 0.6 and remaining_teams > 3 and pool_cap_current > 5:
            pool_cap_current = max(5, pool_cap_current - 2)

        their_full_pool = _tradeable_pool(team, players)
        their_full_ids = [p["id"] for p in their_full_pool]
        if not their_full_ids:
            continue
        their_pool_ids = their_full_ids[:pool_cap_current]

        their_weakness = weakness.get(team["roster_id"], {})
        their_rank = team.get("rank") or (num_teams or 14)
        scouting = scouting_by_roster.get(team["roster_id"])
        partner_type = _partner_type(their_rank, num_teams, playoff_teams, scouting)
        their_keep_ids = team["players"]

        _ts0, _tbp0, their_baseline_points = _week_lineup_analysis(
            their_keep_ids, players, roster_positions, flex_positions, current_week, current_week,
        )

        their_waiver_by_pos = waiver_by_position_all

        ctx = {
            "players": players,
            "roster_positions": roster_positions,
            "flex_positions": flex_positions,
            "current_week": current_week,
            "rules": rules,
            "bye_calendar_weeks": bye_calendar_weeks,
            "my_current_ids": my_current_ids,
            "their_keep_ids": their_keep_ids,
            "my_baseline_points": my_baseline_points,
            "their_baseline_points": their_baseline_points,
            "total_roster_slots": total_roster_slots,
            "my_waiver_by_pos": waiver_by_position_all,
            "their_waiver_by_pos": their_waiver_by_pos,
            "my_weakness": my_weakness,
            "their_weakness": their_weakness,
        }
        team_contexts[team["roster_id"]] = (ctx, their_full_ids, their_pool_ids)

        states = _generate_team_pair_states(my_pool_ids[: pool_cap_current], their_pool_ids, ctx, perf)
        for st in states:
            st["roster_id"] = team["roster_id"]
            st["team_name"] = team["team_name"]
            st["partner_type"] = partner_type
            st["their_rank"] = their_rank
            st["their_record"] = f"{team.get('wins', 0)}-{team.get('losses', 0)}"
            st["their_waiver_moves"] = scouting["waiver_moves"] if scouting else None
            st["their_trades"] = scouting["trades"] if scouting else None
        all_states.extend(states)

    build_seconds_search = round(time.monotonic() - start_time, 2)
    performance_note = None
    if build_seconds_search > PERFORMANCE_BUDGET_SECONDS:
        performance_note = (
            f"Die Trade-Suche hat {build_seconds_search}s gedauert und wurde für die letzten Teams auf "
            f"die {pool_cap_current} wertvollsten Spieler je Team begrenzt, um den Build nicht unnötig zu "
            "verlangsamen. Alle Hart-Regeln blieben dabei unverändert in Kraft."
        )

    # ---- Kandidaten zu vollständigen Vorschlägen anreichern -----------------
    def finalize(st, compute_breakdown=True):
        give_combo = [players[i] for i in st["give_player_ids"]]
        get_combo = [players[i] for i in st["get_player_ids"]]
        give_ids = set(st["give_player_ids"])
        get_ids = set(st["get_player_ids"])
        diff_pct = st["value_diff_pct"] / 100.0
        side_size = max(len(give_ids), len(get_ids))
        level = _relaxation_level(diff_pct, st["lineup_delta"], st["their_lineup_delta"], side_size)

        labels = _purpose_labels(
            give_combo, get_combo, weakness.get(st["roster_id"], {}), st["lineup_delta"],
            my_starters_by_pos, my_roster_by_pos, bye_calendar_weeks, sell_high_ids, buy_low_ids,
            st["their_need_fit"], level,
        )
        if not labels:
            return None

        acceptance = _acceptance_label(
            st["give_value"], st["get_value"], st["their_lineup_delta"], st["their_need_fit"], st["partner_type"],
        )
        has_injured = any(p.get("injury_status") in HARD_OUT_STATUSES for p in give_combo + get_combo)
        injured_detail = [
            {"player_id": p["id"], "name": p.get("name"), "status": p.get("injury_status")}
            for p in give_combo + get_combo if p.get("injury_status") in HARD_OUT_STATUSES
        ]
        includes_key_player = bool(give_ids & key_player_ids)
        stance = _age_stance(give_combo, get_combo, is_dynasty)
        is_rival = False
        pr = playoff_results.get(st["roster_id"])
        if pr is not None and playoff_teams:
            prob = pr.get("playoff_probability", 0)
            is_rival = 15 <= prob <= 95 and abs((pr.get("projected_rank") or 99) - playoff_teams) <= 2.5

        proposal = {
            "roster_id": st["roster_id"],
            "team_name": st["team_name"],
            "give_player_ids": st["give_player_ids"],
            "get_player_ids": st["get_player_ids"],
            "give_value": st["give_value"],
            "get_value": st["get_value"],
            "value_diff_pct": st["value_diff_pct"],
            "value_diff_pct_signed": st["value_diff_pct_signed"],
            "lineup_points_before": st["lineup_points_before"],
            "lineup_points_after": st["lineup_points_after"],
            "lineup_delta": st["lineup_delta"],
            "their_lineup_points_before": st["their_lineup_points_before"],
            "their_lineup_points_after": st["their_lineup_points_after"],
            "their_lineup_delta": st["their_lineup_delta"],
            "is_win_win": st["is_win_win"],
            "acceptance": acceptance,
            "partner_type": st["partner_type"],
            "stance": stance,
            "purpose_labels": labels,
            "roster_legal_for_me": st["roster_legal_for_me"],
            "must_drop_players": st["must_drop_players"],
            "my_drop_candidate_ids": st["my_drop_candidate_ids"],
            "can_fill_via_waiver_mine": st["can_fill_via_waiver_mine"],
            "their_roster_legal": st["their_roster_legal"],
            "their_must_drop_players": st["their_must_drop_players"],
            "their_drop_candidate_ids": st["their_drop_candidate_ids"],
            "can_fill_via_waiver_theirs": st["can_fill_via_waiver_theirs"],
            "includes_key_player": includes_key_player,
            "has_injured_player": has_injured,
            "injured_players_detail": injured_detail,
            "my_need_fit": st["my_need_fit"],
            "their_need_fit": st["their_need_fit"],
            "their_record": st["their_record"],
            "their_waiver_moves": st["their_waiver_moves"],
            "their_trades": st["their_trades"],
            "is_current_week_opponent": st["roster_id"] == current_opponent_roster_id,
            "is_playoff_rival": is_rival,
            "relaxation_level": level,
            "relaxation_label": RELAXATION_LABELS[level],
            "reasons": _reasons(give_combo, get_combo, st["their_need_fit"], st["my_need_fit"], diff_pct),
            "partner_accept_reasons": _partner_accept_reasons(
                give_combo, st["their_need_fit"], st["their_lineup_delta"], st["partner_type"], acceptance,
            ),
        }
        if compute_breakdown:
            my_after_ids = [pid for pid in my_current_ids if pid not in give_ids] + list(get_ids)
            breakdown = _value_breakdown(
                my_current_ids, my_after_ids, players, roster_positions, flex_positions,
                current_week, deadline_weeks, playoff_weeks,
            )
            proposal["value_breakdown"] = breakdown
            proposal["my_value_delta_until_deadline"] = breakdown["until_deadline_total"]
            proposal["my_value_delta_playoffs"] = breakdown["playoffs_total"]
        return proposal

    finalized_all = [p for p in (finalize(st, compute_breakdown=False) for st in all_states) if p]

    # ---- Allgemeine Top-Liste: Vielfalt statt Dopplungen --------------------
    def sort_key(p):
        rival_penalty = 0.5 * max(p["their_lineup_delta"], 0) if p["is_playoff_rival"] else 0
        return p["lineup_delta"] - rival_penalty

    by_team = {}
    for p in finalized_all:
        by_team.setdefault(p["roster_id"], []).append(p)

    pre_diverse = []
    for rid, cands in by_team.items():
        cands.sort(key=sort_key, reverse=True)
        pre_diverse.extend(cands[:MAX_PROPOSALS_PER_TEAM * 3])

    pre_diverse.sort(key=sort_key, reverse=True)

    def anchor_give(p):
        return max(p["give_player_ids"], key=lambda pid: (players.get(pid) or {}).get("trade_value") or 0)

    give_appearance_count = {}
    group_seen = {}
    diverse = []
    seen_combo = set()
    for p in pre_diverse:
        combo_key = (p["roster_id"], tuple(p["give_player_ids"]), tuple(p["get_player_ids"]))
        if combo_key in seen_combo:
            continue
        seen_combo.add(combo_key)

        anchor = anchor_give(p)
        group_key = (p["roster_id"], anchor)
        if group_key in group_seen:
            kept = group_seen[group_key]
            if len(kept.setdefault("variants", [])) < 2:
                kept["variants"].append({
                    "give_player_ids": p["give_player_ids"],
                    "get_player_ids": p["get_player_ids"],
                    "lineup_delta": p["lineup_delta"],
                    "value_diff_pct": p["value_diff_pct"],
                })
            continue

        if give_appearance_count.get(anchor, 0) >= MAX_GIVE_PLAYER_APPEARANCES:
            continue

        p["variants"] = []
        group_seen[group_key] = p
        give_appearance_count[anchor] = give_appearance_count.get(anchor, 0) + 1
        diverse.append(p)
        if len(diverse) >= MAX_TOTAL_PROPOSALS:
            break

    # Je Bedarfsposition sicherstellen, dass mind. 1 Vorschlag vertreten ist,
    # falls einer existiert (sonst würde z.B. ein RB/TE-Bedarf stumm untergehen).
    needed_positions = sorted([p for p in TRADE_POSITIONS if my_weakness.get(p, 0) >= 1.5], key=lambda p: my_weakness.get(p, 0), reverse=True)
    represented_positions = {pos for p in diverse for pid in p["get_player_ids"] for pos in [players.get(pid, {}).get("position")]}
    for pos in needed_positions:
        if pos in represented_positions:
            continue
        candidate = next(
            (p for p in pre_diverse if any(players.get(pid, {}).get("position") == pos for pid in p["get_player_ids"])
             and (p["roster_id"], tuple(p["give_player_ids"]), tuple(p["get_player_ids"])) not in
             {(d["roster_id"], tuple(d["give_player_ids"]), tuple(d["get_player_ids"])) for d in diverse}),
            None,
        )
        if candidate:
            candidate["variants"] = candidate.get("variants", [])
            diverse.append(candidate)

    diverse.sort(key=sort_key, reverse=True)
    final_proposals = diverse[:MAX_TOTAL_PROPOSALS]
    for p in final_proposals:
        give_ids = set(p["give_player_ids"])
        get_ids = set(p["get_player_ids"])
        my_after_ids = [pid for pid in my_current_ids if pid not in give_ids] + list(get_ids)
        breakdown = _value_breakdown(
            my_current_ids, my_after_ids, players, roster_positions, flex_positions,
            current_week, deadline_weeks, playoff_weeks,
        )
        p["value_breakdown"] = breakdown
        p["my_value_delta_until_deadline"] = breakdown["until_deadline_total"]
        p["my_value_delta_playoffs"] = breakdown["playoffs_total"]

    # ---- Teil D/F: Indizes je handelbarem Spieler ----------------------------
    def with_breakdown(p):
        if "value_breakdown" in p:
            return p
        give_ids = set(p["give_player_ids"])
        get_ids = set(p["get_player_ids"])
        my_after_ids = [pid for pid in my_current_ids if pid not in give_ids] + list(get_ids)
        breakdown = _value_breakdown(
            my_current_ids, my_after_ids, players, roster_positions, flex_positions,
            current_week, deadline_weeks, playoff_weeks,
        )
        p["value_breakdown"] = breakdown
        p["my_value_delta_until_deadline"] = breakdown["until_deadline_total"]
        p["my_value_delta_playoffs"] = breakdown["playoffs_total"]
        return p

    block_index = {}
    for p in finalized_all:
        for pid in p["give_player_ids"]:
            block_index.setdefault(pid, []).append(p)
    target_index = {}
    for p in finalized_all:
        for pid in p["get_player_ids"]:
            target_index.setdefault(pid, []).append(p)

    def dedupe_sorted(lst, key):
        seen = set()
        out = []
        for p in sorted(lst, key=key, reverse=True):
            combo_key = (p["roster_id"], tuple(p["give_player_ids"]), tuple(p["get_player_ids"]))
            if combo_key in seen:
                continue
            seen.add(combo_key)
            out.append(p)
        return out

    owner_of_map = {}
    team_by_id = {t["roster_id"]: t for t in teams}
    for t in teams:
        if t["roster_id"] == my_roster_id:
            continue
        for pid in t["players"]:
            owner_of_map[pid] = t["roster_id"]

    def _owner_of(pid):
        return owner_of_map.get(pid)

    def _build_topup_index(player_ids, side, base_index):
        """Reichert den Index für jeden Spieler an, der noch nicht genug
        Treffer aus der allgemeinen Suche hat, mit einer gezielten Nachsuche
        (_topup_states_for_player) an - die roster_id ist dabei immer schon
        aus der umschließenden Team-Schleife bekannt, keine Rückableitung
        nötig."""
        out = {}
        for pid in player_ids:
            matches = dedupe_sorted(base_index.get(pid, []), key=sort_key)
            min_needed = MIN_PROPOSALS_PER_PLAYER if side == "give" else TARGET_OFFER_TIER_COUNT
            if len(matches) >= min_needed:
                out[pid] = matches
                continue
            extra_finalized = []
            for rid, (ctx, their_full_ids, _pool_ids) in team_contexts.items():
                if side == "get" and rid != _owner_of(pid):
                    continue
                extra_raw = _topup_states_for_player(pid, side, my_full_ids, their_full_ids, ctx, perf)
                team = team_by_id.get(rid)
                if not team:
                    continue
                scouting = scouting_by_roster.get(rid)
                partner_type = _partner_type(team.get("rank") or (num_teams or 14), num_teams, playoff_teams, scouting)
                for st in extra_raw:
                    st["roster_id"] = rid
                    st["team_name"] = team["team_name"]
                    st["partner_type"] = partner_type
                    st["their_record"] = f"{team.get('wins', 0)}-{team.get('losses', 0)}"
                    st["their_waiver_moves"] = scouting["waiver_moves"] if scouting else None
                    st["their_trades"] = scouting["trades"] if scouting else None
                    fp = finalize(st, compute_breakdown=False)
                    if fp:
                        extra_finalized.append(fp)
            matches = dedupe_sorted(matches + extra_finalized, key=sort_key)
            out[pid] = matches
        return out

    block_player_candidates = _build_topup_index(my_full_ids, "give", block_index)
    opponent_tradeable_ids = [pid for pid, rid in owner_of_map.items() if rid in team_contexts and players.get(pid, {}).get("trade_value")]
    target_raw_index = _build_topup_index(opponent_tradeable_ids, "get", target_index)

    block_player_candidates = {
        pid: {
            "section_a": [with_breakdown(p) for p in dedupe_sorted(
                [m for m in matches if any(players.get(gid, {}).get("position") in needed_positions for gid in m["get_player_ids"])],
                key=sort_key,
            )[:10]],
            "section_b": [with_breakdown(p) for p in matches[:10]],
        }
        for pid, matches in block_player_candidates.items()
    }

    target_offers = {}
    for pid, matches in target_raw_index.items():
        if not matches:
            continue
        ranked = sorted(matches, key=lambda p: p["give_value"])
        n = len(ranked)
        tiers = {}
        if n >= 1:
            tiers["entry"] = with_breakdown(ranked[0])
        if n >= 2:
            tiers["mid"] = with_breakdown(ranked[min(n - 1, n // 2)])
        if n >= 1:
            tiers["max"] = with_breakdown(ranked[-1])
        target_offers[pid] = tiers

    # ---- Übersicht / Teams ---------------------------------------------------
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
        "my_needs": needed_positions,
        "key_player_ids": sorted(key_player_ids),
        "team_summaries": team_summaries,
        "proposals": final_proposals,
        "block_player_candidates": {str(pid): v for pid, v in block_player_candidates.items()},
        "target_offers": {str(pid): v for pid, v in target_offers.items()},
        "lineup_points_baseline": my_baseline_points,
        "weakness_matrix": {str(rid): w for rid, w in weakness.items()},
        "team_pools": team_pools,
        "remaining_weeks_estimate": remaining_weeks_estimate,
        "league_rules_note": _league_rules_note(rules, is_dynasty, num_teams),
        "performance_note": performance_note,
        "build_seconds": round(time.monotonic() - start_time, 2),
        "states_evaluated": perf["evals"],
    }


def validate_proposals(trade_finder_data, players):
    """Build-Gate: prüft die harten Invarianten über ALLE tatsächlich
    erzeugten Vorschläge (proposals + block_player_candidates + target_offers),
    nicht nur Stichproben. Gibt eine Liste von Fehlertexten zurück (leer =
    alles ok)."""
    errors = []

    def check_proposal(p, source):
        for pid in p["give_player_ids"] + p["get_player_ids"]:
            pos = (players.get(pid) or {}).get("position")
            if pos in ("K", "DEF"):
                errors.append(f"[{source}] Trade enthält K/DEF ({pid}, {pos}): {p['team_name']}")
        if not p.get("purpose_labels"):
            errors.append(f"[{source}] Vorschlag ohne Zweck-Label: {p['team_name']} {p['give_player_ids']}->{p['get_player_ids']}")
        get_qb = [pid for pid in p["get_player_ids"] if (players.get(pid) or {}).get("position") == "QB"]
        get_te = [pid for pid in p["get_player_ids"] if (players.get(pid) or {}).get("position") == "TE"]
        if len(get_qb) > 1:
            errors.append(f"[{source}] mehr als 1 QB im selben Trade erhalten: {p['give_player_ids']}->{p['get_player_ids']}")
        if len(get_te) > 1:
            errors.append(f"[{source}] mehr als 1 TE im selben Trade erhalten: {p['give_player_ids']}->{p['get_player_ids']}")

    seen_combos = set()
    for p in trade_finder_data.get("proposals", []):
        check_proposal(p, "proposals")
        key = (p["roster_id"], tuple(sorted(p["give_player_ids"])), tuple(sorted(p["get_player_ids"])))
        if key in seen_combos:
            errors.append(f"Doppelter Vorschlag: {key}")
        seen_combos.add(key)

    for pid, sections in trade_finder_data.get("block_player_candidates", {}).items():
        for p in sections.get("section_a", []) + sections.get("section_b", []):
            check_proposal(p, f"block_player_candidates[{pid}]")

    for pid, tiers in trade_finder_data.get("target_offers", {}).items():
        for p in tiers.values():
            check_proposal(p, f"target_offers[{pid}]")

    return errors
