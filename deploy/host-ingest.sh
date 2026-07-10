#!/usr/bin/env bash
# host-ingest.sh — Nächtliche Ingestion DIREKT auf dem Infomaniak-Host.
#
# Läuft unabhängig vom Laptop (der Host ist immer an). Ablauf:
#   Repos aktualisieren -> Korb leeren (rollierendes Fenster) -> ingestieren
#   -> validieren -> Site bauen -> in den dev-Docroot spiegeln.
# Der Agent SAMMELT nur (E4/E20); ratifiziert wird weiter lokal mit src/ratify.py.
#
# Einmalige Einrichtung: siehe docs/ingestion-betrieb.md (Abschnitt Host-Cron).
# Danach per Cron: 0 3 * * *  $HOME/ki-radar/core/deploy/host-ingest.sh >> $HOME/ki-radar/ingest.log 2>&1
set -eu

# ---- Konfiguration (bei Bedarf anpassen) --------------------------------------
WORKDIR="${KI_RADAR_WORKDIR:-$HOME/ki-radar}"
KERN_URL="https://github.com/kaspAir/KI-Technology-Radar"
INST_URL="git@github.com:kaspAir/KI-Technology-Radar-Instanz.git"   # SSH (Read-Deploy-Key)
DOCROOT="${KI_RADAR_DOCROOT:-/home/clients/2a1849703150229016af3666c2f46b09/sites/dev.ki-tech-radar.ch}"
SINCE_DAYS="${KI_RADAR_SINCE_DAYS:-30}"
MAX_ITEMS="${KI_RADAR_MAX_ITEMS:-25}"
MAX_COST="${KI_RADAR_MAX_COST:-5}"
MODEL="${KI_RADAR_MODEL:-claude-haiku-4-5-20251001}"
PRICE_IN="${KI_RADAR_PRICE_IN:-1}"; PRICE_OUT="${KI_RADAR_PRICE_OUT:-5}"

# Anthropic-Key aus separater Datei (chmod 600), NICHT im Skript/Repo.
[ -f "$HOME/.ki-radar-env" ] && . "$HOME/.ki-radar-env"
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "FEHLER: ANTHROPIC_API_KEY nicht gesetzt (erwartet in \$HOME/.ki-radar-env)"; exit 1
fi

mkdir -p "$WORKDIR"; cd "$WORKDIR"

# ---- Repos aktualisieren ------------------------------------------------------
if [ -d core/.git ]; then git -C core pull -q --ff-only; else git clone -q --depth 1 -b dev "$KERN_URL" core; fi
if [ -d instance/.git ]; then git -C instance pull -q --ff-only; else git clone -q -b dev "$INST_URL" instance; fi

# ---- Python-Umgebung (einmalig erstellt) --------------------------------------
if [ ! -x venv/bin/python ]; then python3 -m venv venv; ./venv/bin/pip install -q --upgrade pip; fi
./venv/bin/python -c "import yaml, jsonschema" 2>/dev/null || ./venv/bin/pip install -q pyyaml jsonschema
PY=./venv/bin/python

# ---- Ingestion (rollierendes Fenster) -----------------------------------------
rm -f instance/inbox/ingest-*.yaml instance/inbox/ingest-*-report.md 2>/dev/null || true
SINCE="$(date -d "${SINCE_DAYS} days ago" +%Y-%m-%d 2>/dev/null || echo "")"
echo "[$(date '+%F %T')] Ingestion: alle Quellen, seit ${SINCE:-Anfang}, max ${MAX_ITEMS}/Quelle, Deckel \$${MAX_COST}"
$PY core/src/ingest.py --instance instance --all-sources --since "$SINCE" \
    --max-items "$MAX_ITEMS" --max-output-tokens 120000 --model "$MODEL" \
    --price-in "$PRICE_IN" --price-out "$PRICE_OUT" --max-cost-usd "$MAX_COST" \
    --out instance/inbox

# ---- Validieren + Site bauen --------------------------------------------------
$PY core/src/validate.py --instance instance
$PY core/view/buildsite.py --instance instance --mode internal --out out

# ---- Veröffentlichen: in den dev-Docroot spiegeln -----------------------------
if [ -z "$DOCROOT" ]; then echo "FEHLER: DOCROOT leer"; exit 1; fi
mkdir -p "$DOCROOT"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete out/ "$DOCROOT"/
else
  cp -a out/. "$DOCROOT"/
fi
echo "[$(date '+%F %T')] fertig -> $DOCROOT"
