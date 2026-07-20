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
RADAR_WORKERS=4
```

> **Wichtig — Zeitlimit:** `RADAR_TIMEOUT` (Vorgabe neu 1800 s) muss deutlich über der
> längsten Beratungsantwort liegen. Stand er auf 180 s, hielt Gunicorn den Prozess für
> hängend und killte ihn mitten im Lauf: die bereits bezahlte Antwort war verloren und
> die Oberfläche antwortete während des Neustarts nicht. Wer hier kürzt, holt sich genau
> dieses Fehlerbild zurück.
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

## 10. Nächtliche Ingestion (neue Belege der letzten 24 h)

`deploy/app-ingest.sh` holt aus den kuratierten Quellen (RSS/Atom + arXiv, E6) die
neuesten Belege und spiegelt neue Kandidaten in die MariaDB → sie erscheinen sofort
unter „Vorschläge". Der Agent sammelt/entwirft nur (E4/E20), ratifiziert wird von Hand.

**Key separat ablegen** (nicht ins Web-`.env`) — `~/.ki-radar-env` (chmod 600):
```
export ANTHROPIC_API_KEY='sk-ant-...'
```
**Test (kostenlos, nur Mechanik):**
```sh
RADAR_INGEST_MAX_COST=0 ~/radar-app/.venv/bin/python ~/radar-app/src/ingest.py \
  --instance ~/radar-instance --all-sources --since "$(date -d '1 day ago' +%F)" --dry-run
```
**Echter Lauf + Cron (03:15):**
```sh
bash ~/radar-app/deploy/app-ingest.sh          # einmal von Hand prüfen
(crontab -l; echo "15 3 * * * /bin/sh $HOME/radar-app/deploy/app-ingest.sh >> $HOME/radar-app/logs/ingest.log 2>&1") | crontab -
```
Stellschrauben (optional in `.env`): `RADAR_INGEST_MAX_COST` (Deckel $, Default 5),
`RADAR_INGEST_MAX_ITEMS` (je Quelle, 25), `RADAR_INGEST_DAYS` (Fenster, 1),
`RADAR_INGEST_MODEL`. Der akkumulierende Pool liegt unter `~/radar-pool/pool.yaml`
(ausserhalb Git → `~/radar-instance` bleibt für `app-run.sh` sauber). Kosten real
erfahrungsgemäss ~$0.10–0.30/Nacht (24-h-Fenster = wenige neue Items).

## 11. Monatlicher Markt-Refresh (Entwurf zur Anbieter-Landschaft)

Die `/markt`-Ampel + Indikatoren (`markt/anbieter.yaml`) sind ein **kuratiertes** Urteil
und werden NICHT automatisch überschrieben (E8: keine erfundenen Finanzzahlen/Tendenzen).
`deploy/app-marktrefresh.sh` sammelt die Monats-Signale aus dem Pool und **entwirft** je
Firma „Tendenz + Belege" in eine Review-Datei — der Kurator ratifiziert von Hand.

```sh
# Test (kostet ~$0.x, Deckel $2):
bash ~/radar-app/deploy/app-marktrefresh.sh
cat ~/radar-app/reviews/anbieter-vorschlag-$(date +%Y-%m).md     # Entwurf lesen

# Cron (1. des Monats, 04:00):
(crontab -l; echo "0 4 1 * * /bin/sh $HOME/radar-app/deploy/app-marktrefresh.sh >> $HOME/radar-app/logs/marktrefresh.log 2>&1") | crontab -
```
Danach: `markt/anbieter.yaml` in der Instanz anpassen → Instanz pushen → `app-run.sh`
(zieht die Instanz) → `/markt` zeigt den neuen Stand. Nichts wird ohne dich verändert.

## 9. Fehlersuche

- **502 im Browser:** Gunicorn läuft nicht → `tail ~/radar-app/logs/error.log`, `app-run.sh` erneut.
- **Login/Startprobleme:** `RADAR_*` in `.env` gesetzt? `curl -s 127.0.0.1:8030/healthz`.
- **Prozess:** `cat ~/radar-app/tmp/gunicorn.pid` + `kill -0 <pid>`.
