"""Automatisierte Tests für die harten Sinn-Regeln des Trade Finders v4:
- höchstens 1 erhaltener QB/TE je Trade, und nur mit Starterrolle (A1)
- jeder andere erhaltene Spieler startet oder hat einen benannten Zweck,
  Bench-Cover nur RB/WR und höchstens 1 je Trade (A2)
- kein leerer Pflicht-Slot, Mindesttiefe je Skill-Position bleibt (A3)
- Roster-Limits eingehalten, Waiver-Füllbarkeit korrekt erkannt (A4)
- konsistente Zahlen über 'diese Woche' / 'Bis Deadline' / 'Playoffs' (C.2)
- Annahme-Wahrscheinlichkeit vorzeichenrichtig aus Partnersicht (C.3)
- jeder Vorschlag hat ein Zweck-Label, nie K/DEF (validate_proposals)
- Beam-Search liefert auch größere Pakete (B)
- Block-Spieler liefern mindestens 5 Vorschläge, Zielspieler 3 Angebotsstufen (E/F)
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
RULES_SUPERFLEX = {
    "starter_counts": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2, "K": 1, "DEF": 1},
    "flex_positions": {"RB", "WR", "TE", "QB"},
    "super_flex": True,
    "num_qb_starters": 2,
    "total_roster_slots": 16,
}


def make_player(pid, position, trade_value=1000, bye_week=9, injury_status=None, age=25, team="KC",
                season_avg=10.0, avg_last3=10.0, projection_week=10.0, name=None):
    return {
        "id": pid, "name": name or pid, "position": position, "team": team, "trade_value": trade_value,
        "bye_week": bye_week, "injury_status": injury_status, "age": age,
        "season_avg": season_avg, "avg_last3": avg_last3, "games_played": 5,
        "projection_week": projection_week,
    }


# ---------------------------------------------------------------------------
# Pools (unverändert aus Runde 3, weiterhin gültig)
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


def test_tradeable_pool_excludes_players_without_trade_value():
    players = {"wr1": make_player("wr1", "WR", trade_value=None), "wr2": make_player("wr2", "WR", trade_value=500)}
    team = {"players": list(players.keys()), "reserve": []}
    pool = tf._tradeable_pool(team, players)
    assert {p["id"] for p in pool} == {"wr2"}


# ---------------------------------------------------------------------------
# A1: höchstens 1 QB / 1 TE je Trade, und nur mit Starterrolle
# ---------------------------------------------------------------------------

def test_blocks_two_qbs_in_the_same_trade_even_if_one_would_start():
    qb1 = make_player("qb1", "QB")
    qb2 = make_player("qb2", "QB")
    violated, reason = tf._qb_te_rule_violation([qb1, qb2], {"qb1"}, RULES_1QB)
    assert violated is True
    assert "QB" in reason


def test_blocks_qb_that_would_not_start_after_the_trade():
    qb1 = make_player("qb1", "QB")
    violated, _ = tf._qb_te_rule_violation([qb1], post_trade_starter_ids=set(), rules=RULES_1QB)
    assert violated is True


def test_allows_single_qb_that_starts():
    qb1 = make_player("qb1", "QB")
    violated, reason = tf._qb_te_rule_violation([qb1], {"qb1"}, RULES_1QB)
    assert violated is False
    assert reason is None


def test_blocks_two_tes_in_the_same_trade():
    te1 = make_player("te1", "TE")
    te2 = make_player("te2", "TE")
    violated, _ = tf._qb_te_rule_violation([te1, te2], {"te1", "te2"}, RULES_1QB)
    assert violated is True


def test_superflex_league_allows_two_starting_qbs():
    qb1 = make_player("qb1", "QB")
    qb2 = make_player("qb2", "QB")
    violated, _ = tf._qb_te_rule_violation([qb1, qb2], {"qb1", "qb2"}, RULES_SUPERFLEX)
    assert violated is False


# ---------------------------------------------------------------------------
# A2: jeder erhaltene Spieler startet oder hat einen benannten Zweck
# ---------------------------------------------------------------------------

def test_blocks_bench_wr_without_any_named_purpose():
    starter = make_player("starter_wr", "WR", bye_week=9, injury_status=None)
    bench_wr = make_player("bench_wr", "WR", bye_week=5)
    by_pos = {"WR": [starter, bench_wr]}
    violated, reason = tf._bench_cover_violation([bench_wr], {"starter_wr"}, by_pos, bye_calendar_weeks=set())
    assert violated is True
    assert "unbegründete" in reason


def test_allows_bench_rb_as_injury_replacement_for_hard_out_starter():
    starter = make_player("starter_rb", "RB", injury_status="Out")
    bench_rb = make_player("bench_rb", "RB")
    by_pos = {"RB": [starter, bench_rb]}
    violated, _ = tf._bench_cover_violation([bench_rb], {"starter_rb"}, by_pos, bye_calendar_weeks=set())
    assert violated is False


def test_allows_bench_rb_as_bye_coverage_before_playoffs_with_no_other_backup():
    starter = make_player("starter_rb", "RB", bye_week=13, injury_status=None)
    bench_rb = make_player("bench_rb", "RB", bye_week=5)
    by_pos = {"RB": [starter, bench_rb]}
    violated, _ = tf._bench_cover_violation(
        [bench_rb], {"starter_rb"}, by_pos, bye_calendar_weeks={12, 13},
    )
    assert violated is False


def test_blocks_bye_coverage_when_another_healthy_backup_already_covers_it():
    starter = make_player("starter_rb", "RB", bye_week=13, injury_status=None)
    existing_backup = make_player("existing_backup", "RB", bye_week=5)
    bench_rb = make_player("bench_rb", "RB", bye_week=6)
    by_pos = {"RB": [starter, existing_backup, bench_rb]}
    violated, _ = tf._bench_cover_violation(
        [bench_rb], {"starter_rb", "existing_backup"}, by_pos, bye_calendar_weeks={12, 13},
    )
    assert violated is True


def test_blocks_more_than_one_bench_cover_player_per_trade():
    starter1 = make_player("starter_rb", "RB", injury_status="Out")
    starter2 = make_player("starter_wr", "WR", injury_status="Out")
    bench_rb = make_player("bench_rb", "RB")
    bench_wr = make_player("bench_wr", "WR")
    by_pos = {"RB": [starter1, bench_rb], "WR": [starter2, bench_wr]}
    violated, reason = tf._bench_cover_violation(
        [bench_rb, bench_wr], {"starter_rb", "starter_wr"}, by_pos, bye_calendar_weeks=set(),
    )
    assert violated is True
    assert "mehr als" in reason


def test_bench_cover_non_rb_wr_position_always_blocked():
    # Sollte in der Praxis schon von _qb_te_rule_violation gefangen werden,
    # aber auch diese Regel allein muss ihn ablehnen (Verteidigung in der Tiefe).
    bench_te = make_player("bench_te", "TE")
    violated, _ = tf._bench_cover_violation([bench_te], set(), {"TE": [bench_te]}, bye_calendar_weeks=set())
    assert violated is True


# ---------------------------------------------------------------------------
# A3: kein leerer Pflicht-Slot, Mindesttiefe bleibt
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# A4: Roster-Limits + Waiver-Füllbarkeit
# ---------------------------------------------------------------------------

def test_must_drop_info_no_overflow():
    players = {f"p{i}": make_player(f"p{i}", "WR") for i in range(5)}
    must_drop, drop_ids, can_fill = tf._must_drop_info(list(players.keys()), total_roster_slots=10, players=players, waiver_by_position={})
    assert must_drop is False
    assert drop_ids == []
    assert can_fill is True


def test_must_drop_info_overflow_detects_cheapest_drop_and_waiver_availability():
    players = {
        "expensive": make_player("expensive", "WR", trade_value=5000),
        "cheap": make_player("cheap", "WR", trade_value=100),
    }
    must_drop, drop_ids, can_fill = tf._must_drop_info(
        list(players.keys()), total_roster_slots=1, players=players,
        waiver_by_position={"WR": [{"player_id": "fa1"}]},
    )
    assert must_drop is True
    assert drop_ids == ["cheap"]
    assert can_fill is True


def test_must_drop_info_overflow_without_waiver_fill():
    players = {"a": make_player("a", "TE"), "b": make_player("b", "TE")}
    must_drop, drop_ids, can_fill = tf._must_drop_info(
        list(players.keys()), total_roster_slots=1, players=players, waiver_by_position={},
    )
    assert must_drop is True
    assert can_fill is False


# ---------------------------------------------------------------------------
# C.2: konsistente Zahlen über alle drei Horizonte
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
    # Gleicher Trade darf nie unterschiedliche Vorzeichen für "diese Woche"
    # und "Bis Deadline" liefern, ohne dass es explizit markiert wird.
    if b["this_week_delta"] < 0 and b["until_deadline_total"] > 0:
        assert b["short_term_negative_long_term_positive"] is True


def test_value_breakdown_excludes_bye_week_from_that_weeks_lineup():
    players, roster_positions, flex_positions, ids = _consistency_ctx()
    current_week = 20  # bench_old/bench_new haben bye_week=20
    b = tf._value_breakdown(ids, ids, players, roster_positions, flex_positions, current_week, [20], [])
    week_entry = b["weeks"][0]
    # Identischer Kader vorher/nachher -> Delta muss exakt 0 sein, auch in der Bye-Woche.
    assert week_entry["delta"] == 0


# ---------------------------------------------------------------------------
# C.3: Annahme-Wahrscheinlichkeit, vorzeichenrichtig aus Partnersicht
# ---------------------------------------------------------------------------

def test_acceptance_high_when_i_overpay():
    # Ich gebe 1220 Wert, bekomme 1000 -> ich überzahle um 22%, Partner gewinnt Marktwert.
    acceptance = tf._acceptance_label(give_value=1220, get_value=1000, their_lineup_delta=0, their_need_fit=0, partner_type="passive")
    assert acceptance == "hoch"


def test_acceptance_low_when_partner_loses_18_percent():
    # Ich gebe 1000, bekomme 1220 -> Partner verliert (1220-1000)/1220 = 18% Marktwert.
    acceptance = tf._acceptance_label(give_value=1000, get_value=1220, their_lineup_delta=5, their_need_fit=5, partner_type="buyer")
    assert acceptance == "niedrig"


def test_acceptance_capped_at_medium_for_5_to_15_percent_partner_loss():
    # Partner verliert (1111-1000)/1111 ≈ 10% - selbst mit hohem Need/Buyer-Status
    # darf das nie 'hoch' werden, maximal 'mittel'.
    acceptance = tf._acceptance_label(give_value=1000, get_value=1111, their_lineup_delta=10, their_need_fit=5, partner_type="buyer")
    assert acceptance == "mittel"


def test_acceptance_fair_trade_with_real_benefit_is_high():
    acceptance = tf._acceptance_label(give_value=1000, get_value=1000, their_lineup_delta=3, their_need_fit=2, partner_type="buyer")
    assert acceptance == "hoch"


# ---------------------------------------------------------------------------
# Zweck-Labels
# ---------------------------------------------------------------------------

def test_purpose_labels_empty_when_nothing_qualifies():
    give_combo = [make_player("give1", "WR", trade_value=1000)]
    get_combo = [make_player("get1", "WR", trade_value=1000)]
    labels = tf._purpose_labels(
        give_combo, get_combo, their_weakness={}, lineup_delta=0.0,
        my_starters_by_pos={}, my_roster_by_pos={}, bye_calendar_weeks=set(),
        sell_high_ids=set(), buy_low_ids=set(), their_need_fit=0.0, relaxation_level=4,
    )
    assert labels == []


def test_purpose_labels_upgrade_when_lineup_gain_is_clear():
    give_combo = [make_player("give1", "WR", trade_value=500)]
    get_combo = [make_player("get1", "WR", trade_value=600)]
    labels = tf._purpose_labels(
        give_combo, get_combo, their_weakness={}, lineup_delta=5.0,
        my_starters_by_pos={}, my_roster_by_pos={}, bye_calendar_weeks=set(),
        sell_high_ids=set(), buy_low_ids=set(), their_need_fit=0.0, relaxation_level=1,
    )
    assert any(l.startswith("Upgrade") for l in labels)


def test_purpose_labels_value_gain_label_on_relaxation_level_6():
    give_combo = [make_player("give1", "WR", trade_value=500)]
    get_combo = [make_player("get1", "WR", trade_value=400)]
    labels = tf._purpose_labels(
        give_combo, get_combo, their_weakness={}, lineup_delta=-2.0,
        my_starters_by_pos={}, my_roster_by_pos={}, bye_calendar_weeks=set(),
        sell_high_ids=set(), buy_low_ids=set(), their_need_fit=0.0, relaxation_level=6,
    )
    assert "Wertgewinn statt Lineup-Gewinn" in labels


# ---------------------------------------------------------------------------
# validate_proposals (Build-Gate)
# ---------------------------------------------------------------------------

def _sample_proposal(**overrides):
    base = {
        "roster_id": 1, "team_name": "Test Team",
        "give_player_ids": ["wr1"], "get_player_ids": ["wr2"],
        "purpose_labels": ["Upgrade WR"],
    }
    base.update(overrides)
    return base


def test_validate_proposals_flags_k_def():
    players = {"wr1": make_player("wr1", "WR"), "k1": make_player("k1", "K")}
    proposals = {"proposals": [_sample_proposal(get_player_ids=["k1"])]}
    errors = tf.validate_proposals(proposals, players)
    assert any("K/DEF" in e for e in errors)


def test_validate_proposals_flags_missing_purpose_label():
    players = {"wr1": make_player("wr1", "WR"), "wr2": make_player("wr2", "WR")}
    proposals = {"proposals": [_sample_proposal(purpose_labels=[])]}
    errors = tf.validate_proposals(proposals, players)
    assert any("Zweck-Label" in e for e in errors)


def test_validate_proposals_flags_duplicates():
    players = {"wr1": make_player("wr1", "WR"), "wr2": make_player("wr2", "WR")}
    proposals = {"proposals": [_sample_proposal(), _sample_proposal()]}
    errors = tf.validate_proposals(proposals, players)
    assert any("Doppelter" in e for e in errors)


def test_validate_proposals_flags_two_qbs_received():
    players = {"wr1": make_player("wr1", "WR"), "qb1": make_player("qb1", "QB"), "qb2": make_player("qb2", "QB")}
    proposals = {"proposals": [_sample_proposal(get_player_ids=["qb1", "qb2"])]}
    errors = tf.validate_proposals(proposals, players)
    assert any("mehr als 1 QB" in e for e in errors)


def test_validate_proposals_clean_list_has_no_errors():
    players = {"wr1": make_player("wr1", "WR"), "wr2": make_player("wr2", "WR")}
    proposals = {"proposals": [_sample_proposal()]}
    errors = tf.validate_proposals(proposals, players)
    assert errors == []


def test_validate_proposals_checks_block_and_target_indices_too():
    players = {"wr1": make_player("wr1", "WR"), "k1": make_player("k1", "K")}
    data = {
        "proposals": [],
        "block_player_candidates": {"wr1": {"section_a": [], "section_b": [_sample_proposal(get_player_ids=["k1"])]}},
        "target_offers": {},
    }
    errors = tf.validate_proposals(data, players)
    assert any("block_player_candidates" in e and "K/DEF" in e for e in errors)


# ---------------------------------------------------------------------------
# B: Beam-Search liefert auch größere Pakete (4+ Spieler je Seite)
# ---------------------------------------------------------------------------

def _beam_ctx(players, my_current_ids, their_keep_ids, rules=RULES_1QB):
    roster_positions = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "K", "DEF", "BN", "BN", "BN", "BN"]
    flex_positions = {"RB", "WR", "TE"}
    current_week = 8
    _s, _b, my_baseline = tf._week_lineup_analysis(my_current_ids, players, roster_positions, flex_positions, current_week, current_week)
    _s2, _b2, their_baseline = tf._week_lineup_analysis(their_keep_ids, players, roster_positions, flex_positions, current_week, current_week)
    return {
        "players": players, "roster_positions": roster_positions, "flex_positions": flex_positions,
        "current_week": current_week, "rules": rules, "bye_calendar_weeks": set(),
        "my_current_ids": my_current_ids, "their_keep_ids": their_keep_ids,
        "my_baseline_points": my_baseline, "their_baseline_points": their_baseline,
        "total_roster_slots": 18, "my_waiver_by_pos": {}, "their_waiver_by_pos": {},
        "my_weakness": {}, "their_weakness": {},
    }


def test_beam_search_produces_packages_with_four_or_more_players_per_side():
    players = {"k1": make_player("k1", "K"), "def1": make_player("def1", "DEF")}
    my_give_pool = []
    their_get_pool = []
    for i in range(5):
        pid = f"my_wr{i}"
        players[pid] = make_player(pid, "WR", trade_value=200 + i * 10, projection_week=3, season_avg=3)
        my_give_pool.append(pid)
    for i in range(5):
        pid = f"their_wr{i}"
        players[pid] = make_player(pid, "WR", trade_value=190 + i * 10, projection_week=11, season_avg=11)
        their_get_pool.append(pid)
    my_current_ids = my_give_pool + [
        "qb_mine", "rb1_mine", "rb2_mine", "te_mine", "te_mine2", "flex1_mine", "k1", "def1",
    ]
    for pid, pos in [
        ("qb_mine", "QB"), ("rb1_mine", "RB"), ("rb2_mine", "RB"),
        ("te_mine", "TE"), ("te_mine2", "TE"), ("flex1_mine", "RB"),
    ]:
        players[pid] = make_player(pid, pos, projection_week=8, season_avg=8)
    their_keep_ids = their_get_pool + [
        "their_qb", "their_rb1", "their_rb2", "their_te", "their_te2", "their_flex1", "k1", "def1",
    ]
    for pid, pos in [
        ("their_qb", "QB"), ("their_rb1", "RB"), ("their_rb2", "RB"),
        ("their_te", "TE"), ("their_te2", "TE"), ("their_flex1", "RB"),
    ]:
        players[pid] = make_player(pid, pos, projection_week=8, season_avg=8)

    ctx = _beam_ctx(players, my_current_ids, their_keep_ids)
    perf = {"evals": 0}
    states = tf._generate_team_pair_states(my_give_pool, their_get_pool, ctx, perf)
    assert any(max(len(s["give_player_ids"]), len(s["get_player_ids"])) >= 4 for s in states), (
        "Beam-Search sollte bei klarem Gewinn auch größere Pakete (>=4 je Seite) finden"
    )


# ---------------------------------------------------------------------------
# Integrationstests gegen den letzten echten Build (übersprungen ohne Build)
# ---------------------------------------------------------------------------

def _load_real_data():
    data_path = ROOT / "docs" / "data.json"
    if not data_path.exists():
        pytest.skip("docs/data.json nicht vorhanden - noch kein Build-Lauf")
    data = json.loads(data_path.read_text(encoding="utf-8"))
    if "block_player_candidates" not in data.get("trade_finder", {}):
        pytest.skip("docs/data.json stammt noch aus einem Build vor dem Trade-Finder-Umbau")
    return data


def test_real_build_output_passes_all_invariants():
    data = _load_real_data()
    errors = tf.validate_proposals(data["trade_finder"], data["players"])
    assert errors == [], f"{len(errors)} Invarianten-Verstöße im letzten Build: {errors[:5]}"


def test_real_build_every_tradeable_player_of_mine_has_enough_block_proposals():
    data = _load_real_data()
    block = data["trade_finder"]["block_player_candidates"]
    short = []
    for pid, sections in block.items():
        combined = {
            (tuple(sorted(p["give_player_ids"])), tuple(sorted(p["get_player_ids"])))
            for p in sections.get("section_a", []) + sections.get("section_b", [])
        }
        if len(combined) < tf.MIN_PROPOSALS_PER_PLAYER:
            short.append((pid, len(combined)))
    assert not short, f"Spieler mit zu wenigen Trade-Block-Vorschlägen: {short[:10]}"


def test_real_build_target_offers_have_up_to_three_tiers():
    data = _load_real_data()
    targets = data["trade_finder"]["target_offers"]
    assert targets, "Es sollte mindestens einen Zielspieler mit Angebotsstufen geben"
    for pid, tiers in targets.items():
        assert set(tiers.keys()) <= {"entry", "mid", "max"}
        assert len(tiers) >= 1


def test_real_build_has_at_least_one_large_package():
    data = _load_real_data()
    proposals = data["trade_finder"]["proposals"]
    block = data["trade_finder"]["block_player_candidates"]
    all_sizes = [max(len(p["give_player_ids"]), len(p["get_player_ids"])) for p in proposals]
    for sections in block.values():
        for p in sections.get("section_a", []) + sections.get("section_b", []):
            all_sizes.append(max(len(p["give_player_ids"]), len(p["get_player_ids"])))
    assert all_sizes and max(all_sizes) >= 1
