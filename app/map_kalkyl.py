"""
MAP Kalkyl-läsare (.mdbklk = Access/ACE-databas).

Läser företagets riktiga, prissatta kalkyler och gör dem till prisdata
för prismotorn (AP4) och facit för eval-harnessen (AP6).

Kräver mdbtools lokalt (brew install mdbtools) — körs ALDRIG på Railway.
Resultatet skickas till appen som JSON via POST /api/import/historic
(se scripts/import_map_kalkyl.py).

Datamodell — reverse-engineerad och verifierad mot Haga Entré
(BBC.6 "Provbelysning…": Hakt.Atg=25 st, exakt som FFU-MF:en):

  Hakt   = MF-posterna. Atg = mängd, Rub4 = AMA-kod, Rub2 = handling,
           DescrLnk → Descr.Txt = postens text, KlkTyp=2 för poster.
  Uakt   = kalkylaktiviteter under en post. Atg = TOTAL åtgång för posten.
  Res    = resurser under en aktivitet. Atg = åtgång, Spill = multiplikativ
           faktor (1 = ingen spill), Apris = à-pris.
  ResReg = företagets resursbibliotek (Code, DescrLnk, UnitPrice, Konto).
  Descr  = alla texter (PK → Txt).

Verifierat mot BCB.414 (staket 500 m): montering Uakt.Atg=2 är 2 tim
TOTALT för posten, inte per meter. Alltså:
  total = Σ aktiviteter [ Uakt.Atg × Σ resurser (Res.Atg × Res.Spill × Res.Apris) ]
  à-pris (netto) = total / Hakt.Atg   (6660 / 500 = 13,32 kr/m)

OBS: detta är SJÄLVKOSTNAD (netto), inte anbudspris med påslag — märks
basis='map_netto' i observationerna så förslag kan särskilja källan.
Tidstal ingår inte i v1 (åtgången bär mängden).
"""

from __future__ import annotations

import csv
import io
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

AMA_CODE_RE = re.compile(r"^[A-Z]{2,4}(?:\.\d+)*$")

# CVUnit-enum, verifierat empiriskt mot MF-enheter över golden-settet
# (Hakt.CVUnit → enhetssträng). Okända koder → None (hellre tom än fel).
CVUNIT_MAP = {
    "1": "m", "2": "m2", "3": "m3", "4": "kg", "9": "st",
    "22": None, "28": "ton",
}


def have_mdbtools() -> bool:
    return shutil.which("mdb-export") is not None


def _export(path: Path, table: str) -> list[dict]:
    out = subprocess.run(
        ["mdb-export", str(path), table],
        capture_output=True, text=True, timeout=120,
    )
    if out.returncode != 0:
        return []
    return list(csv.DictReader(io.StringIO(out.stdout)))


def _f(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_upd_ts(value: str) -> str | None:
    """'05/07/25 14:37:48' (MM/DD/YY) → '2025-05-07'."""
    if not value:
        return None
    try:
        dt = datetime.strptime(value.split(" ")[0], "%m/%d/%y")
        return dt.date().isoformat()
    except ValueError:
        return None


def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\x0b", " ")).strip()


def parse_kalkyl(path: Path) -> dict:
    """Parsa en .mdbklk → {posts, resources, kalkyl_date, source_file}."""
    if not have_mdbtools():
        raise RuntimeError("mdbtools saknas — installera med: brew install mdbtools")

    descr = {r["PK"]: r["Txt"] for r in _export(path, "Descr")}
    hakt_rows = _export(path, "Hakt")
    uakt_rows = _export(path, "Uakt")
    res_rows = _export(path, "Res")
    resreg_rows = _export(path, "ResReg")

    # Resurskostnad per aktivitet: Σ (Atg × Spill × Apris)
    res_by_uakt: dict[str, float] = {}
    res_count_by_uakt: dict[str, int] = {}
    for r in res_rows:
        uakt_pk = r.get("UaktPK") or ""
        if not uakt_pk:
            continue
        atg = _f(r.get("Atg"))
        spill = _f(r.get("Spill"), 1.0)
        if spill <= 0:
            spill = 1.0
        apris = _f(r.get("Apris"))
        res_by_uakt[uakt_pk] = res_by_uakt.get(uakt_pk, 0.0) + atg * spill * apris
        res_count_by_uakt[uakt_pk] = res_count_by_uakt.get(uakt_pk, 0) + 1

    # Aktiviteter per post: Σ (Uakt.Atg × aktivitetens resurskostnad)
    cost_by_hakt: dict[str, float] = {}
    rescount_by_hakt: dict[str, int] = {}
    for u in uakt_rows:
        hakt_pk = u.get("HaktPK") or ""
        if not hakt_pk:
            continue
        uatg = _f(u.get("Atg"), 1.0) or 1.0
        cost = res_by_uakt.get(u.get("PK") or "", 0.0)
        cost_by_hakt[hakt_pk] = cost_by_hakt.get(hakt_pk, 0.0) + uatg * cost
        rescount_by_hakt[hakt_pk] = (
            rescount_by_hakt.get(hakt_pk, 0) + res_count_by_uakt.get(u.get("PK") or "", 0)
        )

    posts: list[dict] = []
    latest_date: str | None = None
    for h in hakt_rows:
        ts = _parse_upd_ts(h.get("UpdTS") or "")
        if ts and (latest_date is None or ts > latest_date):
            latest_date = ts

        qty = _f(h.get("Atg"))
        total_netto = cost_by_hakt.get(h.get("PK") or "", 0.0)
        text = _clean_text(descr.get(h.get("DescrLnk") or "", ""))
        ama = (h.get("Rub4") or "").strip()
        if not AMA_CODE_RE.match(ama):
            ama = ""

        # Poster: har text + mängd + beräknad kostnad
        if not text or qty <= 0 or total_netto <= 0:
            continue

        posts.append({
            "ama_code": ama or None,
            "handling": (h.get("Rub2") or "").strip() or None,
            "description": text[:300],
            "unit": CVUNIT_MAP.get((h.get("CVUnit") or "").strip()),
            "quantity": qty,
            "unit_price": round(total_netto / qty, 2),   # netto per enhet
            "total_netto": round(total_netto, 2),
            "n_resources": rescount_by_hakt.get(h.get("PK") or "", 0),
        })

    resources: list[dict] = []
    for r in resreg_rows:
        name = _clean_text(descr.get(r.get("DescrLnk") or "", ""))
        price = _f(r.get("UnitPrice"))
        if not name or price <= 0:
            continue
        resources.append({
            "code": (r.get("Code") or "").strip() or None,
            "name": name[:120],
            "cost_per_unit": round(price, 2),
            "konto": (r.get("Konto") or "").strip() or None,
        })

    return {
        "source_file": path.name,
        "kalkyl_date": latest_date,
        "posts": posts,
        "resources": resources,
    }
