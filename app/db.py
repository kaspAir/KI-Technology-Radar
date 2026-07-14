"""db.py — Datenmodell des Selbstbedienungs-Radars (MVP).

Zwei Schichten (siehe docs/selbstbedienungs-radar-design.md):
- Proposal = geteilter Pool (Belege/Vorschläge), einmal für alle.
- Curation = private Wertung je Nutzer/Mandant (welcher Vorschlag auf MEIN Radar,
  welcher Ring). E25: die private Kuratierung ist pro user_id getrennt.

SQLite fürs Bauen; für Produktion RADAR_DB auf MariaDB setzen
(z.B. mysql+pymysql://user:pw@host/db).
"""
from __future__ import annotations

import datetime as _dt
import os

from sqlalchemy import (DateTime, ForeignKey, Integer, String, Text,
                        UniqueConstraint, create_engine, func)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column,
                            sessionmaker)

DATABASE_URL = os.environ.get("RADAR_DB", "sqlite:///./radar.db")
_connect = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, future=True, connect_args=_connect)
SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    pw: Mapped[str] = mapped_column(String(255))
    created: Mapped[_dt.datetime] = mapped_column(DateTime, server_default=func.now())


class Proposal(Base):
    """Geteilter Pool-Eintrag (aus der Ingestion). Dedup über url."""
    __tablename__ = "proposals"
    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text, default="")
    citation: Mapped[str] = mapped_column(Text, default="")
    source_id: Mapped[str] = mapped_column(String(80), default="")
    branchen: Mapped[str] = mapped_column(String(300), default="")   # space-getrennte domain-Slugs
    suggested_entry: Mapped[str] = mapped_column(String(200), default="")
    relevance_general: Mapped[int] = mapped_column(Integer, default=0)
    date_published: Mapped[str] = mapped_column(String(20), default="")


class Curation(Base):
    """Private Wertung: dieser Nutzer nimmt diesen Vorschlag auf seinen Radar (Ring)."""
    __tablename__ = "curations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id"), index=True)
    ring: Mapped[str] = mapped_column(String(20), default="Watch")
    created: Mapped[_dt.datetime] = mapped_column(DateTime, server_default=func.now())
    __table_args__ = (UniqueConstraint("user_id", "proposal_id", name="uq_user_prop"),)


class Profile(Base):
    """Mandanten-Profil (E24 Konfiguration, tenant-privat, 1:1 zum Nutzer/Mandant).
    `data` = JSON der Profil-Felder (schwerpunkte, risikofreudigkeit, kpis, …).
    Direkt-Speichern über /profil — steuert das Lagebild pro Mandant."""
    __tablename__ = "profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    data: Mapped[str] = mapped_column(Text, default="{}")
    updated: Mapped[_dt.datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


def init_db() -> None:
    Base.metadata.create_all(engine)
