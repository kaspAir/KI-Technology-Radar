"""main.py — Selbstbedienungs-Radar (MVP, mandantenfähig).

Hierarchie: Plattform-Admin -> Mandanten (Baum) -> Nutzer (Rolle admin|member|viewer).
Curation/Profile hängen am Mandanten (geteilt). Untermandanten erben das Profil des
Eltern-Mandanten als Vorgabe (effective_profile).

Start (Entwicklung):
  RADAR_ADMIN_EMAIL=du@x.ch RADAR_ADMIN_PW=... uvicorn app.main:app --reload
Umgebung: RADAR_DB, RADAR_SECRET, RADAR_INSTANCE, RADAR_ADMIN_EMAIL/PW (Bootstrap).
"""
from __future__ import annotations

import json
import os
import re
import secrets
from pathlib import Path
from urllib.parse import quote

import yaml
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from starlette.middleware.sessions import SessionMiddleware

from .db import (Curation, Profile, Proposal, ROLES, SessionLocal, Tenant, User,
                 init_db)
from .security import hash_pw, verify_pw

RINGS = ["Adopt", "Pilot", "Explore", "Watch", "Reject"]
HIDDEN = "—"  # Sentinel-Ring: ein Mandant blendet einen geerbten Blip aus
BASE = Path(__file__).resolve().parent
CORE_VIEW = BASE.parent / "view"
INSTANCE = Path(os.environ.get("RADAR_INSTANCE", str(BASE.parent.parent / "KI-Technology-Radar-Instanz")))
app = FastAPI(title="KI-Radar — Selbstbedienung")
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("RADAR_SECRET", "dev-only-change-me"))
templates = Jinja2Templates(directory=str(BASE / "templates"))


@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    """Liveness für den Keepalive-Watchdog (ohne Auth/DB — antwortet, solange der
    Prozess lebt)."""
    return "ok"

PROFILE_FIELDS = [
    ("§", "Identität & Mandat", None, None),
    ("name", "Name der Organisation", "text", None),
    ("typ", "Organisationstyp", "select", ["Behörde", "Kompetenzzentrum", "Verband-Mitglied", "KMU", "Grossunternehmen", "Andere"]),
    ("mandat", "Mandat / Auftrag", "textarea", None),
    ("groesse_reife", "Grösse & technische Reife", "text", None),
    ("§", "Strategische Ausrichtung", None, None),
    ("schwerpunkte", "Schwerpunkte / Fokusthemen", "list", None),
    ("aktuelle_branchen", "Aktuelle Branchen", "list", None),
    ("wunschbranchen", "Wunsch-/Zielbranchen", "list", None),
    ("nicht_ziele", "Bewusste Nicht-Ziele / Scope-Grenzen", "list", None),
    ("zeithorizont", "Zeithorizont", "select", ["operativ (≈1 Jahr)", "mittelfristig (2–3 Jahre)", "strategisch (5+ Jahre)"]),
    ("§", "Wertungs-Parameter (steuern die Empfehlungen)", None, None),
    ("risikofreudigkeit", "Risikofreudigkeit", "select", ["konservativ", "ausgewogen", "früh-adoptierend"]),
    ("souveraenitaet", "Souveränität / Datenresidenz-Priorität", "select", ["hoch", "mittel", "tief"]),
    ("compliance_strenge", "Compliance-/Governance-Strenge", "select", ["hoch", "mittel", "tief"]),
    ("make_vs_buy", "Make-vs-Buy-Neigung", "select", ["selbst aufbauen", "ausgewogen", "einkaufen"]),
    ("budget_rahmen", "Budget-/Investitionsrahmen (grob)", "text", None),
    ("§", "Ziele & Messung", None, None),
    ("kpis", "KPIs / Erfolgskriterien", "list", None),
    ("ziele", "Strategische Ziele (1–3)", "list", None),
    ("§", "Kompetenz-Kontext", None, None),
    ("staerken", "Vorhandene Stärken", "list", None),
    ("kompetenz_luecken", "Kompetenz-Lücken / Aufbau-Ziele", "list", None),
]


