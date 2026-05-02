"""
Lodet — FastAPI-app
===================
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import __version__
from app import afb_templates as afb
from app import ama_catalog
from app import agent as lodet_agent
from app import chat as lodet_chat
from app import file_classifier
from app import pdf_extractor
from app import ue_emailer
from app.excel_builder import build_workbook
from app.parser import parse_csv_bytes


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
EXAMPLES_DIR = BASE_DIR.parent / "examples"

MAX_UPLOAD_BYTES = 10 * 1024 * 1024

app = FastAPI(
    title="Lodet",
    description="Anbudsverktyg för svenska bygg- och anläggningsentreprenörer",
    version=__version__,
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


# --- Agent / paketanalys --------------------------------------------------

@app.post("/api/package/analyze")
async def api_package_analyze(files: list[UploadFile] = File(...)) -> JSONResponse:
    """
    Tar emot ett helt anbudspaket (många filer på en gång), klassificerar
    varje fil och returnerar agentens analys + rekommendationer.

    Om en CSV-fil hittas parsas den som mängdförteckning.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Inga filer mottagna")

    file_infos: list[lodet_agent.FileInfo] = []
    parsed_mf: dict | None = None

    for f in files:
        if not f.filename:
            continue
        data = await f.read()
        size_kb = max(1, len(data) // 1024)

        content_text = ""
        if f.filename.lower().endswith(".pdf"):
            content_text = pdf_extractor.extract_first_page_text(data)

        kind = file_classifier.classify(f.filename, data, content_text)

        # Försök parsa mängdförteckning om CSV
        if kind.type == "mf" and f.filename.lower().endswith(".csv") and parsed_mf is None:
            try:
                doc = parse_csv_bytes(data)
                parsed_mf = doc.to_dict()
            except Exception:
                pass

        # Plocka ut metadata om PDF
        meta_extra: dict = {}
        if content_text:
            meta_extra = pdf_extractor.sniff_metadata_from_text(content_text)
        if f.filename.lower().endswith(".pdf"):
            pdf_meta = pdf_extractor.extract_metadata(data)
            meta_extra.update({"page_count": pdf_meta.get("page_count")})

        file_infos.append(
            lodet_agent.FileInfo(
                filename=f.filename,
                type=kind.type,
                label=kind.label,
                confidence=kind.confidence,
                size_kb=size_kb,
                project_id=kind.project_id or file_classifier.extract_project_id(f.filename),
                discipline=kind.discipline,
                metadata=meta_extra or None,
            )
        )

    analysis = lodet_agent.analyze_package(file_infos, parsed_mf)
    return JSONResponse({
        "analysis": analysis,
        "parsed_mf": parsed_mf,
    })


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
