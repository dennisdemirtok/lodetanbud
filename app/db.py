"""
Databaslager — SQLAlchemy 2.0 async (genomförandeplan AP1).

DATABASE_URL styr dialekt:
  - postgresql://… / postgres://…  → Postgres via asyncpg (Railway/Supabase)
  - (osatt)                        → SQLite via aiosqlite på LODET_DATA_DIR-volymen

SQLite-defaulten gör att deployen fungerar innan Postgres-beslutet
(Supabase vs Railway) är taget — samma kod, byt bara env-variabeln.

IDs är strängar med prefix (case_/doc_/job_) istället för uuid-kolumner:
legacy-case-ids från JSON-arkivet ("case_1777…") migreras då oförändrade
och alla sparade URL:er/localStorage-referenser överlever.
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _data_root() -> Path:
    root = Path(os.getenv("LODET_DATA_DIR", "/data"))
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".write_test"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
    except (OSError, PermissionError):
        root = Path("/tmp/lodet")
        root.mkdir(parents=True, exist_ok=True)
    return root


DATA_ROOT = _data_root()
FILES_DIR = DATA_ROOT / "files"


def database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url
    return f"sqlite+aiosqlite:///{DATA_ROOT / 'lodet.db'}"


engine = create_async_engine(database_url(), echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


def new_id(prefix: str) -> str:
    return f"{prefix}_{int(time.time())}_{uuid.uuid4().hex[:6]}"


def utcnow_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Base(DeclarativeBase):
    pass


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # multi-tenant förberett nu, används efter AP5
    created_at: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(32), default="INTAKE", index=True)
    source: Mapped[str] = mapped_column(String(16))
    source_name: Mapped[str] = mapped_column(Text)
    project_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer: Mapped[str | None] = mapped_column(Text, nullable=True)
    bid_due_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    total_amount_sek: Mapped[float | None] = mapped_column(Float, nullable=True)
    # summary, lessons, required_docs, drafts, insights, ama_codes, mf_metadata, analysis
    # ligger i meta under AP1 — flyttar till egna tabeller i AP3/AP4
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(Text)
    doc_type: Mapped[str] = mapped_column(String(32))
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)  # relativ DATA_ROOT; None för legacy-cases
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class MfLine(Base):
    __tablename__ = "mf_lines"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    position: Mapped[int] = mapped_column(Integer)
    ama_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    total: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {row} → Linked Evidence, utökas med page/bbox i AP2
    extraction_method: Mapped[str] = mapped_column(String(16), default="deterministic")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    reviewed_by_user: Mapped[bool] = mapped_column(Boolean, default=False)
    original_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # AI:ns ursprungsvärden vid användarrättning
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # is_lump_sum, ama_section_title, _resources, line_number


class Requirement(Base):
    """Kravmatris (AP3) — varje krav är ett ordagrant, verifierat citat ur AF."""
    __tablename__ = "requirements"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    af_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(16))  # skall|bor|utvardering|formalia|bilaga
    text: Mapped[str] = mapped_column(Text)        # kravets lydelse — citat, inte parafras
    response_format: Mapped[str | None] = mapped_column(String(16), nullable=True)  # fritext|bilaga|intyg|pris|checkbox
    deadline: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {page, verified, match_ratio}
    confidence: Mapped[float] = mapped_column(Float, default=0.0)     # 0 = citat ej verifierat
    status: Mapped[str] = mapped_column(String(16), default="unanswered")  # unanswered|drafted|answered|na
    answer_draft_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # → drafts (AP5)
    reviewed_by_user: Mapped[bool] = mapped_column(Boolean, default=False)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("cases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(32), nullable=True)


class PriceObservation(Base):
    """À-prishistorik (AP4) — varje granskat/prissatt case blir prisdata.

    Embedding-kolumnen (plan §4.1, pgvector 1536) väntar på ett embedding-API
    (Anthropic saknar eget; Voyage/OpenAI-nyckel behövs). Tills dess körs
    likhetssteget i förslagskaskaden med pg_trgm (Postgres) respektive
    difflib (SQLite) på description — deterministiskt och nyckelfritt.
    meta.embedding är reserverad plats när nyckeln finns."""
    __tablename__ = "price_observations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("cases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    ama_code: Mapped[str] = mapped_column(String(32), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit_price: Mapped[float] = mapped_column(Float)
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observed_at: Mapped[str] = mapped_column(String(32))  # ISO-datum
    source: Mapped[str] = mapped_column(String(16), default="own_bid")  # own_bid|awarded|ue_quote
    won: Mapped[bool | None] = mapped_column(Boolean, nullable=True)    # fylls vid utfall (AP5)
    project_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_price_obs_code_date", "ama_code", "observed_at"),
    )


class AnswerLibrary(Base):
    """Svarsbibliotek (AP5) — godkända AFB-fritextsvar återanvänds på
    liknande krav. Likhet körs på requirement_text (pg_trgm/difflib);
    meta.embedding reserverad för pgvector när embedding-nyckel finns."""
    __tablename__ = "answer_library"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    af_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    requirement_text: Mapped[str] = mapped_column(Text)   # kravets lydelse
    answer_text: Mapped[str] = mapped_column(Text)        # det godkända svaret
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_case_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("cases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    at: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(48))
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)


async def init_db() -> None:
    """Skapa schema om det saknas (idempotent). På Postgres aktiveras
    pgvector (för embeddings när API-nyckel finns) och pg_trgm (driver
    likhetssteget i prisförslagskaskaden, AP4)."""
    if engine.dialect.name == "postgresql":
        for ext in ("vector", "pg_trgm"):
            try:
                async with engine.begin() as conn:
                    await conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext}"))
            except Exception as e:
                print(f"[lodet] kunde inte aktivera extension {ext}: {e}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    FILES_DIR.mkdir(parents=True, exist_ok=True)


async def log_event(
    session: AsyncSession, case_id: str | None, kind: str, data: dict | None = None
) -> None:
    session.add(Event(case_id=case_id, at=utcnow_iso(), kind=kind, data=data or {}))
