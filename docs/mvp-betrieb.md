# MVP-Betrieb — den Selbstbedienungs-Radar als Website betreiben

> Aus „läuft auf meinem Laptop" wird eine echte Website. Ein **zentraler**
> Gunicorn-Prozess auf dem Infomaniak-Host bedient **alle** Mandanten; jeder
> öffnet nur eine URL und loggt sich ein — kein localhost, kein PowerShell, keine
> Installation beim Kunden. Aufbau **identisch zum Dashboard** (dashboard-projekte.ch).

## 1. Das Bild

```
  Mandant (Browser) ──HTTPS──▶ app.ki-tech-radar.ch (Docroot)
                                   │  .htaccess ─▶ proxy.php  ($BACKEND=127.0.0.1:8030)
                                   ▼
                        127.0.0.1:8030  Gunicorn/UvicornWorker (app.main:app)
                                   │
                                   ▼
                        MariaDB (Infomaniak)  +  Instanz-Repo (Grundstock/Pool)
```

- **App-Root** (Kern-Klon) `~/radar-app/` mit `.venv/` und `.env/` darin.
- **Docroot** `~/sites/app.ki-tech-radar.ch/` mit `proxy.php` + `.htaccess`.
- **Watchdog** `deploy/keepalive.sh <PORT> <WORKERS>` per Cron (`@reboot` + `*/3`).
- Ports auf dem Host: hermespia 8003, ProS 801x, Dashboard 8021–8023 → **Radar 8030**.

## 2. Einmalige Einrichtung (du, auf dem Host + Infomaniak)

**a) MariaDB** (vorhanden): DB + Benutzer anlegen, DSN notieren:
`mysql+pymysql://USER:PW@HOST:3306/DBNAME?charset=utf8mb4`

**b) Subdomain** `app.ki-tech-radar.ch` mit eigenem Docroot anlegen; im Infomaniak-Panel
**HTTPS erzwingen** (Let's Encrypt + „Force HTTPS"). *Nicht* über `.htaccess` — hinter
dem Plattform-TLS gäbe das eine Endlosschleife (darum macht es das Dashboard auch nicht).

**c) App klonen:**
```sh
git clone -b dev https://github.com/kaspAir/KI-Technology-Radar ~/radar-app
```

**d) Secrets** in `~/radar-app/.env` (KEY=VALUE je Zeile, **nicht** im Repo):
```
RADAR_DB=mysql+pymysql://USER:PW@HOST:3306/DBNAME?charset=utf8mb4
RADAR_SECRET=<40+ Zeichen Zufall, STABIL halten>
RADAR_ADMIN_EMAIL=k.broennimann@gmail.com
RADAR_ADMIN_PW=<starkes Initial-Passwort>
RADAR_INSTANCE=/home/clients/<id>/radar-instance
RADAR_PORT=8030
RADAR_WORKERS=2
```
`chmod 600 ~/radar-app/.env`  ·  Zufall z.B. `openssl rand -hex 24`.

**e) SSH-Deploy-Key** fürs private Instanz-Repo (nur lesend, wie bei der Ingestion),
damit Grundstock/Pool automatisch geseedet werden. Ohne Key startet die App trotzdem —
Grundstock dann später über den Admin-Button „Referenz-Grundstock einlesen".

## 3. Erster Start

```sh
bash ~/radar-app/deploy/app-run.sh
```
Das aktualisiert den Code, klont die Instanz (falls Key), baut `.venv`, installiert
Abhängigkeiten, legt die MariaDB-Tabellen an, seedet Grundstock + Pool (idempotent) und
startet Gunicorn über den Watchdog. Der Plattform-Admin aus `RADAR_ADMIN_*` wird beim
ersten Start angelegt. Test lokal auf dem Host: `curl -s 127.0.0.1:8030/healthz` → `ok`.

## 4. Docroot verdrahten

`deploy/docroot/proxy.php` und `deploy/docroot/.htaccess` in `~/sites/app.ki-tech-radar.ch/`
kopieren. `$BACKEND` in `proxy.php` steht schon auf `127.0.0.1:8030`.
```sh
cp ~/radar-app/deploy/docroot/proxy.php ~/radar-app/deploy/docroot/.htaccess ~/sites/app.ki-tech-radar.ch/
```
Danach ist `https://app.ki-tech-radar.ch` live.

## 5. Am Leben halten (Cron, wie das Dashboard)

Im Infomaniak Cron-Manager:
```
@reboot   /home/clients/<id>/radar-app/deploy/keepalive.sh 8030 2
*/3 * * * * /home/clients/<id>/radar-app/deploy/keepalive.sh 8030 2 >> /home/clients/<id>/radar-app/logs/watchdog.log 2>&1
```
`keepalive.sh` prüft `http://127.0.0.1:8030/healthz` und startet den Prozess nur, wenn er
nicht antwortet (nach Reboot oder Absturz).

## 6. Aktualisieren (neue Version ausrollen)

```sh
bash ~/radar-app/deploy/app-run.sh
```
Holt `origin/dev`, installiert ggf. neue Abhängigkeiten, seedet nach, startet neu.
(Später als Jenkins-Job automatisierbar — SSH-Freischaltung durch dich.)

## 7. Erster Rundgang (Browser)

1. `https://app.ki-tech-radar.ch` → Login als Plattform-Admin.
2. **Mandanten** → ggf. „Referenz-Grundstock einlesen" + Mandant + ersten Admin anlegen.
3. Mandanten-Admin loggt sich ein → erbt den Grundstock, kuratiert, legt Nutzer/Untermandanten an.

## 8. Wichtige Hinweise

- **`RADAR_SECRET` stabil halten** — ändern loggt alle aus (Daten bleiben in der DB).
- **Datenresidenz (CH):** MariaDB + Host bei Infomaniak (CH) — passt. Vor echten
  Mandantendaten sicherstellen, dass keine Verarbeitung ausserhalb CH stattfindet.
- **Migrationen:** die SQLite-Auto-Migration (`_ensure_columns`) ist **nur Dev**. Bei
  MariaDB legt der erste Start die Tabellen an; spätere Schema-Änderungen brauchen echte
  Migrationen (Alembic) — offener Punkt vor produktivem Dauerbetrieb.
- **Backups:** MariaDB-Dump in die Infomaniak-Backups aufnehmen (die DB ist jetzt die
  Quelle der Mandanten-Kuratierung).
- **Statische Seite bleibt getrennt:** `dev/test/int/ki-tech-radar.ch` = statisches
  Schaufenster; `app.ki-tech-radar.ch` = angemeldete App. Zwei verschiedene Produkte.

## 9. Fehlersuche

- **502 im Browser:** Gunicorn läuft nicht → `tail ~/radar-app/logs/error.log`, `app-run.sh` erneut.
- **Login/Startprobleme:** `RADAR_*` in `.env` gesetzt? `curl -s 127.0.0.1:8030/healthz`.
- **Prozess:** `cat ~/radar-app/tmp/gunicorn.pid` + `kill -0 <pid>`.
