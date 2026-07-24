"""main.py — Selbstbedienungs-Radar (MVP, mandantenfähig).

Hierarchie: Plattform-Admin -> Mandanten (Baum) -> Nutzer (Rolle admin|member|viewer).
Curation/Profile hängen am Mandanten (geteilt). Untermandanten erben das Profil des
Eltern-Mandanten als Vorgabe (effective_profile).

Start (Entwicklung):
  RADAR_ADMIN_EMAIL=du@x.ch RADAR_ADMIN_PW=... uvicorn app.main:app --reload
Umgebung: RADAR_DB, RADAR_SECRET, RADAR_INSTANCE, RADAR_ADMIN_EMAIL/PW (Bootstrap).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import html as _html
import json
import os
import re
import secrets
from pathlib import Path
from urllib.parse import quote

import yaml
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import (HTMLResponse, JSONResponse, PlainTextResponse,
                               RedirectResponse)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from starlette.middleware.sessions import SessionMiddleware

from .db import (ChatAttachment, ChatMessage, Curation, CurationEvent, Profile,
                 ProfileDraft, Proposal, ROLES, SessionLocal, Tenant, User, init_db)
from .security import hash_pw, verify_pw

RINGS = ["Adopt", "Pilot", "Explore", "Watch", "Reject"]
HIDDEN = "—"  # Sentinel-Ring: ein Mandant blendet einen geerbten Blip aus
BASE = Path(__file__).resolve().parent
CORE_VIEW = BASE.parent / "view"
INSTANCE = Path(os.environ.get("RADAR_INSTANCE", str(BASE.parent.parent / "KI-Technology-Radar-Instanz")))
app = FastAPI(title="KI-Radar — Selbstbedienung")
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("RADAR_SECRET", "dev-only-change-me"))
templates = Jinja2Templates(directory=str(BASE / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    """Liveness für den Keepalive-Watchdog (ohne Auth/DB — antwortet, solange der
    Prozess lebt). Gibt den laufenden Commit mit aus, damit ohne Rätselraten
    erkennbar ist, WELCHER Stand gerade bedient wird."""
    return f"ok {_running_commit()}"


def _running_commit() -> str:
    """Kurz-Id des ausgecheckten Commits, direkt aus .git gelesen (kein Build-Schritt)."""
    try:
        root = Path(__file__).resolve().parent.parent / ".git"
        head = (root / "HEAD").read_text().strip()
        if head.startswith("ref: "):
            head = (root / head[5:]).read_text().strip()
        return head[:8]
    except Exception:
        return "unbekannt"

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


def _profile_schema() -> dict:
    """JSON-Schema für die Profil-Extraktion aus dem Erstgespräch. Alle Felder optional
    (nur füllen, was im Gespräch wirklich vorkam); Auswahlfelder als enum."""
    props = {}
    for key, label, typ, opt in PROFILE_FIELDS:
        if key == "§":
            continue
        if typ == "list":
            props[key] = {"type": "array", "items": {"type": "string"}, "description": label}
        elif typ == "select" and opt:
            props[key] = {"type": "string", "enum": opt, "description": label}
        else:
            props[key] = {"type": "string", "description": label}
    return {"type": "object", "properties": props}


def _felder_text() -> str:
    """Feld-Übersicht für den Interview-Prompt (nach Abschnitten, mit Auswahloptionen)."""
    lines = []
    for key, label, typ, opt in PROFILE_FIELDS:
        if key == "§":
            lines.append(f"\n{label}:")
        elif typ == "select" and opt:
            lines.append(f"- {label} (z.B. {', '.join(opt)})")
        else:
            lines.append(f"- {label}")
    return "\n".join(lines)


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


def _asof_ring_by_layer(db, tenant_id, as_of):
    """{proposal_id -> ring} für EINE Mandanten-Ebene: jüngstes Event mit at<=as_of."""
    rows = db.execute(
        select(CurationEvent.proposal_id, CurationEvent.ring)
        .where(CurationEvent.tenant_id == tenant_id, CurationEvent.at <= as_of)
        .order_by(CurationEvent.at, CurationEvent.id)).all()
    latest = {}
    for pid, ring in rows:      # aufsteigend sortiert -> letzte Zuweisung je pid gewinnt
        latest[pid] = ring
    return latest


def effective_curation_asof(db, tenant_id, as_of):
    """Wie effective_curation, aber Stand zum Datum as_of (aus der Ereignis-Historie)."""
    ref = reference_tenant_id(db)
    chain = tenant_chain(db, tenant_id)
    base_layers = ([ref] if ref and ref != tenant_id else []) + [t.id for t in chain[:-1]]
    base = {}
    for tid in base_layers:
        origin = "reference" if tid == ref else "inherited"
        for pid, ring in _asof_ring_by_layer(db, tid, as_of).items():
            base[pid] = (ring, origin)
    own = _asof_ring_by_layer(db, tenant_id, as_of)
    pids = set(base) | set(own)
    props = {p.id: p for p in db.scalars(select(Proposal).where(Proposal.id.in_(pids)))} if pids else {}
    out = []
    for pid in pids:
        p = props.get(pid)
        if not p:
            continue
        base_ring = base.get(pid, (None, None))[0]
        ring, origin = (own[pid], "own") if pid in own else base[pid]
        if ring not in RINGS:      # '' (entfernt) oder '—' (ausgeblendet) -> unsichtbar
            continue
        out.append({"prop": p, "ring": ring, "origin": origin,
                    "base_ring": base_ring, "has_own": pid in own})
    return out


def available_years(db, tenant_id):
    """Jahre mit Historie über Referenz + Eltern + eigene (für den Zeitpunkt-Wähler)."""
    ref = reference_tenant_id(db)
    tids = ([ref] if ref else []) + [t.id for t in tenant_chain(db, tenant_id)]
    ats = db.scalars(select(CurationEvent.at).where(CurationEvent.tenant_id.in_(tids))).all()
    return sorted({a[:4] for a in ats if a}, reverse=True)


def _log_curation_event(db, tenant_id, proposal_id, ring):
    """Eigene Wertungs-Änderung in die Historie schreiben (ring, '' = entfernt, '—' = aus)."""
    db.add(CurationEvent(tenant_id=tenant_id, proposal_id=proposal_id, ring=ring,
                         at=_dt.date.today().isoformat(), actor="mensch:mvp"))


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


def _inject_topbar(doc: str, nav: dict) -> str:
    """Fügt den (sticky) MVP-Menübalken in ein eigenständiges HTML-Dokument ein
    (Lagebild/Markt werden nicht über base.html gerendert)."""
    user, tenant = nav.get("user"), nav.get("tenant")
    if not user:
        return doc
    a = 'style="color:#23262D;text-decoration:none;font-size:14px"'
    links = [("/proposals", "Vorschläge"), ("/radar", "Mein Radar"), ("/profil", "Profil"),
             ("/lagebild", "Lagebild"), ("/markt", "Markt")]
    if nav.get("can_manage"):
        links.append(("/team", "Team"))
    items = "".join(f'<a href="{h}" {a}>{_html.escape(t)}</a>' for h, t in links)
    who = (f'<span style="font-size:12px;color:#8a867e">{_html.escape(tenant.name)} · '
           f'{_html.escape(user.role)}</span>') if tenant else ""
    bar = (
        '<header style="position:sticky;top:0;z-index:50;width:100vw;margin-left:calc(50% - 50vw);'
        'box-sizing:border-box;display:flex;gap:16px;align-items:baseline;flex-wrap:wrap;'
        'padding:12px 24px;background:#fff;border-bottom:1px solid #e7e3da;margin-bottom:22px;'
        'font-family:system-ui,-apple-system,sans-serif">'
        '<a href="/" style="display:flex;align-items:center;gap:15px;text-decoration:none">'
        '<img src="/static/radar-color.svg" alt="Radar" width="30" height="30" style="display:block">'
        '<span style="display:flex;flex-direction:column;line-height:1.08">'
        '<span style="font-size:10px;letter-spacing:.3em;text-transform:uppercase;color:#C0851F;'
        'font-weight:600">Aletheia</span>'
        '<span style="font-size:17px;font-weight:600;color:#23262D">Radar</span></span></a>'
        '<nav style="margin-left:auto;display:flex;gap:16px;align-items:baseline;flex-wrap:wrap">'
        + items + who
        + f'<span style="font-size:12px;color:#8a867e">{_html.escape(user.email)}</span>'
        f'<a href="/passwort" {a}>Passwort</a><a href="/logout" {a}>Abmelden</a></nav></header>')
    doc = doc.replace('</head>', '<link rel="icon" href="/static/radar-favicon.svg" type="image/svg+xml">'
                                 '<link rel="apple-touch-icon" href="/static/radar-tile.svg">'
                                 '<style>body{padding-top:0 !important}</style></head>', 1)
    m = re.search(r'<body[^>]*>', doc)
    if m:
        doc = doc[:m.end()] + bar + doc[m.end():]
    return doc


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
        db.add(Curation(tenant_id=user.tenant_id, proposal_id=proposal_id, ring=ring))
        _log_curation_event(db, user.tenant_id, proposal_id, ring)
        db.commit()
    return RedirectResponse(target, 303)


@app.post("/remove")
def remove(request: Request, proposal_id: int = Form(...), user=Depends(current_user), db=Depends(db_session)):
    """Entfernt die EIGENE Wertung eines Blips (geerbte Referenz-Blips bleiben)."""
    if not can_edit(user):
        return RedirectResponse("/radar", 303)
    c = db.scalar(select(Curation).where(Curation.tenant_id == user.tenant_id,
                                         Curation.proposal_id == proposal_id))
    if c:
        db.delete(c)
        _log_curation_event(db, user.tenant_id, proposal_id, "")   # entfernt
        db.commit()
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
    _log_curation_event(db, user.tenant_id, proposal_id, ring)
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
def radar(request: Request, as_of: str = "", user=Depends(current_user), db=Depends(db_session)):
    if not user:
        return RedirectResponse("/login", 302)
    if not user.tenant_id:
        return RedirectResponse("/admin", 302)
    years = available_years(db, user.tenant_id)
    historical = bool(as_of)
    eff = (effective_curation_asof(db, user.tenant_id, as_of) if historical
           else effective_curation(db, user.tenant_id))   # dicts {prop,ring,origin,base_ring,has_own}
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
                       "sector": sec, "href": f"/thema/{prop.id}", "dom": prop.branchen or "",
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
        "branches": branches, "provs": provs, "years": years, "as_of": as_of,
        "historical": historical,
        "themes_json": json.dumps(themes, ensure_ascii=False),
        "sectors_json": json.dumps(sectors, ensure_ascii=False), "radar_js": RADAR_JS})


# --- Mandanten-Profil (pro Mandant, mit Eltern-Vererbung) --------------------
@app.get("/profil", response_class=HTMLResponse)
def profil_form(request: Request, saved: int = 0, entwurf: int = 0,
                user=Depends(current_user), db=Depends(db_session)):
    if not user:
        return RedirectResponse("/login", 302)
    if not user.tenant_id:
        return RedirectResponse("/admin", 302)
    prof = db.get(Profile, user.tenant_id)
    data = json.loads(prof.data) if prof and prof.data else {}
    # Entwurf aus dem Erstgespräch (E4): nur ANZEIGEN, wenn ausdrücklich aufgerufen
    # (?entwurf=1). Er überlagert leere Felder; gespeichert wird er erst durch den
    # Menschen. Vorhandene eigene Werte bleiben stehen (der Entwurf drängt sich nicht auf).
    draft_row = db.get(ProfileDraft, user.tenant_id)
    draft = json.loads(draft_row.data) if (entwurf and draft_row and draft_row.data) else {}
    draft_keys = set()
    if draft:
        merged = dict(data)
        for k, v in draft.items():
            if v in (None, "", [], {}):
                continue
            if data.get(k) in (None, "", [], {}):   # nur leere Felder füllen
                merged[k] = v
                draft_keys.add(k)
        data = merged
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
        "saved": bool(saved), "inherited": inh, "parent": parent,
        "entwurf": bool(draft), "draft_keys": draft_keys,
        # Entwurf zum Nachlesen/Neu-Vorschlagen anbieten, auch ohne ?entwurf=1
        "draft_available": draft_row is not None})


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
    # Speichern IST die Ratifizierung (E4): ein etwaiger Entwurf hat seinen Zweck erfüllt.
    draft = db.get(ProfileDraft, user.tenant_id)
    if draft:
        db.delete(draft)
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
    return HTMLResponse(_inject_topbar(html, _nav(user, db)))


@app.get("/thema/{pid}", response_class=HTMLResponse)
def thema(request: Request, pid: int, user=Depends(current_user), db=Depends(db_session)):
    """Beschreibungs-Seite eines Blips: volles Dossier für Grundstock-Einträge
    (aus der Instanz), schlanke Detailseite für aufgenommene Pool-Vorschläge."""
    if not user:
        return RedirectResponse("/login", 302)
    if not user.tenant_id:
        return RedirectResponse("/admin", 302)
    p = db.get(Proposal, pid)
    if not p:
        return HTMLResponse("<p>Thema nicht gefunden.</p>", status_code=404)
    if p.url.startswith("entry:"):
        import sys as _sys
        if str(CORE_VIEW) not in _sys.path:
            _sys.path.insert(0, str(CORE_VIEW))
        try:
            from detail import render_detail
            doc = render_detail(INSTANCE, p.url[len("entry:"):], internal=True)
        except Exception:
            doc = None
        if doc:
            doc = doc.replace('href="index.html"', 'href="/radar"')
            doc = re.sub(r'href="detail[a-z]*-[^"]*\.html"', 'href="#" onclick="return false"', doc)
            return HTMLResponse(_inject_topbar(doc, _nav(user, db)))
    return templates.TemplateResponse(request, "thema.html", {**_nav(user, db), "active": "radar", "p": p})


# --- Radar-Berater (geerdetes Strategiegespräch, pro Mandant) ----------------
def _chat_context(db, tenant_id, tenant_name):
    """Erdung: Profil (inkl. Vorgaben) + die gewählten Radar-Inhalte — sonst nichts."""
    from . import chat as _chat
    labels = {k: lbl for k, lbl, _t, _o in PROFILE_FIELDS if k != "§"}
    return _chat.build_context(tenant_name, effective_profile(db, tenant_id),
                               effective_curation(db, tenant_id), labels)


def _attachments_by_message(db, tenant_id):
    out = {}
    for a in db.scalars(select(ChatAttachment).where(ChatAttachment.tenant_id == tenant_id)
                        .order_by(ChatAttachment.id)):
        out.setdefault(a.message_id, []).append(a)
    return out


# Ein Platzhalter, der so lange offen ist, wurde von niemandem mehr beantwortet
# (Neustart, abgestürzter Worker). Er darf die Seite nicht ewig blockieren.
# Muss GRÖSSER sein als das Zeitlimit des Laufs selbst (chat.STREAM_TIMEOUT) — sonst
# erklären wir eine Antwort für verloren, die noch ganz normal geschrieben wird.
CHAT_STALE_SECONDS = int(os.environ.get("RADAR_CHAT_STALE_SECONDS", "1200"))
# Abstand, in dem der entstehende Antworttext zwischengespeichert wird.
CHAT_SAVE_EVERY = float(os.environ.get("RADAR_CHAT_SAVE_EVERY", "3"))


def _db_now(db):
    """Aktuelle Zeit AUS DER DATENBANK — nur so ist sie mit created vergleichbar
    (SQLite und MariaDB setzen created serverseitig, evtl. andere Zeitzone)."""
    now = db.scalar(select(func.now()))
    if isinstance(now, str):        # SQLite liefert 'YYYY-MM-DD HH:MM:SS'
        return _dt.datetime.strptime(now[:19], "%Y-%m-%d %H:%M:%S")
    return now


def _expire_stale(db, tenant_id) -> None:
    """Verwaiste Platzhalter ehrlich abschliessen statt endlos „denkt nach" zu zeigen."""
    open_ = db.scalars(select(ChatMessage).where(
        ChatMessage.tenant_id == tenant_id, ChatMessage.status == "pending")).all()
    if not open_:
        return
    now = _db_now(db)
    changed = False
    for m in open_:
        if m.created and (now - m.created).total_seconds() > CHAT_STALE_SECONDS:
            m.content = ("Diese Antwort ging verloren — vermutlich wurde der Dienst mitten im "
                         "Nachdenken neu gestartet. Bitte die Frage nochmals senden.")
            m.status = "error"
            changed = True
    if changed:
        db.commit()


