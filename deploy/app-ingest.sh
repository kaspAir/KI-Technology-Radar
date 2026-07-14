#!/usr/bin/env bash
# app-ingest.sh — nächtliche Ingestion für den MVP: holt die neuesten Belege
# (RSS/Atom-Feeds + arXiv) der letzten 24 h aus den kuratierten Quellen (E6) und
# spiegelt die neuen Kandidaten in die MariaDB (-> erscheinen unter „Vorschläge").
#
# Der Agent SAMMELT nur und ENTWIRFT (E4/E20); ratifiziert wird weiter von Hand.
# Kosten laufen auf ANTHROPIC_API_KEY, mit hartem $-Deckel.
#
# Cron (Infomaniak), z.B. 03:15 Uhr:
#   15 3 * * *  /bin/sh $HOME/radar-app/deploy/app-ingest.sh >> $HOME/radar-app/logs/ingest.log 2>&1
set -eu

APP="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$APP"

# Web-Secrets (RADAR_DB, RADAR_INSTANCE) + separat der API-Key (nicht im Web-.env).
set -a; [ -f .env ] && . ./.env; set +a
[ -f "$HOME/.ki-radar-env" ] && . "$HOME/.ki-radar-env"
: "${RADAR_DB:?RADAR_DB fehlt (.env)}"
: "${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY fehlt (erwartet in \$HOME/.ki-radar-env, chmod 600)}"
export RADAR_DB ANTHROPIC_API_KEY

INSTANCE="${RADAR_INSTANCE:-$APP/../radar-instance}"          # Quellen + Bewertungsraster
POOL="${RADAR_POOL:-$HOME/radar-pool/pool.yaml}"             # akkumulierend, AUSSERHALB Git
DAYS="${RADAR_INGEST_DAYS:-1}"                               # Fenster (Tage)
mkdir -p "$(dirname "$POOL")" logs

# Dedup-Basis einmalig aus dem committeten Pool übernehmen (keine Neu-Entwürfe der
# bereits geseedeten 162 Belege).
if [ ! -f "$POOL" ] && [ -f "$INSTANCE/inbox/pool.yaml" ]; then
  cp "$INSTANCE/inbox/pool.yaml" "$POOL"
fi

if [ ! -d "$INSTANCE/sources" ]; then
  echo "FEHLER: keine Instanz-Quellen unter $INSTANCE (RADAR_INSTANCE prüfen)."; exit 1
fi

SINCE="$(date -d "${DAYS} day ago" +%Y-%m-%d 2>/dev/null || echo "")"
echo "[$(date '+%F %T')] Ingestion: alle Quellen, seit ${SINCE:-Anfang} (Fenster ${DAYS}x24h), Deckel \$${RADAR_INGEST_MAX_COST:-5}"

.venv/bin/python src/ingest.py --instance "$INSTANCE" --all-sources --since "$SINCE" \
    --max-items "${RADAR_INGEST_MAX_ITEMS:-25}" \
    --max-output-tokens "${RADAR_INGEST_MAX_TOKENS:-120000}" \
    --model "${RADAR_INGEST_MODEL:-claude-haiku-4-5-20251001}" \
    --price-in 1 --price-out 5 --max-cost-usd "${RADAR_INGEST_MAX_COST:-5}" \
    --pool "$POOL" --out "$(dirname "$POOL")"

echo "[$(date '+%F %T')] Spiegle neue Kandidaten in die MariaDB (dedup per URL)"
.venv/bin/python -m app.seed "$POOL"
echo "[$(date '+%F %T')] fertig — neue Vorschläge stehen sofort im MVP."
