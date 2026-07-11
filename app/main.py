"""main.py — Selbstbedienungs-Radar (MVP): Login → Vorschläge → mein Radar.

Start (Entwicklung):
  uvicorn app.main:app --reload
Umgebung: RADAR_DB (Default sqlite:///./radar.db), RADAR_SECRET (Session-Schlüssel).
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from .db import Curation, Proposal, SessionLocal, User, init_db
from .security import hash_pw, verify_pw

RINGS = ["Adopt", "Pilot", "Explore", "Watch", "Reject"]
BASE = Path(__file__).resolve().parent
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
