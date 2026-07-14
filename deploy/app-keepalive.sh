#!/usr/bin/env bash
# app-keepalive.sh — hält den Radar-MVP am Leben (Managed Hosting ohne systemd).
#
# Prüft, ob der Gunicorn-Prozess läuft; wenn nicht, startet app-run.sh ihn (neu).
# Per Cron alle paar Minuten, z.B.:
#   */5 * * * *  $HOME/ki-radar/core/deploy/app-keepalive.sh >> $HOME/ki-radar/app.log 2>&1
set -eu
WORKDIR="${KI_RADAR_WORKDIR:-$HOME/ki-radar}"
PIDFILE="${KI_RADAR_PIDFILE:-$WORKDIR/gunicorn.pid}"
RUN="$WORKDIR/core/deploy/app-run.sh"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  exit 0   # läuft
fi
echo "[$(date '+%F %T')] Radar-MVP nicht aktiv — starte neu."
exec bash "$RUN"
