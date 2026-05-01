"""CLI-genväg för Excel-builder. Användning: python -m scripts.cli_excel <parsed.json> <out.xlsx>"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from app.excel_builder import build_workbook


def main() -> None:
    if len(sys.argv) < 3:
        print("Användning: python -m scripts.cli_excel <parsed.json> <output.xlsx>")
        sys.exit(1)

    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    data = json.loads(src.read_text(encoding="utf-8"))
    xlsx = build_workbook(data, generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"))
    dst.write_bytes(xlsx)
    print(f"✓ Excel-mall sparad: {dst}")


if __name__ == "__main__":
    main()
