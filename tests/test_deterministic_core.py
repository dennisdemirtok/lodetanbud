"""
Deterministisk kärna — körs på varje PR (genomförandeplan AP6.2: ingen
promptändring deployas utan eval-diff; de fulla golden-sviterna körs lokalt
eftersom underlagen inte ligger i repot, men kärnan som INTE får regressa
gateas här: AF-split, citatverifiering, statemaskinens grindar,
etikettords-skydden och priskaskadens kodhierarki).
"""

from __future__ import annotations

import pytest

from app.af_parser import split_af_sections, verify_quote, AfSection
from app.price_engine import _ancestor_codes
from app.formalia import _digits, _fmt_sek
from app import states


# ---------- AF-split ------------------------------------------------------

AF_PAGES = [
    """ADMINISTRATIVA FÖRESKRIFTER
INNEHÅLLSFÖRTECKNING
AFB.31 Anbuds form och innehåll ............ 4
AFA Allmän orientering
Beställaren upphandlar markarbeten.
AFB.31 Anbuds form och innehåll
Anbud skall lämnas skriftligen på svenska.
Anbudet skall vara märkt "Anbud Markarbeten".
""",
    """AFB.52 Anbudets giltighetstid
Anbudsgivaren skall vara bunden av sitt anbud i 90 dagar.
""",
]


def test_split_finds_sections_and_skips_toc():
    sections = split_af_sections(AF_PAGES)
    codes = [s.code for s in sections]
    assert "AFA" in codes
    assert "AFB.31" in codes
    assert "AFB.52" in codes
    # TOC-raden ("....... 4") får inte bli en egen sektion-start
    afb31 = [s for s in sections if s.code == "AFB.31"]
    assert len(afb31) == 1
    assert "märkt" in afb31[0].text


def test_split_keeps_page_numbers():
    sections = split_af_sections(AF_PAGES)
    by_code = {s.code: s for s in sections}
    assert by_code["AFB.31"].page == 1
    assert by_code["AFB.52"].page == 2


# ---------- Citatverifiering (hallucinationsskyddet) ----------------------

def _sections():
    return split_af_sections(AF_PAGES)


def test_exact_quote_verifies():
    ok, ratio, page = verify_quote("Anbud skall lämnas skriftligen på svenska.", _sections())
    assert ok and ratio == 1.0 and page == 1


def test_paraphrase_is_rejected():
    ok, ratio, _ = verify_quote(
        "Anbudsgivaren måste skicka in anbudet på det svenska språket via post.",
        _sections(),
    )
    assert not ok  # parafras → aldrig grönt


def test_invented_quote_is_rejected():
    ok, _, _ = verify_quote(
        "Entreprenören skall ställa bankgaranti om 10 % av kontraktssumman.",
        _sections(),
    )
    assert not ok  # hallucinerat krav kan inte verifieras


def test_short_quotes_rejected():
    ok, _, _ = verify_quote("Anbud", _sections())
    assert not ok


# ---------- Statemaskinen --------------------------------------------------

def test_ready_only_reachable_from_formalia_check():
    # Grindprincipen: READY får bara nås från FORMALIA_CHECK
    sources = [s for s, targets in states.TRANSITIONS.items() if states.READY in targets]
    assert sources == [states.FORMALIA_CHECK]


def test_no_state_skips_to_submitted():
    sources = [s for s, targets in states.TRANSITIONS.items() if states.SUBMITTED in targets]
    assert sources == [states.READY]


# ---------- Formalia-hjälpare ----------------------------------------------

def test_anbudssumma_digit_matching():
    draft = f"Vi offererar härmed {_fmt_sek(1_687_336)} kr exklusive mervärdesskatt."
    assert _digits(draft) & _digits(_fmt_sek(1_687_336))


def test_wrong_sum_does_not_match():
    draft = f"Vi offererar härmed {_fmt_sek(1_500_000)} kr."
    assert not (_digits(draft) & _digits(_fmt_sek(1_687_336)))


# ---------- Priskaskadens kodhierarki ---------------------------------------

def test_ancestor_codes_walk_up():
    assert _ancestor_codes("SBB.12") == ["SBB.1", "SBB"]
    assert _ancestor_codes("DCB.313") == ["DCB.31", "DCB.3", "DCB"]
    assert _ancestor_codes("CBB") == []


# ---------- Etikettords-skyddet (DATUM-buggen) ------------------------------

def test_label_words_rejected_as_project_name():
    from app.pdf_extractor import _clean_label_value
    assert _clean_label_value("DATUM") is None
    assert _clean_label_value("DOKUMENTNUMMER") is None
    assert _clean_label_value("VÄG 875 GC SUNDBORN") == "VÄG 875 GC SUNDBORN"


