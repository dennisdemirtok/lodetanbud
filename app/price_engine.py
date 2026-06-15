"""
Prismotor (genomförandeplan AP4) — à-prisförslag ur egen historik.

Deterministisk kaskad, LLM ingenstans i matten:
  1. exakt AMA-kod, senaste 24 mån        → median, p25–p75, n
  2. exakt AMA-kod, äldre observationer   → flagga "äldre data"
  3. förälderkod (SBB.12 → SBB.1 → SBB)   → flagga "närliggande kod"
  4. liknande beskrivning                 → flagga "liknande rad"
     (pg_trgm på Postgres, difflib på SQLite — embeddings när nyckel finns)
  5. ingen träff → tomt förslag, aldrig gissning

Varje förslag bär värde, spann, n och käll-case — det är förslagets
trovärdighet som säljer, inte siffran.

Observationer fylls från prissatta mf_lines per case (källa own_bid).
När SUBMITTED/AWARDED-flödet landar i AP5 uppdateras won-flaggan och
ue_quote-källan kopplas in.
"""

from __future__ import annotations

import difflib
import statistics
from datetime import date, timedelta

from sqlalchemy import delete as sa_delete
from sqlalchemy import or_, select, text as sa_text

from app.db import Case, MfLine, PriceObservation, SessionLocal, engine, log_event, new_id

RECENT_MONTHS = 24
SIMILARITY_FLOOR_PG = 0.40
SIMILARITY_FLOOR_PY = 0.55


async def refresh_observations_for_case(case_id: str) -> int:
    """Skriv om prisobservationerna för ett case ur dess prissatta MF-rader.
    Idempotent (delete + insert)."""
    async with SessionLocal() as session:
        case = await session.get(Case, case_id)
        if case is None:
            return 0

        rows = (await session.execute(
            select(MfLine).where(
                MfLine.case_id == case_id,
                MfLine.unit_price.isnot(None),
            )
        )).scalars().all()

        await session.execute(
            sa_delete(PriceObservation).where(PriceObservation.case_id == case_id)
        )

        observed_at = (case.created_at or "")[:10] or date.today().isoformat()
        count = 0
        for r in rows:
            if not r.unit_price or r.unit_price <= 0:
                continue
            session.add(PriceObservation(
                id=new_id("obs"),
                case_id=case_id,
                ama_code=r.ama_code or "",
                description=r.description,
                unit=r.unit,
                quantity=r.quantity,
                unit_price=float(r.unit_price),
                observed_at=observed_at,
                source="own_bid",
                project_name=case.project_name,
                meta={},
            ))
            count += 1

        if count:
            await log_event(session, case_id, "price_observations_refreshed", {"count": count})
        await session.commit()
        return count


def _quantile_stats(prices: list[float]) -> dict:
    prices = sorted(prices)
    n = len(prices)
    median = statistics.median(prices)
    if n >= 4:
        qs = statistics.quantiles(prices, n=4)
        low, high = qs[0], qs[2]
    elif n > 1:
        low, high = prices[0], prices[-1]
    else:
        low = high = prices[0]
    return {
        "unit_price": round(median, 2),
        "low": round(low, 2),
        "high": round(high, 2),
        "n": n,
    }


def _spread_ratio(prices: list[float]) -> float:
    """Hur mycket de matchande priserna spretar (max/min). DEK.21 i evalen:
    10 kr vs 121 000 kr → 12000×. Stor spridning = AMA-koden ensam räcker inte."""
    lo, hi = min(prices), max(prices)
    return hi / lo if lo > 0 else float("inf")


def _confidence(n: int, spread: float) -> str:
    """Grön bara när flera källor OCH samstämmiga. Driver färg + om raden
    visas som trygg eller 'granska själv' i kalkylatorn."""
    if n < 2 or spread > 8:
        return "low"
    if n < 4 or spread > 3:
        return "medium"
    return "high"


def _narrow_by_description(obs: list[PriceObservation], description: str,
                           floor: float = 0.45) -> list[PriceObservation]:
    """Bland exakt-kod-träffar: behåll dem vars beskrivning liknar postens.
    Samma AMA-kod+enhet kan vara olika arbete (DEK.21 'montering' vs 'leverans')
    — beskrivningen avgör vilka historiska priser som faktiskt är jämförbara."""
    nd = (description or "").strip().lower()
    if len(nd) < 8:
        return obs
    scored = []
    for o in obs:
        r = difflib.SequenceMatcher(None, nd, (o.description or "").strip().lower()).ratio()
        if r >= floor:
            scored.append((r, o))
    scored.sort(key=lambda x: -x[0])
    return [o for _r, o in scored] or obs  # falla tillbaka om inget liknar


