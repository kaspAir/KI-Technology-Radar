#!/usr/bin/env python3
"""detailmuster.py — Detail-Dossier je historischem Muster (klickbar aus Radar).

Beantwortet: Was ist das Muster (Kern, Frühindikator) und WIE bildet es sich —
konkret an den Radar-Einträgen, die es aufrufen (Analogie, Verlauf, Lehre und
Pflicht-Gegenprobe). Verlinkt die Einträge und deren Quellen. Read-only, intern.

  python view/detailmuster.py --instance ../KI-Technology-Radar-Instanz \
      --pattern pattern.abstraktions-sprung --out detailmuster-abstraktions-sprung.html
"""
from __future__ import annotations

import argparse
import datetime
import html
import sys
from pathlib import Path

import yaml

from _fmt import ch_date

CORE = Path(__file__).resolve().parent.parent
GOLD, INK, PAPER = "#C0851F", "#23262D", "#F8F6F2"

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def _norm(v):
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_norm(x) for x in v]
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.isoformat()
    return v


def load_yaml(p: Path):
    with p.open(encoding="utf-8") as fh:
        return _norm(yaml.safe_load(fh))


def collect(base: Path, glob: str, key: str) -> list[dict]:
    items: list[dict] = []
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


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description="Detail-Dossier je historischem Muster.")
    ap.add_argument("--instance", required=True)
    ap.add_argument("--pattern", required=True)
    ap.add_argument("--mode", choices=["internal", "public"], default="internal")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    inst = Path(args.instance)
    if not inst.is_absolute():
        inst = (Path.cwd() / inst).resolve()
    pid = args.pattern

    patterns = {p["id"]: p for p in collect(CORE / "patterns", "patterns.yaml", "patterns")}
    pat = patterns.get(pid)
    if not pat:
        sys.exit(f"Muster nicht gefunden: {pid}")

    entries = {e["id"]: e for e in collect(inst / "entries", "entry.yaml", "entries")}
    asses = collect(inst / "entries", "assessments.yaml", "assessments")
    by_entry: dict[str, list] = {}
    for a in asses:
        by_entry.setdefault(a.get("radar_entry_id"), []).append(a)
    for lst in by_entry.values():
        lst.sort(key=lambda a: a.get("valid_from", ""))
    obs_all = collect(inst / "entries", "observations.yaml", "observations")
    src_of = {s["id"]: s for s in collect(inst / "sources", "*.yaml", "sources")}

    def slug_of(eid: str) -> str:
        return eid.split(".", 1)[-1]

    def src_link(sid: str) -> str:
        s = src_of.get(sid, {})
        name = esc(s.get("name", sid))
        url = s.get("url")
        return f'<a href="{esc(url)}" target="_blank" rel="noopener">{name}</a>' if url else name

    # Alle Anwendungen dieses Musters: (Eintrag, Assessment, Analogie), chronologisch.
    uses = []
    for rid, lst in by_entry.items():
        for a in lst:
            for h in (a.get("historical_analogies") or []):
                if h.get("pattern") == pid:
                    uses.append((rid, a, h))
    uses.sort(key=lambda u: u[1].get("valid_from", ""))

    out = []
    w = out.append

    # 1. Definition — Kern + Frühindikator (Schlagzeile) und, wenn vorhanden, die
    #    ausführliche Herleitung (wie der Radar auf beide kommt).
    herl = pat.get("herleitung")
    herl_html = (f'<div class="herlwrap"><p class="herlcap">Wie der Radar auf Kern '
                 f'und Frühindikator kommt</p><p class="herl">{esc(herl)}</p></div>'
                 if herl else '')
    w('<section class="card">'
      f'<p class="kern"><b>Kern:</b> {esc(pat.get("kern"))}</p>'
      f'<p class="frueh"><b>Frühindikator:</b> {esc(pat.get("fruehindikator"))}</p>'
      f'{herl_html}'
      '</section>')

    # 2. Wie bildet sich das Muster
    w("<h2>Wie sich das Muster bildet</h2>")
    w('<p>Muster sind wiederkehrende Formen der Technologie-Geschichte. Der Radar '
      'vergleicht eine neue Entwicklung mit dem Muster, wenn ihr Verlauf dieselbe Form '
      'annimmt — <b>immer mit Pflicht-Gegenprobe</b> (der „Grenze"): Wo trägt die '
      'Analogie <i>nicht</i>? So entsteht die Einordnung nicht aus Bauchgefühl, sondern '
      'aus belegten Einzelfällen (E13). Unten die konkreten Fälle, an denen dieses '
      'Muster im Radar sichtbar wurde.</p>')

    # 3. Anwendungen im Radar
    w(f"<h2>Fälle im Radar ({len(uses)})</h2>")
    if not uses:
        w("<p>Dieses Muster ist noch an keinen Eintrag geknüpft.</p>")
    else:
        for rid, a, h in uses:
            e = entries.get(rid, {})
            eobs = [o for o in obs_all if o.get("radar_entry_id") == rid]
            srcs = []
            seen = set()
            for o in eobs:
                for s in o.get("source_ids", []):
                    if s not in seen:
                        seen.add(s)
                        srcs.append(src_link(s))
            srctxt = (' · <span class="cite">Quellen: ' + ", ".join(srcs) + "</span>") if srcs else ""
            w('<div class="usecard">'
              f'<div class="uhead"><a href="detail-{esc(slug_of(rid))}.html">{esc(e.get("name"))}</a>'
              f'<span class="when">Ring {esc(a.get("ring"))} · ab {ch_date(a.get("valid_from"))}</span></div>'
              f'<p><b>Analogie:</b> {esc(h.get("similarity"))}</p>'
              f'<p><b>Was geschah:</b> {esc(h.get("what_happened"))}</p>'
              f'<p><b>Lehre:</b> {esc(h.get("lesson"))}</p>'
              f'<p class="limit"><b>Grenze des Vergleichs:</b> {esc(h.get("limit"))}</p>'
              f'<p class="src">{srctxt.lstrip(" ·")}</p>'
              '</div>')

    mode_note = "Interne, analytische Sicht (E25/E26) — nicht veröffentlichen."
    doc = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(pat.get("label"))} — Muster — KI-Radar</title>
