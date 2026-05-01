"""
AFB-bilage-generering — boilerplate-mallar.

Genererar text för:
  - AFB.31 Anbudssumma
  - AFB.32 Underentreprenörer
  - Sekretessbegäran (FHL + OSL)
  - Missiv

I MVP returneras formaterad text som användaren kan kopiera.
I produktion bör dessa renderas till PDF via WeasyPrint eller liknande.
"""

from __future__ import annotations

from datetime import date


def format_sek(amount: float | None) -> str:
    if amount is None:
        return "—"
    return f"{amount:,.0f}".replace(",", " ") + " kr"


def anbudssumma(
    project_name: str,
    document_number: str,
    company_name: str,
    total_amount: float,
    contact_name: str = "",
    contact_email: str = "",
    contact_phone: str = "",
) -> str:
    return f"""AFB.31  ANBUDSSUMMA

Projekt:        {project_name}
Dokumentnr:     {document_number}
Anbudsgivare:   {company_name}

Härmed avges anbud avseende rubricerat projekt enligt
förfrågningsunderlaget med tillhörande bilagor.

Anbudssumma:    {format_sek(total_amount)} exklusive moms
Mervärdesskatt: {format_sek(total_amount * 0.25)}
Total:          {format_sek(total_amount * 1.25)} inklusive moms

Anbudet är bindande till och med 90 kalenderdagar efter
anbudstidens utgång enligt AFB.13.

Anbudsgivare:   {company_name}
Kontaktperson:  {contact_name or '________________________'}
E-post:         {contact_email or '________________________'}
Telefon:        {contact_phone or '________________________'}

Datum:          {date.today().isoformat()}

Underskrift:    ________________________________________
                Behörig firmatecknare
"""


def ue_lista(
    project_name: str,
    company_name: str,
    suggestions: list[dict] | None = None,
) -> str:
    suggestions = suggestions or [
        {"område": "Spont och pålning", "ue": "________________________", "andel": "—"},
        {"område": "Asfaltering", "ue": "________________________", "andel": "—"},
        {"område": "Bro- och vägräcken", "ue": "________________________", "andel": "—"},
        {"område": "Linjemålning", "ue": "________________________", "andel": "—"},
        {"område": "Projektering mark/bro", "ue": "________________________", "andel": "—"},
    ]

    rows = "\n".join(
        f"  • {s['område']:.<35} {s['ue']:<40} {s['andel']}"
        for s in suggestions
    )

    return f"""AFB.32  UNDERENTREPRENÖRER

Projekt:        {project_name}
Anbudsgivare:   {company_name}

Anbudsgivaren avser att anlita följande underentreprenörer
för delar av entreprenaden. Slutlig sammansättning kan
komma att justeras efter beställarens godkännande enligt
AFC.36 / AFD.36.

Område                                 UE                                       Andel av kontraktssum
{'-' * 95}
{rows}

Datum:          {date.today().isoformat()}

Underskrift:    ________________________________________
"""


def sekretessbegaran(
    project_name: str,
    document_number: str,
    company_name: str,
    organisationsnummer: str = "",
    contact_name: str = "",
) -> str:
    return f"""BEGÄRAN OM SEKRETESS

Projekt:        {project_name}
Dokumentnr:     {document_number}
Anbudsgivare:   {company_name}
Org.nr:         {organisationsnummer or '________________________'}

Med stöd av 19 kap. 3 § andra stycket samt 31 kap. 16 §
offentlighets- och sekretesslagen (2009:400) begär
{company_name} att uppgifter i bifogat anbud beläggs
med sekretess i de delar de utgör företagshemligheter
enligt 1 § lagen (2018:558) om företagshemligheter.

Följande uppgifter omfattas av begäran:

  1. Detaljerade priser per post i mängdförteckningen
  2. Påslag, marginaler och täckningsbidrag
  3. Underentreprenörers identitet och avtalsvillkor
  4. Specifika tekniska lösningar och produktval

Skäl för sekretess:
Uppgifterna är inte allmänt kända, har ekonomiskt värde
för {company_name} samt har varit föremål för åtgärder
för att hemlighållas. Spridning skulle medföra synnerlig
skada för bolagets konkurrenssituation.

Sekretessbegäran avser hela anbudshandlingens livstid
och ska bestå även efter att tilldelningsbeslut fattats.

Datum:          {date.today().isoformat()}

Kontaktperson:  {contact_name or '________________________'}
Underskrift:    ________________________________________
                Behörig firmatecknare för {company_name}
"""


def missiv(
    project_name: str,
    document_number: str,
    company_name: str,
    customer_name: str,
    contact_name: str = "",
) -> str:
    return f"""MISSIV — ANBUDSÖVERLÄMNING

Till:           {customer_name}

Avseende:       {project_name}
                Dokumentnr {document_number}

{company_name} har härmed nöjet att överlämna anbud
avseende rubricerat projekt.

Bifogade handlingar:

  1. AFB.31  Anbudssumma
  2. AFB.32  Underentreprenörer
  3. Mängdförteckning med ifyllda à-priser
  4. Begäran om sekretess
  5. Referensobjekt (AFB.33)

Anbudet är upprättat i enlighet med förfrågningsunderlaget
och tillämpliga AB / ABT 04. Vid eventuella frågor under
utvärderingen står {contact_name or 'undertecknad'} till
förfogande för förtydliganden.

Vi ser fram emot er återkoppling.

Med vänlig hälsning,

{contact_name or '________________________'}
{company_name}
Datum: {date.today().isoformat()}
"""


def list_templates() -> list[dict]:
    return [
        {
            "id": "anbudssumma",
            "code": "AFB.31",
            "title": "Anbudssumma",
            "description": "Standardblankett för totalbelopp exkl. moms enligt förfrågningsunderlaget.",
            "auto_fillable": ["project_name", "document_number", "total_amount"],
        },
        {
            "id": "ue-lista",
            "code": "AFB.32",
            "title": "Underentreprenörer",
            "description": "Förteckning över planerade underentreprenörer per teknikområde.",
            "auto_fillable": ["project_name", "suggestions"],
        },
        {
            "id": "sekretess",
            "code": "—",
            "title": "Sekretessbegäran",
            "description": "Standardbrev enligt FHL §1 och OSL 9:3 + 31:16.",
            "auto_fillable": ["project_name", "document_number"],
        },
        {
            "id": "missiv",
            "code": "—",
            "title": "Missiv",
            "description": "Följebrev som listar samtliga bilagor i anbudspaketet.",
            "auto_fillable": ["project_name", "document_number", "customer_name"],
        },
    ]