def _pending_seconds(db, tenant_id) -> int:
    """Laufzeit des offenen Laufs in Sekunden (0 = nichts offen)."""
    m = db.scalars(select(ChatMessage).where(
        ChatMessage.tenant_id == tenant_id, ChatMessage.status == "pending")
        .order_by(ChatMessage.id.desc())).first()
    if not m or not m.created:
        return 0
    return max(0, int((_db_now(db) - m.created).total_seconds()))


def _last_done_id(db, tenant_id) -> int:
    """Id der jüngsten FERTIGEN Nachricht. Die Seite fragt damit „hat sich etwas
    getan?" — unabhängig davon, ob irgendwo noch ein Platzhalter offen steht."""
    # Achtung MariaDB: `status != 'pending'` ist bei NULL weder wahr noch falsch — solche
    # Zeilen fielen stillschweigend raus (Altbestand vor der Spalte). Darum ausdrücklich.
    return db.scalar(select(func.max(ChatMessage.id)).where(
        ChatMessage.tenant_id == tenant_id,
        ChatMessage.channel == "advisor",
        ChatMessage.archived == False,                 # noqa: E712
        or_(ChatMessage.status.is_(None), ChatMessage.status != "pending"))) or 0


def _chat_history(db, tenant_id):
    """Verlauf fürs Modell: Nachrichtentext + der extrahierte Text der Anhänge,
    klar als DOKUMENT gekennzeichnet (damit der Berater die Quelle benennen kann).
    Offene Platzhalter (pending) und gescheiterte Versuche (error) gehören nicht in
    den Verlauf — sie tragen nichts bei und würden den Berater nur verwirren."""
    atts = _attachments_by_message(db, tenant_id)
    hist, seen = [], set()
    for m in db.scalars(select(ChatMessage).where(ChatMessage.tenant_id == tenant_id,
                                                  ChatMessage.channel == "advisor",
                                                  ChatMessage.archived == False)  # noqa: E712
                        .order_by(ChatMessage.id)):
        if m.status in ("pending", "error"):
            continue
        content = m.content
        for a in atts.get(m.id, []):
            if not a.text:
                continue
            key = hashlib.sha256(a.text.encode("utf-8")).hexdigest()
            if key in seen:     # dasselbe Dokument nochmals hochgeladen -> nicht wiederholen
                content += (f"\n\n(Dokument {a.filename}: inhaltlich identisch mit einem "
                            "bereits weiter oben enthaltenen — Inhalt nicht wiederholt.)")
            else:
                seen.add(key)
                content += (f"\n\n--- DOKUMENT: {a.filename} ({a.kind}) ---\n"
                            f"{a.text}\n--- ENDE DOKUMENT ---")
        hist.append({"role": m.role, "content": content})
    return hist


