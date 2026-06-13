"""
PDF-textextraktion — pypdf-baserad.

Plockar text från första sidan för metadata-detektering. Snabb och
tillräcklig för klassificering. För full parser krävs pdfplumber + LLM.
"""

from __future__ import annotations

import io
import re

from pypdf import PdfReader


def extract_first_page_text(data: bytes, max_chars: int = 4000) -> str:
    """Returnera text från första sidan, trunkerad."""
    try:
        reader = PdfReader(io.BytesIO(data))
        if not reader.pages:
            return ""
        text = reader.pages[0].extract_text() or ""
        return text[:max_chars]
    except Exception:
        return ""


def extract_pages_text(data: bytes, max_pages: int = 300) -> list[str]:
    """Text per sida — för käll-länkning (sida) i kravmatrisen (AP3)."""
    try:
        reader = PdfReader(io.BytesIO(data))
        return [(page.extract_text() or "") for page in reader.pages[:max_pages]]
    except Exception:
        return []


def extract_all_text(data: bytes, max_chars: int = 50_000) -> str:
    """Returnera hela dokumentets text, trunkerad."""
    try:
        reader = PdfReader(io.BytesIO(data))
        parts = []
        chars = 0
        for page in reader.pages:
            t = page.extract_text() or ""
            parts.append(t)
            chars += len(t)
            if chars >= max_chars:
                break
        return "\n".join(parts)[:max_chars]
    except Exception:
        return ""


def extract_metadata(data: bytes) -> dict:
    """Extrahera dokument-metadata (titel, antal sidor, författare)."""
    try:
        reader = PdfReader(io.BytesIO(data))
        meta = reader.metadata or {}
        return {
            "page_count": len(reader.pages),
            "title": getattr(meta, "title", None),
            "author": getattr(meta, "author", None),
            "subject": getattr(meta, "subject", None),
        }
    except Exception:
        return {"page_count": 0, "title": None, "author": None, "subject": None}


# ---- Mönsterextraktion från text ---------------------------------------

# Kräver kolon mellan etikett och värde — "projekt: Namn", inte "PROJEKT  DATUM"
# i en tabell-header (det gav DATUM-buggen).
PROJECT_NAME_PATTERN = re.compile(r"(?:projekt|objekt)\s*:\s*([A-ZÅÄÖ][^\n]{4,80})", re.IGNORECASE)
DOCUMENT_NUMBER_PATTERN = re.compile(r"(?:dokument(?:nr|nummer)?|handlings?[\-\s]?nr)\s*:\s*([\w\-\.]{3,20})", re.IGNORECASE)
DATE_PATTERN = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
ANBUDSDAG_PATTERN = re.compile(r"(?:anbud|inl[äa]mn[a-z]+)[^.\n]{0,80}?(\d{1,2}\s+\w+\s+20\d{2}|20\d{2}-\d{2}-\d{2})", re.IGNORECASE)
KUND_PATTERN = re.compile(r"(?:bestäl{1,2}are|kund|uppdragsgivare)\s*:\s*([A-ZÅÄÖ][^\n]{4,60})", re.IGNORECASE)
AMOUNT_PATTERN = re.compile(r"(\d{1,3}(?:\s\d{3})+|\d{4,})\s*(?:kr|sek)", re.IGNORECASE)

# Etikettord som aldrig är ett projekt-/kundnamn (skydd mot tabell-headers)
_LABEL_WORDS = {
    "datum", "dokumentnummer", "dokumentnr", "handläggare", "handlaggare",
    "uppdragsnummer", "uppdragsnr", "projekt", "objekt", "status", "sida",
    "beställare", "bestallare", "kund", "innehåll", "innehall", "bet", "rev",
}


# Värden som ser ut som något ANNAT än ett projektnamn:
#  - handläggar-/signatursträngar: initial + namn + ", förkortning"  (t.ex. "J Berlin, dmvb")
#  - numrerade dokumentkategorier:  "12. Ritningar", "10 Mängdförteckning"
_JUNK_VALUE_RE = re.compile(
    r"^[A-ZÅÄÖ]\.?\s+\S+,\s*[a-zåäö]{2,8}$"
    r"|^\d+[.\d]*[\s_]\S",
)


def _clean_label_value(value: str) -> str | None:
    """Trimma ett extraherat värde och förkasta om det är ett etikettord,
    en handläggarsignatur eller en numrerad dokumentkategori."""
    v = re.sub(r"\s+", " ", (value or "")).strip(" :\t")
    if not v or v.lower() in _LABEL_WORDS:
        return None
    # Förkasta om värdet börjar med ett etikettord (header-rad fångad)
    first = v.split()[0].lower().rstrip(":") if v.split() else ""
    if first in _LABEL_WORDS:
        return None
    if _JUNK_VALUE_RE.match(v):
        return None
    return v


def _project_from_cover_page(text: str) -> str | None:
    """Svensk FFU-framsida: projektnamnet står som egen rad strax OVANFÖR
    'FÖRFRÅGNINGSUNDERLAG' ("Haga Entré Park och Torg\\nFÖRFRÅGNINGSUNDERLAG")."""
    lines = [l.strip() for l in (text or "").splitlines()]
    for i, line in enumerate(lines):
        if re.fullmatch(r"FÖRFRÅGNINGSUNDERLAG\.?", line, re.IGNORECASE):
            for j in range(i - 1, max(-1, i - 4), -1):
                cand = lines[j] if j >= 0 else ""
                if 3 <= len(cand) <= 70 and not re.search(r"\d{4}-\d{2}|@|www\.", cand):
                    cleaned = _clean_label_value(cand)
                    if cleaned:
                        return cleaned
            break
    return None


def sniff_metadata_from_text(text: str) -> dict:
    """Försök hitta projekt/dokument/datum från fri text."""
    found: dict = {}

    if m := PROJECT_NAME_PATTERN.search(text):
        val = _clean_label_value(m.group(1))
        if val:
            found["project_name"] = val
    if "project_name" not in found:
        if val := _project_from_cover_page(text):
            found["project_name"] = val
    if m := DOCUMENT_NUMBER_PATTERN.search(text):
        found["document_number"] = m.group(1).strip()
    if m := DATE_PATTERN.search(text):
        found["date"] = m.group(1)
    if m := ANBUDSDAG_PATTERN.search(text):
        found["bid_due_at"] = m.group(1)
    if m := KUND_PATTERN.search(text):
        val = _clean_label_value(m.group(1))
        if val:
            found["customer_name"] = val
    if m := AMOUNT_PATTERN.search(text):
        amount_str = m.group(1).replace(" ", "")
        try:
            found["mentioned_amount_sek"] = float(amount_str)
        except ValueError:
            pass

    return found
