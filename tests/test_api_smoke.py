"""
API-röktest: uppladdning → ETT case. Hade fångat zip_names-NameError:n.
Kör mot SQLite i tmp-katalog, ingen LLM (analysen köas som jobb men
testet väntar inte på den).
"""

from __future__ import annotations

import importlib
import io
import zipfile

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LODET_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    # Reloada hela db-beroendegrafen i ordning så att db, case_archive,
    # formalia, price_engine och main alla pekar på SAMMA motor (tmp-DB).
    # Annars skriver seed till en motor och endpointen läser från en annan.
    import importlib as _il
    for name in ("app.db", "app.states", "app.worker", "app.company_settings",
                 "app.case_archive", "app.formalia", "app.price_engine",
                 "app.answer_generator", "app.agent_tools", "app.pipeline", "app.main"):
        mod = _il.import_module(name)
        _il.reload(mod)
    import app.main

    from fastapi.testclient import TestClient
    # TestClient kör lifespan (init_db + worker) via context manager
    with TestClient(app.main.app) as c:
        yield c


def _zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Testprojekt/AF.txt", "AFB.31 Anbud skall lämnas på svenska.")
        zf.writestr("Testprojekt/MF.csv", "kod;text;enhet;mängd\nDCB.313;Fyllning;m2;100")
    return buf.getvalue()


def test_zip_upload_creates_one_case(client):
    r = client.post("/api/package/analyze",
                    files=[("files", ("Testprojekt.zip", _zip_bytes(), "application/zip"))])
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["case_count"] == 1 and len(d["case_ids"]) == 1

    case_id = d["case_ids"][0]
    st = client.get(f"/api/cases/{case_id}/status")
    assert st.status_code == 200
    assert st.json()["state"] in ("INTAKE", "EXTRACTING", "NEEDS_REVIEW", "CALCULATING")


def test_mixed_zip_and_loose_files_one_case(client):
    r = client.post("/api/package/analyze", files=[
        ("files", ("Testprojekt.zip", _zip_bytes(), "application/zip")),
        ("files", ("Mapp/ritning.txt", b"R-51-1-01", "text/plain")),
    ])
    assert r.status_code == 200, r.text
    assert r.json()["case_count"] == 1  # ETT FFU = ETT anbud


def test_documents_endpoint_with_mf_lines(client):
    """Dokument-vyn: doc_type=mf måste summera MfLine.total per case.
    Hade fångat l.amount-felet (fältet heter total) — 500 i prod.
    Seedar via TestClientens egen portal så vi delar dess event-loop."""
    import anyio
    import app.db as dbmod

    async def _seed():
        async with dbmod.SessionLocal() as s:
            s.add(dbmod.Case(id="case_doc1", created_at="2026-06-13", state="CALCULATING",
                             source="zip", source_name="Testpaket", project_name="Testprojekt"))
            s.add(dbmod.Document(id="doc1", case_id="case_doc1", filename="MF.csv", doc_type="mf"))
            s.add(dbmod.MfLine(id="l1", case_id="case_doc1", position=0, ama_code="DCB.313",
                               unit="m2", quantity=100, unit_price=12, total=1200))
            s.add(dbmod.MfLine(id="l2", case_id="case_doc1", position=1, ama_code="BCB.414",
                               unit="m", quantity=50, unit_price=8, total=400))
            await s.commit()

    client.portal.call(_seed)  # kör på samma loop som appen

    r = client.get("/api/documents?doc_type=mf")
    assert r.status_code == 200, r.text
    docs = r.json()["documents"]
    mine = [d for d in docs if d["case_id"] == "case_doc1"]
    assert len(mine) == 1
    d = mine[0]
    assert d["line_count"] == 2
    assert d["total_amount_sek"] == 1600
    assert set(d["ama_codes"]) == {"DCB.313", "BCB.414"}
    assert d["project_name"] == "Testprojekt"


def test_overview_checklist(client):
    """Cockpit-översikten: checklista bockas av ur state, progress räknas,
    next_step pekar på första ej klara. En MF-rad oprissatt → prissätt ej klar."""
    import app.db as dbmod

    async def _seed():
        async with dbmod.SessionLocal() as s:
            s.add(dbmod.Case(id="case_ov1", created_at="2026-06-13", state="CALCULATING",
                             source="zip", source_name="Pkt", project_name="Övprojekt",
                             total_amount_sek=1600))
            # parsed_mf på meta så get_case returnerar det
            s.add(dbmod.MfLine(id="o1", case_id="case_ov1", position=0, ama_code="DCB.313",
                               unit="m2", quantity=100, unit_price=12, total=1200))
            s.add(dbmod.MfLine(id="o2", case_id="case_ov1", position=1, ama_code="BCB.414",
                               unit="m", quantity=50, unit_price=None, total=None))
            s.add(dbmod.Requirement(id="r1", case_id="case_ov1", position=0, kind="skall",
                                    text="A skall lämna intyg", status="unanswered"))
            await s.commit()

    client.portal.call(_seed)
    r = client.get("/api/cases/case_ov1/overview")
    assert r.status_code == 200, r.text
    ov = r.json()
    keys = {c["key"]: c for c in ov["checklist"]}
    # firma + submit alltid med; skall finns; price finns bara om parsed_mf har rader
    assert "skall" in keys and keys["skall"]["done"] is False
    assert keys["skall"]["detail"].startswith("0/1")
    assert "firma" in keys and keys["firma"]["done"] is False
    assert "submit" in keys
    assert ov["stats"]["krav_skall"] == 1
    assert ov["next_step"] is not None
    assert 0 <= ov["progress"] <= 100
