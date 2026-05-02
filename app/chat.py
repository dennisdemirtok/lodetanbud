"""
Lodet-agenten — chat-backend mot Claude API.

Kräver miljövariabel ANTHROPIC_API_KEY. Strömmar svar tillbaka via SSE.
"""

from __future__ import annotations

import json
import os
from typing import AsyncIterator

from anthropic import AsyncAnthropic, APIError, AuthenticationError


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

STIL:
- Svara på svenska om användaren skriver svenska, annars på engelska
- Var konkret och direkt — använd punktlistor när det hjälper
- Om användaren har ett uppladdat paket, referera till det
- Om du är osäker, säg det — gissa aldrig på siffror, koder eller villkor
- Vid frågor om prissättning: föreslå metoder (E84-justering, historiska matchningar, UE-mejl)
                       men ge inga konkreta priser utan datakälla
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


def _system_with_context(context: dict | None) -> str:
    if not context:
        return SYSTEM_PROMPT
    return (
        SYSTEM_PROMPT
        + "\n\n---\nKONTEXT — användaren har laddat upp ett paket med följande sammanfattning:\n"
        + json.dumps(context, ensure_ascii=False, indent=2)
    )


async def stream_chat(
    messages: list[dict],
    context: dict | None = None,
) -> AsyncIterator[str]:
    """
    Strömma chat-svar som SSE-rader. Yield:ar 'data: {...}\\n\\n' per chunk.
    """
    if not is_configured():
        yield _sse({"type": "error", "message": "ANTHROPIC_API_KEY saknas i miljön. Lägg till den i Railway-variablerna."})
        return

    client = get_client()
    system_text = _system_with_context(context)

    try:
        async with client.messages.stream(
            model="claude-opus-4-7",
            max_tokens=4096,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            system=system_text,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield _sse({"type": "token", "text": text})

            final = await stream.get_final_message()
            usage = {
                "input_tokens": final.usage.input_tokens,
                "output_tokens": final.usage.output_tokens,
                "cache_read_input_tokens": getattr(final.usage, "cache_read_input_tokens", 0),
            }
            yield _sse({"type": "done", "usage": usage})

    except AuthenticationError:
        yield _sse({"type": "error", "message": "API-nyckeln är ogiltig eller återkallad."})
    except APIError as e:
        yield _sse({"type": "error", "message": f"Claude API-fel: {e.message}"})
    except Exception as e:
        yield _sse({"type": "error", "message": f"Oväntat fel: {e}"})


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
