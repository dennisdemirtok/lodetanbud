"""
AFB-svarsgenerering kravvis (genomförandeplan AP5).

För varje requirement med response_format='fritext': bygg kontext ur
företagsfakta (company_settings) + top-k liknande tidigare svar
(answer_library), be Claude besvara kravet med ENDAST fakta ur kontexten,
och markera luckor med [SAKNAS: …] i stället för att fabulera bolagsfakta.

Godkända svar skrivs till answer_library och återanvänds på liknande krav.
Likhet körs på requirement_text (pg_trgm på Postgres, difflib på SQLite);
embeddings kopplas in när en embedding-nyckel finns.
"""

from __future__ import annotations

import difflib
import re

from sqlalchemy import select, text as sa_text

from app import company_settings, llm
from app.db import AnswerLibrary, SessionLocal, engine, log_event, new_id, utcnow_iso

SIMILARITY_FLOOR_PG = 0.30
SIMILARITY_FLOOR_PY = 0.45
SAKNAS_RE = re.compile(r"\[SAKNAS:[^\]]*\]")


_ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {
            "type": "string",
            "description": (
                "Svaret på kravet, på svenska, i anbudston. Använd ENDAST fakta "
                "ur den givna kontexten. Där en uppgift saknas, skriv exakt "
                "[SAKNAS: kort beskrivning av vad som behövs] i stället för att gissa."
            ),
        },
        "sources_used": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Vilka kontextkällor du faktiskt använde (t.ex. 'företagsfakta: certifikat', 'tidigare svar AFB.52').",
        },
        "missing": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Lista över [SAKNAS]-luckorna — uppgifter användaren måste fylla i.",
        },
    },
    "required": ["answer", "sources_used", "missing"],
    "additionalProperties": False,
}

_ANSWER_SYSTEM = """Du skriver svar på krav i ett svenskt bygganbud (AFB-bilaga).

Du får: kravets ordagranna lydelse, fakta om anbudsgivarens företag, och
ev. tidigare godkända svar på liknande krav. Skriv ett koncist, korrekt
svar i anbudston.

ABSOLUT REGEL — INGA PÅHITTADE BOLAGSFAKTA:
Använd ENDAST uppgifter som finns i den givna kontexten. Hitta ALDRIG på
omsättning, certifikat, referensprojekt, antal anställda, namn eller
siffror. Saknas en uppgift kravet efterfrågar — skriv exakt
[SAKNAS: vad som behövs] på den platsen. Det är bättre att lämna en
tydlig lucka än att fabulera. Lista varje sådan lucka i 'missing'.

STIL: sakligt, kortfattat, inga floskler. Hänvisa till bifogade bilagor
där kravet kräver dokument vi inte kan skriva fram här (intyg, CV)."""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


async def find_library_matches(req_text: str, limit: int = 3) -> list[AnswerLibrary]:
    """Top-k tidigare svar på liknande krav."""
    req_text = _norm(req_text)
    if len(req_text) < 12:
        return []

    async with SessionLocal() as session:
        if engine.dialect.name == "postgresql":
            sql = """
                SELECT id FROM answer_library
                WHERE similarity(requirement_text, :t) > :floor
                ORDER BY similarity(requirement_text, :t) DESC
                LIMIT :lim
            """
            try:
                ids = [r[0] for r in (await session.execute(
                    sa_text(sql), {"t": req_text, "floor": SIMILARITY_FLOOR_PG, "lim": limit}
                )).all()]
            except Exception:
                ids = []
            if not ids:
                return []
            rows = (await session.execute(
                select(AnswerLibrary).where(AnswerLibrary.id.in_(ids))
            )).scalars().all()
            return list(rows)

        # SQLite: difflib i Python
        rows = (await session.execute(select(AnswerLibrary).limit(500))).scalars().all()
        scored = []
        nt = req_text.lower()
        for r in rows:
            ratio = difflib.SequenceMatcher(None, nt, (r.requirement_text or "").lower()).ratio()
            if ratio >= SIMILARITY_FLOOR_PY:
                scored.append((ratio, r))
        scored.sort(key=lambda x: -x[0])
        return [r for _s, r in scored[:limit]]


