#!/usr/bin/env python3
"""ratify.py — Batch-Ratifikation: ausgewählte Eingangskorb-Kandidaten -> Radar.

Nimmt eine Auswahl-Datei (JSON-Liste von Kandidaten, wie sie die Kandidaten-Ansicht
`kandidaten.html` per Klick herunterlädt) und erzeugt daraus echte Einträge:
entry.yaml + observations.yaml + assessments.yaml + Events. Bewusst als
SCHNELL-AUFNAHME auf Ring **Watch** (rel < 4, ohne erzwungene Analogie) — die
tiefere Bewertung (Ring/Relevanz/Gegenprobe) machst du danach pro Eintrag.
Mensch ist der Ratifizierende (E4): --reviewer.

  python src/ratify.py --instance ../KI-Technology-Radar-Instanz --selection auswahl.json

Danach: validieren, Site bauen, committen.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

import yaml

CORE = Path(__file__).resolve().parent.parent
TYPE_AREA = {"research": "area.forschung", "vendor": "area.produkte",
             "product": "area.produkte", "regulator": "area.recht-regulatorik",
             "community": "area.markt-praxis"}

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def load_yaml(p: Path):
    with p.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def collect(base: Path, glob: str, key: str):
    items = []
    if not base.exists():
        return items
    for p in sorted(base.rglob(glob)):
        d = load_yaml(p)
        if isinstance(d, dict) and key in d:
            items.extend(d[key])
        elif isinstance(d, dict):
            items.append(d)
        elif isinstance(d, list):
            items.extend(d)
    return items


def slugify(s: str, n: int = 42) -> str:
    s = (s or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s[:n].strip("-")) or "x"


def dump(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(obj, allow_unicode=True, sort_keys=False), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Batch-Ratifikation ausgewählter Kandidaten.")
    ap.add_argument("--instance", required=True)
    ap.add_argument("--selection", required=True, help="JSON-Liste ausgewählter Kandidaten")
    ap.add_argument("--reviewer", default="mensch:r1")
    ap.add_argument("--ring", default="Watch")
    ap.add_argument("--run-date", default=datetime.date.today().isoformat())
    args = ap.parse_args()
    inst = Path(args.instance)
    if not inst.is_absolute():
        inst = (Path.cwd() / inst).resolve()

    sel = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    if isinstance(sel, dict) and "candidates" in sel:
        sel = sel["candidates"]
    if not isinstance(sel, list) or not sel:
        sys.exit("Auswahl-Datei enthält keine Kandidaten-Liste.")

    valid_domains = {t["id"] for t in collect(CORE / "vocab-core", "domain.yaml", "terms")}
    src_type = {s["id"]: s.get("type") for s in collect(inst / "sources", "*.yaml", "sources")}
    existing = {e["id"] for e in collect(inst / "entries", "entry.yaml", "entries")}

    # nächste freie evt.rat-Nummer bestimmen
    elog = inst / "events" / "events.log"
    maxn = 0
    if elog.exists():
        for m in re.finditer(r"evt\.rat-(\d+)", elog.read_text(encoding="utf-8")):
            maxn = max(maxn, int(m.group(1)))
    evn = [maxn]

    def eid():
        evn[0] += 1
        return f"evt.rat-{evn[0]:04d}"

    now = f"{args.run_date}T12:00:00+02:00"
    events, created, skipped = [], [], []
    review_due = f"{int(args.run_date[:4]) + 1}{args.run_date[4:]}"

    for c in sel:
        o = c.get("observation") or {}
        title = o.get("title") or ""
        slug = slugify(title)
        eidv = f"entry.{slug}"
        if not title or eidv in existing:
            skipped.append((title or "(ohne Titel)", "existiert bereits / kein Titel"))
            continue
        existing.add(eidv)
        branchen = [b for b in (c.get("branchen") or []) if b in valid_domains] or ["domain.querschnitt-grundlagen"]
        area = TYPE_AREA.get(src_type.get((o.get("source_ids") or [""])[0]), "area.markt-praxis")
        first_seen = o.get("date_published") or args.run_date
        draft_by = o.get("created_by") if str(o.get("created_by", "")).startswith("ki:") else "ki:claude-opus-4"
        obs_id = o.get("id") or f"obs.ingest-{slug}"
        ass_id = f"assess.{slug}-001"

        # Beobachtung (aus Korb übernommen, jetzt verlinkt)
        obs = dict(o)
        obs.update({"radar_entry_id": eidv, "status": "linked"})

        entry = {
            "id": eidv, "name": title[:90], "area": area, "tech_tags": [],
            "domains": branchen, "competences": [], "methods": [],
            "first_seen": first_seen, "current_ring": args.ring,
            "review_due": review_due, "status": "active",
        }
        rel = c.get("relevance_general")
        rel = min(rel, 3) if isinstance(rel, int) else 3     # <4 → keine Analogie nötig (E13)
        opp = c.get("reason") or o.get("summary") or "Aus dem Eingangskorb aufgenommen."
        assess = {
            "id": ass_id, "radar_entry_id": eidv, "decided_at": now, "valid_from": args.run_date,
            "draft_by": draft_by, "draft_ring": args.ring,
            "draft_arguments": {
                "opportunities": [{"statement": opp[:280], "citation": obs_id}],
                "risks": [], "affected_domains": branchen,
                "affected_competences": [], "affected_methods": [],
            },
            "draft_rationale": "Batch-Schnellaufnahme aus dem Eingangskorb.",
            "time_horizon": "mid", "momentum": "steady",
            "relevance_general": rel, "relevance_org": 2, "action_pressure": "low",
            "ring": args.ring,
            "rationale": (f"Schnell-Ratifikation (Batch, {args.reviewer}): auf den Radar zum "
                          "Beobachten genommen; Ring/Relevanz/Gegenprobe noch zu vertiefen. — PRIVAT (E25)."),
            "reviewer": args.reviewer,
        }

        base = inst / "entries" / slug
        dump(base / "entry.yaml", entry)
        dump(base / "observations.yaml", {"observations": [obs]})
        dump(base / "assessments.yaml", {"assessments": [assess]})

        for verb, actor, subj, payload in [
            ("observation.added", args.reviewer, obs_id, "Aus Eingangskorb ratifiziert (Batch)"),
            ("entry.created", args.reviewer, eidv, f"{title[:60]} aufgenommen (Batch, Ring {args.ring})"),
            ("observation.linked", args.reviewer, obs_id, {"to": eidv}),
            ("assessment.drafted", draft_by, ass_id, f"Entwurf Ring {args.ring}"),
            ("assessment.ratified", args.reviewer, ass_id, "Ratifiziert durch Mensch (E4)"),
            ("ring.changed", args.reviewer, eidv, {"from": None, "to": args.ring}),
        ]:
            events.append({"id": eid(), "at": now, "actor": actor, "verb": verb,
                           "subject_id": subj, "payload": payload})
        created.append(eidv)

    if events:
        with elog.open("a", encoding="utf-8") as fh:
            for ev in events:
                fh.write(json.dumps(ev, ensure_ascii=False) + "\n")

    print(f"Ratifiziert (neue Einträge): {len(created)}")
    for e in created:
        print(f"  + {e}")
    if skipped:
        print(f"Übersprungen: {len(skipped)}")
        for t, why in skipped:
            print(f"  · {t[:50]} — {why}")
    print("\nNächste Schritte: validieren, Site bauen, committen.")
    print(f"  python radar.py validate --instance {args.instance}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
