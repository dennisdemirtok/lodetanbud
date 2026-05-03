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
from app import case_archive
from app import chat as lodet_chat
from app import excel_parser
from app import file_classifier
from app import lesson_extractor
from app import pdf_extractor
from app import pdf_renderer
from app import requirement_extractor
from app import ue_emailer
from app import zip_handler
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

def _classify_one(filename: str, data: bytes) -> tuple[lodet_agent.FileInfo, dict | None]:
    """Klassificera en enskild fil och returnera (FileInfo, ev. parsed_mf)."""
    size_kb = max(1, len(data) // 1024)
    content_text = ""
    if filename.lower().endswith(".pdf"):
        content_text = pdf_extractor.extract_first_page_text(data)

    kind = file_classifier.classify(filename, data, content_text)

    parsed_mf: dict | None = None
    lower_name = filename.lower()
    if kind.type == "mf":
        try:
            if lower_name.endswith(".csv"):
                doc = parse_csv_bytes(data)
                parsed_mf = doc.to_dict()
            elif lower_name.endswith((".xlsx", ".xlsm")):
                doc = excel_parser.parse_excel_bytes(data)
                parsed_mf = doc.to_dict()
        except Exception:
            pass

    meta_extra: dict = {}
    if content_text:
        meta_extra = pdf_extractor.sniff_metadata_from_text(content_text)
    if filename.lower().endswith(".pdf"):
        pdf_meta = pdf_extractor.extract_metadata(data)
        meta_extra.update({"page_count": pdf_meta.get("page_count")})

    info = lodet_agent.FileInfo(
        filename=filename,
        type=kind.type,
        label=kind.label,
        confidence=kind.confidence,
        size_kb=size_kb,
        project_id=kind.project_id or file_classifier.extract_project_id(filename),
        discipline=kind.discipline,
        metadata=meta_extra or None,
    )
    return info, parsed_mf


async def _analyze_filebatch(
    filename_data_pairs: list[tuple[str, bytes]],
    source: str,
    source_name: str,
    save_to_archive: bool = True,
) -> dict:
    """
    Klassificera en samling filer (filnamn + bytes), kör agentanalys,
    extrahera lärdomar och anbudskrav med Claude och spara till arkiv.
    """
    file_infos: list[lodet_agent.FileInfo] = []
    parsed_mf: dict | None = None

    for fname, data in filename_data_pairs:
        info, mf = _classify_one(fname, data)
        file_infos.append(info)
        if mf and parsed_mf is None:
            parsed_mf = mf

    analysis = lodet_agent.analyze_package(file_infos, parsed_mf)

    # Plocka ut full text från AF-PDFen för krav-extraktion
    af_text = ""
    data_by_name = {fname: data for fname, data in filename_data_pairs}
    for info in file_infos:
        if info.type == "af" and info.filename.lower().endswith(".pdf"):
            data = data_by_name.get(info.filename)
            if data:
                af_text = pdf_extractor.extract_all_text(data, max_chars=50_000)
                if af_text:
                    break

    saved_case = None
    if save_to_archive:
        files_dict = analysis["files"]
        try:
            extracted = await lesson_extractor.extract_lessons(
                package_summary=analysis["summary"],
                parsed_mf=parsed_mf,
                files=files_dict,
            )
            lessons = extracted.get("lessons") or []
            if extracted.get("summary"):
                analysis["summary"]["agent_summary"] = extracted["summary"]
            if extracted.get("tags"):
                analysis["summary"]["tags"] = extracted["tags"]
        except Exception:
            lessons = []

        try:
            required_docs = await requirement_extractor.extract_required_docs(af_text)
        except Exception:
            required_docs = list(requirement_extractor.DEFAULT_REQUIRED_DOCS)

        try:
            case = case_archive.save_case(
                source=source,
                source_name=source_name,
                summary=analysis["summary"],
                files=files_dict,
                parsed_mf=parsed_mf,
                lessons=lessons,
                required_docs=required_docs,
            )
            saved_case = {
                "id": case.id,
                "lessons": case.lessons,
                "required_docs": case.required_docs,
            }
        except Exception:
            saved_case = None

    return {
        "analysis": analysis,
        "parsed_mf": parsed_mf,
        "saved_case": saved_case,
    }


@app.post("/api/package/analyze")
async def api_package_analyze(files: list[UploadFile] = File(...)) -> JSONResponse:
    """
    Tar emot ett helt anbudspaket — vanliga filer eller en eller flera ZIP-filer.

    Om en ZIP innehåller flera toppmappar tolkas varje toppmapp som ett separat
    anbudspaket. Resultatet sparas till case-arkivet på Volume.
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
                pairs = [(x.filename, x.data) for x in fs]
                source_name = f"{zip_base}/{folder}" if folder != "(rotmapp)" else zip_base
                zip_groups.append((source_name, pairs))
        else:
            plain_files.append((f.filename, data))

    results: list[dict] = []

    # Plain (lösa filer + ev. mapp via webkitdirectory) → ETT paket
    if plain_files:
        source_name = "uppladdat-paket"
        result = await _analyze_filebatch(
            plain_files,
            source="folder" if len(plain_files) > 1 else "single",
            source_name=source_name,
        )
        results.append(result)

    # En analys per ZIP-mapp
    for source_name, pairs in zip_groups:
        result = await _analyze_filebatch(
            pairs,
            source="zip",
            source_name=source_name,
        )
        results.append(result)

    if len(results) == 1:
        return JSONResponse(results[0])

    return JSONResponse({
        "multi": True,
        "case_count": len(results),
        "results": results,
    })


# --- Kunskapsbas (sparade cases) ------------------------------------------

@app.get("/api/cases")
async def api_cases_list() -> JSONResponse:
    return JSONResponse({"cases": case_archive.list_cases_summary()})


@app.get("/api/cases/{case_id}")
async def api_case_get(case_id: str) -> JSONResponse:
    case = case_archive.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case hittades inte")
    return JSONResponse(case)


@app.delete("/api/cases/{case_id}")
async def api_case_delete(case_id: str) -> JSONResponse:
    if not case_archive.delete_case(case_id):
        raise HTTPException(status_code=404, detail="Case hittades inte")
    return JSONResponse({"deleted": case_id})


# --- Anbudsutkast (drafts per case) ---------------------------------------

def _build_draft_text(case: dict, doc_id: str, doc_meta: dict) -> str:
    """Generera utkast-text för ett krav i ett case."""
    project_name = case.get("project_name") or "—"
    document_number = case.get("document_number") or "—"
    customer = case.get("customer") or "—"
    total = case.get("total_amount_sek") or 0.0
    company_name = case.get("summary", {}).get("company_name") or "Anbudsgivare AB"

    if doc_id == "anbudssumma":
        return afb.anbudssumma(
            project_name=project_name,
            document_number=document_number,
            company_name=company_name,
            total_amount=float(total),
        )
    if doc_id == "ue-lista":
        return afb.ue_lista(project_name=project_name, company_name=company_name)
    if doc_id == "sekretess":
        return afb.sekretessbegaran(
            project_name=project_name,
            document_number=document_number,
            company_name=company_name,
        )
    if doc_id == "missiv":
        return afb.missiv(
            project_name=project_name,
            document_number=document_number,
            company_name=company_name,
            customer_name=customer,
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

Underskrift:    ________________________________________
"""


@app.get("/api/cases/{case_id}/drafts")
async def api_case_drafts(case_id: str) -> JSONResponse:
    """Lista required_docs + status (genererat/redigerat) för ett case."""
    case = case_archive.get_case(case_id)
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
    case = case_archive.get_case(case_id)
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
    case_archive.update_draft(case_id, doc_id, text, edited=False)

    return JSONResponse({
        "case_id": case_id,
        "doc_id": doc_id,
        "text": text,
        "status": "generated",
    })


@app.put("/api/cases/{case_id}/draft/{doc_id}")
async def api_case_draft_update(case_id: str, doc_id: str, payload: dict = Body(...)) -> JSONResponse:
    """Spara redigerad utkast-text."""
    case = case_archive.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case hittades inte")

    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text saknas")

    case_archive.update_draft(case_id, doc_id, text, edited=True)
    return JSONResponse({"case_id": case_id, "doc_id": doc_id, "status": "edited"})


@app.get("/api/cases/{case_id}/draft/{doc_id}/pdf")
async def api_case_draft_pdf(case_id: str, doc_id: str) -> Response:
    """Returnera utkastet som PDF. Genererar text on-demand om inget sparat utkast finns."""
    case = case_archive.get_case(case_id)
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
        case_archive.update_draft(case_id, doc_id, text, edited=False)

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
    case = case_archive.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case hittades inte")

    parsed_mf = case.get("parsed_mf")
    if not parsed_mf:
        raise HTTPException(status_code=404, detail="Ingen mängdförteckning hittades i detta case")

    return JSONResponse(parsed_mf)


@app.put("/api/cases/{case_id}/mf")
async def api_case_mf_update(case_id: str, payload: dict = Body(...)) -> JSONResponse:
    """Spara redigerad mängdförteckning (à-priser/belopp). Räknar om totalbelopp."""
    case = case_archive.get_case(case_id)
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

    if not case_archive.update_parsed_mf(case_id, parsed_mf):
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
    case = case_archive.get_case(case_id)
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
    case = case_archive.get_case(case_id)
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
