"""
Företagsinställningar — persistent lagring av anbudsgivarens
företagsdata. Används vid generering av anbudssumma, sekretess,
missiv, UE-mejl m.m.

Lagras som en enda JSON-fil på samma volym som case-arkivet
(/data/company.json eller /tmp/lodet/company.json lokalt).
"""

from __future__ import annotations

import json
import os
from pathlib import Path


_DATA_ROOT = Path(os.getenv("LODET_DATA_DIR", "/data"))
_SETTINGS_PATH = _DATA_ROOT / "company.json"


_DEFAULTS: dict = {
    "company_name": "",
    "organisationsnummer": "",
    "contact_name": "",
    "contact_email": "",
    "contact_phone": "",
    "address": "",
    "default_customer": "",
    "logo_url": "",
    # Företagsfakta för AFB-svarsgenerering (AP5) — det svaren får citera.
    # Tomma fält → [SAKNAS]-markörer i utkasten, aldrig påhittade fakta.
    "omsattning_msek": "",        # årsomsättning
    "antal_anstallda": "",
    "certifikat": "",             # t.ex. "ISO 9001, ISO 14001, BF9K"
    "referensprojekt": "",        # fritext: lista över relevanta referensobjekt
    "nyckelpersoner": "",         # platschef/arbetsledare med erfarenhet
    "ue_policy": "",              # hur företaget arbetar med underentreprenörer
    # Standardpåslag (%) på självkostnad → anbudssumma. Per anbud kan det
    # överskridas (case.meta.paslag_procent).
    "paslag_procent": "15",
    # Inlärt UE-bibliotek (flywheel): område → {company, email}. Struktur, ej sträng.
    "ue_contacts": {},
}


# Vilka fält som är "fakta" (vs kontaktuppgifter) — styr svarsgeneratorns kontext
FACT_FIELDS = (
    "omsattning_msek", "antal_anstallda", "certifikat",
    "referensprojekt", "nyckelpersoner", "ue_policy",
)


def _ensure_path() -> Path:
    """Säkerställ att data-katalogen finns. Faller tillbaka till /tmp lokalt."""
    global _SETTINGS_PATH
    try:
        _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Verifiera skriv-tillgång
        test = _SETTINGS_PATH.parent / ".write_test"
        test.write_text("x", encoding="utf-8")
        test.unlink()
    except (OSError, PermissionError):
        fallback = Path("/tmp/lodet/company.json")
        fallback.parent.mkdir(parents=True, exist_ok=True)
        _SETTINGS_PATH = fallback
    return _SETTINGS_PATH


def get_settings() -> dict:
    """Returnera lagrade inställningar, eller defaults om inget sparats."""
    path = _ensure_path()
    if not path.exists():
        return dict(_DEFAULTS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return dict(_DEFAULTS)
        merged = dict(_DEFAULTS)
        merged.update({k: v for k, v in data.items() if k in _DEFAULTS})
        return merged
    except (OSError, json.JSONDecodeError):
        return dict(_DEFAULTS)


def save_settings(payload: dict) -> dict:
    """Skriv ut inställningar och returnera den uppdaterade strukturen."""
    path = _ensure_path()
    current = get_settings()
    for key, default in _DEFAULTS.items():
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(default, (dict, list)):
            # Struktur-fält (t.ex. ue_contacts) — spara som-är, stringifiera inte
            current[key] = value if isinstance(value, type(default)) else default
        else:
            current[key] = "" if value is None else str(value).strip()
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def is_configured() -> bool:
    """True om åtminstone företagsnamn är ifyllt."""
    s = get_settings()
    return bool(s.get("company_name"))
