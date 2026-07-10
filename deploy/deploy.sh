#!/usr/bin/env bash
# Deploy der statischen Seite per rsync über SSH — Infomaniak managed hosting,
# kein Docker auf dem Zielhost (im Geist der übrigen Suite: SSH-basiert).
#
# Für eine statische Seite genügt es, den Inhalt von site/ in den bestehenden
# Subdomain-Docroot zu spiegeln — kein Host-seitiger git-Checkout nötig.
#
# Erwartete Variablen (in Jenkins als Global-Env/Credentials setzen):
#   DEPLOY_ENABLED=true            schaltet den Deploy scharf (sonst übersprungen)
#   DEPLOY_HOST=<host>             SSH-Host (Infomaniak)
#   DEPLOY_USER=<user>            SSH-User (optional, sonst aus Credential/ssh-config)
#   DEPLOY_PATH_DEV=<docroot>     Docroot der jeweiligen Subdomain
#   DEPLOY_PATH_TEST / _INT / _PROD
#   SSH_OPTS=<opts>              optionale ssh-Optionen (z.B. -i <key>)
#
# Ohne Konfiguration endet das Skript mit Exit 0 (Build bleibt grün).
set -euo pipefail

env="${RADAR_ENV:?RADAR_ENV fehlt}"
case "$env" in
  dev)  docroot="${DEPLOY_PATH_DEV:-}"  ;;
  test) docroot="${DEPLOY_PATH_TEST:-}" ;;
  int)  docroot="${DEPLOY_PATH_INT:-}"  ;;
  prod) docroot="${DEPLOY_PATH_PROD:-}" ;;
  *) echo "Unbekannte Umgebung: $env"; exit 1 ;;
esac

host="${DEPLOY_HOST:-}"
user="${DEPLOY_USER:-}"
target="${user:+$user@}${host}"

if [ "${DEPLOY_ENABLED:-}" != "true" ] || [ -z "$host" ] || [ -z "$docroot" ]; then
  echo "Deploy ($env) nicht konfiguriert (DEPLOY_ENABLED/DEPLOY_HOST/DEPLOY_PATH_* fehlen) — übersprungen."
  exit 0
fi

echo "Deploy ($env): site/ -> ${target}:${docroot}/"
# Nur den Seiteninhalt spiegeln (README nicht ausliefern). Kein --delete, um bei
# einem falsch gesetzten Docroot nichts zu löschen.
rsync -az --exclude 'README.md' -e "ssh ${SSH_OPTS:-}" ./site/ "${target}:${docroot}/"
echo "Deploy ($env) ok — ${docroot} aktualisiert."
