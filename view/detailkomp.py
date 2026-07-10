#!/usr/bin/env python3
"""detailkomp.py — Detail-Dossier je Kompetenz (klickbar aus Radar-Panels).

Beantwortet: Warum ist die Kompetenz empfohlen (Nachfrage, E15) und warum
kritisch (Kritikalität + Begründung, Erosions-Verlauf)? Verlinkt die treibenden
Einträge und deren Quellen. Read-only, nur interne Sicht (strategisch, E25).

  python view/detailkomp.py --instance ../KI-Technology-Radar-Instanz \
      --competence competence.programmierung --out detailkomp-programmierung.html
"""
from __future__ import annotations

import argparse
import datetime
import html
import json
import sys
from pathlib import Path

import yaml

from _fmt import ch_date

CORE = Path(__file__).resolve().parent.parent
GOLD, INK, PAPER = "#C0851F", "#23262D", "#F8F6F2"
CRIT_MEAN = {1: "leicht delegierbar/ersetzbar", 2: "gering — darf verblassen",
             3: "mittel — wichtig, aber nicht fundamental", 4: "hoch",
             5: "unverzichtbares Fundament"}

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


def main() -> int:
    ap = argparse.ArgumentParser(description="Detail-Dossier je Kompetenz.")
    ap.add_argument("--instance", required=True)
    ap.add_argument("--competence", required=True)
    ap.add_argument("--mode", choices=["internal", "public"], default="internal")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    inst = Path(args.instance)
    if not inst.is_absolute():
        inst = (Path.cwd() / inst).resolve()
    cid = args.competence

    labels = {}
    for t in collect(CORE / "vocab-core", "competence.yaml", "terms"):
        labels[t["id"]] = t.get("label", t["id"])
    for t in collect(inst / "vocab", "*.yaml", "terms"):
        labels[t["id"]] = t.get("label", t["id"])
    label = labels.get(cid, cid)

    entries = {e["id"]: e for e in collect(inst / "entries", "entry.yaml", "entries")}
    asses = collect(inst / "entries", "assessments.yaml", "assessments")
    by_entry: dict[str, list] = {}
    for a in asses:
        by_entry.setdefault(a.get("radar_entry_id"), []).append(a)
    for lst in by_entry.values():
        lst.sort(key=lambda a: a.get("valid_from", ""))
    obs_all = collect(inst / "entries", "observations.yaml", "observations")
    src_of = {s["id"]: s for s in collect(inst / "sources", "*.yaml", "sources")}

    # Kritikalitäts-Bewertungen dieser Kompetenz (Verlauf), jüngste = aktuell.
    cas = sorted([c for c in collect(inst / "competences", "*.yaml", "competence_assessments")
                  if c.get("competence_id") == cid], key=lambda c: c.get("valid_from", ""))
    ca = cas[-1] if cas else {}

    def slug_of(eid: str) -> str:
        return eid.split(".", 1)[-1]

    def src_link(sid: str) -> str:
        s = src_of.get(sid, {})
        name = esc(s.get("name", sid))
        url = s.get("url")
        return f'<a href="{esc(url)}" target="_blank" rel="noopener">{name}</a>' if url else name

    # Nachfrage as-of einem Datum: Beiträge der Einträge, die diese Kompetenz führen
    # und (as-of) hochrelevant sind (E15). Gewicht = relevance_org bzw. _general.
    def contributions(dt: str):
        rows = []
        for rid, lst in by_entry.items():
            cand = [a for a in lst if a.get("valid_from", "") <= dt]
            if not cand:
                continue
            a = cand[-1]
            if (a.get("relevance_general") or 0) < 4:
                continue
            if cid not in (entries.get(rid, {}).get("competences") or []):
                continue
            wgt = a.get("relevance_org") or a.get("relevance_general") or 0
            rows.append((rid, wgt, a))
        return rows

    today = datetime.date.today().isoformat()
    # „Aktuell" = jüngstes Assessment je Eintrag (wie die Radar-Startansicht), NICHT
    # nach Kalendertag gefiltert — sonst zählte eine erst in ein paar Tagen datierte
    # Ratifizierung noch nicht, und Dossier und Radar-Panel widersprächen sich.
    def current_contributions():
        rows = []
        for rid, lst in by_entry.items():
            if not lst:
                continue
            a = lst[-1]
            if (a.get("relevance_general") or 0) < 4:
                continue
            if cid not in (entries.get(rid, {}).get("competences") or []):
                continue
            wgt = a.get("relevance_org") or a.get("relevance_general") or 0
            rows.append((rid, wgt, a))
        return rows

    now_rows = current_contributions()
    demand_now = sum(w for _, w, _ in now_rows)

    # Nachfrage-Verlauf: vergangene Ereignis-Jahre as-of Jahresende + aktueller Stand.
    years = event_years(inst)
    max_vf = max([a.get("valid_from", "") for lst in by_entry.values() for a in lst] + [today])
    cur_year = max(today[:4], max_vf[:4])
    series = [(y, sum(w for _, w, _ in contributions(f"{y}-12-31")))
              for y in years if y < cur_year]
    series.append((cur_year, demand_now))

    vals = [v for _, v in series]
    peak = max(vals, default=0)
    crit = ca.get("criticality", 0)
    # Verdikt (mirror Bericht 5a: Erosion = gefallen, Blindspot = nie Nachfrage).
    if peak > 0 and demand_now < peak:
        verdict = ("⚠️", "Erosion",
                   "Die Nachfrage ist gegenüber dem Höchststand gefallen — bei hoher "
                   "Kritikalität heisst das: Wissen und Nachwuchs bewusst erhalten.")
    elif peak == 0 and crit >= 4:
        verdict = ("👁️", "Blindspot / aufkommend",
                   "Kritisch, aber (noch) keine Nachfrage im Radar — im Blick behalten, "
                   "damit die Lücke nicht übersehen wird.")
    elif demand_now > 0:
        verdict = ("✅", "stabil / gefragt",
                   "Aktuell nachgefragt und getragen von relevanten Einträgen.")
    else:
        verdict = ("·", "geringe Kritikalität",
                   "Weder stark nachgefragt noch als Fundament eingestuft — unkritisch.")

    all_entries = [rid for rid in entries
                   if cid in (entries[rid].get("competences") or [])]

    out = []
    w = out.append

    # 1. Kritikalität + Begründung
    if ca:
        div = ""
        if ca.get("draft_criticality") is not None and ca.get("draft_criticality") != crit:
            div = (f'<p class="div">Divergenz (E9): KI-Entwurf Kritikalität '
                   f'<b>{esc(ca.get("draft_criticality"))}</b> → ratifiziert <b>{esc(crit)}</b>.</p>')
        w('<section class="card">'
          f'<div class="big"><span class="score">{esc(crit)}</span>'
          f'<span class="of">/5 · {esc(CRIT_MEAN.get(crit, ""))}</span></div>'
          f'<p class="rat"><b>Ratifiziert (Mensch):</b> {esc(ca.get("rationale"))}</p>'
          + (f'<p class="rat"><b>KI-Entwurf:</b> {esc(ca.get("draft_rationale"))}</p>'
             if ca.get("draft_rationale") else "")
          + div
          + f'<p class="cite">Kritikalität = wie fundamental (unabhängig von der Nachfrage). '
            f'Entwurf {esc(ca.get("draft_by"))}, ratifiziert {esc(ca.get("reviewer"))} '
            f'am {ch_date(ca.get("valid_from"))}.</p>'
          '</section>')
    else:
        w('<section class="card"><p class="rat">Für diese Kompetenz ist noch keine '
          'Kritikalität ratifiziert.</p></section>')

    # 2. Verdikt (Erosion / Blindspot / stabil)
    w(f'<h2>Einordnung</h2>')
    w(f'<p class="verdict"><span class="vicon">{verdict[0]}</span> <b>{esc(verdict[1])}</b> — {esc(verdict[2])}</p>')

    # 3. Nachfrage heute (E15) — welche Einträge treiben sie?
    w("<h2>Nachfrage heute — woraus abgeleitet (E15)</h2>")
    if now_rows:
        w(f'<p>Aggregiert aus hochrelevanten Einträgen (Gewicht = Organisations-Relevanz). '
          f'Summe: <b>{demand_now}</b>.</p><div class="komp">')
        for rid, wgt, a in sorted(now_rows, key=lambda r: -r[1]):
            e = entries.get(rid, {})
            w(f'<a class="krow" href="detail-{esc(slug_of(rid))}.html">'
              f'<div><span class="kname">{esc(e.get("name"))}</span> '
              f'<span class="kdrv">Ring {esc(a.get("ring"))} · Relevanz allg. '
              f'{esc(a.get("relevance_general"))}/org {esc(a.get("relevance_org"))}</span></div>'
              f'<span class="kscore">+{wgt}</span></a>')
        w("</div>")
    else:
        w("<p>Aktuell kein hochrelevanter Eintrag treibt diese Kompetenz — daher keine "
          "abgeleitete Nachfrage (das kann Blindspot bedeuten, siehe Einordnung).</p>")

    # 4. Nachfrage-Verlauf über die Zeit
    if len(series) > 1:
        w("<h2>Nachfrage im Zeitverlauf</h2>")
        w('<table><tr><th>Ende Jahr</th><th>Nachfrage (aggregiert)</th></tr>')
        for y, v in series:
            bar = "▉" * v if v else "—"
            w(f'<tr><td>{esc(y)}</td><td><span class="bar">{bar}</span> {esc(v)}</td></tr>')
        w("</table>")

    # 5. Betroffene Einträge + Quellen
    if all_entries:
        w("<h2>Verknüpfte Einträge & Quellen</h2>")
        w('<div class="komp">')
        seen_src = set()
        for rid in all_entries:
            e = entries.get(rid, {})
            eobs = [o for o in obs_all if o.get("radar_entry_id") == rid]
            srcs = []
            for o in eobs:
                for s in o.get("source_ids", []):
                    if s not in seen_src:
                        seen_src.add(s)
                        srcs.append(src_link(s))
            srctxt = (" · Quellen: " + ", ".join(srcs)) if srcs else ""
            w(f'<div class="krow"><div>'
              f'<a class="kname" href="detail-{esc(slug_of(rid))}.html">{esc(e.get("name"))}</a> '
              f'<span class="kdrv">Ring {esc(e.get("current_ring"))}{srctxt}</span></div></div>')
        w("</div>")

    mode_note = "Interne, strategische Sicht (E25) — nicht veröffentlichen."
    doc = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(label)} — Kompetenz — KI-Radar</title>
