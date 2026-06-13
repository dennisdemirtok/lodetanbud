"""
Autopilot — mål-driven agent som driver ett anbud framåt och pausar för
mänskligt omdöme (Harvey/Legora-mönstret: plan → utför → checkpoint → fortsätt).

run(case_id) kör de säkra, deterministiska stegen autonomt och STANNAR vid
första punkt där den behöver din input:

  1. Applicera GRÖNA prisförslag (hög confidence — evalen: 98% trygga).
     Gul/röd appliceras ALDRIG automatiskt; de lämnas för granskning.
  2. Skriv en liten batch skall-svarsutkast (granska→godkänn gäller; utkast).
  3. Detektera UE-områden → CHECKPOINT om de inte är tilldelade (frågar dig).
  4. Firmatecknare saknas → CHECKPOINT.
  5. Kör formaliagrinden och rapportera vad som är kvar.

Stannar vid första checkpoint; återupptas när du svarat (frontend kör run igen).
"""

from __future__ import annotations

from sqlalchemy import select

from app import afb_templates
from app import agent as lodet_agent
from app import answer_generator, case_archive, company_settings, formalia, price_engine
from app import db as lodet_db
from app import states as st

SKALL_BATCH = 3  # svarsutkast per körning — håll litet (ett Opus-anrop styck)

# Företagsfält som behövs för att ett anbud ska kunna lämnas in
_COMPANY_FIELDS = [
    {"key": "company_name", "label": "Företagsnamn"},
    {"key": "organisationsnummer", "label": "Org.nr"},
    {"key": "contact_name", "label": "Kontaktperson / firmatecknare"},
    {"key": "contact_email", "label": "E-post"},
]


async def run(case_id: str) -> dict:
    case = await case_archive.get_case(case_id)
    if case is None:
        return {"error": "Anbudet hittades inte"}

    state = case.get("state")
    if state in (st.INTAKE, st.EXTRACTING):
        return _result([], None, False, busy=True,
                       summary="Anbudet analyseras fortfarande — kör autopiloten när det är klart.")

    actions: list[dict] = []

    # 1. Applicera gröna prisförslag (aldrig gul/röd)
    applied, reviewed = await _apply_green_prices(case_id, case)
    if applied or reviewed:
        parts = []
        if applied:
            parts.append(f"{applied} priser satta automatiskt (hög träffsäkerhet)")
        if reviewed:
            parts.append(f"{reviewed} kvar att granska (gul/röd)")
        actions.append({"step": "price", "label": "Prissatte mängdförteckningen",
                        "detail": " · ".join(parts), "route": f"#/kalkylator/{case_id}"})
        case = await case_archive.get_case(case_id)  # ladda om efter prisändringar

    # 2. Skriv en batch skall-svarsutkast
    drafted, remaining = await _draft_skall(case_id, case)
    if drafted:
        d = f"{drafted} utkast skrivna"
        if remaining:
            d += f" · {remaining} kvar (kör igen för fler)"
        actions.append({"step": "skall", "label": "Skrev svarsutkast på skall-krav",
                        "detail": d, "route": f"#/krav/{case_id}"})

    # 3. UE-checkpoint — frågar dig vilka underentreprenörer
    ue_areas = _detect_ue_areas(case)
    ue_assignments = case.get("ue_assignments") or {}
    if ue_areas and not ue_assignments:
        # Flywheel: förfyll från inlärt UE-bibliotek (område → företag)
        lib = company_settings.get_settings().get("ue_contacts") or {}
        return _result(actions, {
            "type": "ue",
            "title": "Vilka underentreprenörer använder ni?",
            "intro": "Jag hittade arbeten i mängdförteckningen som brukar handlas upp "
                     "som UE. Fyll i de ni anlitar så genererar jag UE-listan (AFB.32) — "
                     "lämna tomt för det ni gör i egen regi.",
            "areas": [{"area": a, "company": (lib.get(a) or {}).get("company", ""),
                       "email": (lib.get(a) or {}).get("email", "")} for a in ue_areas],
        }, False)
    if ue_areas and ue_assignments and "ue-lista" not in (case.get("drafts") or {}):
        n = await _generate_ue_lista(case_id, case, ue_assignments)
        actions.append({"step": "ue", "label": "Genererade UE-lista (AFB.32)",
                        "detail": f"{n} underentreprenörer kopplade", "route": f"#/krav/{case_id}"})

    # 4. Firmatecknare-checkpoint
    company = company_settings.get_settings()
    if not (company.get("company_name") and company.get("contact_name")):
        return _result(actions, {
            "type": "company",
            "title": "Fyll i företag & firmatecknare",
            "intro": "Det här behövs på anbudet och i AFB-bilagorna. Fyll i en gång "
                     "så minns jag det till nästa anbud.",
            "fields": [{**f, "value": company.get(f["key"]) or ""} for f in _COMPANY_FIELDS],
        }, False)

    # 5. Formaliakontroll
    gate = await formalia.run_gate(case)
    actions.append({
        "step": "formalia", "label": "Körde formaliakontrollen",
        "detail": "Allt klart — redo att lämna in" if gate.get("passed")
                  else f"{gate.get('blocking_count', 0)} punkter blockerar inlämning",
        "route": f"#/slutfor/{case_id}",
    })

    return _result(actions, None, done=gate.get("passed", False))


