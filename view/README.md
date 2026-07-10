# view — Radar-Ansicht (read-only)

`render.py` erzeugt aus einer Instanz eine selbstenthaltene HTML-Radar-Ansicht.
Das ist eine **Reporting-Ansicht zum Anschauen**, nicht die interaktive
Produkt-UI (die kommt in einem späteren Release, E1).

```bash
python view/render.py --instance ../KI-Technology-Radar-Instanz --out view/output/radar.html
```

Danach `view/output/radar.html` im Browser öffnen (Doppelklick).

## Zwei Modi — wichtig für den Datenschutz

- `--mode internal` (Standard): **volle Sicht** inkl. `relevance_org`,
  Handlungsdruck, Momentum. Enthält **private Wertung (E25)** — **nicht
  veröffentlichen**, nur intern öffnen.
- `--mode public`: nur **Allowlist-Felder** (name, area, ring, first_seen) gemäss
  E26 — für eine *bewusste* Veröffentlichung. Zeigt nie die private Wertung.

Eine Veröffentlichung des Radars (öffentliche URL) ist damit ein **bewusster
Schritt** (E26): dafür ausschliesslich die `public`-Ansicht verwenden.
