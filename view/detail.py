#!/usr/bin/env python3
"""detail.py — Detail-Dossier je Eintrag (klickbar aus dem Radar).

Zeigt Beobachtungen, aktuelle Bewertung mit Begründung, historischen Vergleich
mit Pflicht-Gegenprobe und den VERLAUF über die Zeit (alle Assessments). Read-only.
internal = volle Sicht (private Wertung, E25); public = nur Allowlist (E26).

  python view/detail.py --instance ../KI-Technology-Radar-Instanz --entry entry.mcp --out detail-mcp.html
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
RING_MEAN = {"Watch": "beobachten", "Explore": "aktiv experimentieren",
             "Pilot": "in echtem Kontext erproben", "Adopt": "produktiv nutzen",
             "Reject": "bewusst nicht verfolgen"}

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


def top_area(a: str) -> str:
    parts = (a or "").split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else a


def main() -> int:
    ap = argparse.ArgumentParser(description="Detail-Dossier je Eintrag.")
    ap.add_argument("--instance", required=True)
    ap.add_argument("--entry", required=True)
    ap.add_argument("--mode", choices=["internal", "public"], default="internal")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    inst = Path(args.instance)
    if not inst.is_absolute():
        inst = (Path.cwd() / inst).resolve()
    internal = args.mode != "public"

    labels = {}
    for f in ("area", "domain", "competence", "method", "tech-tag"):
        for t in collect(CORE / "vocab-core", f"{f}.yaml", "terms"):
            labels[t["id"]] = t.get("label", t["id"])
    for t in collect(inst / "vocab", "*.yaml", "terms"):
        labels[t["id"]] = t.get("label", t["id"])
    pat_label = {p["id"]: p.get("label", p["id"]) for p in collect(CORE / "patterns", "patterns.yaml", "patterns")}
    src_of = {s["id"]: s for s in collect(inst / "sources", "*.yaml", "sources")}

    def src_link(sid: str, target: str = "") -> str:
        # Link zeigt auf den ARTIKEL (target=obs.url) wenn vorhanden, sonst auf die Quelle.
        s = src_of.get(sid, {})
        name = esc(s.get("name", sid))
        href = target or s.get("url")
        return f'<a href="{esc(href)}" target="_blank" rel="noopener">{name}</a>' if href else name

    entries = {e["id"]: e for e in collect(inst / "entries", "entry.yaml", "entries")}
    entry = entries.get(args.entry)
    if not entry:
        sys.exit(f"Eintrag nicht gefunden: {args.entry}")
    obs = [o for o in collect(inst / "entries", "observations.yaml", "observations")
           if o.get("radar_entry_id") == args.entry]
    # Chronologisch (älteste zuerst) — so liest sich die Beleg-Linie als Geschichte
    # des Themas, inkl. der Backfill-Meilensteine (GPT-1 → GPT-2 → GPT-3 → …).
    obs.sort(key=lambda o: str(o.get("date_published") or ""))
    asses = sorted([a for a in collect(inst / "entries", "assessments.yaml", "assessments")
                    if a.get("radar_entry_id") == args.entry], key=lambda a: a.get("valid_from", ""))
    latest = asses[-1] if asses else {}

    def chips(ids):
        return " ".join(f'<span class="chip">{esc(labels.get(i, i))}</span>' for i in (ids or []))

    ring = entry.get("current_ring", "")
    area = labels.get(top_area(entry.get("area", "")), "")
    out = []
    w = out.append

    # Aktuelle Einschätzung
    if latest:
        div = ""
        if latest.get("draft_ring") and latest.get("draft_ring") != latest.get("ring"):
            div = (f'<p class="div">Divergenz (E9): KI-Entwurf <b>{esc(latest["draft_ring"])}</b> '
                   f'→ Endfassung <b>{esc(latest["ring"])}</b>.</p>')
        rows = [("Zeit-Horizont", latest.get("time_horizon")), ("Momentum", latest.get("momentum")),
                ("Handlungsdruck", latest.get("action_pressure")),
                ("Relevanz allgemein", latest.get("relevance_general"))]
        if internal:
            rows.append(("Relevanz Organisation", latest.get("relevance_org")))
        meta = "".join(f'<div><span>{esc(k)}</span><b>{esc(v)}</b></div>' for k, v in rows if v is not None)
        rat = f'<p class="rat">{esc(latest.get("rationale"))}</p>' if internal and latest.get("rationale") else ""
        w(f'<section class="card"><div class="meta2">{meta}</div>{div}{rat}</section>')

    # Chancen / Risiken (internal)
    if internal and latest.get("draft_arguments"):
        da = latest["draft_arguments"]
        for kind, title in (("opportunities", "Chancen"), ("risks", "Risiken")):
            items = da.get(kind, [])
            if items:
                w(f'<h2>{title}</h2><ul>')
                for it in items:
                    w(f'<li>{esc(it.get("statement"))} <span class="cite">[{esc(it.get("citation"))}]</span></li>')
                w("</ul>")

    # Historischer Vergleich
    for h in latest.get("historical_analogies", []) if latest else []:
        w(f'<h2>Historischer Vergleich — {esc(pat_label.get(h.get("pattern"), h.get("pattern")))}</h2>')
        if h.get("begruendung"):
            w('<div class="begr"><p class="begrcap">Begründung aus den Belegen</p>'
              f'<p>{esc(h.get("begruendung"))}</p></div>')
        w(f'<p>{esc(h.get("similarity"))} {esc(h.get("what_happened"))}</p>')
        w(f'<p><b>Lehre:</b> {esc(h.get("lesson"))}</p>')
        w(f'<p class="limit"><b>Grenze des Vergleichs:</b> {esc(h.get("limit"))}</p>')

    # Beobachtungen
    if obs:
        w("<h2>Beobachtungen (Belege)</h2>")
        for o in obs:
            url = o.get("url")
            src = ", ".join(src_link(s, url) for s in o.get("source_ids", []))
            beleg = (f' <a class="beleg" href="{esc(url)}" target="_blank" rel="noopener">Artikel öffnen ↗</a>'
                     if url else "")
            w(f'<div class="obs"><div class="obs-h"><b>{esc(o.get("title"))}</b>'
              f'<span class="conf">{esc(o.get("confidence"))} · {ch_date(o.get("date_published"))}</span></div>'
              f'<p>{esc(o.get("summary"))}</p>'
              f'<p class="cite">Quelle: {src} — {esc(o.get("citation"))}{beleg}</p></div>')

    # Verlauf
    if asses:
        w("<h2>Verlauf über die Zeit</h2>")
        w('<table><tr><th>ab</th><th>Ring</th><th>Momentum</th>'
          + ("<th>Rel. allg./org</th>" if internal else "<th>Rel.</th>") + "<th>Entwurf → Endfassung</th></tr>")
        prev = None
        for a in asses:
            ch = "→" if (prev and prev != a.get("ring")) else ""
            rel = (f'{esc(a.get("relevance_general"))}/{esc(a.get("relevance_org"))}' if internal
                   else esc(a.get("relevance_general")))
            who = "KI" if str(a.get("draft_by", "")).startswith("ki:") else "Mensch"
            dr = f'{esc(a.get("draft_ring"))} → {esc(a.get("ring"))}' if a.get("draft_ring") != a.get("ring") else "—"
            w(f'<tr><td>{ch_date(a.get("valid_from"))}</td><td><b>{ch} {esc(a.get("ring"))}</b></td>'
              f'<td>{esc(a.get("momentum"))}</td><td>{rel}</td><td>{who}: {dr}</td></tr>')
            prev = a.get("ring")
        w("</table>")

    # Klassifikation
    w("<h2>Klassifikation</h2>")
    w(f'<p><span class="k">Domänen</span> {chips(entry.get("domains"))}</p>')
    w(f'<p><span class="k">Kompetenzen</span> {chips(entry.get("competences"))}</p>')
    if entry.get("methods"):
        w(f'<p><span class="k">Methoden</span> {chips(entry.get("methods"))}</p>')
    if entry.get("tech_tags"):
        w(f'<p><span class="k">Tech-Tags</span> {chips(entry.get("tech_tags"))}</p>')
    if entry.get("provider_dependency") or entry.get("providers"):
        _dl = {"high": "hoch", "medium": "mittel", "low": "gering", "none": "keine"}
        _pl = {"openai": "OpenAI", "anthropic": "Anthropic", "google": "Google",
               "microsoft": "Microsoft", "meta": "Meta", "deepseek": "DeepSeek",
               "nvidia": "Nvidia", "open": "Offen (Hedge)"}
        _provs = ", ".join(_pl.get(x, x) for x in (entry.get("providers") or [])) or "—"
        w(f'<p><span class="k">Anbieter-Abhängigkeit</span> '
          f'<b>{esc(_dl.get(entry.get("provider_dependency"), "—"))}</b> — {esc(_provs)} '
          f'<span class="meta">(Blast-Radius: fällt der Anbieter aus, ist dieses Thema betroffen)</span></p>')

    mode_note = ("Öffentliche Ansicht (Allowlist, E26)" if not internal
                 else "Interne Ansicht — enthält private Wertung (E25)")
    doc = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(entry.get("name"))} — KI-Radar</title>
<style>
  body{{margin:0;background:{PAPER};color:{INK};font-family:system-ui,-apple-system,sans-serif;padding:28px}}
  .wrap{{max-width:760px;margin:0 auto}}
  .sig{{font-size:12px;letter-spacing:.3em;text-transform:uppercase;color:{GOLD};margin:0}}
  a.back{{font-size:13px;color:{GOLD};text-decoration:none}}
  h1{{font-size:26px;font-weight:600;margin:4px 0 4px}}
  .sub{{color:#6b6862;font-size:14px;margin:0 0 18px}}
  .ring{{color:{GOLD};font-weight:600}}
  h2{{font-size:17px;font-weight:600;margin:22px 0 8px}}
  p,li{{font-size:14px;line-height:1.6}}
  .card{{background:#fff;border:1px solid #e7e3da;border-radius:12px;padding:14px 16px;margin-top:6px}}
  .meta2{{display:flex;flex-wrap:wrap;gap:14px 24px}}
  .meta2 div{{display:flex;flex-direction:column}}
  .meta2 span{{font-size:12px;color:#8a867e}}
  .meta2 b{{font-size:15px;font-weight:600}}
  .div{{color:{GOLD};font-size:13.5px;margin:10px 0 0}}
  .rat{{margin:10px 0 0;color:#4a4741}}
  .cite{{font-size:12px;color:#8a867e}}
  .cite a{{color:{GOLD};text-decoration:none;border-bottom:1px solid rgba(192,133,31,.35)}}
  .cite a:hover{{border-color:{GOLD}}}
  .beleg{{white-space:nowrap;font-weight:500;border-bottom:none!important}}
  .limit{{background:#fff;border-left:3px solid {GOLD};padding:8px 12px;border-radius:4px}}
  .begr{{background:#fff;border:1px solid #e7e3da;border-radius:8px;padding:10px 14px;margin:6px 0 10px}}
  .begrcap{{margin:0 0 3px;font-size:11px;font-weight:600;letter-spacing:.03em;text-transform:uppercase;color:{GOLD}}}
  .begr p{{margin:0}}
  .obs{{background:#fff;border:1px solid #e7e3da;border-radius:10px;padding:12px 14px;margin:8px 0}}
  .obs-h{{display:flex;justify-content:space-between;gap:12px;align-items:baseline}}
  .conf{{font-size:12px;color:#8a867e;white-space:nowrap}}
  table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:4px}}
  th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid #e7e3da}}
  th{{color:#8a867e;font-weight:500}}
  .chip{{display:inline-block;background:#fff;border:1px solid #e7e3da;border-radius:999px;padding:2px 10px;font-size:12.5px;margin:2px}}
  .k{{font-size:12px;color:#8a867e;display:inline-block;min-width:96px}}
  .note{{font-size:12px;color:#8a867e;margin:24px 0 0}}
</style></head><body><div class="wrap">
<a class="back" href="index.html">← zum Radar</a>
<p class="sig" style="margin-top:8px">Aletheia · Radar · Dossier</p>
<h1>{esc(entry.get("name"))}</h1>
<p class="sub">{esc(area)} · Ring <span class="ring">{esc(ring)}</span> ({esc(RING_MEAN.get(ring, ""))}) · aufgenommen {ch_date(entry.get("first_seen"))}</p>
{''.join(out)}
<p class="note">{mode_note}. Erzeugt aus der Instanz mit view/detail.py — read-only.</p>
</div></body></html>"""

    o = Path(args.out)
    if not o.is_absolute():
        o = (Path.cwd() / o).resolve()
    o.parent.mkdir(parents=True, exist_ok=True)
    o.write_text(doc, encoding="utf-8")
    print(f"Dossier: {o}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
