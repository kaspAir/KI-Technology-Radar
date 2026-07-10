# src — Validierung

`validate.py` prüft Radar-Daten gegen das Schema (E1). Es ist ein *Werkzeug zur
Schemaentwicklung*, nicht das Radar-Produkt — bewusst klein gehalten.

## Voraussetzungen

```bash
pip install pyyaml jsonschema
```

## Aufruf

Der Kern liest sein Datenverzeichnis aus der Konfiguration (E23), in dieser
Reihenfolge:

```bash
python src/validate.py --instance ../KI-Technology-Radar-Instanz
# oder:
export RADAR_INSTANCE=../KI-Technology-Radar-Instanz && python src/validate.py
# oder: radar.config.yaml im aktuellen Verzeichnis mit  instance: ../KI-Technology-Radar-Instanz
```

Siehe [radar.config.example.yaml](../radar.config.example.yaml).

## Was geprüft wird

- jedes Objekt gegen sein JSON-Schema (`/schema`)
- referenzielle Integrität gegen das kontrollierte Vokabular (E7): Bereiche,
  Domänen, Kompetenzen, Methoden, Tech-Tags — inkl. richtiger Taxonomie und
  `active`-Status (deprecated-Terme sind für neue Zuweisungen gesperrt, E19)
- `parent_id`-Integrität und max. 2 Ebenen (v1)
- Quellenpflicht: jede Observation nennt existierende `source_ids` (E8)
- `status: linked` verlangt ein gültiges `radar_entry_id`
- Pattern-Referenzen in historischen Analogien zeigen auf `/patterns`
- **`current_ring`-Konsistenz**: der am Eintrag gespeicherte Ring wird gegen den
  Ring des jüngsten Assessments geprüft (Warnung bei Abweichung — Schutz gegen
  die abgeleitet-aber-gespeichert-Staleness)
- jede Zeile in `events.log` gegen das Event-Schema (E21)

Exit-Code `0` = keine Fehler (Warnungen erlaubt), `1` = mindestens ein Fehler.
