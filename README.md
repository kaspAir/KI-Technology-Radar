# KI-Technology-Radar — Kern

> Neues am Horizont erkennen, bevor es alle sehen.

Der **KI-Technology-Radar** beobachtet Entwicklungen im Bereich Künstliche
Intelligenz systematisch, ordnet sie ein und macht ihre Relevanz für eine
betreibende Organisation beurteilbar. Er ist kein Newsfeed, sondern ein
strukturierter Orientierungs- und Entscheidungsprozess.

Der Radar ist eine Ausprägung von **Aletheia** (Wahrnehmung) in der
**Phronesis**-Familie.

Dieses Repository ist der **Kern**: der veröffentlichbare *Mechanismus* —
Schema, Starter-Taxonomien, Muster-Bibliothek und Validierung. Die *Daten* einer
Organisation (Beobachtungen, Bewertungen, Quellen, Berichte) liegen getrennt in
einer **Instanz** und werden hier nie eingecheckt (siehe [Kern und Instanz](#kern-und-instanz)).

## Designprinzipien (verbindlich in jeder Version)

1. **Mensch bewertet, KI entwirft.** Verbindlich wird eine Bewertung erst mit menschlicher Bestätigung.
2. **Keine Aussage ohne Quelle.** Beobachtetes und Vermutetes werden getrennt gehalten.
3. **Sicherheitsgrad kennzeichnen.** Bestätigtes Ereignis, frühes Signal und blosse Ankündigung sind zu unterscheiden.
4. **Fokus auf Veränderung.** Erfasst wird das Neue und sich Bewegende, kein Vollkatalog.
5. **Kontrolliertes Vokabular.** Klassifiziert wird nur in bestehende Listen; neue Labels brauchen Freigabe.
6. **Bewusste Quellenauswahl statt Rauschen.** Feste, kuratierte Quellen, kein offenes Web-Crawling.
7. **Historischer Vergleich mit Gegenprobe.** Jede Analogie nennt die Stelle, an der sie nicht mehr trägt.
8. **Aussensignal muss andocken.** Eine Beobachtung ohne Bezug zu Domäne, Methode oder Kompetenz bleibt wertlos.

Die vollständige Begründung steht in [docs/design-entscheidungen.md](docs/design-entscheidungen.md).

## Aufbau des Kerns

```
/docs         Konzept, Architektur, Designentscheidungen, Umgebungen & Branches
/schema       Schema-Definitionen (JSON Schema, als YAML)
/vocab-core   Starter-Taxonomien (Bereiche, Domänen, Kompetenzen, Methoden, Tech-Tags)
/patterns     Muster-Bibliothek für historische Vergleiche
/examples     Beispiel-Instanz (öffentlich, synthetisch) — Selbsttest des Kerns
/testing      Testkonzept-Umsetzung: Testfall-/Protokoll-Schema, Suite, pytest
/src          validate.py — validiert Daten gegen das Schema (Werkzeug, nicht Produkt)
Jenkinsfile   CI-Pipeline (schnelle Suite pro Build, Deploy je Umgebung)
Dockerfile    reproduzierbares Testimage
LICENSE
```

## Domänenmodell (Kurzform)

```
Taxonomy ──< Term (kann Kind eines Terms sein; max. 2 Ebenen in v1)
   └── area · domain · competence · method · tech_tag
                    │  (referenziert)
                    ▼
Source ──< Observation >── RadarEntry ──< Assessment ──< HistoricalAnalogy (n)
           (Eingangskorb)      │
                               └── area (1) · domains (n) · competences (n)
                                   methods (n) · tech_tags (n)
Event  (append-only)  → protokolliert jede Änderung
Report (t0 → t1)      → Projektion über Events + aktueller Radar-Stand
```

## Kern und Instanz

Die Trennung verläuft entlang einer **Repo-Grenze**, nicht entlang von
Konventionen (E23/E25). Öffentlich sind Schema, Mechanismus, Muster-Bibliothek
und Starter-Taxonomien. Privat — in einer separaten Instanz — sind Assessments,
Events, Bewertungsraster, Quellenliste und Identitäten.

Der Kern liest sein Datenverzeichnis aus der Konfiguration:

```bash
python src/validate.py --instance ../KI-Technology-Radar-Instanz
```

## Testen & Umgebungen

Der Radar folgt dem **Suite-Testkonzept** (deterministischer Runner, KI nur für
Sprache, Testart folgt Umgebungstreue). Bei jedem Build läuft die schnelle Suite
und erzeugt ein versioniertes **Testprotokoll**:

```bash
python testing/run_suite.py --env dev --instance examples/sample-instance
```

Vier Umgebungen und die Branch-Promotion (`dev → test → int → main/prod`) sind in
[docs/umgebungen-und-branches.md](docs/umgebungen-und-branches.md) beschrieben,
die Testkonzept-Umsetzung in [testing/README.md](testing/README.md).

## Stand

Release **R1**: Taxonomien + Ereignisprotokoll ab Eintrag 1 + ein von Hand
ausgefüllter Eintrag (Model Context Protocol). Zusätzlich die Testkonzept-
Grundlage (Schritt 1–2: Testfall-/Protokoll-Schema, schnelle Suite, CI-Pipeline).
Der Release-Plan steht in den Designentscheidungen.

## Lizenz

Siehe [LICENSE](LICENSE). *(Vorläufig MIT — bei Bedarf auf Apache-2.0 o. Ä. wechseln.)*
