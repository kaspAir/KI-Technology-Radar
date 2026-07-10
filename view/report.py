#!/usr/bin/env python3
"""report.py — erzeugt einen Monatsbericht als Projektion (E21, R7).

Der Bericht ist kein gepflegtes Artefakt, sondern wird für einen Zeitraum
t0 → t1 aus dem Ereignisprotokoll und dem aktuellen Radar-Stand berechnet.
Sektionen 0 und 2 fallen als Abfrage über die Events an; 5 wird aggregiert
(E15); 8 aus review_due. Read-only.

Aufruf:
  python view/report.py --instance ../KI-Technology-Radar-Instanz --from 2026-07-13 --to 2026-08-14
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

import yaml

from _fmt import ch_date

CORE = Path(__file__).resolve().parent.parent
RING_ORDER = ["Adopt", "Pilot", "Explore", "Watch", "Reject"]
RING_MEAN = {"Watch": "beobachten", "Explore": "aktiv experimentieren",
             "Pilot": "in echtem Kontext erproben", "Adopt": "produktiv nutzen",
             "Reject": "bewusst nicht verfolgen"}

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def _normalize(v):
    if isinstance(v, dict):
        return {k: _normalize(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_normalize(x) for x in v]
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.isoformat()
    return v


def load_yaml(p: Path):
    with p.open(encoding="utf-8") as fh:
        return _normalize(yaml.safe_load(fh))


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


def top_area(area_id: str) -> str:
    parts = (area_id or "").split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else area_id


def main() -> int:
    ap = argparse.ArgumentParser(description="Monatsbericht als Projektion (E21).")
    ap.add_argument("--instance", required=True)
    ap.add_argument("--from", dest="frm", help="YYYY-MM-DD (Default: erstes Ereignis)")
    ap.add_argument("--to", dest="to", help="YYYY-MM-DD (Default: heute)")
    ap.add_argument("--out", help="Zieldatei (Default: stdout)")
    args = ap.parse_args()
    inst = Path(args.instance)
    if not inst.is_absolute():
        inst = (Path.cwd() / inst).resolve()

    area_terms = [t for t in collect(CORE / "vocab-core", "area.yaml", "terms") if not t.get("parent_id")]
    area_label = {t["id"]: t["label"] for t in area_terms}
    comp_label = {t["id"]: t.get("label", t["id"]) for t in collect(CORE / "vocab-core", "competence.yaml", "terms")}
    pat_label = {p["id"]: p.get("label", p["id"]) for p in collect(CORE / "patterns", "patterns.yaml", "patterns")}

    entries = {e["id"]: e for e in collect(inst / "entries", "entry.yaml", "entries")}
    assessments = collect(inst / "entries", "assessments.yaml", "assessments")
    by_entry: dict[str, list] = {}
    for a in assessments:
        by_entry.setdefault(a["radar_entry_id"], []).append(a)
    for lst in by_entry.values():
        lst.sort(key=lambda a: a.get("valid_from", ""))

    events = []
    elog = inst / "events" / "events.log"
    if elog.exists():
        for line in elog.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    events.sort(key=lambda e: e.get("at", ""))

    def edate(ev):
        return (ev.get("at") or "")[:10]

    frm = args.frm or (edate(events[0]) if events else "0000-00-00")
    to = args.to or datetime.date.today().isoformat()
    in_period = [e for e in events if frm <= edate(e) <= to]

    # Radar-Stand ZUM ZEITPUNKT to (nicht absolut jüngstes) — macht auch
    # historische Berichte temporal korrekt (E3/E21).
    def asof(lst):
        cand = [a for a in lst if a.get("valid_from", "") <= to]
        return cand[-1] if cand else None
    latest = {rid: a for rid, a in ((rid, asof(lst)) for rid, lst in by_entry.items()) if a}

    def by_verb(v):
        return [e for e in in_period if e.get("verb") == v]

    out: list[str] = []
    w = out.append
    w(f"# KI-Radar — {ch_date(frm)} → {ch_date(to)}")
    w("")
    w("*Projektion über das Ereignisprotokoll und den aktuellen Radar-Stand (E21). "
      "Automatisch erzeugt mit view/report.py.*")
    w("")

    # 0. Aktivität
    obs_added = len(by_verb("observation.added"))
    ratified = len(by_verb("assessment.ratified"))
    drafted_ki = len([e for e in by_verb("assessment.drafted") if (e.get("actor") or "").startswith("ki:")])
    ring_changes = by_verb("ring.changed")
    w("## 0. Aktivität")
    w(f"{len(in_period)} Ereignisse im Zeitraum: {obs_added} Beobachtungen erfasst, "
      f"{ratified} Assessments ratifiziert, {len(ring_changes)} Ring-Wechsel. "
      f"Davon {drafted_ki} Entwürfe von der KI (Rest manuell). Alle Endfassungen menschlich bestätigt (E4).")
    w("")

    # 1. Wichtigste Entwicklungen (Einträge, die im Zeitraum entstanden oder bewegt wurden), nach Bereich
    touched_ids = {e["subject_id"] for e in in_period
                   if e.get("verb") in ("entry.created", "ring.changed")
                   and (e.get("subject_id") or "").startswith("entry.")}
    w("## 1. Wichtigste Entwicklungen")
    if not touched_ids:
        w("Keine neuen oder bewegten Einträge im Zeitraum.")
    else:
        by_area: dict[str, list] = {}
        for eid in touched_ids:
            e = entries.get(eid)
            if e:
                by_area.setdefault(top_area(e.get("area", "")), []).append(e)
        for aid in sorted(by_area, key=lambda a: area_label.get(a, a)):
            w(f"**{area_label.get(aid, aid)}**")
            for e in by_area[aid]:
                r = (latest.get(e["id"]) or {}).get("ring", e.get("current_ring"))
                w(f"- **{e.get('name')}** → Ring **{r}**")
            w("")

    # 2. Bewegungen
    w("## 2. Bewegungen (Ring-Wechsel + Momentum)")
    if ring_changes:
        for ev in ring_changes:
            e = entries.get(ev.get("subject_id"), {})
            p = ev.get("payload") or {}
            frm_r = p.get("from") if isinstance(p, dict) else None
            to_r = p.get("to") if isinstance(p, dict) else None
            arrow = f"{frm_r or '—'} → **{to_r}**"
            w(f"- **{e.get('name', ev.get('subject_id'))}**: {arrow}")
    else:
        w("Keine Ring-Wechsel im Zeitraum.")
    # Momentum-Änderungen aus den im Zeitraum ratifizierten Assessments
    mom = []
    for rid, lst in by_entry.items():
        period_as = [a for a in lst if frm <= a.get("valid_from", "") <= to]
        if period_as:
            newest = period_as[-1]
            prior = [a for a in lst if a.get("valid_from", "") < newest.get("valid_from", "")]
            if prior and prior[-1].get("momentum") != newest.get("momentum"):
                mom.append(f"- **{entries.get(rid, {}).get('name', rid)}**: Momentum "
                           f"{prior[-1].get('momentum')} → **{newest.get('momentum')}** (ohne Ring-Wechsel)"
                           if not any(rc.get("subject_id") == rid for rc in ring_changes)
                           else f"- **{entries.get(rid, {}).get('name', rid)}**: Momentum → {newest.get('momentum')}")
    for line in mom:
        w(line)
    # Divergenzen (E9): KI-Entwurf-Ring weicht von der Endfassung ab
    for rid, lst in by_entry.items():
        for a in lst:
            if (frm <= a.get("valid_from", "") <= to and a.get("draft_ring")
                    and a.get("draft_ring") != a.get("ring")):
                w(f"- **{entries.get(rid, {}).get('name', rid)}**: KI-Entwurf "
                  f"{a['draft_ring']} → Endfassung **{a['ring']}** (Divergenz, E9)")
    w("")

    # Chancen / Risiken aus den im Zeitraum gültigen Assessments
    def args_in_period(kind):
        # Nur Einträge, die es zum Stichtag gab, mit ihrem Stand as-of `to`
        # (latest = asof(to)) — kein Rückgriff auf zukünftige Assessments.
        res = []
        for rid, a in latest.items():
            for item in a.get("draft_arguments", {}).get(kind, []):
                res.append((entries.get(rid, {}).get("name", rid), item.get("statement")))
        return res

    w("## 3. Chancen")
    for name, st in args_in_period("opportunities"):
        w(f"- *{name}:* {st}")
    w("")
    w("## 4. Risiken")
    for name, st in args_in_period("risks"):
        w(f"- *{name}:* {st}")
    w("")

    # 5. Kompetenzempfehlung (E15) — aus hochrelevanten Einträgen aggregiert
    tally: dict[str, list] = {}
    for rid, a in latest.items():
        if (a.get("relevance_general") or 0) < 4:
            continue
        weight = a.get("relevance_org") or a.get("relevance_general") or 0
        for c in (entries.get(rid, {}).get("competences") or []):
            t = tally.setdefault(c, [0, set()])
            t[0] += weight
            t[1].add(entries.get(rid, {}).get("name"))
    ranked = sorted(tally.items(), key=lambda kv: (-kv[1][0], comp_label.get(kv[0], kv[0])))
    w("## 5. Empfohlene Kompetenzentwicklung")
    w("Aus den Kompetenz-Verknüpfungen der hochrelevanten Einträge aggregiert (E15):")
    for cid, (score, names) in ranked[:6]:
        w(f"- **{comp_label.get(cid, cid)}** ({score}) — {', '.join(sorted(names))}")
    w("")

    # Kompetenz-Risiken: Kritikalität × Nachfrage-VERLAUF (Anfang→Ende Zeitraum).
    # Trennt Erosion (fallende Nachfrage) von Blindspot/aufkommend (nie Nachfrage).
    def demand_at(dt: str) -> dict[str, int]:
        d: dict[str, int] = {}
        for rid, lst in by_entry.items():
            cand = [a for a in lst if a.get("valid_from", "") <= dt]
            if not cand or (cand[-1].get("relevance_general") or 0) < 4:
                continue
            wgt = cand[-1].get("relevance_org") or cand[-1].get("relevance_general") or 0
            for c in (entries.get(rid, {}).get("competences") or []):
                d[c] = d.get(c, 0) + wgt
        return d

    crit_of: dict[str, tuple] = {}
    for ca in collect(inst / "competences", "*.yaml", "competence_assessments"):
        cid = ca.get("competence_id")
        if cid and (cid not in crit_of or ca.get("valid_from", "") >= crit_of[cid][1]):
            crit_of[cid] = (ca.get("criticality", 0), ca.get("valid_from", ""))
    dnow, dref = demand_at(to), demand_at(frm)
    flags = []
    for cid, (crit, _) in crit_of.items():
        if crit < 4:
            continue
        now, ref = dnow.get(cid, 0), dref.get(cid, 0)
        if now < ref:
            flags.append((cid, crit, ref, now, "Erosion", "⚠️", "fallende Nachfrage bei hoher Kritikalität — Nachwuchs/Wissen bewusst erhalten"))
        elif now == 0:
            flags.append((cid, crit, ref, now, "Blindspot/aufkommend", "👁️", "kritisch, aber (noch) keine Nachfrage im Radar"))
    w("## 5a. Kompetenz-Risiken (Kritikalität × Nachfrage-Verlauf)")
    if flags:
        for cid, crit, ref, now, kind, icon, note in sorted(flags, key=lambda r: (r[4] != "Erosion", -r[1])):
            w(f"- {icon} **{comp_label.get(cid, cid)}** [{kind}] — Kritikalität {crit}, "
              f"Nachfrage {ref}→{now}: {note}.")
    else:
        w("Keine kritischen Kompetenzen ausser Nachfrage.")
    w("")

    # 6. Historische Einordnung
    w("## 6. Historische Einordnung")
    for rid, a in latest.items():
        for h in a.get("historical_analogies", []):
            w(f"- **{entries.get(rid, {}).get('name', rid)}** ~ *{pat_label.get(h.get('pattern'), h.get('pattern'))}*. "
              f"Grenze: {h.get('limit')}")
    w("")

    # 7. Empfehlung / Entscheidungen (aus dem aktuellen Ring je Eintrag)
    w("## 7. Empfehlung / Entscheidungen")
    rows7 = [(RING_ORDER.index(a["ring"]) if a.get("ring") in RING_ORDER else 9,
              entries.get(rid, {}).get("name"), a.get("ring")) for rid, a in latest.items()]
    for _, name, ring in sorted(rows7):
        w(f"- **{name}** → {ring} ({RING_MEAN.get(ring, '')}).")
    w("")

    # 8. Fällige Überprüfungen
    w("## 8. Fällige Überprüfungen")
    ents_asof = [entries[rid] for rid in latest if rid in entries]
    overdue = [(e.get("name"), e.get("review_due")) for e in ents_asof
               if e.get("review_due") and e.get("review_due") <= to]
    if overdue:
        for name, due in sorted(overdue, key=lambda x: x[1]):
            w(f"- **{name}** — überfällig seit {ch_date(due)}")
    else:
        nxt = sorted({e.get("review_due") for e in ents_asof if e.get("review_due")})
        w(f"Keine überfällig. Nächste Prüftermine: {', '.join(ch_date(d) for d in nxt) if nxt else '—'}.")
    w("")

    text = "\n".join(out)
    if args.out:
        p = Path(args.out)
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print(f"Geschrieben: {p}  (Zeitraum {frm} → {to}, {len(in_period)} Ereignisse)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
