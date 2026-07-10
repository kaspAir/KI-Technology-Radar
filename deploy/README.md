# deploy — SSH-git-pull (wie die übrige Suite)

`deploy.sh` aktualisiert je Umgebung einen Checkout des Kern-Repos auf dem
Zielhost per SSH und `git pull`. Kein Docker auf dem Zielhost (Infomaniak managed
hosting) — Docker ist nur lokal/CI (Testimage). Der Subdomain-Docroot zeigt auf
`site/` im jeweiligen Checkout.

## Einmalige Einrichtung auf dem Host (Betreiber)

Je Umgebung ein Checkout, Docroot → `site/`:

```
dev.ki-tech-radar.ch   -> <pfad-dev>/site      (Checkout auf Branch dev)
test.ki-tech-radar.ch  -> <pfad-test>/site     (Branch test)
int.ki-tech-radar.ch   -> <pfad-int>/site      (Branch int)
ki-tech-radar.ch       -> <pfad-prod>/site     (Branch main)
```

## Jenkins-Konfiguration

1. **SSH-Credential** `ki-tech-radar-deploy` (SSH Username with private key) anlegen.
2. **Global-Env** (Manage Jenkins → System → Global properties, oder je Job):
   - `DEPLOY_ENABLED = true`
   - `DEPLOY_HOST = <host>`
   - `DEPLOY_USER = <user>` *(optional)*
   - `DEPLOY_PATH_DEV`, `DEPLOY_PATH_TEST`, `DEPLOY_PATH_INT`, `DEPLOY_PATH_PROD`
3. Der Deploy-Stage im `Jenkinsfile` ist bereits verdrahtet; er läuft nur, wenn
   `DEPLOY_ENABLED=true` gesetzt ist. Bis dahin wird er sauber übersprungen — der
   Build bleibt grün.

## Voraussetzungen auf dem Jenkins-Agent

- `ssh`-Client vorhanden; Zielhost per SSH erreichbar (Key im Credential).
- Der Host vertraut dem Deploy-Key; der Checkout hat Leserechte auf das
  öffentliche Kern-Repo (HTTPS genügt, da öffentlich).

> Sicherheitsnaht: Nur der **öffentliche Kern** wird so deployt. Die **private
> Instanz** (Organisationsdaten) wird NICHT auf die Web-Hosts ausgespielt.
