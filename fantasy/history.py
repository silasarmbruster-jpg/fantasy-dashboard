"""Verwaltet history.json im Repo-Root: Trade-Wert-Verlauf über die Zeit,
damit die Spieler-Detailansicht eine kleine Kurve zeigen kann. Höchstens
ein Eintrag pro Kalendertag (mehrere Läufe am selben Tag überschreiben den
Tageseintrag statt einen neuen anzuhängen - an Spieltagen läuft der
Workflow bis zu zweimal), auf die letzten MAX_RUNS Tage begrenzt, damit
die Datei nicht unbegrenzt wächst."""

import json

MAX_RUNS = 60  # Tage, nicht Build-Läufe (siehe build_updated)
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


def build_updated(path, run_date, trade_values):
    """Hängt den aktuellen Lauf im Speicher an (oder überschreibt den
    heutigen Eintrag, falls schon einer existiert), schreibt aber noch
    nichts auf die Platte - das macht erst save(), nachdem die
    Plausibilitätsprüfung des Build-Laufs bestanden hat."""
    hist = load(path)
    values = {pid: tv["value"] for pid, tv in trade_values.items() if tv.get("value") is not None}
    today = run_date[:10]  # YYYY-MM-DD-Teil des ISO-Zeitstempels
    if hist["runs"] and hist["runs"][-1]["date"][:10] == today:
        hist["runs"][-1] = {"date": run_date, "values": values}
    else:
        hist["runs"].append({"date": run_date, "values": values})
    hist["runs"] = hist["runs"][-MAX_RUNS:]
    return hist


def save(path, hist):
    path.write_text(json.dumps(hist, separators=(",", ":")), encoding="utf-8")


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