@app.on_event("startup")
def _startup():
    init_db()
    email = (os.environ.get("RADAR_ADMIN_EMAIL") or "").strip().lower()
    pw = os.environ.get("RADAR_ADMIN_PW") or ""
    if email and pw:
        with SessionLocal() as s:
            if not s.scalar(select(User).where(User.email == email)):
                s.add(User(email=email, pw=hash_pw(pw), is_platform_admin=True, tenant_id=None, role="admin"))
                try:
                    s.commit()
                except IntegrityError:
                    s.rollback()   # ein anderer Worker war schneller — ok


def db_session():
    with SessionLocal() as s:
        yield s


def current_user(request: Request, db=Depends(db_session)):
    uid = request.session.get("uid")
    return db.get(User, uid) if uid else None


def can_edit(u) -> bool:
    return bool(u and (u.is_platform_admin or u.role in ("admin", "member")))


def can_manage(u) -> bool:
    return bool(u and (u.is_platform_admin or u.role == "admin"))


def tenant_chain(db, tenant_id):
    """Kette Wurzel -> ... -> tenant_id (Liste von Tenant-Objekten)."""
    chain, t = [], db.get(Tenant, tenant_id)
    while t:
        chain.append(t)
        t = db.get(Tenant, t.parent_id) if t.parent_id else None
    chain.reverse()
    return chain


def effective_profile(db, tenant_id) -> dict:
    """Effektives Profil = Eltern-Vorgaben (Wurzel zuerst) mit eigenem überschrieben."""
    merged: dict = {}
    for t in tenant_chain(db, tenant_id):
        p = db.get(Profile, t.id)
        if p and p.data:
            for k, v in (json.loads(p.data) or {}).items():
                if v not in (None, "", [], {}):
                    merged[k] = v
    return merged


def reference_tenant_id(db):
    return db.scalar(select(Tenant.id).where(Tenant.is_reference == True))  # noqa: E712


def effective_curation(db, tenant_id):
    """Effektive Kuratierung eines Mandanten = Referenz-Grundstock ⊕ Eltern-Kette ⊕
    eigene Wertung. Nähere Schicht überschreibt per proposal_id; Ring '—' blendet aus.
    Rückgabe: Liste von dicts {prop, ring, origin, base_ring, has_own}:
      origin    reference|inherited|own (nächstliegende Quelle des sichtbaren Rings)
      base_ring geerbter Ring OHNE eigene Wertung (None = rein eigener Blip)
      has_own   True, wenn eine eigene Wertung (Override/Ausblenden/Aufnahme) existiert."""
    ref = reference_tenant_id(db)
    chain = tenant_chain(db, tenant_id)                       # Wurzel .. self
    base_layers = ([ref] if ref and ref != tenant_id else []) + [t.id for t in chain[:-1]]
    base = {}                                                 # pid -> (ring, origin)
    for tid in base_layers:
        origin = "reference" if tid == ref else "inherited"
        for cur in db.scalars(select(Curation).where(Curation.tenant_id == tid)):
            base[cur.proposal_id] = (cur.ring, origin)
    own = {cur.proposal_id: cur.ring
           for cur in db.scalars(select(Curation).where(Curation.tenant_id == tenant_id))}
    pids = set(base) | set(own)
    props = {p.id: p for p in db.scalars(select(Proposal).where(Proposal.id.in_(pids)))} if pids else {}
    out = []
    for pid in pids:
        p = props.get(pid)
        if not p:
            continue
        base_ring = base.get(pid, (None, None))[0]
        if pid in own:
            ring, origin = own[pid], "own"
        else:
            ring, origin = base[pid]
        if ring == HIDDEN:
            continue
        out.append({"prop": p, "ring": ring, "origin": origin,
                    "base_ring": base_ring, "has_own": pid in own})
    return out


# --- Auth -------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def root(request: Request, user=Depends(current_user)):
    if not user:
        return RedirectResponse("/login", 302)
    return RedirectResponse("/admin" if user.is_platform_admin else "/radar", 302)


@app.get("/signup", response_class=HTMLResponse)
def signup_form(request: Request, db=Depends(db_session)):
    # Offene Registrierung nur für den allerersten Nutzer (= Plattform-Admin).
    if db.scalar(select(User.id).limit(1)):
        return templates.TemplateResponse(request, "login.html",
            {"err": "Registrierung geschlossen — dein Administrator legt dich an."}, status_code=403)
    return templates.TemplateResponse(request, "signup.html", {"err": None})


