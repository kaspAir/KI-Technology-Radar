#!/usr/bin/env python3
"""render.py — erzeugt eine statische Radar-Ansicht (HTML) aus einer Instanz.

Read-only Reporting-Ansicht (keine interaktive Produkt-UI — die kommt später).
Liest Bereiche aus dem Kern (vocab-core) und die Einträge/Assessments aus einer
Instanz, platziert jeden Eintrag als Blip (Sektor = Bereich, Radius = Ring) und
schreibt eine selbstenthaltene HTML-Datei.

Modi:
  --mode internal  (Standard) volle Sicht inkl. relevance_org, Handlungsdruck
  --mode public    nur Allowlist-Felder (name, area, ring, first_seen) — E26.
                   Für eine etwaige Veröffentlichung; nie private Wertung zeigen.

Aufruf:
  python view/render.py --instance ../KI-Technology-Radar-Instanz --out view/output/radar.html
"""
from __future__ import annotations

import argparse
import datetime
import html
import math
import sys
from pathlib import Path

import yaml

CORE = Path(__file__).resolve().parent.parent
GOLD = "#C0851F"
INK = "#23262D"
PAPER = "#F8F6F2"

# Ringe von innen nach aussen; Reject wird separat gelistet, nicht platziert.
RINGS = ["Adopt", "Pilot", "Explore", "Watch"]
RING_OUTER = {"Adopt": 52, "Pilot": 98, "Explore": 140, "Watch": 175}
RING_MID = {"Adopt": 26, "Pilot": 75, "Explore": 119, "Watch": 157}
CX, CY, RMAX = 340, 250, 175


def load_yaml(path: Path):
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def collect(base: Path, glob: str, key: str) -> list[dict]:
    items: list[dict] = []
    if not base.exists():
        return items
    for p in sorted(base.rglob(glob)):
        data = load_yaml(p)
        if isinstance(data, dict) and key in data:
            items.extend(data[key])
        elif isinstance(data, dict):
            items.append(data)
        elif isinstance(data, list):
            items.extend(data)
    return items


def top_area(area_id: str) -> str:
    # 'area.produkte.entwicklungswerkzeuge' -> 'area.produkte'
    parts = area_id.split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else area_id


