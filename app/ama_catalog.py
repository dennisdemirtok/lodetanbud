"""
AMA-katalog — referensdata för bibliotek-vyn.

Detta är en hårdkodad delmängd av AMA Anläggning 23 + AF AMA 21,
tillräcklig för att visa upp UI-funktionalitet. I produktion ska detta
laddas från Svensk Byggtjänsts officiella data (med licens).
"""

from __future__ import annotations


AMA_ANLAGGNING_23 = [
    # B-kapitel: Förarbeten, hjälparbeten, saneringsarbeten
    {"code": "BBC.6", "title": "Undersökningar av el- och telesystem", "level": 2, "system": "AMA_Anläggning"},
    {"code": "BEC.611", "title": "Demontering av el- och teleinstallationer för uppläggning i upplag", "level": 3, "system": "AMA_Anläggning"},
    {"code": "BED.61", "title": "Rivning av el- och teleinstallationer för materialåtervinning", "level": 2, "system": "AMA_Anläggning"},
    {"code": "BJD.1", "title": "Stomnät", "level": 2, "system": "AMA_Anläggning"},
    {"code": "BJD.26", "title": "Inmätning av el- och teleinstallationer", "level": 2, "system": "AMA_Anläggning"},
    {"code": "BJD.36", "title": "Utsättning av el- och teleinstallationer", "level": 2, "system": "AMA_Anläggning"},
    # C-kapitel: Mark- och anläggningsarbeten
    {"code": "CBB.31", "title": "Schaktning för ledning eller kabel", "level": 3, "system": "AMA_Anläggning"},
    {"code": "CEC.21", "title": "Fyllning för ledning eller kabel", "level": 3, "system": "AMA_Anläggning"},
    {"code": "CES.111", "title": "Fyllning kategori A för väg eller plan", "level": 3, "system": "AMA_Anläggning"},
    # D-kapitel: Markförstärkningar
    {"code": "DCB.13", "title": "Pålning med slagna pålar av betong", "level": 3, "system": "AMA_Anläggning"},
    # E-kapitel: Konstruktioner
    {"code": "EBE.121", "title": "Form för platsgjuten betongkonstruktion", "level": 3, "system": "AMA_Anläggning"},
    {"code": "ESC.21", "title": "Stålkonstruktion av valsade profiler", "level": 3, "system": "AMA_Anläggning"},
    # S-kapitel: El- och telesystem
    {"code": "SBB.211", "title": "Fundament till kabelskåp", "level": 3, "system": "AMA_Anläggning"},
    {"code": "SBC.21", "title": "Stolpar och master för vägbelysning e d", "level": 2, "system": "AMA_Anläggning"},
    {"code": "SBC.43", "title": "Stolpinsatser", "level": 2, "system": "AMA_Anläggning"},
    {"code": "SBN.112", "title": "Kabelskydd av plaströr", "level": 3, "system": "AMA_Anläggning"},
    {"code": "SBN.122", "title": "Förstärkt kabelskydd av rör", "level": 3, "system": "AMA_Anläggning"},
    {"code": "SCB.72", "title": "Kraftkablar i kabelskyddsrör, flerfackskanaler o d i mark", "level": 2, "system": "AMA_Anläggning"},
    {"code": "SCC.822", "title": "Installationskablar i eller på belysningsstolpar e d", "level": 3, "system": "AMA_Anläggning"},
    {"code": "SEC.22", "title": "Diazedsäkringar", "level": 2, "system": "AMA_Anläggning"},
    {"code": "SKB.32", "title": "Kabelskåp för lågspänning", "level": 2, "system": "AMA_Anläggning"},
    {"code": "SND.1", "title": "Ljusarmaturer för vägtrafikbelysning", "level": 2, "system": "AMA_Anläggning"},
    # Y-kapitel: Märkning, kontroll, dokumentation
    {"code": "YFB.631", "title": "Anmälningshandlingar för elservis", "level": 3, "system": "AMA_Anläggning"},
    {"code": "YG", "title": "MÄRKNING OCH SKYLTNING", "level": 1, "system": "AMA_Anläggning"},
    {"code": "YGB.61", "title": "Märkning av kanalisation", "level": 2, "system": "AMA_Anläggning"},
    {"code": "YGB.6312", "title": "Märkning av kabelskåp", "level": 4, "system": "AMA_Anläggning"},
    {"code": "YGB.6321", "title": "Märkning av huvudledningar", "level": 4, "system": "AMA_Anläggning"},
    {"code": "YGB.6322", "title": "Märkning av gruppledningar", "level": 4, "system": "AMA_Anläggning"},
    {"code": "YGB.6333", "title": "Märkning av platsutrustningar i belysnings- och ljussystem", "level": 4, "system": "AMA_Anläggning"},
    {"code": "YGC.63", "title": "Skyltning för elkraftsinstallationer", "level": 3, "system": "AMA_Anläggning"},
    {"code": "YHB.6", "title": "Kontroll av el- och telesystem", "level": 2, "system": "AMA_Anläggning"},
    {"code": "YHB.63", "title": "Kontroll av elkraftsystem", "level": 3, "system": "AMA_Anläggning"},
    {"code": "YHB.632", "title": "Kontroll av belysnings- och ljussystem", "level": 3, "system": "AMA_Anläggning"},
    {"code": "YJD.63", "title": "Underlag för relationshandlingar för elkraftsinstallationer", "level": 3, "system": "AMA_Anläggning"},
    {"code": "YJF.6", "title": "Digital förvaltningsinformation för el- och teleinstallationer", "level": 2, "system": "AMA_Anläggning"},
    {"code": "YJG.6", "title": "Kontrolldokument, intyg o d för el- och teleinstallationer", "level": 2, "system": "AMA_Anläggning"},
    {"code": "YJJ.6", "title": "Miljödokumentation för el- och teleinstallationer", "level": 2, "system": "AMA_Anläggning"},
    {"code": "YJK.6", "title": "Produktdokumentation för el- och teleinstallationer", "level": 2, "system": "AMA_Anläggning"},
    {"code": "YJL.63", "title": "Drift- och underhållsinstruktioner för elkraftsinstallationer", "level": 3, "system": "AMA_Anläggning"},
]

