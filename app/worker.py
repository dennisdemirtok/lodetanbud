"""
Asyncio-worker (genomförandeplan AP1) — körs som task i FastAPI:s lifespan.

Handlers registreras via @register("kind"). Pipeline-modulen importeras
lazy i loopen för att undvika cirkulära imports vid appstart.
"""

from __future__ import annotations

import asyncio
import traceback
from typing import Awaitable, Callable

from app import jobs as jobq

HANDLERS: dict[str, Callable[..., Awaitable[dict]]] = {}


def register(kind: str):
    def deco(fn):
        HANDLERS[kind] = fn
        return fn
    return deco


async def worker_loop() -> None:
    from app import pipeline  # noqa: F401 — registrerar handlers vid import

    while True:
        try:
            job = await jobq.claim_next()
            if job is None:
                await asyncio.sleep(1.0)
                continue

            handler = HANDLERS.get(job.kind)
            if handler is None:
                await jobq.fail_or_retry(job.id, f"Okänd jobbtyp: {job.kind}", max_attempts=0)
                continue

            try:
                result = await handler(job)
                await jobq.finish(job.id, result)
            except Exception as e:
                tb = traceback.format_exc()
                await jobq.fail_or_retry(job.id, f"{e}\n{tb[-1500:]}")

        except asyncio.CancelledError:
            raise
        except Exception:
            # Worker-loopen får aldrig dö av ett enskilt fel
            await asyncio.sleep(2.0)
