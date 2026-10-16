"""Start/Sit-Optimizer: bestes Lineup für die aktuelle Woche aus Projection,
Matchup-Faktor (inkl. Gegner-Rang gegen die Position), Vegas-Odds, Target-/
Rushing-Share, Form der letzten 3 Wochen und Verletzungsstatus. Liefert pro
Slot eine Begründung und für jede Abweichung vom aktuell gesetzten Lineup
eine A-vs-B-Entscheidung mit Konfidenz."""

FLEX_ELIGIBLE = {"RB", "WR", "TE"}

# Harter Ausschluss: Spieler mit diesem Status kommen für die Aufstellung
# nicht in Frage (wird in der Praxis selten/nie starten).
HARD_OUT_STATUSES = {"Out", "IR", "NA", "Sus", "PUP", "COV", "DNR"}

# Weicher Abschlag auf die Projection bei Unsicherheit über den Einsatz.
SOFT_INJURY_MULTIPLIER = {"Doubtful": 0.5, "Questionable": 0.9}

STATUS_LABELS_DE = {
    "Questionable": "fraglich",
    "Doubtful": "unwahrscheinlich im Einsatz",
    "Out": "out",
    "IR": "verletzt (IR)",
}


def _eligible(p, current_week):
    if p.get("bye_week") == current_week:
        return False
    if p.get("injury_status") in HARD_OUT_STATUSES:
        return False
    return True


def _effective_projection(p):
    base = p.get("projection_week") or 0.0
    mult = SOFT_INJURY_MULTIPLIER.get(p.get("injury_status"), 1.0)
    factor = p.get("matchup_factor") or 1.0
    return round(base * mult * factor, 2)


def _best_lineup(pool, roster_positions, flex_positions=None):
    flex_positions = flex_positions or FLEX_ELIGIBLE
    by_pos = {"QB": [], "RB": [], "WR": [], "TE": [], "K": [], "DEF": []}
    for p in pool:
        if p["position"] in by_pos:
            by_pos[p["position"]].append(p)
    for lst in by_pos.values():
        lst.sort(key=lambda p: p["_eff"], reverse=True)

    used_ids = set()

    def take(pos, n):
        out = []
        for p in by_pos[pos]:
            if len(out) >= n:
                break
            if p["id"] in used_ids:
                continue
            out.append(p)
            used_ids.add(p["id"])
        return out

    counts = {pos: roster_positions.count(pos) for pos in by_pos}
    n_flex = roster_positions.count("FLEX")

    pools_by_label = {pos: take(pos, n) for pos, n in counts.items()}

    flex_candidates = [p for pos in flex_positions for p in by_pos[pos] if p["id"] not in used_ids]
    flex_candidates.sort(key=lambda p: p["_eff"], reverse=True)
    flex = flex_candidates[:n_flex]
    for p in flex:
        used_ids.add(p["id"])
    pools_by_label["FLEX"] = flex

    result = []
    for label in roster_positions:
        bucket = pools_by_label.get(label, [])
        result.append(bucket.pop(0) if bucket else None)
    return result


def _form_note(p):
    if (p.get("games_played") or 0) < 2:
        return None
    season_avg = p.get("season_avg") or 0
    avg_last3 = p.get("avg_last3") or 0
    if season_avg <= 0.5:
        return None
    diff_pct = (avg_last3 - season_avg) / season_avg
    if diff_pct >= 0.15:
        return f"Aufwärtstrend: {avg_last3} Pkt./Sp. in den letzten 3 Wochen vs. {season_avg} Saison-Schnitt"
    if diff_pct <= -0.15:
        return f"Abwärtstrend: {avg_last3} Pkt./Sp. in den letzten 3 Wochen vs. {season_avg} Saison-Schnitt"
    return None


def _usage_notes(p):
    notes = []
    if p["position"] in ("WR", "TE") and p.get("target_share"):
        notes.append(f"{p['target_share']}% Target Share")
    if p["position"] == "RB" and p.get("rush_share"):
        notes.append(f"{p['rush_share']}% Rushing Share")
    if p.get("snap_pct"):
        notes.append(f"{p['snap_pct']}% Snap-Anteil")
    if p.get("redzone_pg"):
        notes.append(f"{p['redzone_pg']} Red-Zone-Chancen/Spiel")
    return notes


def _matchup_note(p):
    if not p.get("matchup_opponent"):
        return None
    rest = p.get("rest_of_season") or []
    loc = "zuhause" if rest and rest[0].get("home") else "auswärts"
    note = f"{'Zuhause' if loc == 'zuhause' else 'Auswärts'} vs. {p['matchup_opponent']}"
    if p.get("matchup_rank") and p.get("matchup_rank_of"):
        rk, of = p["matchup_rank"], p["matchup_rank_of"]
        tier = "schwache Verteidigung" if rk > of * 0.66 else "starke Verteidigung" if rk <= of * 0.33 else "durchschnittliche Verteidigung"
        note += f" · Rang {rk}/{of} gegen {p['position']} ({tier})"
    v = p.get("vegas")
    if v and v.get("over_under") is not None:
        fav_txt = "Favorit" if v.get("favorite") else "Außenseiter" if v.get("favorite") is False else None
        extra = f", {fav_txt} ({v['details']})" if fav_txt and v.get("details") else (f" ({v['details']})" if v.get("details") else "")
        note += f" · Vegas O/U {v['over_under']}{extra}"
    return note


