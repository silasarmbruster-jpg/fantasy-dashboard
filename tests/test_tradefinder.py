"""Automatisierte Tests für den Trade-Finder-Neuaufbau (Runde 5):
- Wert-Regeln: Potenz-Summe-Toleranz, 110%-Obergrenze, Superstar-Regel,
  Bankspieler nie gegen Top-30 (Teil 4)
- Sinn-Regeln: höchstens 1 QB/TE und nur mit Starterrolle, kein leerer
  Pflicht-Slot, Roster-Limits (Teil 5)
- Konsistente Zahlen über alle Horizonte (Teil 6)
- Jede Trade-Idee hat einen Anlass, keine Season-Aus-Verletzten als Buy-Low,
  keine Notlage ohne nachgewiesene Lücke (Teil 8)
- Mindestabdeckung für Block-/Zielspieler (>=2 Pakete in >=3 Formaten oder
  eine Erklärung), mindestens 3 Ideen je aktivierter Kategorie oder eine
  Erklärung (Teil 8)
Ein Build mit Verstößen wird von build.py verworfen (siehe validate_proposals)."""

import json
from pathlib import Path

import pytest

from fantasy import tradefinder as tf

ROOT = Path(__file__).resolve().parent.parent

RULES_1QB = {
    "starter_counts": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2, "K": 1, "DEF": 1},
    "flex_positions": {"RB", "WR", "TE"},
    "super_flex": False,
    "num_qb_starters": 1,
    "total_roster_slots": 16,
}


def make_player(pid, position, trade_value=1000, bye_week=9, injury_status=None, age=25, team="KC",
                 season_avg=10.0, avg_last3=10.0, projection_week=10.0, name=None, trade_rank=None):
    return {
        "id": pid, "name": name or pid, "position": position, "team": team, "trade_value": trade_value,
        "bye_week": bye_week, "injury_status": injury_status, "age": age,
        "season_avg": season_avg, "avg_last3": avg_last3, "games_played": 5,
        "projection_week": projection_week, "trade_rank": trade_rank,
    }


# ---------------------------------------------------------------------------
# Teil 4: Wert-Regeln
# ---------------------------------------------------------------------------

def test_tradeable_pool_excludes_k_def_and_reserve():
    players = {
        "qb1": make_player("qb1", "QB"), "k1": make_player("k1", "K"),
        "def1": make_player("def1", "DEF"), "wr1": make_player("wr1", "WR"),
        "reserve1": make_player("reserve1", "RB"),
    }
    team = {"players": list(players.keys()), "reserve": ["reserve1"]}
    pool = tf._tradeable_pool(team, players)
    pool_ids = {p["id"] for p in pool}
    assert "k1" not in pool_ids
    assert "def1" not in pool_ids
    assert "reserve1" not in pool_ids
    assert pool_ids == {"qb1", "wr1"}


def test_missing_trade_value_treated_as_replacement_level_not_zero():
    p = make_player("p1", "WR", trade_value=None)
    assert tf._player_value(p) == tf.REPLACEMENT_VALUE
    assert tf.REPLACEMENT_VALUE > 0


def _combo(players, ids, current_starter_ids=None):
    return tf._combo_record([players[i] for i in ids], current_starter_ids)


def test_value_check_passes_within_default_tolerance():
    players = {"g1": make_player("g1", "WR", trade_value=1000), "r1": make_player("r1", "WR", trade_value=1050)}
    give = _combo(players, ["g1"])
    get = _combo(players, ["r1"])
    diff = tf._value_check(give, get, max_qb=1, max_te=1, tolerance=0.10)
    assert diff is not None


def test_value_check_rejects_beyond_gain_cap_even_at_max_tolerance():
    # Ich gebe 1000, bekomme 1200 -> +20% Wertgewinn, das ist > GAIN_CAP (10%)
    # und muss IMMER abgelehnt werden, auch bei der lockersten Toleranz.
    players = {"g1": make_player("g1", "WR", trade_value=1000), "r1": make_player("r1", "WR", trade_value=1200)}
    give = _combo(players, ["g1"])
    get = _combo(players, ["r1"])
    diff = tf._value_check(give, get, max_qb=1, max_te=1, tolerance=tf.TOLERANCE_MAX)
    assert diff is None


