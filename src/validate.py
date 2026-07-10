#!/usr/bin/env python3
"""validate.py — validiert Radar-Daten gegen das Schema (E1).

Das Werkzeug ist bewusst getrennt vom Radar-Produkt: es prueft das Schema am
echten Fall, nicht mehr. Es liest den Kern (Schema, vocab-core, patterns) und
eine private Instanz (vocab, sources, entries, events ...). Der Instanz-Pfad
kommt aus der Konfiguration (E23), in dieser Reihenfolge:

    1. --instance <pfad>
    2. Umgebungsvariable RADAR_INSTANCE
    3. radar.config.yaml im aktuellen Verzeichnis (Schluessel: instance)

Prueft:
  * jedes Objekt gegen sein JSON-Schema
  * referenzielle Integritaet ueber das kontrollierte Vokabular (E7)
  * Quellenpflicht, Sicherheitsgrad, Pflicht-Gegenprobe (E8/E13/E16)
  * Konsistenz von entry.current_ring mit dem juengsten ratifizierten
    Assessment (abgeleitet-aber-gespeichert -> Staleness-Warnung)
  * jede Zeile in events.log gegen das Event-Schema (E21)

Exit-Code 0 = keine Fehler (Warnungen erlaubt), 1 = mindestens ein Fehler.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("Fehlt: pyyaml  (pip install pyyaml)")
try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:
    sys.exit("Fehlt: jsonschema  (pip install jsonschema)")

CORE = Path(__file__).resolve().parent.parent
RING_ORDER = ["Watch", "Explore", "Pilot", "Adopt", "Reject"]


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.ok = 0

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def passed(self) -> None:
        self.ok += 1


# --------------------------------------------------------------------------- IO
def _normalize(value):
    """YAML parst 2026-07-10 als date-Objekt. Fuer die JSON-Schema-Pruefung
    (type: string, format: date) normalisieren wir date/datetime zu ISO-Strings,
    damit handgeschriebenes YAML Datumswerte nicht quoten muss."""
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    return value


def load_yaml(path: Path):
    with path.open(encoding="utf-8") as fh:
        return _normalize(yaml.safe_load(fh))


def load_schema(name: str) -> Draft202012Validator:
    data = load_yaml(CORE / "schema" / f"{name}.schema.yaml")
    return Draft202012Validator(data, format_checker=FormatChecker())


def resolve_instance(cli_value: str | None) -> Path:
    candidate = cli_value or os.environ.get("RADAR_INSTANCE")
    if not candidate:
        cfg = Path.cwd() / "radar.config.yaml"
        if cfg.exists():
            candidate = (load_yaml(cfg) or {}).get("instance")
    if not candidate:
        sys.exit(
            "Kein Instanz-Pfad. Nutze --instance <pfad>, setze RADAR_INSTANCE "
            "oder lege radar.config.yaml mit 'instance: <pfad>' an."
        )
    path = Path(candidate)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    if not path.exists():
        sys.exit(f"Instanz-Pfad existiert nicht: {path}")
    return path


def yaml_docs(folder: Path, glob: str, key: str) -> list[dict]:
    """Sammelt Objekte aus den passenden Dateien einer Ebene ein.

    Akzeptiert drei Formen je Datei: Liste unter <key>, einzelnes Objekt,
    oder eine reine Liste auf oberster Ebene. Der glob trennt die Dateiarten
    (entry.yaml vs observations.yaml vs assessments.yaml).
    """
    items: list[dict] = []
    if not folder.exists():
        return items
    for path in sorted(folder.rglob(glob)):
        data = load_yaml(path)
        if data is None:
            continue
        if isinstance(data, dict) and key in data:
            items.extend(data[key])
        elif isinstance(data, list):
            items.extend(data)
        elif isinstance(data, dict):
            items.append(data)
    return items


# ---------------------------------------------------------------- schema-pruefung
def check(validator: Draft202012Validator, obj: dict, label: str, rep: Report) -> bool:
    errs = sorted(validator.iter_errors(obj), key=lambda e: list(e.path))
    if errs:
        for e in errs:
            loc = "/".join(str(p) for p in e.path) or "(root)"
            rep.error(f"{label}: {loc}: {e.message}")
        return False
    rep.passed()
    return True


# ------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="Validiert Radar-Daten gegen das Schema.")
    ap.add_argument("--instance", help="Pfad zum privaten Instanz-Repo")
    args = ap.parse_args()
    inst = resolve_instance(args.instance)
    rep = Report()

    schemas = {
        n: load_schema(n)
        for n in ("term", "source", "observation", "radar-entry", "assessment", "event", "pattern")
    }

    # --- Vokabular: Kern + Instanz zusammenfuehren ------------------------------
    terms = yaml_docs(CORE / "vocab-core", "*.yaml", "terms") + yaml_docs(inst / "vocab", "*.yaml", "terms")
    term_index: dict[str, dict] = {}
    for t in terms:
        if not check(schemas["term"], t, f"term {t.get('id', '?')}", rep):
            continue
        if t["id"] in term_index:
            rep.error(f"term {t['id']}: doppelte ID")
        term_index[t["id"]] = t

    def valid_ref(ref: str, taxonomy: str, where: str) -> None:
        t = term_index.get(ref)
        if t is None:
            rep.error(f"{where}: unbekannter Term '{ref}'")
        elif t["taxonomy"] != taxonomy:
            rep.error(f"{where}: '{ref}' ist {t['taxonomy']}, erwartet {taxonomy}")
        elif t["status"] != "active":
            rep.error(f"{where}: '{ref}' ist deprecated — fuer neue Zuweisungen gesperrt (E19)")

    # parent_id-Integritaet + max. 2 Ebenen
    for t in term_index.values():
        parent = t.get("parent_id")
        if parent:
            p = term_index.get(parent)
            if p is None:
                rep.error(f"term {t['id']}: parent_id '{parent}' existiert nicht")
            elif p["taxonomy"] != t["taxonomy"]:
                rep.error(f"term {t['id']}: parent gehoert zu anderer Taxonomie")
            elif p.get("parent_id"):
                rep.error(f"term {t['id']}: mehr als 2 Ebenen (v1: max. 2)")

    # --- Patterns ---------------------------------------------------------------
    patterns = yaml_docs(CORE / "patterns", "*.yaml", "patterns")
    pattern_ids = set()
    for p in patterns:
        if check(schemas["pattern"], p, f"pattern {p.get('id', '?')}", rep):
            pattern_ids.add(p["id"])

    # --- Sources (Instanz) ------------------------------------------------------
    sources = yaml_docs(inst / "sources", "*.yaml", "sources")
    source_ids = set()
    for s in sources:
        if check(schemas["source"], s, f"source {s.get('id', '?')}", rep):
            source_ids.add(s["id"])

    # --- Entries (Instanz) ------------------------------------------------------
    entries = yaml_docs(inst / "entries", "entry.yaml", "entries")
    entry_ids = set()
    for e in entries:
        if not check(schemas["radar-entry"], e, f"entry {e.get('id', '?')}", rep):
            continue
        entry_ids.add(e["id"])
        eid = e["id"]
        valid_ref(e["area"], "area", f"entry {eid}.area")
        for ref in e.get("tech_tags", []):
            valid_ref(ref, "tech_tag", f"entry {eid}.tech_tags")
        for ref in e.get("domains", []):
            valid_ref(ref, "domain", f"entry {eid}.domains")
        for ref in e.get("competences", []):
            valid_ref(ref, "competence", f"entry {eid}.competences")
        for ref in e.get("methods", []):
            valid_ref(ref, "method", f"entry {eid}.methods")

    # --- Observations (Instanz) -------------------------------------------------
    observations = yaml_docs(inst / "entries", "observations.yaml", "observations") + yaml_docs(inst / "inbox", "*.yaml", "observations")
    for o in observations:
        if not check(schemas["observation"], o, f"observation {o.get('id', '?')}", rep):
            continue
        oid = o["id"]
        for sref in o.get("source_ids", []):
            if sref not in source_ids:
                rep.error(f"observation {oid}: unbekannte source_id '{sref}'")
        rid = o.get("radar_entry_id")
        if o["status"] == "linked" and not rid:
            rep.error(f"observation {oid}: status 'linked' aber kein radar_entry_id")
        if rid and rid not in entry_ids:
            rep.error(f"observation {oid}: radar_entry_id '{rid}' existiert nicht")

    # --- Assessments (Instanz) --------------------------------------------------
    assessments = yaml_docs(inst / "entries", "assessments.yaml", "assessments")
    latest_ring: dict[str, tuple[str, str]] = {}  # entry_id -> (valid_from, ring)
    for a in assessments:
        if not check(schemas["assessment"], a, f"assessment {a.get('id', '?')}", rep):
            continue
        aid = a["id"]
        rid = a["radar_entry_id"]
        if rid not in entry_ids:
            rep.error(f"assessment {aid}: radar_entry_id '{rid}' existiert nicht")
        da = a["draft_arguments"]
        for ref in da.get("affected_domains", []):
            valid_ref(ref, "domain", f"assessment {aid}.affected_domains")
        for ref in da.get("affected_competences", []):
            valid_ref(ref, "competence", f"assessment {aid}.affected_competences")
        for ref in da.get("affected_methods", []):
            valid_ref(ref, "method", f"assessment {aid}.affected_methods")
        for h in a.get("historical_analogies", []):
            pat = h["pattern"]
            if pat.startswith("pattern.") and pat not in pattern_ids:
                rep.error(f"assessment {aid}: pattern '{pat}' nicht in /patterns")
        # juengstes Assessment je Eintrag merken
        prev = latest_ring.get(rid)
        if prev is None or a["valid_from"] > prev[0]:
            latest_ring[rid] = (a["valid_from"], a["ring"])

    # current_ring-Konsistenz (abgeleitet-aber-gespeichert)
    for e in entries:
        if e["id"] not in entry_ids:
            continue
        derived = latest_ring.get(e["id"])
        stored = e.get("current_ring")
        if derived is None:
            if stored is not None:
                rep.warn(f"entry {e['id']}: current_ring={stored}, aber kein Assessment vorhanden")
        elif stored != derived[1]:
            rep.warn(
                f"entry {e['id']}: current_ring={stored} weicht vom juengsten "
                f"Assessment ({derived[1]}, valid_from {derived[0]}) ab"
            )

    # --- Events (Instanz, JSON Lines) -------------------------------------------
    events_log = inst / "events" / "events.log"
    if events_log.exists():
        for n, line in enumerate(events_log.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError as ex:
                rep.error(f"events.log:{n}: kein gueltiges JSON ({ex.msg})")
                continue
            check(schemas["event"], ev, f"events.log:{n}", rep)
    else:
        rep.warn("Keine events/events.log gefunden — Historie leer (E21)")

    # --- Ausgabe ----------------------------------------------------------------
    print(f"Kern:    {CORE}")
    print(f"Instanz: {inst}")
    print(
        f"Geprueft: {len(term_index)} Terme, {len(pattern_ids)} Muster, "
        f"{len(source_ids)} Quellen, {len(entry_ids)} Eintraege, "
        f"{len(observations)} Beobachtungen, {len(assessments)} Assessments."
    )
    for w in rep.warnings:
        print(f"  WARN  {w}")
    for e in rep.errors:
        print(f"  FEHLER {e}")
    if rep.errors:
        print(f"\n{len(rep.errors)} Fehler, {len(rep.warnings)} Warnungen.")
        return 1
    print(f"\nOK — {rep.ok} Objekte valide, {len(rep.warnings)} Warnungen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
