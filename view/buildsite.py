#!/usr/bin/env python3
"""buildsite.py — erzeugt die komplette deploybare Site in einen Ordner.

  index.html            aktueller Radar
  radar-<jahr>.html     Radar-Stand Ende jedes vergangenen Ereignis-Jahres (Zeit-Umschalter)
  bericht.html          Bericht-Seite mit Zeitraum-Wähler

  python view/buildsite.py --instance ../KI-Technology-Radar-Instanz --mode internal --out out
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

CORE = Path(__file__).resolve().parent.parent

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def event_years(inst: Path) -> list[str]:
    ys = set()
    elog = inst / "events" / "events.log"
    if elog.exists():
        for line in elog.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                try:
                    ys.add(json.loads(line)["at"][:4])
                except Exception:
                    pass
    return sorted(ys)


def _items(base: Path, glob: str, key: str):
    """Alle Objekte aus allen passenden YAML-Dateien (Liste unter `key` oder Einzeldoc)."""
    out = []
    if not base.exists():
        return out
    for p in sorted(base.rglob(glob)):
        try:
            d = yaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, dict) and key in d:
            out.extend(d[key])
        elif isinstance(d, dict):
            out.append(d)
        elif isinstance(d, list):
            out.extend(d)
    return out


def entry_ids(inst: Path) -> list[str]:
    return [e["id"] for e in _items(inst / "entries", "entry.yaml", "entries")
            if isinstance(e, dict) and e.get("id")]


def competence_ids(inst: Path) -> list[str]:
    """Union: ratifizierte Kritikalitäten ∪ von Einträgen referenzierte Kompetenzen —
    deckt genau die aus dem Radar verlinkbaren Kompetenz-Dossiers ab."""
    ids = {c["competence_id"] for c in _items(inst / "competences", "*.yaml", "competence_assessments")
           if isinstance(c, dict) and c.get("competence_id")}
    for e in _items(inst / "entries", "entry.yaml", "entries"):
        for cid in (e.get("competences") or []) if isinstance(e, dict) else []:
            ids.add(cid)
    return sorted(ids)


def pattern_ids(inst: Path) -> list[str]:
    """Von Einträgen (historical_analogies) referenzierte Muster — nur diese sind verlinkt."""
    ids = set()
    for a in _items(inst / "entries", "assessments.yaml", "assessments"):
        for h in (a.get("historical_analogies") or []) if isinstance(a, dict) else []:
            if h.get("pattern"):
                ids.add(h["pattern"])
    return sorted(ids)


def run(script: str, *extra: str) -> None:
    r = subprocess.run([sys.executable, str(CORE / "view" / script), *extra])
    if r.returncode != 0:
        raise SystemExit(f"{script} fehlgeschlagen (Exit {r.returncode})")


def main() -> int:
    ap = argparse.ArgumentParser(description="Deploybare Site erzeugen.")
    ap.add_argument("--instance", required=True)
    ap.add_argument("--mode", choices=["internal", "public"], default="internal")
    ap.add_argument("--out", default="out")
    args = ap.parse_args()
    inst = Path(args.instance)
    if not inst.is_absolute():
        inst = (Path.cwd() / inst).resolve()
    out = Path(args.out)
    if not out.is_absolute():
        out = (Path.cwd() / out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    base = ["--instance", str(inst), "--mode", args.mode]

    # Aktueller Radar
    run("render.py", *base, "--out", str(out / "index.html"))

    # Jahres-Snapshots (alle Ereignis-Jahre ausser dem aktuellsten = 'Aktuell')
    years = event_years(inst)
    cur = years[-1] if years else None
    snaps = [y for y in years if y != cur]
    for y in snaps:
        run("render.py", *base, "--as-of", f"{y}-12-31", "--out", str(out / f"radar-{y}.html"))

    # Bericht-Seite mit Zeitraum-Wähler
    run("reportsite.py", "--instance", str(inst), "--out", str(out / "bericht.html"))

    # Eingangskorb / Kandidaten-Ansicht (branche-filterbar) — nur intern (E25).
    if args.mode == "internal":
        run("kandidaten.py", "--instance", str(inst), "--out", str(out / "kandidaten.html"))

    # Detail-Dossier je Eintrag (detail-<slug>.html) — Ziel der Blip-/Karten-Links.
    ids = entry_ids(inst)
    for eid in ids:
        slug = eid.split(".", 1)[-1]
        run("detail.py", "--instance", str(inst), "--entry", eid,
            "--mode", args.mode, "--out", str(out / f"detail-{slug}.html"))

    # Kompetenz- und Muster-Dossiers — nur intern (strategische/analytische Sicht,
    # E25/E26; in der öffentlichen Ansicht existieren diese Panels nicht).
    kids, pids = [], []
    if args.mode == "internal":
        kids = competence_ids(inst)
        for cid in kids:
            slug = cid.split(".", 1)[-1]
            run("detailkomp.py", "--instance", str(inst), "--competence", cid,
                "--mode", args.mode, "--out", str(out / f"detailkomp-{slug}.html"))
        pids = pattern_ids(inst)
        for pid in pids:
            slug = pid.split(".", 1)[-1]
            run("detailmuster.py", "--instance", str(inst), "--pattern", pid,
                "--mode", args.mode, "--out", str(out / f"detailmuster-{slug}.html"))

    print(f"Site erzeugt in {out}: index.html + {len(snaps)} Jahres-Snapshots "
          f"({', '.join(snaps) or '—'}) + bericht.html + {len(ids)} Detail-Dossiers "
          f"+ {len(kids)} Kompetenz- + {len(pids)} Muster-Dossiers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
