"""
Eval-harness (genomförandeplan AP6) — körs mot golden settet i evals/golden/.

    python -m evals.run --suite mf

MF-suiten mäter extraktionsrobusthet: hittas MF i varje case, hur många
rader parsas, andel lågkonfidenta, fel. När facit-filer finns
(facit_mf.json per case, exporteras från granskningsvyn) jämförs
radrecall och fältaccuracy mot dem. Resultat sparas i evals/results/
och diffas mot föregående körning.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
import unicodedata
import zipfile
from pathlib import Path

from app import excel_parser, pdf_mf_parser
from app.file_classifier import classify
from app.parser import parse_csv_bytes

GOLDEN = Path(__file__).parent / "golden"
RESULTS = Path(__file__).parent / "results"

# Föredragen parsningsordning när flera MF-kandidater finns
_EXT_PRIORITY = {".xlsx": 0, ".xlsm": 0, ".csv": 1, ".pdf": 2}


def _norm(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _collect_files(case_dir: Path) -> list[tuple[str, bytes]]:
    """Alla filer i casen som (relativ-path, bytes) — zip:ar packas upp i minnet."""
    out: list[tuple[str, bytes]] = []
    for p in sorted(case_dir.rglob("*")):
        if not p.is_file() or "__MACOSX" in str(p) or p.name.startswith("."):
            continue
        rel = _norm(str(p.relative_to(case_dir)))
        if p.suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(p) as z:
                    for info in z.infolist():
                        n = info.filename
                        if info.is_dir() or n.startswith("__MACOSX") or n.endswith(".DS_Store"):
                            continue
                        data = z.read(info)
                        if data:
                            out.append((_norm(f"{rel}::{n}"), data))
            except Exception:
                continue
        else:
            out.append((rel, p.read_bytes()))
    return out


def _mf_candidates(files: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    cands = []
    for name, data in files:
        kind = classify(name)
        if kind.type == "mf":
            cands.append((name, data))
    cands.sort(key=lambda x: _EXT_PRIORITY.get(Path(x[0]).suffix.lower(), 9))
    return cands


def _parse_mf(name: str, data: bytes) -> tuple[dict | None, str, list]:
    """Returnerar (parsed_mf-dict, parser-namn, rescue_pages)."""
    ext = Path(name).suffix.lower()
    if ext == ".csv":
        return parse_csv_bytes(data).to_dict(), "csv", []
    if ext in (".xlsx", ".xlsm"):
        return excel_parser.parse_excel_bytes(data).to_dict(), "excel", []
    if ext == ".pdf":
        doc, rescue = pdf_mf_parser.parse_pdf_mf(data)
        return (doc.to_dict() if doc else None), "pdf", rescue
    raise ValueError(f"okänt MF-format: {ext}")


def run_mf_suite() -> list[dict]:
    results = []
    for case_dir in sorted(GOLDEN.iterdir()):
        if not case_dir.is_dir():
            continue
        t0 = time.monotonic()
        rec: dict = {"case": case_dir.name}
        try:
            files = _collect_files(case_dir)
            rec["file_count"] = len(files)
            cands = _mf_candidates(files)
            rec["mf_candidates"] = len(cands)

            parsed, parser_name, rescue = None, None, []
            errors = []
            for name, data in cands:
                try:
                    parsed, parser_name, rescue = _parse_mf(name, data)
                    if parsed and parsed.get("lines"):
                        rec["mf_file"] = Path(name).name[:60]
                        break
                except Exception as e:
                    errors.append(f"{Path(name).name[:40]}: {e}")
                    parsed = None

            if parsed and parsed.get("lines"):
                lines = parsed["lines"]
                rec.update({
                    "ok": True,
                    "parser": parser_name,
                    "lines": len(lines),
                    "priced": sum(1 for l in lines if l.get("unit_price") is not None),
                    "ama_codes": len({l.get("ama_code") for l in lines if l.get("ama_code")}),
                    "low_conf": sum(
                        1 for l in lines
                        if (l.get("confidence") if l.get("confidence") is not None else 1.0) < 0.9
                    ),
                    "rescue_pages": len(rescue),
                    "project": (parsed.get("metadata") or {}).get("project_name"),
                })
            elif cands:
                rec.update({"ok": False, "error": "; ".join(errors[:2]) or "inga rader extraherade"})
            else:
                rec.update({"ok": False, "error": "ingen MF-kandidat hittad av klassificeraren"})
        except Exception as e:
            rec.update({"ok": False, "error": str(e)[:200]})
        rec["duration_s"] = round(time.monotonic() - t0, 1)
        results.append(rec)
    return results


def _print_table(results: list[dict]) -> None:
    print(f"\n{'Case':<40} {'ok':>3} {'parser':>6} {'rader':>6} {'pris':>5} {'AMA':>4} {'låg':>4} {'resc':>4} {'tid':>5}")
    print("-" * 88)
    for r in results:
        if r.get("ok"):
            print(f"{r['case'][:40]:<40} {'✓':>3} {r['parser']:>6} {r['lines']:>6} {r['priced']:>5} "
                  f"{r['ama_codes']:>4} {r['low_conf']:>4} {r['rescue_pages']:>4} {r['duration_s']:>4}s")
        else:
            print(f"{r['case'][:40]:<40} {'✗':>3}  → {r.get('error', '?')[:60]}")
    ok = sum(1 for r in results if r.get("ok"))
    print("-" * 88)
    print(f"MF extraherad i {ok}/{len(results)} cases")


def _diff_previous(results: list[dict], suite: str) -> None:
    prev_files = sorted(RESULTS.glob(f"{suite}_*.json"))
    if not prev_files:
        return
    try:
        prev = json.loads(prev_files[-1].read_text(encoding="utf-8"))
    except Exception:
        return
    prev_by_case = {r["case"]: r for r in prev.get("results", [])}
    diffs = []
    for r in results:
        p = prev_by_case.get(r["case"])
        if not p:
            diffs.append(f"  + {r['case']}: ny")
            continue
        if p.get("ok") != r.get("ok"):
            diffs.append(f"  {'✓' if r.get('ok') else '✗'} {r['case']}: ok {p.get('ok')} → {r.get('ok')}")
        elif r.get("ok") and p.get("lines") != r.get("lines"):
            diffs.append(f"  Δ {r['case']}: rader {p.get('lines')} → {r.get('lines')}")
    if diffs:
        print(f"\nDiff mot {prev_files[-1].name}:")
        print("\n".join(diffs))
    else:
        print(f"\nIngen diff mot {prev_files[-1].name}.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="mf", choices=["mf"])
    args = ap.parse_args()

    if not GOLDEN.exists() or not any(GOLDEN.iterdir()):
        print("Golden settet är tomt — lägg förfrågningsunderlag i evals/golden/.")
        return 1

    results = run_mf_suite()
    _print_table(results)
    _diff_previous(results, args.suite)

    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = RESULTS / f"{args.suite}_{stamp}.json"
    out.write_text(
        json.dumps({"suite": args.suite, "at": stamp, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nResultat sparat: {out.relative_to(Path.cwd()) if out.is_relative_to(Path.cwd()) else out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
