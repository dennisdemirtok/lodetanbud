"""
LLM-anrop — standardiserat (genomförandeplan AP2.2).

Ersätter de spridda anropssätten i requirement_extractor, lesson_extractor
och agent_insights: structured output med json_schema, retry vid
valideringsfel, och event-loggning per anrop (modell, tokens, latens,
validerad/ej) — det är vår observability tills vi behöver mer.

Modellval: extraktion kör Sonnet som default (schema + retry behöver inte
största modellen); Opus sparas till chatten och AFB-utkasten (AP5).
Överstyr med LODET_EXTRACT_MODEL.
"""

from __future__ import annotations

import json
import os
import time

from anthropic import APIError, AsyncAnthropic, AuthenticationError

EXTRACT_MODEL = os.getenv("LODET_EXTRACT_MODEL", "claude-sonnet-4-6")

_client: AsyncAnthropic | None = None


def is_configured() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic()
    return _client


async def call_structured(
    *,
    system: str,
    prompt: str,
    schema: dict,
    purpose: str,
    case_id: str | None = None,
    model: str | None = None,
    max_tokens: int = 2048,
    max_retries: int = 3,
) -> tuple[dict | None, str | None]:
    """
    Structured LLM-anrop med retry. Returnerar (parsed, None) vid framgång,
    (None, felbeskrivning) annars — anroparen avgör fallback eller
    needs_review. Varje försök loggas som llm_call-event.
    """
    if not is_configured():
        return None, "ANTHROPIC_API_KEY saknas"

    model = model or EXTRACT_MODEL
    client = get_client()
    required = set(schema.get("required") or [])
    last_err: str | None = None

    for attempt in range(1, max_retries + 1):
        t0 = time.monotonic()
        usage: dict = {}
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_config={
                    "format": {
                        "type": "json_schema",
                        "schema": schema,
                    }
                },
            )
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
            text = next((b.text for b in response.content if b.type == "text"), "")
            parsed = json.loads(text)
            missing = required - set(parsed)
            if missing:
                raise ValueError(f"saknade fält: {sorted(missing)}")

            await _log(case_id, purpose, model, attempt, t0, usage, ok=True)
            return parsed, None

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            last_err = f"valideringsfel: {e}"
            await _log(case_id, purpose, model, attempt, t0, usage, ok=False, error=last_err)
            continue
        except AuthenticationError:
            last_err = "API-nyckeln är ogiltig eller återkallad"
            await _log(case_id, purpose, model, attempt, t0, usage, ok=False, error=last_err)
            return None, last_err
        except APIError as e:
            last_err = f"API-fel: {getattr(e, 'message', e)}"
            await _log(case_id, purpose, model, attempt, t0, usage, ok=False, error=last_err)
            continue
        except Exception as e:
            last_err = str(e)
            await _log(case_id, purpose, model, attempt, t0, usage, ok=False, error=last_err)
            continue

    return None, last_err


async def _log(
    case_id: str | None,
    purpose: str,
    model: str,
    attempt: int,
    t0: float,
    usage: dict,
    ok: bool,
    error: str | None = None,
) -> None:
    """Logga anropet i events-tabellen. Får aldrig krascha anropet."""
    try:
        from app.db import SessionLocal, log_event

        data = {
            "purpose": purpose,
            "model": model,
            "attempt": attempt,
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "ok": ok,
            **usage,
        }
        if error:
            data["error"] = error[:200]
        async with SessionLocal() as session:
            await log_event(session, case_id, "llm_call", data)
            await session.commit()
    except Exception:
        pass
