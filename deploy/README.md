# deploy — statische Seite per rsync über SSH

`deploy.sh` spiegelt den Inhalt von `site/` per `rsync` über SSH in den
Subdomain-Docroot der jeweiligen Umgebung. SSH-basiert wie die übrige Suite,
kein Docker auf dem Zielhost, **kein** Host-seitiger git-Checkout nötig.

## Jenkins-Konfiguration (Global-Env)

Setze in Manage Jenkins → System → Global properties → Environment variables:

- `DEPLOY_HOST = <user@host>`   *(SSH-Ziel; darf `user@host` enthalten)*
- `DEPLOY_CREDENTIAL = <id>`   *(ID des SSH-Credentials; ein bestehendes darf
  wiederverwendet werden. Ohne Angabe: `ki-tech-radar-deploy`.)*
- `DEPLOY_PATH_DEV`, `DEPLOY_PATH_TEST`, `DEPLOY_PATH_INT`, `DEPLOY_PATH_PROD`
  = der **Docroot** der jeweiligen Subdomain.
- `DEPLOY_ENABLED = true`   *(erst setzen, wenn die Pfade stehen)*

Der Deploy-Stage läuft nur bei `DEPLOY_ENABLED=true`; bis dahin übersprungen →
Build bleibt grün.

## Docroots ermitteln (falls unbekannt)

Setze zuerst nur `DEPLOY_HOST` (+ `DEPLOY_CREDENTIAL`) und baue einmal. Die Stage
**„Deploy-Ziel ermitteln"** verbindet sich dann rein lesend und listet die
Subdomain-Verzeichnisse im Build-Log — daraus ergeben sich die `DEPLOY_PATH_*`.

Alternativ im Infomaniak-Manager: jede Subdomain zeigt auf ein Zielverzeichnis;
genau dieser Pfad ist `DEPLOY_PATH_<UMGEBUNG>`.

> Hinweis: Liegt im Docroot eine Standard-`index.php`, kann sie Vorrang vor
> unserer `index.html` haben. Dann die Standarddatei einmalig entfernen/umbenennen.

## Voraussetzungen auf dem Jenkins-Agent

- `ssh` und `rsync` vorhanden; Zielhost per SSH erreichbar (Key im Credential).

> Sicherheitsnaht: Nur der **öffentliche Kern** (die Seite) wird deployt. Die
> **private Instanz** (Organisationsdaten) wird NIE auf die Web-Hosts ausgespielt.
