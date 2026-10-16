# fantasy-dashboard

Statisches Fantasy-Football-Dashboard für eine Sleeper-Liga (NFL, PPR, 14 Teams).
`build.py` holt Daten ausschließlich über öffentliche APIs ohne Login (Sleeper,
FantasyCalc) und erzeugt `docs/index.html`, `docs/app.js`, `docs/styles.css`
und `docs/data.json`. Die Seite selbst ist eine reine Vanilla-JS-SPA: Filtern,
Sortieren und Navigieren passiert komplett im Browser, ohne Neuladen.

## Liga

Liga ist fest auf eine bestimmte 14-Team-PPR-Liga von Sleeper-Nutzer `Club3`
gepinnt (`fantasy/config.py`), da es zwei 14-Team-Ligen für diesen Nutzer gibt
und die gewünschte explizit bestätigt wurde.

## Build lokal ausführen

```bash
python3 build.py
```

Das Ergebnis liegt danach in `docs/`. Lokal testen:

```bash
cd docs && python3 -m http.server 8000
```

## Deployment

GitHub Pages muss in den Repo-Einstellungen einmalig auf **Branch: main,
Ordner: /docs** gestellt werden (Settings → Pages). Danach aktualisiert
`.github/workflows/daily.yml` die Seite automatisch:

- täglich um 5:30 UTC
- zusätzlich an NFL-Spieltagen (Do/So/Mo) abends
- manuell über „Run workflow“ (workflow_dispatch)

## Entwicklungsstand (Phasen)

1. ✅ Datenabruf, Design-Grundgerüst, Übersicht, Mein Roster
2. ⏳ Alle Spieler, Spieler-Detailseite, Waiver Wire
3. ⏳ Start/Sit
4. ⏳ Trade Finder, Trade-Analyzer
5. ⏳ Liga, Planer, Automatisierung (final)

## Projektstruktur

```
build.py              Orchestriert Datenabruf + generiert docs/
fantasy/
  config.py            Liga-ID, relevante Positionen, Limits
  sleeper_api.py        Sleeper-API-Client
  fantasycalc_api.py     FantasyCalc-API-Client
  scoring.py            Generischer Fantasy-Punkte-Rechner nach Liga-Scoring
  model.py               Baut data.json aus den Rohdaten
site/                  Statische Templates (werden 1:1 nach docs/ kopiert)
  index.html
  app.js
  styles.css
docs/                  Build-Ausgabe, von GitHub Pages ausgeliefert
```
