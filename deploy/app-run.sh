#!/usr/bin/env bash
# app-run.sh — Radar-MVP auf dem Infomaniak-Host ausrollen/aktualisieren & starten.
# Layout wie das Dashboard: App-Root = dieses Repo, .venv + .env darin, Docroot separat.
#
# Einmal einrichten (siehe docs/mvp-betrieb.md), danach je Update erneut aufrufen:
#   bash <app>/deploy/app-run.sh
#
# .env (KEY=VALUE, chmod 600, NICHT im Repo) muss enthalten:
#   RADAR_DB=mysql+pymysql://USER:PW@HOST:3306/DB?charset=utf8mb4
#   RADAR_SECRET=<langer Zufall, stabil halten>
#   RADAR_ADMIN_EMAIL=... ; RADAR_ADMIN_PW=...
#   RADAR_INSTANCE=<Pfad zum Instanz-Klon>        (optional; Default siehe unten)
#   RADAR_PORT=8030 ; RADAR_WORKERS=4             (optional)
set -eu

APP="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$APP"
BRANCH="${KI_RADAR_BRANCH:-dev}"

# ---- Konfig laden -------------------------------------------------------------
set -a; [ -f .env ] && . ./.env; set +a
: "${RADAR_DB:?RADAR_DB fehlt in .env}"
: "${RADAR_SECRET:?RADAR_SECRET fehlt in .env}"
# Instanz-Repo (privat): per .env (RADAR_INSTANCE_GIT) überschreibbar, damit ein
# eigener SSH-Alias genutzt werden kann, ohne globales github.com zu ändern.
INST_URL="${RADAR_INSTANCE_GIT:-git@github.com:kaspAir/KI-Technology-Radar-Instanz.git}"
PORT="${RADAR_PORT:-8030}"; WORKERS="${RADAR_WORKERS:-4}"
export RADAR_INSTANCE="${RADAR_INSTANCE:-$APP/../radar-instance}"

# ---- Code aktualisieren -------------------------------------------------------
if [ -d .git ]; then git fetch -q && git reset -q --hard "origin/$BRANCH"; fi

# ---- Instanz (Grundstock/Pool) holen, falls SSH-Key vorhanden -----------------
if [ -d "$RADAR_INSTANCE/.git" ]; then git -C "$RADAR_INSTANCE" pull -q --ff-only || true
elif git clone -q -b "$BRANCH" "$INST_URL" "$RADAR_INSTANCE" 2>/dev/null; then :; else
  echo "Hinweis: Instanz nicht klonbar (kein Key?) — Grundstock später per Admin-Button."; fi

# ---- Python-Umgebung ----------------------------------------------------------
# Managed Hosting: `python3 -m venv` kann oft kein pip bootstrappen (ensurepip fehlt)
# -> virtualenv bevorzugen (bringt pip mit, wie beim Dashboard). Fallback: venv.
if [ ! -x .venv/bin/pip ]; then
  rm -rf .venv
  if python3 -m virtualenv --version >/dev/null 2>&1; then
    python3 -m virtualenv .venv
  else
    python3 -m venv .venv
  fi
  .venv/bin/python -m pip install -q --upgrade pip
fi
.venv/bin/pip install -q -r app/requirements.txt

# ---- DB init + Grundstock/Pool seeden (idempotent) ----------------------------
.venv/bin/python -c "from app.db import init_db; init_db(); print('DB bereit')"
if [ -d "$RADAR_INSTANCE/entries" ]; then
  .venv/bin/python -m app.seed_reference "$RADAR_INSTANCE" || echo "Referenz-Seed übersprungen."
  [ -f "$RADAR_INSTANCE/inbox/pool.yaml" ] && .venv/bin/python -m app.seed "$RADAR_INSTANCE/inbox/pool.yaml" || true
fi

# ---- Prozess (neu) starten via Watchdog ---------------------------------------
[ -f tmp/gunicorn.pid ] && kill "$(cat tmp/gunicorn.pid)" 2>/dev/null || true
sleep 1
sh deploy/keepalive.sh "$PORT" "$WORKERS"
sleep 2
if curl -sf "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
  echo "[$(date '+%F %T')] Radar-MVP läuft an 127.0.0.1:$PORT (PID $(cat tmp/gunicorn.pid 2>/dev/null))"
else
  echo "FEHLER: Prozess nicht gesund — logs/error.log prüfen."; tail -n 20 logs/error.log 2>/dev/null || true; exit 1
fi