def _build_suggestion(obs: list[PriceObservation], basis: str, base_flags: list[str],
                      description: str | None, target_qty: float | None = None) -> dict:
    """Slå ihop matchande observationer till ett förslag med spann, n,
    confidence och utliggar-flagga. Avgränsar på mängdskala (klumpsumma vs
    per-styck) och beskrivning när exakt-kod-träffarna spretar brett."""
    flags = list(base_flags)

    # Filtrera degenererade obs: mängd <= 0 ger à-pris-artefakter (total/≈0 →
    # astronomiskt à-pris, t.ex. EBC.115 "ton" med mängd ≈ 0 i evalen).
    used = [o for o in obs if o.quantity is None or o.quantity > 0] or obs

    # Mängd-skala-grind: samma AMA-kod kan vara klumpsumma (mängd≈1, jättepris)
    # i ett projekt och per-styck (mängd=83) i ett annat — DEK.21 var
    # "Lekställning à 2 Mkr × 1" vs "Klättergrepp à 10 kr × 83". Behåll bara
    # obs inom 10× av postens mängd; obs utan mängd behålls (kan ej gallras).
    if target_qty and target_qty > 0:
        lo, hi = target_qty / 10.0, target_qty * 10.0
        scaled = [o for o in used if o.quantity is None or (lo <= o.quantity <= hi)]
        if 2 <= len(scaled) < len(used):
            used = scaled
            flags.append("avgränsat på mängdskala")

    # Utliggarskydd: spretar fortfarande brett → avgränsa på beskrivning.
    if len(used) >= 3 and description and _spread_ratio([o.unit_price for o in used]) > 4:
        narrowed = _narrow_by_description(used, description)
        if 2 <= len(narrowed) < len(used):
            used = narrowed
            basis = f"{basis}+beskrivning"
            flags.append("avgränsat på beskrivning")

    prices = [o.unit_price for o in used]
    spread = _spread_ratio(prices)
    conf = _confidence(len(prices), spread)
    if spread > 8:
        flags.append(f"stor spridning ({spread:.0f}×) — granska och sätt själv")
    return {
        **_quantile_stats(prices),
        "basis": basis,
        "flags": flags,
        "confidence": conf,
        "spread_ratio": round(spread, 1) if spread != float("inf") else None,
        "samples": [_obs_to_sample(o) for o in used[:3]],
    }


def _ancestor_codes(code: str) -> list[str]:
    """SBB.12 → [SBB.1, SBB]. Trimmar en siffra i taget, sedan punktdelen."""
    out: list[str] = []
    if "." in code:
        head, tail = code.rsplit(".", 1)
        t = tail
        while len(t) > 1:
            t = t[:-1]
            out.append(f"{head}.{t}")
        out.append(head)
    return out


def _obs_to_sample(o: PriceObservation) -> dict:
    return {
        "project": o.project_name,
        "observed_at": o.observed_at,
        "unit_price": o.unit_price,
        "unit": o.unit,
        "case_id": o.case_id,
    }


async def _fetch_exact(session, code: str, unit: str | None, exclude_case_id: str | None,
                       since: str | None) -> list[PriceObservation]:
    q = select(PriceObservation).where(PriceObservation.ama_code == code)
    if unit:
        q = q.where(PriceObservation.unit == unit)
    if exclude_case_id:
        q = q.where(or_(PriceObservation.case_id.is_(None),
                        PriceObservation.case_id != exclude_case_id))
    if since:
        q = q.where(PriceObservation.observed_at >= since)
    q = q.order_by(PriceObservation.observed_at.desc()).limit(200)
    return list((await session.execute(q)).scalars().all())


async def _fetch_similar(session, description: str, unit: str | None,
                         exclude_case_id: str | None) -> list[PriceObservation]:
    """Likhetssteget — pg_trgm på Postgres, difflib lokalt."""
    if not description or len(description.strip()) < 8:
        return []

    if engine.dialect.name == "postgresql":
        sql = """
            SELECT id FROM price_observations
            WHERE similarity(description, :d) > :floor
              {unit_clause} {exclude_clause}
            ORDER BY similarity(description, :d) DESC
            LIMIT 10
        """.format(
            unit_clause="AND unit = :u" if unit else "",
            exclude_clause="AND (case_id IS NULL OR case_id != :ex)" if exclude_case_id else "",
        )
        params: dict = {"d": description, "floor": SIMILARITY_FLOOR_PG}
        if unit:
            params["u"] = unit
        if exclude_case_id:
            params["ex"] = exclude_case_id
        try:
            ids = [r[0] for r in (await session.execute(sa_text(sql), params)).all()]
        except Exception:
            ids = []
        if not ids:
            return []
        rows = (await session.execute(
            select(PriceObservation).where(PriceObservation.id.in_(ids))
        )).scalars().all()
        return list(rows)

    # SQLite: ladda kandidater och jämför i Python
    q = select(PriceObservation)
    if unit:
        q = q.where(PriceObservation.unit == unit)
    if exclude_case_id:
        q = q.where(or_(PriceObservation.case_id.is_(None),
                        PriceObservation.case_id != exclude_case_id))
    candidates = (await session.execute(q.limit(500))).scalars().all()
    nd = description.strip().lower()
    scored = []
    for o in candidates:
        ratio = difflib.SequenceMatcher(None, nd, (o.description or "").strip().lower()).ratio()
        if ratio >= SIMILARITY_FLOOR_PY:
            scored.append((ratio, o))
    scored.sort(key=lambda x: -x[0])
    return [o for _r, o in scored[:10]]


