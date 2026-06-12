"""
Formaliagrind (genomförandeplan AP5) — 100 % deterministisk, ingen LLM.

Genererar en checklista ur kravmatrisen + kalkylen + företagsinställningar.
FORMALIA_CHECK → READY får ske ENDAST när alla obligatoriska punkter passerar
(grindfunktionen från AP1). Resultatet loggas som event — vem godkände vad när.

Varje punkt: {key, label, passed, required, detail, fix_route}.
"""

from __future__ import annotations

import re
from datetime import date

from sqlalchemy import select

from app import company_settings
from app.db import Requirement, SessionLocal


def _fmt_sek(amount: float) -> str:
    return f"{amount:,.0f}".replace(",", " ")


def _digits(s: str) -> set[str]:
    """Alla heltal i en text (för att hitta belopp i utkast)."""
    return set(re.findall(r"\d[\d  ]{2,}\d", s or ""))


async def run_gate(case: dict) -> dict:
    """Kör checklistan för ett case-dict (från case_archive.get_case).
    Returnerar {items[], passed, blocking}."""
    case_id = case["id"]
    items: list[dict] = []

    async with SessionLocal() as session:
        reqs = (await session.execute(
            select(Requirement).where(Requirement.case_id == case_id)
        )).scalars().all()

    drafts = case.get("drafts") or {}
    company = company_settings.get_settings()
    parsed_mf = case.get("parsed_mf") or {}
    mf_total = (parsed_mf.get("metadata") or {}).get("total_amount_sek") or case.get("total_amount_sek")

    # 1. Alla skall-krav besvarade (answered/na)
    skall = [r for r in reqs if r.kind == "skall"]
    skall_open = [r for r in skall if r.status not in ("answered", "na")]
    items.append({
        "key": "skall_besvarade",
        "label": "Alla skall-krav besvarade",
        "required": True,
        "passed": len(skall_open) == 0,
        "detail": (
            f"Alla {len(skall)} skall-krav är besvarade eller markerade ej tillämpliga."
            if not skall_open else
            f"{len(skall_open)} av {len(skall)} skall-krav är obesvarade."
        ),
        "fix_route": f"#/krav/{case_id}",
    })

    # 2. Bilagekrav har ett dokument kopplat
    bilagor = [r for r in reqs if r.kind == "bilaga"]
    bilaga_missing = []
    for r in bilagor:
        if r.status == "na":
            continue
        has_doc = (r.af_code and r.af_code.lower() in drafts) or bool(r.answer_draft_id)
        # Standardmallar (anbudssumma/ue-lista/sekretess/missiv) räknas via drafts-nycklar
        if not has_doc:
            bilaga_missing.append(r)
    items.append({
        "key": "bilagor_kopplade",
        "label": "Bilagekrav har dokument",
        "required": True,
        "passed": len(bilaga_missing) == 0,
        "detail": (
            f"Alla {len(bilagor)} bilagekrav har ett kopplat dokument."
            if not bilaga_missing else
            f"{len(bilaga_missing)} bilagekrav saknar dokument."
        ),
        "fix_route": f"#/krav/{case_id}",
    })

    # 3. Anbudssumma == kalkylens totalsumma (exakt diff-koll)
    anbudssumma_draft = drafts.get("anbudssumma")
    if anbudssumma_draft and mf_total:
        formatted = _fmt_sek(float(mf_total))
        text_digits = _digits(anbudssumma_draft.get("text") or "")
        # normalisera mellanslag bort vid jämförelse
        norm_formatted = formatted.replace(" ", "")
        match = any(d.replace(" ", "") == norm_formatted for d in text_digits)
        items.append({
            "key": "anbudssumma_matchar",
            "label": "Anbudssumma matchar kalkylen",
            "required": True,
            "passed": match,
            "detail": (
                f"Anbudssumman i AFB.31 stämmer med kalkylens {formatted} kr."
                if match else
                f"AFB.31-dokumentet matchar inte kalkylens totalsumma {formatted} kr — generera om anbudssumman."
            ),
            "fix_route": f"#/kalkylator/{case_id}",
        })
    else:
        items.append({
            "key": "anbudssumma_matchar",
            "label": "Anbudssumma matchar kalkylen",
            "required": True,
            "passed": False,
            "detail": (
                "Anbudssumman (AFB.31) är inte genererad än."
                if not anbudssumma_draft else
                "Kalkylen saknar totalsumma — prissätt mängdförteckningen."
            ),
            "fix_route": f"#/kalkylator/{case_id}",
        })

    # 4. Anbudsdeadline i framtiden (varning < 3 dagar)
    bid_due = parsed_mf.get("metadata", {}).get("bid_due_at") or (case.get("analysis") or {}).get("bid_due_at")
    if bid_due:
        try:
            due = date.fromisoformat(str(bid_due)[:10])
            days = (due - date.today()).days
            items.append({
                "key": "deadline",
                "label": "Anbudsdeadline",
                "required": False,
                "passed": days >= 0,
                "detail": (
                    f"Deadline {due.isoformat()} — {days} dagar kvar." if days > 3 else
                    f"⚠ Deadline {due.isoformat()} — endast {days} dagar kvar!" if days >= 0 else
                    f"Deadline {due.isoformat()} har passerat."
                ),
                "fix_route": None,
            })
        except (ValueError, TypeError):
            pass

    # 5. Firmatecknare / kontaktperson ifylld
    has_signer = bool(company.get("contact_name") and company.get("company_name"))
    items.append({
        "key": "firmatecknare",
        "label": "Företag och firmatecknare ifyllt",
        "required": True,
        "passed": has_signer,
        "detail": (
            f"{company.get('company_name')} · {company.get('contact_name')}"
            if has_signer else
            "Företagsnamn och kontaktperson måste fyllas i under Inställningar / Företagsinfo."
        ),
        "fix_route": "#/inst/foretag",
    })

    # 6. UE-lista finns om UE-krav förekommer
    has_ue_req = any("underentrepren" in (r.text or "").lower() or r.af_code == "AFB.32" for r in reqs)
    if has_ue_req:
        items.append({
            "key": "ue_lista",
            "label": "UE-lista upprättad",
            "required": False,
            "passed": "ue-lista" in drafts,
            "detail": (
                "UE-lista (AFB.32) är genererad."
                if "ue-lista" in drafts else
                "Förfrågan nämner underentreprenörer men UE-listan (AFB.32) är inte genererad."
            ),
            "fix_route": f"#/start",
        })

    blocking = [i for i in items if i["required"] and not i["passed"]]
    return {
        "items": items,
        "passed": len(blocking) == 0,
        "blocking_count": len(blocking),
    }
