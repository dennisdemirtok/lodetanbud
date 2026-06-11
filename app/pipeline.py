"""
Pipeline — jobbhandlers (genomförandeplan AP1).

run_parse_package gör allt som tidigare låg synkront i
POST /api/package/analyze: klassificering, MF-parsing, agentanalys,
Claude-extraktion (krav, insights, lärdomar) och skrivning till casen.

Idempotent: skriver alltid om documents/mf_lines, appendar aldrig —
ett omkört jobb ger samma slutresultat.
"""

from __future__ import annotations

import asyncio

from app import af_parser
from app import agent as lodet_agent
from app import agent_insights
from app import case_archive
from app import docx_extractor
from app import excel_parser
from app import file_classifier
from app import lesson_extractor
from app import llm
from app import pdf_extractor
from app import pdf_mf_parser
from app import requirement_extractor
from app import states
from app.db import DATA_ROOT, Case, SessionLocal
from app.parser import parse_csv_bytes
from app.worker import register

# Rader under denna confidence skickar casen till granskning (AP2)
REVIEW_THRESHOLD = 0.9


def classify_one(filename: str, data: bytes) -> tuple[lodet_agent.FileInfo, dict | None]:
    """Klassificera en enskild fil och returnera (FileInfo, ev. parsed_mf).
    Synkron CPU-funktion — körs i tråd från handlern."""
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
                parsed_mf = parse_csv_bytes(data).to_dict()
            elif lower_name.endswith((".xlsx", ".xlsm")):
                parsed_mf = excel_parser.parse_excel_bytes(data).to_dict()
        except Exception:
            pass

    meta_extra: dict = {}
    if content_text:
        meta_extra = pdf_extractor.sniff_metadata_from_text(content_text)
    if lower_name.endswith(".pdf"):
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


def _classify_batch(
    pairs: list[tuple[str, bytes, str]],
) -> tuple[list[lodet_agent.FileInfo], dict | None, str, list[dict], list[str]]:
    """Klassificera alla filer + extrahera AF-text. Synkron — körs i tråd.

    Returnerar (file_infos, parsed_mf, af_text, rescue_pages, af_pages).
    Excel/CSV-MF föredras; saknas sådan provas PDF-MF via pdfplumber (AP2).
    af_pages (text per sida) driver kravmatrisen (AP3)."""
    file_infos: list[lodet_agent.FileInfo] = []
    parsed_mf: dict | None = None
    mf_pdf_candidates: list[bytes] = []
    data_by_name: dict[str, bytes] = {}

    for fname, data, _relpath in pairs:
        info, mf = classify_one(fname, data)
        file_infos.append(info)
        data_by_name[fname] = data
        if mf and parsed_mf is None:
            parsed_mf = mf
        if info.type == "mf" and fname.lower().endswith(".pdf"):
            mf_pdf_candidates.append(data)

    # PDF-MF-fallback när ingen Excel/CSV-MF parsades
    rescue_pages: list[dict] = []
    if parsed_mf is None:
        for data in mf_pdf_candidates:
            try:
                doc, rescue = pdf_mf_parser.parse_pdf_mf(data)
            except Exception:
                continue
            if doc and doc.lines:
                parsed_mf = doc.to_dict()
                rescue_pages = rescue
                break
            if rescue:
                rescue_pages = rescue

    af_text = ""
    af_pages: list[str] = []
    for info in file_infos:
        if info.type != "af":
            continue
        data = data_by_name.get(info.filename)
        if not data:
            continue
        lower = info.filename.lower()
        if lower.endswith(".pdf"):
            af_pages = pdf_extractor.extract_pages_text(data)
        elif lower.endswith(".docx"):
            # docx saknar sidor — hela texten som "en sida" (källa = s. 1)
            text = docx_extractor.extract_text(data)
            af_pages = [text] if text else []
        else:
            continue
        af_text = "\n".join(af_pages)[:50_000]
        if af_text.strip():
            break

    return file_infos, parsed_mf, af_text, rescue_pages, af_pages