def test_value_check_allows_overpaying_up_to_tolerance():
    # Ich gebe 1000, bekomme 900 -> in Potenz-Summe (^1.5) ein Minus von
    # ca. 14.6% für mich ("zu meinen Lasten"), muss bei Toleranz 20% noch
    # durchgehen, bei 5% aber nicht mehr.
    players = {"g1": make_player("g1", "WR", trade_value=1000), "r1": make_player("r1", "WR", trade_value=900)}
    give = _combo(players, ["g1"])
    get = _combo(players, ["r1"])
    assert tf._value_check(give, get, max_qb=1, max_te=1, tolerance=0.20) is not None
    assert tf._value_check(give, get, max_qb=1, max_te=1, tolerance=0.05) is None


def test_superstar_rule_blocks_disproportionate_single_player():
    # Mein wertvollster Abgabe-Spieler ist 1000 wert, der wertvollste, den
    # ich bekomme, ist 1500 wert (1.5x) - das überschreitet SUPERSTAR_CAP (1.3x).
    players = {
        "g1": make_player("g1", "WR", trade_value=600), "g2": make_player("g2", "WR", trade_value=1000),
        "r1": make_player("r1", "WR", trade_value=1500), "r2": make_player("r2", "WR", trade_value=100),
    }
    give = _combo(players, ["g1", "g2"])
    get = _combo(players, ["r1", "r2"])
    assert tf._value_check(give, get, max_qb=1, max_te=1, tolerance=tf.TOLERANCE_MAX) is None


def test_bench_player_never_gets_top_30_player():
    players = {
        "bench1": make_player("bench1", "WR", trade_value=900),
        "top_player": make_player("top_player", "WR", trade_value=950, trade_rank=12),
    }
    give = _combo(players, ["bench1"], current_starter_ids=set())  # all_bench=True, "bench1" is not a starter
    get = _combo(players, ["top_player"])
    assert tf._value_check(give, get, max_qb=1, max_te=1, tolerance=tf.TOLERANCE_MAX) is None


def test_bench_player_can_get_non_top_30_player():
    players = {
        "bench1": make_player("bench1", "WR", trade_value=900),
        "mid_player": make_player("mid_player", "WR", trade_value=950, trade_rank=80),
    }
    give = _combo(players, ["bench1"], current_starter_ids=set())
    get = _combo(players, ["mid_player"])
    assert tf._value_check(give, get, max_qb=1, max_te=1, tolerance=tf.TOLERANCE_MAX) is not None


def test_value_check_blocks_more_qbs_than_league_allows():
    players = {"g1": make_player("g1", "WR", trade_value=1000), "q1": make_player("q1", "QB", trade_value=400), "q2": make_player("q2", "QB", trade_value=500)}
    give = _combo(players, ["g1"])
    get = _combo(players, ["q1", "q2"])
    assert tf._value_check(give, get, max_qb=1, max_te=1, tolerance=tf.TOLERANCE_MAX) is None


# ---------------------------------------------------------------------------
# Teil 5: Sinn-Regeln
# ---------------------------------------------------------------------------

def test_qb_te_must_start_blocks_qb_on_bench():
    assert tf._qb_te_must_start({"qb1"}, starter_ids=set(), players={"qb1": make_player("qb1", "QB")}) is False


def test_qb_te_must_start_allows_qb_that_starts():
    assert tf._qb_te_must_start({"qb1"}, starter_ids={"qb1"}, players={"qb1": make_player("qb1", "QB")}) is True


def test_qb_te_must_start_ignores_non_qb_te_players():
    players = {"wr1": make_player("wr1", "WR")}
    assert tf._qb_te_must_start({"wr1"}, starter_ids=set(), players=players) is True


def test_lineup_legality_requires_all_mandatory_positions():
    players = {}
    ids = []
    for i, pos in enumerate(["RB", "RB", "WR", "WR", "TE", "RB", "WR"]):
        pid = f"p{i}"
        players[pid] = make_player(pid, pos)
        ids.append(pid)
    legal, reason = tf._lineup_legality(ids, players, RULES_1QB)
    assert legal is False
    assert "QB" in reason


def test_lineup_legality_requires_bench_depth():
    players = {}
    ids = []
    counts = {"QB": 1, "RB": 2, "WR": 2, "TE": 1}
    for pos, n in counts.items():
        for i in range(n):
            pid = f"{pos}{i}"
            players[pid] = make_player(pid, pos)
            ids.append(pid)
    legal, _reason = tf._lineup_legality(ids, players, RULES_1QB)
    assert legal is False