# ---------- steg-hjälpare ---------------------------------------------------

async def _apply_green_prices(case_id: str, case: dict) -> tuple[int, int]:
    """Sätt à-pris på oprissatta rader DÄR motorn är grön (hög confidence).
    Returnerar (antal_satta, antal_kvar_att_granska)."""
    parsed = case.get("parsed_mf") or {}
    lines = parsed.get("lines") or []
    if not lines:
        return 0, 0

    applied = reviewed = 0
    changed = False
    for line in lines:
        if line.get("unit_price") is not None or line.get("is_lump_sum"):
            continue
        s = await price_engine.suggest(
            line.get("ama_code"), line.get("description"), line.get("unit"),
            exclude_case_id=case_id,
        )
        if not s:
            continue
        if s.get("confidence") == "high":
            line["unit_price"] = s["unit_price"]
            qty = line.get("quantity")
            if qty is not None:
                line["total_amount"] = round(float(qty) * float(s["unit_price"]), 2)
            applied += 1
            changed = True
        else:
            reviewed += 1

    if changed:
        total = sum((l.get("total_amount") or 0) for l in lines)
        meta = parsed.get("metadata") or {}
        meta["total_amount_sek"] = round(total, 2)
        parsed["metadata"] = meta
        await case_archive.update_parsed_mf(case_id, parsed)
        try:
            await price_engine.refresh_observations_for_case(case_id)
        except Exception:
            pass
    return applied, reviewed


async def _draft_skall(case_id: str, case: dict) -> tuple[int, int]:
    """Generera svarsutkast för en liten batch obesvarade fritext-skall-krav."""
    async with lodet_db.SessionLocal() as session:
        reqs = (await session.execute(
            select(lodet_db.Requirement).where(
                lodet_db.Requirement.case_id == case_id,
                lodet_db.Requirement.status == "unanswered",
                lodet_db.Requirement.response_format == "fritext",
                lodet_db.Requirement.kind == "skall",
            ).order_by(lodet_db.Requirement.position)
        )).scalars().all()

    total_open = len(reqs)
    targets = reqs[:SKALL_BATCH]
    if not targets:
        return 0, 0

    done = 0
    for r in targets:
        requirement = {"id": r.id, "af_code": r.af_code, "kind": r.kind,
                       "text": r.text, "response_format": r.response_format}
        try:
            out = await answer_generator.generate_answer(case, requirement)
        except Exception:
            continue
        await case_archive.update_draft(case_id, f"req:{r.id}", out["answer"], edited=False)
        async with lodet_db.SessionLocal() as session:
            row = await session.get(lodet_db.Requirement, r.id)
            if row is not None and row.status == "unanswered":
                row.answer_draft_id = f"req:{r.id}"
                row.status = "drafted"
                await session.commit()
        done += 1
    return done, total_open - done


def _detect_ue_areas(case: dict) -> list[str]:
    lines = (case.get("parsed_mf") or {}).get("lines") or []
    codes = [l.get("ama_code") for l in lines if l.get("ama_code")]
    return lodet_agent._suggest_ue_areas(codes)


async def _generate_ue_lista(case_id: str, case: dict, assignments: dict) -> int:
    """Bygg AFB.32-utkast ur UE-tilldelningarna (område → {company, email})."""
    company = company_settings.get_settings()
    suggestions = []
    for area, a in assignments.items():
        comp = (a or {}).get("company")
        if comp:
            suggestions.append({"område": area, "ue": comp, "andel": "—"})
    if not suggestions:
        return 0
    text = afb_templates.ue_lista(
        project_name=case.get("project_name") or case.get("source_name") or "—",
        company_name=company.get("company_name") or "—",
        suggestions=suggestions,
    )
    await case_archive.update_draft(case_id, "ue-lista", text, edited=False)
    return len(suggestions)


def _result(actions: list[dict], checkpoint: dict | None, done: bool,
            busy: bool = False, summary: str | None = None) -> dict:
    if summary is None:
        if checkpoint:
            summary = checkpoint["title"]
        elif done:
            summary = "Anbudet är klart att lämna in 🎉"
        else:
            summary = "Körde det jag kunde — se vad som är kvar i listan."
    return {"actions": actions, "checkpoint": checkpoint, "done": done,
            "busy": busy, "summary": summary}
