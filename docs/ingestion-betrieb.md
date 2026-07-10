# Ingestion-Agent — Betrieb (Kalibrierung → Server)

Der Agent (`src/ingest.py`) sammelt aus **kuratierten Quellen** (E6) und legt
`status: inbox`-Beobachtungen in die Instanz `inbox/`. Er **ratifiziert nichts** —
in den Radar hebt ein Mensch die Entwürfe (E4). Kosten laufen auf den
Anthropic-Key; deshalb harte Deckel (`--max-items`, `--max-output-tokens`) und
eine ehrliche Token-/Kostenbilanz im Laufbericht.

## 1. Mechanik testen (kostenlos)

```bash
python src/ingest.py --instance ../KI-Technology-Radar-Instanz \
  --source source.research-ml --arxiv-query "cat:cs.CL OR cat:cs.AI" \
  --since 2025-07-01 --max-items 10 --dry-run
```

Prüft Holen/Parsen/Schema/Ausgabe ohne Modellaufruf. Ergebnis: `inbox/ingest-…-dry.yaml`
+ Laufbericht.

## 2. Kalibrier-Lauf (echt, klein, misst Qualität UND Kosten)

Voraussetzung: `ANTHROPIC_API_KEY` gesetzt. Preise (aktuell, USD/1M Tokens) für
die Kostenbilanz mitgeben — nichts erfunden, du setzt die geltenden Zahlen:

```bash
export ANTHROPIC_API_KEY=sk-...
python src/ingest.py --instance ../KI-Technology-Radar-Instanz \
  --source source.research-ml --arxiv-query "cat:cs.CL OR cat:cs.AI" \
  --since 2025-07-01 --max-items 15 --max-output-tokens 20000 \
  --model claude-haiku-4-5-20251001 --price-in 1.0 --price-out 5.0
```

Danach: Laufbericht ansehen (Trefferquote, Tokens, geschätzte Kosten), ein paar
Entwürfe im Eingangskorb querlesen. Erst wenn Qualität und Kosten passen → breiter
Lauf (mehr Items, weiter zurück, mehr Quellen). Modell nach Bedarf hochstufen
(`claude-sonnet-5` / `claude-opus-4-8`).

## 3. Ratifikation (Mensch, getrennt)

Gute Entwürfe aus `inbox/ingest-*.yaml` in einen Eintrag unter `entries/` heben
(Beobachtung + Assessment + `entry.created`/`ring.changed`-Events), Rest löschen.
Validieren (`python radar.py validate --instance …`), Site bauen, deployen.

## 4. Serverbetrieb (läuft ohne deinen Laptop)

Als geplanter Job auf dem geteilten Host — zwei Wege:

- **Jenkins (empfohlen, passt zur bestehenden CI):** neuer Job auf dem
  **privaten Instanz-Repo**, Trigger `cron('H 3 * * *')` (nächtlich). Stage ruft
  `ingest.py` (Kern via Checkout/Klon), committet die neuen `inbox/`-Dateien ins
  Instanz-Repo. `ANTHROPIC_API_KEY` als Jenkins-Credential, Deckel als Job-Parameter.
  Der Job deployt NICHT und hebt nichts in den Radar — er füllt nur den Korb.
- **Cron auf dem Host:** `crontab` ruft ein Skript, das Kern+Instanz aktualisiert,
  `ingest.py` startet und den Korb ins Instanz-Repo committet.

Der Agent schreibt ausschliesslich in `inbox/` — nie in `entries/` oder ins
Event-Protokoll. So bleibt „Sammeln ≠ Geltung" (E20) auch im Automatikbetrieb wahr.
