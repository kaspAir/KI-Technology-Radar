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
import email.utils
import hashlib
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


# --- Quellen-Adapter ---------------------------------------------------------
# Jeder Adapter liefert normalisierte Items:
#   {source_id, title, summary, url, published (YYYY-MM-DD), slug, cite}
# `url` ist der DEEP-LINK auf den echten Artikel/Eintrag (nicht die Quell-Startseite).

def _norm_date(s: str) -> str:
    s = (s or "").strip()
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        return m.group(1)
    try:
        return email.utils.parsedate_to_datetime(s).date().isoformat()
    except Exception:
        return ""


def _strip_html(s: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", s or "").split())


def fetch_arxiv(src, query, since, max_items, source_xml=None):
    """arXiv-API (submittedDate desc), client-seitig auf published >= since gefiltert."""
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
        aid = re.sub(r"v\d+$", "", (e.findtext(f"{ATOM}id") or "").strip().rsplit("/", 1)[-1])
        authors = [a.findtext(f"{ATOM}name") or "" for a in e.findall(f"{ATOM}author")]
        first = authors[0].split()[-1] if authors and authors[0].split() else "o.A."
        etal = " et al." if len(authors) > 1 else ""
        title = " ".join((e.findtext(f"{ATOM}title") or "").split())
        items.append({
            "source_id": src["id"], "title": title,
            "summary": " ".join((e.findtext(f"{ATOM}summary") or "").split()),
            "url": f"https://arxiv.org/abs/{aid}" if aid else "",
            "published": pub, "slug": slugify(aid),
            "cite": f'{first}{etal}, „{title}", {pub[:4]}, arXiv:{aid}.',
        })
        if len(items) >= max_items:
            break
    return items


def fetch_feed(src, feed_url, since, max_items):
    """Generischer RSS/Atom-Adapter: Titel, Deep-Link, Zusammenfassung, Datum je Item."""
    req = urllib.request.Request(feed_url, headers={"User-Agent": "ki-radar-ingest/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    root = ET.fromstring(raw)
    nodes = root.findall(".//{*}item") or root.findall(".//{*}entry")
    name = src.get("name", src["id"])
    items = []
    for n in nodes:
        title = " ".join((n.findtext("{*}title") or "").split())
        link_el = n.find("{*}link")
        url = ((link_el.get("href") or link_el.text or "").strip() if link_el is not None else "")
        summ = _strip_html(n.findtext("{*}description") or n.findtext("{*}summary")
                           or n.findtext("{*}content") or "")
        pub = _norm_date(n.findtext("{*}pubDate") or n.findtext("{*}published")
                         or n.findtext("{*}updated") or "")
        if not title or not url:
            continue
        if since and pub and pub < since:
            continue
        h = hashlib.md5(url.encode("utf-8")).hexdigest()[:6]
        items.append({
            "source_id": src["id"], "title": title, "summary": summ, "url": url,
            "published": pub, "slug": (slugify(title)[:48] or "x") + "-" + h,
            "cite": f'{name}, „{title}"' + (f", {pub}" if pub else "") + f". {url}",
        })
        if len(items) >= max_items:
            break
    return items


def fetch_source(src, since, max_items, source_xml=None):
    ing = src.get("ingest") or {}
    if ing.get("type") == "arxiv":
        return fetch_arxiv(src, ing.get("query", "cat:cs.AI"), since, max_items, source_xml)
    if ing.get("type") == "feed":
        return fetch_feed(src, ing["feed"], since, max_items)
    return []


# --- Entwurf: Dry-Run (kostenlos) -------------------------------------------

def observation_of(item, run_date, created_by, title=None, summary=None, confidence="likely"):
    body = summary or item.get("summary") or item["title"]
    return {
        "id": f"obs.ingest-{item['slug']}",
        "radar_entry_id": None,                 # bleibt im Korb bis Ratifikation
        "source_ids": [item["source_id"]],
        "title": (title or item["title"])[:200],
        "summary": (body[:400] + "…") if len(body) > 400 else body,
        "citation": item["cite"],
        "url": item["url"],
        "confidence": confidence,
        "status": "inbox",
        "date_published": item["published"] or run_date,
        "date_observed": run_date,
        "created_by": created_by,
    }


def draft_dry(item: dict, run_date: str) -> dict:
    # Ohne Modell keine Branchen-Zuordnung möglich → Querschnitt als Platzhalter.
    return {
        "observation": observation_of(item, run_date, "ki:ingest-dry"),
        "branchen": ["domain.querschnitt-grundlagen"],
        "suggested_entry": "",
        "relevance_general": None,
        "reason": "dry-run: Rohentwurf ohne Bewertung/Branche",
    }


# --- Entwurf: real (Modellaufruf mit Bewertungsraster) -----------------------

def call_anthropic(model: str, system: str, user: str, max_tokens: int) -> tuple[str, dict]:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY nicht gesetzt (für den echten Lauf nötig).")
    # System-Prompt (Raster+Scope) ist über alle Items IDENTISCH → cachen (0.1x, schneller).
    body = json.dumps({
        "model": model, "max_tokens": max_tokens,
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
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


def draft_real(item, run_date, rubric, scope, model, max_tokens):
    """Ein Modellaufruf je Item. Das Modell bewertet Relevanz und entwirft — Zitat
    und URL kommen ZWINGEND aus dem Item (keine erfundenen Fundstellen, E8)."""
    system = (
        "Du bist der Ingestion-Assistent eines KI-Technology-Radars. Du ENTWIRFST "
        "nur; ein Mensch ratifiziert (E4). Erfinde nichts: Zitat und URL stammen "
        "unverändert aus dem Item. Antworte AUSSCHLIESSLICH mit einem JSON-Objekt.\n\n"
        "Aufnahme-Kriterium: Hat das Item mit KÜNSTLICHER INTELLIGENZ zu tun "
        "(Methode, Modell, Anwendung, Governance, Wirkung)? Wenn JA → aufnehmen und "
        "der/den passenden BRANCHE(N) zuordnen, auch wenn es eine Nische ist. Nur "
        "wenn es NICHTS mit KI zu tun hat → verwerfen.\n\n"
        "Bewertungsraster (für relevance_general / Einordnung):\n" + rubric + "\n\n" + scope
    )
    user = (
        "Item:\n"
        f"Titel: {item['title']}\n"
        f"Datum: {item.get('published', '')}\nURL: {item['url']}\n"
        f"Zitat: {item['cite']}\n"
        f"Zusammenfassung/Abstract: {(item.get('summary') or '')[:1500]}\n\n"
        "Aufgabe: Gib JSON:\n"
        '{"ai_related": bool, "branchen": ["domain.<id>", …] (1-3 aus der Branchen-'
        'Liste; wenn nichts speziell passt: ["domain.querschnitt-grundlagen"]), '
        '"new_branche": "" (nur falls eine Branche fehlt: Vorschlag als Klartext), '
        '"relevance_general": 1-5, "confidence": "confirmed|likely|rumored", '
        '"title": "prägnanter deutscher Beobachtungstitel", '
        '"summary": "2-3 Sätze, was neu/bedeutsam ist", '
        '"suggested_entry": "bestehende entry.<id> ODER Vorschlag für neuen Eintragsnamen", '
        '"reason": "kurze Begründung"}'
    )
    def extract(t: str):
        t = re.sub(r"```(?:json)?", "", t or "").strip()
        i, j = t.find("{"), t.rfind("}")
        if i != -1 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except Exception:
                return None
        return None

    text, usage = call_anthropic(model, system, user, max_tokens)
    verdict = extract(text)
    if verdict is None:  # ein strenger Nachschlag, dann aufgeben (verhindert Treffer-Verlust)
        text2, u2 = call_anthropic(
            model, system,
            user + "\n\nWICHTIG: Antworte AUSSCHLIESSLICH mit dem JSON-Objekt — keine Prosa, keine Code-Fences.",
            max_tokens)
        usage = {"input_tokens": usage.get("input_tokens", 0) + u2.get("input_tokens", 0),
                 "output_tokens": usage.get("output_tokens", 0) + u2.get("output_tokens", 0)}
        verdict = extract(text2) or {"ai_related": False, "reason": "keine JSON-Antwort (auch nach Nachschlag)"}
    cand = None
    if verdict.get("ai_related"):
        branchen = [b for b in (verdict.get("branchen") or []) if isinstance(b, str) and b.startswith("domain.")]
        cand = {
            "observation": observation_of(item, run_date, f"ki:{model}",
                                          title=verdict.get("title"), summary=verdict.get("summary"),
                                          confidence=verdict.get("confidence", "likely")),
            "branchen": branchen or ["domain.querschnitt-grundlagen"],
            "new_branche": verdict.get("new_branche") or "",
            "suggested_entry": verdict.get("suggested_entry") or "",
            "relevance_general": verdict.get("relevance_general"),
            "reason": verdict.get("reason") or "",
        }
    return cand, verdict, usage


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
    ap.add_argument("--all-sources", action="store_true",
                    help="alle kuratierten Quellen mit ingest-Block abarbeiten (statt einer)")
    ap.add_argument("--source", default=None, help="Einzelquelle (arXiv), z.B. source.research-ml")
    ap.add_argument("--arxiv-query", default="cat:cs.CL OR cat:cs.AI OR cat:cs.LG")
    ap.add_argument("--since", default="", help="YYYY-MM-DD: nur Items ab diesem Datum")
    ap.add_argument("--max-items", type=int, default=15, help="harter Deckel: max. Items JE Quelle")
    ap.add_argument("--max-output-tokens", type=int, default=20000, help="harter Deckel: Summe Output-Tokens")
    ap.add_argument("--max-cost-usd", type=float, default=0.0,
                    help="harter Kosten-Deckel in USD (braucht --price-in/--price-out); 0 = aus")
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

    # Quellen sind kuratiert (E6). Einzelmodus: arXiv-Query auf die gewählte Quelle;
    # --all-sources: jede Quelle mit einem `ingest`-Block (arxiv/feed).
    sources = collect(inst / "sources", "*.yaml", "sources")
    src_by_id = {s["id"]: s for s in sources}
    if args.all_sources:
        todo = [s for s in sources if s.get("ingest")]
        if not todo:
            sys.exit("Keine kuratierte Quelle hat einen ingest-Block.")
    else:
        if not args.source or args.source not in src_by_id:
            sys.exit(f"--source fehlt/ungültig (oder nutze --all-sources). Bekannt: {sorted(src_by_id)}")
        base = dict(src_by_id[args.source])
        base["ingest"] = {"type": "arxiv", "query": args.arxiv_query}
        todo = [base]

    items = []
    for s in todo:
        try:
            got = fetch_source(s, args.since, args.max_items,
                               args.source_file if not args.all_sources else None)
        except Exception as ex:                       # eine kaputte Quelle stoppt nicht alles
            print(f"  {s['id']}: Fehler beim Holen ({type(ex).__name__}: {str(ex)[:60]})")
            continue
        print(f"  {s['id']}: {len(got)} Items")
        items.extend(got)
    print(f"Geholt: {len(items)} Items aus {len(todo)} Quelle(n) (seit {args.since or 'Anfang'})")

    # Bekannte Branchen (domain-Taxonomie) — für Prompt UND Validierung der Zuordnung.
    domains = collect(CORE / "vocab-core", "domain.yaml", "terms")
    known_branchen = {t["id"] for t in domains}

    rubric = scope = ""
    if not args.dry_run:
        rub = inst / "agents" / "bewertungsraster.md"
        rubric = rub.read_text(encoding="utf-8") if rub.exists() else ""
        comps = collect(CORE / "vocab-core", "competence.yaml", "terms")
        ents = collect(inst / "entries", "entry.yaml", "entries")
        scope = ("Kontext:\nBRANCHEN (wähle daraus für 'branchen'):\n"
                 + "\n".join(f'  {t["id"]} — {t.get("label")}' for t in domains)
                 + "\nKompetenzen: " + ", ".join(t["id"] for t in comps)
                 + "\nBestehende Einträge: "
                 + ", ".join(f'{e["id"]} ({e.get("name")})' for e in ents))

    def running_cost() -> float:
        return (tok_in / 1e6) * args.price_in + (tok_out / 1e6) * args.price_out

    if args.max_cost_usd and not (args.price_in or args.price_out):
        print("Hinweis: --max-cost-usd ohne --price-in/--price-out unwirksam "
              "(Kosten unbekannt) — es greift nur der Token-Deckel.")

    cands, report_rows = [], []
    tok_in = tok_out = 0
    for i, it in enumerate(items, 1):
        if not args.dry_run and (i == 1 or i % 10 == 0):
            print(f"  … {i}/{len(items)} · {len(cands)} Kandidaten · {tok_out} out-Tok"
                  + (f" · ~${running_cost():.3f}" if (args.price_in or args.price_out) else ""),
                  flush=True)
        if not args.dry_run and tok_out >= args.max_output_tokens:
            report_rows.append(("—", it["title"][:60], "GESTOPPT (Token-Deckel)"))
            break
        if (not args.dry_run and args.max_cost_usd and (args.price_in or args.price_out)
                and running_cost() >= args.max_cost_usd):
            report_rows.append(("—", it["title"][:60], f"GESTOPPT (Kosten-Deckel ${args.max_cost_usd:.2f})"))
            break
        if args.dry_run:
            c = draft_dry(it, args.run_date)
            verdict = {"ai_related": True, "reason": "dry-run"}
        else:
            try:
                c, verdict, usage = draft_real(it, args.run_date, rubric,
                                               scope, args.model, 1024)
            except Exception as ex:  # ein Fehler darf den Lauf nicht abbrechen
                report_rows.append(("!", it["title"][:60], f"Fehler: {ex}"))
                continue
            tok_in += usage.get("input_tokens", 0)
            tok_out += usage.get("output_tokens", 0)
        if c:
            err = obs_ok(c["observation"])
            if err:
                report_rows.append(("✗", it["title"][:60], f"Entwurf ungültig: {err}"))
                continue
            # unbekannte Branchen aussortieren; leere → Querschnitt (nichts erfinden)
            c["branchen"] = [b for b in c["branchen"] if b in known_branchen] or ["domain.querschnitt-grundlagen"]
            cands.append(c)
            br = ", ".join(b.split(".", 1)[-1] for b in c["branchen"])
            report_rows.append(("✓", it["title"][:60],
                                f'[{br}] rel {c.get("relevance_general", "—")} → {c.get("suggested_entry") or "?"}'))
        else:
            report_rows.append(("·", it["title"][:60], f'kein KI-Bezug: {verdict.get("reason", "")[:50]}'))

    outdir.mkdir(parents=True, exist_ok=True)
    stamp = f"{args.run_date}-{'dry' if args.dry_run else slugify(args.model)}"
    if cands:
        obs_path = outdir / f"ingest-{stamp}.yaml"
        obs_path.write_text(yaml.safe_dump({"candidates": cands}, allow_unicode=True,
                                           sort_keys=False), encoding="utf-8")
    # Laufbericht: ehrliche Bilanz (Items, Entwürfe, Tokens, geschätzte Kosten).
    cost = (tok_in / 1e6) * args.price_in + (tok_out / 1e6) * args.price_out
    quellen = (", ".join(s["id"] for s in todo) if args.all_sources
               else f"{args.source} · Query: `{args.arxiv_query}`")
    lines = [f"# Ingestion-Lauf {stamp}", "",
             f"- Quellen: {quellen} · seit {args.since or 'Anfang'}",
             f"- Modus: {'DRY-RUN (kostenlos)' if args.dry_run else args.model}",
             f"- Items geholt: {len(items)} · Kandidaten: {len(cands)}",
             f"- Deckel: max_items {args.max_items}, max_output_tokens {args.max_output_tokens}",
             f"- Tokens: {tok_in} in / {tok_out} out"
             + (f" · geschätzte Kosten: ${cost:.4f}" if (args.price_in or args.price_out)
                else " · Kosten: Preise via --price-in/--price-out setzen"),
             "", "## Items", "", "| | Titel | Ergebnis |", "|--|--|--|"]
    lines += [f"| {a} | {b} | {c} |" for a, b, c in report_rows]
    (outdir / f"ingest-{stamp}-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Kandidaten: {len(cands)} → {outdir}")
    print(f"Tokens: {tok_in} in / {tok_out} out"
          + (f" · ~${cost:.4f}" if (args.price_in or args.price_out) else ""))
    print(f"Bericht: {outdir / f'ingest-{stamp}-report.md'}")
    print("Hinweis: Entwürfe liegen im Eingangskorb (status: inbox) — noch NICHT im Radar. "
          "Ratifikation durch den Menschen (E4) ist der nächste, getrennte Schritt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
