#!/usr/bin/env python3
"""kandidaten.py — Eingangskorb-Ansicht (Kandidaten des Ingestion-Agenten).

Zeigt die noch NICHT ratifizierten Kandidaten (E4/E20) aus <instance>/inbox,
filterbar nach BRANCHE. Klar getrennt vom Radar: hier steht, was der Agent
gesammelt und entworfen hat; in den Radar hebt es der Mensch. Nur intern (E25).

  python view/kandidaten.py --instance ../KI-Technology-Radar-Instanz --out kandidaten.html
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


def load_yaml(p: Path):
    with p.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


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
    ap = argparse.ArgumentParser(description="Eingangskorb-/Kandidaten-Ansicht.")
    ap.add_argument("--instance", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    inst = Path(args.instance)
    if not inst.is_absolute():
        inst = (Path.cwd() / inst).resolve()

    labels = {t["id"]: t.get("label", t["id"])
              for t in collect(CORE / "vocab-core", "domain.yaml", "terms")}
    src_of = {s["id"]: s for s in collect(inst / "sources", "*.yaml", "sources")}

    # Kandidaten aus allen Inbox-Dateien (Format: candidates: [{observation, branchen, …}]).
    cands = []
    inbox = inst / "inbox"
    if inbox.exists():
        for p in sorted(inbox.rglob("*.yaml")):
            d = load_yaml(p)
            if isinstance(d, dict) and "candidates" in d:
                cands.extend(d["candidates"])

    def src_link(sid, target):
        # Link zeigt auf den ARTIKEL (target=obs.url) wenn vorhanden, sonst auf die Quelle.
        s = src_of.get(sid, {})
        name = esc(s.get("name", sid))
        href = target or s.get("url")
        return f'<a href="{esc(href)}" target="_blank" rel="noopener">{name}</a>' if href else name

    # Branchen, die tatsächlich vorkommen → Filter-Dropdown.
    present: dict[str, int] = {}
    for c in cands:
        for b in c.get("branchen", []):
            present[b] = present.get(b, 0) + 1
    opts = ['<option value="">Alle Branchen (' + str(len(cands)) + ")</option>"]
    for b in sorted(present, key=lambda x: labels.get(x, x)):
        opts.append(f'<option value="{esc(b)}">{esc(labels.get(b, b))} ({present[b]})</option>')

    # Karten, nach Relevanz absteigend.
    def relkey(c):
        r = c.get("relevance_general")
        return -(r if isinstance(r, int) else 0)
    cards = []
    for c in sorted(cands, key=relkey):
        o = c.get("observation", {})
        brs = c.get("branchen", [])
        data = " ".join(esc(b) for b in brs)
        chips = " ".join(f'<span class="chip">{esc(labels.get(b, b))}</span>' for b in brs)
        url = o.get("url")
        art = (f' · <a href="{esc(url)}" target="_blank" rel="noopener">Artikel öffnen ↗</a>') if url else ""
        rel = c.get("relevance_general")
        sug = c.get("suggested_entry") or "—"
        newbr = (f' · <span class="newbr">Branchen-Vorschlag: {esc(c["new_branche"])}</span>'
                 if c.get("new_branche") else "")
        srcs = ", ".join(src_link(s, url) for s in o.get("source_ids", []))
        titlehtml = (f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(o.get("title"))}</a>'
                     if url else esc(o.get("title")))
        cards.append(
            f'<article class="card" data-br="{data}">'
            f'<div class="chips">{chips}<span class="rel">Relevanz {esc(rel) if rel else "—"}</span></div>'
            f'<h3>{titlehtml}</h3>'
            f'<p class="sum">{esc(o.get("summary"))}</p>'
            f'<p class="meta">Vorschlag Eintrag: <b>{esc(sug)}</b>{newbr}</p>'
            f'<p class="cite">Quelle: {srcs} — {esc(o.get("citation"))}{art}</p>'
            f'</article>')

    stamp = datetime.datetime.now().astimezone().strftime("%d.%m.%Y %H:%M")
    body = ("".join(cards) if cards
            else '<p class="empty">Der Eingangskorb ist leer — der Ingestion-Agent hat noch '
                 'nichts gesammelt (oder alles wurde ratifiziert/geleert).</p>')

    doc = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Eingangskorb — KI-Radar</title>
<style>
  body{{margin:0;background:{PAPER};color:{INK};font-family:system-ui,-apple-system,sans-serif;padding:28px}}
  .wrap{{max-width:820px;margin:0 auto}}
  .sig{{font-size:12px;letter-spacing:.3em;text-transform:uppercase;color:{GOLD};margin:0}}
  a.back{{font-size:13px;color:{GOLD};text-decoration:none}}
  h1{{font-size:26px;font-weight:600;margin:4px 0 2px}}
  .sub{{color:#6b6862;font-size:14px;margin:0 0 6px}}
  .warn{{background:#fff;border-left:3px solid {GOLD};border-radius:6px;padding:10px 14px;font-size:13.5px;color:#4a4741;margin:12px 0 18px}}
  .bar{{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:#6b6862;margin:0 0 18px}}
  .bar select{{font:inherit;color:{INK};background:#fff;border:1px solid #e7e3da;border-radius:8px;padding:5px 9px}}
  .card{{background:#fff;border:1px solid #e7e3da;border-radius:12px;padding:14px 16px;margin:10px 0}}
  .chips{{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:6px}}
  .chip{{background:{PAPER};border:1px solid #e7e3da;border-radius:999px;padding:2px 10px;font-size:12px;color:#6b6862}}
  .rel{{margin-left:auto;font-size:12px;color:{GOLD};font-weight:600}}
  h3{{font-size:17px;font-weight:600;margin:2px 0 6px}}
  h3 a{{color:inherit;text-decoration:none;border-bottom:2px solid rgba(192,133,31,.4)}}
  h3 a:hover{{color:{GOLD}}}
  .sum{{font-size:14px;line-height:1.55;margin:0 0 8px}}
  .meta{{font-size:13px;color:#4a4741;margin:0 0 4px}}
  .newbr{{color:{GOLD}}}
  .cite{{font-size:12px;color:#8a867e;margin:0}}
  .cite a{{color:{GOLD};text-decoration:none;border-bottom:1px solid rgba(192,133,31,.35)}}
  .empty{{color:#6b6862;font-size:14px}}
  .note{{font-size:12px;color:#8a867e;margin:22px 0 0}}
</style></head><body><div class="wrap">
<a class="back" href="index.html">← zum Radar</a>
<p class="sig" style="margin-top:8px">Aletheia · Eingangskorb</p>
<h1>Kandidaten (noch nicht ratifiziert)</h1>
<p class="sub">Stand {stamp} · {len(cands)} Kandidaten · gesammelt vom Ingestion-Agenten</p>
<div class="warn"><b>Erfassung ≠ Geltung (E20).</b> Das hier ist der Eingangskorb, nicht der Radar.
Der Agent entwirft (KI), in den Radar hebt es der Mensch durch Ratifikation (E4). Belege/Zitate
sind zu prüfen.</div>
<label class="bar">Branche&nbsp;
<select id="brsel" onchange="filt()">{''.join(opts)}</select></label>
<div id="list">{body}</div>
<p class="note">Interne Sicht (E25). Erzeugt mit view/kandidaten.py — read-only.</p>
<script>
function filt(){{var v=document.getElementById('brsel').value;
document.querySelectorAll('.card').forEach(function(c){{
c.style.display=(!v||(' '+c.dataset.br+' ').indexOf(' '+v+' ')>=0)?'':'none';}});}}
</script>
</div></body></html>"""

    o = Path(args.out)
    if not o.is_absolute():
        o = (Path.cwd() / o).resolve()
    o.parent.mkdir(parents=True, exist_ok=True)
    o.write_text(doc, encoding="utf-8")
    print(f"Kandidaten-Ansicht: {o} ({len(cands)} Kandidaten)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