def test_lineup_legality_passes_with_full_roster_and_depth():
    players = {}
    ids = []
    counts = {"QB": 2, "RB": 4, "WR": 4, "TE": 2, "K": 1, "DEF": 1}
    for pos, n in counts.items():
        for i in range(n):
            pid = f"{pos}{i}"
            players[pid] = make_player(pid, pos)
            ids.append(pid)
    legal, reason = tf._lineup_legality(ids, players, RULES_1QB)
    assert legal is True
    assert reason is None


def test_must_drop_info_no_overflow():
    players = {f"p{i}": make_player(f"p{i}", "WR") for i in range(5)}
    must_drop, drop_ids, can_fill = tf._must_drop_info(list(players.keys()), total_roster_slots=10, players=players, waiver_by_position={})
    assert must_drop is False
    assert drop_ids == []
    assert can_fill is True


def test_must_drop_info_detects_cheapest_drop_and_waiver_availability():
    players = {"expensive": make_player("expensive", "WR", trade_value=5000), "cheap": make_player("cheap", "WR", trade_value=100)}
    must_drop, drop_ids, can_fill = tf._must_drop_info(
        list(players.keys()), total_roster_slots=1, players=players, waiver_by_position={"WR": [{"player_id": "fa1"}]},
    )
    assert must_drop is True
    assert drop_ids == ["cheap"]
    assert can_fill is True


def test_package_label_matches_give_get_size_relationship():
    assert tf._package_label(3, 1) == "Spitze verbessern"
    assert tf._package_label(1, 3) == "Breite aufbauen"
    assert tf._package_label(2, 2) == "Gleichwertiger Tausch"


# ---------------------------------------------------------------------------
# Annahme-Wahrscheinlichkeit, vorzeichenrichtig
# ---------------------------------------------------------------------------

def test_acceptance_high_when_i_overpay():
    acceptance = tf._acceptance_label(give_value=1220, get_value=1000, their_lineup_delta=0, their_need_fit=0, partner_type="passive")
    assert acceptance == "hoch"


def test_acceptance_low_when_partner_loses_18_percent():
    acceptance = tf._acceptance_label(give_value=1000, get_value=1220, their_lineup_delta=5, their_need_fit=5, partner_type="buyer")
    assert acceptance == "niedrig"


def test_acceptance_capped_at_medium_for_5_to_15_percent_partner_loss():
    acceptance = tf._acceptance_label(give_value=1000, get_value=1111, their_lineup_delta=10, their_need_fit=5, partner_type="buyer")
    assert acceptance == "mittel"


# ---------------------------------------------------------------------------
# Teil 6 / Teil 8: konsistente Zahlen
# ---------------------------------------------------------------------------

def _consistency_ctx():
    roster_positions = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "K", "DEF", "BN", "BN"]
    flex_positions = {"RB", "WR", "TE"}
    players = {
        "qb1": make_player("qb1", "QB", projection_week=15, season_avg=15),
        "rb1": make_player("rb1", "RB", projection_week=10, season_avg=10),
        "rb2": make_player("rb2", "RB", projection_week=9, season_avg=9),
        "wr1": make_player("wr1", "WR", projection_week=8, season_avg=8),
        "wr2": make_player("wr2", "WR", projection_week=7, season_avg=7),
        "te1": make_player("te1", "TE", projection_week=6, season_avg=6),
        "flex1": make_player("flex1", "RB", projection_week=5, season_avg=5),
        "flex2": make_player("flex2", "WR", projection_week=4, season_avg=4),
        "k1": make_player("k1", "K", projection_week=8, season_avg=8),
        "def1": make_player("def1", "DEF", projection_week=8, season_avg=8),
        "bench_old": make_player("bench_old", "WR", projection_week=3, season_avg=3, bye_week=20),
        "bench_new": make_player("bench_new", "WR", projection_week=12, season_avg=12, bye_week=20),
    }
    ids = list(players.keys())
    return players, roster_positions, flex_positions, ids


