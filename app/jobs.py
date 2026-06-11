"""
Jobbkö — tabell-baserad (genomförandeplan AP1).

Dialekt-portabel claim utan FOR UPDATE SKIP LOCKED: en enda in-process-
worker gör att optimistisk UPDATE räcker (rowcount=0 → någon annan tog
jobbet → hoppa). SKIP LOCKED/Celery först när vi kör flera instanser.
"""

from __future__ import annotations

from sqlalchemy import select, update

from app.db import Job, SessionLocal, log_event, new_id, utcnow_iso


async def enqueue(session, case_id: str | None, kind: str, payload: dict | None = None) -> Job:
    """Köa ett jobb i en befintlig session (commit görs av anroparen)."""
    job = Job(
        id=new_id("job"),
        case_id=case_id,
        kind=kind,
        status="queued",
        attempts=0,
        payload=payload or {},
        created_at=utcnow_iso(),
    )
    session.add(job)
    await log_event(session, case_id, "job_queued", {"kind": kind, "job_id": job.id})
    return job


async def enqueue_standalone(case_id: str | None, kind: str, payload: dict | None = None) -> str:
    """Köa ett jobb i egen transaktion. Returnerar job-id."""
    async with SessionLocal() as session:
        job = await enqueue(session, case_id, kind, payload)
        await session.commit()
        return job.id


async def claim_next() -> Job | None:
    """Plocka nästa köade jobb. Optimistisk claim — None om kön är tom
    eller någon annan hann före."""
    async with SessionLocal() as session:
        row = (
            await session.execute(
                select(Job).where(Job.status == "queued").order_by(Job.created_at).limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        res = await session.execute(
            update(Job)
            .where(Job.id == row.id, Job.status == "queued")
            .values(status="running", started_at=utcnow_iso(), attempts=row.attempts + 1)
        )
        await session.commit()
        if res.rowcount == 0:
            return None
        await session.refresh(row)
        return row


async def finish(job_id: str, result: dict | None = None) -> None:
    async with SessionLocal() as session:
        job = await session.get(Job, job_id)
        if job is None:
            return
        job.status = "done"
        job.result = result or {}
        job.finished_at = utcnow_iso()
        await log_event(session, job.case_id, "job_done", {"kind": job.kind, "job_id": job.id})
        await session.commit()


async def fail_or_retry(job_id: str, error: str, max_attempts: int = 3) -> None:
    """3:e felet → failed + event; annars tillbaka till kön."""
    async with SessionLocal() as session:
        job = await session.get(Job, job_id)
        if job is None:
            return
        job.error = (error or "")[:2000]
        if job.attempts >= max_attempts:
            job.status = "failed"
            job.finished_at = utcnow_iso()
            await log_event(
                session, job.case_id, "job_failed",
                {"kind": job.kind, "job_id": job.id, "attempts": job.attempts, "error": job.error[:300]},
            )
        else:
            job.status = "queued"
            await log_event(
                session, job.case_id, "job_retry",
                {"kind": job.kind, "job_id": job.id, "attempt": job.attempts},
            )
        await session.commit()


async def reset_orphans() -> int:
    """Vid uppstart: 'running'-jobb från en kraschad process → tillbaka
    till kön (idempotenta handlers gör omkörning säker)."""
    async with SessionLocal() as session:
        res = await session.execute(
            update(Job).where(Job.status == "running").values(status="queued")
        )
        await session.commit()
        return res.rowcount or 0


async def jobs_for_case(session, case_id: str) -> list[dict]:
    rows = (
        await session.execute(
            select(Job).where(Job.case_id == case_id).order_by(Job.created_at)
        )
    ).scalars().all()
    return [
        {
            "id": j.id,
            "kind": j.kind,
            "status": j.status,
            "attempts": j.attempts,
            "error": j.error,
            "created_at": j.created_at,
            "finished_at": j.finished_at,
        }
        for j in rows
    ]
