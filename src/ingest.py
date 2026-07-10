#!/usr/bin/env python3
"""ingest.py — Ingestion-Agent: kuratierte Quellen -> Eingangskorb (E20).

Der Agent SAMMELT und ENTWIRFT, er ratifiziert nichts (E4). Ergebnis sind
`status: inbox`-Beobachtungen unter der Instanz `inbox/`, die ein Mensch später
prüft und in den Radar hebt. Quellen sind KURATIERT (E6) — kein offenes Crawling.

Betrieb: läuft serverseitig (Cron/Jenkins), unabhängig vom Laptop. Kosten laufen
auf den Anthropic-Key des Betreibers; deshalb HARTE Deckel (--max-items,
--max-output-tokens) und ehrliche Token-/Kosten-Bilanz im Laufbericht.

Modi:
  --dry-run   holt die Quelle, erzeugt Roh-Entwürfe aus den Metadaten OHNE
              KI-Aufruf (kostenlos) — zum Testen der Mechanik.
  (real)      ruft das Modell mit dem Bewertungsraster der Instanz auf, das
              relevante Treffer bewertet und Beobachtungen entwirft.

Kalibrier-Aufruf (nur arXiv, letzte ~12 Monate, kleiner Deckel):
  python src/ingest.py --instance ../KI-Technology-Radar-Instanz \
      --source source.research-ml --arxiv-query "cat:cs.CL OR cat:cs.AI" \
      --since 2025-07-01 --max-items 15 --max-output-tokens 20000 --dry-run
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

CORE = Path(__file__).resolve().parent.parent
ARXIV_API = "http://export.arxiv.org/api/query"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ATOM = "{http://www.w3.org/2005/Atom}"

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


def slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s or "x"


# --- Quellen-Adapter: arXiv --------------------------------------------------

def fetch_arxiv(query: str, since: str, max_items: int, source_xml: str | None) -> list[dict]:
    """Holt jüngste arXiv-Treffer (submittedDate desc) und filtert client-seitig
    auf published >= since. Liefert normalisierte Item-Dicts."""
    if source_xml:
        raw = Path(source_xml).read_text(encoding="utf-8")
    else:
        params = urllib.parse.urlencode({
            "search_query": query, "sortBy": "submittedDate",
            "sortOrder": "descending", "start": 0, "max_results": max(max_items * 3, 20),
        })
        with urllib.request.urlopen(f"{ARXIV_API}?{params}", timeout=30) as r:
            raw = r.read().decode("utf-8")
    root = ET.fromstring(raw)
    items = []
    for e in root.findall(f"{ATOM}entry"):
        pub = (e.findtext(f"{ATOM}published") or "")[:10]
        if since and pub and pub < since:
            continue
        aid_url = (e.findtext(f"{ATOM}id") or "").strip()
        aid = re.sub(r"v\d+$", "", aid_url.rsplit("/", 1)[-1])
        authors = [a.findtext(f"{ATOM}name") or "" for a in e.findall(f"{ATOM}author")]
        items.append({
            "arxiv_id": aid,
            "title": " ".join((e.findtext(f"{ATOM}title") or "").split()),
            "summary": " ".join((e.findtext(f"{ATOM}summary") or "").split()),
            "authors": authors,
            "published": pub,
            "url": f"https://arxiv.org/abs/{aid}" if aid else aid_url,
        })
        if len(items) >= max_items:
            break
    return items


def citation_for(item: dict) -> str:
    first = (item["authors"][0].split()[-1] if item.get("authors") else "o.A.")
    etal = " et al." if len(item.get("authors", [])) > 1 else ""
    year = (item.get("published") or "")[:4]
    return f'{first}{etal}, „{item["title"]}", {year}, arXiv:{item["arxiv_id"]}.'


# --- Entwurf: Dry-Run (kostenlos) -------------------------------------------

def draft_dry(item: dict, source_id: str, run_date: str) -> dict:
    return {
        "id": f"obs.ingest-{slugify(item['arxiv_id'])}",
        "radar_entry_id": None,                 # bleibt im Korb bis Ratifikation
        "source_ids": [source_id],
        "title": item["title"][:200],
        "summary": (item["summary"][:400] + "…") if len(item["summary"]) > 400 else item["summary"],
        "citation": citation_for(item),
        "url": item["url"],
        "confidence": "likely",
        "status": "inbox",
        "date_published": item["published"] or run_date,
        "date_observed": run_date,
        "created_by": "ki:ingest-dry",
    }


# --- Entwurf: real (Modellaufruf mit Bewertungsraster) -----------------------

def call_anthropic(model: str, system: str, user: str, max_tokens: int) -> tuple[str, dict]:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY nicht gesetzt (für den echten Lauf nötig).")
    body = json.dumps({
        "model": model, "max_tokens": max_tokens, "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode("utf-8")
    req = urllib.request.Request(ANTHROPIC_URL, data=body, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode("utf-8"))
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    return text, data.get("usage", {})


def draft_real(item, source_id, run_date, rubric, scope, model, max_tokens):
    """Ein Modellaufruf je Item. Das Modell bewertet Relevanz und entwirft — Zitat
    und URL kommen ZWINGEND aus dem Item (keine erfundenen Fundstellen, E8)."""
    system = (
        "Du bist der Ingestion-Assistent eines KI-Technology-Radars für eine "
        "Organisation im Schweizer öffentlichen Sektor. Du ENTWIRFST nur; ein "
        "Mensch ratifiziert (E4). Erfinde nichts: Zitat und URL stammen unverändert "
        "aus dem Item. Antworte AUSSCHLIESSLICH mit einem JSON-Objekt.\n\n"
        "Bewertungsraster (verbindlich):\n" + rubric + "\n\n" + scope
    )
    user = (
        "Item (arXiv):\n"
        f"Titel: {item['title']}\nAutoren: {', '.join(item['authors'][:6])}\n"
        f"Datum: {item['published']}\narXiv-ID: {item['arxiv_id']}\nURL: {item['url']}\n"
        f"Abstract: {item['summary'][:1500]}\n\n"
        "Aufgabe: Ist das für diesen Radar relevant (Feld-Entwicklung, die eine "
        "Beobachtung wert ist)? Gib JSON:\n"
        '{"relevant": bool, "relevance_general": 1-5, "confidence": '
        '"confirmed|likely|rumored", "title": "prägnanter Beobachtungstitel", '
        '"summary": "2-3 Sätze, was neu/bedeutsam ist", "suggested_entry": '
        '"bestehende entry.<id> ODER Vorschlag für neuen Eintragsnamen", '
        '"reason": "kurze Begründung fürs Kuratieren"}'
    )
    text, usage = call_anthropic(model, system, user, max_tokens)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    verdict = json.loads(m.group(0)) if m else {"relevant": False, "reason": "keine JSON-Antwort"}
    obs = None
    if verdict.get("relevant"):
        obs = {
            "id": f"obs.ingest-{slugify(item['arxiv_id'])}",
            "radar_entry_id": None,
            "source_ids": [source_id],
            "title": (verdict.get("title") or item["title"])[:200],
            "summary": verdict.get("summary") or item["summary"][:400],
            "citation": citation_for(item),
            "url": item["url"],
            "confidence": verdict.get("confidence", "likely"),
            "status": "inbox",
            "date_published": item["published"] or run_date,
            "date_observed": run_date,
            "created_by": f"ki:{model}",
        }
    return obs, verdict, usage


# --- Schema-Leichtprüfung der Entwürfe ---------------------------------------

_OBS_RE = re.compile(r"^obs\.[a-z0-9-]+$")


def obs_ok(o: dict) -> str | None:
    if not _OBS_RE.match(o.get("id", "")):
        return f"ungültige id {o.get('id')}"
    for f in ("title", "summary", "citation", "confidence", "status", "created_by"):
        if not o.get(f):
            return f"Feld fehlt: {f}"
    if o["confidence"] not in ("confirmed", "likely", "rumored"):
        return f"confidence {o['confidence']}"
    if o["status"] != "inbox":
        return "status != inbox"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingestion-Agent: Quellen -> Eingangskorb.")
    ap.add_argument("--instance", required=True)
    ap.add_argument("--source", required=True, help="Quellen-ID für die Zuordnung, z.B. source.research-ml")
    ap.add_argument("--arxiv-query", default="cat:cs.CL OR cat:cs.AI OR cat:cs.LG")
    ap.add_argument("--since", default="", help="YYYY-MM-DD: nur Items ab diesem Datum")
    ap.add_argument("--max-items", type=int, default=15, help="harter Deckel: max. Items")
    ap.add_argument("--max-output-tokens", type=int, default=20000, help="harter Deckel: Summe Output-Tokens")
    ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--price-in", type=float, default=0.0, help="USD je 1M Input-Tokens (für die Kostenbilanz)")
    ap.add_argument("--price-out", type=float, default=0.0, help="USD je 1M Output-Tokens")
    ap.add_argument("--dry-run", action="store_true", help="ohne Modellaufruf (kostenlos), nur Mechanik")
    ap.add_argument("--source-file", default=None, help="lokale Atom-XML statt Netz (Test/Reproduktion)")
    ap.add_argument("--run-date", default=datetime.date.today().isoformat())
    ap.add_argument("--out", default=None, help="Ausgabeverzeichnis (Default: <instance>/inbox)")
    args = ap.parse_args()

    inst = Path(args.instance)
    if not inst.is_absolute():
        inst = (Path.cwd() / inst).resolve()
    outdir = Path(args.out) if args.out else inst / "inbox"
    if not outdir.is_absolute():
        outdir = (Path.cwd() / outdir).resolve()

    # Quelle muss kuratiert sein (E6) — sonst kein Ingest.
    src_ids = {s["id"] for s in collect(inst / "sources", "*.yaml", "sources")}
    if args.source not in src_ids:
        sys.exit(f"Quelle {args.source} ist nicht kuratiert (E6). Bekannt: {sorted(src_ids)}")

    items = fetch_arxiv(args.arxiv_query, args.since, args.max_items, args.source_file)
    print(f"Geholt: {len(items)} Items (arXiv, seit {args.since or 'Anfang'})")

    rubric = scope = ""
    if not args.dry_run:
        rub = inst / "agents" / "bewertungsraster.md"
        rubric = rub.read_text(encoding="utf-8") if rub.exists() else ""
        comps = collect(CORE / "vocab-core", "competence.yaml", "terms")
        areas = collect(CORE / "vocab-core", "area.yaml", "terms")
        ents = collect(inst / "entries", "entry.yaml", "entries")
        scope = ("Kontext:\nBereiche: " + ", ".join(t["id"] for t in areas)
                 + "\nKompetenzen: " + ", ".join(t["id"] for t in comps)
                 + "\nBestehende Einträge: "
                 + ", ".join(f'{e["id"]} ({e.get("name")})' for e in ents))

    drafts, report_rows = [], []
    tok_in = tok_out = 0
    for it in items:
        if not args.dry_run and tok_out >= args.max_output_tokens:
            report_rows.append(("—", it["title"][:60], "GESTOPPT (Token-Deckel)"))
            break
        if args.dry_run:
            o = draft_dry(it, args.source, args.run_date)
            verdict = {"relevant": True, "reason": "dry-run: Rohentwurf ohne Bewertung"}
        else:
            try:
                o, verdict, usage = draft_real(it, args.source, args.run_date, rubric,
                                               scope, args.model, 1024)
            except Exception as ex:  # ein Fehler darf den Lauf nicht abbrechen
                report_rows.append(("!", it["title"][:60], f"Fehler: {ex}"))
                continue
            tok_in += usage.get("input_tokens", 0)
            tok_out += usage.get("output_tokens", 0)
        if o:
            err = obs_ok(o)
            if err:
                report_rows.append(("✗", it["title"][:60], f"Entwurf ungültig: {err}"))
                continue
            drafts.append(o)
            report_rows.append(("✓", it["title"][:60],
                                f'rel {verdict.get("relevance_general", "—")} → {verdict.get("suggested_entry", "?")}'))
        else:
            report_rows.append(("·", it["title"][:60], f'verworfen: {verdict.get("reason", "")[:50]}'))

    outdir.mkdir(parents=True, exist_ok=True)
    stamp = f"{args.run_date}-{'dry' if args.dry_run else slugify(args.model)}"
    if drafts:
        obs_path = outdir / f"ingest-{stamp}.yaml"
        obs_path.write_text(yaml.safe_dump({"observations": drafts}, allow_unicode=True,
                                           sort_keys=False), encoding="utf-8")
    # Laufbericht: ehrliche Bilanz (Items, Entwürfe, Tokens, geschätzte Kosten).
    cost = (tok_in / 1e6) * args.price_in + (tok_out / 1e6) * args.price_out
    lines = [f"# Ingestion-Lauf {stamp}", "",
             f"- Quelle: {args.source} · Query: `{args.arxiv_query}` · seit {args.since or 'Anfang'}",
             f"- Modus: {'DRY-RUN (kostenlos)' if args.dry_run else args.model}",
             f"- Items geholt: {len(items)} · Entwürfe: {len(drafts)}",
             f"- Deckel: max_items {args.max_items}, max_output_tokens {args.max_output_tokens}",
             f"- Tokens: {tok_in} in / {tok_out} out"
             + (f" · geschätzte Kosten: ${cost:.4f}" if (args.price_in or args.price_out)
                else " · Kosten: Preise via --price-in/--price-out setzen"),
             "", "## Items", "", "| | Titel | Ergebnis |", "|--|--|--|"]
    lines += [f"| {a} | {b} | {c} |" for a, b, c in report_rows]
    (outdir / f"ingest-{stamp}-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Entwürfe: {len(drafts)} → {outdir}")
    print(f"Tokens: {tok_in} in / {tok_out} out"
          + (f" · ~${cost:.4f}" if (args.price_in or args.price_out) else ""))
    print(f"Bericht: {outdir / f'ingest-{stamp}-report.md'}")
    print("Hinweis: Entwürfe liegen im Eingangskorb (status: inbox) — noch NICHT im Radar. "
          "Ratifikation durch den Menschen (E4) ist der nächste, getrennte Schritt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
