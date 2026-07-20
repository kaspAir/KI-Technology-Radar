#!/bin/sh
# keepalive.sh — Watchdog für den Radar-MVP (Muster wie dashboard/deploy/keepalive.sh).
# Startet Gunicorn, falls es nicht (mehr) läuft. Für Cron (@reboot + alle paar Minuten)
# -> die Umgebung heilt sich nach Server-Neustart oder Absturz selbst.
#
#   keepalive.sh <PORT> <WORKERS>
#
# Unterschied zum Dashboard: der Radar ist ASGI (FastAPI) -> Gunicorn braucht den
# UvicornWorker. Secrets kommen aus <app>/.env (RADAR_DB, RADAR_SECRET, ...).
PORT="${1:-8030}"
WORKERS="${2:-2}"
APP="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$APP" || exit 0

# Läuft schon und antwortet? -> nichts tun.
if curl -sf "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
    exit 0
fi

[ -x .venv/bin/gunicorn ] || exit 0
mkdir -p logs tmp

# evtl. toten Prozess aufräumen
if [ -f tmp/gunicorn.pid ]; then
    kill "$(cat tmp/gunicorn.pid)" 2>/dev/null || true
fi

# Secrets/Konfig laden (KEY=VALUE je Zeile; nicht im Repo).
# Auch ~/.ki-radar-env, weil dort der ANTHROPIC_API_KEY liegen kann — den braucht
# der Web-Prozess für den Radar-Berater (/chat), nicht nur die Ingestion.
set -a
[ -f .env ] && . ./.env
[ -f "$HOME/.ki-radar-env" ] && . "$HOME/.ki-radar-env"
set +a

nohup .venv/bin/gunicorn app.main:app \
    -k uvicorn.workers.UvicornWorker \
    --bind "127.0.0.1:$PORT" --workers "$WORKERS" --timeout "${RADAR_TIMEOUT:-180}" \
    --access-logfile logs/access.log --error-logfile logs/error.log >/dev/null 2>&1 &
echo $! > tmp/gunicorn.pid
