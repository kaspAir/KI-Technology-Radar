# Umgebungen, Branches und Promotion

Der Radar folgt dem Vier-Umgebungen-Modell des Suite-Testkonzepts (Kap. 3) und
einer streng sequenziellen Promotion mit Freigabe-Toren.

## Branch → Umgebung → URL

| Branch | Umgebung | Auslegung (Kap. 3) | URL |
|--------|----------|--------------------|-----|
| `dev`  | dev  | nur Entwickler, klein, Schnittstellen gemockt | https://dev.ki-tech-radar.ch |
| `test` | test | internes exploratives Testen (BKI AG), gemockt | http://test.ki-tech-radar.ch |
| `int`  | int  | Produktions-Spiegel, echte Schnittstellen; Kunde testet & nimmt ab | https://int.ki-tech-radar.ch |
| `main` | prod | Produktivbetrieb; nur Smoke/Health | https://ki-tech-radar.ch |

## Promotion — sequenziell, mit Freigabe (nie eine Stufe überspringen)

```
dev  --(dev grün + Freigabe)-->  test  --(Freigabe)-->  int  --(Freigabe)-->  main/prod
```

- **dev:** Erste Anlaufstelle. „Grün" = die schnelle deterministische Suite in der
  Jenkins-Pipeline ist bestanden und das Testprotokoll liegt vor.
- **test:** Erst nach ausdrücklicher Freigabe. Internes exploratives Testen.
- **int:** Erst nach Freigabe. Zwei Phasen mit internem Tor (Kap. 7): Phase 1 =
  interne Validierung gegen echte Umsysteme (Systemintegration, Performance,
  dynamische Sicherheit); erst wenn das Protokoll grün und signiert ist, beginnt
  Phase 2 = Kunde testet explorativ und nimmt ab.
- **main/prod:** Erst nach Freigabe. Kein Testbetrieb — nur nicht-destruktive
  Smoke- und Health-Checks (Kap. 17).

## Testarten je Umgebung (verbindliche Referenz, Kap. 6)

| Testart | dev | test | int | prod |
|---|---|---|---|---|
| Unit / Komponente | ✓ | ✓ | ✓ | – |
| Kontrakt (gg. Mock) | ✓ | ✓ | – | – |
| Fachlich | ✓ Mock | ✓ Mock | ✓ real | – |
| Systemintegration (echt) | – | – | ✓ | – |
| Performance / Last | – | – | ✓ | – |
| Sicherheit statisch | ✓ | ✓ | ✓ | – |
| Sicherheit dynamisch / Pentest | – | – | ✓ | – |
| Exploratives Testen | – | BKI | Kunde | – |
| Abnahme | – | – | Kunde | – |
| Smoke / Health | – | – | ✓ | ✓ |

## Jenkins-Pipelines

| Branch | Umgebung | Jenkins-Job |
|--------|----------|-------------|
| `dev`  | dev  | 3.1 KI-Radar dev |
| `test` | test | 3.2 KI-Radar Test |
| `int`  | int  | 3.3 KI-Radar Int |
| `main` | prod | 3.4 KI-Radar Prod |

## Deploy

Per SSH-git-pull wie die übrige Suite (kein Docker auf dem Zielhost). Der
Subdomain-Docroot jeder Umgebung zeigt auf `site/` im jeweiligen Host-Checkout;
`deploy/deploy.sh` zieht den passenden Branch. Verdrahtet im `Jenkinsfile`, scharf
nur bei `DEPLOY_ENABLED=true`. Einrichtung und benötigte Variablen:
[deploy/README.md](../deploy/README.md).

## Offene Infrastruktur-Punkte (Betreiber)

- SSH-Credential `ki-tech-radar-deploy` + `DEPLOY_HOST` / `DEPLOY_PATH_*` in Jenkins setzen,
  Host-Checkouts je Umgebung anlegen (Docroot → `site/`), dann `DEPLOY_ENABLED=true`.
- Branch-Protection so, dass Promotion nur nach grüner Suite + Freigabe möglich ist.
- Der Radar hat in R1 **noch keine interaktive UI** (YAML-first, keine UI vor
  stabilem Schema — E1). Deployt wird eine **statische Platzhalter-Seite**
  (`site/`), die je Umgebung ein Lebenszeichen zeigt; die echte Radar-Ansicht
  kommt in einem späteren Release.