def _injury_note(p):
    if not p.get("injury_status"):
        return None
    label = STATUS_LABELS_DE.get(p["injury_status"], p["injury_status"])
    body = f" ({p['injury_body_part']})" if p.get("injury_body_part") else ""
    practice = (
        f" · Training: {p['practice_description']}" if p.get("practice_description")
        else " · keine Trainingsstatus-Daten verfügbar"
    )
    return f"Status: {label}{body}{practice}"


def _slot_reasons(p):
    """Vollständige Begründung für EINEN empfohlenen Spieler (unabhängig
    davon, ob er bereits startet oder neu hereinkommt)."""
    notes = []
    m = _matchup_note(p)
    if m:
        notes.append(m)
    notes.extend(_usage_notes(p))
    form = _form_note(p)
    if form:
        notes.append(form)
    inj = _injury_note(p)
    if inj:
        notes.append(inj)
    if not notes:
        notes.append(f"Projektion: {p.get('projection_week', 0)} Pkt.")
    return notes


def _confidence(delta):
    if abs(delta) >= 4:
        return "hoch"
    if abs(delta) >= 1.5:
        return "mittel"
    return "niedrig"


def _decision_reasons(current, rec, current_week):
    reasons = []
    if current is None:
        reasons.append("Slot war nicht besetzt.")
        reasons.extend(_slot_reasons(rec))
        return reasons
    if current.get("bye_week") == current_week:
        reasons.append(f"{current['name']} hat diese Woche Bye.")
    elif current.get("injury_status") in HARD_OUT_STATUSES:
        reasons.append(_injury_note(current) or f"{current['name']} ist nicht einsatzfähig.")
    else:
        reasons.append(f"Höhere erwartete Punktzahl: {rec['_eff']} vs. {current['_eff']} Pkt.")
        inj = _injury_note(current)
        if inj:
            reasons.append(f"{current['name']}: {inj}")
    reasons.extend(_slot_reasons(rec))
    return reasons


def _duel_summary(data):
    m = data.get("matchup")
    if not m or not m.get("opponent"):
        return None
    wp = m.get("win_probability_me")
    if wp is None:
        return None
    if wp >= 60:
        stance, advice = "favorit", "Du bist Favorit in diesem Duell - bei knappen Entscheidungen lohnt sich eher der Spieler mit dem sichereren Floor als der mit dem höheren Risiko."
    elif wp <= 40:
        stance, advice = "underdog", "Du bist Außenseiter in diesem Duell - bei knappen Entscheidungen kann der Spieler mit dem höheren Ceiling (Boom-Potenzial) die bessere Wahl sein, auch bei etwas niedrigerer Projection."
    else:
        stance, advice = "ausgeglichen", "Knappes Duell laut Projection - einzelne Start/Sit-Entscheidungen können hier den Ausschlag geben."
    return {"win_probability_me": wp, "stance": stance, "advice": advice}


def compute(data):
    players = data["players"]
    current_week = data["league"]["week"]
    roster_positions = data["league"]["roster_positions"]

    my_player_ids = [s["player_id"] for s in data["my_roster"]["slots"]] + data["my_roster"]["bench"]
    pool = []
    for pid in my_player_ids:
        p = players.get(pid)
        if not p or not _eligible(p, current_week):
            continue
        p = dict(p)
        p["_eff"] = _effective_projection(p)
        pool.append(p)

    recommended = _best_lineup(pool, roster_positions)

    current_slots = data["my_roster"]["slots"]
    current_starting_set = {s["player_id"] for s in current_slots if s["player_id"]}
    recommended_set = {p["id"] for p in recommended if p}

    recommended_slots = [
        {
            "slot": slot_label,
            "player_id": rec_p["id"] if rec_p else None,
            "effective_projection": rec_p["_eff"] if rec_p else 0.0,
            "reasons": _slot_reasons(rec_p) if rec_p else [],
        }
        for slot_label, rec_p in zip(roster_positions, recommended)
    ]

    # Echte Entscheidungen sind Bank->Start-Wechsel, keine kosmetische
    # Umsortierung zwischen zwei Spielern, die beide schon starten
    # (z.B. RB1<->RB2 oder TE<->FLEX). Dafür werden "neu hinein" und
    # "raus auf die Bank" über Mengendifferenzen bestimmt und nach
    # Position gepaart, statt stur Slot-Index gegen Slot-Index zu vergleichen.
    to_bench_ids = current_starting_set - recommended_set
    remaining_bench = []
    for pid in to_bench_ids:
        p = players.get(pid)
        if not p:
            continue
        p = dict(p)
        p["_eff"] = _effective_projection(p)
        remaining_bench.append(p)

    decisions = []
    for slot_label, rec_p in zip(roster_positions, recommended):
        if rec_p is None or rec_p["id"] not in recommended_set or rec_p["id"] in current_starting_set:
            continue
        same_pos = [b for b in remaining_bench if b["position"] == rec_p["position"]]
        partner = same_pos[0] if same_pos else (remaining_bench[0] if remaining_bench else None)
        if partner:
            remaining_bench.remove(partner)
        delta = round(rec_p["_eff"] - (partner["_eff"] if partner else 0.0), 2)
        decisions.append({
            "slot": slot_label,
            "current_player_id": partner["id"] if partner else None,
            "recommended_player_id": rec_p["id"],
            "delta": delta,
            "confidence": _confidence(delta),
            "reasons": _decision_reasons(partner, rec_p, current_week),
        })

    decisions.sort(key=lambda d: d["delta"], reverse=True)

    return {
        "week": current_week,
        "recommended_slots": recommended_slots,
        "decisions": decisions,
        "duel_summary": _duel_summary(data),
    }
