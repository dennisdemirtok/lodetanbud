"""
Flywheel-rapport (genomförandeplan AP6.3) — "edits as compass".

Veckoquery mot events-tabellen: vad rättar användarna, vilka prisförslag
accepteras, var dyker [SAKNAS] upp. Talar om VAD som ska förbättras härnäst.

    python -m evals.flywheel                         # mot lokal/DATABASE_URL
    python -m evals.flywheel --json                  # maskinläsbart

Läser samma databas som appen (DATABASE_URL eller SQLite på volymen).
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter

from sqlalchemy import func, select

from app.db import Event, MfLine, PriceObservation, Requirement, SessionLocal


async def collect() -> dict:
    async with SessionLocal() as session:
        events = (await session.execute(select(Event))).scalars().all()

        # 1. user_edits per typ
        edit_kinds = Counter()
        review_fields = Counter()
        price_applied = []
        for e in events:
            if e.kind == "user_edit":
                what = (e.data or {}).get("what", "?")
                edit_kinds[what] += 1
                for f in (e.data or {}).get("fields", []) or []:
                    review_fields[f] += 1
            elif e.kind == "price_suggestion_applied":
                price_applied.append(e.data or {})

        # 2. Mest rättade AMA-koder (mf_lines med original_values satt)
        edited_lines = (await session.execute(
            select(MfLine).where(MfLine.reviewed_by_user.is_(True))
        )).scalars().all()
        edited_codes = Counter(l.ama_code for l in edited_lines if l.ama_code and l.original_values)

        # 3. Prisförslag — antal applicerade, per basis
        basis_counter = Counter(p.get("basis", "?") for p in price_applied)

        # 4. Confidence-fördelning på extraherade rader (var faller extraktionen?)
        all_lines = (await session.execute(select(MfLine))).scalars().all()
        llm_lines = sum(1 for l in all_lines if l.extraction_method == "llm")
        low_conf = sum(1 for l in all_lines if (l.confidence or 1) < 0.9)

        # 5. Krav: andel overifierade citat, andel besvarade
        reqs = (await session.execute(select(Requirement))).scalars().all()
        skall = [r for r in reqs if r.kind == "skall"]
        skall_answered = sum(1 for r in skall if r.status in ("answered", "na"))
        unverified = sum(1 for r in reqs if not (r.source or {}).get("verified"))

        obs_count = (await session.execute(
            select(func.count()).select_from(PriceObservation)
        )).scalar_one()
        obs_won = (await session.execute(
            select(func.count()).select_from(PriceObservation).where(PriceObservation.won.is_(True))
        )).scalar_one()

    return {
        "user_edits_per_kind": dict(edit_kinds.most_common()),
        "most_edited_mf_fields": dict(review_fields.most_common(8)),
        "most_corrected_ama_codes": dict(edited_codes.most_common(10)),
        "price_suggestions_applied": len(price_applied),
        "price_applied_by_basis": dict(basis_counter.most_common()),
        "mf_lines_total": len(all_lines),
        "mf_lines_llm_extracted": llm_lines,
        "mf_lines_low_confidence": low_conf,
        "requirements_total": len(reqs),
        "skall_answered": f"{skall_answered}/{len(skall)}",
        "unverified_citations": unverified,
        "price_observations": obs_count,
        "price_observations_won": obs_won,
    }


def _print(report: dict) -> None:
    print("\n=== Lodet flywheel-rapport ===\n")
    print("EDITS (vad rättar användarna — det här ska förbättras härnäst):")
    for k, v in (report["user_edits_per_kind"] or {"(inga)": 0}).items():
        print(f"  {v:>5}  {k}")
    if report["most_corrected_ama_codes"]:
        print("\nMEST RÄTTADE AMA-KODER (extraktionen träffar sämst här):")
        for code, n in report["most_corrected_ama_codes"].items():
            print(f"  {n:>5}  {code}")
    if report["most_edited_mf_fields"]:
        print("\nMEST RÄTTADE MF-FÄLT:")
        for f, n in report["most_edited_mf_fields"].items():
            print(f"  {n:>5}  {f}")
    print("\nPRISMOTORN:")
    print(f"  {report['price_observations']} observationer ({report['price_observations_won']} vunna)")
    print(f"  {report['price_suggestions_applied']} förslag applicerade · per basis: {report['price_applied_by_basis'] or '—'}")
    print("\nEXTRAKTION:")
    print(f"  {report['mf_lines_total']} MF-rader ({report['mf_lines_llm_extracted']} LLM, {report['mf_lines_low_confidence']} lågkonfidenta)")
    print(f"  {report['requirements_total']} krav · skall besvarade {report['skall_answered']} · {report['unverified_citations']} overifierade citat")
    print()


async def main_async(as_json: bool) -> None:
    report = await collect()
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print(report)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    asyncio.run(main_async(args.json))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