def polar(angle_deg: float, r: float) -> tuple[float, float]:
    a = math.radians(angle_deg)
    return CX + r * math.cos(a), CY + r * math.sin(a)


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description="Radar-Ansicht (HTML) aus einer Instanz erzeugen.")
    ap.add_argument("--instance", required=True)
    ap.add_argument("--mode", choices=["internal", "public"], default="internal")
    ap.add_argument("--out", default=str(CORE / "view" / "output" / "radar.html"))
    args = ap.parse_args()
    inst = Path(args.instance)
    if not inst.is_absolute():
        inst = (Path.cwd() / inst).resolve()

    # Bereiche (nur oberste Ebene) als Sektoren, in Katalog-Reihenfolge.
    area_terms = [t for t in collect(CORE / "vocab-core", "area.yaml", "terms")
                  if not t.get("parent_id")]
    areas = [t["id"] for t in area_terms]
    area_label = {t["id"]: t["label"] for t in area_terms}
    n = len(areas)
    sector_center = {aid: -90 + i * (360 / n) for i, aid in enumerate(areas)}

    # Einträge + jüngstes Assessment.
    entries = collect(inst / "entries", "entry.yaml", "entries")
    assessments = collect(inst / "entries", "assessments.yaml", "assessments")
    latest: dict[str, dict] = {}
    for a in assessments:
        rid = a.get("radar_entry_id")
        if rid and (rid not in latest or a.get("valid_from", "") > latest[rid].get("valid_from", "")):
            latest[rid] = a

    placed, rejected = [], []
    # Gruppieren nach (Sektor, Ring) für Winkel-Versatz bei Mehrfachbelegung.
    groups: dict[tuple[str, str], list[dict]] = {}
    for e in entries:
        if e.get("status") == "archived":
            continue
        ring = e.get("current_ring")
        aid = top_area(e.get("area", ""))
        if ring == "Reject":
            rejected.append(e)
            continue
        if ring not in RING_MID or aid not in sector_center:
            continue
        groups.setdefault((aid, ring), []).append(e)

    for (aid, ring), es in groups.items():
        base = sector_center[aid]
        span = 46  # Grad Streuung innerhalb Sektor/Ring
        for k, e in enumerate(es):
            off = 0 if len(es) == 1 else (k - (len(es) - 1) / 2) * (span / max(1, len(es)))
            x, y = polar(base + off, RING_MID[ring])
            placed.append((e, latest.get(e["id"], {}), x, y))

    # --- SVG bauen -----------------------------------------------------------
    svg = [f'<svg viewBox="0 0 680 460" width="100%" role="img" xmlns="http://www.w3.org/2000/svg">']
    svg.append('<title>KI-Technology-Radar</title><desc>Radar-Ansicht der aktuellen Einträge.</desc>')
    # Ringe aussen -> innen
    for i, ring in enumerate(reversed(RINGS)):
        r = RING_OUTER[ring]
        op = [0.05, 0.08, 0.12, 0.18][i]
        svg.append(f'<circle cx="{CX}" cy="{CY}" r="{r}" fill="{GOLD}" fill-opacity="{op}" '
                   f'stroke="{INK}" stroke-opacity="0.18"/>')
    # Sektor-Trenner (an den Grenzen zwischen Sektoren)
    for i in range(n):
        bnd = -90 - (360 / n) / 2 + i * (360 / n)
        x, y = polar(bnd, RMAX)
        svg.append(f'<line x1="{CX}" y1="{CY}" x2="{x:.1f}" y2="{y:.1f}" stroke="{INK}" '
                   f'stroke-opacity="0.15"/>')
    svg.append(f'<circle cx="{CX}" cy="{CY}" r="3" fill="{INK}" fill-opacity="0.6"/>')
    # Ring-Beschriftung entlang der Vertikalen nach oben
    for ring in RINGS:
        _, y = polar(-90, RING_MID[ring])
        svg.append(f'<text x="{CX}" y="{y+4:.0f}" text-anchor="middle" font-size="11" '
                   f'fill="{INK}" fill-opacity="0.55" font-family="system-ui,sans-serif" '
                   f'font-weight="500">{ring}</text>')
    # Bereichs-Beschriftung
    for aid in areas:
        ang = sector_center[aid]
        x, y = polar(ang, RMAX + 20)
        c = math.cos(math.radians(ang))
        anchor = "middle" if abs(c) < 0.35 else ("start" if c > 0 else "end")
        svg.append(f'<text x="{x:.0f}" y="{y+4:.0f}" text-anchor="{anchor}" font-size="13" '
                   f'fill="{INK}" font-weight="500" font-family="system-ui,sans-serif">'
                   f'{esc(area_label[aid])}</text>')
    # Blips
    for e, a, x, y in placed:
        svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" fill="{PAPER}"/>'
                   f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{GOLD}"/>')
        lx = x + 12
        svg.append(f'<text x="{lx:.1f}" y="{y+4:.1f}" text-anchor="start" font-size="12.5" '
                   f'fill="{INK}" font-weight="500" font-family="system-ui,sans-serif">'
                   f'{esc(e.get("name"))}</text>')
    svg.append("</svg>")

    # --- Karten --------------------------------------------------------------
    cards = []
    order = {r: i for i, r in enumerate(RINGS)}
    for e, a, *_ in sorted(placed, key=lambda t: order.get(t[0].get("current_ring"), 9)):
        ring = e.get("current_ring", "")
        area = area_label.get(top_area(e.get("area", "")), "")
        if args.mode == "public":
            detail = f'first seen {esc(e.get("first_seen"))}'
        else:
            detail = (f'Relevanz {esc(a.get("relevance_general"))}/{esc(a.get("relevance_org"))} · '
                      f'Handlungsdruck {esc(a.get("action_pressure"))} · {esc(a.get("momentum"))}')
        cards.append(
            f'<div class="card"><div class="meta">{esc(area)} · '
            f'<span class="ring">{esc(ring)}</span></div>'
            f'<div class="name">{esc(e.get("name"))}</div>'
            f'<div class="detail">{detail}</div></div>')

    stamp = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    mode_note = ("Öffentliche Ansicht (Allowlist, E26)" if args.mode == "public"
                 else "Interne Ansicht — enthält private Wertung (E25), nicht veröffentlichen")
    rej = ""
    if rejected:
        names = ", ".join(esc(e.get("name")) for e in rejected)
        rej = f'<p class="rej">Reject (bewusst nicht verfolgt): {names}</p>'

    doc = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KI-Technology-Radar</title>
<style>
  body{{margin:0;background:{PAPER};color:{INK};font-family:system-ui,-apple-system,sans-serif;padding:28px}}
  .wrap{{max-width:720px;margin:0 auto}}
  .sig{{font-size:12px;letter-spacing:.3em;text-transform:uppercase;color:{GOLD};margin:0}}
  h1{{font-size:26px;font-weight:600;margin:2px 0 2px}}
  .sub{{color:#6b6862;font-size:14px;margin:0 0 18px}}
  .legend{{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:13px;color:#6b6862;margin:8px 0 18px}}
  .legend b{{color:{INK};font-weight:500}}
  .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}}
  .card{{background:#fff;border:1px solid #e7e3da;border-radius:12px;padding:14px 16px}}
  .meta{{font-size:12.5px;color:#6b6862}}
  .ring{{color:{GOLD};font-weight:600}}
  .name{{font-size:17px;font-weight:600;margin:2px 0 6px}}
  .detail{{font-size:13px;color:#6b6862;line-height:1.5}}
  .note{{font-size:12px;color:#8a867e;margin:18px 0 0}}
  .rej{{font-size:13px;color:#6b6862;margin:10px 0 0}}
</style></head><body><div class="wrap">
<p class="sig">Aletheia · Radar</p>
<h1>KI-Technology-Radar</h1>
<p class="sub">Stand {stamp} · {len(placed)} Einträge</p>
{''.join(svg)}
<div class="legend"><b>Ringe (innen→aussen):</b>
<span><b>Adopt</b> produktiv nutzen</span><span><b>Pilot</b> real erproben</span>
<span><b>Explore</b> experimentieren</span><span><b>Watch</b> beobachten</span></div>
<div class="cards">{''.join(cards)}</div>
{rej}
<p class="note">{mode_note}. Erzeugt aus der Instanz mit view/render.py — read-only.</p>
</div></body></html>"""

    out = Path(args.out)
    if not out.is_absolute():
        out = (Path.cwd() / out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    print(f"Modus: {args.mode} · {len(placed)} Einträge platziert"
          + (f", {len(rejected)} Reject" if rejected else ""))
    print(f"Geschrieben: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
