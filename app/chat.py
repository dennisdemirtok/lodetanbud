"""
Lodet-agenten — chat-backend mot Claude API.

Kräver miljövariabel ANTHROPIC_API_KEY. Strömmar svar tillbaka via SSE.
"""

from __future__ import annotations

import json
import os
from typing import AsyncIterator

from anthropic import AsyncAnthropic, APIError, AuthenticationError

from app import case_archive


SYSTEM_PROMPT = """Du är Lodet-agenten — en domänexpert på svenska bygg- och anläggningsanbud.

DIN ROLL:
Du hjälper bygg- och anläggningsentreprenörer förstå förfrågningsunderlag,
prissätta anbud, och generera anbudsdokument korrekt.

DOMÄNEXPERTIS:
- AMA-systemen: AMA Anläggning 23, AMA Hus 21, AMA El, AF AMA 21
- AMA-koder följer mönstret SBC.21, YGB.6312 osv — hierarkiskt med 1–4 nivåer
- Mängdförteckningar (MF): KOD/TEXT/ENHET/MÄNGD/À-PRIS/BELOPP-format
- Klumpsumma = poster utan enhet/mängd/à-pris, bara totalbelopp (ofta 1 kr som placeholder)
- AF-dokument (AFA, AFB, AFC, AFD, AFG, AFH) — administrativa villkor
- AFB-bilagor: AFB.31 anbudssumma, AFB.32 underentreprenörer, AFB.33 referenser
- E84-index per kapitel:
  - B/C/D/E (anläggning) → E84:3.2
  - F (hus) → E84:4.0
  - P/Q/R (VVS) → E84:6.X
  - S/T (el) → E84:7.X
  - Y (märkning/dokumentation) → KPI
- AB 04 / ABT 06 — standardvillkor för utförande- och totalentreprenad
- Sekretessbegäran enligt FHL §1 + OSL 9:3 + 31:16

LODETS FUNKTIONER (vad agenten kan länka till):
- Multi-upload av paket på Start: PDF + CSV + Excel
- Filklassificering: MF, AF, TB, ritningar (K/T/V/A/M-disciplin), IF, RF, kontrakt
- Excel-mall med prisförslag baserat på historiska matchningar
- AMA-bibliotek för referens
- Mall-generator för AFB.31, AFB.32, sekretessbegäran, missiv
- UE-mejl-generator baserat på AMA-sektioner i MF

DU UTFÖR ÅTGÄRDER:
Du har verktyg och du ANVÄNDER dem — du är en agent som jobbar, inte en FAQ.
- Frågar användaren om sitt anbuds läge → get_case_overview FÖRST, svara sedan ur datan.
- Ber användaren om priser/prissättning → suggest_prices och redovisa täckningen.
- Frågar användaren vad som saknas/om anbudet är klart → run_formalia.
- Ber användaren om hjälp med kravsvar → list_open_requirements, sedan generate_answers.
- Nämner användaren ett anbud vid namn utan id → list_cases för att hitta det.
Kedja verktyg när det behövs. Sammanfatta ALLTID vad du gjorde och vad du såg,
med konkreta siffror ur verktygsresultaten. Hänvisa till rutterna (knappar visas
automatiskt). Hitta aldrig på data som verktygen inte gav dig.

GRÄNSER (granska→godkänn-principen):
- Du applicerar aldrig priser och lämnar aldrig in — användaren granskar alltid.
- Svarsutkast du genererar är utkast (status 'drafted'), aldrig godkända svar.
- Saknas bolagsfakta blir det [SAKNAS: …]-markörer — aldrig påhitt.

STIL:
- Svara på svenska om användaren skriver svenska, annars på engelska
- Var konkret och direkt — använd punktlistor när det hjälper
- Om användaren har ett uppladdat paket, referera till det
- Om du är osäker, säg det — gissa aldrig på siffror, koder eller villkor
- Vid prisfrågor utan datakälla: kör suggest_prices istället för att resonera fritt
- Håll svar kortfattade om frågan är enkel; var utförlig endast vid komplexa resonemang
"""


_client: AsyncAnthropic | None = None


def get_client() -> AsyncAnthropic:
    """Lazy-initiera klienten så att appen kan starta utan API-nyckel."""
    global _client
    if _client is None:
        _client = AsyncAnthropic()
    return _client


