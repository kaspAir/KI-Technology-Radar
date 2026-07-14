#!/usr/bin/env python3
"""marktsite.py — erzeugt markt.html: Anbieter-Landschaft (Firmen-Ampel je
relevanter Firma) + Makro-Indikatoren zur KI-Ökonomie (Baustein B).

Quelle: <instance>/markt/anbieter.yaml (kuratiert, web-verifiziert, E8). Die
Exponierung je Firma wird aus den provider-Tags der Radar-Themen berechnet
(verknüpft mit dem Blast-Radius, C). STRATEGISCHE Sicht, nur internal (E25/E26):
KEINE Anlage-/Markt-Timing-Aussage — der Zweck ist Belastbarkeit/Resilienz.

  python view/marktsite.py --instance ../KI-Technology-Radar-Instanz --out markt.html
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

TEND = {  # tendenz -> (emoji, label, farbe)
    "staerker": ("🟢", "stärker", "#2e7d32"),
    "stabil": ("🟢", "stabil", "#2e7d32"),
    "gespannt": ("🟠", "gespannt", "#C0851F"),
    "unter_druck": ("🔴", "unter Druck", "#C0362C"),
}
RICHT = {"gruen": ("🟢", "#2e7d32"), "orange": ("🟠", "#C0851F"), "rot": ("🔴", "#C0362C")}


def load_yaml(p: Path):
    with p.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description="Anbieter-Landschaft + Makro-Indikatoren (markt.html).")
    ap.add_argument("--instance", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    inst = Path(args.instance)
    if not inst.is_absolute():
        inst = (Path.cwd() / inst).resolve()

    data = load_yaml(inst / "markt" / "anbieter.yaml") or {}
    firmen = data.get("firmen", [])
    indikatoren = data.get("indikatoren", [])

    # Exponierung je Anbieter-Slug aus den provider-Tags der Themen.
    exposure: dict[str, list] = {}
    for ep in sorted((inst / "entries").glob("*/entry.yaml")):
        e = load_yaml(ep)
        slug = e["id"].split(".", 1)[-1]
        for pr in (e.get("providers") or []):
            exposure.setdefault(pr, []).append((e.get("name"), slug))

    def src_link(url, cite):
        c = esc(cite)
        return f'<a href="{esc(url)}" target="_blank" rel="noopener">{c}</a>' if url else c

    out = []
    w = out.append

    # 1. Firmen-Ampel
    w('<h2>Anbieter-Landschaft — Tendenz je Firma</h2>')
    w('<p class="lead">Wie geht es den relevanten Trägern der KI-Welle — und wie stark '
      'hängen <b>unsere</b> Themen an ihnen (Blast-Radius)? Ausgewogen und belegt; '
      '<b>keine Anlage-Aussage</b>. Der Hebel ist Resilienz, nicht Markt-Timing.</p>')
    w('<div class="firms">')
    order = {"unter_druck": 0, "gespannt": 1, "stabil": 2, "staerker": 3}
    for f in sorted(firmen, key=lambda x: (-len(exposure.get(x.get("exposure_slug"), [])),
                                           order.get(x.get("tendenz"), 9))):
        emoji, lbl, col = TEND.get(f.get("tendenz"), ("·", "—", INK))
        exp = exposure.get(f.get("exposure_slug"), [])
        explinks = ", ".join(f'<a href="detail-{esc(s)}.html">{esc(n)}</a>' for n, s in exp)
        exptxt = (f'<b>{len(exp)}</b> abhängige Theme{"" if len(exp) == 1 else "n"}: {explinks}'
                  if exp else 'kein Thema hängt direkt daran')
        sig = ""
        for s in (f.get("signale") or []):
            conf = s.get("confidence", "")
            sig += (f'<li>{esc(s.get("text"))} '
                    f'<span class="cite">{ch_date(s.get("date"))} · {src_link(s.get("url"), s.get("cite"))}'
                    f'{" · " + esc(conf) if conf else ""}</span></li>')
        w(f'<section class="firm" style="border-left-color:{col}">'
          f'<div class="fhead"><span class="tend" style="color:{col}">{emoji} {esc(lbl)}</span>'
          f'<span class="fname">{esc(f.get("name"))}</span>'
          f'<span class="frole">{esc(f.get("rolle"))}</span></div>'
          f'<p class="fnote">{esc(f.get("note"))}</p>'
          f'<ul class="fsig">{sig}</ul>'
          f'<p class="fexp">Unsere Exponierung: {exptxt}</p>'
          '</section>')
    w('</div>')

    # 2. Makro-Indikatoren
    w('<h2>Makro-Indikatoren — Gesamtbild des Marktes</h2>')
    w('<p class="lead">Leitindikatoren der KI-Ökonomie. Sie prognostizieren keinen '
      'Crash — sie zeigen die <b>Spannung</b> (viel Kapital &amp; Bau, dünne Erträge) '
      'gegen die <b>Tragfähigkeit</b> (reale Nachfrage, reifende offene Modelle).</p>')
    w('<div class="inds">')
    for i in indikatoren:
        emoji, col = RICHT.get(i.get("richtung"), ("·", INK))
        w(f'<section class="ind" style="border-left-color:{col}">'
          f'<div class="ihead"><span class="idot">{emoji}</span>'
          f'<span class="iname">{esc(i.get("name"))}</span></div>'
          f'<p class="itext">{esc(i.get("text"))}</p>'
          f'<p class="cite">{ch_date(i.get("date"))} · {src_link(i.get("url"), i.get("cite"))}</p>'
          '</section>')
    w('</div>')

    stamp = datetime.date.today().isoformat()
    doc = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KI-Markt & Anbieter — KI-Radar</title>
<style>
  body{{margin:0;background:{PAPER};color:{INK};font-family:system-ui,-apple-system,sans-serif;padding:28px}}
  .wrap{{max-width:780px;margin:0 auto}}
  a.back{{font-size:13px;color:{GOLD};text-decoration:none}}
  .sig{{font-size:12px;letter-spacing:.3em;text-transform:uppercase;color:{GOLD};margin:8px 0 0}}
  h1{{font-size:26px;font-weight:600;margin:4px 0 2px}}
  .sub{{color:#6b6862;font-size:14px;margin:0 0 8px}}
  h2{{font-size:18px;font-weight:600;margin:26px 0 6px}}
  .lead{{font-size:14px;line-height:1.6;color:#4a4741;margin:0 0 12px}}
  .firms,.inds{{display:flex;flex-direction:column;gap:10px}}
  .firm,.ind{{background:#fff;border:1px solid #e7e3da;border-left-width:5px;border-radius:12px;padding:12px 15px}}
  .fhead{{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}}
  .tend{{font-size:13px;font-weight:700;white-space:nowrap}}
  .fname{{font-size:17px;font-weight:600}}
  .frole{{font-size:12px;color:#8a867e;margin-left:auto}}
  .fnote{{font-size:13.5px;color:#3a3833;margin:6px 0 6px;line-height:1.5}}
  .fsig{{margin:0;padding-left:18px}}
  .fsig li{{font-size:13.5px;line-height:1.55;margin:0 0 4px}}
  .fexp{{font-size:13px;color:#4a4741;margin:8px 0 0;border-top:1px solid #eee7db;padding-top:7px}}
  .ihead{{display:flex;align-items:baseline;gap:8px}}
  .iname{{font-size:15px;font-weight:600}}
  .itext{{font-size:13.5px;line-height:1.55;color:#3a3833;margin:5px 0 4px}}
  .cite{{font-size:12px;color:#8a867e}}
  .cite a,.fsig a,.fexp a{{color:{GOLD};text-decoration:none;border-bottom:1px solid rgba(192,133,31,.35)}}
  .fexp a{{border-bottom:1px dotted #b3afa6;color:inherit}}
  .fexp a:hover,.cite a:hover{{color:{GOLD}}}
  .note{{font-size:12px;color:#8a867e;margin:22px 0 0}}
</style></head><body><div class="wrap">
<a class="back" href="index.html">← zum Radar</a>
<p class="sig">Aletheia · Radar · Markt</p>
<h1>KI-Markt & Anbieter</h1>
<p class="sub">Stand {ch_date(stamp)} · Tendenzen der Träger + Makro-Indikatoren · verknüpft mit dem Blast-Radius</p>
{''.join(out)}
<p class="note">Interne, strategische Sicht (E25/E26) — nicht veröffentlichen. Belege
web-verifiziert, ausgewogen; KEINE Anlage-/Markt-Timing-Empfehlung. Erzeugt mit
view/marktsite.py — read-only.</p>
</div></body></html>"""

    o = Path(args.out)
    if not o.is_absolute():
        o = (Path.cwd() / o).resolve()
    o.parent.mkdir(parents=True, exist_ok=True)
    o.write_text(doc, encoding="utf-8")
    print(f"Markt-Ansicht: {o} ({len(firmen)} Firmen, {len(indikatoren)} Indikatoren)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
