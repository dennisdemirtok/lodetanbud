"""
Lärdoms-extraktor — använder Claude för att hitta återanvändbara fakta i ett analyserat paket.

Strukturerade outputs säkerställer att Claude returnerar rader vi kan
indexera och söka mot senare. Faller tillbaka till heuristik om Claude API
inte är konfigurerad.
"""

from __future__ import annotations

import json
import os

from anthropic import APIError, AsyncAnthropic, AuthenticationError


_LESSONS_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "En mening som sammanfattar projektet och vad som är värt att minnas."
        },
        "lessons": {
            "type": "array",
            "description": "Återanvändbara fakta från detta paket. Varje lärdom ska kunna stå själv och vara nyttig för framtida prissättning.",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "price_point",
                            "ue_decision",
                            "risk_factor",
                            "scope_note",
                            "customer_pattern",
                            "general"
                        ]
                    },
                    "ama_code": {
                        "type": "string",
                        "description": "Relevant AMA-kod om tillämpligt, t.ex. 'SBC.21'. Tom sträng om inte."
                    },
                    "note": {
                        "type": "string",
                        "description": "Kort fritextlärdom på svenska."
                    }
                },
                "required": ["type", "ama_code", "note"],
                "additionalProperties": False
            }
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Sökord som beskriver projektet, t.ex. ['vägbelysning', 'små-kommun', 'el']."
        }
    },
    "required": ["summary", "lessons", "tags"],
    "additionalProperties": False
}


_EXTRACTOR_SYSTEM = """Du är en analytiker som granskar ett svenskt anbudspaket och extraherar
återanvändbara fakta för framtida prissättning.

För varje paket:
1. Sammanfatta projektet i en mening (vem är beställaren, vad är scopet, vilken storlek)
2. Lista 3–8 lärdomar som kan vara nyttiga vid framtida liknande anbud
3. Tagga med sökord (teknikområde, kommuntyp, projekttyp)

LÄRDOMS-TYPER:
- price_point: konkret prispunkt (à-pris, totalpris) för en viss AMA-kod
- ue_decision: vad lämnades till UE och varför
- risk_factor: något att vara försiktig med (geoteknik, närhet till spår, väderfönster, ...)
- scope_note: oklarhet eller scope-fråga som behöver klarläggas
- customer_pattern: mönster i hur denna beställare upphandlar
- general: annat värt att minnas

REGLER:
- Skriv på svenska
- Var specifik — undvik generaliseringar som "vanlig prisnivå"
- Använd siffror där de finns
- Om paketet saknar information för en typ, hoppa över den (lägg inte till tomma)
- Maximalt 8 lärdomar per paket"""


async def extract_lessons(
    package_summary: dict,
    parsed_mf: dict | None,
    files: list[dict],
) -> dict:
    """
    Returnera {summary, lessons[], tags[]}.
    Faller tillbaka till heuristisk extraktion om Claude inte är konfigurerad eller felar.
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        return _fallback(package_summary, parsed_mf, files)

    try:
        client = AsyncAnthropic()
        prompt = _build_extractor_prompt(package_summary, parsed_mf, files)

        response = await client.messages.create(
            model="claude-opus-4-7",
            max_tokens=2048,
            system=_EXTRACTOR_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": _LESSONS_SCHEMA,
                }
            },
        )

        text = next((b.text for b in response.content if b.type == "text"), "")
        if not text:
            return _fallback(package_summary, parsed_mf, files)

        parsed = json.loads(text)
        return {
            "summary": parsed.get("summary") or "",
            "lessons": parsed.get("lessons") or [],
            "tags": parsed.get("tags") or [],
        }

    except (AuthenticationError, APIError, json.JSONDecodeError, KeyError):
        return _fallback(package_summary, parsed_mf, files)
    except Exception:
        return _fallback(package_summary, parsed_mf, files)


def _build_extractor_prompt(
    package_summary: dict,
    parsed_mf: dict | None,
    files: list[dict],
) -> str:
    parts = []
    parts.append("Här är ett analyserat anbudspaket. Extrahera återanvändbara lärdomar.")
    parts.append("")
    parts.append("PAKETET:")
    parts.append(json.dumps(_compact_summary(package_summary), ensure_ascii=False, indent=2))
    parts.append("")

    if files:
        parts.append("FILER:")
        for f in files[:30]:
            parts.append(f"  - {f.get('filename')} ({f.get('label')})")
        if len(files) > 30:
            parts.append(f"  ... och {len(files) - 30} filer till")
        parts.append("")

    if parsed_mf:
        parts.append("MÄNGDFÖRTECKNING (sample, max 30 rader):")
        meta = parsed_mf.get("metadata") or {}
        parts.append(f"  Projekt: {meta.get('project_name') or '—'}")
        parts.append(f"  Totalbelopp: {meta.get('total_amount_sek') or '—'} kr")
        parts.append("")
        for line in (parsed_mf.get("lines") or [])[:30]:
            ama = line.get("ama_code") or "—"
            desc = (line.get("description") or "")[:60]
            unit = line.get("unit") or "—"
            qty = line.get("quantity")
            price = line.get("unit_price")
            total = line.get("total_amount")
            parts.append(f"  [{ama}] {desc} | {unit} {qty} × {price} kr = {total} kr")

    parts.append("")
    parts.append("Returnera summary, lessons (3–8) och tags enligt schemat.")

    return "\n".join(parts)


def _compact_summary(s: dict) -> dict:
    """Kompakt version utan onödig brus."""
    return {
        "project_name": s.get("project_name"),
        "customer": s.get("customer"),
        "file_count": s.get("file_count"),
        "type_breakdown": s.get("type_breakdown"),
        "disciplines": s.get("disciplines"),
        "ritning_count": s.get("ritning_count"),
        "has_mf": s.get("has_mf"),
        "has_af": s.get("has_af"),
        "has_tb": s.get("has_tb"),
        "has_kontrakt": s.get("has_kontrakt"),
    }


def _fallback(package_summary: dict, parsed_mf: dict | None, files: list[dict]) -> dict:
    """Heuristisk extraktion när Claude inte är tillgänglig."""
    lessons: list[dict] = []
    tags: list[str] = []

    if package_summary.get("project_name"):
        tags.append(package_summary["project_name"][:40])

    if parsed_mf:
        meta = parsed_mf.get("metadata") or {}
        if meta.get("total_amount_sek"):
            lessons.append({
                "type": "general",
                "ama_code": "",
                "note": f"Totalbelopp för {meta.get('project_name') or 'detta projekt'}: "
                        f"{meta['total_amount_sek']:,.0f} kr".replace(",", " ")
            })
        for line in (parsed_mf.get("lines") or [])[:5]:
            if line.get("unit_price") and line.get("ama_code"):
                desc = (line.get("description") or "")[:50]
                lessons.append({
                    "type": "price_point",
                    "ama_code": line["ama_code"],
                    "note": f"{desc}: {line['unit_price']:,.0f} kr/{line.get('unit', 'st')}"
                            .replace(",", " "),
                })

    summary_text = package_summary.get("project_name") or "Anbudspaket"
    if files:
        summary_text += f" — {len(files)} filer"

    return {"summary": summary_text, "lessons": lessons, "tags": tags}
