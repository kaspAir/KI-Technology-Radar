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

    print(f"Site erzeugt in {out}: index.html + {len(snaps)} Jahres-Snapshots "
          f"({', '.join(snaps) or '—'}) + bericht.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
