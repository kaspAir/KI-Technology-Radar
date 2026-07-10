# Testing — Umsetzung des Suite-Testkonzepts

Dieser Ordner setzt das **Suite-Testkonzept (Zielarchitektur V0.1)** für den
KI-Technology-Radar um. Das Testkonzept gilt produktübergreifend; hier ist es auf
den Radar angewandt, entlang seines eigenen Rollouts (Kap. 16, **Schritt 1–2**).

## Prinzipien, die hier gelten

- **Deterministischer Runner entscheidet, KI nur für Sprache** (ADR-T01). `run_suite.py`
  und `pytest` entscheiden Pass/Fail; kein Agent.
- **Testart folgt Umgebungstreue** (ADR-T02). Schnelle Suite auf dev/test gegen
  Mocks/Fixtures; schwere Suiten (Systemintegration, Performance, dyn. Sicherheit)
  erst auf int.
- **Kontrakt ≠ Systemintegration** (ADR-T03). Das Protokoll weist den
  Schnittstellenmodus (`mock`/`real`) aus, damit keine Scheinsicherheit entsteht.
- **Geteiltes Werkzeug, produktspezifische Fälle** (ADR-T05). `schema/` ist das
  geteilte Werkzeug; `cases/` sind die Fälle *dieses* Produkts.
- **Nicht die ganze Suite bei jedem Build** (ADR-T06). Bei jedem Build nur die
  schnelle Suite; schwere Suiten auf Promotion nach int.

## Was hier liegt

```
schema/testcase.schema.yaml   geteiltes Testfall-Schema (Kap. 11)
schema/protocol.schema.yaml   Testprotokoll-Schema, Governance-Mixin (Kap. 12)
cases/kern-mechanismus.yaml   produktspezifischer Testfall-Katalog (ADR-T05)
tests/test_validate.py        deterministische pytest-Materialisierung der Fälle
run_suite.py                  schnelle Suite ausführen + Protokoll erzeugen
protocols/                    erzeugte Protokolle (Build-Artefakte, git-ignoriert)
```

## Lokal ausführen

```bash
pip install -r ../requirements.txt
python run_suite.py --env dev --instance ../examples/sample-instance
```

Erzeugt ein Protokoll unter `protocols/` und endet mit Exit-Code `0` (bestanden)
oder `1` (fehlgeschlagen). In der CI läuft dasselbe im Docker-Image (siehe
`../Jenkinsfile`), das Protokoll wird als Build-Artefakt archiviert.

## Bewusst noch NICHT umgesetzt (ehrlich ausgewiesen, keine Scheinsicherheit)

- **Schwere Suiten** (Systemintegration/Performance/DAST) — erst auf int, wenn es
  echte Umsysteme und eine Produktions-Grösse gibt (der Radar hat in R1 noch
  keinen laufenden Dienst; E1: keine UI vor stabilem Schema). Im Protokoll als
  `nicht_ausgefuehrt` markiert.
- **int-Zwei-Phasen-Tor** mit interner Freigabe/Signatur (Kap. 7) — Rollout-Schritt 3.
- **Agent-Rollen** (Testfälle generieren, Protokoll formulieren, Fehler triagieren,
  explorativ generieren; ADR-T07) — Rollout-Schritt 3. Bis dahin rein deterministisch.
- **Jira-Projektion / Traceability** (Xray/Zephyr, ADR-T08) — später.

## Verhältnis zum geteilten Suite-Werkzeug (ADR-T05 / Kap. 14)

`schema/` und der Protokoll-Layer sind bewusst so geschnitten, dass sie später in
ein **geteiltes** Suite-Werkzeug wandern können, sobald ein zweites Produkt sie
braucht. Wichtig dabei (Kap. 14): geteilt wird das **Framework**, nicht ein
zentraler Runner, durch den alles zwingend laufen muss — sonst entsteht ein
Flaschenhals/Single-Point-of-Failure in der CI.