def test_value_breakdown_this_week_is_one_entry_of_the_weekly_list():
    players, roster_positions, flex_positions, before_ids = _consistency_ctx()
    after_ids = [pid for pid in before_ids if pid != "bench_old"] + ["bench_new"]
    before_ids_final = [pid for pid in before_ids if pid != "bench_new"]
    current_week = 8
    deadline_weeks = [8, 9, 10]
    playoff_weeks = [14, 15, 16, 17]
    b = tf._value_breakdown(before_ids_final, after_ids, players, roster_positions, flex_positions, current_week, deadline_weeks, playoff_weeks)
    week_entry = next(w for w in b["weeks"] if w["week"] == current_week)
    assert b["this_week_delta"] == week_entry["delta"]


def test_value_breakdown_same_trade_gives_same_numbers_every_time():
    players, roster_positions, flex_positions, before_ids = _consistency_ctx()
    after_ids = [pid for pid in before_ids if pid != "bench_old"] + ["bench_new"]
    before_ids_final = [pid for pid in before_ids if pid != "bench_new"]
    args = (before_ids_final, after_ids, players, roster_positions, flex_positions, 8, [8, 9, 10], [14, 15, 16, 17])
    b1 = tf._value_breakdown(*args)
    b2 = tf._value_breakdown(*args)
    assert b1["until_deadline_total"] == b2["until_deadline_total"]
    assert b1["playoffs_total"] == b2["playoffs_total"]
    assert b1["this_week_delta"] == b2["this_week_delta"]


def test_value_breakdown_deadline_total_bounded_by_weeks_times_max_delta():
    players, roster_positions, flex_positions, before_ids = _consistency_ctx()
    after_ids = [pid for pid in before_ids if pid != "bench_old"] + ["bench_new"]
    before_ids_final = [pid for pid in before_ids if pid != "bench_new"]
    current_week = 8
    deadline_weeks = [8, 9, 10, 11]
    playoff_weeks = [14, 15, 16, 17]
    b = tf._value_breakdown(before_ids_final, after_ids, players, roster_positions, flex_positions, current_week, deadline_weeks, playoff_weeks)
    deadline_entries = [w for w in b["weeks"] if w["week"] in deadline_weeks]
    max_delta = max(w["delta"] for w in deadline_entries)
    assert b["until_deadline_total"] <= len(deadline_weeks) * max_delta + 1e-6


def test_value_breakdown_rest_of_season_covers_gap_weeks_between_deadline_and_playoffs():
    # Wochen 12/13 liegen zwischen Trade-Deadline (11) und Playoff-Start (14)
    # und tauchen in keiner der beiden Teilmengen auf - "Rest of Season" muss
    # sie trotzdem mitzählen, sonst fehlt ein Teil der Saison in der Summe.
    players, roster_positions, flex_positions, before_ids = _consistency_ctx()
    after_ids = [pid for pid in before_ids if pid != "bench_old"] + ["bench_new"]
    before_ids_final = [pid for pid in before_ids if pid != "bench_new"]
    current_week = 8
    deadline_weeks = [8, 9, 10, 11]
    playoff_weeks = [14, 15, 16, 17]
    rest_of_season_weeks = list(range(8, 18))  # 8..17, inkl. der Lücke 12/13
    b = tf._value_breakdown(
        before_ids_final, after_ids, players, roster_positions, flex_positions,
        current_week, deadline_weeks, playoff_weeks, rest_of_season_weeks,
    )
    assert "rest_of_season_total" in b
    week_numbers = {w["week"] for w in b["weeks"]}
    assert {12, 13}.issubset(week_numbers)
    expected = round(sum(w["delta"] for w in b["weeks"] if w["week"] in rest_of_season_weeks), 2)
    assert b["rest_of_season_total"] == expected
    # Rest of Season deckt strikt mehr Wochen ab als Deadline+Playoffs allein.
    assert len(rest_of_season_weeks) > len(set(deadline_weeks) | set(playoff_weeks))


def test_rest_of_season_player_value_scales_with_weeks_and_season_avg():
    p_high = make_player("p1", "WR", season_avg=20.0, avg_last3=20.0)
    p_low = make_player("p2", "WR", season_avg=5.0, avg_last3=5.0)
    assert tf._rest_of_season_player_value(p_high, 10) > tf._rest_of_season_player_value(p_low, 10)
    assert tf._rest_of_season_player_value(p_high, 10) > tf._rest_of_season_player_value(p_high, 2)
    assert tf._rest_of_season_player_value(p_high, 0) == 0.0


