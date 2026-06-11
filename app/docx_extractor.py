"""
DOCX-textextraktion — stdlib-baserad (zipfile + regex på word/document.xml).

AF-dokument levereras ofta som .docx från kommuner (golden set: Skjutbana
Lugnet). Vi behöver bara löptexten för kravmatrisen — ingen formatering,
inga tabellstrukturer — så en beroendefri extraktion räcker.
"""

from __future__ import annotations

import html
import io
import re
import zipfile


def extract_text(data: bytes, max_chars: int = 200_000) -> str:
    """Extrahera löptext ur en .docx. Tom sträng vid fel."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    except Exception:
        return ""

    # Paragraf- och radbrytningar → riktiga radbrytningar
    xml = xml.replace("</w:p>", "\n").replace("<w:br/>", "\n").replace("<w:br />", "\n")
    # Tabbar (används ofta mellan AF-kod och rubrik)
    xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    text = html.unescape(text)
    # Normalisera överblivna entiteter och whitespace per rad
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)[:max_chars]