def is_configured() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _system_with_context(
    context: dict | None,
    relevant_cases: list[dict] | None = None,
    case_id: str | None = None,
) -> str:
    parts = [SYSTEM_PROMPT]
    relevant_cases = relevant_cases or []

    if case_id:
        parts.append(f"\n---\nAKTUELLT ANBUD: case_id = {case_id}")
        parts.append("Användaren tittar på det här anbudet just nu. Använd det som "
                     "case_id i verktygen om hen inte uttryckligen menar ett annat anbud.")

    if relevant_cases:
        parts.append("\n---\nKUNSKAPSBAS — relevanta tidigare anbud från arkivet:")
        for case in relevant_cases:
            parts.append("")
            parts.append(case_archive.case_summary_for_context(case))
        parts.append("")
        parts.append("Använd dessa lärdomar när det är relevant. Säg när du refererar till "
                     "tidigare projekt och var tydlig med datum och dokumentnummer.")

    if context:
        parts.append("\n---\nAKTUELL UPPLADDNING — användaren har just laddat upp ett paket:")
        parts.append(json.dumps(context, ensure_ascii=False, indent=2))

    return "\n".join(parts)


MAX_TOOL_ROUNDS = 6


async def stream_chat(
    messages: list[dict],
    context: dict | None = None,
    case_id: str | None = None,
) -> AsyncIterator[str]:
    """
    Strömma chat-svar som SSE-rader, med agent-loop: modellen kan anropa
    verktyg (agent_tools); varje verktygskörning skickas som tool_start/
    tool_result-events så UI:t visar arbetsstegen Harvey-stil.
    """
    if not is_configured():
        yield _sse({"type": "error", "message": "ANTHROPIC_API_KEY saknas i miljön. Lägg till den i Railway-variablerna."})
        return

    from app import agent_tools

    client = get_client()
    last_user_query = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_query = m.get("content") or ""
            break

    # Hämta relevanta cases från arkivet (async sedan AP1/DB-bytet)
    try:
        relevant_cases = await case_archive.find_relevant(last_user_query, limit=3)
    except Exception:
        relevant_cases = []
    system_text = _system_with_context(context, relevant_cases=relevant_cases, case_id=case_id)

    convo: list[dict] = list(messages)

    try:
        for _round in range(MAX_TOOL_ROUNDS):
            async with client.messages.stream(
                model="claude-opus-4-7",
                max_tokens=4096,
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
                system=system_text,
                messages=convo,
                tools=agent_tools.TOOLS,
            ) as stream:
                async for text in stream.text_stream:
                    yield _sse({"type": "token", "text": text})
                final = await stream.get_final_message()

            if final.stop_reason != "tool_use":
                usage = {
                    "input_tokens": final.usage.input_tokens,
                    "output_tokens": final.usage.output_tokens,
                    "cache_read_input_tokens": getattr(final.usage, "cache_read_input_tokens", 0),
                }
                yield _sse({"type": "done", "usage": usage})
                return

            # Verktygsrunda: kör varje tool_use, visa stegen i UI:t
            convo.append({"role": "assistant", "content": final.content})
            tool_results = []
            for block in final.content:
                if block.type != "tool_use":
                    continue
                label = agent_tools.LABELS.get(block.name, block.name)
                yield _sse({"type": "tool_start", "name": block.name, "label": label})

                outcome = await agent_tools.execute(block.name, dict(block.input or {}))

                yield _sse({
                    "type": "tool_result",
                    "name": block.name,
                    "label": label,
                    "summary": outcome.get("summary") or "klart",
                    **({"route": outcome["route"], "route_label": outcome.get("route_label") or "Öppna"}
                       if outcome.get("route") else {}),
                })
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(outcome.get("result"), ensure_ascii=False, default=str),
                })
            convo.append({"role": "user", "content": tool_results})

        yield _sse({"type": "done", "usage": {}})

    except AuthenticationError:
        yield _sse({"type": "error", "message": "API-nyckeln är ogiltig eller återkallad."})
    except APIError as e:
        yield _sse({"type": "error", "message": f"Claude API-fel: {e.message}"})
    except Exception as e:
        yield _sse({"type": "error", "message": f"Oväntat fel: {e}"})


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
