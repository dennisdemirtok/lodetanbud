"""
Lodet — FastAPI-app
===================
"""

from __future__ import annotations

import asyncio
import json
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select as sa_select

from app import __version__
from app import afb_templates as afb
from app import ama_catalog
from app import case_archive
from app import chat as lodet_chat
from app import company_settings
from app import db as lodet_db
from app import db_migrate
from app import jobs as jobq
from app import pdf_renderer
from app import requirement_extractor
from app import resource_library
from app import states as case_states
from app import ue_emailer
from app import worker as lodet_worker
from app import zip_handler
from app.excel_builder import build_workbook
from app.parser import parse_csv_bytes


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
EXAMPLES_DIR = BASE_DIR.parent / "examples"

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initiera DB, återställ avbrutna jobb, migrera legacy-JSON och
    starta jobb-workern (genomförandeplan AP1)."""
    await lodet_db.init_db()
    reset = await jobq.reset_orphans()
    if reset:
        print(f"[lodet] {reset} avbrutna jobb återställda till kön")
    try:
        migrated = await db_migrate.migrate_legacy_json()
        if migrated:
            print(f"[lodet] {migrated} legacy-JSON-cases migrerade till databasen")
    except Exception as e:
        print(f"[lodet] legacy-migrering misslyckades: {e}")
    worker_task = asyncio.create_task(lodet_worker.worker_loop())
    yield
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Lodet",
    description="Anbudsverktyg för svenska bygg- och anläggningsentreprenörer",
    version=__version__,
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def _local_timestamp() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


async def _read_upload(file: UploadFile) -> bytes:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Ingen fil mottagen")
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Endast .csv-filer stöds i denna version")
    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Filen är tom")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Filen är för stor (max 10 MB)")
    return data


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "version": __version__},
    )


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "version": __version__}


# --- Parse / Excel ---------------------------------------------------------

@app.post("/api/parse")
async def api_parse(file: UploadFile = File(...)) -> JSONResponse:
    data = await _read_upload(file)
    try:
        doc = parse_csv_bytes(data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Parsefel: {e}")

    return JSONResponse(
        {
            "filename": file.filename,
            "summary": doc.summary(),
            "data": doc.to_dict(),
        }
    )


@app.post("/api/excel")
async def api_excel(file: UploadFile = File(...)) -> Response:
    data = await _read_upload(file)
    try:
        doc = parse_csv_bytes(data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Parsefel: {e}")

    xlsx = build_workbook(doc.to_dict(), generated_at=_local_timestamp())
    project_slug = (doc.project_name or "anbud").replace(" ", "_").replace(",", "").replace("/", "-")
    today = datetime.now().strftime("%Y%m%d")
    filename = f"Lodet_Anbud_{project_slug}_{today}.xlsx"

    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Lodet-Version": __version__,
        },
    )


# --- Demo / exempeldata ---------------------------------------------------

@app.get("/api/example")
async def api_example() -> JSONResponse:
    example_path = EXAMPLES_DIR / "parsed_output.json"
    if not example_path.exists():
        raise HTTPException(status_code=404, detail="Exempelfil saknas")
    with example_path.open(encoding="utf-8") as fh:
        data = json.load(fh)

    summary = {
        "project": data["metadata"].get("project_name"),
        "document_number": data["metadata"].get("document_number"),
        "date": data["metadata"].get("date"),
        "status": data["metadata"].get("status"),
        "total_amount_sek": data["metadata"].get("total_amount_sek"),
        "line_count": len(data["lines"]),
        "ama_codes_used": sorted({l["ama_code"] for l in data["lines"] if l.get("ama_code")}),
        "lump_sum_count": sum(1 for l in data["lines"] if l.get("is_lump_sum")),
        "priced_lines": sum(1 for l in data["lines"] if l.get("unit_price") is not None),
    }

    return JSONResponse(
        {
            "filename": "demo_westcon_vag875.csv",
            "summary": summary,
            "data": data,
        }
    )


@app.post("/api/example/excel")
async def api_example_excel() -> Response:
    example_path = EXAMPLES_DIR / "parsed_output.json"
    if not example_path.exists():
        raise HTTPException(status_code=404, detail="Exempelfil saknas")
    with example_path.open(encoding="utf-8") as fh:
        data = json.load(fh)

    xlsx = build_workbook(data, generated_at=_local_timestamp())
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="Lodet_Anbud_demo_Westcon.xlsx"',
        },
    )


# --- AMA-bibliotek --------------------------------------------------------

@app.get("/api/ama")
async def api_ama(system: str = "AMA_Anläggning") -> JSONResponse:
    if system not in {"AMA_Anläggning", "AF_AMA"}:
        raise HTTPException(status_code=400, detail="Okänt AMA-system")

    grouped = ama_catalog.grouped_by_section(system)
    sections = []
    for letter in sorted(grouped.keys()):
        sections.append(
            {
                "letter": letter,
                "label": ama_catalog.section_label(letter),
                "index_basis": ama_catalog.index_for_section(letter),
                "codes": grouped[letter],
            }
        )

    return JSONResponse(
        {
            "system": system,
            "section_count": len(sections),
            "code_count": sum(len(s["codes"]) for s in sections),
            "sections": sections,
        }
    )


# --- AFB-mallar -----------------------------------------------------------

@app.get("/api/afb/templates")
async def api_afb_templates() -> JSONResponse:
    return JSONResponse({"templates": afb.list_templates()})


@app.post("/api/afb/{template_id}")
async def api_afb_render(
    template_id: str,
    project_name: str = Form("VÄG 875, GC SUNDBORN"),
    document_number: str = Form("1E12MF10"),
    company_name: str = Form("Westcon Entreprenad AB"),
    customer_name: str = Form("Trafikverket"),
    total_amount: float = Form(1687336.0),
    contact_name: str = Form(""),
    contact_email: str = Form(""),
    contact_phone: str = Form(""),
    organisationsnummer: str = Form(""),
) -> JSONResponse:
    if template_id == "anbudssumma":
        text = afb.anbudssumma(
            project_name=project_name,
            document_number=document_number,
            company_name=company_name,
            total_amount=total_amount,
            contact_name=contact_name,
            contact_email=contact_email,
            contact_phone=contact_phone,
        )
    elif template_id == "ue-lista":
        text = afb.ue_lista(project_name=project_name, company_name=company_name)
    elif template_id == "sekretess":
        text = afb.sekretessbegaran(
            project_name=project_name,
            document_number=document_number,
            company_name=company_name,
            organisationsnummer=organisationsnummer,
            contact_name=contact_name,
        )
    elif template_id == "missiv":
        text = afb.missiv(
            project_name=project_name,
            document_number=document_number,
            company_name=company_name,
            customer_name=customer_name,
            contact_name=contact_name,
        )
    else:
        raise HTTPException(status_code=404, detail=f"Okänd mall: {template_id}")

    return JSONResponse({"template_id": template_id, "text": text})


# --- Chat (Claude API) ----------------------------------------------------

@app.get("/api/chat/status")
async def api_chat_status() -> JSONResponse:
    return JSONResponse({"configured": lodet_chat.is_configured()})


@app.post("/api/chat")
async def api_chat(payload: dict = Body(...)) -> StreamingResponse:
    messages = payload.get("messages") or []
    context = payload.get("context")

    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=400, detail="Inga meddelanden mottagna")

    cleaned = []
    for m in messages[-30:]:
        role = m.get("role")
        content = m.get("content")
        if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
            cleaned.append({"role": role, "content": content})

    if not cleaned or cleaned[-1]["role"] != "user":
        raise HTTPException(status_code=400, detail="Sista meddelandet måste vara från användaren")

    return StreamingResponse(
        lodet_chat.stream_chat(cleaned, context=context),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# --- Agent / paketanalys ---------------------------------------------------
# Analysen körs av workern (app/pipeline.py). Endpointen gör bara den
# synkrona delen: packa upp, spara filer på volymen, skapa case (INTAKE)
# och köa parse_package — svar < 1 s. Frontend pollar /status.

def _safe_storage_name(filename: str) -> str:
    name = filename.replace("\\", "/").strip("/")
    name = name.replace("/", "__")
    name = re.sub(r"[^\w.\-åäöÅÄÖ ()]+", "_", name)
    return name[:180] or "fil"


async def _stage_package(source: str, source_name: str, pairs: list[tuple[str, bytes]]) -> str:
    """Skapa case-skal, skriv filerna till volymen och köa analys-jobbet."""
    case_id = await case_archive.create_case_shell(source, source_name)
    case_dir = lodet_db.FILES_DIR / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    file_refs: list[dict] = []
    used: set[str] = set()
    for filename, data in pairs:
        safe = _safe_storage_name(filename)
        candidate, i = safe, 1
        while candidate in used:
            candidate = f"{i}__{safe}"
            i += 1
        used.add(candidate)
        path = case_dir / candidate
        path.write_bytes(data)
        file_refs.append({
            "filename": filename,
            "path": str(path.relative_to(lodet_db.DATA_ROOT)),
        })

    await jobq.enqueue_standalone(case_id, "parse_package", {"case_id": case_id, "files": file_refs})
    return case_id


@app.post("/api/package/analyze")
async def api_package_analyze(files: list[UploadFile] = File(...)) -> JSONResponse:
    """
    Tar emot ett helt anbudspaket — vanliga filer eller en eller flera ZIP-filer.
    Om en ZIP innehåller flera toppmappar tolkas varje toppmapp som ett separat
    anbudspaket. Returnerar case-ids direkt; analysen körs som jobb.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Inga filer mottagna")

    plain_files: list[tuple[str, bytes]] = []
    zip_groups: list[tuple[str, list[tuple[str, bytes]]]] = []

    for f in files:
        if not f.filename:
            continue
        data = await f.read()
        if zip_handler.is_zip_filename(f.filename):
            try:
                extracted = zip_handler.extract_zip(data)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            grouped = zip_handler.group_by_folder(extracted)
            zip_base = f.filename.rsplit(".", 1)[0]
            for folder, fs in grouped.items():
                # relative_path (med mappar) som filnamn — mappnamn bär
                # klassificeringssignal (t.ex. "10. Mängdförteckning/")
                pairs = [(x.relative_path, x.data) for x in fs]
                source_name = f"{zip_base}/{folder}" if folder != "(rotmapp)" else zip_base
                zip_groups.append((source_name, pairs))
        else:
            plain_files.append((f.filename, data))

    case_ids: list[str] = []

    # Plain (lösa filer + ev. mapp via webkitdirectory) → ETT paket
    if plain_files:
        case_ids.append(await _stage_package(
            source="folder" if len(plain_files) > 1 else "single",
            source_name="uppladdat-paket",
            pairs=plain_files,
        ))

    # Ett case per ZIP-mapp
    for source_name, pairs in zip_groups:
        case_ids.append(await _stage_package(source="zip", source_name=source_name, pairs=pairs))

    if not case_ids:
        raise HTTPException(status_code=400, detail="Inga giltiga filer i uppladdningen")

    return JSONResponse({
        "case_ids": case_ids,
        "multi": len(case_ids) > 1,
        "case_count": len(case_ids),
    })