# ---------- Prismotorn: exclude får inte filtrera bort NULL-case-obs --------

@pytest.mark.anyio
async def test_exclude_keeps_standalone_observations(tmp_path, monkeypatch):
    """Importerade MAP-obs har case_id=NULL. SQL:s trevärdeslogik gör att
    'case_id != x' filtrerar bort NULL-rader — kaskaden ska behålla dem."""
    import importlib
    monkeypatch.setenv("LODET_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import app.db as dbmod
    importlib.reload(dbmod)
    import app.price_engine as pe
    importlib.reload(pe)

    await dbmod.init_db()
    async with dbmod.SessionLocal() as session:
        session.add(dbmod.PriceObservation(
            id="obs_t1", case_id=None, ama_code="DCB.313", description="Fyllning",
            unit="m2", unit_price=9.0, quantity=100, observed_at="2026-01-01",
            source="map_netto", won=False, meta={},
        ))
        await session.commit()

    s = await pe.suggest("DCB.313", "Fyllning", "m2", exclude_case_id="case_nagot")
    assert s is not None and s["n"] == 1  # NULL-obs överlever exclude


def test_cover_page_project_name():
    from app.pdf_extractor import sniff_metadata_from_text
    text = "KARLSTAD.SE\nHaga Entré Park och Torg\nFÖRFRÅGNINGSUNDERLAG\nDiarie nr: 322223\nDATUM: 2025-02-28"
    assert sniff_metadata_from_text(text).get("project_name") == "Haga Entré Park och Torg"


# ---------- Prismotorn: utliggarskydd + confidence -------------------------

def test_spread_and_confidence():
    from app.price_engine import _spread_ratio, _confidence
    # DEK.21-fallet: 10 kr vs 121 320 kr → enorm spridning → låg confidence
    assert _spread_ratio([10, 121320]) > 1000
    assert _confidence(5, _spread_ratio([10, 121320])) == "low"
    # Samstämmig historik, flera källor → grön
    assert _confidence(5, _spread_ratio([100, 110, 120])) == "high"
    # Få källor eller måttlig spridning → gul
    assert _confidence(2, 2.0) == "medium"
    assert _confidence(1, 1.0) == "low"


def test_project_name_junk_guard():
    """Projektnamns-extraktionen ska förkasta handläggarsignaturer och
    numrerade dokumentkategorier — men behålla riktiga projektnamn."""
    from app.pdf_extractor import _clean_label_value
    assert _clean_label_value("J Berlin, dmvb") is None        # signatur
    assert _clean_label_value("12. Ritningar") is None         # kategori-mapp
    assert _clean_label_value("10 Mängdförteckning") is None
    assert _clean_label_value("Viltpassage E16") == "Viltpassage E16"
    assert _clean_label_value("Skjutbana Lugnet, Falun") == "Skjutbana Lugnet, Falun"
    assert _clean_label_value("VÄG 875 GC SUNDBORN") == "VÄG 875 GC SUNDBORN"


def test_classifier_handles_nfd_filenames():
    """macOS lagrar 'ä' dekomponerat (NFD: a+◌̈). Klassificeraren måste vika
    BÅDE NFC och NFD till 'a/o' — annars klassas en Mac-uppladdad
    'Mängdförteckning.xlsx' som okänd och hela prisflödet faller."""
    import unicodedata
    from app.file_classifier import classify, _name_signal
    nfc = "10.1 Ej prissatt mängdförteckning ÖL Katrinedal.xlsx"
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd  # de skiljer sig på byte-nivå
    assert "mangdforteckning" in _name_signal(nfc)
    assert "mangdforteckning" in _name_signal(nfd)   # regressionen
    assert classify(nfc, b"", "").type == "mf"
    assert classify(nfd, b"", "").type == "mf"


def test_narrow_by_description_picks_comparable_work():
    """Samma kod+enhet men olika arbete: beskrivningen avgör vilka priser
    som är jämförbara (montering vs leverans)."""
    from types import SimpleNamespace
    from app.price_engine import _narrow_by_description
    obs = [
        SimpleNamespace(unit_price=10, description="Montering av stolpe på plats"),
        SimpleNamespace(unit_price=12, description="Montering av stolpe inkl infästning"),
        SimpleNamespace(unit_price=121320, description="Leverans av komplett transformatorstation"),
    ]
    narrowed = _narrow_by_description(obs, "Montering av belysningsstolpe")
    descs = [o.description for o in narrowed]
    assert any("Montering" in d for d in descs)
    assert all("transformatorstation" not in d for d in descs)  # utliggaren bortgallrad
