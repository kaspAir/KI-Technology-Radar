"""seed.py — importiert den geteilten Pool (inbox/pool.yaml) in die Proposal-Tabelle.

  python -m app.seed ../KI-Technology-Radar-Instanz/inbox/pool.yaml

Dedup über url (Upsert). Später schreibt die Ingestion direkt in die DB; fürs MVP
seeden wir aus der bestehenden pool.yaml.
"""
from __future__ import annotations

import sys

import yaml

from .db import Proposal, SessionLocal, init_db


def run(pool_path: str) -> int:
    init_db()
    doc = yaml.safe_load(open(pool_path, encoding="utf-8")) or {}
    cands = doc.get("candidates", []) if isinstance(doc, dict) else []
    n_new = 0
    with SessionLocal() as db:
        known = {u for (u,) in db.query(Proposal.url).all()}
        for c in cands:
            o = c.get("observation", {})
            url = o.get("url")
            if not url or url in known:
                continue
            known.add(url)
            db.add(Proposal(
                url=url, title=(o.get("title") or "")[:300], summary=o.get("summary") or "",
                citation=o.get("citation") or "", source_id=(o.get("source_ids") or [""])[0],
                branchen=" ".join(b.split(".", 1)[-1] for b in (c.get("branchen") or [])),
                suggested_entry=c.get("suggested_entry") or "",
                relevance_general=c.get("relevance_general") or 0,
                date_published=str(o.get("date_published") or "")))
            n_new += 1
        db.commit()
    print(f"Seed: {n_new} neue Vorschläge importiert ({pool_path}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1] if len(sys.argv) > 1 else "pool.yaml"))
