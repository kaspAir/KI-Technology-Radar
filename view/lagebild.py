#!/usr/bin/env python3
"""lagebild.py — Management-Lagebild (Einseiter) für EINEN Mandanten.

Verdichtet die tenant-private Kuratierung EINER Instanz (Ringe, relevance_org,
Kompetenz-Kritikalität, Anbieter-Abhängigkeit, Markt-Thema, Beleg-Reifegrad) zu
einer entscheidungsreifen Seite: Lage · Chancen · Risiken/Abhängigkeiten ·
Kompetenz-Empfehlungen · Handlungsempfehlungen · Reifegrad. Alles pro Mandant —
derselbe Generator wird im MVP je tenant_id aufgerufen (WERTEN-Schicht, E25).
Nur internal (private Wertung, E26). KEINE Anlage-Aussage.

  python view/lagebild.py --instance ../KI-Technology-Radar-Instanz --out lagebild.html
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
GREEN, ORANGE, RED = "#2e7d32", "#C0851F", "#C0362C"
RING_MEAN = {"Adopt": "produktiv nutzen", "Pilot": "real erproben",
             "Explore": "experimentieren", "Watch": "beobachten"}
PLABEL = {"openai": "OpenAI", "anthropic": "Anthropic", "google": "Google",
          "microsoft": "Microsoft", "meta": "Meta", "deepseek": "DeepSeek",
          "nvidia": "Nvidia", "open": "Offene Modelle"}

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


def slug(eid: str) -> str:
    return eid.split(".", 1)[-1]


def render_lagebild(inst: Path, profile: dict | None = None) -> str:
    """Baut das Lagebild-HTML für EINEN Mandanten. profile: das Profil-Dict
    (aus DB/MVP) — wenn None, wird <instance>/mandant.yaml gelesen. So nutzen
    statischer Build UND MVP dieselbe Logik (WERTEN-Schicht, pro Mandant)."""
    country = load_yaml(inst / "country.yaml") if (inst / "country.yaml").exists() else {}
    if profile is not None:
        profil = profile or {}
    else:
        profil = (load_yaml(inst / "mandant.yaml") if (inst / "mandant.yaml").exists() else {}) or {}
    mandant = profil.get("name") or (country or {}).get("label", "diese Instanz")

    comp_label = {t["id"]: t.get("label", t["id"])
                  for t in collect(CORE / "vocab-core", "competence.yaml", "terms")}
    domain_label = {t["id"]: t.get("label", t["id"])
                    for t in collect(CORE / "vocab-core", "domain.yaml", "terms")}

    # Profil steuert die Wertung: Risikofreudigkeit -> welche Ringe als Chance zählen;
    # Wunschbranchen -> Themen in diesen Domänen ranken höher.
    risk = str(profil.get("risikofreudigkeit") or "").lower()
    if any(x in risk for x in ("früh", "fruh", "adoptier", "offensiv")):
        # Risikofreudig: aufkommende (Explore-)Chancen bewusst nach vorne holen.
        chancen_rings, ringw = ("Adopt", "Pilot", "Explore"), {"Adopt": 1, "Pilot": 1, "Explore": 2}
    elif "konservativ" in risk:
        # Konservativ: nur Reifes (Adopt/Pilot) als Chance.
        chancen_rings, ringw = ("Adopt", "Pilot"), {"Adopt": 2, "Pilot": 1}
    else:  # ausgewogen / kein Profil: Explore zulässig, aber zurückhaltend.
        chancen_rings, ringw = ("Adopt", "Pilot", "Explore"), {"Adopt": 2, "Pilot": 1, "Explore": -2}
    wunsch = [str(x).lower() for x in (profil.get("wunschbranchen") or [])]

    def wunsch_boost(e):
        labels = " ".join(domain_label.get(d, d).lower() for d in (e.get("domains") or []))
        return 3 if any(w and (w in labels or labels and w.split()[0] in labels) for w in wunsch) else 0

    entries = {e["id"]: e for e in collect(inst / "entries", "entry.yaml", "entries")}
    asses = collect(inst / "entries", "assessments.yaml", "assessments")
    latest: dict[str, dict] = {}
    for a in asses:
        rid = a.get("radar_entry_id")
        if rid and (rid not in latest or a.get("valid_from", "") > latest[rid].get("valid_from", "")):
            latest[rid] = a
    obs_all = collect(inst / "entries", "observations.yaml", "observations")

    # platzierte Themen (nicht Reject/archived), mit jüngstem Assessment.
    placed = []
    for eid, e in entries.items():
        if e.get("status") == "archived":
            continue
        a = latest.get(eid)
        ring = (a.get("ring") if a else None) or e.get("current_ring")
        if ring == "Reject" or not a:
            continue
        placed.append((e, a, ring))

    def relg(a):
        return a.get("relevance_general") or 0

    def relo(a):
        return a.get("relevance_org") or a.get("relevance_general") or 0

    # --- Chancen: reif + hoch org-relevant, nach Profil gewichtet ---
    chancen = sorted([(e, a, r) for e, a, r in placed if r in chancen_rings and relg(a) >= 4],
                     key=lambda t: -(relo(t[1]) + ringw.get(t[2], 0) + wunsch_boost(t[0])))[:6]

    # --- Anbieter-Abhängigkeit (Blast-Radius) ---
    prov_count: dict[str, list] = {}
    for e, a, r in placed:
        for pr in (e.get("providers") or []):
            prov_count.setdefault(pr, []).append(e.get("name"))
    top_prov = sorted([(p, v) for p, v in prov_count.items() if p != "open"],
                      key=lambda kv: -len(kv[1]))

    # --- Kompetenz-Nachfrage (E15) + Kritikalität/Erosion ---
    tally: dict[str, list] = {}
    for e, a, r in placed:
        if relg(a) < 4:
            continue
        w = relo(a)
        for c in (e.get("competences") or []):
            t = tally.setdefault(c, [0, set()])
            t[0] += w
            t[1].add(e.get("name"))
    ranked = sorted(tally.items(), key=lambda kv: (-kv[1][0], comp_label.get(kv[0], kv[0])))
    reco = [(comp_label.get(c, c), sc) for c, (sc, _n) in ranked[:5]]

    crit_of: dict[str, int] = {}
    for ca in collect(inst / "competences", "*.yaml", "competence_assessments"):
        cid = ca.get("competence_id")
        if cid:
            crit_of[cid] = ca.get("criticality", 0)
    dmap = {c: v[0] for c, v in tally.items()}
    demanded = sorted(v for v in dmap.values() if v > 0)
    median_d = demanded[len(demanded) // 2] if demanded else 0
    low_cut = 0.25 * median_d
    reco_ids = {c for c, _ in ranked[:5]}
    erosion = [comp_label.get(c, c) for c, cr in crit_of.items()
               if cr >= 4 and c not in reco_ids and dmap.get(c, 0) <= low_cut]

    # --- Markt-/Blasen-Tendenz ---
    markt = latest.get("entry.ki-markt-tragfaehigkeit")
    bubble = ""
    if markt:
        h = (markt.get("historical_analogies") or [{}])[0]
        bubble = h.get("begruendung_kurz") or markt.get("rationale", "")

    # --- Reifegrad: Belege bestätigt vs. zu verifizieren; ratifiziert von Mensch ---
    n_ratified = sum(1 for e, a, r in placed if str(a.get("reviewer", "")).startswith("mensch"))
    per_theme_conf = []
    for e, a, r in placed:
        eo = [o for o in obs_all if o.get("radar_entry_id") == e["id"]]
        conf = sum(1 for o in eo if o.get("confidence") == "confirmed")
        per_theme_conf.append((e.get("name"), conf, len(eo)))
    tot_obs = sum(n for _, _, n in per_theme_conf)
    tot_conf = sum(c for _, c, _ in per_theme_conf)
    thin = sorted([(nm, c, n) for nm, c, n in per_theme_conf if n >= 2 and c / n < 0.5],
                  key=lambda t: t[1] / t[2])[:4]

    # --- Handlungsempfehlungen (aus den Daten abgeleitet) ---
    actions = []
    if top_prov and len(top_prov[0][1]) >= 3:
        p, v = top_prov[0]
        actions.append(f"<b>Abhängigkeit von {esc(PLABEL.get(p, p))} absichern</b> — {len(v)} Themen hängen daran. "
                       f"Ein Open-Model-/Lokal-Pilot (offene Modelle als Hedge) senkt das Klumpenrisiko und stärkt die Datenresidenz.")
    if reco:
        actions.append("<b>Kompetenzen priorisiert aufbauen</b> — nächste 6 Monate: "
                       + ", ".join(esc(n) for n, _ in reco[:3]) + ".")
    if erosion:
        actions.append("<b>Kritische Grundlagen bewusst erhalten</b> — im Blick behalten (hohe Kritikalität, wenig Nachfrage): "
                       + ", ".join(esc(x) for x in erosion) + ". Wissen/Nachwuchs sichern, bevor es still erodiert.")
    if any(e["id"] in ("entry.ai-act", "entry.ki-governance") for e, a, r in placed):
        actions.append("<b>Governance-Position beziehen</b> — der EU AI Act wirkt als De-facto-Massstab; den CH-Weg (Sektorrecht, Europarat) aktiv verfolgen und früh positionieren.")
    if bubble:
        actions.append("<b>Markt-Tragfähigkeit beobachten, nicht wetten</b> — " + esc(bubble)
                       + " Der Hebel ist Resilienz (offene Modelle, dauerhafte Kompetenzen), kein Markt-Timing.")

    # ------------------------------------------------------------------ HTML
    def ring_badge(r):
        col = {"Adopt": GREEN, "Pilot": GOLD, "Explore": "#6b6862", "Watch": "#8a867e"}.get(r, INK)
        return f'<span class="rb" style="color:{col}">{esc(r)}</span>'

    o = []
    w = o.append

    ringcount: dict[str, int] = {}
    for e, a, r in placed:
        ringcount[r] = ringcount.get(r, 0) + 1
    ringline = " · ".join(f"{ringcount.get(k,0)}× {k}" for k in ("Adopt", "Pilot", "Explore", "Watch") if ringcount.get(k))
    w('<section class="lage">'
      f'<div><span class="k">Themen</span><b>{len(placed)}</b> aktiv <span class="mut">({ringline})</span></div>'
      + (f'<div><span class="k">Grösste Abhängigkeit</span><b>{esc(PLABEL.get(top_prov[0][0], top_prov[0][0]))}</b> — {len(top_prov[0][1])} Themen</div>' if top_prov else '')
      + (f'<div><span class="k">Markt-Tendenz</span><b class="warn">Spannung beobachten</b></div>' if bubble else '')
      + '</section>')

    # Mandanten-Profil anzeigen (oder zum Ausfüllen einladen).
    if profil:
        def pv(k):
            v = profil.get(k)
            return ", ".join(str(x) for x in v) if isinstance(v, list) else (v or "")
        prows = []
        for lbl, k in [("Typ", "typ"), ("Schwerpunkte", "schwerpunkte"), ("Wunschbranchen", "wunschbranchen"),
                       ("Risikofreudigkeit", "risikofreudigkeit"), ("Souveränität", "souveraenitaet"), ("KPIs", "kpis")]:
            if pv(k):
                prows.append(f'<div><span class="k">{lbl}</span>{esc(pv(k))}</div>')
        if prows:
            w('<h2>Mandanten-Profil <a class="edit" href="profil.html">bearbeiten →</a></h2>')
            w('<section class="lage prof">' + "".join(prows) + '</section>')
    else:
        w('<p class="mut" style="background:#fff;border:1px solid #e7e3da;border-radius:12px;padding:12px 14px">'
          'Noch <b>kein Mandanten-Profil</b> hinterlegt — im '
          '<a href="profil.html">Profil-Formular</a> erfassen (Risikofreudigkeit, '
          'Wunschbranchen, KPIs …), damit Chancen &amp; Empfehlungen auf euch zugeschnitten sind.</p>')

    w('<h2>Chancen — worauf jetzt setzen</h2>')
    w('<div class="cards">')
    for e, a, r in chancen:
        w(f'<a class="card" href="detail-{esc(slug(e["id"]))}.html">'
          f'<div class="ch"><b>{esc(e.get("name"))}</b> {ring_badge(r)}</div>'
          f'<div class="mut">{esc(RING_MEAN.get(r, ""))} · Org-Relevanz {esc(relo(a))}/5</div></a>')
    w('</div>')

    w('<h2>Risiken & Abhängigkeiten</h2><ul class="risk">')
    if top_prov:
        p, v = top_prov[0]
        hedge = ", ".join(entries[e["id"]].get("name") for e, a, r in placed
                          if "open" in (e.get("providers") or []))
        w(f'<li><b>Anbieter-Klumpenrisiko:</b> {esc(PLABEL.get(p, p))} trägt {len(v)} Themen '
          f'({esc(", ".join(v[:4]))}{"…" if len(v) > 4 else ""}). '
          f'Hedge: offene/lokale Modelle{(" (" + esc(hedge) + ")") if hedge else ""}.</li>')
    if erosion:
        w(f'<li><b>Kompetenz-Erosion:</b> kritisch, aber wenig nachgefragt — {esc(", ".join(erosion))}. '
          'Gefahr des stillen Abbaus.</li>')
    if bubble:
        w(f'<li><b>Markt/Blasenrisiko:</b> {esc(bubble)}</li>')
    w('</ul>')

    w('<h2>Kompetenz-Empfehlungen (aus den Daten, E15)</h2>')
    w('<p class="mut">Aufbauen (Nachfrage): <b>' + ", ".join(esc(n) for n, _ in reco) + '</b>.'
      + (f' &nbsp;·&nbsp; Erhalten (Erosionsrisiko): <b>{esc(", ".join(erosion))}</b>.' if erosion else '') + '</p>')

    w('<h2>Handlungsempfehlungen</h2><ol class="act">')
    for act in actions:
        w(f'<li>{act}</li>')
    w('</ol>')

    pct = round(100 * tot_conf / tot_obs) if tot_obs else 0
    w('<h2>Reifegrad & Vertrauen</h2>')
    w(f'<p class="mut"><b>{n_ratified}/{len(placed)}</b> Themen mit menschlich ratifizierter Wertung (E4) · '
      f'<b>{tot_conf}/{tot_obs}</b> Belege bestätigt (~{pct}%), Rest „likely/zu verifizieren".</p>')
    if thin:
        w('<p class="mut">Am dünnsten belegt (mehr Prüfung nötig): '
          + ", ".join(f'{esc(nm)} ({c}/{n})' for nm, c, n in thin) + '.</p>')

    stamp = datetime.date.today().isoformat()
    doc = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Management-Lagebild — KI-Radar</title>
<style>
  body{{margin:0;background:{PAPER};color:{INK};font-family:system-ui,-apple-system,sans-serif;padding:28px}}
  .wrap{{max-width:780px;margin:0 auto}}
  a.back{{font-size:13px;color:{GOLD};text-decoration:none}}
  .sig{{font-size:12px;letter-spacing:.3em;text-transform:uppercase;color:{GOLD};margin:8px 0 0}}
  h1{{font-size:26px;font-weight:600;margin:4px 0 2px}}
  .sub{{color:#6b6862;font-size:14px;margin:0 0 14px}}
  h2{{font-size:18px;font-weight:600;margin:24px 0 8px}}
  .mut{{color:#6b6862;font-size:13.5px;line-height:1.6}}
  .k{{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#8a867e;display:block}}
  .warn{{color:{RED}}}
  .lage{{display:flex;flex-wrap:wrap;gap:12px 26px;background:#fff;border:1px solid #e7e3da;border-radius:12px;padding:14px 16px}}
  .lage b{{font-size:17px}}
  .prof{{background:#faf7f1}} .prof b{{font-size:14px}}
  .edit{{font-size:12px;font-weight:400;color:{GOLD};text-decoration:none}}
  .mut a{{color:{GOLD}}}
  .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}}
  .card{{display:block;background:#fff;border:1px solid #e7e3da;border-radius:12px;padding:12px 14px;text-decoration:none;color:inherit;transition:border-color .12s}}
  .card:hover{{border-color:{GOLD}}}
  .ch{{font-size:15px}}
  .rb{{font-size:12px;font-weight:700;margin-left:4px}}
  ul.risk{{margin:0;padding-left:18px}} ul.risk li{{font-size:14px;line-height:1.6;margin:0 0 6px}}
  ol.act{{margin:0;padding-left:20px}} ol.act li{{font-size:14px;line-height:1.6;margin:0 0 8px}}
  .note{{font-size:12px;color:#8a867e;margin:24px 0 0}}
</style></head><body><div class="wrap">
<a class="back" href="index.html">← zum Radar</a>
<p class="sig">Aletheia · Radar · Lagebild</p>
<h1>Management-Lagebild</h1>
<p class="sub">Mandant <b>{esc(mandant)}</b> · Stand {ch_date(stamp)} · verdichtet aus der eigenen Kuratierung (pro Mandant, E25)</p>
{''.join(o)}
<p class="note">Interne, strategische Sicht (E25/E26) — nicht veröffentlichen. Pro
Mandant aus dessen Wertung abgeleitet; im MVP je Mandant. KEINE Anlage-Aussage.
Erzeugt mit view/lagebild.py — read-only.</p>
</div></body></html>"""
    return doc


def main() -> int:
    ap = argparse.ArgumentParser(description="Management-Lagebild je Mandant.")
    ap.add_argument("--instance", required=True)
    ap.add_argument("--mode", choices=["internal", "public"], default="internal")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.mode == "public":
        print("Lagebild ist private Wertung (E25/E26) — nur internal."); return 0
    inst = Path(args.instance)
    if not inst.is_absolute():
        inst = (Path.cwd() / inst).resolve()
    doc = render_lagebild(inst)
    out = Path(args.out)
    if not out.is_absolute():
        out = (Path.cwd() / out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    print(f"Lagebild: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
