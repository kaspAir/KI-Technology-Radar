# MVP-Betrieb — den Selbstbedienungs-Radar als Website betreiben

> Aus „läuft auf meinem Laptop" wird eine echte Website. Ein **zentraler**
> Gunicorn-Prozess auf dem Infomaniak-Host bedient **alle** Mandanten; jeder
> öffnet nur eine URL und loggt sich ein — kein localhost, kein PowerShell, keine
> Installation beim Kunden.

## 1. Das Bild

```
  Mandant (Browser) ──HTTPS──▶ radar.ki-tech-radar.ch (Docroot)
                                   │  .htaccess ─▶ proxy.php  (PHP-Reverse-Proxy)
                                   ▼
                        127.0.0.1:8030  Gunicorn (app.main:app)
                                   │
                                   ▼
                        MariaDB (Infomaniak)  +  Instanz-Repo (Grundstock/Pool)
```

Genau das Muster von **hermespia.ch** (Gunicorn + PHP-Proxy, kein Docker), nur mit
eigenem Port und eigener DB.

## 2. Einmalige Einrichtung (auf dem Host, du)

**a) MariaDB** (in Infomaniak schon vorhanden): eine Datenbank + Benutzer anlegen,
DSN notieren. Format:
`mysql+pymysql://USER:PASSWORT@HOST:3306/DBNAME?charset=utf8mb4`

**b) Subdomain** z.B. `radar.ki-tech-radar.ch` mit eigenem Docroot; HTTPS-Zertifikat
aktivieren (Infomaniak: Let's Encrypt, ein Klick).

**c) SSH-Deploy-Key** fürs private Instanz-Repo (nur lesend), damit der Grundstock/Pool
geseedet werden kann (wie bei der Ingestion, `docs/ingestion-betrieb.md`). Ohne Key
läuft die App trotzdem — dann Grundstock später über den Admin-Button einlesen.

**d) Secrets-Datei** `~/.ki-radar-env` (chmod 600, **nicht** ins Repo):

```sh
export RADAR_DB='mysql+pymysql://USER:PW@HOST:3306/DBNAME?charset=utf8mb4'
export RADAR_SECRET='<40+ Zeichen Zufall, STABIL halten>'   # openssl rand -hex 24
export RADAR_ADMIN_EMAIL='k.broennimann@gmail.com'
export RADAR_ADMIN_PW='<starkes Initial-Passwort>'
export RADAR_PORT='8030'
```
`chmod 600 ~/.ki-radar-env`

## 3. Erster Start (auf dem Host)

```sh
mkdir -p ~/ki-radar && cd ~/ki-radar
git clone -b dev https://github.com/kaspAir/KI-Technology-Radar core
bash core/deploy/app-run.sh
```
`app-run.sh` erstellt die venv, installiert Abhängigkeiten, legt die Tabellen an,
seedet Referenz-Grundstock + Vorschläge-Pool (idempotent) und startet Gunicorn als
Daemon (PID in `~/ki-radar/gunicorn.pid`). Der Plattform-Admin aus `RADAR_ADMIN_EMAIL/PW`
wird beim ersten Start angelegt.

## 4. Docroot verdrahten

`deploy/docroot/proxy.php` und `deploy/docroot/.htaccess` in den Docroot der Subdomain
kopieren. `proxy.php` nutzt `RADAR_PORT` (Default 8030 = zu `gunicorn_conf.py` passend).
Danach ist `https://radar.ki-tech-radar.ch` live.

## 5. Am Leben halten (statt systemd)

Managed Hosting hat kein systemd. `app-keepalive.sh` startet den Prozess neu, falls er
nicht läuft (z.B. nach Host-Neustart). Per Cron (Infomaniak Cron-Manager):

```
*/5 * * * *  $HOME/ki-radar/core/deploy/app-keepalive.sh >> $HOME/ki-radar/app.log 2>&1
```

## 6. Aktualisieren (neue Version ausrollen)

```sh
bash ~/ki-radar/core/deploy/app-run.sh
```
Holt `origin/dev`, installiert ggf. neue Abhängigkeiten, seedet nach und startet den
Prozess neu. (Später als Jenkins-Job automatisierbar — SSH-Freischaltung durch dich.)

## 7. Erster Rundgang (im Browser)

1. `https://radar.ki-tech-radar.ch` → Login als Plattform-Admin.
2. **Mandanten** → „Referenz-Grundstock einlesen" (falls nicht schon per Seed) + Mandant + ersten Admin anlegen.
3. Mandanten-Admin loggt sich ein → erbt den Grundstock, kuratiert, legt Nutzer/Untermandanten an.

## 8. Wichtige Hinweise

- **`RADAR_SECRET` stabil halten** — ändern loggt alle aus (Daten bleiben in der DB).
- **Datenresidenz (CH):** MariaDB + Host bei Infomaniak (CH) — passt. Vor echten
  Mandantendaten prüfen, dass keine Verarbeitung ausserhalb CH stattfindet.
- **Migrationen:** die SQLite-Auto-Migration (`_ensure_columns`) ist **nur Dev**. Bei
  MariaDB legt der erste Start die Tabellen an; spätere Schema-Änderungen brauchen
  echte Migrationen (Alembic) — offener Punkt vor produktivem Dauerbetrieb.
- **Backups:** MariaDB-Dump in die Infomaniak-Backups aufnehmen (die DB ist jetzt die
  Quelle der Mandanten-Kuratierung, nicht mehr nur eine Projektion).

## 9. Fehlersuche

- **502 im Browser:** Gunicorn läuft nicht → `cat ~/ki-radar/app.log`, `app-run.sh` erneut.
- **Login klappt nicht:** `RADAR_ADMIN_*` in `~/.ki-radar-env` gesetzt? Erststart gelaufen?
- **Prozess prüfen:** `cat ~/ki-radar/gunicorn.pid` + `kill -0 <pid>`; Port: `curl -s 127.0.0.1:8030/login | head`.