<style>
  body{{margin:0;background:{PAPER};color:{INK};font-family:system-ui,-apple-system,sans-serif;padding:28px}}
  .wrap{{max-width:760px;margin:0 auto}}
  .sig{{font-size:12px;letter-spacing:.3em;text-transform:uppercase;color:{GOLD};margin:0}}
  a.back{{font-size:13px;color:{GOLD};text-decoration:none}}
  h1{{font-size:26px;font-weight:600;margin:4px 0 4px}}
  .sub{{color:#6b6862;font-size:14px;margin:0 0 18px}}
  h2{{font-size:17px;font-weight:600;margin:22px 0 8px}}
  p,li{{font-size:14px;line-height:1.6}}
  .card{{background:#fff;border:1px solid #e7e3da;border-radius:12px;padding:16px;margin-top:6px}}
  .big{{display:flex;align-items:baseline;gap:8px;margin-bottom:8px}}
  .score{{font-size:34px;font-weight:700;color:{GOLD};line-height:1}}
  .of{{font-size:14px;color:#6b6862}}
  .rat{{margin:8px 0 0;color:#4a4741}}
  .div{{color:{GOLD};font-size:13.5px;margin:10px 0 0}}
  .cite{{font-size:12px;color:#8a867e;margin-top:10px}}
  .cite a{{color:{GOLD};text-decoration:none;border-bottom:1px solid rgba(192,133,31,.35)}}
  .verdict{{background:#fff;border-left:3px solid {GOLD};border-radius:6px;padding:10px 14px}}
  .vicon{{font-size:16px}}
  .komp{{display:flex;flex-direction:column;gap:8px}}
  .krow{{display:flex;justify-content:space-between;align-items:baseline;background:#fff;
        border:1px solid #e7e3da;border-radius:12px;padding:10px 16px;text-decoration:none;color:inherit;
        transition:border-color .12s}}
  a.krow:hover{{border-color:{GOLD}}}
  .kname{{font-size:15px;font-weight:600;color:inherit;text-decoration:none}}
  a.kname{{border-bottom:1px solid rgba(192,133,31,.35)}}
  .kdrv{{font-size:12px;color:#8a867e}}
  .kdrv a{{color:{GOLD};text-decoration:none;border-bottom:1px solid rgba(192,133,31,.35)}}
  .kscore{{font-size:14px;font-weight:600;color:{GOLD}}}
  table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:4px}}
  th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid #e7e3da}}
  th{{color:#8a867e;font-weight:500}}
  .bar{{color:{GOLD};letter-spacing:1px}}
  .note{{font-size:12px;color:#8a867e;margin:24px 0 0}}
</style></head><body><div class="wrap">
<a class="back" href="index.html">← zum Radar</a>
<p class="sig" style="margin-top:8px">Aletheia · Radar · Kompetenz</p>
<h1>{esc(label)}</h1>
<p class="sub">Kompetenz-Dossier · Kritikalität × Nachfrage-Verlauf (Erosions-Modell)</p>
{''.join(out)}
<p class="note">{mode_note} Erzeugt mit view/detailkomp.py — read-only.</p>
</div></body></html>"""

    o = Path(args.out)
    if not o.is_absolute():
        o = (Path.cwd() / o).resolve()
    o.parent.mkdir(parents=True, exist_ok=True)
    o.write_text(doc, encoding="utf-8")
    print(f"Kompetenz-Dossier: {o}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