def _build_context(
    requirement: dict,
    company: dict,
    library: list[AnswerLibrary],
    case_answers: list[dict] | None = None,
) -> str:
    parts = ["KRAVETS LYDELSE (ordagrant):", requirement.get("text") or "", ""]

    if case_answers:
        parts.append("PROJEKTSPECIFIKA FAKTA (användarens svar på agentens frågor om DETTA anbud):")
        for qa in case_answers:
            parts.append(f"  - Fråga: {qa.get('question')}")
            parts.append(f"    Svar: {qa.get('answer')}")
        parts.append("")

    parts.append("FÖRETAGSFAKTA (anbudsgivaren):")
    facts = {
        "Företag": company.get("company_name"),
        "Org.nr": company.get("organisationsnummer"),
        "Årsomsättning (Mkr)": company.get("omsattning_msek"),
        "Antal anställda": company.get("antal_anstallda"),
        "Certifikat": company.get("certifikat"),
        "Referensprojekt": company.get("referensprojekt"),
        "Nyckelpersoner": company.get("nyckelpersoner"),
        "UE-policy": company.get("ue_policy"),
        "Kontaktperson": company.get("contact_name"),
    }
    any_fact = False
    for label, val in facts.items():
        if val and str(val).strip():
            parts.append(f"  - {label}: {val}")
            any_fact = True
    if not any_fact:
        parts.append("  (inga företagsfakta ifyllda — markera allt som efterfrågas med [SAKNAS])")
    parts.append("")

    if library:
        parts.append("TIDIGARE GODKÄNDA SVAR på liknande krav (får återanvändas/anpassas):")
        for lib in library:
            parts.append(f"  [{lib.af_code or '—'}] krav: {(lib.requirement_text or '')[:120]}")
            parts.append(f"    svar: {(lib.answer_text or '')[:400]}")
        parts.append("")

    parts.append("Skriv svaret enligt schemat. Påhittade bolagsfakta är förbjudet — använd [SAKNAS: …] vid luckor.")
    return "\n".join(parts)


async def generate_answer(case: dict, requirement: dict) -> dict:
    """
    Returnera {answer, missing[], sources_used[], library_used} för ett krav.
    Faller tillbaka till en platsmall med [SAKNAS]-markörer om Claude saknas.
    """
    company = company_settings.get_settings()
    library = await find_library_matches(requirement.get("text") or "")
    case_id = case.get("id")

    # Användarens svar på agentens frågor = projektspecifika fakta
    case_answers = [
        q for q in ((case.get("insights") or {}).get("questions") or [])
        if isinstance(q, dict) and (q.get("answer") or "").strip()
    ]

    if not llm.is_configured():
        # Deterministisk fallback: platsmall, allt okänt markeras
        title = requirement.get("af_code") or "Krav"
        return {
            "answer": (
                f"{title}\n\n[SAKNAS: svar på kravet \"{(requirement.get('text') or '')[:120]}\" "
                f"— fyll i manuellt eller konfigurera Claude för automatisk generering]"
            ),
            "missing": ["Hela svaret behöver fyllas i manuellt (Claude ej konfigurerad)"],
            "sources_used": [],
            "library_used": len(library),
        }

    parsed, _err = await llm.call_structured(
        system=_ANSWER_SYSTEM,
        prompt=_build_context(requirement, company, library, case_answers=case_answers),
        schema=_ANSWER_SCHEMA,
        purpose="generate_afb_answer",
        case_id=case_id,
        max_tokens=2048,
    )
    if parsed is None:
        return {
            "answer": f"[SAKNAS: svar kunde inte genereras — fyll i manuellt]",
            "missing": ["Generering misslyckades"],
            "sources_used": [],
            "library_used": len(library),
        }

    answer = parsed.get("answer") or ""
    # Verifiera [SAKNAS]-listan mot själva texten (modellen kan glömma lista)
    found = SAKNAS_RE.findall(answer)
    missing = parsed.get("missing") or []
    if found and not missing:
        missing = [m.strip("[]") for m in found]

    return {
        "answer": answer,
        "missing": missing,
        "sources_used": parsed.get("sources_used") or [],
        "library_used": len(library),
    }


async def save_to_library(
    requirement: dict, answer_text: str, source_case_id: str | None = None
) -> None:
    """Skriv ett godkänt svar till biblioteket. Hoppar över om svaret
    fortfarande har [SAKNAS]-luckor (ofärdigt)."""
    if not answer_text or SAKNAS_RE.search(answer_text):
        return
    req_text = _norm(requirement.get("text") or "")
    if len(req_text) < 12:
        return

    async with SessionLocal() as session:
        # Dedup: uppdatera om identiskt krav redan finns
        existing = (await session.execute(
            select(AnswerLibrary).where(AnswerLibrary.requirement_text == req_text).limit(1)
        )).scalar_one_or_none()
        now = utcnow_iso()
        if existing is not None:
            existing.answer_text = answer_text
            existing.updated_at = now
            existing.use_count = (existing.use_count or 0) + 1
        else:
            session.add(AnswerLibrary(
                id=new_id("ans"),
                af_code=(requirement.get("af_code") or None),
                requirement_text=req_text,
                answer_text=answer_text,
                use_count=1,
                created_at=now,
                source_case_id=source_case_id,
                meta={},
            ))
        await log_event(session, source_case_id, "answer_saved_to_library", {
            "af_code": requirement.get("af_code"),
        })
        await session.commit()
