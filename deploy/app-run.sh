#!/usr/bin/env bash
# app-run.sh — Selbstbedienungs-Radar (MVP) auf dem Infomaniak-Host ausrollen & starten.
#
# Macht aus „läuft auf meinem Laptop" eine echte Website: ein zentraler Gunicorn-
# Prozess an 127.0.0.1:$RADAR_PORT; der PHP-Proxy im Docroot (wie hermespia.ch)
# leitet die öffentliche Domain darauf um. Mandanten öffnen nur die URL + Login.
#
# Ablauf: Kern-Repo aktualisieren -> venv/Abhängigkeiten -> DB init + Grundstock/Pool
#         seeden (idempotent) -> Gunicorn (neu) starten (Daemon + PID-Datei).
#
# Secrets & Konfiguration kommen aus $HOME/.ki-radar-env (chmod 600), NICHT aus dem
# Repo. Erwartete Variablen dort:
#   RADAR_DB=mysql+pymysql://USER:PW@HOST:3306/DB?charset=utf8mb4
#   RADAR_SECRET=<langer Zufallsstring, stabil halten>
#   RADAR_ADMIN_EMAIL=... ; RADAR_ADMIN_PW=...   (Bootstrap des Plattform-Admins)
#   RADAR_PORT=8030                               (lokaler Gunicorn-Port)
# Einmalige Einrichtung: siehe docs/mvp-betrieb.md.
set -eu

WORKDIR="${KI_RADAR_WORKDIR:-$HOME/ki-radar}"
KERN_URL="https://github.com/kaspAir/KI-Technology-Radar"
INST_URL="git@github.com:kaspAir/KI-Technology-Radar-Instanz.git"   # SSH (Read-Deploy-Key)
BRANCH="${KI_RADAR_BRANCH:-dev}"
PIDFILE="${KI_RADAR_PIDFILE:-$WORKDIR/gunicorn.pid}"

[ -f "$HOME/.ki-radar-env" ] && . "$HOME/.ki-radar-env"
: "${RADAR_DB:?RADAR_DB nicht gesetzt (erwartet in \$HOME/.ki-radar-env)}"
: "${RADAR_SECRET:?RADAR_SECRET nicht gesetzt}"
export RADAR_DB RADAR_SECRET RADAR_ADMIN_EMAIL RADAR_ADMIN_PW RADAR_PORT
export RADAR_INSTANCE="${RADAR_INSTANCE:-$WORKDIR/instance}"

mkdir -p "$WORKDIR"; cd "$WORKDIR"

# ---- Repos aktualisieren ------------------------------------------------------
if [ -d core/.git ]; then git -C core fetch -q && git -C core reset -q --hard "origin/$BRANCH"
else git clone -q -b "$BRANCH" "$KERN_URL" core; fi
# Instanz (für Grundstock/Pool-Seed); optional, wenn kein SSH-Key: überspringen.
if [ -d instance/.git ]; then git -C instance pull -q --ff-only || true
elif git clone -q -b "$BRANCH" "$INST_URL" instance 2>/dev/null; then :; else
  echo "Hinweis: Instanz-Repo nicht klonbar (kein Key?) — Seed wird übersprungen."; fi

# ---- Python-Umgebung ----------------------------------------------------------
if [ ! -x appvenv/bin/python ]; then python3 -m venv appvenv; ./appvenv/bin/pip install -q --upgrade pip; fi
./appvenv/bin/pip install -q -r core/app/requirements.txt
PY=$PWD/appvenv/bin/python

# ---- DB initialisieren + Grundstock/Pool einlesen (idempotent) ----------------
cd core
"$PY" -c "from app.db import init_db; init_db(); print('DB bereit')"
if [ -d "$RADAR_INSTANCE/entries" ]; then
  "$PY" -m app.seed_reference "$RADAR_INSTANCE" || echo "Referenz-Seed übersprungen."
  [ -f "$RADAR_INSTANCE/inbox/pool.yaml" ] && "$PY" -m app.seed "$RADAR_INSTANCE/inbox/pool.yaml" || true
fi

# ---- Gunicorn (neu) starten ---------------------------------------------------
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Stoppe alten Prozess $(cat "$PIDFILE")"; kill "$(cat "$PIDFILE")" 2>/dev/null || true; sleep 2
fi
exec_env() { RADAR_DB="$RADAR_DB" RADAR_SECRET="$RADAR_SECRET" RADAR_INSTANCE="$RADAR_INSTANCE" \
             RADAR_ADMIN_EMAIL="${RADAR_ADMIN_EMAIL:-}" RADAR_ADMIN_PW="${RADAR_ADMIN_PW:-}" \
             RADAR_PORT="${RADAR_PORT:-8030}" "$@"; }
exec_env "$PWD/../appvenv/bin/gunicorn" -c app/gunicorn_conf.py --pid "$PIDFILE" --daemon app.main:app
sleep 2
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "[$(date '+%F %T')] Radar-MVP läuft (PID $(cat "$PIDFILE")) an 127.0.0.1:${RADAR_PORT:-8030}"
else
  echo "FEHLER: Gunicorn nicht gestartet — Logs prüfen."; exit 1
fi