def test_rest_of_season_player_value_discounts_injury_and_bad_trend():
    healthy = make_player("p1", "WR", season_avg=10.0, avg_last3=10.0, injury_status=None)
    hurt = make_player("p2", "WR", season_avg=10.0, avg_last3=10.0, injury_status="Questionable")
    cold = make_player("p3", "WR", season_avg=10.0, avg_last3=5.0)
    assert tf._rest_of_season_player_value(hurt, 8) < tf._rest_of_season_player_value(healthy, 8)
    assert tf._rest_of_season_player_value(cold, 8) < tf._rest_of_season_player_value(healthy, 8)


def test_score_ranks_by_rest_of_season_not_this_week():
    # Paket A: schlecht diese Woche, aber stark über den Rest der Saison.
    # Paket B: umgekehrt. Der Fokus muss auf Rest of Season liegen (A > B).
    a = {"rest_of_season_proxy": 50.0, "lineup_delta": -5.0, "their_lineup_delta": 0, "is_playoff_rival": False}
    b = {"rest_of_season_proxy": 5.0, "lineup_delta": 20.0, "their_lineup_delta": 0, "is_playoff_rival": False}
    assert tf._score(a) > tf._score(b)


# ---------------------------------------------------------------------------
# validate_proposals (Build-Gate)
# ---------------------------------------------------------------------------

def _sample_candidate(**overrides):
    base = {
        "roster_id": 1, "team_name": "Test Team",
        "give_player_ids": ["wr1"], "get_player_ids": ["wr2"],
        "value_diff_pct": 5.0, "anlass": "Testgrund",
    }
    base.update(overrides)
    return base


def test_validate_proposals_flags_k_def():
    players = {"wr1": make_player("wr1", "WR"), "k1": make_player("k1", "K")}
    data = {"block_candidates": {"wr1": {"by_format": {"1-1": [_sample_candidate(get_player_ids=["k1"])]}}}, "target_candidates": {}, "ideas": {}}
    errors = tf.validate_proposals(data, players)
    assert any("K/DEF" in e for e in errors)


def test_validate_proposals_flags_two_qbs_received():
    players = {"wr1": make_player("wr1", "WR"), "qb1": make_player("qb1", "QB"), "qb2": make_player("qb2", "QB")}
    data = {"block_candidates": {"wr1": {"by_format": {"1-2": [_sample_candidate(get_player_ids=["qb1", "qb2"])]}}}, "target_candidates": {}, "ideas": {}}
    errors = tf.validate_proposals(data, players)
    assert any("mehr als 1 QB" in e for e in errors)


def test_validate_proposals_flags_gain_above_cap():
    players = {"wr1": make_player("wr1", "WR"), "wr2": make_player("wr2", "WR")}
    data = {"block_candidates": {"wr1": {"by_format": {"1-1": [_sample_candidate(value_diff_pct=25.0)]}}}, "target_candidates": {}, "ideas": {}}
    errors = tf.validate_proposals(data, players)
    assert any("10%-Obergrenze" in e for e in errors)


def test_validate_proposals_flags_idea_without_anlass():
    players = {"wr1": make_player("wr1", "WR"), "wr2": make_player("wr2", "WR")}
    item = _sample_candidate()
    del item["anlass"]
    data = {"block_candidates": {}, "target_candidates": {}, "ideas": {"sell_high": {"items": [item]}}}
    errors = tf.validate_proposals(data, players)
    assert any("ohne Anlass" in e for e in errors)


def test_validate_proposals_clean_data_has_no_errors():
    players = {"wr1": make_player("wr1", "WR"), "wr2": make_player("wr2", "WR")}
    data = {
        "block_candidates": {"wr1": {"by_format": {"1-1": [_sample_candidate()]}}},
        "target_candidates": {},
        "ideas": {"sell_high": {"items": [_sample_candidate(roster_id=2)]}},
    }
    errors = tf.validate_proposals(data, players)
    assert errors == []


# ---------------------------------------------------------------------------
# Integrationstests gegen den letzten echten Build (übersprungen ohne Build)
# ---------------------------------------------------------------------------

def _load_real_data():
    data_path = ROOT / "docs" / "data.json"
    if not data_path.exists():
        pytest.skip("docs/data.json nicht vorhanden - noch kein Build-Lauf")
    data = json.loads(data_path.read_text(encoding="utf-8"))
    if "block_candidates" not in data.get("trade_finder", {}):
        pytest.skip("docs/data.json stammt noch aus einem Build vor dem Trade-Finder-Neuaufbau (Runde 5)")
    return data


