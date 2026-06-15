"""
Case-arkiv — Postgres/SQLite via SQLAlchemy (genomförandeplan AP1).

Ersätter JSON-filerna på volymen. Publika API:t har samma funktioner och
returnerar samma dict-form som JSON-versionen (nu async), så frontend,
excel_builder och draft-endpoints är oförändrade.

parsed_mf demonteras till mf_lines-rader vid skrivning och monteras ihop
vid läsning — det ger radnivå-data (source/confidence/reviewed_by_user)
som AP2:s granskningsvy bygger på, utan att ändra API-formen.

lessons/required_docs/drafts/insights ligger kvar i cases.meta under AP1
och flyttar till egna tabeller i AP3/AP4.
"""

from __future__ import annotations

import re

from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from app import states
from app.db import Case, Document, MfLine, SessionLocal, log_event, new_id, utcnow_iso


# ---- Montering / demontering ---------------------------------------------

_LINE_META_KEYS = ("line_number", "ama_section_title", "is_lump_sum", "_resources")


def _line_row_to_dict(row: MfLine) -> dict:
    meta = row.meta or {}
    d = {
        "line_number": meta.get("line_number", row.position),
        "ama_code": row.ama_code,
        "ama_section_title": meta.get("ama_section_title"),
        "description": row.description,
        "unit": row.unit,
        "quantity": row.quantity,
        "unit_price": row.unit_price,
        "total_amount": row.total,
        "is_lump_sum": bool(meta.get("is_lump_sum")),
        "source": row.source,
        "extraction_method": row.extraction_method,
        "confidence": row.confidence,
        "reviewed_by_user": row.reviewed_by_user,
    }
    if row.original_values:
        d["original_values"] = row.original_values
    if meta.get("_resources"):
        d["_resources"] = meta["_resources"]
    return d


def _line_dict_to_row(case_id: str, position: int, line: dict) -> MfLine:
    meta = {k: line.get(k) for k in _LINE_META_KEYS if line.get(k) is not None}
    return MfLine(
        id=new_id("line"),
        case_id=case_id,
        position=position,
        ama_code=line.get("ama_code"),
        description=line.get("description"),
        unit=line.get("unit"),
        quantity=line.get("quantity"),
        unit_price=line.get("unit_price"),
        total=line.get("total_amount"),
        source=line.get("source") or {"row": line.get("line_number", position)},
        extraction_method=line.get("extraction_method") or "deterministic",
        confidence=float(line.get("confidence") if line.get("confidence") is not None else 1.0),
        reviewed_by_user=bool(line.get("reviewed_by_user")),
        original_values=line.get("original_values"),
        meta=meta,
    )


def _doc_row_to_dict(row: Document) -> dict:
    meta = row.meta or {}
    return {
        "filename": row.filename,
        "type": row.doc_type,
        "label": row.label,
        "confidence": row.confidence,
        "size_kb": meta.get("size_kb"),
        "project_id": meta.get("project_id"),
        "discipline": meta.get("discipline"),
        "metadata": meta.get("metadata"),
        "storage_path": row.storage_path,
    }


def _doc_dict_to_row(case_id: str, f: dict) -> Document:
    extra = {
        "size_kb": f.get("size_kb"),
        "project_id": f.get("project_id"),
        "discipline": f.get("discipline"),
        "metadata": f.get("metadata"),
    }
    meta_dict = f.get("metadata") or {}
    return Document(
        id=new_id("doc"),
        case_id=case_id,
        filename=f.get("filename") or "",
        doc_type=f.get("type") or "okant",
        label=f.get("label"),
        confidence=f.get("confidence"),
        storage_path=f.get("storage_path"),
        page_count=meta_dict.get("page_count") if isinstance(meta_dict, dict) else None,
        meta=extra,
    )


def _case_to_dict(case: Case, docs: list[Document], lines: list[MfLine]) -> dict:
    meta = case.meta or {}
    parsed_mf = None
    if lines or meta.get("mf_metadata"):
        parsed_mf = {
            "metadata": meta.get("mf_metadata") or {},
            "lines": [_line_row_to_dict(r) for r in sorted(lines, key=lambda x: x.position)],
        }
    return {
        "id": case.id,
        "created_at": case.created_at,
        "state": case.state,
        "state_label": states.LABELS.get(case.state, case.state),
        "source": case.source,
        "source_name": case.source_name,
        "summary": meta.get("summary") or {},
        "files": [_doc_row_to_dict(d) for d in docs],
        "parsed_mf": parsed_mf,
        "lessons": meta.get("lessons") or [],
        "project_name": case.project_name,
        "document_number": case.document_number,
        "customer": case.customer,
        "total_amount_sek": case.total_amount_sek,
        "ama_codes": meta.get("ama_codes") or [],
        "required_docs": meta.get("required_docs") or [],
        "drafts": meta.get("drafts") or {},
        "insights": meta.get("insights") or {"observations": [], "questions": [], "vendor_templates": []},
        "ue_assignments": meta.get("ue_assignments") or {},
        "paslag_procent": meta.get("paslag_procent"),
        "analysis": meta.get("analysis"),
    }


