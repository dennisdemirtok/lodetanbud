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
