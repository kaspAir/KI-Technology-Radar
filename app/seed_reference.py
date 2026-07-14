"""seed_reference.py — baut den geteilten Referenz-Radar (Grundstock ab 2017).

  python -m app.seed_reference ../KI-Technology-Radar-Instanz

Liest die ratifizierten Einträge der Referenz-Instanz (entries/*/entry.yaml) und legt
sie als Proposals + Curations unter dem EINEN Referenz-Mandanten (is_reference) ab.
Jeder echte Mandant erbt diesen Grundstock (effective_curation) und kann ihn pro
Blip überschreiben. Idempotent (Upsert über url bzw. (tenant_id, proposal_id)).
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

from .db import Curation, CurationEvent, Proposal, SessionLocal, Tenant, init_db

REFERENCE_NAME = "Referenz-Radar (Grundstock ab 2017)"
RINGS = {"Adopt", "Pilot", "Explore", "Watch", "Reject"}


def get_or_create_reference(db) -> Tenant:
    t = db.query(Tenant).filter(Tenant.is_reference == True).first()  # noqa: E712
    if not t:
        t = Tenant(name=REFERENCE_NAME, parent_id=None, is_reference=True)
        db.add(t); db.flush()
    return t


def run(instance_path: str) -> int:
    init_db()
    inst = Path(instance_path)
    edir = inst / "entries"
    if not edir.exists():
        print(f"Keine entries/ unter {inst} gefunden.")
        return 1
    n_new = n_ring = n_ev = 0
    with SessionLocal() as db:
        ref = get_or_create_reference(db)
        # Historie idempotent neu aufbauen: alte Referenz-Events verwerfen.
        db.query(CurationEvent).filter(CurationEvent.tenant_id == ref.id).delete()
        for ey in sorted(edir.glob("*/entry.yaml")):
            e = yaml.safe_load(ey.read_text(encoding="utf-8")) or {}
            eid = e.get("id", "")
            ring = str(e.get("current_ring") or "Watch")
            if ring not in RINGS or not eid:
                continue
            url = f"entry:{eid}"
            branchen = " ".join(d.split(".", 1)[-1] for d in (e.get("domains") or []))
            providers = " ".join(e.get("providers") or [])
            dep = str(e.get("provider_dependency") or "")
            p = db.query(Proposal).filter(Proposal.url == url).first()
            if not p:
                p = Proposal(url=url, title=e.get("name") or eid, summary="",
                             citation="", source_id="referenz",
                             branchen=branchen, suggested_entry=eid,
                             relevance_general=0, date_published=str(e.get("first_seen") or ""),
                             providers=providers, provider_dependency=dep)
                db.add(p); db.flush(); n_new += 1
            else:
                p.title = e.get("name") or eid
                p.branchen = branchen
                p.suggested_entry = eid
                p.date_published = str(e.get("first_seen") or "")
                p.providers = providers
                p.provider_dependency = dep
            c = db.query(Curation).filter(Curation.tenant_id == ref.id,
                                          Curation.proposal_id == p.id).first()
            if not c:
                db.add(Curation(tenant_id=ref.id, proposal_id=p.id, ring=ring)); n_ring += 1
            else:
                c.ring = ring
            # Historie: jedes Assessment (ring + valid_from) als Event importieren.
            af = ey.parent / "assessments.yaml"
            seen_hist = False
            if af.exists():
                for a in (yaml.safe_load(af.read_text(encoding="utf-8")) or {}).get("assessments", []):
                    r = str(a.get("ring") or "")
                    at = str(a.get("valid_from") or "")[:10]
                    if r in RINGS and at:
                        db.add(CurationEvent(tenant_id=ref.id, proposal_id=p.id, ring=r,
                                             at=at, actor=str(a.get("reviewer") or "mensch:backfill")))
                        n_ev += 1; seen_hist = True
            if not seen_hist:   # kein Assessment-Verlauf -> wenigstens den aktuellen Stand ab first_seen
                db.add(CurationEvent(tenant_id=ref.id, proposal_id=p.id, ring=ring,
                                     at=str(e.get("first_seen") or "2017-01-01")[:10], actor="mensch:backfill"))
                n_ev += 1
        db.commit()
    print(f"Referenz-Radar: {n_new} neue Blips importiert, {n_ring} Ring-Zuordnungen, {n_ev} Historien-Events ({inst}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1] if len(sys.argv) > 1 else "../KI-Technology-Radar-Instanz"))
