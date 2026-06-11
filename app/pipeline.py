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

from app import agent as lodet_agent
from app import agent_insights
from app import case_archive
from app import excel_parser
from app import file_classifier
from app import lesson_extractor
from app import pdf_extractor
from app import requirement_extractor
from app import states
from app.db import DATA_ROOT, Case, SessionLocal
from app.parser import parse_csv_bytes
from app.worker import register


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
) -> tuple[list[lodet_agent.FileInfo], dict | None, str]:
    """Klassificera alla filer + extrahera AF-text. Synkron — körs i tråd."""
    file_infos: list[lodet_agent.FileInfo] = []
    parsed_mf: dict | None = None
    data_by_name: dict[str, bytes] = {}

    for fname, data, _relpath in pairs:
        info, mf = classify_one(fname, data)
        file_infos.append(info)
        data_by_name[fname] = data
        if mf and parsed_mf is None:
            parsed_mf = mf

    af_text = ""
    for info in file_infos:
        if info.type == "af" and info.filename.lower().endswith(".pdf"):
            data = data_by_name.get(info.filename)
            if data:
                af_text = pdf_extractor.extract_all_text(data, max_chars=50_000)
                if af_text:
                    break

    return file_infos, parsed_mf, af_text


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

    # CPU-tungt (pypdf/openpyxl) i tråd så event-loopen inte blockeras
    file_infos, parsed_mf, af_text = await asyncio.to_thread(_classify_batch, pairs)

    analysis = lodet_agent.analyze_package(file_infos, parsed_mf)
    files_dict = analysis["files"]

    # storage_path in i fil-dicts så documents-raderna pekar på volymen
    path_by_name = {fname: relpath for fname, _data, relpath in pairs}
    for f in files_dict:
        f["storage_path"] = path_by_name.get(f.get("filename"))

    # LLM-stegen — var och en med egen fallback, som tidigare
    try:
        extracted = await lesson_extractor.extract_lessons(
            package_summary=analysis["summary"], parsed_mf=parsed_mf, files=files_dict
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
        insights = await agent_insights.extract_insights(
            package_summary=analysis["summary"], files=files_dict, af_text=af_text
        )
    except Exception:
        insights = {"observations": [], "questions": [], "vendor_templates": []}

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

    # EXTRACTING → CALCULATING (NEEDS_REVIEW-grenen aktiveras i AP2
    # när extraktion får confidence-scoring)
    async with SessionLocal() as session:
        case = await session.get(Case, case_id)
        if case.state == states.EXTRACTING:
            await states.transition(session, case, states.CALCULATING)
        await session.commit()

    return {
        "case_id": case_id,
        "file_count": len(files_dict),
        "line_count": len((parsed_mf or {}).get("lines") or []),
        "lesson_count": len(lessons),
        "required_count": len(required_docs),
    }
