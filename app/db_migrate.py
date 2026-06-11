"""
Engångsmigrering: legacy JSON-cases (/data/cases/*.json) → databasen.

Körs automatiskt vid appstart (lifespan) och kan köras manuellt via
scripts/migrate_json_cases.py. Idempotent — cases vars id redan finns
i databasen hoppas över, så omkörning är säker.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from app import states
from app.case_archive import _doc_dict_to_row, _line_dict_to_row
from app.db import Case, SessionLocal, log_event


def _legacy_dirs() -> list[Path]:
    dirs = [Path(os.getenv("LODET_DATA_DIR", "/data")) / "cases", Path("/tmp/lodet/cases")]
    return [d for d in dirs if d.exists()]


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