async def _load_case_full(session, case_id: str) -> tuple[Case | None, list[Document], list[MfLine]]:
    case = await session.get(Case, case_id)
    if case is None:
        return None, [], []
    docs = (await session.execute(
        select(Document).where(Document.case_id == case_id)
    )).scalars().all()
    lines = (await session.execute(
        select(MfLine).where(MfLine.case_id == case_id)
    )).scalars().all()
    return case, list(docs), list(lines)


# ---- CRUD ------------------------------------------------------------------

async def create_case_shell(source: str, source_name: str) -> str:
    """Skapa ett tomt case i INTAKE — innan analysen körts. Returnerar id."""
    async with SessionLocal() as session:
        cid = new_id("case")
        case = Case(
            id=cid,
            created_at=utcnow_iso(),
            state=states.INTAKE,
            source=source,
            source_name=source_name,
            meta={},
        )
        session.add(case)
        await log_event(session, cid, "case_created", {"source": source, "source_name": source_name})
        await session.commit()
        return cid


async def update_case_full(
    case_id: str,
    *,
    summary: dict,
    files: list[dict],
    parsed_mf: dict | None,
    lessons: list[dict],
    required_docs: list[dict],
    insights: dict,
    analysis: dict | None = None,
) -> dict | None:
    """Skriv analysresultatet till casen. Idempotent — skriver om
    documents/mf_lines, appendar aldrig."""
    async with SessionLocal() as session:
        case = await session.get(Case, case_id)
        if case is None:
            return None

        mf_meta = (parsed_mf or {}).get("metadata") or {}
        mf_lines = (parsed_mf or {}).get("lines") or []

        case.project_name = summary.get("project_name") or mf_meta.get("project_name")
        case.document_number = mf_meta.get("document_number")
        case.customer = summary.get("customer")
        case.total_amount_sek = mf_meta.get("total_amount_sek")

        ama_codes = sorted({
            l.get("ama_code") for l in mf_lines if l.get("ama_code")
        })

        case.meta = {
            **(case.meta or {}),
            "summary": summary,
            "lessons": lessons,
            "required_docs": required_docs,
            "insights": insights,
            "ama_codes": ama_codes,
            "mf_metadata": mf_meta if parsed_mf else None,
            "analysis": analysis,
        }

        await session.execute(sa_delete(Document).where(Document.case_id == case_id))
        await session.execute(sa_delete(MfLine).where(MfLine.case_id == case_id))
        for f in files:
            session.add(_doc_dict_to_row(case_id, f))
        for i, line in enumerate(mf_lines):
            session.add(_line_dict_to_row(case_id, i, line))

        await log_event(session, case_id, "analysis_written", {
            "file_count": len(files), "line_count": len(mf_lines),
        })
        await session.commit()

        return {
            "id": case_id,
            "lessons": lessons,
            "required_docs": required_docs,
            "insights": insights,
        }


async def list_cases() -> list[dict]:
    """Alla cases (fulla dicts), senaste först."""
    async with SessionLocal() as session:
        rows = (await session.execute(
            select(Case).order_by(Case.created_at.desc())
        )).scalars().all()
        out = []
        for case in rows:
            _, docs, lines = await _load_case_full(session, case.id)
            out.append(_case_to_dict(case, docs, lines))
        return out


