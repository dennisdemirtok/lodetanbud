"""
Resursbibliotek — företagets katalog över kalkyleringsresurser.

Maskiner med förare, arbetare per kategori, material, underentreprenörer.
Används för att räkna ut à-priser per MF-rad genom att kombinera resurser
med faktor/spill/tid/mängd (likt BidCon).

Lagras som JSON på samma volym som case-arkivet.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path


_DATA_ROOT = Path(os.getenv("LODET_DATA_DIR", "/data"))
_RESOURCES_PATH = _DATA_ROOT / "resources.json"


RESOURCE_TYPES = {
    "maskin_forare":   "Maskin m. förare",
    "maskin":          "Maskin",
    "arbetare":        "Arbetare",
    "material":        "Material",
    "underentreprenor": "Underentreprenör",
    "ovrigt":          "Övrigt",
}


# Standardresurser för svenska anläggningsentreprenader
_DEFAULT_RESOURCES: list[dict] = [
    {"name": "Grävmaskin 14 ton (m. förare)", "type": "maskin_forare", "category": "Markarbeten", "unit": "tim", "cost_per_unit": 1450.0},
    {"name": "Dumper (m. förare)",            "type": "maskin_forare", "category": "Markarbeten", "unit": "tim", "cost_per_unit": 1350.0},
    {"name": "Hjullastare (m. förare)",       "type": "maskin_forare", "category": "Markarbeten", "unit": "tim", "cost_per_unit": 1400.0},
    {"name": "Vibroplatta",                   "type": "maskin",        "category": "Markarbeten", "unit": "tim", "cost_per_unit": 350.0},
    {"name": "Anläggare",                     "type": "arbetare",      "category": "Mark",        "unit": "tim", "cost_per_unit": 600.0},
    {"name": "Maskinförare",                  "type": "arbetare",      "category": "Mark",        "unit": "tim", "cost_per_unit": 620.0},
    {"name": "Elektriker",                    "type": "arbetare",      "category": "El",          "unit": "tim", "cost_per_unit": 720.0},
    {"name": "Rörmokare",                     "type": "arbetare",      "category": "VVS",         "unit": "tim", "cost_per_unit": 700.0},
    {"name": "Asfaltmassa AG 22",             "type": "material",      "category": "Beläggning",  "unit": "ton", "cost_per_unit": 1800.0},
    {"name": "Bergkross 0-32",                "type": "material",      "category": "Mark",        "unit": "ton", "cost_per_unit": 240.0},
    {"name": "Belysningsstolpe std 5m",       "type": "material",      "category": "El",          "unit": "st",  "cost_per_unit": 4200.0},
    {"name": "LED-armatur 50W",               "type": "material",      "category": "El",          "unit": "st",  "cost_per_unit": 3100.0},
    {"name": "Kabel EKKJ 4x10 mm²",           "type": "material",      "category": "El",          "unit": "m",   "cost_per_unit": 78.0},
    {"name": "Kabelskyddsrör SRE 110",        "type": "material",      "category": "El",          "unit": "m",   "cost_per_unit": 65.0},
]


def _ensure_path() -> Path:
    global _RESOURCES_PATH
    try:
        _RESOURCES_PATH.parent.mkdir(parents=True, exist_ok=True)
        test = _RESOURCES_PATH.parent / ".write_test"
        test.write_text("x", encoding="utf-8")
        test.unlink()
    except (OSError, PermissionError):
        fallback = Path("/tmp/lodet/resources.json")
        fallback.parent.mkdir(parents=True, exist_ok=True)
        _RESOURCES_PATH = fallback
    return _RESOURCES_PATH


def _new_id() -> str:
    return f"res_{int(time.time())}_{uuid.uuid4().hex[:6]}"


def _read_all() -> list[dict]:
    path = _ensure_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write_all(items: list[dict]) -> None:
    path = _ensure_path()
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def list_resources() -> list[dict]:
    """Returnera alla resurser sorterade efter typ + namn."""
    items = _read_all()
    items.sort(key=lambda r: (r.get("type", ""), r.get("name", "")))
    return items


def get_resource(resource_id: str) -> dict | None:
    for r in _read_all():
        if r.get("id") == resource_id:
            return r
    return None


def create_resource(payload: dict) -> dict:
    items = _read_all()
    new = {
        "id": _new_id(),
        "name": (payload.get("name") or "").strip(),
        "type": payload.get("type") or "ovrigt",
        "category": (payload.get("category") or "").strip(),
        "unit": (payload.get("unit") or "tim").strip(),
        "cost_per_unit": float(payload.get("cost_per_unit") or 0),
        "notes": (payload.get("notes") or "").strip(),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if not new["name"]:
        raise ValueError("Resursnamn saknas")
    if new["type"] not in RESOURCE_TYPES:
        raise ValueError(f"Okänd resurstyp: {new['type']}")
    items.append(new)
    _write_all(items)
    return new


def update_resource(resource_id: str, payload: dict) -> dict | None:
    items = _read_all()
    for i, r in enumerate(items):
        if r.get("id") == resource_id:
            for key in ("name", "type", "category", "unit", "notes"):
                if key in payload:
                    r[key] = (payload[key] or "").strip() if isinstance(payload[key], str) else payload[key]
            if "cost_per_unit" in payload:
                r["cost_per_unit"] = float(payload["cost_per_unit"] or 0)
            if r["type"] not in RESOURCE_TYPES:
                raise ValueError(f"Okänd resurstyp: {r['type']}")
            items[i] = r
            _write_all(items)
            return r
    return None


def delete_resource(resource_id: str) -> bool:
    items = _read_all()
    before = len(items)
    items = [r for r in items if r.get("id") != resource_id]
    if len(items) == before:
        return False
    _write_all(items)
    return True


def seed_defaults() -> int:
    """Lägg in standardresurser om biblioteket är tomt. Returnerar antal tillagda."""
    items = _read_all()
    if items:
        return 0
    for r in _DEFAULT_RESOURCES:
        create_resource(r)
    return len(_DEFAULT_RESOURCES)


def calculate_line(line_resources: list[dict], line_quantity: float | None) -> dict:
    """Räkna ut totalkostnad och à-pris för en MF-rad baserat på dess resurser.

    line_resources: lista av dict med:
      - resource_id eller cost_per_unit (om resursen inte är från biblioteket)
      - factor (multiplikator, default 1)
      - spill (spillfaktor, default 0 — 0.05 = 5%)
      - time (timmar/enhet)
      - quantity (mängd av resursen)
    line_quantity: total mängd för MF-raden (för att räkna à-pris)
    """
    total = 0.0
    enriched: list[dict] = []
    library = {r["id"]: r for r in _read_all()}

    for r in line_resources:
        cost_per_unit = r.get("cost_per_unit")
        if cost_per_unit is None and r.get("resource_id"):
            lib_res = library.get(r["resource_id"])
            cost_per_unit = lib_res.get("cost_per_unit") if lib_res else 0
        cost_per_unit = float(cost_per_unit or 0)

        factor = float(r.get("factor") or 1)
        spill = float(r.get("spill") or 0)  # decimal: 0.05 = 5% spillpåslag
        time_val = float(r.get("time") or 0)  # informativ tids-uppgift, ej räknande
        qty = float(r.get("quantity") or 0)  # antal enheter (t.ex. timmar för en maskin)

        # Formel: cost = factor × (1 + spill) × quantity × cost_per_unit
        # quantity är "totalantal enheter för resursen i denna MF-rad" (t.ex. antal timmar dumper kör).
        # time är ett informativt fält som hjälper användaren tänka per-enhet → totalmängd.
        if qty > 0:
            row_cost = factor * (1 + spill) * qty * cost_per_unit
        elif time_val > 0:
            row_cost = factor * (1 + spill) * time_val * cost_per_unit
        else:
            row_cost = 0.0

        total += row_cost
        enriched.append({**r, "cost_per_unit": cost_per_unit, "calculated_cost": round(row_cost, 2)})

    total = round(total, 2)
    unit_price = None
    if line_quantity and line_quantity > 0:
        unit_price = round(total / float(line_quantity), 2)

    return {
        "total_cost": total,
        "unit_price": unit_price,
        "resources": enriched,
    }