@app.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request, user=Depends(current_user), db=Depends(db_session)):
    if not user:
        return RedirectResponse("/login", 302)
    if not user.tenant_id:
        return RedirectResponse("/admin", 302)
    from . import chat as _chat
    _expire_stale(db, user.tenant_id)
    msgs = db.scalars(select(ChatMessage).where(ChatMessage.tenant_id == user.tenant_id,
                                                ChatMessage.channel == "advisor",
                                                ChatMessage.archived == False)  # noqa: E712
                      .order_by(ChatMessage.id)).all()
    n_archived = db.scalar(select(func.count()).select_from(ChatMessage).where(
        ChatMessage.tenant_id == user.tenant_id, ChatMessage.channel == "advisor",
        ChatMessage.archived == True)) or 0  # noqa: E712
    kept, dropped = _chat.fit_history(_chat_history(db, user.tenant_id))
    return templates.TemplateResponse(request, "chat.html", {
        **_nav(user, db), "active": "chat", "msgs": msgs,
        "pending": any(m.status == "pending" for m in msgs),
        "last_done": _last_done_id(db, user.tenant_id), "commit": _running_commit(),
        # Wie lange läuft der offene Lauf WIRKLICH schon? Serverseitig gerechnet, damit
        # die Uhr beim Neuladen der Seite nicht auf null zurückspringt.
        "pending_secs": _pending_seconds(db, user.tenant_id),
        "ctx_chars": sum(len(m["content"]) for m in kept), "ctx_dropped": dropped,
        "ctx_budget": _chat.HISTORY_BUDGET, "n_archived": n_archived,
        "atts": _attachments_by_message(db, user.tenant_id),
        "has_profile": bool(effective_profile(db, user.tenant_id)),
        "n_blips": len(effective_curation(db, user.tenant_id))})


