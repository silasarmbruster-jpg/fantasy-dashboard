"""Verwaltet history.json im Repo-Root: Trade-Wert-Verlauf über die Zeit,
damit die Spieler-Detailansicht eine kleine Kurve zeigen kann. Wird bei
jedem Build-Lauf um den aktuellen Lauf ergänzt und auf die letzten
MAX_RUNS Läufe begrenzt, damit die Datei nicht unbegrenzt wächst."""

import json

MAX_RUNS = 60
MAX_POINTS_PER_PLAYER = 14


def load(path):
    if not path.exists():
        return {"runs": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "runs" not in data:
            return {"runs": []}
        return data
    except (json.JSONDecodeError, OSError):
        return {"runs": []}


def append_and_save(path, run_date, trade_values):
    hist = load(path)
    values = {pid: tv["value"] for pid, tv in trade_values.items() if tv.get("value") is not None}
    hist["runs"].append({"date": run_date, "values": values})
    hist["runs"] = hist["runs"][-MAX_RUNS:]
    path.write_text(json.dumps(hist, separators=(",", ":")), encoding="utf-8")
    return hist


def player_histories(hist, player_ids):
    """player_id -> [{date, value}, ...] (letzte MAX_POINTS_PER_PLAYER Punkte)."""
    out = {pid: [] for pid in player_ids}
    for run in hist["runs"]:
        values = run.get("values") or {}
        for pid in player_ids:
            v = values.get(pid)
            if v is not None:
                out[pid].append({"date": run["date"], "value": v})
    return {pid: points[-MAX_POINTS_PER_PLAYER:] for pid, points in out.items()}
