"""Automatisierte Tests für die harten Sinn-Regeln des Trade Finders:
'kein zweiter QB/TE ohne Grund', 'kein Slot bleibt leer', 'Roster-Tiefe
eingehalten', 'jeder Vorschlag hat ein Zweck-Label', 'nie K/DEF'. Diese
Regeln entscheiden, ob ein Trade-Vorschlag überhaupt angezeigt wird - ein
Build mit Verstößen wird von build.py verworfen (siehe validate_proposals)."""

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
}
RULES_SUPERFLEX = {
    "starter_counts": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2, "K": 1, "DEF": 1},
    "flex_positions": {"RB", "WR", "TE", "QB"},
    "super_flex": True,
    "num_qb_starters": 2,
}


def make_player(pid, position, trade_value=1000, bye_week=9, injury_status=None, age=25, team="KC"):
    return {
        "id": pid, "position": position, "team": team, "trade_value": trade_value,
        "bye_week": bye_week, "injury_status": injury_status, "age": age,
        "season_avg": 10.0, "avg_last3": 10.0, "games_played": 5,
    }


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


def test_no_second_qb_when_healthy_starter_is_kept():
    players = {"my_qb": make_player("my_qb", "QB", injury_status=None), "their_qb": make_player("their_qb", "QB")}
    keep_ids = ["my_qb", "some_wr"]
    give_combo = [make_player("some_wr", "WR")]
    get_combo = [players["their_qb"]]
    assert tf._redundant_position_violation(keep_ids, give_combo, get_combo, players, RULES_1QB) is True


def test_second_qb_allowed_when_giving_away_current_starter():
    players = {"my_qb": make_player("my_qb", "QB"), "their_qb1": make_player("their_qb1", "QB"), "their_qb2": make_player("their_qb2", "QB")}
    keep_ids = ["my_qb"]
    give_combo = [players["my_qb"]]
    get_combo = [players["their_qb1"], players["their_qb2"]]
    assert tf._redundant_position_violation(keep_ids, give_combo, get_combo, players, RULES_1QB) is False


def test_second_qb_allowed_when_existing_starter_is_hard_out():
    players = {"my_qb": make_player("my_qb", "QB", injury_status="IR"), "their_qb": make_player("their_qb", "QB")}
    keep_ids = ["my_qb", "filler"]
    give_combo = [make_player("filler", "WR")]
    get_combo = [players["their_qb"]]
    assert tf._redundant_position_violation(keep_ids, give_combo, get_combo, players, RULES_1QB) is False


def test_second_qb_never_flagged_in_superflex_league():
    players = {"my_qb": make_player("my_qb", "QB"), "their_qb": make_player("their_qb", "QB")}
    keep_ids = ["my_qb", "filler"]
    give_combo = [make_player("filler", "WR")]
    get_combo = [players["their_qb"]]
    assert tf._redundant_position_violation(keep_ids, give_combo, get_combo, players, RULES_SUPERFLEX) is False


def test_no_third_te_when_two_healthy_tes_already_kept():
    players = {
        "te1": make_player("te1", "TE"), "te2": make_player("te2", "TE"), "their_te": make_player("their_te", "TE"),
    }
    keep_ids = ["te1", "te2", "filler"]
    give_combo = [make_player("filler", "WR")]
    get_combo = [players["their_te"]]
    assert tf._redundant_position_violation(keep_ids, give_combo, get_combo, players, RULES_1QB) is True


def test_lineup_legality_requires_all_mandatory_positions():
    players = {}
    ids = []
    for i, pos in enumerate(["RB", "RB", "WR", "WR", "TE", "RB", "WR"]):
        pid = f"p{i}"
        players[pid] = make_player(pid, pos)
        ids.append(pid)
    # Kein einziger QB auf dem Kader -> Pflicht-Slot kann nicht gefüllt werden
    legal, reason = tf._lineup_legality(ids, players, RULES_1QB)
    assert legal is False
    assert "QB" in reason


def test_lineup_legality_requires_bench_depth():
    players = {}
    ids = []
    counts = {"QB": 1, "RB": 2, "WR": 2, "TE": 1}  # genau die Pflicht-Slots, keine Tiefe
    for pos, n in counts.items():
        for i in range(n):
            pid = f"{pos}{i}"
            players[pid] = make_player(pid, pos)
            ids.append(pid)
    legal, reason = tf._lineup_legality(ids, players, RULES_1QB)
    assert legal is False


def test_lineup_legality_passes_with_full_roster_and_depth():
    players = {}
    ids = []
    # K/DEF immer dabei: die werden nie getradet, bleiben also in jedem
    # post-trade player_ids unverändert erhalten.
    counts = {"QB": 2, "RB": 4, "WR": 4, "TE": 2, "K": 1, "DEF": 1}
    for pos, n in counts.items():
        for i in range(n):
            pid = f"{pos}{i}"
            players[pid] = make_player(pid, pos)
            ids.append(pid)
    legal, reason = tf._lineup_legality(ids, players, RULES_1QB)
    assert legal is True
    assert reason is None


def test_purpose_labels_empty_when_nothing_qualifies():
    give_combo = [make_player("give1", "WR", trade_value=1000)]
    get_combo = [make_player("get1", "WR", trade_value=1000)]
    labels = tf._purpose_labels(
        give_combo, get_combo, my_weakness={}, their_weakness={}, lineup_delta=0.0,
        my_starters_by_pos={}, my_roster_by_pos={}, bye_calendar_weeks=set(),
        sell_high_ids=set(), buy_low_ids=set(), their_need_fit=0.0,
    )
    assert labels == []


def test_purpose_labels_upgrade_when_lineup_gain_is_clear():
    give_combo = [make_player("give1", "WR", trade_value=500)]
    get_combo = [make_player("get1", "WR", trade_value=600)]
    labels = tf._purpose_labels(
        give_combo, get_combo, my_weakness={}, their_weakness={}, lineup_delta=5.0,
        my_starters_by_pos={}, my_roster_by_pos={}, bye_calendar_weeks=set(),
        sell_high_ids=set(), buy_low_ids=set(), their_need_fit=0.0,
    )
    assert any(l.startswith("Upgrade") for l in labels)


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


def test_validate_proposals_clean_list_has_no_errors():
    players = {"wr1": make_player("wr1", "WR"), "wr2": make_player("wr2", "WR")}
    proposals = {"proposals": [_sample_proposal()]}
    errors = tf.validate_proposals(proposals, players)
    assert errors == []


def test_real_build_output_passes_all_invariants():
    """Integrationstest: prüft die Invarianten gegen die zuletzt gebaute
    echte data.json, falls vorhanden. Übersprungen bei frischem Checkout
    ohne vorherigen Build-Lauf."""
    data_path = ROOT / "docs" / "data.json"
    if not data_path.exists():
        pytest.skip("docs/data.json nicht vorhanden - noch kein Build-Lauf")
    data = json.loads(data_path.read_text(encoding="utf-8"))
    errors = tf.validate_proposals(data["trade_finder"], data["players"])
    assert errors == [], f"{len(errors)} Invarianten-Verstöße im letzten Build: {errors[:5]}"
