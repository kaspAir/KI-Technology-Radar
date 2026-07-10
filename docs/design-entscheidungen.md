# Designentscheidungen (E1–E27)

Diese Entscheidungen sind in jeder Version einzuhalten. Sie sind zugleich die
Kriterien, an denen sich die Qualität des Radars messen lässt.

| # | Entscheidung | Begründung |
|---|--------------|------------|
| E1 | Lean starten, dann portieren: erst YAML/Tabelle, 2–3 echte Berichte, dann festes Tooling. | Das erste Schema ist immer unreif. Schema getrennt vom Werkzeug validieren, sonst baut man zweimal. |
| E2 | Observation und RadarEntry trennen. | Der Radar lebt von der Bewegung der Einträge über die Zeit. Das geht nur, wenn das verfolgte Ding eine eigene Identität hat, an die datierte Belege andocken. |
| E3 | Assessment versioniert und zeitgestempelt. | „Wie hat sich die Einschätzung bewegt?" ist wertvoller als eine Momentaufnahme. |
| E4 | KI entwirft, Mensch bestätigt; erst die Bestätigung macht einen Eintrag verbindlich. | Verantwortung bleibt beim Menschen; Vollautomatik würde den Zweck (beurteilbar, nicht nur sichtbar) aushebeln. |
| E5 | Bewertungsraster zuerst manuell entwickeln. | Man kann kein Urteil automatisieren, das man selbst noch nicht explizit gemacht hat. |
| E6 | Kein offenes Crawling; feste Quellenliste, monatlicher Batch. | Ein automatischer Feed flutet mit Rauschen. Niedrige Taktung macht KI-Ausfälle folgenlos. |
| E7 | Kontrolliertes Vokabular; KI sortiert ein, erweitert nicht. | Sonst in drei Monaten 40 Domänen und keine Auswertbarkeit mehr. |
| E8 | Quellenpflicht für jede Aussage. | Ein Eintrag mit erfundener Ankündigung ist schlimmer als kein Eintrag — er zerstört das Vertrauen. |
| E9 | Divergenzprotokoll: KI-Entwurf und menschliche Endfassung beide speichern. | Aus der Differenz lernt man das eigene Bewertungsraster schärfer kennen. |
| E10 | Nur ein Stance-Feld (`ring`), keine zweite „technische Reife"-Achse. | Beide messen fast dasselbe; Redundanz vermeiden. |
| E11 | Vier Klassifikations-Achsen: Domänen, Kompetenzen, Methoden, Tech-Tags. | KI verändert nicht nur Branchen und Kompetenzen, sondern konkrete Methoden. |
| E12 | Zeit in drei Konzepte trennen: Horizont, Verlauf, Momentum. | Vermischt werden sie unbrauchbar; getrennt beantworten sie drei verschiedene Fragen. |
| E13 | Historischer Vergleich mit Pflicht-Gegenprobe (`limit`). | Ein Vergleich ohne seine Grenze ist keine Erkenntnis, sondern eine Verwechslung. |
| E14 | KI speichert Argumente, nicht nur Werte (`draft_arguments`). | Der Mensch prüft eine Begründung, keine Zahl; Abweichungen werden auf Argument-Ebene sichtbar. |
| E15 | Kompetenzempfehlung wird abgeleitet, nicht separat gepflegt. | Sie aggregiert sich aus den Kompetenz-Verknüpfungen der hochrelevanten Einträge einer Periode. |
| E16 | Sicherheitsgrad je Beobachtung erfassen (`confidence`). | Gerade bei schnell bewegter KI ist die ehrliche Kennzeichnung von Unsicherheit Teil der Genauigkeit. |
| E17 | Radar erfasst Veränderung, keinen Vollkatalog. | Der Wert liegt im Erkennen des Neuen gegen den Hintergrund des Bekannten. |
| E18 | Alle Achsen sind Taxonomien mit demselben Mechanismus; Hierarchie optional, max. 2 Ebenen in v1. | Ein Mechanismus, fünf Instanzen — Unterbereiche kosten kein neues Konzept. |
| E19 | Terme werden nie gelöscht, nur `deprecated`. Zuweisung an Blätter, Auswertung rollt auf die Eltern hoch. | Versionierte Assessments referenzieren Terme historisch. Ein gelöschter Term zerreisst die Historie. |
| E20 | Erfassung und Geltung trennen: KI sammelt in einen Eingangskorb; in den Radar tritt nur Ratifiziertes. | Der Radar wirkt jederzeit aktuell, ohne E4/E6 zu verletzen: laufend beobachten, periodisch urteilen. |
| E21 | Append-only Ereignisprotokoll. Der Bericht ist eine Projektion, kein gepflegtes Artefakt. | Ein Protokoll lässt sich nicht rückwirkend anlegen. |
| E22 | Der Radar zeigt das Alter jeder Einschätzung (`review_due`). | „Immer aktuell" ist ohne sichtbares Urteilsalter eine Behauptung, keine Eigenschaft. |
| E23 | Kern und Instanz trennen. Keine Organisation kommt im Schema vor. | Nur so ist der Kern veröffentlichbar. Ein Organisationsname in einem Feldnamen macht den Kern unteilbar. |
| E24 | Relevanz-Achsen heissen `relevance_general` und `relevance_org` — nie ein Eigenname. | Der Kunde ist Konfiguration, nicht Schema. |
| E25 | Sichtbarkeit auf Entitätsklassen, nicht auf Feldern. | Klassengrenzen lassen sich mechanisch durchsetzen (Repo-Grenze); Feldgrenzen beruhen auf Disziplin und versagen. |
| E26 | Export per Allowlist. Veröffentlicht wird nur, was ausdrücklich freigegeben ist. | Eine Denylist vergisst das Feld, das erst nächstes Jahr hinzukommt. |
| E27 | Reviewer als pseudonyme ID. Die Zuordnung Person ↔ ID bleibt in der Instanz. | Namen in einem veröffentlichten Datensatz sind Personendaten. |

