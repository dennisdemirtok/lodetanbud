"""
Lodet — FastAPI-app
===================
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select as sa_select
from sqlalchemy.orm.attributes import flag_modified

from app import __version__
from app import afb_templates as afb
from app import ama_catalog
from app import answer_generator
from app import autopilot
from app import case_archive
from app import chat as lodet_chat
from app import company_settings
from app import db as lodet_db
from app import db_migrate
from app import formalia
from app import jobs as jobq
from app import pdf_renderer
from app import price_engine
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
    try:
        moved = await db_migrate.migrate_sqlite_to_postgres()
        if moved:
            print(f"[lodet] {moved} rader migrerade från volymens SQLite till Postgres")
    except Exception as e:
        print(f"[lodet] sqlite→postgres-migrering misslyckades: {e}")
    try:
        migrated = await db_migrate.migrate_legacy_json()
        if migrated:
            print(f"[lodet] {migrated} legacy-JSON-cases migrerade till databasen")
    except Exception as e:
        print(f"[lodet] legacy-migrering misslyckades: {e}")
    reset = await jobq.reset_orphans()
    if reset:
        print(f"[lodet] {reset} avbrutna jobb återställda till kön")
    # Bakgrundsworkern kan stängas av i tester (LODET_DISABLE_WORKER) så att
    # dess poll-loop inte håller DB-motorn över en reload mellan testfall.
    worker_task = None
    if not os.getenv("LODET_DISABLE_WORKER"):
        worker_task = asyncio.create_task(lodet_worker.worker_loop())
    yield
    if worker_task is not None:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
    # Släpp DB-anslutningar vid shutdown (ren shutdown i prod; tar bort
    # engine-teardown-racen mellan testers reload av app.db)
    try:
        await lodet_db.engine.dispose()
    except Exception:
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
    case_id = payload.get("case_id") or None

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
        lodet_chat.stream_chat(cleaned, context=context, case_id=case_id),
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


# Generiska mappnamn som inte säger vilket PROJEKT det är
_GENERIC_FOLDER_RE = re.compile(
    r"förfrågningsunderlag|upphandlingsdokument|bilagor|ffu|anbudshandlingar|"
    r"dokument|underlag|handlingar|ritningar|mängdförteckning|växtförteckning|"
    r"beskrivning", re.IGNORECASE,
)
# Numrerad dokumentkategori-mapp: "12. Ritningar", "10_Mängdförteckning", "03 Upphandling"
_CATEGORY_FOLDER_RE = re.compile(r"^\d+[.\d]*[\s_]")


def _is_category_folder(name: str) -> bool:
    """Mappnamn som beskriver en dokumentKATEGORI, inte projektet."""
    return bool(_GENERIC_FOLDER_RE.search(name) or _CATEGORY_FOLDER_RE.match(name))


def _common_top_folder(paths: list[str]) -> str | None:
    """Bästa mappnamnet ur relativa sökvägar — första segmentet som beskriver
    PROJEKTET, inte en dokumentkategori ("1 Förfrågningsunderlag 2/Haga Entré/
    12. Ritningar/…" → "Haga Entré", aldrig "12. Ritningar")."""
    from collections import Counter
    tops = Counter()
    for p in paths:
        parts = p.replace("\\", "/").strip("/").split("/")
        if len(parts) > 1 and parts[0]:
            tops[parts[0]] += 1
    if not tops:
        return None
    top, n = tops.most_common(1)[0]
    if n < max(2, len(paths) // 2):
        return None
    if not _is_category_folder(top):
        return top
    # Toppen är en kategori-mapp — leta första icke-kategori-segment en nivå ner
    seconds = Counter()
    for p in paths:
        parts = p.replace("\\", "/").strip("/").split("/")
        if len(parts) > 2 and parts[0] == top and parts[1]:
            seconds[parts[1]] += 1
    for seg, _cnt in seconds.most_common(5):
        if not _is_category_folder(seg) and not zip_handler.is_zip_filename(seg):
            return seg
    return None  # hellre fallback till "uppladdat-paket" än en kategori-mapp


@app.post("/api/package/analyze")
async def api_package_analyze(files: list[UploadFile] = File(...)) -> JSONResponse:
    """
    Tar emot ETT förfrågningsunderlag — mapp, lösa filer och/eller ZIP:ar.
    Allt i en uppladdning blir ETT anbud (ett FFU = ett case). ZIP:ar
    extraheras in i samma paket; mappstrukturen behålls som
    klassificeringssignal i filnamnen.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Inga filer mottagna")

    pairs: list[tuple[str, bytes]] = []
    zips: list[tuple[str, int]] = []  # (basnamn, bytes) — störst vinner namnet

    for f in files:
        if not f.filename:
            continue
        data = await f.read()
        if zip_handler.is_zip_filename(f.filename):
            try:
                extracted = zip_handler.extract_zip(data)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            zips.append((f.filename.rsplit(".", 1)[0].split("/")[-1], len(data)))
            # relative_path (med mappar) som filnamn — mappnamn bär
            # klassificeringssignal (t.ex. "10. Mängdförteckning/")
            pairs.extend((x.relative_path, x.data) for x in extracted)
        else:
            pairs.append((f.filename, data))

    if not pairs:
        raise HTTPException(status_code=400, detail="Inga giltiga filer i uppladdningen")

    # Paketnamn: största icke-generiska zip:en, annars bästa mappnamnet
    zip_name = next(
        (n for n, _sz in sorted(zips, key=lambda z: -z[1]) if not _GENERIC_FOLDER_RE.search(n)),
        None,
    )
    source_name = zip_name or _common_top_folder([p for p, _ in pairs]) or "uppladdat-paket"

    case_id = await _stage_package(
        source="zip" if zips else ("folder" if len(pairs) > 1 else "single"),
        source_name=source_name,
        pairs=pairs,
    )

    return JSONResponse({"case_ids": [case_id], "multi": False, "case_count": 1})


@app.get("/api/cases/{case_id}/status")
async def api_case_status(case_id: str) -> JSONResponse:
    """State + jobblista + live-progress för polling under analys."""
    async with lodet_db.SessionLocal() as session:
        case = await session.get(lodet_db.Case, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Case hittades inte")
        jobs = await jobq.jobs_for_case(session, case_id)

        # Arbetssteg (analysis_progress-events) — senaste status per steg,
        # i den ordning stegen först dök upp
        rows = (await session.execute(
            sa_select(lodet_db.Event)
            .where(lodet_db.Event.case_id == case_id,
                   lodet_db.Event.kind == "analysis_progress")
            .order_by(lodet_db.Event.id)
        )).scalars().all()

    steps: list[dict] = []
    by_step: dict[str, dict] = {}
    for ev in rows:
        d = ev.data or {}
        key = d.get("step") or "?"
        if key in by_step:
            by_step[key].update(d)
        else:
            entry = dict(d)
            by_step[key] = entry
            steps.append(entry)

    return JSONResponse({
        "case_id": case_id,
        "state": case.state,
        "state_label": case_states.LABELS.get(case.state, case.state),
        "jobs": jobs,
        "progress": steps,
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
        "project_name": case.project_name or case.source_name,
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

    try:
        await price_engine.refresh_observations_for_case(case_id)
    except Exception:
        pass

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


# --- Prismotor (AP4) --------------------------------------------------------

@app.post("/api/price/suggest-bulk")
async def api_price_suggest_bulk(payload: dict = Body(...)) -> JSONResponse:
    """À-prisförslag för en uppsättning rader. Stateless mot editorns data:
    tar {lines: [{idx, ama_code, description, unit}], exclude_case_id}."""
    lines = payload.get("lines") or []
    exclude_case_id = payload.get("exclude_case_id")
    if len(lines) > 500:
        raise HTTPException(status_code=400, detail="max 500 rader per anrop")

    suggestions: dict = {}
    for line in lines:
        idx = line.get("idx")
        if idx is None:
            continue
        s = await price_engine.suggest(
            ama_code=(line.get("ama_code") or "").strip() or None,
            description=line.get("description"),
            unit=(line.get("unit") or "").strip() or None,
            exclude_case_id=exclude_case_id,
        )
        if s is not None:
            suggestions[str(idx)] = s

    return JSONResponse({
        "suggestions": suggestions,
        "observation_count": await price_engine.observation_count(),
    })


@app.post("/api/import/historic")
async def api_import_historic(request: Request, payload: dict = Body(...)) -> JSONResponse:
    """Backfill av historisk prisdata (MAP-kalkyler m.m.). Gateär bakom
    LODET_IMPORT_TOKEN — avstängd om env-variabeln saknas, så ingen öppen
    skriv-endpoint på produktion."""
    token = os.getenv("LODET_IMPORT_TOKEN")
    if not token:
        raise HTTPException(status_code=503, detail="Import är inte aktiverad (LODET_IMPORT_TOKEN saknas)")
    if request.headers.get("X-Import-Token") != token:
        raise HTTPException(status_code=401, detail="Ogiltig import-token")

    project_name = (payload.get("project_name") or "").strip()
    if not project_name:
        raise HTTPException(status_code=400, detail="project_name saknas")
    posts = payload.get("posts") or []
    if not isinstance(posts, list) or len(posts) > 5000:
        raise HTTPException(status_code=400, detail="posts saknas eller > 5000")

    result = await price_engine.import_historic(
        project_name=project_name,
        observed_at=payload.get("observed_at"),
        region=payload.get("region"),
        posts=posts,
        source=payload.get("source") or "map_netto",
        import_key=payload.get("import_key"),
    )
    return JSONResponse(result)


@app.post("/api/cases/{case_id}/price-suggestion-applied")
async def api_price_suggestion_applied(case_id: str, payload: dict = Body(...)) -> JSONResponse:
    """Logga att ett förslag applicerades — kvalitetsmått för motorn
    (andel accepterade oförändrade följs i flywheel-rapporten, AP6)."""
    async with lodet_db.SessionLocal() as session:
        await lodet_db.log_event(session, case_id, "price_suggestion_applied", {
            "ama_code": payload.get("ama_code"),
            "suggested": payload.get("suggested"),
            "basis": payload.get("basis"),
            "n": payload.get("n"),
        })
        await session.commit()
    return JSONResponse({"ok": True})


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

    # Berika med AFB-svarsstatus ur drafts (AP5)
    full_case = await case_archive.get_case(case_id)
    drafts = (full_case or {}).get("drafts") or {}
    reqs = []
    for r in rows:
        d = _requirement_dict(r)
        ans = drafts.get(f"req:{r.id}")
        d["has_answer"] = bool(ans)
        d["answer_gaps"] = bool(ans and answer_generator.SAKNAS_RE.search(ans.get("text") or ""))
        reqs.append(d)
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
        "project_name": case.project_name or case.source_name,
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
    if status not in ("unanswered", "drafted", "answered", "na"):
        raise HTTPException(status_code=400, detail="status måste vara unanswered, drafted, answered eller na")

    async with lodet_db.SessionLocal() as session:
        row = await session.get(lodet_db.Requirement, req_id)
        if row is None or row.case_id != case_id:
            raise HTTPException(status_code=404, detail="Kravet hittades inte")
        prev_status = row.status
        row.status = status
        row.reviewed_by_user = True
        await lodet_db.log_event(session, case_id, "user_edit", {
            "what": "requirement_status", "req_id": req_id, "status": status,
        })
        await session.commit()
        await session.refresh(row)
        req_dict = _requirement_dict(row)
        answer_draft_id = row.answer_draft_id

    # När ett krav markeras besvarat och har ett genererat svar utan luckor:
    # skriv svaret till svarsbiblioteket (AP5-flywheel).
    if status == "answered" and prev_status != "answered" and answer_draft_id:
        draft = await case_archive.get_draft(case_id, answer_draft_id)
        if draft and draft.get("text"):
            await answer_generator.save_to_library(req_dict, draft["text"], source_case_id=case_id)

    return JSONResponse({"requirement": req_dict})


# --- AFB-svarsgenerering kravvis (AP5) --------------------------------------

@app.post("/api/cases/{case_id}/krav/{req_id}/answer")
async def api_generate_answer(case_id: str, req_id: str) -> JSONResponse:
    """Generera AFB-fritextsvar för ett krav. Sparas som draft (key='req:<id>'),
    kravet får answer_draft_id + status='drafted'."""
    case = await case_archive.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case hittades inte")

    async with lodet_db.SessionLocal() as session:
        row = await session.get(lodet_db.Requirement, req_id)
        if row is None or row.case_id != case_id:
            raise HTTPException(status_code=404, detail="Kravet hittades inte")
        requirement = _requirement_dict(row)

    result = await answer_generator.generate_answer(case, requirement)
    draft_key = f"req:{req_id}"
    await case_archive.update_draft(case_id, draft_key, result["answer"], edited=False)

    async with lodet_db.SessionLocal() as session:
        row = await session.get(lodet_db.Requirement, req_id)
        if row is not None:
            row.answer_draft_id = draft_key
            if row.status == "unanswered":
                row.status = "drafted"
            await session.commit()

    return JSONResponse({
        "case_id": case_id,
        "req_id": req_id,
        "answer": result["answer"],
        "missing": result["missing"],
        "sources_used": result["sources_used"],
        "library_used": result["library_used"],
        "draft_key": draft_key,
    })


@app.put("/api/cases/{case_id}/krav/{req_id}/answer")
async def api_save_answer(case_id: str, req_id: str, payload: dict = Body(...)) -> JSONResponse:
    """Spara redigerat AFB-svar."""
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text saknas")

    async with lodet_db.SessionLocal() as session:
        row = await session.get(lodet_db.Requirement, req_id)
        if row is None or row.case_id != case_id:
            raise HTTPException(status_code=404, detail="Kravet hittades inte")

    draft_key = f"req:{req_id}"
    await case_archive.update_draft(case_id, draft_key, text, edited=True)

    async with lodet_db.SessionLocal() as session:
        row = await session.get(lodet_db.Requirement, req_id)
        if row is not None and not row.answer_draft_id:
            row.answer_draft_id = draft_key
            await session.commit()

    has_gaps = bool(answer_generator.SAKNAS_RE.search(text))
    return JSONResponse({"case_id": case_id, "req_id": req_id, "has_gaps": has_gaps})


@app.get("/api/cases/{case_id}/krav/{req_id}/answer")
async def api_get_answer(case_id: str, req_id: str) -> JSONResponse:
    """Hämta sparat AFB-svar för ett krav."""
    draft = await case_archive.get_draft(case_id, f"req:{req_id}")
    if draft is None:
        return JSONResponse({"text": None})
    return JSONResponse({
        "text": draft.get("text"),
        "edited_at": draft.get("edited_at"),
        "has_gaps": bool(answer_generator.SAKNAS_RE.search(draft.get("text") or "")),
    })


@app.post("/api/cases/{case_id}/insights/answer")
async def api_answer_insight_question(case_id: str, payload: dict = Body(...)) -> JSONResponse:
    """Spara användarens svar på en av agentens frågor. Svaret blir
    projektspecifik fakta som svarsgeneratorn och chatt-agenten använder."""
    index = payload.get("index")
    answer = (payload.get("answer") or "").strip()
    if not isinstance(index, int) or not answer:
        raise HTTPException(status_code=400, detail="index (int) och answer krävs")

    async with lodet_db.SessionLocal() as session:
        case = await session.get(lodet_db.Case, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Case hittades inte")

        meta = dict(case.meta or {})
        insights = dict(meta.get("insights") or {})
        questions = list(insights.get("questions") or [])
        if not (0 <= index < len(questions)) or not isinstance(questions[index], dict):
            raise HTTPException(status_code=404, detail="Frågan hittades inte")

        questions[index] = {
            **questions[index],
            "answer": answer,
            "answered_at": datetime.now(timezone.utc).isoformat(),
        }
        insights["questions"] = questions
        meta["insights"] = insights
        case.meta = meta
        flag_modified(case, "meta")

        await lodet_db.log_event(session, case_id, "user_edit", {
            "what": "insight_question_answered",
            "question": (questions[index].get("question") or "")[:200],
        })
        await session.commit()

    return JSONResponse({"ok": True, "index": index})


# --- Per-anbud översikt (cockpit) -------------------------------------------

@app.get("/api/cases/{case_id}/overview")
async def api_case_overview(case_id: str) -> JSONResponse:
    """Cockpit för ett anbud: nyckeltal + härledd att-göra-lista + formalia.
    Checklistan är arbetsflödet (granska→prissätt→besvara→bilagor→firma→
    lämna in), bockas av deterministiskt ur state. Detta är både
    'TODO efter uppladdning' och 'projektöversikt'."""
    case = await case_archive.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case hittades inte")

    parsed_mf = case.get("parsed_mf") or {}
    lines = parsed_mf.get("lines") or []
    priced = [l for l in lines if l.get("unit_price") is not None]
    mf_total = (parsed_mf.get("metadata") or {}).get("total_amount_sek") or case.get("total_amount_sek")
    low_conf = sum(1 for l in lines if (l.get("confidence") if l.get("confidence") is not None else 1.0) < 0.9)

    async with lodet_db.SessionLocal() as session:
        reqs = (await session.execute(
            sa_select(lodet_db.Requirement).where(lodet_db.Requirement.case_id == case_id)
        )).scalars().all()
    skall = [r for r in reqs if r.kind == "skall"]
    bilagor = [r for r in reqs if r.kind == "bilaga"]
    answered = [r for r in reqs if r.status in ("answered", "na")]
    skall_answered = [r for r in skall if r.status in ("answered", "na")]
    drafts = case.get("drafts") or {}
    company = company_settings.get_settings()

    state = case.get("state")
    has_mf = len(lines) > 0
    bilaga_done = sum(1 for r in bilagor if r.status == "na"
                      or (r.af_code and r.af_code.lower() in drafts) or r.answer_draft_id)

    # Att-göra-lista (arbetsflöde). done = klart; current sätts på första ej klara.
    checklist: list[dict] = []
    if low_conf > 0 or state == case_states.NEEDS_REVIEW:
        checklist.append({
            "key": "review", "label": "Granska extraktionen",
            "detail": f"{low_conf} rader under konfidens-tröskeln behöver bekräftas" if low_conf else "Bekräfta de extraherade raderna",
            "done": state not in (case_states.NEEDS_REVIEW, case_states.EXTRACTING, case_states.INTAKE),
            "route": f"#/granska/{case_id}",
        })
    if has_mf:
        checklist.append({
            "key": "price", "label": "Prissätt mängdförteckningen",
            "detail": f"{len(priced)}/{len(lines)} rader prissatta" + (f" · {round(mf_total):,} kr".replace(",", " ") if mf_total else ""),
            "done": len(lines) > 0 and len(priced) == len(lines),
            "route": f"#/kalkylator/{case_id}",
        })
    if skall:
        checklist.append({
            "key": "skall", "label": "Besvara skall-kraven",
            "detail": f"{len(skall_answered)}/{len(skall)} besvarade",
            "done": len(skall_answered) == len(skall),
            "route": f"#/krav/{case_id}",
        })
    if bilagor:
        checklist.append({
            "key": "bilagor", "label": "Koppla bilagor",
            "detail": f"{bilaga_done}/{len(bilagor)} bilagekrav har dokument",
            "done": bilaga_done == len(bilagor),
            "route": f"#/krav/{case_id}",
        })
    checklist.append({
        "key": "firma", "label": "Fyll i företag & firmatecknare",
        "detail": f"{company.get('company_name')}" if company.get("company_name") and company.get("contact_name")
                  else "Saknas — fyll i under Inställningar",
        "done": bool(company.get("company_name") and company.get("contact_name")),
        "route": "#/inst/foretag",
    })
    checklist.append({
        "key": "submit", "label": "Kör formaliakontroll & lämna in",
        "detail": "Sista kontrollen innan inlämning",
        "done": state in (case_states.SUBMITTED, case_states.AWARDED, case_states.LOST),
        "route": f"#/slutfor/{case_id}",
    })

    done_count = sum(1 for c in checklist if c["done"])
    next_step = next((c for c in checklist if not c["done"]), None)

    busy = state in (case_states.INTAKE, case_states.EXTRACTING)
    gate = None if busy else await formalia.run_gate(case)

    return JSONResponse({
        "case_id": case_id,
        "project_name": case.get("project_name") or case.get("source_name"),
        "document_number": case.get("document_number"),
        "customer": case.get("customer"),
        "state": state,
        "state_label": case_states.LABELS.get(state, state),
        "created_at": case.get("created_at"),
        "bid_due_at": (parsed_mf.get("metadata") or {}).get("bid_due_at") or case.get("bid_due_at"),
        "stats": {
            "mf_rows": len(lines),
            "mf_priced": len(priced),
            "mf_total_sek": round(mf_total) if mf_total else None,
            "krav_total": len(reqs),
            "krav_skall": len(skall),
            "krav_answered": len(answered),
            "file_count": len(case.get("files") or []),
        },
        "checklist": checklist,
        "progress": round(100 * done_count / len(checklist)) if checklist else 0,
        "next_step": {"label": next_step["label"], "route": next_step["route"]} if next_step else None,
        "formalia": {"passed": gate["passed"], "blocking_count": gate["blocking_count"]} if gate else None,
        "busy": busy,
    })


@app.post("/api/cases/{case_id}/autopilot")
async def api_autopilot(case_id: str) -> JSONResponse:
    """Driv anbudet framåt: agenten kör de säkra stegen autonomt och pausar
    vid första checkpoint som kräver din input (UE, firmatecknare)."""
    result = await autopilot.run(case_id)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return JSONResponse(result)


@app.post("/api/cases/{case_id}/ue")
async def api_save_ue(case_id: str, payload: dict = Body(...)) -> JSONResponse:
    """Spara UE-tilldelningar (område → företag/e-post) på anbudet, och lär in
    dem i företagsbiblioteket så de förfylls nästa gång (flywheel)."""
    assignments = payload.get("assignments")
    if not isinstance(assignments, dict):
        raise HTTPException(status_code=400, detail="assignments (område → {company,email}) krävs")

    async with lodet_db.SessionLocal() as session:
        case = await session.get(lodet_db.Case, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Case hittades inte")
        meta = dict(case.meta or {})
        meta["ue_assignments"] = assignments
        case.meta = meta
        flag_modified(case, "meta")
        await lodet_db.log_event(session, case_id, "user_edit",
                                 {"what": "ue_assignments", "areas": list(assignments.keys())})
        await session.commit()

    # Flywheel: lär in område → företag i företagsbiblioteket
    try:
        settings = company_settings.get_settings()
        lib = dict(settings.get("ue_contacts") or {})
        for area, a in assignments.items():
            if (a or {}).get("company"):
                lib[area] = {"company": a["company"], "email": a.get("email") or ""}
        company_settings.save_settings({"ue_contacts": lib})
    except Exception:
        pass

    return JSONResponse({"ok": True, "areas": len(assignments)})


# --- Formaliagrind + state-flöde (AP5) --------------------------------------

@app.patch("/api/cases/{case_id}")
async def api_case_patch(case_id: str, payload: dict = Body(...)) -> JSONResponse:
    """Redigera anbudets grundfält (projektnamn, kund, dok-nr). Auto-extraktion
    ur tender-dokument är best-effort — användaren kan alltid rätta namnet,
    precis som 'rename matter' i Harvey/Legora."""
    editable = {"project_name", "customer", "document_number"}
    updates = {k: (str(v).strip() or None) for k, v in payload.items() if k in editable}
    if not updates:
        raise HTTPException(status_code=400, detail=f"Inga redigerbara fält (tillåtna: {sorted(editable)})")
    async with lodet_db.SessionLocal() as session:
        case = await session.get(lodet_db.Case, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Case hittades inte")
        for k, v in updates.items():
            setattr(case, k, v)
        await lodet_db.log_event(session, case_id, "user_edit", {"what": "case_fields", "fields": list(updates)})
        await session.commit()
    return JSONResponse({"ok": True, **updates})


@app.get("/api/cases/{case_id}/formalia")
async def api_formalia(case_id: str) -> JSONResponse:
    """Kör formaliagrindens checklista (deterministisk)."""
    case = await case_archive.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case hittades inte")
    result = await formalia.run_gate(case)
    result["case_id"] = case_id
    result["state"] = case.get("state")
    return JSONResponse(result)


@app.post("/api/cases/{case_id}/advance")
async def api_advance(case_id: str, payload: dict = Body(default={})) -> JSONResponse:
    """Driv anbudet framåt i statemaskinen för stegen som inte har egen grind:
    CALCULATING→DRAFTING→FORMALIA_CHECK. READY nås bara via /finalize."""
    target = payload.get("to")
    allowed_targets = {case_states.DRAFTING, case_states.FORMALIA_CHECK, case_states.CALCULATING}
    if target not in allowed_targets:
        raise HTTPException(status_code=400, detail=f"to måste vara en av {sorted(allowed_targets)}")

    async with lodet_db.SessionLocal() as session:
        case = await session.get(lodet_db.Case, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Case hittades inte")
        try:
            await case_states.transition(session, case, target)
        except case_states.IllegalTransition as e:
            raise HTTPException(status_code=409, detail=str(e))
        await session.commit()
        return JSONResponse({"state": case.state, "state_label": case_states.LABELS.get(case.state)})


@app.post("/api/cases/{case_id}/finalize")
async def api_finalize(case_id: str) -> JSONResponse:
    """FORMALIA_CHECK → READY — ENDAST när grinden passerar (409 annars).
    Detta är grindfunktionen: inget anbud blir klart med obesvarade skall-krav."""
    case = await case_archive.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case hittades inte")

    gate = await formalia.run_gate(case)
    if not gate["passed"]:
        return JSONResponse(
            status_code=409,
            content={
                "passed": False,
                "blocking_count": gate["blocking_count"],
                "items": gate["items"],
                "detail": f"{gate['blocking_count']} obligatoriska punkter blockerar.",
            },
        )

    async with lodet_db.SessionLocal() as session:
        row = await session.get(lodet_db.Case, case_id)
        if row.state != case_states.FORMALIA_CHECK:
            # tillåt finalize direkt från DRAFTING genom mellanläge
            if row.state == case_states.DRAFTING:
                await case_states.transition(session, row, case_states.FORMALIA_CHECK)
            else:
                raise HTTPException(status_code=409, detail=f"Fel state för finalize: {row.state}")
        await case_states.transition(session, row, case_states.READY)
        await lodet_db.log_event(session, case_id, "formalia_passed", {
            "checks": len(gate["items"]),
        })
        await session.commit()
        return JSONResponse({"passed": True, "state": row.state, "state_label": case_states.LABELS.get(row.state)})


@app.post("/api/cases/{case_id}/submit")
async def api_submit(case_id: str) -> JSONResponse:
    """READY → SUBMITTED. Prissatta rader blir prisdata (own_bid, won=null)."""
    async with lodet_db.SessionLocal() as session:
        case = await session.get(lodet_db.Case, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Case hittades inte")
        try:
            await case_states.transition(session, case, case_states.SUBMITTED)
        except case_states.IllegalTransition as e:
            raise HTTPException(status_code=409, detail=str(e))
        await session.commit()

    try:
        await price_engine.refresh_observations_for_case(case_id)
    except Exception:
        pass
    return JSONResponse({"state": case_states.SUBMITTED, "state_label": case_states.LABELS.get(case_states.SUBMITTED)})


@app.post("/api/cases/{case_id}/outcome")
async def api_outcome(case_id: str, payload: dict = Body(...)) -> JSONResponse:
    """SUBMITTED → AWARDED/LOST. Fyller won-flaggan på prisobservationerna
    (stänger flywheeln: utfall tillbaka in i datan, AP4/AP6)."""
    result = payload.get("result")
    if result not in ("won", "lost"):
        raise HTTPException(status_code=400, detail="result måste vara 'won' eller 'lost'")
    target = case_states.AWARDED if result == "won" else case_states.LOST

    async with lodet_db.SessionLocal() as session:
        case = await session.get(lodet_db.Case, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Case hittades inte")
        try:
            await case_states.transition(session, case, target)
        except case_states.IllegalTransition as e:
            raise HTTPException(status_code=409, detail=str(e))
        # Fyll won-flaggan på casens prisobservationer
        obs = (await session.execute(
            sa_select(lodet_db.PriceObservation).where(lodet_db.PriceObservation.case_id == case_id)
        )).scalars().all()
        for o in obs:
            o.won = (result == "won")
        await session.commit()

    return JSONResponse({
        "state": target,
        "state_label": case_states.LABELS.get(target),
        "observations_updated": len(obs),
    })


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


@app.get("/api/documents")
async def api_documents_list(doc_type: str | None = None) -> JSONResponse:
    """Dokument ur DB:n (ej localStorage), grupperbart per typ. doc_type=mf
    berikas med MF-radantal + total per case. Driver Dokument-vyerna."""
    async with lodet_db.SessionLocal() as session:
        dq = sa_select(lodet_db.Document)
        if doc_type:
            dq = dq.where(lodet_db.Document.doc_type == doc_type)
        docs = (await session.execute(dq)).scalars().all()

        case_ids = {d.case_id for d in docs}
        cases = {}
        if case_ids:
            crows = (await session.execute(
                sa_select(lodet_db.Case).where(lodet_db.Case.id.in_(case_ids))
            )).scalars().all()
            cases = {c.id: c for c in crows}

        # MF-radstatistik per case (bara när vi listar MF)
        mf_stats: dict[str, dict] = {}
        if doc_type == "mf" and case_ids:
            for cid in case_ids:
                lines = (await session.execute(
                    sa_select(lodet_db.MfLine).where(lodet_db.MfLine.case_id == cid)
                )).scalars().all()
                total = sum((l.total or 0) for l in lines if l.total)
                mf_stats[cid] = {
                    "line_count": len(lines),
                    "priced": sum(1 for l in lines if l.unit_price is not None),
                    "total_amount_sek": round(total) or None,
                    "ama_codes": sorted({l.ama_code for l in lines if l.ama_code}),
                }

    out = []
    for d in docs:
        c = cases.get(d.case_id)
        if c is None:
            continue  # föräldralöst dokument (case raderat) — visa inte
        entry = {
            "document_id": d.id,
            "case_id": d.case_id,
            "filename": d.filename,
            "doc_type": d.doc_type,
            "label": d.label,
            "page_count": d.page_count,
            "project_name": c.project_name or c.source_name,
            "document_number": c.document_number,
            "state": c.state,
            "created_at": c.created_at,
            "next_route": case_states.LABELS.get(c.state) and f"#/kalkylator/{d.case_id}",
        }
        if d.case_id in mf_stats:
            entry.update(mf_stats[d.case_id])
        out.append(entry)

    # Nyast först
    out.sort(key=lambda e: e.get("created_at") or "", reverse=True)
    return JSONResponse({"documents": out})


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

    # Prissatta rader blir prisdata (AP4) — idempotent omskrivning
    try:
        await price_engine.refresh_observations_for_case(case_id)
    except Exception:
        pass

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
    """Dashboard-data aggregerad från databasen (cases, events, observationer)."""
    from sqlalchemy import func

    ACTIVE_STATES = {
        case_states.CALCULATING, case_states.NEEDS_REVIEW,
        case_states.DRAFTING, case_states.FORMALIA_CHECK, case_states.READY,
    }

    async with lodet_db.SessionLocal() as session:
        cases = (await session.execute(
            sa_select(lodet_db.Case).order_by(lodet_db.Case.created_at.desc())
        )).scalars().all()
        obs_count = (await session.execute(
            sa_select(func.count()).select_from(lodet_db.PriceObservation)
        )).scalar_one()
        recent_events = (await session.execute(
            sa_select(lodet_db.Event).order_by(lodet_db.Event.id.desc()).limit(40)
        )).scalars().all()

    active = [c for c in cases if c.state in ACTIVE_STATES]
    awarded = [c for c in cases if c.state == case_states.AWARDED]
    lost = [c for c in cases if c.state == case_states.LOST]
    decided = len(awarded) + len(lost)
    win_rate = round(100 * len(awarded) / decided) if decided else 0
    total_active_value = sum(c.total_amount_sek or 0 for c in active)

    # Senaste aktivitet ur events (state_change, analysis_written, user_edit)
    case_by_id = {c.id: c for c in cases}
    activity = []
    _kinds = {
        "case_created": ("parse", "Nytt anbud skapat"),
        "analysis_written": ("parse", "Paket analyserat"),
        "state_change": ("submit", "Statusbyte"),
        "formalia_passed": ("win", "Formaliakontroll godkänd"),
        "historic_prices_imported": ("parse", "Prishistorik importerad"),
    }
    for e in recent_events:
        meta = _kinds.get(e.kind)
        if not meta:
            continue
        c = case_by_id.get(e.case_id) if e.case_id else None
        proj = (c.project_name or c.source_name) if c else (e.data or {}).get("project", "—")
        sub = ""
        if e.kind == "state_change":
            sub = f"→ {case_states.LABELS.get((e.data or {}).get('to'), '')}"
        elif e.kind == "analysis_written":
            sub = f"{(e.data or {}).get('line_count', 0)} rader"
        elif e.kind == "historic_prices_imported":
            sub = f"{(e.data or {}).get('count', 0)} prisrader"
        activity.append({
            "type": meta[0],
            "title": f"{proj} — {meta[1]}",
            "subtitle": sub,
            "timestamp": (e.at or "").replace("T", " ")[:16],
        })
        if len(activity) >= 6:
            break

    # Kommande deadlines ur aktiva cases med bid_due_at
    deadlines = []
    for c in active:
        due = c.bid_due_at or ((c.meta or {}).get("mf_metadata") or {}).get("bid_due_at")
        if due:
            deadlines.append({"project": c.project_name or c.source_name, "customer": c.customer or "—", "due": str(due)[:10]})
    deadlines.sort(key=lambda d: d["due"])

    return JSONResponse({
        "stats": {
            "active_bids": len(active),
            "total_bid_value_sek": round(total_active_value),
            "win_rate_pct": win_rate,
            "ama_codes_in_library": len(ama_catalog.all_codes()),
            "price_observations": obs_count,
        },
        "recent_activity": activity,
        "upcoming_deadlines": deadlines[:5],
    })
