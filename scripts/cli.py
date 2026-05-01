"""CLI-genväg för parser. Användning: python -m scripts.cli <csv> [out.json]"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.parser import parse_csv


def main() -> None:
    if len(sys.argv) < 2:
        print("Användning: python -m scripts.cli <csv> [output.json]")
        sys.exit(1)

    src = Path(sys.argv[1])
    doc = parse_csv(src)
    summary = doc.summary()

    print("=" * 70)
    print(f"DOKUMENT: {summary['project']}  ({summary['document_number']})")
    print(f"Status: {summary['status']}  |  Datum: {doc.date}  |  Handläggare: {doc.handlaggare}")
    if summary['total_amount_sek']:
        print(f"Totalt belopp: {summary['total_amount_sek']:,.0f} kr".replace(",", " "))
    print(f"Rader: {summary['line_count']}  ({summary['priced_lines']} prissatta, {summary['lump_sum_count']} klumpsumma)")
    print(f"AMA-koder: {len(summary['ama_codes_used'])}")
    print("=" * 70)

    if len(sys.argv) >= 3:
        Path(sys.argv[2]).write_text(
            json.dumps(doc.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n✓ JSON sparad till {sys.argv[2]}")


if __name__ == "__main__":
    main()
