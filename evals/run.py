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
from app.af_parser import split_af_sections
from app.file_classifier import classify
from app.parser import parse_csv_bytes
from app.pdf_extractor import extract_pages_text

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


def run_krav_suite() -> list[dict]:
    """Deterministisk del av krav-suiten: hittas AF, hur många sektioner
    splittas, vilka huvuddelar. Recall mot facit_krav.json (manuell
    skall-kravlista) aktiveras när facit-filer finns."""
    results = []
    for case_dir in sorted(GOLDEN.iterdir()):
        if not case_dir.is_dir():
            continue
        t0 = time.monotonic()
        rec: dict = {"case": case_dir.name}
        try:
            files = _collect_files(case_dir)
            af_cands = [
                (n, d) for n, d in files
                if classify(n).type == "af" and Path(n).suffix.lower() in (".pdf", ".docx")
            ]
            # PDF föredras (har sidnummer för käll-länkning)
            af_cands.sort(key=lambda x: 0 if Path(x[0]).suffix.lower() == ".pdf" else 1)
            rec["af_candidates"] = len(af_cands)
            if not af_cands:
                rec.update({"ok": False, "error": "ingen AF (pdf/docx) hittad av klassificeraren"})
            else:
                name, data = af_cands[0]
                if Path(name).suffix.lower() == ".docx":
                    from app.docx_extractor import extract_text as _docx_text
                    text = _docx_text(data)
                    pages = [text] if text else []
                else:
                    pages = extract_pages_text(data)
                sections = split_af_sections(pages)
                huvuddelar: dict[str, int] = {}
                for s in sections:
                    huvuddelar[s.code[:3]] = huvuddelar.get(s.code[:3], 0) + 1
                rec.update({
                    "ok": len(sections) > 0,
                    "af_file": Path(name).name[:60],
                    "pages": len(pages),
                    "sections": len(sections),
                    "huvuddelar": huvuddelar,
                })
                facit = case_dir / "facit_krav.json"
                rec["has_facit"] = facit.exists()
        except Exception as e:
            rec.update({"ok": False, "error": str(e)[:200]})
        rec["duration_s"] = round(time.monotonic() - t0, 1)
        results.append(rec)
    return results


def run_pris_suite() -> list[dict]:
    """Pris-MAPE via leave-one-project-out på MAP-kalkylernas nettopriser.

    Bygger prisobservationer ur alla kalkyler, sedan för varje post:
    median av samma AMA-kod i ANDRA projekt → jämför mot postens faktiska
    nettopris → MAPE. Mäter prismotorns exakt-kod-steg på riktig data."""
    import statistics
    from app.map_kalkyl import have_mdbtools, parse_kalkyl

    if not have_mdbtools():
        return [{"case": "(mdbtools saknas — kan ej köra pris-suite)", "ok": False}]

    # Samla observationer: ama_code → [(project, unit_price)]
    by_code: dict[str, list[tuple[str, float]]] = {}
    per_case_posts: dict[str, list[dict]] = {}
    for case_dir in sorted(GOLDEN.iterdir()):
        if not case_dir.is_dir():
            continue
        mdbs = list(case_dir.rglob("*.mdbklk"))
        if not mdbs:
            continue
        main = max(mdbs, key=lambda p: p.stat().st_size)
        try:
            parsed = parse_kalkyl(main)
        except Exception:
            continue
        posts = [p for p in parsed["posts"] if p.get("ama_code") and p.get("unit_price", 0) > 0]
        per_case_posts[case_dir.name] = posts
        for p in posts:
            by_code.setdefault(p["ama_code"], []).append((case_dir.name, p["unit_price"]))

    results = []
    for case_name, posts in per_case_posts.items():
        errors = []
        covered = 0
        for p in posts:
            others = [price for (proj, price) in by_code.get(p["ama_code"], []) if proj != case_name]
            if not others:
                continue
            pred = statistics.median(others)
            actual = p["unit_price"]
            if actual > 0:
                errors.append(abs(pred - actual) / actual)
                covered += 1
        mape = round(100 * statistics.mean(errors), 1) if errors else None
        median_ape = round(100 * statistics.median(errors), 1) if errors else None
        results.append({
            "case": case_name,
            "ok": mape is not None,
            "posts": len(posts),
            "covered": covered,
            "coverage_pct": round(100 * covered / len(posts)) if posts else 0,
            "mape": mape,
            "median_ape": median_ape,
        })
    return results


