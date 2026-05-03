"""
Case-arkiv — persistent lagring av analyserade anbudspaket.

Varje paket sparas som en case_<id>.json-fil på Railway Volume (/data/cases/).
Indexeras vid läsning genom att lista mappen.

För MVP: filsystem. När arkivet växer eller multi-tenant behövs → migrera till
Postgres/Supabase enligt spec C.2.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path


_DATA_ROOT = Path(os.getenv("LODET_DATA_DIR", "/data"))
_CASES_DIR = _DATA_ROOT / "cases"


def _ensure_dirs() -> None:
    """Skapa katalogstrukturen om den saknas. Faller tillbaka till /tmp lokalt."""
    global _CASES_DIR
    try:
        _CASES_DIR.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError):
        # Lokal dev utan /data — använd /tmp
        fallback = Path("/tmp/lodet/cases")
        fallback.mkdir(parents=True, exist_ok=True)
        _CASES_DIR = fallback


def _new_case_id() -> str:
    return f"case_{int(time.time())}_{uuid.uuid4().hex[:6]}"


@dataclass
class Case:
    id: str
    created_at: str
    source: str            # "zip", "folder", "single", "csv"
    source_name: str       # filnamn eller mappnamn
    summary: dict          # paketanalysens summary
    files: list[dict]      # klassificerade filer
    parsed_mf: dict | None # om mängdförteckning hittades
    lessons: list[dict]    # Claude-extraherade lärdomar
    project_name: str | None = None
    document_number: str | None = None
    customer: str | None = None
    total_amount_sek: float | None = None
    ama_codes: list[str] = None  # type: ignore
    required_docs: list[dict] = None  # type: ignore  # krav extraherade från AF
    drafts: dict = None  # type: ignore               # doc_id -> {text, generated_at, edited_at}
    insights: dict = None  # type: ignore             # {observations, questions, vendor_templates}

    def to_dict(self) -> dict:
        d = asdict(self)
        if d["ama_codes"] is None:
            d["ama_codes"] = []
        if d["required_docs"] is None:
            d["required_docs"] = []
        if d["drafts"] is None:
            d["drafts"] = {}
        if d["insights"] is None:
            d["insights"] = {"observations": [], "questions": [], "vendor_templates": []}
        return d


def save_case(
    source: str,
    source_name: str,
    summary: dict,
    files: list[dict],
    parsed_mf: dict | None = None,
    lessons: list[dict] | None = None,
    required_docs: list[dict] | None = None,
    insights: dict | None = None,
) -> Case:
    """Skriv ett case till disk och returnera det."""
    _ensure_dirs()
    cid = _new_case_id()

    project_name = summary.get("project_name") or (
        parsed_mf.get("metadata", {}).get("project_name") if parsed_mf else None
    )
    document_number = (
        parsed_mf.get("metadata", {}).get("document_number") if parsed_mf else None
    )
    total = (
        parsed_mf.get("metadata", {}).get("total_amount_sek") if parsed_mf else None
    )
    ama_codes = []
    if parsed_mf:
        ama_codes = sorted({
            l.get("ama_code")
            for l in parsed_mf.get("lines", [])
            if l.get("ama_code")
        })

    case = Case(
        id=cid,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        source=source,
        source_name=source_name,
        summary=summary,
        files=files,
        parsed_mf=parsed_mf,
        lessons=lessons or [],
        project_name=project_name,
        document_number=document_number,
        customer=summary.get("customer"),
        total_amount_sek=total,
        ama_codes=ama_codes,
        required_docs=required_docs or [],
        drafts={},
        insights=insights or {"observations": [], "questions": [], "vendor_templates": []},
    )

    path = _CASES_DIR / f"{cid}.json"
    path.write_text(json.dumps(case.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return case


def list_cases() -> list[dict]:
    """Returnera alla cases sorterat efter senaste först."""
    _ensure_dirs()
    out = []
    for p in sorted(_CASES_DIR.glob("case_*.json"), reverse=True):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def list_cases_summary() -> list[dict]:
    """Lättare lista för UI — utan parsed_mf och files."""
    full = list_cases()
    out = []
    for c in full:
        required = c.get("required_docs") or []
        drafts = c.get("drafts") or {}
        out.append({
            "id": c["id"],
            "created_at": c["created_at"],
            "source": c["source"],
            "source_name": c["source_name"],
            "project_name": c.get("project_name"),
            "document_number": c.get("document_number"),
            "customer": c.get("customer"),
            "total_amount_sek": c.get("total_amount_sek"),
            "ama_codes": c.get("ama_codes") or [],
            "lesson_count": len(c.get("lessons") or []),
            "file_count": len(c.get("files") or []),
            "required_count": len(required),
            "draft_count": len(drafts),
        })
    return out


def get_case(case_id: str) -> dict | None:
    _ensure_dirs()
    path = _CASES_DIR / f"{case_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def delete_case(case_id: str) -> bool:
    _ensure_dirs()
    path = _CASES_DIR / f"{case_id}.json"
    if not path.exists():
        return False
    path.unlink()
    return True


def update_lessons(case_id: str, lessons: list[dict]) -> bool:
    """Skriv om lessons-fältet på ett befintligt case."""
    _ensure_dirs()
    case = get_case(case_id)
    if case is None:
        return False
    case["lessons"] = lessons
    path = _CASES_DIR / f"{case_id}.json"
    path.write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def update_required_docs(case_id: str, required_docs: list[dict]) -> bool:
    _ensure_dirs()
    case = get_case(case_id)
    if case is None:
        return False
    case["required_docs"] = required_docs
    path = _CASES_DIR / f"{case_id}.json"
    path.write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def update_parsed_mf(case_id: str, parsed_mf: dict) -> bool:
    """Spara redigerad mängdförteckning. Synkar total_amount_sek på case-nivå."""
    _ensure_dirs()
    case = get_case(case_id)
    if case is None:
        return False
    case["parsed_mf"] = parsed_mf
    meta = parsed_mf.get("metadata") or {}
    if meta.get("total_amount_sek") is not None:
        case["total_amount_sek"] = meta["total_amount_sek"]
    path = _CASES_DIR / f"{case_id}.json"
    path.write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def update_draft(case_id: str, doc_id: str, text: str, edited: bool = False) -> bool:
    """Spara ett genererat eller redigerat utkast för ett krav."""
    _ensure_dirs()
    case = get_case(case_id)
    if case is None:
        return False
    drafts = case.get("drafts") or {}
    existing = drafts.get(doc_id) or {}
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    drafts[doc_id] = {
        "text": text,
        "generated_at": existing.get("generated_at") or now,
        "edited_at": now if edited else existing.get("edited_at"),
    }
    case["drafts"] = drafts
    path = _CASES_DIR / f"{case_id}.json"
    path.write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def get_draft(case_id: str, doc_id: str) -> dict | None:
    case = get_case(case_id)
    if case is None:
        return None
    return (case.get("drafts") or {}).get(doc_id)


# ---- Sökning för chat-kontext --------------------------------------------

def find_relevant(query: str, ama_codes: list[str] | None = None, limit: int = 3) -> list[dict]:
    """
    Enkel keyword/AMA-baserad sökning. Returnerar de mest relevanta cases.
    """
    cases = list_cases()
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
