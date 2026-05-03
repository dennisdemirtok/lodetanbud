"""
File classifier — känner igen vad en uppladdad fil är.

Mönster baserade på riktiga svenska anbudspaket (Westcon, BidCon, Trafikverket).
Klassificerar via filnamn + innehållsmönster.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class FileKind:
    """En klassificerad fil med metadata."""
    type: str              # 'mf' | 'af' | 'tb' | 'ritning' | 'if' | 'rf' | 'kontrakt' | 'sekretess' | 'okant'
    label: str             # Människovänlig etikett
    confidence: float      # 0..1
    subtype: str | None = None
    project_id: str | None = None
    discipline: str | None = None  # K, T, V, M, A, W ... för ritningar


# ---- Filnamnsmönster ----------------------------------------------------

RITNING_PATTERN = re.compile(r"^(\d{2,3})([A-Z])(\d{4,5})", re.IGNORECASE)
PROJEKT_PATTERN = re.compile(r"^(\d{1,2}[A-Z]\d{1,2})", re.IGNORECASE)
IF_RF_PATTERN = re.compile(r"^(\d{1,2}[A-Z]\d{1,2})(IF|RF|MF)(\d+)", re.IGNORECASE)

# Disciplinkoder enligt BSAB / svenska byggregelverk
DISCIPLINE_LABELS = {
    "A": "Arkitektur",
    "B": "Brand",
    "E": "El",
    "G": "Geoteknik",
    "H": "Hiss",
    "I": "Inredning",
    "K": "Konstruktion",
    "L": "Landskap",
    "M": "Mark",
    "P": "VA / VVS",
    "Q": "Process",
    "R": "Rörelseteknik",
    "S": "Styr- och övervakning",
    "T": "Trafik / Tekniska anläggningar",
    "V": "Ventilation",
    "W": "Värme / Kyla",
    "Z": "Specialanläggning",
}


def _name_signal(name: str) -> str:
    """Normalisera filnamn för matchning."""
    return name.lower().replace("ä", "a").replace("ö", "o").replace("å", "a")


def classify(filename: str, content: bytes | None = None, content_text: str = "") -> FileKind:
    """
    Klassificera en fil. Använder filnamn primärt, content_text som tiebreaker.

    content_text bör vara förstas sidan för PDF, eller hela filen för CSV/text.
    """
    name = filename.strip()
    norm = _name_signal(name)
    text_lower = content_text.lower() if content_text else ""

    # ---- Filnamnsmönster (hög konfidens) — körs först --------------
    fname_no_ext = re.sub(r"\.[^.]+$", "", name)

    # MF — explicit detection FÖRE alla andra (filnamn kan innehålla
    # "teknisk beskrivning" eftersom MF ofta levereras kombinerat)
    if "mangdforteckning" in norm:
        if norm.endswith(".csv"):
            return FileKind("mf", "Mängdförteckning", 0.95)
        if norm.endswith((".xlsx", ".xlsm", ".xls")):
            return FileKind("mf", "Mängdförteckning", 0.95)
        if norm.endswith(".pdf"):
            return FileKind("mf", "Mängdförteckning (PDF)", 0.88)

    # À-prislista — separat dokumenttyp som inte är samma som MF
    if "aprislista" in norm or "a-prislista" in norm or "à-prislista" in name.lower():
        return FileKind("aprislista", "À-prislista", 0.92)

    # CSV — sannolikt mängdförteckning även utan "mangd" i namnet
    if norm.endswith(".csv"):
        if "mf" in norm.split() or "kalkyl" in norm:
            return FileKind("mf", "Mängdförteckning", 0.95)
        return FileKind("mf", "Mängdförteckning", 0.7)

    # <projekt>IF<nr> / <projekt>RF<nr> / <projekt>MF<nr>
    ifrf = IF_RF_PATTERN.match(fname_no_ext)
    if ifrf:
        proj = ifrf.group(1)
        kind_letter = ifrf.group(2).upper()
        labels = {"IF": "Innehållsförteckning", "RF": "Ritningsförteckning", "MF": "Mängdförteckning"}
        type_map = {"IF": "if", "RF": "rf", "MF": "mf"}
        return FileKind(type_map[kind_letter], labels[kind_letter], 0.95, subtype=kind_letter, project_id=proj)

    # Ritning (mönster: SSSDDDDD där D är disciplin-bokstav)
    m = RITNING_PATTERN.match(fname_no_ext)
    if m:
        series = m.group(1)
        disc = m.group(2).upper()
        if disc in DISCIPLINE_LABELS:
            label = f"Ritning {disc}-{series}"
            return FileKind(
                "ritning",
                label,
                0.95,
                subtype=disc,
                discipline=DISCIPLINE_LABELS[disc],
            )

    # ---- Filnamn med svenska ord -----------------------------------
    if "sekretess" in norm:
        return FileKind("sekretess", "Sekretessbegäran", 0.95)

    # EK eller "entreprenadkontrakt" — fångar både "1. EK Foo.pdf" och "Entreprenadkontrakt.pdf"
    if (
        "entreprenadkontrakt" in norm
        or "kontrakt" in norm
        or "agreement" in norm
        or re.search(r"^[\d\.\s]*ek\b", norm)
    ):
        return FileKind("kontrakt", "Entreprenadkontrakt", 0.92)

    # AF — fångar både "9. AF Kulturparken.pdf" och "AF Kulturparken.pdf"
    if (
        "administrativa" in norm
        or "foreskrifter" in norm
        or re.search(r"^[\d\.\s]*af\b", norm)
    ):
        return FileKind("af", "Administrativa föreskrifter", 0.92, subtype="AF")

    if "teknisk beskrivning" in norm or "(tb)" in norm or norm.startswith("tb") or norm.startswith("6.3"):
        return FileKind("tb", "Teknisk beskrivning", 0.9, subtype="TB")

    # Beställarens bilage-mallar — ofta nummer-prefix-baserade
    if "cv-mall" in norm or "cv mall" in norm:
        return FileKind("mall", "CV-mall (beställaren)", 0.92, subtype="cv")
    if "referensuppdrag" in norm or "referensobjekt" in norm:
        return FileKind("mall", "Referensobjekt-mall (beställaren)", 0.92, subtype="referenser")
    if "sanningsforsakran" in norm:
        return FileKind("mall", "Sanningsförsäkran (beställaren)", 0.92, subtype="sanning")
    if "arbetsmiljoplan" in norm:
        return FileKind("mall", "Arbetsmiljöplan (beställaren)", 0.9, subtype="amp")
    if "annat foretags kapacitet" in norm:
        return FileKind("mall", "Annat företags kapacitet (beställaren)", 0.9, subtype="kapacitet")
    if "kontrollplan" in norm:
        return FileKind("mall", "Kontrollplan (beställaren)", 0.85, subtype="kontroll")
    if "riskanalys" in norm:
        return FileKind("riskanalys", "Riskanalys", 0.9)
    if "vaxtforteckning" in norm or "växtförteckning" in name.lower():
        return FileKind("vaxt", "Växtförteckning", 0.9)

    if "innehallsforteckning" in norm:
        return FileKind("if", "Innehållsförteckning", 0.9, subtype="IF")
    if "ritningsforteckning" in norm:
        return FileKind("rf", "Ritningsförteckning", 0.9, subtype="RF")

    # ---- Innehållsbaserade fallbacks (låg-medel konfidens) ---------
    if "afa" in text_lower[:2000] and "afb" in text_lower[:2000]:
        return FileKind("af", "Administrativa föreskrifter", 0.85, subtype="AF")
    if "teknisk beskrivning" in text_lower[:1500]:
        return FileKind("tb", "Teknisk beskrivning", 0.85, subtype="TB")

    # Bygghandling / projektkod
    pm = PROJEKT_PATTERN.match(fname_no_ext)
    if pm:
        return FileKind(
            "okant",
            f"Projektdokument {pm.group(1)}",
            0.5,
            project_id=pm.group(1),
        )

    # PDF default
    if norm.endswith(".pdf"):
        return FileKind("okant", f"PDF: {name}", 0.3)

    # Excel
    if norm.endswith((".xlsx", ".xlsm", ".xls")):
        return FileKind("okant", "Excel-fil (oklart syfte)", 0.4)

    return FileKind("okant", f"Okänd: {name}", 0.1)


def extract_project_id(filename: str) -> str | None:
    """Plocka ut projektnummer från filnamn t.ex. '1C12MF10' → '1C12'."""
    m = PROJEKT_PATTERN.match(filename)
    return m.group(1) if m else None