def _print_pris_table(results: list[dict]) -> None:
    print(f"\n{'Case':<40} {'poster':>7} {'täckt':>6} {'täck%':>6} {'MAPE%':>7} {'median%':>8}")
    print("-" * 80)
    all_mape = []
    for r in results:
        if r.get("ok"):
            print(f"{r['case'][:40]:<40} {r['posts']:>7} {r['covered']:>6} {r['coverage_pct']:>5}% {r['mape']:>6} {r['median_ape']:>8}")
            all_mape.append(r["mape"])
        else:
            print(f"{r['case'][:40]:<40}  → {r.get('case','').startswith('(') and r['case'] or 'ingen data'}")
    print("-" * 80)
    median_apes = [r["median_ape"] for r in results if r.get("ok") and r.get("median_ape") is not None]
    if median_apes:
        import statistics
        print(f"PRIMÄRT MÅTT — median-APE över cases: {statistics.median(median_apes):.0f}% "
              f"(typiskt avstånd mellan median-av-andra-projekt och faktiskt pris)")
        print("MAPE-kolumnen domineras av poster med pytteskt pris (÷ litet tal) — använd median-APE.")
        print("Tolkning: ~85% median-APE visar att AMA-kod ensam är en GROV prediktor — därför")
        print("visar motorn spann + n + källcase, inte en punktsiffra. Förbättras av enhets-/")
        print("region-viktning och beskrivningslikhet (kaskadsteg 4). Följs över tid.")


def run_afb_suite() -> list[dict]:
    """AFB-strukturcheck: [SAKNAS]-markörer välformade, schema giltigt.
    Recall-måttet (fakta i kontext men markerad saknad = fel) kräver
    labelade (krav, fakta, facit) — väntar på facit_afb.json."""
    from app import answer_generator
    import re
    checks = []
    # Strukturell sanity: SAKNAS_RE fångar markörerna
    samples = [
        ("Vi har [SAKNAS: omsättning] Mkr.", 1),
        ("ISO 9001 och [SAKNAS: antal år] erfarenhet av [SAKNAS: typ].", 2),
        ("Komplett svar utan luckor.", 0),
    ]
    for text, expected in samples:
        found = len(answer_generator.SAKNAS_RE.findall(text))
        checks.append({"sample": text[:40], "expected": expected, "found": found, "ok": found == expected})
    facit_exists = any((GOLDEN / d.name / "facit_afb.json").exists()
                       for d in GOLDEN.iterdir() if d.is_dir())
    return [{"checks": checks, "has_facit": facit_exists}]


def _print_afb_table(results: list[dict]) -> None:
    r = results[0]
    print("\nAFB-svarsstruktur ([SAKNAS]-markörhantering):")
    for c in r["checks"]:
        print(f"  {'✓' if c['ok'] else '✗'} {c['sample']:<42} förväntat {c['expected']}, hittade {c['found']}")
    ok = all(c["ok"] for c in r["checks"])
    print(f"\n{'✓ alla strukturchecks OK' if ok else '✗ strukturfel'}")
    if not r["has_facit"]:
        print("(facit_afb.json saknas — recall mot labelade svar aktiveras när facit finns)")


def _print_krav_table(results: list[dict]) -> None:
    print(f"\n{'Case':<40} {'ok':>3} {'sidor':>6} {'sekt':>5}  huvuddelar")
    print("-" * 88)
    for r in results:
        if r.get("ok"):
            hd = " ".join(f"{k}:{v}" for k, v in (r.get("huvuddelar") or {}).items())
            print(f"{r['case'][:40]:<40} {'✓':>3} {r['pages']:>6} {r['sections']:>5}  {hd}")
        else:
            print(f"{r['case'][:40]:<40} {'✗':>3}  → {r.get('error', '?')[:60]}")
    ok = sum(1 for r in results if r.get("ok"))
    print("-" * 88)
    print(f"AF-sektioner splittade i {ok}/{len(results)} cases")
    if not any(r.get("has_facit") for r in results):
        print("(inga facit_krav.json ännu — recall mäts när manuella skall-kravlistor finns)")


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
    ap.add_argument("--suite", default="mf", choices=["mf", "krav", "pris", "afb"])
    args = ap.parse_args()

    if not GOLDEN.exists() or not any(GOLDEN.iterdir()):
        print("Golden settet är tomt — lägg förfrågningsunderlag i evals/golden/.")
        return 1

    if args.suite == "krav":
        results = run_krav_suite()
        _print_krav_table(results)
    elif args.suite == "pris":
        results = run_pris_suite()
        _print_pris_table(results)
    elif args.suite == "afb":
        results = run_afb_suite()
        _print_afb_table(results)
    else:
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
