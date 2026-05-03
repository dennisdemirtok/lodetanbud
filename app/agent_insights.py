"""
Agent-insights — Claude granskar förfrågningsunderlaget och lyfter
proaktivt fram saker användaren bör uppmärksamma INNAN anbudet skapas.

Ger paketet "liv": istället för en tom checklista listar agenten
deadlines, compliance-krav, risker, beställarens egna mallar och
frågor som behöver besvaras innan utkasten kan färdigställas.
"""

from __future__ import annotations

import json
import os

from anthropic import APIError, AsyncAnthropic, AuthenticationError


_INSIGHTS_SCHEMA = {
    "type": "object",
    "properties": {
        "observations": {
            "type": "array",
            "description": "Viktiga saker användaren bör veta. 0–8 stycken.",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["deadline", "compliance", "risk", "scope", "missing", "info"],
                        "description": (
                            "deadline=tidsfrist; compliance=krav på behörighet/försäkring/intyg; "
                            "risk=geoteknik/spår/miljö/väderfönster; scope=oklarhet i omfattning; "
                            "missing=något i AF saknar information; info=övrigt värt att veta"
                        ),
                    },
                    "title": {"type": "string", "description": "Kort rubrik på svenska, max 80 tecken."},
                    "body": {"type": "string", "description": "1–3 meningar med detalj."},
                    "source_section": {"type": "string", "description": "Var i AF-texten detta står (t.ex. AFB.13). Tom om okänt."},
                },
                "required": ["type", "title", "body", "source_section"],
                "additionalProperties": False,
            },
        },
        "questions": {
            "type": "array",
            "description": "Frågor agenten har för användaren. 0–5 stycken.",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "Direkt fråga på svenska."},
                    "why_it_matters": {"type": "string", "description": "Varför detta påverkar anbudet."},
                },
                "required": ["question", "why_it_matters"],
                "additionalProperties": False,
            },
        },
        "vendor_templates": {
            "type": "array",
            "description": "Mallar som beställaren tillhandahållit i paketet. Mappar till draft-id om relevant.",
            "items": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "maps_to_draft_id": {
                        "type": "string",
                        "description": (
                            "Om mallen ersätter ett av våra standard-utkast, ange id: "
                            "'sekretess', 'missiv', eller annan slug. Tom sträng om ingen mappning."
                        ),
                    },
                    "note": {"type": "string", "description": "Kort kommentar om hur mallen ska användas."},
                },
                "required": ["filename", "maps_to_draft_id", "note"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["observations", "questions", "vendor_templates"],
    "additionalProperties": False,
}


_INSIGHTS_SYSTEM = """Du är en svensk anbudsexpert som granskar ett upphandlingspaket
(AF + bilagor + MF) och lyfter proaktivt fram det som anbudsgivaren behöver
uppmärksamma INNAN anbudet skapas.

DITT MÅL:
1. Hitta deadlines, behörighets-/försäkringskrav, geotekniska/miljö-/spår-risker
2. Notera scope-oklarheter (saker som kan tolkas på flera sätt)
3. Lista beställarens egna mallar som ersätter standard-utkast (sekretess, missiv)
4. Ställ konkreta frågor till användaren som behövs för att färdigställa anbudet

REGLER:
- Skriv på svenska, var konkret och specifik
- Hänvisa till AFB-koder eller bilagenummer när det går
- Ställ INTE generella frågor — bara sådana där användarens svar faktiskt påverkar anbudet
- Lista BARA mallar som anbudsgivaren ska FYLLA I och skicka tillbaka, inte underlag att läsa
- Maximalt 8 observationer, 5 frågor, 6 vendor-mallar
- Hoppa över sektioner om inget värt att rapportera finns
"""


_DEFAULT_RESPONSE = {"observations": [], "questions": [], "vendor_templates": []}


async def extract_insights(
    package_summary: dict,
    files: list[dict],
    af_text: str,
) -> dict:
    """
    Returnera {observations, questions, vendor_templates} baserat på
    AF-texten och fil-listan. Faller tillbaka till heuristisk vendor-
    template-detektion om Claude inte är konfigurerad.
    """
    fallback = {
        "observations": [],
        "questions": [],
        "vendor_templates": _detect_vendor_templates_heuristic(files),
    }

    if not os.getenv("ANTHROPIC_API_KEY"):
        return fallback

    if not af_text or len(af_text.strip()) < 200:
        return fallback

    try:
        client = AsyncAnthropic()
        prompt = _build_prompt(package_summary, files, af_text)

        response = await client.messages.create(
            model="claude-opus-4-7",
            max_tokens=3072,
            system=_INSIGHTS_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": _INSIGHTS_SCHEMA,
                }
            },
        )

        text = next((b.text for b in response.content if b.type == "text"), "")
        if not text:
            return fallback

        parsed = json.loads(text)
        return {
            "observations": parsed.get("observations") or [],
            "questions": parsed.get("questions") or [],
            "vendor_templates": parsed.get("vendor_templates") or fallback["vendor_templates"],
        }

    except (AuthenticationError, APIError, json.JSONDecodeError, KeyError):
        return fallback
    except Exception:
        return fallback


def _build_prompt(package_summary: dict, files: list[dict], af_text: str) -> str:
    parts = []
    parts.append("Här är ett svenskt förfrågningsunderlag. Granska det och returnera observations, questions och vendor_templates enligt schemat.")
    parts.append("")
    parts.append("PAKETET:")
    parts.append(f"  Projekt: {package_summary.get('project_name') or '—'}")
    parts.append(f"  Beställare: {package_summary.get('customer') or '—'}")
    parts.append(f"  Antal filer: {package_summary.get('file_count') or len(files)}")
    parts.append("")
    parts.append("FILER I PAKETET:")
    for f in files[:50]:
        parts.append(f"  - [{f.get('type')}] {f.get('filename')} ({f.get('label')})")
    if len(files) > 50:
        parts.append(f"  ... och {len(files) - 50} filer till")
    parts.append("")
    parts.append("AF-TEXT (max 40 000 tecken):")
    parts.append(af_text[:40_000])
    parts.append("")
    parts.append("Svara med fullt JSON enligt schemat (observations, questions, vendor_templates).")
    return "\n".join(parts)


def _detect_vendor_templates_heuristic(files: list[dict]) -> list[dict]:
    """Fallback när Claude inte är tillgänglig — basera bara på filtyp 'mall'."""
    out = []
    for f in files:
        if f.get("type") == "mall":
            subtype = f.get("subtype") or ""
            note = f.get("label") or "Beställarens mall"
            maps_to = ""
            if "sekret" in (f.get("filename") or "").lower():
                maps_to = "sekretess"
            out.append({
                "filename": f.get("filename") or "",
                "maps_to_draft_id": maps_to,
                "note": note,
            })
        elif f.get("type") == "sekretess":
            out.append({
                "filename": f.get("filename") or "",
                "maps_to_draft_id": "sekretess",
                "note": "Sekretess-mall från beställaren — använd istället för standardtexten",
            })
    return out
