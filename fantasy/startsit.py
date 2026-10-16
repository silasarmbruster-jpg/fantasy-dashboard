"""Start/Sit-Optimizer: bestes Lineup für die aktuelle Woche aus Projection,
Matchup-Faktor, Verletzungsstatus und Bye Week, inkl. Begründungen für jede
Abweichung vom aktuell gesetzten Lineup."""

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


def _best_lineup(pool, roster_positions):
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

    flex_candidates = [p for pos in FLEX_ELIGIBLE for p in by_pos[pos] if p["id"] not in used_ids]
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


def _reasons(current, rec, current_week):
    reasons = []
    if current is None:
        reasons.append("Slot war nicht besetzt.")
        return reasons
    if current.get("bye_week") == current_week:
        reasons.append(f"{current['name']} hat diese Woche Bye.")
    elif current.get("injury_status") in HARD_OUT_STATUSES:
        label = STATUS_LABELS_DE.get(current["injury_status"], current["injury_status"])
        reasons.append(f"{current['name']} ist {label}.")
    else:
        reasons.append(f"Höhere erwartete Punktzahl: {rec['_eff']} vs. {current['_eff']} Pkt.")
        if current.get("injury_status") in SOFT_INJURY_MULTIPLIER:
            reasons.append(f"{current['name']} ist {STATUS_LABELS_DE.get(current['injury_status'], current['injury_status'])}.")
    if rec.get("matchup_factor", 1.0) >= 1.08:
        reasons.append(f"{rec['name']} trifft auf eine schwache Verteidigung gegen {rec['position']}.")
    if current.get("matchup_factor", 1.0) <= 0.92 and current.get("injury_status") not in HARD_OUT_STATUSES:
        reasons.append(f"{current['name']} trifft auf eine starke Verteidigung gegen {current['position']}.")
    return reasons


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
        decisions.append({
            "slot": slot_label,
            "current_player_id": partner["id"] if partner else None,
            "recommended_player_id": rec_p["id"],
            "delta": round(rec_p["_eff"] - (partner["_eff"] if partner else 0.0), 2),
            "reasons": _reasons(partner, rec_p, current_week),
        })

    decisions.sort(key=lambda d: d["delta"], reverse=True)

    return {
        "week": current_week,
        "recommended_slots": recommended_slots,
        "decisions": decisions,
    }