<style>
  body{{margin:0;background:{PAPER};color:{INK};font-family:system-ui,-apple-system,sans-serif;padding:28px}}
  .wrap{{max-width:760px;margin:0 auto}}
  .sig{{font-size:12px;letter-spacing:.3em;text-transform:uppercase;color:{GOLD};margin:0}}
  a.back{{font-size:13px;color:{GOLD};text-decoration:none}}
  h1{{font-size:26px;font-weight:600;margin:4px 0 4px}}
  .sub{{color:#6b6862;font-size:14px;margin:0 0 18px}}
  h2{{font-size:17px;font-weight:600;margin:22px 0 8px}}
  p{{font-size:14px;line-height:1.6}}
  .card{{background:#fff;border:1px solid #e7e3da;border-radius:12px;padding:14px 16px;margin-top:6px}}
  .kern{{margin:0}}
  .frueh{{margin:8px 0 0;color:#4a4741}}
  .herlwrap{{margin:12px 0 0;padding:12px 0 0;border-top:1px solid #eee7db}}
  .herlcap{{margin:0 0 4px;font-size:12px;font-weight:600;letter-spacing:.02em;text-transform:uppercase;color:{GOLD}}}
  .herl{{margin:0;color:#3a3833}}
  .usecard{{background:#fff;border:1px solid #e7e3da;border-radius:12px;padding:14px 16px;margin:10px 0}}
  .uhead{{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:6px}}
  .uhead a{{font-size:16px;font-weight:600;color:{INK};text-decoration:none;border-bottom:2px solid rgba(192,133,31,.4)}}
  .uhead a:hover{{color:{GOLD}}}
  .when{{font-size:12px;color:#8a867e;white-space:nowrap}}
  .limit{{background:{PAPER};border-left:3px solid {GOLD};padding:8px 12px;border-radius:4px}}
  .cite,.src{{font-size:12px;color:#8a867e}}
  .cite a,.src a{{color:{GOLD};text-decoration:none;border-bottom:1px solid rgba(192,133,31,.35)}}
  .note{{font-size:12px;color:#8a867e;margin:24px 0 0}}
</style></head><body><div class="wrap">
<a class="back" href="index.html">← zum Radar</a>
<p class="sig" style="margin-top:8px">Aletheia · Radar · Muster</p>
<h1>{esc(pat.get("label"))}</h1>
<p class="sub">Historisches Muster (E13) · Vergleich mit Pflicht-Gegenprobe</p>
{''.join(out)}
<p class="note">{mode_note} Erzeugt mit view/detailmuster.py — read-only.</p>
</div></body></html>"""

    o = Path(args.out)
    if not o.is_absolute():
        o = (Path.cwd() / o).resolve()
    o.parent.mkdir(parents=True, exist_ok=True)
    o.write_text(doc, encoding="utf-8")
    print(f"Muster-Dossier: {o}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
