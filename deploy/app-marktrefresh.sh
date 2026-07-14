#!/usr/bin/env bash
# app-marktrefresh.sh — monatlicher ENTWURF zur Aktualisierung der Anbieter-Landschaft.
#
# Sammelt die Markt-/Anbieter-Signale des Monats aus dem Pool und entwirft je Firma
# „Tendenz + Belege" (mit echten URLs, E8) in eine Review-Datei. anbieter.yaml wird
# NICHT verändert — der Kurator ratifiziert von Hand (Ampel anpassen), pusht die
# Instanz, dann zeigt /markt nach dem nächsten app-run.sh den neuen Stand.
#
# Cron (Infomaniak), 1. des Monats 04:00:
#   0 4 1 * *  /bin/sh $HOME/radar-app/deploy/app-marktrefresh.sh >> $HOME/radar-app/logs/marktrefresh.log 2>&1
set -eu

APP="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$APP"

set -a; [ -f .env ] && . ./.env; set +a
[ -f "$HOME/.ki-radar-env" ] && . "$HOME/.ki-radar-env"
: "${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY fehlt (erwartet in \$HOME/.ki-radar-env oder .env)}"
export ANTHROPIC_API_KEY

INSTANCE="${RADAR_INSTANCE:-$APP/../radar-instance}"
POOL="${RADAR_POOL:-$HOME/radar-pool/pool.yaml}"
MONTH="$(date +%Y-%m)"
OUT="$APP/reviews/anbieter-vorschlag-$MONTH.md"
mkdir -p "$APP/reviews" logs

if [ ! -f "$INSTANCE/markt/anbieter.yaml" ]; then
  echo "FEHLER: $INSTANCE/markt/anbieter.yaml fehlt (RADAR_INSTANCE prüfen)."; exit 1
fi

echo "[$(date '+%F %T')] Markt-Refresh-Entwurf ($MONTH), Deckel \$${RADAR_MARKT_MAX_COST:-2}"
.venv/bin/python src/markt_refresh.py --instance "$INSTANCE" --pool "$POOL" \
    --model "${RADAR_MARKT_MODEL:-claude-haiku-4-5-20251001}" \
    --max-cost-usd "${RADAR_MARKT_MAX_COST:-2}" --out "$OUT"

echo "[$(date '+%F %T')] Entwurf liegt hier zum Prüfen: $OUT"
echo "  -> danach markt/anbieter.yaml von Hand anpassen, Instanz pushen, app-run.sh."
