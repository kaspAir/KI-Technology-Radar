#!/usr/bin/env python3
"""backfill.py — historische Meilensteine (2017–2025) aus einer KURATIERTEN,
verifizierten Liste als datierte Beobachtungen in den Radar einspeisen.

Kein Crawling (E6), keine erfundenen Fundstellen (E8): Quelle ist die vom Kurator
gepflegte Liste `<instance>/backfill/milestones.yaml` (jede Zeile mit echter URL +
Zitat). Für jeden Meilenstein wird — sofern `suggested_entry` auf ein existierendes
Thema zeigt — eine Beobachtung an dessen observations.yaml angehängt (dedupliziert
über die URL), markiert als Rekonstruktion (created_by: mensch:backfill, E21), plus
ein Event (observation.added). Zeigt suggested_entry ins Leere, landet der Fund als
Kandidat im Pool (Langschwanz).

  python src/backfill.py --instance ../KI-Technology-Radar-Instanz            # anhängen
  python src/backfill.py --instance ../KI-Technology-Radar-Instanz --dry-run  # nur zeigen

Ergänzend (Baustein A, braucht Key): arXiv-Jahresharvest via ingest.py, z.B.
  python src/ingest.py --instance <inst> --source source.research-ml \\
      --since 2019-01-01 --until 2019-12-31 --pool <inst>/inbox/pool.yaml
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

import yaml

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def load_yaml(p: Path):
    with p.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def dump_yaml(p: Path, obj) -> None:
    p.write_text(yaml.safe_dump(obj, allow_unicode=True, sort_keys=False), encoding="utf-8")


def slugify(s: str) -> str:
    s = s.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:48]


def main() -> int:
    ap = argparse.ArgumentParser(description="Historische Meilensteine als Beobachtungen einspeisen.")
    ap.add_argument("--instance", required=True)
    ap.add_argument("--file", default=None, help="Meilenstein-Liste (Default: <inst>/backfill/milestones.yaml)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    inst = Path(args.instance)
    if not inst.is_absolute():
        inst = (Path.cwd() / inst).resolve()
    mfile = Path(args.file) if args.file else inst / "backfill" / "milestones.yaml"
    if not mfile.exists():
        sys.exit(f"Meilenstein-Datei fehlt: {mfile}")
    milestones = (load_yaml(mfile) or {}).get("milestones", [])
    if not milestones:
        print("Keine Meilensteine in der Liste."); return 0

    entries_dir = inst / "entries"
    existing = {p.parent.name for p in entries_dir.glob("*/entry.yaml")}

    elog = inst / "events" / "events.log"
    txt = elog.read_text(encoding="utf-8") if elog.exists() else ""
    mx = max([int(m.group(1)) for m in re.finditer(r"evt\.bf-(\d+)", txt)] + [0])

    now = datetime.datetime.now(datetime.timezone.utc).astimezone().replace(microsecond=0).isoformat()
    events = []
    n_att, n_pool, n_skip = 0, 0, 0
    pool_new = []

    for m in milestones:
        url = m.get("url")
        slug = str(m.get("suggested_entry", "")).split(".", 1)[-1]
        date = str(m.get("date", ""))
        obs = {
            "id": "obs.bf-" + slugify(m.get("title", ""))[:40] + "-" + date[:4],
            "radar_entry_id": m.get("suggested_entry"),
            "source_ids": [m["source_id"]] if m.get("source_id") else [],
            "title": m.get("title"),
            "summary": m.get("summary"),
            "citation": m.get("cite"),
            "url": url,
            "confidence": m.get("confidence", "confirmed"),
            "status": "linked",
            "date_published": date,
            "date_observed": date,
            "created_by": "mensch:backfill",
        }
        if slug and slug in existing:
            of = entries_dir / slug / "observations.yaml"
            doc = load_yaml(of) or {"observations": []}
            doc.setdefault("observations", [])
            if any((o.get("url") and o.get("url") == url) for o in doc["observations"]):
                print(f"  · schon vorhanden, übersprungen: {slug} ← {m.get('title')[:50]}")
                n_skip += 1
                continue
            print(f"  + {slug} ← {date} {m.get('title')[:56]}")
            if not args.dry_run:
                doc["observations"].append(obs)
                dump_yaml(of, doc)
                mx += 1
                events.append({"id": f"evt.bf-{mx:04d}", "at": now, "actor": "mensch:backfill",
                               "verb": "observation.added", "subject_id": obs["id"],
                               "payload": {"to": m.get("suggested_entry"), "note": "REKONSTRUKTION (Backfill)"}})
            n_att += 1
        else:
            print(f"  ~ Pool (kein Thema): {date} {m.get('title')[:56]}")
            pool_new.append({"observation": obs, "branchen": m.get("branchen", []),
                             "suggested_entry": m.get("suggested_entry", ""),
                             "relevance_general": m.get("relevance_general", 3),
                             "reason": "Backfill-Meilenstein", "new_branche": ""})
            n_pool += 1

    if pool_new and not args.dry_run:
        pf = inst / "inbox" / "pool.yaml"
        pool = load_yaml(pf) or {"candidates": []}
        pool.setdefault("candidates", [])
        have = {(c.get("observation") or {}).get("url") for c in pool["candidates"]}
        added = [c for c in pool_new if (c["observation"].get("url") not in have)]
        pool["candidates"].extend(added)
        dump_yaml(pf, pool)

    if events and not args.dry_run:
        with elog.open("a", encoding="utf-8") as fh:
            for e in events:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")

    print(f"\n{n_att} als Belege angehängt · {n_pool} in den Pool · {n_skip} übersprungen"
          + (" (dry-run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
