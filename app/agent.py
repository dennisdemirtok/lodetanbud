"""
Lodet-agenten — analyserar ett anbudspaket och föreslår nästa steg.

MVP: regelbaserad. I produktion kan denna ersättas eller kompletteras
med Claude API för djupare analys av AF-text och TB-text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Iterable


@dataclass
class FileInfo:
    """Analyserad fil i paketet."""
    filename: str
    type: str
    label: str
    confidence: float
    size_kb: int
    project_id: str | None = None
    discipline: str | None = None
    metadata: dict | None = None


@dataclass
class Recommendation:
    """En åtgärd agenten föreslår."""
    id: str
    priority: int           # 1 = högst
    title: str
    body: str
    action_label: str | None = None
    action_route: str | None = None  # frontend hash route


# ---- AMA-sektioner som ofta lämnas till UE ------------------------------

UE_AREAS_PER_SECTION = {
    "B": ["Spont och pålning", "Sanering", "Demontering"],
    "C": ["Asfaltering", "Schaktning"],
    "D": ["Pålning", "Markförstärkning"],
    "E": ["Bro- och konstruktionsarbeten", "Vägräcken"],
    "F": ["Husbyggnadsarbeten", "Stomme"],
    "P": ["VA-arbeten", "VVS-installation"],
    "S": ["Elinstallation", "Belysningsinstallation"],
    "T": ["Tele- och datainstallationer"],
    "Y": ["Märkning och skyltning", "Linjemålning"],
}


def _suggest_ue_areas(ama_codes: Iterable[str]) -> list[str]:
    """Föreslå UE-områden baserat på AMA-sektioner i mängdförteckningen."""
    sections = {(c or "")[:1] for c in ama_codes}
    out: list[str] = []
    for letter in sorted(sections):
        for area in UE_AREAS_PER_SECTION.get(letter, []):
            if area not in out:
                out.append(area)
    return out


# ---- Huvudanalys --------------------------------------------------------

def analyze_package(
    files: list[FileInfo],
    parsed_mf: dict | None = None,
) -> dict:
    """
    Givet en lista klassificerade filer + ev. parsad MF → returnera analys.
    """
    by_type: dict[str, list[FileInfo]] = {}
    for f in files:
        by_type.setdefault(f.type, []).append(f)

    summary = {
        "file_count": len(files),
        "total_size_kb": sum(f.size_kb for f in files),
        "type_breakdown": {t: len(fs) for t, fs in by_type.items()},
        "has_mf": "mf" in by_type,
        "has_af": "af" in by_type,
        "has_tb": "tb" in by_type,
        "has_kontrakt": "kontrakt" in by_type,
        "ritning_count": len(by_type.get("ritning", [])),
        "disciplines": sorted({f.discipline for f in by_type.get("ritning", []) if f.discipline}),
        "project_ids": sorted({f.project_id for f in files if f.project_id}),
    }

    project_name = None
    customer = None
    bid_due = None
    if parsed_mf:
        project_name = parsed_mf.get("metadata", {}).get("project_name")
    for f in files:
        if not f.metadata:
            continue
        if not project_name:
            project_name = f.metadata.get("project_name")
        if not customer:
            customer = f.metadata.get("customer_name")
        if not bid_due:
            bid_due = f.metadata.get("bid_due_at")

    summary["project_name"] = project_name
    summary["customer"] = customer
    summary["bid_due_at"] = bid_due

    # ---- Bygg agentens narrative -----------------------------------
    narrative_parts = []
    if files:
        narrative_parts.append(f"Jag har gått igenom **{len(files)} filer** ({summary['total_size_kb']} kB totalt):")
        items = []
        for type_name, kind_files in by_type.items():
            label = {
                "mf": "mängdförteckning",
                "af": "AF-dokument",
                "tb": "teknisk beskrivning",
                "ritning": "ritning",
                "if": "innehållsförteckning",
                "rf": "ritningsförteckning",
                "kontrakt": "entreprenadkontrakt",
                "sekretess": "sekretessbegäran",
                "okant": "okänd fil",
            }.get(type_name, type_name)
            count = len(kind_files)
            plural = "" if count == 1 else "er" if label.endswith("a") else "ar" if "ritning" in label else "er"
            items.append(f"{count} {label}{plural if count != 1 else ''}")
        narrative_parts.append(" · ".join(items))
    else:
        narrative_parts.append("Inget paket uppladdat ännu — släpp filer i fältet ovan så börjar jag.")

    narrative = "\n\n".join(narrative_parts)

    # ---- Bygg rekommendationer -------------------------------------
    recs: list[Recommendation] = []

    if not summary["has_mf"]:
        recs.append(Recommendation(
            id="missing-mf",
            priority=1,
            title="Mängdförteckning saknas",
            body="Inget MF-dokument hittades i paketet. Kontrollera om förfrågan saknar prislista, eller ladda upp .csv/.xlsx separat.",
            action_label="Ladda upp MF",
            action_route="#/upload",
        ))
    elif parsed_mf:
        meta = parsed_mf.get("metadata", {})
        recs.append(Recommendation(
            id="parsed-mf",
            priority=1,
            title=f"MF parsad: {meta.get('project_name') or '—'}",
            body=f"{len(parsed_mf.get('lines', []))} rader strukturerade. Totalbelopp: {_fmt_sek(meta.get('total_amount_sek'))}. Generera Excel-mall med prisförslag?",
            action_label="Hämta Excel-mall",
            action_route="#/upload",
        ))

    if summary["has_af"]:
        recs.append(Recommendation(
            id="afb-bilagor",
            priority=2,
            title="AF-dokument hittat",
            body="Förfrågan innehåller administrativa föreskrifter. Generera AFB.31 anbudssumma + AFB.32 UE-lista + sekretessbegäran från mallar — alla autofyllda från MF-summa.",
            action_label="Öppna AFB-mallar",
            action_route="#/docs/afb",
        ))
    else:
        recs.append(Recommendation(
            id="missing-af",
            priority=3,
            title="AF-dokument saknas",
            body="Ingen administrativ föreskrift hittades. Stäm av med beställare om upphandlingen kräver AFB-bilagor.",
        ))

    # UE-förslag baserat på AMA-koder i MF
    if parsed_mf:
        ama_codes = {l.get("ama_code") for l in parsed_mf.get("lines", []) if l.get("ama_code")}
        ue_areas = _suggest_ue_areas(ama_codes)
        if ue_areas:
            recs.append(Recommendation(
                id="ue-mail",
                priority=2,
                title=f"Begär offert från {len(ue_areas)} UE-område{'n' if len(ue_areas) > 1 else ''}",
                body=f"Baserat på AMA-koderna i MF:en föreslår jag att hämta in pris för: {', '.join(ue_areas[:5])}{'…' if len(ue_areas) > 5 else ''}. Generera färdiga mejlutkast?",
                action_label="Skapa UE-mejl",
                action_route="#/agent/ue",
            ))

    if summary["has_kontrakt"]:
        recs.append(Recommendation(
            id="kontrakt",
            priority=4,
            title="Kontraktsutkast bifogat",
            body="Ett entreprenadkontraktsutkast följer paketet. Granska AB/ABT-referenser och eventuella avvikelser från standardvillkor innan inlämning.",
        ))

    if summary["ritning_count"] > 0:
        disciplines = ", ".join(summary["disciplines"]) if summary["disciplines"] else "—"
        recs.append(Recommendation(
            id="ritningar",
            priority=4,
            title=f"{summary['ritning_count']} ritningar i paketet",
            body=f"Discipliner: {disciplines}. Använd ritningarna för verifiering av MF-kvantiteter och som stöd vid platsbesök.",
        ))

    if not recs:
        recs.append(Recommendation(
            id="empty",
            priority=5,
            title="Inget att göra ännu",
            body="Ladda upp en mängdförteckning eller AF-dokument så börjar agenten ge förslag.",
        ))

    recs.sort(key=lambda r: r.priority)

    return {
        "summary": summary,
        "narrative": narrative,
        "files": [asdict(f) for f in files],
        "recommendations": [asdict(r) for r in recs],
        "ue_suggestions": _suggest_ue_areas(
            (l.get("ama_code") for l in (parsed_mf or {}).get("lines", []))
            if parsed_mf else []
        ),
    }


def _fmt_sek(amount: float | int | None) -> str:
    if amount is None:
        return "—"
    return f"{amount:,.0f}".replace(",", " ") + " kr"
