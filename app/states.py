"""
Statemaskin för anbud (genomförandeplan AP1).

Regel: endast transition() ändrar state. FORMALIA_CHECK → READY får bara
ske via grindfunktionen i AP5 — aldrig från LLM-kod, aldrig direkt från
en endpoint.
"""

from __future__ import annotations

INTAKE = "INTAKE"                  # filer uppladdade, väntar på/under klassificering
EXTRACTING = "EXTRACTING"          # parsers + LLM-extraktion kör
NEEDS_REVIEW = "NEEDS_REVIEW"      # rader/krav under confidence-tröskel (AP2)
CALCULATING = "CALCULATING"        # kalkyl pågår (användardrivet state)
DRAFTING = "DRAFTING"              # AFB-svar genereras/redigeras
FORMALIA_CHECK = "FORMALIA_CHECK"  # deterministisk grind (AP5)
READY = "READY"                    # klart att lämna in
SUBMITTED = "SUBMITTED"
AWARDED = "AWARDED"
LOST = "LOST"

TRANSITIONS: dict[str, set[str]] = {
    INTAKE: {EXTRACTING},
    EXTRACTING: {NEEDS_REVIEW, CALCULATING},
    NEEDS_REVIEW: {CALCULATING},
    CALCULATING: {DRAFTING},
    DRAFTING: {FORMALIA_CHECK},
    FORMALIA_CHECK: {READY, DRAFTING},
    READY: {SUBMITTED},
    SUBMITTED: {AWARDED, LOST},
}

# UI-etiketter för state-chips
LABELS: dict[str, str] = {
    INTAKE: "Mottaget",
    EXTRACTING: "Analyserar",
    NEEDS_REVIEW: "Behöver granskning",
    CALCULATING: "Kalkyl",
    DRAFTING: "Utkast",
    FORMALIA_CHECK: "Formaliakontroll",
    READY: "Klart att lämna",
    SUBMITTED: "Inlämnat",
    AWARDED: "Vunnet",
    LOST: "Förlorat",
}


class IllegalTransition(Exception):
    pass


async def transition(session, case, to_state: str) -> None:
    """Enda vägen att byta state. Loggar event."""
    from app.db import log_event

    allowed = TRANSITIONS.get(case.state, set())
    if to_state not in allowed:
        raise IllegalTransition(f"{case.state} → {to_state} är inte tillåten")
    case.state = to_state
    await log_event(session, case.id, "state_change", {"to": to_state})