## Regeln für Hierarchien

1. **Bereich ist eine Eigenschaft des Eintrags, nicht der Quelle.** Eine Quelle kann in mehrere Bereiche einzahlen; der Eintrag gehört in genau einen.
2. **Zuweisung an Blätter, Auswertung rollt hoch.** Ein Eintrag wird dem tiefsten passenden Term zugeordnet. „Alles unter Produkte" liefert automatisch alle Unterbereiche mit.
3. **Terme sind Daten, kein Code.** Neue Unterbereiche entstehen durch Ergänzen einer YAML-Datei.
4. **Nie löschen, nur deprecated (E19).** Deprecated-Terme sind für neue Zuweisungen gesperrt, bleiben aber lesbar.
5. **Umhängen ist eine Migration, kein Edit** — mit Datum und Eintrag im Ereignisprotokoll.

## Kern und Instanz

**Kern — öffentlich (der Mechanismus)**

```
/docs /schema /vocab-core /patterns /export /src   LICENSE
```

**Instanz — privat (das Urteil einer Organisation)**

```
/vocab /sources /agents /inbox /entries /events /reports /identities
```

Privat sind ganze Klassen (E25): Assessments, Events, Bewertungsraster,
Quellenliste, Identitäten. Bei einer bewussten Veröffentlichung: nur über einen
Export mit Allowlist (E26) — freigegeben `name, area, ring, summary, citation,
first_seen`; **nie** `rationale, relevance_org, draft_arguments, reviewer, Events`.

## Bewusst nicht in v1 (Scope-Bremse)

Kein offenes Web-Crawling · kein festes Ziel-Tooling vor 2–3 stabilen Zyklen ·
keine zweite Reife-Achse neben `ring` · keine automatische Bestätigung · kein
Auto-Commit aus dem Eingangskorb · keine UI (YAML/Markdown genügt) · `momentum`
optional · Hierarchien in v1 nur einstufig befüllen (zweite Ebene vorgesehen,
aber leer) · keine Mandantenfähigkeit im Code — eine Instanz pro Organisation,
getrennt durch Konfiguration und Repo-Grenze.

## Release-Plan

| Release | Inhalt | Zweck |
|---------|--------|-------|
| **R1** | Taxonomien (mit `parent_id`) + Ereignisprotokoll ab Eintrag 1 + 1 Eintrag von Hand | Schema am echten Fall testen; Historie von Beginn an lückenlos |
| R2 | 3 Einträge, 1 Monatsbericht — manuell | Bewertungsraster entwickeln (E5) |
| R3 | KI erstellt `draft_arguments`, Mensch bestätigt | KI-Entwurf einführen (E4/E14) |
| R4 | Zweiter Zyklus → erste Bewegungen & Momentum; Bericht als Projektion | Zeit-Dimension und Ereignisprotokoll validieren |
| R5 | Historische Vergleiche + Muster-Liste | Vergleichslogik |
| R6 | Abgeleitete Kompetenzempfehlung im Bericht | strategischer Mehrwert |
| R7+ | Portierung ins Ziel-Tooling | erst wenn Schema stabil |
| R8 | Kern vom Instanz-Repo trennen, Lizenz, Allowlist-Export, Starter-Taxonomien | Veröffentlichbarkeit — frühestens nach R4 |

> **Abweichung von der Vorlage:** E23/E25 begründen die Trennung damit, dass nur
> eine Repo-Grenze verlässlich ist. Deshalb ist die Kern-/Instanz-Trennung
> **schon ab R1** als zwei getrennte Repositorys umgesetzt, nicht erst ab R8.
> R8 reduziert sich damit auf Lizenz, Allowlist-Export und das Ausreifen der
> Starter-Taxonomien.