async def list_cases_summary() -> list[dict]:
    """Lättare lista för UI — utan parsed_mf och files."""
    async with SessionLocal() as session:
        rows = (await session.execute(
            select(Case).order_by(Case.created_at.desc())
        )).scalars().all()
        doc_counts: dict[str, int] = {}
        for d in (await session.execute(select(Document.case_id))).scalars().all():
            doc_counts[d] = doc_counts.get(d, 0) + 1

        out = []
        for c in rows:
            meta = c.meta or {}
            out.append({
                "id": c.id,
                "created_at": c.created_at,
                "state": c.state,
                "state_label": states.LABELS.get(c.state, c.state),
                "source": c.source,
                "source_name": c.source_name,
                "project_name": c.project_name,
                "document_number": c.document_number,
                "customer": c.customer,
                "total_amount_sek": c.total_amount_sek,
                "ama_codes": meta.get("ama_codes") or [],
                "lesson_count": len(meta.get("lessons") or []),
                "file_count": doc_counts.get(c.id, 0),
                "required_count": len(meta.get("required_docs") or []),
                "draft_count": len(meta.get("drafts") or {}),
            })
        return out


async def get_case(case_id: str) -> dict | None:
    async with SessionLocal() as session:
        case, docs, lines = await _load_case_full(session, case_id)
        if case is None:
            return None
        return _case_to_dict(case, docs, lines)


async def delete_case(case_id: str) -> bool:
    async with SessionLocal() as session:
        case = await session.get(Case, case_id)
        if case is None:
            return False
        await session.delete(case)  # cascade tar documents/mf_lines/jobs/events
        await session.commit()
        return True


# ---- Partiella uppdateringar ----------------------------------------------

async def _update_meta(case_id: str, key: str, value) -> bool:
    async with SessionLocal() as session:
        case = await session.get(Case, case_id)
        if case is None:
            return False
        case.meta = {**(case.meta or {}), key: value}
        await session.commit()
        return True


async def update_lessons(case_id: str, lessons: list[dict]) -> bool:
    return await _update_meta(case_id, "lessons", lessons)


async def update_required_docs(case_id: str, required_docs: list[dict]) -> bool:
    return await _update_meta(case_id, "required_docs", required_docs)


async def update_draft(case_id: str, doc_id: str, text: str, edited: bool = False) -> bool:
    """Spara ett genererat eller redigerat utkast för ett krav."""
    async with SessionLocal() as session:
        case = await session.get(Case, case_id)
        if case is None:
            return False
        meta = case.meta or {}
        drafts = dict(meta.get("drafts") or {})
        existing = drafts.get(doc_id) or {}
        now = utcnow_iso()
        drafts[doc_id] = {
            "text": text,
            "generated_at": existing.get("generated_at") or now,
            "edited_at": now if edited else existing.get("edited_at"),
        }
        case.meta = {**meta, "drafts": drafts}
        await log_event(session, case_id, "draft_updated", {"doc_id": doc_id, "edited": edited})
        await session.commit()
        return True


async def get_draft(case_id: str, doc_id: str) -> dict | None:
    case = await get_case(case_id)
    if case is None:
        return None
    return (case.get("drafts") or {}).get(doc_id)


async def update_parsed_mf(case_id: str, parsed_mf: dict) -> bool:
    """Spara redigerad mängdförteckning. Skriver om mf_lines och synkar
    total_amount_sek på case-nivå."""
    async with SessionLocal() as session:
        case = await session.get(Case, case_id)
        if case is None:
            return False

        mf_meta = parsed_mf.get("metadata") or {}
        lines = parsed_mf.get("lines") or []

        await session.execute(sa_delete(MfLine).where(MfLine.case_id == case_id))
        for i, line in enumerate(lines):
            session.add(_line_dict_to_row(case_id, i, line))

        if mf_meta.get("total_amount_sek") is not None:
            case.total_amount_sek = mf_meta["total_amount_sek"]
        ama_codes = sorted({l.get("ama_code") for l in lines if l.get("ama_code")})
        case.meta = {**(case.meta or {}), "mf_metadata": mf_meta, "ama_codes": ama_codes}

        await log_event(session, case_id, "user_edit", {
            "what": "parsed_mf", "line_count": len(lines),
            "total_amount_sek": mf_meta.get("total_amount_sek"),
        })
        await session.commit()
        return True


# ---- Kravmatris (AP3) -------------------------------------------------------

