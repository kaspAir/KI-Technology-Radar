"""main.py — Selbstbedienungs-Radar (MVP): Login → Vorschläge → mein Radar.

Start (Entwicklung):
  uvicorn app.main:app --reload
Umgebung: RADAR_DB (Default sqlite:///./radar.db), RADAR_SECRET (Session-Schlüssel).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from .db import Curation, Profile, Proposal, SessionLocal, User, init_db
from .security import hash_pw, verify_pw

RINGS = ["Adopt", "Pilot", "Explore", "Watch", "Reject"]

# Mandanten-Profil-Felder (E24). typ: text | textarea | select | list. "§" = Abschnitt.
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
BASE = Path(__file__).resolve().parent
CORE_VIEW = BASE.parent / "view"   # für die wiederverwendbare Lagebild-Logik
INSTANCE = Path(os.environ.get("RADAR_INSTANCE", str(BASE.parent.parent / "KI-Technology-Radar-Instanz")))
app = FastAPI(title="KI-Radar — Selbstbedienung")
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("RADAR_SECRET", "dev-only-change-me"))
templates = Jinja2Templates(directory=str(BASE / "templates"))


@app.on_event("startup")
def _startup():
    init_db()


def db_session():
    with SessionLocal() as s:
        yield s


def current_user(request: Request, db=Depends(db_session)):
    uid = request.session.get("uid")
    return db.get(User, uid) if uid else None


# --- Auth -------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def root(request: Request, user=Depends(current_user)):
    return RedirectResponse("/radar" if user else "/login", 302)


@app.get("/signup", response_class=HTMLResponse)
def signup_form(request: Request):
    return templates.TemplateResponse(request, "signup.html", {"err": None})


@app.post("/signup")
def signup(request: Request, email: str = Form(...), pw: str = Form(...), db=Depends(db_session)):
    email = email.strip().lower()
    if not email or len(pw) < 8:
        return templates.TemplateResponse(request, "signup.html",
            {"err": "E-Mail nötig, Passwort mind. 8 Zeichen."}, status_code=400)
    if db.scalar(select(User).where(User.email == email)):
        return templates.TemplateResponse(request, "signup.html",
            {"err": "E-Mail ist schon registriert."}, status_code=400)
    u = User(email=email, pw=hash_pw(pw))
    db.add(u); db.commit()
    request.session["uid"] = u.id
    return RedirectResponse("/proposals", 302)


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
    return RedirectResponse("/radar", 302)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", 302)


# --- Vorschläge (geteilter Pool) + mein Radar -------------------------------
@app.get("/proposals", response_class=HTMLResponse)
def proposals(request: Request, b: str = "", user=Depends(current_user), db=Depends(db_session)):
    if not user:
        return RedirectResponse("/login", 302)
    mine = {c.proposal_id for c in db.scalars(select(Curation).where(Curation.user_id == user.id))}
    rows = db.scalars(select(Proposal).order_by(Proposal.relevance_general.desc(), Proposal.id.desc())).all()
    open_rows = [p for p in rows if p.id not in mine and (not b or b in p.branchen.split())]
    branchen = sorted({x for p in rows if p.id not in mine for x in p.branchen.split() if x})
    return templates.TemplateResponse(request, "proposals.html", {
        "user": user, "rows": open_rows[:200], "branchen": branchen,
        "sel": b, "rings": RINGS, "total_open": len([p for p in rows if p.id not in mine])})


@app.post("/add")
def add(request: Request, proposal_id: int = Form(...), ring: str = Form("Watch"),
        user=Depends(current_user), db=Depends(db_session)):
    if not user:
        return RedirectResponse("/login", 302)
    if ring not in RINGS:
        ring = "Watch"
    if not db.scalar(select(Curation).where(Curation.user_id == user.id, Curation.proposal_id == proposal_id)):
        db.add(Curation(user_id=user.id, proposal_id=proposal_id, ring=ring)); db.commit()
    return RedirectResponse("/proposals", 303)


@app.post("/remove")
def remove(request: Request, curation_id: int = Form(...), user=Depends(current_user), db=Depends(db_session)):
    if not user:
        return RedirectResponse("/login", 302)
    c = db.get(Curation, curation_id)
    if c and c.user_id == user.id:
        db.delete(c); db.commit()
    return RedirectResponse("/radar", 303)


@app.get("/radar", response_class=HTMLResponse)
def radar(request: Request, user=Depends(current_user), db=Depends(db_session)):
    if not user:
        return RedirectResponse("/login", 302)
    q = select(Curation, Proposal).join(Proposal, Curation.proposal_id == Proposal.id).where(
        Curation.user_id == user.id)
    items = list(db.execute(q).all())
    by_ring = {r: [] for r in RINGS}
    for cur, prop in items:
        by_ring.setdefault(cur.ring, []).append((cur, prop))
    return templates.TemplateResponse(request, "radar.html", {
        "user": user, "by_ring": by_ring, "rings": RINGS, "n": len(items)})


# --- Mandanten-Profil (E24, tenant-privat, DIREKT gespeichert) ---------------
@app.get("/profil", response_class=HTMLResponse)
def profil_form(request: Request, saved: int = 0, user=Depends(current_user), db=Depends(db_session)):
    if not user:
        return RedirectResponse("/login", 302)
    prof = db.get(Profile, user.id)
    data = json.loads(prof.data) if prof and prof.data else {}
    vals = {}
    for key, label, typ, opt in PROFILE_FIELDS:
        if key == "§":
            continue
        v = data.get(key)
        vals[key] = ", ".join(str(x) for x in v) if isinstance(v, list) else (v or "")
    return templates.TemplateResponse(request, "profil.html", {
        "user": user, "active": "profil", "fields": PROFILE_FIELDS, "vals": vals, "saved": bool(saved)})


@app.post("/profil")
async def save_profil(request: Request, user=Depends(current_user), db=Depends(db_session)):
    if not user:
        return RedirectResponse("/login", 302)
    form = await request.form()
    data = {}
    for key, label, typ, opt in PROFILE_FIELDS:
        if key == "§":
            continue
        raw = (form.get(key) or "").strip()
        data[key] = [x.strip() for x in raw.split(",") if x.strip()] if typ == "list" else raw
    payload = json.dumps(data, ensure_ascii=False)
    prof = db.get(Profile, user.id)
    if prof:
        prof.data = payload
    else:
        db.add(Profile(user_id=user.id, data=payload))
    db.commit()
    return RedirectResponse("/profil?saved=1", 303)


# --- Lagebild: LIVE aus dem Profil (+ geteilter Radar-Instanz) berechnet ------
@app.get("/lagebild", response_class=HTMLResponse)
def lagebild_view(request: Request, user=Depends(current_user), db=Depends(db_session)):
    if not user:
        return RedirectResponse("/login", 302)
    prof = db.get(Profile, user.id)
    data = json.loads(prof.data) if prof and prof.data else {}
    import sys as _sys
    if str(CORE_VIEW) not in _sys.path:
        _sys.path.insert(0, str(CORE_VIEW))
    try:
        from lagebild import render_lagebild
        # Dieselbe WERTEN-Logik wie der statische Build — hier mit dem PROFIL des
        # eingeloggten Mandanten (aus der DB) statt aus mandant.yaml. So rechnet
        # das Lagebild live: Profil speichern -> hier sofort neu berechnet.
        html = render_lagebild(INSTANCE, data)
        # Der Generator erzeugt statische Datei-Links (profil.html, detail-*.html …).
        # Im MVP gibt es Routen, keine .html-Dateien -> Links umbiegen bzw. (mangels
        # Detail-Seiten im MVP) neutralisieren, damit nichts ins Leere führt.
        html = (html.replace('href="profil.html"', 'href="/profil"')
                    .replace('href="index.html"', 'href="/radar"')
                    .replace('href="bericht.html"', 'href="/radar"')
                    .replace('href="markt.html"', 'href="/radar"')
                    .replace('href="kandidaten.html"', 'href="/proposals"'))
        html = re.sub(r'href="detail[^"]*\.html"', 'href="#" onclick="return false"', html)
    except Exception as e:
        html = ("<div style='max-width:720px;margin:40px auto;font-family:system-ui'>"
                f"<p>Lagebild derzeit nicht verfügbar: {e}</p>"
                "<p><a href='/profil'>← Profil</a></p></div>")
    return HTMLResponse(html)
