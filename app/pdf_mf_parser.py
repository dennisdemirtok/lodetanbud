"""
PDF-MF-parser — pdfplumber med tabellextraktion (genomförandeplan AP2.1).

Pipeline per sida:
  1. find_tables() deterministiskt → rader med {page, bbox}-span
  2. sidor med MF-signal men utan användbara tabeller → rescue-kandidater
     (skickas sidvis till Claude av pipelinen, extraction_method='llm')
  3. skannade sidor (< 50 tecken text, inga tabeller) → flaggas ocr_needed

Confidence per rad är heuristisk: känd enhet, parsad mängd, giltig
AMA-kod och summa ≈ mängd × à-pris höjer; deterministisk PDF når aldrig
1.0 (det gör bara CSV/Excel och människor i granskningsvyn).
"""

from __future__ import annotations

import io
import re
import unicodedata
from typing import Any

import pdfplumber

from app.parser import OfferDocument, OfferLine, is_ama_code, parse_swedish_number
from app.pdf_extractor import sniff_metadata_from_text


KNOWN_UNITS = {
    "m", "m2", "m²", "m3", "m³", "st", "ton", "kg", "tim", "h", "lm",
    "km", "mil", "kpl", "ls", "kr", "%", "mån", "dygn", "vecka", "ha",
}

_HEADER_TOKENS = {
    "kod":        {"KOD", "AMA-KOD", "AMA"},
    "text":       {"TEXT", "BENÄMNING", "BESKRIVNING"},
    "unit":       {"ENHET"},
    "qty":        {"MÄNGD", "ANTAL"},
    "unit_price": {"À-PRIS", "Á-PRIS", "A-PRIS", "ENHETSPRIS", "À PRIS"},
    "total":      {"BELOPP", "TOTALT", "SUMMA", "TOTALSUMMA"},
}

_MF_SIGNAL = re.compile(r"(MÄNGD|À-PRIS|Á-PRIS|BELOPP|ENHET)", re.IGNORECASE)


def _norm(value: Any) -> str:
    if value is None:
        return ""
    s = unicodedata.normalize("NFKC", str(value))
    return re.sub(r"\s+", " ", s).strip()


def _norm_upper(value: Any) -> str:
    return _norm(value).upper()


def _detect_header(row_values: list) -> dict[str, int] | None:
    upper = [_norm_upper(c) for c in row_values]
    has_kod = any(c in _HEADER_TOKENS["kod"] for c in upper)
    has_text = any(c in _HEADER_TOKENS["text"] for c in upper)
    if not (has_kod and has_text):
        return None
    mapping: dict[str, int] = {}
    for key, tokens in _HEADER_TOKENS.items():
        for idx, val in enumerate(upper):
            if val in tokens:
                mapping[key] = idx
                break
    return mapping


def _row_bbox(cells: list) -> list[float] | None:
    """Union av cell-bboxar i en tabellrad → [x0, top, x1, bottom]."""
    boxes = [c for c in cells if c is not None]
    if not boxes:
        return None
    x0 = min(b[0] for b in boxes)
    top = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    bottom = max(b[3] for b in boxes)
    return [round(x0, 1), round(top, 1), round(x1, 1), round(bottom, 1)]


# ---- Ordposition-baserad extraktion ---------------------------------------
# Svenska MF-PDF:er saknar ofta tabellinjer — kolumnerna finns bara som
# x-positioner. Vi hittar header-orden (KOD TEXT ENHET MÄNGD À-PRIS BELOPP),
# härleder kolumngränser ur deras x-center och bucketar varje radords
# center i rätt kolumn.

_COL_ORDER = ["kod", "text", "unit", "qty", "unit_price", "total"]


def _find_word_header(words: list[dict]) -> dict[str, float] | None:
    """Hitta header-raden bland orden. Returnerar {kolumn: x-center}."""
    by_token: dict[str, list[dict]] = {}
    for w in words:
        token = _norm_upper(w["text"])
        for key, tokens in _HEADER_TOKENS.items():
            if token in tokens:
                by_token.setdefault(key, []).append(w)

    if "kod" not in by_token or "text" not in by_token:
        return None

    # Kräver att KOD och TEXT ligger på samma visuella rad (±3 pt)
    for kod_w in by_token["kod"]:
        row_top = kod_w["top"]
        anchors: dict[str, float] = {}
        for key, ws in by_token.items():
            for w in ws:
                if abs(w["top"] - row_top) <= 3:
                    anchors[key] = (w["x0"] + w["x1"]) / 2
                    break
        if "kod" in anchors and "text" in anchors and ("qty" in anchors or "unit" in anchors):
            return anchors
    return None