def _run_chat_answer(tenant_id: int, tenant_name: str, placeholder_id: int):
    """Läuft im Hintergrund (eigene DB-Sitzung) — die HTTP-Antwort ist längst raus."""
    import time
    from . import chat as _chat
    with SessionLocal() as db:
        last = [0.0]

        def _save_partial(text: str) -> None:
            """Zwischenstand sichern — höchstens alle paar Sekunden, damit die Datenbank
            nicht bei jedem Wort schreibt. So überlebt der Text einen Neustart."""
            if time.monotonic() - last[0] < CHAT_SAVE_EVERY:
                return
            last[0] = time.monotonic()
            m = db.get(ChatMessage, placeholder_id)
            if m and m.status == "pending":     # abgebrochen? dann nicht mehr schreiben
                m.content = text
                db.commit()

        def _save_think(chars: int) -> None:
            """Lebenszeichen, solange noch kein Antworttext da ist."""
            if time.monotonic() - last[0] < CHAT_SAVE_EVERY:
                return
            last[0] = time.monotonic()
            m = db.get(ChatMessage, placeholder_id)
            if m and m.status == "pending":
                m.progress = "denkt · {:,} Zeichen".format(chars).replace(",", "’")
                db.commit()

        try:
            answer = _chat.ask(_chat_context(db, tenant_id, tenant_name),
                               _chat_history(db, tenant_id),
                               on_text=_save_partial, on_think=_save_think)
            status = ""
        except Exception as e:      # unerwartet — der Platzhalter darf nicht hängen bleiben
            db.rollback()
            m = db.get(ChatMessage, placeholder_id)
            teil = (m.content if m else "") or ""
            answer = (f"Der Berater konnte nicht zu Ende antworten ({type(e).__name__}). "
                      "Bitte erneut versuchen.")
            if teil:    # schon geschriebener Text ist bezahlt — er bleibt erhalten
                answer = teil + "\n\n— — —\n" + answer
            status = "error"
        m = db.get(ChatMessage, placeholder_id)
        if m:
            m.content, m.status = answer, status
            db.commit()