@app.post("/signup")
def signup(request: Request, email: str = Form(...), pw: str = Form(...), db=Depends(db_session)):
    if db.scalar(select(User.id).limit(1)):
        return templates.TemplateResponse(request, "login.html",
            {"err": "Registrierung geschlossen."}, status_code=403)
    email = email.strip().lower()
    if not email or len(pw) < 8:
        return templates.TemplateResponse(request, "signup.html",
            {"err": "E-Mail nötig, Passwort mind. 8 Zeichen."}, status_code=400)
    u = User(email=email, pw=hash_pw(pw), is_platform_admin=True, tenant_id=None, role="admin")
    db.add(u); db.commit()
    request.session["uid"] = u.id
    return RedirectResponse("/admin", 302)


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {"err": None})


@app.post("/login")
def login(request: Request, email: str = Form(...), pw: str = Form(...), db=Depends(db_session)):
    u = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not u or not verify_pw(pw, u.pw):
        return templates.TemplateResponse(request, "login.html",
            {"err": "E-Mail oder Passwort falsch."}, status_code=401)
    request.session["uid"] = u.id
    return RedirectResponse("/admin" if u.is_platform_admin else "/radar", 302)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", 302)


@app.get("/passwort", response_class=HTMLResponse)
def passwort_form(request: Request, saved: int = 0, user=Depends(current_user), db=Depends(db_session)):
    if not user:
        return RedirectResponse("/login", 302)
    return templates.TemplateResponse(request, "passwort.html",
        {**_nav(user, db), "active": "passwort", "saved": bool(saved), "err": None})


@app.post("/passwort")
def passwort_change(request: Request, current: str = Form(...), new: str = Form(...),
                    confirm: str = Form(...), user=Depends(current_user), db=Depends(db_session)):
    """Eigenes Passwort ändern (Selbstbedienung, jede Rolle)."""
    if not user:
        return RedirectResponse("/login", 302)

    def err(msg):
        return templates.TemplateResponse(request, "passwort.html",
            {**_nav(user, db), "active": "passwort", "saved": False, "err": msg}, status_code=400)

    if not verify_pw(current, user.pw):
        return err("Aktuelles Passwort stimmt nicht.")
    if len(new) < 8:
        return err("Neues Passwort braucht mindestens 8 Zeichen.")
    if new != confirm:
        return err("Die beiden neuen Passwörter stimmen nicht überein.")
    user.pw = hash_pw(new)
    db.commit()
    return RedirectResponse("/passwort?saved=1", 303)


def _nav(user, db):
    """Kontext für die Navigation (Rolle/Mandant)."""
    tenant = db.get(Tenant, user.tenant_id) if user and user.tenant_id else None
    return {"user": user, "tenant": tenant, "can_edit": can_edit(user), "can_manage": can_manage(user)}


# --- Plattform-Admin: Mandanten verwalten -----------------------------------
@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request, user=Depends(current_user), db=Depends(db_session)):
    if not user:
        return RedirectResponse("/login", 302)
    if not user.is_platform_admin:
        return RedirectResponse("/radar", 302)
    tenants = [t for t in db.scalars(select(Tenant).order_by(
        Tenant.parent_id.is_(None).desc(), Tenant.name)).all() if not t.is_reference]
    users = db.scalars(select(User)).all()
    ucount = {}
    for u in users:
        ucount[u.tenant_id] = ucount.get(u.tenant_id, 0) + 1
    ref_id = reference_tenant_id(db)
    n_ref = db.scalar(select(func.count()).select_from(Curation).where(
        Curation.tenant_id == ref_id)) if ref_id else 0
    n_pool = db.scalar(select(func.count()).select_from(Proposal)) or 0
    return templates.TemplateResponse(request, "admin.html",
        {**_nav(user, db), "active": "admin", "tenants": tenants, "ucount": ucount,
         "n_ref": n_ref or 0, "n_pool": n_pool})


