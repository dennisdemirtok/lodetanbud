"""
Engångsmigrering: legacy JSON-cases (/data/cases/*.json) → databasen.

Körs automatiskt vid appstart (lifespan) och kan köras manuellt via
scripts/migrate_json_cases.py. Idempotent — cases vars id redan finns
i databasen hoppas över, så omkörning är säker.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from app import states
from app.case_archive import _doc_dict_to_row, _line_dict_to_row
from app.db import Case, SessionLocal, engine, log_event


def _legacy_dirs() -> list[Path]:
    dirs = [Path(os.getenv("LODET_DATA_DIR", "/data")) / "cases", Path("/tmp/lodet/cases")]
    return [d for d in dirs if d.exists()]


# ---- SQLite → Postgres ------------------------------------------------------
# När DATABASE_URL pekas mot Postgres ligger AP1-erans data kvar i lodet.db
# på volymen. Kopierar alla rader vars id inte redan finns. Idempotent.

_SQLITE_JSON_COLS = {
    "cases": {"meta"},
    "documents": {"meta"},
    "mf_lines": {"source", "original_values", "meta"},
    "requirements": {"source"},
    "jobs": {"payload", "result"},
    "events": {"data"},
}


def _row_to_kwargs(table: str, row: sqlite3.Row) -> dict:
    out = dict(row)
    for col in _SQLITE_JSON_COLS.get(table, set()):
        if col in out and isinstance(out[col], str):
            try:
                out[col] = json.loads(out[col])
            except (json.JSONDecodeError, TypeError):
                out[col] = None
    return out


async def migrate_sqlite_to_postgres() -> int:
    """Engångsflytt av volymens SQLite-data in i Postgres. Returnerar antal
    flyttade rader. No-op när engine inte är Postgres eller filen saknas."""
    if engine.dialect.name != "postgresql":
        return 0

    sqlite_path = Path(os.getenv("LODET_DATA_DIR", "/data")) / "lodet.db"
    if not sqlite_path.exists():
        return 0

    from app.db import Document, Event, Job, MfLine, Requirement

    models = {
        "cases": Case,
        "documents": Document,
        "mf_lines": MfLine,
        "requirements": Requirement,
        "jobs": Job,
    }

    con = sqlite3.connect(str(sqlite_path))
    con.row_factory = sqlite3.Row
    moved = 0

    try:
        existing_tables = {
            r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }

        # Id-bärande tabeller — hoppa över redan migrerade ids
        for table, model in models.items():
            if table not in existing_tables:
                continue
            for row in con.execute(f"SELECT * FROM {table}"):
                kwargs = _row_to_kwargs(table, row)
                async with SessionLocal() as session:
                    if await session.get(model, kwargs["id"]) is not None:
                        continue
                    session.add(model(**kwargs))
                    await session.commit()
                    moved += 1

        # Events: autoincrement-pk — lägg in utan id så PG-sekvensen styr.
        # Dubbletter undviks med markörevent.
        if "events" in existing_tables:
            async with SessionLocal() as session:
                from sqlalchemy import select as _select
                marker = (await session.execute(
                    _select(Event).where(Event.kind == "sqlite_events_migrated").limit(1)
                )).scalar_one_or_none()
            if marker is None:
                for row in con.execute("SELECT * FROM events ORDER BY id"):
                    kwargs = _row_to_kwargs("events", row)
                    kwargs.pop("id", None)
                    async with SessionLocal() as session:
                        session.add(Event(**kwargs))
                        await session.commit()
                        moved += 1
                async with SessionLocal() as session:
                    await log_event(session, None, "sqlite_events_migrated", {"from": str(sqlite_path)})
                    await session.commit()
    finally:
        con.close()

    if moved:
        async with SessionLocal() as session:
            await log_event(session, None, "migrated_from_sqlite", {"rows": moved})
            await session.commit()
    return moved


async def migrate_legacy_json() -> int:
    """Returnerar antal migrerade cases."""
    migrated = 0
    for directory in _legacy_dirs():
        for path in sorted(directory.glob("case_*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            case_id = data.get("id")
            if not case_id:
                continue

            async with SessionLocal() as session:
                if await session.get(Case, case_id) is not None:
                    continue  # redan migrerad

                parsed_mf = data.get("parsed_mf") or {}
                mf_meta = parsed_mf.get("metadata") or {}
                mf_lines = parsed_mf.get("lines") or []

                case = Case(
                    id=case_id,
                    created_at=data.get("created_at") or "",
                    # Legacy-cases var färdiganalyserade → de landar i kalkyl-läget
                    state=states.CALCULATING,
                    source=data.get("source") or "okant",
                    source_name=data.get("source_name") or "",
                    project_name=data.get("project_name"),
                    document_number=data.get("document_number"),
                    customer=data.get("customer"),
                    total_amount_sek=data.get("total_amount_sek"),
                    meta={
                        "summary": data.get("summary") or {},
                        "lessons": data.get("lessons") or [],
                        "required_docs": data.get("required_docs") or [],
                        "drafts": data.get("drafts") or {},
                        "insights": data.get("insights")
                        or {"observations": [], "questions": [], "vendor_templates": []},
                        "ama_codes": data.get("ama_codes") or [],
                        "mf_metadata": mf_meta if parsed_mf else None,
                        "analysis": None,
                    },
                )
                session.add(case)

                for f in data.get("files") or []:
                    session.add(_doc_dict_to_row(case_id, f))
                for i, line in enumerate(mf_lines):
                    session.add(_line_dict_to_row(case_id, i, line))

                await log_event(session, case_id, "migrated_from_json", {"path": str(path)})
                await session.commit()
                migrated += 1

    return migrated