@app.post("/chat")
async def chat_send(request: Request, background: BackgroundTasks, message: str = Form(""),
                    files: list[UploadFile] = File(default=[]),
                    user=Depends(current_user), db=Depends(db_session)):
    if not can_edit(user) or not user.tenant_id:
        return RedirectResponse("/chat", 303)
    from . import chat as _chat, extract as _extract
    uploads = [f for f in (files or []) if getattr(f, "filename", "")]
    text = (message or "").strip()
    if not text and not uploads:
        return RedirectResponse("/chat", 303)
    if not text:
        text = "(Dokument zur Durchsicht hochgeladen.)"

    tenant = db.get(Tenant, user.tenant_id)
    msg = ChatMessage(tenant_id=user.tenant_id, user_id=user.id, role="user", content=text)
    db.add(msg); db.flush()
    for f in uploads:
        kind, doc, note = _extract.extract(f.filename, await f.read())
        db.add(ChatAttachment(tenant_id=user.tenant_id, message_id=msg.id,
                              filename=f.filename[:255], kind=kind or "?",
                              note=note[:255], text=doc))
    # Platzhalter anlegen; die Antwort entsteht im HINTERGRUND, damit die
    # HTTP-Anfrage nicht auf das Modell wartet (sonst Timeout im Proxy).
    holder = ChatMessage(tenant_id=user.tenant_id, user_id=None, role="assistant",
                         content="", status="pending")
    db.add(holder); db.commit()
    background.add_task(_run_chat_answer, user.tenant_id,
                        tenant.name if tenant else "", holder.id)
    return RedirectResponse("/chat#neueste", 303)


