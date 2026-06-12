"""
AF-parser → kravmatris (genomförandeplan AP3).

Pipeline:
  1. Deterministisk sektionssplit på AF-kodrubriker (AFB.31, AFC.361 …)
     med sidnummer per sektion.
  2. LLM-extraktion per chunk av sektioner — instruktionen kräver
     ORDAGRANNA citat, aldrig parafraser.
  3. Citatverifiering i kod: citatet måste återfinnas i källtexten
     (exakt eller fuzzy ≥ 0.9). Annars confidence = 0 och kravet flaggas.
     Det gör hallucinerade krav omöjliga i matrisen — ett krav som inte
     kan återfinnas visas aldrig som grönt.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from app import llm

# Rubrikrad: börjar med AF-kod (AFA/AFB/AFC/AFD/AFG/AFH + ev. punktnummer)
_AF_HEADING_RE = re.compile(r"^(AF[A-Z](?:\.\d+)*)\b[ \t]*(.*)$")

# Huvuddelar för gruppering i UI
HUVUDDELAR = {
    "AFA": "AFA — Allmän orientering",
    "AFB": "AFB — Upphandlingsföreskrifter",
    "AFC": "AFC — Entreprenadföreskrifter (AB)",
    "AFD": "AFD — Entreprenadföreskrifter (ABT)",
    "AFG": "AFG — Allmänna arbeten och hjälpmedel",
    "AFH": "AFH — Allmänna hjälpmedel",
    "AFJ": "AFJ — Allmänna arbeten",
}


@dataclass
class AfSection:
    code: str
    title: str
    text: str
    page: int


def split_af_sections(pages: list[str]) -> list[AfSection]:
    """Dela AF-dokumentet på kodrubriker. Deterministiskt, med sidnummer."""
    sections: list[AfSection] = []
    current: AfSection | None = None

    for pno, page_text in enumerate(pages, start=1):
        for raw_line in page_text.splitlines():
            line = raw_line.strip()
            m = _AF_HEADING_RE.match(line)
            is_heading = (
                m is not None
                and len(line) <= 120
                and (not m.group(2) or not m.group(2)[0].islower())
                # innehållsförteckningens "AFB.1 Former ......... 4" är inte rubriker
                and not re.search(r"\.{4,}", line)
            )
            if is_heading:
                if current is not None:
                    sections.append(current)
                current = AfSection(code=m.group(1), title=(m.group(2) or "").strip(), text="", page=pno)
            elif current is not None:
                current.text += raw_line + "\n"

    if current is not None:
        sections.append(current)

    return [s for s in sections if s.text.strip() or s.title]


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def verify_quote(quote: str, sections: list[AfSection]) -> tuple[bool, float, int | None]:
    """
    Verifiera att citatet återfinns i källtexten.
    Returnerar (verified, match_ratio, page).
    """
    nq = _normalize(quote)
    if len(nq) < 10:
        return False, 0.0, None

    # Exakt (whitespace-normaliserad) träff
    for s in sections:
        ns = _normalize(f"{s.code} {s.title} {s.text}")
        if nq in ns:
            return True, 1.0, s.page

    # Fuzzy: längsta sammanhängande träff / citatlängd
    best_ratio, best_page = 0.0, None
    for s in sections:
        ns = _normalize(f"{s.title} {s.text}")
        if not ns:
            continue
        sm = difflib.SequenceMatcher(None, nq, ns, autojunk=False)
        m = sm.find_longest_match(0, len(nq), 0, len(ns))
        ratio = m.size / len(nq)
        if ratio > best_ratio:
            best_ratio, best_page = ratio, s.page
            if best_ratio >= 0.999:
                break

    if best_ratio >= 0.9:
        return True, round(best_ratio, 3), best_page
    return False, round(best_ratio, 3), best_page


def _chunk_sections(sections: list[AfSection], max_chars: int = 7000) -> list[list[AfSection]]:
    """Gruppera intilliggande sektioner till chunks för LLM-anrop."""
    chunks: list[list[AfSection]] = []
    cur: list[AfSection] = []
    size = 0
    for s in sections:
        s_len = len(s.title) + len(s.text) + 24
        if cur and size + s_len > max_chars:
            chunks.append(cur)
            cur, size = [], 0
        cur.append(s)
        size += s_len
    if cur:
        chunks.append(cur)
    return chunks


KRAV_SCHEMA = {
    "type": "object",
    "properties": {
        "requirements": {
            "type": "array",
            "description": "Krav på anbudsgivaren/entreprenören i texten.",
            "items": {
                "type": "object",
                "properties": {
                    "af_code": {
                        "type": "string",
                        "description": "AF-koden för sektionen kravet står i (t.ex. 'AFB.52'). Tom om oklar.",
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["skall", "bor", "utvardering", "formalia", "bilaga"],
                    },
                    "quote": {
                        "type": "string",
                        "description": "Kravets lydelse ORDAGRANT ur texten. Citera hela meningen, parafrasera ALDRIG.",
                    },
                    "response_format": {
                        "type": "string",
                        "enum": ["fritext", "bilaga", "intyg", "pris", "checkbox"],
                    },
                    "deadline": {
                        "type": "string",
                        "description": "ISO-datum (ÅÅÅÅ-MM-DD) om kravet har en tidsfrist, annars tom sträng.",
                    },
                },
                "required": ["af_code", "kind", "quote", "response_format", "deadline"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["requirements"],
    "additionalProperties": False,
}


KRAV_SYSTEM = """Du extraherar KRAV ur administrativa föreskrifter (AF) i ett
svenskt förfrågningsunderlag. Du får ett antal sektioner med AF-kod och text.

