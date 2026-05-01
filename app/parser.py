"""
Lodet parser — svensk mängdförteckning (CSV) → strukturerad form.

Hanterar:
  - Parent-child-struktur (AMA-kod-grupp → konkreta poster)
  - AMA Anläggning-koder (BBC, BEC, SBC, SND, YGB, YHB, YJK, ...)
  - Klumpsumma (markerat med "-" i enhet/mängd/à-pris)
  - Svenska tal-formatering ("371 700" → 371700)
  - Citerade flerradsbeskrivningar
  - Tomma separatorrader
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import IO


AMA_CODE_PATTERN = re.compile(r"^[A-Z]{1,4}(?:\.\d+)*$")


@dataclass
class OfferLine:
    line_number: int
    ama_code: str | None
    ama_section_title: str | None
    description: str
    unit: str | None
    quantity: float | None
    unit_price: float | None
    total_amount: float | None
    is_lump_sum: bool
    raw_row: list[str] = field(repr=False, default_factory=list)


@dataclass
class OfferDocument:
    document_number: str | None
    project_name: str | None
    date: str | None
    handlaggare: str | None
    uppdragsnummer: str | None
    total_amount: float | None
    status: str | None
    lines: list[OfferLine] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "project": self.project_name,
            "document_number": self.document_number,
            "date": self.date,
            "status": self.status,
            "total_amount_sek": self.total_amount,
            "line_count": len(self.lines),
            "ama_codes_used": sorted({l.ama_code for l in self.lines if l.ama_code}),
            "lump_sum_count": sum(1 for l in self.lines if l.is_lump_sum),
            "priced_lines": sum(1 for l in self.lines if l.unit_price is not None),
        }

    def to_dict(self) -> dict:
        return {
            "metadata": {
                "project_name": self.project_name,
                "document_number": self.document_number,
                "date": self.date,
                "handlaggare": self.handlaggare,
                "uppdragsnummer": self.uppdragsnummer,
                "total_amount_sek": self.total_amount,
                "status": self.status,
            },
            "lines": [
                {k: v for k, v in asdict(ln).items() if k != "raw_row"}
                for ln in self.lines
            ],
        }


def parse_swedish_number(value: str) -> float | None:
    if not value or value.strip() in {"-", ""}:
        return None
    cleaned = value.strip().replace(" ", "").replace("\xa0", "")
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def is_ama_code(value: str) -> bool:
    if not value:
        return False
    return bool(AMA_CODE_PATTERN.match(value.strip()))


def detect_columns(rows: list[list[str]]) -> dict[str, int]:
    targets = {
        "kod": ["KOD"],
        "text": ["TEXT", "BENÄMNING", "BESKRIVNING"],
        "unit": ["ENHET"],
        "qty": ["MÄNGD", "MÄNGD ", "ANTAL"],
        "unit_price": ["À-PRIS", "Á-PRIS", "A-PRIS", "ENHETSPRIS"],
        "total": ["BELOPP", "TOTALT", "SUMMA"],
    }

    for row_idx, row in enumerate(rows[:15]):
        upper = [c.strip().upper() for c in row]
        if "KOD" in upper and any(t in upper for t in ["TEXT", "BENÄMNING"]):
            mapping: dict[str, int] = {}
            for key, candidates in targets.items():
                for c in candidates:
                    if c in upper:
                        mapping[key] = upper.index(c)
                        break
            mapping["_header_row"] = row_idx
            return mapping

    raise ValueError("Hittade ingen kolumnheader (KOD/TEXT/...) inom de första 15 raderna")


def extract_metadata(rows: list[list[str]]) -> dict:
    meta: dict = {
        "project_name": None,
        "document_number": None,
        "date": None,
        "handlaggare": None,
        "uppdragsnummer": None,
        "total_amount": None,
        "status": None,
    }

    label_value_pairs = [
        ("MÄNGDFÖRTECKNING", "status"),
        ("PROJEKT", "project_name"),
        ("DOKUMENTNUMMER", "document_number"),
        ("DATUM", "date"),
        ("HANDLÄGGARE", "handlaggare"),
        ("UPPDRAGSNUMMER", "uppdragsnummer"),
        ("TOTALT BELOPP", "total_amount"),
    ]

    for label, target in label_value_pairs:
        for row_idx, row in enumerate(rows[:12]):
            for col_idx, cell in enumerate(row):
                if cell.strip().upper() == label and row_idx + 1 < len(rows):
                    next_row = rows[row_idx + 1]
                    if col_idx < len(next_row):
                        value = next_row[col_idx].strip()
                        if value and value not in {"-"}:
                            if target == "total_amount":
                                meta[target] = parse_swedish_number(value)
                            else:
                                meta[target] = value
                            break

    return meta


def _read_csv_rows(stream: IO[str], delimiter: str = ";") -> list[list[str]]:
    reader = csv.reader(stream, delimiter=delimiter, quotechar='"')
    return [row for row in reader]


def parse_csv_text(text: str, delimiter: str = ";") -> OfferDocument:
    """Parse CSV-innehåll (sträng) till OfferDocument."""
    return _parse_rows(_read_csv_rows(io.StringIO(text), delimiter=delimiter))


def parse_csv_bytes(data: bytes, delimiter: str = ";") -> OfferDocument:
    """Parse CSV-bytes till OfferDocument. Hanterar BOM och latin-1 fallback."""
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Kunde inte avkoda CSV-fil — okänd teckenkodning")
    return parse_csv_text(text, delimiter=delimiter)


def parse_csv(path: Path, delimiter: str = ";") -> OfferDocument:
    """Läs fil från disk och parse till OfferDocument."""
    with path.open(encoding="utf-8-sig") as fh:
        return _parse_rows(_read_csv_rows(fh, delimiter=delimiter))


def _parse_rows(raw_rows: list[list[str]]) -> OfferDocument:
    meta = extract_metadata(raw_rows)
    cols = detect_columns(raw_rows)
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

    for idx, row in enumerate(raw_rows[header_row + 1:], start=header_row + 2):
        max_col = max(cols.get(k, 0) for k in ["kod", "text", "unit", "qty", "unit_price", "total"])
        if len(row) <= max_col:
            row = row + [""] * (max_col - len(row) + 1)

        kod = row[cols["kod"]].strip()
        text = row[cols["text"]].strip()
        unit = row[cols["unit"]].strip() if "unit" in cols else ""
        qty = row[cols["qty"]].strip() if "qty" in cols else ""
        unit_price = row[cols["unit_price"]].strip() if "unit_price" in cols else ""
        total = row[cols["total"]].strip() if "total" in cols else ""

        if not any([kod, text, unit, qty, unit_price, total]):
            continue

        if is_ama_code(kod):
            current_ama_code = kod
            current_section_title = text or None
            continue

        if not text:
            continue

        line = OfferLine(
            line_number=idx,
            ama_code=current_ama_code,
            ama_section_title=current_section_title,
            description=text,
            unit=unit if unit and unit != "-" else None,
            quantity=parse_swedish_number(qty),
            unit_price=parse_swedish_number(unit_price),
            total_amount=parse_swedish_number(total),
            is_lump_sum=(unit == "-" and qty == "-" and unit_price == "-"),
            raw_row=row,
        )
        doc.lines.append(line)

    return doc
