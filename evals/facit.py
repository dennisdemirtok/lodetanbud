"""
Facit-eval — jämför systemets extraktion + prisprediktion mot den RIKTIGA
kalkylen (Kalkyl & Anbud-mappen) per golden-case. Svarar på: hur mycket blir
rätt, vad missar vi, och var brister det?

    python -m evals.facit            # tabell
    python -m evals.facit --json     # maskinläsbart

Tre mått per case:
  1. MF-rad-täckning   — andel av facit-kalkylens AMA-koder vi även hittade i
                         vår parsning av FÖRFRÅGNINGSUNDERLAGETS mängdförteckning.
  2. Mängd-träff       — för matchade koder: stämmer kvantiteten (±1%)?
  3. Prisprediktion    — leave-one-out (samma kod+enhet i ANDRA projekt) →
                         median → jämfört mot facitens faktiska nettopris.
                         Per-post median-APE + total predikterad vs faktisk.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path

from app.map_kalkyl import have_mdbtools, parse_kalkyl
from evals.run import GOLDEN, _collect_files, _mf_candidates, _parse_mf


def _norm_code(c: str) -> str:
    return (c or "").strip().upper().replace(" ", "")


def _ffu_files(case_dir: Path):
    """Filer i förfrågningsunderlaget — exkludera facit-mappen (Kalkyl & Anbud)."""
    return [(n, d) for (n, d) in _collect_files(case_dir)
            if "kalkyl" not in n.lower() and "anbud" not in n.lower()]


def _our_mf_rows(case_dir: Path) -> list[dict]:
    """Vad SYSTEMET extraherar ur FFU:ns mängdförteckning."""
    cands = _mf_candidates(_ffu_files(case_dir))
    for name, data in cands:
        try:
            parsed, _p, _r = _parse_mf(name, data)
        except Exception:
            continue
        if parsed and parsed.get("lines"):
            return parsed["lines"]
    return []


def _facit_posts(case_dir: Path) -> list[dict]:
    """Facit: posterna ur den riktiga MAP-kalkylen (.mdbklk)."""
    mdbs = list(case_dir.rglob("*.mdbklk"))
    if not mdbs:
        return []
    try:
        parsed = parse_kalkyl(max(mdbs, key=lambda p: p.stat().st_size))
    except Exception:
        return []
    return [p for p in parsed["posts"] if p.get("ama_code")]


def run() -> list[dict]:
    if not have_mdbtools():
        return [{"case": "(mdbtools saknas)", "ok": False}]

    # Global prisbas för leave-one-out (kod+enhet → [(case, netto)])
    by_key: dict[tuple, list] = {}
    facit_by_case: dict[str, list[dict]] = {}
    for case_dir in sorted(GOLDEN.iterdir()):
        if not case_dir.is_dir():
            continue
        posts = _facit_posts(case_dir)
        if not posts:
            continue
        facit_by_case[case_dir.name] = posts
        for p in posts:
            if p.get("unit_price", 0) > 0:
                qty = p["total_netto"] / p["unit_price"] if p.get("total_netto") else None
                by_key.setdefault((_norm_code(p["ama_code"]), p.get("unit")), []).append(
                    (case_dir.name, p["unit_price"], qty))

    results = []
    for case_dir in sorted(GOLDEN.iterdir()):
        if not case_dir.is_dir() or case_dir.name not in facit_by_case:
            continue
        case = case_dir.name
        facit = facit_by_case[case]
        our_rows = _our_mf_rows(case_dir)

        facit_codes = Counter(_norm_code(p["ama_code"]) for p in facit)
        our_codes = Counter(_norm_code(r.get("ama_code")) for r in our_rows if r.get("ama_code"))

        matched = set(facit_codes) & set(our_codes)
        missing = set(facit_codes) - set(our_codes)   # i facit, ej extraherade
        cover = round(100 * len(matched) / len(facit_codes)) if facit_codes else 0

        # Mängd-träff för matchade koder (jämför summerad mängd per kod)
        our_qty = _qty_by_code(our_rows)
        facit_qty = _qty_by_code(facit)
        qty_ok = sum(1 for c in matched if _close(our_qty.get(c), facit_qty.get(c)))
        qty_rate = round(100 * qty_ok / len(matched)) if matched else 0

        # Prisprediktion (leave-one-out, enhetsmatchad) vs facit-netto
        errs = []
        tot_pred = tot_act = 0.0
        safe_pred = safe_act = 0.0   # bara prediktioner motorn visar som trygga (ej röda)
        for p in facit:
            if p.get("unit_price", 0) <= 0 or not p.get("total_netto"):
                continue
            qty = p["total_netto"] / p["unit_price"]
            cands = [(pr, q) for (c, pr, q) in by_key.get((_norm_code(p["ama_code"]), p.get("unit")), []) if c != case]
            # Mängd-skala-grind (speglar prismotorn): klumpsumma ≠ per-styck
            comparable = True
            if qty > 0:
                scaled = [(pr, q) for (pr, q) in cands if q is None or qty / 10 <= q <= qty * 10]
                if len(scaled) >= 2:
                    cands = scaled
                elif not scaled:
                    comparable = False  # ingen jämförbar mängdskala → ej trygg
            others = [pr for (pr, q) in cands]
            if not others:
                continue
            pred = statistics.median(others)
            errs.append(abs(pred - p["unit_price"]) / p["unit_price"])
            tot_pred += pred * qty
            tot_act += p["total_netto"]
            # "Trygg" = jämförbar skala OCH samstämmig spridning (motorns gröna/gula)
            spread = (max(others) / min(others)) if min(others) > 0 else float("inf")
            if comparable and len(others) >= 2 and spread <= 8:
                safe_pred += pred * qty
                safe_act += p["total_netto"]

        results.append({
            "case": case,
            "ok": True,
            "facit_poster": len(facit),
            "extraherade_rader": len(our_rows),
            "matchade_koder": len(matched),
            "saknade_koder": len(missing),
            "kod_tackning_pct": cover,
            "mangd_traff_pct": qty_rate,
            "pris_median_ape": round(100 * statistics.median(errs)) if errs else None,
            "total_facit": round(tot_act) if tot_act else None,
            "total_predikterat": round(tot_pred) if tot_pred else None,
            "total_avvik_pct": round(100 * (tot_pred - tot_act) / tot_act) if tot_act else None,
            "total_avvik_sakra_pct": round(100 * (safe_pred - safe_act) / safe_act) if safe_act else None,
            "sakra_andel_pct": round(100 * safe_act / tot_act) if tot_act else None,
            "topp_saknade": [c for c, _n in Counter({c: facit_codes[c] for c in missing}).most_common(5)],
        })
    return results


def _qty_by_code(rows: list[dict]) -> dict:
    out: dict[str, float] = {}
    for r in rows:
        c = _norm_code(r.get("ama_code"))
        q = r.get("quantity")
        if c and isinstance(q, (int, float)):
            out[c] = out.get(c, 0) + q
    return out


def _close(a, b, tol=0.01) -> bool:
    if a is None or b is None or b == 0:
        return a == b
    return abs(a - b) / abs(b) <= tol


def _print(results: list[dict]) -> None:
    print(f"\n{'Case':<38}{'kod%':>6}{'mängd%':>7}{'pris-APE':>9}{'total-avv':>10}{'trygg-avv':>10}{'trygg%':>7}")
    print("-" * 92)
    covers, qtys, totdevs, safedevs = [], [], [], []
    for r in results:
        if not r.get("ok"):
            print(f"{r['case'][:38]:<38}  {r.get('case','')}")
            continue
        ape = f"{r['pris_median_ape']}%" if r['pris_median_ape'] is not None else "—"
        dev = f"{r['total_avvik_pct']:+d}%" if r['total_avvik_pct'] is not None else "—"
        sdev = f"{r['total_avvik_sakra_pct']:+d}%" if r['total_avvik_sakra_pct'] is not None else "—"
        safe = f"{r['sakra_andel_pct']}%" if r['sakra_andel_pct'] is not None else "—"
        print(f"{r['case'][:38]:<38}{r['kod_tackning_pct']:>5}%{r['mangd_traff_pct']:>6}%{ape:>9}{dev:>10}{sdev:>10}{safe:>7}")
        covers.append(r['kod_tackning_pct'])
        qtys.append(r['mangd_traff_pct'])
        if r['total_avvik_pct'] is not None:
            totdevs.append(abs(r['total_avvik_pct']))
        if r['total_avvik_sakra_pct'] is not None:
            safedevs.append(abs(r['total_avvik_sakra_pct']))
    print("-" * 92)
    if covers:
        print(f"\nMEDIAN kod-täckning {statistics.median(covers):.0f}% · mängd-träff {statistics.median(qtys):.0f}%"
              f" · total-avvik {statistics.median(totdevs):.0f}% · TRYGG-avvik {statistics.median(safedevs):.0f}%" if safedevs else "")
        print("trygg-avv = total-avvikelse på bara de poster motorn visar grönt/gult (mängdjämförbara + samstämmiga)")
        print("trygg% = andel av facitsumman som faller på trygga poster (resten flaggas röd → människan sätter)")
    print("\nTolkning:")
    print("  kod% = andel av facit-kalkylens poster vi även extraherade ur FFU-MF (extraktionskvalitet)")
    print("  mängd% = av matchade koder: andel där kvantiteten stämmer (±1%)")
    print("  pris-APE = typiskt fel i förutsagt à-pris per post (leave-one-out)")
    print("  total-avvik = predikterad nettototal vs facitens — fel tar delvis ut varandra")
    # Var brister det mest?
    worst = [r for r in results if r.get("ok") and r['kod_tackning_pct'] < 90]
    if worst:
        print("\nLägst kod-täckning (extraktionen brister):")
        for r in sorted(worst, key=lambda x: x['kod_tackning_pct'])[:5]:
            print(f"  {r['case'][:40]:<40} {r['kod_tackning_pct']}% · saknar t.ex. {', '.join(r['topp_saknade'][:4]) or '—'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    results = run()
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        _print(results)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
