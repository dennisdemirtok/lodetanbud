"""
ZIP-hantering — extrahera ZIP-filer i minnet och returnera fil-list för
nedströms paketanalys.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass


@dataclass
class ExtractedFile:
    """En fil extraherad från en ZIP eller mapp."""
    filename: str          # bara filnamnet (utan path)
    relative_path: str     # full path inom ZIP/mapp
    folder: str            # toppnivå-mapp (för gruppering)
    data: bytes


def is_zip_filename(name: str) -> bool:
    return name.lower().endswith(".zip")


def extract_zip(data: bytes) -> list[ExtractedFile]:
    """
    Extrahera en ZIP-fil till en lista av filer.
    Hoppar över macOS-skräp (__MACOSX/, .DS_Store) och tomma kataloger.
    """
    out: list[ExtractedFile] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                name = info.filename
                if info.is_dir():
                    continue
                if name.startswith("__MACOSX/") or "/.DS_Store" in name or name.endswith(".DS_Store"):
                    continue
                if name.endswith("/"):
                    continue

                file_bytes = zf.read(info)
                if not file_bytes:
                    continue

                # Plocka toppmapp om den finns
                parts = name.split("/")
                folder = parts[0] if len(parts) > 1 else ""
                filename = parts[-1]

                out.append(
                    ExtractedFile(
                        filename=filename,
                        relative_path=name,
                        folder=folder,
                        data=file_bytes,
                    )
                )
    except zipfile.BadZipFile:
        raise ValueError("Korrupt eller ogiltig ZIP-fil")

    return out


def group_by_folder(files: list[ExtractedFile]) -> dict[str, list[ExtractedFile]]:
    """Gruppera filer per toppmapp (varje mapp = ett anbud)."""
    grouped: dict[str, list[ExtractedFile]] = {}
    for f in files:
        key = f.folder or "(rotmapp)"
        grouped.setdefault(key, []).append(f)
    return grouped