@app.post("/admin/tenant")
def admin_create_tenant(request: Request, name: str = Form(...), admin_email: str = Form(...),
                        admin_pw: str = Form(...), user=Depends(current_user), db=Depends(db_session)):
    if not user or not user.is_platform_admin:
        return RedirectResponse("/login", 302)
    name = name.strip()
    admin_email = admin_email.strip().lower()
    if not name or not admin_email or len(admin_pw) < 8:
        return RedirectResponse("/admin?err=1", 303)
    if db.scalar(select(User).where(User.email == admin_email)):
        return RedirectResponse("/admin?err=mail", 303)
    t = Tenant(name=name, parent_id=None)
    db.add(t); db.flush()
    db.add(User(email=admin_email, pw=hash_pw(admin_pw), tenant_id=t.id, role="admin"))
    db.commit()
    return RedirectResponse("/admin?ok=1", 303)


@app.post("/admin/seed-reference")
def admin_seed_reference(request: Request, user=Depends(current_user), db=Depends(db_session)):
    """Referenz-Grundstock (Einträge ab 2017) aus der Instanz einlesen — erbt jeder Mandant."""
    if not user or not user.is_platform_admin:
        return RedirectResponse("/login", 302)
    from .seed_reference import run as seed_ref
    try:
        seed_ref(str(INSTANCE))
        return RedirectResponse("/admin?ok=ref", 303)
    except Exception:
        return RedirectResponse("/admin?err=ref", 303)


@app.post("/admin/seed-pool")
def admin_seed_pool(request: Request, user=Depends(current_user), db=Depends(db_session)):
    """Geteilten Vorschläge-Pool aus der Instanz-pool.yaml einlesen."""
    if not user or not user.is_platform_admin:
        return RedirectResponse("/login", 302)
    from .seed import run as seed_pool
    pool = INSTANCE / "inbox" / "pool.yaml"
    if not pool.exists():
        return RedirectResponse("/admin?err=pool", 303)
    try:
        seed_pool(str(pool))
        return RedirectResponse("/admin?ok=pool", 303)
    except Exception:
        return RedirectResponse("/admin?err=pool", 303)


# --- Mandanten-Admin: Team + Untermandanten ---------------------------------
@app.get("/team", response_class=HTMLResponse)
def team(request: Request, user=Depends(current_user), db=Depends(db_session)):
    if not user:
        return RedirectResponse("/login", 302)
    if not user.tenant_id or not can_manage(user):
        return RedirectResponse("/radar", 302)
    members = db.scalars(select(User).where(User.tenant_id == user.tenant_id).order_by(User.email)).all()
    subs = db.scalars(select(Tenant).where(Tenant.parent_id == user.tenant_id).order_by(Tenant.name)).all()
    submembers = {s.id: db.scalars(select(User).where(User.tenant_id == s.id)).all() for s in subs}
    return templates.TemplateResponse(request, "team.html",
        {**_nav(user, db), "active": "team", "members": members, "subs": subs,
         "submembers": submembers, "roles": ROLES})


@app.post("/team/user")
def team_add_user(request: Request, email: str = Form(...), role: str = Form("member"),
                  pw: str = Form(...), tenant_id: int = Form(None),
                  user=Depends(current_user), db=Depends(db_session)):
    if not user or not can_manage(user):
        return RedirectResponse("/login", 302)
    # in eigenen Mandanten oder einen eigenen Untermandanten
    tid = tenant_id or user.tenant_id
    allowed = {user.tenant_id} | {s.id for s in db.scalars(select(Tenant).where(Tenant.parent_id == user.tenant_id))}
    if tid not in allowed or role not in ROLES or len(pw) < 8:
        return RedirectResponse("/team?err=1", 303)
    email = email.strip().lower()
    if not email or db.scalar(select(User).where(User.email == email)):
        return RedirectResponse("/team?err=mail", 303)
    db.add(User(email=email, pw=hash_pw(pw), tenant_id=tid, role=role))
    db.commit()
    return RedirectResponse("/team?ok=1", 303)


@app.post("/team/subtenant")
def team_add_sub(request: Request, name: str = Form(...), user=Depends(current_user), db=Depends(db_session)):
    if not user or not can_manage(user) or not user.tenant_id:
        return RedirectResponse("/login", 302)
    name = name.strip()
    if name:
        db.add(Tenant(name=name, parent_id=user.tenant_id)); db.commit()
    return RedirectResponse("/team?ok=sub", 303)


