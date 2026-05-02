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

PROJECT_NAME_PATTERN = re.compile(r"(?:projekt|objekt)[:\s]+([A-ZÅÄÖ][^\n]{4,80})", re.IGNORECASE)
DOCUMENT_NUMBER_PATTERN = re.compile(r"(?:dokument(?:nr|nummer)?|handlings?[\-\s]?nr)[:\s]+([\w\-\.]{3,20})", re.IGNORECASE)
DATE_PATTERN = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
ANBUDSDAG_PATTERN = re.compile(r"(?:anbud|inl[äa]mn[a-z]+)[^.\n]{0,80}?(\d{1,2}\s+\w+\s+20\d{2}|20\d{2}-\d{2}-\d{2})", re.IGNORECASE)
KUND_PATTERN = re.compile(r"(?:bestäl{1,2}are|kund|uppdragsgivare)[:\s]+([A-ZÅÄÖ][^\n]{4,60})", re.IGNORECASE)
AMOUNT_PATTERN = re.compile(r"(\d{1,3}(?:\s\d{3})+|\d{4,})\s*(?:kr|sek)", re.IGNORECASE)


def sniff_metadata_from_text(text: str) -> dict:
    """Försök hitta projekt/dokument/datum från fri text."""
    found: dict = {}

    if m := PROJECT_NAME_PATTERN.search(text):
        found["project_name"] = m.group(1).strip()
    if m := DOCUMENT_NUMBER_PATTERN.search(text):
        found["document_number"] = m.group(1).strip()
    if m := DATE_PATTERN.search(text):
        found["date"] = m.group(1)
    if m := ANBUDSDAG_PATTERN.search(text):
        found["bid_due_at"] = m.group(1)
    if m := KUND_PATTERN.search(text):
        found["customer_name"] = m.group(1).strip()
    if m := AMOUNT_PATTERN.search(text):
        amount_str = m.group(1).replace(" ", "")
        try:
            found["mentioned_amount_sek"] = float(amount_str)
        except ValueError:
            pass

    return found
