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
import json
import math
import sys
from pathlib import Path

import yaml

from _fmt import ch_date

CORE = Path(__file__).resolve().parent.parent
GOLD = "#C0851F"
INK = "#23262D"
PAPER = "#F8F6F2"

# Ringe von innen nach aussen; Reject wird separat gelistet, nicht platziert.
RINGS = ["Adopt", "Pilot", "Explore", "Watch"]
RING_OUTER = {"Adopt": 52, "Pilot": 98, "Explore": 140, "Watch": 175}
RING_MID = {"Adopt": 26, "Pilot": 75, "Explore": 119, "Watch": 157}
CX, CY, RMAX = 340, 250, 175


def _normalize(v):
    if isinstance(v, dict):
        return {k: _normalize(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_normalize(x) for x in v]
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.isoformat()
    return v


def load_yaml(path: Path):
    with path.open(encoding="utf-8") as fh:
        return _normalize(yaml.safe_load(fh))


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
    ap.add_argument("--as-of", dest="as_of", help="YYYY-MM-DD: Radar-Stand zu diesem Zeitpunkt (historisch)")
    ap.add_argument("--out", default=str(CORE / "view" / "output" / "radar.html"))
    args = ap.parse_args()
    inst = Path(args.instance)
    if not inst.is_absolute():
        inst = (Path.cwd() / inst).resolve()

    # Jurisdiktion (A1): Land dieser Instanz + Manifest fuer den Umschalter.
    country = load_yaml(inst / "country.yaml") if (inst / "country.yaml").exists() else None
    manifest = collect(inst, "countries.yaml", "countries")

    # Bereiche (nur oberste Ebene) als Sektoren, in Katalog-Reihenfolge.
    area_terms = [t for t in collect(CORE / "vocab-core", "area.yaml", "terms")
                  if not t.get("parent_id")]
    areas = [t["id"] for t in area_terms]
    area_label = {t["id"]: t["label"] for t in area_terms}
    n = len(areas)
    sector_center = {aid: -90 + i * (360 / n) for i, aid in enumerate(areas)}
    pattern_label = {p["id"]: p.get("label", p["id"])
                     for p in collect(CORE / "patterns", "patterns.yaml", "patterns")}
    comp_label = {t["id"]: t.get("label", t["id"])
                  for t in collect(CORE / "vocab-core", "competence.yaml", "terms")}
    domain_label = {t["id"]: t.get("label", t["id"])
                    for t in collect(CORE / "vocab-core", "domain.yaml", "terms")}

    def dom_data(e):
        return " ".join(d.split(".", 1)[-1] for d in (e.get("domains") or []))

    # Einträge + jüngstes Assessment.
    entries = collect(inst / "entries", "entry.yaml", "entries")
    assessments = collect(inst / "entries", "assessments.yaml", "assessments")
    # Radar-Stand ZUM ZEITPUNKT --as-of (Standard: aktuell). Nur Assessments bis
    # zum Stichtag; Ring = jüngstes Assessment as-of, nicht das absolut jüngste.
    asof = args.as_of
    latest: dict[str, dict] = {}
    for a in assessments:
        rid = a.get("radar_entry_id")
        if asof and a.get("valid_from", "") > asof:
            continue
        if rid and (rid not in latest or a.get("valid_from", "") > latest[rid].get("valid_from", "")):
            latest[rid] = a

    placed, rejected = [], []
    # Gruppieren nach (Sektor, Ring) für Winkel-Versatz bei Mehrfachbelegung.
    groups: dict[tuple[str, str], list[dict]] = {}
    for e in entries:
        if e.get("status") == "archived":
            continue
        if asof and (e.get("first_seen") or "") > asof:
            continue                                   # existierte damals noch nicht
        a_eff = latest.get(e["id"])
        if asof and not a_eff:
            continue                                   # damals noch nicht bewertet
        ring = (a_eff.get("ring") if a_eff else None) or e.get("current_ring")
        aid = top_area(e.get("area", ""))
        if ring == "Reject":
            rejected.append(e)
            continue
        if ring not in RING_MID or aid not in sector_center:
            continue
        groups.setdefault((aid, ring), []).append(e)

    theme_rows = []   # für die clientseitige, überlappungsfreie Ansicht (JS-Layout)
    for (aid, ring), es in groups.items():
        base = sector_center[aid]
        span = 46  # Grad Streuung innerhalb Sektor/Ring
        for k, e in enumerate(es):
            off = 0 if len(es) == 1 else (k - (len(es) - 1) / 2) * (span / max(1, len(es)))
            x, y = polar(base + off, RING_MID[ring])
            placed.append((e, latest.get(e["id"], {}), x, y))
            slug = e["id"].split(".", 1)[-1]
            theme_rows.append({
                "id": slug, "name": e.get("name"), "ring": ring, "sector": aid,
                "href": f"detail-{slug}.html", "dom": dom_data(e),
            })
    sectors_json = [{"id": aid, "label": area_label.get(aid, aid),
                     "angle": sector_center[aid]} for aid in areas]

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
    # Blips — jeder verlinkt auf sein Detail-Dossier (detail-<slug>.html).
    for e, a, x, y in placed:
        slug = e["id"].split(".", 1)[-1]
        svg.append(f'<a class="blip" data-dom="{esc(dom_data(e))}" href="detail-{esc(slug)}.html">')
        svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" fill="{PAPER}"/>'
                   f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{GOLD}"/>')
        lx = x + 12
        svg.append(f'<text x="{lx:.1f}" y="{y+4:.1f}" text-anchor="start" font-size="12.5" '
                   f'fill="{INK}" font-weight="500" font-family="system-ui,sans-serif">'
                   f'{esc(e.get("name"))}</text>')
        svg.append('</a>')
    svg.append("</svg>")

    # --- Karten --------------------------------------------------------------
    cards = []
    order = {r: i for i, r in enumerate(RINGS)}
    for e, a, *_ in sorted(placed, key=lambda t: order.get(t[0].get("current_ring"), 9)):
        ring = e.get("current_ring", "")
        area = area_label.get(top_area(e.get("area", "")), "")
        if args.mode == "public":
            detail = f'seit {ch_date(e.get("first_seen"))}'
        else:
            detail = (f'Relevanz {esc(a.get("relevance_general"))}/{esc(a.get("relevance_org"))} · '
                      f'Handlungsdruck {esc(a.get("action_pressure"))} · {esc(a.get("momentum"))}')
        slug = e["id"].split(".", 1)[-1]
        cards.append(
            f'<a class="cardlink" data-dom="{esc(dom_data(e))}" href="detail-{esc(slug)}.html">'
            f'<div class="card"><div class="meta">{esc(area)} · '
            f'<span class="ring">{esc(ring)}</span></div>'
            f'<div class="name">{esc(e.get("name"))}</div>'
            f'<div class="detail">{detail}</div></div></a>')

    stamp = datetime.datetime.now().astimezone().strftime("%d.%m.%Y %H:%M")
    stand = f"Stand zum {ch_date(asof)} (historisch)" if asof else f"Stand {stamp}"
    mode_note = ("Öffentliche Ansicht (Allowlist, E26)" if args.mode == "public"
                 else "Interne Ansicht — enthält private Wertung (E25), nicht veröffentlichen")
    # Link zum Eingangskorb nur intern (Kandidaten sind unratifiziert, E4/E25).
    kandlink = ('' if args.mode == "public"
                else ' &nbsp;·&nbsp; <a href="kandidaten.html">Eingangskorb — Kandidaten nach Branche →</a>')

    # Länder-Umschalter (A1): navigiert zwischen den Länder-Radaren (je Land eine Instanz).
    cur_code = (country or {}).get("code")
    sel_entries = manifest or ([country] if country else [])
    opts = []
    for c in sel_entries:
        lbl = f'{c.get("flag", "")} {c.get("label", c.get("code", ""))}'.strip()
        if c.get("status") == "planned" or not c.get("url"):
            opts.append(f'<option disabled>{esc(lbl)} — in Vorbereitung</option>')
        else:
            sel = " selected" if c.get("code") == cur_code else ""
            opts.append(f'<option value="{esc(c["url"])}"{sel}>{esc(lbl)}</option>')
    country_sel = ""
    if opts:
        country_sel = ('<label class="jur">Jurisdiktion&nbsp;'
                       '<select onchange="if(this.value)location.href=this.value">'
                       + "".join(opts) + "</select></label>")

    # Zeit-Umschalter: Jahres-Snapshots (Ende Jahr) + Aktuell.
    years = event_years(inst)
    cur_year = years[-1] if years else None
    snap_years = [y for y in reversed(years) if y != cur_year]
    tsel = ""
    if snap_years:
        sel_year = (asof or "")[:4]
        topts = [f'<option value="index.html"{"" if asof else " selected"}>Aktuell</option>']
        for y in snap_years:
            topts.append(f'<option value="radar-{y}.html"'
                         f'{" selected" if sel_year == y else ""}>Ende {y}</option>')
        tsel = ('<label class="jur">Zeitpunkt&nbsp;'
                '<select onchange="if(this.value)location.href=this.value">'
                + "".join(topts) + "</select></label>")
    # Branche-Umschalter: filtert Blips + Karten clientseitig nach Domäne/Branche.
    present_dom: dict[str, int] = {}
    for e, *_ in placed:
        for d in (e.get("domains") or []):
            present_dom[d] = present_dom.get(d, 0) + 1
    bran_sel = ""
    if present_dom:
        bopts = ['<option value="">Alle Branchen</option>']
        for d in sorted(present_dom, key=lambda x: domain_label.get(x, x)):
            bopts.append(f'<option value="{esc(d.split(".", 1)[-1])}">'
                         f'{esc(domain_label.get(d, d))} ({present_dom[d]})</option>')
        bran_sel = ('<label class="jur">Branche&nbsp;<select id="bran" onchange="branf()">'
                    + "".join(bopts) + "</select></label>")

    rej = ""
    if rejected:
        names = ", ".join(
            f'<a class="rejlink" href="detail-{esc(e["id"].split(".", 1)[-1])}.html">{esc(e.get("name"))}</a>'
            for e in rejected)
        rej = f'<p class="rej">Reject (bewusst nicht verfolgt): {names}</p>'

    # Historische Muster (E13): Vergleich mit Pflicht-Gegenprobe. Analytische
    # Wertung -> nur in der internen Ansicht, nicht in der Allowlist-Sicht (E26).
    muster = ""
    if args.mode != "public":
        rows = []
        for e, a, *_ in sorted(placed, key=lambda t: order.get(t[0].get("current_ring"), 9)):
            for h in (a.get("historical_analogies") or []):
                pl = esc(pattern_label.get(h.get("pattern"), h.get("pattern")))
                mslug = str(h.get("pattern", "")).split(".", 1)[-1]
                kurz = h.get("begruendung_kurz")
                kurz_html = f'<div class="mkurz">{esc(kurz)}</div>' if kurz else ''
                rows.append(
                    f'<a class="mrow" href="detailmuster-{esc(mslug)}.html">'
                    f'<div class="mhead"><b>{esc(e.get("name"))}</b> ~ {pl} <span class="arrow">→</span></div>'
                    f'{kurz_html}'
                    f'<div class="mlimit">Grenze: {esc(h.get("limit"))}</div></a>')
        if rows:
            muster = ('<h2>Historische Muster (Vergleich mit Gegenprobe)</h2>'
                      '<div class="muster">' + "".join(rows) + "</div>")

    # R6: Kompetenzempfehlung aus den Daten ableiten (E15) — aggregiert über die
    # Kompetenz-Verknüpfungen der hochrelevanten Einträge, gewichtet mit der
    # Organisations-Relevanz. Strategische, private Sicht -> nicht public (E25/E26).
    komp = ""
    reco = []
    if args.mode != "public":
        tally: dict[str, list] = {}
        for e, a, *_ in placed:
            if (a.get("relevance_general") or 0) < 4:      # nur hochrelevante Einträge
                continue
            weight = a.get("relevance_org") or a.get("relevance_general") or 0
            for c in (e.get("competences") or []):
                t = tally.setdefault(c, [0, set()])
                t[0] += weight
                t[1].add(e.get("name"))
        ranked = sorted(tally.items(), key=lambda kv: (-kv[1][0], comp_label.get(kv[0], kv[0])))
        krows = []
        for cid, (score, names) in ranked[:6]:
            label = comp_label.get(cid, cid)
            reco.append(label)
            kslug = cid.split(".", 1)[-1]
            krows.append(
                f'<a class="krow" href="detailkomp-{esc(kslug)}.html">'
                f'<div><span class="kname">{esc(label)}</span> '
                f'<span class="kdrv">{esc(", ".join(sorted(names)))}</span></div>'
                f'<span class="kscore">{score}</span></a>')
        if krows:
            komp = ('<h2>Empfohlene Kompetenzentwicklung '
                    '<span class="ksub">nächste 6 Monate · aus den Daten abgeleitet (E15)</span></h2>'
                    '<div class="komp">' + "".join(krows) + "</div>")

    # Erosionsrisiko-Panel (hohe Kritikalität × geringe Nachfrage) — nur internal.
    erosion = ""
    if args.mode != "public":
        crit_of: dict[str, tuple] = {}
        for ca in collect(inst / "competences", "*.yaml", "competence_assessments"):
            cid = ca.get("competence_id")
            if asof and ca.get("valid_from", "") > asof:
                continue                                   # Urteil gab es damals noch nicht
            if cid and (cid not in crit_of or ca.get("valid_from", "") >= crit_of[cid][1]):
                crit_of[cid] = (ca.get("criticality", 0), ca.get("valid_from", ""))
        dmap = {cid: v[0] for cid, v in tally.items()}
        # "wenig Nachfrage" robust bestimmen: NICHT am absoluten Maximum (ein einzelnes
        # stark nachgefragtes Feld wie KI-Aufsicht verzerrt die Schwelle), sondern am
        # Median der tatsächlich nachgefragten Kompetenzen. Zudem: eine bereits als
        # Top-Nachfrage EMPFOHLENE Kompetenz ist per Definition keine Erosionslücke —
        # sie hier auszuschliessen verhindert den Widerspruch, dass dieselbe Kompetenz
        # zugleich unter "entwickeln" und unter "Erosion" steht (z.B. Datenschutz).
        reco_ids = {cid for cid, _ in ranked[:6]}
        demanded = sorted(v for v in dmap.values() if v > 0)
        median_d = demanded[len(demanded) // 2] if demanded else 0
        low_cut = 0.25 * median_d
        erows = []
        for cid, (crit, _) in crit_of.items():
            d = dmap.get(cid, 0)
            if cid in reco_ids:
                continue
            if not (crit >= 4 and d <= low_cut):
                continue
            erows.append(
                f'<a class="krow" href="detailkomp-{esc(cid.split(".", 1)[-1])}.html">'
                f'<div><span class="kname">👁️ {esc(comp_label.get(cid, cid))}</span> '
                f'<span class="kdrv">Kritikalität {crit} · Nachfrage {d}</span></div>'
                f'<span class="kscore">im Blick</span></a>')
        if erows:
            erosion = ('<h2>Kritische Kompetenzen im Blick '
                       '<span class="ksub">hohe Kritikalität × wenig Nachfrage — Erosion/Lücke: siehe Bericht</span></h2>'
                       '<div class="komp">' + "".join(erows) + "</div>")

    # Client-Layout: Themendaten + Sektoren als JSON, dann die Render-Engine.
    radar_js_data = ("const THEMES=" + json.dumps(theme_rows, ensure_ascii=False)
                     + ";\nconst SECTORS=" + json.dumps(sectors_json, ensure_ascii=False) + ";\n")
    script_js = r"""
const GOLD='#C0851F',INK='#23262D';
const RINGORDER=['Adopt','Pilot','Explore','Watch'];
const RINGMEAN={Adopt:'produktiv nutzen',Pilot:'real erproben',Explore:'experimentieren',Watch:'beobachten'};
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function curFilter(){var s=document.getElementById('bran');return s?s.value:'';}
function matches(t,f){return !f||((' '+(t.dom||'')+' ').indexOf(' '+f+' ')>=0);}
function byRingOf(list){var m={};list.forEach(function(t){(m[t.ring]=m[t.ring]||[]).push(t);});return m;}

function renderColumns(byRing){
  var h='',any=false;
  RINGORDER.forEach(function(ring){
    var ts=byRing[ring];if(!ts||!ts.length)return;any=true;
    h+='<section class="rpanel"><div class="rphead"><span class="rpname">'+ring+'</span><span class="rpmean">'+RINGMEAN[ring]+'</span><span class="rpcount">'+ts.length+'</span></div><div class="rpcols" style="--nsec:'+SECTORS.length+'">';
    SECTORS.forEach(function(sec){
      var st=ts.filter(function(t){return t.sector===sec.id;});
      h+='<div class="rpcol"><div class="rpcolh">'+esc(sec.label)+'</div>';
      st.forEach(function(t){h+='<a class="chip" href="'+t.href+'">'+esc(t.name)+'</a>';});
      if(!st.length)h+='<div class="rpempty">–</div>';
      h+='</div>';
    });
    h+='</div></section>';
  });
  return any?h:'<p class="rpnone">Keine Themen für diese Branche.</p>';
}

function miniRadar(ts){
  var n=SECTORS.length,cx=350,R=92,minGap=17;
  var pts=[];
  SECTORS.forEach(function(sec){
    var st=ts.filter(function(t){return t.sector===sec.id;}),m=st.length,span=30;
    st.forEach(function(t,k){
      var off=m===1?0:(k-(m-1)/2)*(span/Math.max(1,m));
      var ang=(sec.angle+off)*Math.PI/180,br=R*(0.66-(k%3)*0.12);
      pts.push({t:t,cos:Math.cos(ang),br:br,right:Math.cos(ang)>=-0.0001,dy:Math.sin(ang)*br});
    });
  });
  ['right','left'].forEach(function(side){
    var isR=side==='right';
    var g=pts.filter(function(p){return p.right===isR;}).sort(function(a,b){return a.dy-b.dy;});
    g.forEach(function(p,i){p.ly=(i===0)?p.dy:Math.max(p.dy,g[i-1].ly+minGap);});
  });
  var maxAbs=60;pts.forEach(function(p){maxAbs=Math.max(maxAbs,Math.abs(p.ly),Math.abs(p.dy));});
  var H=Math.max(210,2*maxAbs+50),cy=H/2;
  var s=['<svg viewBox="0 0 700 '+H.toFixed(0)+'" class="mini" xmlns="http://www.w3.org/2000/svg">'];
  s.push('<circle cx="'+cx+'" cy="'+cy+'" r="'+R+'" fill="'+GOLD+'" fill-opacity="0.10" stroke="'+INK+'" stroke-opacity="0.18"/>');
  for(var i=0;i<n;i++){var b=(-90-(360/n)/2+i*(360/n))*Math.PI/180;s.push('<line x1="'+cx+'" y1="'+cy+'" x2="'+(cx+R*Math.cos(b)).toFixed(1)+'" y2="'+(cy+R*Math.sin(b)).toFixed(1)+'" stroke="'+INK+'" stroke-opacity="0.12"/>');}
  // Sektor-Kurzmarke (Nummer) am Rand — die Namen stehen einmal in der Legende
  // darüber. So kollidiert nichts mit den äusseren Theme-Labels.
  SECTORS.forEach(function(sec,i){var a=sec.angle*Math.PI/180;var lx=cx+(R-11)*Math.cos(a),ly=cy+(R-11)*Math.sin(a);s.push('<text x="'+lx.toFixed(0)+'" y="'+(ly+3).toFixed(0)+'" text-anchor="middle" font-size="10" fill="'+INK+'" fill-opacity="0.4" font-weight="600">'+(i+1)+'</text>');});
  s.push('<circle cx="'+cx+'" cy="'+cy+'" r="2.5" fill="'+INK+'" fill-opacity="0.5"/>');
  pts.forEach(function(p){
    var bx=cx+p.br*p.cos,by=cy+p.dy,lx=p.right?(cx+R+14):(cx-R-14),ly=cy+p.ly,el=p.right?(cx+R+6):(cx-R-6);
    s.push('<a href="'+p.t.href+'" class="mblip"><polyline points="'+bx.toFixed(1)+','+by.toFixed(1)+' '+el.toFixed(1)+','+ly.toFixed(1)+' '+lx.toFixed(1)+','+ly.toFixed(1)+'" fill="none" stroke="'+INK+'" stroke-opacity="0.22"/><circle cx="'+bx.toFixed(1)+'" cy="'+by.toFixed(1)+'" r="4.5" fill="'+GOLD+'"/><text x="'+lx.toFixed(1)+'" y="'+(ly+3).toFixed(1)+'" text-anchor="'+(p.right?'start':'end')+'" font-size="11" fill="'+INK+'">'+esc(p.t.name)+'</text></a>');
  });
  s.push('</svg>');return s.join('');
}

function renderRadar(byRing){
  var h='',any=false;
  RINGORDER.forEach(function(ring){
    var ts=byRing[ring];if(!ts||!ts.length)return;any=true;
    h+='<section class="rpanel"><div class="rphead"><span class="rpname">'+ring+'</span><span class="rpmean">'+RINGMEAN[ring]+'</span><span class="rpcount">'+ts.length+'</span></div>'+miniRadar(ts)+'</section>';
  });
  if(!any)return '<p class="rpnone">Keine Themen für diese Branche.</p>';
  var leg='<p class="seclegend">Sektoren (Ziffern im Radar, im Uhrzeigersinn ab oben): '+SECTORS.map(function(s,i){return '<b>'+(i+1)+'</b> '+esc(s.label);}).join(' · ')+'</p>';
  return leg+h;
}

function renderRadarArea(){
  var f=curFilter(),mode=localStorage.getItem('radarview')||'radar';
  var byRing=byRingOf(THEMES.filter(function(t){return matches(t,f);}));
  var el=document.getElementById('radararea');
  if(el)el.innerHTML=(mode==='columns')?renderColumns(byRing):renderRadar(byRing);
  document.querySelectorAll('.vbtn').forEach(function(b){b.className='vbtn'+(b.getAttribute('data-v')===mode?' on':'');});
}
function setView(m){localStorage.setItem('radarview',m);renderRadarArea();}
function branf(){
  var v=curFilter();
  document.querySelectorAll('.cardlink').forEach(function(el){
    el.style.display=(!v||((' '+(el.getAttribute('data-dom')||'')+' ').indexOf(' '+v+' ')>=0))?'':'none';
  });
  renderRadarArea();
}
document.addEventListener('DOMContentLoaded',renderRadarArea);
"""
    doc = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KI-Technology-Radar</title>
<style>
  body{{margin:0;background:{PAPER};color:{INK};font-family:system-ui,-apple-system,sans-serif;padding:28px}}
  .wrap{{max-width:720px;margin:0 auto}}
  .sig{{font-size:12px;letter-spacing:.3em;text-transform:uppercase;color:{GOLD};margin:0}}
  h1{{font-size:26px;font-weight:600;margin:2px 0 2px}}
  .sub{{color:#6b6862;font-size:14px;margin:0 0 8px}}
  .jur{{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:#6b6862;margin:0 0 18px}}
  .jur select{{font:inherit;color:{INK};background:#fff;border:1px solid #e7e3da;border-radius:8px;padding:4px 8px}}
  .berichtlink{{margin:0 0 14px}}
  .berichtlink a{{font-size:13px;color:{GOLD};text-decoration:none}}
  .legend{{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:13px;color:#6b6862;margin:8px 0 18px}}
  .legend b{{color:{INK};font-weight:500}}
  .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}}
  .cardlink{{text-decoration:none;color:inherit;display:block}}
  .card{{background:#fff;border:1px solid #e7e3da;border-radius:12px;padding:14px 16px;transition:border-color .12s,box-shadow .12s}}
  .cardlink:hover .card{{border-color:{GOLD};box-shadow:0 2px 10px rgba(192,133,31,.12)}}
  svg a{{cursor:pointer}}
  svg a:hover text{{fill:{GOLD}}}
  .rejlink{{color:inherit;text-decoration:none;border-bottom:1px dotted #b3afa6}}
  .rejlink:hover{{color:{GOLD};border-color:{GOLD}}}
  .meta{{font-size:12.5px;color:#6b6862}}
  .ring{{color:{GOLD};font-weight:600}}
  .name{{font-size:17px;font-weight:600;margin:2px 0 6px}}
  .detail{{font-size:13px;color:#6b6862;line-height:1.5}}
  .note{{font-size:12px;color:#8a867e;margin:18px 0 0}}
  .rej{{font-size:13px;color:#6b6862;margin:10px 0 0}}
  h2{{font-size:18px;font-weight:600;margin:24px 0 10px}}
  .muster{{display:flex;flex-direction:column;gap:10px}}
  .mrow{{display:block;background:#fff;border:1px solid #e7e3da;border-radius:12px;padding:12px 16px;text-decoration:none;color:inherit;transition:border-color .12s}}
  a.mrow:hover{{border-color:{GOLD}}}
  .mhead{{font-size:14px}}
  .arrow{{color:{GOLD};float:right}}
  .mkurz{{font-size:13.5px;color:#3a3833;margin-top:5px;line-height:1.5}}
  .mlimit{{font-size:13px;color:#6b6862;margin-top:5px;line-height:1.5}}
  .ksub{{font-size:13px;font-weight:400;color:#8a867e}}
  .komp{{display:flex;flex-direction:column;gap:8px}}
  .krow{{display:flex;justify-content:space-between;align-items:baseline;background:#fff;border:1px solid #e7e3da;border-radius:12px;padding:10px 16px;text-decoration:none;color:inherit;transition:border-color .12s}}
  a.krow:hover{{border-color:{GOLD}}}
  .kname{{font-size:15px;font-weight:600}}
  .kdrv{{font-size:12px;color:#8a867e}}
  .kscore{{font-size:14px;font-weight:600;color:{GOLD}}}
  .viewtoggle{{display:inline-flex;border:1px solid #e7e3da;border-radius:9px;overflow:hidden;margin:0 0 16px}}
  .vbtn{{font:inherit;font-size:13px;border:0;border-left:1px solid #e7e3da;background:#fff;color:#6b6862;padding:6px 13px;cursor:pointer}}
  .vbtn:first-child{{border-left:0}}
  .vbtn.on{{background:{GOLD};color:#fff}}
  #radararea{{margin:0 0 6px}}
  .rpanel{{background:#fff;border:1px solid #e7e3da;border-radius:14px;padding:14px 16px;margin:0 0 14px}}
  .rphead{{display:flex;align-items:baseline;gap:9px;margin:0 0 10px}}
  .rpname{{font-size:16px;font-weight:600;color:{GOLD}}}
  .rpmean{{font-size:12.5px;color:#8a867e}}
  .rpcount{{margin-left:auto;font-size:12.5px;color:#8a867e;background:#faf7f1;border:1px solid #eee7db;border-radius:20px;padding:1px 9px}}
  .rpcols{{display:grid;grid-template-columns:repeat(var(--nsec,5),1fr);gap:10px}}
  .rpcol{{min-width:0}}
  .rpcolh{{font-size:11px;font-weight:600;color:#6b6862;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid #eee7db;padding-bottom:4px;margin-bottom:7px}}
  .chip{{display:block;font-size:12.5px;color:{INK};text-decoration:none;background:#faf7f1;border:1px solid #eee7db;border-radius:8px;padding:5px 9px;margin:0 0 6px;line-height:1.32}}
  .chip:hover{{border-color:{GOLD};color:{GOLD}}}
  .rpempty{{font-size:12px;color:#cfc9bd}}
  .mini{{width:100%;height:auto;display:block}}
  .mini text{{font-family:system-ui,sans-serif}}
  .mblip{{cursor:pointer}}
  .mblip:hover text{{fill:{GOLD}}}
  .rpnone{{color:#8a867e;font-size:14px;padding:8px 2px}}
  .seclegend{{font-size:11.5px;color:#8a867e;margin:0 0 12px;line-height:1.5}}
  .seclegend b{{color:{INK}}}
  @media(max-width:560px){{.rpcols{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><div class="wrap">
<p class="sig">Aletheia · Radar</p>
<h1>KI-Technology-Radar</h1>
<p class="sub">{stand} · {len(placed)} Einträge</p>
{country_sel} {tsel} {bran_sel}
<p class="berichtlink"><a href="bericht.html">Berichte — Zeitraum frei wählbar →</a>{kandlink}</p>
<div class="viewtoggle">
<button class="vbtn on" data-v="radar" onclick="setView('radar')">◎ Ring-Radare</button>
<button class="vbtn" data-v="columns" onclick="setView('columns')">▤ Sektor-Spalten</button></div>
<div id="radararea"></div>
<noscript>{''.join(svg)}</noscript>
<div class="legend"><b>Ringe:</b>
<span><b>Adopt</b> produktiv nutzen</span><span><b>Pilot</b> real erproben</span>
<span><b>Explore</b> experimentieren</span><span><b>Watch</b> beobachten</span></div>
<div class="cards">{''.join(cards)}</div>
{rej}
{komp}
{erosion}
{muster}
<p class="note">{mode_note}. Erzeugt aus der Instanz mit view/render.py — read-only.</p>
<script>{radar_js_data}{script_js}</script>
</div></body></html>"""

    out = Path(args.out)
    if not out.is_absolute():
        out = (Path.cwd() / out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    print(f"Modus: {args.mode} · {len(placed)} Einträge platziert"
          + (f", {len(rejected)} Reject" if rejected else ""))
    if reco:
        print("Kompetenzempfehlung (abgeleitet): " + " · ".join(reco))
    print(f"Geschrieben: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
