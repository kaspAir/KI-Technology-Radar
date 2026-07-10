#!/usr/bin/env bash
# Deploy per SSH-git-pull — dasselbe Muster wie die übrige Phronesis-Suite
# (Infomaniak managed hosting, kein Docker auf dem Zielhost).
#
# Der Zielhost hält je Umgebung einen Checkout des Kern-Repos; der Subdomain-
# Docroot zeigt auf dessen site/. Deploy = auf dem Host den passenden Branch
# ziehen. Alles ist über Env-Variablen parametrisiert — NICHTS ist hartkodiert.
#
# Erwartete Variablen (in Jenkins als Global-Env/Credentials setzen):
#   DEPLOY_ENABLED=true            schaltet den Deploy scharf (sonst übersprungen)
#   DEPLOY_HOST=<host>             SSH-Host (z.B. Infomaniak-Host)
#   DEPLOY_USER=<user>             SSH-User (optional, sonst aus Credential/ssh-config)
#   DEPLOY_PATH_DEV=<pfad>         Checkout-Pfad auf dem Host je Umgebung
#   DEPLOY_PATH_TEST / _INT / _PROD
#   SSH_OPTS=<opts>               optionale ssh-Optionen (z.B. -i <key>)
#
# Ohne Konfiguration endet das Skript mit Exit 0 (Build bleibt grün).
set -euo pipefail

env="${RADAR_ENV:?RADAR_ENV fehlt}"
case "$env" in
  dev)  path="${DEPLOY_PATH_DEV:-}";  branch="dev"  ;;
  test) path="${DEPLOY_PATH_TEST:-}"; branch="test" ;;
  int)  path="${DEPLOY_PATH_INT:-}";  branch="int"  ;;
  prod) path="${DEPLOY_PATH_PROD:-}"; branch="main" ;;
  *) echo "Unbekannte Umgebung: $env"; exit 1 ;;
esac

host="${DEPLOY_HOST:-}"
user="${DEPLOY_USER:-}"
target="${user:+$user@}${host}"

if [ "${DEPLOY_ENABLED:-}" != "true" ] || [ -z "$host" ] || [ -z "$path" ]; then
  echo "Deploy ($env) nicht konfiguriert (DEPLOY_ENABLED/DEPLOY_HOST/DEPLOY_PATH_* fehlen) — übersprungen."
  exit 0
fi

echo "Deploy ($env): ${target}:${path}  (branch ${branch})"
# shellcheck disable=SC2086
ssh ${SSH_OPTS:-} "$target" "cd '$path' && git fetch --all --prune && git checkout '$branch' && git pull --ff-only"
echo "Deploy ($env) ok — Docroot zeigt auf ${path}/site/"
