#!/usr/bin/env python3
"""begruendung.py — entwirft je historischem Vergleich eine BELEGBASIERTE Begründung.

Für jeden Eintrag mit einem historischen Vergleich (Analogie zu einem Muster)
liest das Skript die Beobachtungen (Artikel) DIESES Eintrags und entwirft mit dem
Modell eine Begründung, die zeigt, wie sich Kern UND Frühindikator des Musters an
GENAU DIESEN Belegen zeigen — nicht aus Allgemeinwissen (E8/E13). Der Entwurf wird
in die Analogie geschrieben (Felder 'begruendung' + 'begruendung_kurz'), plus ein
Event 'assessment.enriched'. KI entwirft, Mensch ratifiziert (E4).

  python src/begruendung.py --instance ../KI-Technology-Radar-Instanz \
      --model claude-haiku-4-5-20251001 --max-cost-usd 2
  # optional: --only transformer,ai-act   --dry-run
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

import yaml

# call_anthropic wird aus ingest.py wiederverwendet (gleicher Ordner).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest import call_anthropic  # noqa: E402

CORE = Path(__file__).resolve().parent.parent

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


def extract_json(t: str) -> dict:
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j < 0:
        raise ValueError("keine JSON-Antwort")
    return json.loads(t[i:j + 1])


SYSTEM = (
    "Du bist der Begründungs-Assistent eines KI-Technology-Radars. Du ENTWIRFST "
    "nur; ein Mensch ratifiziert (E4). WICHTIG: Deine Begründung darf sich "
    "AUSSCHLIESSLICH auf die unten gelisteten Belege (Beobachtungen dieses "
    "Eintrags) stützen — NICHT auf Allgemeinwissen, nicht auf Technikgeschichte, "
    "nicht auf erfundene Fakten (E8/E13). Nenne konkrete Belege. Wenn die Belege "
    "das Muster nur schwach stützen, sage das. Schreibe nüchternes Deutsch "
    "(Schweizer Rechtschreibung, 'ss' statt 'ß'). Antworte AUSSCHLIESSLICH mit "
    "einem JSON-Objekt."
)


def build_user(pat: dict, entry_name: str, belege: list[dict]) -> str:
    lines = "\n".join(
        f"- {b['title']}: {(b.get('summary') or '')[:400]}" for b in belege
    ) or "(keine Belege vorhanden)"
    return (
        f"Muster: {pat.get('label')}\n"
        f"Kern des Musters: {pat.get('kern')}\n"
        f"Frühindikator des Musters: {pat.get('fruehindikator')}\n\n"
        f"Radar-Eintrag: {entry_name}\n"
        f"Belege dieses Eintrags (Titel: Zusammenfassung):\n{lines}\n\n"
        "Aufgabe: Zeige, wie sich Kern UND Frühindikator dieses Musters an GENAU "
        "diesen Belegen zeigen. Gib JSON:\n"
        '{"begruendung": "3–5 Sätze, ausschliesslich aus den Belegen, mit '
        'konkreten Bezügen darauf; mappt Kern und Frühindikator auf die Belege", '
        '"begruendung_kurz": "ein Satz als Zusammenfassung für die Radar-Übersicht"}'
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Belegbasierte Begründungen je historischem Vergleich entwerfen.")
    ap.add_argument("--instance", required=True)
    ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--only", default="", help="Kommaliste von Eintrags-Slugs (sonst alle)")
    ap.add_argument("--max-output-tokens", type=int, default=60000)
    ap.add_argument("--max-cost-usd", type=float, default=3.0)
    ap.add_argument("--price-in", type=float, default=1.0)
    ap.add_argument("--price-out", type=float, default=5.0)
    ap.add_argument("--dry-run", action="store_true", help="nur anzeigen, nichts schreiben")
    args = ap.parse_args()

    inst = Path(args.instance)
    if not inst.is_absolute():
        inst = (Path.cwd() / inst).resolve()
    only = {s.strip() for s in args.only.split(",") if s.strip()}

    patterns = {p["id"]: p for p in
                load_yaml(CORE / "patterns" / "patterns.yaml").get("patterns", [])}

    now = datetime.datetime.now(datetime.timezone.utc).astimezone().replace(microsecond=0).isoformat()
    elog = inst / "events" / "events.log"
    import re
    mx = max([int(m.group(1)) for m in re.finditer(r"evt\.rat-(\d+)", elog.read_text(encoding="utf-8"))] + [0]) \
        if elog.exists() else 0

    tok_out = 0
    cost = 0.0
    n_ok = 0
    new_events = []

    for d in sorted((inst / "entries").glob("*/")):
        slug = d.name
        if only and slug not in only:
            continue
        af = d / "assessments.yaml"
        of = d / "observations.yaml"
        ef = d / "entry.yaml"
        if not (af.exists() and ef.exists()):
            continue
        doc = load_yaml(af)
        asl = doc.get("assessments", [])
        if not asl:
            continue
        latest = sorted(asl, key=lambda a: a.get("valid_from", ""))[-1]
        analogies = latest.get("historical_analogies") or []
        if not analogies:
            continue
        entry = load_yaml(ef)
        belege = (load_yaml(of).get("observations", []) if of.exists() else [])
        changed = False
        for h in analogies:
            pat = patterns.get(h.get("pattern"))
            if not pat:
                continue
            if args.max_output_tokens and tok_out >= args.max_output_tokens:
                print("Deckel Output-Tokens erreicht — Stopp."); break
            if args.max_cost_usd and cost >= args.max_cost_usd:
                print("Kosten-Deckel erreicht — Stopp."); break
            user = build_user(pat, entry.get("name", slug), belege)
            try:
                text, usage = call_anthropic(args.model, SYSTEM, user, 900)
                obj = extract_json(text)
            except Exception as e:
                print(f"  !! {slug} ~ {h.get('pattern')}: {e}")
                continue
            ti = usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
            to = usage.get("output_tokens", 0)
            tok_out += to
            cost += ti / 1e6 * args.price_in + to / 1e6 * args.price_out
            begr = (obj.get("begruendung") or "").strip()
            kurz = (obj.get("begruendung_kurz") or "").strip()
            if not begr:
                print(f"  !! {slug}: leere Begründung"); continue
            print(f"  OK {slug} ~ {h.get('pattern')} ({len(belege)} Belege)")
            if args.dry_run:
                print("     ", begr[:160], "…")
                continue
            h["begruendung"] = begr
            if kurz:
                h["begruendung_kurz"] = kurz
            changed = True
            mx += 1
            new_events.append({"id": f"evt.rat-{mx:04d}", "at": now, "actor": f"ki:{args.model}",
                               "verb": "assessment.enriched", "subject_id": latest["id"],
                               "payload": {"field": "begruendung", "grounded_in": "observations"}})
            n_ok += 1
        if changed and not args.dry_run:
            af.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")

    if new_events and not args.dry_run:
        with elog.open("a", encoding="utf-8") as fh:
            for e in new_events:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")

    print(f"\n{n_ok} Begründungen entworfen · ~{tok_out} Output-Tokens · ~${cost:.2f}"
          + (" (dry-run, nichts geschrieben)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