async def replace_requirements(case_id: str, reqs: list[dict]) -> int:
    """Skriv om kravmatrisen för ett case (idempotent). Kopplar kraven till
    AF-PDF-dokumentet om ett finns."""
    from app.db import Document, Requirement
    from sqlalchemy import select as _select

    async with SessionLocal() as session:
        af_doc = (await session.execute(
            _select(Document).where(
                Document.case_id == case_id,
                Document.doc_type == "af",
            )
        )).scalars().first()
        af_doc_id = af_doc.id if af_doc else None

        await session.execute(sa_delete(Requirement).where(Requirement.case_id == case_id))
        for i, r in enumerate(reqs):
            session.add(Requirement(
                id=new_id("req"),
                case_id=case_id,
                document_id=af_doc_id,
                position=r.get("position", i),
                af_code=r.get("af_code"),
                kind=r.get("kind") or "skall",
                text=r.get("text") or "",
                response_format=r.get("response_format"),
                deadline=r.get("deadline"),
                source=r.get("source"),
                confidence=float(r.get("confidence") or 0.0),
                status="unanswered",
            ))
        if reqs:
            await log_event(session, case_id, "requirements_extracted", {
                "count": len(reqs),
                "skall": sum(1 for r in reqs if r.get("kind") == "skall"),
                "verified": sum(1 for r in reqs if (r.get("source") or {}).get("verified")),
            })
        await session.commit()
        return len(reqs)


# ---- Events ----------------------------------------------------------------

async def list_events(case_id: str, limit: int = 100) -> list[dict]:
    from app.db import Event
    async with SessionLocal() as session:
        rows = (await session.execute(
            select(Event).where(Event.case_id == case_id).order_by(Event.id.desc()).limit(limit)
        )).scalars().all()
        return [{"at": e.at, "kind": e.kind, "data": e.data or {}} for e in rows]


# ---- Sökning för chat-kontext ----------------------------------------------

async def find_relevant(query: str, ama_codes: list[str] | None = None, limit: int = 3) -> list[dict]:
    """Keyword/AMA-baserad scoring (oförändrad logik). Byts till pgvector i AP4."""
    cases = await list_cases()
    if not cases:
        return []

    query_lower = query.lower()
    query_terms = set(re.findall(r"[\wåäöÅÄÖ\.]+", query_lower))
    target_codes = set((ama_codes or []) + _extract_ama_codes(query))

    scored: list[tuple[float, dict]] = []
    for c in cases:
        score = 0.0

        case_codes = set(c.get("ama_codes") or [])
        if target_codes:
            overlap = case_codes & target_codes
            score += len(overlap) * 5.0
            for code in target_codes:
                for case_code in case_codes:
                    if case_code != code and (case_code.startswith(code) or code.startswith(case_code)):
                        score += 2.0

        haystack_parts = [
            c.get("project_name") or "",
            c.get("customer") or "",
            c.get("source_name") or "",
        ]
        for lesson in c.get("lessons") or []:
            haystack_parts.append(lesson.get("note") or "")
            haystack_parts.append(lesson.get("type") or "")
            haystack_parts.append(lesson.get("ama_code") or "")
        haystack = " ".join(haystack_parts).lower()
        haystack_terms = set(re.findall(r"[\wåäöÅÄÖ\.]+", haystack))
        score += len(query_terms & haystack_terms) * 0.5

        if score > 0:
            scored.append((score, c))

    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:limit]]


def _extract_ama_codes(text: str) -> list[str]:
    """Plocka AMA-koder från fri text, t.ex. 'SBC.21' eller 'YGB.6312'."""
    return re.findall(r"\b[A-Z]{1,4}\.\d+(?:\.\d+)*\b", text)


def case_summary_for_context(case: dict, max_lessons: int = 8) -> str:
    """Formattera ett case till kompakt kontext-text för Claude."""
    lines = []
    lines.append(f"## {case.get('project_name') or '(okänt projekt)'}")
    if case.get("document_number"):
        lines.append(f"Dokumentnr: {case['document_number']}")
    if case.get("customer"):
        lines.append(f"Beställare: {case['customer']}")
    if case.get("total_amount_sek"):
        amount = case["total_amount_sek"]
        lines.append(f"Totalbelopp: {amount:,.0f} kr".replace(",", " "))
    lines.append(f"Datum: {case.get('created_at', '')}")

    ama = case.get("ama_codes") or []
    if ama:
        sample = ", ".join(ama[:10])
        more = f" (+{len(ama) - 10})" if len(ama) > 10 else ""
        lines.append(f"AMA-koder: {sample}{more}")

    lessons = case.get("lessons") or []
    if lessons:
        lines.append("Lärdomar:")
        for lsn in lessons[:max_lessons]:
            note = lsn.get("note") or ""
            code = lsn.get("ama_code")
            kind = lsn.get("type") or ""
            prefix = f"[{kind}]" if kind else "•"
            ama_part = f" {code}: " if code else " "
            lines.append(f"  {prefix}{ama_part}{note}")

    return "\n".join(lines)
