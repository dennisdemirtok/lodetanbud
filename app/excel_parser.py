"""
Excel-parser för svenska mängdförteckningar (.xlsx, .xlsm).

Återanvänder OfferLine/OfferDocument från parser.py så att resten av
systemet (frontend-tabell, drafts, Excel/CSV-export) fungerar oförändrat
oavsett om MF kom in som CSV eller Excel.
"""

from __future__ import annotations

import io
from typing import Any

from openpyxl import load_workbook

from app.parser import (
    OfferDocument,
    OfferLine,
    is_ama_code,
    parse_swedish_number,
)


def parse_excel_bytes(data: bytes) -> OfferDocument:
    """Parse Excel-MF till OfferDocument. Försöker varje blad i workbooken
    och returnerar första bladet som har MF-struktur."""
    wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)

    last_error: ValueError | None = None
    for ws in wb.worksheets:
        try:
            rows = _read_sheet_rows(ws, max_rows=5000)
            if not rows:
                continue
            return _parse_excel_rows(rows)
        except ValueError as e:
            last_error = e
            continue

    raise ValueError(
        f"Hittade ingen mängdförteckning-struktur i Excel-filen"
        + (f" (senaste fel: {last_error})" if last_error else "")
    )


def _read_sheet_rows(ws, max_rows: int = 5000) -> list[list[Any]]:
    """Läs rader som lista av lista. Behåller native typer (int/float/str)."""
    out: list[list[Any]] = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i >= max_rows:
            break
        cells = list(row)
        # Trimma trailing None
        while cells and cells[-1] is None:
            cells.pop()
        out.append(cells)
    return out


def _to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _to_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return parse_swedish_number(str(value))


def _detect_columns(rows: list[list[Any]]) -> dict[str, int]:
    """Letar efter header-rad. Speglar parser.detect_columns men robustare
    eftersom Excel ofta har metadata på första 20 raderna."""
    targets = {
        "kod": ["KOD", "AMA-KOD", "AMA"],
        "text": ["TEXT", "BENÄMNING", "BESKRIVNING"],
        "unit": ["ENHET"],
        "qty": ["MÄNGD", "ANTAL"],
        "unit_price": ["À-PRIS", "Á-PRIS", "A-PRIS", "ENHETSPRIS", "À PRIS", "À-PRIS (KR)"],
        "total": ["BELOPP", "TOTALT", "SUMMA", "TOTALSUMMA"],
    }

    for row_idx, row in enumerate(rows[:30]):
        upper = [_to_str(c).upper() for c in row]
        has_kod = any(c in {"KOD", "AMA-KOD", "AMA"} for c in upper)
        has_text = any(c in {"TEXT", "BENÄMNING", "BESKRIVNING"} for c in upper)
        if has_kod and has_text:
            mapping: dict[str, int] = {}
            for key, candidates in targets.items():
                for c in candidates:
                    if c in upper:
                        mapping[key] = upper.index(c)
                        break
            mapping["_header_row"] = row_idx
            return mapping

    raise ValueError("Hittade ingen kolumnheader (KOD/TEXT/…) i Excel-arket")


def _extract_metadata(rows: list[list[Any]]) -> dict:
    """Plocka projekt/dokument-metadata från första 15 raderna."""
    meta: dict = {
        "project_name": None,
        "document_number": None,
        "date": None,
        "handlaggare": None,
        "uppdragsnummer": None,
        "total_amount": None,
        "status": None,
    }

    label_targets = [
        ("MÄNGDFÖRTECKNING", "status"),
        ("PROJEKT", "project_name"),
        ("OBJEKT", "project_name"),
        ("DOKUMENTNUMMER", "document_number"),
        ("DOKUMENTNR", "document_number"),
        ("HANDLINGSNR", "document_number"),
        ("DATUM", "date"),
        ("HANDLÄGGARE", "handlaggare"),
        ("UPPDRAGSNUMMER", "uppdragsnummer"),
        ("UPPDRAGSNR", "uppdragsnummer"),
        ("TOTALT BELOPP", "total_amount"),
        ("TOTALSUMMA", "total_amount"),
    ]

    for label, target in label_targets:
        for row_idx, row in enumerate(rows[:15]):
            for col_idx, cell in enumerate(row):
                if _to_str(cell).upper() != label:
                    continue
                # Värde i samma rad nästa cell ELLER raden under samma kolumn
                same_row_next = _to_str(row[col_idx + 1]) if col_idx + 1 < len(row) else ""
                next_row = rows[row_idx + 1] if row_idx + 1 < len(rows) else []
                next_row_same_col = _to_str(next_row[col_idx]) if col_idx < len(next_row) else ""
                value = same_row_next or next_row_same_col
                if value and value not in {"-", ":"}:
                    if target == "total_amount":
                        meta[target] = parse_swedish_number(value)
                    elif meta.get(target) is None:
                        meta[target] = value
                break

    return meta


def _parse_excel_rows(rows: list[list[Any]]) -> OfferDocument:
    meta = _extract_metadata(rows)
    cols = _detect_columns(rows)
    header_row = cols["_header_row"]

    doc = OfferDocument(
        document_number=meta["document_number"],
        project_name=meta["project_name"],
        date=meta["date"],
        handlaggare=meta["handlaggare"],
        uppdragsnummer=meta["uppdragsnummer"],
        total_amount=meta["total_amount"],
        status=meta["status"],
    )

    current_ama_code: str | None = None
    current_section_title: str | None = None
    sum_amount = 0.0

    for idx, row in enumerate(rows[header_row + 1:], start=header_row + 2):
        max_col = max(cols.get(k, 0) for k in ["kod", "text", "unit", "qty", "unit_price", "total"])
        if len(row) <= max_col:
            row = row + [None] * (max_col - len(row) + 1)

        kod = _to_str(row[cols["kod"]])
        text = _to_str(row[cols["text"]])
        unit = _to_str(row[cols["unit"]]) if "unit" in cols else ""
        qty_raw = row[cols["qty"]] if "qty" in cols else None
        price_raw = row[cols["unit_price"]] if "unit_price" in cols else None
        total_raw = row[cols["total"]] if "total" in cols else None

        if not any([kod, text, unit, _to_str(qty_raw), _to_str(price_raw), _to_str(total_raw)]):
            continue

        # Sektionsrad — AMA-kod ensam med titel och inga mängder/priser
        if is_ama_code(kod) and qty_raw is None and price_raw is None:
            current_ama_code = kod
            current_section_title = text or None
            continue

        if not text:
            continue

        qty = _to_number(qty_raw)
        unit_price = _to_number(price_raw)
        total = _to_number(total_raw)

        unit_str = unit if unit and unit != "-" else None
        is_lump = (
            (not unit_str)
            and qty is None
            and unit_price is None
            and total is not None
        )

        line = OfferLine(
            line_number=idx,
            ama_code=current_ama_code,
            ama_section_title=current_section_title,
            description=text,
            unit=unit_str,
            quantity=qty,
            unit_price=unit_price,
            total_amount=total,
            is_lump_sum=is_lump,
            raw_row=[_to_str(c) for c in row],
        )
        doc.lines.append(line)
        if total:
            sum_amount += total

    # Om metadata inte hade totalsumma — använd summan av rader
    if doc.total_amount is None and sum_amount > 0:
        doc.total_amount = round(sum_amount, 2)

    if not doc.lines:
        raise ValueError("Hittade inga rader under header — bladet kanske är tomt eller har annan struktur")

    return doc