@app.post("/team/user/remove")
def team_remove_user(request: Request, user_id: int = Form(...), user=Depends(current_user), db=Depends(db_session)):
    if not user or not can_manage(user):
        return RedirectResponse("/login", 302)
    target = db.get(User, user_id)
    allowed = {user.tenant_id} | {s.id for s in db.scalars(select(Tenant).where(Tenant.parent_id == user.tenant_id))}
    if target and target.id != user.id and target.tenant_id in allowed:
        db.delete(target); db.commit()
    return RedirectResponse("/team?ok=rm", 303)


# --- Vorschläge (geteilter Pool) + mein Radar (pro Mandant) ------------------
@app.get("/proposals", response_class=HTMLResponse)
def proposals(request: Request, b: str = "", user=Depends(current_user), db=Depends(db_session)):
    if not user:
        return RedirectResponse("/login", 302)
    if not user.tenant_id:
        return RedirectResponse("/admin", 302)
    mine = {d["prop"].id for d in effective_curation(db, user.tenant_id)}
    rows = db.scalars(select(Proposal).order_by(Proposal.relevance_general.desc(), Proposal.id.desc())).all()
    open_rows = [p for p in rows if p.id not in mine and (not b or b in p.branchen.split())]
    branchen = sorted({x for p in rows if p.id not in mine for x in p.branchen.split() if x})
    return templates.TemplateResponse(request, "proposals.html", {
        **_nav(user, db), "active": "proposals", "rows": open_rows[:200], "branchen": branchen,
        "sel": b, "rings": RINGS[:4], "total_open": len([p for p in rows if p.id not in mine])})


@app.post("/add")
def add(request: Request, proposal_id: int = Form(...), ring: str = Form("Watch"),
        b: str = Form(""), user=Depends(current_user), db=Depends(db_session)):
    target = "/proposals" + (f"?b={quote(b)}" if b else "")   # Branchen-Filter behalten
    if not can_edit(user) or not user.tenant_id:
        return RedirectResponse(target, 303)
    if ring not in RINGS:
        ring = "Watch"
    if not db.scalar(select(Curation).where(Curation.tenant_id == user.tenant_id, Curation.proposal_id == proposal_id)):
        db.add(Curation(tenant_id=user.tenant_id, proposal_id=proposal_id, ring=ring)); db.commit()
    return RedirectResponse(target, 303)


@app.post("/remove")
def remove(request: Request, proposal_id: int = Form(...), user=Depends(current_user), db=Depends(db_session)):
    """Entfernt die EIGENE Wertung eines Blips (geerbte Referenz-Blips bleiben)."""
    if not can_edit(user):
        return RedirectResponse("/radar", 303)
    c = db.scalar(select(Curation).where(Curation.tenant_id == user.tenant_id,
                                         Curation.proposal_id == proposal_id))
    if c:
        db.delete(c); db.commit()
    return RedirectResponse("/radar", 303)


@app.post("/override")
def override(request: Request, proposal_id: int = Form(...), ring: str = Form(...),
            user=Depends(current_user), db=Depends(db_session)):
    """Eigene Wertung eines Blips setzen/ändern: ring in RINGS = anpassen (überschreibt
    geerbte Referenz), ring == '—' = geerbten Blip ausblenden."""
    if not can_edit(user) or not user.tenant_id:
        return RedirectResponse("/radar", 303)
    if ring not in RINGS and ring != HIDDEN:
        return RedirectResponse("/radar", 303)
    c = db.scalar(select(Curation).where(Curation.tenant_id == user.tenant_id,
                                         Curation.proposal_id == proposal_id))
    if c:
        c.ring = ring
    else:
        db.add(Curation(tenant_id=user.tenant_id, proposal_id=proposal_id, ring=ring))
    db.commit()
    return RedirectResponse("/radar", 303)


def _sectors_and_areamap():
    core = BASE.parent
    areas = []
    af = core / "vocab-core" / "area.yaml"
    if af.exists():
        for t in (yaml.safe_load(af.read_text(encoding="utf-8")) or {}).get("terms", []):
            if not t.get("parent_id"):
                areas.append((t["id"], t.get("label", t["id"])))
    n = len(areas) or 1
    sectors = [{"id": a, "label": lbl, "angle": -90 + i * (360 / n)} for i, (a, lbl) in enumerate(areas)]
    amap = {}
    edir = INSTANCE / "entries"
    if edir.exists():
        for ey in edir.glob("*/entry.yaml"):
            e = yaml.safe_load(ey.read_text(encoding="utf-8")) or {}
            area = e.get("area", "")
            amap[e.get("id", "")] = ".".join(area.split(".")[:2]) if area.count(".") >= 1 else area
    return sectors, amap


