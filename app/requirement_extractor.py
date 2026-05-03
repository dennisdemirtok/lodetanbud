"""
Krav-extraktor — läser AF-texten i ett förfrågningsunderlag och returnerar
listan över dokument som anbudsgivaren ska skicka in.

Använder Claude med structured output. Faller tillbaka till en standard-lista
om Claude inte är konfigurerad eller felar.
"""

from __future__ import annotations

import json
import os

from anthropic import APIError, AsyncAnthropic, AuthenticationError


KNOWN_TEMPLATE_IDS = {"anbudssumma", "ue-lista", "sekretess", "missiv"}


_REQ_SCHEMA = {
    "type": "object",
    "properties": {
        "required_docs": {
            "type": "array",
            "description": "Dokument som anbudsgivaren ska skicka in i sitt anbud.",
            "items": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": (
                            "Kort kebab-case ID. För standard-mallar använd EXAKT: "
                            "'anbudssumma' (AFB.31), 'ue-lista' (AFB.32), "
                            "'sekretess' (sekretessbegäran), 'missiv' (följebrev), "
                            "'mf' (ifylld mängdförteckning). Annars slugifiera (t.ex. 'kvalitetsplan')."
                        ),
                    },
                    "title": {"type": "string", "description": "Läsbart namn på svenska."},
                    "code": {
                        "type": "string",
                        "description": "AFB-kod om angiven (t.ex. 'AFB.31'). Tom om saknas.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Kort beskrivning av vad som ska ingå (max 200 tecken).",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["pdf", "xlsx", "other"],
                        "description": "pdf för textdokument, xlsx för ifylld MF/Excel, annars other.",
                    },
                    "required": {
                        "type": "boolean",
                        "description": "true om obligatoriskt, false om valfritt.",
                    },
                    "source_section": {
                        "type": "string",
                        "description": "Var i AF-texten kravet fanns (t.ex. 'AFB.51'). Tom om saknas.",
                    },
                },
                "required": ["id", "title", "code", "description", "format", "required", "source_section"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["required_docs"],
    "additionalProperties": False,
}


_EXTRACTOR_SYSTEM = """Du är en analytiker som läser AF-texten (administrativa
föreskrifter) i ett svenskt förfrågningsunderlag och extraherar listan över
dokument som anbudsgivaren ska skicka in i sitt anbud.

LETA EFTER:
- Avsnitt AFB.5 "Innehåll i anbudet" eller motsvarande i AF AMA-strukturen
- Andra ställen där "anbudet ska innehålla", "bifogas anbudet", "redovisas i anbudet" nämns
- Krav på CV, referensobjekt, kvalitetsplan, miljöplan, arbetsmiljöplan
- Krav på ifylld mängdförteckning med priser
- Krav på AFB.31 anbudssumma, AFB.32 underentreprenörer
- Krav på sekretessbegäran (om anbudsgivaren själv ska skicka in)

REGLER:
- Använd EXAKT ID 'anbudssumma' för AFB.31, 'ue-lista' för AFB.32,
  'sekretess' för sekretessbegäran, 'missiv' för följebrev,
  'mf' för ifylld mängdförteckning
- För övriga krav: slugifiera id (svensk text → 'kvalitetsplan', 'cv-nyckelpersoner', etc.)
- Lista BARA dokument anbudsgivaren ska SKICKA IN — inte filer i förfrågningsunderlaget
- Om AF-texten är tom eller saknas — returnera en standard-lista (anbudssumma, ue-lista, mf, sekretess, missiv)
- Skriv på svenska
- Använd format='xlsx' för mängdförteckning, format='pdf' för text-dokument
"""


DEFAULT_REQUIRED_DOCS: list[dict] = [
    {
        "id": "anbudssumma",
        "title": "Anbudssumma",
        "code": "AFB.31",
        "description": "Totalbelopp exkl. moms enligt förfrågningsunderlaget. Bindande till och med 90 dagar efter anbudstidens utgång.",
        "format": "pdf",
        "required": True,
        "source_section": "AFB.31",
    },
    {
        "id": "ue-lista",
        "title": "Underentreprenörer",
        "code": "AFB.32",
        "description": "Förteckning över planerade UE per teknikområde med andel av kontraktssumma.",
        "format": "pdf",
        "required": True,
        "source_section": "AFB.32",
    },
    {
        "id": "mf",
        "title": "Mängdförteckning med priser",
        "code": "",
        "description": "Komplett mängdförteckning med ifyllda à-priser och belopp per post.",
        "format": "xlsx",
        "required": True,
        "source_section": "",
    },
    {
        "id": "sekretess",
        "title": "Sekretessbegäran",
        "code": "",
        "description": "Begäran enligt FHL §1 + OSL 9:3 / 31:16 om att anbudet eller delar därav ska beläggas med sekretess.",
        "format": "pdf",
        "required": False,
        "source_section": "",
    },
    {
        "id": "missiv",
        "title": "Missiv (följebrev)",
        "code": "",
        "description": "Följebrev som listar samtliga bilagor i anbudspaketet.",
        "format": "pdf",
        "required": False,
        "source_section": "",
    },
]


async def extract_required_docs(af_text: str) -> list[dict]:
    """
    Returnera lista över required documents extraherade från AF-texten.
    Faller tillbaka till DEFAULT_REQUIRED_DOCS om Claude inte är konfigurerad
    eller AF-texten är tom.
    """
    if not af_text or len(af_text.strip()) < 100:
        return list(DEFAULT_REQUIRED_DOCS)

    if not os.getenv("ANTHROPIC_API_KEY"):
        return list(DEFAULT_REQUIRED_DOCS)

    try:
        client = AsyncAnthropic()
        prompt = (
            "Här är AF-texten från ett svenskt förfrågningsunderlag. "
            "Extrahera listan över dokument som anbudsgivaren ska skicka in.\n\n"
            "AF-TEXT:\n"
            f"{af_text[:50_000]}\n\n"
            "Returnera required_docs enligt schemat."
        )

        response = await client.messages.create(
            model="claude-opus-4-7",
            max_tokens=2048,
            system=_EXTRACTOR_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": _REQ_SCHEMA,
                }
            },
        )

        text = next((b.text for b in response.content if b.type == "text"), "")
        if not text:
            return list(DEFAULT_REQUIRED_DOCS)

        parsed = json.loads(text)
        docs = parsed.get("required_docs") or []
        if not docs:
            return list(DEFAULT_REQUIRED_DOCS)
        return docs

    except (AuthenticationError, APIError, json.JSONDecodeError, KeyError):
        return list(DEFAULT_REQUIRED_DOCS)
    except Exception:
        return list(DEFAULT_REQUIRED_DOCS)


def is_known_template(doc_id: str) -> bool:
    return doc_id in KNOWN_TEMPLATE_IDS


def is_mf(doc_id: str) -> bool:
    return doc_id == "mf"