def _column_boundaries(anchors: dict[str, float]) -> list[tuple[str, float, float]]:
    """[(kolumn, x_min, x_max)] ur header-ankarnas mittpunkter."""
    present = [(k, anchors[k]) for k in _COL_ORDER if k in anchors]
    present.sort(key=lambda kv: kv[1])
    bounds: list[tuple[str, float, float]] = []
    for i, (key, cx) in enumerate(present):
        lo = -1e9 if i == 0 else (present[i - 1][1] + cx) / 2
        hi = 1e9 if i == len(present) - 1 else (cx + present[i + 1][1]) / 2
        bounds.append((key, lo, hi))
    return bounds


def _words_to_rows(words: list[dict], header_top: float | None, bounds) -> list[dict]:
    """Klustra ord till visuella rader och bucketa per kolumn."""
    if header_top is not None:
        words = [w for w in words if w["top"] > header_top + 3]

    rows: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if rows and abs(rows[-1][0]["top"] - w["top"]) <= 3:
            rows[-1].append(w)
        else:
            rows.append([w])

    out: list[dict] = []
    for row_words in rows:
        cells: dict[str, list[str]] = {}
        centers: dict[str, list[float]] = {}
        for w in row_words:
            cx = (w["x0"] + w["x1"]) / 2
            for key, lo, hi in bounds:
                if lo <= cx < hi:
                    cells.setdefault(key, []).append(w["text"])
                    centers.setdefault(key, []).append(cx)
                    break
        bbox = [
            round(min(w["x0"] for w in row_words), 1),
            round(min(w["top"] for w in row_words), 1),
            round(max(w["x1"] for w in row_words), 1),
            round(max(w["bottom"] for w in row_words), 1),
        ]
        out.append({
            "cells": {k: " ".join(v) for k, v in cells.items()},
            "centers": centers,
            "bbox": bbox,
        })
    return out


def _to_number(value: Any) -> float | None:
    if value is None:
        return None
    return parse_swedish_number(str(value))


def _line_confidence(
    ama_code: str | None,
    unit: str | None,
    qty: float | None,
    price: float | None,
    total: float | None,
) -> float:
    conf = 0.6
    if unit and unit.lower() in KNOWN_UNITS:
        conf += 0.15
    if qty is not None:
        conf += 0.12
    if ama_code and is_ama_code(ama_code):
        conf += 0.05
    if total is not None and qty is not None and price is not None:
        if abs(total - qty * price) <= max(1.0, abs(total) * 0.01):
            conf = 0.97
    return round(min(conf, 0.97), 2)