def _domain_labels():
    """{Branche-Suffix -> Label} aus vocab-core/domain.yaml (z.B. 'gesundheit'->'Gesundheit')."""
    core = BASE.parent
    labels = {}
    df = core / "vocab-core" / "domain.yaml"
    if df.exists():
        for t in (yaml.safe_load(df.read_text(encoding="utf-8")) or {}).get("terms", []):
            labels[t["id"].split(".", 1)[-1]] = t.get("label", t["id"])
    return labels


PLABEL = {"openai": "OpenAI", "anthropic": "Anthropic", "google": "Google",
          "microsoft": "Microsoft", "meta": "Meta", "deepseek": "DeepSeek",
          "nvidia": "Nvidia", "open": "Offen (Hedge)"}


@app.get("/radar", response_class=HTMLResponse)
def radar(request: Request, user=Depends(current_user), db=Depends(db_session)):
    if not user:
        return RedirectResponse("/login", 302)
    if not user.tenant_id:
        return RedirectResponse("/admin", 302)
    eff = effective_curation(db, user.tenant_id)      # dicts {prop,ring,origin,base_ring,has_own}
    by_ring = {r: [] for r in RINGS}
    for d in eff:
        by_ring.setdefault(d["ring"], []).append(d)
    sectors, amap = _sectors_and_areamap()
    sector_ids = [s["id"] for s in sectors]
    fallback = sector_ids[0] if sector_ids else "area.x"
    dom_labels = _domain_labels()
    dom_count, prov_count = {}, {}
    themes = []
    for d in eff:
        prop = d["prop"]
        sec = amap.get(prop.suggested_entry or "", "") or fallback
        if sec not in sector_ids:
            sec = fallback
        themes.append({"id": str(prop.id), "name": prop.title, "ring": d["ring"],
                       "sector": sec, "href": "#", "dom": prop.branchen or "",
                       "prov": prop.providers or "", "dep": prop.provider_dependency or ""})
        for br in (prop.branchen or "").split():
            dom_count[br] = dom_count.get(br, 0) + 1
        for pr in (prop.providers or "").split():
            prov_count[pr] = prov_count.get(pr, 0) + 1
    branches = [{"value": b, "label": dom_labels.get(b, b.replace("-", " ").title()), "n": n}
                for b, n in sorted(dom_count.items(), key=lambda kv: dom_labels.get(kv[0], kv[0]))]
    provs = [{"value": p, "label": PLABEL.get(p, p), "n": n}
             for p, n in sorted(prov_count.items(), key=lambda kv: -kv[1])]
    n_own = sum(1 for d in eff if d["origin"] == "own")
    n_ref = sum(1 for d in eff if d["origin"] != "own")
    hidden_blips = [db.get(Proposal, c.proposal_id) for c in db.scalars(
        select(Curation).where(Curation.tenant_id == user.tenant_id, Curation.ring == HIDDEN))]
    hidden_blips = [p for p in hidden_blips if p]
    import sys as _sys
    if str(CORE_VIEW) not in _sys.path:
        _sys.path.insert(0, str(CORE_VIEW))
    try:
        from radar_js import RADAR_JS
    except Exception:
        RADAR_JS = ""
    return templates.TemplateResponse(request, "radar.html", {
        **_nav(user, db), "active": "radar", "by_ring": by_ring, "rings": RINGS, "n": len(eff),
        "n_own": n_own, "n_ref": n_ref, "hidden_blips": hidden_blips,
        "branches": branches, "provs": provs,
        "themes_json": json.dumps(themes, ensure_ascii=False),
        "sectors_json": json.dumps(sectors, ensure_ascii=False), "radar_js": RADAR_JS})


