"""
UE-mailgenerator — bygger mailutkast för att begära pris från underentreprenörer.
"""

from __future__ import annotations

from datetime import date, timedelta


def email_template(
    area: str,
    project_name: str,
    document_number: str,
    company_name: str = "Westcon Entreprenad AB",
    contact_name: str = "Lars Olsson",
    contact_email: str = "lars@westcon.se",
    contact_phone: str = "070-000 00 00",
    bid_due: str | None = None,
    relevant_codes: list[str] | None = None,
) -> dict:
    """Returnera mail-utkast som dict {subject, body, mailto}."""
    deadline = bid_due or (date.today() + timedelta(days=14)).isoformat()
    codes_text = ""
    if relevant_codes:
        codes_str = ", ".join(relevant_codes[:6])
        codes_text = f"\n\nRelevanta AMA-koder från mängdförteckningen:\n  {codes_str}\n"

    subject = f"Offertförfrågan — {area} — {project_name}"

    body = f"""Hej,

{company_name} arbetar med ett anbud för rubricerat projekt och behöver
ert á-pris och totalsumma för delen som rör {area.lower()}.

Projekt:        {project_name}
Dokumentnr:     {document_number}
Vår deadline:   {deadline}{codes_text}

Underlag bifogas (mängdförteckning + relevanta ritningar). Vänligen
återkom med:

  • À-priser per post
  • Totalsumma exklusive moms
  • Eventuella reservationer eller alternativutföranden
  • Giltighetstid för offerten

Önskas ytterligare underlag återkommer ni till mig direkt.

Med vänlig hälsning,

{contact_name}
{company_name}
{contact_email}
{contact_phone}
"""

    mailto = (
        f"mailto:?"
        f"subject={_url_encode(subject)}"
        f"&body={_url_encode(body)}"
    )

    return {
        "area": area,
        "subject": subject,
        "body": body,
        "mailto": mailto,
    }


def _url_encode(s: str) -> str:
    """Enkel URL-encoding för mailto-länkar."""
    from urllib.parse import quote
    return quote(s, safe="")


def generate_for_areas(
    areas: list[str],
    project_name: str,
    document_number: str,
    company_name: str = "Westcon Entreprenad AB",
    contact_name: str = "",
    contact_email: str = "",
    contact_phone: str = "",
    bid_due: str | None = None,
    relevant_codes: list[str] | None = None,
) -> list[dict]:
    """Generera ett mailutkast per UE-område."""
    return [
        email_template(
            area=area,
            project_name=project_name,
            document_number=document_number,
            company_name=company_name,
            contact_name=contact_name or "Lars Olsson",
            contact_email=contact_email or "lars@westcon.se",
            contact_phone=contact_phone or "070-000 00 00",
            bid_due=bid_due,
            relevant_codes=relevant_codes,
        )
        for area in areas
    ]