def parse_pdf_mf(data: bytes) -> tuple[OfferDocument | None, list[dict]]:
    """
    Parsa en PDF-mängdförteckning.

    Strategi per sida: (1) find_tables för linjerade tabeller,
    (2) ordposition-baserad kolumnbucketing för linjelösa layouter,
    (3) sidor med MF-signal som ändå inte gav rader → rescue (LLM).

    Returnerar (doc, rescue_pages).
    """
    doc = OfferDocument(
        document_number=None, project_name=None, date=None,
        handlaggare=None, uppdragsnummer=None, total_amount=None, status=None,
    )
    rescue_pages: list[dict] = []
    ocr_pages = 0
    cols: dict[str, int] | None = None          # tabell-läge: kolumnindex
    word_anchors: dict[str, float] | None = None  # ord-läge: x-center per kolumn
    current_ama: str | None = None
    current_section: str | None = None
    sum_amount = 0.0

    def emit(kod: str, txt: str, unit: str, qty, price, total, bbox, pno: int, raw: list[str]) -> bool:
        """Gemensam radlogik för båda extraktionslägena. True om rad skrevs."""
        nonlocal current_ama, current_section, sum_amount
        has_unit = bool(unit) and unit != "-"

        if not any([kod, txt, has_unit, qty is not None, price is not None, total is not None]):
            return False

        # Sektionsrubrik: AMA-kod utan mängddata
        if is_ama_code(kod) and qty is None and price is None and total is None:
            current_ama = kod
            current_section = txt or current_section
            return False

        # TB-text utan mängddata → skip
        if not is_ama_code(kod) and not has_unit and qty is None and price is None and total is None:
            return False
        if not txt:
            return False

        line_code = kod if is_ama_code(kod) else current_ama
        conf = _line_confidence(line_code, unit if has_unit else None, qty, price, total)

        doc.lines.append(OfferLine(
            line_number=len(doc.lines) + 1,
            ama_code=line_code,
            ama_section_title=current_section,
            description=txt,
            unit=unit if has_unit else None,
            quantity=qty,
            unit_price=price,
            total_amount=total,
            is_lump_sum=(not has_unit and qty is None and price is None and total is not None),
            source={"page": pno, **({"bbox": bbox} if bbox else {})},
            extraction_method="deterministic",
            confidence=conf,
            raw_row=raw,
        ))
        if total:
            sum_amount += total
        return True

    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception:
        return None, []

    with pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""

            if pno == 1 and text:
                meta = sniff_metadata_from_text(text)
                doc.project_name = meta.get("project_name")
                doc.document_number = meta.get("document_number")
                doc.date = meta.get("date")

            try:
                tables = page.find_tables()
            except Exception:
                tables = []

            # Skannad sida: nästan ingen text och inga tabeller → OCR behövs
            if len(text.strip()) < 50 and not tables:
                ocr_pages += 1
                continue

            page_rows = 0

            # ---- Läge 1: linjerade tabeller -----------------------------
            for table in tables:
                try:
                    values = table.extract()
                except Exception:
                    continue
                if not values:
                    continue

                row_cells = [r.cells for r in table.rows]
                start_idx = 0
                local_cols = None
                for i, row in enumerate(values[:5]):
                    detected = _detect_header(row)
                    if detected:
                        local_cols = detected
                        start_idx = i + 1
                        break
                if local_cols:
                    cols = local_cols
                elif cols is None:
                    continue
                elif values and max(cols.values()) >= len(values[0]):
                    continue

                max_col = max(cols.values())
                for i in range(start_idx, len(values)):
                    row = list(values[i])
                    if len(row) <= max_col:
                        row = row + [None] * (max_col - len(row) + 1)

                    kod = _norm(row[cols["kod"]]) if "kod" in cols else ""
                    txt = _norm(row[cols["text"]]) if "text" in cols else ""
                    unit = _norm(row[cols["unit"]]) if "unit" in cols else ""
                    qty = _to_number(row[cols["qty"]]) if "qty" in cols else None
                    price = _to_number(row[cols["unit_price"]]) if "unit_price" in cols else None
                    total = _to_number(row[cols["total"]]) if "total" in cols else None
                    bbox = _row_bbox(row_cells[i]) if i < len(row_cells) else None

                    if emit(kod, txt, unit, qty, price, total, bbox, pno, [_norm(c) for c in row]):
                        page_rows += 1

            # ---- Läge 2: ordpositioner (linjelösa MF:er) -----------------
            if page_rows == 0:
                try:
                    words = page.extract_words()
                except Exception:
                    words = []

                if words:
                    header = _find_word_header(words)
                    header_top = None
                    if header:
                        word_anchors = header
                        # headerns top = KOD-ordets top (för att skippa raden)
                        kod_tokens = _HEADER_TOKENS["kod"]
                        for w in words:
                            if _norm_upper(w["text"]) in kod_tokens:
                                header_top = w["top"]
                                break

                    if word_anchors:
                        bounds = _column_boundaries(word_anchors)
                        # Buffert för wrappade beskrivningar: text-rader utan
                        # mängddata direkt ovanför en MF-rad hör till den.
                        text_buf: list[tuple[list[float], str]] = []
                        for row in _words_to_rows(words, header_top, bounds):
                            c = row["cells"]
                            centers = row.get("centers") or {}
                            kod = _norm(c.get("kod", ""))
                            txt = _norm(c.get("text", ""))
                            unit = _norm(c.get("unit", ""))
                            qty = _to_number(c.get("qty"))
                            price = _to_number(c.get("unit_price"))
                            total = _to_number(c.get("total"))

                            # Semantisk validering — lång TB-text wrappar in i
                            # enhet/mängd-kolumnerna och måste filtreras här.
                            def _near(key: str, tol: float = 30.0) -> bool:
                                anchor = word_anchors.get(key)
                                cs = centers.get(key) or []
                                return bool(cs) and anchor is not None and all(
                                    abs(cx - anchor) <= tol for cx in cs
                                )

                            is_section = is_ama_code(kod) and qty is None and price is None and total is None
                            unit_known = bool(unit) and unit.lower() in KNOWN_UNITS
                            unit_ok = unit_known or (
                                bool(unit) and len(unit) <= 6 and unit.isalpha() and _near("unit")
                            )
                            qty_ok = qty is not None and _near("qty", tol=60.0)
                            is_mf_row = unit_ok and qty_ok
                            is_lump = (
                                not kod and not unit and qty is None and price is None
                                and total is not None and _near("total", tol=60.0)
                                and bool(txt) and len(txt) <= 70
                                and not txt.rstrip().endswith((".", ":", ","))
                            )
                            only_text = (
                                bool(txt) and not kod and not unit
                                and qty is None and price is None and total is None
                            )

                            if not (is_section or is_mf_row or is_lump):
                                # Text-rad utan mängddata: kan vara wrappad
                                # MF-beskrivning — buffra om den hänger ihop
                                # vertikalt med föregående text-rad.
                                if only_text:
                                    if text_buf and row["bbox"][1] - text_buf[-1][0][3] > 7:
                                        text_buf = []
                                    text_buf.append((row["bbox"], txt))
                                else:
                                    text_buf = []
                                continue

                            # MF-rad utan egen beskrivning → hämta från
                            # tight liggande text-rader ovanför
                            if is_mf_row and not txt and text_buf:
                                if row["bbox"][1] - text_buf[-1][0][3] <= 7:
                                    txt = " ".join(t for _b, t in text_buf)
                            text_buf = []

                            if emit(kod, txt, unit if is_mf_row else ("" if is_lump else unit),
                                    qty, price, total, row["bbox"], pno,
                                    [kod, txt, unit, c.get("qty", ""), c.get("unit_price", ""), c.get("total", "")]):
                                # okänd (men positionerad) enhet → rött för granskning
                                if is_mf_row and not unit_known:
                                    doc.lines[-1].confidence = min(doc.lines[-1].confidence, 0.6)
                                page_rows += 1

            # ---- Läge 3: rescue (LLM i pipelinen) ------------------------
            if page_rows == 0 and text and _MF_SIGNAL.search(text) and len(text.strip()) > 200:
                rescue_pages.append({"page": pno, "text": text[:8000]})

    if doc.total_amount is None and sum_amount > 0:
        doc.total_amount = round(sum_amount, 2)

    if not doc.lines and not rescue_pages:
        return None, []

    if ocr_pages:
        # Flagga för granskningsvyn — OCR-försteg införs senare
        doc.status = f"{ocr_pages} sidor verkar skannade (OCR behövs)"

    return (doc if doc.lines else None), rescue_pages


