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
    # Anbieter-Abhängigkeit (Blast-Radius): nur an ratifizierten Grundstock-Blips
    # gesetzt (aus entry.yaml importiert). providers = space-getrennt.
    providers: Mapped[str] = mapped_column(Text, default="")
    provider_dependency: Mapped[str] = mapped_column(Text, default="")


class Curation(Base):
    """Private Wertung eines MANDANTEN: dieser Vorschlag auf sein Radar (Ring)."""
    __tablename__ = "curations"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id"), index=True)
    ring: Mapped[str] = mapped_column(String(20), default="Watch")
    created: Mapped[_dt.datetime] = mapped_column(DateTime, server_default=func.now())
    __table_args__ = (UniqueConstraint("tenant_id", "proposal_id", name="uq_tenant_prop"),)


class CurationEvent(Base):
    """Ereignis-Historie der Wertung (E21): ein Mandant setzte einen Blip zum Datum
    'at' auf 'ring'. Stand as-of eines Datums = jüngstes Event mit at<=Datum je
    (tenant, proposal). ring in RINGS = sichtbar; '—' = ausgeblendet; '' = entfernt.
    Für den Grundstock aus assessments.yaml importiert (historische valid_from-Daten);
    für eigene Wertungen bei jeder Aktion (add/override/remove) mitgeschrieben."""
    __tablename__ = "curation_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id"), index=True)
    ring: Mapped[str] = mapped_column(String(20), default="")
    at: Mapped[str] = mapped_column(String(20), index=True)   # YYYY-MM-DD
    actor: Mapped[str] = mapped_column(String(80), default="mensch:mvp")
    created: Mapped[_dt.datetime] = mapped_column(DateTime, server_default=func.now())


class ChatMessage(Base):
    """Gesprächsverlauf des Radar-Beraters — pro MANDANT (E25), nicht pro Nutzer:
    das Team führt EIN Strategiegespräch. role = user|assistant."""
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text, default="")
    # '' = fertig · 'pending' = Berater denkt noch · 'error' = fehlgeschlagen.
    # Die Antwort entsteht im Hintergrund, damit keine HTTP-Anfrage darauf wartet.
    status: Mapped[str] = mapped_column(String(20), default="")
    # „Zurücksetzen" ARCHIVIERT statt zu löschen: ein neues Gespräch beginnt frisch,
    # das alte bleibt nachlesbar. Zerstörende Knöpfe ohne Rückweg gehören nicht ins Produkt.
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created: Mapped[_dt.datetime] = mapped_column(DateTime, server_default=func.now())


class ChatAttachment(Base):
    """Vom Mandanten hochgeladenes Dokument zu einer Chat-Nachricht. Gespeichert wird
    der EXTRAHIERTE TEXT (nicht die Datei) — er ist die Quelle, die der Berater sieht."""
    __tablename__ = "chat_attachments"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("chat_messages.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255), default="")
    kind: Mapped[str] = mapped_column(String(20), default="")
    note: Mapped[str] = mapped_column(String(255), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    created: Mapped[_dt.datetime] = mapped_column(DateTime, server_default=func.now())


class Profile(Base):
    """Mandanten-Profil (E24, pro Mandant). data = JSON der Profil-Felder."""
    __tablename__ = "profiles"
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    data: Mapped[str] = mapped_column(Text, default="{}")
    updated: Mapped[_dt.datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


def _ensure_columns() -> None:
    """Leichte additive Migration (SQLite + MariaDB): fehlende Spalten per ALTER TABLE
    ADD COLUMN ergänzen, damit ein Schema-Zuwachs die bestehende DB nicht unbrauchbar
    macht. Deckt additive Änderungen ab; komplexere Migrationen später via Alembic.
    Der Spaltentyp wird dialektkorrekt aus dem SQLAlchemy-Typ kompiliert."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                coltype = col.type.compile(dialect=engine.dialect)
                default = ""
                d = getattr(col.default, "arg", None) if col.default is not None else None
                if d is not None and not callable(d):
                    if isinstance(d, bool):
                        default = f" DEFAULT {1 if d else 0}"
                    elif isinstance(d, (int, float)):
                        default = f" DEFAULT {d}"
                    elif isinstance(d, str):
                        default = " DEFAULT '{}'".format(d.replace("'", "''"))
                conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {col.name} {coltype}{default}"))


def init_db() -> None:
    Base.metadata.create_all(engine)
    _ensure_columns()