@app.get("/api/cases/{case_id}/status")
async def api_case_status(case_id: str) -> JSONResponse:
    """State + jobblista för polling under analys."""
    async with lodet_db.SessionLocal() as session:
        case = await session.get(lodet_db.Case, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Case hittades inte")
        jobs = await jobq.jobs_for_case(session, case_id)
    return JSONResponse({
        "case_id": case_id,
        "state": case.state,
        "state_label": case_states.LABELS.get(case.state, case.state),
        "jobs": jobs,
    })


@app.get("/api/cases/{case_id}/result")
async def api_case_result(case_id: str) -> JSONResponse:
    """Analysresultat i samma form som gamla synkrona /api/package/analyze."""
    case = await case_archive.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case hittades inte")
    analysis = case.get("analysis") or {
        "summary": case.get("summary") or {},
        "files": case.get("files") or [],
        "narrative": (case.get("summary") or {}).get("agent_summary") or "",
        "recommendations": [],
        "ue_suggestions": [],
    }
    return JSONResponse({
        "analysis": analysis,
        "parsed_mf": case.get("parsed_mf"),
        "saved_case": {
            "id": case["id"],
            "state": case.get("state"),
            "lessons": case.get("lessons") or [],
            "required_docs": case.get("required_docs") or [],
            "insights": case.get("insights"),
            "project_name": case.get("project_name"),
        },
    })


@app.get("/api/cases/{case_id}/events")
async def api_case_events(case_id: str) -> JSONResponse:
    """Audit-tidslinje för ett case (senaste först)."""
    events = await case_archive.list_events(case_id)
    return JSONResponse({"events": events})


# --- Granskning (AP2) -------------------------------------------------------

REVIEW_RED = 0.7
REVIEW_YELLOW = 0.9

_REVIEW_EDITABLE = {"ama_code", "description", "unit", "quantity", "unit_price"}


def _review_line_dict(row: lodet_db.MfLine) -> dict:
    meta = row.meta or {}
    return {
        "id": row.id,
        "position": row.position,
        "ama_code": row.ama_code,
        "description": row.description,
        "unit": row.unit,
        "quantity": row.quantity,
        "unit_price": row.unit_price,
        "total_amount": row.total,
        "is_lump_sum": bool(meta.get("is_lump_sum")),
        "confidence": row.confidence,
        "extraction_method": row.extraction_method,
        "reviewed_by_user": row.reviewed_by_user,
        "source": row.source,
        "original_values": row.original_values,
    }


async def _recompute_case_total(session, case_id: str) -> float:
    totals = (await session.execute(
        sa_select(lodet_db.MfLine.total).where(lodet_db.MfLine.case_id == case_id)
    )).scalars().all()
    total = round(sum(t for t in totals if t), 2)
    case = await session.get(lodet_db.Case, case_id)
    if case is not None:
        case.total_amount_sek = total
        meta = case.meta or {}
        mfm = dict(meta.get("mf_metadata") or {})
        mfm["total_amount_sek"] = total
        case.meta = {**meta, "mf_metadata": mfm}
    return total


@app.get("/api/cases/{case_id}/review")
async def api_case_review(case_id: str) -> JSONResponse:
    """Granskningsvyns data: rader med confidence/spans + ev. käll-PDF."""
    async with lodet_db.SessionLocal() as session:
        case = await session.get(lodet_db.Case, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Case hittades inte")
        rows = (await session.execute(
            sa_select(lodet_db.MfLine)
            .where(lodet_db.MfLine.case_id == case_id)
            .order_by(lodet_db.MfLine.position)
        )).scalars().all()
        docs = (await session.execute(
            sa_select(lodet_db.Document).where(
                lodet_db.Document.case_id == case_id,
                lodet_db.Document.doc_type == "mf",
            )
        )).scalars().all()

    pdf_doc = next(
        (d for d in docs if (d.storage_path or "").lower().endswith(".pdf")), None
    )
    return JSONResponse({
        "case_id": case_id,
        "state": case.state,
        "state_label": case_states.LABELS.get(case.state, case.state),
        "project_name": case.project_name,
        "thresholds": {"red": REVIEW_RED, "yellow": REVIEW_YELLOW},
        "lines": [_review_line_dict(r) for r in rows],
        "pdf_document": {
            "id": pdf_doc.id,
            "filename": pdf_doc.filename,
            "url": f"/api/cases/{case_id}/file/{pdf_doc.id}",
        } if pdf_doc else None,
    })


@app.put("/api/cases/{case_id}/review/lines/{line_id}")
async def api_review_line_update(case_id: str, line_id: str, payload: dict = Body(...)) -> JSONResponse:
    """Spara en granskad/rättad rad. AI:ns ursprungsvärden bevaras i
    original_values (= träningsdata, AP6-flywheel)."""
    async with lodet_db.SessionLocal() as session:
        row = await session.get(lodet_db.MfLine, line_id)
        if row is None or row.case_id != case_id:
            raise HTTPException(status_code=404, detail="Raden hittades inte")

        changed: list[str] = []
        originals = dict(row.original_values or {})
        for key in _REVIEW_EDITABLE & set(payload.keys()):
            value = payload[key]
            if key in ("quantity", "unit_price"):
                value = None if value in (None, "") else float(value)
            else:
                value = (str(value).strip() or None) if value is not None else None
            old = getattr(row, key)
            if old != value:
                if key not in originals:
                    originals[key] = old
                setattr(row, key, value)
                changed.append(key)

        meta = row.meta or {}
        if not meta.get("is_lump_sum"):
            if row.quantity is not None and row.unit_price is not None:
                row.total = round(row.quantity * row.unit_price, 2)
            else:
                row.total = None

        row.reviewed_by_user = True
        row.confidence = 1.0
        if changed:
            row.original_values = originals

        total = await _recompute_case_total(session, case_id)
        await lodet_db.log_event(session, case_id, "user_edit", {
            "what": "review_line", "line_id": line_id, "fields": changed,
        })
        await session.commit()
        await session.refresh(row)
        return JSONResponse({"line": _review_line_dict(row), "total_amount_sek": total})


@app.post("/api/cases/{case_id}/review/approve")
async def api_review_approve(case_id: str, payload: dict = Body(default={})) -> JSONResponse:
    """Godkänn rader utan ändring — alla över min_confidence, eller givna ids."""
    line_ids = payload.get("line_ids")
    min_conf = float(payload.get("min_confidence", REVIEW_YELLOW))

    async with lodet_db.SessionLocal() as session:
        q = sa_select(lodet_db.MfLine).where(
            lodet_db.MfLine.case_id == case_id,
            lodet_db.MfLine.reviewed_by_user.is_(False),
        )
        rows = (await session.execute(q)).scalars().all()
        approved = 0
        for row in rows:
            if line_ids is not None:
                if row.id not in line_ids:
                    continue
            elif row.confidence < min_conf:
                continue
            row.reviewed_by_user = True
            approved += 1
        if approved:
            await lodet_db.log_event(session, case_id, "user_edit", {
                "what": "approve_lines", "count": approved,
            })
        await session.commit()
    return JSONResponse({"approved": approved})


@app.post("/api/cases/{case_id}/review/complete")
async def api_review_complete(case_id: str) -> JSONResponse:
    """Slutför granskningen: kräver att inga ogranskade rader ligger under
    gult — annars 409. NEEDS_REVIEW → CALCULATING via statemaskinen."""
    async with lodet_db.SessionLocal() as session:
        case = await session.get(lodet_db.Case, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Case hittades inte")

        rows = (await session.execute(
            sa_select(lodet_db.MfLine).where(
                lodet_db.MfLine.case_id == case_id,
                lodet_db.MfLine.reviewed_by_user.is_(False),
            )
        )).scalars().all()
        blockers = sum(1 for r in rows if r.confidence < REVIEW_YELLOW)
        if blockers:
            raise HTTPException(
                status_code=409,
                detail=f"{blockers} rader under konfidens-tröskeln är ogranskade",
            )

        if case.state == case_states.NEEDS_REVIEW:
            await case_states.transition(session, case, case_states.CALCULATING)
        await session.commit()
        return JSONResponse({
            "state": case.state,
            "state_label": case_states.LABELS.get(case.state, case.state),
        })


# --- Kravmatris (AP3) -------------------------------------------------------

def _requirement_dict(r: lodet_db.Requirement) -> dict:
    return {
        "id": r.id,
        "position": r.position,
        "af_code": r.af_code,
        "kind": r.kind,
        "text": r.text,
        "response_format": r.response_format,
        "deadline": r.deadline,
        "source": r.source,
        "confidence": r.confidence,
        "status": r.status,
        "reviewed_by_user": r.reviewed_by_user,
    }


@app.get("/api/cases/{case_id}/krav")
async def api_case_krav(case_id: str) -> JSONResponse:
    """Kravmatrisen: källänkade krav grupperade per AF-huvuddel + räknare."""
    from app.af_parser import HUVUDDELAR

    async with lodet_db.SessionLocal() as session:
        case = await session.get(lodet_db.Case, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Case hittades inte")
        rows = (await session.execute(
            sa_select(lodet_db.Requirement)
            .where(lodet_db.Requirement.case_id == case_id)
            .order_by(lodet_db.Requirement.position)
        )).scalars().all()
        docs = (await session.execute(
            sa_select(lodet_db.Document).where(
                lodet_db.Document.case_id == case_id,
                lodet_db.Document.doc_type == "af",
            )
        )).scalars().all()

    af_doc = next((d for d in docs if (d.storage_path or "").lower().endswith(".pdf")), None)

    reqs = [_requirement_dict(r) for r in rows]
    skall = [r for r in reqs if r["kind"] == "skall"]
    answered = [r for r in reqs if r["status"] in ("answered", "na")]
    counts = {
        "total": len(reqs),
        "skall": len(skall),
        "skall_answered": sum(1 for r in skall if r["status"] in ("answered", "na")),
        "answered": len(answered),
        "unverified": sum(1 for r in reqs if not (r.get("source") or {}).get("verified")),
        "per_kind": {},
    }
    for r in reqs:
        counts["per_kind"][r["kind"]] = counts["per_kind"].get(r["kind"], 0) + 1

    return JSONResponse({
        "case_id": case_id,
        "state": case.state,
        "project_name": case.project_name,
        "counts": counts,
        "huvuddelar": HUVUDDELAR,
        "requirements": reqs,
        "af_document": {
            "id": af_doc.id,
            "filename": af_doc.filename,
            "url": f"/api/cases/{case_id}/file/{af_doc.id}",
        } if af_doc else None,
    })


@app.put("/api/cases/{case_id}/krav/{req_id}")
async def api_case_krav_update(case_id: str, req_id: str, payload: dict = Body(...)) -> JSONResponse:
    """Uppdatera status på ett krav (unanswered|answered|na)."""
    status = payload.get("status")
    if status not in ("unanswered", "answered", "na"):
        raise HTTPException(status_code=400, detail="status måste vara unanswered, answered eller na")

    async with lodet_db.SessionLocal() as session:
        row = await session.get(lodet_db.Requirement, req_id)
        if row is None or row.case_id != case_id:
            raise HTTPException(status_code=404, detail="Kravet hittades inte")
        row.status = status
        row.reviewed_by_user = True
        await lodet_db.log_event(session, case_id, "user_edit", {
            "what": "requirement_status", "req_id": req_id, "status": status,
        })
        await session.commit()
        await session.refresh(row)
        return JSONResponse({"requirement": _requirement_dict(row)})


@app.get("/api/cases/{case_id}/file/{doc_id}")
async def api_case_file(case_id: str, doc_id: str) -> FileResponse:
    """Servera en lagrad originalfil (för PDF-panelen i granskningsvyn)."""
    async with lodet_db.SessionLocal() as session:
        doc = await session.get(lodet_db.Document, doc_id)
    if doc is None or doc.case_id != case_id or not doc.storage_path:
        raise HTTPException(status_code=404, detail="Filen hittades inte")
    path = lodet_db.DATA_ROOT / doc.storage_path
    if not path.exists():
        raise HTTPException(status_code=404, detail="Filen saknas på volymen")
    return FileResponse(path, filename=doc.filename)


# --- Kunskapsbas (sparade cases) ------------------------------------------

@app.get("/api/cases")
async def api_cases_list() -> JSONResponse:
    return JSONResponse({"cases": await case_archive.list_cases_summary()})


@app.get("/api/cases/{case_id}")
async def api_case_get(case_id: str) -> JSONResponse:
    case = await case_archive.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case hittades inte")
    return JSONResponse(case)


@app.delete("/api/cases/{case_id}")
async def api_case_delete(case_id: str) -> JSONResponse:
    if not await case_archive.delete_case(case_id):
        raise HTTPException(status_code=404, detail="Case hittades inte")
    return JSONResponse({"deleted": case_id})


# --- Resursbibliotek ------------------------------------------------------

@app.get("/api/resources")
async def api_resources_list() -> JSONResponse:
    return JSONResponse({
        "resources": resource_library.list_resources(),
        "types": resource_library.RESOURCE_TYPES,
    })


@app.post("/api/resources")
async def api_resources_create(payload: dict = Body(...)) -> JSONResponse:
    try:
        res = resource_library.create_resource(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(res)


@app.put("/api/resources/{resource_id}")
async def api_resources_update(resource_id: str, payload: dict = Body(...)) -> JSONResponse:
    try:
        res = resource_library.update_resource(resource_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if res is None:
        raise HTTPException(status_code=404, detail="Resursen hittades inte")
    return JSONResponse(res)


@app.delete("/api/resources/{resource_id}")
async def api_resources_delete(resource_id: str) -> JSONResponse:
    if not resource_library.delete_resource(resource_id):
        raise HTTPException(status_code=404, detail="Resursen hittades inte")
    return JSONResponse({"deleted": resource_id})


@app.post("/api/resources/seed")
async def api_resources_seed() -> JSONResponse:
    added = resource_library.seed_defaults()
    return JSONResponse({"added": added})


@app.post("/api/resources/calculate")
async def api_resources_calculate(payload: dict = Body(...)) -> JSONResponse:
    """Räkna ut totalkostnad/à-pris för en lista av resurser kopplade till en MF-rad."""
    line_resources = payload.get("resources") or []
    line_quantity = payload.get("line_quantity")
    result = resource_library.calculate_line(line_resources, line_quantity)
    return JSONResponse(result)


# --- Företagsinställningar ------------------------------------------------

@app.get("/api/company")
async def api_company_get() -> JSONResponse:
    return JSONResponse(company_settings.get_settings())


@app.put("/api/company")
async def api_company_put(payload: dict = Body(...)) -> JSONResponse:
    saved = company_settings.save_settings(payload)
    return JSONResponse({"saved": True, "settings": saved})


# --- Anbudsutkast (drafts per case) ---------------------------------------

def _build_draft_text(case: dict, doc_id: str, doc_meta: dict) -> str:
    """Generera utkast-text för ett krav i ett case. Auto-fyller från
    företagsinställningar och MF-totalbelopp där det är tillgängligt."""
    company = company_settings.get_settings()

    project_name = case.get("project_name") or "—"
    document_number = case.get("document_number") or "—"
    customer = case.get("customer") or company.get("default_customer") or "—"

    # Anbudssumma: använd alltid den senaste totalen från MF om finns
    parsed_mf = case.get("parsed_mf") or {}
    mf_meta = parsed_mf.get("metadata") or {}
    total = mf_meta.get("total_amount_sek") or case.get("total_amount_sek") or 0.0

    company_name = company.get("company_name") or "[ANBUDSGIVARE — fyll i under Inställningar / Företagsinfo]"
    contact_name = company.get("contact_name") or ""
    contact_email = company.get("contact_email") or ""
    contact_phone = company.get("contact_phone") or ""
    organisationsnummer = company.get("organisationsnummer") or ""

    if doc_id == "anbudssumma":
        return afb.anbudssumma(
            project_name=project_name,
            document_number=document_number,
            company_name=company_name,
            total_amount=float(total),
            contact_name=contact_name,
            contact_email=contact_email,
            contact_phone=contact_phone,
        )
    if doc_id == "ue-lista":
        return afb.ue_lista(project_name=project_name, company_name=company_name)
    if doc_id == "sekretess":
        return afb.sekretessbegaran(
            project_name=project_name,
            document_number=document_number,
            company_name=company_name,
            organisationsnummer=organisationsnummer,
            contact_name=contact_name,
        )
    if doc_id == "missiv":
        return afb.missiv(
            project_name=project_name,
            document_number=document_number,
            company_name=company_name,
            customer_name=customer,
            contact_name=contact_name,
        )

    # Okänt krav — generisk platsmall
    title = doc_meta.get("title") or doc_id
    description = doc_meta.get("description") or ""
    code = doc_meta.get("code") or ""
    code_line = f"{code}  " if code else ""

    return f"""{code_line}{title.upper()}

Projekt:        {project_name}
Dokumentnr:     {document_number}
Anbudsgivare:   {company_name}

{description}

[Fyll i innehållet enligt förfrågningsunderlagets krav.]


Datum:          {datetime.now().strftime('%Y-%m-%d')}

Kontaktperson:  {contact_name or '________________________'}
Underskrift:    ________________________________________
"""


@app.get("/api/cases/{case_id}/drafts")
async def api_case_drafts(case_id: str) -> JSONResponse:
    """Lista required_docs + status (genererat/redigerat) för ett case."""
    case = await case_archive.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case hittades inte")

    drafts = case.get("drafts") or {}
    required = case.get("required_docs") or []

    items = []
    for doc in required:
        d = drafts.get(doc["id"])
        items.append({
            **doc,
            "is_known_template": requirement_extractor.is_known_template(doc["id"]),
            "is_mf": requirement_extractor.is_mf(doc["id"]),
            "status": "edited" if (d and d.get("edited_at")) else ("generated" if d else "pending"),
            "generated_at": d.get("generated_at") if d else None,
            "edited_at": d.get("edited_at") if d else None,
            "preview": (d.get("text") or "")[:160] if d else "",
        })

    return JSONResponse({
        "case_id": case_id,
        "project_name": case.get("project_name"),
        "required_docs": items,
        "has_mf": bool(case.get("parsed_mf")),
    })


@app.post("/api/cases/{case_id}/draft/{doc_id}")
async def api_case_draft_generate(case_id: str, doc_id: str) -> JSONResponse:
    """Generera (eller återgenerera) utkast för ett krav i ett case."""
    case = await case_archive.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case hittades inte")

    if doc_id == "mf":
        raise HTTPException(status_code=400, detail="MF hämtas som Excel via /api/cases/{id}/mf/excel")

    required = case.get("required_docs") or []
    doc_meta = next((d for d in required if d.get("id") == doc_id), None)
    if doc_meta is None:
        # Tillåt generering även för okända id om de skickas — använd doc_id som titel
        doc_meta = {"id": doc_id, "title": doc_id, "description": "", "code": ""}

    text = _build_draft_text(case, doc_id, doc_meta)
    await case_archive.update_draft(case_id, doc_id, text, edited=False)

    return JSONResponse({
        "case_id": case_id,
        "doc_id": doc_id,
        "text": text,
        "status": "generated",
    })


@app.put("/api/cases/{case_id}/draft/{doc_id}")
async def api_case_draft_update(case_id: str, doc_id: str, payload: dict = Body(...)) -> JSONResponse:
    """Spara redigerad utkast-text."""
    case = await case_archive.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case hittades inte")

    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text saknas")

    await case_archive.update_draft(case_id, doc_id, text, edited=True)
    return JSONResponse({"case_id": case_id, "doc_id": doc_id, "status": "edited"})


@app.get("/api/cases/{case_id}/draft/{doc_id}/pdf")
async def api_case_draft_pdf(case_id: str, doc_id: str) -> Response:
    """Returnera utkastet som PDF. Genererar text on-demand om inget sparat utkast finns."""
    case = await case_archive.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case hittades inte")

    draft = (case.get("drafts") or {}).get(doc_id)
    text = draft.get("text") if draft else None

    if not text:
        required = case.get("required_docs") or []
        doc_meta = next((d for d in required if d.get("id") == doc_id), None) or {
            "id": doc_id, "title": doc_id, "description": "", "code": "",
        }
        text = _build_draft_text(case, doc_id, doc_meta)
        await case_archive.update_draft(case_id, doc_id, text, edited=False)

    required = case.get("required_docs") or []
    doc_meta = next((d for d in required if d.get("id") == doc_id), {})
    title = doc_meta.get("title") or doc_id
    project = case.get("project_name") or "—"

    pdf_bytes = pdf_renderer.text_to_pdf(
        text=text,
        title=f"{title} — {project}",
        subtitle=case.get("document_number") or "",
    )

    project_slug = (case.get("project_name") or "anbud").replace(" ", "_").replace(",", "").replace("/", "-")
    filename = f"Lodet_{doc_id}_{project_slug}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@app.get("/api/cases/{case_id}/mf")
async def api_case_mf_get(case_id: str) -> JSONResponse:
    """Hämta nuvarande mängdförteckning för ett case (för editor)."""
    case = await case_archive.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case hittades inte")

    parsed_mf = case.get("parsed_mf")
    if not parsed_mf:
        raise HTTPException(status_code=404, detail="Ingen mängdförteckning hittades i detta case")

    return JSONResponse(parsed_mf)


@app.put("/api/cases/{case_id}/mf")
async def api_case_mf_update(case_id: str, payload: dict = Body(...)) -> JSONResponse:
    """Spara redigerad mängdförteckning (à-priser/belopp). Räknar om totalbelopp."""
    case = await case_archive.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case hittades inte")

    parsed_mf = payload.get("parsed_mf")
    if not isinstance(parsed_mf, dict):
        raise HTTPException(status_code=400, detail="parsed_mf saknas eller har fel format")

    lines = parsed_mf.get("lines") or []

    # Räkna om belopp per rad och totalbelopp baserat på unit_price * quantity
    total = 0.0
    for line in lines:
        if line.get("is_lump_sum"):
            amount = line.get("total_amount")
            total += amount or 0
            continue
        qty = line.get("quantity")
        price = line.get("unit_price")
        if qty is not None and price is not None:
            amount = round(float(qty) * float(price), 2)
            line["total_amount"] = amount
            total += amount

    meta = parsed_mf.get("metadata") or {}
    meta["total_amount_sek"] = round(total, 2)
    parsed_mf["metadata"] = meta

    if not await case_archive.update_parsed_mf(case_id, parsed_mf):
        raise HTTPException(status_code=500, detail="Kunde inte spara MF")

    return JSONResponse({
        "case_id": case_id,
        "total_amount_sek": round(total, 2),
        "line_count": len(lines),
        "saved_at": _local_timestamp(),
    })


@app.get("/api/cases/{case_id}/mf/csv")
async def api_case_mf_csv(case_id: str) -> Response:
    """Returnera MF som semikolon-separerad CSV (öppnas direkt i Google Sheets)."""
    case = await case_archive.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case hittades inte")

    parsed_mf = case.get("parsed_mf")
    if not parsed_mf:
        raise HTTPException(status_code=404, detail="Ingen mängdförteckning hittades i detta case")

    import csv as _csv
    import io as _io

    buf = _io.StringIO()
    buf.write("﻿")  # BOM så Excel/Sheets förstår UTF-8
    writer = _csv.writer(buf, delimiter=";", quoting=_csv.QUOTE_MINIMAL)
    writer.writerow(["AMA-kod", "Beskrivning", "Enhet", "Antal", "À-pris", "Belopp"])

    for line in parsed_mf.get("lines", []):
        writer.writerow([
            line.get("ama_code") or "",
            line.get("description") or "",
            line.get("unit") or "",
            "" if line.get("quantity") is None else line["quantity"],
            "" if line.get("unit_price") is None else line["unit_price"],
            "" if line.get("total_amount") is None else line["total_amount"],
        ])

    project_slug = (case.get("project_name") or "anbud").replace(" ", "_").replace(",", "").replace("/", "-")
    filename = f"Lodet_MF_{project_slug}.csv"

    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@app.get("/api/cases/{case_id}/mf/excel")
async def api_case_mf_excel(case_id: str) -> Response:
    """Returnera ifylld mängdförteckning som Excel-mall."""
    case = await case_archive.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case hittades inte")

    parsed_mf = case.get("parsed_mf")
    if not parsed_mf:
        raise HTTPException(status_code=404, detail="Ingen mängdförteckning hittades i detta case")

    xlsx = build_workbook(parsed_mf, generated_at=_local_timestamp())
    project_slug = (case.get("project_name") or "anbud").replace(" ", "_").replace(",", "").replace("/", "-")
    filename = f"Lodet_MF_{project_slug}.xlsx"

    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@app.post("/api/ue/email")
async def api_ue_email(
    areas: str = Form(...),
    project_name: str = Form("VÄG 875, GC SUNDBORN"),
    document_number: str = Form("1E12MF10"),
    company_name: str = Form("Westcon Entreprenad AB"),
    contact_name: str = Form(""),
    contact_email: str = Form(""),
    contact_phone: str = Form(""),
    bid_due: str = Form(""),
    relevant_codes: str = Form(""),
) -> JSONResponse:
    area_list = [a.strip() for a in areas.split(",") if a.strip()]
    code_list = [c.strip() for c in relevant_codes.split(",") if c.strip()]

    drafts = ue_emailer.generate_for_areas(
        areas=area_list,
        project_name=project_name,
        document_number=document_number,
        company_name=company_name,
        contact_name=contact_name,
        contact_email=contact_email,
        contact_phone=contact_phone,
        bid_due=bid_due or None,
        relevant_codes=code_list,
    )
    return JSONResponse({"drafts": drafts, "count": len(drafts)})


# --- Dashboard / stats ----------------------------------------------------

@app.get("/api/dashboard")
async def api_dashboard() -> JSONResponse:
    """Statisk dashboard-data för MVP. I produktion: aggregeras från DB."""
    return JSONResponse(
        {
            "stats": {
                "active_bids": 3,
                "total_bid_value_sek": 27_842_000,
                "win_rate_pct": 42,
                "ama_codes_in_library": len(ama_catalog.all_codes()),
            },
            "recent_activity": [
                {
                    "type": "parse",
                    "title": "VÄG 875, GC SUNDBORN parsad",
                    "subtitle": "48 rader · 1 687 336 kr",
                    "timestamp": "2026-04-30 16:42",
                },
                {
                    "type": "win",
                    "title": "Belysning Industrigatan vunnen",
                    "subtitle": "Härnösands kommun · 2 410 000 kr",
                    "timestamp": "2026-04-28 09:15",
                },
                {
                    "type": "submit",
                    "title": "GC-väg Skogsbacken inlämnad",
                    "subtitle": "Sollefteå kommun · 4 800 000 kr",
                    "timestamp": "2026-04-27 14:00",
                },
            ],
            "upcoming_deadlines": [
                {"project": "Vägbelysning Rv 84", "customer": "Trafikverket", "due": "2026-05-12"},
                {"project": "Renovering Storgatan", "customer": "Bollnäs kommun", "due": "2026-05-19"},
            ],
        }
    )