AF_AMA_21 = [
    {"code": "AFA", "title": "Allmän orientering", "level": 1, "system": "AF_AMA"},
    {"code": "AFB", "title": "Upphandlingsföreskrifter", "level": 1, "system": "AF_AMA"},
    {"code": "AFB.31", "title": "Anbudsformulär — anbudssumma", "level": 2, "system": "AF_AMA"},
    {"code": "AFB.32", "title": "Anbudsformulär — underentreprenörer", "level": 2, "system": "AF_AMA"},
    {"code": "AFB.33", "title": "Anbudsformulär — referensobjekt", "level": 2, "system": "AF_AMA"},
    {"code": "AFC", "title": "Entreprenadföreskrifter vid utförandeentreprenad", "level": 1, "system": "AF_AMA"},
    {"code": "AFD", "title": "Entreprenadföreskrifter vid totalentreprenad", "level": 1, "system": "AF_AMA"},
    {"code": "AFG", "title": "Allmänna arbeten och hjälpmedel", "level": 1, "system": "AF_AMA"},
    {"code": "AFH", "title": "Allmänna hjälpmedel", "level": 1, "system": "AF_AMA"},
]

SECTION_LABELS = {
    "B": "B — Förarbeten, hjälparbeten, saneringsarbeten",
    "C": "C — Mark- och anläggningsarbeten",
    "D": "D — Markförstärkningar och bärande konstruktioner",
    "E": "E — Konstruktionsarbeten",
    "F": "F — Husunderbyggnad",
    "G": "G — Vindar, byggnadsverk, m.m.",
    "H": "H — Innerväggar, golv, undertak, m.m.",
    "J": "J — Tak och vattenavledning",
    "K": "K — Inredning, utrustning",
    "L": "L — Markarbeten på tomtmark",
    "M": "M — Husbyggnadsarbeten",
    "N": "N — Anläggningsarbeten på vatten",
    "P": "P — VVS-system",
    "Q": "Q — Apparater för vätska och gas",
    "R": "R — Värme-, kyl- och processmediasystem",
    "S": "S — Apparater, ledningar m.m. i el- och telesystem",
    "T": "T — Apparater, kanaler m.m. i el- och telesystem",
    "U": "U — Apparater för styr- och övervakningssystem",
    "V": "V — Reservdelar, drift- och underhållsinstruktioner",
    "X": "X — Märkning, kontroll, dokumentation",
    "Y": "Y — Märkning, kontroll, dokumentation, mediaförsörjning",
    "Z": "Z — Inredning och utrustning",
}

E84_INDEX_MAPPING = {
    "B": "E84:3.2 (anläggning)",
    "C": "E84:3.2 (anläggning)",
    "D": "E84:3.2 (anläggning)",
    "E": "E84:3.2 (anläggning)",
    "F": "E84:4.0 (husbyggnad)",
    "P": "E84:6.X (VVS)",
    "Q": "E84:6.X (VVS)",
    "R": "E84:6.X (VVS)",
    "S": "E84:7.X (el)",
    "T": "E84:7.X (el)",
    "Y": "KPI",
}


def all_codes() -> list[dict]:
    return AMA_ANLAGGNING_23 + AF_AMA_21


def grouped_by_section(system: str = "AMA_Anläggning") -> dict[str, list[dict]]:
    """Gruppera koder per sektion-bokstav."""
    source = AMA_ANLAGGNING_23 if system == "AMA_Anläggning" else AF_AMA_21
    grouped: dict[str, list[dict]] = {}
    for entry in source:
        letter = entry["code"][0]
        grouped.setdefault(letter, []).append(entry)
    return grouped


def section_label(letter: str) -> str:
    return SECTION_LABELS.get(letter, f"{letter} — Övrigt")


def index_for_section(letter: str) -> str:
    return E84_INDEX_MAPPING.get(letter, "—")