async def suggest(
    ama_code: str | None,
    description: str | None,
    unit: str | None,
    exclude_case_id: str | None = None,
    quantity: float | None = None,
) -> dict | None:
    """Prisförslag enligt kaskaden. None när ingen träff — aldrig gissning.
    quantity (postens mängd) används för mängd-skala-grindning så klumpsumma
    inte blandas med per-styck-priser."""
    since = (date.today() - timedelta(days=RECENT_MONTHS * 30)).isoformat()

    async with SessionLocal() as session:
        # 1. Exakt kod, senaste 24 mån
        if ama_code:
            obs = await _fetch_exact(session, ama_code, unit, exclude_case_id, since)
            if obs:
                return _build_suggestion(obs, "exact", [], description, quantity)

            # 2. Exakt kod, äldre
            obs = await _fetch_exact(session, ama_code, unit, exclude_case_id, None)
            if obs:
                return _build_suggestion(obs, "exact_old", ["äldre än 24 mån"], description, quantity)

            # 3. Förälderkoder
            for parent in _ancestor_codes(ama_code):
                obs = await _fetch_exact(session, parent, unit, exclude_case_id, None)
                if obs:
                    return _build_suggestion(obs, "parent", [f"närliggande kod {parent}"], description, quantity)

        # 4. Liknande beskrivning (redan avgränsad på beskrivning → ingen ytterligare narrowing)
        obs = await _fetch_similar(session, description or "", unit, exclude_case_id)
        if obs:
            return _build_suggestion(obs, "similar", ["liknande rad"], None, quantity)

    # 5. Ingen träff
    return None


async def observation_count() -> int:
    from sqlalchemy import func
    async with SessionLocal() as session:
        return (await session.execute(
            select(func.count()).select_from(PriceObservation)
        )).scalar_one()


async def import_historic(
    project_name: str,
    observed_at: str | None,
    region: str | None,
    posts: list[dict],
    source: str = "map_netto",
    import_key: str | None = None,
) -> dict:
    """Importera historiska prisobservationer (t.ex. ur MAP-kalkyler, AP4-backfill).

    Idempotent per (import_key): tar bort tidigare observationer med samma
    import_key i meta innan insert, så omkörning inte dubblerar. import_key
    default = project_name + observed_at."""
    key = import_key or f"{project_name}|{observed_at or ''}"
    obs_date = (observed_at or date.today().isoformat())[:10]

    async with SessionLocal() as session:
        # Rensa tidigare import med samma nyckel (Postgres: jsonb ->>)
        if engine.dialect.name == "postgresql":
            await session.execute(sa_text(
                "DELETE FROM price_observations WHERE meta->>'import_key' = :k"
            ), {"k": key})
        else:
            existing = (await session.execute(select(PriceObservation))).scalars().all()
            for o in existing:
                if (o.meta or {}).get("import_key") == key:
                    await session.delete(o)

        count = 0
        for p in posts:
            price = p.get("unit_price")
            if price is None or float(price) <= 0:
                continue
            ama = (p.get("ama_code") or "").strip()
            if not ama:
                continue
            session.add(PriceObservation(
                id=new_id("obs"),
                case_id=None,
                ama_code=ama,
                description=p.get("description"),
                unit=p.get("unit"),
                quantity=p.get("quantity"),
                unit_price=float(price),
                region=region,
                observed_at=obs_date,
                source=source,
                project_name=project_name,
                meta={"import_key": key, "n_resources": p.get("n_resources")},
            ))
            count += 1

        await log_event(session, None, "historic_prices_imported", {
            "project": project_name, "count": count, "source": source, "import_key": key,
        })
        await session.commit()
        return {"imported": count, "import_key": key}
