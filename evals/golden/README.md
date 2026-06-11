# Golden set — riktiga förfrågningsunderlag

Lägg en mapp per förfrågningsunderlag här, döpt efter projektet:

```
evals/golden/
├── Kulturparken och Trefasgatan Kopparlunden/
│   ├── 9. AF Kulturparken och Trefasgatan.pdf
│   ├── 10.01 Mängdförteckning med teknisk beskrivning.xlsx
│   └── … (alla filer, gärna hela originalmappen rakt av)
├── Vägbelysning Rv 84/
│   └── …
└── …
```

**Vad som ska in:** 10–20 riktiga underlag med MF + AF, gärna PDF:er av
varierande kvalitet (rena exporter, skannade, trasiga tabeller). Det är
variationen som gör settet värdefullt — leta gärna upp de jobbigaste.

**Vad de används till (AP6):** eval-harnessen kör parsern + krav-
extraktionen mot varje case och jämför mot facit (`facit_mf.json`,
`facit_krav.json` per mapp). Facit byggs billigt i AP2/AP3: kör
pipelinen, rätta i granskningsvyn, exportera det godkända som facit —
dina egna rättningar är annoteringen. Du behöver alltså bara lägga in
rådokumenten; facit-filerna skapas senare i appen.

**OBS:** innehållet i den här mappen är gitignorat (riktiga
upphandlingsdokument ska inte upp på GitHub). Bara denna README följer
med i repot.
