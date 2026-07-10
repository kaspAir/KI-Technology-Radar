# Ingestion-Agent — Betrieb (Kalibrierung → Server)

Der Agent (`src/ingest.py`) sammelt aus **kuratierten Quellen** (E6) und legt
KI-bezogene Treffer als **Kandidaten** (nach Branche zugeordnet) in die Instanz
`inbox/`. Er **ratifiziert nichts** — in den Radar hebt ein Mensch die Entwürfe (E4).
Kosten laufen auf den Anthropic-Key; deshalb harte Deckel (`--max-items` je Quelle,
`--max-output-tokens`, `--max-cost-usd`) und eine ehrliche Bilanz im Laufbericht.

**Quellen** stehen in `<instance>/sources/sources.yaml`. Eine Quelle mit `ingest:`-Block
wird automatisch abgerufen (`type: arxiv` mit `query`, oder `type: feed` mit RSS/Atom-
`feed`-URL). `--all-sources` arbeitet alle davon ab; `--source <id> --arxiv-query <q>`
nur eine (arXiv). Deep-Links zeigen auf den echten Artikel, nicht die Startseite.

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

## 4. Serverbetrieb — Cron auf dem Infomaniak-Host (läuft ohne Laptop)

WICHTIG: Jenkins läuft lokal (Docker auf dem Laptop). Für echten Laptop-freien
Betrieb läuft die nächtliche Ingestion **auf dem Host** (immer an, hat Python +
Key + ist das Deploy-Ziel). Skript: `deploy/host-ingest.sh` (Repos aktualisieren →
Korb leeren → ingestieren → validieren → Site bauen → in den dev-Docroot spiegeln).

### Einmalige Einrichtung (per SSH auf dem Host)

```bash
# 1) Read-Deploy-Key fürs PRIVATE Instanz-Repo
ssh-keygen -t ed25519 -f ~/.ssh/ki-radar -N ""
cat ~/.ssh/ki-radar.pub    # -> GitHub: Instanz-Repo > Settings > Deploy keys > Add (read-only)
printf 'Host github.com\n  IdentityFile ~/.ssh/ki-radar\n' >> ~/.ssh/config

# 2) Repos anlegen
mkdir -p ~/ki-radar && cd ~/ki-radar
git clone --depth 1 -b dev https://github.com/kaspAir/KI-Technology-Radar core
git clone -b dev git@github.com:kaspAir/KI-Technology-Radar-Instanz.git instance

# 3) Anthropic-Key in geschützte Datei (NICHT ins Repo)
printf 'export ANTHROPIC_API_KEY=sk-ant-...\n' > ~/.ki-radar-env && chmod 600 ~/.ki-radar-env

# 4) Testlauf von Hand (prüft Python/venv/Netz/Docroot)
bash ~/ki-radar/core/deploy/host-ingest.sh
```

Docroot ggf. anpassen: `export KI_RADAR_DOCROOT=…` (Default = dev.ki-tech-radar.ch-Pfad).
Für einen grösseren Erstlauf: `KI_RADAR_SINCE_DAYS=365 KI_RADAR_MAX_ITEMS=80 bash …/host-ingest.sh`.

### Cron eintragen (Infomaniak: Cron-Manager oder `crontab -e`)

```
0 3 * * *  bash $HOME/ki-radar/core/deploy/host-ingest.sh >> $HOME/ki-radar/ingest.log 2>&1
```

Der Host pullt vor jedem Lauf das Instanz-Repo → deine lokal ratifizierten Einträge
(via `src/ratify.py` + push) landen automatisch im nächtlichen Build. Der Agent
schreibt nur in `inbox/` (E4/E20). Jenkins bleibt für manuelle dev/test/int/main-Builds.
