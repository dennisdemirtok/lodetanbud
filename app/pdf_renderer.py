"""
PDF-rendering — fpdf2-baserad text→PDF för anbudsdokument.

Genererar enkla, läsbara PDFer från formaterad text. Monospace-font för
att bevara fixed-width-tabeller (t.ex. UE-listan i AFB.32).

Använder Latin-1-fonter (Helvetica/Courier inbyggt i PDF) — unicode-tecken
utanför cp1252 ersätts via _sanitize. Senare bör vi byta till Unicode TTF.
"""

from __future__ import annotations

from datetime import date

from fpdf import FPDF


_UNICODE_REPLACEMENTS = {
    "—": "-",   # — em-dash
    "–": "-",   # – en-dash
    "‒": "-",   # ‒ figure-dash
    "‐": "-",   # ‐ hyphen
    "‘": "'",   # ' left single quote
    "’": "'",   # ' right single quote
    "‚": ",",   # ‚ low single quote
    "“": '"',   # " left double quote
    "”": '"',   # " right double quote
    "„": '"',   # „ low double quote
    "•": "*",   # • bullet
    "…": "...", # … ellipsis
    "′": "'",   # ′ prime
    "″": '"',   # ″ double prime
    " ": " ",   # non-breaking space
    " ": " ",   # thin space
    " ": " ",   # narrow no-break space
    "​": "",    # zero-width space
}


def _sanitize(text: str) -> str:
    """Byt ut unicode-tecken som standard PDF-fonter saknar mot ASCII-ekvivalent."""
    if not text:
        return ""
    for src, dst in _UNICODE_REPLACEMENTS.items():
        if src in text:
            text = text.replace(src, dst)
    # Fallback: encode/decode via latin-1 med replace
    return text.encode("latin-1", "replace").decode("latin-1")


class _LodetPDF(FPDF):
    def __init__(self, title: str = "", subtitle: str = "") -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self._title = _sanitize(title)
        self._subtitle = _sanitize(subtitle)
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(left=20, top=18, right=20)

    def header(self) -> None:
        if self._title:
            self.set_font("Helvetica", "B", 11)
            self.set_text_color(28, 44, 58)  # lodbla
            self.cell(0, 6, self._title, new_x="LMARGIN", new_y="NEXT")
        if self._subtitle:
            self.set_font("Helvetica", "", 9)
            self.set_text_color(110, 110, 110)
            self.cell(0, 5, self._subtitle, new_x="LMARGIN", new_y="NEXT")
        if self._title or self._subtitle:
            self.ln(2)
            self.set_draw_color(217, 212, 201)  # linjegra
            self.line(20, self.get_y(), 190, self.get_y())
            self.ln(4)

    def footer(self) -> None:
        self.set_y(-14)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(150, 150, 150)
        self.cell(
            0,
            5,
            _sanitize(f"Genererad av Lodet - {date.today().isoformat()} - sida {self.page_no()}"),
            align="C",
        )


def text_to_pdf(text: str, title: str = "", subtitle: str = "") -> bytes:
    """Rendera fritextdokument (med fixed-width-layout) till PDF-bytes."""
    pdf = _LodetPDF(title=title, subtitle=subtitle)
    pdf.add_page()
    pdf.set_text_color(43, 43, 43)  # jarn
    pdf.set_font("Courier", "", 9.5)

    line_height = 4.6
    for raw_line in text.splitlines():
        line = _sanitize(raw_line.rstrip("\r"))
        if line.strip() == "":
            pdf.ln(line_height)
            continue
        # Använd multi_cell så långa rader bryts snyggt
        pdf.multi_cell(0, line_height, line, new_x="LMARGIN", new_y="NEXT")

    out = pdf.output()
    return bytes(out) if not isinstance(out, (bytes, bytearray)) else bytes(out)