@app.get("/chat/status")
def chat_status(request: Request, user=Depends(current_user), db=Depends(db_session)):
    """Winziger Endpunkt fürs Nachfragen der Seite.

    Entscheidend ist `done` = Id der jüngsten FERTIGEN Nachricht. Die Seite lädt neu,
    sobald sich diese Id ändert. Früher wartete sie darauf, dass NICHTS mehr offen ist —
    ein verwaister Platzhalter (Neustart mitten im Lauf) blockierte dann die fertige
    Antwort dauerhaft, bis der Anwender abbrach. Genau das darf nicht passieren.
    """
    if not user or not user.tenant_id:
        return JSONResponse({"pending": False, "done": 0})
    _expire_stale(db, user.tenant_id)
    n = db.scalar(select(func.count()).select_from(ChatMessage).where(
        ChatMessage.tenant_id == user.tenant_id, ChatMessage.status == "pending"))
    return JSONResponse({"pending": bool(n), "done": _last_done_id(db, user.tenant_id)},
                        headers={"Cache-Control": "no-store"})


@app.post("/chat/cancel")
def chat_cancel(request: Request, user=Depends(current_user), db=Depends(db_session)):
    """Warten aufgeben. Der Platzhalter wird NICHT gelöscht, sondern als gescheitert
    markiert: trifft die Antwort doch noch ein, schreibt der Hintergrundlauf sie
    hinein und sie erscheint — statt verloren zu gehen."""
    if not can_edit(user) or not user.tenant_id:
        return RedirectResponse("/chat", 303)
    db.query(ChatMessage).filter(ChatMessage.tenant_id == user.tenant_id,
                                 ChatMessage.status == "pending").update(
        {"status": "error",
         "content": "Abgebrochen. Falls die Antwort doch noch eintrifft, erscheint sie hier."})
    db.commit()
    return RedirectResponse("/chat", 303)