# --- Mandanten-Profil (pro Mandant, mit Eltern-Vererbung) --------------------
@app.get("/profil", response_class=HTMLResponse)
def profil_form(request: Request, saved: int = 0, user=Depends(current_user), db=Depends(db_session)):
    if not user:
        return RedirectResponse("/login", 302)
    if not user.tenant_id:
        return RedirectResponse("/admin", 302)
    prof = db.get(Profile, user.tenant_id)
    data = json.loads(prof.data) if prof and prof.data else {}
    parent = db.get(Tenant, db.get(Tenant, user.tenant_id).parent_id) if db.get(Tenant, user.tenant_id).parent_id else None
    inherited = effective_profile(db, parent.id) if parent else {}
    vals = {}
    for key, label, typ, opt in PROFILE_FIELDS:
        if key == "§":
            continue
        v = data.get(key)
        vals[key] = ", ".join(str(x) for x in v) if isinstance(v, list) else (v or "")
    inh = {}
    for k, v in inherited.items():
        inh[k] = ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)
    return templates.TemplateResponse(request, "profil.html", {
        **_nav(user, db), "active": "profil", "fields": PROFILE_FIELDS, "vals": vals,
        "saved": bool(saved), "inherited": inh, "parent": parent})


@app.post("/profil")
async def save_profil(request: Request, user=Depends(current_user), db=Depends(db_session)):
    if not can_edit(user) or not user.tenant_id:
        return RedirectResponse("/login", 302)
    form = await request.form()
    data = {}
    for key, label, typ, opt in PROFILE_FIELDS:
        if key == "§":
            continue
        raw = (form.get(key) or "").strip()
        data[key] = [x.strip() for x in raw.split(",") if x.strip()] if typ == "list" else raw
    payload = json.dumps(data, ensure_ascii=False)
    prof = db.get(Profile, user.tenant_id)
    if prof:
        prof.data = payload
    else:
        db.add(Profile(tenant_id=user.tenant_id, data=payload))
    db.commit()
    return RedirectResponse("/profil?saved=1", 303)


# --- Lagebild: live aus dem EFFEKTIVEN Profil (inkl. Eltern-Vorgaben) --------
@app.get("/lagebild", response_class=HTMLResponse)
def lagebild_view(request: Request, user=Depends(current_user), db=Depends(db_session)):
    if not user:
        return RedirectResponse("/login", 302)
    if not user.tenant_id:
        return RedirectResponse("/admin", 302)
    data = effective_profile(db, user.tenant_id)
    import sys as _sys
    if str(CORE_VIEW) not in _sys.path:
        _sys.path.insert(0, str(CORE_VIEW))
    try:
        from lagebild import render_lagebild
        html = render_lagebild(INSTANCE, data)
        html = (html.replace('href="profil.html"', 'href="/profil"')
                    .replace('href="index.html"', 'href="/radar"')
                    .replace('href="bericht.html"', 'href="/radar"')
                    .replace('href="markt.html"', 'href="/markt"')
                    .replace('href="kandidaten.html"', 'href="/proposals"'))
        html = re.sub(r'href="detail[^"]*\.html"', 'href="#" onclick="return false"', html)
    except Exception as e:
        html = ("<div style='max-width:720px;margin:40px auto;font-family:system-ui'>"
                f"<p>Lagebild derzeit nicht verfügbar: {e}</p><p><a href='/profil'>← Profil</a></p></div>")
    return HTMLResponse(html)


@app.get("/markt", response_class=HTMLResponse)
def markt_view(request: Request, user=Depends(current_user), db=Depends(db_session)):
    """KI-Markt & Anbieter (Tendenzen + Makro-Indikatoren) — geteilte Marktsicht."""
    if not user:
        return RedirectResponse("/login", 302)
    if not user.tenant_id:
        return RedirectResponse("/admin", 302)
    import sys as _sys
    if str(CORE_VIEW) not in _sys.path:
        _sys.path.insert(0, str(CORE_VIEW))
    try:
        from marktsite import render_markt
        html = render_markt(INSTANCE)
        html = html.replace('href="index.html"', 'href="/radar"')
        html = re.sub(r'href="detail-[^"]*\.html"', 'href="#" onclick="return false"', html)
    except Exception as e:
        html = ("<div style='max-width:720px;margin:40px auto;font-family:system-ui'>"
                f"<p>Marktsicht derzeit nicht verfügbar: {e}</p><p><a href='/radar'>← Radar</a></p></div>")
    return HTMLResponse(html)