# Schema för LLM-rescue av sidor där tabellextraktionen misslyckades
RESCUE_SCHEMA = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "array",
            "description": "MF-rader på sidan. Hoppa över ren beskrivningstext utan mängd/enhet.",
            "items": {
                "type": "object",
                "properties": {
                    "ama_code": {"type": "string", "description": "AMA-kod raden hör till (t.ex. 'CBB.112'). Tom om okänd."},
                    "description": {"type": "string"},
                    "unit": {"type": "string", "description": "Enhet (m, m2, m3, st, ton...). Tom för klumpsumma."},
                    "quantity": {"type": ["number", "null"]},
                    "unit_price": {"type": ["number", "null"]},
                    "total_amount": {"type": ["number", "null"]},
                },
                "required": ["ama_code", "description", "unit", "quantity", "unit_price", "total_amount"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["lines"],
    "additionalProperties": False,
}

RESCUE_SYSTEM = """Du extraherar rader ur en svensk mängdförteckning (MF).
Du får råtext från EN sida i en MF-PDF där tabellstrukturen inte gick att
läsa maskinellt. Plocka ut varje MF-rad: AMA-kod (ärvs från närmaste
rubrik ovanför om raden saknar egen), beskrivning, enhet, mängd, à-pris,
belopp. Ta INTE med ren beskrivande text (teknisk beskrivning) som saknar
mängd och enhet. Hitta ALDRIG på värden — null när uppgift saknas."""