@app.post("/chat/reset")
def chat_reset(request: Request, user=Depends(current_user), db=Depends(db_session)):
    if not can_edit(user) or not user.tenant_id:
        return RedirectResponse("/chat", 303)
    # ARCHIVIEREN statt löschen — das alte Gespräch bleibt unter /chat/archiv lesbar.
    # Nur den Berater-Kanal, nicht das Erstgespräch (channel='onboarding').
    db.query(ChatMessage).filter(ChatMessage.tenant_id == user.tenant_id,
                                 ChatMessage.channel == "advisor",
                                 ChatMessage.archived == False).update(  # noqa: E712
        {"archived": True})
    db.commit()
    return RedirectResponse("/chat", 303)


@app.get("/chat/archiv", response_class=HTMLResponse)
def chat_archive(request: Request, user=Depends(current_user), db=Depends(db_session)):
    """Frühere Gespräche — nur lesen, nichts geht mehr verloren."""
    if not user:
        return RedirectResponse("/login", 302)
    if not user.tenant_id:
        return RedirectResponse("/admin", 302)
    msgs = db.scalars(select(ChatMessage).where(ChatMessage.tenant_id == user.tenant_id,
                                                ChatMessage.archived == True)  # noqa: E712
                      .order_by(ChatMessage.id)).all()
    return templates.TemplateResponse(request, "chat_archiv.html", {
        **_nav(user, db), "active": "chat", "msgs": msgs,
        "atts": _attachments_by_message(db, user.tenant_id)})