@register("parse_package")
async def run_parse_package(job) -> dict:
    payload = job.payload or {}
    case_id: str = payload["case_id"]
    file_refs: list[dict] = payload.get("files") or []  # [{filename, path}] relativt DATA_ROOT

    # INTAKE → EXTRACTING (omkörning efter retry: redan EXTRACTING — låt stå)
    async with SessionLocal() as session:
        case = await session.get(Case, case_id)
        if case is None:
            raise ValueError(f"Case {case_id} finns inte")
        if case.state == states.INTAKE:
            await states.transition(session, case, states.EXTRACTING)
        await session.commit()

    pairs: list[tuple[str, bytes, str]] = []
    for ref in file_refs:
        p = DATA_ROOT / ref["path"]
        pairs.append((ref["filename"], p.read_bytes(), ref["path"]))

    # CPU-tungt (pypdf/openpyxl/pdfplumber) i tråd så event-loopen inte blockeras
    file_infos, parsed_mf, af_text, rescue_pages, af_pages = await asyncio.to_thread(_classify_batch, pairs)

    # LLM-rescue: sidor där PDF-tabellextraktionen misslyckades
    if rescue_pages and llm.is_configured():
        rescued = await _llm_rescue_mf(case_id, rescue_pages)
        if rescued:
            if parsed_mf is None:
                parsed_mf = {"metadata": {}, "lines": []}
            parsed_mf["lines"] = (parsed_mf.get("lines") or []) + rescued

    analysis = lodet_agent.analyze_package(file_infos, parsed_mf)
    files_dict = analysis["files"]

    # storage_path in i fil-dicts så documents-raderna pekar på volymen
    path_by_name = {fname: relpath for fname, _data, relpath in pairs}
    for f in files_dict:
        f["storage_path"] = path_by_name.get(f.get("filename"))

    # LLM-stegen — var och en med egen fallback, som tidigare
    try:
        extracted = await lesson_extractor.extract_lessons(
            package_summary=analysis["summary"], parsed_mf=parsed_mf, files=files_dict,
            case_id=case_id,
        )
        lessons = extracted.get("lessons") or []
        if extracted.get("summary"):
            analysis["summary"]["agent_summary"] = extracted["summary"]
        if extracted.get("tags"):
            analysis["summary"]["tags"] = extracted["tags"]
    except Exception:
        lessons = []

    try:
        required_docs = await requirement_extractor.extract_required_docs(af_text, case_id=case_id)
    except Exception:
        required_docs = list(requirement_extractor.DEFAULT_REQUIRED_DOCS)

    try:
        insights = await agent_insights.extract_insights(
            package_summary=analysis["summary"], files=files_dict, af_text=af_text,
            case_id=case_id,
        )
    except Exception:
        insights = {"observations": [], "questions": [], "vendor_templates": []}

    # Kravmatris (AP3): hela AF → källänkade, citatverifierade krav
    try:
        matrix = await af_parser.extract_matrix(af_pages, case_id=case_id)
    except Exception:
        matrix = []

    if matrix:
        skall = sum(1 for r in matrix if r.get("kind") == "skall")
        unverified = sum(1 for r in matrix if not (r.get("source") or {}).get("verified"))
        body = f"{skall} skall-krav att besvara"
        if unverified:
            body += f" · {unverified} citat kunde inte verifieras och är flaggade"
        analysis["recommendations"].insert(0, {
            "id": "kravmatris",
            "priority": 1,
            "title": f"{len(matrix)} krav extraherade ur AF",
            "body": body,
            "action_label": "Öppna kravmatrisen",
            "action_route": f"#/krav/{case_id}",
        })

    await case_archive.update_case_full(
        case_id,
        summary=analysis["summary"],
        files=files_dict,
        parsed_mf=parsed_mf,
        lessons=lessons,
        required_docs=required_docs,
        insights=insights,
        analysis=analysis,
    )

    # Kravmatrisen skrivs efter update_case_full (documents-raderna måste
    # finnas för AF-dokument-kopplingen)
    if matrix:
        try:
            await case_archive.replace_requirements(case_id, matrix)
        except Exception:
            pass

    # EXTRACTING → NEEDS_REVIEW om någon rad ligger under tröskeln,
    # annars direkt till CALCULATING
    lines = (parsed_mf or {}).get("lines") or []
    low_conf = sum(
        1 for l in lines
        if (l.get("confidence") if l.get("confidence") is not None else 1.0) < REVIEW_THRESHOLD
    )
    target = states.NEEDS_REVIEW if low_conf > 0 else states.CALCULATING

    async with SessionLocal() as session:
        case = await session.get(Case, case_id)
        if case.state == states.EXTRACTING:
            await states.transition(session, case, target)
        await session.commit()

    return {
        "case_id": case_id,
        "file_count": len(files_dict),
        "line_count": len(lines),
        "low_confidence_count": low_conf,
        "lesson_count": len(lessons),
        "required_count": len(required_docs),
        "requirement_count": len(matrix),
        "state": target,
    }


async def _llm_rescue_mf(case_id: str, rescue_pages: list[dict], max_pages: int = 12) -> list[dict]:
    """Skicka sidor där tabellextraktionen misslyckades till Claude,
    en sida per anrop. Returnerar line-dicts med extraction_method='llm'."""
    out: list[dict] = []
    for page_info in rescue_pages[:max_pages]:
        parsed, _err = await llm.call_structured(
            system=pdf_mf_parser.RESCUE_SYSTEM,
            prompt=(
                f"Sida {page_info['page']} ur mängdförteckningen:\n\n"
                f"{page_info['text']}\n\n"
                "Extrahera MF-raderna enligt schemat."
            ),
            schema=pdf_mf_parser.RESCUE_SCHEMA,
            purpose="mf_rescue",
            case_id=case_id,
            max_tokens=4096,
        )
        if parsed is None:
            continue
        for raw in parsed.get("lines") or []:
            desc = (raw.get("description") or "").strip()
            if not desc:
                continue
            unit = (raw.get("unit") or "").strip() or None
            qty = raw.get("quantity")
            conf = 0.75
            if unit and unit.lower() in pdf_mf_parser.KNOWN_UNITS:
                conf += 0.05
            if qty is not None:
                conf += 0.05
            out.append({
                "line_number": None,
                "ama_code": (raw.get("ama_code") or "").strip() or None,
                "ama_section_title": None,
                "description": desc,
                "unit": unit,
                "quantity": qty,
                "unit_price": raw.get("unit_price"),
                "total_amount": raw.get("total_amount"),
                "is_lump_sum": False,
                "source": {"page": page_info["page"]},
                "extraction_method": "llm",
                "confidence": round(min(conf, 0.85), 2),
            })
    return out
