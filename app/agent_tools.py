"""
Agent-verktyg — chatt-agenten UTFÖR åtgärder, inte bara svarar.

Varje verktyg återanvänder samma interna vägar som UI-knapparna
(prismotorn, formaliagrinden, svarsgeneratorn) — agenten kan alltså
aldrig göra något som användaren inte kan göra själv, och allt loggas
som samma events. Read-only där det är rimligt: prisförslag APPLICERAS
inte av agenten — användaren granskar i kalkylatorn (granska→godkänn-
principen gäller även agenten).
"""

from __future__ import annotations

from app import case_archive, formalia, price_engine
from app import db as lodet_db
from app import states as case_states
from sqlalchemy import select


TOOLS: list[dict] = [
    {
        "name": "list_cases",
        "description": "Lista användarens anbud med state och nästa steg. Använd när användaren refererar till ett anbud du inte vet id för.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_case_overview",
        "description": "Hämta full översikt för ett anbud: MF-status, kravläge, formalia-snabbstatus, obesvarade frågor. Kör ALLTID denna först när användaren frågar om sitt aktuella anbud.",
        "input_schema": {
            "type": "object",
            "properties": {"case_id": {"type": "string"}},
            "required": ["case_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "suggest_prices",
        "description": "Kör prismotorn (deterministisk kaskad mot historiska kalkyler) för anbudets oprissatta MF-rader. Applicerar INGET — returnerar täckning och exempel; användaren granskar förslagen i kalkylatorn.",
        "input_schema": {
            "type": "object",
            "properties": {"case_id": {"type": "string"}},
            "required": ["case_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run_formalia",
        "description": "Kör formaliagrindens deterministiska checklista för anbudet (skall-krav besvarade, bilagor, anbudssumma matchar kalkyl, deadline, firmatecknare, UE-lista).",
        "input_schema": {
            "type": "object",
            "properties": {"case_id": {"type": "string"}},
            "required": ["case_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_open_requirements",
        "description": "Lista obesvarade krav för ett anbud (skall-krav först). Använd innan generate_answers eller när användaren frågar vad som återstår.",
        "input_schema": {
            "type": "object",
            "properties": {"case_id": {"type": "string"}},
            "required": ["case_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "generate_answers",
        "description": "Generera AFB-svarsutkast för obesvarade fritext-krav (max 3 per anrop, skall-krav först). Utkasten sparas med status 'drafted' och luckor markeras [SAKNAS: …] — användaren granskar i kravmatrisen. Hittar aldrig på bolagsfakta.",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string"},
                "max_count": {"type": "integer", "minimum": 1, "maximum": 3},
            },
            "required": ["case_id"],
            "additionalProperties": False,
        },
    },
]

# UI-etiketter per verktyg — visas som arbetssteg i chatten
LABELS = {
    "list_cases": "Hämtar anbudslistan",
    "get_case_overview": "Läser anbudets status",
    "suggest_prices": "Kör prismotorn mot historiken",
    "run_formalia": "Kör formaliakontrollen",
    "list_open_requirements": "Hämtar obesvarade krav",
    "generate_answers": "Skriver svarsutkast",
}


async def execute(name: str, args: dict) -> dict:
    """Kör ett verktyg. Returnerar {result, summary, route?} — result går
    till modellen, summary+route till UI:t som utfört-steg."""
    fn = {
        "list_cases": _list_cases,
        "get_case_overview": _get_case_overview,
        "suggest_prices": _suggest_prices,
        "run_formalia": _run_formalia,
        "list_open_requirements": _list_open_requirements,
        "generate_answers": _generate_answers,
    }.get(name)
    if fn is None:
        return {"result": {"error": f"okänt verktyg: {name}"}, "summary": "Okänt verktyg"}
    try:
        return await fn(args)
    except Exception as e:
        return {"result": {"error": str(e)}, "summary": f"Fel: {e}"}


async def _list_cases(args: dict) -> dict:
    cases = await case_archive.list_cases()
    rows = [{
        "case_id": c["id"],
        "projekt": c.get("project_name") or c.get("source_name"),
        "state": c.get("state"),
        "state_label": case_states.LABELS.get(c.get("state"), c.get("state")),
        "summa_sek": c.get("total_amount_sek"),
    } for c in cases[:25]]
    return {
        "result": {"cases": rows},
        "summary": f"{len(rows)} anbud",
    }


async def _get_case_overview(args: dict) -> dict:
    case_id = args["case_id"]
    case = await case_archive.get_case(case_id)
    if case is None:
        return {"result": {"error": "case finns inte"}, "summary": "Anbudet hittades inte"}

    lines = (case.get("parsed_mf") or {}).get("lines") or []
    priced = [l for l in lines if l.get("unit_price") is not None]
    total = sum((l.get("amount") or 0) for l in lines if l.get("amount"))

    async with lodet_db.SessionLocal() as session:
        reqs = (await session.execute(
            select(lodet_db.Requirement).where(lodet_db.Requirement.case_id == case_id)
        )).scalars().all()
    skall = [r for r in reqs if r.kind == "skall"]
    answered = [r for r in reqs if r.status in ("answered", "na")]
    drafted = [r for r in reqs if r.status == "drafted"]

    questions = [
        q for q in ((case.get("insights") or {}).get("questions") or [])
        if isinstance(q, dict) and not q.get("answer")
    ]

    return {
        "result": {
            "case_id": case_id,
            "projekt": case.get("project_name") or case.get("source_name"),
            "state": case.get("state"),
            "state_label": case_states.LABELS.get(case.get("state"), case.get("state")),
            "mf": {
                "rader": len(lines),
                "prissatta": len(priced),
                "oprissatta": len(lines) - len(priced),
                "summa_sek": round(total),
            },
            "krav": {
                "totalt": len(reqs),
                "skall": len(skall),
                "besvarade": len(answered),
                "utkast": len(drafted),
                "obesvarade": len(reqs) - len(answered) - len(drafted),
            },
            "obesvarade_fragor_till_anvandaren": [q.get("question") for q in questions][:5],
            "rutter": {
                "kalkylator": f"#/kalkylator/{case_id}",
                "kravmatris": f"#/krav/{case_id}",
                "slutfor": f"#/slutfor/{case_id}",
            },
        },
        "summary": f"{len(lines)} MF-rader · {len(reqs)} krav",
    }


async def _suggest_prices(args: dict) -> dict:
    case_id = args["case_id"]
    case = await case_archive.get_case(case_id)
    if case is None:
        return {"result": {"error": "case finns inte"}, "summary": "Anbudet hittades inte"}

    lines = (case.get("parsed_mf") or {}).get("lines") or []
    unpriced = [l for l in lines if l.get("unit_price") is None]

    hits, examples = 0, []
    by_basis: dict[str, int] = {}
    for l in unpriced[:200]:
        s = await price_engine.suggest(
            l.get("ama_code"), l.get("description"), l.get("unit"),
            exclude_case_id=case_id,
        )
        if s:
            hits += 1
            by_basis[s["basis"]] = by_basis.get(s["basis"], 0) + 1
            if len(examples) < 4:
                examples.append({
                    "ama_code": l.get("ama_code"),
                    "beskrivning": (l.get("description") or "")[:60],
                    "median_kr": s.get("unit_price"),
                    "spann": f"{s.get('low')}–{s.get('high')} kr",
                    "antal_observationer": s.get("n"),
                    "basis": s["basis"],
                })

    coverage = f"{hits}/{len(unpriced)}" if unpriced else "0/0"
    return {
        "result": {
            "oprissatta_rader": len(unpriced),
            "rader_med_forslag": hits,
            "tackning": coverage,
            "per_basis": by_basis,
            "exempel": examples,
            "viktigt": "Förslagen är INTE applicerade — användaren granskar och applicerar i kalkylatorn (knappen 'Föreslå priser').",
        },
        "summary": f"Förslag för {coverage} oprissatta rader",
        "route": f"#/kalkylator/{case_id}",
        "route_label": "Granska i kalkylatorn",
    }


async def _run_formalia(args: dict) -> dict:
    case_id = args["case_id"]
    case = await case_archive.get_case(case_id)
    if case is None:
        return {"result": {"error": "case finns inte"}, "summary": "Anbudet hittades inte"}
    gate = await formalia.run_gate(case)
    return {
        "result": gate,
        "summary": ("Allt klart — inget blockerar" if gate.get("passed")
                    else f"{gate.get('blocking_count', 0)} punkter blockerar inlämning"),
        "route": f"#/slutfor/{case_id}",
        "route_label": "Öppna checklistan",
    }


async def _list_open_requirements(args: dict) -> dict:
    case_id = args["case_id"]
    async with lodet_db.SessionLocal() as session:
        reqs = (await session.execute(
            select(lodet_db.Requirement)
            .where(lodet_db.Requirement.case_id == case_id,
                   lodet_db.Requirement.status.in_(["unanswered", "flagged"]))
            .order_by(lodet_db.Requirement.position)
        )).scalars().all()

    skall_first = sorted(reqs, key=lambda r: (r.kind != "skall", r.position or 0))
    rows = [{
        "req_id": r.id,
        "af_code": r.af_code,
        "kind": r.kind,
        "text": (r.text or "")[:160],
        "response_format": r.response_format,
    } for r in skall_first[:20]]
    return {
        "result": {"obesvarade": len(reqs), "krav": rows},
        "summary": f"{len(reqs)} obesvarade krav",
        "route": f"#/krav/{case_id}",
        "route_label": "Öppna kravmatrisen",
    }


async def _generate_answers(args: dict) -> dict:
    from app import answer_generator

    case_id = args["case_id"]
    max_count = min(int(args.get("max_count") or 3), 3)
    case = await case_archive.get_case(case_id)
    if case is None:
        return {"result": {"error": "case finns inte"}, "summary": "Anbudet hittades inte"}

    async with lodet_db.SessionLocal() as session:
        reqs = (await session.execute(
            select(lodet_db.Requirement)
            .where(lodet_db.Requirement.case_id == case_id,
                   lodet_db.Requirement.status == "unanswered",
                   lodet_db.Requirement.response_format == "fritext")
            .order_by(lodet_db.Requirement.position)
        )).scalars().all()

    targets = sorted(reqs, key=lambda r: r.kind != "skall")[:max_count]
    if not targets:
        return {
            "result": {"genererade": 0, "info": "inga obesvarade fritext-krav"},
            "summary": "Inga obesvarade fritext-krav",
        }

    generated = []
    for r in targets:
        requirement = {
            "id": r.id, "af_code": r.af_code, "kind": r.kind, "text": r.text,
            "response_format": r.response_format,
        }
        out = await answer_generator.generate_answer(case, requirement)
        draft_key = f"req:{r.id}"
        await case_archive.update_draft(case_id, draft_key, out["answer"], edited=False)
        async with lodet_db.SessionLocal() as session:
            row = await session.get(lodet_db.Requirement, r.id)
            if row is not None:
                row.answer_draft_id = draft_key
                if row.status == "unanswered":
                    row.status = "drafted"
                await session.commit()
        generated.append({
            "req_id": r.id,
            "af_code": r.af_code,
            "krav": (r.text or "")[:100],
            "luckor": out["missing"],
            "svar_kort": (out["answer"] or "")[:200],
        })

    n_gaps = sum(1 for g in generated if g["luckor"])
    summary = f"{len(generated)} utkast skrivna"
    if n_gaps:
        summary += f" · {n_gaps} med [SAKNAS]-luckor"
    return {
        "result": {"genererade": len(generated), "utkast": generated,
                   "kvar_obesvarade": max(0, len(reqs) - len(targets))},
        "summary": summary,
        "route": f"#/krav/{case_id}",
        "route_label": "Granska utkasten",
    }