# ======================================================================================
# Erstgespräch (Onboarding): der neue Mandant REDET zuerst mit dem Berater; daraus wird
# ein Profil-Entwurf abgeleitet, den er im /profil-Formular ratifiziert (E4). Bewusst
# synchron — die Interview-Beiträge sind kurz, kein Streaming/Hintergrundlauf nötig.
# ======================================================================================

def _onboarding_history(db, tenant_id):
    """Verlauf des Erstgesprächs als [{role, content}] (channel='onboarding')."""
    return [{"role": m.role, "content": m.content}
            for m in db.scalars(select(ChatMessage).where(
                ChatMessage.tenant_id == tenant_id,
                ChatMessage.channel == "onboarding").order_by(ChatMessage.id))]


@app.get("/onboarding", response_class=HTMLResponse)
def onboarding_page(request: Request, err: str = "", user=Depends(current_user),
                    db=Depends(db_session)):
    if not user:
        return RedirectResponse("/login", 302)
    if not user.tenant_id:
        return RedirectResponse("/admin", 302)
    msgs = db.scalars(select(ChatMessage).where(
        ChatMessage.tenant_id == user.tenant_id,
        ChatMessage.channel == "onboarding").order_by(ChatMessage.id)).all()
    n_user = sum(1 for m in msgs if m.role == "user")
    return templates.TemplateResponse(request, "onboarding.html", {
        **_nav(user, db), "active": "onboarding", "msgs": msgs,
        "can_start": n_user >= 1, "has_draft": db.get(ProfileDraft, user.tenant_id) is not None,
        "has_profile": bool(effective_profile(db, user.tenant_id)), "err": err})


@app.post("/onboarding/senden")
def onboarding_send(request: Request, message: str = Form(""),
                    user=Depends(current_user), db=Depends(db_session)):
    if not can_edit(user) or not user.tenant_id:
        return RedirectResponse("/onboarding", 303)
    text = (message or "").strip()
    if not text:
        return RedirectResponse("/onboarding", 303)
    from . import chat as _chat
    db.add(ChatMessage(tenant_id=user.tenant_id, user_id=user.id, role="user",
                       channel="onboarding", content=text))
    db.commit()
    reply = _chat.interview(_onboarding_history(db, user.tenant_id), _felder_text())
    db.add(ChatMessage(tenant_id=user.tenant_id, user_id=None, role="assistant",
                       channel="onboarding", content=reply))
    db.commit()
    return RedirectResponse("/onboarding#neueste", 303)


@app.post("/onboarding/entwurf")
def onboarding_draft(request: Request, user=Depends(current_user), db=Depends(db_session)):
    """Aus dem Erstgespräch einen Profil-Entwurf ableiten (E4: KI entwirft). Er wird als
    ProfileDraft abgelegt und im /profil-Formular vorgeschlagen — ratifiziert wird beim
    Speichern durch den Menschen, nicht hier."""
    if not can_edit(user) or not user.tenant_id:
        return RedirectResponse("/onboarding", 303)
    from . import chat as _chat
    hist = _onboarding_history(db, user.tenant_id)
    if not any(m["role"] == "user" for m in hist):
        return RedirectResponse("/onboarding?err=leer", 303)
    data, err = _chat.extract_profile(hist, _profile_schema())
    if err or not data:
        return RedirectResponse("/onboarding?err=1", 303)
    # nur bekannte Felder, leere weglassen — der Entwurf soll ehrlich lückenhaft sein
    keys = {k for k, _l, _t, _o in PROFILE_FIELDS if k != "§"}
    clean = {k: v for k, v in data.items() if k in keys and v not in (None, "", [], {})}
    payload = json.dumps(clean, ensure_ascii=False)
    existing = db.get(ProfileDraft, user.tenant_id)
    if existing:
        existing.data = payload
    else:
        db.add(ProfileDraft(tenant_id=user.tenant_id, data=payload))
    db.commit()
    return RedirectResponse("/profil?entwurf=1", 303)


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
    return HTMLResponse(_inject_topbar(html, _nav(user, db)))
