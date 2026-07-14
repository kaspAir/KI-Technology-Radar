#!/usr/bin/env python3
"""markt_refresh.py — entwirft eine AKTUALISIERUNG der Anbieter-Landschaft aus den
frischen Markt-/Anbieter-Kandidaten im Pool (SAMMELN → WERTEN-Entwurf).

Für jede Firma in markt/anbieter.yaml sammelt das Skript die passenden Pool-
Kandidaten (aus dem nächtlichen Web-Monitoring), lässt das Modell daraus einen
Tendenz- + Signal-Entwurf ableiten — AUSSCHLIESSLICH aus diesen Artikeln, mit
echten Fundstellen (E8) — und schreibt einen VORSCHLAG (Markdown). anbieter.yaml
wird NICHT verändert; der Kurator prüft und übernimmt von Hand (E4).

  python src/markt_refresh.py --instance ../KI-Technology-Radar-Instanz \
      --model claude-haiku-4-5-20251001 --max-cost-usd 2
  # -> schreibt <instance>/markt/anbieter-vorschlag.md
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest import call_anthropic  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# Schlüsselwörter je Firma, um passende Kandidaten zu finden.
KEYWORDS = {
    "openai": ["openai", "chatgpt", "sam altman", "gpt-5", "gpt-4"],
    "anthropic": ["anthropic", "claude"],
    "google": ["google", "deepmind", "gemini", "alphabet"],
    "microsoft": ["microsoft", "azure", "copilot"],
    "meta": ["meta", "llama", "zuckerberg", "muse spark"],
    "nvidia": ["nvidia", "jensen huang"],
    "xai": ["xai", "grok", "elon musk"],
    "offene-modelle": ["deepseek", "qwen", "alibaba", "open-weight", "open source", "mistral"],
}
TENDLBL = {"staerker": "stärker 🟢", "stabil": "stabil 🟢", "gespannt": "gespannt 🟠", "unter_druck": "unter Druck 🔴"}


def load_yaml(p: Path):
    with p.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def extract_json(t: str) -> dict:
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j < 0:
        raise ValueError("keine JSON-Antwort")
    return json.loads(t[i:j + 1])


SYSTEM = (
    "Du bist der Markt-Aktualisierungs-Assistent eines KI-Technology-Radars. Du "
    "ENTWIRFST nur; ein Mensch ratifiziert (E4). Nutze AUSSCHLIESSLICH die "
    "vorgelegten Artikel (echte Fundstellen) — erfinde keine Zahlen, keine Quellen "
    "(E8). Wenn die Artikel keine belastbare Änderung stützen, gib tendenz='keine'. "
    "Nüchternes Deutsch (Schweizer Rechtschreibung, 'ss' statt 'ß'). KEINE Anlage-/"
    "Markt-Timing-Empfehlung — nur Beschreibung der Tendenz. Antworte AUSSCHLIESSLICH "
    "mit einem JSON-Objekt."
)


def build_user(firm: dict, cands: list) -> str:
    arts = "\n".join(
        f"- [{c['date']}] {c['title']}: {(c['summary'] or '')[:300]} ({c['url']})"
        for c in cands
    )
    return (
        f"Firma: {firm.get('name')} — Rolle: {firm.get('rolle')}\n"
        f"Aktuelle Tendenz: {firm.get('tendenz')}\n\n"
        f"Frische Artikel (nur diese verwenden):\n{arts}\n\n"
        "Aufgabe: Gib JSON:\n"
        '{"tendenz": "staerker|stabil|gespannt|unter_druck|keine", '
        '"tendenz_begruendung": "1 Satz, warum (oder warum keine Änderung)", '
        '"signale": [{"text": "1 Satz Signal AUS den Artikeln (mit Zahl/Fakt)", '
        '"cite": "Quelle/Medium + Datum", "url": "Artikel-URL", "date": "YYYY-MM-DD"}]}'
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Aktualisierungs-Entwurf der Anbieter-Landschaft.")
    ap.add_argument("--instance", required=True)
    ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--max-output-tokens", type=int, default=40000)
    ap.add_argument("--max-cost-usd", type=float, default=2.0)
    ap.add_argument("--price-in", type=float, default=1.0)
    ap.add_argument("--price-out", type=float, default=5.0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--pool", default=None,
                    help="Pool-Datei mit den frischen Signalen (Default: <instance>/inbox/pool.yaml)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    inst = Path(args.instance)
    if not inst.is_absolute():
        inst = (Path.cwd() / inst).resolve()
    data = load_yaml(inst / "markt" / "anbieter.yaml") or {}
    firmen = data.get("firmen", [])

    pool_path = Path(args.pool) if args.pool else inst / "inbox" / "pool.yaml"
    pool = (load_yaml(pool_path) or {}).get("candidates", []) if pool_path.exists() else []
    # Kandidaten aus dem Markt-/Anbieter-Monitoring (frische Signale).
    MON = {"source.markt-monitoring", "source.anbieter-monitoring", "source.markt-analysen"}
    items = []
    for c in pool:
        o = c.get("observation") or {}
        srcs = set(o.get("source_ids") or [])
        text = ((o.get("title") or "") + " " + (o.get("summary") or "")).lower()
        items.append({"title": o.get("title") or "", "summary": o.get("summary") or "",
                      "url": o.get("url") or "", "date": str(o.get("date_published") or "")[:10],
                      "text": text, "mon": bool(srcs & MON)})

    tok_out, cost = 0, 0.0
    lines = ["# Anbieter-Landschaft — Aktualisierungs-Vorschlag (KI-Entwurf, E4)",
             "",
             f"Erzeugt aus {len(items)} Pool-Kandidaten. **anbieter.yaml wurde NICHT verändert** — "
             "bitte prüfen und von Hand übernehmen. Jede Angabe mit Artikel-Link (E8).",
             ""]
    n_firm = 0
    for f in firmen:
        kws = KEYWORDS.get(f.get("id"), [f.get("name", "").lower()])
        cands = [it for it in items if any(k in it["text"] for k in kws)]
        # Monitoring-Treffer bevorzugen, dann nach Datum, max 6.
        cands.sort(key=lambda x: (not x["mon"], x["date"]), reverse=True)
        cands = cands[:6]
        if not cands:
            lines.append(f"## {f.get('name')} — aktuell: {TENDLBL.get(f.get('tendenz'), f.get('tendenz'))}")
            lines.append("_Keine frischen Kandidaten im Pool — keine Änderung vorgeschlagen._\n")
            continue
        if args.max_output_tokens and tok_out >= args.max_output_tokens:
            lines.append(f"## {f.get('name')}\n_Deckel erreicht — übersprungen._\n"); continue
        if args.max_cost_usd and cost >= args.max_cost_usd:
            lines.append(f"## {f.get('name')}\n_Kosten-Deckel — übersprungen._\n"); continue
        try:
            text, usage = call_anthropic(args.model, SYSTEM, build_user(f, cands), 700)
            obj = extract_json(text)
        except Exception as e:
            lines.append(f"## {f.get('name')}\n_Fehler: {e}_\n"); continue
        to = usage.get("output_tokens", 0)
        tok_out += to
        cost += (usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)) / 1e6 * args.price_in + to / 1e6 * args.price_out
        tnew = obj.get("tendenz", "keine")
        change = "" if tnew in ("keine", f.get("tendenz")) else f" → **Vorschlag: {TENDLBL.get(tnew, tnew)}**"
        lines.append(f"## {f.get('name')} — aktuell: {TENDLBL.get(f.get('tendenz'), f.get('tendenz'))}{change}")
        lines.append(f"_{obj.get('tendenz_begruendung', '')}_")
        for s in (obj.get("signale") or []):
            u = s.get("url", "")
            lines.append(f"- {s.get('text', '')} — [{s.get('cite', 'Quelle')}]({u}) · {s.get('date', '')}")
        lines.append("")
        n_firm += 1
        print(f"  Entwurf {f.get('name')} ({len(cands)} Kandidaten)")

    if not args.dry_run:
        outp = Path(args.out) if args.out else inst / "markt" / "anbieter-vorschlag.md"
        if not outp.is_absolute():
            outp = (Path.cwd() / outp).resolve()
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\nVorschlag geschrieben: {outp}")
    print(f"{n_firm} Firmen-Entwürfe · ~{tok_out} Output-Tokens · ~${cost:.2f}"
          + (" (dry-run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
