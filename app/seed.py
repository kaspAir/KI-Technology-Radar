"""seed.py — importiert den geteilten Pool (inbox/pool.yaml) in die Proposal-Tabelle.

  python -m app.seed ../KI-Technology-Radar-Instanz/inbox/pool.yaml

Dedup über url. Zwei Fallstricke, die hier bewusst behandelt werden:
1. `Proposal.url` ist VARCHAR(N) — MariaDB KÜRZT längere URLs beim Speichern still
   (Google-News-Links sind 400–500+ Zeichen). Der Dedup-Schlüssel muss deshalb
   derselbe gekürzte Wert sein, sonst versucht jeder Lauf dieselben Zeilen erneut
   und läuft in den Unique-Index (1062) — was früher den ganzen Import kippte.
2. MariaDB-Collations sind case-INsensitiv, Python-Vergleiche nicht -> Schlüssel
   zusätzlich kleinschreiben.
Zusätzlich: erst ein Sammel-Commit (schnell), bei Ablehnung zeilenweise nachziehen,
damit eine einzelne schlechte Zeile nie den ganzen nächtlichen Import verhindert.
"""
from __future__ import annotations

import sys

import yaml

from .db import Proposal, SessionLocal, init_db

URL_MAX = Proposal.__table__.c.url.type.length or 500


def _key(url: str) -> str:
    """Dedup-Schlüssel = genau das, was die DB speichert (gekürzt, case-insensitiv)."""
    return (url or "")[:URL_MAX].lower()


def run(pool_path: str) -> int:
    init_db()
    doc = yaml.safe_load(open(pool_path, encoding="utf-8")) or {}
    cands = doc.get("candidates", []) if isinstance(doc, dict) else []
    n_new = n_skip = 0
    with SessionLocal() as db:
        known = {_key(u) for (u,) in db.query(Proposal.url).all()}
        rows = []
        for c in cands:
            o = c.get("observation", {})
            url = (o.get("url") or "")[:URL_MAX]
            if not url or _key(url) in known:
                continue
            known.add(_key(url))
            rows.append(dict(
                url=url, title=(o.get("title") or "")[:300], summary=o.get("summary") or "",
                citation=o.get("citation") or "", source_id=(o.get("source_ids") or [""])[0],
                branchen=" ".join(b.split(".", 1)[-1] for b in (c.get("branchen") or [])),
                suggested_entry=c.get("suggested_entry") or "",
                relevance_general=c.get("relevance_general") or 0,
                date_published=str(o.get("date_published") or "")))

        if rows:
            db.add_all([Proposal(**r) for r in rows])
            try:
                db.commit()
                n_new = len(rows)
            except Exception:          # eine Zeile abgelehnt -> zeilenweise nachziehen
                db.rollback()
                for r in rows:
                    db.add(Proposal(**r))
                    try:
                        db.commit(); n_new += 1
                    except Exception:
                        db.rollback(); n_skip += 1

    msg = f"Seed: {n_new} neue Vorschläge importiert"
    if n_skip:
        msg += f", {n_skip} übersprungen (von der DB abgelehnt)"
    print(f"{msg} ({pool_path}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1] if len(sys.argv) > 1 else "pool.yaml"))
