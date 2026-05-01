# Lodet — anbudsverktyg

> *"I lod. Inget mer, inget mindre."*

Lodet hjälper svenska bygg- och anläggningsentreprenörer att lämna anbud snabbare och med högre precision. Ladda upp en mängdförteckning, så parsar Lodet AMA-strukturen, föreslår priser baserat på historik och levererar en redigerbar Excel-mall för granskning.

Detta repo innehåller MVP:n: en FastAPI-app som parsar svensk MF-CSV och bygger en Excel-mall i Lodets brand-format.

## Stack

- **Python 3.12** (FastAPI + Uvicorn)
- **openpyxl** för Excel-generering
- **Vanilla HTML/CSS/JS** för frontend (inga build-steg)
- Deploy: Railway via Nixpacks

## Köra lokalt

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Öppna http://127.0.0.1:8000 — dra in en CSV eller klicka på "Prova med Westcon-demo".

### Snabbtest från terminalen

```bash
# parsa demo-CSV utan webb-UI
python -m scripts.cli "examples/demo_input.csv" tmp.json
python -m scripts.cli_excel tmp.json tmp.xlsx
```

## API

| Endpoint | Metod | Innehåll |
|---|---|---|
| `/` | GET | Landningssida med uppladdning |
| `/api/parse` | POST | Multipart `file=@x.csv` → JSON-preview |
| `/api/excel` | POST | Multipart `file=@x.csv` → `.xlsx` (download) |
| `/api/example` | GET | Westcon-demo-data som JSON |
| `/api/example/excel` | POST | Excel byggd från demo |
| `/healthz` | GET | Health check (Railway) |

## Projektstruktur

```
.
├── app/
│   ├── main.py            FastAPI-rutter
│   ├── parser.py          Svensk MF-CSV → strukturerad form
│   ├── excel_builder.py   openpyxl Excel-mall
│   ├── templates/         Jinja2 HTML
│   └── static/            CSS, JS, favicon
├── examples/              Demo-data (Westcon Vägbelysning Sundborn)
├── requirements.txt
├── Procfile               Railway start command
├── railway.json           Railway build config
├── nixpacks.toml          Python 3.12 pinning
└── runtime.txt            Backup runtime hint
```

## Deploy

### Railway

```bash
railway login
railway link        # välj projekt eller skapa nytt
railway up          # deployar från denna katalog
```

Railway plockar upp `railway.json` + `nixpacks.toml` automatiskt och kör `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

### GitHub

```bash
git push origin main
```

Railway kan kopplas till repot för auto-deploy vid push.

## Roadmap

Se `lodet-teknisk-spec-v0.2.md` för fullständig spec. Nästa milstolpar:

- [ ] Excel-parser (openpyxl) utöver CSV
- [ ] PDF-parser (pdfplumber + LLM-fallback)
- [ ] AMA-referenstabell + hierarkisk matchning
- [ ] Embeddings + pgvector för semantisk sökning
- [ ] AFB-bilage-generering (anbudssumma, UE, sekretess)
- [ ] Multi-tenant + RLS i Supabase

## Licens

Proprietär. © 2026 Dennis Demirtok.
