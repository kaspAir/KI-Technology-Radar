# Konzept & Architektur

Dieses Verzeichnis hält das versionierbare Konzept des KI-Technology-Radars.

- **[design-entscheidungen.md](design-entscheidungen.md)** — die 27 Designentscheidungen (E1–E27) mit Begründung und der Release-Plan.

## Zweck

Aus vielen einzelnen Meldungen entsteht eine nachvollziehbare, über die Zeit
verfolgbare Einschätzung, woran eine Organisation arbeiten, was sie beobachten
und welche Kompetenzen sie aufbauen sollte. Der eigentliche strategische
Mehrwert ist eine **ableitbare Kompetenzempfehlung**: welche Fähigkeiten in den
nächsten Monaten wichtiger werden.

## Die drei getrennten Zeit-Konzepte (E12)

| Konzept   | Feld                              | Frage                          | Wer                 |
|-----------|-----------------------------------|--------------------------------|---------------------|
| Horizont  | `time_horizon`                    | Wann wird es relevant?         | Mensch (KI-Vorschlag) |
| Verlauf   | `first_seen` + Assessment-Historie| Wohin bewegt es sich?          | abgeleitet          |
| Momentum  | `momentum`                        | Heizt es auf oder kühlt es ab? | Mensch (KI-Vorschlag) |

## Ringe (die Empfehlung, E10)

| Ring    | Bedeutung                    | ~ ThoughtWorks |
|---------|------------------------------|----------------|
| Watch   | Beobachten, noch nichts tun  | Assess         |
| Explore | Aktiv experimentieren        | Trial          |
| Pilot   | In echtem Kontext erproben   | Trial+         |
| Adopt   | Produktiv nutzen             | Adopt          |
| Reject  | Bewusst nicht verfolgen      | Hold           |

## Klassifikations-Achsen (E11/E18)

Alle fünf sind technisch dasselbe — Taxonomien aus Termen mit optionalem
Elternteil. Kein Sonderfall „Bereich".

| Achse            | Kardinalität | Frage                       |
|------------------|--------------|-----------------------------|
| Bereiche (area)  | genau 1      | in welchem Beobachtungsfeld |
| Domänen          | n            | für wen relevant            |
| Kompetenzen      | n            | welche Fähigkeit wird wichtiger |
| Methoden         | n            | was verändert sich konkret  |
| Tech-Tags        | n            | was ist es technisch        |

## Berichtsstruktur (Projektion, kein Artefakt — E21)

Der Bericht wird nicht gepflegt, sondern für einen Zeitraum `t0 → t1` aus dem
Ereignisprotokoll und dem aktuellen Radar-Stand berechnet.

```
0. Aktivität                        ← direkt aus dem Ereignisprotokoll
1. Wichtigste Entwicklungen (3–5)
2. Bewegungen (Ring-Wechsel + Momentum)
3. Chancen
4. Risiken
5. Empfohlene Kompetenzentwicklung  ← aus Kompetenz-Verknüpfungen aggregiert
6. Historische Einordnung
7. Empfehlung / Entscheidungen
8. Fällige Überprüfungen (review_due überschritten)
```
