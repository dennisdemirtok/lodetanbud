"""
Backfill av historisk prisdata ur MAP-kalkyler (.mdbklk) → prismotorn (AP4).

Körs LOKALT (kräver mdbtools). Parsar varje cases huvudkalkyl och postar
nettopris-observationerna till appens import-endpoint.

    # mot produktion (kräver LODET_IMPORT_TOKEN satt på Railway + lokalt):
    LODET_IMPORT_TOKEN=xxx python -m scripts.import_map_kalkyl \
        --url https://lodetanbud-production.up.railway.app

    # torrkörning (parsar + sammanfattar, postar inget):
    python -m scripts.import_map_kalkyl --dry-run

Idempotent: varje case postas med import_key = projektnamn|datum, så
omkörning ersätter i stället för att dubblera.
"""

from __future__ import annotations

import argparse
import os
import sys
import unicodedata
import urllib.request
from pathlib import Path

from app.map_kalkyl import have_mdbtools, parse_kalkyl

GOLDEN = Path(__file__).resolve().parent.parent / "evals" / "golden"


def _post(url: str, token: str, body: dict) -> dict:
    import json
    req = urllib.request.Request(
        url.rstrip("/") + "/api/import/historic",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Import-Token": token},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def _main_kalkyl(case_dir: Path) -> Path | None:
    mdbs = list(case_dir.rglob("*.mdbklk"))
    if not mdbs:
        return None
    return max(mdbs, key=lambda p: p.stat().st_size)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://lodetanbud-production.up.railway.app")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--region", default=None, help="t.ex. 'Mellansverige' — sätts på alla obs")
    args = ap.parse_args()

    if not have_mdbtools():
        print("mdbtools saknas — installera med: brew install mdbtools")
        return 1

    token = os.getenv("LODET_IMPORT_TOKEN")
    if not args.dry_run and not token:
        print("LODET_IMPORT_TOKEN saknas i miljön (krävs för skarp körning, ej --dry-run)")
        return 1

    if not GOLDEN.exists():
        print(f"Hittar inte golden-settet: {GOLDEN}")
        return 1

    total_posts = 0
    total_imported = 0
    for case_dir in sorted(GOLDEN.iterdir()):
        if not case_dir.is_dir():
            continue
        mdb = _main_kalkyl(case_dir)
        if mdb is None:
            print(f"  {case_dir.name[:42]:<44} (ingen .mdbklk)")
            continue
        try:
            parsed = parse_kalkyl(mdb)
        except Exception as e:
            print(f"  {case_dir.name[:42]:<44} FEL: {e}")
            continue

        priced = [p for p in parsed["posts"] if p.get("ama_code") and p.get("unit_price")]
        total_posts += len(priced)
        status = f"{len(priced)} poster · {parsed['kalkyl_date'] or '?'}"

        if args.dry_run:
            print(f"  {case_dir.name[:42]:<44} {status}  [dry-run]")
            continue

        try:
            res = _post(args.url, token, {
                "project_name": unicodedata.normalize("NFC", case_dir.name),
                "observed_at": parsed["kalkyl_date"],
                "region": args.region,
                "posts": priced,
                "source": "map_netto",
            })
            total_imported += res.get("imported", 0)
            print(f"  {case_dir.name[:42]:<44} {status} → {res.get('imported')} importerade")
        except Exception as e:
            print(f"  {case_dir.name[:42]:<44} POST-fel: {e}")

    print("-" * 72)
    if args.dry_run:
        print(f"Torrkörning: {total_posts} prissatta poster redo att importeras.")
    else:
        print(f"Importerade {total_imported} prisobservationer av {total_posts} möjliga.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
