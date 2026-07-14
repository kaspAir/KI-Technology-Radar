"""db.py — Datenmodell des Selbstbedienungs-Radars (MVP, mandantenfähig).

Hierarchie (A2):
- Tenant = Mandant/Organisation, als BAUM (parent_id): Haupt-Mandant -> Untermandanten
  (z.B. Abteilungen). Jeder Mandant hat SEINE eigene Kuratierung + Profil (Instanz).
- User = gehört zu genau einem Mandanten, mit Rolle admin|member|viewer.
  is_platform_admin = Plattform-Betreiber (du), über allen Mandanten (tenant_id NULL).
- Curation/Profile hängen am MANDANTEN (tenant_id), nicht am Einzelnutzer -> alle
  Nutzer einer Org arbeiten am gemeinsamen Radar (E25: pro Mandant getrennt).
- Proposal = geteilter Pool (für alle Mandanten gleich).

SQLite fürs Bauen; Produktion: RADAR_DB auf MariaDB.
"""
from __future__ import annotations

import datetime as _dt
import os
from typing import Optional

from sqlalchemy import (Boolean, DateTime, ForeignKey, Integer, String, Text,
                        UniqueConstraint, create_engine, func)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column,
                            relationship, sessionmaker)

DATABASE_URL = os.environ.get("RADAR_DB", "sqlite:///./radar.db")
_connect = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
# pool_pre_ping: MariaDB/MySQL trennt inaktive Verbindungen -> vor Gebrauch prüfen
# (verhindert „server has gone away" im Dauerbetrieb). Bei SQLite unschädlich.
engine = create_engine(DATABASE_URL, future=True, connect_args=_connect,
                       pool_pre_ping=not DATABASE_URL.startswith("sqlite"))
SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)

ROLES = ["admin", "member", "viewer"]


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    """Mandant/Organisation. parent_id=NULL -> oberster Mandant; sonst Untermandant.

    is_reference=True markiert den EINEN geteilten Referenz-Radar (Grundstock ab 2017),
    den alle Mandanten erben (E24: zentral gepflegt, pro Mandant überschreibbar).
    """
    __tablename__ = "tenants"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    is_reference: Mapped[bool] = mapped_column(Boolean, default=False)
    created: Mapped[_dt.datetime] = mapped_column(DateTime, server_default=func.now())
    children = relationship("Tenant", backref="parent", remote_side=[id])


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    pw: Mapped[str] = mapped_column(String(255))
    tenant_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default="member")   # admin|member|viewer
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
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
    branchen: Mapped[str] = mapped_column(String(300), default="")
    suggested_entry: Mapped[str] = mapped_column(String(200), default="")
    relevance_general: Mapped[int] = mapped_column(Integer, default=0)
    date_published: Mapped[str] = mapped_column(String(20), default="")


class Curation(Base):
    """Private Wertung eines MANDANTEN: dieser Vorschlag auf sein Radar (Ring)."""
    __tablename__ = "curations"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id"), index=True)
    ring: Mapped[str] = mapped_column(String(20), default="Watch")
    created: Mapped[_dt.datetime] = mapped_column(DateTime, server_default=func.now())
    __table_args__ = (UniqueConstraint("tenant_id", "proposal_id", name="uq_tenant_prop"),)


class Profile(Base):
    """Mandanten-Profil (E24, pro Mandant). data = JSON der Profil-Felder."""
    __tablename__ = "profiles"
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    data: Mapped[str] = mapped_column(Text, default="{}")
    updated: Mapped[_dt.datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


def _ensure_columns() -> None:
    """Leichte Dev-Migration (nur SQLite): fehlende Spalten per ALTER TABLE ergänzen,
    damit ein Schema-Zuwachs die bestehende radar.db nicht unbrauchbar macht.
    Produktion (MariaDB) bekommt später echte Migrationen (Alembic)."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    _sqlite_type = {"INTEGER": "INTEGER", "BOOLEAN": "BOOLEAN", "VARCHAR": "VARCHAR",
                    "TEXT": "TEXT", "DATETIME": "DATETIME"}
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            have = {c["name"] for c in insp.get_columns(table.name)} if insp.has_table(table.name) else set()
            if not have:
                continue
            for col in table.columns:
                if col.name in have:
                    continue
                ctype = _sqlite_type.get(col.type.__class__.__name__.upper(), "VARCHAR")
                default = "0" if ctype in ("INTEGER", "BOOLEAN") else ("''" if ctype in ("VARCHAR", "TEXT") else None)
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ctype}'
                if default is not None:
                    ddl += f" DEFAULT {default}"
                conn.execute(text(ddl))


def init_db() -> None:
    Base.metadata.create_all(engine)
    _ensure_columns()