Hitta varje ställe där ANBUDSGIVAREN eller ENTREPRENÖREN ska/skall/bör/krävs
göra, lämna, bifoga, uppfylla, inneha eller redovisa något.

KIND:
- skall: tvingande krav (ska, skall, krävs, förutsätts, villkor)
- bor: önskemål (bör)
- utvardering: utvärderingskriterium eller poängsättning av anbud
- formalia: anbudets form — märkning, språk, giltighetstid, inlämningssätt
- bilaga: dokument/intyg/bevis som ska BIFOGAS anbudet

RESPONSE_FORMAT: hur kravet besvaras — fritext (beskrivning i anbudet),
bilaga (eget dokument), intyg (tredjepartsbevis), pris (prisuppgift),
checkbox (accepteras utan svar).

REGLER:
- quote = ORDAGRANT citat ur texten, hela meningen (max ~300 tecken).
  Citatet verifieras maskinellt mot källtexten och KASSERAS om det inte
  återfinns — parafrasera aldrig, korrigera aldrig stavning.
- Hoppa över beställarens egna åtaganden (vad beställaren ska göra).
- Hoppa över rena upplysningar utan krav.
- Ett krav per rad även när en mening innehåller flera krav — citera då
  samma mening flera gånger med olika kind/response_format."""


async def _extract_chunk(chunk: list[AfSection], case_id: str | None) -> list[dict]:
    """LLM-extraktion + citatverifiering för EN chunk. Returnerar
    requirement-dicts (utan position — sätts av anroparen)."""
    parts = ["Sektioner ur AF-dokumentet:\n"]
    for s in chunk:
        parts.append(f"## {s.code} {s.title}".strip())
        parts.append(s.text.strip()[:6000])
        parts.append("")
    parts.append("Extrahera kraven enligt schemat.")

    parsed, _err = await llm.call_structured(
        system=KRAV_SYSTEM,
        prompt="\n".join(parts),
        schema=KRAV_SCHEMA,
        purpose="extract_af_requirements",
        case_id=case_id,
        max_tokens=4096,
    )
    if parsed is None:
        return []

    chunk_codes = {s.code for s in chunk}
    rows: list[dict] = []
    for raw in parsed.get("requirements") or []:
        quote = (raw.get("quote") or "").strip()
        if not quote:
            continue
        verified, ratio, page = verify_quote(quote, chunk)
        af_code = (raw.get("af_code") or "").strip()
        if af_code not in chunk_codes:
            af_code = af_code or None
        rows.append({
            "af_code": af_code or None,
            "kind": raw.get("kind") or "skall",
            "text": quote,
            "response_format": raw.get("response_format") or "fritext",
            "deadline": (raw.get("deadline") or "").strip() or None,
            "source": {"page": page, "verified": verified, "match_ratio": ratio},
            "confidence": 0.0 if not verified else (0.95 if ratio >= 0.999 else 0.85),
        })
    return rows


async def extract_matrix(
    pages: list[str],
    case_id: str | None = None,
) -> list[dict]:
    """
    Hela kedjan: split → LLM per chunk (parallellt) → citatverifiering.
    Returnerar requirement-dicts redo för DB. Tom lista om LLM saknas.

    Chunkarna körs parallellt med begränsad samtidighet — en stor AF
    (~15 chunks) gick tidigare sekventiellt på ~6 min, nu ~30–60 s.
    """
    import asyncio

    sections = split_af_sections(pages)
    if not sections or not llm.is_configured():
        return []

    chunks = _chunk_sections(sections)
    sem = asyncio.Semaphore(5)  # tak mot rate-limits

    async def _guarded(chunk):
        async with sem:
            try:
                return await _extract_chunk(chunk, case_id)
            except Exception:
                return []

    results = await asyncio.gather(*[_guarded(c) for c in chunks])

    # Platta + sätt position i dokumentordning (chunkarna är ordnade)
    out: list[dict] = []
    for chunk_rows in results:
        for r in chunk_rows:
            r["position"] = len(out)
            out.append(r)
    return out
