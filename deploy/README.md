# deploy — statische Seite per rsync über SSH

`deploy.sh` spiegelt den Inhalt von `site/` per `rsync` über SSH in den
Subdomain-Docroot der jeweiligen Umgebung. SSH-basiert wie die übrige Suite,
kein Docker auf dem Zielhost, **kein** Host-seitiger git-Checkout nötig.

## Jenkins-Konfiguration (das genügt)

1. **SSH-Credential** `ki-tech-radar-deploy` (SSH Username with private key) anlegen.
2. **Global-Env** (Manage Jenkins → System → Global properties, oder je Job):
   - `DEPLOY_ENABLED = true`
   - `DEPLOY_HOST = <host>`   *(Infomaniak-SSH-Host)*
   - `DEPLOY_USER = <user>`   *(optional, sonst aus Credential/ssh-config)*
   - `DEPLOY_PATH_DEV`, `DEPLOY_PATH_TEST`, `DEPLOY_PATH_INT`, `DEPLOY_PATH_PROD`
     = der **Docroot** der jeweiligen Subdomain (z.B. der Ordner, in dem die
     Infomaniak-Standardseite liegt).
3. Der Deploy-Stage im `Jenkinsfile` läuft nur, wenn `DEPLOY_ENABLED=true`. Bis
   dahin wird er sauber übersprungen — der Build bleibt grün.

## Docroot herausfinden

Im Infomaniak-Manager zeigt jede Subdomain auf ein Verzeichnis. Genau dieser Pfad
ist `DEPLOY_PATH_<UMGEBUNG>`. Die aktuell sichtbare „in Bearbeitung"-Seite liegt
dort — unser `index.html` landet daneben.

> Hinweis: Liegt dort eine Standard-`index.php`, kann sie Vorrang vor unserer
> `index.html` haben. Dann die Standarddatei einmalig entfernen/umbenennen.

## Voraussetzungen auf dem Jenkins-Agent

- `ssh` und `rsync` vorhanden; Zielhost per SSH erreichbar (Key im Credential).

> Sicherheitsnaht: Nur der **öffentliche Kern** (die Seite) wird deployt. Die
> **private Instanz** (Organisationsdaten) wird NIE auf die Web-Hosts ausgespielt.