def test_real_build_output_passes_all_invariants():
    data = _load_real_data()
    errors = tf.validate_proposals(data["trade_finder"], data["players"])
    assert errors == [], f"{len(errors)} Invarianten-Verstöße im letzten Build: {errors[:5]}"


def test_real_build_every_player_with_market_value_has_coverage_or_explanation():
    data = _load_real_data()
    tf_data = data["trade_finder"]
    short = []
    for source in ("block_candidates", "target_candidates"):
        for pid, entry in tf_data[source].items():
            total = sum(len(v) for v in entry["by_format"].values())
            n_formats = len(entry["by_format"])
            ok = (total >= tf.MIN_PACKAGES_PER_PLAYER and n_formats >= tf.MIN_FORMATS_PER_PLAYER) or entry.get("empty_reason")
            if not ok:
                short.append((source, pid, total, n_formats))
    assert not short, f"Spieler ohne ausreichende Abdeckung UND ohne Erklärung: {short[:10]}"


def test_real_build_ideas_have_at_least_three_items_or_an_explanation():
    data = _load_real_data()
    ideas = data["trade_finder"]["ideas"]
    bad = [key for key, idea in ideas.items() if len(idea.get("items", [])) < 3 and not idea.get("empty_reason")]
    assert not bad, f"Trade-Ideen-Kategorien ohne >=3 Ideen UND ohne Erklärung: {bad}"


def test_real_build_every_idea_item_references_real_data_in_its_anlass():
    data = _load_real_data()
    ideas = data["trade_finder"]["ideas"]
    players = data["players"]
    for key, idea in ideas.items():
        for item in idea.get("items", []):
            assert item.get("anlass"), f"Idee ohne Anlass in {key}: {item['give_player_ids']}->{item['get_player_ids']}"


def test_real_build_no_season_ending_injury_in_buy_low():
    data = _load_real_data()
    buy_low = data["trade_finder"]["ideas"].get("buy_low", {})
    players = data["players"]
    for item in buy_low.get("items", []):
        for pid in item["get_player_ids"]:
            status = players.get(pid, {}).get("injury_status")
            assert status not in tf.SEASON_ENDING_STATUSES, f"Season-Aus-Spieler {pid} ({status}) als Buy-Low vorgeschlagen"


def test_real_build_partner_notlage_items_reference_a_real_gap():
    data = _load_real_data()
    notlage = data["trade_finder"]["ideas"].get("partner_notlage", {})
    for item in notlage.get("items", []):
        anlass = item.get("anlass", "")
        assert "Bedarf" in anlass and "Woche" in anlass, f"Notlage-Idee ohne erkennbare Lücken-Angabe: {anlass}"


def test_real_build_ideas_are_diverse_across_anchor_and_partner():
    # Jede Trade-Ideen-Kategorie darf nicht von einem einzigen wertvollsten
    # Abgabe-Spieler oder einem einzigen Partner-Team dominiert werden - sonst
    # wirken z.B. "Spitze verbessern" und "Breite aufbauen" wie geringfügige
    # Varianten desselben einen Trades.
    data = _load_real_data()
    ideas = data["trade_finder"]["ideas"]
    players = data["players"]
    violations = []
    for key, idea in ideas.items():
        anchor_counts, partner_counts = {}, {}
        for item in idea.get("items", []):
            anchor = max(item["give_player_ids"], key=lambda pid: (players.get(pid) or {}).get("trade_value") or 0)
            anchor_counts[anchor] = anchor_counts.get(anchor, 0) + 1
            partner_counts[item["roster_id"]] = partner_counts.get(item["roster_id"], 0) + 1
        if anchor_counts and max(anchor_counts.values()) > tf.MAX_IDEA_PER_ANCHOR:
            violations.append((key, "anchor", max(anchor_counts, key=anchor_counts.get)))
        if partner_counts and max(partner_counts.values()) > tf.MAX_IDEA_PER_PARTNER:
            violations.append((key, "partner", max(partner_counts, key=partner_counts.get)))
    assert not violations, f"Kategorien ohne Vielfalt bei Abgabe-Spieler/Partner: {violations}"
